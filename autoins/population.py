"""Build the insured population: policies (households), drivers, vehicles, coverages, driver records.

Everything here is fixed at the time a policy is first written. Things that change over
time (age, prior claims, premium, renewal) are handled in simulate.py.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from . import config as C
from . import truth
from .refdata import Reference, stream


@dataclass
class Population:
    pol: pd.DataFrame        # one row per policy
    drv: pd.DataFrame        # one row per driver
    veh: pd.DataFrame        # one row per insured vehicle
    usage: pd.DataFrame      # who drives which vehicle, and how much (sorted by vehicle)
    incidents: pd.DataFrame  # violations and prior-carrier accidents (driver, day, kind, description)
    zip_truth: pd.DataFrame  # true ZIP hazard, including the part the insurer cannot see
    agencies: pd.DataFrame


def row_choice(p: np.ndarray, rng: np.random.Generator) -> np.ndarray:
    """Sample one column index per row of a weight matrix."""
    cum = np.cumsum(p, axis=1)
    u = rng.random(len(p))[:, None] * cum[:, -1:]
    return np.minimum((u > cum).sum(axis=1), p.shape[1] - 1)


def _agencies(ref: Reference, rng: np.random.Generator) -> pd.DataFrame:
    z = ref.zips
    words_a = ["Lakeshore", "Prairie", "Fox Valley", "North Shore", "Midway", "Heartland", "Great Lakes", "Tri-County",
               "Windy City", "Riverwalk", "Parkway", "Cornerstone", "Gateway", "Landmark", "Keystone", "Meridian",
               "Summit", "Harbor", "Liberty", "Unity", "Beacon", "Crossroads", "Evergreen", "Pinnacle"]
    words_b = ["Insurance Agency", "Insurance Group", "Insurance Services", "Insurance Brokers", "Agency"]
    n_ind, n_exc = 16, 8
    homes = rng.choice(len(z), n_ind + n_exc, replace=False, p=(z.population / z.population.sum()).to_numpy())
    rows = []
    for i, h in enumerate(homes):
        rows.append(dict(agency_id=i + 1, name=f"{words_a[i]} {words_b[rng.integers(len(words_b))]}",
                         channel=C.CHANNELS[0] if i < n_ind else C.CHANNELS[1], zi=int(h),
                         size=float(rng.lognormal(0, 0.6))))
    rows.append(dict(agency_id=len(rows) + 1, name="Direct - Online", channel="Direct", zi=-1, size=0.7))
    rows.append(dict(agency_id=len(rows) + 1, name="Direct - Contact Center", channel="Direct", zi=-1, size=0.3))
    return pd.DataFrame(rows)


def build(cfg: C.Config, ref: Reference) -> Population:
    z, cal = ref.zips, ref.cal
    n = cfg.n_policies
    Z = len(z)

    # ---- true ZIP hazard ------------------------------------------------------
    r = stream(cfg.seed, "zip")
    zt = pd.DataFrame({"zip": z.zip, "location_id": z.location_id})
    zt["crash_random_effect"] = r.normal(0, C.ZIP_RANDOM_EFFECT_SIGMA["crash"], Z)
    zt["theft_random_effect"] = r.normal(0, C.ZIP_RANDOM_EFFECT_SIGMA["theft"], Z)
    zt["true_crash_hazard"] = z.crash_hazard_index * np.exp(zt.crash_random_effect)
    zt["true_theft_hazard"] = z.theft_hazard_index * np.exp(zt.theft_random_effect)
    zt["density_factor"] = np.clip((z.population_density_sqmi / 5000) ** 0.25, 0.6, 1.8)
    zt["animal_factor"] = np.clip((z.population_density_sqmi / 3000) ** -0.5, 0.25, 3.0)
    zt["p_other_driver_uninsured"] = np.clip(C.P_UNINSURED_BASE * z.crash_hazard_index ** 0.9, 0.06, 0.40)
    penetration = np.exp(r.normal(0, C.ZIP_PENETRATION_SIGMA, Z))

    # ---- policies ---------------------------------------------------------------
    r = stream(cfg.seed, "policy")
    w = (z.households_with_vehicle * penetration).to_numpy()
    zi = r.choice(Z, n, p=w / w.sum())
    zr = z.iloc[zi].reset_index(drop=True)
    term_months = r.choice(list(C.TERM_MONTHS_P), n, p=list(C.TERM_MONTHS_P.values()))
    n_init = int(round(n * cfg.initial_book_share))
    is_init = np.arange(n) < n_init
    n_months = (cal.date(cal.valuation_day).astype("M8[M]") - cal.start.astype("M8[M]")).astype(int) + 1
    first_month = np.where(is_init, r.integers(0, 12, n) % term_months, r.integers(0, n_months, n))
    dom = r.integers(1, 29, n)
    first_day = cal.day_of(first_month, dom)
    keep_new = first_day <= cal.valuation_day
    first_month = np.where(keep_new, first_month, first_month - 1)
    first_day = cal.day_of(first_month, dom)

    bands = list(C.AGE_BAND_BOUNDS)
    band_mid = np.array([np.mean(C.AGE_BAND_BOUNDS[b]) for b in bands])
    tilt = np.exp(np.where(is_init[:, None], C.AGE_TILT_IN_FORCE, C.AGE_TILT_NEW_BUSINESS) * (band_mid[None, :] - 45))
    wb = zr[[f"age_share_{b}" for b in bands]].to_numpy() * np.array([C.HOUSEHOLDER_WEIGHT[b] for b in bands]) * tilt
    bi_ = row_choice(wb, r)
    lo = np.array([C.AGE_BAND_BOUNDS[b][0] for b in bands])[bi_]
    hi = np.array([C.AGE_BAND_BOUNDS[b][1] for b in bands])[bi_]
    ni_age = lo + r.random(n) * (hi - lo)

    # Households with many vehicles often split them across policies, so the tail is thinned (ASSUMED).
    n_veh = 1 + row_choice(zr[["veh_hh_share_1", "veh_hh_share_2", "veh_hh_share_3", "veh_hh_share_4plus"]].to_numpy()
                           * np.array([1.15, 1.0, 0.65, 0.45]), r)
    p_m = np.interp(ni_age, [18, 24, 28, 35, 50, 65, 85], [0.05, 0.18, 0.42, 0.58, 0.63, 0.60, 0.45])
    odds = p_m / (1 - p_m) * np.array([0.45, 1.8, 2.2, 2.2])[n_veh - 1]
    married = r.random(n) < odds / (1 + odds)
    p_own = zr.pct_owner_occupied.to_numpy().clip(0.03, 0.97)
    odds = p_own / (1 - p_own) * np.interp(ni_age, [18, 25, 35, 50, 70], [0.2, 0.35, 0.9, 1.5, 1.8]) * np.where(married, 1.6, 0.8)
    homeowner = r.random(n) < odds / (1 + odds)
    income = zr.median_household_income.to_numpy() * np.interp(ni_age, [18, 25, 35, 50, 65, 80], [0.5, 0.75, 1.0, 1.15, 0.95, 0.7]) \
        * np.where(married, 1.25, 0.8) * np.exp(r.normal(0, 0.5, n))
    inc_rel = income / 85_000

    channel = r.choice(3, n, p=C.CHANNEL_P)
    channel = np.where((ni_age < 35) & (r.random(n) < 0.25), 2, channel)
    agencies = _agencies(ref, stream(cfg.seed, "agency"))
    agency_id = np.zeros(n, dtype=int)
    lat, lon = zr.lat.to_numpy(), zr.lon.to_numpy()
    for ch in range(3):
        a = agencies[agencies.channel == C.CHANNELS[ch]]
        m = np.flatnonzero(channel == ch)
        if ch == 2:
            wgt = np.tile(a["size"].to_numpy(), (len(m), 1))
        else:
            az = z.iloc[a.zi]
            dist = 69 * np.hypot(lat[m, None] - az.lat.to_numpy()[None], (lon[m, None] - az.lon.to_numpy()[None]) * 0.745)
            wgt = a["size"].to_numpy()[None] * np.exp(-dist / 7.0) + 1e-6
        agency_id[m] = a.agency_id.to_numpy()[row_choice(wgt, r)]

    tenure_terms = np.where(is_init, np.floor(r.exponential(4.5, n) * 12 / term_months), 0).astype(int)
    tenure_terms = np.minimum(tenure_terms, ((ni_age - 18).clip(0) * 12 / term_months).astype(int))
    multi_policy = r.random(n) < np.where(homeowner, 0.55, 0.20) * np.array([1.0, 1.25, 0.7])[channel]

    pol = pd.DataFrame(dict(
        pol=np.arange(n), zi=zi, term_months=term_months, first_month=first_month, dom=dom, first_day=first_day,
        is_initial=is_init, tenure_terms=tenure_terms, n_veh=n_veh, married=married, homeowner=homeowner,
        income=income, inc_rel=inc_rel, channel=channel, agency_id=agency_id, multi_policy=multi_policy, ni_age=ni_age))
    in_city = (zr.region == "City of Chicago").to_numpy()

    # ---- drivers ----------------------------------------------------------------
    r = stream(cfg.seed, "driver")
    spouse = married & (r.random(n) < 0.93)
    other_adult = ~married & (n_veh >= 2) & (r.random(n) < 0.45) | ~married & (n_veh == 1) & (r.random(n) < 0.06)
    kid_rate = np.where((ni_age >= 36) & (ni_age <= 62), np.array(C.KID_RATE_BY_VEHICLES)[n_veh - 1], 0.0)
    n_kids = np.minimum(r.poisson(kid_rate), 2)
    parts = []
    parts.append(pd.DataFrame(dict(pol=np.arange(n), role=0, age=ni_age)))
    s_idx = np.flatnonzero(spouse)
    parts.append(pd.DataFrame(dict(pol=s_idx, role=1, age=np.clip(ni_age[s_idx] + r.normal(0, 3.5, len(s_idx)), 18, 92))))
    o_idx = np.flatnonzero(other_adult)
    parts.append(pd.DataFrame(dict(pol=o_idx, role=2, age=np.clip(ni_age[o_idx] + r.normal(0, 10, len(o_idx)), 18, 90))))
    k_idx = np.repeat(np.arange(n), n_kids)
    kid_age = 16 + r.random(len(k_idx)) * np.minimum(9, ni_age[k_idx] - 19 - 16).clip(1)
    parts.append(pd.DataFrame(dict(pol=k_idx, role=3, age=kid_age)))
    drv = pd.concat(parts, ignore_index=True)
    drv["neg_age"] = -drv.age
    drv = drv.sort_values(["pol", "role", "neg_age"], kind="stable").drop(columns="neg_age").reset_index(drop=True)
    nd = len(drv)
    drv["drv"] = np.arange(nd)
    drv["ord"] = drv.groupby("pol").cumcount()
    p_ = drv.pol.to_numpy()
    ni_male = r.random(n) < np.where(married, 0.60, 0.50)
    male = np.where(drv.role == 0, ni_male[p_], np.where(drv.role == 1, ni_male[p_] ^ (r.random(nd) < 0.97), r.random(nd) < 0.5))
    drv["male"] = male
    age = drv.age.to_numpy()
    u = r.random(nd)
    p_div = np.interp(age, [18, 30, 45, 60, 80], [0.0, 0.08, 0.25, 0.28, 0.15])
    p_wid = np.interp(age, [18, 55, 70, 85], [0.0, 0.02, 0.15, 0.45])
    single_status = np.where(u < p_wid, "W", np.where(u < p_wid + p_div, "D", "S"))
    drv["marital"] = np.where((drv.role <= 1) & married[p_], "M", np.where(drv.role == 3, "S", single_status))
    drv["dob_day"] = (pol.first_day.to_numpy()[p_] - age * 365.25).astype(int)
    transit = zr.pct_commute_transit.to_numpy()[p_]
    delay = r.exponential(np.where(drv.role == 3, 0.6, 0.8 + 5.0 * transit))
    drv["licensed_day"] = drv.dob_day + ((16 + np.minimum(delay, (age - 16).clip(0))) * 365.25).astype(int)
    household = np.exp(r.normal(-C.HOUSEHOLD_SIGMA ** 2 / 2, C.HOUSEHOLD_SIGMA, n))
    drv["latent"] = r.gamma(C.LATENT_GAMMA_SHAPE, 1 / C.LATENT_GAMMA_SHAPE, nd) * household[p_]
    pol["household_factor"] = household
    drv["good_student"] = (drv.role == 3) & (age < 25) & (r.random(nd) < 0.40)
    employed = r.random(nd) < np.interp(age, [16, 18, 22, 60, 66, 75], [0.15, 0.45, 0.78, 0.74, 0.30, 0.05])
    wfh = zr.pct_work_from_home.to_numpy()[p_]
    drives = employed & (r.random(nd) < (zr.pct_commute_drive.to_numpy()[p_] / (1 - wfh)).clip(0.05, 0.98)) & (r.random(nd) > wfh)
    miles = zr.mean_commute_minutes.to_numpy()[p_] * np.where(in_city[p_], 0.30, 0.48) * np.exp(r.normal(-0.1, 0.55, nd))
    drv["commute_miles"] = np.where(drives, np.clip(np.round(miles), 1, 65), 0)
    drv["employed"] = employed
    drv["first_name"] = np.where(male, r.choice(ref.first_m, nd), r.choice(ref.first_f, nd))
    surname = r.choice(ref.last, n)
    own_name = (drv.role == 2) | ((drv.role == 1) & (r.random(nd) < 0.20))
    drv["last_name"] = np.where(own_name, r.choice(ref.last, nd), surname[p_])
    n_drv = drv.groupby("pol").size().reindex(range(n)).to_numpy()
    pol["n_drv"] = n_drv

    # ---- vehicles -----------------------------------------------------------------
    r = stream(cfg.seed, "vehicle")
    vp = np.repeat(np.arange(n), n_veh)
    nv = len(vp)
    veh = draw_vehicles(ref, r, vp, cal.year_frac(pol.first_day.to_numpy()[vp]), inc_rel[vp],
                        zr.population_density_sqmi.to_numpy()[vp], age_scale=4.3, age_shape=2.0)
    model_year = veh.model_year.to_numpy()
    # rank vehicles within the policy by value (most valuable first) and assign primary drivers
    veh["neg_value"] = -truth.actual_cash_value(veh.msrp.to_numpy(), model_year, pol.first_day.to_numpy()[vp], cal)
    veh = veh.sort_values(["pol", "neg_value"], kind="stable").drop(columns="neg_value").reset_index(drop=True)
    veh["veh"] = np.arange(nv)
    veh["rank"] = veh.groupby("pol").cumcount()
    vp = veh.pol.to_numpy()
    first_drv = drv.groupby("pol").drv.first().to_numpy()
    primary_ord = np.where(veh["rank"] < n_drv[vp], veh["rank"], 0)
    veh["primary_drv"] = first_drv[vp] + primary_ord
    veh["extra_vehicle"] = veh["rank"] >= n_drv[vp]
    pd_ = veh.primary_drv.to_numpy()
    model_year = veh.model_year.to_numpy()
    age0 = (cal.year_frac(pol.first_day.to_numpy()[vp]) - model_year).clip(0)
    veh["ownership"] = draw_ownership(r, age0)
    commute = drv.commute_miles.to_numpy()[pd_] * ~veh.extra_vehicle.to_numpy()
    dage = drv.age.to_numpy()[pd_]
    true_miles = (5200 + commute * 2 * 230) * np.exp(r.normal(-0.06, 0.35, nv)) * np.where(in_city[vp], 0.85, 1.0) \
        * np.interp(dage, [16, 25, 60, 70, 85], [0.8, 1.0, 1.0, 0.8, 0.5]) * np.where(veh.extra_vehicle, 0.45, 1.0)
    veh["true_miles"] = np.clip(true_miles, 800, 38_000)
    veh["reported_miles"] = np.clip(np.round(veh.true_miles * np.exp(r.normal(-0.10, 0.22, nv)) / 500) * 500, 1000, 30_000)
    business = drv.employed.to_numpy()[pd_] & ~veh.extra_vehicle.to_numpy() & (r.random(nv) < 0.05)
    veh["use"] = np.where(business, "Business", np.where(commute > 0, "Commute", "Pleasure"))
    dens1 = zr.population_density_sqmi.to_numpy()[vp]
    p_street = np.clip(0.06 + 0.55 * dens1 / 15000, 0.04, 0.75) * np.where(homeowner[vp], 0.55, 1.0)
    p_garage = np.where(homeowner[vp], 0.60, 0.22) * (1 - p_street)
    u = r.random(nv)
    veh["parking"] = np.where(u < p_street, 0, np.where(u < p_street + p_garage, 2, 1))

    usage, assigned = usage_table(veh.veh.to_numpy(), vp, veh.primary_drv.to_numpy(), veh.extra_vehicle.to_numpy(), drv.pol.to_numpy())
    drv["assigned"] = assigned
    drv["added_day"] = pol.first_day.to_numpy()[drv.pol.to_numpy()]

    # ---- insurance score, driver records, underwriting tier -------------------------
    r = stream(cfg.seed, "underwriting")
    ni_latent = drv.latent.to_numpy()[first_drv]
    zscore = (0.50 * np.log(inc_rel) / 0.6 + 0.30 * np.clip((ni_age - 45) / 20, -1.2, 1.5) + 0.30 * homeowner
              - 0.55 * (np.log(ni_latent) + 0.25) / 0.72 + 0.55 * r.normal(0, 1, n))
    score = np.clip(np.round(700 + 75 * zscore), 350, 900)
    no_hit = r.random(n) < np.interp(ni_age, [18, 22, 30, 60], [0.20, 0.10, 0.03, 0.02])
    pol["insurance_score"] = np.where(no_hit, np.nan, score)
    pol["score_z"] = zscore

    incidents = _driver_records(cfg, ref, pol, drv, zt, r)
    fd = pol.first_day.to_numpy()[incidents.pol.to_numpy()]
    recent = (incidents.day <= fd) & (incidents.day > fd - C.LOOKBACK_DAYS)
    pts = np.bincount(incidents.pol[recent], np.where(incidents.kind[recent] == "minor", 1, np.where(incidents.kind[recent] == "major", 4, 3)), n)
    p_lapse = 1 / (1 + np.exp(-(-2.6 - 0.9 * zscore - 0.04 * (ni_age - 40).clip(-22, 0))))
    prior_ins = is_init | (r.random(n) > p_lapse)
    pol["prior_insurance"] = prior_ins
    tier = np.where(~prior_ins | (pts >= 5) | (score < 560) & ~no_hit, 2,
                    np.where((score >= 740) & ~no_hit & (pts == 0) & (homeowner | (tenure_terms * term_months >= 36)), 0, 1))
    pol["tier"] = tier
    u = r.random(n)
    p_pif = np.clip(0.30 + 0.12 * zscore, 0.05, 0.75)
    p_eft = (1 - p_pif) * 0.62
    pol["pay_plan"] = np.where(u < p_pif, 0, np.where(u < p_pif + p_eft, 1, 2))

    # ---- coverages ------------------------------------------------------------------
    r = stream(cfg.seed, "coverage")
    lat_cov = 0.9 * zscore + 0.5 * homeowner + 0.4 * np.log(inc_rel) + r.normal(0, 1, n) - 1.6 * (tier == 2)
    cuts = np.quantile(lat_cov[tier != 2], np.cumsum(C.BI_LIMIT_P)[:-1])
    pol["bi_opt"] = np.searchsorted(cuts, lat_cov)
    pol["um_opt"] = np.where(r.random(n) < 0.18, 0, pol.bi_opt)
    med = r.choice(len(C.MED_LIMITS), n, p=C.MED_LIMIT_P)
    pol["med_opt"] = np.where((pol.bi_opt == 0) & (r.random(n) < 0.5), 0, med)
    veh_age = age0
    p_full = full_coverage_probability(veh_age, inc_rel[vp], zscore[vp], tier[vp])
    financed = veh.ownership.to_numpy() != "Owned"
    veh["has_coll"] = financed | (r.random(nv) < p_full)
    veh["has_comp"] = veh.has_coll | (r.random(nv) < 0.15)
    tilt = np.clip(0.25 * np.log(inc_rel[vp]) + 0.15 * zscore[vp], -0.6, 0.6)[:, None] * np.array([-1.5, -0.5, 0.6, 1.4])[None, :]
    veh["coll_ded_opt"] = row_choice(np.array(C.COLL_DED_P)[None, :] * np.exp(tilt), r)
    veh["comp_ded_opt"] = np.minimum(row_choice(np.array(C.COMP_DED_P)[None, :] * np.exp(tilt), r), veh.coll_ded_opt + 1)
    veh["full_glass"] = veh.has_comp & (r.random(nv) < C.FULL_GLASS_P)
    veh["added_day"] = pol.first_day.to_numpy()[vp]
    veh["removed_day"] = -1
    veh["active"] = True

    return Population(pol=pol, drv=drv, veh=veh, usage=usage, incidents=incidents, zip_truth=zt, agencies=agencies)


def draw_vehicles(ref: Reference, r: np.random.Generator, pol_idx, year_frac, inc_rel, density, age_scale, age_shape) -> pd.DataFrame:
    """Pick a make, model and model year for each vehicle. Used for the starting fleet and for replacements."""
    mdl = ref.models
    nv = len(pol_idx)
    vage = np.minimum(r.gamma(age_shape, age_scale * np.clip(inc_rel, 0.3, 4) ** -0.35), 24.0)
    model_year = np.minimum(np.floor(year_frac - vage + 0.4), np.floor(year_frac)).astype(int)
    seg = mdl.segment.to_numpy()
    base_w = mdl.popularity.to_numpy()[None, :] * (
        (model_year[:, None] >= mdl.first_year.to_numpy()[None, :]) & (model_year[:, None] <= mdl.last_year.to_numpy()[None, :]))
    ir = np.clip(inc_rel, 0.25, 5)[:, None]
    aff = np.where(seg == "luxury", ir ** 1.3, np.where(seg == "economy", ir ** -0.5, np.where(seg == "ev", ir ** 1.0, 1.0)))
    geo = np.where(seg == "truck", np.clip(density / 4000, 0.2, 5)[:, None] ** -0.45, 1.0)
    mi_ = row_choice(base_w * aff * geo + 1e-9, r)
    veh = pd.DataFrame(dict(pol=pol_idx, model_idx=mi_, model_year=model_year))
    veh["msrp"] = mdl.msrp_2024.to_numpy()[mi_] * 1.03 ** (model_year - 2024)
    veh["segment"] = seg[mi_]
    veh["body_type"] = mdl.body_type.to_numpy()[mi_]
    veh["theft_factor"] = mdl.theft_factor.to_numpy()[mi_]
    veh["kia_hyundai"] = np.isin(mdl.make.to_numpy()[mi_], ["Kia", "Hyundai"]) & (model_year >= C.KIA_HYUNDAI_MODEL_YEARS[0]) \
        & (model_year <= C.KIA_HYUNDAI_MODEL_YEARS[1])
    lux = np.isin(veh.segment, ["luxury", "ev"])
    veh["adas"] = r.random(nv) < np.clip((model_year - np.where(lux, 2013, 2015)) / 7, 0, 0.96)
    veh["anti_theft"] = r.random(nv) < np.where(model_year >= 2010, 0.85, 0.40)
    return veh


def draw_ownership(r: np.random.Generator, vehicle_age) -> np.ndarray:
    u = r.random(len(vehicle_age))
    p_fin = np.interp(vehicle_age, [0, 3, 6, 10, 15], [0.62, 0.55, 0.30, 0.08, 0.01])
    p_lease = np.interp(vehicle_age, [0, 2, 3.5, 4], [0.22, 0.18, 0.04, 0.0])
    return np.where(u < p_lease, "Leased", np.where(u < p_lease + p_fin, "Financed", "Owned"))


def full_coverage_probability(vehicle_age, inc_rel, score_z, tier) -> np.ndarray:
    return 1 / (1 + np.exp(-(3.6 - 0.36 * vehicle_age + 0.5 * np.log(inc_rel) + 0.3 * score_z - 0.6 * (tier == 2))))


def usage_table(veh_id, veh_pol, veh_primary, veh_extra, drv_pol) -> tuple[pd.DataFrame, np.ndarray]:
    """Who drives which vehicle and how much. The primary driver does 80% of the driving; the rest is
    shared by the other household drivers, with drivers who have no car of their own counted three times."""
    v = pd.DataFrame(dict(veh=veh_id, pol=veh_pol, primary_drv=veh_primary))
    d = pd.DataFrame(dict(pol=drv_pol, drv=np.arange(len(drv_pol))))
    usage = v.merge(d, on="pol").sort_values(["veh", "drv"], kind="stable").reset_index(drop=True)
    assigned = np.zeros(len(drv_pol), dtype=bool)
    assigned[veh_primary[~veh_extra]] = True
    is_primary = usage.drv.to_numpy() == usage.primary_drv.to_numpy()
    raw = np.where(is_primary, 0.0, np.where(assigned[usage.drv.to_numpy()], 1.0, 3.0))
    tot = np.bincount(usage.veh.to_numpy(), raw, int(veh_id.max()) + 1)[usage.veh.to_numpy()]
    usage["weight"] = np.where(is_primary, np.where(tot > 0, 0.80, 1.0), 0.20 * raw / np.where(tot > 0, tot, 1))
    return usage[["veh", "drv", "weight"]], assigned


def violations(drv: pd.DataFrame, t0: np.ndarray, t1: np.ndarray, r: np.random.Generator) -> pd.DataFrame:
    """Moving violations for each driver between day t0 and day t1."""
    years = (t1 - t0).clip(0) / 365.25
    behaviour = drv.latent.to_numpy() ** C.VIOLATION_LATENT_EXPONENT * np.where(drv.male, 1.25, 0.80) \
        * np.interp(drv.age.to_numpy(), [16, 20, 30, 50, 70], [1.9, 1.8, 1.25, 0.85, 0.5])
    ids, out = drv.drv.to_numpy(), []
    for kind, rate, names, probs in [("minor", C.VIOLATION_RATE, C.MINOR_VIOLATIONS, C.MINOR_VIOLATION_P),
                                     ("major", C.MAJOR_VIOLATION_RATE, C.MAJOR_VIOLATIONS, C.MAJOR_VIOLATION_P)]:
        k = r.poisson(rate * behaviour ** (1.4 if kind == "major" else 1.0) * years)
        d = np.repeat(np.arange(len(drv)), k)
        day = (t0[d] + r.random(len(d)) * (t1[d] - t0[d])).astype(int)
        out.append(pd.DataFrame(dict(drv=ids[d], day=day, kind=kind, description=r.choice(names, len(d), p=probs))))
    return pd.concat(out, ignore_index=True)


def _driver_records(cfg, ref, pol, drv, zt, r) -> pd.DataFrame:
    """Violation timelines for the whole period, and at-fault accidents with a prior carrier
    in the three years before the policy was first written with this company."""
    cal = ref.cal
    nd = len(drv)
    p_ = drv.pol.to_numpy()
    first_day = pol.first_day.to_numpy()[p_]
    t0 = np.maximum(first_day - C.LOOKBACK_DAYS, drv.licensed_day.to_numpy())
    out = [violations(drv, t0, np.full(nd, cal.valuation_day), r)]
    # prior-carrier at-fault accidents (the company's own claims are added during the simulation)
    hazard = truth.driver_multiplier(drv, first_day - 550, cal) * zt.true_crash_hazard.to_numpy()[pol.zi.to_numpy()[p_]]
    prior_years = (first_day - t0).clip(0) / 365.25
    lam = (C.BASE_RATE["AF_MV"] + C.BASE_RATE["AF_SV"]) * C.PRIOR_ACCIDENT_FACTOR * hazard * prior_years * np.where(drv.assigned, 1.0, 0.35)
    k = r.poisson(lam)
    d = np.repeat(np.arange(nd), k)
    day = (t0[d] + r.random(len(d)) * (first_day[d] - t0[d])).astype(int)
    out.append(pd.DataFrame(dict(drv=d, day=day, kind="accident", description="At-fault accident (prior carrier)")))
    inc = pd.concat(out, ignore_index=True)
    inc["pol"] = p_[inc.drv.to_numpy()]
    return inc.sort_values(["drv", "day"], kind="stable").reset_index(drop=True)
