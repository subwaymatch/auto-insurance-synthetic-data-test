#!/usr/bin/env python3
"""Derive the catastrophe events (config.CAT_EVENTS) from NOAA's Storm Events Database.

    python scripts/build_catastrophe_events.py                 # download NOAA's yearly files, then print the list
    python scripts/build_catastrophe_events.py --cache DIR     # use files already downloaded to DIR

Source: NOAA National Centers for Environmental Information, Storm Events Database, "details" files
(https://www.ncei.noaa.gov/pub/data/swdi/stormevents/csvfiles/), public domain. Each row is a report of hail,
wind, a tornado or a flood in one county, with its place, size and NOAA's estimate of property damage.

A day in the seven counties is a catastrophe for this book when its reports reach one of these thresholds, set
to pick the storms that damage many parked and driven cars (the kind a catastrophe service designates):

* hail: at least HAIL_REPORTS reports of hail 1.75 inches (golf ball) or larger;
* flash flooding: at least FLOOD_DAMAGE of property damage reported in flood and flash-flood events;
* wind: a tornado outbreak (TORNADOES or more) or a derecho-scale day (WIND_REPORTS or more damaging-wind reports).

A day that qualifies on hail is a hail event even if it also brought wind or floods. Each event's footprint is the
median position of its reports and the 80th-percentile distance from it, kept within RADIUS miles for its peril.
How likely a car at the centre is to be hit (the peak) is ASSUMED, scaled by the event's severity within the
range the generator used before (hail 3% to 5%, flood 1% to 1.4%, wind 1% to 1.2%). Its hours (config.CAT_HOURS)
run from its first report to the time nine in ten of its reports had ended, on the local clock. Only the date,
hours, place, peril and relative size are real: the claims and losses are simulated. NOAA publishes with a lag of a few months, so
the latest events may be missing until the list is rebuilt.

The script prints the list to paste into autoins/config.py; it writes nothing.
"""
from __future__ import annotations

import argparse
import re
import sys
import urllib.request
from pathlib import Path

import numpy as np
import pandas as pd

URL = "https://www.ncei.noaa.gov/pub/data/swdi/stormevents/csvfiles/"
COUNTIES = {"COOK", "DUPAGE", "DU PAGE", "LAKE", "WILL", "KANE", "MCHENRY", "KENDALL"}
YEARS = range(2021, 2027)
HAIL_REPORTS, BIG_HAIL = 5, 1.75
FLOOD_DAMAGE = 100e6
TORNADOES, WIND_REPORTS = 20, 100
RADIUS = {"HAIL_CAT": (6, 20), "FLOOD_CAT": (6, 10), "WIND_CAT": (6, 30)}
DEFAULT_CACHE = Path(__file__).resolve().parent.parent / "reference" / "_cache" / "noaa"


def download(cache: Path) -> None:
    cache.mkdir(parents=True, exist_ok=True)
    index = urllib.request.urlopen(URL, timeout=60).read().decode()
    for y in YEARS:
        names = sorted(set(re.findall(rf"StormEvents_details-ftp_v1\.0_d{y}_c\d+\.csv\.gz", index)))
        if names and not (cache / names[-1]).exists():
            urllib.request.urlretrieve(URL + names[-1], cache / names[-1])


def money(x) -> float:
    if not isinstance(x, str) or not x:
        return 0.0
    scale = {"K": 1e3, "M": 1e6, "B": 1e9}.get(x[-1].upper(), 1.0)
    try:
        return float(x[:-1] if x[-1].isalpha() else x) * scale
    except ValueError:
        return 0.0


def load(cache: Path) -> pd.DataFrame:
    cols = ["BEGIN_YEARMONTH", "BEGIN_DAY", "BEGIN_TIME", "END_YEARMONTH", "END_DAY", "END_TIME", "STATE", "CZ_NAME",
            "EVENT_TYPE", "MAGNITUDE", "DAMAGE_PROPERTY", "BEGIN_LAT", "BEGIN_LON"]
    files = [sorted(cache.glob(f"StormEvents_details-ftp_v1.0_d{y}_c*.csv.gz"))[-1:] for y in YEARS]
    d = pd.concat([pd.read_csv(f, usecols=cols, low_memory=False) for fs in files for f in fs], ignore_index=True)
    d = d[(d.STATE == "ILLINOIS") & d.CZ_NAME.str.upper().isin(COUNTIES)].copy()
    ym = d.BEGIN_YEARMONTH.astype(str)
    d["date"] = ym.str[:4] + "-" + ym.str[4:] + "-" + d.BEGIN_DAY.astype(str).str.zfill(2)
    d["damage"] = d.DAMAGE_PROPERTY.map(money)
    # report times are in Central Standard Time (CST-6) all year: on the local clock, an hour later in summer
    local = lambda ym, day, t: (pd.to_datetime(ym.astype(str) + day.astype(str).str.zfill(2) + t.astype(str).str.zfill(4),
                                               format="%Y%m%d%H%M") + pd.Timedelta(hours=6)).dt.tz_localize("UTC") \
        .dt.tz_convert("America/Chicago")
    begin, end = local(d.BEGIN_YEARMONTH, d.BEGIN_DAY, d.BEGIN_TIME), local(d.END_YEARMONTH, d.END_DAY, d.END_TIME)
    d["begin_hour"] = begin.dt.hour + begin.dt.minute / 60
    d["end_hour"] = (end.dt.tz_localize(None).dt.normalize() - begin.dt.tz_localize(None).dt.normalize()).dt.days * 24 \
        + end.dt.hour + end.dt.minute / 60
    return d


def events(d: pd.DataFrame) -> list[tuple]:
    out = []
    for date, x in d.groupby("date"):
        hail = x[(x.EVENT_TYPE == "Hail") & (x.MAGNITUDE >= BIG_HAIL)]
        flood = x[x.EVENT_TYPE.isin(["Flash Flood", "Flood"])]
        tornado, wind = x[x.EVENT_TYPE == "Tornado"], x[x.EVENT_TYPE == "Thunderstorm Wind"]
        if len(hail) >= HAIL_REPORTS:
            peril, r = "HAIL_CAT", x[x.EVENT_TYPE == "Hail"]
            peak = 0.030 + 0.001 * min(len(hail), 20)
        elif flood.damage.sum() >= FLOOD_DAMAGE:
            peril, r = "FLOOD_CAT", flood
            peak = 0.010 + 0.004 * min(flood.damage.sum() / 500e6, 1.0)
        elif len(tornado) >= TORNADOES or len(wind) >= WIND_REPORTS:
            peril, r = "WIND_CAT", pd.concat([tornado, wind])
            peak = 0.010 + 0.002 * (len(tornado) >= TORNADOES)
        else:
            continue
        r = r.dropna(subset=["BEGIN_LAT"])
        lat, lon = r.BEGIN_LAT.median(), r.BEGIN_LON.median()
        dist = 69 * np.hypot(r.BEGIN_LAT - lat, (r.BEGIN_LON - lon) * 0.745)
        radius = float(np.clip(np.percentile(dist, 80), *RADIUS[peril]))
        counties = ", ".join(r.CZ_NAME.str.title().str.replace("Du Page", "DuPage").value_counts().index[:4])
        storm = x[x.EVENT_TYPE.isin(["Hail", "Thunderstorm Wind", "Tornado", "Flash Flood", "Flood"])]
        hours = (np.floor(storm.begin_hour.min() * 4) / 4, min(np.ceil(storm.end_hour.quantile(0.9) * 4) / 4, 24.0))
        out.append((date, peril, round(lat, 2), round(lon, 2), round(radius, 1), round(peak, 4), len(hail), len(tornado),
                    len(wind), flood.damage.sum() / 1e6, counties, hours))
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--cache", type=Path, default=DEFAULT_CACHE)
    a = ap.parse_args()
    if not any(a.cache.glob("StormEvents_details-*.csv.gz")):
        download(a.cache)
    ev = events(load(a.cache))
    print(f"{'date':12s}{'peril':11s}{'lat':>7s}{'lon':>8s}{'radius':>8s}{'peak':>8s}{'big hail':>10s}{'tornadoes':>11s}"
          f"{'wind':>6s}{'flood $M':>10s}{'hours':>14s}  counties")
    for e in ev:
        print(f"{e[0]:12s}{e[1]:11s}{e[2]:7.2f}{e[3]:8.2f}{e[4]:8.1f}{e[5]:8.4f}{e[6]:10d}{e[7]:11d}{e[8]:6d}{e[9]:10.1f}"
              f"{e[11][0]:7.2f}-{e[11][1]:5.2f}  {e[10]}")
    print(f"\n{len(ev)} events; by year {pd.Series([e[0][:4] for e in ev]).value_counts().sort_index().to_dict()}", file=sys.stderr)


if __name__ == "__main__":
    main()
