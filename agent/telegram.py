"""Telegram delivery. Needs TELEGRAM_BOT_TOKEN (from @BotFather) and TELEGRAM_CHAT_ID."""
from __future__ import annotations

import html
import json
import os
import time
from pathlib import Path

import requests

API = "https://api.telegram.org/bot{token}/{method}"


def _call(method: str, data: dict | None = None, files=None) -> dict:
    token = os.environ["TELEGRAM_BOT_TOKEN"]
    for attempt in range(5):
        try:
            if files:
                for f in files.values():
                    f[1].seek(0)
            r = requests.post(API.format(token=token, method=method), data=data, files=files, timeout=60)
        except (requests.ConnectionError, requests.Timeout):  # flaky network: wait and retry
            if attempt == 4:
                raise
            time.sleep(5 * (attempt + 1))
            continue
        if r.status_code == 429:  # flood control
            time.sleep(r.json().get("parameters", {}).get("retry_after", 5) + 1)
            continue
        r.raise_for_status()
        return r.json()
    r.raise_for_status()
    return {}


def configured() -> bool:
    return bool(os.getenv("TELEGRAM_BOT_TOKEN") and os.getenv("TELEGRAM_CHAT_ID"))


def send_text(text: str, url: str | None = None, button: str = "🚀 Apply now") -> None:
    data = {"chat_id": os.environ["TELEGRAM_CHAT_ID"], "text": text[:4096], "parse_mode": "HTML",
            "disable_web_page_preview": "true"}
    # Telegram rejects the whole message if a button URL isn't http(s): only attach valid links
    row = [{"text": button, "url": url}] if url and url.lower().startswith(("https://", "http://")) else []
    dash = os.getenv("DASHBOARD_URL", "").strip()
    if dash.startswith("http"):
        row.append({"text": "📋 Dashboard", "url": dash})
    if row:
        data["reply_markup"] = json.dumps({"inline_keyboard": [row]})
    _call("sendMessage", data)


def send_file(path: Path, caption: str = "") -> None:
    with open(path, "rb") as fh:
        _call("sendDocument", {"chat_id": os.environ["TELEGRAM_CHAT_ID"], "caption": caption[:1024]},
              files={"document": (path.name, fh)})


def esc(s) -> str:
    return html.escape(str(s or ""))


def find_chat_id() -> None:
    """Prints chat ids of people who messaged the bot (run once during setup)."""
    res = _call("getUpdates")
    ids = {(u.get("message") or {}).get("chat", {}).get("id") for u in res.get("result", [])}
    ids.discard(None)
    if ids:
        print("Your TELEGRAM_CHAT_ID:", ", ".join(map(str, ids)))
    else:
        print("No messages yet — open your bot in Telegram, press Start / send 'hi', then run this again.")
