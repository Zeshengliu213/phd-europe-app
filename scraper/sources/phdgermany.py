"""DAAD PhDGermany adapter — DAAD's curated PhD listings across Germany.

Aggregates positions from German universities, Max Planck Institutes,
Helmholtz centres, Leibniz institutes and other research organisations.
The listing is paginated 10 jobs per page via ?phd-p=N.
"""
from __future__ import annotations

import os
import re
import sys
import time
from datetime import datetime

from bs4 import BeautifulSoup

SOURCE_ID = "phdgermany"
BASE = "https://www.daad.de"
LIST_URL = (
    "https://www.daad.de/en/studying-in-germany/phd-studies-research/"
    "phd-germany/?phd-p={page}"
)

_DETAIL_HREF_RE = re.compile(r"/phd-germany/detail/[^\s\"']+-(\d{3,6})/")
_DATE_RE = re.compile(r"(\d{1,2})\.(\d{1,2})\.(\d{4})")

_MAX_PAGES = int(os.getenv("PHDGERMANY_MAX_PAGES", "8"))
_REQ_SLEEP = float(os.getenv("PHDGERMANY_SLEEP", "0.4"))


def _parse_date(text: str) -> str | None:
    m = _DATE_RE.search(text or "")
    if not m:
        return None
    try:
        d, mo, y = int(m.group(1)), int(m.group(2)), int(m.group(3))
        return datetime(y, mo, d).date().isoformat()
    except ValueError:
        return None


def _label_value(text: str, label: str) -> str:
    """Pull the value following 'Label:' from a pipe-joined card text."""
    pat = re.compile(rf"{re.escape(label)}\s*:?\s*\|\s*([^|]+)", re.I)
    m = pat.search(text)
    return m.group(1).strip() if m else ""


def _extract_card(article) -> dict | None:
    a = article.find("a", href=_DETAIL_HREF_RE)
    if not a:
        return None
    href = a["href"].split("?")[0]
    m = _DETAIL_HREF_RE.search(href)
    if not m:
        return None
    job_id = m.group(1)
    url = BASE + href if href.startswith("/") else href

    text = article.get_text(" | ", strip=True)
    parts = [p.strip() for p in text.split("|") if p.strip()]

    institution = parts[0] if parts else ""
    department = parts[1] if len(parts) > 1 else ""
    title = ""
    for p in parts[2:]:
        low = p.lower().rstrip(":")
        if low in {
            "type of promotion", "application deadline", "working language",
            "beginning", "required degree", "location", "more",
        }:
            break
        title = p
        break

    deadline = _parse_date(_label_value(text, "Application deadline"))
    city = _label_value(text, "Location")

    return {
        "id": f"phdgermany-{job_id}",
        "source": SOURCE_ID,
        "source_url": url,
        "title": title,
        "institution": institution or "Unknown",
        "country": "DE",
        "city": city,
        "department": department,
        "posted": None,
        "deadline": deadline,
        "profile": "PhD",
        "research_fields": [],
        "description_html": "",
        "contacts": [],
    }


def _parse_page(html: str) -> list[dict]:
    soup = BeautifulSoup(html, "lxml")
    out: list[dict] = []
    seen: set[str] = set()
    for art in soup.find_all("article", class_=re.compile(r"\bresult\b")):
        j = _extract_card(art)
        if not j or j["source_url"] in seen:
            continue
        seen.add(j["source_url"])
        out.append(j)
    return out


def fetch(session) -> list[dict]:
    out: list[dict] = []
    seen_urls: set[str] = set()
    for page in range(1, _MAX_PAGES + 1):
        try:
            r = session.get(LIST_URL.format(page=page), timeout=30)
            r.raise_for_status()
        except Exception as e:
            print(f"  [phdgermany] page {page} FAILED: {e}", file=sys.stderr)
            continue
        page_jobs = _parse_page(r.text)
        new = [j for j in page_jobs if j["source_url"] not in seen_urls]
        for j in new:
            seen_urls.add(j["source_url"])
        out.extend(new)
        print(
            f"  [phdgermany] page {page}: +{len(new)} (cum {len(out)})",
            file=sys.stderr,
        )
        if not new:
            break
        time.sleep(_REQ_SLEEP)
    return out
