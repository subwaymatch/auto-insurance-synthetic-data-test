"""Download the public source data used to build reference/zip_reference.csv.

This is a one-off, network-dependent step. Its outputs are cached in a local
directory (not committed). `build_reference_data.py` turns the cache into the
small CSVs under reference/ that the generator reads, so generating data never
needs the network.

Sources (all public, no API key needed):
  * US Census Bureau ACS 2020-2024 5-year table-based summary files (ZCTA level)
  * US Census Bureau 2020 ZCTA-to-county relationship file and 2024 ZCTA gazetteer
  * GeoNames postal code file (CC BY 4.0) for ZIP place names
  * City of Chicago Data Portal: Traffic Crashes (Crashes, People), Crimes,
    and ZIP Code boundaries
"""
from __future__ import annotations

import argparse
import json
import time
import urllib.parse
import urllib.request
from pathlib import Path

ACS_YEAR = 2024
ACS_BASE = (f"https://www2.census.gov/programs-surveys/acs/summary_file/{ACS_YEAR}"
            f"/table-based-SF/data/5YRData/acsdt5y{ACS_YEAR}-{{table}}.dat")
ACS_TABLES = ["b01003", "b19013", "b25003", "b08201", "b08301", "b08013", "b01001", "b03002"]
ZCTA_PREFIX = "860Z200US60"   # ZCTA rows for ZIPs starting with 60 (northern Illinois)

REL_URL = "https://www2.census.gov/geo/docs/maps-data/data/rel2020/zcta520/tab20_zcta520_county20_natl.txt"
GAZ_URL = "https://www2.census.gov/geo/docs/maps-data/data/gazetteer/2024_Gazetteer/2024_Gaz_zcta_national.zip"
GEONAMES_URL = "https://download.geonames.org/export/zip/US.zip"

CHI = "https://data.cityofchicago.org/resource/"
CRASHES, PEOPLE, CRIMES, ZIP_BOUNDS = "85ca-t3if", "u6pd-qa9d", "ijzp-q8t2", "unjd-c2ca"
PERIOD = "crash_date between '2021-01-01T00:00:00' and '2025-12-31T23:59:59'"


def get(url: str, dest: Path, tries: int = 6, timeout: int = 300) -> None:
    if dest.exists() and dest.stat().st_size > 0:
        print(f"cached   {dest.name}")
        return
    for attempt in range(tries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "reference-data-builder"})
            with urllib.request.urlopen(req, timeout=timeout) as r, open(dest.with_suffix(".part"), "wb") as f:
                while chunk := r.read(1 << 20):
                    f.write(chunk)
            dest.with_suffix(".part").rename(dest)
            print(f"fetched  {dest.name} ({dest.stat().st_size:,} bytes)")
            return
        except Exception as e:  # noqa: BLE001 - retry any transient failure
            wait = 3 * 2 ** attempt
            print(f"retry    {dest.name}: {e} (waiting {wait}s)")
            time.sleep(wait)
    raise RuntimeError(f"could not download {url}")


def get_acs_filtered(table: str, dest: Path) -> None:
    """Stream a national ACS table and keep only the header and northern-Illinois ZCTA rows."""
    if dest.exists() and dest.stat().st_size > 0:
        print(f"cached   {dest.name}")
        return
    url = ACS_BASE.format(table=table)
    for attempt in range(6):
        try:
            with urllib.request.urlopen(url, timeout=600) as r, open(dest.with_suffix(".part"), "w") as f:
                for i, raw in enumerate(r):
                    line = raw.decode("utf-8", "replace")
                    if i == 0 or line.startswith(ZCTA_PREFIX):
                        f.write(line)
            dest.with_suffix(".part").rename(dest)
            print(f"fetched  {dest.name}")
            return
        except Exception as e:  # noqa: BLE001
            print(f"retry    {dest.name}: {e}")
            time.sleep(3 * 2 ** attempt)
    raise RuntimeError(f"could not download {url}")


def soql(dataset: str, fmt: str = "json", **params: str) -> str:
    q = urllib.parse.urlencode({f"${k}": v for k, v in params.items()})
    return f"{CHI}{dataset}.{fmt}?{q}"


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--cache", type=Path, default=Path("reference/_cache"))
    cache = ap.parse_args().cache
    cache.mkdir(parents=True, exist_ok=True)

    for t in ACS_TABLES:
        get_acs_filtered(t, cache / f"acs_{t}.psv")
    get(REL_URL, cache / "zcta_county_rel.txt")
    get(GAZ_URL, cache / "gaz_zcta.zip")
    get(GEONAMES_URL, cache / "geonames_us.zip")

    get(soql(ZIP_BOUNDS, "geojson", limit="500"), cache / "chicago_zip_boundaries.geojson")
    # Drivers involved in Chicago crashes, by the ZIP code they live in.
    get(soql(PEOPLE, select="zipcode,count(*) as n", where=f"person_type='DRIVER' AND {PERIOD}",
             group="zipcode", limit="100000"), cache / "chi_drivers_by_home_zip.json")
    get(soql(CRASHES, select="date_extract_y(crash_date) as y,date_extract_m(crash_date) as m,count(*) as n,"
                             "sum(case(hit_and_run_i='Y',1,true,0)) as hit_and_run,"
                             "sum(case(injuries_total>0,1,true,0)) as injury",
             where=PERIOD, group="y,m", order="y,m", limit="1000"), cache / "chi_crashes_by_month.json")
    get(soql(CRIMES, select="year,date_extract_m(date) as m,count(*) as n",
             where="primary_type='MOTOR VEHICLE THEFT' AND year >= 2019",
             group="year,m", order="year,m", limit="1000"), cache / "chi_theft_by_month.json")
    get(soql(CRIMES, "csv", select="year,latitude,longitude",
             where="primary_type='MOTOR VEHICLE THEFT' AND year between 2021 and 2025 AND latitude IS NOT NULL",
             limit="500000"), cache / "chi_theft_points.csv")

    for name in ["chi_drivers_by_home_zip.json", "chi_crashes_by_month.json", "chi_theft_by_month.json"]:
        json.loads((cache / name).read_text())  # fail loudly if the portal returned an error page
    print("done")


if __name__ == "__main__":
    main()
