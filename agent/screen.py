"""AI screening: reads each opportunity against Dorra's real profile and keeps only the ones that fit her targets
and that she can realistically get. Each listing gets a chance score (0-100) and a one-line reason.

Runs on the free Gemini tier in batches of 20, using the lighter model first, and remembers its verdicts
(stored on the listing), so each posting is screened only once.
"""
from __future__ import annotations

import json

from . import llm

PROFILE = """Dorra Bouallegue, Sousse, Tunisia (Tunisian citizen: needs a visa for on-site work in the EU, UK or Gulf;
remote work from Tunisia is fine).
- BSc Computer Science (2025). Currently studying for an engineering degree (Diplôme d'ingénieur) at École Polytechnique de Sousse.
- ~1 year at PayPal Europe (via Transcom): customer service representative + team mentor (3 teams). Disputes, account
  limitations, transaction investigations, root-cause analysis, escalations, KPIs, ticket/case handling.
- AI & Predictive Maintenance intern (Enova Robotics, 2025): Python, ROS, SVM / Random Forest, data pipelines.
- AI intern, time-series forecasting with LSTM (TAV Airports, 2024): TensorFlow, EDA.
- Agile team lead (17 people, MERN + WebRTC project); web dev internships (MERN, PHP/MySQL).
- Skills: Python, SQL, JavaScript, FastAPI, Flask, React, Node.js, PostgreSQL, MongoDB, Docker, Git, AWS basics, Linux,
  machine learning, deep learning, LLMs, RAG, prompt engineering. Certifications: NVIDIA (DL, predictive maintenance),
  Google Gen AI, Oracle Cloud AI Associate, Cisco cybersecurity intro.
- Languages: Arabic (native), French (advanced), English (C1). No German, Italian, Dutch, Spanish, etc."""

TARGETS = """WHAT SHE WANTS (keep these):
- Machine learning / deep learning / AI / data science / data analyst roles at junior, graduate or intern level,
  including AI research assistant roles and AI startups, and AI applied to finance/fintech.
- Fintech & banking operations: payments operations, fraud, KYC/AML, disputes/chargebacks, risk/transaction monitoring.
- Back-office operations, technical customer support, service desk / help desk / ticketing (Zendesk, Jira SD, etc.),
  application/production support, implementation/integration support, technical operations, QA/testing at entry level.
- Other roles she could realistically get with this exact background (e.g. junior solutions/customer-success engineer,
  junior business/product analyst in fintech or SaaS, trust & safety, AI trainer/evaluator, tech/AI consulting graduate roles).
- Events: AI / tech conferences, summits, hackathons, summer/winter schools, bootcamps, workshops (fully funded, partly
  funded OR free; online or in person), including AI applied to other fields (health, climate, agriculture, education,
  finance), and calls for volunteers / ambassadors / organizers / student volunteers at tech & AI events.
- Alternance / apprenticeship / work-study (mostly France, French is fine for her) and English-speaking "working
  student" roles in tech, data, AI, support or fintech: KEEP them (she is very interested). Note in "why" that a
  French alternance needs enrolment in a partner school / programme (she would apply via Campus France).
- Scholarships, fellowships and exchange programs open to Tunisian / African / international students, preferably in
  CS, AI, data, engineering, fintech or general leadership/STEM.

REJECT:
- Other fields (biology/chemistry/pharma lab science, marine, mechanical/electrical/networking hardware, ERP like SAP /
  PeopleSoft / Oracle EBS, legal, journalism, arts, peace studies, medicine, public-sector policy consulting, sales).
- Senior / lead / 3+ years required, PhD-required or academic staff posts (postdoc, lecturer, visiting scholar for faculty).
- Postings written in or requiring a language she doesn't speak (German, Italian, Dutch, ...). French is FINE.
- Opportunities limited to nationalities she doesn't have (e.g. only Nigerians, US citizens, EU citizens, nationals).
- Paid courses, generic advice/listicle articles, expired programs."""

PROMPT = """You screen opportunities for one person. Be strict: she said she keeps getting irrelevant results.

{profile}

{targets}

For EACH opportunity below decide:
- "keep": true only if it matches what she wants AND she has a realistic chance (or is clearly eligible, for events,
  scholarships and exchanges).
- "chance": 0-100, her realistic chance of being shortlisted / accepted on SKILLS AND EXPERIENCE alone
  (do not lower it for visas — that is reported separately).
- "visa": "none" (remote / no visa needed), "offered" (sponsorship or relocation mentioned), "needed" (on-site abroad,
  nothing said), or "blocked" (says no sponsorship / must already have the right to work there).
- "family": one of ml_ai, data, fintech_ops, back_office, tech_support, ticketing, research, consulting, analyst,
  event, volunteer_organizer, scholarship, exchange, part_time, other.
- "why": max 12 words, concrete (what fits or what blocks her).

Opportunities:
{items}

Return ONLY JSON: {{"results": [{{"id": "<id>", "keep": true, "chance": 70, "family": "ml_ai", "visa": "none", "why": "..."}}]}}"""

LITE = ["gemini-3.5-flash-lite"]


def _item(r: dict) -> str:
    desc = " ".join((r.get("description") or "").split())[:500]
    return (f'- id: {r["id"]}\n  type: {r.get("kind", "job")} | {r.get("title", "")} | {r.get("company") or "-"} | '
            f'{r.get("location") or "location not stated"} | {r.get("mode", "")}\n  text: {desc}')


def screen(rows: list[dict], batch: int = 20) -> dict[str, dict]:
    """Returns {id: {"keep", "chance", "family", "why"}} for the rows it could judge (unjudged rows are left out)."""
    out: dict[str, dict] = {}
    if not llm.available():
        return out
    for i in range(0, len(rows), batch):
        part = rows[i:i + batch]
        prompt = PROMPT.format(profile=PROFILE, targets=TARGETS, items="\n".join(_item(r) for r in part))
        try:
            ans = llm.ask_json(prompt, models=LITE, temperature=0.2)
            res = ans if isinstance(ans, list) else ans.get("results", [])
        except Exception as ex:
            print(f"  screening batch failed: {ex}")
            continue
        ids = {r["id"] for r in part}
        for x in res:
            if isinstance(x, dict) and x.get("id") in ids:
                try:
                    chance = max(0, min(100, int(x.get("chance", 0))))
                except (TypeError, ValueError):
                    chance = 0
                out[x["id"]] = {"keep": bool(x.get("keep")), "chance": chance,
                                "family": str(x.get("family", "other"))[:24], "why": str(x.get("why", ""))[:120],
                                "visa": str(x.get("visa", ""))[:10]}
    return out


def passes(check: dict | None, min_chance: int = 40) -> bool:
    """Relevant, realistic on skills, and not explicitly closed to people who need a visa."""
    return bool(check) and bool(check.get("keep")) and check.get("chance", 0) >= min_chance and check.get("visa") != "blocked"


if __name__ == "__main__":  # quick manual test: python -m agent.screen
    from .main import load_env
    from . import dashboard
    load_env()
    rows = list(dashboard.load().values())[:20]
    print(json.dumps(screen(rows), indent=1, ensure_ascii=False)[:3000])
