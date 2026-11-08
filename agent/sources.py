"""Free job / internship / fellowship sources. No API keys needed."""
from __future__ import annotations

import html
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime

import feedparser
import requests

UA = {"User-Agent": "Mozilla/5.0 (personal job-alert agent)"}
TIMEOUT = 30


@dataclass
class Job:
    id: str
    title: str
    company: str
    url: str
    description: str
    location: str = ""
    source: str = ""
    kind: str = "job"            # job | internship | fellowship
    work_mode: str = "remote"    # remote | hybrid | onsite | unknown
    posted: datetime | None = None
    tags: list[str] = field(default_factory=list)
    salary: str = ""

    # filled later
    category: str = ""
    fit: str = ""                # Excellent | Very good | Good (target jobs)
    employment: str = ""         # full-time | part-time | ""
    score: float = 0.0
    ats: float = 0.0
    matched: list[str] = field(default_factory=list)
    missing: list[str] = field(default_factory=list)


def clean(text: str | None) -> str:
    text = html.unescape(text or "")
    text = re.sub(r"<(br|/p|/li|/h\d)[^>]*>", "\n", text, flags=re.I)
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"[ \t\r\f\v]+", " ", text)
    return re.sub(r"\n\s*\n+", "\n", text).strip()


def _dt(value) -> datetime | None:
    if value is None or value == "":
        return None
    try:
        if isinstance(value, (int, float)):
            return datetime.fromtimestamp(value, tz=timezone.utc)
        s = str(value)
        if s.isdigit():
            return datetime.fromtimestamp(int(s), tz=timezone.utc)
        try:
            d = datetime.fromisoformat(s.replace("Z", "+00:00"))
        except ValueError:
            d = parsedate_to_datetime(s)
        return d if d.tzinfo else d.replace(tzinfo=timezone.utc)
    except Exception:
        return None


def _get(url, **kw):
    r = requests.get(url, headers=UA, timeout=TIMEOUT, **kw)
    r.raise_for_status()
    return r.json()


def detect_kind(title: str, text: str) -> str:
    t = f"{title} {text[:400]}".lower()
    if re.search(r"\b(fellowship|fellows?\b|scholarship|grant|bootcamp|residency)", t):
        return "fellowship"
    if re.search(r"\b(intern|internship|trainee|apprentice|working student|werkstudent|graduate program)", t):
        return "internship"
    return "job"


def detect_mode(text: str, remote_flag: bool | None = None) -> str:
    t = text.lower()
    if "hybrid" in t:
        return "hybrid"
    if remote_flag or re.search(r"\b(remote|work from home|wfh|anywhere|online)\b", t):
        return "remote"
    if remote_flag is False:
        return "onsite"
    return "unknown"


# ---------------------------------------------------------------- sources

def remotive(search_terms: list[str]) -> list[Job]:
    out, seen = [], set()
    for term in search_terms[:6] or [""]:
        data = _get("https://remotive.com/api/remote-jobs", params={"search": term, "limit": 100})
        for j in data.get("jobs", []):
            if j["id"] in seen:
                continue
            seen.add(j["id"])
            desc = clean(j.get("description"))
            out.append(Job(
                id=f"remotive-{j['id']}", title=j["title"], company=j.get("company_name", ""),
                url=j["url"], description=desc, location=j.get("candidate_required_location", ""),
                source="Remotive", kind=detect_kind(j["title"], j.get("job_type", "")),
                work_mode="remote", posted=_dt(j.get("publication_date")),
                tags=j.get("tags") or [], salary=j.get("salary") or "",
            ))
    return out


def remoteok(_terms) -> list[Job]:
    data = _get("https://remoteok.com/api")
    out = []
    for j in data[1:]:
        if not isinstance(j, dict) or "id" not in j:
            continue
        desc = clean(j.get("description"))
        sal = f"${j['salary_min']}-{j['salary_max']}" if j.get("salary_min") else ""
        out.append(Job(
            id=f"remoteok-{j['id']}", title=j.get("position", ""), company=j.get("company", ""),
            url=j.get("url") or j.get("apply_url", ""), description=desc, location=j.get("location", ""),
            source="RemoteOK", kind=detect_kind(j.get("position", ""), desc), work_mode="remote",
            posted=_dt(j.get("epoch") or j.get("date")), tags=j.get("tags") or [], salary=sal,
        ))
    return out


def arbeitnow(_terms) -> list[Job]:
    out = []
    for page in (1, 2, 3):
        data = _get("https://www.arbeitnow.com/api/job-board-api", params={"page": page})
        for j in data.get("data", []):
            desc = clean(j.get("description"))
            out.append(Job(
                id=f"arbeitnow-{j['slug']}", title=j["title"], company=j.get("company_name", ""),
                url=j["url"], description=desc, location=j.get("location", ""), source="Arbeitnow",
                kind=detect_kind(j["title"], " ".join(j.get("job_types") or [])),
                work_mode=detect_mode(f"{j['title']} {desc[:600]}", j.get("remote")),
                posted=_dt(j.get("created_at")), tags=j.get("tags") or [],
            ))
    return out


def jobicy(terms) -> list[Job]:
    raw, ids = [], set()
    for params in [{"count": 100}] + [{"count": 50, "tag": t} for t in terms[:6]]:
        try:
            for j in _get("https://jobicy.com/api/v2/remote-jobs", params=params).get("jobs", []):
                if j["id"] not in ids:
                    ids.add(j["id"])
                    raw.append(j)
        except Exception:
            continue
    out = []
    for j in raw:
        desc = clean(j.get("jobDescription") or j.get("jobExcerpt"))
        sal = f"{j.get('salaryMin')}-{j.get('salaryMax')} {j.get('salaryCurrency', '')}" if j.get("salaryMin") else ""
        out.append(Job(
            id=f"jobicy-{j['id']}", title=html.unescape(j["jobTitle"]), company=j.get("companyName", ""),
            url=j["url"], description=desc, location=j.get("jobGeo", ""), source="Jobicy",
            kind=detect_kind(j["jobTitle"], str(j.get("jobType", ""))), work_mode="remote",
            posted=_dt(j.get("pubDate")), tags=j.get("jobIndustry") or [], salary=sal,
        ))
    return out


def himalayas(terms) -> list[Job]:
    raw, ids = [], set()
    calls = [("https://himalayas.app/jobs/api", {"limit": 20, "offset": o}) for o in (0, 20, 40, 60, 80)]
    calls += [("https://himalayas.app/jobs/api/search", {"q": t}) for t in terms[:6]]
    for url, params in calls:
        try:
            for j in _get(url, params=params).get("jobs", []):
                if j["guid"] not in ids:
                    ids.add(j["guid"])
                    raw.append(j)
        except Exception:
            continue
    out = []
    if True:
        for j in raw:
            desc = clean(j.get("description") or j.get("excerpt"))
            out.append(Job(
                id=f"himalayas-{j['guid']}", title=j["title"], company=j.get("companyName", ""),
                url=j.get("applicationLink") or j["guid"], description=desc,
                location=", ".join(j.get("locationRestrictions") or []) or "Worldwide",
                source="Himalayas", kind=detect_kind(j["title"], j.get("employmentType", "")),
                work_mode="remote", posted=_dt(j.get("pubDate")), tags=j.get("categories") or [],
            ))
    return out


def workable(_terms, queries: list[str] | None = None) -> list[Job]:
    """Workable's job search, limited to remote jobs that are open in Tunisia."""
    out, seen = [], set()
    for q in queries or ["customer support"]:
        try:
            data = _get("https://jobs.workable.com/api/v1/jobs",
                        params={"query": q, "location": "Tunisia", "workplace": "remote"})
        except Exception:
            continue
        for j in data.get("jobs", []):
            if j.get("id") in seen or j.get("workplace") != "remote":
                continue
            seen.add(j.get("id"))
            loc = j.get("location") or {}
            if (loc.get("countryName") or "").lower() != "tunisia":
                continue
            desc = clean("\n".join(str(j.get(k) or "") for k in ("description", "requirementsSection", "benefitsSection")))
            emp = (j.get("employmentType") or "").replace("_", " ")
            out.append(Job(
                id=f"workable-{j['id']}", title=j["title"], company=(j.get("company") or {}).get("title", ""),
                url=j.get("url", ""), description=f"Employment type: {emp}\n{desc}",
                location="Tunisia (remote)", source="Workable", kind=detect_kind(j["title"], emp),
                work_mode="remote", posted=_dt(j.get("created")),
            ))
    return out


def rss(feeds: list[str]) -> list[Job]:
    """Fellowship / scholarship / internship feeds (Opportunity Desk etc.)."""
    out = []
    for feed_url in feeds:
        f = feedparser.parse(feed_url, agent=UA["User-Agent"])
        name = f.feed.get("title", feed_url)
        for e in f.entries:
            body = clean(e.get("content", [{}])[0].get("value") if e.get("content") else e.get("summary"))
            title = clean(e.get("title"))
            company = ""  # opportunity blogs: the real organisation is inside the post
            if "weworkremotely" in feed_url and ": " in title:  # "Company: Job title"
                company, title = title.split(": ", 1)
            out.append(Job(
                id=f"rss-{e.get('id') or e.get('link')}", title=title, company=company, url=e.get("link", ""),
                description=body, location="", source=name,
                kind=detect_kind(title, body),
                work_mode="remote" if "weworkremotely" in feed_url else detect_mode(f"{title} {body[:800]}"),
                posted=_dt(e.get("published") or e.get("updated")),
                tags=[t.get("term", "") for t in e.get("tags", [])],
            ))
    return out


SOURCES = {
    "workable": workable,
    "remotive": remotive,
    "remoteok": remoteok,
    "arbeitnow": arbeitnow,
    "jobicy": jobicy,
    "himalayas": himalayas,
}


def fetch_all(cfg: dict, log=print) -> list[Job]:
    jobs: list[Job] = []
    terms = cfg.get("search_terms", [])
    for name in cfg.get("sources", list(SOURCES)):
        if name not in SOURCES:
            continue
        try:
            got = SOURCES[name](terms, cfg.get("workable_queries")) if name == "workable" else SOURCES[name](terms)
            log(f"  {name}: {len(got)}")
            jobs += got
        except Exception as ex:  # one broken source must never stop the run
            log(f"  {name}: FAILED ({ex})")
    if cfg.get("rss_feeds"):
        try:
            got = rss(cfg["rss_feeds"])
            log(f"  rss feeds: {len(got)}")
            jobs += got
        except Exception as ex:
            log(f"  rss: FAILED ({ex})")
    return jobs
