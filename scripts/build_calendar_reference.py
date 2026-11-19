#!/usr/bin/env python3
"""Build the calendar reference files from City of Chicago daily crash and vehicle-theft counts.

    python scripts/fetch_public_data.py --only calendar
    python scripts/build_calendar_reference.py

Writes two small files the generator reads, so the simulated calendar has real days in it:

  reference/daily_index.csv   one row per day: that day's count of crashes, and of vehicle thefts, relative to
                              the average day of its month. Weekends, holidays, snow days and quiet days are
                              all in it. Monthly seasonality and the year-to-year trend stay where they were
                              (reference/month_seasonality.csv, reference/year_indices.csv): dividing by the
                              month's average takes them out of this file.
  reference/hour_of_day.csv   share of crashes, and of vehicle thefts, by hour for each day of the week
                              (0 = Monday), used for the time of day of a loss.

The last days of each download are dropped: reports for them are still arriving.
"""
from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd

INCOMPLETE_DAYS = 21          # police reports are filed for some weeks after the event


def daily(path: Path) -> pd.Series:
    d = pd.read_csv(path)
    s = pd.Series(d["n"].to_numpy(), index=pd.to_datetime(d["day"]).dt.normalize())
    s = s.reindex(pd.date_range(s.index.min(), s.index.max()), fill_value=0)
    s = s.iloc[:-INCOMPLETE_DAYS]
    whole = s.groupby(s.index.to_period("M")).transform("size") == s.index.days_in_month     # whole months only
    s = s[whole]
    return (s / s.groupby(s.index.to_period("M")).transform("mean")).round(4)


def hourly(path: Path, day_col: str, sunday: int) -> pd.DataFrame:
    """Share by hour within each weekday. `sunday` is the source's code for Sunday (the next six follow)."""
    d = pd.read_csv(path).rename(columns={day_col: "d", "crash_hour": "hour"})
    d["weekday"] = (d["d"] - sunday + 6) % 7                 # 0 = Monday
    d["share"] = (d["n"] / d.groupby("weekday")["n"].transform("sum")).round(5)
    return d[["weekday", "hour", "share"]].sort_values(["weekday", "hour"])


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--cache", type=Path, default=Path("reference/_cache"))
    ap.add_argument("--out", type=Path, default=Path("reference"))
    a = ap.parse_args()
    idx = pd.DataFrame({"crash_index": daily(a.cache / "chi_crashes_by_day.csv"),
                        "theft_index": daily(a.cache / "chi_theft_by_day.csv")}).dropna()
    idx.index.name = "date"
    idx.to_csv(a.out / "daily_index.csv", lineterminator="\n", date_format="%Y-%m-%d")
    hours = pd.concat([hourly(a.cache / "chi_crashes_by_weekday_hour.csv", "crash_day_of_week", 1).assign(group="crash"),
                       hourly(a.cache / "chi_theft_by_weekday_hour.csv", "dow", 0).assign(group="theft")])
    hours[["group", "weekday", "hour", "share"]].to_csv(a.out / "hour_of_day.csv", index=False, lineterminator="\n")
    wd = idx.groupby(idx.index.dayofweek).mean().round(3)
    print(f"daily_index.csv: {len(idx):,} days, {idx.index.min().date()} to {idx.index.max().date()}")
    print("average index by weekday (0 = Monday):\n" + wd.to_string())
    print(f"crash index: 1st percentile {idx.crash_index.quantile(.01):.2f}, 99th {idx.crash_index.quantile(.99):.2f}, "
          f"highest {idx.crash_index.max():.2f} on {idx.crash_index.idxmax().date()}")


if __name__ == "__main__":
    main()
