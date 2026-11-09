"""Free job / internship / fellowship sources. No API keys needed."""
from __future__ import annotations

import html
import json
import time
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


WORKMODE = {"remote": "remote", "hybrid": "hybrid", "on_site": "onsite"}
FOCUS_LOC = re.compile(r"london|united kingdom|\buk\b|england|italy|italia|milan|milano|rome|roma|turin|torino|"
                       r"bologna|florence|firenze|naples|napoli|padua|padova|pisa|trento|genoa|genova|verona|bergamo", re.I)


def set_focus(places: list[str]) -> None:
    """Places you want on-site roles in (from config.yaml) + remote markers, for company boards and Workable."""
    global FOCUS_LOC
    words = [re.escape(str(p).lower()) for p in places if p] + ["remote", "anywhere", "worldwide", "global", "emea", "europe"]
    FOCUS_LOC = re.compile(r"(?<![a-z])(" + "|".join(sorted(set(words), key=len, reverse=True)) + r")(?![a-z])", re.I)


def workable(_terms, searches: list[dict] | None = None) -> list[Job]:
    """Workable's job search. Each search: {location, workplace (optional), queries}.
    Tunisia searches keep only remote jobs open in Tunisia; London/Italy keep jobs located there."""
    out, seen = [], set()
    for srch in searches or []:
        where = srch["location"]
        for q in srch.get("queries", []):
            params = {"query": q}
            if where:
                params["location"] = where
            if srch.get("workplace"):
                params["workplace"] = srch["workplace"]
            try:
                data = _get("https://jobs.workable.com/api/v1/jobs", params=params)
            except Exception:
                continue
            for j in data.get("jobs", []):
                if j.get("id") in seen:
                    continue
                loc = j.get("location") or {}
                country, city = (loc.get("countryName") or ""), (loc.get("city") or "")
                if where.lower() == "tunisia":
                    if country.lower() != "tunisia" or j.get("workplace") != "remote":
                        continue
                    location = "Tunisia (remote)"
                elif not where:  # remote anywhere: keep, Tunisia eligibility is judged later
                    if j.get("workplace") != "remote":
                        continue
                    location = ", ".join(x for x in (city, country) if x) or "Remote"
                else:
                    location = ", ".join(x for x in (city, country) if x)
                    if not FOCUS_LOC.search(location):
                        continue
                seen.add(j.get("id"))
                desc = clean("\n".join(str(j.get(k) or "") for k in ("description", "requirementsSection", "benefitsSection")))
                emp = (j.get("employmentType") or "").replace("_", " ")
                out.append(Job(
                    id=f"workable-{j['id']}", title=j["title"], company=(j.get("company") or {}).get("title", ""),
                    url=j.get("url", ""), description=f"Employment type: {emp}\n{desc}", location=location,
                    source="Workable", kind=detect_kind(j["title"], emp),
                    work_mode=WORKMODE.get(j.get("workplace"), "unknown"), posted=_dt(j.get("created")),
                ))
    return out


def company_boards(_terms, boards: dict | None = None) -> list[Job]:
    """Jobs from company career pages (Greenhouse / Lever / Ashby), kept only in London, UK or Italy."""
    out = []
    for company, ats in (boards or {}).items():
        try:
            if ats == "greenhouse":
                data = _get(f"https://boards-api.greenhouse.io/v1/boards/{company}/jobs", params={"content": "true"})
                rows = [(str(j["id"]), j["title"], j.get("absolute_url", ""), (j.get("location") or {}).get("name", ""),
                         clean(html.unescape(j.get("content") or "")), j.get("updated_at")) for j in data.get("jobs", [])]
            elif ats == "lever":
                data = _get(f"https://api.lever.co/v0/postings/{company}", params={"mode": "json"})
                rows = [(j["id"], j["text"], j.get("hostedUrl", ""), (j.get("categories") or {}).get("location", ""),
                         clean((j.get("descriptionPlain") or "") + "\n" + "\n".join(
                             f"{l.get('text', '')}\n{clean(l.get('content', ''))}" for l in j.get("lists") or [])),
                         j.get("createdAt", 0) / 1000 if j.get("createdAt") else None) for j in data]
            else:  # ashby
                data = _get(f"https://api.ashbyhq.com/posting-api/job-board/{company}")
                rows = [(j["id"], j["title"], j.get("jobUrl", ""),
                         ", ".join([j.get("location") or ""] + [x.get("location", "") for x in j.get("secondaryLocations") or []]),
                         clean(j.get("descriptionPlain") or j.get("descriptionHtml") or ""), j.get("publishedAt"))
                        for j in data.get("jobs", []) if j.get("isListed", True)]
        except Exception:
            continue
        name = {"trading212": "Trading 212", "complyadvantage": "ComplyAdvantage", "gocardless": "GoCardless",
                "oaknorth": "OakNorth", "truelayer": "TrueLayer", "elevenlabs": "ElevenLabs", "sumup": "SumUp",
                "9fin": "9fin"}.get(company, company.title())
        for jid, title, url, location, desc, posted in rows:
            if not FOCUS_LOC.search(location or ""):
                continue
            out.append(Job(
                id=f"{ats}-{company}-{jid}", title=title, company=name, url=url, description=desc,
                location=location, source=f"{name} careers", kind=detect_kind(title, desc[:300]),
                work_mode=detect_mode(f"{title} {location} {desc[:1500]}"), posted=_dt(posted),
            ))
    return out


ACADEMIC_TITLE = re.compile(r"research|machine learning|\bml\b|\bai\b|artificial intelligence|deep learning|data scien|"
                            r"\bnlp\b|computer vision|intern|ktp|graduate|software engineer", re.I)
ACADEMIC_SKIP = re.compile(r"faculty position|postdoc|post-doc|post doctoral|postdoctoral|lecturer|professor|reader in|chair in|studentship|"
                           r"\bphd\b|research fellow|head of|director|manager|senior|principal|technician|administrator", re.I)


def jobs_ac_uk(_terms, queries: list[str] | None = None, max_details: int = 40) -> list[Job]:
    """UK university & research-institute jobs (jobs.ac.uk search + the JobPosting data on each job page)."""
    links: dict[str, str] = {}
    for q in queries or []:
        try:
            r = requests.get("https://www.jobs.ac.uk/search/", params={"keywords": q, "sortOrder": "1"},
                             headers=UA, timeout=TIMEOUT)
            r.raise_for_status()
        except Exception:
            continue
        for href, text in re.findall(r'<a[^>]+href="(/job/[A-Z0-9]+/[^"]+)"[^>]*>(.*?)</a>', r.text, re.S):
            title = clean(text)
            if title and ACADEMIC_TITLE.search(title) and not ACADEMIC_SKIP.search(title):
                links.setdefault(href, title)
    out = []
    for href, title in list(links.items())[:max_details]:
        url = "https://www.jobs.ac.uk" + href
        try:
            page = requests.get(url, headers=UA, timeout=TIMEOUT).text
            m = re.search(r'<script type="application/ld\+json">(.*?)</script>', page, re.S)
            d = json.loads(m.group(1)) if m else {}
        except Exception:
            continue
        if isinstance(d, list):
            d = next((x for x in d if isinstance(x, dict) and x.get("@type") == "JobPosting"), {})
        org = d.get("hiringOrganization") or {}
        loc = d.get("jobLocation") or {}
        if isinstance(loc, list):
            loc = loc[0] if loc else {}
        addr = (loc.get("address") or {}) if isinstance(loc, dict) else {}
        city = addr.get("addressLocality") or addr.get("addressRegion") or ""
        country = addr.get("addressCountry") or "United Kingdom"
        if isinstance(country, dict):
            country = country.get("name", "United Kingdom")
        country = {"GB": "United Kingdom", "UK": "United Kingdom"}.get(str(country), str(country))
        sal = d.get("baseSalary") or {}
        salary = ""
        if isinstance(sal, dict):
            v = sal.get("value") or {}
            if isinstance(v, dict) and (v.get("minValue") or v.get("value")):
                salary = f"£{v.get('minValue') or v.get('value')}" + (f"–£{v['maxValue']}" if v.get("maxValue") else "")
        desc = clean(d.get("description") or "")
        deadline_txt = f"\nApplication deadline: {d['validThrough'][:10]}" if d.get("validThrough") else ""
        out.append(Job(
            id=f"jobsacuk-{href.split('/')[2]}", title=clean(d.get("title") or title),
            company=clean(org.get("name") if isinstance(org, dict) else str(org)) or "University",
            url=url, description=desc + deadline_txt, location=", ".join(x for x in (city, country) if x),
            source="jobs.ac.uk", kind=detect_kind(title, desc[:400]),
            work_mode=detect_mode(f"{title} {desc[:1500]}") if re.search(r"remote|hybrid", desc[:1500], re.I) else "onsite",
            posted=_dt(d.get("datePosted")), salary=salary,
        ))
        time.sleep(0.4)  # be polite
    return out


EVENT_RE = re.compile(r"\b(conference|summit|forum|symposium|congress|hackathon|bootcamp|boot camp|workshop|"
                      r"summer (school|program|programme|camp|course|institute|academy|research)|winter school|spring school|"
                      r"exchange|study (visit|tour)|youth camp|leadership camp|leadership (program|programme)|"
                      r"training (program|programme)|competition|challenge|festival|expo|delegation|youth assembly|"
                      r"model united nations|innovation week|tech week)\b", re.I)


def rss_kind(title: str, body: str) -> str:
    """Opportunity-site posts: scholarships/fellowships stay 'fellowship'; travel programs & events become 'event'."""
    if re.search(r"\b(scholarship|fellowship|fellows)\b", title, re.I) and not re.search(r"exchange|summer|conference", title, re.I):
        return "fellowship"
    if EVENT_RE.search(title):
        return "event"
    return detect_kind(title, body)


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
                kind=detect_kind(title, body) if "weworkremotely" in feed_url else rss_kind(title, body),
                work_mode="remote" if "weworkremotely" in feed_url else detect_mode(f"{title} {body[:800]}"),
                posted=_dt(e.get("published") or e.get("updated")),
                tags=[t.get("term", "") for t in e.get("tags", [])],
            ))
    return out


SOURCES = {
    "workable": workable,
    "company_boards": company_boards,
    "jobs_ac_uk": jobs_ac_uk,
    "remotive": remotive,
    "remoteok": remoteok,
    "arbeitnow": arbeitnow,
    "jobicy": jobicy,
    "himalayas": himalayas,
}


def fetch_all(cfg: dict, log=print) -> list[Job]:
    if cfg.get("focus_places"):
        set_focus(cfg["focus_places"])
    jobs: list[Job] = []
    terms = cfg.get("search_terms", [])
    for name in cfg.get("sources", list(SOURCES)):
        if name not in SOURCES:
            continue
        try:
            extra = {"workable": cfg.get("workable_searches"), "company_boards": cfg.get("company_boards"),
                     "jobs_ac_uk": cfg.get("jobs_ac_uk_queries")}
            got = SOURCES[name](terms, extra[name]) if name in extra else SOURCES[name](terms)
            log(f"  {name}: {len(got)}")
            jobs += got
        except Exception as ex:  # one broken source must never stop the run
            log(f"  {name}: FAILED ({ex})")
    n_rss = 0
    for feed in cfg.get("rss_feeds", []):  # one broken feed must not stop the others
        try:
            got = rss([feed])
            n_rss += len(got)
            jobs += got
        except Exception as ex:
            log(f"  rss {feed}: FAILED ({ex})")
    log(f"  rss feeds: {n_rss}")
    for j in jobs:  # some boards double-escape titles ("&amp;")
        j.title = html.unescape(html.unescape(j.title)).strip()
        j.company = html.unescape(j.company or "").strip()
    return jobs
