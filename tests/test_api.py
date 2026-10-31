import json

import pytest
from fastapi.testclient import TestClient

import app.data as data_mod
import app.main as main_mod
from app.data import load_districts
from app.forecast import parse_location
from app.pipeline import build_snapshot


@pytest.fixture
def client(tmp_path, monkeypatch, open_meteo_payload):
    ds = load_districts()[:2]
    snap = build_snapshot(ds, [parse_location(p) for p in open_meteo_payload])
    path = tmp_path / "latest.json"
    path.write_text(json.dumps(snap), encoding="utf-8")
    monkeypatch.setattr(main_mod, "SNAPSHOT_JSON", path)
    monkeypatch.setattr(main_mod, "load_snapshot", lambda: data_mod.load_snapshot(path))
    main_mod._cache.update(mtime=None, snap=None)
    return TestClient(main_mod.app), ds


def test_health(client):
    c, _ = client
    assert c.get("/api/health").json()["status"] == "ok"


def test_risk_sorted_by_hazard(client):
    c, _ = client
    for hazard in ("overall", "flood", "heat"):
        rows = c.get("/api/risk", params={"hazard": hazard}).json()["districts"]
        assert [r[hazard] for r in rows] == sorted((r[hazard] for r in rows), reverse=True)


def test_risk_filters(client):
    c, _ = client
    body = c.get("/api/risk", params={"min_level": "Severe"}).json()
    assert all(r["level"] == "Severe" for r in body["districts"])
    assert c.get("/api/risk", params={"hazard": "wind"}).status_code == 422


def test_detail_and_404(client):
    c, ds = client
    r = c.get(f"/api/risk/{ds[0].code}").json()
    assert r["name"] == ds[0].name and len(r["daily"]) == 7
    assert c.get("/api/risk/99999").status_code == 404


def test_districts_endpoint(client):
    c, _ = client
    assert len(c.get("/api/districts").json()) == 640
    assert all(d["state"] == "Kerala" for d in c.get("/api/districts", params={"state": "kerala"}).json())


def test_static_site_served(client):
    c, _ = client
    assert "India Weather Risk" in c.get("/").text
    assert c.get("/data/districts.geojson").status_code == 200


def test_no_snapshot_returns_503(tmp_path, monkeypatch):
    monkeypatch.setattr(main_mod, "SNAPSHOT_JSON", tmp_path / "missing.json")
    main_mod._cache.update(mtime=None, snap=None)
    assert TestClient(main_mod.app).get("/api/risk").status_code == 503
