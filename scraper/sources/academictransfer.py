"""AcademicTransfer (Netherlands) PhD scraper.

Uses the public sitemap to enumerate vacancies, filters by PhD/doctoral slug,
then extracts JSON-LD JobPosting blocks from each detail page.
"""
from __future__ import annotations

import json
import os
import re
import sys
import time

SOURCE_ID = "academictransfer"
SITEMAP = "https://www.academictransfer.com/sitemap-vacancies.xml"
BASE = "https://www.academictransfer.com"

JOB_KIND = os.getenv("JOB_KIND", "phd").lower()
_URL_RE = re.compile(r"<loc>([^<]+/jobs/\d+/[^<]+?)</loc>")
# Slug filter switches with JOB_KIND. AcademicTransfer URLs embed the role
# type in the slug, e.g. /jobs/12345/postdoc-...-vu-amsterdam.
if JOB_KIND == "postdoc":
    _PHD_SLUG = re.compile(r"/(post[-]?doc|postdoctoral)", re.I)
else:
    _PHD_SLUG = re.compile(r"/(phd|doctoral|promovend)", re.I)
_LD_RE = re.compile(
    r'<script[^>]+type="application/ld\+json"[^>]*>(.*?)</script>',
    re.S,
)
_MAX_JOBS = 120


def _iso_date(s: str) -> str:
    return (s or "")[:10]


def _find_job_posting(node) -> dict | None:
    if isinstance(node, dict):
        if node.get("@type") == "JobPosting":
            return node
        for v in node.values():
            found = _find_job_posting(v)
            if found:
                return found
    elif isinstance(node, list):
        for v in node:
            found = _find_job_posting(v)
            if found:
                return found
    return None


def _extract_posting(html: str) -> dict | None:
    for m in _LD_RE.finditer(html):
        blob = m.group(1).strip()
        try:
            obj = json.loads(blob)
        except Exception:
            continue
        found = _find_job_posting(obj)
        if found:
            return found
    return None


def _to_job(url: str, posting: dict) -> dict:
    org = posting.get("hiringOrganization") or {}
    loc = posting.get("jobLocation") or {}
    if isinstance(loc, list):
        loc = loc[0] if loc else {}
    addr = (loc.get("address") or {}) if isinstance(loc, dict) else {}
    return {
        "source": SOURCE_ID,
        "source_url": url,
        "country": "NL",
        "institution": (org.get("name") or "").strip() or "Unknown (NL)",
        "title": (posting.get("title") or "").strip(),
        "description_html": posting.get("description") or "",
        "deadline": _iso_date(posting.get("validThrough", "")),
        "posted": _iso_date(posting.get("datePosted", "")),
        "city": (addr.get("addressLocality") or "") if isinstance(addr, dict) else "",
        "department": "",
        "profile": "R1",
        "research_fields": [],
        "contacts": [],
    }


def fetch(session) -> list[dict]:
    r = session.get(SITEMAP, timeout=30)
    r.raise_for_status()
    urls = _URL_RE.findall(r.text)
    phd_urls = [u for u in urls if _PHD_SLUG.search(u)]
    phd_urls = phd_urls[:_MAX_JOBS]
    print(f"  [at] sitemap: {len(urls)} total, {len(phd_urls)} PhD (capped)", file=sys.stderr)

    jobs: list[dict] = []
    for i, u in enumerate(phd_urls):
        try:
            dr = session.get(u, timeout=30)
            if dr.status_code != 200:
                continue
            posting = _extract_posting(dr.text)
            if not posting:
                continue
            jobs.append(_to_job(u, posting))
        except Exception as e:
            print(f"    [at] {u}: {e}", file=sys.stderr)
        if (i + 1) % 25 == 0:
            print(f"    [at] {i+1}/{len(phd_urls)}", file=sys.stderr)
        time.sleep(0.15)
    return jobs
