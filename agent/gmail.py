"""Reads replies to your applications from Gmail (IMAP + app password), classifies them with the free AI
(confirmation / interview / assessment / rejection / offer / info request) and links them to listings.

Needs GMAIL_ADDRESS and GMAIL_APP_PASSWORD (Google account > Security > 2-Step Verification > App passwords).
Read-only: the agent never sends, deletes or marks emails as read.
"""
from __future__ import annotations

import email
import html
import hashlib
import imaplib
import json
import os
import re
import urllib.parse
from datetime import datetime, timedelta, timezone
from email.header import decode_header, make_header
from email.utils import parsedate_to_datetime
from pathlib import Path

from . import llm, secure

ROOT = Path(__file__).resolve().parent.parent
SEEN = ROOT / "state" / "gmail_seen.json"
STORE = ROOT / "state" / "responses.enc"

JOBISH = re.compile(
    r"applica|applying|candida|interview|entretien|assessment|coding (test|challenge)|take[- ]home|position|"
    r"\brole\b|recruit|hiring|talent|unfortunately|regret|not (be )?moving forward|other candidates|offer|next steps|"
    r"thank you for (your )?(interest|applying)|greenhouse|lever\.co|workable|ashby|smartrecruiters|teamtailor|"
    r"recruitee|bamboohr|personio|workday|jobvite|icims|fellowship|scholarship|internship|stage\b|shortlist|selected",
    re.I)
TYPES = ["confirmation", "interview", "assessment", "rejection", "offer", "info_request", "other"]
ICON = {"confirmation": "📨", "interview": "🗣", "assessment": "🧪", "rejection": "✖", "offer": "🎉",
        "info_request": "❓", "other": "✉️"}

PROMPT = """You sort a job seeker's emails. For each email decide if it is a reply about one of HER applications.
Types: "confirmation" (application received), "interview" (invitation/scheduling), "assessment" (test, task,
questionnaire), "rejection", "offer", "info_request" (they need documents/answers), "other" (newsletters, job alerts,
marketing, unrelated, LinkedIn/Indeed recommendation emails).
Known applications (id | company | title):
{listings}

Emails:
{emails}

Return ONLY JSON: {{"results": [ {{"i": <email number>, "type": one of {types}, "company": "<company name or ''>",
"listing_id": "<id from the known list if it clearly matches, else ''>", "summary": "<1 sentence>",
"action": "<what she should do next, or ''>", "due": "<YYYY-MM-DD if a date/deadline is given, else ''>"}} ]}}"""


def configured() -> bool:
    return bridge_configured() or bool(os.getenv("GMAIL_ADDRESS") and os.getenv("GMAIL_APP_PASSWORD"))


def bridge_configured() -> bool:
    return bool(os.getenv("GMAIL_WEBAPP_URL", "").startswith("https://") and os.getenv("GMAIL_WEBAPP_KEY"))


def fetch_bridge(days_first_run: int = 30) -> list[dict]:
    """Reads job-reply emails through the Apps Script bridge running in the user's own Google account."""
    import requests
    seen = _load_seen()
    days = days_first_run
    if seen.get("last"):
        days = max(2, (datetime.now(timezone.utc) - datetime.fromisoformat(seen["last"])).days + 2)
    r = requests.get(os.environ["GMAIL_WEBAPP_URL"], params={"key": os.environ["GMAIL_WEBAPP_KEY"], "days": days},
                     timeout=90, allow_redirects=True)
    r.raise_for_status()
    data = r.json()
    if data.get("error"):
        raise RuntimeError(f"bridge said: {data['error']}")
    known, out = set(seen.get("ids", [])), []
    for m in data.get("emails", []):
        mid = (m.get("msgid") or "").strip()
        key = hashlib.sha1((mid or f"{m.get('date')}{m.get('subject')}").encode()).hexdigest()[:16]
        if key in known:
            continue
        known.add(key)
        if not JOBISH.search(f"{m.get('from', '')} {m.get('subject', '')} {m.get('body', '')[:3000]}"):
            continue
        out.append({"key": key, "msgid": mid, "from": m.get("from", ""), "subject": m.get("subject", ""),
                    "date": m.get("date") or datetime.now(timezone.utc).isoformat(), "body": m.get("body", "")[:2500]})
    seen["ids"] = list(known)[-3000:]
    seen["last"] = datetime.now(timezone.utc).isoformat()
    SEEN.write_text(json.dumps(seen), encoding="utf-8")
    return out


def _dec(v) -> str:
    try:
        return str(make_header(decode_header(v or "")))
    except Exception:
        return v or ""


def _body(msg) -> str:
    parts = msg.walk() if msg.is_multipart() else [msg]
    text, html = "", ""
    for p in parts:
        ct = p.get_content_type()
        if p.get_content_disposition() == "attachment":
            continue
        try:
            payload = p.get_payload(decode=True)
            if payload is None:
                continue
            s = payload.decode(p.get_content_charset() or "utf-8", errors="ignore")
        except Exception:
            continue
        if ct == "text/plain" and not text:
            text = s
        elif ct == "text/html" and not html:
            html = s
    if not text and html:
        text = re.sub(r"<style.*?</style>|<script.*?</script>", " ", html, flags=re.S | re.I)
        text = re.sub(r"<[^>]+>", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def _load_seen() -> dict:
    return json.loads(SEEN.read_text(encoding="utf-8")) if SEEN.exists() else {"last": "", "ids": []}


def load_responses() -> list[dict]:
    if not STORE.exists() or not os.getenv("DASHBOARD_PASSWORD"):
        return []
    return json.loads(secure.decrypt(json.loads(STORE.read_text(encoding="utf-8")), secure.password()))


def _save_responses(rows: list[dict]) -> None:
    rows = sorted(rows, key=lambda r: r.get("date", ""), reverse=True)[:500]
    STORE.write_text(json.dumps(secure.encrypt(json.dumps(rows, ensure_ascii=False).encode(), secure.password())),
                     encoding="utf-8")


def fetch(days_first_run: int = 30, max_emails: int = 60) -> list[dict]:
    seen = _load_seen()
    since = datetime.now(timezone.utc) - timedelta(days=days_first_run)
    if seen.get("last"):
        since = datetime.fromisoformat(seen["last"]) - timedelta(days=1)
    M = imaplib.IMAP4_SSL("imap.gmail.com", 993)
    M.login(os.environ["GMAIL_ADDRESS"], os.environ["GMAIL_APP_PASSWORD"].replace(" ", ""))
    M.select("INBOX", readonly=True)  # read-only: nothing is marked as read
    _, data = M.search(None, "SINCE", since.strftime("%d-%b-%Y"))
    ids = data[0].split()[-400:]
    out, known = [], set(seen.get("ids", []))
    for num in reversed(ids):
        if len(out) >= max_emails:
            break
        _, hdr = M.fetch(num, "(BODY.PEEK[HEADER.FIELDS (MESSAGE-ID FROM SUBJECT DATE)])")
        h = email.message_from_bytes(hdr[0][1])
        mid = (h.get("Message-ID") or "").strip()
        key = hashlib.sha1((mid or f"{h.get('Date')}{h.get('Subject')}").encode()).hexdigest()[:16]
        if key in known:
            continue
        known.add(key)
        frm, subj = _dec(h.get("From")), _dec(h.get("Subject"))
        if re.search(r"jobalerts?|job-alerts?|jobs-noreply@linkedin|alert@indeed|newsletter|digest", frm + subj, re.I):
            continue
        _, raw = M.fetch(num, "(BODY.PEEK[])")
        msg = email.message_from_bytes(raw[0][1])
        body = _body(msg)
        if not JOBISH.search(f"{frm} {subj} {body[:3000]}"):
            continue
        try:
            dt = parsedate_to_datetime(h.get("Date")).astimezone(timezone.utc).isoformat()
        except Exception:
            dt = datetime.now(timezone.utc).isoformat()
        out.append({"key": key, "msgid": mid, "from": frm, "subject": subj, "date": dt, "body": body[:2500]})
    M.logout()
    seen["ids"] = list(known)[-3000:]
    seen["last"] = datetime.now(timezone.utc).isoformat()
    SEEN.write_text(json.dumps(seen), encoding="utf-8")
    return out


def classify(mails: list[dict], listings: dict) -> list[dict]:
    if not mails:
        return []
    recent = sorted(listings.values(), key=lambda r: r.get("found", ""), reverse=True)[:200]
    known = "\n".join(f"{r['id']} | {r.get('company') or '-'} | {r['title']}" for r in recent)
    results = []
    for start in range(0, len(mails), 15):
        batch = mails[start:start + 15]
        em = "\n\n".join(f"#{i} FROM: {m['from']}\nSUBJECT: {m['subject']}\nDATE: {m['date'][:10]}\n{m['body'][:1500]}"
                         for i, m in enumerate(batch))
        try:
            res = llm.ask_json(PROMPT.format(listings=known, emails=em, types=TYPES)).get("results", [])
        except Exception as ex:
            print(f"  gmail AI classify failed: {ex}")
            continue
        for r in res:
            try:
                m = batch[int(r["i"])]
            except Exception:
                continue
            t = r.get("type", "other")
            if t not in TYPES or t == "other":
                continue
            lid = r.get("listing_id", "") if r.get("listing_id", "") in listings else ""
            results.append({
                "key": m["key"], "date": m["date"], "from": m["from"], "subject": m["subject"], "type": t,
                "company": r.get("company", ""), "listing_id": lid, "summary": r.get("summary", ""),
                "action": r.get("action", ""), "due": r.get("due", ""),
                "link": "https://mail.google.com/mail/u/0/#search/" + urllib.parse.quote(f"rfc822msgid:{m['msgid']}")
                if m["msgid"] else "https://mail.google.com/mail/u/0/#inbox",
            })
    return results


def check(listings: dict, notify=None) -> list[dict]:
    """Fetch + classify new emails, store them (encrypted), return all responses."""
    rows = load_responses()
    if not configured():
        return rows
    try:
        mails = fetch_bridge() if bridge_configured() else fetch()
    except Exception as ex:
        print(f"Gmail: FAILED ({ex})")
        return rows
    new = classify(mails, listings)
    print(f"Gmail: {len(mails)} job-related emails checked, {len(new)} application replies")
    have = {r["key"] for r in rows}
    new = [r for r in new if r["key"] not in have]
    for r in new:
        if notify:
            e = html.escape
            title = listings.get(r["listing_id"], {}).get("title", "")
            notify(f"{ICON.get(r['type'], '✉️')} <b>{r['type'].replace('_', ' ').title()}</b> — {e(r['company'] or r['from'])}"
                   + (f"\n{e(title)}" if title else "") + f"\n{e(r['summary'])}"
                   + (f"\n👉 {e(r['action'])}" if r["action"] else "")
                   + (f"\n⏰ due {e(r['due'])}" if r["due"] else ""), r["link"])
    rows = new + rows
    _save_responses(rows)
    return rows
