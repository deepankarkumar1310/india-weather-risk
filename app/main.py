"""FastAPI app: JSON API under /api, the map at /."""
from __future__ import annotations

from enum import Enum
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.staticfiles import StaticFiles

from .data import DATA_DIR, SNAPSHOT_JSON, load_districts, load_snapshot
from .risk import MODEL_VERSION

WEB_DIR = Path(__file__).resolve().parents[1] / "web"

app = FastAPI(
    title="India Weather Risk API",
    version=MODEL_VERSION,
    description="7-day flood and heatwave risk for 640 Indian districts. "
    "Weather data by Open-Meteo.com (CC BY 4.0).",
)
app.add_middleware(GZipMiddleware, minimum_size=1000)


class Hazard(str, Enum):
    overall = "overall"
    flood = "flood"
    heat = "heat"


class Level(str, Enum):
    Low = "Low"
    Moderate = "Moderate"
    High = "High"
    Severe = "Severe"


_cache: dict = {"mtime": None, "snap": None}


def snapshot() -> dict:
    """The latest snapshot, reloaded whenever the file changes on disk."""
    mtime = SNAPSHOT_JSON.stat().st_mtime if SNAPSHOT_JSON.exists() else None
    if mtime != _cache["mtime"]:
        _cache.update(mtime=mtime, snap=load_snapshot())
    if _cache["snap"] is None:
        raise HTTPException(503, "No forecast yet. Run `python scripts/refresh.py`.")
    return _cache["snap"]


def summary(r: dict) -> dict:
    keys = ("code", "name", "state", "flood", "heat", "overall", "level", "peak_date")
    return {k: r[k] for k in keys}


@app.get("/api/health", tags=["meta"])
def health():
    snap = load_snapshot()
    return {
        "status": "ok" if snap else "no-data",
        "generated_at": snap and snap["generated_at"],
        "districts": snap and snap["district_count"],
        "model_version": MODEL_VERSION,
    }


@app.get("/api/districts", tags=["districts"])
def districts(state: str | None = None):
    """All districts with their forecast point and baseline climate."""
    rows = load_districts()
    if state:
        rows = [d for d in rows if d.state.lower() == state.lower()]
    return [d.__dict__ for d in rows]


@app.get("/api/risk", tags=["risk"])
def risk(
    hazard: Hazard = Hazard.overall,
    min_level: Level | None = None,
    state: str | None = None,
    limit: int = Query(700, ge=1, le=700),
):
    """Every district's 7-day peak risk, highest first."""
    snap = snapshot()
    order = [lvl.value for lvl in Level]
    rows = list(snap["districts"].values())
    if state:
        rows = [r for r in rows if r["state"].lower() == state.lower()]
    if min_level:
        rows = [r for r in rows if order.index(r["level"]) >= order.index(min_level.value)]
    rows.sort(key=lambda r: r[hazard.value], reverse=True)
    return {
        "generated_at": snap["generated_at"],
        "hazard": hazard.value,
        "count": len(rows[:limit]),
        "districts": [summary(r) for r in rows[:limit]],
    }


@app.get("/api/risk/{code}", tags=["risk"])
def risk_detail(code: int):
    """Full 7-day breakdown and plain-language drivers for one district."""
    snap = snapshot()
    r = snap["districts"].get(str(code))
    if r is None:
        raise HTTPException(404, f"No district with code {code}")
    return {"generated_at": snap["generated_at"], **r}


app.mount("/data", StaticFiles(directory=DATA_DIR), name="data")
app.mount("/", StaticFiles(directory=WEB_DIR, html=True), name="web")
