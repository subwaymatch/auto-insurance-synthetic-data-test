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

# Paid claim frequency per 100 earned car-years and average paid claim, with tolerance bands.
# Anchors: Triple-I / ISO private passenger auto, 2022-2024 national (BI 0.70-0.80 at $24.7-28.3k,
# PD 2.50-2.59 at $6.0-6.8k, collision 4.16-4.48 at $5.4-5.5k, comprehensive 3.78-4.08 at $2.2-2.3k).
# The frequency bands sit above national because the book is urban.
TARGETS = {
    "BI":   dict(freq=(0.70, 1.15), sev=(20_000, 30_000)),
    "PD":   dict(freq=(2.40, 3.40), sev=(5_800, 7_400)),
    "COLL": dict(freq=(4.00, 5.80), sev=(4_700, 6_300)),
    "COMP": dict(freq=(3.60, 5.20), sev=(1_900, 2_700)),
}
LOSS_RATIO_BAND = (0.52, 0.88)          # every full accident year; industry 2022-2025 ran roughly 61%-80%,
                                        # and a book this size moves several points on large claims alone
OVERALL_LOSS_RATIO_BAND = (0.62, 0.76)


def integrity_lifecycle(rep, risk, term, pol, veh, clm, feat, pay, inc, r_start, r_end) -> None:
    """Checks on vehicle lifecycles, information timing, policy dates, premium and payments."""
    dt = lambda x: pd.to_datetime(x)
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
    tl = feat[feat["Total Loss"] == "Y"].merge(clm[["Claim ID", "Insured Vehicle ID", "Loss Date"]], on="Claim ID")
    tl = tl.groupby("Insured Vehicle ID")["Loss Date"].min()
    gone = dt(tl) + pd.Timedelta(days=1)
    rep.check("every total loss ends the vehicle's cover the day after the loss",
              (removed.reindex(tl.index) == gone).all() and (v["Removal Reason"].reindex(tl.index) == "Total Loss").all(),
              f"{len(tl):,} total-loss vehicles")
    rp = veh.dropna(subset=["Replaces Vehicle ID"])
    old = v.reindex(rp["Replaces Vehicle ID"].astype(int))
    rep.check("replacement vehicles follow the vehicle they replace on the same policy",
              (old["Policy Number"].to_numpy() == rp["Policy Number"].to_numpy()).all()
              and (dt(old["Removed Date"]).to_numpy() <= dt(rp["Added Date"]).to_numpy()).all(),
              f"{len(rp):,} replacements, {(old['Removal Reason'] == 'Total Loss').sum():,} after a total loss")

    # information timing: every rated record is exactly the incidents known on the term's rating date
    t = term.set_index("Policy Term ID")
    eff, rdate = dt(t["Policy Effective Date"]), dt(t["Rating Date"])
    rep.check("every term is rated before it takes effect", (rdate <= eff).all())
    i = inc.assign(d=dt(inc["Incident Date"]), k=dt(inc["Known Date"]))
    j = risk[["Record ID", "Driver ID", "Policy Term ID"]].merge(i[["Driver ID", "d", "k", "Incident Type"]], on="Driver ID")
    je, jr = eff.reindex(j["Policy Term ID"]).to_numpy(), rdate.reindex(j["Policy Term ID"]).to_numpy()
    j = j[(j.d.to_numpy() <= je) & (j.d.to_numpy() > je - np.timedelta64(3 * 365, "D")) & (j.k.to_numpy() <= jr)]
    pts = j["Incident Type"].map({"Minor Violation": 1, "Major Violation": 3}).fillna(0).groupby(j["Record ID"]).sum()
    acc = (j["Incident Type"] == "At-Fault Accident").groupby(j["Record ID"]).sum()
    rep.check("rated violations and accidents are those known on the rating date",
              (risk["Record ID"].map(pts).fillna(0) == risk["Rated Violation Points"]).all()
              and (risk["Record ID"].map(acc).fillna(0) == risk["Rated At-Fault Accidents"]).all())
    rep.check("an incident is known only after it happened", (i.k >= i.d).all())
    rep.check("no good-student discount at 25 or older", not ((risk["Rated Good Student"] == "Y") & (risk["Rated Driver Age"] >= 25)).any())

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
    done = term["Cancel Date"].notna() | (dt(term["Policy Expiration Date"]) <= dt(clm["Report Date"]).max())
    gap = (term["Written Premium"] + term["Endorsement Premium"] + term["Return Premium"]
           - term["Earned Before Extract"] - term["Earned Premium"])[done]
    rep.check("finished terms' written, endorsement and return premium equal their earned premium",
              (gap.abs() <= 0.01 * term["Vehicle Count"][done] + 0.05).all(), f"largest difference ${gap.abs().max():.2f}")

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


class Report:
    def __init__(self) -> None:
        self.failures = 0

    def check(self, label: str, ok: bool, detail: str = "") -> None:
        self.failures += not ok
        print(f"  [{'ok' if ok else 'FAIL'}] {label}{(': ' + detail) if detail else ''}")

    def band(self, label: str, value: float, band: tuple[float, float], fmt: str = "{:,.2f}") -> None:
        self.check(label, band[0] <= value <= band[1], f"{fmt.format(value)} (target {fmt.format(band[0])} to {fmt.format(band[1])})")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", type=Path, default=Path(__file__).resolve().parent / "output")
    out = ap.parse_args().out
    read = lambda name, **kw: pd.read_csv(out / f"{name}.csv", keep_default_na=False, na_values=[""], low_memory=False, **kw)
    pol, term, risk = read("policy_dimension"), read("policy_term_fact"), read("risk_fact")
    drv, veh, loc = read("driver_dimension"), read("insured_vehicle_dimension"), read("location_dimension")
    clm, feat, pay = read("claims_fact"), read("claim_coverage_fact"), read("claim_payment_fact")
    inc = read("driver_incident_fact")
    truth = pd.read_csv(out / "answer_key" / "risk_truth.csv")
    start = np.datetime64(json.loads((out / "run_summary.json").read_text())["start"])
    pd.set_option("display.width", 200)
    rep = Report()

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
    cov_ok = feat.merge(clm[["Claim ID", "Insured Vehicle ID"]], on="Claim ID").merge(veh, on="Insured Vehicle ID")
    rep.check("collision/comprehensive claims only on vehicles with that coverage",
              (cov_ok.loc[cov_ok["Coverage Code"] == "COLL", "Collision Coverage"] == "Y").all()
              and (cov_ok.loc[cov_ok["Coverage Code"] == "COMP", "Comprehensive Coverage"] == "Y").all())
    age = (pd.to_datetime(drv["Added Date"]) - pd.to_datetime(drv["Date of Birth"])).dt.days.to_numpy() / 365.25
    rep.check("all drivers are 16 or older when first insured", age.min() >= 16, f"youngest {age.min():.1f}, oldest {age.max():.1f}")
    integrity_lifecycle(rep, risk, term, pol, veh, clm, feat, pay, inc, r_start, r_end)

    print("\nFREQUENCY AND SEVERITY (paid claims, by coverage)")
    f = feat.merge(clm[["Claim ID", "Record ID", "Loss Date", "Catastrophe ID", "Cause of Loss"]], on="Claim ID")
    has = {"BI": risk["BI Premium"] > 0, "PD": risk["PD Premium"] > 0, "UM": risk["UM Premium"] > 0,
           "MED": risk["Med Pay Premium"] > 0, "COLL": risk["Collision Premium"] > 0, "COMP": risk["Comprehensive Premium"] > 0}
    prem_col = {"BI": "BI Premium", "PD": "PD Premium", "UM": "UM Premium", "MED": "Med Pay Premium",
                "COLL": "Collision Premium", "COMP": "Comprehensive Premium"}
    share = risk["Earned Premium"] / risk["Total Premium"]
    exp_total = 0.0
    print(f"  {'coverage':9s}{'car-years':>11s}{'claims/100':>12s}{'avg paid':>10s}{'loss ratio':>12s}{'actual/expected':>17s}")
    for k in ["BI", "PD", "UM", "MED", "COLL", "COMP"]:
        g = f[f["Coverage Code"] == k]
        gp = g[g["Paid Loss"] > 0]
        years = risk.loc[has[k], "Earned Exposure"].sum()
        e_prem = (risk[prem_col[k]] * share).sum()
        expected = truth[f"Expected Loss {k}"].sum()
        noncat = g[g["Catastrophe ID"].isna()]["Net Incurred Loss"].sum()
        print(f"  {k:9s}{years:11,.0f}{len(gp) / years * 100:12.2f}{gp['Paid Loss'].mean():10,.0f}"
              f"{g['Net Incurred Loss'].sum() / e_prem:12.1%}{noncat / expected:17.3f}")
        if k in TARGETS:
            rep.band(f"{k} frequency per 100 car-years", len(gp) / years * 100, TARGETS[k]["freq"])
            rep.band(f"{k} average paid claim", gp["Paid Loss"].mean(), TARGETS[k]["sev"], "{:,.0f}")
        exp_total += expected
    noncat_all = f[f["Catastrophe ID"].isna()]["Net Incurred Loss"].sum()
    rep.band("non-catastrophe incurred vs answer-key expected (all coverages)", noncat_all / exp_total, (0.93, 1.07), "{:.3f}")

    print("\nLOSS RATIO BY ACCIDENT YEAR (net incurred as of the valuation date / earned premium)")
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
          f"{(veh['Comprehensive Coverage'] == 'Y').mean():.1%} with comprehensive, {(veh['Removed Date'].isna()).sum() / len(pol):.2f} per policy, {veh['Removed Date'].notna().sum():,} replaced")
    print(f"  BI limits: {pol['BI Limit'].value_counts(normalize=True).round(3).to_dict()}")
    print(f"  underwriting company mix: {pol['Underwriting Company ID'].value_counts(normalize=True).sort_index().round(3).to_dict()}")
    ended = term[(pd.to_datetime(term["Policy Expiration Date"]) <= pd.to_datetime(clm["Report Date"]).max())]
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

    print(f"\n{'ALL CHECKS PASSED' if rep.failures == 0 else str(rep.failures) + ' CHECK(S) FAILED'}")
    sys.exit(1 if rep.failures else 0)


if __name__ == "__main__":
    main()
