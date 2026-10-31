"""Fetch today's forecast for every district and write data/latest.json.

    python scripts/refresh.py               # all districts
    python scripts/refresh.py --limit 20    # quick smoke test
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.data import SNAPSHOT_JSON, load_districts  # noqa: E402
from app.forecast import fetch_forecasts  # noqa: E402
from app.pipeline import build_snapshot  # noqa: E402


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--out", type=Path, default=SNAPSHOT_JSON)
    args = ap.parse_args()

    districts = load_districts()[: args.limit]
    print(f"Fetching forecasts for {len(districts)} districts...")
    forecasts = fetch_forecasts((d.lat, d.lon) for d in districts)
    snap = build_snapshot(districts, forecasts)

    args.out.write_text(json.dumps(snap, separators=(",", ":"), ensure_ascii=False), encoding="utf-8")
    levels: dict[str, int] = {}
    for r in snap["districts"].values():
        levels[r["level"]] = levels.get(r["level"], 0) + 1
    print(f"Wrote {args.out} ({args.out.stat().st_size / 1e3:.0f} kB): {levels}")


if __name__ == "__main__":
    main()
