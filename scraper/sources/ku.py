"""University of Copenhagen PhD adapter. List: employment.ku.dk/phd/."""
from __future__ import annotations

import os
import re
import sys
import time
import warnings
from urllib.parse import urljoin

from bs4 import BeautifulSoup
from urllib3.exceptions import InsecureRequestWarning

warnings.simplefilter("ignore", InsecureRequestWarning)

SOURCE_ID = "ku"
BASE = "https://employment.ku.dk"
LIST_URL = f"{BASE}/phd/"
INSTITUTION = "University of Copenhagen"

_SCRIPT_RE = re.compile(r"<(script|style)\b[^>]*>.*?</\1>", re.I | re.S)
_ON_ATTR_RE = re.compile(r"\s+on[a-z]+\s*=\s*(\"[^\"]*\"|'[^']*')", re.I)

MONTH_EN = {
    "january": 1, "february": 2, "march": 3, "april": 4, "may": 5, "june": 6,
    "july": 7, "august": 8, "september": 9, "october": 10, "november": 11, "december": 12,
    "jan": 1, "feb": 2, "mar": 3, "apr": 4, "jun": 6, "jul": 7,
    "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12,
}


def _parse_en_date(s: str) -> str | None:
    if not s:
        return None
    m = re.search(r"(\d{1,2})[\.\s]+([A-Za-z]+)[\.\s]+(\d{4})", s)
    if m:
        mon = m.group(2).lower()
        if mon in MONTH_EN:
            try:
                return f"{m.group(3)}-{MONTH_EN[mon]:02d}-{int(m.group(1)):02d}"
            except ValueError:
                return None
    m = re.search(r"(\d{4})-(\d{2})-(\d{2})", s)
    return m.group(0) if m else None


def _clean(frag: str) -> str:
    frag = _SCRIPT_RE.sub("", frag)
    frag = _ON_ATTR_RE.sub("", frag)
    return frag.strip()


def _list_ids(html: str) -> list[str]:
    ids: list[str] = []
    seen: set[str] = set()
    for m in re.finditer(r'href="/phd/\?show=(\d+)"', html):
        jid = m.group(1)
        if jid not in seen:
            seen.add(jid)
            ids.append(jid)
    return ids


def _parse_detail(html: str) -> dict:
    soup = BeautifulSoup(html, "lxml")
    title_el = soup.find("h1")
    title = title_el.get_text(" ", strip=True) if title_el else ""

    body_el = soup.select_one("div.vacancy_details_area") or soup.select_one("div.main-content")
    description_html = _clean(body_el.decode_contents()) if body_el else ""

    text = body_el.get_text(" ", strip=True) if body_el else ""
    deadline = None
    m = re.search(r"deadline[:\s]*([0-9]{1,2}\s+[A-Za-z]+\s+\d{4})", text, re.I)
    if m:
        deadline = _parse_en_date(m.group(1))

    department = ""
    dep_m = re.search(r"Faculty of [A-Z][A-Za-z &]+", text)
    if dep_m:
        department = dep_m.group(0).strip()

    contacts: list[dict] = []
    for email_m in re.finditer(r"([A-Z][A-Za-zà-ÿ]+(?:\s+[A-Z][A-Za-zà-ÿ-]+){1,3})[^<@]{0,40}?([\w.+-]+@ku\.dk)", text):
        name, email = email_m.group(1).strip(), email_m.group(2)
        if not any(c.get("email") == email for c in contacts):
            contacts.append({"name": name, "email": email})
        if len(contacts) >= 3:
            break

    return {
        "title": title,
        "description_html": description_html,
        "deadline": deadline,
        "department": department,
        "contacts": contacts,
    }


def fetch(session, *, delay: float = 0.3, max_jobs: int | None = None) -> list[dict]:
    # KU adapter is hardcoded to /phd/ paths. Skip in postdoc mode (KU postdoc
    # listings live on a different surface that needs its own adapter).
    if os.getenv("JOB_KIND", "phd").lower() == "postdoc":
        print("  [ku] skipped (postdoc mode; PhD-only adapter)", file=sys.stderr)
        return []
    r = session.get(LIST_URL, timeout=30, verify=False)
    r.raise_for_status()
    ids = _list_ids(r.text)
    if max_jobs:
        ids = ids[:max_jobs]

    jobs: list[dict] = []
    for jid in ids:
        url = urljoin(BASE, f"/phd/?show={jid}")
        try:
            rd = session.get(url, timeout=30, verify=False)
            if rd.status_code != 200:
                continue
            detail = _parse_detail(rd.text)
        except Exception:
            continue
        time.sleep(delay)

        jobs.append({
            "id": f"{SOURCE_ID}-{jid}",
            "source": SOURCE_ID,
            "title": detail["title"],
            "institution": INSTITUTION,
            "country": "DK",
            "city": "Copenhagen",
            "department": detail.get("department", ""),
            "posted": None,
            "deadline": detail.get("deadline"),
            "profile": "R1",
            "research_fields": [],
            "description_html": detail["description_html"],
            "contacts": detail.get("contacts", []),
            "source_url": url,
        })
    return jobs
