"""Free job / internship / fellowship sources. No API keys needed."""
from __future__ import annotations

import html
import json
import time
import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
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
    check: dict | None = None    # AI screening verdict: keep, chance, family, visa, why
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


BOARDS_OK: set[str] = set()   # "ashby-monzo" ... boards that answered this run
LIVE_IDS: set[str] = set()    # every posting id those boards still list


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
        BOARDS_OK.add(f"{ats}-{company}")
        LIVE_IDS.update(f"{ats}-{company}-{r[0]}" for r in rows)
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


ADZUNA_COUNTRY = {"gb": "United Kingdom", "it": "Italy", "de": "Germany", "nl": "Netherlands", "es": "Spain",
                  "be": "Belgium", "ch": "Switzerland", "at": "Austria", "pl": "Poland", "fr": "France"}


def adzuna(_terms, opts: dict | None = None) -> list[Job]:
    """Adzuna job search engine (free developer key). Rotates country x query pairs so each run stays small:
    8 runs a day x `per_run` searches stays under the free limit (250 searches a day)."""
    import os as _os
    app_id, app_key = _os.getenv("ADZUNA_APP_ID", "").strip(), _os.getenv("ADZUNA_APP_KEY", "").strip()
    opts = opts or {}
    if not (app_id and app_key):
        return []
    pairs = [(c, q) for c in opts.get("countries", []) for q in opts.get("queries", [])]
    if not pairs:
        return []
    per_run = opts.get("per_run", 28)
    slot = int(datetime.now(timezone.utc).timestamp() // (3 * 3600))  # changes every 3 hours
    start = (slot * per_run) % len(pairs)
    batch = [pairs[(start + i) % len(pairs)] for i in range(min(per_run, len(pairs)))]
    out, seen = [], set()
    for country, q in batch:
        try:
            r = requests.get(f"https://api.adzuna.com/v1/api/jobs/{country}/search/1", headers=UA, timeout=TIMEOUT,
                             params={"app_id": app_id, "app_key": app_key, "what": q, "results_per_page": 50,
                                     "max_days_old": opts.get("max_days_old", 21), "content-type": "application/json"})
            if r.status_code == 429:
                break  # daily/minute limit reached: try again next run
            data = r.json() if r.ok else {}
        except Exception:
            continue
        for j in data.get("results", []):
            jid = f"adzuna-{j.get('id')}"
            if jid in seen:
                continue
            seen.add(jid)
            area = (j.get("location") or {}).get("display_name") or ""
            country_name = ADZUNA_COUNTRY.get(country, country.upper())
            loc = area if country_name.lower() in area.lower() else ", ".join(x for x in (area, country_name) if x)
            title, desc = clean(j.get("title")), clean(j.get("description"))
            sal = ""
            if j.get("salary_min"):
                sal = f"{int(j['salary_min'])}" + (f"–{int(j['salary_max'])}" if j.get("salary_max") else "") + \
                      (" GBP" if country == "gb" else " CHF" if country == "ch" else " PLN" if country == "pl" else " EUR")
            contract = " ".join(x for x in (j.get("contract_time"), j.get("contract_type")) if x).replace("_", "-")
            out.append(Job(
                id=jid, title=title, company=clean((j.get("company") or {}).get("display_name", "")),
                url=j.get("redirect_url", ""), description=(f"Contract: {contract}\n" if contract else "") + desc,
                location=loc, source="Adzuna", kind=detect_kind(title, desc[:300]),
                work_mode=detect_mode(f"{title} {desc[:600]}") if re.search(r"remote|hybrid", f"{title} {desc}", re.I) else "unknown",
                posted=_dt(j.get("created")), salary=sal,
            ))
        time.sleep(2.6)  # free plan: max 25 searches per minute
    return out


def curated(_terms, items: list | None = None) -> list[Job]:
    """Hand-picked programs found by web research (volunteer calls, ambassador programs, AI schools...).
    They stay listed until their deadline passes; 'rolling' ones stay until removed from config.yaml."""
    out = []
    for it in items or []:
        dl = str(it.get("deadline", "")).strip()
        desc = it.get("description", "") + (f"\nDeadline: {dl}" if re.match(r"\d{4}-\d{2}-\d{2}", dl) else
                                            f"\nApplication window: {dl or 'rolling'} (check the official page).")
        j = Job(id="curated-" + re.sub(r"[^a-z0-9]+", "-", it["title"].lower()).strip("-")[:60], title=it["title"],
                company=it.get("org", ""), url=it["url"], description=desc, location=it.get("location", "Online"),
                source="Curated (web research)", kind=it.get("kind", "event"),
                work_mode=it.get("mode", "remote"))
        j.category = it.get("category", "")
        j.fit = "Excellent"
        j.score = 95.0
        j.check = {"keep": True, "chance": int(it.get("chance", 70)), "family": it.get("family", "event"),
                   "visa": it.get("visa", "none"), "why": it.get("why", "")}
        out.append(j)
    return out


def devpost(_terms, opts: dict | None = None) -> list[Job]:
    """Open & upcoming hackathons on Devpost (most are online, so joinable from Tunisia)."""
    opts = opts or {}
    out, seen = [], set()
    for theme in opts.get("themes", [""]):
        for page in range(1, opts.get("pages", 2) + 1):
            params = {"status[]": ["upcoming", "open"], "per_page": 50, "page": page, "order_by": "deadline"}
            if theme:
                params["themes[]"] = theme
            try:
                hs = _get("https://devpost.com/api/hackathons", params=params).get("hackathons", [])
            except Exception:
                break
            for h in hs:
                if h.get("id") in seen:
                    continue
                seen.add(h.get("id"))
                dates = h.get("submission_period_dates", "")  # "Oct 01 - Nov 12, 2026"
                m = re.search(r"-\s*([A-Za-z]{3})\s+(\d{1,2}),\s*(\d{4})", dates) or re.search(r"([A-Za-z]{3})\s+(\d{1,2}),\s*(\d{4})", dates)
                end = f"{m.group(2)} {m.group(1)} {m.group(3)}" if m else ""
                loc = (h.get("displayed_location") or {}).get("location", "Online")
                themes = ", ".join(t.get("name", "") for t in h.get("themes") or [])
                prize = clean(str(h.get("prize_amount", "")))
                desc = (f"Hackathon by {h.get('organization_name') or 'Devpost'}. Themes: {themes}. Prizes: {prize}. "
                        f"Submission period: {dates}. Registrations: {h.get('registrations_count', '')}. "
                        f"{'Online event: join from anywhere.' if 'online' in loc.lower() else 'In-person event in ' + loc + '.'} "
                        f"Free to join. Technology / coding hackathon." + (f"\nDeadline: {end}" if end else ""))
                out.append(Job(
                    id=f"devpost-{h.get('id')}", title=f"{h.get('title', '')} (hackathon)", company=h.get("organization_name") or "Devpost",
                    url=h.get("url", ""), description=desc, location=loc, source="Devpost", kind="event",
                    work_mode="remote" if "online" in loc.lower() else "onsite", salary=prize,
                ))
    return out


def gdg_events(_terms, opts: dict | None = None) -> list[Job]:
    """Google Developer Groups events: online AI events, events of chapters in your places (incl. Tunisia)."""
    from .match import written_in  # local import: match imports this module
    opts = opts or {}
    places = [p.lower() for p in opts.get("chapters", [])]
    topic = re.compile(opts.get("topics_regex", r"\b(ai|ml|gemini|machine learning|deep learning|data|llm|genai|devfest|"
                                                r"build with ai|tensorflow|keras|cloud|agent|fintech|hackathon)\b"), re.I)
    out = []
    for page in range(1, opts.get("pages", 6) + 1):
        try:
            d = _get("https://gdg.community.dev/api/event_slim/", params={"status": "Live", "page_size": 100, "page": page})
        except Exception:
            break
        for e in d.get("results", []):
            title, chapter = clean(e.get("title", "")), e.get("chapter_title", "")
            desc = clean(e.get("description") or e.get("description_short") or "")[:3000]
            virtual = (e.get("audience_type") or "").upper() == "VIRTUAL"
            local = any(p in chapter.lower() for p in places)
            if not (local or (virtual and topic.search(f"{title} {desc[:600]}"))):
                continue
            if written_in(f"{title} {desc}") and not re.search(r"tunis|sousse|sfax|monastir|bizerte|gabes|nabeul|kairouan", chapter, re.I):
                continue  # in a language she doesn't read (Tunisian chapters write French/English/Arabic)
            when = (e.get("start_date") or "")[:10]
            out.append(Job(
                id=f"gdg-{e.get('id')}", title=f"{title} — {chapter}", company=chapter,
                url=e.get("static_url") or e.get("custom_tickets_url") or e.get("url") or "https://gdg.community.dev/events/",
                description=(f"Google Developer Group event ({'online' if virtual else 'in person'}), free community event. "
                             f"{desc}\nDeadline: {when}" if when else desc),
                location="Online" if virtual else chapter.replace("GDG", "").strip(), source="GDG", kind="event",
                work_mode="remote" if virtual else "onsite", posted=_dt(e.get("start_date")),
            ))
        if not d.get("next"):
            break
    return out


def wp_search(_terms, opts: dict | None = None) -> list[Job]:
    """Searches opportunity sites (WordPress) and reads FULL posts, so real deadlines and funding details are known."""
    opts = opts or {}
    after = (datetime.now(timezone.utc) - timedelta(days=opts.get("days", 75))).strftime("%Y-%m-%dT00:00:00")
    out, seen = [], set()
    for site in opts.get("sites", []):
        for q in opts.get("queries", []):
            try:
                r = requests.get(site.rstrip("/") + "/wp-json/wp/v2/posts", headers=UA, timeout=TIMEOUT,
                                 params={"search": q, "per_page": opts.get("per_query", 30), "after": after,
                                         "_fields": "id,link,date,title,content"})
                posts = r.json() if r.ok else []
            except Exception:
                continue
            if not isinstance(posts, list):
                continue
            for p in posts:
                link = p.get("link", "")
                if not link or link in seen:
                    continue
                seen.add(link)
                title = clean((p.get("title") or {}).get("rendered", ""))
                body = clean((p.get("content") or {}).get("rendered", ""))[:9000]
                if re.match(r"^\d+\s+\w+", title) or re.search(r"\b(how to|tips|currently open|list of)\b", title, re.I):
                    continue  # round-up / advice articles, not an opportunity
                out.append(Job(
                    id=f"wp-{link}", title=title, company="", url=link, description=body,
                    location="", source=re.sub(r"^https?://(www\.)?", "", site).split("/")[0],
                    kind=rss_kind(title, body), work_mode=detect_mode(f"{title} {body[:800]}"),
                    posted=_dt(p.get("date")),
                ))
            time.sleep(0.2)
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
    "wp_search": wp_search,
    "adzuna": adzuna,
    "devpost": devpost,
    "curated": curated,
    "gdg_events": gdg_events,
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
                     "jobs_ac_uk": cfg.get("jobs_ac_uk_queries"), "wp_search": cfg.get("opportunity_search"),
                     "adzuna": cfg.get("adzuna"), "devpost": cfg.get("devpost"), "curated": cfg.get("curated"),
                     "gdg_events": cfg.get("gdg_events")}
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
