"""Open-Meteo forecast client.

Open-Meteo is free for non-commercial use, needs no API key, and accepts many
coordinates in one request, so all 640 districts take about 7 calls.
Weather data by Open-Meteo.com (CC BY 4.0).
"""
from __future__ import annotations

import time
from collections.abc import Iterable

import httpx

from .risk import Day

API_URL = "https://api.open-meteo.com/v1/forecast"
DAILY_VARS = [
    "temperature_2m_max",
    "temperature_2m_min",
    "apparent_temperature_max",
    "precipitation_sum",
    "precipitation_probability_max",
]
BATCH_SIZE = 100
FORECAST_DAYS = 7


def build_params(points: list[tuple[float, float]]) -> dict:
    return {
        "latitude": ",".join(f"{lat:.4f}" for lat, _ in points),
        "longitude": ",".join(f"{lon:.4f}" for _, lon in points),
        "daily": ",".join(DAILY_VARS),
        "timezone": "Asia/Kolkata",
        "forecast_days": FORECAST_DAYS,
    }


def parse_location(payload: dict) -> list[Day]:
    """Convert one location's Open-Meteo response into Day objects.

    Missing values come back as null; rain is treated as 0 and temperature
    gaps drop the day.
    """
    d = payload["daily"]
    days = []
    for i, date in enumerate(d["time"]):
        tmax = d["temperature_2m_max"][i]
        if tmax is None:
            continue
        days.append(
            Day(
                date=date,
                rain_mm=d["precipitation_sum"][i] or 0.0,
                tmax=tmax,
                tmin=d.get("temperature_2m_min", [None] * (i + 1))[i],
                feels_like=d.get("apparent_temperature_max", [None] * (i + 1))[i],
                rain_prob=d.get("precipitation_probability_max", [None] * (i + 1))[i],
            )
        )
    return days


def _get(client: httpx.Client, params: dict, retries: int = 4) -> list[dict]:
    delay = 2.0
    for attempt in range(retries + 1):
        try:
            r = client.get(API_URL, params=params, timeout=60)
            if r.status_code == 429 or r.status_code >= 500:
                raise httpx.HTTPStatusError(f"HTTP {r.status_code}", request=r.request, response=r)
            r.raise_for_status()
            data = r.json()
            return data if isinstance(data, list) else [data]
        except (httpx.HTTPError, ValueError):
            if attempt == retries:
                raise
            time.sleep(delay)
            delay *= 2
    raise RuntimeError("unreachable")


def fetch_forecasts(points: Iterable[tuple[float, float]], client: httpx.Client | None = None) -> list[list[Day]]:
    """Fetch forecasts for many points, preserving input order."""
    points = list(points)
    own = client is None
    client = client or httpx.Client(headers={"User-Agent": "india-weather-risk"})
    try:
        out: list[list[Day]] = []
        for start in range(0, len(points), BATCH_SIZE):
            batch = points[start: start + BATCH_SIZE]
            payloads = _get(client, build_params(batch))
            if len(payloads) != len(batch):
                raise RuntimeError(f"expected {len(batch)} locations, got {len(payloads)}")
            out.extend(parse_location(p) for p in payloads)
            time.sleep(1.0)  # be polite to a free service
        return out
    finally:
        if own:
            client.close()
