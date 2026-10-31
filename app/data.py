"""Load the district reference table and the latest risk snapshot."""
from __future__ import annotations

import csv
import json
from dataclasses import dataclass
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parents[1] / "data"
DISTRICTS_CSV = DATA_DIR / "districts.csv"
SNAPSHOT_JSON = DATA_DIR / "latest.json"


def _num(s: str) -> float | None:
    return float(s) if s not in ("", None) else None


@dataclass(frozen=True)
class District:
    code: int
    name: str
    state: str
    lat: float
    lon: float
    population: int | None
    vulnerability: float | None
    normal_rx5day_mm: float | None
    normal_annual_rain_mm: float | None
    normal_hot_days: float | None


def load_districts(path: Path = DISTRICTS_CSV) -> list[District]:
    with path.open(newline="", encoding="utf-8") as f:
        return [
            District(
                code=int(r["code"]),
                name=r["name"],
                state=r["state"],
                lat=float(r["lat"]),
                lon=float(r["lon"]),
                population=int(r["population"]) if r["population"] else None,
                vulnerability=_num(r["vulnerability"]),
                normal_rx5day_mm=_num(r["normal_rx5day_mm"]),
                normal_annual_rain_mm=_num(r["normal_annual_rain_mm"]),
                normal_hot_days=_num(r["normal_hot_days"]),
            )
            for r in csv.DictReader(f)
        ]


def load_snapshot(path: Path = SNAPSHOT_JSON) -> dict | None:
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))
