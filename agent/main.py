"""Job agent: fetch -> filter -> score (ATS) -> AI screening -> tailor CV + cover letter -> Telegram + dashboard.

Usage:
  python -m agent.main                 # normal run (what the scheduler calls)
  python -m agent.main --dry-run       # print matches, send nothing, don't mark as seen
  python -m agent.main --chat-id       # find your Telegram chat id during setup
  python -m agent.main --test-telegram # send a test message
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from collections import Counter
from contextlib import contextmanager
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import yaml

from . import dashboard, enrich, gmail, llm, screen, sources, tailor, telegram
from .match import find_cv, load_cv, score_jobs, written_in
from .sources import Job, fetch_all

ROOT = Path(__file__).resolve().parent.parent
STATE = ROOT / "state" / "seen.json"
OUT = ROOT / "output"
KIND_ICON = {"job": "💼", "internship": "🎓", "fellowship": "🌍", "event": "✈️"}
FIT_RANK = {"Excellent": 3, "Very good": 2, "Good": 1}
SEEN_DAYS = 90


def load_env() -> None:
    """Reads KEY=VALUE lines from .env (local runs). Real environment variables always win."""
    env = ROOT / ".env"
    if env.exists():
        for line in env.read_text(encoding="utf-8").splitlines():
            if "=" in line and not line.strip().startswith("#"):
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


@contextmanager
def phase(name: str):
    t0 = time.perf_counter()
    yield
    print(f"[{name}: {time.perf_counter() - t0:.1f}s]", flush=True)


def now_iso() -> str:
    return datetime.now(UTC).isoformat()


# ---------------------------------------------------------------- seen-state (no duplicate alerts)
def load_seen() -> dict:
    return json.loads(STATE.read_text(encoding="utf-8")) if STATE.exists() else {}


def save_seen(seen: dict) -> None:
    cutoff = (datetime.now(UTC) - timedelta(days=SEEN_DAYS)).isoformat()
    seen = {k: v for k, v in seen.items() if v >= cutoff}
    STATE.parent.mkdir(exist_ok=True)
    STATE.write_text(json.dumps(seen, indent=0, sort_keys=True), encoding="utf-8")


def dedupe_key(j: Job) -> str:
    return f"{j.title.lower().strip()}|{j.company.lower().strip()}"


def new_jobs(jobs: list[Job], seen: dict) -> list[Job]:
    """Postings never alerted before, one per (title, company)."""
    fresh, keys = [], set()
    for j in jobs:
        k = dedupe_key(j)
        if j.id in seen or k in seen or k in keys:
            continue
        keys.add(k)
        fresh.append(j)
    return fresh


def deadline_passed(j: Job, today: str) -> bool:
    dl = enrich.deadline_strict(j.description)
    return bool(dl) and dl < today


# ---------------------------------------------------------------- Telegram card
def format_card(j: Job, ai: dict | None) -> str:
    e = telegram.esc
    lines = [
        f"<b>{e(j.category or KIND_ICON.get(j.kind, '💼'))}</b>",
        f"<b>{e(j.title)}</b>",
        (f"🏢 {e(j.company)}  ·  " if j.company else "") + f"📍 {e(j.location or 'n/a')}  ·  {e(j.work_mode)}"
        + (f"  ·  ⏱ {e(j.employment)}" if j.employment else ""),
        f"🎯 Match <b>{j.score:.0f}/100</b>"
        + (f"  ·  ATS keywords <b>{j.ats:.0f}%</b>" if j.kind != "fellowship" or j.ats else "")
        + (f" → ~{e(ai.get('ats_score_estimate'))}% after tailoring" if ai and ai.get("ats_score_estimate") else ""),
    ]
    if j.check:
        visa = {"none": "no visa needed", "offered": "visa sponsorship offered", "needed": "visa needed",
                "blocked": "no sponsorship"}.get(j.check.get("visa", ""), "")
        lines.append(f"🤖 Chance <b>{e(j.check.get('chance', 0))}%</b> — {e(j.check.get('why', ''))}"
                     + (f" · 🛂 {visa}" if visa else ""))
    if j.salary:
        lines.append(f"💰 {e(j.salary)}")
    if j.posted:
        lines.append(f"🗓 posted {j.posted:%d %b %Y}  ·  via {e(j.source)}")
    if j.matched:
        lines.append(f"✅ You have: {e(', '.join(j.matched[:10]))}")
    if j.missing:
        lines.append(f"❌ Missing: {e(', '.join(j.missing[:10]))}")
    if ai and ai.get("fit_summary"):
        lines.append(f"\n🧠 {e(ai['fit_summary'])}")
    tips = tailor._listify(ai.get("boost_tips")) if ai else tailor.basic_tips(j)
    if tips:
        lines.append("\n<b>Boost your application:</b>")
        lines += [f"• {e(t)}" for t in tips[:6]]
    return "\n".join(lines)


# ---------------------------------------------------------------- phases
def screen_new(matches: list[Job], cfg: dict) -> tuple[list[Job], list[Job]]:
    """AI-reads each new match against her real profile. Returns (kept, dropped); unscreened ones are kept
    (they are screened on a later run before being alerted)."""
    verdicts = screen.screen([dashboard.record(j, None) for j in matches[:cfg.get("screen_new_per_run", 200)]])
    for j in matches:
        j.check = verdicts.get(j.id)
    dropped = [j for j in matches if j.check is not None and not screen.passes(j.check)]
    kept = [j for j in matches if j.check is None or screen.passes(j.check)]
    kept.sort(key=lambda j: ((j.check or {}).get("chance", 0), j.score), reverse=True)
    print(f"AI screening: {len(verdicts)} checked, {len(dropped)} dropped as irrelevant or out of reach")
    return kept, dropped


def send_alerts(top: list[Job], cv_text: str, cfg: dict, send: bool) -> tuple[dict, set[str]]:
    """Writes kits for the best ones and sends the cards. Returns (kits by id, ids delivered)."""
    if send and top:
        summary = "\n".join(f"{c}: {n}" for c, n in Counter(j.category for j in top).items())
        telegram.send_text(f"🔔 <b>{len(top)} new matches</b> — {datetime.now():%d %b %H:%M}\n{telegram.esc(summary)}")
    ai_limit = cfg.get("max_ai_tailoring_per_run", 5)
    tailored: dict = {}
    delivered: set[str] = set()
    for i, j in enumerate(top):
        ai = tailor.generate(j, cv_text, cfg) if i < ai_limit else None
        tailored[j.id] = ai
        card = format_card(j, ai)
        print("\n" + "-" * 60 + "\n" + card.replace("<b>", "").replace("</b>", "") + f"\n{j.url}")
        if not send:
            delivered.add(j.id)
            continue
        try:
            telegram.send_text(card, url=j.url)
            for f in tailor.write_docs(j, ai, OUT) if ai else []:
                telegram.send_file(f, caption=("✍️ Cover letter" if "Cover" in f.name else "📄 ATS CV tailored for this job")
                                   + f" — {j.title[:60]}")
            delivered.add(j.id)
        except Exception as ex:
            print(f"   telegram error: {ex}")  # not marked seen -> retried next run
    return tailored, delivered


def backfill_screening(listings: dict, cfg: dict) -> None:
    """Screens older listings that were never checked; removes the ones that don't fit."""
    todo = [r for r in listings.values() if "check" not in r][:cfg.get("screen_backfill_per_run", 120)]
    if not todo:
        return
    verdicts = screen.screen(todo)
    gone = 0
    for k, v in verdicts.items():
        if screen.passes(v):
            listings[k]["check"] = v
        else:
            listings.pop(k, None)
            gone += 1
    print(f"AI screening of older listings: {len(verdicts)} checked, {gone} removed")


def backfill_kits(listings: dict, cv_text: str, cfg: dict) -> None:
    """Older good matches without an apply kit get one (best chance first; one kit per duplicate posting)."""
    limit = cfg.get("max_backfill_kits_per_run", 0)
    if not limit:
        return
    have = {dashboard._dupe_key(r) for r in listings.values() if "ai" in r}
    todo = sorted((r for r in listings.values() if "ai" not in r and r.get("check") and r.get("kind") != "event"),
                  key=lambda r: ((r.get("check") or {}).get("chance", 0), FIT_RANK.get(r.get("fit"), 0)), reverse=True)
    picked, keys = [], set(have)
    for r in todo:
        k = dashboard._dupe_key(r)
        if k not in keys:
            keys.add(k)
            picked.append(r)
        if len(picked) >= limit:
            break
    for r in picked:
        jb = Job(id=r["id"], title=r["title"], company=r.get("company", ""), url=r["url"],
                 description=r.get("description", ""), location=r.get("location", ""), kind=r.get("kind", "job"),
                 work_mode=r.get("mode", "remote"), category=r.get("category", ""),
                 matched=r.get("matched", []), missing=r.get("missing", []))
        ai = tailor.generate(jb, cv_text, cfg)
        if ai:
            listings[r["id"]] = {**r, "ai": dashboard.record(jb, ai)["ai"]}
            print(f"  kit backfilled: {r['title'][:60]}")


def prune(listings: dict, cfg: dict, today: str) -> int:
    """Removes listings past their deadline, taken down by the company, or written in a language she doesn't speak."""
    banned = cfg.get("filters", {}).get("exclude_required_languages", [])
    removed = 0
    for k in list(listings):
        r = listings[k]
        dl = enrich.apply(dict(r)).get("deadline") or ""
        board = "-".join(k.split("-")[:2])
        lang = written_in(f"{r.get('title', '')} {r.get('description', '')}")
        if (dl and dl < today) or (board in sources.BOARDS_OK and k not in sources.LIVE_IDS) or (lang and lang in banned):
            del listings[k]
            removed += 1
    return removed


def run(dry: bool = False) -> int:
    load_env()
    cfg = yaml.safe_load((ROOT / "config.yaml").read_text(encoding="utf-8"))
    if (ROOT / "cv" / "profile.txt").exists():  # private profile, kept encrypted in cv.enc
        cfg["profile"] = (ROOT / "cv" / "profile.txt").read_text(encoding="utf-8")
    cv_text = load_cv(find_cv(ROOT / "cv"))
    print(f"CV loaded ({len(cv_text)} chars). AI writing: {'ON' if llm.available() else 'OFF (no free key set)'}")
    today = date.today().isoformat()

    with phase("fetch"):
        print("Fetching opportunities…", flush=True)
        jobs = fetch_all(cfg)
    seen = load_seen()
    fresh = new_jobs(jobs, seen)
    print(f"{len(jobs)} fetched, {len(fresh)} new")

    curated = [j for j in jobs if j.source.startswith("Curated") and not deadline_passed(j, today)]
    with phase("score"):
        matches = score_jobs([j for j in fresh if not j.source.startswith("Curated")], cv_text, cfg)
    with phase("screen"):
        matches, dropped = screen_new(matches, cfg)
    stamp = now_iso()
    if not dry:
        for j in dropped:  # never look at them again
            seen[j.id] = stamp
    matches = [j for j in curated if j.id not in seen] + matches
    limit = cfg.get("max_alerts_per_run", 8)
    top = [j for j in matches if j.check][:limit]  # only screened ones go to Telegram
    print(f"{len(matches)} match your profile; sending top {len(top)}")

    send = telegram.configured() and not dry
    if not dry and not telegram.configured():
        print("!! TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID not set — printing only.")
    with phase("alerts"):
        tailored, delivered = send_alerts(top, cv_text, cfg, send)
    if not dry:
        for j in top:
            if j.id in delivered:
                seen[j.id] = seen[dedupe_key(j)] = stamp

    if dashboard.enabled() and not dry:
        with phase("dashboard"):
            listings = dashboard.load()
            for j in curated + matches:  # every match goes on the website, even beyond the Telegram limit
                dashboard.upsert(listings, dashboard.record(j, tailored.get(j.id)))
            backfill_screening(listings, cfg)
            backfill_kits(listings, cv_text, cfg)
            print(f"Removed {prune(listings, cfg, today)} expired or closed listings")
            dashboard.save(listings)
            notify = (lambda text, link: telegram.send_text(text, url=link, button="📧 Open in Gmail")) if send else None
            responses = gmail.check(listings, notify)
            print(f"Dashboard: {len(listings)} listings -> {dashboard.build(listings, cv_text, cfg, responses)}")
    elif not dashboard.enabled():
        print("Dashboard skipped: set DASHBOARD_PASSWORD to build the website.")

    if not dry:
        # Non-matches are remembered so they aren't re-scored forever. Matches not delivered yet (beyond this
        # run's limit, not screened yet, or a Telegram error) stay unseen and are retried next run.
        pending = {j.id for j in matches if j.id not in delivered}
        for j in fresh:
            if j.id not in pending:
                seen.setdefault(j.id, stamp)
        save_seen(seen)
    if send and not top and cfg.get("notify_when_empty", False):
        telegram.send_text("😴 No new matching opportunities this round.")
    return 0


def main() -> None:
    for stream in (sys.stdout, sys.stderr):  # emoji-safe output on Windows consoles
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--chat-id", action="store_true")
    ap.add_argument("--test-telegram", action="store_true")
    a = ap.parse_args()
    load_env()
    if a.chat_id:
        telegram.find_chat_id()
        return
    if a.test_telegram:
        telegram.send_text("✅ Job agent is connected! You'll get matches here.")
        print("sent")
        return
    sys.exit(run(dry=a.dry_run))


if __name__ == "__main__":
    main()
