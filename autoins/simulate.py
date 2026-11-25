"""Walk every policy through its terms: rate it, decide renewal and cancellation, simulate claims.

Policies advance one term per pass. Within a pass everything is vectorised across policies,
so the order of random draws is fixed and the run is reproducible for a given seed.

Information timing. The simulator knows every claim's ultimate cost, but the insurer does not.
Each term is rated before its effective date using only incidents known by then: violations once
they post to the driving record, accidents once they appear on a claims-history report, and the
company's own at-fault claims once their payments make them chargeable (claims.Development).
A mid-term change is rated on the day it happens, with what is known that day.

Renewals. Everything about a renewal is decided on its offer date, 30 to 45 days before it takes
effect, from the policy as it stood that day (_renewals): the underwriting review (drivers on the
policy then, records known then), the telematics score and programme offer, the renewal premium
(the expiring term's exposure rows in force that day: its cars, rated drivers, address and
coverage), and the customer's decision (that premium against what the same cars cost, and the
claims reported by then). The policy is simulated a whole term at a time, so by then the rest of
the expiring term has been simulated too; the decision reads the past from effective-dated
histories (the exposure rows, and the histories on Sim) rather than the current state, so it is
the same whatever happens later. Later events still count as later events: a change between the
offer and the effective date (a move, a car or driver added or gone) re-rates the pending renewal on
the day of the change, as a policy system re-issues it (a revised offer: the term's rating date is
that day and the offer date stays on the term), a cancellation ends the policy before it renews,
and a household with no car left has nothing to renew. Every renewal evaluated is kept
(Result.offers), renewed or not.

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

from dataclasses import dataclass, field, replace

import numpy as np
import pandas as pd

from . import claims
from . import config as C
from . import market, names, population, rating, refdata, telematics, truth
from .refdata import day_weight, stream

CANCEL_REASONS = ["", "Underwriting", "Non-Payment", "Insured Request", "Insured Deceased"]
REMOVAL_REASONS = ["", "Replaced", "Total Loss", "Sold", "Left With Driver", "Destroyed or Stolen"]
DRIVER_REMOVAL_REASONS = ["", "Moved Out", "Moved Out", "Divorce", "Deceased"]   # by leave code 1-4
KIND = {"minor": 0, "major": 1, "accident": 2}
# mid-term changes, in the order they are applied when several fall on one day
ARRIVAL, TRADE, SELL, LEAVE, MARRY, TEEN, ADD, MOVE = range(8)
CRASH_DEATH = 5         # a LEAVE event's code for an insured killed in a crash (recorded as a death, code 4)
CHANGE_REASONS = ["Replacement Vehicle Added", "Vehicle Replaced", "Vehicle Removed", "Driver Removed",
                  "Spouse Added", "Newly Licensed Driver Added", "Vehicle Added", "Address Change"]
END_RAN, END_ENDORSED, END_GONE = 0, 1, 2      # why a risk row ended: term end, endorsement, vehicle gone
EVENT_COLUMNS = ["pol", "day", "kind", "target", "extra"]
WRECKED = 1                     # a SELL event's `extra` when the car has already left (destroyed or stolen): the
                                # endorsement removing it re-rates the policy's other cars (_cut_at_removal)


@dataclass
class Result:
    terms: pd.DataFrame
    rows: pd.DataFrame       # one per policy term x vehicle x endorsement period
    occ: pd.DataFrame        # loss events, with report and chargeable dates
    feat: pd.DataFrame       # coverage-level claim features, developed to ultimate
    pays: pd.DataFrame       # every payment and recovery, including those after the valuation date
    reserves: pd.DataFrame   # every case reserve change, including those after the valuation date
    plan: rating.Plan
    static: truth.Static
    tele: dict = None        # telematics enrolments and scores (see _score_enrolled, _programme_offer)
    offers: pd.DataFrame = None        # every renewal evaluated on its offer day, renewed or not (see _renewals)
    offer_cars: pd.DataFrame = None    # the cars each renewal was offered for, with their telematics discount
    sim: object = None                 # the run's final state (for tests that re-evaluate past decisions)


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


class History:
    """Values that change over time, each recorded with the day it takes effect. at(ids, days) gives the values in
    effect for each id on each day: the latest recorded on or before that day (for an earlier day, the first one
    recorded). Several records for one id on one day: the last one counts. Every id needs a first record."""
    OFF, SPAN = 2 ** 21, 2 ** 22          # days run from about -10**6 (OPENING) to a few thousand

    def __init__(self) -> None:
        self.parts: list = []
        self._t = None

    def add(self, ids, day, *values) -> None:
        # copies: a caller's array (the policies' named insureds, say) may change later, and must not rewrite the past
        ids = np.atleast_1d(np.array(ids, dtype=np.int64))
        self.parts.append((ids, *(np.broadcast_to(np.array(x, dtype=np.int64), ids.shape) for x in (day, *values))))
        self._t = None

    def table(self) -> list:
        """[ids, days, values...] sorted by id and day, keeping only the records that change a value."""
        if self._t is None:
            cols = [np.concatenate(c) for c in zip(*self.parts)]
            order = np.lexsort((np.arange(len(cols[0])), cols[1], cols[0]))
            cols = [c[order] for c in cols]
            ids, day = cols[0], cols[1]
            last = np.r_[(ids[1:] != ids[:-1]) | (day[1:] != day[:-1]), True]
            cols = [c[last] for c in cols]
            changed = np.r_[True, cols[0][1:] != cols[0][:-1]]
            for c in cols[2:]:
                changed[1:] |= c[1:] != c[:-1]
            self._t = [c[changed] for c in cols]
            self._key = self._t[0] * self.SPAN + self._t[1] + self.OFF
        return self._t

    def at(self, ids, days) -> list:
        t = self.table()
        ids = np.asarray(ids, dtype=np.int64)
        j = np.searchsorted(self._key, ids * self.SPAN + np.asarray(days, dtype=np.int64) + self.OFF, "right") - 1
        j = np.maximum(j, np.searchsorted(t[0], ids, "left"))
        return [c[j] for c in t[2:]]


OPENING = -10 ** 6      # the day recorded for the household as it stood before the first simulated day


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
    R_renew: np.random.Generator = None     # the renewal decisions' own draws (see _renewals)
    # Effective-dated histories, so a decision dated in the past sees the household as it stood then:
    assign: History = field(default_factory=History)    # car -> (rated driver, garaging ZIP), from the exposure rows
    marital: History = field(default_factory=History)   # driver -> married (1) or not
    ni: History = field(default_factory=History)        # policy -> named insured
    home: History = field(default_factory=History)      # policy -> homeowner (1) or renter
    n_rows: int = 0
    n_occ: int = 0
    pending: np.ndarray = field(default_factory=lambda: np.zeros(0, dtype=int))      # total-loss cars whose
    pending_day: np.ndarray = field(default_factory=lambda: np.zeros(0, dtype=int))  # replacement comes after the term
    clm_pol: list = field(default_factory=list)     # every claim: its policy and the day it was reported
    clm_report: list = field(default_factory=list)
    af_pol: list = field(default_factory=list)      # the at-fault ones again
    af_report: list = field(default_factory=list)
    tele: "Tele" = None
    last_change: np.ndarray = None      # per policy: the latest day its drivers, cars or address changed
    name_changes: list = field(default_factory=list)   # (drv, day, old surname) when a named insured takes a spouse's
    mile_changes: list = field(default_factory=list)   # (car, day, old, new) true annual miles when a car's use changes
    warm: "Warm" = None                 # the warm-up: losses before the start (see _warm_up)


@dataclass
class Warm:
    """The warm-up (config.warm_up_days): the in-force book's losses in the part of its term before the start,
    simulated and developed on a calendar beginning `off` days earlier (so its day numbers are the extract's plus
    `off`, and every date and working day is right), with draws of their own."""
    cal: object
    off: int
    R: np.random.Generator
    dev: claims.Development


@dataclass
class Tele:
    """Telematics programme state: per policy (current enrolment, last scoring day, re-offer date) and the records."""
    R: np.random.Generator
    eid: np.ndarray
    last_scored: np.ndarray
    block: np.ndarray
    device: np.ndarray
    enrol: list = field(default_factory=list)       # (enrolment id, pol, start day, device)
    ended: dict = field(default_factory=dict)       # enrolment id -> (end day, reason)
    void: set = field(default_factory=set)          # opted in with a renewal that did not take effect: never started
    scores: list = field(default_factory=list)      # DataFrames, one per pass

    def end(self, pols: np.ndarray, day: np.ndarray, reason: str, st, void: bool = False) -> None:
        """End the enrolments of policies `pols` on `day` (or, with void, cancel enrolments that never started)."""
        pols, day = np.asarray(pols), np.broadcast_to(np.asarray(day), np.shape(pols))
        on = self.eid[pols] >= 0
        for e, d in zip(self.eid[pols][on], day[on]):
            if void:
                self.void.add(int(e))
            else:
                self.ended.setdefault(int(e), (int(d), reason))
        self.eid[pols] = -1
        cars = np.isin(st.v["pol"], pols)
        st.v["tele_on"][cars] = False
        st.v["tele_disc"][cars] = 0.0


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
    # the day the company knew the last car had gone (a car written off is known from the claim's first notice,
    # though its removal is backdated to the day after the loss); a period re-rated after a write-off is rated no
    # earlier than the day it was known (rate_from); the day a cancellation for want of a car was known
    last_known: np.ndarray = None
    rate_from: np.ndarray = None
    cancel_known: np.ndarray = None

    def __post_init__(self):
        n = len(self.s)
        self.last_known = np.full(n, -1) if self.last_known is None else self.last_known
        self.rate_from = np.full(n, -10 ** 9) if self.rate_from is None else self.rate_from
        self.cancel_known = np.full(n, -10 ** 9) if self.cancel_known is None else self.cancel_known


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
              dev=claims.Development(cal, stream(cfg.seed, "claims"), stream(cfg.seed, "claim detail")), recs=recs,
              R_renew=stream(cfg.seed, "renewal"))
    off = C.warm_up_days(cfg)
    if off > 0:
        wcal = refdata.load(replace(cfg, start=str(cal.start - np.timedelta64(off, "D")))).cal
        sim.warm = Warm(cal=wcal, off=off, R=stream(cfg.seed, "warm-up losses"),
                        dev=claims.Development(wcal, stream(cfg.seed, "warm-up claims"), stream(cfg.seed, "warm-up claim detail")))
        sim.warm.dev.n_feat = 10 ** 9           # feature numbers apart from the extract's own
    sim.tele = Tele(R=stream(cfg.seed, "telematics"), eid=np.full(n, -1), last_scored=np.full(n, -10 ** 6),
                    block=np.full(n, -10 ** 6), device=np.zeros(n, dtype=int))
    sim.last_change = np.full(n, -10 ** 6)
    # the household before the first simulated day: who drives each car, where, and who is married
    v0, d0 = st.v, pop.drv
    sim.assign.add(np.arange(len(v0["pol"])), OPENING, v0["primary_drv"], v0["zi"])
    sim.marital.add(d0.drv.to_numpy(), OPENING, d0.marital.to_numpy() == "M")
    sim.ni.add(np.arange(n), OPENING, p["ni_drv"])
    sim.home.add(np.arange(n), OPENING, p["homeowner"])
    R = sim.R
    tm = p["term_months"]
    ty = tm / 12
    quote_w = np.array([C.DAY_WEIGHTS["quote"][c] for c in C.CHANNELS])[p["channel"]]
    active = np.ones(n, dtype=bool)
    last_term, last_offer, last_cancel = np.full(n, -1), np.full(n, OPENING), np.full(n, -1)
    terms, rows, offers, offer_cars, nonrenew_term, nonrenew_reason = [], [], [], [], [], []
    prev_rows, ending = None, (np.zeros(0, dtype=int), np.zeros(0, dtype=int))
    n_terms = k = 0

    while True:
        s_all = cal.day_of(p["first_month"] + k * tm, p["dom"])
        e_all = cal.day_of(p["first_month"] + (k + 1) * tm, p["dom"])
        term_no = p["tenure_terms"] + k + 1
        # renewals are rated and offered by a batch that runs on business days; a new customer is quoted on a day
        # the channel is open (config.DAY_WEIGHTS)
        u_lead = R.random(n)
        lead = np.where(term_no > 1,
                        cal.weighted_lead(s_all, *C.RENEWAL_OFFER_LEAD_DAYS, lambda d: cal.is_business(d).astype(float), u_lead),
                        cal.weighted_lead(s_all, *C.NEW_BUSINESS_QUOTE_LEAD_DAYS, lambda d: day_weight(cal, d, quote_w[:, None, :]), u_lead))
        rate_day = s_all - lead               # the offer day: underwriting, the offer and telematics scoring happen on it
        if k == 0 and "quote_day" in p:       # a new customer is quoted on the day its company was chosen
            rate_day = np.where(term_no == 1, p["quote_day"], rate_day)
        tenure_years = (p["tenure_terms"] + k) * ty
        if k == 0:
            P = np.flatnonzero(active & (s_all <= V_DAY))
        else:
            # every policy in force on its offer day is offered its renewal, if the offer falls by the valuation
            # date: one cancelled later in the expiring term too, and one whose renewal takes effect after it
            P = np.flatnonzero((active | ((last_cancel >= 0) & (last_cancel > rate_day))) & (last_term >= 0) & (rate_day <= V_DAY))
        if len(P) == 0:
            break
        change = np.zeros(n)
        _score_enrolled(sim, P, s_all, rate_day)
        if k == 0:
            _programme_offer(sim, P, k, s_all, rate_day, term_no)
        else:
            P, off, cars = _renewals(sim, P, k, s_all, rate_day, tenure_years, ty, term_no, last_term, last_offer,
                                     last_cancel, prev_rows, change)
            offers.append(off)
            offer_cars.append(cars)
            ended = off[off.outcome.isin(["Company Non-Renewal", "Insured Did Not Renew"])]
            nonrenew_term.append(ended.exp_term.to_numpy())
            nonrenew_reason.append(ended.outcome.to_numpy())
            active[off.pol[off.outcome != "Renewed"].to_numpy()] = False
        # a cancelled policy's enrolment ends on its cancellation day, once its renewal offer has been scored
        sim.tele.end(ending[0], ending[1], "Policy Canceled", st)
        if len(P) == 0:
            break

        # mid-term cancellation; a term already running on the start date can only end after it
        s, e = s_all[P], e_all[P]
        tdays = e - s
        p_nonpay = np.array([C.NONPAY_RATE[x] for x in C.PAY_PLANS])[p["pay_plan"][P]] * ty[P] \
            * np.clip(np.exp(-0.6 * p["score_z"][P]), 0.3, 4.0) * np.where(p["tier"][P] == 2, 1.6, 1.0) \
            * np.exp(C.STABILITY_CANCEL["nonpay"] * p["stab"][P]) * np.where(term_no[P] == 1, C.NONPAY_NEW_BUSINESS, 1.0)
        p_request = C.MIDTERM_INSURED_REQUEST_RATE * ty[P] * np.exp(C.STABILITY_CANCEL["request"] * p["stab"][P])
        p_uw = C.UW_CANCEL_NEW_BUSINESS_P * np.where(p["prior_insurance"][P], 1, 3) * ~p["is_initial"][P] * (k == 0)
        u, f = R.random(len(P)), R.random(len(P))
        reason = np.where(u < p_uw, 1, np.where(u < p_uw + p_nonpay, 2, np.where(u < p_uw + p_nonpay + p_request, 3, 0)))
        # underwriting reviews new business in its first 60 days; a policy found ineligible gets a notice of
        # cancellation at least 30 days ahead (215 ILCS 5/143.15; tables._communications mails it)
        cday = s + np.where(reason == 1, C.UW_CANCEL_DAYS[0] + f * (C.UW_CANCEL_DAYS[1] - C.UW_CANCEL_DAYS[0]),
                            5 + f * (tdays - 6)).astype(int)
        # non-payment: the cancellation follows a missed monthly instalment (config.NONPAY_*; billing.py bills it)
        missed, due = _missed_installment(sim, P, p["first_month"][P] + k * tm[P], term_no[P] == 1, R.random(len(P)))
        grace = R.integers(C.NONPAY_GRACE_DAYS[0], C.NONPAY_GRACE_DAYS[1] + 1, len(P))
        reason = np.where((reason == 2) & (missed < 0), 0, reason)          # no instalment left to miss inside the extract
        cday = np.where(reason == 2, np.minimum(due + grace, e - 1), cday)
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
        rated = _rerated(sim, rate_day, s_all, term_no)
        term_of_pol = np.full(n, -1)
        term_of_pol[P] = n_terms + np.arange(len(P))
        if k > 0:
            # a renewal re-rated after a household change between its offer and its effective date (_rerated)
            op = off.pol.to_numpy()
            off["term"] = term_of_pol[op]
            off["revised_day"] = np.where(off.term.to_numpy() >= 0, np.where(rated[op] > off.offer_day.to_numpy(), rated[op], -1),
                                          off.revised_day.to_numpy())
        missed_inst = np.full(n, -1)
        missed_inst[P[cancelled & (reason == 2)]] = missed[cancelled & (reason == 2)]
        T = Term(s=s_all, e=e_all, x_pol=x_pol, cancel_day=cancel_day, cancel_reason=cancel_reason, rate_day=rated,
                 tenure=tenure_years, ty=ty, term_of_pol=term_of_pol, last_gone=np.full(n, -1))
        term_rows = _simulate_term(sim, T, P, events)

        terms.append(pd.DataFrame(dict(
            term=term_of_pol[P], pol=P, term_no=term_no[P], s=s_all[P], e=e_all[P], offer_day=rate_day[P], rate_day=rated[P],
            cancel_day=cancel_day[P], cancel_reason=np.array(CANCEL_REASONS)[cancel_reason[P]], cancel_known=T.cancel_known[P],
            rate_level=cal.rate_level_at(s_all[P]), new_business=term_no[P] == 1, month0=p["first_month"][P] + k * tm[P],
            # the instalment whose non-payment cancelled the term (a term cancelled earlier for another reason,
            # such as its last car going, keeps that reason)
            missed_installment=np.where(cancel_reason[P] == CANCEL_REASONS.index("Non-Payment"), missed_inst[P], -1))))
        rows.append(term_rows)
        prev_rows = term_rows
        last_offer[P], last_term[P], last_cancel[P] = rate_day[P], term_of_pol[P], cancel_day[P]
        done = P[cancel_day[P] >= 0]
        ending = (done, cancel_day[done])
        active[done] = False
        n_terms += len(P)
        k += 1
    sim.tele.end(ending[0], ending[1], "Policy Canceled", st)

    terms = pd.concat(terms, ignore_index=True)
    terms["nonrenewal_reason"] = ""
    if nonrenew_term:
        terms.loc[np.concatenate(nonrenew_term), "nonrenewal_reason"] = np.concatenate(nonrenew_reason)
    pop.veh = pd.DataFrame({c: st.v[c] for c in pop.veh.columns})     # now includes every vehicle ever insured
    for c in ("n_drv", "n_veh", "ni_drv", "zi", "homeowner", "bi_opt", "um_opt"):   # the policy as it stands at the end
        pop.pol[c] = st.p[c]
    occ, feat, pays, reserves = sim.dev.result()
    if sim.warm is not None and sim.warm.dev.occs:
        occ, feat, pays, reserves = (pd.concat([a_, _shifted(b_, -sim.warm.off)], ignore_index=True)
                                     for a_, b_ in zip((occ, feat, pays, reserves), sim.warm.dev.result()))
    tl = sim.tele
    enrol = pd.DataFrame(tl.enrol, columns=["eid", "pol", "start", "device"])
    end = enrol.eid.map(lambda e: tl.ended.get(e, (-1, ""))[0])
    enrol = enrol.assign(end=end, reason=enrol.eid.map(lambda e: tl.ended.get(e, (-1, ""))[1]))
    scores = pd.concat(tl.scores, ignore_index=True) if tl.scores else pd.DataFrame()
    # an opt-in with a renewal that did not take effect never started: drop it and number the rest in order
    enrol = enrol[~enrol.eid.isin(tl.void)].reset_index(drop=True)
    new_id = pd.Series(np.arange(len(enrol)), index=enrol.eid)
    enrol["eid"] = np.arange(len(enrol))
    if len(scores):
        scores["eid"] = new_id.reindex(scores.eid).to_numpy()
    no_offers = pd.DataFrame(columns=["pol"])
    return Result(terms=terms, rows=pd.concat(rows, ignore_index=True), occ=occ, feat=feat, pays=pays, reserves=reserves,
                  plan=plan, static=st, tele={"enrol": enrol, "scores": scores},
                  offers=pd.concat(offers, ignore_index=True) if offers else no_offers,
                  offer_cars=pd.concat(offer_cars, ignore_index=True) if offer_cars else no_offers, sim=sim)


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
        # a change that could not happen as the policy now stands (a trade of a car already gone, a sale from a
        # one-car household, a teenager whose parents are too young) is dropped before it can end a period: a
        # period ends only at a change the policy records
        ev = ev[_feasible(sim, T, ev)]
        upcoming = ev[live[ev.pol.to_numpy()]]
        # a death due of a household's only driver ends the policy that day (rentals stop then)
        d_act = sim.pop.drv.active.to_numpy()
        n_drv_on = np.bincount(sim.pop.drv.pol.to_numpy()[d_act], minlength=n)
        dies = upcoming[(upcoming.kind.to_numpy() == LEAVE) & (upcoming.extra.to_numpy() == 4)]
        dies = dies[n_drv_on[dies.pol.to_numpy()] == 1]
        T.death_end = np.full(n, np.iinfo(np.int64).max // 4)
        np.minimum.at(T.death_end, dies.pol.to_numpy(), dies.day.to_numpy())
        # (and one already developed, from a loss late last term, is cut short too)
        sim.dev.stop_rentals(dies.pol.to_numpy(), dies.day.to_numpy())
        if sim.warm is not None:
            sim.warm.dev.stop_rentals(dies.pol.to_numpy(), dies.day.to_numpy() + sim.warm.off)
        np.minimum.at(nb, upcoming.pol.to_numpy(), upcoming.day.to_numpy())
        v = st.v
        V = np.flatnonzero(v["active"] & live[v["pol"]] & (v["added_day"] <= clock[v["pol"]]))
        a, why = clock[v["pol"][V]], reason_now[v["pol"][V]]
        started = np.zeros(n, dtype=bool)
        ran = np.zeros(n, dtype=bool)                   # a row of the policy runs to its boundary
        while len(V):
            # a policy's rows are rated in date order, so a replacement car joining later in the term is rated
            # knowing the claims of cars that joined before it
            vpol = st.v["pol"][V]                       # (vehicle arrays grow as replacements are added)
            first_a = np.full(n, np.iinfo(np.int64).max)
            np.minimum.at(first_a, vpol, a)
            now = a == first_a[vpol]
            # a crash death can cut a policy's rows only in the batch that starts its period (simulate._crash_deaths)
            fresh = ~started[vpol[now]]
            Vn, an, whyn, arrivals = _simulate_rows(sim, T, V[now], a[now], why[now], nb, out, fresh)
            started[vpol[now]] = True
            V, a, why = np.r_[V[~now], Vn], np.r_[a[~now], an], np.r_[why[~now], whyn]
            ev = _events(ev, arrivals)
            r_ = out[-1]
            ran[r_.pol.to_numpy()[r_.end_kind.to_numpy() != END_GONE]] = True
            # a policy whose cars all left in the period (a replacement on its way) has no row running to its
            # boundary yet: if a change to a car now gone set that boundary, the boundary moves to the next change
            # that can still happen, so the replacement's row does not end at a change that does not happen
            loose = live & ~ran
            if loose.any() and len(ev):
                ev = ev[_feasible(sim, T, ev) | ~loose[ev.pol.to_numpy()]]
                up = ev[loose[ev.pol.to_numpy()]]
                again = T.x_pol.copy()
                np.minimum.at(again, up.pol.to_numpy(), up.day.to_numpy())
                nb[loose] = again[loose]

        # a policy whose last car has gone, with no replacement coming, is cancelled the day it went; so is one
        # whose replacement will not come before its renewal can be offered (as _simulate_rows decides for a household
        # left with no car: there would be nothing on the policy to renew). Losing its last car can take more than
        # one period (a car written off while another was left, then that one), so it is judged here again
        v = st.v
        has_car = np.bincount(v["pol"][v["active"]], minlength=n) > 0
        arr = ev[ev.kind.to_numpy() == ARRIVAL]
        ap = arr.pol.to_numpy()
        early = (arr.day.to_numpy() < T.e[ap] - C.RENEWAL_OFFER_LEAD_DAYS[1]) | (T.x_pol[ap] < T.e[ap])
        has_car[ap[early]] = True
        # (unless it went the day after the valuation date, or the company does not yet know: a car written off is
        # known from the claim's first notice; the cancellation is then backdated to the day it went)
        empty = in_prog[~has_car[in_prog] & (T.last_gone[in_prog] >= 0) & (T.last_gone[in_prog] <= sim.ref.cal.valuation_day)
                        & (T.last_known[in_prog] <= sim.ref.cal.valuation_day)]
        # an insured killed in the crash that took the last car is dead by then: the death is recorded first (a named
        # insured with no spouse to take over ends the policy as a death), and the policy cancelled after it
        dead = ev[np.isin(ev.pol.to_numpy(), empty) & (ev.kind.to_numpy() == LEAVE) & (ev.extra.to_numpy() == CRASH_DEATH)]
        if len(dead):
            was = T.cancel_day.copy()
            _apply_events(sim, T, dead.assign(day=np.minimum(dead.day.to_numpy(), T.last_gone[dead.pol.to_numpy()])))
            ev = ev.drop(index=dead.index)
            empty = empty[T.cancel_day[empty] == was[empty]]      # not those the death has just ended
        _cancel(T, empty, T.last_gone[empty], "Insured Request")
        T.cancel_known[empty] = T.last_known[empty]
        live[empty] = False
        ev = ev[live[ev.pol.to_numpy()] | (ev.day.to_numpy() > nb[ev.pol.to_numpy()])]

        # apply the changes falling on each policy's boundary
        pe = ev.pol.to_numpy()
        due = live[pe] & (ev.day.to_numpy() == nb[pe]) & (nb[pe] < T.x_pol[pe])
        labels = _apply_events(sim, T, ev[due])
        changed = np.fromiter(labels.keys(), dtype=int, count=len(labels))
        sim.last_change[changed] = np.maximum(sim.last_change[changed], nb[changed])
        ev = ev[~due & (live[pe] | (ev.kind.to_numpy() == ARRIVAL))]
        reason_now[:] = ""
        for pol, lab in labels.items():
            reason_now[pol] = "; ".join(dict.fromkeys(lab))
        if labels:
            _refresh_usage(sim, nb)
        clock[in_prog] = np.minimum(nb[in_prog], T.x_pol[in_prog])
        in_prog = in_prog[clock[in_prog] < T.x_pol[in_prog]]
        ev = ev[np.isin(ev.pol.to_numpy(), in_prog)]

    rows = pd.concat(out, ignore_index=True)
    pol, x, a = rows.pol.to_numpy(), rows.x.to_numpy(), rows.s.to_numpy()
    span = T.e[pol] - T.s[pol]
    cancelled = T.cancel_day[pol] >= 0
    # rows ending at a change that turned out to be a cancellation are cancelled like any other
    ran = (rows.end_kind.to_numpy() == END_RAN) | ((rows.end_kind.to_numpy() == END_ENDORSED) & cancelled & (x == T.cancel_day[pol]))
    # a car destroyed on the valuation date leaves the day after it, and a car written off whose claim is not yet
    # reported is not yet known to have gone: its row still runs
    ran |= (rows.end_kind.to_numpy() == END_GONE) & ((x > sim.ref.cal.valuation_day)
                                                     | (rows.gone_known.to_numpy() > sim.ref.cal.valuation_day))
    rows["end_kind"] = np.where(ran, END_RAN, rows.end_kind)
    sched = np.where(ran, T.e[pol], x)                  # cover as written, before any cancellation
    return rows.assign(
        sched=sched, earned_exposure=(x - np.maximum(a, 0)) / 365.25, earned_share=(x - np.maximum(a, 0)) / span,
        written_share=(sched - a) / span, return_share=(sched - x) * cancelled / span,
        before_share=(np.minimum(x, 0) - np.minimum(a, 0)) / span, at_start=a == T.s[pol])


def _simulate_rows(sim: Sim, T: Term, V, a, why, nb, out: list, fresh=None):
    """Rate vehicles V from day a and simulate their losses up to their policy's next boundary. Appends risk
    rows to `out`. Returns the replacements that arrive before the boundary (to simulate next), and as events the
    replacements arriving later in the term and the insureds killed in a crash (_crash_deaths, which can bring a
    policy's boundary forward in `nb`). fresh: the vehicle's policy has no other rows yet in this period."""
    st, cal, R, p, v = sim.st, sim.ref.cal, sim.R, sim.st.p, sim.st.v
    drv = sim.pop.drv
    vp = v["pol"][V]
    b = nb[vp]
    dr = v["primary_drv"][V]
    # a change is rated with what is known that day (a write-off's removal, backdated, once the company knows of it)
    asof = np.where(a == T.s[vp], T.rate_day[vp], np.maximum(a, T.rate_from[vp]))
    points, _, acc = sim.recs.for_rows(dr, a, asof)
    prem, cd, fair = _premium(sim, V, a, T.s[vp], points, acc, T.tenure[vp], T.ty[vp])
    ctx = truth.context(st, cal, V, a, b)
    watched = np.where(v["tele_on"][V], telematics.BEHAVIOUR_FACTOR, 1.0)     # drivers take more care while monitored
    for k_ in ("AF_MV", "AF_SV"):
        ctx["rate"][k_] = ctx["rate"][k_] * watched
    # a car its owner kept after a total loss earlier in the term is on a salvage certificate: not driven, no losses
    # (and a car lost in a claim the company will not hear of by the valuation date is still insured, as far as it
    # knows, but has no further losses)
    salvaged = (v["salvage_day"][V] >= T.s[vp]) | v["lost_unknown"][V]
    for k_ in ctx["rate"]:
        ctx["rate"][k_] = ctx["rate"][k_] * ~salvaged
    ctx["idle"] = salvaged                              # (nor is it out in a storm's path)
    occ, feat, wrecks, deaths, sim.n_occ = truth.simulate(ctx, st, cal, R, sim.n_occ)
    occ["notice"] = claims.first_notice(cal, occ, R)
    occ, feat, stop_day, how, stop_occ = _stop_at_total_loss(occ, feat, wrecks, len(V))
    # when the company knows a car has gone: from the claim's first notice when the loss is claimed here (a total
    # loss, or a wreck with any claim on the policy), otherwise from the day after it (the customer takes it off)
    notice = pd.Series(occ.notice.to_numpy(), index=occ.occ.to_numpy())
    # (claimed here: a total loss, or a wreck with a physical damage, rental or towing claim, all opened at first
    # notice; a wreck with only liability claims, presented later, is the customer taking the car off)
    pd_feat = feat.occ.to_numpy()[np.isin(feat.cvg.to_numpy(), ["COLL", "COMP", "RENT", "TOW"])]
    claimed = (how == 1) | ((how == 2) & np.isin(stop_occ, pd_feat))
    known = np.where(claimed, np.maximum(notice.reindex(stop_occ).fillna(-1).to_numpy().astype(np.int64), stop_day + 1),
                     stop_day + 1)
    fresh = np.ones(len(V), dtype=bool) if fresh is None else fresh
    occ, feat, stop_day, how, b, died = _crash_deaths(T, st.p["ni_drv"], vp, b, nb, fresh, occ, feat, deaths, stop_day, how)
    occ, feat, stop_day, how, b, removed = _cut_at_removal(T, V, vp, b, nb, fresh, occ, feat, stop_day, how, known,
                                                           cal.valuation_day)
    died = _events(died, removed)
    feat = _rentals_until_death(T, vp, occ, feat)
    # a car lost in a claim not reported by the valuation date stays on the policy: the company does not know
    unknown = (stop_day >= 0) & (known > cal.valuation_day)
    v["lost_unknown"][V[unknown]] = True
    stop_day, how = np.where(unknown, -1, stop_day), np.where(unknown, 0, how)
    gone = stop_day >= 0
    x = np.where(gone, stop_day + 1, b)
    truth.set_window(ctx, cal, a, x)
    exp_loss = truth.expected(ctx, cal)
    row_ids = sim.n_rows + np.arange(len(V))
    sim.n_rows += len(V)
    sim.assign.add(V, a, dr, v["zi"][V])           # who drives the car, and where it is kept, from day a
    out.append(pd.DataFrame(dict(
        row=row_ids, term=T.term_of_pol[vp], pol=vp, veh=V, drv=dr, s=a, x=x, gone_known=np.where(gone, known, -1),
        end_kind=np.where(gone, END_GONE, np.where(b < T.x_pol[vp], END_ENDORSED, END_RAN)),
        zi=v["zi"][V], rated_on=asof, reason=why, driver_age=(a - drv.dob_day.to_numpy()[dr]) / 365.25,
        violation_points=points, at_fault_accidents=acc, tenure_years=T.tenure[vp],
        class_code=cd["class"], score_tier=cd["score_tier"], good_student=cd["good_student"],
        homeowner=cd["homeowner"], married=cd["married"], acv=ctx["acv"], multi_car=cd["multi_car"],
        reported_miles=v["reported_miles"][V], use=v["use"][V], parking=v["parking"][V], true_miles=v["true_miles"][V],
        multi_policy=cd["multi_policy"], paid_in_full=cd["paid_in_full"], inexperienced=cd["inexperienced"],
        occasional_youthful=cd["occasional_youthful"], bi_opt=p["bi_opt"][vp], um_opt=p["um_opt"][vp], med_opt=p["med_opt"][vp],
        coll_ded=np.where(v["has_coll"][V], np.array(C.COLL_DEDUCTIBLES)[v["coll_ded_opt"][V]], 0),
        comp_ded=np.where(v["has_comp"][V], np.array(C.COMP_DEDUCTIBLES)[v["comp_ded_opt"][V]], 0),
        full_glass=v["full_glass"][V], rent_opt=np.where(v["has_rent"][V], v["rent_opt"][V], -1), has_tow=v["has_tow"][V],
        tele_on=v["tele_on"][V], tele_disc=v["tele_disc"][V],
        **{f"prem_{c}": prem[c] for c in C.COVERAGES}, **{f"exp_{c}": exp_loss[c] for c in C.COVERAGES}, fair=fair)))

    if len(occ):
        occ["ownership"] = v["ownership"][occ.veh.to_numpy()]         # at the loss: a lender is paid off on a total loss
        kept = occ.occ.isin(feat.occ[feat.retained.to_numpy().astype(bool)])
        v["salvage_title"][V[occ.vrow[kept].to_numpy()]] = True      # owner kept a paid total loss
        v["salvage_day"][V[occ.vrow[kept].to_numpy()]] = occ.day[kept].to_numpy()
        v["ownership"][V[occ.vrow[kept].to_numpy()]] = "Owned"        # the settlement paid off any loan or lease on it
        occ["term"] = T.term_of_pol[occ.pol.to_numpy()]
        occ["row"] = row_ids[occ.pop("vrow").to_numpy()]
        occ = sim.dev.add(occ, feat)
        sim.clm_pol.append(occ.pol.to_numpy())
        sim.clm_report.append(occ.report_day.to_numpy())
        af = occ.at_fault.to_numpy().astype(bool)
        sim.af_pol.append(occ.pol.to_numpy()[af])
        sim.af_report.append(occ.report_day.to_numpy()[af])
        ch = occ[occ.chargeable_day > claims.NO_DAY]
        sim.recs.add(ch.drv, ch.day, np.full(len(ch), KIND["accident"]), ch.chargeable_day)

    if sim.warm is not None:
        _warm_up(sim, T, V, a, x, row_ids, watched)

    # cars destroyed or stolen leave the policy; most households replace them
    old, left = V[gone], x[gone]
    none = np.zeros(0, dtype=int)
    if len(old) == 0:
        return none, none, np.zeros(0, dtype=object), died
    seen = known[gone]                          # the day the company knew (its removal is backdated to `left`)
    st.retire(old, left, np.where(how[gone] == 1, REMOVAL_REASONS.index("Total Loss"), REMOVAL_REASONS.index("Destroyed or Stolen")),
              known=seen)
    op = vp[gone]
    np.maximum.at(T.last_gone, op, left)
    np.maximum.at(T.last_known, op, seen)
    # the policy's next rows are rated no earlier than the removal is known (a car added the same day, say)
    np.maximum.at(T.rate_from, op, np.where(seen > left, seen, -10 ** 9))
    # a pending renewal is revised once the removal is known; one not known before the renewal takes effect does
    # not revise it (nor hide an earlier change that does)
    np.maximum.at(sim.last_change, op, np.where(seen <= T.e[op], np.maximum(left, seen), -10 ** 9))
    replace = R.random(len(old)) < np.where(p["n_veh"][op] > 1, C.P_REPLACE_AFTER_TOTAL_LOSS["multi"],
                                             C.P_REPLACE_AFTER_TOTAL_LOSS["single"])
    # (a replacement is put on the policy once the loss has been reported)
    buy = np.maximum(left + population.draw_lag(R, len(old), **C.TOTAL_LOSS_REPLACEMENT_DELAY), seen)
    # a household left with no car that will not have its replacement before the renewal is offered cancels the
    # policy instead (and insures the next car when it buys it): there is nothing on the policy to renew
    no_car = np.bincount(v["pol"][v["active"]], minlength=len(p["zi"]))[op] == 0
    replace &= ~(no_car & (buy >= T.e[op] - C.RENEWAL_OFFER_LEAD_DAYS[1]))
    now = replace & (buy < b[gone])
    later = replace & ~now & (buy < T.x_pol[op])
    after = replace & ~now & ~later & (T.cancel_day[op] < 0) & (T.x_pol[op] == T.e[op])
    np.subtract.at(p["n_veh"], op, 1)          # one car fewer until a replacement arrives (multi-car status follows)
    sim.pending, sim.pending_day = np.r_[sim.pending, old[after]], np.r_[sim.pending_day, buy[after]]
    arrivals = pd.DataFrame(dict(pol=op[later], day=buy[later], kind=ARRIVAL, target=old[later], extra=-1))
    first_new = len(v["pol"])
    if now.any():
        st.add_replacements(old[now], _draw_replacements(sim, old[now], buy[now]))
        np.add.at(p["n_veh"], op[now], 1)
        np.maximum.at(sim.last_change, op[now], buy[now])
    Vn = np.arange(first_new, len(st.v["pol"]))
    return Vn, st.v["added_day"][Vn], np.full(len(Vn), CHANGE_REASONS[ARRIVAL], dtype=object), _events(arrivals, died)


def _rentals_until_death(T: Term, vp, occ: pd.DataFrame, feat: pd.DataFrame) -> pd.DataFrame:
    """A rental for a crash ends when the household's only driver dies (T.death_end: the day a death is due that
    leaves no driver, ending the policy): it is paid for the days until then, and not at all if that is the day
    of the loss."""
    end = getattr(T, "death_end", None)
    if end is None or len(feat) == 0 or "rent_days" not in feat:
        return feat
    r = np.flatnonzero(feat.cvg.to_numpy() == "RENT")
    if len(r) == 0:
        return feat
    o = occ.set_index("occ")
    fo = feat.occ.to_numpy()[r]
    left = end[vp[o.vrow.reindex(fo).to_numpy().astype(int)]] - o.day.reindex(fo).to_numpy()
    days = feat.rent_days.to_numpy().astype(float)[r]
    short = left < days
    if not short.any():
        return feat
    feat = feat.copy()
    share = np.where(short, np.clip(left, 0, None) / np.maximum(days, 1), 1.0)
    for col in ("gross", "paid", "subro"):
        if col in feat:
            vals = feat[col].to_numpy().astype(float).copy()
            vals[r] = vals[r] * share
            feat[col] = vals
    rd = feat.rent_days.to_numpy().astype(float).copy()
    rd[r] = np.where(short, np.clip(left, 0, None), rd[r])
    feat["rent_days"] = rd
    gone = np.zeros(len(feat), dtype=bool)
    gone[r[short & (left <= 0)]] = True
    return feat[~gone].reset_index(drop=True)


def _cut_rows(T: Term, vp, b, nb, occ, feat, stop_day, how, cut, crash=None, who=None):
    """End the period of the policies with cut[pol] >= 0 on that day: their rows in this batch end there, nothing on
    them from that day is kept (it is simulated again in the next period), a car's loss after it no longer ends the
    car, and the policy's next boundary is that day. With crash and who (per policy: the crash day and the set of
    (policy, driver) keys killed), the dead's own driving after the crash is dropped too."""
    op = vp[occ.vrow.to_numpy().astype(int)]
    oday = occ.day.to_numpy()
    drop = (cut[op] >= 0) & (oday >= cut[op])
    if crash is not None:
        key = lambda q, w: q.astype(np.int64) * (1 << 32) + w.astype(np.int64)
        drop |= (cut[op] >= 0) & np.isin(key(op, occ.drv.to_numpy()), who) & (oday > crash[op])
    occ = occ[~drop].reset_index(drop=True)
    feat = feat[feat.occ.isin(occ.occ)].reset_index(drop=True)
    vc = cut[vp]
    late = (vc >= 0) & (stop_day >= vc)
    stop_day, how = np.where(late, -1, stop_day), np.where(late, 0, how)
    b = np.where(vc >= 0, np.minimum(b, vc), b)
    pol = np.flatnonzero(cut >= 0)
    np.minimum.at(nb, pol, cut[pol])
    return occ, feat, stop_day, how, b


def _cut_at_removal(T: Term, V, vp, b, nb, fresh, occ, feat, stop_day, how, known=None, v_day=None):
    """A car destroyed or stolen leaves the policy the day after the loss, and the policy records its removal that
    day (a SELL event marked WRECKED): the policy's other cars are re-rated from then, so a multi-car discount ends
    with the car it depended on. Only in the batch that starts the policy's period (where all its cars are), and
    before the period's end. `known`: the day the company knew the car had gone (a company total loss from the
    claim's first notice); a removal not known by the valuation date `v_day` is not made (the company still has the
    car on the policy), and the re-rated period is rated no earlier than the day it was known (T.rate_from).
    Returns (occ, feat, stop_day, how, boundary per vehicle, the removal events)."""
    none = pd.DataFrame(columns=EVENT_COLUMNS)
    known = stop_day + 1 if known is None else known
    seen = np.ones(len(stop_day), dtype=bool) if v_day is None else known <= v_day
    gone = np.flatnonzero((stop_day >= 0) & fresh & seen)
    if len(gone) == 0:
        return occ, feat, stop_day, how, b, none
    n = len(T.s)
    left = stop_day[gone] + 1
    cut = np.full(n, np.iinfo(np.int64).max)
    np.minimum.at(cut, vp[gone], left)
    # the policy keeps another car past that day (not one lost the same day), within its period
    stays = (stop_day < 0) | (stop_day + 1 > cut[vp])
    keeps = np.bincount(vp[stays], minlength=n) > 0
    pol = np.unique(vp[gone])
    pol = pol[keeps[pol] & (cut[pol] <= nb[pol]) & (cut[pol] < T.x_pol[pol])]     # (on the boundary: it is the change there)
    if len(pol) == 0:
        return occ, feat, stop_day, how, b, none
    c = np.full(n, -1, dtype=np.int64)
    c[pol] = cut[pol]
    if getattr(T, "rate_from", None) is not None:      # (only the removal the period ends at: a later loss is simulated again)
        at_cut = np.isin(vp[gone], pol) & (left == cut[vp[gone]])
        np.maximum.at(T.rate_from, vp[gone], np.where(at_cut, known[gone], -10 ** 9))
    occ, feat, stop_day, how, b = _cut_rows(T, vp, b, nb, occ, feat, stop_day, how, c)
    first = pd.Series(V[gone], index=vp[gone]).groupby(level=0).first().reindex(pol).to_numpy()
    return occ, feat, stop_day, how, b, pd.DataFrame(dict(pol=pol, day=c[pol], kind=SELL, target=first, extra=WRECKED))


def _feasible(sim: Sim, T: Term, ev: pd.DataFrame) -> np.ndarray:
    """Which scheduled changes could happen as the policy now stands (the guards of _apply_events): a trade or sale
    of a car still on the policy (a sale only from a household with another car), a driver still on it leaving (a
    divorce only from a spouse), a marriage of a named insured not married, a teenager old enough given the
    parents' ages, a car added to a policy with fewer than four."""
    if len(ev) == 0:
        return np.ones(0, dtype=bool)
    v, drv, p = sim.st.v, sim.pop.drv, sim.st.p
    kind, pol, tgt, extra, day = (ev[c].to_numpy() for c in ("kind", "pol", "target", "extra", "day"))
    n_cars = np.bincount(v["pol"][v["active"]], minlength=len(T.s))
    ok = np.ones(len(ev), dtype=bool)
    car = np.clip(tgt, 0, len(v["pol"]) - 1)
    person = np.clip(tgt, 0, len(drv) - 1)
    ok[kind == TRADE] = v["active"][car[kind == TRADE]]
    m = (kind == SELL) & (extra != WRECKED)
    ok[m] = v["active"][car[m]] & (n_cars[pol[m]] >= 2)
    m = kind == LEAVE
    ok[m] = drv.active.to_numpy()[person[m]] & ((extra[m] != 3) | (drv.role.to_numpy()[person[m]] == 1))
    m = kind == MARRY
    ok[m] = drv.marital.to_numpy()[p["ni_drv"][pol[m]]] != "M"
    m = kind == TEEN
    if m.any():
        ok[m] = (day[m] - _youngest_parent_dob(sim, pol[m])) / 365.25 - 18 >= 16
    m = kind == ADD
    ok[m] = n_cars[pol[m]] < 4
    return ok


def _crash_deaths(T: Term, ni, vp, b, nb, fresh, occ, feat, deaths, stop_day, how):
    """Listed drivers killed in a crash (truth.simulate), at the wheel or riding along, leave the policy as a death
    does (a LEAVE event, code 4: a surviving spouse takes the policy over, or it is cancelled; their cars pass to
    others), the day after they die: the day of the crash or up to a month later. They drive no more after the
    crash, and the policy's rows end on the day they leave, so the rest of the period is rated and simulated without
    them. A fatal crash counts only if it happened (not after its car was destroyed), in the batch that starts the
    policy's period, and before the term's last day; otherwise it leaves its victims badly hurt instead. One fatal
    crash per policy and period, with all its dead. Returns (occ, feat, stop_day, how, boundary per vehicle, LEAVE
    events)."""
    none = pd.DataFrame(columns=EVENT_COLUMNS)
    if len(deaths) == 0:
        return occ, feat, stop_day, how, b, none
    d = deaths.sort_values(["pol", "day", "occ"], kind="stable")
    vr, day, pol = d.vrow.to_numpy().astype(int), d.day.to_numpy().astype(np.int64), d.pol.to_numpy().astype(int)
    sd = stop_day[vr]
    leave = np.minimum.reduce([day + 1 + d.death_delay.to_numpy().astype(np.int64), b[vr], T.x_pol[pol] - 1])
    ok = ((sd < 0) | (day < sd) | d.occ.isin(occ.occ).to_numpy()) & fresh[vr] & (leave >= day + 1)
    first = d[ok].drop_duplicates("pol").set_index("pol").occ      # the first fatal crash of each policy, with all its dead
    ok &= d.occ.to_numpy() == pd.Series(pol).map(first).fillna(-1).to_numpy()
    if "death" in feat:                                   # crashes that did not kill: badly hurt instead
        feat = feat.assign(death=feat.death.to_numpy().astype(bool) & feat.occ.isin(d.occ[ok]).to_numpy())
    if not ok.any():
        return occ, feat, stop_day, how, b, none
    occ = occ.assign(fatal_crash=occ.occ.isin(d.occ[ok]).to_numpy())        # someone died in it (a police report)
    pol, day, leave, victim = pol[ok], day[ok], leave[ok], d.drv.to_numpy()[ok].astype(np.int64)
    n = len(T.s)
    cut, crash = np.full(n, -1, dtype=np.int64), np.full(n, -1, dtype=np.int64)
    cut[pol], crash[pol] = leave, day
    # after the crash its dead drive no more; from the day they leave, nothing on the policy is simulated here
    who = pol.astype(np.int64) * (1 << 32) + victim
    occ, feat, stop_day, how, b = _cut_rows(T, vp, b, nb, occ, feat, stop_day, how, cut, crash, who)
    # the named insured last, so that a spouse killed with them does not take the policy over (_drivers_leave)
    last = np.argsort(victim == ni[pol], kind="stable")
    return occ, feat, stop_day, how, b, pd.DataFrame(dict(pol=pol[last], day=leave[last], kind=LEAVE, target=victim[last],
                                                          extra=CRASH_DEATH))


WARM_DAYS = ["day", "report_day", "chargeable_day", "siu_day", "open_day", "close_day", "attorney_day", "suit_day",
             "reopen_day", "final_close_day"]


def _shifted(frame: pd.DataFrame, by: int) -> pd.DataFrame:
    """The warm-up's records with their day numbers moved by `by` (claims.NO_DAY stays NO_DAY)."""
    frame = frame.copy()
    for c in WARM_DAYS:
        if c in frame:
            d = frame[c].to_numpy().astype(np.int64)
            frame[c] = np.where(d > claims.NO_DAY, d + by, claims.NO_DAY)
    return frame


def _warm_up(sim: Sim, T: Term, V, a, x, row_ids, watched) -> None:
    """Losses on rows of the in-force book in the part of their term before the start (Warm). They become claims
    like any other, developed on the warm-up calendar: those still open on the start date, or reported after it,
    are in the extract (claims.develop); the at-fault ones reach the driver's record when chargeable, and any claim
    counts in the customer's renewal decision. The book in force on the start date is the cars still insured that
    day, so a car written off, destroyed or stolen before it is not in it: such losses are left out."""
    W = sim.warm
    pre = np.flatnonzero(a < 0)
    s, e = np.maximum(a[pre], -W.off), np.minimum(x[pre], 0)
    pre, s, e = pre[e > s], s[e > s], e[e > s]
    if len(pre) == 0:
        return
    st = sim.st
    ctx = truth.context(st, W.cal, V[pre], s + W.off, e + W.off)
    for k_ in ("AF_MV", "AF_SV"):
        ctx["rate"][k_] = ctx["rate"][k_] * watched[pre]
    occ, feat, wrecks, deaths, sim.n_occ = truth.simulate(ctx, st, W.cal, W.R, sim.n_occ)
    # (the opening book is as it stood on the start date: a car destroyed, or an insured killed, before it is not in it)
    gone = occ.occ.isin(wrecks.occ) | occ.occ.isin(feat.occ[feat.total.to_numpy().astype(bool)]) | occ.occ.isin(deaths.occ)
    occ = occ[~gone.to_numpy()].copy()
    feat = feat[feat.occ.isin(occ.occ)]
    if len(occ) == 0:
        return
    occ["term"] = T.term_of_pol[occ.pol.to_numpy()]
    occ["row"] = row_ids[pre][occ.pop("vrow").to_numpy()]
    occ["ownership"] = st.v["ownership"][occ.veh.to_numpy()]
    occ = _shifted(W.dev.add(occ, feat), -W.off)
    sim.clm_pol.append(occ.pol.to_numpy())
    sim.clm_report.append(occ.report_day.to_numpy())
    af = occ.at_fault.to_numpy().astype(bool)
    sim.af_pol.append(occ.pol.to_numpy()[af])
    sim.af_report.append(occ.report_day.to_numpy()[af])
    ch = occ[occ.chargeable_day > claims.NO_DAY]
    sim.recs.add(ch.drv, ch.day, np.full(len(ch), KIND["accident"]), ch.chargeable_day)


def _missed_installment(sim: Sim, P: np.ndarray, month0: np.ndarray, new_business: np.ndarray, u: np.ndarray):
    """For policies P on a monthly plan: which instalment (1 = the first after the down payment) would go unpaid
    if the term were cancelled for non-payment, and the day it falls due. Instalments are due monthly on the
    anniversary day; only those whose cancellation would fall inside the extract count. Returns (instalment or
    -1, due day)."""
    cal, p = sim.ref.cal, sim.st.p
    tm = p["term_months"][P]
    j = np.arange(1, 12)
    due = cal.day_of(month0[:, None] + j[None, :], p["dom"][P][:, None])
    decay = np.where(new_business, C.NONPAY_INSTALLMENT_DECAY["new"], C.NONPAY_INSTALLMENT_DECAY["renewal"])
    w = decay[:, None] ** (j[None, :] - 1) * (j[None, :] < tm[:, None]) * (due + C.NONPAY_GRACE_DAYS[0] >= 0)
    cum = np.cumsum(w, axis=1)
    pick = (u[:, None] * cum[:, -1:] > cum).sum(axis=1).clip(0, len(j) - 1)
    ok = (cum[:, -1] > 0) & (p["pay_plan"][P] > 0)
    return np.where(ok, j[pick], -1), due[np.arange(len(P)), pick]


def _events(*parts: pd.DataFrame) -> pd.DataFrame:
    """Concatenate change schedules (pol, day, kind, target, extra), all integers."""
    return pd.concat([p_[EVENT_COLUMNS] for p_ in parts], ignore_index=True).astype("int64")


def _cancel(T: Term, pols: np.ndarray, day: np.ndarray, reason: str) -> None:
    T.cancel_day[pols], T.cancel_reason[pols], T.x_pol[pols] = day, CANCEL_REASONS.index(reason), day


def _rerated(sim: Sim, offer_day: np.ndarray, s_all: np.ndarray, term_no: np.ndarray) -> np.ndarray:
    """The day each term is finally rated. A renewal is offered on its offer day; if the household changes after
    that and on or before the effective date (a move, a car or driver added or gone), the policy system re-rates
    the pending renewal that day, so the renewal's premium and rating date reflect the change. New business is
    rated on its quote day: its drivers and cars join on the first day by definition."""
    st, drv = sim.st, sim.pop.drv
    last = sim.last_change.copy()
    v = st.v
    a = np.flatnonzero(v["active"])
    np.maximum.at(last, v["pol"][a], v["added_day"][a])
    d = np.flatnonzero(drv.active.to_numpy())
    np.maximum.at(last, drv.pol.to_numpy()[d], drv.added_day.to_numpy()[d])
    late = (term_no > 1) & (last > offer_day) & (last <= s_all)
    return np.where(late, last, offer_day)


def _premium(sim, V, day, eff, points, acc, tenure_years, term_years):
    """Full-term premium for vehicles V rated as of `day` on a term effective on `eff` (whose filed rates apply)."""
    cd = rating.codes(sim.st, sim.ref.cal, V, day, points, acc, tenure_years)
    lim, level = rating.limit_factors(sim.st, V), sim.ref.cal.rate_level_at(eff)
    prem = rating.premium(sim.plan, cd, lim, level, term_years)
    fair = rating.premium(sim.plan, cd, lim, level, term_years, table="indicated")
    keep = 1 - sim.st.v["tele_disc"][V]
    for c in telematics.DISCOUNTED_COVERAGES:
        prem[c] = np.round(prem[c] * keep, 2)
        fair[c] = fair[c] * keep
    return prem, cd, sum(fair.values())


# ----------------------------------------------------------------------------------------- telematics
def _drivers_then(sim: Sim, d: np.ndarray, day: np.ndarray) -> pd.DataFrame:
    """Drivers d as they were on `day` (their marital status then), for truth.driver_multiplier."""
    married = sim.marital.at(d, day)[0]
    return sim.pop.drv.iloc[d].assign(marital=np.where(married == 1, "M", "S"))


def _scored_parts(sim: Sim, V: np.ndarray, ws: np.ndarray, we: np.ndarray):
    """Each car's scoring window [ws, we) in parts driven by one assigned driver (telematics.split_windows, from the
    cars' assignment history), each part starting no earlier than the day the car and its driver were both on the
    policy. Returns (car, start, end, driver)."""
    v, drv = sim.st.v, sim.pop.drv
    ok = we > ws
    t = sim.assign.table()
    w, s, e, d = telematics.split_windows(t[0], t[1], t[2], V[ok], ws[ok], we[ok])
    car = V[ok][w]
    s = np.maximum(s, np.maximum(v["added_day"][car], drv.added_day.to_numpy()[d]))
    keep = e > s
    return car[keep], s[keep], e[keep], d[keep]


def _measure(sim: Sim, car, d, s, e):
    """Driving metrics and score of each car driven by driver d over [s, e), with the driver and the garaging ZIP
    as they were then (telematics.metrics)."""
    mid = (s + e) // 2
    dens = sim.ref.zips.population_density_sqmi.to_numpy()[sim.assign.at(car, mid)[1]]
    mt = telematics.metrics(sim.tele.R, truth.driver_multiplier(_drivers_then(sim, d, mid), mid, sim.ref.cal),
                            (mid - sim.pop.drv.dob_day.to_numpy()[d]) / 365.25, _miles_then(sim, car, s, e), dens, e - s)
    plug_in = sim.tele.device[sim.st.v["pol"][car]] == telematics.DEVICE_TYPES.index("Plug-in Device")
    mt["phone_minutes"] = np.where(plug_in, np.nan, mt["phone_minutes"])     # an OBD dongle cannot see the phone
    return mt, telematics.score(mt, e - s)


def _record_scores(sim: Sim, car, d, s, e, mt, sc, s_all, leave):
    """Publish the scores of window parts (car, driver d, [s, e)). A customer who left the programme on day
    leave[policy] is scored up to then and earns nothing. A car's discount for the term being rated is the average
    of the discounts its scored parts earned, weighted by the days monitored and rounded half up to a whole
    percent, or the participation discount if no part was monitored long enough. Returns (cars, discounts)."""
    v, tl = sim.st.v, sim.tele
    pol = v["pol"][car]
    left = leave[pol] >= 0
    end = np.where(left, np.clip(leave[pol], s, e), e)
    mon = end - s
    frac = np.where(e > s, mon / np.maximum(e - s, 1), 0.0)
    scored = mon >= telematics.MIN_SCORED_DAYS
    earned = scored & ~left
    pct = np.round(telematics.earned_discount(sc) * 100).astype(np.int64)
    # the discount applies from the term being rated, to a car still on the policy when it starts (no day number marks
    # none: -1 is a real day, 31 December before the start)
    applies = np.where(left | ~v["active"][car], -10 ** 9, s_all[pol])
    # a part with any mileage made at least one trip; one with none (rounded to a mile) made none
    trips = np.where(np.round(mt["miles"] * frac) > 0, np.maximum(np.round(mt["trips"] * frac), 1), 0).astype(int)
    tl.scores.append(pd.DataFrame(dict(
        eid=tl.eid[pol], pol=pol, veh=car, drv=d, s=s, e=end, days=mon,
        miles=mt["miles"] * frac, trips=trips, hard_brakes=mt["hard_brakes"],
        rapid_accels=mt["rapid_accels"], speeding_pct=mt["speeding_pct"], phone_minutes=mt["phone_minutes"],
        night_pct=mt["night_pct"], score=np.where(scored, sc, -1), discount=np.where(earned, pct / 100, 0.0),
        applies_s=applies))[mon > 0])
    cars, ci = np.unique(car, return_inverse=True)
    w = np.where(earned, mon, 0).astype(np.int64)
    num = np.bincount(ci, w * pct, len(cars)).astype(np.int64)
    den = np.bincount(ci, w, len(cars)).astype(np.int64)
    car_pct = np.where(den > 0, (2 * num + den) // np.maximum(2 * den, 1), round(telematics.PARTICIPATION_DISCOUNT * 100))
    return cars, np.where(leave[v["pol"][cars]] >= 0, 0.0, car_pct / 100)


def _score_enrolled(sim: Sim, P: np.ndarray, s_all, rate_day) -> None:
    """On each policy's rating date, the cars of policies P in the programme (telematics.py) are scored for the
    driving since the last score: every car monitored and on the policy that day, its window split where its
    assigned driver changed. Some customers leave the programme, more often after poor scores. Cars that joined the
    policy since it enrolled are monitored from the term being rated, on the participation discount."""
    st, p, v, tl = sim.st, sim.st.p, sim.st.v, sim.tele
    n = len(p["zi"])
    enrolled = P[tl.eid[P] >= 0]
    if len(enrolled) == 0:
        return
    on = np.zeros(n, dtype=bool)
    on[enrolled] = True
    day = rate_day[v["pol"]]
    V = np.flatnonzero(on[v["pol"]] & v["tele_on"] & (v["added_day"] <= day) & ((v["removed_day"] < 0) | (v["removed_day"] > day)))
    vp = v["pol"][V]
    car, s, e, d = _scored_parts(sim, V, np.maximum(v["tele_since"][V], tl.last_scored[vp]), rate_day[vp])
    mt, sc = _measure(sim, car, d, s, e)
    # the customer may leave during the window, more often after poor scores (the policy's average car)
    cars, ci = np.unique(car, return_inverse=True)
    car_score = np.bincount(ci, sc * (e - s), len(cars)) / np.maximum(np.bincount(ci, e - s, len(cars)), 1)
    cp = v["pol"][cars]
    avg = np.bincount(cp, car_score, n) / np.maximum(np.bincount(cp, minlength=n), 1)
    start = np.full(n, 10 ** 9)
    np.minimum.at(start, v["pol"][car], s)
    span = np.where(start < 10 ** 9, rate_day - start, 0)
    off = telematics.dropout(tl.R, np.where(span[enrolled] > 0, avg[enrolled], 70.0), span[enrolled], tl.device[enrolled])
    leave = np.full(n, -1)
    leave[enrolled] = np.where(off >= 0, start[enrolled] + off, -1)
    cars, disc = _record_scores(sim, car, d, s, e, mt, sc, s_all, leave)
    v["tele_disc"][cars] = disc
    gone = enrolled[leave[enrolled] >= 0]
    tl.block[gone] = leave[gone] + telematics.REJOIN_WAIT_DAYS
    tl.end(gone, leave[gone], "Opted Out", st)
    stay = enrolled[leave[enrolled] < 0]
    tl.last_scored[stay] = rate_day[stay]
    on[:] = False
    on[stay] = True
    new = np.flatnonzero(on[v["pol"]] & ~v["tele_on"] & (v["active"] | (v["removed_day"] > day)))
    v["tele_on"][new], v["tele_since"][new], v["tele_disc"][new] = True, s_all[v["pol"][new]], telematics.PARTICIPATION_DISCOUNT


def _programme_offer(sim: Sim, P: np.ndarray, k: int, s_all, rate_day, term_no):
    """The programme is offered, with the quote or the renewal offer, to policies P not in it (and not just out of
    it). Take-up depends on the household as quoted (new business) or as it stood on the offer day. A policy joins
    from the term's start, so an opt-in with a renewal that does not take effect never starts (_renewals). A policy
    in the programme when the extract starts joined earlier and was scored before it. Returns (policies offered,
    policies that joined)."""
    st, p, v, cal, tl = sim.st, sim.st.p, sim.st.v, sim.ref.cal, sim.tele
    R, drv, n = tl.R, sim.pop.drv, len(p["zi"])
    offer = P[(tl.eid[P] < 0) & (tl.block[P] <= rate_day[P])]
    if len(offer) == 0:
        return offer, offer
    opening = (k == 0) & p["is_initial"][offer]
    asof = np.where(term_no == 1, s_all, rate_day)
    dp, rem = drv.pol.to_numpy(), drv.removed_day.to_numpy()
    on = np.zeros(n, dtype=bool)
    on[offer] = True
    d = np.flatnonzero(on[dp] & (drv.added_day.to_numpy() <= asof[dp]) & ((rem < 0) | (rem > asof[dp])))
    dpol = dp[d]
    m = truth.driver_multiplier(_drivers_then(sim, d, rate_day[dpol]), rate_day[dpol], cal)
    household = np.bincount(dpol, m, n)[offer] / np.maximum(np.bincount(dpol, minlength=n)[offer], 1)
    young = (rate_day[offer] - drv.dob_day.to_numpy()[sim.ni.at(offer, asof[offer])[0]]) / 365.25 < 30
    base = telematics.base_uptake(cal.year_frac(rate_day[offer]), term_no[offer] == 1, opening)
    join = offer[telematics.uptake(R, base, household, young, p["channel"][offer])]
    if len(join) == 0:
        return offer, join
    was_open = (k == 0) & p["is_initial"][join]
    # a policy in the programme when the extract starts joined it some time after the policy was written
    inception = cal.day_of(p["first_month"][join] - p["tenure_terms"][join] * p["term_months"][join], p["dom"][join])
    # a customer already enrolled when the extract opens joined with an earlier term: on one of the policy's
    # earlier effective dates, within about three years (an enrollment starts with a term, as any opt-in does)
    tmj = p["term_months"][join]
    back_max = np.minimum(p["tenure_terms"][join], np.maximum(36 // tmj, 1))
    back = np.where(back_max > 0, np.floor(R.random(len(join)) * back_max).astype(int) + 1, 0)
    start = np.where(was_open, np.maximum(cal.day_of(p["first_month"][join] - back * tmj, p["dom"][join]), inception), s_all[join])
    dev = telematics.device(R, cal.year_frac(start))
    eid = len(tl.enrol) + np.arange(len(join))
    tl.enrol.extend(zip(eid.tolist(), join.tolist(), start.tolist(), dev.tolist()))
    tl.eid[join], tl.device[join], tl.last_scored[join] = eid, dev, start
    on[:] = False
    on[join] = True
    V = np.flatnonzero(on[v["pol"]] & (v["active"] | (v["removed_day"] > rate_day[v["pol"]])))
    vp = v["pol"][V]
    since = np.zeros(n, dtype=int)
    since[join] = start
    v["tele_on"][V], v["tele_since"][V], v["tele_disc"][V] = True, since[vp], telematics.PARTICIPATION_DISCOUNT
    # policies already in the programme when the extract starts were scored before it: their earned discount applies
    old = V[was_open[np.searchsorted(join, vp)]]
    if len(old):
        op = v["pol"][old]
        car, s, e, d = _scored_parts(sim, old, np.maximum(since[op], rate_day[op] - 180), rate_day[op])
        mt, sc = _measure(sim, car, d, s, e)
        cars, disc = _record_scores(sim, car, d, s, e, mt, sc, s_all, np.full(n, -1))
        v["tele_disc"][cars] = disc
        scored = v["pol"][cars]
        tl.last_scored[scored] = rate_day[scored]
    return offer, join


# ----------------------------------------------------------------------------------------- renewals
UW_NONRENEW_P = 0.5     # share of the policies the underwriting review flags that the company does not renew
CHANNEL_RETENTION = np.array([C.CHANNEL_RETENTION[c] for c in C.CHANNELS])


def underwriting_review(sim: Sim, pols: np.ndarray, offer_day: np.ndarray, eff: np.ndarray) -> np.ndarray:
    """Whether the underwriting review on each policy's offer day flags it for non-renewal: two or more at-fault
    accidents, two or more major violations, or one of each, among the drivers on the policy that day, dated in
    the three years before the renewal and known by the offer day. (Arrays aligned with pols.)"""
    drv = sim.pop.drv
    dp, rem = drv.pol.to_numpy(), drv.removed_day.to_numpy()
    i_of = np.full(len(sim.st.p["zi"]), -1)
    i_of[pols] = np.arange(len(pols))
    j = i_of[dp]
    mine = j >= 0
    o = np.where(mine, offer_day[j], -10 ** 9)
    on = mine & (drv.added_day.to_numpy() <= o) & ((rem < 0) | (rem > o))
    _, majors, acc = sim.recs.as_of(len(dp), np.where(mine, eff[j], 0), o)
    acc, majors = np.bincount(j[on], acc[on], len(pols)), np.bincount(j[on], majors[on], len(pols))
    return (acc >= 2) | (majors >= 2) | ((acc >= 1) & (majors >= 1))


def evaluate_offers(sim: Sim, pols, exp_term, offer_day, eff, since, tenure_years, term_years, ni_age, rows: pd.DataFrame,
                    tele_disc: np.ndarray) -> tuple[dict, pd.DataFrame]:
    """The renewal each policy in `pols` is offered on its offer day for the term effective `eff`, from the policy as
    it stood that day: the expiring term's exposure rows in force on the offer day (its cars, their rated drivers,
    the address and the coverage in force), the incidents known by then and the claims reported by then (since the
    previous offer, `since`). Nothing dated later is used, so the offer is the same whatever the rest of the
    expiring term brings. Also the customer's propensity to accept it (the logit of the renewal model).

    rows: exposure rows holding the expiring terms' (any superset). tele_disc: each car's telematics discount
    from the score taken on the offer day. ni_age: the named insured's age at the renewal. All other arrays are
    aligned with pols. Returns (dict of per-policy arrays, the cars offered with their premium)."""
    st, cal, p = sim.st, sim.ref.cal, sim.st.p
    m = len(pols)
    i_of = np.full(len(p["zi"]), -1)
    i_of[pols] = np.arange(m)
    i = i_of[rows.pol.to_numpy()]
    r = rows[i >= 0]
    i = i[i >= 0]
    snap = (r.term.to_numpy() == exp_term[i]) & (r.s.to_numpy() <= offer_day[i]) & (r.x.to_numpy() > offer_day[i])
    r, i = r[snap], i[snap]
    V, dr, e_ = r.veh.to_numpy(), r.drv.to_numpy(), eff[i]
    points, _, acc = sim.recs.for_rows(dr, e_, offer_day[i])
    house = {"drv": dr, **{c: r[c].to_numpy() for c in ("married", "zi", "homeowner", "multi_car", "occasional_youthful",
                                                         "reported_miles", "use")}}
    coll, comp, rent = r.coll_ded.to_numpy(), r.comp_ded.to_numpy(), r.rent_opt.to_numpy()
    cover = {c: r[c].to_numpy() for c in ("bi_opt", "um_opt", "med_opt")}
    cover.update(has_coll=coll > 0, coll_ded_opt=np.searchsorted(C.COLL_DEDUCTIBLES, coll).clip(0, len(C.COLL_DEDUCTIBLES) - 1),
                 has_comp=comp > 0, comp_ded_opt=np.searchsorted(C.COMP_DEDUCTIBLES, comp).clip(0, len(C.COMP_DEDUCTIBLES) - 1),
                 full_glass=r.full_glass.to_numpy().astype(bool), has_rent=rent >= 0, rent_opt=rent.clip(0),
                 has_tow=r.has_tow.to_numpy().astype(bool))
    cd = rating.codes(st, cal, V, e_, points, acc, tenure_years[i], household=house)
    prem = rating.premium(sim.plan, cd, rating.limit_factors(st, V, cover), cal.rate_level_at(e_), term_years[i])
    keep = 1 - tele_disc[V]
    for c in telematics.DISCOUNTED_COVERAGES:
        prem[c] = np.round(prem[c] * keep, 2)
    total = sum(prem.values())
    premium = np.bincount(i, total, m)
    expiring = np.bincount(i, r[[f"prem_{c}" for c in C.COVERAGES]].sum(axis=1).to_numpy(), m)
    change = np.where(expiring > 0, premium / np.maximum(expiring, 1e-9) - 1, 0.0)
    # the customer's own claims reported since the last offer, up to this one
    cp = np.concatenate(sim.clm_pol) if sim.clm_pol else np.zeros(0, dtype=int)
    cr = np.concatenate(sim.clm_report) if sim.clm_report else np.zeros(0, dtype=int)
    j = i_of[cp]
    cr, j = cr[j >= 0], j[j >= 0]
    prev_claims = np.bincount(j[(cr > since[j]) & (cr <= offer_day[j])], minlength=m)
    ap = np.concatenate(sim.af_pol) if sim.af_pol else np.zeros(0, dtype=int)
    ar = np.concatenate(sim.af_report) if sim.af_report else np.zeros(0, dtype=int)
    j = i_of[ap]
    ar, j = ar[j >= 0], j[j >= 0]
    prev_at_fault = np.bincount(j[(ar > since[j]) & (ar <= offer_day[j])], minlength=m)
    after_claim = C.CLAIM_RETENTION
    homeowner = sim.home.at(pols, offer_day)[0]
    tmo = p["term_months"][pols]
    logit = (np.where(tmo == 6, C.RENEWAL_BASE_LOGIT[6], C.RENEWAL_BASE_LOGIT[12])
             + 0.12 * np.minimum(tenure_years, 6) + 0.4 * p["multi_policy"][pols] + 0.2 * homeowner
             + 0.015 * np.clip(ni_age - 45, -25, 25) - 0.5 * (p["tier"][pols] == 2)
             # a customer who has just had a claim shops around, more so when it was their fault or the second
             + after_claim["any"] * (prev_claims > 0) + after_claim["at_fault"] * (prev_at_fault > 0)
             + after_claim["repeat"] * (prev_claims > 1)
             - C.PRICE_ELASTICITY * np.maximum(change - C.PRICE_TOLERANCE, 0)
             + 2.0 * np.maximum(-change, 0)
             # what the insurer cannot see: the household's stability, its channel's and its agency's hold on it
             + C.STABILITY_RETENTION * p["stab"][pols] + CHANNEL_RETENTION[p["channel"][pols]] + p["agency_retention"][pols]
             # and what it can: a company dearer than the market that day loses more of its renewals
             - C.MARKET_RETENTION * market.gap(cal, offer_day))
    cars = pd.DataFrame(dict(pol=pols[i], exp_term=exp_term[i], veh=V, tele_disc=tele_disc[V], premium=total))
    return dict(n_veh=np.bincount(i, minlength=m), expiring=expiring, premium=premium, change=change,
                prev_claims=prev_claims, logit=logit), cars


def _renewals(sim: Sim, P, k, s_all, rate_day, tenure_years, ty, term_no, last_term, last_offer, last_cancel,
              prev_rows, change):
    """The renewal of each policy in P (in force on its offer day, rate_day), decided on the offer day with the policy
    as it stood then and what was known then, in the order an insurer works: the underwriting review (a company
    non-renewal gets a notice, not an offer), the telematics offer, the renewal premium (evaluate_offers), and the
    customer's decision on it. Nothing after the offer day changes these. Later events still matter: a household
    change before the effective date re-rates the renewal (a revised offer, _rerated), a cancellation before it ends
    the policy, and a household with no car left has nothing to renew. The draws come from the renewal stream, one
    pair per policy per term, so a decision depends only on its own policy's history up to the offer.
    Fills `change` (the offered premium change, by policy). Returns (policies renewing, offers, cars offered)."""
    st, p, v = sim.st, sim.st.p, sim.st.v
    n, V_DAY = len(s_all), sim.ref.cal.valuation_day
    u_company, u_stay = sim.R_renew.random(n)[P], sim.R_renew.random(n)[P]
    o, eff = rate_day[P], s_all[P]
    company = underwriting_review(sim, P, o, eff) & (u_company < UW_NONRENEW_P)
    offered, joined = _programme_offer(sim, P[~company], k, s_all, rate_day, term_no)
    # the named insured's age at the renewal, of the person who was the named insured on the offer day (a surviving
    # spouse who took the policy over by then is a different person; a change after the offer is not yet known)
    ni_age = (eff - sim.pop.drv.dob_day.to_numpy()[sim.ni.at(P, o)[0]]) / 365.25
    ev, cars = evaluate_offers(sim, P, last_term[P], o, eff, last_offer[P], tenure_years[P], ty[P], ni_age, prev_rows,
                               v["tele_disc"])
    p_accept = 1 / (1 + np.exp(-ev["logit"]))
    cancelled = (last_cancel[P] >= 0) & (last_cancel[P] > o)     # (offer days can fall before the start: negative)
    has_car = np.bincount(v["pol"][v["active"]], minlength=n) > 0
    has_car[v["pol"][sim.pending]] = True
    outcome = np.select([cancelled, company, eff > V_DAY, (u_stay >= p_accept) | ~has_car[P]],
                        ["Canceled Before Renewal", "Company Non-Renewal", "Pending", "Insured Did Not Renew"], "Renewed")
    renew = outcome == "Renewed"
    # a household change after the offer re-rates a renewal still to come: a revised offer (for a renewal that takes
    # effect, the term's final rating date, set by run)
    lc = sim.last_change[P]
    # (a change after the valuation date is not yet known: a car wrecked on the valuation date leaves the next day)
    revised = np.where(~company & (lc > o) & (lc <= eff) & (lc <= V_DAY) & (~cancelled | (lc < last_cancel[P])), lc, -1)
    change[P] = ev["change"]
    joined_now, offered_now = np.isin(P, joined), np.isin(P, offered)
    out = ~renew & (outcome != "Pending")
    tl = sim.tele
    tl.end(P[out & joined_now], s_all[P[out & joined_now]], "", st, void=True)
    gone = P[out & ~cancelled]
    tl.end(gone, s_all[gone], "Policy Ended", st)
    off = pd.DataFrame(dict(
        pol=P, exp_term=last_term[P], offer_day=o, eff=eff, n_veh=ev["n_veh"], expiring=ev["expiring"],
        premium=ev["premium"], change=ev["change"], tele_opt=np.select([joined_now, offered_now], ["Y", "N"], ""),
        company=company, p_accept=p_accept, outcome=outcome, revised_day=revised, term=-1,
        # what the evaluation used, kept so tests can evaluate it again from the history
        k=k, since=last_offer[P], tenure=tenure_years[P], ty=ty[P], ni_age=ni_age, prev_claims=ev["prev_claims"],
        u_company=u_company, u_stay=u_stay))
    return P[renew], off, cars


def _stop_at_total_loss(occ: pd.DataFrame, feat: pd.DataFrame, wrecks: pd.DataFrame, nv: int):
    """Keep each vehicle's losses up to and including the first that destroys it (a total loss the company
    pays and takes the wreck from, or a wreck nobody pays us for). A vehicle's losses form independent Poisson
    processes, so dropping everything after that loss gives exactly the losses of a vehicle insured until
    then. A car its owner keeps after a total loss stays on the policy but has no further losses in the term: on a
    salvage certificate it may not be driven until it is rebuilt and inspected (and at renewal it loses its
    physical damage cover). Returns (occ, feat, day destroyed or -1, 1 for a company total loss / 2 for another
    wreck, the occurrence that destroyed it or -1)."""
    kept = occ[occ.occ.isin(feat.occ[feat.total.to_numpy().astype(bool) & feat.retained.to_numpy().astype(bool)])]
    if len(kept):
        first = kept.sort_values(["vrow", "day", "occ"], kind="stable").drop_duplicates("vrow")
        k_day, k_occ = np.full(nv, -1), np.full(nv, -1)
        k_day[first.vrow.to_numpy().astype(int)], k_occ[first.vrow.to_numpy().astype(int)] = first.day.to_numpy(), first.occ.to_numpy()
        kd = k_day[occ.vrow.to_numpy()]
        later = (kd >= 0) & ((occ.day.to_numpy() > kd) | ((occ.day.to_numpy() == kd) & (occ.occ.to_numpy() != k_occ[occ.vrow.to_numpy()])))
        occ = occ[~later].reset_index(drop=True)
        feat = feat[feat.occ.isin(occ.occ)].reset_index(drop=True)
        wd = k_day[wrecks.vrow.to_numpy().astype(int)]
        wrecks = wrecks[~((wd >= 0) & (wrecks.day.to_numpy() > wd))]
    stop_day, how, first_occ = np.full(nv, -1), np.zeros(nv, dtype=int), np.full(nv, -1)
    company = occ[occ.occ.isin(feat.occ[feat.total.to_numpy().astype(bool) & ~feat.retained.to_numpy().astype(bool)])]
    ends = pd.concat([company[["vrow", "day", "occ"]].assign(how=1), wrecks[["vrow", "day", "occ"]].assign(how=2)],
                     ignore_index=True)
    if len(ends) == 0:
        return occ, feat, stop_day, how, first_occ
    first = ends.sort_values(["vrow", "day", "how", "occ"], kind="stable").drop_duplicates("vrow")
    vr = first.vrow.to_numpy().astype(int)
    stop_day[vr], how[vr], first_occ[vr] = first.day.to_numpy(), first.how.to_numpy(), first.occ.to_numpy()
    ov, day = occ.vrow.to_numpy(), occ.day.to_numpy()
    sd = stop_day[ov]
    drop = (sd >= 0) & ((day > sd) | ((day == sd) & (occ.occ.to_numpy() != first_occ[ov])))
    occ = occ[~drop].reset_index(drop=True)
    feat = feat[feat.occ.isin(occ.occ)].reset_index(drop=True)
    return occ, feat, stop_day, how, first_occ


def _give_spare_car(sim: Sim, pol, day, new_drv) -> None:
    """A driver joining without a car of their own (a newly licensed teenager, a new spouse) takes over a spare car
    the household already has (an extra car of a driver with another): the least valuable one. It is driven as they
    drive from the day they join."""
    v = sim.st.v
    cars, when = [], []
    for q, d, w in zip(pol, day, new_drv):
        spare = np.flatnonzero((v["pol"] == q) & v["active"] & v["extra_vehicle"])
        if len(spare) == 0:
            continue
        car = spare[np.argmax(v["rank"][spare])]
        v["primary_drv"][car], v["extra_vehicle"][car] = w, False
        cars.append(car)
        when.append(d)
    _redraw_mileage(sim, np.array(cars, dtype=np.int64), np.array(when, dtype=np.int64))


def _promote_spares(sim: Sim, day_of_pol: np.ndarray) -> None:
    """A driver left with only a spare car (their main car sold or written off) now drives it as their main car:
    it is no longer an extra car, and its mileage and use are theirs from the day of the change."""
    v = sim.st.v
    act = np.flatnonzero(v["active"])
    main = np.zeros(int(v["primary_drv"].max()) + 1 if len(v["primary_drv"]) else 0, dtype=bool)
    main[v["primary_drv"][act[~v["extra_vehicle"][act]]]] = True
    orphan = act[v["extra_vehicle"][act] & ~main[v["primary_drv"][act]]]
    if len(orphan) == 0:
        return
    first = pd.DataFrame(dict(car=orphan, drv=v["primary_drv"][orphan], rank=v["rank"][orphan])).sort_values(
        ["drv", "rank"], kind="stable").drop_duplicates("drv").car.to_numpy()
    v["extra_vehicle"][first] = False
    _redraw_mileage(sim, first, day_of_pol[v["pol"][first]])


def _refresh_usage(sim: Sim, day_of_pol: np.ndarray = None) -> None:
    """Rebuild who drives which car from the vehicles and drivers now on each policy (first promoting a spare car
    whose driver has lost their main one, when the day of the change is given)."""
    v, drv = sim.st.v, sim.pop.drv
    if day_of_pol is not None:
        _promote_spares(sim, day_of_pol)
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
        np.add.at(sim.st.p["n_veh"], pp[now], 1)
        np.maximum.at(sim.last_change, pp[now], arrive[now])
    later = ok & ~now
    return pd.DataFrame(dict(pol=pp[later], day=arrive[later], kind=ARRIVAL, target=pend[later], extra=-1))


def _apply_events(sim: Sim, T: Term, due: pd.DataFrame) -> dict:
    """Apply the changes in `due` (each on its own policy's boundary day). Returns {policy: [labels]}."""
    st, p, R = sim.st, sim.st.p, sim.R
    labels: dict = {}
    # drivers leave first: a death that ends the policy that day (no one to take it over) ends it before anything
    # else would change it, so a car traded or a driver added the same day is not put on a canceled policy
    for kind in [LEAVE] + [k for k in range(len(CHANGE_REASONS)) if k != LEAVE]:
        e = due[due.kind == kind].drop_duplicates(["pol", "target"] if kind in (ARRIVAL, TRADE, LEAVE) else ["pol"])
        if kind == SELL:            # one sale a day, and, apart from it, the record of a car written off
            g = due[due.kind == kind]
            w = g.extra.to_numpy() == WRECKED
            e = pd.concat([g[w].drop_duplicates(["pol"]), g[~w].drop_duplicates(["pol"])])
        if kind != LEAVE:
            ended = (T.cancel_day[e.pol.to_numpy()] >= 0) & (T.cancel_day[e.pol.to_numpy()] <= e.day.to_numpy())
            e = e[~ended]
        if len(e) == 0:
            continue
        pol, day, tgt, extra = (e[c].to_numpy() for c in ("pol", "day", "target", "extra"))
        v = st.v
        n_cars = np.bincount(v["pol"][v["active"]], minlength=len(T.s))
        if kind == ARRIVAL:
            ok = np.ones(len(e), dtype=bool)
            st.add_vehicles(_draw_replacements(sim, tgt, day))
            np.add.at(p["n_veh"], pol, 1)
        elif kind == TRADE:
            ok = v["active"][tgt]
            st.retire(tgt[ok], day[ok], REMOVAL_REASONS.index("Replaced"))
            st.add_vehicles(_draw_replacements(sim, tgt[ok], day[ok]))
        elif kind == SELL:
            wrecked = extra == WRECKED                  # already gone: the endorsement only records it
            sold = v["active"][tgt] & (n_cars[pol] >= 2) & ~wrecked
            ok = sold | wrecked
            st.retire(tgt[sold], day[sold], REMOVAL_REASONS.index("Sold"))
            np.subtract.at(p["n_veh"], pol[sold], 1)
            np.maximum.at(T.last_gone, pol[sold], day[sold])
        elif kind == LEAVE:
            ok = _drivers_leave(sim, T, pol, day, tgt, extra)
        elif kind == MARRY:
            drv = sim.pop.drv
            ni = p["ni_drv"][pol]
            ok = drv.marital.to_numpy()[ni] != "M"
            if ok.any():
                _marry(sim, pol[ok], day[ok])
        elif kind == TEEN:
            ages, probs = zip(*C.TEEN_LICENCE_AGE_P.items())
            age = R.choice(ages, len(e), p=probs) + R.random(len(e)) * 0.95
            # each parent on the policy was at least 18 when the child was born
            age = np.minimum(age, (day - _youngest_parent_dob(sim, pol)) / 365.25 - 18)
            ok = age >= 16
            if ok.any():
                kids = _new_drivers(sim, pol[ok], day[ok], role=3, age=age[ok], male=R.random(ok.sum()) < 0.5,
                                    licensed=day[ok], marital="S")
                _give_spare_car(sim, pol[ok], day[ok], kids)
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
    """Drivers leave a policy (codes: 1 child or 2 other adult moved out, 3 divorce, 4 death, 5 death in a crash,
    recorded as 4). A leaving driver's own car usually goes with them; otherwise another household driver takes it
    over. Returns which of the drivers left (not one already gone: a teenager killed in a crash who was to move
    out later)."""
    st, p, R = sim.st, sim.st.p, sim.R
    drv = sim.pop.drv
    ok = drv.active.to_numpy()[who]
    went = np.zeros(len(who), dtype=bool)
    pol, day, who, code = pol[ok], day[ok], who[ok], np.where(code[ok] == CRASH_DEATH, 4, code[ok])
    active = drv.active.to_numpy().copy()
    role, marital = drv.role.to_numpy().copy(), drv.marital.to_numpy().copy()
    removed, why = drv.removed_day.to_numpy().copy(), drv.removal_reason.to_numpy().copy()
    d_pol = drv.pol.to_numpy()
    dying = set(zip(who[code == 4].tolist(), day[code == 4].tolist()))    # (a couple killed together: no widow)
    for q, d, w, c in zip(pol, day, who, code):
        # two drivers of one policy can leave on the same day, so each is judged as the policy now stands
        if c == 3 and role[w] != 1:
            continue    # no longer a spouse: widowed earlier today, and now the named insured
        if w == p["ni_drv"][q]:      # the named insured died: a surviving spouse takes the policy over, or it is cancelled
            spouse = np.flatnonzero((d_pol == q) & active & (role == 1))
            if len(spouse):
                s0 = spouse[0]
                role[s0], marital[s0], p["ni_drv"][q] = 0, "W", s0
                sim.marital.add(s0, d, 0)
                sim.ni.add(q, d, s0)
            else:                    # no one to take it over: cancelled, and the named insured shown as deceased
                _cancel(T, np.array([q]), np.array([d]), "Insured Deceased")
        elif c == 3:                 # both are divorced: the named insured, and the spouse who leaves
            marital[p["ni_drv"][q]] = "D"
            sim.marital.add(p["ni_drv"][q], d, 0)
            marital[w] = "D"
            sim.marital.add(w, d, 0)
        elif c == 4 and role[w] == 1 and (int(p["ni_drv"][q]), int(d)) not in dying:
            marital[p["ni_drv"][q]] = "W"
            sim.marital.add(p["ni_drv"][q], d, 0)
        active[w], removed[w], why[w] = False, d, c
        p["n_drv"][q] -= 1
    drv["active"], drv["role"], drv["marital"] = active, role, marital
    drv["removed_day"], drv["removal_reason"] = removed, why
    left = ~active[who]
    went[np.flatnonzero(ok)[left]] = True
    # a policy the death ended (no one to take it over) keeps its cars as they were: nothing is handed over
    ended = (T.cancel_day[pol] >= 0) & (T.cancel_day[pol] <= day)
    left &= ~ended
    _hand_over_cars(sim, T, who[left], day[left], code[left])
    return went


def _hand_over_cars(sim: Sim, T: Term, who, day, code) -> None:
    st, p, R = sim.st, sim.st.p, sim.R
    v, drv = st.v, sim.pop.drv
    take_p = np.array([0.0, C.TAKES_CAR_P["child"], C.TAKES_CAR_P["other"], C.TAKES_CAR_P["divorce"], C.TAKES_CAR_P["death"]])
    owner_day = dict(zip(who, day))
    owner_code = dict(zip(who, code))
    cars = np.flatnonzero(v["active"] & np.isin(v["primary_drv"], who))
    d_assigned = drv.assigned.to_numpy().copy()
    kept, when = [], []
    for car in cars:
        q, w = v["pol"][car], v["primary_drv"][car]
        n_cars = np.count_nonzero(v["active"] & (v["pol"] == q))
        if n_cars > 1 and R.random() < take_p[owner_code[w]]:
            st.retire(np.array([car]), np.array([owner_day[w]]), REMOVAL_REASONS.index("Left With Driver"))
            p["n_veh"][q] -= 1
            T.last_gone[q] = max(T.last_gone[q], owner_day[w])
            continue
        v["primary_drv"][car], v["extra_vehicle"][car] = _driver_for_car(sim, q, d_assigned, owner_day[w])
        kept.append(car)
        when.append(owner_day[w])
    # the car is now driven as its new driver drives: their commute, age and employment, and whether it is an extra
    # car for them, give its mileage and use from the handover (dated, so earlier periods keep theirs)
    _redraw_mileage(sim, np.array(kept, dtype=np.int64), np.array(when, dtype=np.int64))


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


def _youngest_parent_dob(sim: Sim, pol) -> np.ndarray:
    """The later birth day of each policy's named insured and spouse on the policy (if any)."""
    drv = sim.pop.drv
    dob = drv.dob_day.to_numpy()[sim.st.p["ni_drv"][pol]]
    sp = drv[(drv.role.to_numpy() == 1) & drv.active.to_numpy()]
    sp_dob = pd.Series(sp.dob_day.to_numpy()).groupby(sp.pol.to_numpy()).max().reindex(pol).to_numpy()
    return np.where(np.isnan(sp_dob), dob, np.maximum(dob, np.nan_to_num(sp_dob))).astype(np.int64)


def _new_drivers(sim: Sim, pol, day, role, age, male, licensed, marital) -> np.ndarray:
    """Add drivers to policies from `day`. Returns their IDs. Adults bring a driving record with them."""
    st, p, R, ref, cal = sim.st, sim.st.p, sim.R, sim.ref, sim.ref.cal
    drv = sim.pop.drv
    m = len(pol)
    dob = np.floor(day - age * 365.25).astype(int)
    zr = ref.zips.iloc[p["zi"][pol]]
    in_city = (zr.region == "City of Chicago").to_numpy()
    employed, commute = population.draw_commute(R, age, zr, in_city)
    if role == 3:
        employed, commute = np.zeros(m, dtype=bool), np.zeros(m)
    ni = p["ni_drv"][pol]
    u_keep = R.random(m)
    ids = len(drv) + np.arange(m)
    # a teen takes the household's group and surname; a spouse or other adult usually shares the group (names.py)
    p_same = {1: names.SAME_GROUP_SPOUSE, 2: names.SAME_GROUP_OTHER_ADULT}.get(role, 1.0)
    group = ref.names.related_group(R, drv.race_group.to_numpy()[ni], ref.names.zip_mix(zr), p_same)
    own = ref.names.surname(R, group)
    rename = np.zeros(m, dtype=bool)
    if role == 3:
        last = _household_surname(drv, pol, ni)
    else:
        # a new spouse (names.KEPT_OWN_SURNAME): a wife keeps her surname or takes the named insured's; a husband keeps
        # his, and a woman named insured takes it from the wedding day unless she keeps her own
        husband = male & ~drv.male.to_numpy()[ni]
        keep = u_keep < names.KEPT_OWN_SURNAME[np.where(husband, drv.race_group.to_numpy()[ni], group)]
        last = np.where(husband | keep, own, drv.last_name.to_numpy()[ni])
        rename = husband & ~keep
    # no one shares a full name with anyone who has been on the policy: a clash is named again
    first = ref.names.first_name(R, group, male, np.floor(cal.year_frac(dob)).astype(int))
    on = drv[np.isin(drv.pol.to_numpy(), pol)]
    taken = set(zip(on.pol.to_numpy().tolist(), on.first_name.to_numpy().tolist(), on.last_name.to_numpy().tolist()))
    # a new spouse may come to share the named insured's surname, so does not share their first name either
    ni_first = drv.first_name.to_numpy()[ni]
    for _ in range(20):
        clash = np.array([(q, f, l) in taken for q, f, l in zip(pol.tolist(), first.tolist(), np.asarray(last).tolist())], dtype=bool) \
            | ((role == 1) & (first == ni_first))
        if not clash.any():
            break
        first[clash] = ref.names.first_name(R, group[clash], np.asarray(male)[clash],
                                            np.floor(cal.year_frac(dob[clash])).astype(int))
    new = pd.DataFrame(dict(
        pol=pol, role=role, age=age, drv=ids, ord=p["n_drv"][pol], male=male, marital=marital, dob_day=dob,
        licensed_day=licensed, latent=R.gamma(C.LATENT_GAMMA_SHAPE, 1 / C.LATENT_GAMMA_SHAPE, m) * p["household_factor"][pol],
        good_grades=(role == 3) & (R.random(m) < C.GOOD_STUDENT_GRADES_P),
        school_end_day=dob + (population.school_end_age(R, m) * 365.25).astype(int), commute_miles=commute, employed=employed,
        first_name=first, race_group=group, last_name=last, assigned=False, added_day=day,
        removed_day=-1, removal_reason=0, active=True))
    sim.pop.drv = pd.concat([drv, new[drv.columns]], ignore_index=True)
    if rename.any():
        d, who = sim.pop.drv, ni[rename]
        sim.name_changes.append(pd.DataFrame(dict(drv=who, day=np.broadcast_to(day, m)[rename],
                                                  old=d.last_name.to_numpy()[who])))
        last_now = d.last_name.to_numpy().copy()
        last_now[who] = own[rename]
        d["last_name"] = last_now
    sim.marital.add(ids, day, marital == "M")
    np.add.at(p["n_drv"], pol, 1)
    t0 = np.maximum(day - C.LOOKBACK_DAYS, licensed)
    inc = [population.violations(new, t0, np.full(m, cal.valuation_day), R, cal)]
    if role != 3:      # an adult joining arrives with accidents from a previous insurer
        hazard = sim.pop.zip_truth.true_crash_hazard.to_numpy()[p["zi"][pol]]
        inc.append(population.prior_accidents(R, new.assign(assigned=True), t0, day, day, hazard, cal))
    inc = pd.concat(inc, ignore_index=True)
    inc["pol"] = sim.pop.drv.pol.to_numpy()[inc.drv.to_numpy()]
    sim.pop.incidents = pd.concat([sim.pop.incidents, inc[sim.pop.incidents.columns]], ignore_index=True)
    sim.recs.add(inc.drv, inc.day, inc.kind.map(KIND), inc.known_day)
    return ids


def _household_surname(drv: pd.DataFrame, pol: np.ndarray, ni: np.ndarray) -> np.ndarray:
    """The surname a household's children carry: the husband's when a woman named insured is married to him (she
    may have kept her own), otherwise the named insured's."""
    last = drv.last_name.to_numpy()[ni].copy()
    h = drv[(drv.role.to_numpy() == 1) & drv.active.to_numpy() & drv.male.to_numpy()]
    husband = pd.Series(h.last_name.to_numpy(), index=h.pol.to_numpy())
    husband = husband[~husband.index.duplicated(keep="last")].reindex(pol).to_numpy()
    use = ~drv.male.to_numpy()[ni] & pd.notna(husband)
    last[use] = husband[use]
    return last


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
    sim.marital.add(ni, day, 1)
    spouse = _new_drivers(sim, pol, day, role=1, age=age, male=male, licensed=licensed, marital="M")
    brings = R.random(len(pol)) < C.SPOUSE_BRINGS_CAR_P
    _add_vehicles(sim, pol[brings], day[brings], spouse[brings])
    _give_spare_car(sim, pol[~brings], day[~brings], spouse[~brings])


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
    new = population.draw_vehicles(ref, R, pol, cal.year_frac(day), p["inc_rel"][pol], density,
                                   age_scale=C.FLEET_AGE["scale"], age_shape=C.FLEET_AGE["shape"])
    new["true_miles"], new["reported_miles"], new["use"] = population.draw_mileage(
        R, drv.commute_miles.to_numpy()[primary], (day - dob[primary]) / 365.25, drv.employed.to_numpy()[primary], extra, in_city)
    new["parking"] = population.draw_parking(R, density, p["homeowner"][pol].astype(bool))
    vage = (cal.year_frac(day) - new.model_year.to_numpy()).clip(0)
    new["ownership"] = population.draw_ownership(R, vage)
    p_full = population.full_coverage_probability(vage, p["inc_rel"][pol], p["score_z"][pol], p["tier"][pol])
    new["has_coll"] = (new.ownership.to_numpy() != "Owned") | (R.random(len(pol)) < p_full)
    new["has_comp"] = new.has_coll | (R.random(len(pol)) < C.P_COMP_ONLY)
    new["full_glass"] = new.has_comp & (R.random(len(pol)) < C.FULL_GLASS_P)
    new["has_rent"], new["rent_opt"], new["has_tow"] = population.draw_addons(R, new.has_coll.to_numpy(), new.has_comp.to_numpy())
    new["coll_ded_opt"], new["comp_ded_opt"] = population.draw_deductibles(R, p["inc_rel"][pol], p["score_z"][pol])
    # ranks are never reused: a car written off keeps its rank for the replacement on its way
    last_rank = np.full(len(p["zi"]), -1)
    np.maximum.at(last_rank, v["pol"], v["rank"])
    new["rank"] = last_rank[pol] + 1 + (pd.Series(pol).groupby(pol).cumcount().to_numpy())
    new["primary_drv"], new["extra_vehicle"] = primary, extra
    new["veh"] = len(v["pol"]) + np.arange(len(pol))
    new["added_day"], new["removed_day"], new["active"] = day, -1, True
    new["removal_reason"], new["replaces"], new["salvage_title"] = 0, -1, False
    new["salvage_day"], new["removal_known"], new["lost_unknown"] = -10 ** 9, -1, False
    st.add_vehicles(new)
    np.add.at(p["n_veh"], pol, 1)


def _move(sim: Sim, pol, day, new_zi) -> None:
    """The household moves within the area: new garaging ZIP, perhaps a different tenure and parking, and a new
    commute for each working driver, so each car's mileage and use are drawn again (and reported at the change)."""
    st, p, R, ref = sim.st, sim.st.p, sim.R, sim.ref
    v = st.v
    owner = p["homeowner"][pol].astype(bool)
    p["homeowner"][pol] = R.random(len(pol)) < np.where(owner, C.OWNER_AFTER_MOVE_P["owner"], C.OWNER_AFTER_MOVE_P["renter"])
    p["zi"][pol] = new_zi
    sim.home.add(pol, day, p["homeowner"][pol])
    where = np.zeros(len(p["zi"]), dtype=bool)
    where[pol] = True
    cars = np.flatnonzero(v["active"] & where[v["pol"]])
    v["zi"][cars] = p["zi"][v["pol"][cars]]
    v["parking"][cars] = population.draw_parking(R, ref.zips.population_density_sqmi.to_numpy()[v["zi"][cars]],
                                                 p["homeowner"][v["pol"][cars]].astype(bool))
    drv = sim.pop.drv
    when = np.zeros(len(p["zi"]), dtype=np.int64)
    when[pol] = day
    d = np.flatnonzero(drv.active.to_numpy() & where[drv.pol.to_numpy()])
    zr = ref.zips.iloc[p["zi"][drv.pol.to_numpy()[d]]]
    age = (when[drv.pol.to_numpy()[d]] - drv.dob_day.to_numpy()[d]) / 365.25
    _, commute = population.draw_commute(R, age, zr, (zr.region == "City of Chicago").to_numpy())
    miles = drv.commute_miles.to_numpy().copy()
    miles[d] = np.where(drv.employed.to_numpy()[d], commute, 0)         # the same job, a new journey to it
    drv["commute_miles"] = miles
    _redraw_mileage(sim, cars, when[v["pol"][cars]])


def _redraw_mileage(sim: Sim, cars: np.ndarray, day: np.ndarray) -> None:
    """Annual mileage (true and reported) and use of vehicles `cars` from their primary drivers as of `day`."""
    if len(cars) == 0:
        return
    v, drv = sim.st.v, sim.pop.drv
    primary = v["primary_drv"][cars]
    in_city = (sim.ref.zips.region.to_numpy() == "City of Chicago")[v["zi"][cars]]
    old = v["true_miles"][cars].astype(float).copy()
    v["true_miles"][cars], v["reported_miles"][cars], v["use"][cars] = population.draw_mileage(
        sim.R, drv.commute_miles.to_numpy()[primary], (day - drv.dob_day.to_numpy()[primary]) / 365.25,
        drv.employed.to_numpy()[primary], v["extra_vehicle"][cars], in_city)
    v["mile_rel"][cars] = v["true_miles"][cars] / 10_000
    v["use_factor"][cars] = np.where(v["use"][cars] == "Business", C.BUSINESS_USE_FACTOR, 1.0)
    sim.mile_changes.append(pd.DataFrame(dict(car=cars.astype(np.int64), day=np.broadcast_to(day, len(cars)).astype(np.int64),
                                              old=old, new=v["true_miles"][cars].astype(float))))


def _miles_then(sim: Sim, car, s, e) -> np.ndarray:
    """Each car's true annual mileage over days [s, e), weighted by the days at each level: what it was driven then,
    whatever changed later (sim.mile_changes; the arrays hold only the latest)."""
    car, s, e = (np.asarray(a, dtype=np.int64) for a in (car, s, e))
    now = sim.st.v["true_miles"][car].astype(float)
    if not sim.mile_changes or len(car) == 0:
        return now
    ch = pd.concat(sim.mile_changes, ignore_index=True)
    w = pd.DataFrame(dict(i=np.arange(len(car)), car=car, s=s, e=e)).merge(ch, on="car")
    w = w[w.day.to_numpy() > w.s.to_numpy()].sort_values(["i", "day"], kind="stable")
    # the level at the start is the one the first later change replaced (or today's, if none came later)
    first = w.groupby("i").head(1)
    level = now.copy()
    level[first.i.to_numpy()] = first.old.to_numpy()
    inside = w[w.day.to_numpy() < w.e.to_numpy()]
    span = np.maximum(e - s, 1)
    total = level * span + np.bincount(inside.i.to_numpy(), (inside.new - inside.old).to_numpy()
                                       * (inside.e - inside.day).to_numpy(), len(car))
    return total / span


def _renewal_changes(sim: Sim, renewing: np.ndarray, s_all: np.ndarray, ty: np.ndarray, change: np.ndarray) -> None:
    """Coverage changes at renewal: salvage-title cars lose physical damage cover, loans are paid off, older
    owned cars drop collision, and after a large increase some customers raise their deductibles."""
    st, R, cal = sim.st, sim.R, sim.ref.cal
    v = st.v
    idx = np.flatnonzero(v["active"] & renewing[v["pol"]])
    pol = v["pol"][idx]
    salvage = idx[v["salvage_title"][idx]]
    for c in ("has_coll", "has_comp", "full_glass", "has_rent", "has_tow"):
        v[c][salvage] = False
    paid_off = idx[(v["ownership"][idx] == "Financed") & (R.random(len(idx)) < 1 - np.exp(-ty[pol] / C.LOAN_YEARS))]
    v["ownership"][paid_off] = "Owned"
    age = cal.year_frac(s_all[pol]) - v["model_year"][idx]
    h = np.interp(age, C.DROP_PD_AGE_KNOTS, C.DROP_PD_RATE)
    drop = idx[(v["ownership"][idx] == "Owned") & v["has_coll"][idx] & (R.random(len(idx)) < 1 - np.exp(-h * ty[pol]))]
    keep_comp = R.random(len(drop)) < C.KEEP_COMP_WHEN_DROPPING_COLL_P
    v["has_coll"][drop], v["has_comp"][drop], v["has_rent"][drop] = False, keep_comp, False
    v["full_glass"][drop] &= keep_comp
    v["has_tow"][drop] &= keep_comp
    rd = C.RAISE_DEDUCTIBLE
    p_up = np.clip(rd["base"] + rd["per_increase"] * np.maximum(change[pol] - 0.10, 0), 0, rd["cap"])
    up = idx[v["has_coll"][idx] & (v["coll_ded_opt"][idx] < len(C.COLL_DEDUCTIBLES) - 1) & (R.random(len(idx)) < p_up)]
    v["coll_ded_opt"][up] += 1
    v["comp_ded_opt"][up] = np.minimum(v["comp_ded_opt"][up] + 1, len(C.COMP_DEDUCTIBLES) - 1)
    # liability limits: some customers buy higher limits; after a large increase a few buy lower ones
    p = st.p
    pols = np.flatnonzero(renewing)
    lc = C.LIMIT_CHANGE
    u = R.random(len(pols))
    up = (u < lc["up"] * ty[pols]) & (p["bi_opt"][pols] < len(C.BI_LIMITS) - 1)
    down = (u > 1 - (lc["down"] + lc["down_per_increase"] * np.maximum(change[pols] - 0.10, 0)) * ty[pols]) & (p["bi_opt"][pols] > 0)
    step = up.astype(int) - down.astype(int)
    follows = p["um_opt"][pols] == p["bi_opt"][pols]          # uninsured motorist limits usually match liability
    p["bi_opt"][pols] += step
    p["um_opt"][pols] = np.where(follows, p["bi_opt"][pols], np.minimum(p["um_opt"][pols], p["bi_opt"][pols]))


def _draw_replacements(sim: Sim, old: np.ndarray, day: np.ndarray) -> pd.DataFrame:
    """New vehicles replacing `old`, insured from `day`. They keep the old vehicle's driver, use and deductibles,
    unless that driver has left: then the car goes to another driver and its mileage and use are theirs."""
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
        zi = p["zi"][pol[left]]
        miles, reported, use = population.draw_mileage(
            R, drv.commute_miles.to_numpy()[primary[left]], (day[left] - drv.dob_day.to_numpy()[primary[left]]) / 365.25,
            drv.employed.to_numpy()[primary[left]], extra[left], (ref.zips.region.to_numpy() == "City of Chicago")[zi])
        for c, x in (("true_miles", miles), ("reported_miles", reported), ("use", use)):
            col = new[c].to_numpy().copy()
            col[left] = x
            new[c] = col
    vage = (cal.year_frac(day) - new.model_year.to_numpy()).clip(0)
    new["ownership"] = population.draw_ownership(R, vage, acquired=True)
    p_full = population.full_coverage_probability(vage, p["inc_rel"][pol], p["score_z"][pol], p["tier"][pol])
    new["has_coll"] = (new.ownership.to_numpy() != "Owned") | (R.random(len(old)) < p_full)
    new["has_comp"] = new.has_coll | (R.random(len(old)) < C.P_COMP_ONLY)
    new["full_glass"] = new.has_comp & (R.random(len(old)) < C.FULL_GLASS_P)
    new["has_rent"], new["rent_opt"], new["has_tow"] = population.draw_addons(R, new.has_coll.to_numpy(), new.has_comp.to_numpy())
    new["veh"] = len(v["pol"]) + np.arange(len(old))
    new["added_day"], new["removed_day"], new["active"] = day, -1, True
    new["removal_reason"], new["replaces"], new["salvage_title"] = 0, old, False
    new["salvage_day"], new["removal_known"], new["lost_unknown"] = -10 ** 9, -1, False
    return new
