"""The insurer's rating plan: what each vehicle is charged.

The plan only sees what a real insurer would see (the rating variables below). Its discounts and
surcharges (multi-car, multi-policy, homeowner, paid in full, prior insurance, tenure, good student,
married) are filed as round percentages (config.FILED_DISCOUNTS), as real plans file them. Every
other relativity is fitted around those with the classic minimum-bias procedure, to the company's
claims experience (simulated from the true expected costs: config.EXPERIENCE_YEARS), and each level is
credibility-weighted with a bureau complement, so the plan is broadly adequate but carries the
estimation error of a real one. Then the deliberate distortions in config.PLANTED_DISTORTIONS are
applied. Everything the plan cannot see (latent driver risk, household stability, the agency's book
quality, true mileage, parking, ZIP effects inside a territory, the Kia/Hyundai theft wave) is left
unpriced, and a filed discount is right only as far as its round percentage happens to match what the
risk justifies (Plan.indicated holds what each variable is truly worth).
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from . import config as C
from . import refdata, truth

CLASS_LEVELS = ["16-17 M", "16-17 F", "18-20 M", "18-20 F", "21-24 M", "21-24 F",
                "25-29", "30-39", "40-49", "50-64", "65-74", "75+"]
LEVELS = {
    "class": CLASS_LEVELS,
    "married": ["No", "Yes"],
    "inexperienced": ["No", "Yes"],
    "good_student": ["No", "Yes"],
    "violation_points": ["0", "1", "2", "3", "4+"],
    "at_fault_accidents": ["0", "1", "2+"],
    "score_tier": ["No Hit", "Under 550", "550-599", "600-649", "650-699", "700-749", "750-799", "800+"],
    "company_tier": C.TIER_NAMES,
    "segment": ["economy", "mainstream", "luxury", "truck", "sports", "ev", "minivan"],
    "vehicle_age": ["0-2", "3-5", "6-9", "10-14", "15+"],
    "vehicle_value": ["Under 24k", "24-30k", "30-38k", "38-48k", "48-62k", "62k+"],
    "mileage": ["Under 5,000", "5,000-7,999", "8,000-11,999", "12,000-15,999", "16,000+"],
    "use": ["Pleasure", "Commute", "Business"],
    "multi_car": ["No", "Yes"],
    "homeowner": ["No", "Yes"],
    "multi_policy": ["No", "Yes"],
    "prior_insurance": ["No", "Yes"],
    "paid_in_full": ["No", "Yes"],
    "tenure": ["New", "1-2 years", "3-5 years", "6+ years"],
    "occasional_youthful": ["No", "Yes"],
    "territory": [f"T{i + 1:02d}" for i in range(C.N_TERRITORIES)],
}
SCORE_EDGES = [550, 600, 650, 700, 750, 800]


@dataclass
class Plan:
    base: dict = field(default_factory=dict)         # coverage -> base rate (annual, at rate level 1.0)
    factors: dict = field(default_factory=dict)      # coverage -> variable -> relativities
    fitted: dict = field(default_factory=dict)       # the same before planted distortions
    indicated: dict = field(default_factory=dict)    # every variable fitted freely: what each is truly worth
    terr_liab: np.ndarray = None                     # ZIP index -> territory
    terr_comp: np.ndarray = None


def territories(ref) -> tuple[np.ndarray, np.ndarray]:
    """Group ZIPs into territories of roughly equal size by the public hazard indices."""
    z = ref.zips
    out = []
    for col in ("crash_hazard_index", "theft_hazard_index"):
        order = np.argsort(z[col].to_numpy(), kind="stable")
        share = np.cumsum(z.households_with_vehicle.to_numpy()[order]) / z.households_with_vehicle.sum()
        terr = np.empty(len(z), dtype=int)
        terr[order] = np.minimum((share * C.N_TERRITORIES).astype(int), C.N_TERRITORIES - 1)
        out.append(terr)
    return out[0], out[1]


def codes(st: truth.Static, cal, V: np.ndarray, s: np.ndarray, points: np.ndarray, accidents: np.ndarray,
          tenure_years: np.ndarray, household: dict = None) -> dict:
    """Rating variable levels for vehicles V rated as of day s. points, accidents (the primary driver's
    record) and tenure_years are per vehicle row. The household (each car's rated driver, the driver's marital
    status, the address, homeowner, multi-car and occasional-youthful status) is the policy as it stands now,
    unless `household` gives it as it stood on an earlier day: per row "drv", "married", "zi", "homeowner",
    "multi_car" and "occasional_youthful" (a renewal offer evaluated from the policy's history)."""
    v, p = st.v, st.p
    drv = st.pop.drv
    pol = v["pol"][V]
    d = v["primary_drv"][V] if household is None else household["drv"]
    age = (s - drv.dob_day.to_numpy()[d]) / 365.25
    male = drv.male.to_numpy()[d]
    band = np.searchsorted([18, 21, 25, 30, 40, 50, 65, 75], age, side="right")
    cls = np.where(band <= 2, band * 2 + (~male), band + 3)
    score = p["insurance_score"][pol]
    vage = cal.year_frac(s) - v["model_year"][V]
    if household is None:
        # a household driver under 25 with no car of their own is rated on the policy's least valuable vehicle
        s_pol = np.zeros(len(p["zi"]), dtype=int)
        s_pol[pol] = s
        dp = drv.pol.to_numpy()
        young = drv.active.to_numpy() & ~drv.assigned.to_numpy() & ((s_pol[dp] - drv.dob_day.to_numpy()) / 365.25 < 25)
        young_unassigned = np.bincount(dp, young, len(s_pol)) > 0
        # ... on whichever insured vehicle now has the highest rank (the least valuable car when first written)
        last_rank = np.full(len(s_pol), -1)
        np.maximum.at(last_rank, v["pol"][v["active"]], v["rank"][v["active"]])
        household = {"married": (drv.marital.to_numpy()[d] == "M").astype(int), "zi": v["zi"][V],
                     "homeowner": p["homeowner"][pol].astype(int), "multi_car": (p["n_veh"][pol] > 1).astype(int),
                     "occasional_youthful": (young_unassigned[pol] & (v["rank"][V] == last_rank[pol])).astype(int)}
    return {
        "class": cls,
        "married": np.asarray(household["married"]).astype(int),
        "inexperienced": ((s - drv.licensed_day.to_numpy()[d]) < 3 * 365.25).astype(int),
        "good_student": truth.good_student(drv.good_grades.to_numpy()[d], drv.school_end_day.to_numpy()[d],
                                           drv.dob_day.to_numpy()[d], s).astype(int),
        "violation_points": np.minimum(points, 4),
        "at_fault_accidents": np.minimum(accidents, 2),
        "score_tier": np.where(np.isnan(score), 0, 1 + np.searchsorted(SCORE_EDGES, np.nan_to_num(score), side="right")),
        "company_tier": p["tier"][pol],
        "segment": st.v["seg_code"][V],
        "vehicle_age": np.searchsorted([3, 6, 10, 15], vage, side="right"),
        "vehicle_value": np.searchsorted([24_000, 30_000, 38_000, 48_000, 62_000], v["msrp"][V], side="right"),
        "mileage": np.searchsorted([5_000, 8_000, 12_000, 16_000], v["reported_miles"][V], side="right"),
        "use": np.where(v["use"][V] == "Business", 2, np.where(v["use"][V] == "Commute", 1, 0)),
        "multi_car": np.asarray(household["multi_car"]).astype(int),
        "homeowner": np.asarray(household["homeowner"]).astype(int),
        "multi_policy": p["multi_policy"][pol].astype(int),
        "prior_insurance": p["prior_insurance"][pol].astype(int),
        "paid_in_full": (p["pay_plan"][pol] == 0).astype(int),
        "tenure": np.searchsorted([1, 3, 6], tenure_years, side="right"),
        "occasional_youthful": np.asarray(household["occasional_youthful"]).astype(int),
        "zi": np.asarray(household["zi"]),
    }


def limit_factors(st: truth.Static, V: np.ndarray, cover: dict = None) -> dict:
    """Limit, deductible and option factors for vehicles V: the coverage as it stands now, or as given in `cover`
    (per row: "bi_opt", "um_opt", "med_opt", "has_coll", "coll_ded_opt", "has_comp", "comp_ded_opt",
    "full_glass", "has_rent", "rent_opt", "has_tow")."""
    if cover is None:
        v, p = st.v, st.p
        pol = v["pol"][V]
        cover = {k: p[k][pol] for k in ("bi_opt", "um_opt", "med_opt")}
        cover.update({k: v[k][V] for k in ("has_coll", "coll_ded_opt", "has_comp", "comp_ded_opt", "full_glass",
                                           "has_rent", "rent_opt", "has_tow")})
    c = cover
    return {
        "BI": np.array(C.BI_LIMIT_FACTOR)[c["bi_opt"]],
        "PD": np.array(C.PD_LIMIT_FACTOR)[c["bi_opt"]],
        "UM": np.array(C.UM_LIMIT_FACTOR)[c["um_opt"]],
        "MED": np.array(C.MED_LIMIT_FACTOR)[c["med_opt"]],
        "COLL": c["has_coll"] * np.array(C.COLL_DED_FACTOR)[c["coll_ded_opt"]],
        "COMP": c["has_comp"] * np.array(C.COMP_DED_FACTOR)[c["comp_ded_opt"]]
                * np.where(c["full_glass"], C.FULL_GLASS_FACTOR, 1.0),
        "RENT": c["has_rent"] * np.array(C.RENTAL_FACTOR)[c["rent_opt"]],
        "TOW": c["has_tow"] * 1.0,
    }


def _variables(plan: Plan, cov: str, cd: dict) -> dict:
    """The code arrays that apply to one coverage (territory depends on the coverage)."""
    out = {k: a for k, a in cd.items() if k != "zi"}
    out["territory"] = (plan.terr_comp if cov == "COMP" else plan.terr_liab)[cd["zi"]]
    return out


def relativity(plan: Plan, cov: str, cd: dict, table: str = "factors") -> np.ndarray:
    f = getattr(plan, table)[cov]
    out = np.ones(len(cd["zi"]))
    for name, code in _variables(plan, cov, cd).items():
        out = out * f[name][code]
    return out


def premium(plan: Plan, cd: dict, lim: dict, rate_level: np.ndarray, term_years: np.ndarray) -> dict:
    return {cov: np.round(plan.base[cov] * relativity(plan, cov, cd) * lim[cov] * rate_level * term_years, 2)
            for cov in C.COVERAGES}


def filed_factors(cov: str) -> dict:
    """The filed discount and surcharge tables as they apply to one coverage (1.0 where a discount does not)."""
    return {k: np.array(f if cov in covs else [1.0] * len(f)) for k, (f, covs) in C.FILED_DISCOUNTS.items()}


def _minimum_bias(variables: dict, y: np.ndarray, sweeps: int = 40, credibility: float = 25.0, offset=None) -> dict:
    """Bailey's multiplicative minimum-bias fit. Sparse levels are pulled toward 1.0. `offset` is a fixed
    multiplier on each row (the filed discounts), which the fitted variables work around."""
    f = {k: np.ones(len(LEVELS[k])) for k in variables}
    off = np.ones(len(y)) if offset is None else np.asarray(offset, dtype=float)
    mean = y.sum() / off.sum()
    pred = mean * off
    for _ in range(sweeps):
        for k, code in variables.items():
            other = pred / f[k][code]
            num = np.bincount(code, y, len(f[k]))
            den = np.bincount(code, other, len(f[k]))
            new = (num + credibility * mean) / (den + credibility * mean)
            new = new / new[np.argmax(np.bincount(code, minlength=len(new)))]
            f[k] = new
            pred = other * new[code]
        pred = pred * y.sum() / pred.sum()
    return {k: np.round(a, 3) for k, a in f.items()}


def experience(y: dict, R: np.random.Generator) -> tuple[dict, dict]:
    """The claims experience the plan is fitted to: for each coverage, each vehicle's losses over
    config.EXPERIENCE_YEARS and how many claims made them, drawn as a compound Poisson-gamma sum around its
    true expected cost `y`. Returns (losses, claim counts) by coverage."""
    loss, count = {}, {}
    for cov in C.COVERAGES:
        mean, cv = C.EXPERIENCE_SEVERITY[cov]
        n = R.poisson(np.maximum(y[cov], 0.0) * C.EXPERIENCE_YEARS / mean)
        loss[cov] = np.where(n > 0, R.gamma(np.maximum(n, 1) / cv ** 2, mean * cv ** 2), 0.0)
        count[cov] = n
    return loss, count


def credibility(claims: np.ndarray, cv: float) -> np.ndarray:
    """Limited-fluctuation credibility of a rating level's pure premium from its claim count."""
    return np.minimum(np.sqrt(claims / (C.FULL_CREDIBILITY_CLAIMS * (1 + cv ** 2))), 1.0)


def fit(cfg: C.Config, ref, st: truth.Static, points0: np.ndarray, accidents0: np.ndarray) -> Plan:
    """Fit the plan on every vehicle as it looks when first written, at day-one cost levels: to the claims
    experience those vehicles produce, each level credibility-weighted with the bureau's relativity."""
    cal = ref.cal
    plan = Plan()
    plan.terr_liab, plan.terr_comp = territories(ref)
    V = np.arange(len(st.v["pol"]))
    s = st.p["first_day"][st.v["pol"]]
    tenure = (st.p["tenure_terms"] * st.p["term_months"] / 12)[st.v["pol"]]
    d = st.v["primary_drv"][V]
    cd = codes(st, cal, V, s, points0[d], accidents0[d], tenure)
    ctx = truth.context(st, cal, V, s, s + 365, cost_day=0)
    ctx["expo"] = {k: np.full(len(V), cal.exposure(truth.PERIL_GROUP[k], 0, 365)) for k in ctx["rate"]}
    ctx["expo"]["THEFT_TOTAL"] = np.where(ctx["kh"], cal.exposure("theft_kh", 0, 365), ctx["expo"]["THEFT_TOTAL"])
    first_year = truth.new_customer_factor(ctx["t0"], s, s + 365)       # each policy's year from its first day in the data
    for k in C.NEW_CUSTOMER_PERILS:
        ctx["expo"][k] = ctx["expo"][k] * first_year
    y = truth.expected(ctx, cal)
    R = refdata.stream(cfg.seed, "rating experience")
    seen, claims = experience(y, R)
    lim = limit_factors(st, V)
    for cov in C.COVERAGES:
        m = lim[cov] > 0
        variables = {k: a[m] for k, a in _variables(plan, cov, cd).items()}
        target = y[cov][m] / lim[cov][m]
        plan.indicated[cov] = _minimum_bias(variables, target)
        # the filed discounts are taken as given; everything else is fitted around them, to the experience
        filed = filed_factors(cov)
        offset = np.prod([filed[k][variables[k]] for k in filed], axis=0)
        free = {k: a for k, a in variables.items() if k not in filed}
        true = _minimum_bias(free, target, offset=offset)
        observed = _minimum_bias(free, seen[cov][m] / lim[cov][m], offset=offset)
        fitted = {}
        for k, code in free.items():
            z = credibility(np.bincount(code, claims[cov][m], len(LEVELS[k])), C.EXPERIENCE_SEVERITY[cov][1])
            bureau = true[k] * np.exp(C.BUREAU_ERROR * R.standard_normal(len(z)))
            blend = z * observed[k] + (1 - z) * bureau
            fitted[k] = np.round(blend / blend[np.argmax(np.bincount(code, minlength=len(z)))], 3)
        fitted.update({k: np.round(a, 3) for k, a in filed.items()})
        plan.fitted[cov] = fitted
        f = {k: a.copy() for k, a in fitted.items()}
        for ordered in ("violation_points", "at_fault_accidents"):      # a filed plan would not reward a worse record
            f[ordered] = np.maximum.accumulate(f[ordered])
        for level, mult in C.PLANTED_DISTORTIONS["class"].items():
            f["class"][CLASS_LEVELS.index(level)] *= mult
        f["mileage"] = f["mileage"] ** C.PLANTED_DISTORTIONS["mileage_exponent"]
        plan.factors[cov] = {k: np.round(a, 3) for k, a in f.items()}
        plan.base[cov] = 1.0
        rel = relativity(plan, cov, cd)[m] * lim[cov][m]
        load = C.COMP_CAT_LOAD if cov == "COMP" else 1.0
        plan.base[cov] = float(round(seen[cov][m].sum() / C.EXPERIENCE_YEARS / C.TARGET_LOSS_RATIO * load / rel.sum(), 2))
    return plan


def to_json(plan: Plan) -> dict:
    out = {"base_rates_annual": plan.base, "planted_distortions": C.PLANTED_DISTORTIONS,
           "filed_discounts": {k: {"factors": dict(zip(LEVELS[k], f)), "coverages": covs}
                               for k, (f, covs) in C.FILED_DISCOUNTS.items()},
           "rate_changes": C.RATE_CHANGES, "relativities": {}, "relativities_before_distortion": {},
           "relativities_indicated": {}}
    for table, key in (("factors", "relativities"), ("fitted", "relativities_before_distortion"),
                       ("indicated", "relativities_indicated")):
        for cov, f in getattr(plan, table).items():
            out[key][cov] = {k: dict(zip(LEVELS[k], map(float, a))) for k, a in f.items()}
    return out
