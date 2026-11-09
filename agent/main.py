"""Job agent: fetch -> filter -> score (ATS) -> tailor CV + cover letter -> Telegram.

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
from datetime import datetime, timedelta, timezone
from pathlib import Path

import yaml

from . import dashboard, gmail, llm, tailor, telegram
from .match import find_cv, load_cv, score_jobs
from .sources import Job, fetch_all

ROOT = Path(__file__).resolve().parent.parent
STATE = ROOT / "state" / "seen.json"
OUT = ROOT / "output"
KIND_ICON = {"job": "💼", "internship": "🎓", "fellowship": "🌍"}


def load_env():
    env = ROOT / ".env"
    if env.exists():
        for line in env.read_text(encoding="utf-8").splitlines():
            if "=" in line and not line.strip().startswith("#"):
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


def load_seen() -> dict:
    if STATE.exists():
        return json.loads(STATE.read_text(encoding="utf-8"))
    return {}


def save_seen(seen: dict) -> None:
    cutoff = (datetime.now(timezone.utc) - timedelta(days=90)).isoformat()
    seen = {k: v for k, v in seen.items() if v >= cutoff}
    STATE.parent.mkdir(exist_ok=True)
    STATE.write_text(json.dumps(seen, indent=0, sort_keys=True), encoding="utf-8")


def dedupe_key(j) -> str:
    return f"{j.title.lower().strip()}|{j.company.lower().strip()}"


def format_card(j, ai: dict | None) -> str:
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
    if j.salary:
        lines.append(f"💰 {e(j.salary)}")
    if j.posted:
        lines.append(f"🗓 posted {j.posted:%d %b %Y}  ·  via {e(j.source)}")
    if j.matched:
        lines.append(f"✅ You have: {e(', '.join(j.matched[:10]))}")
    if j.missing:
        lines.append(f"❌ Missing: {e(', '.join(j.missing[:10]))}")
    if ai:
        if ai.get("fit_summary"):
            lines.append(f"\n🧠 {e(ai['fit_summary'])}")
        tips = tailor._listify(ai.get("boost_tips"))
    else:
        tips = tailor.basic_tips(j)
    if tips:
        lines.append("\n<b>Boost your application:</b>")
        lines += [f"• {e(t)}" for t in tips[:6]]
    return "\n".join(lines)


def run(dry: bool = False) -> int:
    load_env()
    cfg = yaml.safe_load((ROOT / "config.yaml").read_text(encoding="utf-8"))
    if (ROOT / "cv" / "profile.txt").exists():  # private profile, kept encrypted in cv.enc
        cfg["profile"] = (ROOT / "cv" / "profile.txt").read_text(encoding="utf-8")
    cv_text = load_cv(find_cv(ROOT / "cv"))
    print(f"CV loaded ({len(cv_text)} chars). AI writing: {'ON' if llm.available() else 'OFF (no free key set)'}")

    print("Fetching opportunities…")
    jobs = fetch_all(cfg)
    seen = load_seen()
    fresh, keys = [], set()
    for j in jobs:
        k = dedupe_key(j)
        if j.id in seen or k in seen or k in keys:
            continue
        keys.add(k)
        fresh.append(j)
    print(f"{len(jobs)} fetched, {len(fresh)} new")

    matches = score_jobs(fresh, cv_text, cfg)
    limit = cfg.get("max_alerts_per_run", 8)
    ai_limit = cfg.get("max_ai_tailoring_per_run", 5)
    top = matches[:limit]
    print(f"{len(matches)} match your profile; sending top {len(top)}")

    send = telegram.configured() and not dry
    if not dry and not telegram.configured():
        print("!! TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID not set — printing only.")

    now = datetime.now(timezone.utc).isoformat()
    if send and top:
        from collections import Counter
        counts = Counter(j.category for j in top)
        summary = "\n".join(f"{c}: {n}" for c, n in counts.items())
        telegram.send_text(f"🔔 <b>{len(top)} new matches</b> — {datetime.now():%d %b %H:%M}\n{telegram.esc(summary)}")
    tailored: dict = {}
    for i, j in enumerate(top):
        ai =tailor.generate(j, cv_text, cfg) if i < ai_limit else None
        tailored[j.id] = ai
        card = format_card(j, ai)
        print("\n" + "-" * 60 + "\n" + card.replace("<b>", "").replace("</b>", "") + f"\n{j.url}")
        files = tailor.write_docs(j, ai, OUT) if ai else []
        if send:
            try:
                telegram.send_text(card, url=j.url)
                for f in files:
                    telegram.send_file(f, caption=("✍️ Cover letter" if "Cover" in f.name else "📄 ATS CV tailored for this job")
                                       + f" — {j.title[:60]}")
            except Exception as ex:
                print(f"   telegram error: {ex}")
                continue  # not marked seen → retried next run
        if not dry:
            seen[j.id] = now
            seen[dedupe_key(j)] = now
    if dashboard.enabled() and not dry:
        listings = dashboard.load()
        for j in matches:  # every match goes on the website, even beyond the Telegram limit
            dashboard.upsert(listings, dashboard.record(j, tailored.get(j.id)))
        # backfill: older good matches that still have no apply kit (best fit first)
        rank = {"Excellent": 3, "Very good": 2, "Good": 1}
        todo = sorted((r for r in listings.values() if "ai" not in r and r.get("fit")),
                      key=lambda r: (rank.get(r.get("fit"), 0), r.get("score", 0)), reverse=True)
        have = {(r["title"].lower(), r.get("company", "").lower()) for r in listings.values() if "ai" in r}
        uniq, keys = [], set()
        for r in todo:  # the same posting can appear twice (two sources): build its kit once
            k = (r["title"].lower(), r.get("company", "").lower())
            if k not in have and k not in keys:
                keys.add(k)
                uniq.append(r)
        for r in uniq[:cfg.get("max_backfill_kits_per_run", 0)]:
            jb = Job(id=r["id"], title=r["title"], company=r.get("company", ""), url=r["url"],
                     description=r.get("description", ""), location=r.get("location", ""), kind=r.get("kind", "job"),
                     work_mode=r.get("mode", "remote"), category=r.get("category", ""),
                     matched=r.get("matched", []), missing=r.get("missing", []))
            ai = tailor.generate(jb, cv_text, cfg)
            if ai:
                upd = dict(r)
                upd["ai"] = dashboard.record(jb, ai)["ai"]
                listings[r["id"]] = upd
                print(f"  kit backfilled: {r['title'][:60]}")
        dashboard.save(listings)
        notify = (lambda text, link: telegram.send_text(text, url=link, button="📧 Open in Gmail")) if send else None
        responses = gmail.check(listings, notify)
        print(f"Dashboard: {len(listings)} listings -> {dashboard.build(listings, cv_text, cfg, responses)}")
    elif not dashboard.enabled():
        print("Dashboard skipped: set DASHBOARD_PASSWORD to build the website.")
    if not dry:
        # remember non-matches so they aren't re-scored forever; good matches that didn't fit
        # in this run's limit stay unseen and are sent next run
        later = {j.id for j in matches[limit:]}
        for j in fresh:
            if j.id not in later:
                seen.setdefault(j.id, now)
        save_seen(seen)
    if send and not top and cfg.get("notify_when_empty", False):
        telegram.send_text("😴 No new matching opportunities this round.")
    return 0


def main():
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
        return telegram.find_chat_id()
    if a.test_telegram:
        telegram.send_text("✅ Job agent is connected! You'll get matches here.")
        return print("sent")
    sys.exit(run(dry=a.dry_run))


if __name__ == "__main__":
    main()
