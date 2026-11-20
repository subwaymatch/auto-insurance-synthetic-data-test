#!/usr/bin/env python3
"""Fetch the outlines of Lakefront's 290 ZIP codes for the website's territory map.

    pip install shapely
    python site/geo/fetch_zip_boundaries.py --location <build>/location.csv

Downloads each ZIP code tabulation area (2020 Census ZCTAs, from the Census Bureau's TIGERweb service),
simplifies it, dissolves the ZIPs into county outlines, and writes site/geo/zip_boundaries.geojson with each
ZIP's city, county and rating territories taken from a build's location.csv. Run it again if the ZIP list or
the territories change; site/build.py checks the file against samples/synthetic/location.csv.
"""
from __future__ import annotations

import argparse
import csv
import json
import urllib.parse
import urllib.request
from pathlib import Path

from shapely.geometry import mapping, shape
from shapely.ops import unary_union

HERE = Path(__file__).resolve().parent
LAYER = "https://tigerweb.geo.census.gov/arcgis/rest/services/TIGERweb/PUMA_TAD_TAZ_UGA_ZCTA/MapServer/7/query"
SIMPLIFY_DEGREES = 0.0012    # about 100 m: invisible at the map's size
DIGITS = 4                   # about 10 m


def fetch(zips: list[str]) -> list[dict]:
    features = []
    for i in range(0, len(zips), 60):
        chunk = zips[i:i + 60]
        body = urllib.parse.urlencode({
            "where": "ZCTA5 IN (%s)" % ",".join(f"'{z}'" for z in chunk),
            "outFields": "ZCTA5", "returnGeometry": "true", "outSR": "4326", "f": "geojson",
        }).encode()
        with urllib.request.urlopen(urllib.request.Request(LAYER, data=body), timeout=120) as r:
            features += json.load(r)["features"]
    return features


def rounded(geom):
    def walk(c):
        return [walk(x) for x in c] if isinstance(c[0], (list, tuple)) else [round(c[0], DIGITS), round(c[1], DIGITS)]
    g = mapping(geom)
    return {"type": g["type"], "coordinates": walk(g["coordinates"])}


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--location", type=Path, required=True, help="location.csv from a full build")
    ap.add_argument("--out", type=Path, default=HERE / "zip_boundaries.geojson")
    args = ap.parse_args()
    rows = {r["zip_code"]: r for r in csv.DictReader(args.location.open())}
    found = {f["properties"]["ZCTA5"]: f for f in fetch(sorted(rows))}
    missing = sorted(set(rows) - set(found))
    if missing:
        raise SystemExit(f"no boundary for ZIP codes {missing}")
    zips, by_county = [], {}
    for z, r in sorted(rows.items()):
        geom = shape(found[z]["geometry"]).buffer(0)
        by_county.setdefault(r["county"], []).append(geom)
        zips.append({"type": "Feature", "geometry": rounded(geom.simplify(SIMPLIFY_DEGREES, preserve_topology=True)),
                     "properties": {"kind": "zip", "zip_code": z, "city": r["city"], "county": r["county"],
                                    "liability_territory": r["liability_territory"],
                                    "comprehensive_territory": r["comprehensive_territory"]}})
    counties = [{"type": "Feature", "properties": {"kind": "county", "county": c},
                 "geometry": rounded(unary_union(g).buffer(0.0004).buffer(-0.0004).simplify(SIMPLIFY_DEGREES * 1.5))}
                for c, g in sorted(by_county.items())]
    out = {"type": "FeatureCollection",
           "source": "US Census Bureau, TIGERweb, 2020 Census ZIP Code Tabulation Areas (simplified)",
           "features": zips + counties}
    args.out.write_text(json.dumps(out, separators=(",", ":")))
    print(f"wrote {len(zips)} ZIP codes and {len(counties)} counties to {args.out} ({args.out.stat().st_size // 1024} KB)")


if __name__ == "__main__":
    main()
