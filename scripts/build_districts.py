"""Build the district reference files used by the app.

Run once (or whenever the source data changes):

    python scripts/build_districts.py --source /path/to/source-data

`--source` must contain:
  boundaries/2011_Dist.shp (+ .dbf/.shx)   DataMeet 2011 district boundaries
  census2011_district_variables.csv        Census 2011 Primary Census Abstract (by censuscode)
  climate_baseline.csv                     1991-2020 IMD climatology per district (by censuscode)
  ndap_census_district_crosswalk.csv       NITI Aayog CVI 2021 matched to census codes

Outputs (committed to the repo, so the app never needs the raw data):
  data/districts.csv       one row per district: location + baseline + vulnerability
  data/districts.geojson   simplified polygons for the map
"""
from __future__ import annotations

import argparse
import csv
import json
import statistics
from collections import defaultdict
from pathlib import Path

import shapefile  # pyshp
from shapely.geometry import mapping, shape

ROOT = Path(__file__).resolve().parents[1]
SIMPLIFY_DEG = 0.02  # ~2 km; keeps the GeoJSON small while looking smooth at country zoom
COORD_DECIMALS = 3


def read_csv(path: Path) -> list[dict]:
    with path.open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def round_coords(obj):
    if isinstance(obj, (list, tuple)):
        if obj and isinstance(obj[0], (int, float)):
            return [round(obj[0], COORD_DECIMALS), round(obj[1], COORD_DECIMALS)]
        return [round_coords(o) for o in obj]
    return obj


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--source", type=Path, required=True)
    args = ap.parse_args()
    src: Path = args.source

    census = {int(r["censuscode"]): r for r in read_csv(src / "census2011_district_variables.csv")}
    climate = {int(r["censuscode"]): r for r in read_csv(src / "climate_baseline.csv")}

    # Several 2021 districts can map back to one 2011 district: average their index.
    cvi_by_code: dict[int, list[float]] = defaultdict(list)
    for r in read_csv(src / "ndap_census_district_crosswalk.csv"):
        if r["censuscode"] and r["climate_vul_in"] not in ("", "NaN"):
            cvi_by_code[int(float(r["censuscode"]))].append(float(r["climate_vul_in"]))
    cvi = {k: statistics.mean(v) for k, v in cvi_by_code.items()}

    reader = shapefile.Reader(str(src / "boundaries" / "2011_Dist"))
    rows, features = [], []
    for sr in reader.iterShapeRecords():
        rec = sr.record.as_dict()
        code = int(rec["censuscode"])
        if code == 0:  # area with no census data: drawn on the map, never forecast
            features.append({"type": "Feature", "properties": {"code": 0, "name": "No data", "state": rec["ST_NM"].strip()},
                             "geometry": round_coords(mapping(shape(sr.shape.__geo_interface__).simplify(SIMPLIFY_DEG)))})
            continue
        geom = shape(sr.shape.__geo_interface__)
        if not geom.is_valid:
            geom = geom.buffer(0)
        point = geom.representative_point()  # always inside the polygon, unlike a centroid
        c = census.get(code, {})
        cl = climate.get(code, {})
        rows.append(
            {
                "code": code,
                "name": rec["DISTRICT"].strip(),
                "state": rec["ST_NM"].strip(),
                "lat": round(point.y, 4),
                "lon": round(point.x, 4),
                "population": c.get("total_population", ""),
                "vulnerability": round(cvi[code], 3) if code in cvi else "",
                "normal_rx5day_mm": cl.get("rx5day_mm", ""),
                "normal_annual_rain_mm": cl.get("annual_rain_mm", ""),
                "normal_hot_days": cl.get("hot_days", ""),
            }
        )
        simple = geom.simplify(SIMPLIFY_DEG, preserve_topology=True)
        features.append(
            {
                "type": "Feature",
                "properties": {"code": code, "name": rec["DISTRICT"].strip(), "state": rec["ST_NM"].strip()},
                "geometry": round_coords(mapping(simple)),
            }
        )

    rows.sort(key=lambda r: r["code"])
    out_csv = ROOT / "data" / "districts.csv"
    with out_csv.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)

    out_geo = ROOT / "data" / "districts.geojson"
    out_geo.write_text(json.dumps({"type": "FeatureCollection", "features": features}, separators=(",", ":")))
    print(f"{len(rows)} districts -> {out_csv.name}, {out_geo.name} ({out_geo.stat().st_size/1e6:.2f} MB)")
    print(f"with vulnerability index: {sum(1 for r in rows if r['vulnerability'] != '')}")


if __name__ == "__main__":
    main()
