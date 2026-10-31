"""Turn a 7-day forecast into flood and heat risk scores for one district.

Risk follows the IPCC framing: risk = hazard x vulnerability.

* Hazard (0-1) comes from the forecast, scored against India Meteorological
  Department (IMD) thresholds and against the district's own 30-year climate.
* Vulnerability comes from the NITI Aayog Climate Vulnerability Index (2021).
  It scales hazard between 50% (least vulnerable district) and 100% (most
  vulnerable), so a storm never disappears from the map just because a
  district is well prepared.

Every number here is documented in docs/METHODOLOGY.md.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date as _date

MODEL_VERSION = "1.0.0"

# IMD 24-hour rainfall categories (mm): heavy, very heavy, extremely heavy.
RAIN_MODERATE = 15.6
RAIN_HEAVY = 64.5
RAIN_VERY_HEAVY = 115.6
RAIN_EXTREME = 204.5

# IMD heatwave criteria for the plains: Tmax >= 40 C, severe at >= 45 C.
HEAT_WATCH = 35.0
HEAT_WAVE = 40.0
HEAT_SEVERE = 45.0
WARM_NIGHT = 30.0

LEVELS = [(0.6, "Severe"), (0.35, "High"), (0.15, "Moderate"), (0.0, "Low")]


def _ramp(x: float, points: list[tuple[float, float]]) -> float:
    """Piecewise-linear interpolation through (x, y) points, flat outside them."""
    if x <= points[0][0]:
        return points[0][1]
    for (x0, y0), (x1, y1) in zip(points, points[1:]):
        if x <= x1:
            return y0 + (y1 - y0) * (x - x0) / (x1 - x0)
    return points[-1][1]


def pretty_date(iso: str) -> str:
    """'2026-11-03' -> 'Tue 3 Nov'."""
    d = _date.fromisoformat(iso)
    return f"{d:%a} {d.day} {d:%b}"


def rain_category(mm: float) -> str:
    if mm >= RAIN_EXTREME:
        return "extremely heavy"
    if mm >= RAIN_VERY_HEAVY:
        return "very heavy"
    if mm >= RAIN_HEAVY:
        return "heavy"
    if mm >= RAIN_MODERATE:
        return "moderate"
    return "light"


def rain_intensity_score(daily_mm: float) -> float:
    """How severe one day's rain is on IMD's national scale."""
    return _ramp(
        daily_mm,
        [(RAIN_MODERATE, 0.0), (RAIN_HEAVY, 0.35), (RAIN_VERY_HEAVY, 0.6), (RAIN_EXTREME, 0.85), (300.0, 1.0)],
    )


def rain_anomaly_score(window_mm: float, normal_rx5day_mm: float | None) -> float:
    """How unusual a multi-day total is *for this district*.

    `normal_rx5day_mm` is the district's average wettest 5-day spell of the
    year (1991-2020). Reaching half of it scores 0; 1.5x of it scores 1.
    """
    if not normal_rx5day_mm or normal_rx5day_mm <= 0:
        return 0.0
    return _ramp(window_mm / normal_rx5day_mm, [(0.5, 0.0), (1.5, 1.0)])


def flood_hazard(daily_mm: float, window_mm: float, normal_rx5day_mm: float | None) -> float:
    intensity = rain_intensity_score(daily_mm)
    anomaly = rain_anomaly_score(window_mm, normal_rx5day_mm)
    return round(0.6 * intensity + 0.4 * anomaly, 3)


def heat_hazard(tmax: float, feels_like: float | None, tmin: float | None, hot_streak: int) -> float:
    """Heat hazard for one day.

    `hot_streak` is how many consecutive days (ending today) reach 40 C. IMD
    declares a heatwave only after two such days, so a one-day spike counts
    for less.
    """
    t_score = _ramp(tmax, [(HEAT_WATCH, 0.0), (HEAT_WAVE, 0.3), (HEAT_SEVERE, 0.75), (48.0, 1.0)])
    f_score = 0.0 if feels_like is None else _ramp(feels_like, [(38.0, 0.0), (46.0, 0.6), (54.0, 1.0)])
    score = max(t_score, f_score)
    if tmin is not None and tmin >= WARM_NIGHT and tmax >= HEAT_WAVE:
        score += 0.1  # no relief at night
    if tmax >= HEAT_WAVE and hot_streak < 2:
        score *= 0.85
    return round(min(score, 1.0), 3)


def vulnerability_weight(v: float | None, v_min: float, v_max: float) -> float:
    """Map a vulnerability index onto a 0.5-1.0 multiplier."""
    if v is None or v_max <= v_min:
        return 0.75
    rel = min(max((v - v_min) / (v_max - v_min), 0.0), 1.0)
    return round(0.5 + 0.5 * rel, 3)


def level(score: float) -> str:
    for threshold, name in LEVELS:
        if score >= threshold:
            return name
    return "Low"


@dataclass
class Day:
    date: str
    rain_mm: float
    tmax: float
    tmin: float | None = None
    feels_like: float | None = None
    rain_prob: float | None = None


@dataclass
class DistrictRisk:
    flood: float
    heat: float
    overall: float
    level: str
    peak_date: str
    drivers: list[str] = field(default_factory=list)
    daily: list[dict] = field(default_factory=list)


def score_district(days: list[Day], normal_rx5day_mm: float | None, vuln_weight: float) -> DistrictRisk:
    if not days:
        raise ValueError("no forecast days")

    daily = []
    streak = 0
    for i, d in enumerate(days):
        window = sum(x.rain_mm for x in days[max(0, i - 4): i + 1])  # 5-day running total
        streak = streak + 1 if d.tmax >= HEAT_WAVE else 0
        fh = flood_hazard(d.rain_mm, window, normal_rx5day_mm)
        hh = heat_hazard(d.tmax, d.feels_like, d.tmin, streak)
        daily.append(
            {
                "date": d.date,
                "rain_mm": round(d.rain_mm, 1),
                "rain_prob": d.rain_prob,
                "tmax": round(d.tmax, 1),
                "tmin": None if d.tmin is None else round(d.tmin, 1),
                "feels_like": None if d.feels_like is None else round(d.feels_like, 1),
                "flood": round(fh * vuln_weight, 3),
                "heat": round(hh * vuln_weight, 3),
            }
        )

    for row in daily:
        row["overall"] = max(row["flood"], row["heat"])
        row["level"] = level(row["overall"])

    flood = max(r["flood"] for r in daily)
    heat = max(r["heat"] for r in daily)
    overall = max(flood, heat)
    peak = max(daily, key=lambda r: r["overall"])

    return DistrictRisk(
        flood=flood,
        heat=heat,
        overall=overall,
        level=level(overall),
        peak_date=peak["date"],
        drivers=_explain(days, normal_rx5day_mm, vuln_weight),
        daily=daily,
    )


def _explain(days: list[Day], normal_rx5day_mm: float | None, vuln_weight: float) -> list[str]:
    """Plain-language reasons, most important first."""
    out = []
    wettest = max(days, key=lambda d: d.rain_mm)
    if wettest.rain_mm >= RAIN_MODERATE:
        out.append(f"{wettest.rain_mm:.0f} mm of rain on {pretty_date(wettest.date)} ({rain_category(wettest.rain_mm)} by IMD scale)")
    wettest_5 = max(sum(d.rain_mm for d in days[max(0, i - 4): i + 1]) for i in range(len(days)))
    if normal_rx5day_mm and wettest_5 >= 0.5 * normal_rx5day_mm:
        out.append(f"{wettest_5:.0f} mm over 5 days = {wettest_5 / normal_rx5day_mm:.1f}x the district's usual wettest 5-day spell")
    hottest = max(days, key=lambda d: d.tmax)
    if hottest.tmax >= HEAT_WATCH:
        feels = f", feels like {hottest.feels_like:.0f} °C" if hottest.feels_like is not None else ""
        out.append(f"Up to {hottest.tmax:.1f} °C on {pretty_date(hottest.date)}{feels}")
    hw_days = sum(1 for d in days if d.tmax >= HEAT_WAVE)
    if hw_days >= 2:
        out.append(f"{hw_days} days at or above the 40 °C heatwave mark")
    if not out:
        return ["No significant rain or heat in the 7-day forecast"]
    if vuln_weight >= 0.85:
        out.append("High climate vulnerability (NITI Aayog index) amplifies impact")
    elif vuln_weight <= 0.6:
        out.append("Low climate vulnerability (NITI Aayog index) reduces impact")
    return out
