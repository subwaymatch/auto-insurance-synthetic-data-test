"""The true risk model: how often each vehicle has a loss, and what it costs.

The same severity functions are used twice: with random draws to simulate claims, and
on a fixed grid of quantiles to compute the expected loss of every vehicle. The
expected loss is what the rating plan is fitted to, and it is written to the answer key.
Per-accident limits on injury coverages, which depend on several claimants at once, enter
the expected loss through a table built by simulation (AGG_SHARE).
"""
from __future__ import annotations

from dataclasses import dataclass
from math import erf, sqrt
from statistics import NormalDist

import numpy as np
import pandas as pd

from . import config as C
from .refdata import Calendar, normal_grid

K = 96
ZG = normal_grid(K)[None, :]                    # standard normal quantiles
UG = ((np.arange(K) + 0.5) / K)[None, :]        # uniform quantiles

DRIVING_PERILS = ["AF_MV", "AF_SV", "NAF", "PARKED"]
COMP_PERILS = ["GLASS", "THEFT_TOTAL", "THEFT_PARTIAL", "VANDALISM", "ANIMAL", "WEATHER", "FLOOD", "FIRE", "OTHER_COMP"]
PERIL_GROUP = {"AF_MV": "crash", "AF_SV": "crash", "NAF": "crash", "PARKED": "crash", "GLASS": "glass",
               "THEFT_TOTAL": "theft", "THEFT_PARTIAL": "theft", "VANDALISM": "flat", "ANIMAL": "animal",
               "WEATHER": "weather", "FLOOD": "weather", "FIRE": "flat", "OTHER_COMP": "flat"}
SEGMENTS = ["economy", "mainstream", "luxury", "truck", "sports", "ev", "minivan"]
MEAN_CLAIMANTS = float(np.dot(np.arange(1, 5), C.BI_CLAIMANTS_P))
MEAN_SALVAGE = float(np.mean(C.SALVAGE_RANGE))
MEAN_SUBRO = float(np.mean(C.SUBROGATION_SHARE))


def _rental_means() -> np.ndarray:
    """Expected rental reimbursement per rental, by option and by repair (0) or replacement after a total loss (1)."""
    z = normal_grid(K)
    cost = C.RENTAL_DAILY_COST["median"] * np.exp(C.RENTAL_DAILY_COST["sigma"] * z)
    out = np.zeros((len(C.RENTAL_OPTIONS), 2))
    for j, kind in enumerate(("repair", "total")):
        days = np.ceil(C.RENTAL_DAYS[kind]["median"] * np.exp(C.RENTAL_DAYS[kind]["sigma"] * z))
        for o, (daily, most) in enumerate(C.RENTAL_OPTIONS):
            out[o, j] = np.minimum(days[:, None] * np.minimum(cost[None, :], daily), most).mean()
    return out


RENTAL_MEAN = _rental_means()
TOW_MEAN = float(np.minimum(C.TOW_COST["median"] * np.exp(C.TOW_COST["sigma"] * ZG), C.TOWING_LIMIT).mean())


# ---------------------------------------------------------------------------- drivers and vehicles
def good_student(good_grades, school_end_day, dob_day, day) -> np.ndarray:
    """Good-student status on `day`: B grades, still in full-time school, and under the age limit.
    The same rule drives the insurer's discount and the true-risk effect, so neither outlives school."""
    day = np.asarray(day)
    return np.asarray(good_grades, dtype=bool) & (day < np.asarray(school_end_day)) \
        & ((day - np.asarray(dob_day)) / 365.25 < C.GOOD_STUDENT_MAX_AGE)


def driver_multiplier(drv: pd.DataFrame, day, cal: Calendar) -> np.ndarray:
    """At-fault accident propensity of each driver on a given day, relative to a reference driver."""
    age = (np.asarray(day) - drv.dob_day.to_numpy()) / 365.25
    licensed = (np.asarray(day) - drv.licensed_day.to_numpy()).clip(0) / 365.25
    f = np.interp(age, C.AGE_KNOTS, C.AGE_FACTOR)
    f = f * (1 + C.YOUNG_MALE_EXTRA * np.clip((27 - age) / 9, 0, 1) * drv.male.to_numpy())
    f = f * np.where(drv.marital.to_numpy() == "M", C.MARRIED_FACTOR, 1.0)
    f = f * np.interp(licensed, C.INEXPERIENCE_KNOTS, C.INEXPERIENCE_FACTOR)
    gs = good_student(drv.good_grades.to_numpy(), drv.school_end_day.to_numpy(), drv.dob_day.to_numpy(), day)
    f = f * np.where(gs, C.GOOD_STUDENT_FACTOR, 1.0)
    return f * drv.latent.to_numpy()


def actual_cash_value(msrp, model_year, day, cal: Calendar, level_day=None) -> np.ndarray:
    """What a car is worth on `day` (config.RESIDUAL_VALUE), at the used-car prices of `level_day` (default: the
    same day)."""
    age = (cal.year_frac(day) - np.asarray(model_year) + 0.5).clip(0)
    resid = np.exp(np.interp(age, C.RESIDUAL_VALUE_AGE, np.log(C.RESIDUAL_VALUE)))
    level = cal.used_car[np.clip(day if level_day is None else level_day, 0, cal.horizon)]
    # the used-car market against the new-car prices the model year was sold at, felt fully from a year old
    new = np.interp(model_year, list(C.NEW_VEHICLE_PRICE_LEVEL), list(C.NEW_VEHICLE_PRICE_LEVEL.values()))
    level = 1 + (level / new - 1) * np.minimum(age, 1.0)
    return np.maximum(np.asarray(msrp) * np.minimum(resid * level, C.NEW_VALUE_CAP), C.MIN_VEHICLE_VALUE)


# ---------------------------------------------------------------------------- severity kernels
def pd_paid(z, limit, factor, trend):
    return np.minimum(C.PD_SEV["median"] * factor * trend * np.exp(C.PD_SEV["sigma"] * z), limit)


def injury_paid(z, limit, factor, trend, sev):
    return np.minimum(sev["median"] * factor * trend * np.exp(sev["sigma"] * z), limit)


def med_paid(z, limit, trend):
    return np.minimum(C.MED_SEV["median"] * trend * np.exp(C.MED_SEV["sigma"] * z), limit)


def collision(z, peril_factor, repair_factor, trend, acv, deductible):
    """Returns (gross loss, amount paid, total-loss flag)."""
    damage = C.COLL_SEV["median"] * peril_factor * repair_factor * trend * np.exp(C.COLL_SEV["sigma"] * z)
    total = damage >= C.TOTAL_LOSS_THRESHOLD * acv
    gross = np.where(total, acv, damage)
    return gross, np.maximum(gross - deductible, 0.0), total


def comp_gross(peril: str, z, u, repair_factor, adas, trend, acv):
    """Returns (gross loss, total-loss flag). As for collision, damage at or above the total-loss
    threshold makes the vehicle a total loss, settled at its actual cash value."""
    if peril == "THEFT_TOTAL":      # 40% recovered with damage, 60% never recovered
        damage = acv * np.where(u < 0.40, 0.08 + u / 0.40 * 0.42, 1.0)
    elif peril in ("FLOOD", "FLOOD_CAT"):
        damage = acv * np.where(u < 0.50, 0.10 + u / 0.50 * 0.40, 0.80 + (u - 0.50) / 0.50 * 0.20)
    elif peril == "FIRE":
        damage = acv * (0.20 + 0.80 * u)
    else:
        median, sigma = C.COMP_SEV[peril]
        if peril == "GLASS":
            median = median * np.where(adas, C.GLASS_ADAS_FACTOR, 1.0)
        elif peril == "ANIMAL":
            median = median * repair_factor ** 0.6
        damage = median * trend * np.exp(sigma * z)
    total = (damage >= C.TOTAL_LOSS_THRESHOLD * acv) & (peril != "GLASS")
    return np.where(total, acv, np.minimum(damage, acv)), total


def round_settlement(x, rng: np.random.Generator) -> np.ndarray:
    """Agreed injury damages as negotiated: round figures (config.SETTLEMENT_STEPS), never below one step."""
    x = np.asarray(x, dtype=float)
    bounds = np.array([b for b, _ in C.SETTLEMENT_STEPS])
    step = np.array([s for _, s in C.SETTLEMENT_STEPS])[np.searchsorted(bounds, x, side="right").clip(0, len(bounds) - 1)]
    step = step * np.where(rng.random(len(x)) < 0.5, 2, 1)
    exact = rng.random(len(x)) < C.SETTLEMENT_EXACT_P
    return np.where(exact, np.round(x, 2), np.maximum(np.round(x / step), 1) * step)


def cap_per_accident(paid, accident, n_accidents: int, room) -> np.ndarray:
    """Share each accident's per-accident limit among its claimants. `paid` holds what each claimant would
    get under the per-person limit, `accident` the accident each belongs to, and `room` each accident's
    limit. Where an accident's payments exceed its room they are cut pro rata. The arithmetic is in whole
    cents, with the cents left over by rounding down going to the first claimants, so an accident's
    payments add up to the limit exactly and never to a cent more. Returns dollars."""
    cents = np.round(np.asarray(paid, dtype=float) * 100).astype(np.int64)
    cap = np.round(np.maximum(np.asarray(room, dtype=float), 0.0) * 100).astype(np.int64)
    tot = np.bincount(accident, cents, n_accidents).astype(np.int64)
    over = (tot > cap)[accident]
    cut = np.where(over, cents * cap[accident] // np.maximum(tot[accident], 1), cents)
    spare = np.where(tot > cap, cap - np.bincount(accident, cut, n_accidents).astype(np.int64), 0)
    paying = cents > 0                                 # the spare cents go to claimants who are being paid
    before = np.cumsum(paying) - paying
    first = np.full(n_accidents, len(cents), dtype=np.int64)
    np.minimum.at(first, accident, np.arange(len(cents)))
    rank = before - before[np.minimum(first, len(cents) - 1)][accident]     # position among the accident's paid claimants
    return (cut + (over & paying & (rank < spare[accident]))) / 100


_ERF = np.frompyfunc(erf, 1, 1)


def normal_cdf(x) -> np.ndarray:
    x = np.asarray(x, dtype=float)
    return (0.5 * (1 + _ERF(x / sqrt(2)))).astype(float) if x.size else x


_PPF = np.frompyfunc(NormalDist().inv_cdf, 1, 1)


def selection_lift(p, rho: float, sigma: float) -> np.ndarray:
    """How much a log-normal cost exp(sigma Z) is raised, on average, among the cases selected: those whose latent
    draw, correlated rho with Z, is in its top share p (a Gaussian copula). E[exp(sigma Z) | selected] over
    E[exp(sigma Z)] is Phi(rho sigma + Phi^-1(p)) / p. Dividing the cost by it keeps the selected cases' mean."""
    p = np.clip(np.atleast_1d(np.asarray(p, dtype=float)), 1e-9, 1 - 1e-9)
    return normal_cdf(rho * sigma + np.asarray(_PPF(p), dtype=float)) / p


def correlated(z: np.ndarray, rho: float, rng: np.random.Generator) -> np.ndarray:
    """Standard normal draws correlated `rho` with z."""
    return rho * z + np.sqrt(1 - rho ** 2) * rng.standard_normal(len(z))


def has_uim(c: dict) -> np.ndarray:
    """Underinsured motorist cover comes with uninsured motorist limits above the 25/50 minimum, and only then
    (215 ILCS 5/143a-2(4)): a policy with minimum limits has none."""
    return c["um_pp"] > C.BI_LIMITS[0][0]


def other_driver_limits(rng: np.random.Generator, n: int) -> tuple[np.ndarray, np.ndarray]:
    """Bodily injury limits (per person, per accident) of n at-fault drivers who are insured."""
    lims, w = zip(*C.OTHER_DRIVER_BI_LIMIT.items())
    pp = np.array(lims)[rng.choice(len(lims), n, p=w)]
    return pp, np.array([dict(C.BI_LIMITS)[x] for x in pp])


def underinsured(gross, um_pp, other_pp, accident=None, n_accidents: int = 0, other_pa=None):
    """Underinsured motorist benefit per claimant before our per-accident limit: damages up to the policy's own
    per-person limit, less what the at-fault driver's insurer pays. That insurer pays each claimant up to its
    per-person limit and, given `accident` and `other_pa`, all of an accident's claimants together up to its
    per-accident limit (shared pro rata), so several claimants can leave more for our coverage to pay.
    Returns (benefit, other insurer's payment)."""
    other = np.minimum(gross, other_pp)
    if accident is not None:
        other = cap_per_accident(other, accident, n_accidents, other_pa)
    return np.maximum(np.minimum(gross, um_pp) - other, 0.0), other


AGG_SCALES = np.geomspace(0.5, 1.6, 12)        # severity level (segment factor x trend) the table is built on


def _aggregate_shares(n: int = 40_000) -> dict:
    """Share of per-person-limited injury payments that the per-accident limits leave, by coverage, limit
    option and severity level (for underinsured motorist, above 1 where the at-fault insurer's own per-accident
    limit leaves more to pay). `expected` multiplies its per-claimant figures by these so that the answer
    key allows for accidents with several claimants. Built once by simulation from a fixed set of draws
    (they are part of the model, not of a run), common to every cell so the shares vary smoothly."""
    r = np.random.default_rng(143)
    live = np.arange(4)[None, :] < (1 + r.choice(4, n, p=C.BI_CLAIMANTS_P))[:, None]
    z, u = r.standard_normal((n, 4)), r.random((n, 4))
    other_pp, other_pa = other_driver_limits(r, n)
    acc = np.repeat(np.arange(n), 4)
    out = {}
    for cov, sev in (("BI", C.BI_SEV), ("UM", C.UM_SEV), ("UIM", C.UM_SEV)):
        base = sev["median"] * np.exp(sev["sigma"] * z) * live
        pays = u >= C.CWP["BI" if cov == "BI" else "UM"]
        tab = np.ones((len(C.BI_LIMITS), len(AGG_SCALES)))
        for i, (pp, pa) in enumerate(C.BI_LIMITS):
            for j, scale in enumerate(AGG_SCALES):
                if cov == "UIM":
                    # `expected` works per claimant; the accident adds the other insurer's per-accident limit,
                    # which leaves more to us, and our own per-accident limit less what that insurer paid
                    per_claimant, _ = underinsured(base * scale, pp, other_pp[:, None])
                    paid, other = underinsured((base * scale).ravel(), pp, np.repeat(other_pp, 4), acc, n, other_pa)
                    paid, other = paid.reshape(n, 4), other.reshape(n, 4)
                    room = np.maximum(pa - other.sum(1), 0.0)
                else:
                    paid, room = np.minimum(base * scale, pp), pa
                    per_claimant = paid
                tot, base_tot = (paid * pays).sum(1), (per_claimant * pays).sum()
                tab[i, j] = np.minimum(tot, room).sum() / base_tot if base_tot > 0 else 1.0
        out[cov] = tab
    return out


AGG_SHARE = _aggregate_shares()


def aggregate_share(cov: str, limit_opt: np.ndarray, scale: np.ndarray) -> np.ndarray:
    """Look up AGG_SHARE for each vehicle's limit option and severity level."""
    out = np.ones(len(limit_opt))
    for i in range(len(C.BI_LIMITS)):
        m = limit_opt == i
        out[m] = np.interp(np.log(scale[m]), np.log(AGG_SCALES), AGG_SHARE[cov][i])
    return out


# ---------------------------------------------------------------------------- per-vehicle context
@dataclass
class Static:
    """Flat numpy views of the population, indexed by vehicle, driver or policy."""
    pop: object
    v: dict
    p: dict
    zt: dict
    u_veh: np.ndarray
    u_drv: np.ndarray
    u_w: np.ndarray
    cat_p: np.ndarray       # [event, zip] hit probability

    @classmethod
    def build(cls, pop, ref) -> "Static":
        z = ref.zips
        p = {c: pop.pol[c].to_numpy().copy() for c in pop.pol.columns}
        zt = {c: pop.zip_truth[c].to_numpy() for c in pop.zip_truth.columns}
        cat = np.zeros((len(C.CAT_EVENTS), len(z)))
        for i, (_, _, _, _, lat, lon, radius, peak) in enumerate(C.CAT_EVENTS):
            d = (69.0 * np.hypot(z.lat - lat, (z.lon - lon) * np.cos(np.radians(lat)))).to_numpy()
            cat[i] = peak * np.exp(-1.5 * (d / radius) ** 2) * (d < 1.6 * radius)
        st = cls(pop=pop, v={}, p=p, zt=zt, u_veh=pop.usage.veh.to_numpy(), u_drv=pop.usage.drv.to_numpy(),
                 u_w=pop.usage.weight.to_numpy(), cat_p=cat)
        st.v = st._columns(pop.veh)
        return st

    def _columns(self, veh: pd.DataFrame) -> dict:
        v = {c: veh[c].to_numpy().copy() for c in veh.columns}
        seg = v["segment"]
        v["seg_freq"] = np.array([C.SEGMENT_FREQ[s] for s in seg])
        v["pd_factor"] = np.array([C.SEGMENT_PD_SEV.get(s, 1.0) for s in seg]) * np.where(v["body_type"] == "SUV", C.SUV_PD_SEV, 1.0)
        v["bi_factor"] = np.array([C.SEGMENT_BI_SEV.get(s, 1.0) for s in seg])
        v["mile_rel"] = v["true_miles"] / 10_000
        v["seg_code"] = np.array([SEGMENTS.index(x) for x in seg], dtype=int)
        v["use_factor"] = np.where(v["use"] == "Business", C.BUSINESS_USE_FACTOR, 1.0)
        v["zi"] = self.p["zi"][v["pol"]]
        # telematics (see telematics.py): the discount the car is rated with, and whether it is being monitored
        v.setdefault("tele_disc", np.zeros(len(veh)))
        v.setdefault("tele_on", np.zeros(len(veh), dtype=bool))
        v.setdefault("tele_since", np.full(len(veh), -10 ** 6))
        return v

    def retire(self, old: np.ndarray, day: np.ndarray, reason: int, known=None) -> None:
        """Take vehicles `old` off their policies from `day` (the first day they are not insured). `known`: the day
        the company learned of it, if later (a car written off is removed, backdated, once the claim is reported)."""
        self.v["active"][old] = False
        self.v["removed_day"][old] = day
        self.v["removal_reason"][old] = reason
        self.v["removal_known"][old] = day if known is None else np.maximum(day, known)

    def add_vehicles(self, new: pd.DataFrame) -> None:
        """Append vehicles (new must carry every stored vehicle column). Call set_usage before simulating them."""
        if len(new) == 0:
            return
        add = self._columns(new[[c for c in self.v if c in new.columns]])
        self.v = {k: np.concatenate([a, add[k]]) for k, a in self.v.items()}

    def add_replacements(self, old: np.ndarray, new: pd.DataFrame) -> None:
        """Add vehicles `new` (one per entry of `old`), which inherit the drivers of the vehicles they replace."""
        first_new = len(self.v["pol"])
        self.add_vehicles(new)
        new_id = np.full(first_new, -1)
        new_id[old] = first_new + np.arange(len(old))
        m = new_id[self.u_veh] >= 0
        self.u_veh = np.concatenate([self.u_veh, new_id[self.u_veh[m]]])
        self.u_drv = np.concatenate([self.u_drv, self.u_drv[m]])
        self.u_w = np.concatenate([self.u_w, self.u_w[m]])

    def set_usage(self, usage: pd.DataFrame) -> None:
        self.u_veh, self.u_drv, self.u_w = usage.veh.to_numpy(), usage.drv.to_numpy(), usage.weight.to_numpy()


def new_customer_factor(t0, s, x) -> np.ndarray:
    """Average over days [s, x) of the new-customer multiplier 1 + sum(amplitude * exp(-days since t0 / scale))
    (config.NEW_CUSTOMER), for policies first written on day t0."""
    a = np.maximum(np.asarray(s) - t0, 0).astype(float)
    b = np.maximum(np.asarray(x) - t0, a + 1)
    f = np.ones(len(a))
    for amp, scale in C.NEW_CUSTOMER.values():
        f += amp * scale / (b - a) * (np.exp(-a / scale) - np.exp(-b / scale))
    return f


def new_customer_days(t0, s, x, rng: np.random.Generator) -> np.ndarray:
    """Loss days in [s, x) for the claims the new-customer multiplier adds: drawn from its decaying part."""
    a = np.maximum(np.asarray(s) - t0, 0).astype(float)
    b = np.maximum(np.asarray(x) - t0, a + 1)
    parts = np.array([amp * scale * (np.exp(-a / scale) - np.exp(-b / scale)) for amp, scale in C.NEW_CUSTOMER.values()])
    which = (rng.random(len(a)) * parts.sum(axis=0) > np.cumsum(parts, axis=0)[:-1]).sum(axis=0)
    scale = np.array([v[1] for v in C.NEW_CUSTOMER.values()])[which]
    lo, hi = np.exp(-a / scale), np.exp(-b / scale)
    t = -scale * np.log(lo - rng.random(len(a)) * (lo - hi))
    return np.clip(t0 + np.floor(t).astype(int), s, np.maximum(np.asarray(x) - 1, s))


def set_window(c: dict, cal: Calendar, s: np.ndarray, x: np.ndarray) -> None:
    """Change the exposure window of a context (used when a total loss ends a vehicle's cover early).
    Severity and vehicle value stay as simulated; only the exposure behind the expected loss changes."""
    c["s"], c["x"] = s, x
    # exposure is counted inside the extract: the new-customer multiplier is averaged over the same days
    c["nc"] = new_customer_factor(c["t0"], np.clip(s, 0, cal.horizon), np.clip(x, 0, cal.horizon))
    c["expo"] = {k: cal.exposure(PERIL_GROUP[k], s, x) for k in c["rate"]}
    c["expo"]["THEFT_TOTAL"] = np.where(c["kh"], cal.exposure("theft_kh", s, x), c["expo"]["THEFT_TOTAL"])
    for k in C.NEW_CUSTOMER_PERILS:
        c["expo"][k] = c["expo"][k] * c["nc"]


def context(st: Static, cal: Calendar, V: np.ndarray, s: np.ndarray, x: np.ndarray, cost_day=None) -> dict:
    """Everything needed to price or simulate vehicles V over the window [s, x).
    cost_day fixes the cost level (used when fitting the rating plan); default is the window midpoint."""
    v, p, zt = st.v, st.p, st.zt
    pol = v["pol"][V]
    zi = v["zi"][V]
    mid = np.clip((s + np.minimum(x, cal.horizon)) // 2, 0, cal.horizon)     # vehicle age is taken here
    cost = mid if cost_day is None else np.full(len(V), cost_day)             # price level is taken here
    c = dict(V=V, pol=pol, zi=zi, s=s, x=x, n=len(V))

    # household drivers: weight each driver's propensity by how much they use the vehicle
    local = np.full(len(v["pol"]), -1)
    local[V] = np.arange(len(V))
    rows = np.flatnonzero(local[st.u_veh] >= 0)
    uv, ud, uw = local[st.u_veh[rows]], st.u_drv[rows], st.u_w[rows]
    drv = st.pop.drv.iloc[ud]
    m = driver_multiplier(drv, s[uv], cal)
    c["h_af"] = np.bincount(uv, uw * m, len(V))
    c["h_naf"] = np.bincount(uv, uw * m ** 0.25, len(V))

    def keys(weight):
        cs = np.cumsum(weight)
        first = np.r_[True, uv[1:] != uv[:-1]]
        base = np.maximum.accumulate(np.where(first, cs - weight, 0.0))
        tot = np.bincount(uv, weight, len(V))[uv]
        return uv + np.clip((cs - base) / tot, 0, 1) * (1 - 1e-9)
    c["key_af"], c["key_any"], c["u_drv"] = keys(uw * m), keys(uw), ud

    crash, theft = zt["true_crash_hazard"][zi], zt["true_theft_hazard"][zi]
    dens = zt["density_factor"][zi]
    mile = v["mile_rel"][V]
    multi = np.where(p["n_veh"][pol] > 1, C.MULTI_CAR_FREQ, 1.0)      # each car of a multi-car household is driven less hard
    drive = mile ** C.MILEAGE_ELASTICITY * v["use_factor"][V] * v["seg_freq"][V] * multi
    adas = v["adas"][V]
    park = v["parking"][V]
    B = C.BASE_RATE
    c["rate"] = {
        "AF_MV": B["AF_MV"] * c["h_af"] * drive * np.where(adas, C.ADAS_FREQ_FACTOR["AF_MV"], 1.0) * crash,
        "AF_SV": B["AF_SV"] * c["h_af"] * drive * np.where(adas, C.ADAS_FREQ_FACTOR["AF_SV"], 1.0) * crash ** 0.5,
        "NAF": B["NAF"] * c["h_naf"] * mile ** C.MILEAGE_ELASTICITY * multi * crash,
        "PARKED": B["PARKED"] * dens * np.array(C.PARKING_HIT_FACTOR)[park] * crash ** 0.5,
        "GLASS": B["GLASS"] * mile ** 0.5,
        "THEFT_TOTAL": B["THEFT_TOTAL"] * theft * v["theft_factor"][V] * np.array(C.PARKING_THEFT_FACTOR)[park]
                       * np.where(v["anti_theft"][V], C.ANTI_THEFT_FACTOR, 1.0),
        "THEFT_PARTIAL": B["THEFT_PARTIAL"] * theft ** 0.8 * np.array(C.PARKING_THEFT_FACTOR)[park],
        "VANDALISM": B["VANDALISM"] * theft ** 0.5 * dens * np.array(C.PARKING_HIT_FACTOR)[park],
        "ANIMAL": B["ANIMAL"] * zt["animal_factor"][zi] * mile ** 0.5,
        "WEATHER": B["WEATHER"] * np.array(C.PARKING_WEATHER_FACTOR)[park],
        "FLOOD": np.full(len(V), B["FLOOD"]),
        "FIRE": np.full(len(V), B["FIRE"]),
        "OTHER_COMP": np.full(len(V), B["OTHER_COMP"]),
    }
    kh = v["kia_hyundai"][V]
    c["kh"] = kh
    c["t0"] = p["inception_day"][pol]
    set_window(c, cal, s, x)

    # coverage terms and cost levels
    bi = np.array(C.BI_LIMITS)
    c["bi_opt"], c["um_opt"] = p["bi_opt"][pol], p["um_opt"][pol]
    c["bi_pp"], c["bi_pa"] = bi[p["bi_opt"][pol], 0], bi[p["bi_opt"][pol], 1]
    c["um_pp"], c["um_pa"] = bi[p["um_opt"][pol], 0], bi[p["um_opt"][pol], 1]
    c["pd_lim"] = np.array(C.PD_LIMITS)[p["bi_opt"][pol]]
    c["med_lim"] = np.array(C.MED_LIMITS)[p["med_opt"][pol]]
    c["has_coll"], c["has_comp"] = v["has_coll"][V], v["has_comp"][V]
    c["coll_ded"] = np.array(C.COLL_DEDUCTIBLES)[v["coll_ded_opt"][V]]
    c["comp_ded"] = np.array(C.COMP_DEDUCTIBLES)[v["comp_ded_opt"][V]]
    c["glass_ded"] = np.where(v["full_glass"][V], 0, c["comp_ded"])
    c["has_rent"], c["rent_opt"], c["has_tow"] = v["has_rent"][V], v["rent_opt"][V], v["has_tow"][V]
    c["acv"] = actual_cash_value(v["msrp"][V], v["model_year"][V], mid, cal, level_day=cost)
    age = (cal.year_frac(mid) - v["model_year"][V] + 0.5).clip(0)
    c["repair"] = (v["msrp"][V] / 32_000) ** 0.5 * np.where(adas, 1.12, 1.0) * np.where(v["segment"][V] == "ev", 1.15, 1.0) \
        * np.clip(1.05 - 0.012 * age, 0.80, 1.05)
    c["adas"], c["pd_factor"], c["bi_factor"], c["park"] = adas, v["pd_factor"][V], v["bi_factor"][V], park
    c["model_year"] = v["model_year"][V]
    c["p_bi"] = np.clip(C.P_BI_GIVEN_AF_MV * crash ** C.BI_TERRITORY_EXPONENT, 0, 0.6)
    c["p_un"] = zt["p_other_driver_uninsured"][zi]
    c["cost"] = cost
    return c


def _trend(cal, key, day):
    return cal.sev_trend[key][np.clip(day, 0, cal.horizon)]


# ---------------------------------------------------------------------------- expected losses
def expected(c: dict, cal: Calendar) -> dict:
    """Expected net loss by coverage for each vehicle over its window (catastrophes excluded)."""
    n = {k: c["rate"][k] * c["expo"][k] for k in c["rate"]}
    col = lambda a: np.asarray(a, dtype=float)[:, None]
    t = {k: col(_trend(cal, k, c["cost"])) for k in C.SEVERITY_TREND}
    E = {}
    e_pd = pd_paid(ZG, col(c["pd_lim"]), col(c["pd_factor"]), t["PD"]).mean(1)
    E["PD"] = (n["AF_MV"] * C.P_PD_GIVEN_AF_MV + n["AF_SV"] * C.P_PD_GIVEN_AF_SV) * (1 - C.CWP["PD"]) * e_pd
    tb = t["BI"][:, 0]
    e_bi = injury_paid(ZG, col(c["bi_pp"]), col(c["bi_factor"]), t["BI"], C.BI_SEV).mean(1) \
        * aggregate_share("BI", c["bi_opt"], c["bi_factor"] * tb)
    E["BI"] = (n["AF_MV"] * c["p_bi"] + n["AF_SV"] * C.P_BI_GIVEN_AF_SV) * MEAN_CLAIMANTS * (1 - C.CWP["BI"]) * e_bi
    e_um = injury_paid(ZG, col(c["um_pp"]), 1.0, t["BI"], C.UM_SEV).mean(1) * aggregate_share("UM", c["um_opt"], tb)
    g = C.UM_SEV["median"] * t["BI"] * np.exp(C.UM_SEV["sigma"] * ZG)      # underinsured: the excess over the other limit
    e_uim = sum(w * underinsured(g, col(c["um_pp"]), lim)[0].mean(1) for lim, w in C.OTHER_DRIVER_BI_LIMIT.items()) \
        * aggregate_share("UIM", c["um_opt"], tb) * has_uim(c)
    E["UM"] = n["NAF"] * C.P_UM_INJURY * MEAN_CLAIMANTS * (1 - C.CWP["UM"]) * (c["p_un"] * e_um + (1 - c["p_un"]) * e_uim)
    e_med = med_paid(ZG, col(np.maximum(c["med_lim"], 1)), t["BI"]).mean(1)
    E["MED"] = (c["med_lim"] > 0) * sum(n[k] * q for k, q in C.P_MED.items()) * (1 - C.CWP["MED"]) * e_med

    coll = np.zeros(c["n"])
    tow_back = {}                                  # expected tows recovered by subrogation, per peril
    rentals = np.zeros((c["n"], 2))                # expected paid repairs and total losses that lead to a rental
    acv, ded, rep = col(c["acv"]), col(c["coll_ded"]), col(c["repair"])
    for k in DRIVING_PERILS:
        _, paid, total = collision(ZG, C.COLL_PERIL_SEV[k], rep, t["COLL"], acv, ded)
        net = (paid - np.minimum(total * acv * MEAN_SALVAGE, paid)).mean(1) * (1 - C.CWP["COLL"])
        if k == "NAF":
            insured_other = C.P_FILE_COLL["NAF"] * (1 - C.P_SUBROGATION["NAF"] * MEAN_SUBRO)
            coll += n[k] * net * (c["p_un"] * C.P_FILE_COLL["NAF_UNINSURED"] + (1 - c["p_un"]) * insured_other)
            filed = c["p_un"] * C.P_FILE_COLL["NAF_UNINSURED"] + (1 - c["p_un"]) * C.P_FILE_COLL["NAF"]
        else:
            coll += n[k] * net * C.P_FILE_COLL[k] * (1 - C.P_SUBROGATION.get(k, 0.0) * MEAN_SUBRO)
            filed = C.P_FILE_COLL[k]
        paid_n = n[k] * filed * (1 - C.CWP["COLL"])
        # recovered with the collision payment: the share of filed claims subrogated (NAF: only an insured other driver)
        recovered = C.P_SUBROGATION.get(k, 0.0) * MEAN_SUBRO * (C.P_FILE_COLL[k] * (1 - c["p_un"]) / filed if k == "NAF" else 1.0)
        rentals += (paid_n * (1 - recovered))[:, None] * np.stack([((paid > 0) & ~total).mean(1), ((paid > 0) & total).mean(1)], axis=1)
        tow_back[k] = c["has_coll"] * n[k] * C.P_FILE_COLL[k] * (1 - c["p_un"] if k == "NAF" else 1.0) * (1 - C.CWP["COLL"]) * (paid > 0).mean(1) \
            * C.P_SUBROGATION.get(k, 0.0) * MEAN_SUBRO
    E["COLL"] = c["has_coll"] * coll

    comp = np.zeros(c["n"])
    for k in COMP_PERILS:
        gross, total = comp_gross(k, ZG, UG, rep, col(c["adas"]).astype(bool), t["COMP"], acv)
        paid = np.maximum(gross - col(c["glass_ded"] if k == "GLASS" else c["comp_ded"]), 0)
        salvage = np.minimum(salvageable(k, total, UG) * acv * MEAN_SALVAGE, paid)
        comp += n[k] * (paid - salvage).mean(1) * (1 - C.CWP["COMP"])
        if k != "GLASS":
            rentals += (n[k] * (1 - C.CWP["COMP"]))[:, None] * np.stack(
                [((paid > 0) & ~total).mean(1), ((paid > 0) & total).mean(1)], axis=1)
    E["COMP"] = c["has_comp"] * comp
    per_rental = RENTAL_MEAN[c["rent_opt"]]
    E["RENT"] = c["has_rent"] * C.RENTAL_USE_P * (1 - C.CWP["RENT"]) * (rentals * per_rental).sum(1)
    E["TOW"] = c["has_tow"] * (1 - C.CWP["TOW"]) * TOW_MEAN \
        * sum(n[k] * q - tow_back.get(k, 0.0) * q for k, q in C.TOW_P.items() if k in n)     # catastrophes aside
    return E


def salvageable(peril: str, total, u):
    """Total losses that leave a wreck to sell (every one except a theft that is never recovered)."""
    return total & ~((peril == "THEFT_TOTAL") & (u >= 0.40))


# ---------------------------------------------------------------------------- claim simulation
def _pick_driver(c, key, vi, rng):
    q = vi + rng.random(len(vi)) * (1 - 2e-9)
    return c["u_drv"][np.searchsorted(c[key], q)]


def simulate(c: dict, st: Static, cal: Calendar, rng: np.random.Generator, occ_offset: int):
    """Simulate losses for the vehicles in context c. Returns (occurrences, features, wrecks, crash deaths, next
    occurrence id). A crash death (occ, vrow, pol, drv, day, death_delay) is a listed driver killed in a crash, at
    the wheel or riding along.
    An occurrence is one loss event; a feature is one coverage (and claimant) paying on it. A wreck is a
    vehicle destroyed or stolen without a company-paid total loss (no physical damage cover, the other
    driver's insurer paid, or the claim was not paid); it leaves the policy all the same."""
    occs, feats, wrecks = [], [], []
    n_occ = occ_offset
    severity = []                                      # each occurrence's severity (config.CRASH_SEVERITY_CORR)
    rho = C.CRASH_SEVERITY_CORR

    def sev(ids, key):
        """Standard normal draws for occurrences `ids`, correlated with their severity."""
        return correlated(np.concatenate(severity)[np.asarray(ids, dtype=np.int64) - occ_offset], rho[key], rng)

    def happens(ids, key, p):
        """Whether something with probability p happens on each occurrence, likelier the more severe it is."""
        return normal_cdf(-sev(ids, key)) < p

    def wreck(vi, day, ids):
        wrecks.append(pd.DataFrame(dict(vrow=vi, day=day, occ=ids)))

    def settle_total(paid, total, salvage_value, vi, day, hail=False):
        """Paid total losses: usually the insurer takes the wreck and sells it; a few owners keep it, and
        the salvage value comes off the settlement instead. Illinois allows that only for hail damage or a
        car 9 or more model years old, and a lender or lessor would not give up its security for a wreck, so only
        a car owned outright is kept. Returns (paid, salvage recovery, owner retained)."""
        eligible = hail | (cal.year[np.clip(day, 0, cal.horizon - 1)] - c["model_year"][vi] >= C.OWNER_RETAINED_MIN_AGE)
        eligible &= st.v["ownership"][c["V"][vi]] == "Owned"
        retained = total & eligible & (salvage_value > 0) & (paid - salvage_value > 0) \
            & (rng.random(len(paid)) < C.P_OWNER_RETAINED_SALVAGE)
        salvage = np.where(retained, 0.0, np.minimum(total * salvage_value, paid))
        return np.where(retained, paid - salvage_value, paid), salvage, retained

    def new_occurrences(peril, vi, day, driver, at_fault=False, cat=-1, uninsured=None):
        nonlocal n_occ
        ids = np.arange(n_occ, n_occ + len(vi))
        n_occ += len(vi)
        severity.append(rng.standard_normal(len(vi)))
        occs.append(pd.DataFrame(dict(occ=ids, vrow=vi, veh=c["V"][vi], pol=c["pol"][vi], day=day, peril=peril, drv=driver,
                                      at_fault=at_fault, cat=cat,
                                      other_uninsured=False if uninsured is None else uninsured)))
        return ids

    def add(cov, ids, gross, paid, cwp, claimant=1, total=False, salvage=0.0, subro=0.0, retained=False, nominal=False,
            um_type="", offset=0.0, cap=np.inf, room=np.inf, rent_days=0, death=False, injured=-1):
        """cap: the most the feature could pay under the policy (its per-person or per-claim limit, or the car's
        value less the deductible); room: for injury coverages, what the per-accident limit allows for all the
        accident's claimants under the coverage together. Case reserves obey both, the second shared among the
        claimants from what the adjuster knows at each review (claims._share_accident_limit). rent_days: how long a
        rental car was kept (the rental is paid once it is returned). injured: the policy's listed driver the
        feature is for (its own people's medical payments and uninsured motorist claims), -1 for anyone else. death:
        that person died in the crash (simulate._crash_deaths takes them off the policy)."""
        feats.append(pd.DataFrame(dict(occ=ids, cvg=cov, claimant=claimant, gross=gross, paid=np.where(cwp, 0.0, paid),
                                       cwp=cwp, total=total, salvage=salvage, subro=subro, retained=retained,
                                       nominal=nominal, um_type=um_type, offset=offset, cap=cap, room=room,
                                       rent_days=rent_days, death=death, injured=injured)))

    died = []                                          # (occurrence, days from the crash to the death)

    drivers = st.pop.drv
    on = drivers[drivers.active.to_numpy()]
    household = pd.DataFrame(dict(pol=on.pol.to_numpy(), pid=on.drv.to_numpy(), role=on.role.to_numpy(),
                                  dob=on.dob_day.to_numpy()))

    def fatal(ids, vi, peril, driver, day):
        """Who dies in each crash (config.CRASH_DEATH_*, RIDE_ALONG_P): the insured at the wheel, and the household's
        other listed drivers riding along, likelier in a severe crash. All of a crash's dead die the same day.
        Returns (the driver died, the dead passengers: i, the index into ids, and pid)."""
        frail = lambda age: np.interp(age, C.CRASH_DEATH_AGE_KNOTS, C.CRASH_DEATH_AGE_FACTOR)
        p = C.CRASH_DEATH_P[peril] * frail((day - drivers.dob_day.to_numpy()[driver]) / 365.25)
        dies = happens(ids, "DEATH", p)
        later = rng.random(len(ids)) >= C.CRASH_DEATH_SAME_DAY_P
        delay = np.where(later, np.minimum(1 + np.floor(rng.exponential(C.CRASH_DEATH_DELAY_MEAN, len(ids))),
                                           C.CRASH_DEATH_DELAY_MAX), 0).astype(np.int64)
        ride = pd.DataFrame(dict(i=np.arange(len(ids)), pol=c["pol"][vi], driver=driver)).merge(household, on="pol")
        ride = ride[ride.pid.to_numpy() != ride.driver.to_numpy()]
        ride = ride[rng.random(len(ride)) < np.array(C.RIDE_ALONG_P)[ride.role.to_numpy()]]
        i = ride.i.to_numpy()
        p_ride = C.CRASH_DEATH_P[peril] * C.PASSENGER_DEATH_FACTOR * frail((day[i] - ride.dob.to_numpy()) / 365.25)
        gone = happens(ids[i], "DEATH", p_ride)
        pas = pd.DataFrame(dict(i=i[gone], pid=ride.pid.to_numpy()[gone])).sort_values(["i", "pid"], kind="stable")
        died.append(pd.DataFrame(dict(occ=ids[dies], victim=driver[dies], death_delay=delay[dies])))
        died.append(pd.DataFrame(dict(occ=ids[pas.i.to_numpy()], victim=pas.pid.to_numpy(), death_delay=delay[pas.i.to_numpy()])))
        return dies, pas

    n_house = np.bincount(on.pol.to_numpy(), minlength=int(c["pol"].max()) + 1 if len(c["pol"]) else 0)

    def no_one_left(vi, dies, pas):
        """The crash killed every listed driver of the household: no one is left to need a rental car."""
        return n_house[c["pol"][vi]] - dies - np.bincount(pas.i.to_numpy(), minlength=len(vi)) <= 0

    def passengers_of(pas, m):
        """The dead passengers of the crashes selected by mask m, indexed into the selection."""
        pos = np.cumsum(m) - 1
        sel = pas[m[pas.i.to_numpy()]]
        return sel.assign(i=pos[sel.i.to_numpy()])

    def death_claim(gross, limit, dies):
        """A death claim is valued far above the policy's limit for the person (wrongful death, medical and funeral
        costs), so it pays the limit."""
        return np.where(dies, np.maximum(gross, limit * rng.uniform(1.5, 4.0, len(gross))), gross)

    def injury_lift(p, sigma):
        """Injuries happen in the more severe crashes, and are worse there: divided by this, the injury costs of
        the crashes with one keep the average they are calibrated to (selection_lift)."""
        return selection_lift(p, rho["INJURY"] * rho["INJURY_SEV"], sigma)

    def injury_features(cov, ids, vi, day, dist, pp, pa, factor, p, dies=None, pas=None, driver=None):
        """For uninsured motorist claims, the policy's own people: the insured driver is the first claimant (dies:
        died in the crash), and the household's dead passengers (pas) the next ones; other claimants are not."""
        if len(ids) == 0:
            return
        k = 1 + rng.choice(4, len(ids), p=C.BI_CLAIMANTS_P)
        n_pas = np.zeros(len(ids), dtype=np.int64) if pas is None else np.bincount(pas.i.to_numpy(), minlength=len(ids))
        k = np.maximum(k, 1 + n_pas)
        o = np.repeat(np.arange(len(ids)), k)
        claimant = np.arange(len(o)) - np.repeat(np.cumsum(k) - k, k) + 1
        injured = np.full(len(o), -1, dtype=np.int64)
        if driver is not None:
            injured[claimant == 1] = driver[o[claimant == 1]]
        if pas is not None and len(pas):
            rank = pas.groupby("i").cumcount().to_numpy()
            at = np.searchsorted(o, pas.i.to_numpy()) + 1 + rank          # claimants 2, 3, ... of the crash
            injured[at] = pas.pid.to_numpy()
        lift = injury_lift(np.broadcast_to(p, len(ids)), dist["sigma"])[o]
        gross = dist["median"] * factor[o] * _trend(cal, "BI", day[o]) * np.exp(dist["sigma"] * sev(ids[o], "INJURY_SEV")) / lift
        death = np.zeros(len(o), dtype=bool) if dies is None else dies[o] & (claimant == 1)
        if pas is not None and len(pas):
            death[at] = True
        gross = round_settlement(death_claim(gross, pp[o], death), rng)
        cwp = (rng.random(len(o)) < C.CWP[cov]) & ~death                 # a death claim is paid
        paid = cap_per_accident(np.where(cwp, 0.0, np.minimum(gross, pp[o])), o, len(ids), pa)   # per-accident limit
        add(cov, ids[o], gross, paid, cwp, claimant=claimant, um_type="Uninsured" if cov == "UM" else "",
            cap=pp[o], room=pa[o], death=death, injured=injured)

    def collision_features(peril, ids, vi, day, file_p, subro_p, no_rental=None):
        # the damage to the insured car happens whether or not anyone claims it from us
        z = sev(ids, "COLL")
        gross, paid, total = collision(z, C.COLL_PERIL_SEV[peril], c["repair"][vi],
                                       _trend(cal, "COLL", day), c["acv"][vi], c["coll_ded"][vi])
        filed = c["has_coll"][vi] & (rng.random(len(vi)) < file_p)
        below = paid <= 0
        withdrawn = c["has_coll"][vi] & ~filed & (rng.random(len(vi)) < C.P_FIRST_PARTY_WITHDRAWN)
        keep = filed & (~below | (rng.random(len(vi)) < C.P_FILE_BELOW_DEDUCTIBLE)) | withdrawn
        cwp = below | withdrawn | (rng.random(len(vi)) < C.CWP["COLL"])
        paid = np.where(cwp, 0.0, paid)
        paid_total = total & (paid > 0) & filed
        paid, salvage, retained = settle_total(paid, paid_total, total * c["acv"][vi] * rng.uniform(*C.SALVAGE_RANGE, len(vi)), vi, day)
        share = (rng.random(len(vi)) < subro_p) * rng.uniform(*C.SUBROGATION_SHARE, len(vi))
        subro = share * (paid - salvage)
        add("COLL", ids[keep], gross[keep], paid[keep], cwp[keep], total=paid_total[keep], salvage=salvage[keep],
            subro=subro[keep], retained=retained[keep], cap=np.maximum(c["acv"][vi] - c["coll_ded"][vi], 0.0)[keep])
        paid_now = keep & (paid > 0)
        # the other driver's insurer that pays back the repair pays back the rental and the tow in the same share;
        # no rental when the crash killed everyone in the household who drives
        rent = paid_now & (True if no_rental is None else ~no_rental)
        rental(ids[rent], vi[rent], total[rent], z[rent], share[rent])
        tow(ids, vi, peril, np.where(paid_now, share, 0.0))
        w = total & ~(keep & paid_total)
        wreck(vi[w], day[w], ids[w])

    def med_features(ids, vi, day, p, dies, pas, driver):
        """Medical payments for the insured driver (dies: died in the crash; the claim then pays its limit, not a
        part of it), and for each of the household's passengers who died (claimants 2, 3, ...)."""
        covered = c["med_lim"][vi] > 0
        m = covered & (happens(ids, "MED", p) | dies)
        if m.any():
            i, lim = np.flatnonzero(m), c["med_lim"][vi[m]]
            lift = selection_lift(np.broadcast_to(p, len(m))[m], rho["MED"] ** 2, C.MED_SEV["sigma"])
            gross = C.MED_SEV["median"] * _trend(cal, "BI", day[i]) * np.exp(C.MED_SEV["sigma"] * sev(ids[i], "MED")) / lift
            gross = death_claim(gross, lim, dies[i])
            add("MED", ids[i], gross, np.minimum(gross, lim), (rng.random(len(i)) < C.CWP["MED"]) & ~dies[i],
                cap=lim, death=dies[i], injured=driver[i])
        dead = pas[covered[pas.i.to_numpy()]]
        if len(dead):
            i, lim = dead.i.to_numpy(), c["med_lim"][vi[dead.i.to_numpy()]]
            gross = death_claim(np.zeros(len(i)), lim, np.ones(len(i), dtype=bool))
            add("MED", ids[i], gross, lim, np.zeros(len(i), dtype=bool), claimant=2 + dead.groupby("i").cumcount().to_numpy(),
                cap=lim, death=True, injured=dead.pid.to_numpy())

    def rental(ids, vi, total, damage=None, share=None):
        """Rental reimbursement while a covered car is repaired, or replaced after a total loss. `damage`: the
        collision damage draws, when the rental follows a repair (a bigger repair keeps the car in the shop longer).
        `share`: the part of the collision payment recovered by subrogation, recovered on the rental too."""
        m = c["has_rent"][vi] & (rng.random(len(vi)) < C.RENTAL_USE_P)
        ids, vi, total = ids[m], vi[m], total[m]
        share = np.zeros(len(ids)) if share is None else share[m]
        if len(ids) == 0:
            return
        med = np.where(total, C.RENTAL_DAYS["total"]["median"], C.RENTAL_DAYS["repair"]["median"])
        sig = np.where(total, C.RENTAL_DAYS["total"]["sigma"], C.RENTAL_DAYS["repair"]["sigma"])
        z = rng.standard_normal(len(ids)) if damage is None else correlated(damage[m], rho["RENT_DAYS"], rng)
        days = np.ceil(med * np.exp(sig * z))
        cost = C.RENTAL_DAILY_COST["median"] * np.exp(C.RENTAL_DAILY_COST["sigma"] * rng.standard_normal(len(ids)))
        daily, most = np.array(C.RENTAL_OPTIONS)[c["rent_opt"][vi]].T
        paid, cwp = np.minimum(days * np.minimum(cost, daily), most), rng.random(len(ids)) < C.CWP["RENT"]
        add("RENT", ids, days * cost, paid, cwp, subro=np.where(cwp, 0.0, share * paid), cap=most, rent_days=days)

    def tow(ids, vi, peril, share=None):
        m = c["has_tow"][vi] & happens(ids, "TOW", C.TOW_P.get(peril, 0.0))
        cost = C.TOW_COST["median"] * np.exp(C.TOW_COST["sigma"] * rng.standard_normal(m.sum()))
        paid, cwp = np.minimum(cost, C.TOWING_LIMIT), rng.random(m.sum()) < C.CWP["TOW"]
        back = 0.0 if share is None else np.where(cwp, 0.0, share[m] * paid)
        add("TOW", ids[m], cost, paid, cwp, subro=back, cap=C.TOWING_LIMIT)

    def uim_features(ids, vi, day, dies, pas, driver):
        """Underinsured motorist: the insured's injury damages above what the at-fault driver's insurer pays,
        within the policy's own per-person limit and, for the accident, its per-accident limit less
        everything that insurer paid (215 ILCS 5/143a-2(4): the limits less amounts actually recovered)."""
        if len(ids) == 0:
            return
        k = 1 + rng.choice(4, len(ids), p=C.BI_CLAIMANTS_P)
        k = np.maximum(k, 1 + np.bincount(pas.i.to_numpy(), minlength=len(ids)))
        o = np.repeat(np.arange(len(ids)), k)
        claimant = np.arange(len(o)) - np.repeat(np.cumsum(k) - k, k) + 1
        injured = np.full(len(o), -1, dtype=np.int64)
        injured[claimant == 1] = driver[o[claimant == 1]]
        at = np.searchsorted(o, pas.i.to_numpy()) + 1 + pas.groupby("i").cumcount().to_numpy()
        injured[at] = pas.pid.to_numpy()
        lift = injury_lift(C.P_UM_INJURY, C.UM_SEV["sigma"])
        gross = C.UM_SEV["median"] * _trend(cal, "BI", day[o]) * np.exp(C.UM_SEV["sigma"] * sev(ids[o], "INJURY_SEV")) / lift
        other_pp, other_pa = other_driver_limits(rng, len(ids))
        # a death is valued above both the other driver's limit and the policy's own (dies: the first claimant)
        death = dies[o] & (claimant == 1)
        death[at] = True
        gross = round_settlement(death_claim(gross, other_pp[o] + c["um_pp"][vi][o], death), rng)
        excess, other = underinsured(gross, c["um_pp"][vi][o], other_pp[o], o, len(ids), other_pa)
        cwp = (rng.random(len(o)) < C.CWP["UM"]) & ~death
        room = c["um_pa"][vi] - np.bincount(o, other, len(ids))
        paid = cap_per_accident(np.where(cwp, 0.0, excess), o, len(ids), room)
        cap = np.maximum(c["um_pp"][vi][o] - other, 0.0)
        keep = (excess > 0) & (cwp | (paid > 0))
        add("UM", ids[o][keep], gross[keep], paid[keep], cwp[keep], claimant=claimant[keep], um_type="Underinsured",
            offset=np.round(other[keep], 2), cap=cap[keep], room=np.maximum(room, 0.0)[o][keep], death=death[keep],
            injured=injured[keep])

    def unpaid(cov, ids, p):
        """Claims opened and closed without payment: liability denied, or an injury claim never pursued."""
        ids = ids[rng.random(len(ids)) < p]
        add(cov, ids, np.zeros(len(ids)), np.zeros(len(ids)), np.ones(len(ids), dtype=bool), nominal=True)

    def draw(peril, group=None, mask=None):
        """Loss events of one peril: (vehicle row, day). `group` picks the calendar intensity (default the
        peril's own); new customers' extra claims fall early in the policy's life (new_customer_days)."""
        g = group or PERIL_GROUP[peril]
        extra = peril in C.NEW_CUSTOMER_PERILS
        lam = c["rate"][peril] * cal.exposure(g, c["s"], c["x"]) * (c["nc"] if extra else 1.0)
        if mask is not None:
            lam = lam * mask
        vi = np.repeat(np.arange(c["n"]), rng.poisson(lam))
        day = cal.sample_days(g, c["s"][vi], c["x"][vi], rng)
        if extra and len(vi):
            early = rng.random(len(vi)) < 1 - 1 / c["nc"][vi]
            lo, hi = np.clip(c["s"][vi], 0, cal.horizon), np.clip(c["x"][vi], 0, cal.horizon)
            # early in the policy's life, but on the days crashes happen: the decay weighted by the daily index
            daily = np.diff(cal.cum[g])
            top, todo = daily.max(), np.flatnonzero(early)
            for _ in range(60):
                if len(todo) == 0:
                    break
                cand = new_customer_days(c["t0"][vi[todo]], lo[todo], hi[todo], rng)
                ok = rng.random(len(todo)) * top < daily[np.clip(cand, 0, len(daily) - 1)]
                day[todo[ok]] = cand[ok]
                todo = todo[~ok]
        return vi, day

    # --- driving perils ---
    vi, day = draw("AF_MV")
    who = _pick_driver(c, "key_af", vi, rng)
    ids = new_occurrences("AF_MV", vi, day, who, at_fault=True)
    dies, pas = fatal(ids, vi, "AF_MV", who, day)
    m = rng.random(len(vi)) < C.P_PD_GIVEN_AF_MV
    g = pd_paid(sev(ids[m], "PD"), np.inf, c["pd_factor"][vi[m]], _trend(cal, "PD", day[m]))
    add("PD", ids[m], g, np.minimum(g, c["pd_lim"][vi[m]]), rng.random(m.sum()) < C.CWP["PD"], cap=c["pd_lim"][vi[m]])
    m = happens(ids, "INJURY", c["p_bi"][vi])
    injury_features("BI", ids[m], vi[m], day[m], C.BI_SEV, c["bi_pp"][vi[m]], c["bi_pa"][vi[m]], c["bi_factor"][vi[m]],
                    c["p_bi"][vi[m]])
    unpaid("BI", ids[~m], C.P_INJURY_NOT_PURSUED["AF_MV"])
    collision_features("AF_MV", ids, vi, day, C.P_FILE_COLL["AF_MV"], 0.0, no_one_left(vi, dies, pas))
    med_features(ids, vi, day, C.P_MED["AF_MV"], dies, pas, who)

    vi, day = draw("AF_SV")
    who = _pick_driver(c, "key_af", vi, rng)
    ids = new_occurrences("AF_SV", vi, day, who, at_fault=True)
    dies, pas = fatal(ids, vi, "AF_SV", who, day)
    m = rng.random(len(vi)) < C.P_PD_GIVEN_AF_SV
    g = pd_paid(sev(ids[m], "PD"), np.inf, c["pd_factor"][vi[m]], _trend(cal, "PD", day[m]))
    add("PD", ids[m], g, np.minimum(g, c["pd_lim"][vi[m]]), rng.random(m.sum()) < C.CWP["PD"], cap=c["pd_lim"][vi[m]])
    m = happens(ids, "INJURY", C.P_BI_GIVEN_AF_SV)
    injury_features("BI", ids[m], vi[m], day[m], C.BI_SEV, c["bi_pp"][vi[m]], c["bi_pa"][vi[m]], c["bi_factor"][vi[m]],
                    C.P_BI_GIVEN_AF_SV)
    unpaid("BI", ids[~m], C.P_INJURY_NOT_PURSUED["AF_SV"])
    collision_features("AF_SV", ids, vi, day, C.P_FILE_COLL["AF_SV"], 0.0, no_one_left(vi, dies, pas))
    med_features(ids, vi, day, C.P_MED["AF_SV"], dies, pas, who)

    vi, day = draw("NAF")
    unins = rng.random(len(vi)) < c["p_un"][vi]
    who = _pick_driver(c, "key_any", vi, rng)
    ids = new_occurrences("NAF", vi, day, who, uninsured=unins)
    dies, pas = fatal(ids, vi, "NAF", who, day)
    hurt = happens(ids, "INJURY", C.P_UM_INJURY) | dies | np.isin(np.arange(len(ids)), pas.i.to_numpy())
    m = unins & hurt
    injury_features("UM", ids[m], vi[m], day[m], C.UM_SEV, c["um_pp"][vi[m]], c["um_pa"][vi[m]], np.ones(m.sum()),
                    C.P_UM_INJURY, dies[m], passengers_of(pas, m), who[m])
    uim = ~unins & hurt & has_uim(c)[vi]
    uim_features(ids[uim], vi[uim], day[uim], dies[uim], passengers_of(pas, uim), who[uim])
    alone = no_one_left(vi, dies, pas)
    collision_features("NAF", ids[unins], vi[unins], day[unins], C.P_FILE_COLL["NAF_UNINSURED"], 0.0, alone[unins])
    collision_features("NAF", ids[~unins], vi[~unins], day[~unins], C.P_FILE_COLL["NAF"], C.P_SUBROGATION["NAF"],
                       alone[~unins])
    med_features(ids, vi, day, C.P_MED["NAF"], dies, pas, who)
    unpaid("PD", ids, C.P_LIABILITY_DENIED["PD"])
    unpaid("BI", ids, C.P_LIABILITY_DENIED["BI"])

    vi, day = draw("PARKED")
    ids = new_occurrences("PARKED", vi, day, np.full(len(vi), -1))
    collision_features("PARKED", ids, vi, day, C.P_FILE_COLL["PARKED"], C.P_SUBROGATION["PARKED"])

    # --- comprehensive perils ---
    def comp_features(peril, vi, day, cat=-1):
        if len(vi) == 0:
            return
        u = rng.random(len(vi))
        gross, total = comp_gross(peril, rng.standard_normal(len(vi)), u, c["repair"][vi], c["adas"][vi],
                                  _trend(cal, "COMP", day), c["acv"][vi])
        covered = c["has_comp"][vi]
        paid = np.maximum(gross - (c["glass_ded"] if peril == "GLASS" else c["comp_ded"])[vi], 0.0)
        below = paid <= 0
        keep = covered & (~below | (rng.random(len(vi)) < C.P_FILE_BELOW_DEDUCTIBLE))
        cwp = below | (rng.random(len(vi)) < C.CWP["COMP"])
        towed = c["has_tow"][vi] & (rng.random(len(vi)) < C.TOW_P.get(peril, 0.0))
        paid_total = total & ~cwp
        salvage_value = salvageable(peril, total, u) * c["acv"][vi] * rng.uniform(*C.SALVAGE_RANGE, len(vi))
        paid, salvage, retained = settle_total(np.where(cwp, 0.0, paid), paid_total, salvage_value, vi, day,
                                               hail=peril in ("WEATHER", "HAIL_CAT"))
        ids = np.full(len(vi), -1)
        need = keep | towed
        ids[need] = new_occurrences(peril, vi[need], day[need], np.full(need.sum(), -1), cat=cat)
        ded = (c["glass_ded"] if peril == "GLASS" else c["comp_ded"])[vi]
        add("COMP", ids[keep], gross[keep], paid[keep], cwp[keep], total=paid_total[keep], salvage=salvage[keep],
            retained=retained[keep], cap=np.maximum(c["acv"][vi] - ded, 0.0)[keep])
        paid_now = keep & ~cwp & (paid > 0) & (peril != "GLASS")
        rental(ids[paid_now], vi[paid_now], total[paid_now])
        cost = C.TOW_COST["median"] * np.exp(C.TOW_COST["sigma"] * rng.standard_normal(towed.sum()))
        add("TOW", ids[towed], cost, np.minimum(cost, C.TOWING_LIMIT), rng.random(towed.sum()) < C.CWP["TOW"], cap=C.TOWING_LIMIT)
        w = total & ~(keep & paid_total)
        wreck(vi[w], day[w], ids[w])

    for peril in COMP_PERILS:
        if peril == "THEFT_TOTAL":
            for group, mask in (("theft", ~c["kh"]), ("theft_kh", c["kh"])):
                comp_features(peril, *draw(peril, group, mask))
        else:
            comp_features(peril, *draw(peril))

    for i, (_, date, _, peril, *_rest) in enumerate(C.CAT_EVENTS):
        d = int((np.datetime64(date) - cal.start).astype(int))
        if not 0 <= d <= cal.valuation_day:
            continue
        p_hit = st.cat_p[i][c["zi"]] * np.array(C.PARKING_WEATHER_FACTOR)[c["park"]] * ((c["s"] <= d) & (d < c["x"]))
        if "idle" in c:                                  # a car kept on a salvage title after a total loss
            p_hit = p_hit * ~c["idle"]
        vi = np.flatnonzero(rng.random(c["n"]) < p_hit)
        comp_features(peril, vi, np.full(len(vi), d), cat=i)

    occ = pd.concat(occs, ignore_index=True) if occs else pd.DataFrame()
    feat = pd.concat(feats, ignore_index=True) if feats else pd.DataFrame()
    # the insured who died in a crash: the death stands whether or not anything is claimed for it
    dead = pd.concat(died, ignore_index=True) if died else pd.DataFrame(dict(occ=[], victim=[], death_delay=[]))
    cols = ["occ", "vrow", "pol", "drv", "day", "death_delay"]
    deaths = occ.drop(columns="drv").merge(dead, on="occ").rename(columns={"victim": "drv"})[cols] if len(occ) else \
        pd.DataFrame(columns=cols)
    occ = occ[occ.occ.isin(feat.occ)].reset_index(drop=True)      # a loss with no payable coverage is not a claim
    wrecks = pd.concat(wrecks, ignore_index=True)
    wrecks.loc[~wrecks.occ.isin(occ.occ), "occ"] = -1
    return occ, feat, wrecks, deaths, n_occ
