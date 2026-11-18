#!/usr/bin/env python3
"""Print the figures the README, CHANGELOG and docs/limitations.md quote about the default run.

    python scripts/readme_figures.py --out output

Reads the generated tables (and the answer key) and prints each figure with a label, so the documentation can
be refreshed after the generator or the default run changes. `validate.py` prints the calibration figures
(frequency and severity against national, loss ratios by accident year); this script prints the rest.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd


def read(folder: Path, name: str, **kw) -> pd.DataFrame:
    return pd.read_csv(folder / f"{name}.csv", keep_default_na=False, na_values=[""], low_memory=False, **kw)


def year_overlap(s: pd.Series, e: pd.Series, year: int) -> np.ndarray:
    """Days of each [s, e) window falling in the calendar year."""
    a, b = np.datetime64(f"{year}-01-01"), np.datetime64(f"{year + 1}-01-01")
    return (np.minimum(e.to_numpy(), b) - np.maximum(s.to_numpy(), a)).astype("timedelta64[D]").astype(int).clip(0)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", type=Path, default=Path("output"))
    out = ap.parse_args().out
    summary = json.loads((out / "run_summary.json").read_text())
    start, valuation = pd.Timestamp(summary["start"]), pd.Timestamp(summary["valuation"])
    years = list(range(start.year, valuation.year + 1))

    pol, term, drv, veh = read(out, "policy"), read(out, "policy_term"), read(out, "driver"), read(out, "insured_vehicle")
    ex, clm, feat = read(out, "exposure"), read(out, "claim"), read(out, "claim_feature")
    res, tx, q = read(out, "claim_reserve_transaction"), read(out, "premium_transaction"), read(out, "quote")
    pay, vmy = read(out, "claim_payment"), read(out, "vehicle_model_year")
    enrol, score = read(out, "telematics_enrollment"), read(out, "telematics_score")
    truth = read(out / "answer_key", "exposure_truth")
    vtruth = read(out / "answer_key", "insured_vehicle_truth")
    p = lambda label, value: print(f"  {label}: {value}")

    print("RUN")
    p("policies / terms", f"{len(pol):,} / {len(term):,} ({(term.effective_date < summary['start']).sum():,} terms in force on the start date)")
    removal = veh.removal_reason.value_counts()
    p("drivers / vehicles", f"{len(drv):,} / {len(veh):,} ({drv.removed_date.notna().sum():,} drivers left a policy; "
      f"{removal.get('Replaced', 0):,} vehicles traded in, {removal.get('Sold', 0):,} sold, "
      f"{removal.get('Destroyed or Stolen', 0) + removal.get('Total Loss', 0):,} destroyed or stolen, "
      f"{removal.get('Left With Driver', 0):,} taken by a leaving driver)")
    insured = vmy[vmy.vehicle_model_year_id.isin(veh.vehicle_model_year_id)]
    p("models insured", f"{len(insured.groupby(['make', 'model'])):,} of {len(vmy.groupby(['make', 'model'])):,} "
      f"({insured.make.nunique()} makes)")
    p("exposure rows", f"{len(ex):,} ({(ex.endorsement_number > 0).mean():.1%} start at a mid-term change)")
    p("premium transactions", f"{len(tx):,} ({(tx.transaction_type == 'Endorsement').sum():,} endorsements)")
    car_years, prem = ex.earned_exposure.sum(), ex.earned_premium.sum()
    p("earned exposure / premium", f"{car_years:,.0f} car-years, ${prem / 1e6:,.1f} million (${prem / car_years:,.0f} per car-year)")
    closed = feat[feat.feature_status == "Closed"]
    liab = closed.coverage_code.isin(["BI", "PD", "UM", "MED"])
    phys = closed.coverage_code.isin(["COLL", "COMP"])
    p("claims / features / reserve transactions",
      f"{len(clm):,} / {len(feat):,} / {len(res):,} ({(closed.closed_without_payment[liab] == 'Y').mean():.0%} of closed liability "
      f"and medical features and {(closed.closed_without_payment[phys] == 'Y').mean():.0%} of closed physical damage features paid nothing)")
    p("quotes", f"{len(q):,}, {(q.bound == 'Y').mean():.1%} bound; telematics opt-in {q.telematics_opt_in.eq('Y').mean():.1%}")
    in_force = pol.policy_status == "In Force"
    p("in force at valuation", f"{in_force.sum():,} policies, {pol.number_of_vehicles[in_force].sum():,} vehicles")

    s, e = pd.to_datetime(ex.coverage_start_date).clip(lower=start), pd.to_datetime(ex.coverage_start_date).clip(lower=start)
    e = s + pd.to_timedelta(np.round(ex.earned_exposure * 365.25), unit="D")
    rate = np.divide(ex.earned_premium.to_numpy(), (e - s).dt.days.to_numpy(), out=np.zeros(len(ex)), where=(e - s).dt.days.to_numpy() > 0)
    exp_rate = np.divide(ex.exposure_id.map(truth.set_index("exposure_id").expected_loss_total).to_numpy(), (e - s).dt.days.to_numpy(),
                         out=np.zeros(len(ex)), where=(e - s).dt.days.to_numpy() > 0)
    on = (ex.telematics_enrolled == "Y").to_numpy()
    d = ex.telematics_discount_pct.to_numpy() / 100
    disc_cols = ["bi_premium", "pd_premium", "um_premium", "med_pay_premium", "collision_premium", "comprehensive_premium"]
    discount_share = ex[disc_cols].sum(axis=1).to_numpy() * d / np.maximum(1 - d, 1e-9) / np.maximum(ex.total_premium.to_numpy(), 1e-9)
    print("BY YEAR (earned basis)")
    for y in years:
        o = year_overlap(s, e, y)
        ep = (o * rate).sum()
        p(str(y), f"expected loss ratio {(o * exp_rate).sum() / ep:.1%}; enrolled cars {(o * on).sum() / o.sum():.1%} of car-years; "
          f"telematics discount {(o * rate * discount_share).sum() / ep:.1%} of premium")
    p("telematics", f"{len(enrol):,} enrolments, {len(score):,} scores")

    # bodily injury luck: paid claims a year and the standard deviation of their total in loss-ratio points
    cy = clm.assign(year=pd.to_datetime(clm.loss_date).dt.year)
    bi = feat[feat.coverage_code == "BI"].groupby("claim_id").paid_loss.sum()
    cy["bi"] = cy.claim_id.map(bi).fillna(0)
    for y in years[:-1]:
        o = year_overlap(s, e, y)
        x = cy.loc[(cy.year == y) & (cy.bi > 0), "bi"]
        p(f"{y} bodily injury", f"{len(x):,} paid claims, standard deviation of their total {np.sqrt((x ** 2).sum()) / (o * rate).sum():.1%} of premium")

    print("FINDINGS")
    j = ex.merge(truth[["exposure_id", "expected_loss_total"]], on="exposure_id")
    elr = lambda g: g.expected_loss_total.sum() / g.earned_premium.sum()
    by_class = j.groupby("rated_driver_class").apply(elr, include_groups=False)
    young = by_class[[c for c in by_class.index if c[:2] in ("16", "18", "21")]]
    adult = j[j.rated_driver_class.isin(["25-29", "30-39", "40-49", "50-64"])]
    p("young drivers", f"expected loss ratio {young.min():.0%} to {young.max():.0%} for classes under 25, {elr(adult):.0%} for 25 to 64")
    jv = j.merge(veh[["insured_vehicle_id", "annual_mileage", "automatic_emergency_braking"]], on="insured_vehicle_id")
    p("mileage", f"expected loss ratio {elr(jv[jv.annual_mileage < 5000]):.0%} under 5,000 reported miles, "
      f"{elr(jv[jv.annual_mileage >= 16000]):.0%} at 16,000+")
    p("emergency braking", f"expected loss ratio {elr(jv[jv.automatic_emergency_braking == 'Y']):.1%} with, "
      f"{elr(jv[jv.automatic_emergency_braking == 'N']):.1%} without")
    p("telematics", f"expected loss ratio {elr(j[on]):.1%} enrolled, {elr(j[~on]):.1%} not; "
      f"{elr(j[on & (d <= 0.10)]):.0%} earning 10% or less, {elr(j[on & (d > 0.20)]):.0%} earning 21% to 30%")
    sc = score[score.days_monitored >= 45].merge(veh[["insured_vehicle_id", "annual_mileage"]], on="insured_vehicle_id")
    ratio = sc.miles_driven * 365.25 / sc.days_monitored / sc.annual_mileage
    p("telematics mileage", f"annualised miles above reported for {(ratio > 1).mean():.0%} of scored windows (median {ratio.median() - 1:+.0%})")

    kh = veh.insured_vehicle_id.map(vtruth.set_index("insured_vehicle_id").kia_hyundai_theft_exposure).eq("Y")
    kh_id = set(veh.insured_vehicle_id[kh])
    comp = ex.comprehensive_premium.to_numpy() > 0
    thefts = cy[cy.cause_of_loss == "THEFT_TOTAL"]
    rates = {}
    for y in years:
        o = year_overlap(s, e, y) * comp / 365.25
        affected = ex.insured_vehicle_id.isin(kh_id).to_numpy()
        n = thefts[thefts.year == y].insured_vehicle_id.isin(kh_id)
        rates[y] = (n.sum() / (o * affected).sum() * 1000, (~n).sum() / (o * ~affected).sum() * 1000)
    peak = max(rates, key=lambda y: rates[y][0])
    p("Kia/Hyundai thefts per 1,000 comprehensive vehicle-years",
      "; ".join(f"{y}: {a:.1f} affected, {b:.1f} others" for y, (a, b) in rates.items()) + f" (peak {peak})")

    # incurred development from 12 to 24 months: paid to date plus case reserve at each year end
    pay_ = pay[pay.payment_type == "Loss"].merge(feat[["claim_feature_id", "coverage_code"]], on="claim_feature_id") \
        .merge(clm[["claim_id", "loss_date"]], on="claim_id")
    rs = res[res.reserve_type == "Loss"].merge(feat[["claim_feature_id", "coverage_code"]], on="claim_feature_id") \
        .merge(clm[["claim_id", "loss_date"]], on="claim_id")
    for cov in ("BI", "COLL"):
        out_ = []
        for ay in years:
            if ay + 1 > valuation.year:
                continue
            inc = []
            for age in (0, 1):
                eval_ = f"{ay + age}-12-31"
                pp = pay_[(pay_.coverage_code == cov) & pay_.loss_date.str.startswith(str(ay)) & (pay_.payment_date <= eval_)].amount.sum()
                r = rs[(rs.coverage_code == cov) & rs.loss_date.str.startswith(str(ay)) & (rs.transaction_date <= eval_)]
                case = r.sort_values(["transaction_date", "reserve_transaction_id"]).groupby("claim_feature_id").outstanding_reserve.last().sum()
                inc.append(pp + case)
            out_.append(f"{ay} {inc[1] / inc[0] - 1:+.0%}")
        p(f"{cov} incurred, 12 to 24 months", ", ".join(out_))

    ia = q[(q.distribution_channel == "Independent Agent") & q.competitor_annual_premium.notna()]
    below = ia.quoted_annual_premium < ia.competitor_annual_premium
    p("quotes", f"independent-agent quotes below the best competitor bind {(ia.bound[below] == 'Y').mean():.0%}, "
      f"above {(ia.bound[~below] == 'Y').mean():.0%}")
    sc_ = j.policy_id.map(pol.set_index("policy_id").insurance_score)
    band = pd.cut(sc_, [0, 600, 700, 800, 1000], right=False, labels=["<600", "600-699", "700-799", "800+"]).astype(str).replace("nan", "no score")
    g = j.groupby(band)
    prem_cy = g.earned_premium.sum() / g.earned_exposure.sum()
    p("insurance score", "; ".join(f"{b}: ${prem_cy[b]:,.0f} per car-year, expected {elr(j[band == b]):.0%}" for b in prem_cy.index))


if __name__ == "__main__":
    main()
