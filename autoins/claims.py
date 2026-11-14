"""Claim lifecycle: reporting, expenses, closure, payments, recoveries and reserves.

The simulation knows the ultimate cost of every claim. `Development` decides when each dollar
moves, as the claims happen, so the simulation can tell when the insurer learns of a claim and
when it becomes chargeable. `develop` then cuts everything off at the valuation date: later
payments are not yet made, open claims carry an (imperfect) case reserve, and claims not yet
reported are left out of the extract entirely and written to the answer key instead.

Payment patterns (ASSUMED, by coverage). Glass and most injury claims settle in one payment.
Physical damage is often paid on the first estimate and topped up by supplements; property
damage liability may pay loss of use before the repair; injury claims sometimes get an advance;
medical payments follow the bills. Total losses may be split between the lienholder and the
owner, with title and fee costs paid later. A few payments are voided and reissued, and a few
closed features reopen for a supplemental payment. Every feature's payments add up to its
ultimate paid loss to the cent.
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

# Interim payments before the final one: (probability of a first, probability of a second)
INTERIM_P = {"PD": (0.30, 0.10), "COLL": (0.28, 0.07), "COMP": (0.15, 0.04), "BI": (0.12, 0.0), "UM": (0.12, 0.0)}
MED_BILLS_MEAN = 1.6                  # extra medical-payments bills beyond the first (Poisson, at most 6)
TOTAL_LOSS_SPLIT_P = 0.45             # settlement paid partly to a lienholder
TOTAL_LOSS_FEES_P = 0.20              # title, tax and fees paid after the settlement
REOPEN_P = {"PD": 0.03, "COLL": 0.04, "COMP": 0.02, "BI": 0.04, "UM": 0.04, "MED": 0.05}
VOID_P = 0.012                        # an interim payment is voided and reissued
TXN = ["Partial Payment", "Final Payment", "Supplemental Payment", "Void", "Reissue", "Expense", "Recovery"]


class Development:
    """Develops claims to ultimate as the simulation produces them, with its own random stream."""

    def __init__(self, cal, rng: np.random.Generator) -> None:
        self.cal, self.R = cal, rng
        self.occs, self.feats, self.pays = [], [], []
        self.n_feat = 0

    def add(self, occ: pd.DataFrame, feat: pd.DataFrame) -> pd.DataFrame:
        """Develop a batch of new claims. Returns occ with report_day (first notice the company has of any
        feature) and chargeable_day (the day an at-fault claim's payments reach the surcharge threshold, or -1)."""
        R = self.R
        occ = occ.copy()
        lag = np.floor(R.exponential(occ.peril.map(REPORT_LAG_MEAN).to_numpy()))
        lag += (R.random(len(occ)) < 0.03) * np.floor(R.exponential(45, len(occ)))
        notice = occ.day.to_numpy() + lag.astype(int)

        f = feat.merge(occ[["occ", "day", "peril", "cat", "at_fault"]].assign(notice=notice), on="occ", how="left")
        n = len(f)
        f["fid"] = self.n_feat + np.arange(n)
        self.n_feat += n
        cvg = f.cvg.to_numpy()
        f["paid"] = np.round(f.paid.to_numpy(), 2)
        paid = f.paid.to_numpy()
        injury = np.isin(cvg, ["BI", "UM"])
        extra = np.floor(R.exponential(pd.Series(cvg).map(OPEN_LAG_MEAN).fillna(0).to_numpy() + 1e-9))
        f["open_day"] = f.notice.to_numpy() + extra.astype(int)

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
        total = f.total.to_numpy()
        mean = np.select([cvg == "PD", (cvg == "COLL") & total, cvg == "COLL", peril == "GLASS",
                          peril == "THEFT_TOTAL", f.cat.to_numpy() >= 0, cvg == "COMP", cvg == "MED"],
                         [32, 34, 24, 6, 18, 28, 16, 80], default=0.0)
        dur = mean * g + 30 * (peril == "THEFT_TOTAL")
        inj_dur = 200 * np.exp(0.8 * ln) * np.clip(paid / 15_000, 0.2, 8) ** 0.15 + lit * 420 * np.exp(0.5 * R.standard_normal(n))
        dur = np.where(injury, np.where(paid > 0, inj_dur, 110 * np.exp(0.7 * ln)), dur)
        dur = np.where(~injury & f.cwp.to_numpy(), 14 * g, dur)
        dur = np.maximum(dur, 1).astype(int)
        f["close_day"] = f.open_day.to_numpy() + dur

        pays, f = _schedule(f, R)
        occ["report_day"] = occ.occ.map(f.groupby("occ").open_day.min()).to_numpy()
        occ["chargeable_day"] = occ.occ.map(_chargeable(f, pays)).fillna(-1).astype(int).to_numpy()
        self.occs.append(occ)
        self.feats.append(f.drop(columns=["notice", "at_fault"]))
        self.pays.append(pays)
        return occ

    def result(self):
        cat = lambda parts: pd.concat(parts, ignore_index=True)
        return cat(self.occs), cat(self.feats), cat(self.pays)


def _chargeable(f: pd.DataFrame, pays: pd.DataFrame) -> pd.Series:
    """Day each at-fault occurrence's cumulative PD, BI and collision loss payments reach the threshold."""
    m = f.at_fault.to_numpy().astype(bool) & np.isin(f.cvg.to_numpy(), ["PD", "BI", "COLL"])
    return chargeable_days(pays[pays.kind == "Loss"], f.loc[m, ["fid", "occ"]])


def chargeable_days(loss_pays: pd.DataFrame, fid_occ: pd.DataFrame, threshold: float = C.CHARGEABLE_THRESHOLD) -> pd.Series:
    """For each occurrence, the first day its loss payments (on the features in fid_occ) add up to the
    threshold. Only payments up to that day matter, so a later settlement cannot change it."""
    p = loss_pays.merge(fid_occ, on="fid").sort_values(["occ", "day", "seq"], kind="stable")
    cum = p.groupby("occ").amount.cumsum()
    return p[cum.to_numpy() >= threshold - 0.005].groupby("occ").day.min()


def _legs(f_idx, day, cents, txn) -> pd.DataFrame:
    return pd.DataFrame(dict(i=f_idx, day=np.asarray(day).astype(int), cents=np.asarray(cents).astype(np.int64), txn=txn))


def _schedule(f: pd.DataFrame, R: np.random.Generator):
    """Every loss payment, expense payment and recovery of each feature, through to its final close.
    Adds reopen_day and final_close_day to f. Returns (payments, f)."""
    n = len(f)
    cvg, peril = f.cvg.to_numpy(), f.peril.to_numpy()
    total = f.total.to_numpy().astype(bool)
    od, cd = f.open_day.to_numpy(), f.close_day.to_numpy()
    dur = cd - od
    P = np.round(f.paid.to_numpy() * 100).astype(np.int64)          # ultimate paid, in cents
    has = P > 0
    injury = np.isin(cvg, ["BI", "UM"])

    # ---- reopening: a closed feature reopens for a supplement carved out of the ultimate
    reopen = has & (R.random(n) < pd.Series(cvg).map(REOPEN_P).to_numpy())
    reopen_day = cd + 20 + np.floor(R.exponential(75, n)).astype(int)
    supp_day = reopen_day + 3 + np.floor(R.exponential(20, n)).astype(int)
    final_close = supp_day + np.where(R.random(n) < 0.5, 0, 1 + np.floor(R.exponential(7, n))).astype(int)
    supp = np.where(reopen, np.maximum(np.round(P * R.uniform(0.05, 0.25, n)), 100), 0).astype(np.int64)
    reopen &= supp < P
    supp = np.where(reopen, supp, 0)
    main = P - supp                                                  # paid before the first close

    # ---- the main settlement: day and shape
    lag_long = np.where(injury, 12, 6)
    final_day = cd - np.where(R.random(n) < np.where(injury, 0.5, 0.55), 0,
                              np.minimum(1 + np.floor(R.exponential(lag_long)), dur)).astype(int)
    u1, u2 = R.random(n), R.random(n)
    p1 = pd.Series(cvg).map(lambda c: INTERIM_P.get(c, (0.0, 0.0))[0]).to_numpy()
    p2 = pd.Series(cvg).map(lambda c: INTERIM_P.get(c, (0.0, 0.0))[1]).to_numpy()
    k = (u1 < p1).astype(int) + ((u1 < p1) & (u2 < p2))
    k = np.where(cvg == "MED", np.minimum(R.poisson(MED_BILLS_MEAN, n), 6), k)
    k = np.where(total | (peril == "GLASS"), 0, k)
    k = np.where(has, np.minimum(k, np.maximum(main // 5_000 - 1, 0)), 0)      # at least ~$50 a payment
    split = has & total & (R.random(n) < TOTAL_LOSS_SPLIT_P) & (main >= 20_000)
    fees = has & total & (R.random(n) < TOTAL_LOSS_FEES_P) & (final_day - od >= 10) & (main >= 50_000)

    # interim payments: physical damage is paid early on the estimate, injury advances mid-way, bills throughout
    i = np.repeat(np.arange(n), k)
    pos = np.arange(len(i)) - np.repeat(np.cumsum(k) - k, k)
    c_i = cvg[i]
    t = np.select([np.isin(c_i, ["COLL", "COMP"]), c_i == "PD", np.isin(c_i, ["BI", "UM"])],
                  [R.random(len(i)) ** 2 * 0.9, R.uniform(0.05, 0.9, len(i)), R.uniform(0.15, 0.6, len(i))],
                  default=R.random(len(i)))
    order = np.lexsort((t, i))
    t = t[order]                                                     # times ascend within each feature
    settle_day = np.where(fees, final_day - R.integers(7, 31, n).clip(max=np.maximum(final_day - od, 1)), final_day)
    span = np.maximum(settle_day - od, 0)
    inspect = np.where(np.isin(c_i, ["PD", "COLL", "COMP"]), np.minimum(3, span[i]), 0)   # paid after an appraisal
    interim_day = od[i] + inspect + np.floor(t * (span[i] - inspect)).astype(int)
    w_int = np.select([np.isin(c_i, ["COLL", "COMP"]) & (pos == 0), np.isin(c_i, ["COLL", "COMP"]), c_i == "PD",
                       np.isin(c_i, ["BI", "UM"])], [4.0, 1.0, 0.5, 0.6], default=1.5)
    w_fin = np.select([np.isin(cvg, ["COLL", "COMP"]), cvg == "PD", injury], [1.0, 3.0, 3.0], default=1.5)
    g_int = R.gamma(w_int)
    g_fin = R.gamma(w_fin)
    g_fee = np.where(fees, R.uniform(0.02, 0.06, n), 0.0)
    tot_g = np.bincount(i, g_int, n) + g_fin                          # shares are Dirichlet; the final payment takes the rounding
    int_cents = np.floor(main[i] * g_int / tot_g[i] * (1 - g_fee[i])).astype(np.int64)
    fee_cents = np.where(fees, np.floor(main * g_fee), 0).astype(np.int64)
    fin_cents = main - np.bincount(i, int_cents, n).astype(np.int64) - fee_cents
    # a lienholder payoff and the owner's balance go out on the settlement day
    lien = np.where(split, np.floor(fin_cents * R.uniform(0.4, 0.9, n)), 0).astype(np.int64)

    legs = [
        _legs(i, interim_day, int_cents, "Partial Payment"),
        _legs(np.flatnonzero(split), settle_day[split], lien[split], "Partial Payment"),
        _legs(np.flatnonzero(has), settle_day[has], (fin_cents - lien)[has],
              np.where(fees[has], "Partial Payment", "Final Payment")),
        _legs(np.flatnonzero(fees), final_day[fees], fee_cents[fees], "Final Payment"),
        _legs(np.flatnonzero(reopen), supp_day[reopen], supp[reopen], "Supplemental Payment"),
    ]
    # voided and reissued interim payments (net zero)
    vd = R.random(len(i)) < VOID_P
    void_day = np.minimum(interim_day + 2 + np.floor(R.exponential(5, len(i))).astype(int), settle_day[i])
    legs += [_legs(i[vd], void_day[vd], -int_cents[vd], "Void"), _legs(i[vd], void_day[vd], int_cents[vd], "Reissue")]
    loss = pd.concat(legs, ignore_index=True)
    loss = loss[loss.cents != 0]
    loss["kind"] = "Loss"

    # expenses: appraisal fees early on physical damage, others at close, litigation costs as the suit runs
    exp_c = np.round(f.expense.to_numpy() * 100).astype(np.int64)
    lit = f.litigated.to_numpy().astype(bool)
    early = np.isin(cvg, ["PD", "COLL", "COMP"])
    e_day = np.where(early, od + np.floor(R.uniform(0.05, 0.6, n) * dur).astype(int), cd)
    e_legs = [_legs(np.flatnonzero((exp_c > 0) & ~lit), e_day[(exp_c > 0) & ~lit], exp_c[(exp_c > 0) & ~lit], "Expense")]
    li = np.flatnonzero(lit & (exp_c > 0))
    done = np.zeros(len(li), dtype=np.int64)
    for j, (share, when) in enumerate(((0.25, 0.30), (0.35, 0.65), (0.40, 1.0))):
        amt = np.round(exp_c[li] * share).astype(np.int64) if j < 2 else exp_c[li] - done
        done += amt
        e_legs.append(_legs(li, od[li] + (dur[li] * when).astype(int), amt, "Expense"))
    expense = pd.concat(e_legs, ignore_index=True)
    expense["kind"] = "Expense"

    salv = np.round(f.salvage.to_numpy() * 100).astype(np.int64)
    subro = np.round(f.subro.to_numpy() * 100).astype(np.int64)
    rec = pd.concat([
        _legs(np.flatnonzero(salv > 0), (cd + R.integers(20, 70, n))[salv > 0], -salv[salv > 0], "Recovery").assign(kind="Salvage Recovery"),
        _legs(np.flatnonzero(subro > 0), (cd + np.exp(np.log(110) + 0.6 * R.standard_normal(n)).astype(int))[subro > 0],
              -subro[subro > 0], "Recovery").assign(kind="Subrogation Recovery")], ignore_index=True)

    pays = pd.concat([loss, expense, rec], ignore_index=True)
    pays["fid"] = f.fid.to_numpy()[pays.i.to_numpy()]
    pays["amount"] = pays.cents / 100
    pays = pays.sort_values(["fid", "day", "kind", "cents"], kind="stable").reset_index(drop=True)
    pays["seq"] = np.arange(len(pays))
    f = f.assign(paid=P / 100, reopen_day=np.where(reopen, reopen_day, -1), final_close_day=np.where(reopen, final_close, cd))
    return pays[["fid", "day", "kind", "txn", "amount", "seq"]], f


def develop(cfg: C.Config, ref, res) -> dict:
    """Cut the developed claims off at the valuation date."""
    cal = ref.cal
    R = stream(cfg.seed, "reserves")
    V = cal.valuation_day
    occ, f, pay_all = res.occ.copy(), res.feat.copy().reset_index(drop=True), res.pays
    n = len(f)
    cvg = f.cvg.to_numpy()
    paid = f.paid.to_numpy()
    pos = pd.Series(np.arange(n), index=f.fid.to_numpy())

    known = pay_all[pay_all.day <= V]
    idx = pos.reindex(known.fid).to_numpy()
    tot = lambda kind: np.round(np.bincount(idx[known.kind.to_numpy() == kind], known.amount[known.kind == kind], n), 2)
    f["paid_loss"], f["paid_expense"] = tot("Loss"), tot("Expense")
    f["salvage_rec"], f["subro_rec"] = np.abs(tot("Salvage Recovery")), np.abs(tot("Subrogation Recovery"))
    f["reported"] = f.open_day <= V
    reopened = (f.reopen_day >= 0) & (f.reopen_day <= V)
    f["reopened"] = reopened
    f["closed"] = np.where(reopened, f.final_close_day <= V, f.close_day <= V)
    f["status_close_day"] = np.where(reopened, f.final_close_day, f.close_day)
    mu = pd.Series(cvg).map(lambda k: RESERVE_ERROR[k][0]).to_numpy()
    sg = pd.Series(cvg).map(lambda k: RESERVE_ERROR[k][1]).to_numpy()
    trend = cal.sev_trend["BI"][np.clip(f.day.to_numpy(), 0, cal.horizon)]
    formula = pd.Series(cvg).map(FORMULA_RESERVE).to_numpy() * trend
    z = R.standard_normal(n)
    estimate = np.where(paid > 0, paid * np.exp(mu + sg * z), formula * np.exp(0.3 * z))
    # a reopened feature is reserved for the supplement the adjuster expects
    estimate = np.where(reopened, f.paid_loss.to_numpy() + (paid - f.paid_loss.to_numpy()) * np.exp(0.3 * z), estimate)
    reserve = np.maximum(np.round((estimate - f.paid_loss.to_numpy()) / 50) * 50, 250)
    f["case_reserve"] = np.where(f.reported & ~f.closed, reserve, 0.0)

    rep = f[f.reported].copy()
    occ["report_day"] = occ.occ.map(rep.groupby("occ").open_day.min())       # first notice the company has
    claims = occ[occ.report_day.notna()].copy()
    claims["report_day"] = claims.report_day.astype(int)
    claims = claims.sort_values(["report_day", "occ"], kind="stable").reset_index(drop=True)
    claims["claim_id"] = np.arange(1, len(claims) + 1)
    claims["chargeable"] = (claims.chargeable_day >= 0) & (claims.chargeable_day <= V)
    rep["claim_id"] = rep.occ.map(claims.set_index("occ").claim_id)
    order = {k: i for i, k in enumerate(C.COVERAGES)}
    rep["cvg_order"] = rep.cvg.map(order)
    rep = rep.sort_values(["claim_id", "cvg_order", "claimant"], kind="stable").reset_index(drop=True)
    rep["feature_id"] = np.arange(1, len(rep) + 1)

    payments = known.merge(rep[["fid", "feature_id", "claim_id"]], on="fid")
    payments["kind_order"] = payments.kind.map({"Loss": 0, "Expense": 1, "Salvage Recovery": 2, "Subrogation Recovery": 3})
    payments = payments.sort_values(["day", "feature_id", "kind_order", "seq"], kind="stable").reset_index(drop=True)
    payments["payment_id"] = np.arange(1, len(payments) + 1)

    unreported = f[~f.reported].merge(occ[["occ", "pol", "veh", "row"]], on="occ")
    return dict(claims=claims, features=rep, payments=payments, unreported=unreported)
