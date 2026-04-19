"""Aalto University PhD adapter via Workday CXS API."""
from __future__ import annotations

import re
import time

SOURCE_ID = "aalto"
INSTITUTION = "Aalto University"
BASE = "https://aalto.wd3.myworkdayjobs.com"
LIST_URL = f"{BASE}/wday/cxs/aalto/aalto/jobs"
DETAIL_URL = f"{BASE}/wday/cxs/aalto/aalto"

PHD_RE = re.compile(r"\b(doctoral researcher|doctoral candidate|phd)\b", re.I)

_SCRIPT_RE = re.compile(r"<(script|style)\b[^>]*>.*?</\1>", re.I | re.S)
_ON_ATTR_RE = re.compile(r"\s+on[a-z]+\s*=\s*(\"[^\"]*\"|'[^']*')", re.I)


def _clean(html: str) -> str:
    html = _SCRIPT_RE.sub("", html)
    html = _ON_ATTR_RE.sub("", html)
    return html.strip()


def _search(session, *, offset: int, limit: int = 20) -> dict:
    r = session.post(
        LIST_URL,
        json={"limit": limit, "offset": offset, "searchText": "doctoral"},
        headers={"Content-Type": "application/json", "Accept": "application/json"},
        timeout=30,
    )
    r.raise_for_status()
    return r.json()


def fetch(session, *, delay: float = 0.25, max_jobs: int | None = None) -> list[dict]:
    postings: list[dict] = []
    offset, limit = 0, 20
    while True:
        payload = _search(session, offset=offset, limit=limit)
        batch = payload.get("jobPostings") or []
        postings.extend(batch)
        total = payload.get("total") or 0
        offset += len(batch)
        if not batch or offset >= total:
            break

    postings = [p for p in postings if PHD_RE.search(p.get("title") or "")]
    if max_jobs:
        postings = postings[:max_jobs]

    jobs: list[dict] = []
    for p in postings:
        ext_path = p.get("externalPath") or ""
        if not ext_path:
            continue
        try:
            rd = session.get(
                f"{DETAIL_URL}{ext_path}",
                headers={"Accept": "application/json"},
                timeout=30,
            )
            if rd.status_code != 200:
                continue
            info = rd.json().get("jobPostingInfo") or {}
        except Exception:
            continue
        time.sleep(delay)

        jid = info.get("jobReqId") or (ext_path.rsplit("_", 1)[-1] if "_" in ext_path else ext_path.rsplit("/", 1)[-1])
        loc = info.get("location") or p.get("locationsText") or ""
        city = loc.split(",")[0].strip() if loc else "Espoo"

        jobs.append({
            "id": f"{SOURCE_ID}-{jid}",
            "source": SOURCE_ID,
            "title": (info.get("title") or p.get("title") or "").strip(),
            "institution": INSTITUTION,
            "country": "FI",
            "city": city,
            "department": "",
            "posted": info.get("startDate"),
            "deadline": info.get("endDate"),
            "profile": "R1",
            "research_fields": [],
            "description_html": _clean(info.get("jobDescription") or ""),
            "contacts": [],
            "source_url": info.get("externalUrl") or f"{BASE}/aalto/job{ext_path}",
        })
    return jobs
