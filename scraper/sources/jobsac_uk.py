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
SEARCH_URL = (
    "https://www.jobs.ac.uk/search/?keywords=phd"
    "&pageSize=25&startIndex={start}"
)

_JOB_HREF_RE = re.compile(r"^/job/[A-Z0-9]+/")
_DATE_PLACED_RE = re.compile(
    r"Date\s+Placed:\s*(\d{1,2})\s+([A-Za-z]{3,9})(?:\s+(\d{4}))?",
    re.I,
)

_MAX_PAGES = int(os.getenv("JOBSAC_MAX_PAGES", "8"))
_REQ_SLEEP = float(os.getenv("JOBSAC_SLEEP", "0.4"))


def _parse_date(day: str, month: str, year: str | None) -> str | None:
    try:
        y = int(year) if year else datetime.utcnow().year
        dt = datetime.strptime(f"{int(day):02d} {month[:3]} {y}", "%d %b %Y")
        return dt.date().isoformat()
    except ValueError:
        return None


def _extract_card(div) -> dict | None:
    a = div.find("a", href=_JOB_HREF_RE)
    if not a:
        return None
    href = a["href"].split("?")[0]
    job_id = href.split("/")[2] if href.startswith("/job/") else href
    url = BASE + href
    title = a.get_text(strip=True)

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
        "profile": "PhD",
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
    return out
