"""The true risk model: how often each vehicle has a loss, and what it costs.

The same severity functions are used twice: with random draws to simulate claims, and
on a fixed grid of quantiles to compute the exact expected loss of every vehicle. The
expected loss is what the rating plan is fitted to, and it is written to the answer key.
"""
from __future__ import annotations

from dataclasses import dataclass

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


def actual_cash_value(msrp, model_year, day, cal: Calendar) -> np.ndarray:
    age = (cal.year_frac(day) - np.asarray(model_year) + 0.5).clip(0)
    dep = np.maximum(0.95 * np.exp(-0.145 * age), 0.07)
    return np.maximum(np.asarray(msrp) * dep * cal.used_car[np.clip(day, 0, cal.horizon)], 1200.0)


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
        v["seg_code"] = np.array([SEGMENTS.index(x) for x in seg])
        v["use_factor"] = np.where(v["use"] == "Business", C.BUSINESS_USE_FACTOR, 1.0)
        v["zi"] = self.p["zi"][v["pol"]]
        return v

    def retire(self, old: np.ndarray, day: np.ndarray, reason: int) -> None:
        """Take vehicles `old` off their policies from `day` (the first day they are not insured)."""
        self.v["active"][old] = False
        self.v["removed_day"][old] = day
        self.v["removal_reason"][old] = reason

    def add_replacements(self, old: np.ndarray, new: pd.DataFrame) -> None:
        """Add vehicles `new` (one per entry of `old`), which inherit the drivers of the vehicles they replace."""
        first_new = len(self.v["pol"])
        add = self._columns(new[[c for c in self.v if c in new.columns]])
        self.v = {k: np.concatenate([a, add[k]]) for k, a in self.v.items()}
        new_id = np.full(first_new, -1)
        new_id[old] = first_new + np.arange(len(old))
        m = new_id[self.u_veh] >= 0
        self.u_veh = np.concatenate([self.u_veh, new_id[self.u_veh[m]]])
        self.u_drv = np.concatenate([self.u_drv, self.u_drv[m]])
        self.u_w = np.concatenate([self.u_w, self.u_w[m]])

    def set_usage(self, usage: pd.DataFrame) -> None:
        self.u_veh, self.u_drv, self.u_w = usage.veh.to_numpy(), usage.drv.to_numpy(), usage.weight.to_numpy()


def set_window(c: dict, cal: Calendar, s: np.ndarray, x: np.ndarray) -> None:
    """Change the exposure window of a context (used when a total loss ends a vehicle's cover early).
    Severity and vehicle value stay as simulated; only the exposure behind the expected loss changes."""
    c["s"], c["x"] = s, x
    c["expo"] = {k: cal.exposure(PERIL_GROUP[k], s, x) for k in c["rate"]}
    c["expo"]["THEFT_TOTAL"] = np.where(c["kh"], cal.exposure("theft_kh", s, x), c["expo"]["THEFT_TOTAL"])


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
    drive = mile ** C.MILEAGE_ELASTICITY * v["use_factor"][V] * v["seg_freq"][V]
    adas = v["adas"][V]
    park = v["parking"][V]
    B = C.BASE_RATE
    c["rate"] = {
        "AF_MV": B["AF_MV"] * c["h_af"] * drive * np.where(adas, C.ADAS_FREQ_FACTOR["AF_MV"], 1.0) * crash,
        "AF_SV": B["AF_SV"] * c["h_af"] * drive * np.where(adas, C.ADAS_FREQ_FACTOR["AF_SV"], 1.0) * crash ** 0.5,
        "NAF": B["NAF"] * c["h_naf"] * mile ** C.MILEAGE_ELASTICITY * crash,
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
    set_window(c, cal, s, x)

    # coverage terms and cost levels
    bi = np.array(C.BI_LIMITS)
    c["bi_pp"], c["bi_pa"] = bi[p["bi_opt"][pol], 0], bi[p["bi_opt"][pol], 1]
    c["um_pp"], c["um_pa"] = bi[p["um_opt"][pol], 0], bi[p["um_opt"][pol], 1]
    c["pd_lim"] = np.array(C.PD_LIMITS)[p["bi_opt"][pol]]
    c["med_lim"] = np.array(C.MED_LIMITS)[p["med_opt"][pol]]
    c["has_coll"], c["has_comp"] = v["has_coll"][V], v["has_comp"][V]
    c["coll_ded"] = np.array(C.COLL_DEDUCTIBLES)[v["coll_ded_opt"][V]]
    c["comp_ded"] = np.array(C.COMP_DEDUCTIBLES)[v["comp_ded_opt"][V]]
    c["glass_ded"] = np.where(v["full_glass"][V], 0, c["comp_ded"])
    c["acv"] = actual_cash_value(v["msrp"][V], v["model_year"][V], mid, cal) * cal.used_car[cost] / cal.used_car[mid]
    age = (cal.year_frac(mid) - v["model_year"][V] + 0.5).clip(0)
    c["repair"] = (v["msrp"][V] / 32_000) ** 0.5 * np.where(adas, 1.12, 1.0) * np.where(v["segment"][V] == "ev", 1.15, 1.0) \
        * np.clip(1.05 - 0.012 * age, 0.80, 1.05)
    c["adas"], c["pd_factor"], c["bi_factor"], c["park"] = adas, v["pd_factor"][V], v["bi_factor"][V], park
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
    e_bi = injury_paid(ZG, col(c["bi_pp"]), col(c["bi_factor"]), t["BI"], C.BI_SEV).mean(1)
    E["BI"] = (n["AF_MV"] * c["p_bi"] + n["AF_SV"] * C.P_BI_GIVEN_AF_SV) * MEAN_CLAIMANTS * (1 - C.CWP["BI"]) * e_bi
    e_um = injury_paid(ZG, col(c["um_pp"]), 1.0, t["BI"], C.UM_SEV).mean(1)
    E["UM"] = n["NAF"] * c["p_un"] * C.P_UM_INJURY * MEAN_CLAIMANTS * (1 - C.CWP["UM"]) * e_um
    e_med = med_paid(ZG, col(np.maximum(c["med_lim"], 1)), t["BI"]).mean(1)
    E["MED"] = (c["med_lim"] > 0) * sum(n[k] * q for k, q in C.P_MED.items()) * (1 - C.CWP["MED"]) * e_med

    coll = np.zeros(c["n"])
    acv, ded, rep = col(c["acv"]), col(c["coll_ded"]), col(c["repair"])
    for k in DRIVING_PERILS:
        _, paid, total = collision(ZG, C.COLL_PERIL_SEV[k], rep, t["COLL"], acv, ded)
        net = (paid - np.minimum(total * acv * MEAN_SALVAGE, paid)).mean(1) * (1 - C.CWP["COLL"])
        if k == "NAF":
            insured_other = C.P_FILE_COLL["NAF"] * (1 - C.P_SUBROGATION["NAF"] * MEAN_SUBRO)
            coll += n[k] * net * (c["p_un"] * C.P_FILE_COLL["NAF_UNINSURED"] + (1 - c["p_un"]) * insured_other)
        else:
            coll += n[k] * net * C.P_FILE_COLL[k] * (1 - C.P_SUBROGATION.get(k, 0.0) * MEAN_SUBRO)
    E["COLL"] = c["has_coll"] * coll

    comp = np.zeros(c["n"])
    for k in COMP_PERILS:
        gross, _ = comp_gross(k, ZG, UG, rep, col(c["adas"]).astype(bool), t["COMP"], acv)
        d = col(c["glass_ded"] if k == "GLASS" else c["comp_ded"])
        comp += n[k] * np.maximum(gross - d, 0).mean(1) * (1 - C.CWP["COMP"])
    E["COMP"] = c["has_comp"] * comp
    return E


# ---------------------------------------------------------------------------- claim simulation
def _pick_driver(c, key, vi, rng):
    q = vi + rng.random(len(vi)) * (1 - 2e-9)
    return c["u_drv"][np.searchsorted(c[key], q)]


def simulate(c: dict, st: Static, cal: Calendar, rng: np.random.Generator, occ_offset: int):
    """Simulate losses for the vehicles in context c. Returns (occurrences, features) as DataFrames.
    An occurrence is one loss event; a feature is one coverage (and claimant) paying on it."""
    occs, feats = [], []
    n_occ = occ_offset

    def new_occurrences(peril, vi, day, driver, at_fault=False, cat=-1, uninsured=None):
        nonlocal n_occ
        ids = np.arange(n_occ, n_occ + len(vi))
        n_occ += len(vi)
        occs.append(pd.DataFrame(dict(occ=ids, vrow=vi, veh=c["V"][vi], pol=c["pol"][vi], day=day, peril=peril, drv=driver,
                                      at_fault=at_fault, cat=cat,
                                      other_uninsured=False if uninsured is None else uninsured)))
        return ids

    def add(cov, ids, gross, paid, cwp, claimant=1, total=False, salvage=0.0, subro=0.0):
        feats.append(pd.DataFrame(dict(occ=ids, cvg=cov, claimant=claimant, gross=gross, paid=np.where(cwp, 0.0, paid),
                                       cwp=cwp, total=total, salvage=salvage, subro=subro)))

    def injury_features(cov, ids, vi, day, sev, pp, pa, factor):
        if len(ids) == 0:
            return
        k = 1 + rng.choice(4, len(ids), p=C.BI_CLAIMANTS_P)
        o = np.repeat(np.arange(len(ids)), k)
        claimant = np.arange(len(o)) - np.repeat(np.cumsum(k) - k, k) + 1
        gross = sev["median"] * factor[o] * _trend(cal, "BI", day[o]) * np.exp(sev["sigma"] * rng.standard_normal(len(o)))
        cwp = rng.random(len(o)) < C.CWP[cov]
        paid = np.where(cwp, 0.0, np.minimum(gross, pp[o]))
        tot = np.bincount(o, paid, len(ids))
        paid = paid * np.minimum(1.0, pa / np.maximum(tot, 1e-9))[o]     # per-accident limit
        add(cov, ids[o], gross, paid, cwp, claimant=claimant)

    def collision_features(peril, ids, vi, day, file_p, subro_p):
        m = c["has_coll"][vi] & (rng.random(len(vi)) < file_p)
        ids, vi, day = ids[m], vi[m], day[m]
        if len(ids) == 0:
            return
        gross, paid, total = collision(rng.standard_normal(len(vi)), C.COLL_PERIL_SEV[peril], c["repair"][vi],
                                       _trend(cal, "COLL", day), c["acv"][vi], c["coll_ded"][vi])
        below = paid <= 0
        keep = ~below | (rng.random(len(vi)) < C.P_FILE_BELOW_DEDUCTIBLE)
        cwp = below | (rng.random(len(vi)) < C.CWP["COLL"])
        paid = np.where(cwp, 0.0, paid)
        total = total & (paid > 0)
        salvage = np.minimum(total * c["acv"][vi] * rng.uniform(*C.SALVAGE_RANGE, len(vi)), paid)
        subro = (rng.random(len(vi)) < subro_p) * rng.uniform(*C.SUBROGATION_SHARE, len(vi)) * (paid - salvage)
        add("COLL", ids[keep], gross[keep], paid[keep], cwp[keep], total=total[keep], salvage=salvage[keep], subro=subro[keep])

    def med_features(ids, vi, day, p):
        m = (c["med_lim"][vi] > 0) & (rng.random(len(vi)) < p)
        ids, vi, day = ids[m], vi[m], day[m]
        if len(ids):
            gross = C.MED_SEV["median"] * _trend(cal, "BI", day) * np.exp(C.MED_SEV["sigma"] * rng.standard_normal(len(vi)))
            add("MED", ids, gross, np.minimum(gross, c["med_lim"][vi]), rng.random(len(vi)) < C.CWP["MED"])

    def draw(peril, group=None, mask=None):
        lam = c["rate"][peril] * (cal.exposure(group, c["s"], c["x"]) if group else c["expo"][peril])
        if mask is not None:
            lam = lam * mask
        vi = np.repeat(np.arange(c["n"]), rng.poisson(lam))
        return vi, cal.sample_days(group or PERIL_GROUP[peril], c["s"][vi], c["x"][vi], rng)

    # --- driving perils ---
    vi, day = draw("AF_MV")
    ids = new_occurrences("AF_MV", vi, day, _pick_driver(c, "key_af", vi, rng), at_fault=True)
    m = rng.random(len(vi)) < C.P_PD_GIVEN_AF_MV
    g = pd_paid(rng.standard_normal(m.sum()), np.inf, c["pd_factor"][vi[m]], _trend(cal, "PD", day[m]))
    add("PD", ids[m], g, np.minimum(g, c["pd_lim"][vi[m]]), rng.random(m.sum()) < C.CWP["PD"])
    m = rng.random(len(vi)) < c["p_bi"][vi]
    injury_features("BI", ids[m], vi[m], day[m], C.BI_SEV, c["bi_pp"][vi[m]], c["bi_pa"][vi[m]], c["bi_factor"][vi[m]])
    collision_features("AF_MV", ids, vi, day, C.P_FILE_COLL["AF_MV"], 0.0)
    med_features(ids, vi, day, C.P_MED["AF_MV"])

    vi, day = draw("AF_SV")
    ids = new_occurrences("AF_SV", vi, day, _pick_driver(c, "key_af", vi, rng), at_fault=True)
    m = rng.random(len(vi)) < C.P_PD_GIVEN_AF_SV
    g = pd_paid(rng.standard_normal(m.sum()), np.inf, c["pd_factor"][vi[m]], _trend(cal, "PD", day[m]))
    add("PD", ids[m], g, np.minimum(g, c["pd_lim"][vi[m]]), rng.random(m.sum()) < C.CWP["PD"])
    m = rng.random(len(vi)) < C.P_BI_GIVEN_AF_SV
    injury_features("BI", ids[m], vi[m], day[m], C.BI_SEV, c["bi_pp"][vi[m]], c["bi_pa"][vi[m]], c["bi_factor"][vi[m]])
    collision_features("AF_SV", ids, vi, day, C.P_FILE_COLL["AF_SV"], 0.0)
    med_features(ids, vi, day, C.P_MED["AF_SV"])

    vi, day = draw("NAF")
    unins = rng.random(len(vi)) < c["p_un"][vi]
    ids = new_occurrences("NAF", vi, day, _pick_driver(c, "key_any", vi, rng), uninsured=unins)
    m = unins & (rng.random(len(vi)) < C.P_UM_INJURY)
    injury_features("UM", ids[m], vi[m], day[m], C.UM_SEV, c["um_pp"][vi[m]], c["um_pa"][vi[m]], np.ones(m.sum()))
    collision_features("NAF", ids[unins], vi[unins], day[unins], C.P_FILE_COLL["NAF_UNINSURED"], 0.0)
    collision_features("NAF", ids[~unins], vi[~unins], day[~unins], C.P_FILE_COLL["NAF"], C.P_SUBROGATION["NAF"])
    med_features(ids, vi, day, C.P_MED["NAF"])

    vi, day = draw("PARKED")
    ids = new_occurrences("PARKED", vi, day, np.full(len(vi), -1))
    collision_features("PARKED", ids, vi, day, C.P_FILE_COLL["PARKED"], C.P_SUBROGATION["PARKED"])

    # --- comprehensive perils ---
    def comp_features(peril, vi, day, cat=-1):
        m = c["has_comp"][vi]
        vi, day = vi[m], day[m]
        if len(vi) == 0:
            return
        gross, total = comp_gross(peril, rng.standard_normal(len(vi)), rng.random(len(vi)), c["repair"][vi], c["adas"][vi],
                                  _trend(cal, "COMP", day), c["acv"][vi])
        paid = np.maximum(gross - (c["glass_ded"] if peril == "GLASS" else c["comp_ded"])[vi], 0.0)
        below = paid <= 0
        keep = ~below | (rng.random(len(vi)) < C.P_FILE_BELOW_DEDUCTIBLE)
        cwp = below | (rng.random(len(vi)) < C.CWP["COMP"])
        ids = new_occurrences(peril, vi[keep], day[keep], np.full(keep.sum(), -1), cat=cat)
        add("COMP", ids, gross[keep], paid[keep], cwp[keep], total=total[keep] & ~cwp[keep])

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
        vi = np.flatnonzero(rng.random(c["n"]) < p_hit)
        comp_features(peril, vi, np.full(len(vi), d), cat=i)

    occ = pd.concat(occs, ignore_index=True) if occs else pd.DataFrame()
    feat = pd.concat(feats, ignore_index=True) if feats else pd.DataFrame()
    occ = occ[occ.occ.isin(feat.occ)].reset_index(drop=True)      # a loss with no payable coverage is not a claim
    return occ, feat, n_occ
