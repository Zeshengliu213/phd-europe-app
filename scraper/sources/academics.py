"""academics.com adapter — major German PhD job board (English mirror).

The site is built with Phoenix LiveView and uses JS-driven pagination, so
only the first results page is fetched (~25 jobs). Most listings are based
in Germany; a few are in Austria / Switzerland — country is inferred from
the city name when possible, otherwise defaults to DE.
"""
from __future__ import annotations

import os
import re
import sys
from datetime import datetime

from bs4 import BeautifulSoup

SOURCE_ID = "academics"
BASE = "https://www.academics.com"
# JOB_KIND switches the listing slug. Default = PhD students; postdoc mode
# uses the postdoc landing page.
JOB_KIND = os.getenv("JOB_KIND", "phd").lower()
if JOB_KIND == "postdoc":
    SEARCH_URL = "https://www.academics.com/jobsearch/position-postdoc/Uw=="
else:
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

    # Title: the anchor's title attribute is the cleanest source.
    title = (a.get("title") or "").strip()
    if not title:
        h2 = li.find("h2")
        title = h2.get_text(strip=True) if h2 else ""

    # Institution: the logo image alt is "<Institution> - Logo".
    institution = ""
    img = li.find("img", alt=re.compile(r"-\s*Logo\s*$", re.I))
    if img:
        institution = re.sub(r"\s*-\s*Logo\s*$", "", img["alt"], flags=re.I).strip()

    # City: scan leaf divs that aren't the title or institution.
    city = ""
    for d in li.find_all("div"):
        if d.find("div"):
            continue
        t = d.get_text(" ", strip=True)
        if not t or t in {title, institution, "Top Job"}:
            continue
        if _DATE_RE.fullmatch(t):
            continue
        if 2 <= len(t) <= 40 and not t.startswith("20"):
            city = t
            break

    # Deadline intentionally left None: the date shown in cards is unreliable
    # (varies between "valid until", "posted on", and stale defaults).
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
        "deadline": None,
        "profile": "Postdoc" if JOB_KIND == "postdoc" else "PhD",
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
