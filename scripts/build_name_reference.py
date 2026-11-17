"""Build reference/surnames.csv and reference/first_names.csv from public name statistics.

Drivers' surnames are drawn conditional on a synthetic race/ethnicity group, and first
names on that group, sex and birth decade. The five groups match the ZIP shares in
reference/zip_reference.csv:

  white     non-Hispanic white
  black     non-Hispanic Black or African American
  hispanic  Hispanic or Latino (any race)
  asian     non-Hispanic Asian or Pacific Islander
  other     non-Hispanic American Indian/Alaska Native, or two or more races

This script only builds the name tables; the group is meant to be used for nothing but
choosing names. Like fetch_public_data.py, raw downloads are cached in reference/_cache
(ignored by git) and reused, so only a rebuild needs the network; the build itself is
deterministic. Reading the Tzioumis workbook needs openpyxl.

Sources
-------
1. Surnames: US Census Bureau, "Frequently Occurring Surnames from the 2010 Census",
   https://www2.census.gov/topics/genealogy/2010surnames/names.zip
   (documentation: https://www2.census.gov/topics/genealogy/2010surnames/surnames.pdf).
   The 162,253 surnames held by 100 or more people, with count and percent by six
   race/Hispanic-origin categories; "(S)" marks a suppressed percent. US government work,
   public domain; the Census Bureau asks to be credited as the source.
2. First names by sex and year of birth: Social Security Administration, national
   baby-name data, https://www.ssa.gov/oact/babynames/names.zip (yobYYYY.txt:
   name,sex,count; every name with at least 5 births of that sex in the year, from
   Social Security card applications). US government work, public domain.
   ssa.gov refuses some automated or cloud clients (HTTP 403); if so, download the file
   in a browser, save it as <cache>/ssa_names.zip and run this script again.
3. Race/ethnicity of first names: Tzioumis, K. (2018), "Demographic aspects of first
   names", Scientific Data 5, 180025, https://doi.org/10.1038/sdata.2018.25. Data:
   Tzioumis, Konstantinos, 2018, "Data for: Demographic aspects of first names",
   https://doi.org/10.7910/DVN/TYJKEZ, Harvard Dataverse, V1. Licence CC0 1.0 (the
   Dataverse community norms ask users to cite the data). 4,250 first names of 2.66
   million mortgage applicants (three mortgage datasets; race and Hispanic origin
   self-reported as on HMDA loan application registers), with percent by the same six
   categories as the Census surname file. The file is found through the Dataverse API
   and downloaded in its original format (firstnames.xlsx, sheet "Data").

Method
------
surnames.csv (surname, count, white, black, hispanic, asian, other):
  A suppressed percent gets an even split of the leftover share (100 minus the published
  percents of that surname). Each group column is count x percent, the estimated number of
  people in that group with the surname, rounded to whole people; "other" adds the
  American Indian/Alaska Native and two-or-more-races columns. A surname is kept if it is
  held by at least SURNAME_MIN_SHARE of some group's 2010 population, which keeps rare
  names while balancing coverage across groups. Names are put in proper case
  (SMITH -> Smith, MCDONALD -> McDonald, each part of a hyphenated or spaced name). The
  source has no punctuation, so O'Brien appears as Obrien and no apostrophes are added.

first_names.csv (sex, birth_decade, first_name, white, black, hispanic, asian, other):
  By Bayes' rule,
      weight(name | sex, decade, group)  proportional to  births(name, sex, decade) x P(group | name),
  with births from SSA summed over the ten years of the decade (decade 2010 = 2010-2019)
  and P(group | name) from Tzioumis, re-based from the mortgage applicants' group mix to the
  population's (the Census 2010 totals of the surname file): each name's shares are multiplied by
  population share / applicant share for each group and renormalised. Without this, names shared
  across groups would be under-weighted within the groups that are rare among applicants, and
  distinctive names over-weighted. A name missing from the Tzioumis list gets the population's
  group mix. The file's "ALL OTHER
  FIRST NAMES" row is not used for them: it describes names that were rare among adult
  mortgage applicants (28% Asian) and would mislabel names that only became common in
  recent decades. Within each sex and decade a name is kept if it is among the top
  FIRST_NAME_TOP (--first-name-top) names of some group; weights are then renormalised to sum to 1 within
  (sex, birth_decade, group).

Caveats
-------
* Tzioumis' shares describe adult mortgage applicants (82% white, 4% Black, 7% Hispanic,
  6% Asian/Pacific Islander), not each birth cohort, and are not split by sex or birth
  year. The re-basing above corrects the overall mix to the 2010 population, not to each birth
  cohort (younger cohorts are more Hispanic and Asian). Names that became common only recently
  may be missing from the list and get the population mix (the script prints the share of
  births whose name is listed).
* The Census file stores surnames without punctuation and cut to 15 letters.
* Both name sources combine Asian with Pacific Islander; the ZIP "asian" share is Asian
  alone, and its residual share also includes "some other race".
* With --race-independent-first-names (for when Dataverse cannot be reached) every group
  column of first_names.csv equals the SSA name frequency.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import time
import urllib.error
import urllib.request
import zipfile
from pathlib import Path

import numpy as np
import pandas as pd

CENSUS_SURNAMES_URL = "https://www2.census.gov/topics/genealogy/2010surnames/names.zip"
SSA_NAMES_URL = "https://www.ssa.gov/oact/babynames/names.zip"
DATAVERSE_API = "https://dataverse.harvard.edu/api"
TZIOUMIS_DOI = "doi:10.7910/DVN/TYJKEZ"

GROUPS = ["white", "black", "hispanic", "asian", "other"]
# Source percent columns (Census and Tzioumis use the same names) behind each group.
GROUP_SOURCES = {"white": ["pctwhite"], "black": ["pctblack"], "hispanic": ["pcthispanic"],
                 "asian": ["pctapi"], "other": ["pctaian", "pct2prace"]}
SOURCE_PCTS = [c for cols in GROUP_SOURCES.values() for c in cols]

SURNAME_MIN_SHARE = 2.5e-6     # keep a surname held by >= 2.5 per million of some group
FIRST_NAME_TOP = 500           # keep a first name in the top 500 of some group (per sex, decade)
DECADES = list(range(1920, 2020, 10))
SHOW_DECADE = 1980             # decade used for the printed first-name check


class Unavailable(RuntimeError):
    """A source could not be downloaded."""


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
        except urllib.error.HTTPError as e:
            if 400 <= e.code < 500 and e.code not in (408, 429):  # refused: retrying will not help
                raise Unavailable(f"{url}: HTTP {e.code} {e.reason}") from e
            wait = 3 * 2 ** attempt
            print(f"retry    {dest.name}: {e} (waiting {wait}s)")
            time.sleep(wait)
        except Exception as e:  # noqa: BLE001 - retry any transient failure
            wait = 3 * 2 ** attempt
            print(f"retry    {dest.name}: {e} (waiting {wait}s)")
            time.sleep(wait)
    raise Unavailable(f"could not download {url}")


def get_tzioumis(cache: Path, dest: Path) -> None:
    """Find the first-name workbook in the Dataverse dataset and download its original file."""
    if dest.exists() and dest.stat().st_size > 0:
        print(f"cached   {dest.name}")
        return
    meta = cache / "tzioumis_dataset.json"
    get(f"{DATAVERSE_API}/datasets/:persistentId/?persistentId={TZIOUMIS_DOI}", meta)
    files = json.loads(meta.read_text())["data"]["latestVersion"]["files"]
    ids = [f["dataFile"]["id"] for f in files if (f["dataFile"].get("originalFileName")
                                                    or f["dataFile"]["filename"]).lower().startswith("firstnames")]
    if len(ids) != 1:
        raise Unavailable(f"expected one firstnames file in {TZIOUMIS_DOI}, found {len(ids)}")
    get(f"{DATAVERSE_API}/access/datafile/{ids[0]}?format=original", dest)


# ---- surnames ---------------------------------------------------------------

def proper_case(name: str) -> str:
    parts = []
    for p in re.split(r"([- ])", name):
        p = p.capitalize()
        if len(p) > 2 and p.startswith("Mc"):
            p = "Mc" + p[2:].capitalize()
        parts.append(p)
    return "".join(parts)


def fill_suppressed(pct: pd.DataFrame) -> pd.DataFrame:
    """Percent columns with '(S)' replaced by an even split of the leftover share; rows sum to 1."""
    v = pct.replace("(S)", np.nan).astype(float)
    suppressed = v.isna()
    leftover = (100 - v.sum(axis=1)).clip(lower=0) / suppressed.sum(axis=1).replace(0, np.nan)
    v = v.mask(suppressed, pd.DataFrame({c: leftover for c in v.columns}))
    return v.div(v.sum(axis=1), axis=0)


def group_shares(pct: pd.DataFrame) -> pd.DataFrame:
    return pd.DataFrame({g: pct[cols].sum(axis=1) for g, cols in GROUP_SOURCES.items()})


def build_surnames(path: Path) -> tuple[pd.DataFrame, pd.DataFrame]:
    with zipfile.ZipFile(path) as z, z.open("Names_2010Census.csv") as f:
        d = pd.read_csv(f, dtype=str, keep_default_na=False)
    count = d["count"].astype("int64")
    people = group_shares(fill_suppressed(d[SOURCE_PCTS])).mul(count, axis=0)
    total = people.sum()                         # includes the "ALL OTHER NAMES" row
    named = d["name"] != "ALL OTHER NAMES"
    keep = named & (people / total >= SURNAME_MIN_SHARE).any(axis=1)

    out = pd.DataFrame({"surname": d.loc[keep, "name"].map(proper_case), "count": count[keep]})
    out = out.join(people[keep].round().astype("int64")).reset_index(drop=True)
    if out["surname"].duplicated().any():
        raise ValueError("duplicate surnames after proper-casing")
    coverage = pd.DataFrame({"population_2010": total.round().astype("int64"),
                             "all_listed_surnames": people[named].sum() / total,
                             "kept_surnames": people[keep].sum() / total})
    return out, coverage


# ---- first names ------------------------------------------------------------

def load_ssa(path: Path) -> pd.DataFrame:
    frames = []
    with zipfile.ZipFile(path) as z:
        members = set(z.namelist())
        for year in range(DECADES[0], DECADES[-1] + 10):
            name = f"yob{year}.txt"
            if name not in members:
                if year <= DECADES[-1]:
                    raise ValueError(f"{path.name} has no {name}")
                continue  # the latest decade may be incomplete
            with z.open(name) as f:
                d = pd.read_csv(f, header=None, names=["first_name", "sex", "count"],
                                dtype={"first_name": str, "sex": str, "count": "int64"}, keep_default_na=False)
            frames.append(d.assign(birth_decade=year // 10 * 10))
    ssa = pd.concat(frames, ignore_index=True)
    if not set(ssa["sex"]) <= {"M", "F"}:
        raise ValueError(f"unexpected sex codes {set(ssa['sex'])}")
    return ssa.groupby(["sex", "birth_decade", "first_name"], as_index=False)["count"].sum()


def load_tzioumis(path: Path) -> tuple[pd.DataFrame, pd.Series]:
    """P(group | name) for each listed name (upper case), and the overall mix of the listed names."""
    d = pd.read_excel(path, sheet_name="Data", keep_default_na=False)
    missing = {"firstname", "obs", *SOURCE_PCTS} - set(d.columns)
    if missing:
        raise ValueError(f"Tzioumis file lacks columns {missing}")
    d = d[d["firstname"] != "ALL OTHER FIRST NAMES"]
    p = group_shares(d[SOURCE_PCTS].astype(float))
    p = p.div(p.sum(axis=1), axis=0)
    p.index = d["firstname"].astype(str).str.upper()
    overall = p.mul(d["obs"].to_numpy(), axis=0).sum() / d["obs"].sum()
    return p, overall


def build_first_names(ssa: pd.DataFrame, p_group: pd.DataFrame | None, overall: pd.Series | None,
                      top: int, population: pd.Series | None = None) -> tuple[pd.DataFrame, pd.DataFrame, pd.Series]:
    """population: each group's share of the population, to re-base the applicants' P(group | name) to."""
    if p_group is None:  # race-independent fallback
        p = np.ones((len(ssa), len(GROUPS)))
        matched = np.zeros(len(ssa), dtype=bool)
    else:
        p = p_group.reindex(ssa["first_name"].str.upper())[GROUPS].to_numpy(dtype=float, copy=True)
        matched = ~np.isnan(p[:, 0])
        p[~matched] = overall[GROUPS].to_numpy()
        if population is not None:
            p = p * (population[GROUPS] / overall[GROUPS]).to_numpy()
            p = p / p.sum(axis=1, keepdims=True)
    w = pd.DataFrame(p * ssa["count"].to_numpy()[:, None], columns=GROUPS, index=ssa.index)
    cell = [ssa["sex"], ssa["birth_decade"]]
    full = w / w.groupby(cell).transform("sum")
    keep = (w.groupby(cell).rank(ascending=False, method="first") <= top).any(axis=1)

    kept_cell = [ssa.loc[keep, "sex"], ssa.loc[keep, "birth_decade"]]
    coverage = full[keep].groupby(kept_cell).sum()
    births = ssa["count"]
    matched_share = births[matched].groupby([ssa.loc[matched, "sex"], ssa.loc[matched, "birth_decade"]]).sum() \
        .reindex(births.groupby(cell).sum().index, fill_value=0) / births.groupby(cell).sum()

    out = ssa.loc[keep, ["sex", "birth_decade", "first_name", "count"]].join(
        full[keep] / full[keep].groupby(kept_cell).transform("sum"))
    out = out.sort_values(["sex", "birth_decade", "count", "first_name"], ascending=[True, True, False, True])
    return out.drop(columns="count").reset_index(drop=True), coverage, matched_share


# ---- main -------------------------------------------------------------------

def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--cache", type=Path, default=Path("reference/_cache"))
    ap.add_argument("--out", type=Path, default=Path("reference"))
    ap.add_argument("--race-independent-first-names", action="store_true",
                    help="build first_names.csv from SSA alone (every group column the same); "
                         "only for when the Tzioumis data cannot be downloaded")
    ap.add_argument("--first-name-top", type=int, default=FIRST_NAME_TOP,
                    help="keep a first name if it is in the top N of some group, per sex and decade "
                         f"(default {FIRST_NAME_TOP}); lower it if first_names.csv is too large")
    args = ap.parse_args()
    cache, out_dir = args.cache, args.out
    cache.mkdir(parents=True, exist_ok=True)
    pd.set_option("display.width", 160)

    failed: list[str] = []

    def fetch(label: str, fn, *a) -> bool:
        try:
            fn(*a)
            return True
        except Unavailable as e:
            print(f"FAILED   {label}: {e}")
            failed.append(label)
            return False

    census_zip, ssa_zip = cache / "census_surnames_2010.zip", cache / "ssa_names.zip"
    tz_xlsx = cache / "tzioumis_firstnames.xlsx"
    have_census = fetch("Census 2010 surnames", get, CENSUS_SURNAMES_URL, census_zip)
    have_ssa = fetch("SSA baby names", get, SSA_NAMES_URL, ssa_zip)
    have_tz = args.race_independent_first_names or fetch("Tzioumis first names", get_tzioumis, cache, tz_xlsx)

    if have_census:
        surnames, cov = build_surnames(census_zip)
        dest = out_dir / "surnames.csv"
        surnames.to_csv(dest, index=False, lineterminator="\n")
        print(f"\nwrote {dest}: {len(surnames):,} rows, {dest.stat().st_size / 1e6:.2f} MB")
        print("share of each group's 2010 population whose surname is in the file "
              "(all_listed_surnames = every surname with 100+ people):")
        print(cov.round(3).to_string())
        print("top 10 surnames by group:")
        for g in GROUPS:
            print(f"  {g:9s}", ", ".join(surnames.nlargest(10, g)["surname"]))

    if not have_ssa:
        print(f"\nfirst_names.csv NOT built: download {SSA_NAMES_URL} in a browser, save it as "
              f"{ssa_zip} and run this script again.")
    elif not have_tz:
        print("\nfirst_names.csv NOT built: the Tzioumis data could not be downloaded. Run again later, or "
              "pass --race-independent-first-names to build first names from SSA alone.")
    else:
        if args.race_independent_first_names:
            print("\nWARNING: --race-independent-first-names: every group gets the same first-name distribution")
            p_group = overall = None
        else:
            p_group, overall = load_tzioumis(tz_xlsx)
            print(f"\nTzioumis: {len(p_group):,} names; overall mix used for unlisted names: "
                  + ", ".join(f"{g} {overall[g]:.3f}" for g in GROUPS))
        population = None
        if p_group is not None and have_census:
            totals = build_surnames(census_zip)[1]["population_2010"].astype(float)
            population = totals / totals.sum()
            print("re-based to the 2010 population mix: " + ", ".join(f"{g} {population[g]:.3f}" for g in GROUPS))
        first, cov, matched = build_first_names(load_ssa(ssa_zip), p_group, overall, args.first_name_top, population)
        dest = out_dir / "first_names.csv"
        first.to_csv(dest, index=False, float_format="%.5g", lineterminator="\n")
        print(f"wrote {dest}: {len(first):,} rows, {dest.stat().st_size / 1e6:.2f} MB")
        if dest.stat().st_size > 3e6:
            print("WARNING: first_names.csv is over 3 MB; consider a smaller --first-name-top")
        print("names kept per (sex, birth_decade):")
        print(first.groupby(["sex", "birth_decade"]).size().unstack("birth_decade").to_string())
        print("share of SSA births whose name is in the Tzioumis list:")
        print(matched.unstack("birth_decade").round(3).to_string())
        print("coverage: share of each (sex, decade, group) weight held by the kept names:")
        print(cov.round(3).to_string())
        print(f"coverage min {cov.min().min():.3f}, median {np.median(cov.to_numpy()):.3f}")
        for sex in ["F", "M"]:
            cell = first[(first["sex"] == sex) & (first["birth_decade"] == SHOW_DECADE)]
            print(f"top 10 first names, sex {sex}, born {SHOW_DECADE}s:")
            for g in GROUPS:
                print(f"  {g:9s}", ", ".join(cell.nlargest(10, g)["first_name"]))

    if failed:
        print(f"\nfailed sources: {', '.join(failed)}")
        sys.exit(1)
    print("done")


if __name__ == "__main__":
    main()
