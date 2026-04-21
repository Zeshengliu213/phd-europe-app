"""jobs.ac.uk adapter — UK's main academic job board, PhD studentships filter.

Pagination uses ?startIndex=N&pageSize=25. We default to up to 8 pages
(~200 PhD positions). The first request also seeds session cookies that
the site requires for subsequent requests.
"""
from __future__ import annotations

import os
import re
import sys
import time
from datetime import datetime

from bs4 import BeautifulSoup

SOURCE_ID = "jobsac_uk"
BASE = "https://www.jobs.ac.uk"
# JOB_KIND switches between PhD studentships (default) and postdoctoral roles.
# PhD: jobTypeFacet=phds — clean studentship feed.
# Postdoc: jobTypeFacet=research-related + keyword postdoc; title regex below
# filters to true postdoc / research fellow positions to drop noise.
JOB_KIND = os.getenv("JOB_KIND", "phd").lower()
if JOB_KIND == "postdoc":
    SEARCH_URL = (
        "https://www.jobs.ac.uk/search/?jobTypeFacet%5B%5D=research-related"
        "&keywords=postdoc"
        "&pageSize=25&startIndex={start}"
    )
    _TITLE_OK_RE = re.compile(
        r"\b(post[-\s]?doc(toral)?|research\s+(fellow|associate|scientist))\b",
        re.I,
    )
else:
    SEARCH_URL = (
        "https://www.jobs.ac.uk/search/?jobTypeFacet%5B%5D=phds"
        "&pageSize=25&startIndex={start}"
    )
    _TITLE_OK_RE = None

_JOB_HREF_RE = re.compile(r"^/job/[A-Z0-9]+/")
_DATE_PLACED_RE = re.compile(
    r"Date\s+Placed:\s*(\d{1,2})\s+([A-Za-z]{3,9})(?:\s+(\d{4}))?",
    re.I,
)
# Detail pages carry "Closes: 4th May 2026". Listing cards do not.
_CLOSES_RE = re.compile(
    r"Clos(?:es|ing\s+date|ing\s+Date)\s*:?\s*"
    r"(\d{1,2})(?:st|nd|rd|th)?\s+([A-Za-z]{3,9})\s+(\d{4})",
    re.I,
)

_MAX_PAGES = int(os.getenv("JOBSAC_MAX_PAGES", "8"))
_REQ_SLEEP = float(os.getenv("JOBSAC_SLEEP", "0.4"))
# Set JOBSAC_FETCH_DETAILS=1 to fetch each detail page for the closing date
# (~200 extra requests, +80s).
_FETCH_DETAILS = os.getenv("JOBSAC_FETCH_DETAILS", "0") == "1"


def _parse_date(day: str, month: str, year: str | None) -> str | None:
    """Parse '4 May' or '4 May 2026' → ISO date.
    When year is omitted, infer the next occurrence: if the date has already
    passed this year, roll forward to next year.
    """
    try:
        today = datetime.utcnow().date()
        y = int(year) if year else today.year
        dt = datetime.strptime(f"{int(day):02d} {month[:3]} {y}", "%d %b %Y")
        if not year and dt.date() < today:
            dt = dt.replace(year=today.year + 1)
        return dt.date().isoformat()
    except ValueError:
        return None


def _fetch_deadline(session, url: str) -> str | None:
    try:
        r = session.get(url, timeout=30)
        if r.status_code != 200:
            return None
        m = _CLOSES_RE.search(r.text)
        if not m:
            return None
        return _parse_date(m.group(1), m.group(2), m.group(3))
    except Exception:
        return None


def _extract_card(div) -> dict | None:
    a = div.find("a", href=_JOB_HREF_RE)
    if not a:
        return None
    href = a["href"].split("?")[0]
    job_id = href.split("/")[2] if href.startswith("/job/") else href
    url = BASE + href
    title = a.get_text(strip=True)
    # Postdoc mode: drop noise like "PhD Academy Manager" or admin roles.
    if _TITLE_OK_RE is not None and not _TITLE_OK_RE.search(title):
        return None

    department = ""
    dep_el = div.find("div", class_=re.compile(r"j-search-result__department"))
    if dep_el:
        department = dep_el.get_text(" ", strip=True)

    institution = ""
    emp_el = div.find("div", class_=re.compile(r"j-search-result__employer"))
    if emp_el:
        institution = emp_el.get_text(" ", strip=True)

    city = ""
    text = div.get_text(" ", strip=True)
    m = re.search(r"Location:\s*([A-Za-zÀ-ÿ' \-,\.]{2,60})", text)
    if m:
        city = re.split(r"\s{2,}|Salary:|Date Placed:", m.group(1))[0].strip()

    posted = None
    m = _DATE_PLACED_RE.search(text)
    if m:
        posted = _parse_date(m.group(1), m.group(2), m.group(3))

    return {
        "id": f"jobsac-{job_id}",
        "source": SOURCE_ID,
        "source_url": url,
        "title": title,
        "institution": institution or "Unknown",
        "country": "GB",
        "city": city,
        "department": department,
        "posted": posted,
        "deadline": None,
        "profile": "Postdoc" if JOB_KIND == "postdoc" else "PhD",
        "research_fields": [],
        "description_html": "",
        "contacts": [],
    }


def _parse_page(html: str) -> list[dict]:
    soup = BeautifulSoup(html, "lxml")
    cards = soup.find_all("div", class_=re.compile(r"j-search-result__text"))
    out: list[dict] = []
    seen: set[str] = set()
    for c in cards:
        j = _extract_card(c)
        if not j or j["source_url"] in seen:
            continue
        seen.add(j["source_url"])
        out.append(j)
    return out


def fetch(session) -> list[dict]:
    out: list[dict] = []
    seen_urls: set[str] = set()
    for page in range(_MAX_PAGES):
        start = 1 + page * 25
        url = SEARCH_URL.format(start=start)
        try:
            r = session.get(url, timeout=30)
            r.raise_for_status()
        except Exception as e:
            print(f"  [jobsac_uk] page {page} FAILED: {e}", file=sys.stderr)
            continue
        page_jobs = _parse_page(r.text)
        new = [j for j in page_jobs if j["source_url"] not in seen_urls]
        for j in new:
            seen_urls.add(j["source_url"])
        out.extend(new)
        print(
            f"  [jobsac_uk] page {page} (start={start}): +{len(new)} (cum {len(out)})",
            file=sys.stderr,
        )
        if not new:
            break
        time.sleep(_REQ_SLEEP)

    if _FETCH_DETAILS:
        for i, j in enumerate(out):
            d = _fetch_deadline(session, j["source_url"])
            if d:
                j["deadline"] = d
            if (i + 1) % 25 == 0:
                print(
                    f"  [jobsac_uk] details {i+1}/{len(out)}",
                    file=sys.stderr,
                )
            time.sleep(_REQ_SLEEP)

    return out
