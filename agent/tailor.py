"""Tailored CV, cover letter and application tips for one opportunity."""
from __future__ import annotations

import json
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

STUDENT RULE (very important): {student_rule}
{kind_note}

Keywords from the posting already found in the CV: {matched}
Keywords from the posting missing from the CV: {missing}

STRICT RULES: never invent experience, degrees, employers, dates or numbers that are not in the CV.
Tools, software, platforms and technologies (e.g. Jira, Zendesk, Salesforce, Azure, ServiceNow, Excel) may appear
in the tailored CV ONLY if the CV above literally names them — otherwise they go in "skill_gaps", never in the CV.
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
"key_requirements": list of the 5-10 most important requirements of the posting, each an object with keys
 "requirement" (short), "met" ("yes", "partial" or "no") and "evidence" (what in the CV proves it, or what is missing),
"deadline": application deadline as YYYY-MM-DD if the posting states one, else "",
"salary_or_funding": salary / stipend / funding stated in the posting, else "",
"screening_answers": list of 5 objects with keys "question" and "answer": first-person answers (60-120 words, real CV facts)
 to the questions this application form most likely asks (e.g. why this company, why you, most relevant experience,
 availability/notice and remote setup, salary expectations phrased flexibly),
"ats_cv": a COMPLETE one-page ATS-friendly CV tailored to this posting, as an object with keys
 "name", "headline", "contact" (one line: email | phone | city, country | LinkedIn | GitHub, from the CV),
 "summary" (3-4 lines with the posting's keywords the candidate truly has),
 "skills" (list of 3-5 strings, each "Group: skill, skill, skill", most relevant group first),
 "experience" (list of objects with keys "title", "company", "location", "dates", "bullets" (2-4 strings);
   ALL real jobs/internships from the CV, most relevant first within reverse-chronological order, bullets rewritten
   with the posting's vocabulary, action verb + result),
 "projects" (list of objects with keys "name", "bullets" — only if the CV has projects relevant to this posting, else []),
 "education" (list of objects with keys "degree", "school", "dates"; the in-progress engineering degree ONLY if the student rule allows it),
 "certifications" (list of strings, most relevant first), "languages" (list of strings),
"cover_letter": a complete, specific, warm but professional cover letter (250-350 words) addressed to the {company} hiring team,
 signed with the candidate's name from the CV, no placeholders like [Your Name] unless the CV has no name.
"""


def generate(job: Job, cv_text: str, cfg: dict) -> dict | None:
    if not llm.available():
        return None
    prompt = PROMPT.format(
        student_rule=student_rule(job.category, cfg, job.kind),
        kind_note=KIND_NOTES.get(job.kind, ""),
        profile=cfg.get("profile", ""), cv=cv_text[:12000], kind=job.kind, category=job.category, title=job.title,
        company=job.company or "the selection committee", location=job.location or "n/a", mode=job.work_mode,
        desc=job.description[:9000], matched=", ".join(job.matched) or "none",
        missing=", ".join(job.missing) or "none",
    )
    try:
        ai = llm.ask_json(prompt)
        if not is_student(job.category, cfg, job.kind) and mentions_studies(ai):  # one retry with a sharper reminder
            ai = llm.ask_json(prompt + "\n\nREMINDER: your previous answer mentioned her current studies. Remove every "
                              "mention of being a student, the polytechnic, or an engineering degree in progress.")
        return scrub_studies(ai) if not is_student(job.category, cfg, job.kind) else ai
    except llm.LLMUnavailable as ex:
        print(f"    AI writing skipped: {ex}")
        return None


STUDENT_YES = ("She IS a student: say she is currently studying for an engineering degree at the school named in the "
               "profile (use its exact name, never a generic 'Polytechnic School') "
               "(alongside her Bachelor's in Computer Science) in the CV education section, the cover letter and the answers. "
               "Internships, research assistant roles and scholarships often require current student status.")
STUDENT_NO = ("This is a JOB application: do NOT mention that she is currently a student, the polytechnic school, "
              "an engineering degree in progress, studies, exams or class schedules anywhere (CV, cover letter, answers). "
              "Present her as a Computer Science graduate with professional experience. Education = Bachelor's only.")
STUDY_RE = re.compile(r"polytech|engineering degree|currently (studying|enrolled|pursuing)|student at|in progress|"
                      r"ongoing studies|my studies|alongside my studies|expected graduation|cycle d.ing", re.I)


KIND_NOTES = {
    "event": ("THIS IS A PROGRAM / EVENT APPLICATION (exchange, conference, summit, summer school, hackathon...), not a job. "
              "In \"cover_letter\" write a motivation letter / statement of purpose (300-400 words): why this program, what she "
              "will contribute, what she will learn, and how it serves her goals in AI, machine learning and fintech, plus how "
              "she will share what she learns in Tunisia. In \"screening_answers\" answer the essay questions such programs "
              "usually ask (motivation, leadership example, community impact, career goals, why you should be selected). "
              "In \"boost_tips\" include practical steps: deadline, documents (CV, passport, recommendation letters), and visa."),
    "fellowship": ("THIS IS A SCHOLARSHIP / FELLOWSHIP APPLICATION, not a job. In \"cover_letter\" write a personal statement "
                   "(400-500 words) about her academic and career goals in AI and fintech; in \"screening_answers\" answer typical "
                   "essay questions (leadership, networking, study plan, career plan, impact on Tunisia)."),
}


def is_student(category: str, cfg: dict, kind: str = "") -> bool:
    if kind in ("internship", "fellowship", "event"):
        return True
    for c in cfg.get("categories", []):
        if c.get("name") == category:
            return bool(c.get("student", c.get("kinds") != ["job"]))
    return False


def student_rule(category: str, cfg: dict, kind: str = "") -> str:
    return STUDENT_YES if is_student(category, cfg, kind) else STUDENT_NO


def mentions_studies(ai) -> bool:
    return bool(ai) and bool(STUDY_RE.search(json.dumps(ai, ensure_ascii=False)))


def scrub_studies(ai: dict | None) -> dict | None:
    """Last safety net for job applications: drop in-progress studies from the CV's education list."""
    if not ai:
        return ai
    cv = ai.get("ats_cv")
    if isinstance(cv, dict) and isinstance(cv.get("education"), list):
        cv["education"] = [e for e in cv["education"] if not STUDY_RE.search(json.dumps(e, ensure_ascii=False))]
    return ai


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

    # Full ATS-friendly CV: one column, standard headings, plain bullets, no tables/images
    cvd = ai.get("ats_cv") or {}
    if cvd:
        p = out_dir / f"CV_{base}.docx"
        ats_cv_docx(cvd, p)
        files.append(p)
    return files


def ats_cv_docx(cv: dict, path: Path) -> None:
    import docx
    from docx.enum.text import WD_ALIGN_PARAGRAPH
    from docx.shared import Cm, Pt, RGBColor

    d = docx.Document()
    for s in d.sections:
        s.top_margin = s.bottom_margin = Cm(1.6)
        s.left_margin = s.right_margin = Cm(1.8)
    st = d.styles["Normal"]
    st.font.name, st.font.size = "Calibri", Pt(10.5)
    st.paragraph_format.space_after = Pt(2)

    def para(text="", bold=False, size=None, center=False, after=2, color=None):
        p = d.add_paragraph()
        p.paragraph_format.space_after = Pt(after)
        if center:
            p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        r = p.add_run(str(text))
        r.bold = bold
        if size:
            r.font.size = Pt(size)
        if color:
            r.font.color.rgb = RGBColor.from_string(color)
        return p

    def heading(text):
        p = para(text.upper(), bold=True, size=11.5, after=3, color="1F3A8A")
        p.paragraph_format.space_before = Pt(8)

    def bullet(text):
        p = d.add_paragraph(str(text), style="List Bullet")
        p.paragraph_format.space_after = Pt(1)

    para(cv.get("name", ""), bold=True, size=18, center=True, after=0)
    if cv.get("headline"):
        para(cv["headline"], size=11.5, center=True, after=0)
    para(cv.get("contact", ""), size=9.5, center=True, after=4)
    if cv.get("summary"):
        heading("Professional Summary")
        para(cv["summary"])
    if cv.get("skills"):
        heading("Skills")
        for s in _listify(cv["skills"]):
            bullet(s)
    if cv.get("experience"):
        heading("Professional Experience")
        for e in cv["experience"]:
            if not isinstance(e, dict):
                bullet(e); continue
            p = para(f"{e.get('title', '')} — {e.get('company', '')}", bold=True, after=0)
            p.paragraph_format.space_before = Pt(4)
            para(" | ".join(x for x in (e.get("location", ""), e.get("dates", "")) if x), size=9.5, after=1, color="555555")
            for b in _listify(e.get("bullets")):
                bullet(b)
    if cv.get("projects"):
        heading("Projects")
        for pr in cv["projects"]:
            if isinstance(pr, dict):
                para(pr.get("name", ""), bold=True, after=0)
                for b in _listify(pr.get("bullets")):
                    bullet(b)
            else:
                bullet(pr)
    if cv.get("education"):
        heading("Education")
        for e in cv["education"]:
            if isinstance(e, dict):
                para(f"{e.get('degree', '')} — {e.get('school', '')}" + (f" ({e['dates']})" if e.get("dates") else ""))
            else:
                para(e)
    if cv.get("certifications"):
        heading("Certifications")
        for c in _listify(cv["certifications"]):
            bullet(c)
    if cv.get("languages"):
        heading("Languages")
        para(", ".join(_listify(cv["languages"])))
    d.save(path)


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
