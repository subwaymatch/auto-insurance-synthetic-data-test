"""Quotes: new business as a funnel.

Every new-business policy began as a quote that bound; many more quotes never bound. Each quote has a
competitive position, our premium relative to the best competing quote, and the chance of binding falls
as that ratio rises (config.QUOTE_PRICE_ELASTICITY), from a level that depends on the channel. Policies in
the book are the quotes that bound, so their competitive position is drawn given that they bound. Quotes
that did not bind come from a separate population of prospects, drawn and rated exactly like new business
with the same rating plan, keeping those that did not bind. Competing premiums are visible only on
independent-agent quotes, through the agent's comparative rater, as in practice.

Every quote offers the telematics programme. A prospect who opts in is quoted with the participation
discount, bound or not: bound quotes show what the policy was written with, and prospects opt in at the
rate the programme's take-up model gives new business (telematics.uptake), so a discounted quote is no
more likely to be a bound one than its opt-in makes it.
"""
from __future__ import annotations

from dataclasses import replace

import numpy as np
import pandas as pd

from . import config as C
from . import population, rating, telematics, truth
from .refdata import day_weight, stream
from .simulate import Records



def build(cfg: C.Config, ref, pop, res) -> pd.DataFrame:
    """One row per quote, bound or not, issued between the start and the valuation date."""
    R = stream(cfg.seed, "quotes")
    cal = ref.cal
    t = res.terms
    nb = t[t.new_business & (t.s >= 0)]
    pol = pop.pol.set_index("pol").loc[nb.pol]
    # the policy as quoted: its first term's rows at the start (later moves and limit changes do not count)
    first = res.rows[res.rows.term.isin(nb.term) & res.rows.at_start].groupby("pol")
    at_quote = lambda col: first[col].first().reindex(nb.pol).to_numpy()
    annual = (first[[f"prem_{c}" for c in C.COVERAGES]].sum().sum(axis=1)
              .reindex(nb.pol).fillna(0).to_numpy() / (pol.term_months.to_numpy() / 12))
    drv = pop.drv[pop.drv.added_day.to_numpy() <= pop.pol.first_day.to_numpy()[pop.drv.pol.to_numpy()]]
    young = drv.assign(age=(pop.pol.first_day.to_numpy()[drv.pol.to_numpy()] - drv.dob_day) / 365.25).groupby("pol").age.min()
    bound = pd.DataFrame(dict(
        quote_day=nb.offer_day.to_numpy(), eff=nb.s.to_numpy(), pol=nb.pol.to_numpy(), channel=pol.channel.to_numpy(),
        agency=pol.agency_id.to_numpy(), zi=at_quote("zi"), ni_age=pol.ni_age.to_numpy(),
        n_drv=drv.groupby("pol").size().reindex(nb.pol).to_numpy(), n_veh=first.size().reindex(nb.pol).to_numpy(),
        young=young.reindex(nb.pol).to_numpy(), prior=pol.prior_insurance.to_numpy(), score=pol.insurance_score.to_numpy(),
        bi_opt=at_quote("bi_opt"), telematics=first["tele_on"].any().reindex(nb.pol).fillna(False).to_numpy().astype(bool),
        term_months=pol.term_months.to_numpy(), premium=annual, bound=True))
    bound["log_ratio"] = _position(R, bound.channel.to_numpy(), bind=True)

    # a channel converting a share c of its quotes needs 1/c quotes per policy it writes
    conv = np.array([C.QUOTE_CONVERSION[c] for c in C.CHANNELS])
    need = np.bincount(bound.channel.to_numpy(), minlength=len(C.CHANNELS)) / conv
    lost = _prospects(cfg, ref, res.plan, int(need.sum()), need / need.sum(), R)
    q = pd.concat([bound, lost], ignore_index=True)
    q = q[(q.quote_day >= 0) & (q.quote_day <= cal.valuation_day) & (q.premium > 0)]
    q = q.sort_values(["quote_day", "bound", "pol"], ascending=[True, False, True], kind="stable").reset_index(drop=True)

    D = lambda day: pd.Series(cal.date(np.asarray(day))).dt.strftime("%Y-%m-%d").to_numpy()
    comp = q.premium.to_numpy() / np.exp(q.log_ratio.to_numpy())
    show = np.isin(np.array(C.CHANNELS)[q.channel.to_numpy()], C.COMPARATIVE_RATER_CHANNELS)
    return pd.DataFrame({
        "quote_id": np.arange(1, len(q) + 1), "quote_date": D(q.quote_day), "proposed_effective_date": D(q.eff),
        "distribution_channel": np.array(C.CHANNELS)[q.channel.to_numpy()], "agency_id": q.agency,
        "location_id": ref.zips.location_id.to_numpy()[q.zi.to_numpy()], "term_months": q.term_months,
        "named_insured_age": np.floor(q.ni_age).astype(int), "number_of_drivers": q.n_drv.astype(int),
        "youngest_driver_age": np.floor(q.young).astype(int), "number_of_vehicles": q.n_veh.astype(int),
        "prior_insurance": np.where(q.prior, "Y", "N"), "insurance_score": q.score.astype("Int64"),
        "bi_limit": [f"{C.BI_LIMITS[i][0] // 1000}/{C.BI_LIMITS[i][1] // 1000}" for i in q.bi_opt],
        "telematics_opt_in": np.where(q.telematics.to_numpy().astype(bool), "Y", "N"),
        "quoted_annual_premium": q.premium.round(2),
        "competitor_annual_premium": pd.array(np.where(show, comp.round(2), np.nan), dtype="Float64"),
        "bound": np.where(q.bound, "Y", "N"),
        "policy_id": pd.Series(1_000_000 + q.pol.to_numpy() + 1).astype("Int64").where(q.bound.to_numpy())})


def _base_logit(channel: np.ndarray) -> np.ndarray:
    p = np.array([C.QUOTE_CONVERSION[c] for c in C.CHANNELS])[channel]
    return np.log(p / (1 - p))


def _bind_p(channel, log_ratio):
    return 1 / (1 + np.exp(-(_base_logit(channel) - C.QUOTE_PRICE_ELASTICITY * log_ratio)))


def _position(R: np.random.Generator, channel: np.ndarray, bind: bool) -> np.ndarray:
    """log(our premium / best competing premium), drawn given whether the quote bound (rejection sampling)."""
    out = np.empty(len(channel))
    todo = np.arange(len(channel))
    while len(todo):
        x = R.normal(0, C.COMPETITOR_PRICE_SIGMA, len(todo))
        p = _bind_p(channel[todo], x)
        ok = R.random(len(todo)) < (p if bind else 1 - p)
        out[todo[ok]] = x[ok]
        todo = todo[~ok]
    return out


def _prospects(cfg: C.Config, ref, plan, n: int, channel_p, R: np.random.Generator) -> pd.DataFrame:
    """Households who asked for a quote and did not buy: drawn like new business, rated with the same plan."""
    cal = ref.cal
    pp = population.build(replace(cfg, n_policies=max(n, 1), initial_book_share=0.0), ref, tag="/prospects",
                          channel_p=channel_p)
    st = truth.Static.build(pp, ref)
    p, v = st.p, st.v
    first = p["first_day"]
    quote_w = np.array([C.DAY_WEIGHTS["quote"][c] for c in C.CHANNELS])[p["channel"]]
    quote_day = first - cal.weighted_lead(first, *C.NEW_BUSINESS_QUOTE_LEAD_DAYS,
                                          lambda d: day_weight(cal, d, quote_w[:, None, :]), R.random(len(first)))
    d_pol = pp.drv.pol.to_numpy()
    points, _, acc = Records(pp.incidents).as_of(len(d_pol), first[d_pol], quote_day[d_pol])
    V = np.arange(len(v["pol"]))
    vp, dr = v["pol"][V], v["primary_drv"][V]
    ty = p["term_months"] / 12
    cd = rating.codes(st, cal, V, first[vp], points[dr], acc[dr], np.zeros(len(V)))
    prem = rating.premium(plan, cd, rating.limit_factors(st, V), cal.rate_level_at(first[vp]), ty[vp])
    channel = p["channel"]
    # the telematics offer, taken up as by new business (simulate._telematics), with the participation discount
    d_act = np.flatnonzero(pp.drv.active.to_numpy())
    m = truth.driver_multiplier(pp.drv.iloc[d_act], quote_day[d_pol[d_act]], cal)
    household = np.bincount(d_pol[d_act], m, len(first)) / np.maximum(np.bincount(d_pol[d_act], minlength=len(first)), 1)
    young_ni = (quote_day - pp.drv.dob_day.to_numpy()[p["ni_drv"]]) / 365.25 < 30
    base = telematics.base_uptake(cal.year_frac(quote_day), np.ones(len(first), dtype=bool), np.zeros(len(first), dtype=bool))
    opt_in = telematics.uptake(R, base, household, young_ni, channel)
    for c in telematics.DISCOUNTED_COVERAGES:
        prem[c] = np.round(prem[c] * np.where(opt_in[vp], 1 - telematics.PARTICIPATION_DISCOUNT, 1.0), 2)
    annual = np.bincount(vp, sum(prem.values()), len(first)) / ty
    log_ratio = R.normal(0, C.COMPETITOR_PRICE_SIGMA, len(first))
    lost = R.random(len(first)) >= _bind_p(channel, log_ratio)
    young = pp.drv.assign(age=(first[d_pol] - pp.drv.dob_day.to_numpy()) / 365.25).groupby("pol").age.min().to_numpy()
    out = pd.DataFrame(dict(
        quote_day=quote_day, eff=first, pol=-1, channel=channel, agency=p["agency_id"], zi=p["zi"], ni_age=p["ni_age"],
        n_drv=p["n_drv"], n_veh=p["n_veh"], young=young, prior=p["prior_insurance"], score=p["insurance_score"],
        bi_opt=p["bi_opt"], telematics=opt_in, term_months=p["term_months"], premium=annual, bound=False,
        log_ratio=log_ratio))
    return out[lost]
