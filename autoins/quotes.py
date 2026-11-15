"""Quotes: new business as a funnel.

Every new-business policy began as a quote that bound; many more quotes never bound. Each quote has a
competitive position, our premium relative to the best competing quote, and the chance of binding falls
as that ratio rises (config.QUOTE_PRICE_ELASTICITY), from a level that depends on the channel. Policies in
the book are the quotes that bound, so their competitive position is drawn given that they bound. Quotes
that did not bind come from a separate population of prospects, drawn and rated exactly like new business
with the same rating plan, keeping those that did not bind. Competing premiums are visible only on
independent-agent quotes, through the agent's comparative rater, as in practice.
"""
from __future__ import annotations

from dataclasses import replace

import numpy as np
import pandas as pd

from . import config as C
from . import population, rating, truth
from .refdata import stream
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
        quote_day=nb.rate_day.to_numpy(), eff=nb.s.to_numpy(), pol=nb.pol.to_numpy(), channel=pol.channel.to_numpy(),
        agency=pol.agency_id.to_numpy(), zi=at_quote("zi"), ni_age=pol.ni_age.to_numpy(),
        n_drv=drv.groupby("pol").size().reindex(nb.pol).to_numpy(), n_veh=first.size().reindex(nb.pol).to_numpy(),
        young=young.reindex(nb.pol).to_numpy(), prior=pol.prior_insurance.to_numpy(), score=pol.insurance_score.to_numpy(),
        bi_opt=at_quote("bi_opt"),
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
        "Quote ID": np.arange(1, len(q) + 1), "Quote Date": D(q.quote_day), "Proposed Effective Date": D(q.eff),
        "Distribution Channel": np.array(C.CHANNELS)[q.channel.to_numpy()], "Agency ID": q.agency,
        "Location ID": ref.zips.location_id.to_numpy()[q.zi.to_numpy()], "Term Length Months": q.term_months,
        "Named Insured Age": np.floor(q.ni_age).astype(int), "Number of Drivers": q.n_drv.astype(int),
        "Youngest Driver Age": np.floor(q.young).astype(int), "Number of Vehicles": q.n_veh.astype(int),
        "Prior Insurance": np.where(q.prior, "Y", "N"), "Insurance Score": q.score.astype("Int64"),
        "BI Limit": [f"{C.BI_LIMITS[i][0] // 1000}/{C.BI_LIMITS[i][1] // 1000}" for i in q.bi_opt],
        "Quoted Annual Premium": q.premium.round(2),
        "Competitor Annual Premium": pd.array(np.where(show, comp.round(2), np.nan), dtype="Float64"),
        "Bound": np.where(q.bound, "Y", "N"),
        "Policy Number": pd.Series(1_000_000 + q.pol.to_numpy() + 1).astype("Int64").where(q.bound.to_numpy())})


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
    quote_day = first - R.integers(C.NEW_BUSINESS_QUOTE_LEAD_DAYS[0], C.NEW_BUSINESS_QUOTE_LEAD_DAYS[1] + 1, len(first))
    d_pol = pp.drv.pol.to_numpy()
    points, _, acc = Records(pp.incidents).as_of(len(d_pol), first[d_pol], quote_day[d_pol])
    V = np.arange(len(v["pol"]))
    vp, dr = v["pol"][V], v["primary_drv"][V]
    ty = p["term_months"] / 12
    cd = rating.codes(st, cal, V, first[vp], points[dr], acc[dr], np.zeros(len(V)))
    prem = rating.premium(plan, cd, rating.limit_factors(st, V), cal.rate_level_at(first[vp]), ty[vp])
    annual = np.bincount(vp, sum(prem.values()), len(first)) / ty
    channel = p["channel"]
    log_ratio = R.normal(0, C.COMPETITOR_PRICE_SIGMA, len(first))
    lost = R.random(len(first)) >= _bind_p(channel, log_ratio)
    young = pp.drv.assign(age=(first[d_pol] - pp.drv.dob_day.to_numpy()) / 365.25).groupby("pol").age.min().to_numpy()
    out = pd.DataFrame(dict(
        quote_day=quote_day, eff=first, pol=-1, channel=channel, agency=p["agency_id"], zi=p["zi"], ni_age=p["ni_age"],
        n_drv=p["n_drv"], n_veh=p["n_veh"], young=young, prior=p["prior_insurance"], score=p["insurance_score"],
        bi_opt=p["bi_opt"], term_months=p["term_months"], premium=annual, bound=False, log_ratio=log_ratio))
    return out[lost]
