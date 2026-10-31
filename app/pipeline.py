"""Build a risk snapshot: forecasts in, one JSON file out."""
from __future__ import annotations

import statistics
from collections import defaultdict
from dataclasses import asdict
from datetime import UTC, datetime

from .data import District
from .risk import MODEL_VERSION, Day, score_district, vulnerability_weight


def fill_vulnerability(districts: list[District]) -> dict[int, tuple[float, bool]]:
    """Vulnerability per district; gaps get the state median, then the national median.

    Returns {code: (value, imputed)}.
    """
    known = [d.vulnerability for d in districts if d.vulnerability is not None]
    national = statistics.median(known)
    by_state: dict[str, list[float]] = defaultdict(list)
    for d in districts:
        if d.vulnerability is not None:
            by_state[d.state].append(d.vulnerability)
    out = {}
    for d in districts:
        if d.vulnerability is not None:
            out[d.code] = (d.vulnerability, False)
        elif by_state.get(d.state):
            out[d.code] = (statistics.median(by_state[d.state]), True)
        else:
            out[d.code] = (national, True)
    return out


def build_snapshot(districts: list[District], forecasts: list[list[Day]], now: datetime | None = None) -> dict:
    if len(districts) != len(forecasts):
        raise ValueError("districts and forecasts must line up")
    now = now or datetime.now(UTC)
    vuln = fill_vulnerability(districts)
    values = [v for v, _ in vuln.values()]
    v_min, v_max = min(values), max(values)

    results = {}
    for d, days in zip(districts, forecasts):
        if not days:
            continue
        v, imputed = vuln[d.code]
        w = vulnerability_weight(v, v_min, v_max)
        r = score_district(days, d.normal_rx5day_mm, w)
        results[str(d.code)] = {
            "code": d.code,
            "name": d.name,
            "state": d.state,
            "population": d.population,
            "vulnerability": round(v, 3),
            "vulnerability_imputed": imputed,
            "vulnerability_weight": w,
            **asdict(r),
        }

    dates = sorted({row["date"] for r in results.values() for row in r["daily"]})
    return {
        "generated_at": now.isoformat(timespec="seconds"),
        "model_version": MODEL_VERSION,
        "source": "Open-Meteo forecast (CC BY 4.0); IMD 1991-2020 normals; NITI Aayog CVI 2021",
        "dates": dates,
        "district_count": len(results),
        "districts": results,
    }
