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


def _nth_weekday(year: int, month: int, weekday: int, n: int) -> np.datetime64:
    """The n-th (or, for n = -1, the last) given weekday (0 = Monday) of a month."""
    first = np.datetime64(f"{year}-{month:02d}-01")
    if n > 0:
        return first + ((weekday - (first.astype(int) + 3) % 7) % 7 + 7 * (n - 1)).astype("timedelta64[D]")
    last = (np.datetime64(f"{year + (month == 12)}-{month % 12 + 1:02d}-01") - np.timedelta64(1, "D"))
    return last - (((last.astype(int) + 3) % 7 - weekday) % 7).astype("timedelta64[D]")


def holidays(first_year: int = 1980, last_year: int = 2040) -> np.ndarray:
    """US federal holidays as observed (a Saturday holiday on the Friday, a Sunday one on the Monday), plus the
    day after Thanksgiving. Banks and courts are closed on them, and so, in this dataset, are the company's
    offices: a business day is a weekday that is not one of these."""
    out = []
    for y in range(first_year, last_year + 1):
        fixed = [f"{y}-01-01", f"{y}-07-04", f"{y}-11-11", f"{y}-12-25"] + ([f"{y}-06-19"] if y >= 2021 else [])
        for d in map(np.datetime64, fixed):
            wd = (d.astype(int) + 3) % 7
            out.append(d - np.timedelta64(1, "D") if wd == 5 else d + np.timedelta64(1, "D") if wd == 6 else d)
        thanksgiving = _nth_weekday(y, 11, 3, 4)
        out += [_nth_weekday(y, 1, 0, 3), _nth_weekday(y, 2, 0, 3), _nth_weekday(y, 5, 0, -1), _nth_weekday(y, 9, 0, 1),
                _nth_weekday(y, 10, 0, 2), thanksgiving, thanksgiving + np.timedelta64(1, "D")]
    return np.unique(np.array(out, dtype="M8[D]"))


HOLIDAYS = holidays()


def day_weight(cal: "Calendar", day, w) -> np.ndarray:
    """Weight of each day given w = (..., 3) weights for a weekday, a Saturday, and a Sunday or holiday."""
    wd, hol = cal.weekday(day), cal.is_holiday(day)
    w = np.asarray(w, dtype=float)
    return np.where(hol | (wd == 6), w[..., 2], np.where(wd == 5, w[..., 1], w[..., 0]))


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
    market_level: np.ndarray = field(repr=False, default=None)   # the market's rate level, same indexing
    hours: dict = field(repr=False, default_factory=dict)      # group -> [weekday, hour] share of losses

    def date(self, day) -> np.ndarray:
        return self.start + np.asarray(day).astype("timedelta64[D]")

    # ---- the working calendar. Day numbers may be negative (before the start) or beyond the horizon.
    def weekday(self, day) -> np.ndarray:
        """0 = Monday ... 6 = Sunday."""
        return (self.date(day).astype("M8[D]").astype(np.int64) + 3) % 7

    def is_business(self, day) -> np.ndarray:
        """A weekday that is not a holiday: the days offices, banks and courts work."""
        return np.is_busday(self.date(day).astype("M8[D]"), holidays=HOLIDAYS)

    def is_holiday(self, day) -> np.ndarray:
        return np.isin(self.date(day).astype("M8[D]"), HOLIDAYS)

    def _roll(self, day, how: str) -> np.ndarray:
        d = np.busday_offset(self.date(day).astype("M8[D]"), 0, roll=how, holidays=HOLIDAYS)
        return (d - self.start.astype("M8[D]")).astype(np.int64)

    def next_business(self, day) -> np.ndarray:
        """The day itself if it is a business day, else the next one."""
        return self._roll(day, "forward")

    def prev_business(self, day) -> np.ndarray:
        return self._roll(day, "backward")

    def _offset(self, day, k) -> np.ndarray:
        """The k-th business day after `day` (before it, for negative k); k = 0 on a business day is the day."""
        d = self.date(day).astype("M8[D]")
        k = np.broadcast_to(np.asarray(k), d.shape)
        out = np.where(k >= 0, np.busday_offset(d, np.maximum(k, 0), roll="forward", holidays=HOLIDAYS),
                       np.busday_offset(d, np.minimum(k + 1, 0), roll="backward", holidays=HOLIDAYS))
        return (out - self.start.astype("M8[D]")).astype(np.int64)

    def spread_business(self, day, u) -> np.ndarray:
        """Work that falls due on a weekend or a holiday is done over the following business days, not all on
        the first: a business day stays; any other day moves to one of the next five (u is uniform)."""
        day = np.asarray(day)
        return np.where(self.is_business(day), day, self._offset(day, np.floor(np.asarray(u) * 5).astype(int)))

    def business_between(self, day, lo, hi, u=None) -> np.ndarray:
        """A business day for something due on `day` that must fall in [lo, hi]. A business day stays. Otherwise,
        with u (uniform), one of the two business days before it or the three after it that lie in [lo, hi],
        each as likely; without u, the last business day before it, else the next one. If [lo, hi] holds none
        of them the day stays as it is."""
        day, lo, hi = np.asarray(day), np.asarray(lo), np.asarray(hi)
        if u is None:
            back, fwd = self.prev_business(day), self.next_business(day)
            return np.where(back >= lo, back, np.where(fwd <= hi, fwd, day))
        cand = np.stack([self._offset(day, k) for k in (-2, -1, 0, 1, 2)], axis=1)      # -1 is the last one before
        ok = (cand >= lo[..., None]) & (cand <= hi[..., None])
        n_ok = ok.sum(axis=1)
        pick = np.minimum(np.floor(np.asarray(u) * n_ok).astype(int), np.maximum(n_ok - 1, 0))
        rank = np.cumsum(ok, axis=1) - 1
        col = np.argmax(ok & (rank == pick[:, None]), axis=1)
        chosen = cand[np.arange(len(day)), col]
        return np.where(self.is_business(day) | (n_ok == 0), day, chosen)

    def intake_day(self, day, u, p_weekend=(0.40, 0.50), p_second=0.35) -> np.ndarray:
        """When something that happened on `day` reaches the company: weekend and holiday notices are partly
        held over (shares for Saturdays, and for Sundays and holidays; u is uniform), most to the next business
        day and the rest to the one after."""
        day, u = np.asarray(day), np.asarray(u)
        wd, hol = self.weekday(day), self.is_holiday(day)
        hold = np.where((wd == 6) | hol, p_weekend[1], np.where(wd == 5, p_weekend[0], 0.0))
        return np.where(u < hold, self._offset(day, (u < hold * p_second).astype(int)), day)

    def weighted_lead(self, day, lo: int, hi: int, weight, u) -> np.ndarray:
        """A lead time in [lo, hi] days before `day`, drawn with probability proportional to weight(candidate
        day) (a function of day numbers). u is uniform. If every candidate has zero weight the lead is lo."""
        day = np.asarray(day)
        leads = np.arange(lo, hi + 1)
        w = weight(day[:, None] - leads[None, :])
        cum = np.cumsum(w, axis=1)
        pick = (np.asarray(u)[:, None] * cum[:, -1:] > cum).sum(axis=1).clip(0, len(leads) - 1)
        return leads[np.where(cum[:, -1] > 0, pick, 0)]

    def loss_hour(self, group: str, day, u) -> np.ndarray:
        """Hour of day (0-23) of losses on the given days, from the group's hour profile for that weekday."""
        cum = np.cumsum(self.hours[group], axis=1)[self.weekday(day)]
        return (np.asarray(u)[:, None] * cum[:, -1:] > cum).sum(axis=1).clip(0, 23)

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


def _daily_index(cal: Calendar, dates: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Each simulated day's crash and vehicle-theft intensity relative to the average day of its month, from
    Chicago's daily counts (reference/daily_index.csv, built by scripts/build_calendar_reference.py): weekdays,
    holidays and bad-weather days as they really fell. A day the file does not cover takes the file's average
    for its weekday, scaled down on a holiday as the file's holidays are."""
    idx = pd.read_csv(C.REFERENCE_DIR / "daily_index.csv", parse_dates=["date"]).set_index("date")
    wd_file = idx.index.dayofweek.to_numpy()
    hol_file = np.isin(idx.index.to_numpy().astype("M8[D]"), HOLIDAYS)
    wd = (dates.astype("M8[D]").astype(np.int64) + 3) % 7
    hol = np.isin(dates.astype("M8[D]"), HOLIDAYS)
    out = []
    for col in ("crash_index", "theft_index"):
        x = idx[col].to_numpy()
        by_wd = np.array([x[(wd_file == k) & ~hol_file].mean() for k in range(7)])
        holiday = x[hol_file].mean() / by_wd[wd_file[hol_file]].mean()
        known = idx[col].reindex(pd.DatetimeIndex(dates)).to_numpy()
        out.append(np.where(np.isnan(known), by_wd[wd] * np.where(hol, holiday, 1.0), known))
    return out[0], out[1]


# Time of day of losses the Chicago files do not cover (ASSUMED shapes): share by hour, the same every weekday.
def _bumps(*peaks) -> np.ndarray:
    h = np.arange(24)
    w = sum(a * np.exp(-0.5 * (np.minimum(np.abs(h - m), 24 - np.abs(h - m)) / sd) ** 2) for m, sd, a in peaks) + 0.004
    return w / w.sum()


HOUR_SHAPES = {
    "parked": _bumps((13, 4.0, 1.0), (22, 3.0, 0.5)),       # found on returning to the car: daytime, and overnight
    "glass": _bumps((9, 3.0, 0.8), (16, 3.5, 1.0)),          # driving hours
    "animal": _bumps((6, 1.8, 0.8), (19, 2.5, 1.0)),         # dawn and dusk
    "weather": _bumps((17, 4.0, 1.0)),                       # afternoon and evening storms
    "night": _bumps((1, 3.5, 1.0), (21, 3.0, 0.6)),          # vandalism and fire: late evening and night
    "day": _bumps((13, 5.0, 1.0)),
}


def _hour_profiles() -> dict:
    """Share of losses by hour for each weekday: crashes and vehicle thefts from Chicago's records
    (reference/hour_of_day.csv), the rest from HOUR_SHAPES."""
    h = pd.read_csv(C.REFERENCE_DIR / "hour_of_day.csv")
    out = {g: d.pivot(index="weekday", columns="hour", values="share").reindex(index=range(7), columns=range(24)).fillna(0).to_numpy()
           for g, d in h.groupby("group")}
    out.update({k: np.tile(v, (7, 1)) for k, v in HOUR_SHAPES.items()})
    return out


@dataclass
class VehicleSampler:
    """Draws catalogue rows (make, model and model year) for vehicles of given model years. Rows are grouped by
    model year and segment; a vehicle first picks a segment (popularity of its model year's segments, tilted
    by household income and density), then a model within it in proportion to popularity."""
    first_year: int
    last_year: int
    seg_total: np.ndarray        # (model year, segment) -> total popularity
    order: np.ndarray            # catalogue rows sorted by model year, then segment
    cum: np.ndarray              # cumulative popularity along `order`
    group_offset: np.ndarray     # cumulative popularity before each (model year, segment) group
    group_total: np.ndarray
    group_start: np.ndarray      # position in `order` of each group's first row
    group_end: np.ndarray        # position in `order` after each group's last row

    @classmethod
    def build(cls, models: pd.DataFrame, segments: list[str]) -> "VehicleSampler":
        y0, y1 = int(models.model_year.min()), int(models.model_year.max())
        seg = models.segment.map({s: i for i, s in enumerate(segments)}).to_numpy()
        assert not np.isnan(seg.astype(float)).any(), "catalogue has a segment the simulation does not know"
        g = (models.model_year.to_numpy() - y0) * len(segments) + seg
        order = np.lexsort((np.arange(len(models)), g))
        w = models.popularity.to_numpy()[order]
        cum = np.cumsum(w)
        ng = (y1 - y0 + 1) * len(segments)
        total = np.bincount(g, weights=models.popularity.to_numpy(), minlength=ng)
        count = np.bincount(g, minlength=ng)
        end = np.cumsum(count)
        offset = np.concatenate([[0.0], np.cumsum(total)[:-1]])
        return cls(y0, y1, total.reshape(-1, len(segments)), order, cum, offset, total, end - count, end)


@dataclass
class Reference:
    zips: pd.DataFrame
    models: pd.DataFrame
    cal: Calendar
    names: object = None                       # names.NameSampler
    vehicle_sampler: VehicleSampler | None = None


def load(cfg: C.Config) -> Reference:
    zips = pd.read_csv(C.REFERENCE_DIR / "zip_reference.csv", dtype={"zip": str})
    models = pd.read_csv(C.REFERENCE_DIR / "vehicle_catalogue.csv")
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
    day_crash, day_theft = _daily_index(cal, dates)
    crash = season.crash_seasonality.to_numpy()[mi] * C.year_series(C.FREQ_TREND_CRASH, cal.year) * day_crash
    theft = season.theft_seasonality.to_numpy()[mi] * C.year_series(theft_year, cal.year) * day_theft
    cal.hours = _hour_profiles()
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
    # the market's level: each calendar year's change spread evenly over its days, equal to the company's on the
    # reference date
    origin = np.datetime64("2021-01-01")
    span = np.arange((start - origin).astype(int) + len(level) + 1)
    yr = (origin + span.astype("timedelta64[D]")).astype("M8[Y]").astype(int) + 1970
    cum = np.concatenate([[0.0], np.cumsum(np.log1p(C.year_series(C.MARKET_RATE_CHANGE, yr)) / 365.25)])
    ref_day = (np.datetime64(C.MARKET_REFERENCE_DATE) - origin).astype(int)
    off = (start - origin).astype(int)
    cal.market_level = np.exp(cum[off:off + len(level)] - cum[ref_day])

    from .names import NameSampler
    from .truth import SEGMENTS
    return Reference(zips=zips, models=models, cal=cal, names=NameSampler.load(),
                     vehicle_sampler=VehicleSampler.build(models, SEGMENTS))
