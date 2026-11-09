"""Keeps every match (encrypted) and builds the password-protected dashboard website."""
from __future__ import annotations

import json
import os
from datetime import datetime, timedelta, timezone
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
    cutoff = (datetime.now(timezone.utc) - timedelta(days=KEEP_DAYS)).isoformat()
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
        "found": datetime.now(timezone.utc).isoformat(),
    }
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


def build(listings: dict, cv_text: str, cfg: dict, responses: list | None = None) -> Path:
    applicant_file = ROOT / "cv" / "applicant.yaml"
    applicant = yaml.safe_load(applicant_file.read_text(encoding="utf-8")) if applicant_file.exists() else {}
    payload = {
        "generated": datetime.now(timezone.utc).isoformat(),
        "listings": [enrich.apply(dict(r)) for r in sorted(listings.values(), key=lambda r: r.get("found", ""), reverse=True)],
        "responses": responses or [],
        "categories": [c["name"] for c in cfg.get("categories", [])],
        "applicant": applicant or {},
        "cv": cv_text[:12000],
        "profile": cfg.get("profile", ""),
        "prompt": tailor.PROMPT,
        "student_rules": {c["name"]: tailor.student_rule(c["name"], cfg) for c in cfg.get("categories", [])},
        "student_no": tailor.STUDENT_NO,
        "student_yes": tailor.STUDENT_YES,
        # lets the page write cover letters on demand; only readable after entering the password
        "gemini_key": os.getenv("GEMINI_API_KEY", ""),
    }
    blob = secure.encrypt(json.dumps(payload, ensure_ascii=False).encode("utf-8"), secure.password())
    html = TEMPLATE.read_text(encoding="utf-8").replace("__PAYLOAD__", json.dumps(blob))
    SITE.mkdir(exist_ok=True)
    out = SITE / "index.html"
    out.write_text(html, encoding="utf-8")
    (SITE / ".nojekyll").write_text("", encoding="utf-8")
    return out
