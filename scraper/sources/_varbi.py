"""Shared Varbi.com scraper. Swedish universities expose job boards at <inst>.varbi.com/en/."""
from __future__ import annotations

import os
import re
import time
from datetime import datetime

from bs4 import BeautifulSoup

LIST_URL = "https://{sub}.varbi.com/en/"
DETAIL_URL = "https://{sub}.varbi.com/en/what:job/jobID:{jid}/"

JOB_KIND = os.getenv("JOB_KIND", "phd").lower()
# Swedish: doktorand = PhD, postdoktor = postdoc.
if JOB_KIND == "postdoc":
    PHD_TITLE_RE = re.compile(
        r"\b(post[-\s]?doc(toral)?|postdoktor|research\s+(fellow|associate|scientist))\b",
        re.I,
    )
else:
    PHD_TITLE_RE = re.compile(
        r"\b(doctoral student|phd student|phd candidate|doctoral researcher|doctoral candidate|doktorand)\b",
        re.I,
    )

_SCRIPT_RE = re.compile(r"<(script|style)\b[^>]*>.*?</\1>", re.I | re.S)
_ON_ATTR_RE = re.compile(r"\s+on[a-z]+\s*=\s*(\"[^\"]*\"|'[^']*')", re.I)

MONTH_ABBR = {
    "jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6,
    "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12,
}


def _parse_dotted_date(s: str) -> str | None:
    s = (s or "").strip()
    if not s:
        return None
    m = re.match(r"(\d{4})-(\d{2})-(\d{2})", s)
    if m:
        return m.group(0)
    m = re.match(r"(\d{1,2})\.([A-Za-z]{3})\.?(\d{4})", s)
    if m:
        d, mon, y = m.group(1), m.group(2).lower()[:3], m.group(3)
        if mon in MONTH_ABBR:
            try:
                return datetime(int(y), MONTH_ABBR[mon], int(d)).date().isoformat()
            except ValueError:
                return None
    return None


def _clean_html(frag: str) -> str:
    frag = _SCRIPT_RE.sub("", frag)
    frag = _ON_ATTR_RE.sub("", frag)
    return frag.strip()


def _list_jobs(html: str) -> list[dict]:
    soup = BeautifulSoup(html, "lxml")
    out = []
    for row in soup.select("tr"):
        title_td = row.select_one("td.pos-title a")
        if not title_td:
            continue
        title = title_td.get_text(strip=True)
        href = title_td.get("href", "")
        m = re.search(r"jobID:(\d+)", href)
        if not m:
            continue
        if not PHD_TITLE_RE.search(title):
            continue
        town = row.select_one("td.pos-town")
        ends = row.select_one("td.pos-ends")
        sub_company = row.select_one("td.pos-subcompany")
        out.append({
            "jid": m.group(1),
            "title": title,
            "url": href,
            "city": town.get_text(strip=True) if town else "",
            "deadline": _parse_dotted_date(ends.get_text(strip=True)) if ends else None,
            "sub_company": sub_company.get_text(strip=True) if sub_company else "",
        })
    return out


def _extract_meta_field(html: str, label: str) -> str:
    m = re.search(
        rf">{re.escape(label)}\s*<[^>]*>\s*<[^>]*>\s*([^<]+)",
        html,
    )
    if m:
        return m.group(1).strip()
    m2 = re.search(rf"{re.escape(label)}\s*</[^>]+>\s*<[^>]+>\s*([^<]+)", html)
    return m2.group(1).strip() if m2 else ""


def _parse_detail(html: str) -> dict:
    soup = BeautifulSoup(html, "lxml")
    desc_el = soup.select_one("div.job-desc")
    description_html = _clean_html(desc_el.decode_contents()) if desc_el else ""

    posted = _parse_dotted_date(_extract_meta_field(html, "Published"))
    deadline = _parse_dotted_date(_extract_meta_field(html, "Last application date"))

    contacts: list[dict] = []
    for h in soup.find_all(["h2", "h3"]):
        if "contact" in h.get_text(strip=True).lower():
            for sib in h.find_all_next():
                if sib.name in ("h2", "h3"):
                    break
                if sib.name in ("p", "li"):
                    txt = sib.get_text(" ", strip=True)
                    if not txt:
                        continue
                    email_m = re.search(r"[\w.+-]+@[\w.-]+\.\w+", txt)
                    name = re.split(r"[,;]", txt)[0].strip()
                    entry = {"name": name[:120]}
                    if email_m:
                        entry["email"] = email_m.group(0)
                    contacts.append(entry)
                    if len(contacts) >= 5:
                        break
            break

    return {
        "description_html": description_html,
        "posted": posted,
        "deadline": deadline,
        "contacts": contacts,
    }


def fetch_varbi(session, *, source_id: str, sub: str, institution: str,
                default_city: str = "", delay: float = 0.4,
                max_jobs: int | None = None) -> list[dict]:
    r = session.get(LIST_URL.format(sub=sub), timeout=30)
    r.raise_for_status()
    listings = _list_jobs(r.text)
    if max_jobs:
        listings = listings[:max_jobs]

    jobs: list[dict] = []
    for lst in listings:
        try:
            rd = session.get(DETAIL_URL.format(sub=sub, jid=lst["jid"]), timeout=30)
            detail = _parse_detail(rd.text) if rd.status_code == 200 else {}
        except Exception:
            detail = {}
        time.sleep(delay)

        jobs.append({
            "id": f"{source_id}-{lst['jid']}",
            "source": source_id,
            "title": lst["title"],
            "institution": institution,
            "country": "SE",
            "city": lst["city"] or default_city,
            "department": lst.get("sub_company", ""),
            "posted": detail.get("posted"),
            "deadline": detail.get("deadline") or lst.get("deadline"),
            "profile": "R2" if JOB_KIND == "postdoc" else "R1",
            "research_fields": [],
            "description_html": detail.get("description_html", ""),
            "contacts": detail.get("contacts", []),
            "source_url": lst["url"],
        })
    return jobs
