import json
from datetime import date, datetime

from agent import reminders

ROWS = [
    {"type": "offer", "company": "Wave", "date": "2026-11-18", "tasks": [
        {"what": "Project plan", "due": "2026-11-28"},
        {"what": "Weekly journal", "repeat": "weekly on sunday", "until": "2027-01-15"}]},
    {"type": "offer", "company": "Wave", "date": "2026-11-15", "tasks": [{"what": "Project plan", "due": "2026-11-28"}]},  # duplicate
    {"type": "confirmation", "company": "Pleo", "date": "2026-11-12", "action": "Wait", "due": "2026-11-20"},           # not a task
    {"type": "interview", "company": "Monzo", "date": "2026-11-10", "action": "Video interview", "due": "2026-11-21"},  # fallback
]


def test_tasks_are_deduplicated_and_only_from_active_replies():
    whats = [(t["who"], t["what"]) for t in reminders.tasks(ROWS)]
    assert whats == [("Wave", "Project plan"), ("Wave", "Weekly journal"), ("Monzo", "Video interview")]


def test_buckets_and_weekly_tasks():
    t = {x["what"]: x for x in reminders.tasks(ROWS)}
    assert reminders.due_on(t["Project plan"], date(2026, 11, 28)) == ("today", 0)
    assert reminders.due_on(t["Project plan"], date(2026, 11, 26)) == ("soon", 2)
    assert reminders.due_on(t["Project plan"], date(2026, 11, 21)) == ("week", 7)
    assert reminders.due_on(t["Project plan"], date(2026, 11, 20)) is None          # more than a week away
    assert reminders.due_on(t["Project plan"], date(2026, 11, 29)) is None          # past
    assert reminders.due_on(t["Weekly journal"], date(2026, 11, 22)) == ("today", 0)  # a Sunday
    assert reminders.due_on(t["Weekly journal"], date(2026, 11, 23)) is None
    assert reminders.due_on(t["Weekly journal"], date(2027, 1, 17)) is None         # programme over


def test_digest_text_and_empty_days():
    text = reminders.digest(ROWS, date(2026, 11, 22))
    assert "Weekly journal" in text and "Project plan" in text and "Video interview" not in text  # Monzo was the 21st
    assert reminders.digest([], date(2026, 11, 22)) == ""


def test_one_digest_per_day(tmp_path, monkeypatch):
    monkeypatch.setattr(reminders, "STATE", tmp_path / "rem.json")
    sent = []
    assert not reminders.send_morning_digest(ROWS, sent.append, datetime(2026, 11, 22, 4, 0))   # too early
    assert reminders.send_morning_digest(ROWS, sent.append, datetime(2026, 11, 22, 7, 0))
    assert not reminders.send_morning_digest(ROWS, sent.append, datetime(2026, 11, 22, 10, 0))  # already sent today
    assert len(sent) == 1 and json.loads((tmp_path / "rem.json").read_text())["last"] == "2026-11-22"
