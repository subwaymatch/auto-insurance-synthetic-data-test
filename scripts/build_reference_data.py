"""Build reference/zip_reference.csv and reference/calendar_indices.csv.

Run `fetch_public_data.py` first. This step is deterministic (no randomness):
the same cache always produces the same reference files. The reference files
are committed, so the generator itself never needs the network.

What is observed and what is modelled
-------------------------------------
* Demographics for every ZIP are observed (Census ACS 2020-2024 5-year).
* Crash and vehicle-theft hazard for ZIPs inside the City of Chicago are
  derived from observed police records (drivers involved in crashes by home
  ZIP; vehicle thefts by location), per resident vehicle, 2021-2025.
* The city data does not cover the suburbs, so suburban hazard is MODELLED:
  the city's income gradient is applied to each suburb's income and scaled by
  an assumed suburban level (SUBURB_*_LEVEL below).
* Raw police-record rates overstate insurance differences between areas
  (they count per vehicle, not per mile, and only crashes inside the city
  limits), so the spread is damped by an exponent (CRASH_DAMPING,
  THEFT_DAMPING). These are assumptions, chosen so the range of territory
  relativities is in line with typical rating plans.
"""
from __future__ import annotations

import argparse
import io
import json
import zipfile
from pathlib import Path

import numpy as np
import pandas as pd
import shapely

COUNTIES = {"17031": "Cook", "17043": "DuPage", "17097": "Lake", "17197": "Will",
            "17089": "Kane", "17111": "McHenry", "17093": "Kendall"}
MIN_POPULATION = 2500
MIN_HOUSEHOLDS_WITH_VEHICLE = 800
LOOP = (41.8781, -87.6298)

CRASH_CREDIBILITY_K = 400      # drivers; shrinks small ZIPs toward the city mean
THEFT_CREDIBILITY_K = 150      # thefts
CRASH_DAMPING = 0.55           # exponent applied to the observed crash relativity
THEFT_DAMPING = 0.80
SUBURB_CRASH_LEVEL = 0.85      # suburban level vs a city ZIP of the same income
SUBURB_THEFT_LEVEL = 0.40
YEARS = 5                      # 2021-2025

AGE_BANDS = {  # driver-age band -> B01001 male column numbers (female = male + 24)
    "16_17": [6], "18_20": [7, 8], "21_24": [9, 10], "25_29": [11], "30_34": [12], "35_39": [13],
    "40_44": [14], "45_49": [15], "50_54": [16], "55_59": [17], "60_64": [18, 19],
    "65_69": [20, 21], "70_74": [22], "75_79": [23], "80_84": [24], "85_plus": [25],
}


def acs(cache: Path, table: str) -> pd.DataFrame:
    d = pd.read_csv(cache / f"acs_{table}.psv", sep="|")
    d.index = d.pop("GEO_ID").str[-5:]
    d.index.name = "zip"
    return d[[c for c in d.columns if "_E" in c]].rename(columns=lambda c: int(c.split("_E")[1]))


def wmean(x: pd.Series, w: pd.Series) -> float:
    return float((x * w).sum() / w.sum())


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--cache", type=Path, default=Path("reference/_cache"))
    ap.add_argument("--out", type=Path, default=Path("reference"))
    args = ap.parse_args()
    c = args.cache

    # ---- geography -------------------------------------------------------
    rel = pd.read_csv(c / "zcta_county_rel.txt", sep="|", dtype=str, encoding="utf-8-sig")
    rel = rel[rel.GEOID_ZCTA5_20.notna()].assign(area=lambda d: d.AREALAND_PART.astype(float))
    rel = rel.sort_values(["GEOID_ZCTA5_20", "area"]).groupby("GEOID_ZCTA5_20").tail(1)
    rel = rel[rel.GEOID_COUNTY_20.isin(COUNTIES)].set_index("GEOID_ZCTA5_20")
    z = pd.DataFrame({"county": rel.GEOID_COUNTY_20.map(COUNTIES)})
    z.index.name = "zip"

    with zipfile.ZipFile(c / "gaz_zcta.zip") as zf:
        gaz = pd.read_csv(io.BytesIO(zf.read(zf.namelist()[0])), sep="\t", dtype={"GEOID": str})
    gaz.columns = gaz.columns.str.strip()
    gaz = gaz.set_index("GEOID")
    z["land_sqmi"], z["lat"], z["lon"] = gaz.ALAND_SQMI, gaz.INTPTLAT, gaz.INTPTLONG

    with zipfile.ZipFile(c / "geonames_us.zip") as zf:
        gn = pd.read_csv(io.BytesIO(zf.read("US.txt")), sep="\t", header=None, dtype=str)
    z["city"] = gn[gn[4] == "IL"].drop_duplicates(1).set_index(1)[2]

    # ---- demographics (ACS) ------------------------------------------------
    z["population"] = acs(c, "b01003")[1]
    z["median_household_income"] = acs(c, "b19013")[1]
    ten = acs(c, "b25003")
    z["households"], z["pct_owner_occupied"] = ten[1], ten[2] / ten[1]
    v = acs(c, "b08201")
    z["households_with_vehicle"] = v[1] - v[2]
    z["vehicles_available"] = v[3] + 2 * v[4] + 3 * v[5] + 4.3 * v[6]
    for k, col in zip(["1", "2", "3", "4plus"], [3, 4, 5, 6]):
        z[f"veh_hh_share_{k}"] = v[col] / (v[1] - v[2])
    w = acs(c, "b08301")
    z["pct_commute_drive"] = (w[3] + w[4]) / w[1]
    z["pct_commute_transit"] = w[10] / w[1]
    z["pct_work_from_home"] = w[21] / w[1]
    z["mean_commute_minutes"] = acs(c, "b08013")[1] / (w[1] - w[21])
    age = acs(c, "b01001")
    bands = pd.DataFrame({k: sum(age[m] + age[m + 24] for m in cols) for k, cols in AGE_BANDS.items()})
    bands["16_17"] *= 2 / 3  # ACS band is 15-17
    for k in AGE_BANDS:
        z[f"age_share_{k}"] = bands[k] / bands.sum(axis=1)
    race = acs(c, "b03002")
    for k, col in {"white_nh": 3, "black_nh": 4, "asian_nh": 6, "hispanic": 12}.items():
        z[f"pct_{k}"] = race[col] / race[1]

    z = z[(z.population >= MIN_POPULATION) & (z.households_with_vehicle >= MIN_HOUSEHOLDS_WITH_VEHICLE)].copy()
    # A few ZIPs have a suppressed median income; use the county median of ZIP medians.
    bad = ~(z.median_household_income > 0)
    z.loc[bad, "median_household_income"] = z[~bad].groupby("county").median_household_income.median()[z.county[bad]].values
    z["population_density_sqmi"] = z.population / z.land_sqmi
    z["distance_to_loop_miles"] = 69.0 * np.hypot(z.lat - LOOP[0], (z.lon - LOOP[1]) * np.cos(np.radians(LOOP[0])))
    z["is_chicago"] = z.index.str.startswith("606")
    z["region"] = np.where(z.is_chicago, "City of Chicago", np.where(z.county == "Cook", "Suburban Cook", z.county + " County"))
    z["city"] = z.city.where(~z.is_chicago, "Chicago").fillna("Unknown")

    # ---- observed city hazard ---------------------------------------------
    drv = pd.DataFrame(json.loads((c / "chi_drivers_by_home_zip.json").read_text()))
    drv = drv.assign(zip=drv.zipcode.astype(str).str[:5], n=drv.n.astype(int)).groupby("zip").n.sum()
    z["chicago_crash_drivers_2021_2025"] = drv.reindex(z.index).fillna(0).astype(int).where(z.is_chicago)

    pts = pd.read_csv(c / "chi_theft_points.csv")
    geo = json.loads((c / "chicago_zip_boundaries.geojson").read_text())
    thefts = pd.Series(0, index=z.index)
    for f in geo["features"]:
        zp = f["properties"]["zip"]
        if zp in thefts.index:
            thefts[zp] += int(shapely.contains_xy(shapely.geometry.shape(f["geometry"]), pts.longitude, pts.latitude).sum())
    z["chicago_vehicle_thefts_2021_2025"] = thefts.where(z.is_chicago)

    city = z[z.is_chicago]
    log_inc = np.log(z.median_household_income)
    for name, counts, k, damp, level in [
        ("crash", "chicago_crash_drivers_2021_2025", CRASH_CREDIBILITY_K, CRASH_DAMPING, SUBURB_CRASH_LEVEL),
        ("theft", "chicago_vehicle_thefts_2021_2025", THEFT_CREDIBILITY_K, THEFT_DAMPING, SUBURB_THEFT_LEVEL),
    ]:
        n = city[counts]
        city_rate = n.sum() / city.vehicles_available.sum() / YEARS
        cred = n / (n + k)
        rate = cred * (n / city.vehicles_available / YEARS) + (1 - cred) * city_rate
        z[f"{name}_rate_per_vehicle_year"] = rate.reindex(z.index)
        log_rel = np.log(rate / city_rate)
        slope, intercept = np.polyfit(log_inc[city.index], log_rel, 1, w=np.sqrt(city.vehicles_available))
        modelled = intercept + slope * log_inc + np.log(level)
        raw = log_rel.reindex(z.index).where(z.is_chicago, modelled)
        idx = np.exp(damp * raw)
        z[f"{name}_hazard_index"] = idx / wmean(idx, z.vehicles_available)
        print(f"{name}: city rate {city_rate:.4f}/vehicle-year, income slope {slope:.2f}, "
              f"index range {z[f'{name}_hazard_index'].min():.2f}-{z[f'{name}_hazard_index'].max():.2f}")
    z["hazard_basis"] = np.where(z.is_chicago, "observed", "modelled")

    z = z.drop(columns="is_chicago").sort_index()
    z.insert(0, "location_id", np.arange(1, len(z) + 1))
    num = z.select_dtypes("float").columns
    z[num] = z[num].round(5)
    args.out.mkdir(exist_ok=True)
    z.to_csv(args.out / "zip_reference.csv", lineterminator="\n")
    print(f"wrote {len(z)} ZIPs: {z.region.value_counts().to_dict()}")

    # ---- calendar indices ---------------------------------------------------
    cm = pd.DataFrame(json.loads((c / "chi_crashes_by_month.json").read_text())).astype(int)
    tm = pd.DataFrame(json.loads((c / "chi_theft_by_month.json").read_text())).astype(int)
    days = pd.Series({m: pd.Period(f"2023-{m:02d}").days_in_month for m in range(1, 13)})

    def seasonal(d: pd.DataFrame, month_col: str) -> pd.Series:
        per_day = d.groupby(month_col).n.sum() / days
        return per_day / per_day.mean()

    cal = pd.DataFrame({"month": range(1, 13)}).set_index("month")
    cal["crash_seasonality"] = seasonal(cm, "m")
    cal["theft_seasonality"] = seasonal(tm[tm.year >= 2021], "m")
    cal.round(4).to_csv(args.out / "month_seasonality.csv", lineterminator="\n")
    # Yearly theft index, 2021 = 1. The current year is partial, so every year is compared with
    # 2021 over the same complete months (the last, incomplete month is dropped).
    last_year = int(tm.year.max())
    complete = int(tm[tm.year == last_year].m.max()) - 1
    by_year = tm.groupby("year").n.sum()
    ytd = tm[tm.m <= complete].groupby("year").n.sum()
    yr = pd.DataFrame({"chicago_vehicle_thefts": by_year.loc[2021:]})
    yr["months_complete"] = np.where(yr.index == last_year, complete, 12)
    full, part = by_year / by_year.loc[2021], ytd / ytd.loc[2021]
    yr["theft_index_2021_base"] = full.loc[yr.index].where(yr.index != last_year, part.loc[yr.index]).round(4)
    yr["chicago_crashes"] = cm.groupby("y").n.sum()
    yr["hit_and_run_share"] = (cm.groupby("y").hit_and_run.sum() / cm.groupby("y").n.sum()).round(4)
    yr["injury_crash_share"] = (cm.groupby("y").injury.sum() / cm.groupby("y").n.sum()).round(4)
    yr.index.name = "year"
    yr.to_csv(args.out / "year_indices.csv", lineterminator="\n")
    print(cal.round(3).T.to_string()); print(yr.to_string())


if __name__ == "__main__":
    main()
