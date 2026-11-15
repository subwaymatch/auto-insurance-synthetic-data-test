"""Reference data and the simulation calendar."""
from __future__ import annotations

import zlib
from dataclasses import dataclass, field
from statistics import NormalDist

import numpy as np
import pandas as pd

from . import config as C


def stream(seed: int, name: str) -> np.random.Generator:
    """An independent, named random stream. The same (seed, name) always gives the same numbers,
    so changing one part of the generator does not reshuffle the others."""
    return np.random.default_rng([seed, zlib.crc32(name.encode())])


def normal_grid(k: int) -> np.ndarray:
    """k standard-normal quantile midpoints, used for deterministic expected-value integration."""
    nd = NormalDist()
    return np.array([nd.inv_cdf((i + 0.5) / k) for i in range(k)])


@dataclass
class Calendar:
    """Day 0 is the start date. Arrays are indexed by day number."""
    start: np.datetime64
    valuation_day: int                 # last day known to the extract
    horizon: int                       # valuation_day + 1
    year: np.ndarray = field(repr=False, default=None)
    month: np.ndarray = field(repr=False, default=None)
    cum: dict = field(repr=False, default_factory=dict)        # cumulative frequency intensity by group
    sev_trend: dict = field(repr=False, default_factory=dict)  # daily severity index by coverage group
    used_car: np.ndarray = field(repr=False, default=None)
    rate_level: np.ndarray = field(repr=False, default=None)

    def date(self, day) -> np.ndarray:
        return self.start + np.asarray(day).astype("timedelta64[D]")

    def day_of(self, months, dom) -> np.ndarray:
        """Day number of (start month + months, day-of-month dom). Day numbers before the start are negative.

        dom is the policy's anniversary day. In a month too short for it the date falls on the month's
        last day, and the next anniversary returns to dom: a policy written on 31 August with six-month
        terms renews on 28 (or 29) February and again on 31 August, so anniversaries never drift."""
        m = self.start.astype("M8[M]") + np.asarray(months).astype("timedelta64[M]")
        first = m.astype("M8[D]")
        d = np.minimum(np.asarray(dom), self.days_in_month(months))
        return ((first + (d - 1).astype("timedelta64[D]")) - self.start).astype(int)

    def days_in_month(self, months) -> np.ndarray:
        """Number of days in the month (start month + months)."""
        m = self.start.astype("M8[M]") + np.asarray(months).astype("timedelta64[M]")
        return ((m + np.timedelta64(1, "M")).astype("M8[D]") - m.astype("M8[D]")).astype(int)

    def rate_level_at(self, day) -> np.ndarray:
        """Filed rate level for policies effective on `day` (days before the start use the opening level)."""
        return self.rate_level[np.clip(np.asarray(day), 0, len(self.rate_level) - 1)]

    def year_frac(self, day) -> np.ndarray:
        return self.start.astype("M8[Y]").astype(int) + 1970 + np.asarray(day) / 365.25

    def exposure(self, group: str, s, x) -> np.ndarray:
        """Intensity-weighted years of exposure between day s (inclusive) and day x (exclusive)."""
        c = self.cum[group]
        return c[np.clip(x, 0, self.horizon)] - c[np.clip(s, 0, self.horizon)]

    def sample_days(self, group: str, s, x, rng) -> np.ndarray:
        c = self.cum[group]
        lo, hi = c[np.clip(s, 0, self.horizon)], c[np.clip(x, 0, self.horizon)]
        u = lo + rng.random(len(lo)) * (hi - lo)
        return np.clip(np.searchsorted(c, u, side="right") - 1, s, np.maximum(x - 1, s))


def _midyear_interp(cal: Calendar, table: dict[int, float], days: np.ndarray) -> np.ndarray:
    yrs = sorted(table)
    anchors = [(np.datetime64(f"{y}-07-01") - cal.start).astype(int) for y in yrs]
    return np.interp(days, anchors, [table[y] for y in yrs])


@dataclass
class Reference:
    zips: pd.DataFrame
    models: pd.DataFrame
    first_m: np.ndarray
    first_f: np.ndarray
    last: np.ndarray
    cal: Calendar


def load(cfg: C.Config) -> Reference:
    zips = pd.read_csv(C.REFERENCE_DIR / "zip_reference.csv", dtype={"zip": str})
    models = pd.read_csv(C.REFERENCE_DIR / "vehicle_models.csv")
    names = pd.read_csv(C.REFERENCE_DIR / "names.csv", keep_default_na=False)
    season = pd.read_csv(C.REFERENCE_DIR / "month_seasonality.csv").set_index("month")
    yearly = pd.read_csv(C.REFERENCE_DIR / "year_indices.csv").set_index("year")

    start = np.datetime64(cfg.start)
    vday = int((np.datetime64(cfg.valuation) - start).astype(int))
    cal = Calendar(start=start, valuation_day=vday, horizon=vday + 1)
    days = np.arange(cal.horizon)
    dates = cal.date(days)
    cal.year = dates.astype("M8[Y]").astype(int) + 1970
    cal.month = dates.astype("M8[M]").astype(int) % 12 + 1
    mi = cal.month - 1

    theft_year = dict(zip(yearly.index, yearly.theft_index_2021_base ** C.THEFT_YEAR_DAMPING))
    crash = season.crash_seasonality.to_numpy()[mi] * C.year_series(C.FREQ_TREND_CRASH, cal.year)
    theft = season.theft_seasonality.to_numpy()[mi] * C.year_series(theft_year, cal.year)
    daily = {
        "crash": crash,
        "theft": theft,
        "theft_kh": theft * C.year_series(C.KIA_HYUNDAI_THEFT, cal.year),
        "animal": np.array(C.ANIMAL_SEASONALITY)[mi],
        "weather": np.array(C.WEATHER_SEASONALITY)[mi],
        "glass": np.array(C.GLASS_SEASONALITY)[mi],
        "flat": np.ones(cal.horizon),
    }
    cal.cum = {g: np.concatenate([[0.0], np.cumsum(d)]) / 365.25 for g, d in daily.items()}
    alldays = np.arange(cal.horizon + 1)
    cal.sev_trend = {k: _midyear_interp(cal, t, alldays) for k, t in C.SEVERITY_TREND.items()}
    cal.used_car = _midyear_interp(cal, C.USED_CAR_VALUE_INDEX, alldays)
    level = np.ones(cal.horizon + 400)
    for d, chg in C.RATE_CHANGES:
        level[max((np.datetime64(d) - start).astype(int), 0):] *= 1 + chg
    cal.rate_level = level

    return Reference(
        zips=zips, models=models,
        first_m=names.name[names.kind == "M"].to_numpy(), first_f=names.name[names.kind == "F"].to_numpy(),
        last=names.name[names.kind == "L"].to_numpy(), cal=cal,
    )
