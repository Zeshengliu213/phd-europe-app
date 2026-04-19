"""Varbi aggregator: scrape PhD positions from multiple Swedish universities on Varbi."""
from __future__ import annotations

import sys

from ._varbi import fetch_varbi

SOURCE_ID = "varbi"

INSTITUTIONS = [
    # (sub, institution_name, default_city)
    ("lu", "Lund University", "Lund"),
    ("kth", "KTH Royal Institute of Technology", "Stockholm"),
    ("uu", "Uppsala University", "Uppsala"),
    ("su", "Stockholm University", "Stockholm"),
    ("ki", "Karolinska Institutet", "Stockholm"),
    ("kau", "Karlstad University", "Karlstad"),
    ("miun", "Mid Sweden University", "Sundsvall"),
]


def fetch(session) -> list[dict]:
    all_jobs: list[dict] = []
    for sub, name, city in INSTITUTIONS:
        try:
            jobs = fetch_varbi(
                session,
                source_id=f"varbi-{sub}",
                sub=sub,
                institution=name,
                default_city=city,
            )
        except Exception as e:
            print(f"  [varbi:{sub}] FAILED: {e}", file=sys.stderr)
            continue
        print(f"  [varbi:{sub}] {len(jobs)} PhD jobs")
        all_jobs.extend(jobs)
    return all_jobs
