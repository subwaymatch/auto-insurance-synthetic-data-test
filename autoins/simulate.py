"""Walk every policy through its terms: rate it, decide renewal and cancellation, simulate claims.

Policies advance one term per pass. Within a pass everything is vectorised across policies,
so the order of random draws is fixed and the run is reproducible for a given seed.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from . import config as C
from . import population, rating, truth
from .refdata import stream

CANCEL_REASONS = ["", "Underwriting", "Non-Payment", "Insured Request"]


@dataclass
class Result:
    terms: pd.DataFrame
    rows: pd.DataFrame       # one per policy term x vehicle
    occ: pd.DataFrame        # loss events
    feat: pd.DataFrame       # coverage-level claim features
    plan: rating.Plan
    static: truth.Static


def run(cfg: C.Config, ref, pop) -> Result:
    cal = ref.cal
    st = truth.Static.build(pop, ref)
    p, v = st.p, st.v
    n = len(pop.pol)
    d_pol = pop.drv.pol.to_numpy()
    kind = pop.incidents.kind.map({"minor": 0, "major": 1, "accident": 2}).to_numpy()
    inc_drv, inc_day, inc_kind = [pop.incidents.drv.to_numpy()], [pop.incidents.day.to_numpy()], [kind]

    def record(day_by_driver):
        """Violation points, major violations and at-fault accidents in the 3 years before a day."""
        nd = len(day_by_driver)
        d, t, k_ = np.concatenate(inc_drv), np.concatenate(inc_day), np.concatenate(inc_kind)
        m = (t <= day_by_driver[d]) & (t > day_by_driver[d] - C.LOOKBACK_DAYS)
        d, k_ = d[m], k_[m]
        points = np.bincount(d, np.where(k_ == 0, 1, np.where(k_ == 1, 3, 0)), nd).astype(int)
        return points, np.bincount(d, k_ == 1, nd).astype(int), np.bincount(d, k_ == 2, nd).astype(int)

    points0, _, acc0 = record(p["first_day"][d_pol])
    plan = rating.fit(cfg, ref, st, points0, acc0)

    R = stream(cfg.seed, "simulate")
    tm = p["term_months"]
    ty = tm / 12
    active = np.ones(n, dtype=bool)
    prev_annual, prev_claims, last_term = np.zeros(n), np.zeros(n, dtype=int), np.full(n, -1)
    terms, rows, occs, feats = [], [], [], []
    nonrenew_term, nonrenew_reason = [], []
    n_occ = n_terms = n_rows = k = 0

    while True:
        s_all = cal.day_of(p["first_month"] + k * tm, p["dom"])
        e_all = cal.day_of(p["first_month"] + (k + 1) * tm, p["dom"])
        cand = active & (s_all <= cal.valuation_day)
        if not cand.any():
            break
        V = np.flatnonzero(cand[v["pol"]] & v["active"])
        vp = v["pol"][V]
        points, majors, acc = record(s_all[d_pol])
        tenure_years = (p["tenure_terms"] + k) * ty
        cd = rating.codes(st, cal, V, s_all[vp], points, acc, tenure_years[vp])
        prem = rating.premium(plan, cd, rating.limit_factors(st, V), cal.rate_level[s_all[vp]], ty[vp])
        annual = np.bincount(vp, sum(prem.values()), n) / ty

        P = np.flatnonzero(cand)
        if k > 0:   # renewal decision, made with the renewal premium in hand
            change = annual[P] / prev_annual[P] - 1
            company = ((np.bincount(d_pol, acc, n)[P] >= 3) | (np.bincount(d_pol, majors, n)[P] >= 2)) & (R.random(len(P)) < 0.6)
            logit = (np.where(tm[P] == 6, C.RENEWAL_BASE_LOGIT[6], C.RENEWAL_BASE_LOGIT[12])
                     + 0.12 * np.minimum(tenure_years[P], 6) + 0.4 * p["multi_policy"][P] + 0.2 * p["homeowner"][P]
                     + 0.015 * np.clip(p["ni_age"][P] + k * ty[P] - 45, -25, 25) - 0.5 * (p["tier"][P] == 2)
                     - 0.2 * (prev_claims[P] > 0) - C.PRICE_ELASTICITY * np.maximum(change - C.PRICE_TOLERANCE, 0)
                     + 2.0 * np.maximum(-change, 0))
            stay = ~company & (R.random(len(P)) < 1 / (1 + np.exp(-logit)))
            gone = P[~stay]
            nonrenew_term.append(last_term[gone])
            nonrenew_reason.append(np.where(company[~stay], "Company Non-Renewal", "Insured Did Not Renew"))
            active[gone] = False
            cand[gone] = False
            P = P[stay]
            if len(P) == 0:
                break
            # renewing customers sometimes arrive with a different car; re-rate with the current fleet
            _replace_vehicles(st, ref, cand, s_all, ty, R)
            new_inc = _add_teen_drivers(st, pop, ref, cand, s_all, ty, R)
            if len(new_inc):
                inc_drv.append(new_inc.drv.to_numpy()); inc_day.append(new_inc.day.to_numpy())
                inc_kind.append(new_inc.kind.map({"minor": 0, "major": 1}).to_numpy())
            v, d_pol = st.v, pop.drv.pol.to_numpy()
            points, majors, acc = record(s_all[d_pol])
            V = np.flatnonzero(cand[v["pol"]] & v["active"])
            vp = v["pol"][V]
            cd = rating.codes(st, cal, V, s_all[vp], points, acc, tenure_years[vp])
            prem = rating.premium(plan, cd, rating.limit_factors(st, V), cal.rate_level[s_all[vp]], ty[vp])
            annual = np.bincount(vp, sum(prem.values()), n) / ty

        # mid-term cancellation
        s, e = s_all[P], e_all[P]
        tdays = e - s
        p_nonpay = np.array([C.NONPAY_RATE[x] for x in C.PAY_PLANS])[p["pay_plan"][P]] * ty[P] \
            * np.clip(np.exp(-0.6 * p["score_z"][P]), 0.3, 4.0) * np.where(p["tier"][P] == 2, 1.6, 1.0)
        p_request = C.MIDTERM_INSURED_REQUEST_RATE * ty[P]
        p_uw = C.UW_CANCEL_NEW_BUSINESS_P * np.where(p["prior_insurance"][P], 1, 3) * ~p["is_initial"][P] * (k == 0)
        u, f = R.random(len(P)), R.random(len(P))
        reason = np.where(u < p_uw, 1, np.where(u < p_uw + p_nonpay, 2, np.where(u < p_uw + p_nonpay + p_request, 3, 0)))
        cday = s + np.where(reason == 1, 20 + f * 39, np.where(reason == 2, 35 + f * (tdays - 40), 5 + f * (tdays - 6))).astype(int)
        cancelled = (reason > 0) & (cday <= cal.valuation_day)
        x_pol = np.zeros(n, dtype=int)
        x_pol[P] = np.minimum(np.where(cancelled, cday, e), cal.horizon)

        # claims and expected losses
        ctx = truth.context(st, cal, V, s_all[vp], x_pol[vp])
        exp_loss = truth.expected(ctx, cal)
        occ, feat, n_occ = truth.simulate(ctx, st, cal, R, n_occ)

        term_of_pol = np.full(n, -1)
        term_of_pol[P] = n_terms + np.arange(len(P))
        prev_claims[:] = 0
        if len(occ):
            charge = feat[feat.cvg.isin(["PD", "BI", "COLL"])].groupby("occ").paid.sum()
            occ["chargeable"] = occ.at_fault & (occ.occ.map(charge).fillna(0) >= C.CHARGEABLE_THRESHOLD)
            ch = occ[occ.chargeable]
            inc_drv.append(ch.drv.to_numpy()); inc_day.append(ch.day.to_numpy()); inc_kind.append(np.full(len(ch), 2))
            prev_claims = np.bincount(occ.pol, minlength=n)
            occ["term"] = term_of_pol[occ.pol.to_numpy()]
            occ["row"] = n_rows + occ.pop("vrow").to_numpy()
            occs.append(occ); feats.append(feat)

        d = v["primary_drv"][V]
        earned_share = (x_pol[vp] - s_all[vp]) / (e_all[vp] - s_all[vp])
        row = pd.DataFrame(dict(
            row=n_rows + np.arange(len(V)), term=term_of_pol[vp], pol=vp, veh=V, drv=d, s=s_all[vp], x=x_pol[vp],
            earned_exposure=(x_pol[vp] - s_all[vp]) / 365.25, earned_share=earned_share,
            driver_age=(s_all[vp] - pop.drv.dob_day.to_numpy()[d]) / 365.25,
            violation_points=points[d], at_fault_accidents=acc[d], tenure_years=tenure_years[vp],
            class_code=cd["class"], score_tier=cd["score_tier"], acv=ctx["acv"],
            **{f"prem_{c}": prem[c] for c in C.COVERAGES}, **{f"exp_{c}": exp_loss[c] for c in C.COVERAGES}))
        rows.append(row)
        terms.append(pd.DataFrame(dict(
            term=term_of_pol[P], pol=P, term_no=p["tenure_terms"][P] + k + 1, s=s, e=e,
            cancel_day=np.where(cancelled, cday, -1), cancel_reason=np.array(CANCEL_REASONS)[np.where(cancelled, reason, 0)],
            written_premium=annual[P] * ty[P], rate_level=cal.rate_level[s],
            new_business=~p["is_initial"][P] & (k == 0))))

        prev_annual[P] = annual[P]
        last_term[P] = term_of_pol[P]
        active[P[cancelled]] = False
        n_terms += len(P); n_rows += len(V); k += 1

    terms = pd.concat(terms, ignore_index=True)
    terms["nonrenewal_reason"] = ""
    if nonrenew_term:
        terms.loc[np.concatenate(nonrenew_term), "nonrenewal_reason"] = np.concatenate(nonrenew_reason)
    pop.veh = pd.DataFrame({c: st.v[c] for c in pop.veh.columns})     # now includes replacement vehicles
    pop.pol["n_drv"] = st.p["n_drv"]
    return Result(terms=terms, rows=pd.concat(rows, ignore_index=True), occ=pd.concat(occs, ignore_index=True),
                  feat=pd.concat(feats, ignore_index=True), plan=plan, static=st)


def _replace_vehicles(st: truth.Static, ref, renewing: np.ndarray, s_all: np.ndarray, ty: np.ndarray, R) -> int:
    """At renewal, some vehicles are traded for a newer one. Returns the number replaced."""
    cal, v, p = ref.cal, st.v, st.p
    idx = np.flatnonzero(v["active"] & renewing[v["pol"]])
    pol = v["pol"][idx]
    age = cal.year_frac(s_all[pol]) - v["model_year"][idx]
    hazard = np.interp(age, C.REPLACE_AGE_KNOTS, C.REPLACE_HAZARD)
    hazard = np.where((v["ownership"][idx] == "Leased") & (age >= 3), C.LEASE_END_HAZARD, hazard)
    old = idx[R.random(len(idx)) < 1 - np.exp(-hazard * ty[pol])]
    if len(old) == 0:
        return 0
    pol, day = v["pol"][old], s_all[v["pol"][old]]
    density = ref.zips.population_density_sqmi.to_numpy()[p["zi"][pol]]
    new = population.draw_vehicles(ref, R, pol, cal.year_frac(day), p["inc_rel"][pol], density,
                                   age_scale=C.REPLACEMENT_AGE["scale"], age_shape=C.REPLACEMENT_AGE["shape"])
    for c in ("rank", "primary_drv", "extra_vehicle", "true_miles", "reported_miles", "use", "parking",
              "coll_ded_opt", "comp_ded_opt"):
        new[c] = v[c][old]
    vage = (cal.year_frac(day) - new.model_year.to_numpy()).clip(0)
    new["ownership"] = population.draw_ownership(R, vage)
    p_full = population.full_coverage_probability(vage, p["inc_rel"][pol], p["score_z"][pol], p["tier"][pol])
    new["has_coll"] = (new.ownership.to_numpy() != "Owned") | (R.random(len(old)) < p_full)
    new["has_comp"] = new.has_coll | (R.random(len(old)) < 0.15)
    new["full_glass"] = new.has_comp & (R.random(len(old)) < C.FULL_GLASS_P)
    new["veh"] = len(v["pol"]) + np.arange(len(old))
    new["added_day"], new["removed_day"], new["active"] = day, -1, True
    st.replace_vehicles(old, new, day)
    return len(old)


def _add_teen_drivers(st: truth.Static, pop, ref, renewing: np.ndarray, s_all: np.ndarray, ty: np.ndarray, R) -> pd.DataFrame:
    """At renewal, some households add a newly licensed teenager. Returns the new drivers' violations."""
    cal, p, drv = ref.cal, st.p, pop.drv
    pols = np.flatnonzero(renewing)
    age_now = p["ni_age"][pols] + (s_all[pols] - p["first_day"][pols]) / 365.25
    rate = np.array(C.KID_RATE_BY_VEHICLES)[p["n_veh"][pols] - 1] / C.TEEN_YEARS_AT_HOME
    add = (age_now >= 36) & (age_now <= 60) & (p["n_drv"][pols] < 5) & (R.random(len(pols)) < 1 - np.exp(-rate * ty[pols]))
    pol = pols[add]
    m = len(pol)
    if m == 0:
        return pd.DataFrame(columns=["drv", "day", "kind"])
    day = s_all[pol]
    age = 16 + R.random(m) * 0.9
    male = R.random(m) < 0.5
    named_insured = drv.groupby("pol").drv.first().to_numpy()[pol]
    new = pd.DataFrame(dict(
        pol=pol, role=3, age=age, drv=len(drv) + np.arange(m), ord=p["n_drv"][pol], male=male, marital="S",
        dob_day=(day - age * 365.25).astype(int), licensed_day=day - R.integers(0, 120, m),
        latent=R.gamma(C.LATENT_GAMMA_SHAPE, 1 / C.LATENT_GAMMA_SHAPE, m) * p["household_factor"][pol],
        good_student=R.random(m) < 0.40, commute_miles=0.0, employed=False,
        first_name=np.where(male, R.choice(ref.first_m, m), R.choice(ref.first_f, m)),
        last_name=drv.last_name.to_numpy()[named_insured], assigned=False, added_day=day))
    pop.drv = pd.concat([drv, new[drv.columns]], ignore_index=True)
    p["n_drv"][pol] += 1
    v = st.v
    usage, assigned = population.usage_table(v["veh"], v["pol"], v["primary_drv"], v["extra_vehicle"], pop.drv.pol.to_numpy())
    st.u_veh, st.u_drv, st.u_w = usage.veh.to_numpy(), usage.drv.to_numpy(), usage.weight.to_numpy()
    pop.drv["assigned"] = assigned
    inc = population.violations(new, new.licensed_day.to_numpy(), np.full(m, cal.valuation_day), R)
    inc["pol"] = pop.drv.pol.to_numpy()[inc.drv.to_numpy()]
    pop.incidents = pd.concat([pop.incidents, inc[pop.incidents.columns]], ignore_index=True)
    return inc
