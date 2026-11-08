"""Tailored CV, cover letter and application tips for one opportunity."""
from __future__ import annotations

import re
from datetime import date
from pathlib import Path

from . import llm
from .sources import Job

PROMPT = """You are an expert career coach and ATS (applicant tracking system) specialist.
Candidate profile/preferences: {profile}

CANDIDATE CV:
\"\"\"{cv}\"\"\"

OPPORTUNITY (category: {category}; type: {kind}) — {title} at {company} ({location}, {mode})
\"\"\"{desc}\"\"\"

Keywords from the posting already found in the CV: {matched}
Keywords from the posting missing from the CV: {missing}

STRICT RULES: never invent experience, degrees, employers, dates or numbers that are not in the CV.
You may rephrase, reorder and emphasise real CV content and use the posting's vocabulary for things
the candidate genuinely did. If a missing keyword is not supported by the CV, list it as a gap to learn,
do not add it to the CV.

Return ONLY a JSON object with these keys:
"fit_summary": 2 sentences on why this is (or is not) a good fit,
"ats_score_estimate": integer 0-100 for how well the CV would pass an ATS for this posting after your edits,
"keywords_to_add": list of missing keywords the candidate CAN truthfully add (with where to add them),
"skill_gaps": list of keywords/skills the candidate lacks,
"tailored_headline": one-line CV headline for this role,
"tailored_summary": 3-4 line professional summary for the top of the CV,
"tailored_skills": ordered list of the candidate's real skills, most relevant first,
"tailored_bullets": list of 5-8 rewritten experience/project bullets (from real CV content, action verb + impact),
"boost_tips": list of 4-6 concrete actions to boost THIS application (portfolio item, referral, certification, etc.),
"cover_letter": a complete, specific, warm but professional cover letter (250-350 words) addressed to the {company} hiring team,
 signed with the candidate's name from the CV, no placeholders like [Your Name] unless the CV has no name.
"""


def generate(job: Job, cv_text: str, cfg: dict) -> dict | None:
    if not llm.available():
        return None
    prompt = PROMPT.format(
        profile=cfg.get("profile", ""), cv=cv_text[:12000], kind=job.kind, category=job.category, title=job.title,
        company=job.company or "the selection committee", location=job.location or "n/a", mode=job.work_mode,
        desc=job.description[:9000], matched=", ".join(job.matched) or "none",
        missing=", ".join(job.missing) or "none",
    )
    try:
        return llm.ask_json(prompt)
    except llm.LLMUnavailable as ex:
        print(f"    AI writing skipped: {ex}")
        return None


def _slug(s: str) -> str:
    return re.sub(r"[^a-zA-Z0-9]+", "_", s).strip("_")[:50]


def _listify(v) -> list[str]:
    if isinstance(v, list):
        return [str(x) if not isinstance(x, dict) else " — ".join(map(str, x.values())) for x in v]
    return [str(v)] if v else []


def write_docs(job: Job, ai: dict, out_dir: Path) -> list[Path]:
    """Writes the tailored CV and the cover letter as .docx files ready to upload."""
    import docx
    from docx.shared import Pt

    out_dir.mkdir(parents=True, exist_ok=True)
    base = "_".join(x for x in (_slug(job.company), _slug(job.title)) if x)
    files = []

    # Cover letter
    d = docx.Document()
    d.styles["Normal"].font.name = "Calibri"
    d.styles["Normal"].font.size = Pt(11)
    d.add_paragraph(date.today().strftime("%d %B %Y"))
    for para in str(ai.get("cover_letter", "")).split("\n"):
        if para.strip():
            d.add_paragraph(para.strip())
    p = out_dir / f"CoverLetter_{base}.docx"
    d.save(p)
    files.append(p)

    # Tailored CV content
    d = docx.Document()
    d.styles["Normal"].font.name = "Calibri"
    d.styles["Normal"].font.size = Pt(11)
    d.add_heading(f"Tailored CV — {job.title} @ {job.company}", level=1)
    if ai.get("tailored_headline"):
        d.add_paragraph().add_run(str(ai["tailored_headline"])).bold = True
    d.add_heading("Professional summary", level=2)
    d.add_paragraph(str(ai.get("tailored_summary", "")))
    d.add_heading("Key skills (most relevant first)", level=2)
    d.add_paragraph(" • ".join(_listify(ai.get("tailored_skills"))))
    d.add_heading("Experience / project bullets to use", level=2)
    for b in _listify(ai.get("tailored_bullets")):
        d.add_paragraph(b, style="List Bullet")
    d.add_heading("ATS keywords you can truthfully add", level=2)
    for b in _listify(ai.get("keywords_to_add")):
        d.add_paragraph(b, style="List Bullet")
    d.add_heading("Skill gaps to work on", level=2)
    for b in _listify(ai.get("skill_gaps")):
        d.add_paragraph(b, style="List Bullet")
    d.add_heading("How to boost this application", level=2)
    for b in _listify(ai.get("boost_tips")):
        d.add_paragraph(b, style="List Bullet")
    d.add_paragraph(f"\nApply here: {job.url}")
    p = out_dir / f"TailoredCV_{base}.docx"
    d.save(p)
    files.append(p)
    return files


def basic_tips(job: Job) -> list[str]:
    """Used when no free AI key is configured."""
    tips = []
    if job.missing:
        tips.append("Add (only if true) these posting keywords to your CV: " + ", ".join(job.missing[:10]))
    tips.append("Copy the exact job title into your CV headline for this application.")
    tips.append("Put your 3 most relevant projects/experiences at the top, with numbers (%, time, users).")
    if job.kind == "fellowship":
        tips.append("Fellowships weigh motivation & impact: prepare a 1-page personal statement + 2 referees early.")
    return tips
