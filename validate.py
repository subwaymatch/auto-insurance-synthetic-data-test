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

# Each full accident year's actual loss ratio against its expected one (answer key): the claims simulated are
# consistent with their expectation, give or take claim luck. Calibration itself is held by the expected loss
# ratio against industry (below). A year of the default book has about 250 paid bodily injury claims, whose
# total alone varies by 1.5 to 3 loss-ratio points (one standard deviation; scripts/readme_figures.py). The
# answer key's expected losses exclude catastrophes, so the actual ratio is taken without them. (This replaced
# an absolute band of 52% to 88% on the actual ratio, which mixed calibration with luck.)
ACTUAL_TO_EXPECTED_BAND = (0.85, 1.15)
OVERALL_LOSS_RATIO_BAND = (0.62, 0.76)
# Expected (noise-free, from the answer key) loss ratio by accident year plus the year's catastrophe losses
# (which industry figures include and the answer key's expected losses leave out), against industry pure loss
# ratios (incurred losses excluding LAE / earned premium, direct). US private auto: 80.2% (2022, APCIA), 75.4% (2023),
# 66.1% (2024) and 61.5% (2025) (S&P Global); Illinois: 79.6%, 72.8%, 63.4% and 60.1% (Illinois DOI market
# share reports). Bands are about +/-5 points around those figures.
INDUSTRY_LOSS_RATIO_BAND = {2022: (0.74, 0.85), 2023: (0.68, 0.80), 2024: (0.59, 0.70), 2025: (0.55, 0.67)}


def integrity_claims_and_quotes(rep, term, veh, clm, feat, reserves, quotes) -> None:
    """Reserve history, claim detail, vehicle identifiers and the quote funnel."""
    r = reserves.sort_values(["claim_feature_id", "reserve_type", "transaction_date", "reserve_transaction_id"], kind="stable")
    running = r.groupby(["claim_feature_id", "reserve_type"])["change_amount"].cumsum()
    last = r.groupby(["claim_feature_id", "reserve_type"])["outstanding_reserve"].last().unstack()
    at_val = lambda kind: (last[kind] if kind in last else pd.Series(dtype=float)).reindex(feat["claim_feature_id"]).fillna(0).to_numpy()
    rep.check("reserve history balances, and ends at each feature's case and expense reserve",
              np.allclose(running, r["outstanding_reserve"], atol=0.01)
              and np.allclose(at_val("Loss"), feat["case_reserve"], atol=0.01)
              and np.allclose(at_val("Expense"), feat["expense_reserve"], atol=0.01),
              f"{len(reserves):,} reserve transactions")
    dt = lambda x: pd.to_datetime(x)
    f = feat.merge(clm[["claim_id", "loss_date", "at_fault", "insured_fault_pct", "report_date", "siu_referral_date"]], on="claim_id")
    suits = f[f["litigation"] == "Y"]
    rep.check("suits follow the attorney and the claim, precede the close, and fall within Illinois' two-year limit",
              (dt(suits["suit_date"]) >= dt(suits["attorney_date"])).all()
              and (dt(suits["suit_date"]) >= dt(suits["open_date"])).all()
              and (suits["close_date"].isna() | (dt(suits["suit_date"]) < dt(suits["close_date"]))).all()
              and ((dt(suits["suit_date"]) - dt(suits["loss_date"])).dt.days <= 730).all(),
              f"{(feat['attorney_represented'] == 'Y').sum():,} represented claimants, {len(suits):,} suits")
    fault = clm.dropna(subset=["insured_fault_pct"])
    att = f[f["attorney_represented"] == "Y"]
    rep.check("attorneys are retained after the loss and before the feature closes",
              (dt(att["attorney_date"]) >= dt(att["loss_date"])).all()
              and (att["close_date"].isna() | (dt(att["attorney_date"]) <= dt(att["close_date"]))).all())
    rep.check("an insured at fault is over 50% at fault, and one not at fault is under 51%",
              ((fault["at_fault"] == "Y") == (fault["insured_fault_pct"] > 50)).all())
    siu = clm[clm["siu_referral"] == "Y"]
    rep.check("fraud referrals come after the claim is reported", (siu["siu_referral_date"] >= siu["report_date"]).all())
    rep.check("VIN prefixes are consistent for each make, model and model year",
              (veh.groupby("vehicle_model_year_id")["vin_prefix"].nunique() == 1).all())
    b = quotes[quotes["bound"] == "Y"].merge(term[term["business_type"] == "New"], on="policy_id")
    rep.check("every bound quote is a new-business policy starting on the quoted date",
              (b["proposed_effective_date"] == b["effective_date"]).all() and (quotes["quote_date"] <= quotes["proposed_effective_date"]).all(),
              f"{len(quotes):,} quotes, {(quotes['bound'] == 'Y').mean():.1%} bound")


def business_day(dates) -> np.ndarray:
    """Whether each date is a business day: a weekday that is not a US federal holiday (as observed) or the day
    after Thanksgiving. Worked out here from pandas' holiday calendar, independently of the generator's."""
    from pandas.tseries.holiday import USFederalHolidayCalendar
    d = pd.to_datetime(pd.Series(dates).dropna()).reset_index(drop=True)
    if d.empty:
        return np.ones(0, dtype=bool)
    hol = USFederalHolidayCalendar().holidays(d.min() - pd.Timedelta(days=7), d.max() + pd.Timedelta(days=7))
    after_thanksgiving = [h + pd.Timedelta(days=1) for h in hol if h.month == 11 and h.dayofweek == 3 and h.day >= 22]
    off = set(hol) | set(after_thanksgiving)
    return ((d.dt.dayofweek < 5) & ~d.isin(off)).to_numpy()


def vin_check_digit(vin: pd.Series) -> pd.Series:
    """The check digit a 17-character VIN should carry in position 9 (49 CFR 565)."""
    value = {**{str(i): i for i in range(10)}, **dict(zip("ABCDEFGH", range(1, 9))), **dict(zip("JKLMN", range(1, 6))),
             "P": 7, "R": 9, **dict(zip("STUVWXYZ", range(2, 10)))}
    weights = [8, 7, 6, 5, 4, 3, 2, 10, 0, 9, 8, 7, 6, 5, 4, 3, 2]
    total = sum(vin.str[i].map(value).fillna(0).astype(int) * w for i, w in enumerate(weights))
    return (total % 11).map(lambda r: "X" if r == 10 else str(r))


def integrity_calendar(rep, term, clm, feat, pay, reserves, inc, drv, ledger, contact) -> None:
    """Work done by staff, banks and courts falls on business days."""
    all_on = lambda *cols: all(business_day(c).all() for c in cols)
    reviews = reserves.loc[reserves["transaction_type"] != "Initial Reserve", "transaction_date"]
    rep.check("claim payments, file closes, reserve changes after the first, suits and fraud referrals fall on business days",
              all_on(pay["payment_date"], pay["cleared_date"], clm["close_date"], feat["close_date"], reviews, feat["suit_date"],
                     clm["siu_referral_date"]),
              f"{len(pay):,} payments; {1 - business_day(clm['report_date']).mean():.1%} of claims are reported on a weekend or holiday")
    mvr = inc[inc["source"] == "Motor Vehicle Record"]
    renewals = term[term["business_type"] == "Renewal"]
    keyed = ledger[ledger["transaction_type"] == "Endorsement"]
    rep.check("convictions, driving-record postings, SR-22 filings, renewal offers, keyed policy changes and letters fall on "
              "business days",
              all_on(mvr["conviction_date"], mvr["known_date"], drv["sr22_filed_date"], renewals["offer_date"], keyed["processed_date"],
                     contact.loc[contact["contact_method"] == "Written Letter", "contact_date"]))
    hh = clm["loss_time"].str.slice(0, 2).astype(int)
    rep.check("every loss has a time of day", clm["loss_time"].str.fullmatch(r"\d\d:\d\d").all() and hh.between(0, 23).all())


def integrity_identifiers(rep, pol, term, drv, veh, risk, clm, feat, quotes, vmy) -> None:
    """Business keys are well formed and unique; surrogate keys follow the order records were created in."""
    parts = pol["policy_number"].str.split("-", expand=True)
    digits = parts[0] + parts[1].map(lambda c: "".join(str(ord(ch) - 55) for ch in c)) + parts[2]
    rep.check("policy numbers are unique, carry the underwriting company's code and pass their check digits",
              pol["policy_number"].is_unique and pol["policy_number"].str.fullmatch(r"\d{7}-[A-Z]{3}-\d{2}").all()
              and digits.map(lambda x: int(x) % 97 == 1).all())
    pattern = vmy.set_index("vehicle_model_year_id")["vin_pattern"].reindex(veh["vehicle_model_year_id"]).to_numpy()
    vin = veh["vin"]
    rep.check("every VIN is unique, has 17 characters and a valid check digit, and follows its model year's pattern",
              vin.is_unique and (vin.str.len() == 17).all() and (vin.str[8] == vin_check_digit(vin)).all()
              and (vin.str[:8] == pd.Series(pattern).str[:8]).all() and (vin.str[9] == pd.Series(pattern).str[9]).all()
              and (veh["vin_prefix"] == pattern).all())
    number = clm.set_index("claim_id")["claim_number"].reindex(feat["claim_id"]).to_numpy()
    rep.check("claim, feature and quote numbers are unique; a feature's number extends its claim's",
              clm["claim_number"].is_unique and feat["feature_number"].is_unique and quotes["quote_number"].is_unique
              and (feat["feature_number"].str[:-3] == number).all()
              and (clm["claim_number"].str[:2].astype(int) == pd.to_datetime(clm["report_date"]).dt.year % 100).all())
    units = veh.groupby("policy_id")["unit_number"].agg(["min", "max", "nunique", "size"])
    dnum = drv.groupby("policy_id")["driver_number"].agg(["min", "max", "nunique", "size"])
    rep.check("vehicles and drivers are numbered 1, 2, 3... on each policy",
              all(((g["min"] == 1) & (g["max"] == g["size"]) & (g["nunique"] == g["size"])).all() for g in (units, dnum)))
    first = term.sort_values(["policy_id", "term_number"], kind="stable").groupby("policy_id").head(1).set_index("policy_id")
    f = first.reindex(pol["policy_id"])
    written = np.where(f["business_type"].to_numpy() == "New", f["offer_date"].to_numpy(), pol["original_inception_date"].to_numpy())
    in_order = lambda key, date: pd.Series(np.asarray(date)).iloc[np.argsort(np.asarray(key), kind="stable")].is_monotonic_increasing
    rep.check("record IDs follow the order records were created in (policies by the day written, terms by offer date, "
              "drivers and vehicles by the day added, exposure rows by rating date, claims by report date, features by open date)",
              in_order(pol["policy_id"], written) and in_order(term["policy_term_id"], term["offer_date"])
              and in_order(drv["driver_id"], drv["added_date"]) and in_order(veh["insured_vehicle_id"], veh["added_date"])
              and in_order(risk["exposure_id"], risk["rating_date"]) and in_order(clm["claim_id"], clm["report_date"])
              and in_order(feat["claim_feature_id"], feat["open_date"]))
    serial = pol.sort_values("policy_id")["policy_number"].str[:7].astype(int)
    rep.check("policy serial numbers rise with the day the policy was written", serial.is_monotonic_increasing,
              f"from {pol['policy_number'].min()} to {pol['policy_number'].max()}")


def integrity_billing(rep, inv, rec, term, ledger, pol, valuation) -> None:
    """Bills and cash: every finished term's bills reconcile with the premium ledger, and with the cash received."""
    dt = lambda x: pd.to_datetime(x)
    val = pd.Timestamp(valuation)
    t = term.set_index("policy_term_id")
    net = ledger.groupby("policy_term_id")["written_premium"].sum()
    kept = inv[inv["invoice_status"] != "Cancelled"].groupby("policy_term_id")["premium_amount"].sum()
    refund = -rec[rec["receipt_type"] == "Refund"].groupby("policy_term_id")["amount"].sum()
    end = dt(t["cancel_date"].fillna(t["expiration_date"]))
    done = t.index[end < val - pd.Timedelta(days=150)]
    gap = kept.reindex(done).fillna(0) - refund.reindex(done).fillna(0) - net.reindex(done).fillna(0)
    rep.check("for every finished term, premium billed (less cancelled bills) minus premium refunded equals the ledger's "
              "written, endorsement and return premium", (gap.abs() <= 0.02).all(),
              f"{len(done):,} terms, largest difference ${gap.abs().max():.2f}; {len(inv):,} bills, {len(rec):,} receipts")
    by_bill = rec[rec["invoice_id"].notna()].groupby("invoice_id")["amount"].sum()
    got = by_bill.reindex(inv["invoice_id"]).fillna(0).to_numpy()
    paid = (inv["invoice_status"] == "Paid").to_numpy()
    rep.check("cash received on a paid bill equals its amount due, and nets to zero on any other bill",
              np.allclose(got[paid], inv["amount_due"].to_numpy()[paid], atol=0.011) and np.allclose(got[~paid], 0, atol=0.011)
              and np.allclose(inv["premium_amount"] + inv["installment_fee"] + inv["late_fee"], inv["amount_due"], atol=0.011))
    rep.check("bills are dated in order and by the valuation date; only a paid bill has a paid date; only a balance billed "
              "after cancellation is written off",
              (dt(inv["issue_date"]) <= val).all() and (dt(rec["receipt_date"]) <= val).all()
              and (inv.loc[paid, "paid_date"] >= inv.loc[paid, "issue_date"]).all() and (inv["paid_date"].notna() == paid).all()
              and (inv.loc[inv["invoice_status"] == "Written Off", "invoice_type"] == "Final Balance").all()
              and (inv["write_off_date"].notna() == (inv["invoice_status"] == "Written Off")).all(),
              f"{inv['invoice_status'].value_counts().to_dict()}")
    plan = pol.set_index("policy_id")["payment_plan"].reindex(inv["policy_id"]).to_numpy()
    regular = inv["installment_number"].notna()
    months = pol.set_index("policy_id")["term_months"].reindex(inv["policy_id"]).to_numpy()
    rep.check("a paid-in-full term has one bill and a monthly term one instalment a month",
              (inv.loc[regular & (plan == "Paid in Full"), "installment_number"] == 1).all()
              and (inv.loc[regular, "installment_number"] <= months[regular]).all()
              and not inv[regular].duplicated(["policy_term_id", "installment_number"]).any())
    # a cancellation for non-payment follows an instalment that was never paid
    np_terms = term[term["cancel_reason"] == "Non-Payment"]
    missed = inv[(inv["invoice_status"] == "Cancelled") & (inv["invoice_type"] == "Installment")].groupby("policy_term_id")["due_date"].min()
    lag = (dt(np_terms["cancel_date"]) - dt(missed.reindex(np_terms["policy_term_id"]).to_numpy())).dt.days
    # (rarely the instalment that would have been missed was reduced to nothing by a return premium, and no bill exists)
    rep.check("cancellations for non-payment follow an unpaid instalment by three to four weeks",
              lag.between(21, 28).mean() > 0.98,
              f"{len(np_terms):,} cancellations; median {lag.median():.0f} days after the missed due date; "
              f"{(~lag.between(21, 28)).sum():,} without a matching unpaid bill")


def integrity_payments(rep, pay, clm, feat, emp, vend, ledger, agency, pol, term) -> None:
    """Claim payment detail (payee, cheque numbers, approval) and commissions."""
    dt = lambda x: pd.to_datetime(x)
    cut = pay[pay["check_number"].notna() & (pay["transaction_type"] != "Void")]
    numbers = cut["check_number"].astype(int).sort_values()
    void = pay[pay["transaction_type"] == "Void"].merge(cut[["check_number", "amount", "payment_status", "claim_feature_id"]],
                                                         on="check_number", suffixes=("", "_cheque"))
    rep.check("cheque numbers run in one unbroken sequence in the order cheques were cut; a void carries the number and "
              "amount of the cheque it cancels",
              numbers.is_unique and (numbers.diff().dropna() == 1).all() and cut["check_number"].is_monotonic_increasing
              and len(void) == (pay["transaction_type"] == "Void").sum() and np.allclose(void["amount"], -void["amount_cheque"])
              and (void["payment_status_cheque"] == "Voided").all() and (void["claim_feature_id"] == void["claim_feature_id_cheque"]).all()
              and (pay.loc[pay["payment_method"] != "Check", "check_number"].isna()).all(),
              f"{len(cut):,} cheques from {numbers.min()} to {numbers.max()}; {pay['payment_method'].value_counts().to_dict()}")
    e = emp.set_index("employee_id")
    who = e.reindex(pay["approved_by_employee_id"])
    on = dt(pay["payment_date"]).to_numpy()
    employed = (dt(who["hire_date"]).to_numpy() <= on) & (who["termination_date"].isna().to_numpy() | (on < dt(who["termination_date"]).to_numpy()))
    rep.check("every payment is approved by someone employed that day and within their payment authority",
              employed.all() and (pay["amount"].abs().to_numpy() <= who["payment_authority"].to_numpy()).all(),
              f"approved by {who['job_title'].value_counts().to_dict()}")
    adj = e.reindex(clm["adjuster_id"])
    rep.check("every claim has an adjuster, from its own office unless the desk is being covered",
              adj["job_title"].notna().all() and ((adj["claim_office_id"].to_numpy() == clm["claim_office_id"].to_numpy())
                                                  | (adj["job_title"].to_numpy() == "Claims Manager")).all())
    kind = vend.set_index("vendor_id")["vendor_type"].reindex(pay["vendor_id"]).to_numpy()
    org = pay["payee_type"].isin(["Vendor", "Lienholder", "Other Insurer", "Claimant and Attorney"]).to_numpy()
    rep.check("a payment to an organisation names a vendor of the right kind; a payment to a person names none",
              (pay["vendor_id"].notna().to_numpy() == org).all() and pay["payee_name"].notna().all()
              and (kind[(pay["payee_type"] == "Lienholder").to_numpy()] == "Lienholder").all()
              and (kind[(pay["payee_type"] == "Other Insurer").to_numpy()] == "Other Insurer").all()
              and (kind[(pay["payee_type"] == "Claimant and Attorney").to_numpy()] == "Plaintiff Law Firm").all(),
              f"{pay['payee_type'].value_counts().to_dict()}")
    cleared = pay["payment_status"] == "Cleared"
    rep.check("a cleared payment cleared on or after the day it was issued; outstanding and voided ones have no cleared date",
              (pay.loc[cleared, "cleared_date"] >= pay.loc[cleared, "payment_date"]).all()
              and pay.loc[pay["payment_status"].isin(["Outstanding", "Voided"]), "cleared_date"].isna().all(),
              f"{pay['payment_status'].value_counts().to_dict()}")
    a = agency.set_index("agency_id").reindex(pol.set_index("policy_id")["agency_id"].reindex(ledger["policy_id"]).to_numpy())
    new = term.set_index("policy_term_id")["business_type"].reindex(ledger["policy_term_id"]).to_numpy() == "New"
    rate = np.where(new, a["new_business_commission_pct"].to_numpy(), a["renewal_commission_pct"].to_numpy())
    rep.check("commission is the agency's new-business or renewal rate on each transaction's written premium; direct "
              "business pays none",
              np.allclose(ledger["commission_rate_pct"], rate) and np.allclose(ledger["commission_amount"], ledger["written_premium"] * rate / 100, atol=0.006)
              and (rate[(a["channel"] == "Direct").to_numpy()] == 0).all(),
              f"${ledger['commission_amount'].sum():,.0f} commission on ${ledger['written_premium'].sum():,.0f} written premium")


def integrity_vehicles(rep, vmy, veh, risk, clm) -> None:
    """The make, model and model-year catalogue and the vehicles that point to it."""
    rep.check("each make, model and model year appears once in the vehicle catalogue",
              not vmy.duplicated(["make", "model", "model_year"]).any() and vmy["vehicle_model_year_id"].is_unique,
              f"{len(vmy):,} model years of {vmy.groupby(['make', 'model']).ngroups:,} models from {vmy['make'].nunique()} makes")
    known = vmy.set_index("vehicle_model_year_id")
    rep.check("insured vehicles, exposure rows and claims point to catalogue rows",
              veh["vehicle_model_year_id"].isin(known.index).all() and risk["vehicle_model_year_id"].isin(known.index).all()
              and clm["vehicle_model_year_id"].isin(known.index).all())
    rep.check("each exposure row's model year is its catalogue row's",
              (known["model_year"].reindex(risk["vehicle_model_year_id"]).to_numpy() == risk["model_year"].to_numpy()).all())
    drawn = vmy[vmy["vehicle_model_year_id"].isin(veh["vehicle_model_year_id"])]
    print(f"  {drawn.groupby(['make', 'model']).ngroups:,} models from {drawn['make'].nunique()} makes are insured; "
          f"top makes {veh.merge(vmy, on='vehicle_model_year_id')['make'].value_counts(normalize=True).head(6).round(3).to_dict()}")


def integrity_telematics(rep, enrol, scores, risk, term, valuation, pol=None, veh=None, drv=None) -> None:
    """The telematics programme: enrolments, scores and the discounts rated on each exposure row."""
    dt = lambda x: pd.to_datetime(x)
    e = enrol.set_index("enrollment_id")
    if pol is not None:
        inception = dt(pol.set_index("policy_id")["original_inception_date"])
        added_v = dt(veh.set_index("insured_vehicle_id")["added_date"]).reindex(scores["insured_vehicle_id"]).to_numpy()
        added_d = dt(drv.set_index("driver_id")["added_date"]).reindex(scores["driver_id"]).to_numpy()
        start = dt(scores["period_start_date"]).to_numpy()
        rep.check("a policy joins the programme after it was written, and a car is scored only while it and its "
                  "driver are on the policy",
                  (dt(enrol["enrollment_date"]).to_numpy() >= inception.reindex(enrol["policy_id"]).to_numpy()).all()
                  and (start >= added_v).all() and (start >= added_d).all())
    rep.check("enrolments end after they start and by the valuation date",
              (e["end_date"].isna() | (dt(e["end_date"]) >= dt(e["enrollment_date"]))).all()
              and (dt(e["enrollment_date"]) <= valuation).all() and (dt(e["end_date"]).dropna() <= valuation).all(),
              f"{len(enrol):,} enrolments; {enrol['device_type'].value_counts().to_dict()}; ended {enrol['end_reason'].value_counts().to_dict()}")
    s_ = scores
    within = (dt(s_["period_start_date"]) >= dt(e["enrollment_date"]).reindex(s_["enrollment_id"]).to_numpy()) \
        & (dt(s_["period_end_date"]) <= dt(e["end_date"]).reindex(s_["enrollment_id"]).fillna(pd.Timestamp.max).to_numpy())
    rule = np.round(np.clip((s_["driving_score"] - 45) / 50, 0, 1) * 30)
    scored = s_["driving_score"].notna()
    rep.check("scores fall inside their enrolment, cover their stated days, and earn the published discount",
              within.all() and ((dt(s_["period_end_date"]) - dt(s_["period_start_date"])).dt.days == s_["days_monitored"]).all()
              and s_.loc[scored, "driving_score"].between(1, 100).all()
              and ((s_.loc[scored, "earned_discount_pct"] == rule[scored]) | (s_.loc[scored, "earned_discount_pct"] == 0)).all(),
              f"{len(s_):,} scores, mean {s_['driving_score'].mean():.1f}, average earned discount {s_['earned_discount_pct'].mean():.1f}%")
    # a score is one driver's driving of one car: the driver is the car's rated driver (exposure rows) on every day
    # scored, and a period before the car's first exposure row is its first row's driver (the opening assignment)
    x = s_[["score_id", "insured_vehicle_id", "driver_id", "period_start_date", "period_end_date"]].merge(
        risk[["insured_vehicle_id", "driver_id", "coverage_start_date", "coverage_end_date"]], on="insured_vehicle_id",
        suffixes=("", "_rated"))
    x = x[(x["period_start_date"] < x["coverage_end_date"]) & (x["period_end_date"] > x["coverage_start_date"])]
    other = x.loc[x["driver_id"] != x["driver_id_rated"], "score_id"].nunique()
    nxt = s_[["enrollment_id", "insured_vehicle_id", "period_start_date", "driver_id"]].merge(
        s_[["enrollment_id", "insured_vehicle_id", "period_end_date", "driver_id"]], left_on=["enrollment_id", "insured_vehicle_id", "period_start_date"],
        right_on=["enrollment_id", "insured_vehicle_id", "period_end_date"], suffixes=("", "_before"))
    split = int((nxt["driver_id"] != nxt["driver_id_before"]).sum())
    first = risk.sort_values(["insured_vehicle_id", "coverage_start_date"], kind="stable").groupby("insured_vehicle_id").head(1)
    first = first.set_index("insured_vehicle_id")
    before = s_["period_end_date"].to_numpy() <= first["coverage_start_date"].reindex(s_["insured_vehicle_id"]).to_numpy()
    opening = s_[before]
    rep.check("each score is the driving of the driver assigned to the car on the days scored (by the exposure rows; "
              "the opening assignment before the car's first row)",
              other == 0 and (opening["driver_id"].to_numpy()
                              == first["driver_id"].reindex(opening["insured_vehicle_id"]).to_numpy()).all()
              and s_.loc[~before, "score_id"].isin(x["score_id"]).all(),
              f"{other:,} scores overlap another driver's exposure; {before.sum():,} scores before the car's first exposure row; "
              f"{split:,} scoring periods split where the car's driver changed")
    # the discount a car is rated with at the start of a term is the days-weighted average of the discounts its scores
    # applied to that term earned (rounded half up), or the participation discount if none of them was scored
    ap = s_[s_["applied_to_policy_term_id"].notna() & s_["driving_score"].notna()]
    g = ap.assign(w=ap["days_monitored"] * ap["earned_discount_pct"]).groupby(
        ["applied_to_policy_term_id", "insured_vehicle_id"])[["w", "days_monitored"]].sum()
    rule_pct = np.floor((2 * g["w"] + g["days_monitored"]) / (2 * g["days_monitored"]))
    applied = term.set_index("policy_term_id").reindex(s_["applied_to_policy_term_id"].dropna().astype(int))
    rep.check("a score's discount applies to a later term of the same policy, starting on or after the period scored",
              (applied["effective_date"].to_numpy() >= s_.loc[s_["applied_to_policy_term_id"].notna(), "period_end_date"].to_numpy()).all()
              and (applied["policy_id"].to_numpy() == s_.loc[s_["applied_to_policy_term_id"].notna(), "policy_id"].to_numpy()).all())
    first_rows = risk[(risk["endorsement_number"] == 0) & (risk["telematics_enrolled"] == "Y")]
    want = rule_pct.reindex(pd.MultiIndex.from_arrays([first_rows["policy_term_id"], first_rows["insured_vehicle_id"]])).fillna(5)
    rep.check("each enrolled car starts a term on the days-weighted discount its scores for that term earned, or 5% if "
              "none was scored", (first_rows["telematics_discount_pct"].to_numpy() == want.to_numpy()).all(),
              f"{len(first_rows):,} enrolled car-terms")
    on = risk[risk["telematics_enrolled"] == "Y"].merge(term[["policy_term_id", "offer_date"]], on="policy_term_id")
    j = on[["exposure_id", "policy_id", "coverage_start_date", "offer_date"]].merge(
        enrol[["policy_id", "enrollment_date", "end_date"]], on="policy_id")
    ok = (dt(j["enrollment_date"]) <= dt(j["coverage_start_date"])) \
        & (j["end_date"].isna() | (dt(j["end_date"]) >= dt(j["offer_date"])))
    rep.check("rows rated in the programme belong to an enrolment that began by the row's start and was live when its term "
              "was offered; other rows carry no telematics discount",
              on["exposure_id"].isin(j.loc[ok, "exposure_id"]).all() and (risk.loc[risk["telematics_enrolled"] == "N", "telematics_discount_pct"] == 0).all()
              and risk["telematics_discount_pct"].between(0, 30).all())


def integrity_renewals(rep, offers, term, risk, valuation) -> None:
    """Renewal offers: each is dated inside its expiring term and made from the policy as it stood on the offer date
    (the expiring term's exposure rows in force that day), and its outcome agrees with the policy terms."""
    o = offers
    t = term.set_index("policy_term_id")
    exp = t.reindex(o["expiring_policy_term_id"])
    val = str(pd.Timestamp(valuation).date())
    rep.check("each renewal offer is made during its expiring term, by the valuation date, for the term that follows",
              (exp["policy_id"].to_numpy() == o["policy_id"].to_numpy()).all()
              and (o["offer_date"].to_numpy() >= exp["effective_date"].to_numpy()).all()
              and (o["offer_date"] < o["renewal_effective_date"]).all() and (o["offer_date"] <= val).all()
              and (exp["expiration_date"].to_numpy() == o["renewal_effective_date"].to_numpy()).all()
              and not o["expiring_policy_term_id"].duplicated().any(),
              f"{len(o):,} offers: {o['outcome'].value_counts().to_dict()}")
    # the snapshot: the vehicles and the premium in force on the offer date
    r = risk[["policy_term_id", "coverage_start_date", "coverage_end_date", "total_premium"]].merge(
        o[["renewal_offer_id", "expiring_policy_term_id", "offer_date"]], left_on="policy_term_id",
        right_on="expiring_policy_term_id")
    r = r[(r["coverage_start_date"] <= r["offer_date"]) & (r["coverage_end_date"] > r["offer_date"])]
    g = r.groupby("renewal_offer_id").agg(n=("total_premium", "size"), prem=("total_premium", "sum")).reindex(o["renewal_offer_id"]).fillna(0)
    rep.check("each offer covers the vehicles in force on its offer date, at the premium they were then insured for",
              (g["n"].to_numpy() == o["vehicles_offered"].to_numpy()).all()
              and np.allclose(g["prem"].to_numpy(), o["expiring_premium"].to_numpy(), atol=0.05),
              f"{(o['vehicles_offered'] == 0).sum():,} offers with no vehicle on the policy that day (a replacement to come)")
    has = o["expiring_premium"] > 0
    pct = np.round((o.loc[has, "renewal_premium"] / o.loc[has, "expiring_premium"] - 1) * 100, 1)
    rep.check("the premium change is the renewal premium against the expiring premium",
              (np.abs(pct - o.loc[has, "premium_change_pct"]) <= 0.11).all() and o.loc[~has, "premium_change_pct"].isna().all())
    # outcomes
    ren = o[o["outcome"] == "Renewed"]
    new = t.reindex(ren["renewal_policy_term_id"].astype(int))
    # (a term already running on the start date was renewed before the extract: its offer is not in it)
    later = term["term_number"] > term.groupby("policy_id")["term_number"].transform("min")
    renewals = term.loc[(term["business_type"] == "Renewal") & later, "policy_term_id"]
    revised = np.where(new["rating_date"] > new["offer_date"], new["rating_date"], "")
    rep.check("every renewal term after the first in the data is a renewed offer, with the offer's date, and its revised "
              "offer date if re-rated",
              set(ren["renewal_policy_term_id"].astype(int)) == set(renewals) and len(ren) == len(renewals)
              and (new["offer_date"].to_numpy() == ren["offer_date"].to_numpy()).all()
              and (new["effective_date"].to_numpy() == ren["renewal_effective_date"].to_numpy()).all()
              and (ren["revised_offer_date"].fillna("").to_numpy() == revised).all()
              and o.loc[o["outcome"] != "Renewed", "renewal_policy_term_id"].isna().all(),
              f"{ren['revised_offer_date'].notna().sum():,} renewals revised after a household change")
    nr = o[o["outcome"].isin(["Company Non-Renewal", "Insured Did Not Renew"])]
    nr_terms = term[term["nonrenewal_reason"].notna()]
    rep.check("every non-renewed term has one offer whose outcome is its non-renewal reason",
              t["nonrenewal_reason"].reindex(nr["expiring_policy_term_id"]).tolist() == nr["outcome"].tolist()
              and set(nr["expiring_policy_term_id"]) == set(nr_terms["policy_term_id"]))
    cx = exp["cancel_date"].notna().to_numpy()
    rep.check("an offer ends 'Cancelled Before Renewal' exactly when its expiring term was cancelled after the offer date",
              ((o["outcome"] == "Cancelled Before Renewal").to_numpy() == cx).all()
              and (exp.loc[cx, "cancel_date"].to_numpy() > o.loc[cx, "offer_date"].to_numpy()).all())
    pending = o["outcome"] == "Pending"
    company = o["underwriting_decision"] == "Non-Renew"
    rep.check("a renewal is pending only when it takes effect after the valuation date; a company non-renewal is never "
              "sent a telematics offer or a revision",
              (o.loc[pending, "renewal_effective_date"] > val).all() and (ren["renewal_effective_date"] <= val).all()
              and (company == (o["outcome"] == "Company Non-Renewal") | (company & (o["outcome"] == "Cancelled Before Renewal"))).all()
              and o.loc[company, "telematics_opt_in"].isna().all() and o.loc[company, "revised_offer_date"].isna().all(),
              f"{pending.sum():,} pending; telematics opt-in {o['telematics_opt_in'].value_counts().to_dict()}")


def integrity_limits(rep, f) -> None:
    """Every coverage's payments against the terms on the risk row the claim arose under. `f` is the
    coverage features joined to their claim's risk row. Amounts are compared to the cent."""
    cent = 0.005
    paid, code, claim = f["paid_loss"], f["coverage_code"], f["claim_id"]
    split = lambda col, i: f[col].str.split("/").str[i].astype(float) * 1000
    by_accident = lambda m, x: x[m].groupby(claim[m]).sum()
    first = lambda m, x: x[m].groupby(claim[m]).first()
    bi, um, uim = code == "BI", code == "UM", f["um_uim_type"] == "Underinsured"
    rep.check("bodily injury payments stay within the per-person and per-accident limits",
              (paid[bi] <= split("bi_limit", 0)[bi] + cent).all()
              and (by_accident(bi, paid) <= first(bi, split("bi_limit", 1)) + cent).all(),
              f"{(by_accident(bi, paid) >= first(bi, split('bi_limit', 1)) - cent).sum():,} accidents paid the per-accident limit in full")
    rep.check("property damage and medical payments stay within their limits",
              (paid[code == "PD"] <= f.loc[code == "PD", "pd_limit"] + cent).all()
              and (paid[code == "MED"] <= f.loc[code == "MED", "med_pay_limit"] + cent).all())
    offset = f["other_insurer_payment"].fillna(0)
    rep.check("uninsured and underinsured motorist payments stay within the per-person and per-accident limits, "
              "less what the at-fault driver's insurer paid",
              (paid[um] <= split("um_limit", 0)[um] - offset[um] + cent).all()
              and (by_accident(um, paid) <= first(um, split("um_limit", 1)) - by_accident(um, offset) + cent).all()
              and (um == f["um_uim_type"].notna()).all() and (f["other_insurer_payment"].notna() == uim).all(),
              f"{(um & ~uim).sum():,} uninsured and {uim.sum():,} underinsured motorist features")
    # a vehicle is worth at most its value on the risk row (rounded to $10), and the deductible comes off
    value = f["vehicle_value"] + 5
    glass_free = (f["cause_of_loss"] == "GLASS") & (f["full_glass_coverage"] == "Y")
    comp_ded = np.where(glass_free, 0, f["comprehensive_deductible"])
    rep.check("collision and comprehensive payments stay within the vehicle's value less the deductible",
              (paid[code == "COLL"] <= (value - f["collision_deductible"]).clip(lower=0)[code == "COLL"]).all()
              and (paid[code == "COMP"] <= (value - comp_ded).clip(lower=0)[code == "COMP"]).all())
    rent = code == "RENT"
    rep.check("rental and towing payments stay within the per-claim maximum",
              (paid[rent] <= f.loc[rent, "rental_reimbursement"].str.split("/").str[1].astype(float) + cent).all()
              and (paid[code == "TOW"] <= TOWING_LIMIT + cent).all())
    # case reserves too: an adjuster reserves within the limits, so paid plus case reserve obeys every limit above
    inc = f["paid_loss"] + f["case_reserve"]
    lim = pd.Series(np.inf, index=f.index)
    lim[bi] = split("bi_limit", 0)[bi]
    lim[um] = split("um_limit", 0)[um] - offset[um]
    lim[code == "PD"], lim[code == "MED"] = f.loc[code == "PD", "pd_limit"], f.loc[code == "MED", "med_pay_limit"]
    lim[code == "COLL"] = (value - f["collision_deductible"]).clip(lower=0)[code == "COLL"]
    lim[code == "COMP"] = pd.Series((value - comp_ded).clip(lower=0), index=f.index)[code == "COMP"]
    lim[rent] = f.loc[rent, "rental_reimbursement"].str.split("/").str[1].astype(float)
    lim[code == "TOW"] = TOWING_LIMIT
    rep.check("paid loss plus case reserve stays within every per-person, per-accident and per-claim limit",
              (inc <= lim + cent).all() and (by_accident(bi, inc) <= first(bi, split("bi_limit", 1)) + cent).all()
              and (by_accident(um, inc) <= first(um, split("um_limit", 1)) - by_accident(um, offset) + cent).all(),
              f"{(f['case_reserve'] > 0).sum():,} features with a case reserve")
    on = lambda k, col: (f.loc[code == k, col] > 0).all()
    rep.check("the coverage terms on each risk row agree with its premiums",
              ((f["rental_premium"] > 0) == f["rental_reimbursement"].notna()).all()
              and ((f["towing_premium"] > 0) == (f["towing_and_labor"] == "Y")).all()
              and on("COLL", "collision_deductible") and on("COMP", "comprehensive_deductible"))


def integrity_lifecycle(rep, risk, term, pol, veh, drv, clm, feat, pay, inc, r_start, r_end, valuation) -> None:
    """Checks on vehicle lifecycles, information timing, policy dates, premium and payments."""
    dt = lambda x: pd.to_datetime(x)
    valuation = pd.Timestamp(valuation)
    v = veh.set_index("insured_vehicle_id")
    added, removed = dt(v["added_date"]), dt(v["removed_date"])

    # vehicles: cover, claims and total losses
    rv = risk["insured_vehicle_id"]
    cov_s, cov_e = dt(risk["coverage_start_date"]), dt(risk["coverage_end_date"])
    rep.check("no cover before a vehicle was added or after it was removed",
              (cov_s >= added.reindex(rv).to_numpy()).all() and (cov_e <= removed.reindex(rv).fillna(pd.Timestamp.max).to_numpy()).all())
    loss = dt(clm["loss_date"])
    vid = clm["insured_vehicle_id"]
    rep.check("no loss on a vehicle before it was added or on or after it was removed",
              (loss >= added.reindex(vid).to_numpy()).all() and (loss < removed.reindex(vid).fillna(pd.Timestamp.max).to_numpy()).all())
    o = pd.DataFrame({"v": rv, "s": r_start, "e": r_end}).sort_values(["v", "s"], kind="stable")
    prev_end = o.groupby("v").e.shift()
    rep.check("a vehicle's earned exposure is never counted twice", (prev_end.isna() | (o.s >= prev_end)).all())
    tl = feat[(feat["total_loss"] == "Y") & (feat["owner_retained_salvage"] == "N")]
    tl = tl.merge(clm[["claim_id", "insured_vehicle_id", "loss_date"]], on="claim_id").groupby("insured_vehicle_id")["loss_date"].min()
    gone = dt(tl) + pd.Timedelta(days=1)
    known = gone <= valuation                       # a loss on the valuation date takes the car off the day after
    rep.check("every total loss the company takes the wreck from ends the vehicle's cover the day after the loss",
              (removed.reindex(tl.index)[known] == gone[known]).all() and removed.reindex(tl.index)[~known].isna().all()
              and (v["removal_reason"].reindex(tl.index)[known] == "Total Loss").all(),
              f"{len(tl):,} vehicles; {(feat['owner_retained_salvage'] == 'Y').sum():,} owner-retained; "
              f"{(veh['removal_reason'] == 'Destroyed or Stolen').sum():,} destroyed or stolen without a company total loss")
    rp = veh.dropna(subset=["replaces_insured_vehicle_id"])
    old = v.reindex(rp["replaces_insured_vehicle_id"].astype(int))
    rep.check("replacement vehicles follow the vehicle they replace on the same policy",
              (old["policy_id"].to_numpy() == rp["policy_id"].to_numpy()).all()
              and (dt(old["removed_date"]).to_numpy() <= dt(rp["added_date"]).to_numpy()).all(),
              f"{len(rp):,} replacements, {(old['removal_reason'] == 'Total Loss').sum():,} after a total loss")
    rep.check("nothing is dated after the valuation date",
              all((dt(t_[c]).dropna() <= valuation).all() for t_, c in
                  ((veh, "added_date"), (veh, "removed_date"), (drv, "added_date"), (drv, "removed_date"), (clm, "report_date"),
                   (feat, "open_date"), (feat, "close_date"), (feat, "suit_date"), (feat, "attorney_date"),
                   (pay, "payment_date"), (inc, "known_date"), (term, "cancel_date"), (risk, "coverage_start_date"))))

    # the policy as it stands: on the valuation date if in force, else on its last day of cover
    as_at = np.where(pol["policy_status"] == "In Force", valuation, dt(pol["latest_expiration_date"]) - pd.Timedelta(days=1))
    as_at = pd.Series(np.minimum(as_at, valuation.to_datetime64()), index=pol["policy_id"].to_numpy())
    day = as_at.reindex(risk["policy_id"]).to_numpy()
    covered = risk[(cov_s.to_numpy() <= day) & (cov_e.to_numpy() > day)].groupby("policy_id")["insured_vehicle_id"].nunique()
    day = as_at.reindex(veh["policy_id"]).to_numpy()
    listed = veh[(dt(veh["added_date"]).to_numpy() <= day) & ~(dt(veh["removed_date"]).to_numpy() <= day)].groupby("policy_id").size()
    day = as_at.reindex(drv["policy_id"]).to_numpy()
    drivers = drv[(dt(drv["added_date"]).to_numpy() <= day) & ~(dt(drv["removed_date"]).to_numpy() <= day)].groupby("policy_id").size()
    count = lambda g: g.reindex(pol["policy_id"]).fillna(0).to_numpy()
    in_force = (pol["policy_status"] == "In Force").to_numpy()
    rep.check("each policy's vehicle count is the vehicles covered at its latest status (risk rows and vehicle dates agree)",
              (pol["number_of_vehicles"].to_numpy() == count(covered)).all() and (count(covered) == count(listed)).all(),
              f"{pol['number_of_vehicles'][in_force].sum():,} vehicles on {in_force.sum():,} policies in force, "
              f"{(pol['number_of_vehicles'][in_force] == 0).sum():,} of them waiting for a replacement car")
    rep.check("each policy's driver count is the drivers on it at its latest status",
              (pol["number_of_drivers"].to_numpy() == count(drivers)).all())
    at_start = cov_s.to_numpy() == dt(term.set_index("policy_term_id")["effective_date"]).reindex(risk["policy_term_id"]).to_numpy()
    opening = risk[at_start].groupby("policy_term_id").size().reindex(term["policy_term_id"]).fillna(0).to_numpy()
    rep.check("each term's opening vehicle count is its risk rows at the term start (endorsement 0)",
              (term["vehicles_at_term_start"].to_numpy() == opening).all() and ((risk["endorsement_number"] == 0) == at_start).all())

    # information timing: every rated record is exactly the incidents with a known date on or before the
    # row's rating date (the term's rating date, before it takes effect, or the day of a mid-term change),
    # dated in the three years up to the row's cover start. Dates carry no time of day, so the order of
    # events on one day is fixed by convention: a known date of D means usable by any rating dated D or
    # later, and the company's own claim is known the day after the payment that makes it chargeable, so a
    # loss or payment on the rating date itself is never part of that rating.
    t = term.set_index("policy_term_id")
    eff, rdate = dt(t["effective_date"]), dt(t["rating_date"])
    rep.check("every term is offered, then rated, before it takes effect", (dt(t["offer_date"]) <= rdate).all()
              and (rdate <= eff).all() and (dt(risk["rating_date"]) <= cov_s).all(),
              f"{(dt(t['offer_date']) < rdate).sum():,} renewals re-rated after a change between offer and effective date")
    # a renewal or endorsement is rated with the household as it stood that day: its car and rated driver are
    # already on the policy, and its address is the one in force (new business is quoted before its first day)
    later = (risk["endorsement_number"] > 0) | (t["business_type"].reindex(risk["policy_term_id"]).to_numpy() == "Renewal")
    r_ = risk[later]
    rated = dt(r_["rating_date"]).to_numpy()
    on_v = (dt(v["added_date"]).reindex(r_["insured_vehicle_id"]).to_numpy() <= rated)
    on_d = (dt(drv.set_index("driver_id")["added_date"]).reindex(r_["driver_id"]).to_numpy() <= rated)
    cover = risk[["policy_id", "location_id"]].assign(s=cov_s.to_numpy(), e=cov_e.to_numpy())
    x = r_[["exposure_id", "policy_id", "location_id"]].assign(d=rated).merge(cover, on="policy_id", suffixes=("", "_then"))
    x = x[(x.s.to_numpy() <= x.d.to_numpy()) & (x.e.to_numpy() > x.d.to_numpy())]
    moved = (x.location_id != x.location_id_then).groupby(x.exposure_id).all()
    rep.check("renewals and changes are rated with the car, driver and address on the policy on the rating date",
              on_v.all() and on_d.all() and not moved.any(), f"{len(r_):,} rows; {len(x.exposure_id.unique()):,} had cover on their rating date")
    i = inc.assign(d=dt(inc["incident_date"]), k=dt(inc["known_date"]))
    j = risk[["exposure_id", "driver_id", "coverage_start_date", "rating_date"]].merge(
        i[["driver_id", "d", "k", "incident_type"]], on="driver_id")
    je, jr = dt(j["coverage_start_date"]).to_numpy(), dt(j["rating_date"]).to_numpy()
    j = j[(j.d.to_numpy() <= je) & (j.d.to_numpy() > je - np.timedelta64(3 * 365, "D")) & (j.k.to_numpy() <= jr)]
    pts = j["incident_type"].map({"Minor Violation": 1, "Major Violation": 3}).fillna(0).groupby(j["exposure_id"]).sum()
    acc = (j["incident_type"] == "At-Fault Accident").groupby(j["exposure_id"]).sum()
    rep.check("rated violations and accidents are those known on the rating date",
              (risk["exposure_id"].map(pts).fillna(0) == risk["rated_violation_points"]).all()
              and (risk["exposure_id"].map(acc).fillna(0) == risk["rated_at_fault_accidents"]).all())
    rep.check("an incident is known only after it happened", (i.k >= i.d).all())
    cv = i[i["conviction_date"].notna()]
    rep.check("a conviction falls after the violation and on or before it reaches the driving record",
              ((dt(cv["conviction_date"]) > cv.d) & (dt(cv["conviction_date"]) <= cv.k)).all(), f"{len(cv):,} convictions")
    s22 = drv[drv["sr22_filed_date"].notna()]
    rep.check("an SR-22 is filed before it ends, and only after the driver joined the policy",
              ((dt(s22["sr22_filed_date"]) < dt(s22["sr22_end_date"]))
               & (dt(s22["sr22_filed_date"]) >= dt(s22["added_date"]))).all(), f"{len(s22):,} filings")
    own = i[i["source"] == "Company Claim"]
    rep.check("the company's own claims reach the driving record after the loss date, never on it", (own.k > own.d).all(),
              f"{len(own):,} chargeable company claims")
    rep.check("no good-student discount at 25 or older", not ((risk["rated_good_student"] == "Y") & (risk["rated_driver_age"] >= 25)).any())

    # drivers: rated and claiming drivers were on the policy at the time
    d = drv.set_index("driver_id")
    d_add, d_rem = dt(d["added_date"]), dt(d["removed_date"]).fillna(pd.Timestamp.max)
    rep.check("each risk row's driver was on the policy throughout the row",
              (d_add.reindex(risk["driver_id"]).to_numpy() <= cov_s.to_numpy()).all()
              and (d_rem.reindex(risk["driver_id"]).to_numpy() >= np.minimum(cov_e, pd.Timestamp(r_end.max())).to_numpy()).all())
    af = clm[clm["at_fault"] == "Y"]
    rep.check("drivers in at-fault claims were on the policy on the loss date",
              (d_add.reindex(af["involved_driver_id"]).to_numpy() <= dt(af["loss_date"]).to_numpy()).all()
              and (d_rem.reindex(af["involved_driver_id"]).to_numpy() > dt(af["loss_date"]).to_numpy()).all(),
              f"{drv['removed_date'].notna().sum():,} drivers left a policy; "
              f"{(risk['endorsement_number'] > 0).sum():,} risk rows start at a mid-term change")

    # policy dates: terms chain without gaps, on anniversaries of the original inception day
    tt = term.merge(pol[["policy_id", "original_inception_date"]], on="policy_id")
    es, inc_day = dt(tt["effective_date"]), dt(tt["original_inception_date"]).dt.day
    tt = tt.assign(es=es).sort_values(["policy_id", "es"], kind="stable")
    nxt = tt.groupby("policy_id")["effective_date"].shift(-1)
    rep.check("each term starts on the anniversary day (month-end days kept, no drift) and follows the last",
              (es.dt.day == np.minimum(inc_day, es.dt.days_in_month)).all()
              and (nxt.isna() | (nxt == tt["expiration_date"])).all(),
              f"{(es.dt.day >= 29).mean():.1%} of terms start on the 29th to 31st")

    # premium: written + endorsements + returns = earned before the extract + earned in it, for finished terms
    done = term["cancel_date"].notna() | (dt(term["expiration_date"]) <= valuation)
    gap = (term["written_premium"] + term["endorsement_premium"] + term["return_premium"]
           - term["earned_premium_before_extract"] - term["earned_premium"])[done]
    rep.check("finished terms' written, endorsement and return premium equal their earned premium",
              (gap.abs() <= 0.01 * term["vehicles_at_term_start"][done] + 0.05).all(), f"largest difference ${gap.abs().max():.2f}")

    # payments
    f = feat.set_index("claim_feature_id")
    pd_ = dt(pay["payment_date"])
    rep.check("no payment before its feature opened", (pd_ >= dt(f["open_date"]).reindex(pay["claim_feature_id"]).to_numpy()).all())
    lp = pay[pay["payment_type"] == "Loss"]
    closed = f["feature_status"] == "Closed"
    last = dt(lp.groupby("claim_feature_id")["payment_date"].max()).reindex(f.index[closed])
    rep.check("closed features have no loss payment after their close date", (last.isna() | (last <= dt(f.loc[closed, "close_date"]))).all())
    n = lp.groupby("claim_feature_id").size()
    print(f"  loss payments per paid feature: {n.value_counts().sort_index().to_dict()}; "
          f"{(lp['transaction_type'] == 'Void').sum():,} voids; {f['reopen_date'].notna().sum():,} features reopened")


def benchmark(rep, risk, f, pay, s, e, last_full_year: int) -> None:
    """Frequency and severity on the Triple-I / ISO table's own definitions, by calendar year.

    A claim is counted in the year of its first loss payment, and severity is the year's payments over
    the claims counted in it (paid claims on a calendar-year basis). Liability payments include loss
    adjustment expense. Collision and comprehensive are restricted to risk rows with a $500 deductible, and
    comprehensive leaves out wind and water losses. What still differs is printed with the table."""
    pay = pay.assign(year=pd.to_datetime(pay["payment_date"]).dt.year)
    loss = pay[pay["payment_type"] == "Loss"]
    first_paid = loss[loss.amount > 0].groupby("claim_feature_id").year.min()
    premium = {"BI": "bi_premium", "PD": "pd_premium", "COLL": "collision_premium", "COMP": "comprehensive_premium"}
    deductible = {"COLL": "collision_deductible", "COMP": "comprehensive_deductible"}
    first_year = int(pd.Timestamp(s.min()).year)
    years = range(first_year, last_full_year + 1)
    print(f"  {'':5s}{'year':>5s}{'car-years':>11s}{'claims/100':>12s}{'national':>10s}{'ratio':>7s}{'avg paid':>10s}{'national':>10s}{'ratio':>7s}")
    for k, national in BENCHMARK.items():
        rows = (risk[premium[k]] > 0).to_numpy()
        g = f[f["coverage_code"] == k]
        if k in deductible:
            rows = rows & (risk[deductible[k]] == BENCHMARK_DEDUCTIBLE).to_numpy()
        if k == "COMP":
            g = g[~g["cause_of_loss"].isin(WIND_AND_WATER)]
        g = g[g["exposure_id"].isin(risk.loc[rows, "exposure_id"])]
        kinds = ["Loss", "Expense"] if k in ("BI", "PD") else ["Loss"]
        dollars = pay[pay["claim_feature_id"].isin(g["claim_feature_id"]) & pay["payment_type"].isin(kinds)].groupby("year").amount.sum()
        n = first_paid.reindex(g["claim_feature_id"]).dropna().astype(int).value_counts()
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
    pol, term, risk = read("policy"), read("policy_term"), read("exposure")
    drv, veh, loc = read("driver"), read("insured_vehicle"), read("location")
    clm, feat, pay = read("claim"), read("claim_feature"), read("claim_payment")
    inc, ledger = read("driver_incident"), read("premium_transaction")
    reserves, quotes, vmy = read("claim_reserve_transaction"), read("quote"), read("vehicle_model_year")
    enrol, tscores = read("telematics_enrollment"), read("telematics_score")
    offers = read("renewal_offer")
    inv, rec, emp, vend = read("billing_invoice"), read("billing_receipt"), read("employee"), read("vendor")
    agency, contact = read("agency", dtype={"zip_code": str}), read("customer_contact")
    truth = pd.read_csv(out / "answer_key" / "exposure_truth.csv")
    plan = json.loads((out / "answer_key" / "rating_plan.json").read_text())
    summary = json.loads((out / "run_summary.json").read_text())
    start, valuation = np.datetime64(summary["start"]), np.datetime64(summary["valuation"])
    pd.set_option("display.width", 200)
    rep = Report(calibrate=len(pol) >= MIN_POLICIES_FOR_CALIBRATION)
    if not rep.calibrate:
        print(f"note: {len(pol):,} policies is too few to hold calibration bands; misses are warnings, integrity checks still count")

    print("\nSIZE")
    cy = risk["earned_exposure"].sum()
    ep = risk["earned_premium"].sum()
    print(f"  {len(pol):,} policies, {len(term):,} policy terms, {len(veh):,} vehicles, {len(drv):,} drivers")
    print(f"  {cy:,.0f} earned car-years, ${ep:,.0f} earned premium, {len(clm):,} claims, {len(feat):,} coverage features")
    term_years = (pd.to_datetime(term["expiration_date"]) - pd.to_datetime(term["effective_date"])).dt.days.sum() / 365.25
    written = term["written_premium"].sum() + term["endorsement_premium"].sum()
    print(f"  average premium ${ep / cy:,.0f} per car-year, ${written / term_years:,.0f} per policy-year")
    # each risk row earns from its cover start (or the extract start, if later) for its earned exposure
    r_start = np.maximum(pd.to_datetime(risk["coverage_start_date"]).to_numpy(), start)
    r_days = np.round(risk["earned_exposure"].to_numpy() * 365.25).astype(int)
    r_end = r_start + r_days.astype("timedelta64[D]")

    print("\nINTEGRITY")
    rep.check("risk rows reference valid policy terms", risk["policy_term_id"].isin(term["policy_term_id"]).all())
    rep.check("risk rows reference valid vehicles and drivers", risk["insured_vehicle_id"].isin(veh["insured_vehicle_id"]).all()
              and risk["driver_id"].isin(drv["driver_id"]).all())
    rep.check("claims reference valid risk rows", clm["exposure_id"].isin(risk["exposure_id"]).all())
    c = clm.merge(risk[["exposure_id", "policy_id", "insured_vehicle_id"]], on="exposure_id", suffixes=("", "_r"))
    rep.check("claim vehicle and policy match the risk row", (c["policy_id"] == c["policy_id"]).all()
              and (c["insured_vehicle_id"] == c["insured_vehicle_id_r"]).all())
    c = clm.merge(term, on="policy_term_id")
    end = c["cancel_date"].fillna(c["expiration_date"])
    rep.check("every loss date falls inside its policy term", ((c["loss_date"] >= c["effective_date"]) & (c["loss_date"] < end)).all())
    rep.check("report date is on or after loss date", (clm["report_date"] >= clm["loss_date"]).all())
    rep.check("no negative premiums", (risk[[x for x in risk.columns if x.endswith("_premium")]] >= 0).all().all())
    rep.check("features and payments reference valid claims", feat["claim_id"].isin(clm["claim_id"]).all()
              and pay["claim_feature_id"].isin(feat["claim_feature_id"]).all())
    paid = pay[pay["payment_type"] == "Loss"].groupby("claim_feature_id").amount.sum().reindex(feat["claim_feature_id"]).fillna(0)
    rep.check("loss payments add up to paid loss on every feature", np.allclose(paid.to_numpy(), feat["paid_loss"].to_numpy(), atol=0.02))
    rep.check("claim totals equal the sum of their features",
              np.allclose(feat.groupby("claim_id")["net_incurred_loss"].sum().reindex(clm["claim_id"]).to_numpy(), clm["net_incurred_loss"].to_numpy(), atol=0.05))
    cov_ok = feat.merge(clm[["claim_id", "exposure_id", "cause_of_loss"]], on="claim_id").merge(risk, on="exposure_id")
    rep.check("physical damage, rental and towing claims only on risk rows carrying that coverage",
              all((cov_ok.loc[cov_ok["coverage_code"] == k, col] > 0).all() for k, col in
                  (("COLL", "collision_premium"), ("COMP", "comprehensive_premium"), ("RENT", "rental_premium"),
                   ("TOW", "towing_premium"))))
    integrity_limits(rep, cov_ok)
    age = (pd.to_datetime(drv["added_date"]) - pd.to_datetime(drv["date_of_birth"])).dt.days.to_numpy() / 365.25
    rep.check("all drivers are 16 or older when first insured", age.min() >= 16, f"youngest {age.min():.1f}, oldest {age.max():.1f}")
    integrity_lifecycle(rep, risk, term, pol, veh, drv, clm, feat, pay, inc, r_start, r_end, valuation)
    integrity_claims_and_quotes(rep, term, veh, clm, feat, reserves, quotes)
    integrity_vehicles(rep, vmy, veh, risk, clm)
    integrity_telematics(rep, enrol, tscores, risk, term, pd.Timestamp(valuation), pol, veh, drv)
    integrity_renewals(rep, offers, term, risk, valuation)
    integrity_calendar(rep, term, clm, feat, pay, reserves, inc, drv, ledger, contact)
    integrity_identifiers(rep, pol, term, drv, veh, risk, clm, feat, quotes, vmy)
    integrity_billing(rep, inv, rec, term, ledger, pol, valuation)
    integrity_payments(rep, pay, clm, feat, emp, vend, ledger, agency, pol, term)
    filed = plan["filed_discounts"]
    rep.check("the rating plan charges the filed discounts and surcharges, on the coverages they are filed for",
              all(list(plan["relativities"][cov][k].values()) == (list(d["factors"].values()) if cov in d["coverages"]
                                                                  else [1.0] * len(d["factors"]))
                  for k, d in filed.items() for cov in plan["relativities"]),
              "; ".join(f"{k} {list(d['factors'].values())}" for k, d in filed.items()))
    old = term[pd.to_datetime(term["expiration_date"]) < pd.Timestamp(valuation) - pd.Timedelta(days=90)]
    written = ledger[ledger["transaction_type"] != "Cancellation"].groupby("policy_term_id")["written_premium"].sum()
    returned = ledger[ledger["transaction_type"] == "Cancellation"].groupby("policy_term_id")["written_premium"].sum()
    gap_w = old["written_premium"] + old["endorsement_premium"] - written.reindex(old["policy_term_id"]).fillna(0).to_numpy()
    gap_r = old["return_premium"] - returned.reindex(old["policy_term_id"]).fillna(0).to_numpy()
    rep.check("the transaction ledger adds up to each completed term's written, endorsement and return premium",
              (gap_w.abs() <= 0.01 * old["vehicles_at_term_start"] + 0.05).all() and (gap_r.abs() <= 0.05).all(),
              f"{ledger['transaction_type'].value_counts().to_dict()}")

    print("\nFREQUENCY AND SEVERITY (paid claims by coverage: whole extract, every deductible and cause, loss only)")
    f = feat.merge(clm[["claim_id", "exposure_id", "loss_date", "catastrophe_id", "cause_of_loss"]], on="claim_id")
    has = {"BI": risk["bi_premium"] > 0, "PD": risk["pd_premium"] > 0, "UM": risk["um_premium"] > 0,
           "MED": risk["med_pay_premium"] > 0, "COLL": risk["collision_premium"] > 0, "COMP": risk["comprehensive_premium"] > 0,
           "RENT": risk["rental_premium"] > 0, "TOW": risk["towing_premium"] > 0}
    prem_col = {"BI": "bi_premium", "PD": "pd_premium", "UM": "um_premium", "MED": "med_pay_premium",
                "RENT": "rental_premium", "TOW": "towing_premium",
                "COLL": "collision_premium", "COMP": "comprehensive_premium"}
    share = risk["earned_premium"] / risk["total_premium"]
    exp_total = 0.0
    print(f"  {'coverage':9s}{'car-years':>11s}{'claims/100':>12s}{'avg paid':>10s}{'loss ratio':>12s}{'actual/expected':>17s}")
    for k in ["BI", "PD", "UM", "MED", "COLL", "COMP", "RENT", "TOW"]:
        g = f[f["coverage_code"] == k]
        gp = g[g["paid_loss"] > 0]
        years = risk.loc[has[k], "earned_exposure"].sum()
        e_prem = (risk[prem_col[k]] * share).sum()
        expected = truth[f"expected_loss_{k.lower()}"].sum()
        noncat = g[g["catastrophe_id"].isna()]["net_incurred_loss"].sum()
        print(f"  {k:9s}{years:11,.0f}{len(gp) / years * 100:12.2f}{gp['paid_loss'].mean():10,.0f}"
              f"{g['net_incurred_loss'].sum() / e_prem:12.1%}{noncat / expected:17.3f}")
        if k in TARGETS:
            rep.band(f"{k} frequency per 100 car-years (tuning band)", len(gp) / years * 100, TARGETS[k]["freq"])
            rep.band(f"{k} average paid loss (tuning band)", gp["paid_loss"].mean(), TARGETS[k]["sev"], "{:,.0f}")
        exp_total += expected
    noncat_all = f[f["catastrophe_id"].isna()]["net_incurred_loss"].sum()
    rep.band("non-catastrophe incurred vs answer-key expected (all coverages)", noncat_all / exp_total, (0.93, 1.07), "{:.3f}")

    print("\nBENCHMARK COMPARISON (Triple-I / ISO definitions: paid claims by calendar year, liability with LAE, "
          f"physical damage at a ${BENCHMARK_DEDUCTIBLE} deductible, comprehensive without wind and water)")
    benchmark(rep, risk, f, pay, r_start, r_end, pd.Timestamp(valuation).year - 1)

    print("\nLOSS RATIO BY ACCIDENT YEAR (net incurred as of the valuation date / earned premium; losses exclude LAE,\n"
          "which is shown beside it; add the two for a loss-and-LAE ratio; neither is a combined ratio)")
    s, e, days = r_start, r_end, r_days
    rate = np.divide(risk["earned_premium"].to_numpy(), days, out=np.zeros(len(risk)), where=days > 0)
    loss_year = pd.to_datetime(clm["loss_date"]).dt.year
    years = sorted(loss_year.unique())
    lr, cat_lr = {}, {}
    for y in years:
        a, b = np.datetime64(f"{y}-01-01"), np.datetime64(f"{y + 1}-01-01")
        overlap = (np.minimum(e, b) - np.maximum(s, a)).astype("timedelta64[D]").astype(int).clip(0)
        prem = (overlap * rate).sum()
        m = loss_year == y
        lr[y] = clm.loc[m, "net_incurred_loss"].sum() / prem
        cat = cat_lr[y] = clm.loc[m & clm["catastrophe_id"].notna(), "net_incurred_loss"].sum() / prem
        print(f"  {y}: earned premium ${prem:>12,.0f}   car-years {(overlap * (days > 0)).sum() / 365.25:>8,.0f}   "
              f"loss ratio {lr[y]:6.1%}   (catastrophe {cat:5.1%})   LAE ratio {clm.loc[m, 'paid_expense'].sum() / prem:5.1%}")
    full = [y for y in years if y < years[-1]]
    exp_loss = truth.set_index("exposure_id")["expected_loss_total"].reindex(risk["exposure_id"]).to_numpy()
    exp_rate = np.divide(exp_loss, days, out=np.zeros(len(risk)), where=days > 0)
    for y in full:
        a_, b_ = np.datetime64(f"{y}-01-01"), np.datetime64(f"{y + 1}-01-01")
        overlap = (np.minimum(e, b_) - np.maximum(s, a_)).astype("timedelta64[D]").astype(int).clip(0)
        expected_lr = (overlap * exp_rate).sum() / (overlap * rate).sum()
        # the answer key's expected losses leave out the (fictional, dated) catastrophes, so they are compared
        # with the year's losses excluding catastrophes
        rep.band(f"{y} loss ratio excluding catastrophes ({lr[y] - cat_lr[y]:.1%}) relative to its expected "
                 f"({expected_lr:.1%})", (lr[y] - cat_lr[y]) / expected_lr, ACTUAL_TO_EXPECTED_BAND, "{:.2f}")
    for y, b in INDUSTRY_LOSS_RATIO_BAND.items():
        a_, b_ = np.datetime64(f"{y}-01-01"), np.datetime64(f"{y + 1}-01-01")
        overlap = (np.minimum(e, b_) - np.maximum(s, a_)).astype("timedelta64[D]").astype(int).clip(0)
        if y in years and y < years[-1]:     # industry ratios include catastrophes: the year's are added
            rep.band(f"{y} expected loss ratio (answer key) plus catastrophes vs industry",
                     (overlap * exp_rate).sum() / (overlap * rate).sum() + cat_lr[y], b, "{:.1%}")
    rep.band("overall loss ratio", clm["net_incurred_loss"].sum() / ep, OVERALL_LOSS_RATIO_BAND, "{:.1%}")
    whole = pd.Timestamp(valuation).strftime("%m-%d") == "12-31"
    print(f"  note: {years[-1]} is {'the latest accident year, the least developed' if whole else 'a partial year'}: its "
          "claims not yet reported are missing and its injury claims are young, so it looks better than it will develop.")
    # the book in force on the start date is there from day one: no artificial ramp-up in the first year
    bounds = (start.astype("M8[M]") + np.arange(13).astype("timedelta64[M]")).astype("M8[D]")
    per_day = [(np.minimum(e, b) - np.maximum(s, a)).astype(int).clip(0).sum() / (b - a).astype(int)
               for a, b in zip(bounds[:-1], bounds[1:])]
    rep.band("first month's exposure relative to the first year's average", per_day[0] / np.mean(per_day), (0.85, 1.15), "{:.2f}")

    print("\nBOOK PROFILE")
    age_now = age
    print(f"  drivers: {np.mean(age_now < 25):.1%} under 25, {np.mean(age_now >= 65):.1%} 65+, median age {np.median(age_now):.0f}, "
          f"{(drv.gender == 'M').mean():.1%} male, {(drv['marital_status'] == 'M').mean():.1%} married")
    rep.band("share of drivers with no violation in 3 years", (drv["prior_violations"] == 0).mean(), (0.78, 0.90), "{:.1%}")
    rep.band("share of drivers with no at-fault accident in 3 years", (drv["prior_accidents"] == 0).mean(), (0.86, 0.95), "{:.1%}")
    vage = pd.to_datetime(veh["added_date"]).dt.year.to_numpy() - \
        vmy.set_index("vehicle_model_year_id")["model_year"].reindex(veh["vehicle_model_year_id"]).to_numpy()
    print(f"  vehicles: mean age {vage.mean():.1f} years, {(veh['collision_coverage'] == 'Y').mean():.1%} with collision, "
          f"{(veh['comprehensive_coverage'] == 'Y').mean():.1%} with comprehensive, {(veh['removed_date'].isna()).sum() / len(pol):.2f} per policy, removals {veh['removal_reason'].value_counts().to_dict()}")
    print(f"  BI limits: {pol['bi_limit'].value_counts(normalize=True).round(3).to_dict()}")
    print(f"  underwriting company mix: {pol['company_id'].value_counts(normalize=True).sort_index().round(3).to_dict()}")
    ended = term[(pd.to_datetime(term["expiration_date"]) <= pd.Timestamp(valuation))]
    lapsed = ended["cancel_date"].notna() | ended["nonrenewal_reason"].notna()
    months = (pd.to_datetime(ended["expiration_date"]) - pd.to_datetime(ended["effective_date"])).dt.days / 30.44
    annual_retention = float(np.exp(np.log(1 - lapsed.mean()) * 12 / months.mean()))
    rep.band("annualised policy retention", annual_retention, (0.78, 0.90), "{:.1%}")
    print(f"  cancellations: {term['cancel_reason'].value_counts().to_dict()}; non-renewals: {term['nonrenewal_reason'].value_counts().to_dict()}")
    print(f"  claims: {(clm['claim_status'] == 'Open').mean():.1%} open at valuation; cause mix "
          f"{clm['cause_of_loss'].value_counts(normalize=True).round(3).head(8).to_dict()}")

    print("\nRISK SIGNAL (does the data reward analysis?)")
    r = risk.merge(truth, on="exposure_id")
    cl = clm.groupby("exposure_id")["net_incurred_loss"].sum().reindex(r["exposure_id"]).fillna(0).to_numpy()
    r["loss"] = cl
    young = r["rated_driver_age"] < 21
    for label, m in [("drivers under 21", young), ("drivers 30-64", (r["rated_driver_age"] >= 30) & (r["rated_driver_age"] < 65)),
                     ("1+ at-fault accident", r["rated_at_fault_accidents"] > 0), ("clean record", (r["rated_at_fault_accidents"] == 0) & (r["rated_violation_points"] == 0))]:
        g = r[m]
        print(f"  {label:22s} loss ratio {g.loss.sum() / g['earned_premium'].sum():6.1%}   expected {g['expected_loss_total'].sum() / g['earned_premium'].sum():6.1%}"
              f"   claims per 100 car-years {clm['exposure_id'].isin(g['exposure_id']).sum() / g['earned_exposure'].sum() * 100:5.1f}")
    for label, m in [("telematics: not enrolled", r["telematics_enrolled"] == "N"), ("telematics: enrolled", r["telematics_enrolled"] == "Y"),
                     ("  discount 0-10%", (r["telematics_enrolled"] == "Y") & (r["telematics_discount_pct"] <= 10)),
                     ("  discount 11-20%", r["telematics_discount_pct"].between(11, 20)),
                     ("  discount 21-30%", r["telematics_discount_pct"].between(21, 30))]:
        g = r[m]
        print(f"  {label:22s} loss ratio {g.loss.sum() / g['earned_premium'].sum():6.1%}   expected {g['expected_loss_total'].sum() / g['earned_premium'].sum():6.1%}"
              f"   car-years {g['earned_exposure'].sum():9,.0f}   average premium ${g['earned_premium'].sum() / g['earned_exposure'].sum():,.0f}")
    # what the hidden stability, the new-customer effect and the agencies' book quality leave in the data
    elr = lambda g: g["expected_loss_total"].sum() / g["earned_premium"].sum()
    r = r.merge(term[["policy_term_id", "business_type"]], on="policy_term_id").merge(
        pol[["policy_id", "distribution_channel", "payment_plan", "agency_id"]], on="policy_id")
    new_b, ren_b = r[r["business_type"] == "New"], r[r["business_type"] == "Renewal"]
    print(f"  new business expected loss ratio {elr(new_b):.1%}, renewals {elr(ren_b):.1%}; by channel "
          + ", ".join(f"{k} {elr(g):.1%}" for k, g in r.groupby("distribution_channel"))
          + "; by payment plan " + ", ".join(f"{k} {elr(g):.1%}" for k, g in r.groupby("payment_plan")))
    rep.band("new business expected loss ratio above renewals (points)", (elr(new_b) - elr(ren_b)) * 100, (5.0, 16.0), "{:.1f}")
    by_agency = r.groupby("agency_id").apply(elr, include_groups=False)
    rep.band("spread of expected loss ratio across agencies (90th less 10th percentile, points)",
             (by_agency.quantile(0.9) - by_agency.quantile(0.1)) * 100, (6.0, 25.0), "{:.1f}")
    decided = offers[(offers["underwriting_decision"] == "Renew") & offers["outcome"].isin(["Renewed", "Insured Did Not Renew"])]
    kept_by = (decided["outcome"] == "Renewed").groupby(pol.set_index("policy_id")["distribution_channel"].reindex(decided["policy_id"]).to_numpy()).mean()
    rep.band("renewal rate of exclusive-agent customers above direct customers (points)",
             (kept_by["Exclusive Agent"] - kept_by["Direct"]) * 100, (1.0, 8.0), "{:.1f}")
    bi_paid = feat[(feat["coverage_code"] == "BI") & (feat["paid_loss"] > 0)]["paid_loss"]
    rep.band("share of paid bodily injury settlements that are whole-dollar amounts", (np.round(bi_paid * 100) % 100 == 0).mean(),
             (0.75, 0.95), "{:.1%}")
    wd = pd.to_datetime(clm.loc[clm["cause_of_loss"].isin(["AF_MV", "AF_SV", "NAF"]), "loss_date"]).dt.dayofweek.value_counts(normalize=True)
    # Chicago's daily crash counts put Thursdays and Fridays about 16% above Sundays and Mondays
    rep.band("crashes on Thursdays and Fridays relative to Sundays and Mondays", (wd[3] + wd[4]) / (wd[6] + wd[0]), (1.05, 1.28))
    z = r.merge(loc[["location_id", "region"]], on="location_id").groupby("region").agg(
        car_years=("earned_exposure", "sum"), premium=("earned_premium", "sum"), loss=("loss", "sum"), expected=("expected_loss_total", "sum"))
    z["avg premium"] = (z.premium / z.car_years).round(0)
    z["loss ratio"] = (z.loss / z.premium).round(3)
    z["expected loss ratio"] = (z.expected / z.premium).round(3)
    print("  " + z[["car_years", "avg premium", "loss ratio", "expected loss ratio"]].round(3).to_string().replace("\n", "\n  "))

    warned = f" ({rep.warnings} calibration warning(s) on a small book)" if rep.warnings else ""
    print(f"\n{'ALL CHECKS PASSED' if rep.failures == 0 else str(rep.failures) + ' CHECK(S) FAILED'}{warned}")
    sys.exit(1 if rep.failures else 0)


if __name__ == "__main__":
    main()
