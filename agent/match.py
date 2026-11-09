"""CV loading, filtering, relevance scoring and ATS keyword scoring (no AI needed)."""
from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone
from pathlib import Path

from . import enrich
from .sources import Job

# Common skills / ATS keywords. Extend with `extra_keywords` in config.yaml.
SKILLS = """
python r sql nosql java javascript typescript c++ c# go rust scala matlab julia bash linux git github docker kubernetes
aws azure gcp google cloud terraform ci/cd airflow spark pyspark hadoop kafka dbt snowflake bigquery databricks redshift
postgresql mysql mongodb redis elasticsearch pandas numpy scipy scikit-learn sklearn tensorflow pytorch keras jax xgboost lightgbm catboost
machine learning deep learning data science data analysis data analytics data engineering data visualization statistics
nlp natural language processing computer vision llm llms generative ai genai rag langchain transformers hugging face
reinforcement learning time series forecasting anomaly detection fraud detection recommendation systems mlops feature engineering
a/b testing experimentation hypothesis testing regression classification clustering
tableau power bi looker excel google sheets matplotlib seaborn plotly streamlit
fastapi flask django react node.js next.js html css rest api graphql microservices
agile scrum jira product management project management stakeholder management communication leadership teamwork
research publication writing presentation problem solving critical thinking
cybersecurity security risk compliance finance fintech banking healthcare blockchain
etl elt data warehouse data modeling data pipeline big data cloud computing devops
""".split("\n")

_STOP = set("""a an the and or of to in for on with at by from as is are be this that it you your we our will can
have has their they them who what which into about more than such other using use etc""".split())


def _vocab(cfg: dict) -> list[str]:
    words: set[str] = set()
    multi = ["machine learning", "deep learning", "data science", "data analysis", "data analytics", "data engineering",
             "data visualization", "natural language processing", "computer vision", "generative ai", "hugging face",
             "reinforcement learning", "time series", "anomaly detection", "fraud detection", "recommendation systems",
             "feature engineering", "a/b testing", "hypothesis testing", "power bi", "google sheets", "google cloud",
             "rest api", "product management", "project management", "stakeholder management", "problem solving",
             "critical thinking", "data warehouse", "data modeling", "data pipeline", "big data", "cloud computing"]
    words.update(multi)
    for line in SKILLS:
        for w in line.split():
            words.add(w)
    for w in ("data", "learning", "machine", "deep", "science", "analysis", "management", "testing", "cloud",
              "google", "power", "time", "series", "big", "critical", "thinking", "problem", "solving", "natural",
              "language", "processing", "computer", "vision", "generative", "hugging", "face", "detection", "fraud",
              "anomaly", "feature", "engineering", "project", "product", "stakeholder", "visualization", "warehouse",
              "modeling", "pipeline", "rest", "api", "sheets", "recommendation", "systems", "hypothesis",
              "reinforcement", "analytics", "regression", "go", "r"):
        words.discard(w)  # too generic alone; kept in multi-word form
    words.update(k.lower() for k in cfg.get("extra_keywords", []))
    return sorted(words, key=len, reverse=True)


def _has(term: str, text: str) -> bool:
    return re.search(r"(?<![a-z0-9])" + re.escape(term) + r"s?(?![a-z0-9])", text) is not None


def load_cv(path: str | Path) -> str:
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"CV not found at {p}. Put your CV (PDF/DOCX/TXT/MD) there.")
    if p.suffix.lower() == ".pdf":
        from pypdf import PdfReader
        return "\n".join(page.extract_text() or "" for page in PdfReader(str(p)).pages)
    if p.suffix.lower() == ".docx":
        import docx
        return "\n".join(par.text for par in docx.Document(str(p)).paragraphs)
    return p.read_text(encoding="utf-8", errors="ignore")


def find_cv(folder: str | Path) -> Path:
    folder = Path(folder)
    for ext in ("pdf", "docx", "md", "txt"):
        hits = sorted(folder.glob(f"*.{ext}"))
        hits = [h for h in hits if h.name.lower() != "readme.md"]
        if hits:
            return hits[0]
    raise FileNotFoundError(f"No CV in {folder}/ — add cv.pdf (or .docx/.txt/.md).")


def ats_score(cv_text: str, job_text: str, vocab: list[str]) -> tuple[float, list[str], list[str]]:
    """Share of the job's keywords that appear in the CV, like a simple ATS."""
    cv, jt = cv_text.lower(), job_text.lower()
    wanted = []
    for term in vocab:
        if _has(term, jt) and not any(term in w for w in wanted):
            wanted.append(term)
    if not wanted:
        return 0.0, [], []
    matched = [t for t in wanted if _has(t, cv)]
    missing = [t for t in wanted if t not in matched]
    return round(100 * len(matched) / len(wanted), 1), matched, missing


def passes_filters(job: Job, cfg: dict) -> bool:
    """Global filters; type and remote/hybrid are decided per category."""
    f = cfg.get("filters", {})
    title = job.title.lower()
    if any(_has(w.lower(), title) for w in f.get("exclude_title_words", [])):
        return False
    text = f"{job.title} {job.description}".lower()
    if any(_has(w.lower(), text) for w in f.get("exclude_words", [])):
        return False
    max_age = f.get("max_age_days", 14) * (4 if job.kind == "fellowship" else 1)  # scholarships stay open for months
    if job.posted and job.posted < datetime.now(timezone.utc) - timedelta(days=max_age):
        return False
    allowed = [a.lower() for a in f.get("allowed_locations", [])]
    loc = (job.location or "").lower()
    if allowed and loc and not any(a in loc for a in allowed + ["worldwide", "anywhere", "global", "remote"]):
        return False
    return True


def detect_employment(text: str) -> str:
    t = text.lower()
    if re.search(r"part[- ]time|teilzeit|mi-temps|temps partiel|\bhours? per week|freelance|contractor", t):
        return "part-time"
    if re.search(r"full[- ]time|vollzeit|temps plein|cdi", t):
        return "full-time"
    return ""


def _count(terms: list[str], text: str) -> int:
    return sum(1 for t in terms if _has(t, text))


def _flat(v) -> list[str]:
    """config lists may contain other lists (reused with *name in config.yaml)."""
    out = []
    for x in v or []:
        out.extend(_flat(x) if isinstance(x, list) else [str(x)])
    return out


ITALIAN = re.compile(r"\b(della|delle|degli|nella|sono|esperienza|lavoro|azienda|candidato|requisiti|conoscenza|"
                     r"offriamo|siamo|cerchiamo|stiamo|ruolo|sede)\b", re.I)


def foreign_language_required(text: str, banned: list[str]) -> bool:
    """True if the posting requires a language you don't speak, or is written in Italian."""
    if banned and any(l in banned for l in enrich.languages(text)):
        return True
    return "Italian" in banned and len(ITALIAN.findall(text[:3000])) >= 6


def _score_in_category(j: Job, cat: dict, title: str, body: str) -> float | None:
    if j.kind not in cat.get("kinds", ["job", "internship", "fellowship"]):
        return None
    if j.work_mode not in cat.get("work_modes", ["remote", "hybrid"]):
        return None
    if any(_has(t.lower(), title) for t in cat.get("exclude_title", [])):
        return None
    places = [p.lower() for p in _flat(cat.get("locations_any", []))]
    tn = enrich.tunisia(j.location, f"{title}\n{body}") if j.work_mode == "remote" else ""
    remote_ok = cat.get("remote_ok") or (["yes"] if cat.get("remote_if_tunisia") else [])
    remote_tn = j.work_mode == "remote" and tn in remote_ok
    if places and not remote_tn:
        where = f"{j.location} {title}".lower()
        if cat.get("locations_in") == "all":
            where += " " + body[:2500]
        elif j.location.count(",") >= 3:
            return None  # a long country list = a remote job for many countries, not a London/Italy job
        if not any(_has(p, where) for p in places):
            return None
        m = re.search(r"\b(?:work|based|relocat\w*|located) (?:in|to) ([a-z]+)", title)
        if m and not any(_has(p, m.group(1)) for p in places):
            return None  # "... - Work in Sofia, Bulgaria" posted under Italy
    tn_ok = cat.get("tunisia_ok") or (["yes"] if cat.get("require_tunisia") else [])
    if tn_ok and enrich.tunisia(j.location, f"{title}\n{body}") not in tn_ok:
        return None
    req = [t.lower() for t in cat.get("require_any", [])]
    if req and cat.get("tiers") and _count(req, f"{title} {body[:2500]}") < cat.get("require_min", 1):
        return None
    bonus = cat.get("bonus", 0)
    tiers = cat.get("tiers") or {}
    fit = ""
    if tiers:  # title groups by fit: the best group found decides the fit label
        for label in tiers:
            if _count([t.lower() for t in _flat(tiers[label])], title):
                fit = label
                break
        if not fit:
            return None
        base = {"Excellent": 100, "Very good": 85, "Good": 70}.get(fit, 70)
        boost = min(_count([t.lower() for t in cat.get("boost_any", [])], f"{title} {body}"), 4)
        j.fit = fit
        return min(100, 0.6 * base + 0.4 * j.ats + boost * 3) + bonus
    must = [t.lower() for t in cat.get("must_any", [])]
    t_hits = _count(must, title)
    b_hits = 0 if cat.get("match_in") == "title" else _count(must, body)
    if t_hits + b_hits == 0:
        return None
    req = [t.lower() for t in cat.get("require_any", [])]
    if req and _count(req, f"{title} {body}") == 0:
        return None
    boost = _count([t.lower() for t in cat.get("boost_any", [])], f"{title} {body}")
    if j.kind == "fellowship":  # fellowships rarely list skills: judge on topics, not ATS
        return min(100, 35 + t_hits * 10 + min(b_hits, 3) * 4 + boost * 5)
    relevance = min(100, t_hits * 45 + min(b_hits, 4) * 10 + boost * 8)
    return min(100, 0.55 * relevance + 0.45 * j.ats)


FOCUS_WORDS: set[str] = set()


def score_jobs(jobs: list[Job], cv_text: str, cfg: dict) -> list[Job]:
    global FOCUS_WORDS
    FOCUS_WORDS = {w for p in _flat(cfg.get("focus_places", [])) for w in str(p).lower().split()}
    vocab = _vocab(cfg)
    cats = cfg.get("categories", [])
    out = []
    for j in jobs:
        if not passes_filters(j, cfg):
            continue
        full = j.title + " \n" + j.description
        f = cfg.get("filters", {})
        if f.get("hide_not_open_to_tunisia") and enrich.tunisia(j.location, full) == "no":
            continue
        yrs = enrich.experience_years(full)
        if j.kind == "job" and yrs is not None and yrs > f.get("max_experience_years", 99):
            continue
        if j.kind != "fellowship" and foreign_language_required(full, f.get("exclude_required_languages", [])):
            continue
        m = re.search(r"(?<![a-z])(?:work|based|relocat[a-z]*) (?:in|to) ([a-z]+)", j.title.lower())
        if m and FOCUS_WORDS and m.group(1) not in FOCUS_WORDS:
            continue  # "... - Work In Sofia, Bulgaria": relocation to a place you didn't choose
        title, body = j.title.lower(), f"{j.description} {' '.join(map(str, j.tags))}".lower()
        j.ats, j.matched, j.missing = ats_score(cv_text, f"{j.title} \n{body}", vocab)
        best, fit = None, ""
        for cat in cats:
            j.fit = ""
            sc = _score_in_category(j, cat, title, body)
            if sc is not None and (best is None or sc > best[0]):
                best, fit = (sc, cat["name"]), j.fit
        j.fit = fit
        if not best:
            continue
        j.score, j.category = round(min(100, best[0]), 1), best[1]  # bonus decides the category, score stays 0-100
        j.employment = detect_employment(f"{j.title} {j.description[:1500]}")
        out.append(j)
    out.sort(key=lambda x: x.score, reverse=True)
    return [j for j in out if j.score >= cfg.get("min_score", 35)]
