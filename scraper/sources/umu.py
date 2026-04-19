"""Umeå University PhD adapter. List: www.umu.se/en/work-with-us/open-positions/."""
from __future__ import annotations

import re
import time
from urllib.parse import urljoin

from bs4 import BeautifulSoup

SOURCE_ID = "umu"
BASE = "https://www.umu.se"
LIST_URL = f"{BASE}/en/work-with-us/open-positions/"
INSTITUTION = "Umeå University"

PHD_RE = re.compile(r"\b(phd|doctoral student|doctoral candidate|doctoral researcher|doktorand)\b", re.I)

_DATE_RE = re.compile(r"\b(\d{4})-(\d{2})-(\d{2})\b")
_SCRIPT_RE = re.compile(r"<(script|style)\b[^>]*>.*?</\1>", re.I | re.S)
_ON_ATTR_RE = re.compile(r"\s+on[a-z]+\s*=\s*(\"[^\"]*\"|'[^']*')", re.I)


def _clean(frag: str) -> str:
    frag = _SCRIPT_RE.sub("", frag)
    frag = _ON_ATTR_RE.sub("", frag)
    return frag.strip()


def _list_entries(html: str) -> list[tuple[str, str, str]]:
    seen: set[str] = set()
    out: list[tuple[str, str, str]] = []
    soup = BeautifulSoup(html, "lxml")
    for a in soup.select("a.jobbTitle"):
        href = a.get("href") or ""
        m = re.match(r"/en/work-with-us/open-positions/([a-z0-9\-]+)_(\d+)/", href)
        if not m:
            continue
        title = a.get_text(" ", strip=True)
        if not PHD_RE.search(title):
            continue
        jid = m.group(2)
        if jid in seen:
            continue
        seen.add(jid)
        out.append((jid, title, urljoin(BASE, href)))
    return out


def _parse_detail(html: str) -> dict:
    soup = BeautifulSoup(html, "lxml")
    main = soup.find("main") or soup
    h1 = main.find("h1")
    title = h1.get_text(" ", strip=True) if h1 else ""

    department = ""
    if h1:
        nxt = h1.find_next(["h2", "h3"])
        if nxt:
            department = nxt.get_text(" ", strip=True)

    deadline = None
    for p in main.find_all("p"):
        t = p.get_text(" ", strip=True)
        if len(t) < 25:
            m = _DATE_RE.search(t)
            if m:
                deadline = f"{m.group(1)}-{m.group(2)}-{m.group(3)}"
                break
    if not deadline:
        m = _DATE_RE.search(main.get_text(" ", strip=True))
        if m:
            deadline = f"{m.group(1)}-{m.group(2)}-{m.group(3)}"

    desc_parts: list[str] = []
    for el in main.find_all(["h2", "h3", "p", "ul", "ol"]):
        txt = el.get_text(" ", strip=True)
        if not txt or txt == title or txt == department:
            continue
        if el.name in ("h2", "h3") and txt.lower() in ("information box",):
            break
        desc_parts.append(str(el))
    description_html = _clean("\n".join(desc_parts))

    contacts: list[dict] = []
    text = main.get_text(" ", strip=True)
    for m in re.finditer(r"([A-Z][A-Za-zà-ÿ]+(?:\s+[A-Z][A-Za-zà-ÿ\-]+){1,3})\s*\(?\s*([\w.+\-]+@umu\.se)", text):
        name, email = m.group(1).strip(), m.group(2)
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
    r = session.get(LIST_URL, timeout=30)
    r.raise_for_status()
    r.encoding = "utf-8"
    entries = _list_entries(r.text)
    if max_jobs:
        entries = entries[:max_jobs]

    jobs: list[dict] = []
    for jid, title, url in entries:
        try:
            rd = session.get(url, timeout=30)
            if rd.status_code != 200:
                continue
            rd.encoding = "utf-8"
            detail = _parse_detail(rd.text)
        except Exception:
            continue
        time.sleep(delay)

        jobs.append({
            "id": f"{SOURCE_ID}-{jid}",
            "source": SOURCE_ID,
            "title": detail["title"] or title,
            "institution": INSTITUTION,
            "country": "SE",
            "city": "Umeå",
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
