"""Walk every policy through its terms: rate it, decide renewal and cancellation, simulate claims.

Policies advance one term per pass. Within a pass everything is vectorised across policies,
so the order of random draws is fixed and the run is reproducible for a given seed.

Information timing. The simulator knows every claim's ultimate cost, but the insurer does not.
Each term is rated (and each renewal offered, and each underwriting non-renewal decided) on its
rating date, before the effective date, using only incidents known by then: violations once they
post to the driving record, accidents once they appear on a claims-history report, and the
company's own at-fault claims once their payments make them chargeable (claims.Development).

Vehicle lifecycle. A paid total loss ends the vehicle's cover the day after the loss; nothing
happens to it afterwards. Most households buy a replacement, which joins the policy (with a new
insured-vehicle ID) on the day it is bought, mid-term, or at renewal if the term has run out.
Mid-term vehicle changes are endorsements: premium is charged or returned pro rata.

Opening book. Policies already in force on the start date enter with the term that spans it.
That term was written before the extract; only exposure and premium after the start are earned.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from . import claims
from . import config as C
from . import population, rating, truth
from .refdata import stream

CANCEL_REASONS = ["", "Underwriting", "Non-Payment", "Insured Request"]
REMOVAL_REASONS = ["", "Replaced", "Total Loss"]
KIND = {"minor": 0, "major": 1, "accident": 2}


@dataclass
class Result:
    terms: pd.DataFrame
    rows: pd.DataFrame       # one per policy term x vehicle
    occ: pd.DataFrame        # loss events, with report and chargeable dates
    feat: pd.DataFrame       # coverage-level claim features, developed to ultimate
    pays: pd.DataFrame       # every payment and recovery, including those after the valuation date
    plan: rating.Plan
    static: truth.Static


class Records:
    """Driver incidents (violations and at-fault accidents), each with the day it became known."""

    def __init__(self, inc: pd.DataFrame) -> None:
        self.parts: list[tuple] = []
        self.add(inc.drv, inc.day, inc.kind.map(KIND), inc.known_day)

    def add(self, drv, day, kind, known) -> None:
        self.parts.append(tuple(np.asarray(a, dtype=np.int64) for a in (drv, day, kind, known)))

    def as_of(self, nd: int, eff: np.ndarray, asof: np.ndarray):
        """Violation points, major violations and at-fault accidents for each driver: incidents dated in
        the three years up to `eff` that the insurer knew of by `asof` (both arrays are per driver)."""
        d, t, k_, kn = (np.concatenate(a) for a in zip(*self.parts))
        m = (t <= eff[d]) & (t > eff[d] - C.LOOKBACK_DAYS) & (kn <= asof[d])
        d, k_ = d[m], k_[m]
        points = np.bincount(d, np.where(k_ == 0, 1, np.where(k_ == 1, 3, 0)), nd).astype(int)
        return points, np.bincount(d, k_ == 1, nd).astype(int), np.bincount(d, k_ == 2, nd).astype(int)


def run(cfg: C.Config, ref, pop) -> Result:
    cal = ref.cal
    V_DAY = cal.valuation_day
    st = truth.Static.build(pop, ref)
    p = st.p
    n = len(pop.pol)
    recs = Records(pop.incidents)
    d_pol = pop.drv.pol.to_numpy()
    fd = p["first_day"][d_pol]
    points0, _, acc0 = recs.as_of(len(d_pol), fd, fd)
    plan = rating.fit(cfg, ref, st, points0, acc0)

    R = stream(cfg.seed, "simulate")
    dev = claims.Development(cal, stream(cfg.seed, "claims"))
    tm = p["term_months"]
    ty = tm / 12
    active = np.ones(n, dtype=bool)
    prev_annual, prev_s, last_term = np.zeros(n), np.full(n, -10 ** 6), np.full(n, -1)
    pending = np.zeros(0, dtype=int)         # total-loss vehicles whose replacement arrives after their term ended
    pending_day = np.zeros(0, dtype=int)
    clm_pol, clm_report = [np.zeros(0, int)], [np.zeros(0, int)]
    terms, rows, nonrenew_term, nonrenew_reason = [], [], [], []
    n_terms = n_rows = n_occ = k = 0

    while True:
        s_all = cal.day_of(p["first_month"] + k * tm, p["dom"])
        e_all = cal.day_of(p["first_month"] + (k + 1) * tm, p["dom"])
        cand = active & (s_all <= V_DAY)
        if not cand.any():
            break
        term_no = p["tenure_terms"] + k + 1
        lead = np.where(term_no > 1, R.integers(C.RENEWAL_OFFER_LEAD_DAYS[0], C.RENEWAL_OFFER_LEAD_DAYS[1] + 1, n),
                        R.integers(C.NEW_BUSINESS_QUOTE_LEAD_DAYS[0], C.NEW_BUSINESS_QUOTE_LEAD_DAYS[1] + 1, n))
        rate_day = s_all - lead               # rating, underwriting and the renewal offer happen on this day
        tenure_years = (p["tenure_terms"] + k) * ty
        P = np.flatnonzero(cand)

        if k > 0:   # renewal decision, made with the renewal offer in hand
            v = st.v
            points, majors, acc = recs.as_of(len(d_pol), s_all[d_pol], rate_day[d_pol])
            V = np.flatnonzero(cand[v["pol"]] & v["active"])
            vp = v["pol"][V]
            prem = _premium(st, cal, plan, V, s_all[vp], points, acc, tenure_years[vp], ty[vp])[0]
            annual = np.bincount(vp, sum(prem.values()), n) / ty
            change = np.where(prev_annual[P] > 0, annual[P] / np.maximum(prev_annual[P], 1e-9) - 1, 0.0)
            company = ((np.bincount(d_pol, acc, n)[P] >= 3) | (np.bincount(d_pol, majors, n)[P] >= 2)) & (R.random(len(P)) < 0.6)
            # the customer's own claims reported during the expiring term
            cp, cr = np.concatenate(clm_pol), np.concatenate(clm_report)
            m = (cr >= prev_s[cp]) & (cr < s_all[cp])
            prev_claims = np.bincount(cp[m], minlength=n)[P]
            logit = (np.where(tm[P] == 6, C.RENEWAL_BASE_LOGIT[6], C.RENEWAL_BASE_LOGIT[12])
                     + 0.12 * np.minimum(tenure_years[P], 6) + 0.4 * p["multi_policy"][P] + 0.2 * p["homeowner"][P]
                     + 0.015 * np.clip(p["ni_age"][P] + k * ty[P] - 45, -25, 25) - 0.5 * (p["tier"][P] == 2)
                     - 0.2 * (prev_claims > 0) - C.PRICE_ELASTICITY * np.maximum(change - C.PRICE_TOLERANCE, 0)
                     + 2.0 * np.maximum(-change, 0))
            # a household left with no car and none on order has nothing to insure
            has_car = np.bincount(v["pol"][v["active"]], minlength=n) > 0
            has_car[v["pol"][pending]] = True
            stay = ~company & (R.random(len(P)) < 1 / (1 + np.exp(-logit))) & has_car[P]
            gone = P[~stay]
            nonrenew_term.append(last_term[gone])
            nonrenew_reason.append(np.where(company[~stay], "Company Non-Renewal", "Insured Did Not Renew"))
            active[gone] = False
            cand[gone] = False
            P = P[stay]
            if len(P) == 0:
                break

        # mid-term cancellation; a term already running on the start date can only end after it
        s, e = s_all[P], e_all[P]
        tdays = e - s
        p_nonpay = np.array([C.NONPAY_RATE[x] for x in C.PAY_PLANS])[p["pay_plan"][P]] * ty[P] \
            * np.clip(np.exp(-0.6 * p["score_z"][P]), 0.3, 4.0) * np.where(p["tier"][P] == 2, 1.6, 1.0)
        p_request = C.MIDTERM_INSURED_REQUEST_RATE * ty[P]
        p_uw = C.UW_CANCEL_NEW_BUSINESS_P * np.where(p["prior_insurance"][P], 1, 3) * ~p["is_initial"][P] * (k == 0)
        u, f = R.random(len(P)), R.random(len(P))
        reason = np.where(u < p_uw, 1, np.where(u < p_uw + p_nonpay, 2, np.where(u < p_uw + p_nonpay + p_request, 3, 0)))
        cday = s + np.where(reason == 1, 20 + f * 39, np.where(reason == 2, 35 + f * (tdays - 40), 5 + f * (tdays - 6))).astype(int)
        cancelled = (reason > 0) & (cday >= 0) & (cday <= V_DAY)
        cancel_day, cancel_reason = np.full(n, -1), np.zeros(n, dtype=int)
        cancel_day[P[cancelled]], cancel_reason[P[cancelled]] = cday[cancelled], reason[cancelled]
        x_pol = np.zeros(n, dtype=int)
        x_pol[P] = np.minimum(np.where(cancelled, cday, e), cal.horizon)

        if k > 0:
            # household changes at renewal: trade-ins, replacements for cars totalled late last term, teenagers
            renewing = np.zeros(n, dtype=bool)
            renewing[P] = True
            _replace_vehicles(st, ref, renewing, s_all, ty, R)
            pp = st.v["pol"][pending]
            arrive = np.maximum(pending_day, s_all[pp])
            ok = renewing[pp] & (arrive < x_pol[pp])
            if ok.any():
                st.add_replacements(pending[ok], _draw_replacements(st, ref, pending[ok], arrive[ok], R))
            pending, pending_day = np.zeros(0, dtype=int), np.zeros(0, dtype=int)
            new_inc = _add_teen_drivers(st, pop, ref, renewing, s_all, ty, R)
            if len(new_inc):
                recs.add(new_inc.drv, new_inc.day, new_inc.kind.map(KIND), new_inc.known_day)
            _refresh_usage(st, pop)
            d_pol = pop.drv.pol.to_numpy()

        # rate the term and simulate it: the vehicles in force at the start (or arriving later as
        # replacements), then any replacements for vehicles totalled during the term, and so on
        points, majors, acc = recs.as_of(len(d_pol), s_all[d_pol], rate_day[d_pol])
        term_of_pol = np.full(n, -1)
        term_of_pol[P] = n_terms + np.arange(len(P))
        v = st.v
        V = np.flatnonzero(cand[v["pol"]] & v["active"])
        a = np.maximum(s_all[v["pol"][V]], v["added_day"][V])
        last_gone = np.full(n, -1)
        pass_rows = []
        while len(V):
            v = st.v
            vp = v["pol"][V]
            prem, cd = _premium(st, cal, plan, V, s_all[vp], points, acc, tenure_years[vp], ty[vp])
            ctx = truth.context(st, cal, V, a, x_pol[vp])
            occ, feat, n_occ = truth.simulate(ctx, st, cal, R, n_occ)
            occ, feat, loss_day = _stop_at_total_loss(occ, feat, len(V))
            totaled = loss_day >= 0
            x = np.where(totaled, loss_day + 1, x_pol[vp])
            truth.set_window(ctx, cal, a, x)
            exp_loss = truth.expected(ctx, cal)

            sched = np.where(totaled, x, e_all[vp])          # cover as written, before any cancellation
            span = e_all[vp] - s_all[vp]
            row_ids = n_rows + np.arange(len(V))
            dr = v["primary_drv"][V]
            pass_rows.append(pd.DataFrame(dict(
                row=row_ids, term=term_of_pol[vp], pol=vp, veh=V, drv=dr, s=a, x=x, sched=sched,
                earned_exposure=(x - np.maximum(a, 0)) / 365.25, earned_share=(x - np.maximum(a, 0)) / span,
                written_share=(sched - a) / span, return_share=(sched - x) * (cancel_day[vp] >= 0) / span,
                before_share=(np.minimum(x, 0) - np.minimum(a, 0)) / span, at_start=a == s_all[vp],
                driver_age=(s_all[vp] - pop.drv.dob_day.to_numpy()[dr]) / 365.25,
                violation_points=points[dr], at_fault_accidents=acc[dr], tenure_years=tenure_years[vp],
                class_code=cd["class"], score_tier=cd["score_tier"], good_student=cd["good_student"], acv=ctx["acv"],
                **{f"prem_{c}": prem[c] for c in C.COVERAGES}, **{f"exp_{c}": exp_loss[c] for c in C.COVERAGES})))
            n_rows += len(V)

            if len(occ):
                occ["term"] = term_of_pol[occ.pol.to_numpy()]
                occ["row"] = row_ids[occ.pop("vrow").to_numpy()]
                occ = dev.add(occ, feat)
                clm_pol.append(occ.pol.to_numpy()); clm_report.append(occ.report_day.to_numpy())
                ch = occ[occ.chargeable_day >= 0]
                recs.add(ch.drv, ch.day, np.full(len(ch), KIND["accident"]), ch.chargeable_day)

            # total losses: the car leaves the policy; most households replace it
            old, gone_day = V[totaled], x[totaled]
            if len(old) == 0:
                break
            st.retire(old, gone_day, REMOVAL_REASONS.index("Total Loss"))
            op = vp[totaled]
            np.maximum.at(last_gone, op, gone_day)
            replace = R.random(len(old)) < np.where(p["n_veh"][op] > 1, C.P_REPLACE_AFTER_TOTAL_LOSS["multi"],
                                                     C.P_REPLACE_AFTER_TOTAL_LOSS["single"])
            buy = gone_day + population.draw_lag(R, len(old), **C.TOTAL_LOSS_REPLACEMENT_DELAY)
            now = replace & (buy < x_pol[op])
            later = replace & ~now & (cancel_day[op] < 0) & (x_pol[op] == e_all[op])
            np.subtract.at(p["n_veh"], op[~replace], 1)
            pending, pending_day = np.r_[pending, old[later]], np.r_[pending_day, buy[later]]
            if now.any():
                st.add_replacements(old[now], _draw_replacements(st, ref, old[now], buy[now], R))
            V = np.arange(len(v["pol"]), len(st.v["pol"]))
            a = st.v["added_day"][V]

        # a policy whose last car was totalled, with no replacement coming, is cancelled that day
        v = st.v
        has_car = np.bincount(v["pol"][v["active"]], minlength=n) > 0
        has_car[v["pol"][pending]] = True
        empty = P[~has_car[P] & (last_gone[P] >= 0) & (last_gone[P] < x_pol[P])]
        cancel_day[empty], cancel_reason[empty], x_pol[empty] = last_gone[empty], CANCEL_REASONS.index("Insured Request"), last_gone[empty]

        terms.append(pd.DataFrame(dict(
            term=term_of_pol[P], pol=P, term_no=term_no[P], s=s_all[P], e=e_all[P], rate_day=rate_day[P],
            cancel_day=cancel_day[P], cancel_reason=np.array(CANCEL_REASONS)[cancel_reason[P]],
            rate_level=cal.rate_level_at(s_all[P]), new_business=term_no[P] == 1)))
        # the premium the customer compares the next renewal offer against: vehicles still insured at expiry
        this = pd.concat(pass_rows, ignore_index=True)
        keep = st.v["active"][this.veh.to_numpy()]
        prev_annual = np.bincount(this.pol[keep], this.loc[keep, [f"prem_{c}" for c in C.COVERAGES]].sum(axis=1), n) / ty
        rows += pass_rows
        prev_s[P] = s_all[P]
        last_term[P] = term_of_pol[P]
        active[P[cancel_day[P] >= 0]] = False
        n_terms += len(P)
        k += 1

    terms = pd.concat(terms, ignore_index=True)
    terms["nonrenewal_reason"] = ""
    if nonrenew_term:
        terms.loc[np.concatenate(nonrenew_term), "nonrenewal_reason"] = np.concatenate(nonrenew_reason)
    pop.veh = pd.DataFrame({c: st.v[c] for c in pop.veh.columns})     # now includes replacement vehicles
    pop.pol["n_drv"] = st.p["n_drv"]
    occ, feat, pays = dev.result()
    return Result(terms=terms, rows=pd.concat(rows, ignore_index=True), occ=occ, feat=feat, pays=pays, plan=plan, static=st)


def _premium(st, cal, plan, V, s, points, acc, tenure_years, term_years):
    """Premium for vehicles V on a term effective on day s, rated with the given driver records."""
    cd = rating.codes(st, cal, V, s, points, acc, tenure_years)
    return rating.premium(plan, cd, rating.limit_factors(st, V), cal.rate_level_at(s), term_years), cd


def _stop_at_total_loss(occ: pd.DataFrame, feat: pd.DataFrame, nv: int):
    """Keep each vehicle's losses up to and including its first total loss. A vehicle's losses form
    independent Poisson processes, so dropping everything after the first total loss gives exactly
    the losses of a vehicle insured until that day. Returns (occ, feat, total-loss day or -1 per vehicle)."""
    loss_day = np.full(nv, -1)
    if len(occ) == 0:
        return occ, feat, loss_day
    tl = occ[occ.occ.isin(feat.occ[feat.total.to_numpy()])].sort_values(["vrow", "day", "occ"], kind="stable")
    first = tl.drop_duplicates("vrow")
    first_occ = np.full(nv, -1)
    loss_day[first.vrow.to_numpy()] = first.day.to_numpy()
    first_occ[first.vrow.to_numpy()] = first.occ.to_numpy()
    vr, day = occ.vrow.to_numpy(), occ.day.to_numpy()
    ld = loss_day[vr]
    drop = (ld >= 0) & ((day > ld) | ((day == ld) & (occ.occ.to_numpy() != first_occ[vr])))
    occ = occ[~drop].reset_index(drop=True)
    feat = feat[feat.occ.isin(occ.occ)].reset_index(drop=True)
    return occ, feat, loss_day


def _refresh_usage(st: truth.Static, pop) -> None:
    """Rebuild who drives which car from the vehicles now insured (drivers whose car has gone share the others)."""
    v = st.v
    act = np.flatnonzero(v["active"])
    usage, assigned = population.usage_table(v["veh"][act], v["pol"][act], v["primary_drv"][act], v["extra_vehicle"][act],
                                             pop.drv.pol.to_numpy())
    st.set_usage(usage)
    pop.drv["assigned"] = assigned


def _draw_replacements(st: truth.Static, ref, old: np.ndarray, day: np.ndarray, R) -> pd.DataFrame:
    """New vehicles replacing `old`, insured from `day`. They keep the old vehicle's driver, use and deductibles."""
    cal, v, p = ref.cal, st.v, st.p
    pol = v["pol"][old]
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
    new["removal_reason"], new["replaces"] = 0, old
    return new


def _replace_vehicles(st: truth.Static, ref, renewing: np.ndarray, s_all: np.ndarray, ty: np.ndarray, R) -> int:
    """At renewal, some vehicles are traded for a newer one. Returns the number replaced."""
    cal, v = ref.cal, st.v
    idx = np.flatnonzero(v["active"] & renewing[v["pol"]])
    pol = v["pol"][idx]
    age = cal.year_frac(s_all[pol]) - v["model_year"][idx]
    hazard = np.interp(age, C.REPLACE_AGE_KNOTS, C.REPLACE_HAZARD)
    hazard = np.where((v["ownership"][idx] == "Leased") & (age >= 3), C.LEASE_END_HAZARD, hazard)
    old = idx[R.random(len(idx)) < 1 - np.exp(-hazard * ty[pol])]
    if len(old) == 0:
        return 0
    day = s_all[v["pol"][old]]
    new = _draw_replacements(st, ref, old, day, R)
    st.retire(old, day, REMOVAL_REASONS.index("Replaced"))
    st.add_replacements(old, new)
    return len(old)


def _add_teen_drivers(st: truth.Static, pop, ref, renewing: np.ndarray, s_all: np.ndarray, ty: np.ndarray, R) -> pd.DataFrame:
    """At renewal, some households add a newly licensed teenager. Returns the new drivers' violations."""
    cal, p, drv = ref.cal, st.p, pop.drv
    pols = np.flatnonzero(renewing)
    age_now = p["ni_age"][pols] + (s_all[pols] - p["first_day"][pols]) / 365.25
    rate = np.array(C.KID_RATE_BY_VEHICLES)[np.clip(p["n_veh"][pols], 1, 4) - 1] / C.TEEN_YEARS_AT_HOME
    add = (age_now >= 36) & (age_now <= 60) & (p["n_drv"][pols] < 5) & (R.random(len(pols)) < 1 - np.exp(-rate * ty[pols]))
    pol = pols[add]
    m = len(pol)
    if m == 0:
        return pd.DataFrame(columns=["drv", "day", "kind", "known_day"])
    day = s_all[pol]
    age = 16 + R.random(m) * 0.9
    male = R.random(m) < 0.5
    dob = (day - age * 365.25).astype(int)
    named_insured = drv.groupby("pol").drv.first().to_numpy()[pol]
    new = pd.DataFrame(dict(
        pol=pol, role=3, age=age, drv=len(drv) + np.arange(m), ord=p["n_drv"][pol], male=male, marital="S",
        dob_day=dob, licensed_day=day - R.integers(0, 120, m),
        latent=R.gamma(C.LATENT_GAMMA_SHAPE, 1 / C.LATENT_GAMMA_SHAPE, m) * p["household_factor"][pol],
        good_grades=R.random(m) < C.GOOD_STUDENT_GRADES_P,
        school_end_day=dob + (population.school_end_age(R, m) * 365.25).astype(int), commute_miles=0.0, employed=False,
        first_name=np.where(male, R.choice(ref.first_m, m), R.choice(ref.first_f, m)),
        last_name=drv.last_name.to_numpy()[named_insured], assigned=False, added_day=day))
    pop.drv = pd.concat([drv, new[drv.columns]], ignore_index=True)
    p["n_drv"][pol] += 1
    inc = population.violations(new, new.licensed_day.to_numpy(), np.full(m, cal.valuation_day), R)
    inc["pol"] = pop.drv.pol.to_numpy()[inc.drv.to_numpy()]
    pop.incidents = pd.concat([pop.incidents, inc[pop.incidents.columns]], ignore_index=True)
    return inc
