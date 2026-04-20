"""Coverage / health monitor for the scraper.

Reads ../data/jobs.json (produced by fetch.py) and writes ../data/stats.json
with current counts, a rolling history (last 60 runs), and alerts for sources
that went silent or dropped sharply versus the previous run.

Usage: python scraper/stats.py
Exit code: 0 always (alerts are advisory; CI can grep stats.json for "alerts").
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
JOBS = ROOT / "data" / "jobs.json"
OUT = ROOT / "data" / "stats.json"

HISTORY_MAX = 60
DROP_FRACTION_ALERT = 0.5  # alert if a source falls to <=50% of previous count
DROP_MIN_PREV = 4          # only check ratio if previous count was at least this


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _load_json(path: Path, default):
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as e:
        print(f"[stats] WARN: cannot read {path}: {e}", file=sys.stderr)
        return default


def _count_by(jobs: list[dict], key: str) -> dict[str, int]:
    out: dict[str, int] = {}
    for j in jobs:
        k = (j.get(key) or "?") or "?"
        out[k] = out.get(k, 0) + 1
    return dict(sorted(out.items(), key=lambda kv: (-kv[1], kv[0])))


def _diff_alerts(curr: dict[str, int], prev: dict[str, int]) -> list[str]:
    alerts: list[str] = []
    for src, prev_n in prev.items():
        curr_n = curr.get(src, 0)
        if prev_n > 0 and curr_n == 0:
            alerts.append(
                f"source '{src}' returned 0 jobs (was {prev_n} last run)"
            )
        elif prev_n >= DROP_MIN_PREV and curr_n <= prev_n * DROP_FRACTION_ALERT:
            pct = int(100 * curr_n / prev_n) if prev_n else 0
            alerts.append(
                f"source '{src}' dropped from {prev_n} to {curr_n} ({pct}%)"
            )
    for src in prev.keys() - curr.keys():
        if prev[src] > 0:
            alerts.append(f"source '{src}' missing entirely from this run")
    return alerts


def main() -> int:
    data = _load_json(JOBS, default=None)
    if not data or "jobs" not in data:
        print(f"[stats] ERROR: {JOBS} not found or malformed", file=sys.stderr)
        return 0

    jobs = data["jobs"]
    by_source = _count_by(jobs, "source")
    by_country = _count_by(jobs, "country")

    prev = _load_json(OUT, default={"history": []})
    prev_history: list[dict] = (
        prev.get("history", []) if isinstance(prev, dict) else []
    )
    prev_by_source: dict[str, int] = (
        prev_history[-1].get("by_source", {}) if prev_history else {}
    )

    alerts = _diff_alerts(by_source, prev_by_source)

    snapshot = {
        "ts": _utc_now(),
        "total": len(jobs),
        "by_source": by_source,
        "by_country": by_country,
    }
    history = (prev_history + [snapshot])[-HISTORY_MAX:]

    out = {
        "updated_at": snapshot["ts"],
        "total": snapshot["total"],
        "by_source": by_source,
        "by_country": by_country,
        "history": history,
        "alerts": alerts,
    }
    OUT.write_text(
        json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    print(
        f"[stats] total={out['total']}  sources={len(by_source)}  "
        f"countries={len(by_country)}"
    )
    print("[stats] by_source:", by_source)
    print("[stats] by_country:", by_country)
    if alerts:
        print("[stats] ALERTS:")
        for a in alerts:
            print(f"  ! {a}")
    else:
        print("[stats] no alerts")
    return 0


if __name__ == "__main__":
    sys.exit(main())
