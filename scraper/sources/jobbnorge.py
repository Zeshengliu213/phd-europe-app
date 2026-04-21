"""Jobbnorge adapter: Norwegian university jobs. Filters to PhD / stipendiat positions."""
from __future__ import annotations

import os
import re
import time

SOURCE_ID = "jobbnorge"
LIST_URL = "https://publicapi.jobbnorge.no/v1/jobs?lang=2"
DETAIL_URL = "https://id.jobbnorge.no/api/joblisting?jobId={jid}&languageId=2"

JOB_KIND = os.getenv("JOB_KIND", "phd").lower()
# Norwegian terms: PhD = stipendiat, Postdoc = postdoktor. English accepted too.
if JOB_KIND == "postdoc":
    PHD_RE = re.compile(r"\b(post[-]?doc(toral)?|postdoktor|forsker)\b", re.I)
else:
    PHD_RE = re.compile(r"\b(phd|ph\.?d|stipendiat|doctoral|doktorgrad)\b", re.I)

_DATE_RE = re.compile(r"\$date\('(\d{4})-(\d{2})-(\d{2})")
_DOTTED_RE = re.compile(r"(\d{1,2})\.(\d{1,2})\.(\d{4})")

_SCRIPT_RE = re.compile(r"<(script|style)\b[^>]*>.*?</\1>", re.I | re.S)
_ON_ATTR_RE = re.compile(r"\s+on[a-z]+\s*=\s*(\"[^\"]*\"|'[^']*')", re.I)


def _parse_api_date(s: str | None) -> str | None:
    if not s:
        return None
    m = _DATE_RE.search(s)
    return f"{m.group(1)}-{m.group(2)}-{m.group(3)}" if m else None


def _parse_dotted(s: str | None) -> str | None:
    if not s:
        return None
    m = _DOTTED_RE.search(s)
    return f"{m.group(3)}-{m.group(2).zfill(2)}-{m.group(1).zfill(2)}" if m else None


def _clean(html: str) -> str:
    html = _SCRIPT_RE.sub("", html)
    html = _ON_ATTR_RE.sub("", html)
    return html.strip()


def _institution_from_employer(name: str) -> str:
    if " - " in name:
        short, long = name.split(" - ", 1)
        if re.search(r"\b(University|Institute|College|School)\b", long, re.I):
            return long.strip()
        return short.strip()
    return name.strip()


def _city_from_detail(detail: dict, fallback: str) -> str:
    wp = detail.get("workPlace") or []
    if wp and isinstance(wp, list):
        muni = wp[0].get("municipality") or wp[0].get("area") or ""
        if muni:
            return muni
    return fallback


def _build_description(components: list) -> str:
    parts: list[str] = []
    for c in components or []:
        heading = (c.get("heading") or "").strip()
        text = (c.get("text") or "").strip()
        if heading:
            parts.append(f"<h3>{heading}</h3>")
        if text:
            parts.append(text)
    return _clean("\n".join(parts))


def _contacts(detail: dict) -> list[dict]:
    out: list[dict] = []
    for c in detail.get("contacts") or []:
        entry = {"name": (c.get("name") or "").strip()}
        if c.get("position"):
            entry["position"] = c["position"].strip()
        if c.get("email"):
            entry["email"] = c["email"].strip()
        if c.get("phone"):
            entry["phone"] = c["phone"].strip()
        if entry["name"] or entry.get("email"):
            out.append(entry)
    return out


def fetch(session, *, delay: float = 0.25, max_jobs: int | None = None) -> list[dict]:
    r = session.get(LIST_URL, timeout=30)
    r.raise_for_status()
    listings = r.json()

    phd_listings = [j for j in listings if PHD_RE.search(j.get("title") or "")]
    if max_jobs:
        phd_listings = phd_listings[:max_jobs]

    jobs: list[dict] = []
    for idx, lst in enumerate(phd_listings):
        jid = lst.get("id")
        if not jid:
            continue

        detail: dict = {}
        components: list = []
        try:
            rd = session.get(DETAIL_URL.format(jid=jid), timeout=30)
            if rd.status_code == 200:
                detail = rd.json()
                components = detail.get("components") or []
        except Exception:
            pass
        time.sleep(delay)

        deadline = _parse_dotted(lst.get("deadline")) or _parse_api_date(detail.get("deadlineOn"))
        posted = _parse_api_date(detail.get("publishedOn")) or _parse_api_date(detail.get("published"))

        jobs.append({
            "id": f"{SOURCE_ID}-{jid}",
            "source": SOURCE_ID,
            "title": (lst.get("title") or "").strip(),
            "institution": _institution_from_employer(
                detail.get("employerName") or lst.get("employer") or ""
            ),
            "country": "NO",
            "city": _city_from_detail(detail, lst.get("location") or ""),
            "department": (detail.get("workplaceString") or "").strip(),
            "posted": posted,
            "deadline": deadline,
            "profile": "R1",
            "research_fields": [],
            "description_html": _build_description(components) or (lst.get("summary") or "").strip(),
            "contacts": _contacts(detail),
            "source_url": lst.get("link") or f"https://www.jobbnorge.no/ledige-stillinger/stilling/{jid}",
        })
        if (idx + 1) % 25 == 0:
            print(f"  [jobbnorge] progress {idx+1}/{len(phd_listings)}")
    return jobs
