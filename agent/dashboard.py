"""Keeps every match (encrypted) and builds the password-protected dashboard website."""
from __future__ import annotations

import base64
import hashlib
import json
import os
import re
from datetime import datetime, timedelta, UTC
from pathlib import Path

import yaml

from . import enrich, secure, tailor
from .sources import Job

ROOT = Path(__file__).resolve().parent.parent
STORE = ROOT / "state" / "listings.enc"
SITE = ROOT / "site"
TEMPLATE = Path(__file__).with_name("dashboard_template.html")
KEEP_DAYS = 60
MAX_LISTINGS = 400


def enabled() -> bool:
    return bool(os.getenv("DASHBOARD_PASSWORD"))


def load() -> dict[str, dict]:
    if not STORE.exists():
        return {}
    return json.loads(secure.decrypt(json.loads(STORE.read_text(encoding="utf-8")), secure.password()))


def save(listings: dict[str, dict]) -> None:
    cutoff = (datetime.now(UTC) - timedelta(days=KEEP_DAYS)).isoformat()
    keep = {k: v for k, v in listings.items() if v.get("found", "") >= cutoff}
    keep = dict(sorted(keep.items(), key=lambda kv: kv[1].get("found", ""), reverse=True)[:MAX_LISTINGS])
    STORE.parent.mkdir(exist_ok=True)
    blob = secure.encrypt(json.dumps(keep, ensure_ascii=False).encode("utf-8"), secure.password())
    STORE.write_text(json.dumps(blob), encoding="utf-8")


def record(j: Job, ai: dict | None) -> dict:
    r = {
        "id": j.id, "title": j.title, "company": j.company, "url": j.url, "category": j.category, "fit": j.fit,
        "kind": j.kind, "mode": j.work_mode, "employment": j.employment, "location": j.location,
        "source": j.source, "salary": j.salary, "posted": j.posted.isoformat() if j.posted else "",
        "score": j.score, "ats": j.ats, "matched": j.matched[:20], "missing": j.missing[:20],
        "description": j.description[:6000],
        "found": datetime.now(UTC).isoformat(),
    }
    if getattr(j, "check", None):
        r["check"] = j.check
    if ai:
        r["ai"] = {k: ai.get(k) for k in ("fit_summary", "ats_score_estimate", "keywords_to_add", "skill_gaps",
                                          "tailored_headline", "tailored_summary", "tailored_skills",
                                          "tailored_bullets", "boost_tips", "cover_letter", "key_requirements",
                                          "deadline", "salary_or_funding", "screening_answers", "ats_cv")}
    else:
        r["tips"] = tailor.basic_tips(j)
    return r


def upsert(listings: dict, new: dict) -> None:
    old = listings.get(new["id"])
    if old:
        new["found"] = old.get("found", new["found"])
        if "ai" not in new and "ai" in old:
            new["ai"] = old["ai"]
    listings[new["id"]] = new


def _dupe_key(r: dict) -> tuple[str, str]:
    title = " ".join(r.get("title", "").lower().replace("(", " ").replace(")", " ").split())
    return title, (r.get("company") or "").lower()


def _unique(rows: list[dict]) -> list[dict]:
    """The same post often appears on two opportunity sites: show it once (keep the one with an apply kit).
    Keeps the input order."""
    best: dict = {}
    for r in rows:
        k = _dupe_key(r)
        if k not in best or ("ai" in r and "ai" not in best[k]):
            best[k] = r
    return [r for r in rows if best[_dupe_key(r)] is r]


# Only the page's own inline script may run (pinned by hash); data can only be sent to Gemini and your Apps Script.
CSP = ("default-src 'none'; script-src {script}; style-src 'unsafe-inline'; img-src 'self' data: blob:; "
       "font-src 'self' data:; connect-src https://generativelanguage.googleapis.com https://script.google.com "
       "https://script.googleusercontent.com; base-uri 'none'; form-action 'none'; object-src 'none'; "
       "frame-src 'none'; worker-src 'none'; manifest-src 'self'")
_SCRIPT = re.compile(r"<script>(.*?)</script>", re.S)


def with_csp(html: str) -> str:
    """Fills the CSP meta tag with the SHA-256 of every inline <script> (after the payload is in place)."""
    hashes = " ".join("'sha256-" + base64.b64encode(hashlib.sha256(m.group(1).encode("utf-8")).digest()).decode() + "'"
                      for m in _SCRIPT.finditer(html))
    return html.replace("__CSP__", CSP.format(script=hashes or "'none'"), 1)


def build(listings: dict, cv_text: str, cfg: dict, responses: list | None = None) -> Path:
    applicant_file = ROOT / "cv" / "applicant.yaml"
    applicant = yaml.safe_load(applicant_file.read_text(encoding="utf-8")) if applicant_file.exists() else {}
    payload = {
        "generated": datetime.now(UTC).isoformat(),
        "listings": _unique([enrich.apply(dict(r)) for r in sorted(listings.values(), key=lambda r: r.get("found", ""), reverse=True)]),
        "responses": responses or [],
        "categories": [c["name"] for c in cfg.get("categories", [])],
        "applicant": applicant or {},
        "cv": cv_text[:12000],
        "profile": cfg.get("profile", ""),
        "prompt": tailor.PROMPT,
        "student_rules": {c["name"]: tailor.student_rule(c["name"], cfg) for c in cfg.get("categories", [])},
        "student_no": tailor.STUDENT_NO,
        "student_yes": tailor.STUDENT_YES,
        "kind_notes": tailor.KIND_NOTES,
        # lets the page write cover letters on demand; only readable after entering the password
        "gemini_key": os.getenv("GEMINI_API_KEY", ""),
        # applications database (Google Sheet) through the user's own Apps Script bridge; inside the encrypted blob
        "db": ({"url": os.environ["GMAIL_WEBAPP_URL"], "key": os.environ["GMAIL_WEBAPP_KEY"]}
               if os.getenv("GMAIL_WEBAPP_URL", "").startswith("https://") and os.getenv("GMAIL_WEBAPP_KEY") else None),
    }
    blob = secure.encrypt(json.dumps(payload, ensure_ascii=False).encode("utf-8"), secure.password(), salt=secure.site_salt())
    html = with_csp(TEMPLATE.read_text(encoding="utf-8").replace("__PAYLOAD__", json.dumps(blob)))
    SITE.mkdir(exist_ok=True)
    out = SITE / "index.html"
    out.write_text(html, encoding="utf-8")
    (SITE / ".nojekyll").write_text("", encoding="utf-8")
    return out
