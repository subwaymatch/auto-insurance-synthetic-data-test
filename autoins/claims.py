"""Claim lifecycle: reporting, expenses, closure, payments, recoveries and reserves.

The simulation knows the ultimate cost of every claim. This module decides when each
dollar moves, then cuts everything off at the valuation date: later payments are not yet
made, open claims carry an (imperfect) case reserve, and claims not yet reported are left
out of the extract entirely and written to the answer key instead.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from . import config as C
from .refdata import stream

REPORT_LAG_MEAN = {"AF_MV": 2.0, "AF_SV": 2.0, "NAF": 2.5, "PARKED": 3.0, "GLASS": 4.0, "THEFT_TOTAL": 1.0,
                   "THEFT_PARTIAL": 2.0, "VANDALISM": 3.0, "ANIMAL": 1.5, "WEATHER": 6.0, "FLOOD": 3.0, "FIRE": 1.0,
                   "OTHER_COMP": 4.0, "HAIL_CAT": 9.0, "WIND_CAT": 5.0, "FLOOD_CAT": 3.0}
OPEN_LAG_MEAN = {"BI": 12.0, "UM": 15.0, "MED": 10.0}
FORMULA_RESERVE = {"BI": 12_000, "UM": 10_000, "MED": 1_500, "PD": 3_500, "COLL": 3_500, "COMP": 1_200}
RESERVE_ERROR = {"BI": (-0.12, 0.55), "UM": (-0.12, 0.55), "MED": (0.0, 0.35), "PD": (0.0, 0.20),
                 "COLL": (0.0, 0.20), "COMP": (0.0, 0.20)}          # log-scale (bias, noise) of adjuster estimates
EXPENSE = {"PD": (0.60, 220), "COLL": (0.80, 260), "COMP": (0.40, 120), "MED": (0.30, 150)}   # (share with expense, median)


def develop(cfg: C.Config, ref, res) -> dict:
    cal = ref.cal
    R = stream(cfg.seed, "claims")
    V = cal.valuation_day
    occ = res.occ.copy()
    lag = np.floor(R.exponential(occ.peril.map(REPORT_LAG_MEAN).to_numpy()))
    lag += (R.random(len(occ)) < 0.03) * np.floor(R.exponential(45, len(occ)))
    occ["report_day"] = occ.day + lag.astype(int)

    f = res.feat.merge(occ[["occ", "day", "report_day", "peril", "cat"]], on="occ", how="left")
    n = len(f)
    cvg = f.cvg.to_numpy()
    paid = f.paid.to_numpy()
    injury = np.isin(cvg, ["BI", "UM"])
    extra = np.floor(R.exponential(pd.Series(cvg).map(OPEN_LAG_MEAN).fillna(0).to_numpy() + 1e-9))
    f["open_day"] = f.report_day + extra.astype(int)

    # litigation and loss adjustment expense
    lit = injury & (paid > 0) & (R.random(n) < 0.07 + 0.10 * (paid > 15_000) + 0.22 * (paid > 50_000))
    expense = np.zeros(n)
    z, u = R.standard_normal(n), R.random(n)
    expense = np.where(lit, (3_500 + 0.16 * paid) * np.exp(0.5 * z - 0.125), expense)
    expense = np.where(injury & ~lit & (u < 0.70), 500 * np.exp(0.8 * z), expense)
    for k, (share, median) in EXPENSE.items():
        expense = np.where((cvg == k) & (u < share), median * np.exp(0.5 * z), expense)
    f["litigated"], f["expense"] = lit, np.round(expense, 2)

    # time to close
    g = R.gamma(2.0, 0.5, n)                       # mean 1
    ln = R.standard_normal(n)
    peril = f.peril.to_numpy()
    mean = np.select([cvg == "PD", (cvg == "COLL") & f.total.to_numpy(), cvg == "COLL", peril == "GLASS",
                      peril == "THEFT_TOTAL", f.cat.to_numpy() >= 0, cvg == "COMP", cvg == "MED"],
                     [32, 34, 24, 6, 18, 28, 16, 80], default=0.0)
    dur = mean * g + 30 * (peril == "THEFT_TOTAL")
    inj_dur = 200 * np.exp(0.8 * ln) * np.clip(paid / 15_000, 0.2, 8) ** 0.15 + lit * 420 * np.exp(0.5 * R.standard_normal(n))
    dur = np.where(injury, np.where(paid > 0, inj_dur, 110 * np.exp(0.7 * ln)), dur)
    dur = np.where(~injury & f.cwp.to_numpy(), 14 * g, dur)
    dur = np.maximum(dur, 1).astype(int)
    f["close_day"] = f.open_day + dur
    f["fid"] = np.arange(n)

    # payment schedule (ultimate), cut off at the valuation date below
    pays = []

    def pay(mask, day, kind, amount):
        idx = np.flatnonzero(mask)
        pays.append(pd.DataFrame(dict(fid=idx, day=np.asarray(day)[idx].astype(int), kind=kind,
                                      amount=np.round(np.asarray(amount)[idx], 2))))

    two = (paid > 0) & (R.random(n) < 0.15)
    first = R.uniform(0.55, 0.85, n)
    od, cd = f.open_day.to_numpy(), f.close_day.to_numpy()
    pay((paid > 0) & ~two, cd, "Loss", paid)
    pay(two, od + dur // 2, "Loss", paid * first)
    pay(two, cd, "Loss", paid - np.round(paid * first, 2))
    pay((expense > 0) & ~lit, cd, "Expense", expense)
    for share, when in ((0.25, 0.30), (0.35, 0.65), (0.40, 1.0)):
        pay(lit, od + (dur * when).astype(int), "Expense", expense * share)
    pay(f.salvage.to_numpy() > 0, cd + R.integers(20, 70, n), "Salvage Recovery", -f.salvage.to_numpy())
    pay(f.subro.to_numpy() > 0, cd + np.exp(np.log(110) + 0.6 * R.standard_normal(n)).astype(int), "Subrogation Recovery",
        -f.subro.to_numpy())
    pay_all = pd.concat(pays, ignore_index=True)

    # ---- valuation cut-off ----
    known = pay_all[pay_all.day <= V]
    tot = lambda kind: np.bincount(known.fid[known.kind == kind], known.amount[known.kind == kind], n)
    f["paid_loss"], f["paid_expense"] = tot("Loss"), tot("Expense")
    f["salvage_rec"], f["subro_rec"] = np.abs(tot("Salvage Recovery")), np.abs(tot("Subrogation Recovery"))
    f["reported"] = f.open_day <= V
    f["closed"] = f.close_day <= V
    mu = pd.Series(cvg).map(lambda k: RESERVE_ERROR[k][0]).to_numpy()
    sg = pd.Series(cvg).map(lambda k: RESERVE_ERROR[k][1]).to_numpy()
    trend = cal.sev_trend["BI"][np.clip(f.day.to_numpy(), 0, cal.horizon)]
    formula = pd.Series(cvg).map(FORMULA_RESERVE).to_numpy() * trend
    estimate = np.where(paid > 0, paid * np.exp(mu + sg * R.standard_normal(n)), formula * np.exp(0.3 * R.standard_normal(n)))
    reserve = np.maximum(np.round((estimate - f.paid_loss.to_numpy()) / 50) * 50, 250)
    f["case_reserve"] = np.where(f.reported & ~f.closed, reserve, 0.0)

    rep = f[f.reported].copy()
    occ["report_day"] = occ.occ.map(rep.groupby("occ").open_day.min())       # first notice the company has
    claims = occ[occ.report_day.notna()].copy()
    claims["report_day"] = claims.report_day.astype(int)
    claims = claims.sort_values(["report_day", "occ"], kind="stable").reset_index(drop=True)
    claims["claim_id"] = np.arange(1, len(claims) + 1)
    rep["claim_id"] = rep.occ.map(claims.set_index("occ").claim_id)
    order = {k: i for i, k in enumerate(C.COVERAGES)}
    rep["cvg_order"] = rep.cvg.map(order)
    rep = rep.sort_values(["claim_id", "cvg_order", "claimant"], kind="stable").reset_index(drop=True)
    rep["feature_id"] = np.arange(1, len(rep) + 1)

    payments = known.merge(rep[["fid", "feature_id", "claim_id"]], on="fid")
    payments["kind_order"] = payments.kind.map({"Loss": 0, "Expense": 1, "Salvage Recovery": 2, "Subrogation Recovery": 3})
    payments = payments.sort_values(["day", "feature_id", "kind_order", "amount"], kind="stable").reset_index(drop=True)
    payments["payment_id"] = np.arange(1, len(payments) + 1)

    unreported = f[~f.reported].merge(occ[["occ", "pol", "veh", "row"]], on="occ")
    return dict(claims=claims, features=rep, payments=payments, unreported=unreported)
