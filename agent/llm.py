"""Free LLM backends: Google Gemini (free tier) first, Groq (free tier) as fallback.

Set GEMINI_API_KEY (https://aistudio.google.com/apikey) and/or GROQ_API_KEY (https://console.groq.com/keys).
With no key the agent still runs: it skips AI writing and sends keyword/ATS tips only.
"""
from __future__ import annotations

import json
import os
import re
import time

import requests


class LLMUnavailable(Exception):
    pass


def available() -> bool:
    return bool(os.getenv("GEMINI_API_KEY") or os.getenv("GROQ_API_KEY"))


_GEMINI_MODELS = [m for m in [os.getenv("GEMINI_MODEL"), "gemini-3.5-flash", "gemini-3.5-flash-lite",
                               "gemini-flash-latest"] if m]


def _gemini(prompt: str, models: list[str] | None = None, temperature: float = 0.6) -> str:
    last = None
    for model in (models or []) + _GEMINI_MODELS:  # Google retires models often: fall through to the next one
        try:
            return _gemini_model(prompt, model, temperature)
        except requests.HTTPError as ex:
            last = ex
            if ex.response is None or ex.response.status_code not in (404, 400, 429, 500, 503):
                raise
        except requests.Timeout as ex:
            last = ex
    raise last


def _gemini_model(prompt: str, model: str, temperature: float = 0.6) -> str:
    r = requests.post(
        f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent",
        headers={"x-goog-api-key": os.environ["GEMINI_API_KEY"], "Content-Type": "application/json"},
        json={"contents": [{"parts": [{"text": prompt}]}],
              "generationConfig": {"temperature": temperature, "responseMimeType": "application/json"}},
        timeout=120,
    )
    r.raise_for_status()
    return r.json()["candidates"][0]["content"]["parts"][0]["text"]


def _groq(prompt: str, models: list[str] | None = None, temperature: float = 0.6) -> str:
    r = requests.post(
        "https://api.groq.com/openai/v1/chat/completions",
        headers={"Authorization": f"Bearer {os.environ['GROQ_API_KEY']}"},
        json={"model": os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile"),
              "messages": [{"role": "user", "content": prompt}],
              "temperature": temperature, "response_format": {"type": "json_object"}},
        timeout=120,
    )
    r.raise_for_status()
    return r.json()["choices"][0]["message"]["content"]


def ask_json(prompt: str, models: list[str] | None = None, temperature: float = 0.6) -> dict:
    """models: Gemini models to try first (e.g. a lighter one for quick screening)."""
    backends = []
    if os.getenv("GEMINI_API_KEY"):
        backends.append(_gemini)
    if os.getenv("GROQ_API_KEY"):
        backends.append(_groq)
    if not backends:
        raise LLMUnavailable("no GEMINI_API_KEY or GROQ_API_KEY set")
    last = None
    for fn in backends:
        for attempt in range(3):
            try:
                text = fn(prompt, models, temperature)
                text = re.sub(r"^```(json)?|```$", "", text.strip(), flags=re.M).strip()
                return json.loads(text)
            except requests.HTTPError as ex:
                last = ex
                if ex.response is not None and ex.response.status_code == 429:  # free-tier rate limit
                    time.sleep(20 * (attempt + 1))
                    continue
                break
            except Exception as ex:
                last = ex
                time.sleep(3)
    raise LLMUnavailable(f"all LLM backends failed: {last}")
