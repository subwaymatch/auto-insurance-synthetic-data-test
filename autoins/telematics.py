"""Lakefront DriveCheck: a voluntary usage-based insurance (telematics) programme.

Customers are offered the programme when a policy is written and at each renewal. Those who join install a phone
app, a plug-in device or a windshield beacon on every car on the policy, get a participation discount straight
away, and from the next renewal a discount earned by their driving score. Scores never raise the premium, as in
most US programmes. Some customers leave the programme, more often those who see a poor score.

What the device sees is generated from the truth the insurer cannot see: the at-fault propensity (age, experience and
the hidden risk factor, truth.driver_multiplier) of the driver assigned to the car at the time, and the car's true
annual mileage, which the customer usually understates. A score is one driver's driving of one car: a scoring
window in which the car's assigned driver changed is split there (split_windows), each part is scored as its own
driver's, and the car's discount is the days-weighted average of the discounts its parts earned. So the score carries risk information the rating plan lacks, imperfectly (the
metrics are noisy), and the programme attracts safer drivers (favourable selection). Being monitored also makes
people drive a little more carefully: at-fault crash frequency is lower while a car is enrolled (BEHAVIOUR_FACTOR),
which the answer key's expected losses include. Selection and behaviour can be told apart only with the answer key.

All parameters are ASSUMED, shaped on published descriptions of US programmes (participation discounts of 5% to
10%, earned discounts up to about 30%, discount-only scoring, uptake rising to roughly a fifth to a third of new
customers) and on studies reporting safer driving after enrolment.
"""
from __future__ import annotations

import numpy as np

PROGRAMME = "Lakefront DriveCheck"
DEVICE_TYPES = ["Mobile App", "Plug-in Device", "Bluetooth Beacon"]
DEVICE_P = {2021: [0.45, 0.40, 0.15], 2026: [0.80, 0.08, 0.12]}       # by enrolment year, interpolated
PARTICIPATION_DISCOUNT = 0.05          # from the day a policy joins until its first scored renewal
MAX_EARNED_DISCOUNT = 0.30
DISCOUNTED_COVERAGES = ["BI", "PD", "UM", "MED", "COLL", "COMP"]
MIN_SCORED_DAYS = 45                   # a car monitored for less keeps the participation discount
# take-up of the offer: new business rising over the period, existing customers at each renewal
NEW_BUSINESS_UPTAKE = {2021: 0.11, 2022: 0.13, 2023: 0.16, 2024: 0.19, 2025: 0.21, 2026: 0.23}
RENEWAL_UPTAKE = 0.02
OPENING_BOOK_ENROLLED = 0.07           # policies already enrolled when the extract starts
SELECTION_EXPONENT = -0.9              # odds of joining ~ (household at-fault propensity) ** this
REJOIN_WAIT_DAYS = 730                 # a customer who left is not offered the programme again for two years
DROPOUT_RATE = 0.16                    # a year, at a middling score; poor scorers leave faster
BEHAVIOUR_FACTOR = 0.93                # at-fault crash frequency while a car is monitored
METRIC_NOISE = 0.35


def _by_year(table: dict, year: np.ndarray) -> np.ndarray:
    ys = sorted(table)
    return np.interp(year, ys, [table[y] for y in ys])


def base_uptake(year, new_business, opening_book) -> np.ndarray:
    return np.where(opening_book, OPENING_BOOK_ENROLLED,
                    np.where(new_business, _by_year(NEW_BUSINESS_UPTAKE, year), RENEWAL_UPTAKE))


def uptake(r: np.random.Generator, base, propensity, young, channel) -> np.ndarray:
    """Whether each offered policy joins. propensity: the household's at-fault propensity (1 = average)."""
    odds = base / (1 - base) * np.clip(propensity, 0.2, 5) ** SELECTION_EXPONENT * np.where(young, 1.35, 1.0) \
        * np.array([1.0, 1.15, 1.6])[channel]
    return r.random(len(base)) < odds / (1 + odds)


def device(r: np.random.Generator, year) -> np.ndarray:
    p = np.stack([_by_year({y: v[i] for y, v in DEVICE_P.items()}, year) for i in range(len(DEVICE_TYPES))], axis=1)
    p = p / p.sum(axis=1, keepdims=True)
    return np.minimum((r.random(len(p))[:, None] > np.cumsum(p, axis=1)).sum(axis=1), len(DEVICE_TYPES) - 1)


def metrics(r: np.random.Generator, propensity, age, true_miles, density, days) -> dict:
    """Driving metrics over a monitoring window of `days` for each car. propensity: the primary driver's at-fault
    propensity relative to an average driver; true_miles: the car's true annual mileage."""
    n = len(days)
    noise = lambda s=METRIC_NOISE: np.exp(r.normal(-s * s / 2, s, n))
    young = np.interp(age, [16, 21, 25, 30, 70, 85], [1.9, 1.6, 1.3, 1.0, 1.0, 1.15])
    m = np.clip(propensity, 0.1, 8)
    miles = true_miles * days / 365.25 * noise(0.08)
    trip_len = 6.5 * np.clip(density / 5000, 0.3, 3) ** -0.15 * noise(0.15)
    return {
        "miles": miles,
        "trips": np.maximum(np.round(miles / trip_len), 1).astype(int),
        "hard_brakes": 1.2 * m ** 0.55 * (density / 5000).clip(0.2, 5) ** 0.12 * noise(),
        "rapid_accels": 0.7 * m ** 0.45 * young ** 0.5 * noise(0.4),
        "speeding_pct": np.minimum(2.5 * m ** 0.6 * young ** 0.4 * noise(0.45), 40),
        "phone_minutes": 2.5 * m ** 0.4 * young ** 0.8 * noise(0.5),
        "night_pct": np.minimum(2.5 * m ** 0.25 * young ** 1.2 * noise(0.5), 45),
    }


def score(mt: dict, days) -> np.ndarray:
    """A 1-100 driving score (higher is safer) from the metrics, as programmes publish them: braking, speeding
    and phone use weigh most; more miles and late-night driving count against. A plug-in device cannot see the
    phone (phone_minutes NaN): the other behaviours then carry its weight in proportion."""
    annual = mt["miles"] * 365.25 / np.maximum(days, 1)
    phone = np.log(np.asarray(mt["phone_minutes"], dtype=float) / 2.5)
    seen = ~np.isnan(phone)
    behaviour = (0.30 * np.log(mt["hard_brakes"] / 1.2) + 0.15 * np.log(mt["rapid_accels"] / 0.7)
                 + 0.25 * np.log(np.maximum(mt["speeding_pct"], 0.05) / 2.5)
                 + 0.10 * np.log(np.maximum(mt["night_pct"], 0.05) / 2.5))
    behaviour = np.where(seen, behaviour + 0.20 * np.nan_to_num(phone), behaviour / 0.80)
    idx = behaviour + 0.20 * np.log(np.maximum(annual, 500) / 10_000)
    return np.clip(np.round(60 - 30 * idx), 1, 100).astype(int)


def earned_discount(s) -> np.ndarray:
    """Discount earned by a score: none at 45 or below, rising evenly to the maximum at 95 and above."""
    return np.round(np.clip((np.asarray(s) - 45) / 50, 0, 1) * MAX_EARNED_DISCOUNT, 2)


def dropout(r: np.random.Generator, s, days, device_type) -> np.ndarray:
    """Day offsets (within each window) at which a customer leaves the programme, or -1."""
    rate = DROPOUT_RATE * np.exp(0.035 * (60 - np.asarray(s))) * np.where(device_type == 0, 1.3, 1.0)
    p = 1 - np.exp(-rate * np.asarray(days) / 365.25)
    leave = r.random(len(p)) < p
    return np.where(leave, np.floor(r.random(len(p)) * np.maximum(days, 1)).astype(int), -1)


def split_windows(log_veh, log_day, log_drv, veh, ws, we):
    """Split scoring windows [ws, we) of cars `veh` where the car's assigned driver changes, so each part is one
    driver's driving. log_veh, log_day and log_drv are the cars' assignment histories sorted by car and day: from
    log_day on, log_drv drives log_veh (the exposure rows' rated driver). A day before a car's first entry takes
    that entry's driver. Only entries dated before a window's end can affect it, so a later change of driver
    never alters an earlier score. Returns (window index, part start, part end, driver), parts in date order."""
    log_veh, log_day, log_drv = (np.asarray(a, dtype=np.int64) for a in (log_veh, log_day, log_drv))
    veh, ws, we = (np.asarray(a, dtype=np.int64) for a in (veh, ws, we))
    off, span = 2 ** 21, 2 ** 22                       # days run from about -10**6 to a few thousand
    key = log_veh * span + log_day + off
    lo = np.searchsorted(log_veh, veh, "left")
    if len(veh) and not (log_veh[np.minimum(lo, len(log_veh) - 1)] == veh).all():
        raise ValueError("a scored car has no assignment history")
    j0 = np.maximum(np.searchsorted(key, veh * span + ws + off, "right") - 1, lo)     # the entry in force at ws
    j1 = np.maximum(np.searchsorted(key, veh * span + we + off, "left"), j0 + 1)     # entries dated before we
    n = j1 - j0
    w = np.repeat(np.arange(len(veh)), n)
    pos = np.arange(n.sum()) - np.repeat(np.cumsum(n) - n, n)
    j = j0[w] + pos
    start = np.where(pos == 0, ws[w], log_day[j])
    end = np.where(pos == n[w] - 1, we[w], np.r_[start[1:], 0])
    d = log_drv[j]
    first = (pos == 0) | (d != np.r_[-1, d[:-1]])      # consecutive entries for one driver (a move) are one part
    last = np.r_[first[1:], True]
    return w[first], start[first], end[last], d[first]
