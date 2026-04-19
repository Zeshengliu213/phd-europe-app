"""Linköping University adapter. Parses the RSS feed of open vacancies and keeps only PhD positions."""
from __future__ import annotations

import re
from email.utils import parsedate_to_datetime
from xml.etree import ElementTree as ET

SOURCE_ID = "liu"
FEED_URL = "https://liu.se/rss/liu-jobs-en.rss"
INSTITUTION = "Linköping University"
COUNTRY = "SE"
CITY = "Linköping"

DEPT_TO_FIELDS = {
    "IDA": ["Computer Science"],
    "ISY": ["Electrical Engineering", "Computer Science"],
    "IFM": ["Physics", "Chemistry", "Materials Science"],
    "IMT": ["Biomedical Engineering"],
    "IEI": ["Mechanical Engineering", "Management"],
    "ITN": ["Engineering", "Media Technology"],
    "MAI": ["Mathematics"],
    "IKOS": ["Humanities"],
    "IBL": ["Behavioural Sciences"],
    "IKE": ["Medicine"],
    "BKV": ["Biomedical Sciences"],
    "HMV": ["Health Sciences"],
    "TEMA": ["Thematic Studies"],
    "IAS": ["Analytical Sociology"],
}

_SCRIPT_RE = re.compile(r"<(script|style)\b[^>]*>.*?</\1>", re.I | re.S)
_ON_ATTR_RE = re.compile(r"\s+on[a-z]+\s*=\s*\"[^\"]*\"", re.I)
_ON_ATTR_SQ_RE = re.compile(r"\s+on[a-z]+\s*=\s*'[^']*'", re.I)


def _parse_date(s: str | None) -> str | None:
    if not s:
        return None
    try:
        return parsedate_to_datetime(s).date().isoformat()
    except (TypeError, ValueError):
        return None


def _clean_html(html: str) -> str:
    html = _SCRIPT_RE.sub("", html)
    html = _ON_ATTR_RE.sub("", html)
    html = _ON_ATTR_SQ_RE.sub("", html)
    return html.strip()


def _dept_code(org1: str) -> str:
    m = re.match(r"\s*([A-Z]{2,6})\b", org1 or "")
    return m.group(1) if m else ""


def _research_fields(org1: str) -> list[str]:
    code = _dept_code(org1)
    return DEPT_TO_FIELDS.get(code, [])


def _text(el: ET.Element | None) -> str:
    return (el.text or "").strip() if el is not None else ""


def _contacts(item: ET.Element) -> list[dict]:
    out: list[dict] = []
    children = list(item)
    for i, ch in enumerate(children):
        if ch.tag != "contactPerson":
            continue
        name, email, phone, position = "", "", "", ""
        raw = (ch.text or "").strip()
        parts = [p.strip() for p in raw.split(",")]
        if parts:
            name = parts[0]
        for j in range(i + 1, min(i + 6, len(children))):
            t = children[j].tag
            v = (children[j].text or "").strip()
            if t == "contactPerson":
                break
            if t == "contactPersonFullName" and v:
                name = v
            elif t == "contactPersonEmail":
                email = v
            elif t == "contactPersonTelephone":
                phone = v
            elif t == "contactPersonPosition":
                position = v
        entry = {"name": name}
        if position:
            entry["position"] = position
        if email:
            entry["email"] = email
        if phone:
            entry["phone"] = phone
        out.append(entry)
    return out


def _is_phd(item: ET.Element) -> bool:
    pos = _text(item.find("Position")).lower()
    occ = _text(item.find("occupationArea")).lower()
    return "phd" in pos or "phd" in occ or "doctoral" in pos or "doctoral" in occ


def fetch(session) -> list[dict]:
    r = session.get(FEED_URL, timeout=30)
    r.raise_for_status()
    root = ET.fromstring(r.content)
    jobs: list[dict] = []
    for item in root.findall(".//item"):
        if not _is_phd(item):
            continue
        seq = _text(item.find("CommAdSeqNo"))
        if not seq:
            continue
        title = _text(item.find("title"))
        org1 = _text(item.find("Org1"))
        posted = _parse_date(_text(item.find("pubDate")))
        deadline = _parse_date(_text(item.find("pubDateTo")))
        desc = _text(item.find("description"))
        link = _text(item.find("link"))
        jobs.append({
            "id": f"liu-{seq}",
            "source": SOURCE_ID,
            "title": title,
            "institution": INSTITUTION,
            "country": COUNTRY,
            "city": CITY,
            "department": org1,
            "posted": posted,
            "deadline": deadline,
            "profile": "R1",
            "research_fields": _research_fields(org1),
            "description_html": _clean_html(desc),
            "contacts": _contacts(item),
            "source_url": link,
        })
    return jobs
