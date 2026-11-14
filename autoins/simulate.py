"""Walk every policy through its terms: rate it, decide renewal and cancellation, simulate claims.

Policies advance one term per pass. Within a pass everything is vectorised across policies,
so the order of random draws is fixed and the run is reproducible for a given seed.

Information timing. The simulator knows every claim's ultimate cost, but the insurer does not.
Each term is rated (and each renewal offered, and each underwriting non-renewal decided) on its
rating date, before the effective date, using only incidents known by then: violations once they
post to the driving record, accidents once they appear on a claims-history report, and the
company's own at-fault claims once their payments make them chargeable (claims.Development).
A mid-term change is rated on the day it happens, with what is known that day.

Household changes. Households change during a term as well as at renewal: they move within the
area, buy, sell and trade cars, add newly licensed teenagers and new spouses, and lose drivers who
move out, divorce or die. Each change is an endorsement: every risk row of the policy ends that
day and the policy is re-rated from it, so risk_fact holds one row per vehicle per endorsement
period. At renewal, loans are paid off, older owned cars drop physical damage cover and some
customers raise their deductibles.

Vehicle lifecycle. A car destroyed or stolen ends its cover the day after the loss, whether or
not the company pays for it (a car without collision cover can still be wrecked); nothing happens
to it afterwards. Most households buy a replacement, which joins with a new insured-vehicle ID
when it is bought. A few owners keep a car the company paid as a total loss.

Opening book. Policies already in force on the start date enter with the term that spans it.
That term was written before the extract; only exposure and premium after the start are earned.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from . import claims
from . import config as C
from . import population, rating, truth
from .refdata import stream

CANCEL_REASONS = ["", "Underwriting", "Non-Payment", "Insured Request", "Insured Deceased"]
REMOVAL_REASONS = ["", "Replaced", "Total Loss", "Sold", "Left With Driver", "Destroyed or Stolen"]
DRIVER_REMOVAL_REASONS = ["", "Moved Out", "Moved Out", "Divorce", "Deceased"]   # by leave code 1-4
KIND = {"minor": 0, "major": 1, "accident": 2}
# mid-term changes, in the order they are applied when several fall on one day
ARRIVAL, TRADE, SELL, LEAVE, MARRY, TEEN, ADD, MOVE = range(8)
CHANGE_REASONS = ["Replacement Vehicle Added", "Vehicle Replaced", "Vehicle Removed", "Driver Removed",
                  "Spouse Added", "Newly Licensed Driver Added", "Vehicle Added", "Address Change"]
END_RAN, END_ENDORSED, END_GONE = 0, 1, 2      # why a risk row ended: term end, endorsement, vehicle gone
EVENT_COLUMNS = ["pol", "day", "kind", "target", "extra"]


@dataclass
class Result:
    terms: pd.DataFrame
    rows: pd.DataFrame       # one per policy term x vehicle x endorsement period
    occ: pd.DataFrame        # loss events, with report and chargeable dates
    feat: pd.DataFrame       # coverage-level claim features, developed to ultimate
    pays: pd.DataFrame       # every payment and recovery, including those after the valuation date
    plan: rating.Plan
    static: truth.Static


class Records:
    """Driver incidents (violations and at-fault accidents), each with the day it became known."""

    def __init__(self, inc: pd.DataFrame) -> None:
        self.parts: list[tuple] = []
        self._frame = None
        self.add(inc.drv, inc.day, inc.kind.map(KIND), inc.known_day)

    def add(self, drv, day, kind, known) -> None:
        self.parts.append(tuple(np.asarray(a, dtype=np.int64) for a in (drv, day, kind, known)))
        self._frame = None

    def frame(self) -> pd.DataFrame:
        if self._frame is None:
            d, t, k_, kn = (np.concatenate(a) for a in zip(*self.parts))
            self._frame = pd.DataFrame({"drv": d, "t": t, "k": k_, "kn": kn})
        return self._frame

    @staticmethod
    def _count(i, k_, n):
        points = np.bincount(i, np.where(k_ == 0, 1, np.where(k_ == 1, 3, 0)), n).astype(int)
        return points, np.bincount(i, k_ == 1, n).astype(int), np.bincount(i, k_ == 2, n).astype(int)

    def as_of(self, nd: int, eff: np.ndarray, asof: np.ndarray):
        """Violation points, major violations and at-fault accidents for each driver: incidents dated in
        the three years up to `eff` that the insurer knew of by `asof` (both arrays are per driver)."""
        f = self.frame()
        d, t = f.drv.to_numpy(), f.t.to_numpy()
        m = (t <= eff[d]) & (t > eff[d] - C.LOOKBACK_DAYS) & (f.kn.to_numpy() <= asof[d])
        return self._count(d[m], f.k.to_numpy()[m], nd)

    def for_rows(self, drv: np.ndarray, anchor: np.ndarray, asof: np.ndarray):
        """The same, for each of a set of risk rows (driver, rated-as-of day, known-by day)."""
        rows = pd.DataFrame({"drv": drv, "i": np.arange(len(drv)), "anchor": anchor, "known_by": asof})
        j = rows.merge(self.frame(), on="drv")
        j = j[(j.t <= j.anchor) & (j.t > j.anchor - C.LOOKBACK_DAYS) & (j.kn <= j.known_by)]
        return self._count(j.i.to_numpy(), j.k.to_numpy(), len(drv))


@dataclass
class Sim:
    """Run-wide state shared by the helpers below."""
    ref: object
    pop: object
    st: truth.Static
    plan: rating.Plan
    R: np.random.Generator
    dev: claims.Development
    recs: Records
    n_rows: int = 0
    n_occ: int = 0
    pending: np.ndarray = field(default_factory=lambda: np.zeros(0, dtype=int))      # total-loss cars whose
    pending_day: np.ndarray = field(default_factory=lambda: np.zeros(0, dtype=int))  # replacement comes after the term
    clm_pol: list = field(default_factory=list)
    clm_report: list = field(default_factory=list)


@dataclass
class Term:
    """Per-policy arrays for the pass being simulated (indexed by policy)."""
    s: np.ndarray
    e: np.ndarray
    x_pol: np.ndarray
    cancel_day: np.ndarray
    cancel_reason: np.ndarray
    rate_day: np.ndarray
    tenure: np.ndarray
    ty: np.ndarray
    term_of_pol: np.ndarray
    last_gone: np.ndarray


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

    sim = Sim(ref=ref, pop=pop, st=st, plan=plan, R=stream(cfg.seed, "simulate"),
              dev=claims.Development(cal, stream(cfg.seed, "claims")), recs=recs)
    R = sim.R
    tm = p["term_months"]
    ty = tm / 12
    active = np.ones(n, dtype=bool)
    prev_annual, prev_s, last_term = np.zeros(n), np.full(n, -10 ** 6), np.full(n, -1)
    terms, rows, nonrenew_term, nonrenew_reason = [], [], [], []
    n_terms = k = 0

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
        change = np.zeros(n)

        if k > 0:   # renewal decision, made with the renewal offer in hand
            v, drv = st.v, pop.drv
            d_pol, d_act = drv.pol.to_numpy(), drv.active.to_numpy()
            points, majors, acc = recs.as_of(len(d_pol), s_all[d_pol], rate_day[d_pol])
            V = np.flatnonzero(cand[v["pol"]] & v["active"])
            vp, dr = v["pol"][V], v["primary_drv"][V]
            prem = _premium(sim, V, s_all[vp], s_all[vp], points[dr], acc[dr], tenure_years[vp], ty[vp])[0]
            annual = np.bincount(vp, sum(prem.values()), n) / ty
            change[P] = np.where(prev_annual[P] > 0, annual[P] / np.maximum(prev_annual[P], 1e-9) - 1, 0.0)
            company = ((np.bincount(d_pol, acc * d_act, n)[P] >= 3) | (np.bincount(d_pol, majors * d_act, n)[P] >= 2)) \
                & (R.random(len(P)) < 0.6)
            # the customer's own claims reported during the expiring term
            cp, cr = np.concatenate(sim.clm_pol), np.concatenate(sim.clm_report)
            m = (cr >= prev_s[cp]) & (cr < s_all[cp])
            prev_claims = np.bincount(cp[m], minlength=n)[P]
            logit = (np.where(tm[P] == 6, C.RENEWAL_BASE_LOGIT[6], C.RENEWAL_BASE_LOGIT[12])
                     + 0.12 * np.minimum(tenure_years[P], 6) + 0.4 * p["multi_policy"][P] + 0.2 * p["homeowner"][P]
                     + 0.015 * np.clip(p["ni_age"][P] + k * ty[P] - 45, -25, 25) - 0.5 * (p["tier"][P] == 2)
                     - 0.2 * (prev_claims > 0) - C.PRICE_ELASTICITY * np.maximum(change[P] - C.PRICE_TOLERANCE, 0)
                     + 2.0 * np.maximum(-change[P], 0))
            # a household left with no car and none on order has nothing to insure
            has_car = np.bincount(v["pol"][v["active"]], minlength=n) > 0
            has_car[v["pol"][sim.pending]] = True
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

        renewing = np.zeros(n, dtype=bool)
        renewing[P] = True
        if k > 0:
            _renewal_changes(sim, renewing, s_all, ty, change)
        events = _events(_pending_arrivals(sim, renewing, s_all, x_pol), _schedule_events(sim, P, s_all, x_pol))
        _refresh_usage(sim)
        term_of_pol = np.full(n, -1)
        term_of_pol[P] = n_terms + np.arange(len(P))
        T = Term(s=s_all, e=e_all, x_pol=x_pol, cancel_day=cancel_day, cancel_reason=cancel_reason, rate_day=rate_day,
                 tenure=tenure_years, ty=ty, term_of_pol=term_of_pol, last_gone=np.full(n, -1))
        term_rows = _simulate_term(sim, T, P, events)

        terms.append(pd.DataFrame(dict(
            term=term_of_pol[P], pol=P, term_no=term_no[P], s=s_all[P], e=e_all[P], rate_day=rate_day[P],
            cancel_day=cancel_day[P], cancel_reason=np.array(CANCEL_REASONS)[cancel_reason[P]],
            rate_level=cal.rate_level_at(s_all[P]), new_business=term_no[P] == 1)))
        # the premium the customer compares the next renewal offer against: cars still insured at expiry
        keep = (term_rows.end_kind.to_numpy() == END_RAN) & st.v["active"][term_rows.veh.to_numpy()]
        prev_annual = np.bincount(term_rows.pol[keep], term_rows.loc[keep, [f"prem_{c}" for c in C.COVERAGES]].sum(axis=1), n) / ty
        rows.append(term_rows)
        prev_s[P] = s_all[P]
        last_term[P] = term_of_pol[P]
        active[P[cancel_day[P] >= 0]] = False
        n_terms += len(P)
        k += 1

    terms = pd.concat(terms, ignore_index=True)
    terms["nonrenewal_reason"] = ""
    if nonrenew_term:
        terms.loc[np.concatenate(nonrenew_term), "nonrenewal_reason"] = np.concatenate(nonrenew_reason)
    pop.veh = pd.DataFrame({c: st.v[c] for c in pop.veh.columns})     # now includes every vehicle ever insured
    for c in ("n_drv", "n_veh", "ni_drv", "zi", "homeowner"):              # the policy as it stands at the end
        pop.pol[c] = st.p[c]
    occ, feat, pays = sim.dev.result()
    return Result(terms=terms, rows=pd.concat(rows, ignore_index=True), occ=occ, feat=feat, pays=pays, plan=plan, static=st)


# ----------------------------------------------------------------------------------------- one term
def _simulate_term(sim: Sim, T: Term, P: np.ndarray, events: pd.DataFrame) -> pd.DataFrame:
    """Simulate one term of policies P, endorsement period by endorsement period. Returns its risk rows."""
    st, p = sim.st, sim.st.p
    n = len(T.s)
    clock = T.s.copy()
    in_prog = P.copy()
    reason_now = np.full(n, "", dtype=object)          # what changed at the clock, for rows starting there
    out = []
    ev = events
    while len(in_prog):
        live = np.zeros(n, dtype=bool)
        live[in_prog] = True
        nb = T.x_pol.copy()                             # next boundary: the next change, or the end of the term
        upcoming = ev[live[ev.pol.to_numpy()]]
        np.minimum.at(nb, upcoming.pol.to_numpy(), upcoming.day.to_numpy())
        v = st.v
        V = np.flatnonzero(v["active"] & live[v["pol"]] & (v["added_day"] <= clock[v["pol"]]))
        a, why = clock[v["pol"][V]], reason_now[v["pol"][V]]
        while len(V):
            V, a, why, arrivals = _simulate_rows(sim, T, V, a, why, nb, out)
            ev = _events(ev, arrivals)

        # a policy whose last car has gone, with no replacement coming, is cancelled the day it went
        v = st.v
        has_car = np.bincount(v["pol"][v["active"]], minlength=n) > 0
        has_car[ev.pol[ev.kind == ARRIVAL].to_numpy()] = True
        has_car[v["pol"][sim.pending]] = True
        empty = in_prog[~has_car[in_prog] & (T.last_gone[in_prog] >= 0)]
        _cancel(T, empty, T.last_gone[empty], "Insured Request")
        live[empty] = False
        ev = ev[live[ev.pol.to_numpy()] | (ev.day.to_numpy() > nb[ev.pol.to_numpy()])]

        # apply the changes falling on each policy's boundary
        pe = ev.pol.to_numpy()
        due = live[pe] & (ev.day.to_numpy() == nb[pe]) & (nb[pe] < T.x_pol[pe])
        labels = _apply_events(sim, T, ev[due])
        ev = ev[~due & (live[pe] | (ev.kind.to_numpy() == ARRIVAL))]
        reason_now[:] = ""
        for pol, lab in labels.items():
            reason_now[pol] = "; ".join(dict.fromkeys(lab))
        if labels:
            _refresh_usage(sim)
        clock[in_prog] = np.minimum(nb[in_prog], T.x_pol[in_prog])
        in_prog = in_prog[clock[in_prog] < T.x_pol[in_prog]]
        ev = ev[np.isin(ev.pol.to_numpy(), in_prog)]

    rows = pd.concat(out, ignore_index=True)
    pol, x, a = rows.pol.to_numpy(), rows.x.to_numpy(), rows.s.to_numpy()
    span = T.e[pol] - T.s[pol]
    cancelled = T.cancel_day[pol] >= 0
    # rows ending at a change that turned out to be a cancellation are cancelled like any other
    ran = (rows.end_kind.to_numpy() == END_RAN) | ((rows.end_kind.to_numpy() == END_ENDORSED) & cancelled & (x == T.cancel_day[pol]))
    rows["end_kind"] = np.where(ran, END_RAN, rows.end_kind)
    sched = np.where(ran, T.e[pol], x)                  # cover as written, before any cancellation
    return rows.assign(
        sched=sched, earned_exposure=(x - np.maximum(a, 0)) / 365.25, earned_share=(x - np.maximum(a, 0)) / span,
        written_share=(sched - a) / span, return_share=(sched - x) * cancelled / span,
        before_share=(np.minimum(x, 0) - np.minimum(a, 0)) / span, at_start=a == T.s[pol])


def _simulate_rows(sim: Sim, T: Term, V, a, why, nb, out: list):
    """Rate vehicles V from day a and simulate their losses up to their policy's next boundary. Appends risk
    rows to `out`. Returns the replacements that arrive before the boundary (to simulate next) and the
    replacements arriving later in the term, as ARRIVAL events."""
    st, cal, R, p, v = sim.st, sim.ref.cal, sim.R, sim.st.p, sim.st.v
    drv = sim.pop.drv
    vp = v["pol"][V]
    b = nb[vp]
    dr = v["primary_drv"][V]
    asof = np.where(a == T.s[vp], T.rate_day[vp], a)      # a change is rated with what is known that day
    points, _, acc = sim.recs.for_rows(dr, a, asof)
    prem, cd = _premium(sim, V, a, T.s[vp], points, acc, T.tenure[vp], T.ty[vp])
    ctx = truth.context(st, cal, V, a, b)
    occ, feat, wrecks, sim.n_occ = truth.simulate(ctx, st, cal, R, sim.n_occ)
    occ, feat, stop_day, how = _stop_at_total_loss(occ, feat, wrecks, len(V))
    gone = stop_day >= 0
    x = np.where(gone, stop_day + 1, b)
    truth.set_window(ctx, cal, a, x)
    exp_loss = truth.expected(ctx, cal)
    row_ids = sim.n_rows + np.arange(len(V))
    sim.n_rows += len(V)
    out.append(pd.DataFrame(dict(
        row=row_ids, term=T.term_of_pol[vp], pol=vp, veh=V, drv=dr, s=a, x=x,
        end_kind=np.where(gone, END_GONE, np.where(b < T.x_pol[vp], END_ENDORSED, END_RAN)),
        zi=v["zi"][V], rated_on=asof, reason=why, driver_age=(a - drv.dob_day.to_numpy()[dr]) / 365.25,
        violation_points=points, at_fault_accidents=acc, tenure_years=T.tenure[vp],
        class_code=cd["class"], score_tier=cd["score_tier"], good_student=cd["good_student"],
        homeowner=cd["homeowner"], married=cd["married"], acv=ctx["acv"],
        coll_ded=np.where(v["has_coll"][V], np.array(C.COLL_DEDUCTIBLES)[v["coll_ded_opt"][V]], 0),
        comp_ded=np.where(v["has_comp"][V], np.array(C.COMP_DEDUCTIBLES)[v["comp_ded_opt"][V]], 0),
        **{f"prem_{c}": prem[c] for c in C.COVERAGES}, **{f"exp_{c}": exp_loss[c] for c in C.COVERAGES})))

    if len(occ):
        kept = occ.occ.isin(feat.occ[feat.retained.to_numpy().astype(bool)])
        v["salvage_title"][V[occ.vrow[kept].to_numpy()]] = True      # owner kept a paid total loss
        occ["term"] = T.term_of_pol[occ.pol.to_numpy()]
        occ["row"] = row_ids[occ.pop("vrow").to_numpy()]
        occ = sim.dev.add(occ, feat)
        sim.clm_pol.append(occ.pol.to_numpy())
        sim.clm_report.append(occ.report_day.to_numpy())
        ch = occ[occ.chargeable_day >= 0]
        sim.recs.add(ch.drv, ch.day, np.full(len(ch), KIND["accident"]), ch.chargeable_day)

    # cars destroyed or stolen leave the policy; most households replace them
    old, left = V[gone], x[gone]
    none = np.zeros(0, dtype=int)
    if len(old) == 0:
        return none, none, np.zeros(0, dtype=object), pd.DataFrame(columns=EVENT_COLUMNS)
    st.retire(old, left, np.where(how[gone] == 1, REMOVAL_REASONS.index("Total Loss"), REMOVAL_REASONS.index("Destroyed or Stolen")))
    op = vp[gone]
    np.maximum.at(T.last_gone, op, left)
    replace = R.random(len(old)) < np.where(p["n_veh"][op] > 1, C.P_REPLACE_AFTER_TOTAL_LOSS["multi"],
                                             C.P_REPLACE_AFTER_TOTAL_LOSS["single"])
    buy = left + population.draw_lag(R, len(old), **C.TOTAL_LOSS_REPLACEMENT_DELAY)
    now = replace & (buy < b[gone])
    later = replace & ~now & (buy < T.x_pol[op])
    after = replace & ~now & ~later & (T.cancel_day[op] < 0) & (T.x_pol[op] == T.e[op])
    np.subtract.at(p["n_veh"], op[~replace], 1)
    sim.pending, sim.pending_day = np.r_[sim.pending, old[after]], np.r_[sim.pending_day, buy[after]]
    arrivals = pd.DataFrame(dict(pol=op[later], day=buy[later], kind=ARRIVAL, target=old[later], extra=-1))
    first_new = len(v["pol"])
    if now.any():
        st.add_replacements(old[now], _draw_replacements(sim, old[now], buy[now]))
    Vn = np.arange(first_new, len(st.v["pol"]))
    return Vn, st.v["added_day"][Vn], np.full(len(Vn), CHANGE_REASONS[ARRIVAL], dtype=object), arrivals


def _events(*parts: pd.DataFrame) -> pd.DataFrame:
    """Concatenate change schedules (pol, day, kind, target, extra), all integers."""
    return pd.concat([p_[EVENT_COLUMNS] for p_ in parts], ignore_index=True).astype("int64")


def _cancel(T: Term, pols: np.ndarray, day: np.ndarray, reason: str) -> None:
    T.cancel_day[pols], T.cancel_reason[pols], T.x_pol[pols] = day, CANCEL_REASONS.index(reason), day


def _premium(sim, V, day, eff, points, acc, tenure_years, term_years):
    """Full-term premium for vehicles V rated as of `day` on a term effective on `eff` (whose filed rates apply)."""
    cd = rating.codes(sim.st, sim.ref.cal, V, day, points, acc, tenure_years)
    return rating.premium(sim.plan, cd, rating.limit_factors(sim.st, V), sim.ref.cal.rate_level_at(eff), term_years), cd


def _stop_at_total_loss(occ: pd.DataFrame, feat: pd.DataFrame, wrecks: pd.DataFrame, nv: int):
    """Keep each vehicle's losses up to and including the first that destroys it (a total loss the company
    pays and takes the wreck from, or a wreck nobody pays us for). A vehicle's losses form independent Poisson
    processes, so dropping everything after that loss gives exactly the losses of a vehicle insured until
    then. Returns (occ, feat, day destroyed or -1, 1 for a company total loss / 2 for another wreck)."""
    stop_day, how, first_occ = np.full(nv, -1), np.zeros(nv, dtype=int), np.full(nv, -1)
    company = occ[occ.occ.isin(feat.occ[feat.total.to_numpy().astype(bool) & ~feat.retained.to_numpy().astype(bool)])]
    ends = pd.concat([company[["vrow", "day", "occ"]].assign(how=1), wrecks[["vrow", "day", "occ"]].assign(how=2)],
                     ignore_index=True)
    if len(ends) == 0:
        return occ, feat, stop_day, how
    first = ends.sort_values(["vrow", "day", "how", "occ"], kind="stable").drop_duplicates("vrow")
    vr = first.vrow.to_numpy().astype(int)
    stop_day[vr], how[vr], first_occ[vr] = first.day.to_numpy(), first.how.to_numpy(), first.occ.to_numpy()
    ov, day = occ.vrow.to_numpy(), occ.day.to_numpy()
    sd = stop_day[ov]
    drop = (sd >= 0) & ((day > sd) | ((day == sd) & (occ.occ.to_numpy() != first_occ[ov])))
    occ = occ[~drop].reset_index(drop=True)
    feat = feat[feat.occ.isin(occ.occ)].reset_index(drop=True)
    return occ, feat, stop_day, how


def _refresh_usage(sim: Sim) -> None:
    """Rebuild who drives which car from the vehicles and drivers now on each policy."""
    v, drv = sim.st.v, sim.pop.drv
    act, da = np.flatnonzero(v["active"]), drv.active.to_numpy()
    usage, assigned = population.usage_table(v["veh"][act], v["pol"][act], v["primary_drv"][act], v["extra_vehicle"][act],
                                             drv.drv.to_numpy()[da], drv.pol.to_numpy()[da])
    full = np.zeros(len(drv), dtype=bool)
    full[:min(len(assigned), len(drv))] = assigned[:len(drv)]
    sim.st.set_usage(usage)
    drv["assigned"] = full


# ----------------------------------------------------------------------------------------- changes
def _window(T_s, x_pol):
    """In-extract part of each policy's term in which a change can happen: days w0+1 .. w1-1."""
    w0 = np.maximum(T_s, 0)
    return w0, x_pol, np.clip(x_pol - w0 - 1, 0, None) / 365.25


def _schedule_events(sim: Sim, P: np.ndarray, s_all: np.ndarray, x_pol: np.ndarray) -> pd.DataFrame:
    """Draw the household changes that will happen during this term, each on a random day."""
    st, R, cal, p, v, drv = sim.st, sim.R, sim.ref.cal, sim.st.p, sim.st.v, sim.pop.drv
    n = len(s_all)
    w0, w1, yrs = _window(s_all, x_pol)
    in_p = np.zeros(n, dtype=bool)
    in_p[P] = True
    parts = []

    def happen(pol, rate, kind, target, extra=-1):
        hit = R.random(len(pol)) < 1 - np.exp(-rate * yrs[pol])
        day = w0[pol] + 1 + np.floor(R.random(len(pol)) * np.maximum(w1[pol] - w0[pol] - 1, 0)).astype(int)
        hit &= w1[pol] - w0[pol] > 1
        parts.append(pd.DataFrame(dict(pol=pol[hit], day=day[hit], kind=np.broadcast_to(kind, hit.shape)[hit],
                                       target=np.broadcast_to(target, hit.shape)[hit], extra=np.broadcast_to(extra, hit.shape)[hit])))

    # vehicles: traded in for another, or sold from a multi-car household
    V = np.flatnonzero(v["active"] & in_p[v["pol"]])
    vp = v["pol"][V]
    age = cal.year_frac(s_all[vp]) - v["model_year"][V]
    h_trade = np.interp(age, C.REPLACE_AGE_KNOTS, C.REPLACE_HAZARD)
    h_trade = np.where((v["ownership"][V] == "Leased") & (age >= 3), C.LEASE_END_HAZARD, h_trade)
    n_cars = np.bincount(v["pol"][v["active"]], minlength=n)
    h_sell = np.where(n_cars[vp] >= 2, C.VEHICLE_SELL_RATE * np.where(v["extra_vehicle"][V], 1.5, 1.0), 0.0)
    kind = np.where(R.random(len(V)) * (h_trade + h_sell) < h_trade, TRADE, SELL)
    happen(vp, h_trade + h_sell, kind, V)

    # drivers: children and other adults moving out, divorce, death
    d_act = drv.active.to_numpy()
    D = np.flatnonzero(d_act & in_p[drv.pol.to_numpy()])
    dp, role = drv.pol.to_numpy()[D], drv.role.to_numpy()[D]
    dob = drv.dob_day.to_numpy()
    age = (s_all[dp] - dob[D]) / 365.25
    ni_married = drv.marital.to_numpy()[p["ni_drv"][dp]] == "M"
    h_leave = np.where(role == 3, np.interp(age, C.CHILD_LEAVE_AGE_KNOTS, C.CHILD_LEAVE_RATE) * (age >= 18),
                       np.where(role == 2, C.OTHER_ADULT_LEAVE_RATE, 0.0))
    h_div = np.where((role == 1) & ni_married, C.DIVORCE_RATE, 0.0)
    h_death = np.where(age >= C.MORTALITY_AGE_KNOTS[0], np.interp(age, C.MORTALITY_AGE_KNOTS, C.MORTALITY_RATE), 0.0)
    h = h_leave + h_div + h_death
    u = R.random(len(D)) * h
    code = np.where(u < h_leave, np.where(role == 3, 1, 2), np.where(u < h_leave + h_div, 3, 4))
    happen(dp, h, LEAVE, D, code)

    # households: moves within the area, an extra car, a newly licensed teenager, a new spouse
    ni = p["ni_drv"][P]
    ni_age = (s_all[P] - dob[ni]) / 365.25
    owner = p["homeowner"][P].astype(bool)
    hit_move = R.random(len(P)) < 1 - np.exp(-np.where(owner, C.MOVE_RATE["owner"], C.MOVE_RATE["renter"]) * yrs[P])
    movers = P[hit_move]
    day = w0[movers] + 1 + np.floor(R.random(len(movers)) * np.maximum(w1[movers] - w0[movers] - 1, 0)).astype(int)
    ok = w1[movers] - w0[movers] > 1
    parts.append(pd.DataFrame(dict(pol=movers[ok], day=day[ok], kind=MOVE, target=-1, extra=_destinations(sim, movers[ok]))))

    d_pol, d_age = drv.pol.to_numpy(), (s_all[drv.pol.to_numpy()] - dob) / 365.25
    no_car = np.bincount(d_pol[d_act & ~drv.assigned.to_numpy() & (d_age >= 17)], minlength=n)
    happen(P, np.where(no_car[P] > 0, C.VEHICLE_ADD_RATE_NO_CAR, C.VEHICLE_ADD_RATE) * (n_cars[P] < 4), ADD, -1)
    teen = np.array(C.KID_RATE_BY_VEHICLES)[np.clip(p["n_veh"][P], 1, 4) - 1] / C.TEEN_YEARS_AT_HOME
    happen(P, teen * (ni_age >= 36) * (ni_age <= 60) * (p["n_drv"][P] < 5), TEEN, -1)
    spouse = np.bincount(d_pol[d_act & (drv.role.to_numpy() == 1)], minlength=n) > 0
    unmarried = (drv.marital.to_numpy()[ni] != "M") & ~spouse[P]
    happen(P, unmarried * np.interp(ni_age, C.MARRIAGE_AGE_KNOTS, C.MARRIAGE_RATE) * (ni_age >= 18), MARRY, -1)
    return _events(*parts)


def _destinations(sim: Sim, pols: np.ndarray) -> np.ndarray:
    """New home ZIP for each moving policy: mostly nearby, in proportion to households with a vehicle."""
    z = sim.ref.zips
    if len(pols) == 0:
        return np.zeros(0, dtype=int)
    zi = sim.st.p["zi"][pols]
    lat, lon = z.lat.to_numpy(), z.lon.to_numpy()
    dist = 69 * np.hypot(lat[zi, None] - lat[None, :], (lon[zi, None] - lon[None, :]) * 0.745)
    w = z.households_with_vehicle.to_numpy()[None, :] * np.exp(-dist / C.MOVE_DISTANCE_MILES)
    w[np.arange(len(pols)), zi] = 0.0
    return population.row_choice(w, sim.R)


def _pending_arrivals(sim: Sim, renewing: np.ndarray, s_all: np.ndarray, x_pol: np.ndarray) -> pd.DataFrame:
    """Replacements for cars totalled late last term: on the policy from the start if already bought, else
    an ARRIVAL change on the day they are. Dropped if the policy did not renew."""
    pend, pday = sim.pending, sim.pending_day
    sim.pending, sim.pending_day = np.zeros(0, dtype=int), np.zeros(0, dtype=int)
    pp = sim.st.v["pol"][pend]
    arrive = np.maximum(pday, s_all[pp])
    ok = renewing[pp] & (arrive < x_pol[pp])
    now = ok & (arrive == s_all[pp])
    if now.any():
        sim.st.add_vehicles(_draw_replacements(sim, pend[now], arrive[now]))
    later = ok & ~now
    return pd.DataFrame(dict(pol=pp[later], day=arrive[later], kind=ARRIVAL, target=pend[later], extra=-1))


def _apply_events(sim: Sim, T: Term, due: pd.DataFrame) -> dict:
    """Apply the changes in `due` (each on its own policy's boundary day). Returns {policy: [labels]}."""
    st, p, R = sim.st, sim.st.p, sim.R
    labels: dict = {}
    for kind in range(len(CHANGE_REASONS)):
        e = due[due.kind == kind].drop_duplicates(["pol", "target"] if kind in (ARRIVAL, TRADE, LEAVE) else ["pol"])
        if len(e) == 0:
            continue
        pol, day, tgt, extra = (e[c].to_numpy() for c in ("pol", "day", "target", "extra"))
        v = st.v
        n_cars = np.bincount(v["pol"][v["active"]], minlength=len(T.s))
        if kind == ARRIVAL:
            ok = np.ones(len(e), dtype=bool)
            st.add_vehicles(_draw_replacements(sim, tgt, day))
        elif kind == TRADE:
            ok = v["active"][tgt]
            st.retire(tgt[ok], day[ok], REMOVAL_REASONS.index("Replaced"))
            st.add_vehicles(_draw_replacements(sim, tgt[ok], day[ok]))
        elif kind == SELL:
            ok = v["active"][tgt] & (n_cars[pol] >= 2)
            st.retire(tgt[ok], day[ok], REMOVAL_REASONS.index("Sold"))
            np.subtract.at(p["n_veh"], pol[ok], 1)
            np.maximum.at(T.last_gone, pol[ok], day[ok])
        elif kind == LEAVE:
            ok = _drivers_leave(sim, T, pol, day, tgt, extra)
        elif kind == MARRY:
            drv = sim.pop.drv
            ni = p["ni_drv"][pol]
            ok = drv.marital.to_numpy()[ni] != "M"
            if ok.any():
                _marry(sim, pol[ok], day[ok])
        elif kind == TEEN:
            ok = np.ones(len(e), dtype=bool)
            ages, probs = zip(*C.TEEN_LICENCE_AGE_P.items())
            age = R.choice(ages, len(e), p=probs) + R.random(len(e)) * 0.95
            _new_drivers(sim, pol, day, role=3, age=age, male=R.random(len(e)) < 0.5, licensed=day, marital="S")
        elif kind == ADD:
            ok = n_cars[pol] < 4
            _add_vehicles(sim, pol[ok], day[ok], np.full(ok.sum(), -1))
        else:   # MOVE
            ok = np.ones(len(e), dtype=bool)
            _move(sim, pol, day, extra)
        for q in pol[ok]:
            labels.setdefault(int(q), []).append(CHANGE_REASONS[kind])
    return labels


def _drivers_leave(sim: Sim, T: Term, pol, day, who, code) -> np.ndarray:
    """Drivers leave a policy (codes: 1 child or 2 other adult moved out, 3 divorce, 4 death). A leaving
    driver's own car usually goes with them; otherwise another household driver takes it over."""
    st, p, R = sim.st, sim.st.p, sim.R
    drv = sim.pop.drv
    ok = drv.active.to_numpy()[who]
    pol, day, who, code = pol[ok], day[ok], who[ok], code[ok]
    is_ni = who == p["ni_drv"][pol]
    active = drv.active.to_numpy().copy()
    role, marital = drv.role.to_numpy().copy(), drv.marital.to_numpy().copy()
    removed, why = drv.removed_day.to_numpy().copy(), drv.removal_reason.to_numpy().copy()
    d_pol = drv.pol.to_numpy()
    for q, d, w, c, ni in zip(pol, day, who, code, is_ni):
        if ni:      # the named insured died: a surviving spouse takes the policy over, or it is cancelled
            spouse = np.flatnonzero((d_pol == q) & active & (role == 1))
            if len(spouse):
                s0 = spouse[0]
                role[s0], marital[s0], p["ni_drv"][q] = 0, "W", s0
            else:
                _cancel(T, np.array([q]), np.array([d]), "Insured Deceased")
                continue
        elif c == 3:
            marital[p["ni_drv"][q]] = "D"
        elif c == 4 and role[w] == 1:
            marital[p["ni_drv"][q]] = "W"
        active[w], removed[w], why[w] = False, d, c
        p["n_drv"][q] -= 1
    drv["active"], drv["role"], drv["marital"] = active, role, marital
    drv["removed_day"], drv["removal_reason"] = removed, why
    left = ~active[who]
    _hand_over_cars(sim, T, who[left], day[left], code[left])
    return left


def _hand_over_cars(sim: Sim, T: Term, who, day, code) -> None:
    st, p, R = sim.st, sim.st.p, sim.R
    v, drv = st.v, sim.pop.drv
    take_p = np.array([0.0, C.TAKES_CAR_P["child"], C.TAKES_CAR_P["other"], C.TAKES_CAR_P["divorce"], C.TAKES_CAR_P["death"]])
    owner_day = dict(zip(who, day))
    owner_code = dict(zip(who, code))
    cars = np.flatnonzero(v["active"] & np.isin(v["primary_drv"], who))
    d_assigned = drv.assigned.to_numpy().copy()
    for car in cars:
        q, w = v["pol"][car], v["primary_drv"][car]
        n_cars = np.count_nonzero(v["active"] & (v["pol"] == q))
        if n_cars > 1 and R.random() < take_p[owner_code[w]]:
            st.retire(np.array([car]), np.array([owner_day[w]]), REMOVAL_REASONS.index("Left With Driver"))
            p["n_veh"][q] -= 1
            T.last_gone[q] = max(T.last_gone[q], owner_day[w])
            continue
        v["primary_drv"][car], v["extra_vehicle"][car] = _driver_for_car(sim, q, d_assigned)


def _driver_for_car(sim: Sim, pol: int, assigned: np.ndarray, day: int = None) -> tuple[int, bool]:
    """Who drives a car that needs a new main driver: a current driver without a car of their own if there is
    one, else the named insured (as an extra household car if they already have one). Updates `assigned`."""
    drv, p = sim.pop.drv, sim.st.p
    free = (drv.pol.to_numpy() == pol) & drv.active.to_numpy() & ~assigned
    if day is not None:
        free &= (day - drv.dob_day.to_numpy()) / 365.25 >= 16
    free = np.flatnonzero(free)
    who = int(free[0]) if len(free) else int(p["ni_drv"][pol])
    extra = bool(assigned[who])
    assigned[who] = True
    return who, extra


def _new_drivers(sim: Sim, pol, day, role, age, male, licensed, marital) -> np.ndarray:
    """Add drivers to policies from `day`. Returns their IDs. Adults bring a driving record with them."""
    st, p, R, ref, cal = sim.st, sim.st.p, sim.R, sim.ref, sim.ref.cal
    drv = sim.pop.drv
    m = len(pol)
    dob = (day - age * 365.25).astype(int)
    zr = ref.zips.iloc[p["zi"][pol]]
    in_city = (zr.region == "City of Chicago").to_numpy()
    employed, commute = population.draw_commute(R, age, zr, in_city)
    if role == 3:
        employed, commute = np.zeros(m, dtype=bool), np.zeros(m)
    ni = p["ni_drv"][pol]
    own_name = (role != 3) & (R.random(m) < 0.20)
    ids = len(drv) + np.arange(m)
    new = pd.DataFrame(dict(
        pol=pol, role=role, age=age, drv=ids, ord=p["n_drv"][pol], male=male, marital=marital, dob_day=dob,
        licensed_day=licensed, latent=R.gamma(C.LATENT_GAMMA_SHAPE, 1 / C.LATENT_GAMMA_SHAPE, m) * p["household_factor"][pol],
        good_grades=(role == 3) & (R.random(m) < C.GOOD_STUDENT_GRADES_P),
        school_end_day=dob + (population.school_end_age(R, m) * 365.25).astype(int), commute_miles=commute, employed=employed,
        first_name=np.where(male, R.choice(ref.first_m, m), R.choice(ref.first_f, m)),
        last_name=np.where(own_name, R.choice(ref.last, m), drv.last_name.to_numpy()[ni]), assigned=False, added_day=day,
        removed_day=-1, removal_reason=0, active=True))
    sim.pop.drv = pd.concat([drv, new[drv.columns]], ignore_index=True)
    np.add.at(p["n_drv"], pol, 1)
    t0 = np.maximum(day - C.LOOKBACK_DAYS, licensed)
    inc = [population.violations(new, t0, np.full(m, cal.valuation_day), R)]
    if role != 3:      # an adult joining arrives with accidents from a previous insurer
        hazard = sim.pop.zip_truth.true_crash_hazard.to_numpy()[p["zi"][pol]]
        inc.append(population.prior_accidents(R, new.assign(assigned=True), t0, day, day, hazard, cal))
    inc = pd.concat(inc, ignore_index=True)
    inc["pol"] = sim.pop.drv.pol.to_numpy()[inc.drv.to_numpy()]
    sim.pop.incidents = pd.concat([sim.pop.incidents, inc[sim.pop.incidents.columns]], ignore_index=True)
    sim.recs.add(inc.drv, inc.day, inc.kind.map(KIND), inc.known_day)
    return ids


def _marry(sim: Sim, pol, day) -> None:
    p, R, drv = sim.st.p, sim.R, sim.pop.drv
    ni = p["ni_drv"][pol]
    ni_age = (day - drv.dob_day.to_numpy()[ni]) / 365.25
    age = np.clip(ni_age + R.normal(0, 3.5, len(pol)), 18, 90)
    male = ~drv.male.to_numpy()[ni] ^ (R.random(len(pol)) < 0.03)
    licensed = (day - (age - 16 - np.minimum(R.exponential(0.8, len(pol)), age - 16)) * 365.25).astype(int)
    marital = drv.marital.to_numpy().copy()
    marital[ni] = "M"
    drv["marital"] = marital
    spouse = _new_drivers(sim, pol, day, role=1, age=age, male=male, licensed=licensed, marital="M")
    brings = R.random(len(pol)) < C.SPOUSE_BRINGS_CAR_P
    _add_vehicles(sim, pol[brings], day[brings], spouse[brings])


def _add_vehicles(sim: Sim, pol, day, primary) -> None:
    """A household buys an additional car. Its driver is `primary`, or a driver with no car of their own,
    or the named insured (as an extra household car)."""
    if len(pol) == 0:
        return
    st, p, R, ref, cal = sim.st, sim.st.p, sim.R, sim.ref, sim.ref.cal
    v, drv = st.v, sim.pop.drv
    d_assigned = drv.assigned.to_numpy().copy()
    dob = drv.dob_day.to_numpy()
    primary, extra = primary.copy(), np.zeros(len(pol), dtype=bool)
    for i, q in enumerate(pol):
        if primary[i] < 0:
            primary[i], extra[i] = _driver_for_car(sim, q, d_assigned, day[i])
        else:
            d_assigned[primary[i]] = True
    zi = p["zi"][pol]
    density = ref.zips.population_density_sqmi.to_numpy()[zi]
    in_city = (ref.zips.region.to_numpy() == "City of Chicago")[zi]
    new = population.draw_vehicles(ref, R, pol, cal.year_frac(day), p["inc_rel"][pol], density, age_scale=4.3, age_shape=2.0)
    new["true_miles"], new["reported_miles"], new["use"] = population.draw_mileage(
        R, drv.commute_miles.to_numpy()[primary], (day - dob[primary]) / 365.25, drv.employed.to_numpy()[primary], extra, in_city)
    new["parking"] = population.draw_parking(R, density, p["homeowner"][pol].astype(bool))
    vage = (cal.year_frac(day) - new.model_year.to_numpy()).clip(0)
    new["ownership"] = population.draw_ownership(R, vage)
    p_full = population.full_coverage_probability(vage, p["inc_rel"][pol], p["score_z"][pol], p["tier"][pol])
    new["has_coll"] = (new.ownership.to_numpy() != "Owned") | (R.random(len(pol)) < p_full)
    new["has_comp"] = new.has_coll | (R.random(len(pol)) < C.P_COMP_ONLY)
    new["full_glass"] = new.has_comp & (R.random(len(pol)) < C.FULL_GLASS_P)
    new["coll_ded_opt"], new["comp_ded_opt"] = population.draw_deductibles(R, p["inc_rel"][pol], p["score_z"][pol])
    last_rank = np.full(len(p["zi"]), -1)
    np.maximum.at(last_rank, v["pol"][v["active"]], v["rank"][v["active"]])
    new["rank"] = last_rank[pol] + 1 + (pd.Series(pol).groupby(pol).cumcount().to_numpy())
    new["primary_drv"], new["extra_vehicle"] = primary, extra
    new["veh"] = len(v["pol"]) + np.arange(len(pol))
    new["added_day"], new["removed_day"], new["active"] = day, -1, True
    new["removal_reason"], new["replaces"], new["salvage_title"] = 0, -1, False
    st.add_vehicles(new)
    np.add.at(p["n_veh"], pol, 1)


def _move(sim: Sim, pol, day, new_zi) -> None:
    """The household moves within the area: new garaging ZIP, perhaps a different tenure and parking."""
    st, p, R, ref = sim.st, sim.st.p, sim.R, sim.ref
    v = st.v
    owner = p["homeowner"][pol].astype(bool)
    p["homeowner"][pol] = R.random(len(pol)) < np.where(owner, C.OWNER_AFTER_MOVE_P["owner"], C.OWNER_AFTER_MOVE_P["renter"])
    p["zi"][pol] = new_zi
    where = np.zeros(len(p["zi"]), dtype=bool)
    where[pol] = True
    cars = np.flatnonzero(v["active"] & where[v["pol"]])
    v["zi"][cars] = p["zi"][v["pol"][cars]]
    v["parking"][cars] = population.draw_parking(R, ref.zips.population_density_sqmi.to_numpy()[v["zi"][cars]],
                                                 p["homeowner"][v["pol"][cars]].astype(bool))


def _renewal_changes(sim: Sim, renewing: np.ndarray, s_all: np.ndarray, ty: np.ndarray, change: np.ndarray) -> None:
    """Coverage changes at renewal: salvage-title cars lose physical damage cover, loans are paid off, older
    owned cars drop collision, and after a large increase some customers raise their deductibles."""
    st, R, cal = sim.st, sim.R, sim.ref.cal
    v = st.v
    idx = np.flatnonzero(v["active"] & renewing[v["pol"]])
    pol = v["pol"][idx]
    salvage = idx[v["salvage_title"][idx]]
    v["has_coll"][salvage] = v["has_comp"][salvage] = v["full_glass"][salvage] = False
    paid_off = idx[(v["ownership"][idx] == "Financed") & (R.random(len(idx)) < 1 - np.exp(-ty[pol] / C.LOAN_YEARS))]
    v["ownership"][paid_off] = "Owned"
    age = cal.year_frac(s_all[pol]) - v["model_year"][idx]
    h = np.interp(age, C.DROP_PD_AGE_KNOTS, C.DROP_PD_RATE)
    drop = idx[(v["ownership"][idx] == "Owned") & v["has_coll"][idx] & (R.random(len(idx)) < 1 - np.exp(-h * ty[pol]))]
    keep_comp = R.random(len(drop)) < C.KEEP_COMP_WHEN_DROPPING_COLL_P
    v["has_coll"][drop], v["has_comp"][drop] = False, keep_comp
    v["full_glass"][drop] &= keep_comp
    rd = C.RAISE_DEDUCTIBLE
    p_up = np.clip(rd["base"] + rd["per_increase"] * np.maximum(change[pol] - 0.10, 0), 0, rd["cap"])
    up = idx[v["has_coll"][idx] & (v["coll_ded_opt"][idx] < len(C.COLL_DEDUCTIBLES) - 1) & (R.random(len(idx)) < p_up)]
    v["coll_ded_opt"][up] += 1
    v["comp_ded_opt"][up] = np.minimum(v["comp_ded_opt"][up] + 1, len(C.COMP_DEDUCTIBLES) - 1)


def _draw_replacements(sim: Sim, old: np.ndarray, day: np.ndarray) -> pd.DataFrame:
    """New vehicles replacing `old`, insured from `day`. They keep the old vehicle's driver, use and deductibles."""
    st, ref, R = sim.st, sim.ref, sim.R
    cal, v, p = ref.cal, st.v, st.p
    pol = v["pol"][old]
    density = ref.zips.population_density_sqmi.to_numpy()[p["zi"][pol]]
    new = population.draw_vehicles(ref, R, pol, cal.year_frac(day), p["inc_rel"][pol], density,
                                   age_scale=C.REPLACEMENT_AGE["scale"], age_shape=C.REPLACEMENT_AGE["shape"])
    for c in ("rank", "primary_drv", "extra_vehicle", "true_miles", "reported_miles", "use", "parking",
              "coll_ded_opt", "comp_ded_opt"):
        new[c] = v[c][old]
    # the old car's driver may have left the policy since it was written off
    drv = sim.pop.drv
    left = np.flatnonzero(~drv.active.to_numpy()[new.primary_drv.to_numpy()])
    if len(left):
        assigned = drv.assigned.to_numpy().copy()
        primary, extra = new.primary_drv.to_numpy().copy(), new.extra_vehicle.to_numpy().copy()
        for i in left:
            primary[i], extra[i] = _driver_for_car(sim, pol[i], assigned, day[i])
        new["primary_drv"], new["extra_vehicle"] = primary, extra
    vage = (cal.year_frac(day) - new.model_year.to_numpy()).clip(0)
    new["ownership"] = population.draw_ownership(R, vage)
    p_full = population.full_coverage_probability(vage, p["inc_rel"][pol], p["score_z"][pol], p["tier"][pol])
    new["has_coll"] = (new.ownership.to_numpy() != "Owned") | (R.random(len(old)) < p_full)
    new["has_comp"] = new.has_coll | (R.random(len(old)) < C.P_COMP_ONLY)
    new["full_glass"] = new.has_comp & (R.random(len(old)) < C.FULL_GLASS_P)
    new["veh"] = len(v["pol"]) + np.arange(len(old))
    new["added_day"], new["removed_day"], new["active"] = day, -1, True
    new["removal_reason"], new["replaces"], new["salvage_title"] = 0, old, False
    return new
