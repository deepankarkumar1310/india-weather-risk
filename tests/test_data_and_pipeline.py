import json
from datetime import UTC, datetime

from app.data import DATA_DIR, load_districts
from app.forecast import parse_location
from app.pipeline import build_snapshot, fill_vulnerability


def test_district_table_is_complete():
    ds = load_districts()
    assert len(ds) == 640
    assert len({d.code for d in ds}) == 640
    for d in ds:
        assert 6 <= d.lat <= 38 and 68 <= d.lon <= 98, d
    assert sum(d.vulnerability is not None for d in ds) > 550


def test_geojson_matches_table():
    geo = json.loads((DATA_DIR / "districts.geojson").read_text(encoding="utf-8"))
    codes = {f["properties"]["code"] for f in geo["features"]} - {0}
    assert codes == {d.code for d in load_districts()}


def test_every_district_gets_a_vulnerability():
    ds = load_districts()
    vuln = fill_vulnerability(ds)
    assert set(vuln) == {d.code for d in ds}
    assert any(imputed for _, imputed in vuln.values())


def test_snapshot_shape(open_meteo_payload):
    ds = load_districts()[:2]
    forecasts = [parse_location(p) for p in open_meteo_payload]
    snap = build_snapshot(ds, forecasts, now=datetime(2026, 7, 1, tzinfo=UTC))
    assert snap["district_count"] == 2
    assert snap["dates"][0] == "2026-07-01"
    r = snap["districts"][str(ds[0].code)]
    assert {"flood", "heat", "overall", "level", "drivers", "daily"} <= set(r)
    assert len(r["daily"]) == 7
