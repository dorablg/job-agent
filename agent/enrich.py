"""Pulls filterable details out of a posting: country, paid, deadline, experience, degree, languages,
requirements. Pure text rules (free, no AI) so every listing gets them."""
from __future__ import annotations

import re
from datetime import datetime

COUNTRIES = {
    "United States": ["united states", "usa", "u.s.", "u.s.a", "us-based", "america"],
    "United Kingdom": ["united kingdom", "uk", "england", "london", "scotland", "britain"],
    "Germany": ["germany", "deutschland", "berlin", "munich", "münchen", "hamburg", "frankfurt", "cologne", "köln"],
    "France": ["france", "paris", "lyon", "marseille", "toulouse"], "Tunisia": ["tunisia", "tunis", "sousse", "sfax"],
    "Canada": ["canada", "toronto", "vancouver", "montreal"], "Netherlands": ["netherlands", "amsterdam"],
    "Spain": ["spain", "madrid", "barcelona"], "Italy": ["italy", "rome", "milan"], "Portugal": ["portugal", "lisbon"],
    "Belgium": ["belgium", "brussels"], "Switzerland": ["switzerland", "zurich", "geneva"], "Austria": ["austria", "vienna"],
    "Ireland": ["ireland", "dublin"], "Poland": ["poland", "warsaw"], "Sweden": ["sweden", "stockholm"],
    "Denmark": ["denmark", "copenhagen"], "Norway": ["norway", "oslo"], "Finland": ["finland", "helsinki"],
    "Czechia": ["czech", "prague"], "Romania": ["romania", "bucharest"], "Greece": ["greece", "athens"],
    "Hungary": ["hungary", "budapest"], "Estonia": ["estonia", "tallinn"], "Luxembourg": ["luxembourg"],
    "Morocco": ["morocco", "casablanca", "rabat"], "Egypt": ["egypt", "cairo"], "Algeria": ["algeria", "algiers"],
    "Nigeria": ["nigeria", "lagos", "abuja"], "Kenya": ["kenya", "nairobi"], "South Africa": ["south africa", "cape town", "johannesburg"],
    "Ghana": ["ghana", "accra"], "Rwanda": ["rwanda", "kigali"], "UAE": ["uae", "united arab emirates", "dubai", "abu dhabi"],
    "Saudi Arabia": ["saudi", "riyadh"], "Qatar": ["qatar", "doha"], "Turkey": ["turkey", "türkiye", "istanbul"],
    "India": ["india", "bangalore", "bengaluru", "mumbai", "delhi"], "Japan": ["japan", "tokyo", "kyoto"],
    "South Korea": ["korea", "seoul"], "China": ["china", "beijing", "shanghai"], "Singapore": ["singapore"],
    "Australia": ["australia", "sydney", "melbourne"], "Brazil": ["brazil", "são paulo", "sao paulo"],
    "Mexico": ["mexico"], "Argentina": ["argentina"], "Philippines": ["philippines", "manila"],
    "Taiwan": ["taiwan", "taipei"], "Israel": ["israel", "tel aviv"], "Malaysia": ["malaysia", "kuala lumpur"],
}
REGIONS = {"Worldwide": ["worldwide", "anywhere", "global", "remote - anywhere", "international"],
           "Europe": ["europe", "eu ", "emea", "european"], "Africa": ["africa", "african"],
           "MENA": ["mena", "middle east", "north africa"], "Asia": ["asia", "apac"], "Americas": ["americas", "latam", "latin america"]}
LANGS = ["English", "French", "German", "Spanish", "Arabic", "Italian", "Portuguese", "Dutch", "Polish", "Turkish",
         "Croatian", "Serbian", "Slovak", "Slovenian", "Ukrainian", "Lithuanian", "Latvian", "Estonian", "Flemish", "Hindi",
         "Thai", "Vietnamese", "Indonesian", "Malay",
         "Japanese", "Chinese", "Mandarin", "Korean", "Russian", "Swedish", "Danish", "Norwegian", "Greek", "Bulgarian",
         "Romanian", "Czech", "Hebrew", "Finnish", "Hungarian"]
MONTHS = "january february march april may june july august september october november december".split()


def _has(term: str, text: str) -> bool:
    return re.search(r"(?<![a-z0-9])" + re.escape(term) + r"(?![a-z0-9])", text) is not None


def countries(location: str, title: str, text: str) -> list[str]:
    loc = f" {location.lower()} "
    found = [c for c, al in COUNTRIES.items() if any(_has(a, loc) for a in al)]
    if not found:  # opportunity posts: "... 2027 in Japan (Fully Funded)", "Funded to the U.S."
        t = f" {title.lower()} "
        found = [c for c, al in COUNTRIES.items() if any(_has(a, t) for a in al)]
    return found[:6]


def regions(location: str, text: str) -> list[str]:
    loc = location.lower()
    r = [name for name, al in REGIONS.items() if any(a in loc for a in al)]
    if not r and not location.strip() and re.search(r"\b(work from anywhere|fully remote|remote worldwide)\b", text.lower()):
        r = ["Worldwide"]
    return r


def paid(text: str, salary: str, kind: str) -> str:
    t = text.lower()
    if re.search(r"\bunpaid\b|\bvolunteer(ing)? (role|position|opportunity)\b|\bno (stipend|compensation|salary)\b", t):
        return "unpaid"
    if salary or re.search(r"fully[- ]funded|\bfunded\b|\bstipend\b|\bpaid\b|\bsalary\b|\bcompensation\b|\ballowance\b|"
                           r"\bhonorarium\b|[$€£]\s?\d|\d\s?(k|000)\s?(usd|eur|gbp|\$|€)|per (hour|month|year|annum)|/hr\b|"
                           r"\btuition (waiver|covered)|scholarship covers|travel (costs|expenses) (covered|paid)", t):
        return "paid"
    if kind == "job":
        return "paid"  # real jobs are paid even when the ad hides the number
    return "unknown"


def _parse_date(s: str) -> str:
    s = re.sub(r"(\d)(st|nd|rd|th)", r"\1", s.strip().rstrip(".,")).replace(",", "")
    for fmt in ("%B %d %Y", "%d %B %Y", "%b %d %Y", "%d %b %Y", "%Y-%m-%d", "%d/%m/%Y"):
        try:
            return datetime.strptime(s, fmt).date().isoformat()
        except ValueError:
            pass
    return ""


_MONTHS = {m[:3]: i + 1 for i, m in enumerate(MONTHS)}


def _ymd(day: int, month: int, year: int | None) -> str:
    from datetime import date as _d
    today = _d.today()
    if year is None:  # "Deadline: Nov. 2" -> this year, or next year if that was long ago
        year = today.year
        try:
            if (today - _d(year, month, day)).days > 120:
                year += 1
        except ValueError:
            return ""
    try:
        return _d(year, month, day).isoformat()
    except ValueError:
        return ""


def deadline_strict(text: str) -> str:
    """Finds 'Deadline: December 5, 2026', '8th January 2027', 'Nov. 2', 'Dec 2026', ISO dates. '' if unknown."""
    for m in re.finditer(r"(?:application\s+)?(?:deadline|apply by|applications? (?:close|closes|due)|closing date|due date|"
                         r"submission deadline|last date)\s*(?:is|on|:|–|-|—)?\s*(?:\w+day,?\s*)?([^\n|]{0,40})", text, re.I):
        s = m.group(1).strip()
        if re.match(r"(unspecified|varies|rolling|open|tba|tbc|ongoing|n/?a)", s, re.I):
            continue
        d = re.match(r"(\d{4})-(\d{2})-(\d{2})", s)
        if d:
            return _ymd(int(d.group(3)), int(d.group(2)), int(d.group(1)))
        d = re.match(r"(\d{1,2})(?:st|nd|rd|th)?\s+(?:of\s+)?([A-Za-z]{3,9})\.?,?\s*(\d{4})?", s)
        if d and d.group(2)[:3].lower() in _MONTHS:
            return _ymd(int(d.group(1)), _MONTHS[d.group(2)[:3].lower()], int(d.group(3)) if d.group(3) else None)
        d = re.match(r"([A-Za-z]{3,9})\.?\s+(\d{1,2})(?!\d)(?:st|nd|rd|th)?,?\s*(\d{4})?", s)
        if d and d.group(1)[:3].lower() in _MONTHS:
            return _ymd(int(d.group(2)), _MONTHS[d.group(1)[:3].lower()], int(d.group(3)) if d.group(3) else None)
        d = re.match(r"([A-Za-z]{3,9})\.?\s+(\d{4})", s)  # "Dec 2026" -> end of that month
        if d and d.group(1)[:3].lower() in _MONTHS:
            import calendar
            mo, yr = _MONTHS[d.group(1)[:3].lower()], int(d.group(2))
            return _ymd(calendar.monthrange(yr, mo)[1], mo, yr)
        d = re.match(r"(\d{1,2})/(\d{1,2})/(\d{4})", s)
        if d:
            return _ymd(int(d.group(1)), int(d.group(2)), int(d.group(3)))
    return ""


def deadline(text: str) -> str:
    strict = deadline_strict(text)
    if strict:
        return strict
    return _deadline_loose(text)


def _deadline_loose(text: str) -> str:
    m = re.search(r"(?:deadline|apply by|applications? (?:close|closes|due)|closing date|submit .{0,30}? by|due date)"
                  r"[^0-9a-z]{0,25}(?:is|on|:)?\s*(?:\w+day,?\s*)?"
                  r"(\d{1,2}(?:st|nd|rd|th)?\s+[A-Za-z]{3,9},?\s+\d{4}|[A-Za-z]{3,9}\s+\d{1,2}(?:st|nd|rd|th)?,?\s+\d{4}|\d{4}-\d{2}-\d{2})",
                  text, flags=re.I)
    return _parse_date(m.group(1)) if m else ""


def experience_years(text: str) -> int | None:
    yrs = [int(m.group(1)) for m in re.finditer(
        r"(\d{1,2})\s*\+?\s*(?:-\s*\d{1,2}\s*)?(?:years?|yrs?)(?:'s)?\s+(?:of\s+)?(?:[a-z/&,-]+\s+){0,4}?experience", text.lower())]
    yrs = [y for y in yrs if y <= 15]
    if yrs:
        return min(yrs)
    if re.search(r"\b(no (prior )?experience (required|needed)|entry[- ]level|recent graduate|new grad)\b", text.lower()):
        return 0
    return None


def degree(text: str) -> str:
    t = text.lower()
    if re.search(r"\bph\.?d\b|doctoral|doctorate", t):
        return "PhD"
    if re.search(r"\bmaster'?s?\b|\bm\.?sc\b|\bmba\b|postgraduate", t):
        return "Master's"
    if re.search(r"\bbachelor'?s?\b|\bb\.?sc\b|\bundergraduate\b|university degree|college degree|\bdegree in\b", t):
        return "Bachelor's"
    if re.search(r"high school|secondary school|\bged\b", t):
        return "High school"
    return ""


def languages(text: str) -> list[str]:
    t = text.lower()
    out = []
    for lang in LANGS:
        l = lang.lower()
        if re.search(rf"\b(fluent|fluency|native|proficien\w*|business[- ]level|written and spoken|speak\w*|c1|c2|b2)\b[^.\n]{{0,40}}\b{l}\b"
                     rf"|\b{l}\b[^.\n]{{0,25}}\b(speaker|fluency|fluent|proficien\w*|native|language|required|skills)\b", t):
            out.append(lang)
        elif re.search(rf"(?<![a-z]){l}[- ](speaking|speakers?|market|native)", t[:300]):  # "Greek Speaking ...", "German Speakers", "Czech Market"
            out.append(lang)
    return out


def requirements(desc: str) -> list[str]:
    lines = [l.strip(" •-*·\t") for l in desc.split("\n")]
    head = re.compile(r"(requirement|qualification|what you('ll)? (need|bring)|you (have|bring|are)|who you are|"
                      r"about you|eligib|must have|skills|profile|we('re)? looking for|criteria)", re.I)
    out, take = [], 0
    for l in lines:
        if not l:
            continue
        if len(l) < 70 and head.search(l):
            take = 10
            continue
        if take and 12 < len(l) < 260:
            out.append(l)
            take -= 1
            if len(out) >= 10:
                break
        elif take and len(l) < 70 and l.endswith(":"):
            take = 0
    return out


OPEN_TO_TN = re.compile(r"tunisia|(?<!south )(?<!central )\bafrica(?!n republic)|\bmena\b|middle east|north africa|\bemea\b|worldwide|anywhere|global|"
                        r"work from anywhere|all countries|international", re.I)
CLOSED = re.compile(r"(must|need to|required to) (be )?(based|located|reside|living) in (the )?(us|usa|united states|uk|"
                    r"united kingdom|eu|european union|canada|europe|latam|india|philippines)|"
                    r"(eligible|authori[sz]ed|right) to work in (the )?(us|usa|united states|uk|united kingdom|eu|canada)|"
                    r"\b(us|usa|uk|eu|canada|latam)[- ]only\b|us citizens?|green card|"
                    r"anywhere in the (us|u\.s\.|usa|united states)|remote[ -]+\(?(us|usa|u\.s\.)\)?(?![a-z])|"
                    r"\b(us|u\.s\.)[- ]based (candidates|applicants|employees)|(within|in) the (us|u\.s\.|united states) only|"
                    r"\bw-2\b|\b401\(k\)", re.I)


def tunisia(location: str, text: str) -> str:
    """'yes' = posting is open to Tunisia, 'no' = clearly restricted elsewhere, 'check' = not stated."""
    loc = location or ""
    if re.search(r"tunisia", f"{loc} {text[:3000]}", re.I):
        return "yes"
    if CLOSED.search(text[:6000]):
        return "no"
    if OPEN_TO_TN.search(loc):
        return "yes"
    if loc.strip() and loc.strip().lower() not in ("remote", "n/a"):
        if re.search(r"europe|\beu\b|france|germany|spain|portugal|italy|netherlands|belgium", loc, re.I):
            return "check"  # European companies sometimes hire contractors in Tunisia
        return "no"     # a list of countries/regions that doesn't include Tunisia
    if re.search(r"work from anywhere|fully remote, anywhere|remote worldwide|location: anywhere", text, re.I):
        return "yes"
    return "check"


def visa(text: str) -> str:
    """'sponsor' = the posting offers visa sponsorship, 'rtw' = you must already have the right to work there."""
    t = text.lower()
    if re.search(r"(no|not|unable to|cannot|can't|do not|don't|does not|doesn't|won't|will not)\s+(be able to\s+)?"
                 r"(offer|provide|support)?\s*(visa\s+)?sponsor|without (the need for )?(visa )?sponsorship|"
                 r"(must|need to|required to) (already )?have (the |full |existing )?(right|permission|eligibility|authori[sz]ation) to work|"
                 r"right to work in the uk (is )?(required|essential)|must be eligible to work in the (uk|united kingdom|eu|italy)", t):
        return "rtw"
    if re.search(r"visa sponsorship (is )?(available|offered|provided|possible)|(we|will|can|able to) (offer |provide )?sponsor\w* "
                 r"(visas?|work permits?|skilled worker)|sponsorship (is )?available|skilled worker visa|relocation support|"
                 r"relocation (package|assistance)|we sponsor", t):
        return "sponsor"
    return ""


def currency(salary: str, text: str) -> str:
    s = f"{salary} {text[:6000]}"
    if re.search(r"\$\s?\d|\busd\b|us dollars?", s, re.I):
        return "USD"
    if re.search(r"€\s?\d|\d\s?€|\beur\b|euros?\b", s, re.I):
        return "EUR"
    if re.search(r"£\s?\d|\bgbp\b", s, re.I):
        return "GBP"
    return ""


def apply(r: dict) -> dict:
    """Adds the filter fields to a dashboard record (works on old records too)."""
    desc = r.get("description", "")
    text = f"{r.get('title', '')}\n{desc}"
    r["countries"] = countries(r.get("location", ""), r.get("title", ""), text)
    r["regions"] = regions(r.get("location", ""), text)
    r["paid"] = paid(text, r.get("salary", ""), r.get("kind", "job"))
    ai = r.get("ai") or {}
    r["deadline"] = (ai.get("deadline") or "")[:10] or r.get("deadline") or deadline(text)
    if ai.get("salary_or_funding") and not r.get("salary"):
        r["salary"] = ai["salary_or_funding"]
    if r.get("salary") and r["paid"] == "unknown":
        r["paid"] = "paid"
    r["travel"] = bool(re.search(r"fully[- ]funded|all[- ]expenses|flights?|airfare|air tickets?|round[- ]trip|accommodation|"
                                 r"lodging|travel (grant|support|award|costs|expenses)", text, re.I)) and r.get("kind") in ("event", "fellowship")
    r["tunisia"] = tunisia(r.get("location", ""), text)
    r["currency"] = currency(r.get("salary", ""), desc)
    r["visa"] = visa(text) if r.get("tunisia") != "yes" else ""
    if re.search(r"tunisia \(remote\)", r.get("location", ""), re.I) or (
            r.get("mode") == "remote" and r.get("location", "").count(",") >= 3):
        r["focus"] = "Remote (Tunisia)" if r.get("tunisia") == "yes" else "Remote"
    elif re.search(r"london|united kingdom|\buk\b|england|scotland|wales|cardiff|manchester|leeds|redhill", f"{r.get('location', '')} {r.get('title', '')}", re.I):
        r["focus"] = "London / UK"
    elif re.search(r"ital|milan|rome|roma|turin|torino|bologna|florence|firenze|naples|venice|padua|pisa|trento|verona",
                   f"{r.get('location', '')} {r.get('title', '')}", re.I):
        r["focus"] = "Italy"
    elif re.search(r"\b(uae|united arab emirates|dubai|abu dhabi|qatar|doha|saudi|riyadh|jeddah|bahrain|kuwait|oman|muscat)\b",
                   f"{r.get('location', '')} {r.get('title', '')}", re.I) and r.get("mode") != "remote":
        r["focus"] = "Gulf"
    elif re.search(r"europe|\bemea\b|germany|berlin|munich|hamburg|frankfurt|cologne|netherlands|amsterdam|rotterdam|utrecht|"
                   r"eindhoven|ireland|dublin|cork|spain|madrid|barcelona|valencia|belgium|brussels|antwerp|ghent|switzerland|"
                   r"zurich|z\u00fcrich|geneva|lausanne|basel|austria|vienna|portugal|lisbon|porto|sweden|stockholm|denmark|"
                   r"copenhagen|finland|helsinki|norway|oslo|estonia|tallinn|luxembourg|poland|warsaw|krakow|czech|prague|"
                   r"malta|cyprus|greece|athens|lithuania|vilnius|latvia|riga", r.get("location", ""), re.I) and r.get("mode") != "remote":
        r["focus"] = "Europe"
    elif r.get("mode") == "remote":
        r["focus"] = "Remote (Tunisia)" if r.get("tunisia") == "yes" else "Remote"
    else:
        r["focus"] = "Other"
    r["exp_years"] = experience_years(text)
    r["degree"] = degree(text)
    r["languages"] = languages(text)
    r["requirements"] = requirements(desc)
    if r["paid"] == "unknown" and r.get("kind") == "fellowship" and re.search(r"funded", r.get("title", ""), re.I):
        r["paid"] = "paid"
    return r
