"""Deadline reminders: one Telegram message each morning with what is due (from the replies to her applications).

Tasks come from the email sorter ("tasks": [{"what", "due", "repeat"}]); older replies fall back to their single
action + due date. Weekly tasks ("every Sunday") are reminded on that weekday until they end.
"""
from __future__ import annotations

import html
import json
from datetime import date, datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
STATE = ROOT / "state" / "reminders.json"
ACTIVE = {"offer", "interview", "assessment", "info_request"}
WEEKDAYS = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
DIGEST_HOUR_UTC = 6          # first run after 7:00 in Tunisia


def _d(s: str) -> date | None:
    try:
        return date.fromisoformat(str(s)[:10])
    except ValueError:
        return None


def tasks(responses: list[dict]) -> list[dict]:
    """Every open task, one per (organisation, task)."""
    out, seen = [], set()
    for r in sorted(responses, key=lambda x: x.get("date", ""), reverse=True):
        if r.get("type") not in ACTIVE:
            continue
        who = r.get("company") or r.get("from", "")
        items = r.get("tasks") or ([{"what": r.get("action", ""), "due": r.get("due", ""), "repeat": ""}] if r.get("action") else [])
        for t in items:
            what = str(t.get("what", "")).strip()
            key = (who.lower(), what.lower()[:60])
            if not what or key in seen:
                continue
            seen.add(key)
            out.append({"who": who, "what": what, "due": str(t.get("due", ""))[:10], "repeat": str(t.get("repeat", "")).lower(),
                        "until": str(t.get("until", ""))[:10], "role": r.get("role", "")})
    return out


def due_on(task: dict, today: date) -> tuple[str, int] | None:
    """(bucket, days left) if the task should be in today's digest, else None."""
    rep = task["repeat"]
    if rep:
        until = _d(task["until"])
        if until and today > until:
            return None
        day = next((i for i, w in enumerate(WEEKDAYS) if w in rep), None)
        if day is not None and today.weekday() == day:
            return ("today", 0)
        return None
    due = _d(task["due"])
    if not due:
        return None
    left = (due - today).days
    if left < 0 or left > 7:
        return None
    return ("today" if left == 0 else "soon" if left <= 3 else "week"), left


def digest(responses: list[dict], today: date) -> str:
    rows = {"today": [], "soon": [], "week": []}
    for t in tasks(responses):
        hit = due_on(t, today)
        if hit:
            rows[hit[0]].append((hit[1], t))
    if not any(rows.values()):
        return ""
    e = html.escape
    when = lambda n, t: "every " + t["repeat"].replace("weekly on ", "").strip() if t["repeat"] else (
        "today" if n == 0 else "tomorrow" if n == 1 else f"in {n} days · {datetime.fromisoformat(t['due']).strftime('%a %d %b')}")
    parts = ["⏰ <b>Your deadlines</b>"]
    for key, title in (("today", "🔴 Today"), ("soon", "🟠 Next 3 days"), ("week", "🟡 This week")):
        if rows[key]:
            parts.append(f"\n<b>{title}</b>")
            parts += [f"• <b>{e(t['who'])}</b>: {e(t['what'])} ({when(n, t)})" for n, t in sorted(rows[key], key=lambda x: x[0])]
    return "\n".join(parts)


def send_morning_digest(responses: list[dict], send, now: datetime) -> bool:
    """Sends at most one digest per day (on the first run after DIGEST_HOUR_UTC). Returns True if sent."""
    state = json.loads(STATE.read_text(encoding="utf-8")) if STATE.exists() else {}
    today = now.date()
    if now.hour < DIGEST_HOUR_UTC or state.get("last") == today.isoformat():
        return False
    text = digest(responses, today)
    state["last"] = today.isoformat()
    STATE.parent.mkdir(exist_ok=True)
    STATE.write_text(json.dumps(state), encoding="utf-8")
    if text and send:
        send(text)
        return True
    return False


if __name__ == "__main__":  # preview: python -m agent.reminders
    from .gmail import load_responses
    from .main import load_env
    load_env()
    for i in range(8):
        d = date.today() + timedelta(days=i)
        print(f"--- {d} ---\n{digest(load_responses(), d) or '(nothing due)'}")
