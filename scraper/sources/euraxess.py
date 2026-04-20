"""EURAXESS adapter — EU's official pan-European research jobs portal.

Covers all EU/EEA/associated countries. Filters to First Stage Researcher (R1)
which corresponds to PhD-level positions. Iterates the search results pages
and parses job cards directly (no detail-page fetch by default — that would
be ~5000 requests). Detail enrichment can be enabled via EURAXESS_FETCH_DETAILS=1.
"""
from __future__ import annotations

import os
import re
import sys
import time
from datetime import datetime

from bs4 import BeautifulSoup

SOURCE_ID = "euraxess"
BASE = "https://euraxess.ec.europa.eu"
# R1 = First Stage Researcher (up to PhD); also restrict to job offers
SEARCH_URL = (
    "https://euraxess.ec.europa.eu/jobs/search"
    "?f%5B0%5D=research_profile%3A%22First+Stage+Researcher+%28R1%29%22"
    "&f%5B1%5D=offer_type%3Ajob_offer"
    "&page={page}"
)
# Per-country search URL — uses Drupal facet `job_country` with the
# country's numeric term ID (NOT the ISO code).
PER_COUNTRY_URL = (
    "https://euraxess.ec.europa.eu/jobs/search"
    "?f%5B0%5D=research_profile%3A%22First+Stage+Researcher+%28R1%29%22"
    "&f%5B1%5D=offer_type%3Ajob_offer"
    "&f%5B2%5D=job_country%3A{tid}"
    "&page={page}"
)

# ISO-2 → EURAXESS country term ID (scraped from the country dropdown).
COUNTRY_TID = {
    "AT": 791, "BE": 792, "BA": 775, "BG": 746, "HR": 776, "CY": 777,
    "CZ": 747, "DK": 757, "EE": 758, "FI": 760, "FR": 793, "DE": 794,
    "GR": 779, "HU": 748, "IS": 762, "IE": 763, "IL": 730, "IT": 781,
    "LV": 766, "LT": 767, "LU": 796, "MT": 782, "NL": 798, "NO": 768,
    "PL": 749, "PT": 784, "RO": 751, "RS": 786, "SK": 753, "SI": 787,
    "ES": 788, "SE": 770, "CH": 799, "GB": 771, "UA": 754,
}

_MAX_PAGES = int(os.getenv("EURAXESS_MAX_PAGES", "30"))  # ~10/page → 300 jobs default
_FETCH_DETAILS = os.getenv("EURAXESS_FETCH_DETAILS", "0") == "1"
# EURAXESS's CDN throttles aggressively (~60 req/min). Default to 1.5s spacing
# plus an extra pause between countries; both can be tightened via env.
_REQ_SLEEP = float(os.getenv("EURAXESS_SLEEP", "1.5"))
_COUNTRY_SLEEP = float(os.getenv("EURAXESS_COUNTRY_SLEEP", "3.0"))
_RETRY_AFTER_DEFAULT = float(os.getenv("EURAXESS_RETRY_AFTER", "30"))

# Countries that get under-represented by the global recency-sorted feed —
# they get supplemental per-country fetches.
_PER_COUNTRY = [
    c.strip().upper()
    for c in os.getenv(
        "EURAXESS_PER_COUNTRY",
        "FI,DE,CH,AT,BE,IE,GB,ES,PT,GR,CZ,DK,NO,SE,NL"
    ).split(",")
    if c.strip()
]
_PER_COUNTRY_PAGES = int(os.getenv("EURAXESS_PER_COUNTRY_PAGES", "10"))

_JOB_LINK_RE = re.compile(r"^/jobs/(\d+|hosting/[^/]+)$")
_DATE_RE = re.compile(
    r"(\d{1,2})\s+"
    r"(January|February|March|April|May|June|July|August|"
    r"September|October|November|December)"
    r"\s+(\d{4})",
    re.I,
)

# Country name → ISO 3166-1 alpha-2. Covers EU/EEA + UK/CH + common associates.
COUNTRY_ISO = {
    "Austria": "AT", "Belgium": "BE", "Bulgaria": "BG", "Croatia": "HR",
    "Cyprus": "CY", "Czech Republic": "CZ", "Czechia": "CZ", "Denmark": "DK",
    "Estonia": "EE", "Finland": "FI", "France": "FR", "Germany": "DE",
    "Greece": "GR", "Hungary": "HU", "Iceland": "IS", "Ireland": "IE",
    "Italy": "IT", "Latvia": "LV", "Liechtenstein": "LI", "Lithuania": "LT",
    "Luxembourg": "LU", "Malta": "MT", "Netherlands": "NL", "Norway": "NO",
    "Poland": "PL", "Portugal": "PT", "Romania": "RO", "Slovakia": "SK",
    "Slovenia": "SI", "Spain": "ES", "Sweden": "SE", "Switzerland": "CH",
    "United Kingdom": "GB", "UK": "GB", "Turkey": "TR", "Türkiye": "TR",
    "Serbia": "RS", "Albania": "AL", "Bosnia and Herzegovina": "BA",
    "Montenegro": "ME", "North Macedonia": "MK", "Moldova": "MD",
    "Ukraine": "UA", "Israel": "IL", "Faroe Islands": "FO",
}


def _parse_date(text: str) -> str | None:
    """Parse '20 April 2026' or '5 May 2026, 23:59 (Europe/Lisbon)' → ISO date."""
    if not text:
        return None
    m = _DATE_RE.search(text)
    if not m:
        return None
    try:
        dt = datetime.strptime(
            f"{m.group(1)} {m.group(2)} {m.group(3)}", "%d %B %Y"
        )
        return dt.date().isoformat()
    except ValueError:
        return None


def _country_iso(name: str) -> str:
    name = (name or "").strip()
    return COUNTRY_ISO.get(name, name[:2].upper() if name else "")


def _extract_card(card, default_iso: str = "") -> dict | None:
    """Pull fields from one job card. Returns None if no usable job link found.
    `default_iso` is used when country isn't recognisable in the card text
    (e.g., for per-country filtered fetches we already know the country).
    """
    job_link = None
    title = ""
    for a in card.find_all("a", href=True):
        href = a["href"].split("?")[0].split("#")[0]
        if _JOB_LINK_RE.match(href):
            job_link = BASE + href
            title = a.get_text(strip=True) or title
            break
    if not job_link:
        return None

    text = card.get_text(" ", strip=True)

    # Posted date — usually "Posted on: DD Month YYYY"
    posted = None
    m = re.search(r"Posted\s*(?:on)?\s*:?\s*(\d{1,2}\s+\w+\s+\d{4})", text, re.I)
    if m:
        posted = _parse_date(m.group(1))

    # Deadline — "Application Deadline: DD Month YYYY"
    deadline = None
    m = re.search(
        r"(?:Application\s+)?Deadline\s*:?\s*(\d{1,2}\s+\w+\s+\d{4})",
        text, re.I,
    )
    if m:
        deadline = _parse_date(m.group(1))

    # Organisation — anchor pointing to /partnering/organisations/ or /jobs/organisation/
    org = ""
    for a in card.find_all("a", href=True):
        href = a["href"]
        if "/organisation" in href or "/partnering/" in href:
            org = a.get_text(strip=True)
            break

    # Country — match a known country name as a whole word in the card text
    country_name = ""
    for name in COUNTRY_ISO:
        if re.search(rf"\b{re.escape(name)}\b", text):
            country_name = name
            break

    job_id = job_link.rsplit("/", 1)[-1]
    iso = _country_iso(country_name) or default_iso
    return {
        "id": f"euraxess-{job_id}",
        "source": SOURCE_ID,
        "source_url": job_link,
        "title": title,
        "institution": org or "Unknown",
        "country": iso,
        "city": "",
        "department": "",
        "posted": posted,
        "deadline": deadline,
        "profile": "R1",
        "research_fields": [],
        "description_html": "",
        "contacts": [],
    }


def _parse_page(html: str, default_iso: str = "") -> list[dict]:
    soup = BeautifulSoup(html, "lxml")
    jobs: list[dict] = []
    seen: set[str] = set()

    # A "card" is the smallest container that holds a /jobs/<id> link.
    candidates = soup.find_all(
        lambda t: t.name in ("article", "li", "div")
        and t.find("a", href=_JOB_LINK_RE)
    )

    # Pick the deepest candidate per job link to avoid double-counting.
    chosen: dict[str, object] = {}
    for c in candidates:
        link_a = c.find("a", href=_JOB_LINK_RE)
        if not link_a:
            continue
        href = link_a["href"].split("?")[0].split("#")[0]
        prev = chosen.get(href)
        if prev is None or len(c.find_all(True)) < len(prev.find_all(True)):
            chosen[href] = c

    for card in chosen.values():
        job = _extract_card(card, default_iso=default_iso)
        if not job:
            continue
        if job["source_url"] in seen:
            continue
        seen.add(job["source_url"])
        jobs.append(job)
    return jobs


def _fetch_pages(session, url_template: str, max_pages: int,
                 default_iso: str, seen_urls: set[str], label: str) -> list[dict]:
    out: list[dict] = []
    tid = COUNTRY_TID.get(default_iso, "")
    consecutive_429 = 0
    for page in range(max_pages):
        url = url_template.format(page=page, iso=default_iso, tid=tid)
        try:
            r = session.get(url, timeout=30)
            if r.status_code == 429:
                wait = float(r.headers.get("Retry-After") or _RETRY_AFTER_DEFAULT)
                consecutive_429 += 1
                print(
                    f"  [euraxess:{label}] page {page} 429 — sleeping {wait:.0f}s",
                    file=sys.stderr,
                )
                time.sleep(wait)
                if consecutive_429 >= 3:
                    print(
                        f"  [euraxess:{label}] giving up after 3 consecutive 429s",
                        file=sys.stderr,
                    )
                    break
                continue
            r.raise_for_status()
            consecutive_429 = 0
        except Exception as e:
            print(f"  [euraxess:{label}] page {page} FAILED: {e}", file=sys.stderr)
            continue
        page_jobs = _parse_page(r.text, default_iso=default_iso)
        new = [j for j in page_jobs if j["source_url"] not in seen_urls]
        for j in new:
            seen_urls.add(j["source_url"])
        out.extend(new)
        print(
            f"  [euraxess:{label}] page {page}: +{len(new)} (cum {len(out)})",
            file=sys.stderr,
        )
        if not page_jobs:
            break
        time.sleep(_REQ_SLEEP)
    return out


def fetch(session) -> list[dict]:
    all_jobs: list[dict] = []
    seen_urls: set[str] = set()

    # 1) Global recency-sorted feed
    all_jobs.extend(
        _fetch_pages(session, SEARCH_URL, _MAX_PAGES, "", seen_urls, "global")
    )

    # 2) Per-country supplemental fetches for under-represented countries
    for iso in _PER_COUNTRY:
        if iso not in COUNTRY_TID:
            print(f"  [euraxess:{iso}] skip — no term ID mapping", file=sys.stderr)
            continue
        added = _fetch_pages(
            session, PER_COUNTRY_URL, _PER_COUNTRY_PAGES,
            iso, seen_urls, iso,
        )
        all_jobs.extend(added)
        time.sleep(_COUNTRY_SLEEP)

    if _FETCH_DETAILS:
        _enrich_details(session, all_jobs)
    return all_jobs


def _enrich_details(session, jobs: list[dict]) -> None:
    """Optional: fetch each detail page for city/description (off by default)."""
    for i, j in enumerate(jobs):
        try:
            r = session.get(j["source_url"], timeout=30)
            if r.status_code != 200:
                continue
            soup = BeautifulSoup(r.text, "lxml")
            text = soup.get_text(" ", strip=True)
            m = re.search(
                r"(?:City|Town|Location)\s*:?\s*([A-Za-zÀ-ÿ' \-]{2,40})",
                text,
            )
            if m:
                j["city"] = m.group(1).strip()
        except Exception:
            pass
        if (i + 1) % 25 == 0:
            print(f"  [euraxess] details {i+1}/{len(jobs)}", file=sys.stderr)
        time.sleep(_REQ_SLEEP)
