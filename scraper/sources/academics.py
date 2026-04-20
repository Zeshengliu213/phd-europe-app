"""academics.com adapter — major German PhD job board (English mirror).

The site is built with Phoenix LiveView and uses JS-driven pagination, so
only the first results page is fetched (~25 jobs). Most listings are based
in Germany; a few are in Austria / Switzerland — country is inferred from
the city name when possible, otherwise defaults to DE.
"""
from __future__ import annotations

import re
import sys
from datetime import datetime

from bs4 import BeautifulSoup

SOURCE_ID = "academics"
BASE = "https://www.academics.com"
SEARCH_URL = "https://www.academics.com/jobsearch/position-phd-student/UQ=="

_JOB_HREF_RE = re.compile(r"^/jobs/[a-z0-9\-]+-(\d{6,})$")
_DATE_RE = re.compile(r"(\d{4})-(\d{2})-(\d{2})")

# Coarse city → ISO mapping. Anything not matched defaults to DE (the site is
# overwhelmingly DACH-region; misclassification is bounded).
_AT_CITIES = {"vienna", "wien", "graz", "innsbruck", "salzburg", "linz", "klagenfurt"}
_CH_CITIES = {
    "zurich", "zürich", "geneva", "genève", "basel", "bern", "lausanne",
    "lugano", "fribourg", "neuchâtel", "neuchatel", "st. gallen",
}
_NL_CITIES = {
    "amsterdam", "rotterdam", "utrecht", "delft", "eindhoven", "leiden",
    "groningen", "nijmegen", "wageningen", "maastricht", "tilburg", "enschede",
}
_LU_CITIES = {"luxembourg", "luxemburg", "esch-sur-alzette"}


def _infer_country(city: str) -> str:
    c = (city or "").strip().lower()
    if c in _AT_CITIES:
        return "AT"
    if c in _CH_CITIES:
        return "CH"
    if c in _NL_CITIES:
        return "NL"
    if c in _LU_CITIES:
        return "LU"
    return "DE"


def _parse_iso_date(text: str) -> str | None:
    m = _DATE_RE.search(text or "")
    if not m:
        return None
    try:
        return datetime(int(m.group(1)), int(m.group(2)), int(m.group(3))).date().isoformat()
    except ValueError:
        return None


def _extract_card(li) -> dict | None:
    a = li.find("a", href=_JOB_HREF_RE)
    if not a:
        return None
    href = a["href"].split("?")[0]
    job_id = _JOB_HREF_RE.match(href).group(1)
    url = BASE + href

    h2 = li.find("h2")
    title = h2.get_text(strip=True) if h2 else ""

    org_el = li.find(class_=re.compile(r"text-text-55"))
    institution = org_el.get_text(" ", strip=True) if org_el else ""

    city = ""
    deadline = None
    text = li.get_text(" ", strip=True)
    # The bottom flex row reads "<City> YYYY-MM-DD"
    m = re.search(r"([A-Za-zÀ-ÿ' \-\.]{2,40})\s+(\d{4}-\d{2}-\d{2})\s*$", text)
    if m:
        city = m.group(1).strip().rstrip("-").strip()
        deadline = _parse_iso_date(m.group(2))
    else:
        # Fallback: strip title+institution; last token is usually the city
        leftover = text.replace(title, "").replace(institution, "").strip()
        parts = [p for p in leftover.split() if p]
        if parts:
            city = parts[-1]

    iso = _infer_country(city)

    return {
        "id": f"academics-{job_id}",
        "source": SOURCE_ID,
        "source_url": url,
        "title": title,
        "institution": institution or "Unknown",
        "country": iso,
        "city": city,
        "department": "",
        "posted": None,
        "deadline": deadline,
        "profile": "PhD",
        "research_fields": [],
        "description_html": "",
        "contacts": [],
    }


def fetch(session) -> list[dict]:
    out: list[dict] = []
    seen: set[str] = set()
    try:
        r = session.get(SEARCH_URL, timeout=30)
        r.raise_for_status()
    except Exception as e:
        print(f"  [academics] FAILED: {e}", file=sys.stderr)
        return out

    soup = BeautifulSoup(r.text, "lxml")
    cards = soup.find_all("li", id=re.compile(r"^job-teaser-\d+-container$"))
    for li in cards:
        job = _extract_card(li)
        if not job or job["source_url"] in seen:
            continue
        seen.add(job["source_url"])
        out.append(job)

    print(f"  [academics] {len(out)} jobs", file=sys.stderr)
    return out
