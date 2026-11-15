#!/usr/bin/env python3
"""Check a generated dataset against its calibration targets and for internal consistency.

    python validate.py [--out output]

Reads only the CSV files, exactly as a user of the data would. Exits non-zero if an
integrity check fails or a calibrated figure falls outside its tolerance band.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

# The generator's own tuning bands: paid claim frequency per 100 earned car-years and average paid loss
# over the whole extract, every deductible and cause, loss only. They keep the book stable from seed to
# seed. They are NOT on the published benchmark's definitions; that comparison is BENCHMARK below.
TARGETS = {
    "BI":   dict(freq=(0.70, 1.15), sev=(20_000, 30_000)),
    "PD":   dict(freq=(2.40, 3.40), sev=(5_800, 7_400)),
    "COLL": dict(freq=(4.00, 5.80), sev=(4_700, 6_300)),
    "COMP": dict(freq=(4.20, 6.20), sev=(2_000, 3_100)),
}
# Triple-I / ISO "Private Passenger Auto Insurance Losses, 2015-2024" (national; source: ISO, a Verisk
# business): (claims per 100 earned car years, claim severity) by calendar year. Its footnotes define the
# figures: paid claims, all limits combined; bodily injury and property damage severity include loss
# adjustment expenses; collision and comprehensive are for coverage with a $500 deductible; comprehensive
# excludes wind and water losses and includes glass; some states are excluded (Massachusetts throughout,
# most no-fault states for bodily injury, Michigan and New Jersey for property damage).
BENCHMARK = {
    "BI":   {2022: (0.70, 24_681), 2023: (0.78, 26_178), 2024: (0.80, 28_278)},
    "PD":   {2022: (2.54, 6_024), 2023: (2.59, 6_554), 2024: (2.50, 6_770)},
    "COLL": {2022: (4.48, 5_377), 2023: (4.48, 5_521), 2024: (4.16, 5_489)},
    "COMP": {2022: (3.78, 2_175), 2023: (4.08, 2_305), 2024: (3.95, 2_306)},
}
BENCHMARK_DEDUCTIBLE = 500
WIND_AND_WATER = ["WEATHER", "FLOOD", "HAIL_CAT", "WIND_CAT", "FLOOD_CAT"]
# Bands for the like-for-like comparison, as a ratio to the national figure. Frequency is allowed to run
# above national because the book is urban; severity should sit near it. The first calendar year is shown
# but not held to a band for liability: with no claims from before the extract, its payments are too few.
BENCHMARK_FREQ_BAND = (0.85, 1.45)
BENCHMARK_SEV_BAND = (0.85, 1.15)
TOWING_LIMIT = 100                      # towing and labor pays up to this per claim

LOSS_RATIO_BAND = (0.52, 0.88)          # every full accident year; industry 2022-2025 ran roughly 61%-80%,
                                        # and a book this size moves several points on large claims alone
OVERALL_LOSS_RATIO_BAND = (0.62, 0.76)
# Expected (noise-free, from the answer key) loss ratio by accident year, against industry pure loss ratios
# (incurred losses excluding LAE / earned premium, direct). US private auto: 80.2% (2022, APCIA), 75.4% (2023),
# 66.1% (2024) and 61.5% (2025) (S&P Global); Illinois: 79.6%, 72.8%, 63.4% and 60.1% (Illinois DOI market
# share reports). Bands are about +/-5 points around those figures.
INDUSTRY_LOSS_RATIO_BAND = {2022: (0.74, 0.85), 2023: (0.68, 0.80), 2024: (0.59, 0.70), 2025: (0.55, 0.67)}


def integrity_claims_and_quotes(rep, term, veh, clm, feat, reserves, quotes) -> None:
    """Reserve history, claim detail, vehicle identifiers and the quote funnel."""
    r = reserves.sort_values(["Claim Feature ID", "Reserve Type", "Transaction Date", "Reserve Transaction ID"], kind="stable")
    running = r.groupby(["Claim Feature ID", "Reserve Type"])["Change Amount"].cumsum()
    last = r.groupby(["Claim Feature ID", "Reserve Type"])["Outstanding Reserve"].last().unstack()
    at_val = lambda kind: (last[kind] if kind in last else pd.Series(dtype=float)).reindex(feat["Claim Feature ID"]).fillna(0).to_numpy()
    rep.check("reserve history balances, and ends at each feature's case and expense reserve",
              np.allclose(running, r["Outstanding Reserve"], atol=0.01)
              and np.allclose(at_val("Loss"), feat["Case Reserve"], atol=0.01)
              and np.allclose(at_val("Expense"), feat["Expense Reserve"], atol=0.01),
              f"{len(reserves):,} reserve transactions")
    dt = lambda x: pd.to_datetime(x)
    f = feat.merge(clm[["Claim ID", "Loss Date", "At Fault", "Insured Fault %", "Report Date", "SIU Referral Date"]], on="Claim ID")
    suits = f[f["Litigation"] == "Y"]
    rep.check("suits follow the attorney and the claim, precede the close, and fall within Illinois' two-year limit",
              (dt(suits["Suit Date"]) >= dt(suits["Attorney Date"])).all()
              and (dt(suits["Suit Date"]) >= dt(suits["Open Date"])).all()
              and (suits["Close Date"].isna() | (dt(suits["Suit Date"]) < dt(suits["Close Date"]))).all()
              and ((dt(suits["Suit Date"]) - dt(suits["Loss Date"])).dt.days <= 730).all(),
              f"{(feat['Attorney Represented'] == 'Y').sum():,} represented claimants, {len(suits):,} suits")
    fault = clm.dropna(subset=["Insured Fault %"])
    att = f[f["Attorney Represented"] == "Y"]
    rep.check("attorneys are retained after the loss and before the feature closes",
              (dt(att["Attorney Date"]) >= dt(att["Loss Date"])).all()
              and (att["Close Date"].isna() | (dt(att["Attorney Date"]) <= dt(att["Close Date"]))).all())
    rep.check("an insured at fault is over 50% at fault, and one not at fault is under 51%",
              ((fault["At Fault"] == "Y") == (fault["Insured Fault %"] > 50)).all())
    siu = clm[clm["SIU Referral"] == "Y"]
    rep.check("fraud referrals come after the claim is reported", (siu["SIU Referral Date"] >= siu["Report Date"]).all())
    rep.check("VIN prefixes are consistent for each model and model year",
              (veh.groupby(["Vehicle ID", "Vehicle Model Year"])["VIN Prefix"].nunique() == 1).all())
    b = quotes[quotes["Bound"] == "Y"].merge(term[term["Business Type"] == "New"], on="Policy Number")
    rep.check("every bound quote is a new-business policy starting on the quoted date",
              (b["Proposed Effective Date"] == b["Policy Effective Date"]).all() and (quotes["Quote Date"] <= quotes["Proposed Effective Date"]).all(),
              f"{len(quotes):,} quotes, {(quotes['Bound'] == 'Y').mean():.1%} bound")


def integrity_limits(rep, f) -> None:
    """Every coverage's payments against the terms on the risk row the claim arose under. `f` is the
    coverage features joined to their claim's risk row. Amounts are compared to the cent."""
    cent = 0.005
    paid, code, claim = f["Paid Loss"], f["Coverage Code"], f["Claim ID"]
    split = lambda col, i: f[col].str.split("/").str[i].astype(float) * 1000
    by_accident = lambda m, x: x[m].groupby(claim[m]).sum()
    first = lambda m, x: x[m].groupby(claim[m]).first()
    bi, um, uim = code == "BI", code == "UM", f["UM/UIM Type"] == "Underinsured"
    rep.check("bodily injury payments stay within the per-person and per-accident limits",
              (paid[bi] <= split("BI Limit", 0)[bi] + cent).all()
              and (by_accident(bi, paid) <= first(bi, split("BI Limit", 1)) + cent).all(),
              f"{(by_accident(bi, paid) >= first(bi, split('BI Limit', 1)) - cent).sum():,} accidents paid the per-accident limit in full")
    rep.check("property damage and medical payments stay within their limits",
              (paid[code == "PD"] <= f.loc[code == "PD", "PD Limit"] + cent).all()
              and (paid[code == "MED"] <= f.loc[code == "MED", "Med Pay Limit"] + cent).all())
    offset = f["Other Insurer Payment"].fillna(0)
    rep.check("uninsured and underinsured motorist payments stay within the per-person and per-accident limits, "
              "less what the at-fault driver's insurer paid",
              (paid[um] <= split("UM Limit", 0)[um] - offset[um] + cent).all()
              and (by_accident(um, paid) <= first(um, split("UM Limit", 1)) - by_accident(um, offset) + cent).all()
              and (um == f["UM/UIM Type"].notna()).all() and (f["Other Insurer Payment"].notna() == uim).all(),
              f"{(um & ~uim).sum():,} uninsured and {uim.sum():,} underinsured motorist features")
    # a vehicle is worth at most its value on the risk row (rounded to $10), and the deductible comes off
    value = f["Vehicle Value"] + 5
    glass_free = (f["Cause of Loss"] == "GLASS") & (f["Full Glass Coverage"] == "Y")
    comp_ded = np.where(glass_free, 0, f["Comprehensive Deductible"])
    rep.check("collision and comprehensive payments stay within the vehicle's value less the deductible",
              (paid[code == "COLL"] <= (value - f["Collision Deductible"]).clip(lower=0)[code == "COLL"]).all()
              and (paid[code == "COMP"] <= (value - comp_ded).clip(lower=0)[code == "COMP"]).all())
    rent = code == "RENT"
    rep.check("rental and towing payments stay within the per-claim maximum",
              (paid[rent] <= f.loc[rent, "Rental Reimbursement"].str.split("/").str[1].astype(float) + cent).all()
              and (paid[code == "TOW"] <= TOWING_LIMIT + cent).all())
    on = lambda k, col: (f.loc[code == k, col] > 0).all()
    rep.check("the coverage terms on each risk row agree with its premiums",
              ((f["Rental Premium"] > 0) == f["Rental Reimbursement"].notna()).all()
              and ((f["Towing Premium"] > 0) == (f["Towing and Labor"] == "Y")).all()
              and on("COLL", "Collision Deductible") and on("COMP", "Comprehensive Deductible"))


def integrity_lifecycle(rep, risk, term, pol, veh, drv, clm, feat, pay, inc, r_start, r_end, valuation) -> None:
    """Checks on vehicle lifecycles, information timing, policy dates, premium and payments."""
    dt = lambda x: pd.to_datetime(x)
    valuation = pd.Timestamp(valuation)
    v = veh.set_index("Insured Vehicle ID")
    added, removed = dt(v["Added Date"]), dt(v["Removed Date"])

    # vehicles: cover, claims and total losses
    rv = risk["Insured Vehicle ID"]
    cov_s, cov_e = dt(risk["Coverage Start Date"]), dt(risk["Coverage End Date"])
    rep.check("no cover before a vehicle was added or after it was removed",
              (cov_s >= added.reindex(rv).to_numpy()).all() and (cov_e <= removed.reindex(rv).fillna(pd.Timestamp.max).to_numpy()).all())
    loss = dt(clm["Loss Date"])
    vid = clm["Insured Vehicle ID"]
    rep.check("no loss on a vehicle before it was added or on or after it was removed",
              (loss >= added.reindex(vid).to_numpy()).all() and (loss < removed.reindex(vid).fillna(pd.Timestamp.max).to_numpy()).all())
    o = pd.DataFrame({"v": rv, "s": r_start, "e": r_end}).sort_values(["v", "s"], kind="stable")
    prev_end = o.groupby("v").e.shift()
    rep.check("a vehicle's earned exposure is never counted twice", (prev_end.isna() | (o.s >= prev_end)).all())
    tl = feat[(feat["Total Loss"] == "Y") & (feat["Owner Retained Salvage"] == "N")]
    tl = tl.merge(clm[["Claim ID", "Insured Vehicle ID", "Loss Date"]], on="Claim ID").groupby("Insured Vehicle ID")["Loss Date"].min()
    gone = dt(tl) + pd.Timedelta(days=1)
    known = gone <= valuation                       # a loss on the valuation date takes the car off the day after
    rep.check("every total loss the company takes the wreck from ends the vehicle's cover the day after the loss",
              (removed.reindex(tl.index)[known] == gone[known]).all() and removed.reindex(tl.index)[~known].isna().all()
              and (v["Removal Reason"].reindex(tl.index)[known] == "Total Loss").all(),
              f"{len(tl):,} vehicles; {(feat['Owner Retained Salvage'] == 'Y').sum():,} owner-retained; "
              f"{(veh['Removal Reason'] == 'Destroyed or Stolen').sum():,} destroyed or stolen without a company total loss")
    rp = veh.dropna(subset=["Replaces Vehicle ID"])
    old = v.reindex(rp["Replaces Vehicle ID"].astype(int))
    rep.check("replacement vehicles follow the vehicle they replace on the same policy",
              (old["Policy Number"].to_numpy() == rp["Policy Number"].to_numpy()).all()
              and (dt(old["Removed Date"]).to_numpy() <= dt(rp["Added Date"]).to_numpy()).all(),
              f"{len(rp):,} replacements, {(old['Removal Reason'] == 'Total Loss').sum():,} after a total loss")
    rep.check("nothing is dated after the valuation date",
              all((dt(t_[c]).dropna() <= valuation).all() for t_, c in
                  ((veh, "Added Date"), (veh, "Removed Date"), (drv, "Added Date"), (drv, "Removed Date"), (clm, "Report Date"),
                   (feat, "Open Date"), (feat, "Close Date"), (feat, "Suit Date"), (feat, "Attorney Date"),
                   (pay, "Payment Date"), (inc, "Known Date"), (term, "Cancel Date"), (risk, "Coverage Start Date"))))

    # the policy as it stands: on the valuation date if in force, else on its last day of cover
    as_at = np.where(pol["Policy Status"] == "In Force", valuation, dt(pol["Policy Expiration Date"]) - pd.Timedelta(days=1))
    as_at = pd.Series(np.minimum(as_at, valuation.to_datetime64()), index=pol["Policy Number"].to_numpy())
    day = as_at.reindex(risk["Policy Number"]).to_numpy()
    covered = risk[(cov_s.to_numpy() <= day) & (cov_e.to_numpy() > day)].groupby("Policy Number")["Insured Vehicle ID"].nunique()
    day = as_at.reindex(veh["Policy Number"]).to_numpy()
    listed = veh[(dt(veh["Added Date"]).to_numpy() <= day) & ~(dt(veh["Removed Date"]).to_numpy() <= day)].groupby("Policy Number").size()
    day = as_at.reindex(drv["Policy Number"]).to_numpy()
    drivers = drv[(dt(drv["Added Date"]).to_numpy() <= day) & ~(dt(drv["Removed Date"]).to_numpy() <= day)].groupby("Policy Number").size()
    count = lambda g: g.reindex(pol["Policy Number"]).fillna(0).to_numpy()
    in_force = (pol["Policy Status"] == "In Force").to_numpy()
    rep.check("each policy's vehicle count is the vehicles covered at its latest status (risk rows and vehicle dates agree)",
              (pol["Number of Vehicles"].to_numpy() == count(covered)).all() and (count(covered) == count(listed)).all(),
              f"{pol['Number of Vehicles'][in_force].sum():,} vehicles on {in_force.sum():,} policies in force, "
              f"{(pol['Number of Vehicles'][in_force] == 0).sum():,} of them waiting for a replacement car")
    rep.check("each policy's driver count is the drivers on it at its latest status",
              (pol["Number of Drivers"].to_numpy() == count(drivers)).all())
    at_start = cov_s.to_numpy() == dt(term.set_index("Policy Term ID")["Policy Effective Date"]).reindex(risk["Policy Term ID"]).to_numpy()
    opening = risk[at_start].groupby("Policy Term ID").size().reindex(term["Policy Term ID"]).fillna(0).to_numpy()
    rep.check("each term's opening vehicle count is its risk rows at the term start (endorsement 0)",
              (term["Vehicles at Term Start"].to_numpy() == opening).all() and ((risk["Endorsement Number"] == 0) == at_start).all())

    # information timing: every rated record is exactly the incidents with a known date on or before the
    # row's rating date (the term's rating date, before it takes effect, or the day of a mid-term change),
    # dated in the three years up to the row's cover start. Dates carry no time of day, so the order of
    # events on one day is fixed by convention: a known date of D means usable by any rating dated D or
    # later, and the company's own claim is known the day after the payment that makes it chargeable, so a
    # loss or payment on the rating date itself is never part of that rating.
    t = term.set_index("Policy Term ID")
    eff, rdate = dt(t["Policy Effective Date"]), dt(t["Rating Date"])
    rep.check("every term is rated before it takes effect", (rdate <= eff).all()
              and (dt(risk["Rating Date"]) <= cov_s).all())
    i = inc.assign(d=dt(inc["Incident Date"]), k=dt(inc["Known Date"]))
    j = risk[["Record ID", "Driver ID", "Coverage Start Date", "Rating Date"]].merge(
        i[["Driver ID", "d", "k", "Incident Type"]], on="Driver ID")
    je, jr = dt(j["Coverage Start Date"]).to_numpy(), dt(j["Rating Date"]).to_numpy()
    j = j[(j.d.to_numpy() <= je) & (j.d.to_numpy() > je - np.timedelta64(3 * 365, "D")) & (j.k.to_numpy() <= jr)]
    pts = j["Incident Type"].map({"Minor Violation": 1, "Major Violation": 3}).fillna(0).groupby(j["Record ID"]).sum()
    acc = (j["Incident Type"] == "At-Fault Accident").groupby(j["Record ID"]).sum()
    rep.check("rated violations and accidents are those known on the rating date",
              (risk["Record ID"].map(pts).fillna(0) == risk["Rated Violation Points"]).all()
              and (risk["Record ID"].map(acc).fillna(0) == risk["Rated At-Fault Accidents"]).all())
    rep.check("an incident is known only after it happened", (i.k >= i.d).all())
    own = i[i["Source"] == "Company Claim"]
    rep.check("the company's own claims reach the driving record after the loss date, never on it", (own.k > own.d).all(),
              f"{len(own):,} chargeable company claims")
    rep.check("no good-student discount at 25 or older", not ((risk["Rated Good Student"] == "Y") & (risk["Rated Driver Age"] >= 25)).any())

    # drivers: rated and claiming drivers were on the policy at the time
    d = drv.set_index("Driver ID")
    d_add, d_rem = dt(d["Added Date"]), dt(d["Removed Date"]).fillna(pd.Timestamp.max)
    rep.check("each risk row's driver was on the policy throughout the row",
              (d_add.reindex(risk["Driver ID"]).to_numpy() <= cov_s.to_numpy()).all()
              and (d_rem.reindex(risk["Driver ID"]).to_numpy() >= np.minimum(cov_e, pd.Timestamp(r_end.max())).to_numpy()).all())
    af = clm[clm["At Fault"] == "Y"]
    rep.check("drivers in at-fault claims were on the policy on the loss date",
              (d_add.reindex(af["Claimant Id"]).to_numpy() <= dt(af["Loss Date"]).to_numpy()).all()
              and (d_rem.reindex(af["Claimant Id"]).to_numpy() > dt(af["Loss Date"]).to_numpy()).all(),
              f"{drv['Removed Date'].notna().sum():,} drivers left a policy; "
              f"{(risk['Endorsement Number'] > 0).sum():,} risk rows start at a mid-term change")

    # policy dates: terms chain without gaps, on anniversaries of the original inception day
    tt = term.merge(pol[["Policy Number", "Original Inception Date"]], on="Policy Number")
    es, inc_day = dt(tt["Policy Effective Date"]), dt(tt["Original Inception Date"]).dt.day
    tt = tt.assign(es=es).sort_values(["Policy Number", "es"], kind="stable")
    nxt = tt.groupby("Policy Number")["Policy Effective Date"].shift(-1)
    rep.check("each term starts on the anniversary day (month-end days kept, no drift) and follows the last",
              (es.dt.day == np.minimum(inc_day, es.dt.days_in_month)).all()
              and (nxt.isna() | (nxt == tt["Policy Expiration Date"])).all(),
              f"{(es.dt.day >= 29).mean():.1%} of terms start on the 29th to 31st")

    # premium: written + endorsements + returns = earned before the extract + earned in it, for finished terms
    done = term["Cancel Date"].notna() | (dt(term["Policy Expiration Date"]) <= valuation)
    gap = (term["Written Premium"] + term["Endorsement Premium"] + term["Return Premium"]
           - term["Earned Before Extract"] - term["Earned Premium"])[done]
    rep.check("finished terms' written, endorsement and return premium equal their earned premium",
              (gap.abs() <= 0.01 * term["Vehicles at Term Start"][done] + 0.05).all(), f"largest difference ${gap.abs().max():.2f}")

    # payments
    f = feat.set_index("Claim Feature ID")
    pd_ = dt(pay["Payment Date"])
    rep.check("no payment before its feature opened", (pd_ >= dt(f["Open Date"]).reindex(pay["Claim Feature ID"]).to_numpy()).all())
    lp = pay[pay["Payment Type"] == "Loss"]
    closed = f["Feature Status"] == "Closed"
    last = dt(lp.groupby("Claim Feature ID")["Payment Date"].max()).reindex(f.index[closed])
    rep.check("closed features have no loss payment after their close date", (last.isna() | (last <= dt(f.loc[closed, "Close Date"]))).all())
    n = lp.groupby("Claim Feature ID").size()
    print(f"  loss payments per paid feature: {n.value_counts().sort_index().to_dict()}; "
          f"{(lp['Transaction Type'] == 'Void').sum():,} voids; {f['Reopen Date'].notna().sum():,} features reopened")


def benchmark(rep, risk, f, pay, s, e, last_full_year: int) -> None:
    """Frequency and severity on the Triple-I / ISO table's own definitions, by calendar year.

    A claim is counted in the year of its first loss payment, and severity is the year's payments over
    the claims counted in it (paid claims on a calendar-year basis). Liability payments include loss
    adjustment expense. Collision and comprehensive are restricted to risk rows with a $500 deductible, and
    comprehensive leaves out wind and water losses. What still differs is printed with the table."""
    pay = pay.assign(year=pd.to_datetime(pay["Payment Date"]).dt.year)
    loss = pay[pay["Payment Type"] == "Loss"]
    first_paid = loss[loss.Amount > 0].groupby("Claim Feature ID").year.min()
    premium = {"BI": "BI Premium", "PD": "PD Premium", "COLL": "Collision Premium", "COMP": "Comprehensive Premium"}
    deductible = {"COLL": "Collision Deductible", "COMP": "Comprehensive Deductible"}
    first_year = int(pd.Timestamp(s.min()).year)
    years = range(first_year, last_full_year + 1)
    print(f"  {'':5s}{'year':>5s}{'car-years':>11s}{'claims/100':>12s}{'national':>10s}{'ratio':>7s}{'avg paid':>10s}{'national':>10s}{'ratio':>7s}")
    for k, national in BENCHMARK.items():
        rows = (risk[premium[k]] > 0).to_numpy()
        g = f[f["Coverage Code"] == k]
        if k in deductible:
            rows = rows & (risk[deductible[k]] == BENCHMARK_DEDUCTIBLE).to_numpy()
        if k == "COMP":
            g = g[~g["Cause of Loss"].isin(WIND_AND_WATER)]
        g = g[g["Record ID"].isin(risk.loc[rows, "Record ID"])]
        kinds = ["Loss", "Expense"] if k in ("BI", "PD") else ["Loss"]
        dollars = pay[pay["Claim Feature ID"].isin(g["Claim Feature ID"]) & pay["Payment Type"].isin(kinds)].groupby("year").Amount.sum()
        n = first_paid.reindex(g["Claim Feature ID"]).dropna().astype(int).value_counts()
        # totals over the years held to a band: what the national figures would give on this book's exposure and claims
        held = dict(claims=0.0, at_national=0.0, dollars=0.0, dollars_at_national=0.0)
        for y in years:
            a, b = np.datetime64(f"{y}-01-01"), np.datetime64(f"{y + 1}-01-01")
            car_years = (np.minimum(e, b) - np.maximum(s, a)).astype("timedelta64[D]").astype(int).clip(0)[rows].sum() / 365.25
            claims, paid = n.get(y, 0), dollars.get(y, 0.0)
            freq, sev = claims / car_years * 100, paid / max(claims, 1)
            nf, ns = national.get(y, (np.nan, np.nan))
            note = ""
            if k == "BI" and y == first_year:
                note = "   (not held: no payments on earlier accident years)"
            elif y in national:
                held["claims"] += claims
                held["at_national"] += nf * car_years / 100
                held["dollars"] += paid
                held["dollars_at_national"] += ns * claims
            show = lambda x, fmt: fmt.format(x) if not np.isnan(x) else "-"
            print(f"  {k:5s}{y:>5d}{car_years:11,.0f}{freq:12.2f}{show(nf, '{:.2f}'):>10s}{show(freq / nf, '{:.2f}'):>7s}"
                  f"{sev:10,.0f}{show(ns, '{:,.0f}'):>10s}{show(sev / ns, '{:.2f}'):>7s}{note}")
        if held["at_national"] > 0:
            rep.band(f"{k} frequency relative to national, like for like", held["claims"] / held["at_national"], BENCHMARK_FREQ_BAND)
            rep.band(f"{k} severity relative to national, like for like", held["dollars"] / held["dollars_at_national"], BENCHMARK_SEV_BAND)
    print("  Still different from the national table: it covers the whole country (less a few states) and this book is")
    print("  one metropolitan area, so frequency is expected above it; national figures are not a Chicago or a")
    print("  single-carrier benchmark. The first calendar year has no payments on accidents from before the extract,")
    print("  which matters for bodily injury. Glass claims under full glass cover carry no deductible here. The table's")
    print("  claim-counting rules (per claimant or per accident, and when a claim counts as paid) are not published.")


MIN_POLICIES_FOR_CALIBRATION = 20_000   # smaller books have too few claims for the calibration bands


class Report:
    """Integrity checks (check) always count. Calibration bands (band) are statistical: on a small book
    a miss is reported as a warning rather than a failure."""

    def __init__(self, calibrate: bool = True) -> None:
        self.failures = self.warnings = 0
        self.calibrate = calibrate

    def check(self, label: str, ok: bool, detail: str = "", statistical: bool = False) -> None:
        soft = statistical and not self.calibrate
        self.failures += not ok and not soft
        self.warnings += not ok and soft
        print(f"  [{'ok' if ok else 'warn' if soft else 'FAIL'}] {label}{(': ' + detail) if detail else ''}")

    def band(self, label: str, value: float, band: tuple[float, float], fmt: str = "{:,.2f}") -> None:
        self.check(label, band[0] <= value <= band[1], f"{fmt.format(value)} (target {fmt.format(band[0])} to {fmt.format(band[1])})",
                   statistical=True)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", type=Path, default=Path(__file__).resolve().parent / "output")
    out = ap.parse_args().out
    read = lambda name, **kw: pd.read_csv(out / f"{name}.csv", keep_default_na=False, na_values=[""], low_memory=False, **kw)
    pol, term, risk = read("policy_dimension"), read("policy_term_fact"), read("risk_fact")
    drv, veh, loc = read("driver_dimension"), read("insured_vehicle_dimension"), read("location_dimension")
    clm, feat, pay = read("claims_fact"), read("claim_coverage_fact"), read("claim_payment_fact")
    inc, ledger = read("driver_incident_fact"), read("policy_transaction_fact")
    reserves, quotes = read("claim_reserve_fact"), read("quote_fact")
    truth = pd.read_csv(out / "answer_key" / "risk_truth.csv")
    summary = json.loads((out / "run_summary.json").read_text())
    start, valuation = np.datetime64(summary["start"]), np.datetime64(summary["valuation"])
    pd.set_option("display.width", 200)
    rep = Report(calibrate=len(pol) >= MIN_POLICIES_FOR_CALIBRATION)
    if not rep.calibrate:
        print(f"note: {len(pol):,} policies is too few to hold calibration bands; misses are warnings, integrity checks still count")

    print("\nSIZE")
    cy = risk["Earned Exposure"].sum()
    ep = risk["Earned Premium"].sum()
    print(f"  {len(pol):,} policies, {len(term):,} policy terms, {len(veh):,} vehicles, {len(drv):,} drivers")
    print(f"  {cy:,.0f} earned car-years, ${ep:,.0f} earned premium, {len(clm):,} claims, {len(feat):,} coverage features")
    term_years = (pd.to_datetime(term["Policy Expiration Date"]) - pd.to_datetime(term["Policy Effective Date"])).dt.days.sum() / 365.25
    written = term["Written Premium"].sum() + term["Endorsement Premium"].sum()
    print(f"  average premium ${ep / cy:,.0f} per car-year, ${written / term_years:,.0f} per policy-year")
    # each risk row earns from its cover start (or the extract start, if later) for its earned exposure
    r_start = np.maximum(pd.to_datetime(risk["Coverage Start Date"]).to_numpy(), start)
    r_days = np.round(risk["Earned Exposure"].to_numpy() * 365.25).astype(int)
    r_end = r_start + r_days.astype("timedelta64[D]")

    print("\nINTEGRITY")
    rep.check("risk rows reference valid policy terms", risk["Policy Term ID"].isin(term["Policy Term ID"]).all())
    rep.check("risk rows reference valid vehicles and drivers", risk["Insured Vehicle ID"].isin(veh["Insured Vehicle ID"]).all()
              and risk["Driver ID"].isin(drv["Driver ID"]).all())
    rep.check("claims reference valid risk rows", clm["Record ID"].isin(risk["Record ID"]).all())
    c = clm.merge(risk[["Record ID", "Policy Number", "Insured Vehicle ID"]], on="Record ID", suffixes=("", "_r"))
    rep.check("claim vehicle and policy match the risk row", (c["Policy ID"] == c["Policy Number"]).all()
              and (c["Insured Vehicle ID"] == c["Insured Vehicle ID_r"]).all())
    c = clm.merge(term, on="Policy Term ID")
    end = c["Cancel Date"].fillna(c["Policy Expiration Date"])
    rep.check("every loss date falls inside its policy term", ((c["Loss Date"] >= c["Policy Effective Date"]) & (c["Loss Date"] < end)).all())
    rep.check("report date is on or after loss date", (clm["Report Date"] >= clm["Loss Date"]).all())
    rep.check("no negative premiums", (risk[[x for x in risk.columns if x.endswith("Premium")]] >= 0).all().all())
    rep.check("features and payments reference valid claims", feat["Claim ID"].isin(clm["Claim ID"]).all()
              and pay["Claim Feature ID"].isin(feat["Claim Feature ID"]).all())
    paid = pay[pay["Payment Type"] == "Loss"].groupby("Claim Feature ID").Amount.sum().reindex(feat["Claim Feature ID"]).fillna(0)
    rep.check("loss payments add up to paid loss on every feature", np.allclose(paid.to_numpy(), feat["Paid Loss"].to_numpy(), atol=0.02))
    rep.check("claim totals equal the sum of their features",
              np.allclose(feat.groupby("Claim ID")["Net Incurred Loss"].sum().reindex(clm["Claim ID"]).to_numpy(), clm["Claim Amount"].to_numpy(), atol=0.05))
    cov_ok = feat.merge(clm[["Claim ID", "Record ID", "Cause of Loss"]], on="Claim ID").merge(risk, on="Record ID")
    rep.check("physical damage, rental and towing claims only on risk rows carrying that coverage",
              all((cov_ok.loc[cov_ok["Coverage Code"] == k, col] > 0).all() for k, col in
                  (("COLL", "Collision Premium"), ("COMP", "Comprehensive Premium"), ("RENT", "Rental Premium"),
                   ("TOW", "Towing Premium"))))
    integrity_limits(rep, cov_ok)
    age = (pd.to_datetime(drv["Added Date"]) - pd.to_datetime(drv["Date of Birth"])).dt.days.to_numpy() / 365.25
    rep.check("all drivers are 16 or older when first insured", age.min() >= 16, f"youngest {age.min():.1f}, oldest {age.max():.1f}")
    integrity_lifecycle(rep, risk, term, pol, veh, drv, clm, feat, pay, inc, r_start, r_end, valuation)
    integrity_claims_and_quotes(rep, term, veh, clm, feat, reserves, quotes)
    old = term[pd.to_datetime(term["Policy Expiration Date"]) < pd.Timestamp(valuation) - pd.Timedelta(days=90)]
    written = ledger[ledger["Transaction Type"] != "Cancellation"].groupby("Policy Term ID")["Written Premium"].sum()
    returned = ledger[ledger["Transaction Type"] == "Cancellation"].groupby("Policy Term ID")["Written Premium"].sum()
    gap_w = old["Written Premium"] + old["Endorsement Premium"] - written.reindex(old["Policy Term ID"]).fillna(0).to_numpy()
    gap_r = old["Return Premium"] - returned.reindex(old["Policy Term ID"]).fillna(0).to_numpy()
    rep.check("the transaction ledger adds up to each completed term's written, endorsement and return premium",
              (gap_w.abs() <= 0.01 * old["Vehicles at Term Start"] + 0.05).all() and (gap_r.abs() <= 0.05).all(),
              f"{ledger['Transaction Type'].value_counts().to_dict()}")

    print("\nFREQUENCY AND SEVERITY (paid claims by coverage: whole extract, every deductible and cause, loss only)")
    f = feat.merge(clm[["Claim ID", "Record ID", "Loss Date", "Catastrophe ID", "Cause of Loss"]], on="Claim ID")
    has = {"BI": risk["BI Premium"] > 0, "PD": risk["PD Premium"] > 0, "UM": risk["UM Premium"] > 0,
           "MED": risk["Med Pay Premium"] > 0, "COLL": risk["Collision Premium"] > 0, "COMP": risk["Comprehensive Premium"] > 0,
           "RENT": risk["Rental Premium"] > 0, "TOW": risk["Towing Premium"] > 0}
    prem_col = {"BI": "BI Premium", "PD": "PD Premium", "UM": "UM Premium", "MED": "Med Pay Premium",
                "RENT": "Rental Premium", "TOW": "Towing Premium",
                "COLL": "Collision Premium", "COMP": "Comprehensive Premium"}
    share = risk["Earned Premium"] / risk["Total Premium"]
    exp_total = 0.0
    print(f"  {'coverage':9s}{'car-years':>11s}{'claims/100':>12s}{'avg paid':>10s}{'loss ratio':>12s}{'actual/expected':>17s}")
    for k in ["BI", "PD", "UM", "MED", "COLL", "COMP", "RENT", "TOW"]:
        g = f[f["Coverage Code"] == k]
        gp = g[g["Paid Loss"] > 0]
        years = risk.loc[has[k], "Earned Exposure"].sum()
        e_prem = (risk[prem_col[k]] * share).sum()
        expected = truth[f"Expected Loss {k}"].sum()
        noncat = g[g["Catastrophe ID"].isna()]["Net Incurred Loss"].sum()
        print(f"  {k:9s}{years:11,.0f}{len(gp) / years * 100:12.2f}{gp['Paid Loss'].mean():10,.0f}"
              f"{g['Net Incurred Loss'].sum() / e_prem:12.1%}{noncat / expected:17.3f}")
        if k in TARGETS:
            rep.band(f"{k} frequency per 100 car-years (tuning band)", len(gp) / years * 100, TARGETS[k]["freq"])
            rep.band(f"{k} average paid loss (tuning band)", gp["Paid Loss"].mean(), TARGETS[k]["sev"], "{:,.0f}")
        exp_total += expected
    noncat_all = f[f["Catastrophe ID"].isna()]["Net Incurred Loss"].sum()
    rep.band("non-catastrophe incurred vs answer-key expected (all coverages)", noncat_all / exp_total, (0.93, 1.07), "{:.3f}")

    print("\nBENCHMARK COMPARISON (Triple-I / ISO definitions: paid claims by calendar year, liability with LAE, "
          f"physical damage at a ${BENCHMARK_DEDUCTIBLE} deductible, comprehensive without wind and water)")
    benchmark(rep, risk, f, pay, r_start, r_end, pd.Timestamp(valuation).year - 1)

    print("\nLOSS RATIO BY ACCIDENT YEAR (net incurred as of the valuation date / earned premium; losses exclude LAE,\n"
          "which is shown beside it; add the two for a loss-and-LAE ratio; neither is a combined ratio)")
    s, e, days = r_start, r_end, r_days
    rate = np.divide(risk["Earned Premium"].to_numpy(), days, out=np.zeros(len(risk)), where=days > 0)
    loss_year = pd.to_datetime(clm["Loss Date"]).dt.year
    years = sorted(loss_year.unique())
    lr = {}
    for y in years:
        a, b = np.datetime64(f"{y}-01-01"), np.datetime64(f"{y + 1}-01-01")
        overlap = (np.minimum(e, b) - np.maximum(s, a)).astype("timedelta64[D]").astype(int).clip(0)
        prem = (overlap * rate).sum()
        m = loss_year == y
        lr[y] = clm.loc[m, "Claim Amount"].sum() / prem
        cat = clm.loc[m & clm["Catastrophe ID"].notna(), "Claim Amount"].sum() / prem
        print(f"  {y}: earned premium ${prem:>12,.0f}   car-years {(overlap * (days > 0)).sum() / 365.25:>8,.0f}   "
              f"loss ratio {lr[y]:6.1%}   (catastrophe {cat:5.1%})   LAE ratio {clm.loc[m, 'Expense Amount'].sum() / prem:5.1%}")
    full = [y for y in years if y < years[-1]]
    for y in full:
        rep.band(f"{y} loss ratio", lr[y], LOSS_RATIO_BAND, "{:.1%}")
    exp_loss = truth.set_index("Record ID")["Expected Loss Total"].reindex(risk["Record ID"]).to_numpy()
    exp_rate = np.divide(exp_loss, days, out=np.zeros(len(risk)), where=days > 0)
    for y, b in INDUSTRY_LOSS_RATIO_BAND.items():
        a_, b_ = np.datetime64(f"{y}-01-01"), np.datetime64(f"{y + 1}-01-01")
        overlap = (np.minimum(e, b_) - np.maximum(s, a_)).astype("timedelta64[D]").astype(int).clip(0)
        if y in years and y < years[-1]:
            rep.band(f"{y} expected loss ratio (answer key) vs industry", (overlap * exp_rate).sum() / (overlap * rate).sum(), b, "{:.1%}")
    rep.band("overall loss ratio", clm["Claim Amount"].sum() / ep, OVERALL_LOSS_RATIO_BAND, "{:.1%}")
    print(f"  note: {years[-1]} is a partial year and excludes claims not yet reported, so it looks better than it will develop.")
    # the book in force on the start date is there from day one: no artificial ramp-up in the first year
    bounds = (start.astype("M8[M]") + np.arange(13).astype("timedelta64[M]")).astype("M8[D]")
    per_day = [(np.minimum(e, b) - np.maximum(s, a)).astype(int).clip(0).sum() / (b - a).astype(int)
               for a, b in zip(bounds[:-1], bounds[1:])]
    rep.band("first month's exposure relative to the first year's average", per_day[0] / np.mean(per_day), (0.85, 1.15), "{:.2f}")

    print("\nBOOK PROFILE")
    age_now = age
    print(f"  drivers: {np.mean(age_now < 25):.1%} under 25, {np.mean(age_now >= 65):.1%} 65+, median age {np.median(age_now):.0f}, "
          f"{(drv.Gender == 'M').mean():.1%} male, {(drv['Marital Status'] == 'M').mean():.1%} married")
    rep.band("share of drivers with no violation in 3 years", (drv["Number of Violations"] == 0).mean(), (0.78, 0.90), "{:.1%}")
    rep.band("share of drivers with no at-fault accident in 3 years", (drv["Number of Accidents"] == 0).mean(), (0.86, 0.95), "{:.1%}")
    vage = pd.to_datetime(veh["Added Date"]).dt.year.to_numpy() - veh["Vehicle Model Year"].to_numpy()
    print(f"  vehicles: mean age {vage.mean():.1f} years, {(veh['Collision Coverage'] == 'Y').mean():.1%} with collision, "
          f"{(veh['Comprehensive Coverage'] == 'Y').mean():.1%} with comprehensive, {(veh['Removed Date'].isna()).sum() / len(pol):.2f} per policy, removals {veh['Removal Reason'].value_counts().to_dict()}")
    print(f"  BI limits: {pol['BI Limit'].value_counts(normalize=True).round(3).to_dict()}")
    print(f"  underwriting company mix: {pol['Underwriting Company ID'].value_counts(normalize=True).sort_index().round(3).to_dict()}")
    ended = term[(pd.to_datetime(term["Policy Expiration Date"]) <= pd.Timestamp(valuation))]
    lapsed = ended["Cancel Date"].notna() | ended["Non-Renewal Reason"].notna()
    months = (pd.to_datetime(ended["Policy Expiration Date"]) - pd.to_datetime(ended["Policy Effective Date"])).dt.days / 30.44
    annual_retention = float(np.exp(np.log(1 - lapsed.mean()) * 12 / months.mean()))
    rep.band("annualised policy retention", annual_retention, (0.78, 0.90), "{:.1%}")
    print(f"  cancellations: {term['Cancel Reason'].value_counts().to_dict()}; non-renewals: {term['Non-Renewal Reason'].value_counts().to_dict()}")
    print(f"  claims: {(clm['Claim Status'] == 'Open').mean():.1%} open at valuation; cause mix "
          f"{clm['Cause of Loss'].value_counts(normalize=True).round(3).head(8).to_dict()}")

    print("\nRISK SIGNAL (does the data reward analysis?)")
    r = risk.merge(truth, on="Record ID")
    cl = clm.groupby("Record ID")["Claim Amount"].sum().reindex(r["Record ID"]).fillna(0).to_numpy()
    r["loss"] = cl
    young = r["Rated Driver Age"] < 21
    for label, m in [("drivers under 21", young), ("drivers 30-64", (r["Rated Driver Age"] >= 30) & (r["Rated Driver Age"] < 65)),
                     ("1+ at-fault accident", r["Rated At-Fault Accidents"] > 0), ("clean record", (r["Rated At-Fault Accidents"] == 0) & (r["Rated Violation Points"] == 0))]:
        g = r[m]
        print(f"  {label:22s} loss ratio {g.loss.sum() / g['Earned Premium'].sum():6.1%}   expected {g['Expected Loss Total'].sum() / g['Earned Premium'].sum():6.1%}"
              f"   claims per 100 car-years {clm['Record ID'].isin(g['Record ID']).sum() / g['Earned Exposure'].sum() * 100:5.1f}")
    z = r.merge(loc[["Location ID", "Region"]], on="Location ID").groupby("Region").agg(
        car_years=("Earned Exposure", "sum"), premium=("Earned Premium", "sum"), loss=("loss", "sum"), expected=("Expected Loss Total", "sum"))
    z["avg premium"] = (z.premium / z.car_years).round(0)
    z["loss ratio"] = (z.loss / z.premium).round(3)
    z["expected loss ratio"] = (z.expected / z.premium).round(3)
    print("  " + z[["car_years", "avg premium", "loss ratio", "expected loss ratio"]].round(3).to_string().replace("\n", "\n  "))

    warned = f" ({rep.warnings} calibration warning(s) on a small book)" if rep.warnings else ""
    print(f"\n{'ALL CHECKS PASSED' if rep.failures == 0 else str(rep.failures) + ' CHECK(S) FAILED'}{warned}")
    sys.exit(1 if rep.failures else 0)


if __name__ == "__main__":
    main()
