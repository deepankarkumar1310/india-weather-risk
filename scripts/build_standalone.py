"""Bundle the map into one HTML file that opens without a server.

    python scripts/build_standalone.py            # -> india-weather-risk.html

The file inlines the CSS, JS, district map and the current forecast
(data/latest.json), so it is a snapshot: rebuild it to get a newer forecast.
Leaflet still loads from cdnjs, so an internet connection is needed.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WEB, DATA = ROOT / "web", ROOT / "data"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", type=Path, default=ROOT / "india-weather-risk.html")
    args = ap.parse_args()

    snap_path = DATA / "latest.json"
    if not snap_path.exists():
        raise SystemExit("data/latest.json not found: run scripts/refresh.py or git pull first")

    html = (WEB / "index.html").read_text(encoding="utf-8")
    css = (WEB / "style.css").read_text(encoding="utf-8")
    js = (WEB / "app.js").read_text(encoding="utf-8")
    geo = (DATA / "districts.geojson").read_text(encoding="utf-8")
    snap = json.dumps(json.loads(snap_path.read_text(encoding="utf-8")), separators=(",", ":"), ensure_ascii=False)

    # Keep "</script>" inside JSON from closing the tag early.
    data_js = f"window.EMBEDDED_DATA={{geo:{geo},snap:{snap}}};".replace("</", "<\\/")

    html = html.replace('<link rel="stylesheet" href="style.css">', f"<style>\n{css}\n</style>")
    html = html.replace('<script src="app.js"></script>', f"<script>{data_js}</script>\n  <script>\n{js}\n  </script>")
    assert "style.css" not in html and 'src="app.js"' not in html, "index.html layout changed; update this script"

    args.out.write_text(html, encoding="utf-8")
    print(f"Wrote {args.out} ({args.out.stat().st_size / 1e6:.1f} MB), forecast from {json.loads(snap)['generated_at']}")


if __name__ == "__main__":
    main()
