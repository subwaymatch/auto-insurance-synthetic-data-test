#!/usr/bin/env python3
"""Check a generated dataset against its calibration targets and for internal consistency.

    python validate.py [--out output]

Reads only the CSV files, exactly as a user of the data would. Exits non-zero if an
integrity check fails or a calibrated figure falls outside its tolerance band.
"""
from __future__ import annotations

import argparse
import hashlib
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
    "COLL": dict(freq=(4.00, 6.20), sev=(5_400, 7_400)),
    "COMP": dict(freq=(4.60, 6.80), sev=(2_200, 3_400)),
}
# Triple-I / ISO "Private Passenger Auto Insurance Losses, 2015-2024" (national; source: ISO, a Verisk
# business): (claims per 100 earned car years, claim severity) by calendar year. Its footnotes define the
# figures: paid claims, all limits combined; bodily injury and property damage severity include loss
# adjustment expenses; collision and comprehensive are for coverage with a $500 deductible; comprehensive
# excludes wind and water losses and includes glass; some states are excluded (Massachusetts throughout,
# most no-fault states for bodily injury, Michigan and New Jersey for property damage).
# The table does not say whether salvage and subrogation come off physical damage payments. They are taken
# off here (ASSUMED), for two reasons. Insurers report recoveries to statistical agents as negative paid
# losses. And Verisk's own report on the same data (2024 Executive Insights: Personal Auto) puts collision
# severity at a $500 deductible at $6,951 for the year to March 2024 with salvage and subrogation offsetting
# 24% of collision payments (10.1% and 14.0%), which leaves about the $5,500 this table shows; that report's
# figures are developed accident-year ones, so the match is not exact. On this reading payments before
# recoveries, loss ratios and Illinois' average premiums (ILLINOIS below) are consistent with each other.
BENCHMARK = {
    "BI":   {2022: (0.70, 24_681), 2023: (0.78, 26_178), 2024: (0.80, 28_278)},
    "PD":   {2022: (2.54, 6_024), 2023: (2.59, 6_554), 2024: (2.50, 6_770)},
    "COLL": {2022: (4.48, 5_377), 2023: (4.48, 5_521), 2024: (4.16, 5_489)},
    "COMP": {2022: (3.78, 2_175), 2023: (4.08, 2_305), 2024: (3.95, 2_306)},
}
BENCHMARK_DEDUCTIBLE = 500
# NAIC Auto Insurance Database, average premium supplement (2024 edition), Illinois: average premium per
# insured car-year of each coverage, and (2023) the share of liability car-years that carry collision and
# comprehensive. The book is the Chicago area, not the state, and one carrier, so the bands are wide.
ILLINOIS = {"liability": {2022: 524.36, 2023: 597.70, 2024: 649.14}, "collision": {2022: 384.29, 2023: 440.06, 2024: 473.00},
            "comprehensive": {2022: 171.50, 2023: 218.89, 2024: 260.75}}
ILLINOIS_TAKE_UP = {"collision": 0.826, "comprehensive": 0.875}
ILLINOIS_PREMIUM_BAND = {"liability": (0.90, 1.30), "collision": (0.80, 1.20), "comprehensive": (0.75, 1.20)}
ILLINOIS_TAKE_UP_BAND = (-0.04, 0.04)     # difference from the state's share
WIND_AND_WATER = ["WEATHER", "FLOOD", "HAIL_CAT", "WIND_CAT", "FLOOD_CAT"]
# Bands for the like-for-like comparison, as a ratio to the national figure. Frequency is allowed to run
# above national because the book is urban; severity should sit near it. The first calendar year is shown
# but not held to a band for bodily injury: with no claims from before the warm-up year, its payments are too few.
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


def completed_age(on, born) -> np.ndarray:
    """Whole years completed on dates `on` since dates `born` (YYYY-MM-DD text or dates): an age goes up on the
    birthday, and a 29 February birthday is reached on 1 March in a common year."""
    on, born = pd.to_datetime(pd.Series(np.asarray(on))), pd.to_datetime(pd.Series(np.asarray(born)))
    before = (on.dt.month < born.dt.month) | ((on.dt.month == born.dt.month) & (on.dt.day < born.dt.day))
    return (on.dt.year - born.dt.year - before.astype(int)).to_numpy()


CLASS_AGES = {"16-17": (16, 17), "18-20": (18, 20), "21-24": (21, 24), "25-29": (25, 29), "30-39": (30, 39),
              "40-49": (40, 49), "50-64": (50, 64), "65-74": (65, 74), "75+": (75, 200)}


def load(out: Path) -> dict:
    """Every table of an output folder, read exactly as a user of the data would read the CSV files."""
    read = lambda f: pd.read_csv(f, keep_default_na=False, na_values=[""], low_memory=False, dtype={"zip_code": str, "change_reason": str})
    return {f.stem: read(f) for f in sorted(Path(out).glob("*.csv"))}


def rebuild(t: dict, start, valuation) -> dict:
    """Add back the totals the tables leave to their users, worked out from the records they hold, so the checks
    below can use them. The tables keep what an insurer's systems record (payments, reserve changes, premium
    transactions, coverage dates) and leave out what an analyst totals from them; this is how:

    * a feature's paid loss, recoveries, expenses and case and expense reserves as of the valuation date are its
      claim_payment rows and its last claim_reserve_transaction balance of each type (a loss run); a claim's are
      the sum of its features';
    * an exposure row earns from its cover start (or the extract start) to its cover end (or the day after the
      valuation date): its earned exposure in years and its premium pro rata over the term's days;
    * a term's endorsement and return premium are its premium transactions of those types, its earned premium
      that of its exposure rows, its vehicles at the start the rows beginning on its effective date;
    * a driver's prior violations and at-fault accidents are those in driver_incident dated in the three years
      before joining and known by then.
    Changes and returns `t` (a dict of the tables by name)."""
    start, valuation = pd.Timestamp(start), pd.Timestamp(valuation)
    dt = lambda x: pd.to_datetime(x)
    feat, pay, res = t["claim_feature"], t["claim_payment"], t["claim_reserve_transaction"]
    fid = feat["claim_feature_id"]
    total = lambda m: pay[m].groupby("claim_feature_id")["amount"].sum().reindex(fid).fillna(0).round(2).to_numpy()
    kind, txn = pay["payment_type"], pay["transaction_type"]
    feat["paid_loss"] = total(kind == "Loss")
    feat["salvage_recovery"] = -total(kind == "Salvage Recovery") + 0.0
    feat["subrogation_recovery"] = -total(kind == "Subrogation Recovery") + 0.0
    feat["paid_dcc_expense"], feat["paid_ao_expense"] = total(txn == "DCC Expense"), total(txn == "A&O Expense")
    feat["paid_expense"] = (feat["paid_dcc_expense"] + feat["paid_ao_expense"]).round(2)
    last = res.sort_values(["claim_feature_id", "reserve_type", "transaction_date", "reserve_transaction_id"], kind="stable") \
        .groupby(["claim_feature_id", "reserve_type"])["outstanding_reserve"].last().unstack()
    for col, rtype in (("case_reserve", "Loss"), ("expense_reserve", "Expense")):
        feat[col] = last[rtype].reindex(fid).fillna(0).to_numpy() if rtype in last else 0.0
    feat["incurred_loss"] = (feat["paid_loss"] + feat["case_reserve"]).round(2)
    feat["net_incurred_loss"] = (feat["incurred_loss"] - feat["salvage_recovery"] - feat["subrogation_recovery"]).round(2)
    clm = t["claim"]
    by_claim = feat.groupby("claim_id")
    for col in ("paid_loss", "case_reserve", "net_incurred_loss", "paid_expense", "expense_reserve"):
        clm[col] = by_claim[col].sum().reindex(clm["claim_id"]).fillna(0).round(2).to_numpy()
    clm["recoveries"] = (by_claim["salvage_recovery"].sum() + by_claim["subrogation_recovery"].sum()).reindex(clm["claim_id"]).fillna(0).to_numpy()

    risk, term = t["exposure"], t["policy_term"]
    tm = term.set_index("policy_term_id")
    span = (dt(tm["expiration_date"]) - dt(tm["effective_date"])).dt.days.reindex(risk["policy_term_id"]).to_numpy()
    s_ = np.maximum(dt(risk["coverage_start_date"]), start)
    e_ = np.minimum(dt(risk["coverage_end_date"]), valuation + pd.Timedelta(days=1))
    days = (e_ - s_).dt.days.clip(lower=0).to_numpy()
    risk["earned_exposure"] = days / 365.25
    risk["earned_premium"] = (risk["total_premium"] * days / span).round(2)
    before = (np.minimum(dt(risk["coverage_end_date"]), start) - dt(risk["coverage_start_date"])).dt.days.clip(lower=0).to_numpy()
    veh, vmy = t["insured_vehicle"], t["vehicle_model_year"]
    risk["vehicle_model_year_id"] = veh.set_index("insured_vehicle_id")["vehicle_model_year_id"].reindex(risk["insured_vehicle_id"]).to_numpy()
    risk["model_year"] = vmy.set_index("vehicle_model_year_id")["model_year"].reindex(risk["vehicle_model_year_id"]).to_numpy()
    tx = t["premium_transaction"].groupby(["policy_term_id", "transaction_type"])["written_premium"].sum().unstack()
    tid = term["policy_term_id"]
    term["endorsement_premium"] = tx.get("Endorsement", pd.Series(dtype=float)).reindex(tid).fillna(0).round(2).to_numpy()
    term["return_premium"] = tx.get("Cancellation", pd.Series(dtype=float)).reindex(tid).fillna(0).round(2).to_numpy()
    term["earned_premium"] = risk.groupby("policy_term_id")["earned_premium"].sum().reindex(tid).fillna(0).round(2).to_numpy()
    term["earned_premium_before_extract"] = pd.Series(risk["total_premium"].to_numpy() * before / span) \
        .groupby(risk["policy_term_id"].to_numpy()).sum().reindex(tid).fillna(0).round(2).to_numpy()
    at_start = dt(risk["coverage_start_date"]).to_numpy() == dt(tm["effective_date"]).reindex(risk["policy_term_id"]).to_numpy()
    term["vehicles_at_term_start"] = risk[at_start].groupby("policy_term_id").size().reindex(tid).fillna(0).astype(int).to_numpy()

    drv, inc = t["driver"], t["driver_incident"]
    j = inc.merge(drv[["driver_id", "added_date"]], on="driver_id")
    j = j[(dt(j["incident_date"]) <= dt(j["added_date"])) & (dt(j["incident_date"]) > dt(j["added_date"]) - pd.Timedelta(days=3 * 365))
          & (dt(j["known_date"]) <= dt(j["added_date"]))]
    count = lambda m: j[m].groupby("driver_id").size().reindex(drv["driver_id"]).fillna(0).astype(int).to_numpy()
    drv["prior_violations"] = count(j["incident_type"] != "At-Fault Accident")
    drv["prior_accidents"] = count(j["incident_type"] == "At-Fault Accident")
    return t


def integrity_claims_and_quotes(rep, term, veh, clm, feat, reserves, quotes) -> None:
    """Reserve history, claim detail, vehicle identifiers and the quote funnel."""
    r = reserves.sort_values(["claim_feature_id", "reserve_type", "transaction_date", "reserve_transaction_id"], kind="stable")
    running = r.groupby(["claim_feature_id", "reserve_type"])["change_amount"].cumsum()
    last = r.groupby(["claim_feature_id", "reserve_type"])["outstanding_reserve"].last().unstack()
    at_val = lambda kind: (last[kind] if kind in last else pd.Series(dtype=float)).reindex(feat["claim_feature_id"]).fillna(0).to_numpy()
    rep.check("each reserve balance is the running total of the changes before it, and a closed feature has none left",
              np.allclose(running, r["outstanding_reserve"], atol=0.01)
              and np.allclose(at_val("Loss")[(feat["feature_status"] == "Closed").to_numpy()], 0, atol=0.01),
              f"{len(reserves):,} reserve transactions")
    dt = lambda x: pd.to_datetime(x)
    f = feat.merge(clm[["claim_id", "loss_date", "at_fault", "insured_fault_pct", "report_date", "siu_referral_date"]], on="claim_id")
    suits = f[f["suit_date"].notna()]
    rep.check("suits follow the attorney and the claim, precede the close, and fall within Illinois' two-year limit",
              (dt(suits["suit_date"]) >= dt(suits["attorney_date"])).all()
              and (dt(suits["suit_date"]) >= dt(suits["open_date"])).all()
              and (suits["close_date"].isna() | (dt(suits["suit_date"]) < dt(suits["close_date"]))).all()
              and ((dt(suits["suit_date"]) - dt(suits["loss_date"])).dt.days <= 730).all(),
              f"{feat['attorney_date'].notna().sum():,} represented claimants, {len(suits):,} suits")
    fault = clm.dropna(subset=["insured_fault_pct"])
    att = f[f["attorney_date"].notna()]
    rep.check("attorneys are retained after the loss and before the feature closes",
              (dt(att["attorney_date"]) >= dt(att["loss_date"])).all()
              and (att["close_date"].isna() | (dt(att["attorney_date"]) <= dt(att["close_date"]))).all())
    rep.check("an insured at fault is over 50% at fault, and one not at fault is under 51%",
              ((fault["at_fault"] == "Y") == (fault["insured_fault_pct"] > 50)).all())
    siu = clm[clm["siu_referral_date"].notna()]
    rep.check("fraud referrals are made while the claim is open: on or after its report, and on or before its close",
              (siu["siu_referral_date"] >= siu["report_date"]).all()
              and ~(siu["siu_referral_date"] > siu["close_date"]).any(), f"{len(siu):,} referrals")
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


def integrity_calendar(rep, term, clm, feat, pay, reserves, inc, drv, ledger, contact, emp, agency, producer, inv) -> None:
    """Work done by staff, banks and courts falls on business days."""
    all_on = lambda *cols: all(business_day(c).all() for c in cols)
    reviews = reserves.loc[reserves["transaction_type"] != "Initial Reserve", "transaction_date"]
    rep.check("claim payments, file closes, reserve changes after the first, suits and fraud referrals fall on business days",
              all_on(pay["payment_date"], pay["cleared_date"], clm["close_date"], feat["close_date"], reviews, feat["suit_date"],
                     clm["siu_referral_date"]),
              f"{len(pay):,} payments; {1 - business_day(clm['report_date']).mean():.1%} of claims are reported on a weekend or holiday")
    rep.check("staff are hired and leave, agencies are appointed, producers start and bills are written off on business days",
              all_on(emp["hire_date"], emp["termination_date"], agency["appointment_date"], producer["start_date"],
                     inv["write_off_date"]),
              f"{len(emp):,} staff, {len(agency):,} agencies, {len(producer):,} producers, "
              f"{inv['write_off_date'].notna().sum():,} write-offs")
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
    rep.check("every VIN is unique, has 17 characters and a valid check digit, and follows its model year's pattern "
              "(position 7 a digit to 2009 and a letter after, telling the year code's 30-year cycles apart)",
              vin.is_unique and (vin.str.len() == 17).all() and (vin.str[8] == vin_check_digit(vin)).all()
              and (vin.str[:8] == pd.Series(pattern).str[:8]).all() and (vin.str[9] == pd.Series(pattern).str[9]).all()
              and (vmy["vin_pattern"].str[6].str.isdigit() == (vmy["model_year"] <= 2009)).all())
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


def integrity_billing(rep, inv, rec, term, ledger, pol, valuation, contact=None) -> None:
    """Bills and cash: every finished term's bills reconcile with the premium ledger, and with the cash received."""
    dt = lambda x: pd.to_datetime(x)
    val = pd.Timestamp(valuation)
    t = term.set_index("policy_term_id")
    net = ledger.groupby("policy_term_id")["written_premium"].sum()
    kept = inv[inv["invoice_status"] != "Canceled"].groupby("policy_term_id")["premium_amount"].sum()
    refund = -rec[rec["receipt_type"] == "Refund"].groupby("policy_term_id")["amount"].sum()
    end = dt(t["cancel_date"].fillna(t["expiration_date"]))
    done = t.index[end < val - pd.Timedelta(days=150)]
    gap = kept.reindex(done).fillna(0) - refund.reindex(done).fillna(0) - net.reindex(done).fillna(0)
    rep.check("for every finished term, premium billed (less canceled bills) minus premium refunded equals the ledger's "
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
    rep.check("a paid-in-full term has one bill and a monthly term one installment a month",
              (inv.loc[regular & (plan == "Paid in Full"), "installment_number"] == 1).all()
              and (inv.loc[regular, "installment_number"] <= months[regular]).all()
              and not inv[regular].duplicated(["policy_term_id", "installment_number"]).any())
    # a cancellation for non-payment follows an instalment that was billed and never paid: every one of them
    np_terms = term[term["cancel_reason"] == "Non-Payment"]
    unpaid = inv[(inv["invoice_status"] == "Canceled") & (inv["invoice_type"] == "Installment") & (inv["amount_due"] > 0)]
    missed = unpaid.groupby("policy_term_id")["due_date"].min()
    lag = (dt(np_terms["cancel_date"]) - dt(missed.reindex(np_terms["policy_term_id"]).to_numpy())).dt.days
    rep.check("every cancellation for non-payment follows an unpaid installment, billed and due three to four weeks before it",
              lag.between(21, 28).all(),
              f"{len(np_terms):,} cancellations; median {lag.median():.0f} days after the missed due date; "
              f"{(~lag.between(21, 28)).sum():,} without a matching unpaid bill")
    if contact is not None:
        # Illinois: a notice of cancellation for non-payment is mailed at least ten days before cover ends (215 ILCS
        # 5/143.15). Contacts start with the extract, so cancellations whose missed bill fell due before it are skipped
        notice = contact.loc[contact["purpose"] == "Notice of Cancellation", ["policy_id", "contact_date", "contact_method"]]
        due = missed.reindex(np_terms["policy_term_id"]).to_numpy()
        x = np_terms[["policy_term_id", "policy_id", "cancel_date"]].assign(due=due)
        x = x[x["due"] >= contact["contact_date"].min()].merge(notice, on="policy_id", how="left")
        mailed = ((x["contact_date"] >= x["due"]) & (x["contact_method"] == "Written Letter")
                  & ((dt(x["cancel_date"]) - dt(x["contact_date"])).dt.days >= 10))
        got = mailed.groupby(x["policy_term_id"]).any()
        rep.check("every cancellation for non-payment had a notice of cancellation mailed at least ten days before it",
                  got.all(), f"{len(got):,} cancellations whose missed bill fell due in the extract; {(~got).sum():,} without")
        # any other cancellation by the company: at least 30 days' notice, mailed in the policy's first 60 days
        uw = term.loc[term["cancel_reason"] == "Underwriting", ["policy_term_id", "policy_id", "effective_date", "cancel_date"]]
        y = uw[uw["effective_date"] >= contact["contact_date"].min()].merge(notice, on="policy_id", how="left")
        ahead = (dt(y["cancel_date"]) - dt(y["contact_date"])).dt.days
        warned = ((y["contact_method"] == "Written Letter") & (ahead >= 30)
                  & (dt(y["contact_date"]) - dt(y["effective_date"])).dt.days.between(0, 59)).groupby(y["policy_term_id"]).any()
        rep.check("every underwriting cancellation had a notice of cancellation mailed in the policy's first 60 days, at "
                  "least 30 days before it", warned.all(),
                  f"{len(warned):,} underwriting cancellations; {(~warned).sum():,} without")
        # a notice for an unpaid bill goes while one is past due and unpaid
        nt = notice.reset_index(drop=True)
        w = nt.reset_index().merge(uw[["policy_id", "cancel_date"]], on="policy_id")
        is_uw = (dt(w["cancel_date"]) - dt(w["contact_date"])).dt.days.between(30, 60).groupby(w["index"]).any()
        bill_notice = nt[~is_uw.reindex(nt.index, fill_value=False).to_numpy()]
        bills = inv.loc[inv["invoice_type"] != "Final Balance", ["policy_id", "due_date", "paid_date"]]
        z = bill_notice.reset_index().merge(bills, on="policy_id")
        owing = (z["due_date"] < z["contact_date"]) & (z["paid_date"].isna() | (z["paid_date"] > z["contact_date"]))
        late = int((~owing.groupby(z["index"]).any().reindex(bill_notice.index, fill_value=False)).sum())
        rep.check("every billing notice of cancellation is mailed while a bill on the policy is past due and unpaid",
                  late == 0, f"{len(bill_notice):,} notices; {late:,} after the bill was paid")
    # money moved by a bank or by staff (a cheque banked, a bank draft taken or returned, a refund cheque) moves on
    # a business day; a card, online or agency payment can be made any day
    banked = rec[rec["payment_method"].isin(["Check", "EFT"])]
    rep.check("check and bank-draft receipts, returned drafts and refunds are dated on business days",
              business_day(banked["receipt_date"]).all(),
              f"{len(banked):,} receipts; {(~business_day(rec['receipt_date'])).sum():,} card, online or agency payments on other days")


def integrity_payments(rep, pay, clm, feat, emp, vend, ledger, agency, pol, term) -> None:
    """Claim payment detail (payee, check numbers, approval) and commissions."""
    dt = lambda x: pd.to_datetime(x)
    cut = pay[pay["check_number"].notna() & (pay["transaction_type"] != "Void")]
    numbers = cut["check_number"].astype(int).sort_values()
    void = pay[pay["transaction_type"] == "Void"].merge(cut[["check_number", "amount", "payment_status", "claim_feature_id",
                                                              "payment_id", "payment_date"]],
                                                         on="check_number", suffixes=("", "_cheque"))
    rep.check("check numbers run in one unbroken sequence in the order checks were cut; a void carries the number and "
              "amount of the check it cancels",
              numbers.is_unique and (numbers.diff().dropna() == 1).all() and cut["check_number"].is_monotonic_increasing
              and len(void) == (pay["transaction_type"] == "Void").sum() and np.allclose(void["amount"], -void["amount_cheque"])
              and (void["payment_status_cheque"] == "Voided").all() and (void["claim_feature_id"] == void["claim_feature_id_cheque"]).all()
              and (pay.loc[pay["payment_method"] != "Check", "check_number"].isna()).all(),
              f"{len(cut):,} checks from {numbers.min()} to {numbers.max()}; {pay['payment_method'].value_counts().to_dict()}")
    # replayed in payment order, a void comes after the check it cancels (on the same day too)
    rep.check("a void comes after the check it cancels, in payment order as well as by date",
              bool((void["payment_id"] > void["payment_id_cheque"]).all() and (void["payment_date"] >= void["payment_date_cheque"]).all()),
              f"{len(void):,} voids, {(void['payment_date'] == void['payment_date_cheque']).sum():,} on the day of their check")
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
    org = pay["payee_type"].isin(["Vendor", "Lienholder", "Other Insurer", "Claimant and Attorney", "Insured and Attorney"]).to_numpy()
    rep.check("a payment to an organization names a vendor of the right kind; a payment to a person names none",
              (pay["vendor_id"].notna().to_numpy() == org).all() and pay["payee_name"].notna().all()
              and (kind[(pay["payee_type"] == "Lienholder").to_numpy()] == "Lienholder").all()
              and (kind[(pay["payee_type"] == "Other Insurer").to_numpy()] == "Other Insurer").all()
              and (kind[pay["payee_type"].isin(["Claimant and Attorney", "Insured and Attorney"]).to_numpy()] == "Plaintiff Law Firm").all(),
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


def integrity_payees(rep, pay, clm, feat, veh, drv) -> None:
    """Who each claim payment goes to agrees with the rest of the record on the payment date."""
    dt = lambda x: pd.to_datetime(x)
    f = feat.set_index("claim_feature_id")
    c = clm.set_index("claim_id")
    v = veh.set_index("insured_vehicle_id")
    # a lender or lessor is paid only on a total loss of a financed or leased car, never more than the settlement,
    # and one lender per car. (The vehicle shows its latest ownership; a car the owner kept after a total loss has
    # had its loan or lease paid off by the settlement, so it shows as owned.)
    lien = pay[pay["payee_type"] == "Lienholder"]
    car = c["insured_vehicle_id"].reindex(lien["claim_id"]).to_numpy()
    fl = f.reindex(lien["claim_feature_id"])
    financed = v["ownership"].reindex(car).isin(["Financed", "Leased"]).to_numpy()
    loss = pay[pay["payment_type"] == "Loss"].groupby("claim_feature_id")["amount"].sum()
    tl = feat[(feat["total_loss"] == "Y") & (feat["owner_retained_salvage"] == "N") & (feat["feature_status"] == "Closed")
              & (feat["paid_loss"] > 0)]
    tl_car = c["insured_vehicle_id"].reindex(tl["claim_id"]).to_numpy()
    owed = tl[v["ownership"].reindex(tl_car).isin(["Financed", "Leased"]).to_numpy()]
    rep.check("a lienholder or lessor is paid only on a total loss of a financed or leased car, never more than the "
              "settlement and one lender per car; every closed, paid total loss of a financed or leased car pays one",
              (fl["total_loss"] == "Y").all() and (financed | (fl["owner_retained_salvage"] == "Y").to_numpy()).all()
              and (lien["amount"].to_numpy() <= loss.reindex(lien["claim_feature_id"]).to_numpy() + 0.005).all()
              and (pd.Series(lien["vendor_id"].to_numpy()).groupby(car).nunique() == 1).all()
              and owed["claim_feature_id"].isin(lien["claim_feature_id"]).all(),
              f"{len(lien):,} payments, ${lien['amount'].sum():,.0f}; "
              f"{v['ownership'].reindex(car).value_counts().to_dict()} (latest ownership)")
    kept = f.loc[f["owner_retained_salvage"] == "Y"].index
    leased_tl = feat[(feat["total_loss"] == "Y")
                     & (v["ownership"].reindex(c["insured_vehicle_id"].reindex(feat["claim_id"])).to_numpy() == "Leased")]
    to_lessee = pay[pay["claim_feature_id"].isin(leased_tl["claim_feature_id"]) & (pay["payment_type"] == "Loss")
                    & (pay["payee_type"] != "Lienholder")]
    rep.check("an owner keeps the salvage only of a car owned outright (no lender is paid on it), and a leased car's "
              "settlement, fees and supplements all go to the leasing company",
              not lien["claim_feature_id"].isin(kept).any() and len(to_lessee) == 0,
              f"{len(kept):,} owner-retained total losses, {len(leased_tl):,} leased total losses")
    # an injury claimant is paid jointly with an attorney only from the day the attorney is retained, and from then
    # on always (a void is made out like the check it cancels)
    inj = pay.assign(att=f["attorney_date"].reindex(pay["claim_feature_id"]).to_numpy(),
                     cvg=f["coverage_code"].reindex(pay["claim_feature_id"]).to_numpy())
    joint = inj["payee_type"].isin(["Claimant and Attorney", "Insured and Attorney"])
    after = inj["att"].notna() & (inj["payment_date"] >= inj["att"]) & inj["cvg"].isin(["BI", "UM"]) \
        & (inj["payment_type"] == "Loss") & (inj["transaction_type"] != "Void")
    rep.check("a claimant is paid jointly with an attorney only on or after the day the attorney was retained, and "
              "always after it",
              (inj.loc[joint, "payment_date"] >= inj.loc[joint, "att"]).all() and joint[after].all(),
              f"{joint.sum():,} joint payments; {(joint & inj['transaction_type'].eq('Partial Payment')).sum():,} of them "
              f"advances; {(~joint & inj['att'].notna() & inj['cvg'].isin(['BI', 'UM']) & (inj['payment_type'] == 'Loss')).sum():,} "
              "earlier payments on represented features went to the claimant alone")
    # identities as they stood: a claim's driver was on the policy on the loss date, and a payment to the insured
    # names someone on the policy on the payment date (the named insured can change later)
    d = drv.set_index("driver_id")
    who = clm["involved_driver_id"]
    loss_day = dt(clm["loss_date"]).to_numpy()
    on = ((dt(d["added_date"]).reindex(who).to_numpy() <= loss_day)
          & ~(dt(d["removed_date"]).reindex(who).to_numpy() <= loss_day)
          & (d["policy_id"].reindex(who).to_numpy() == clm["policy_id"].to_numpy()))
    # (by first name: a named insured who married since may now carry another surname than the one on the check).
    # The insured's own uninsured motorist claim pays the person injured, who was on the policy on the loss date
    ins = pay[pay["payee_type"].isin(["Insured", "Insured and Attorney"])][["payment_id", "claim_id", "payment_date", "payee_name"]]
    estate = ins["payee_name"].str.startswith("Estate of ")
    person = ins["payee_name"].str.removeprefix("Estate of ")
    ins = ins.assign(policy_id=c["policy_id"].reindex(ins["claim_id"]).to_numpy(),
                     loss_date=c["loss_date"].reindex(ins["claim_id"]).to_numpy(),
                     first_name=person.str.split(" ", n=1).str[0], person=person, estate=estate)
    m = ins.merge(drv[["policy_id", "first_name", "last_name", "added_date", "removed_date", "removal_reason"]],
                  on=["policy_id", "first_name"], how="left")
    on_day = lambda col: (m["added_date"] <= m[col]) & ~(m["removed_date"] <= m[col])
    # someone who has died since the loss is paid through their estate
    named = on_day("payment_date") | on_day("loss_date")
    same = named & pd.Series([str(a).startswith(f"{b} {c}") for a, b, c in zip(m["person"], m["first_name"], m["last_name"])],
                             index=m.index)
    dead = (m["removal_reason"] == "Deceased") & (m["removed_date"] <= m["payment_date"])
    right = (m["estate"] == dead) & same
    ok_pay, known = right.groupby(m["payment_id"]).any(), same.groupby(m["payment_id"]).any()
    rep.check("a payment due to an insured who has died goes to their estate, and only then",
              bool((ok_pay | ~known).all()), f"{int(estate.sum()):,} payments to an estate")
    rep.check("each claim's driver was on the policy on the loss date, and each payment to the insured (an uninsured "
              "motorist claimant's included) names someone on the policy on the loss or payment date",
              on.all() and named.groupby(m["payment_id"]).any().all(),
              f"{len(clm):,} claims ({(c['at_fault'] == 'N').sum():,} not at fault); {len(ins):,} payments to the insured, "
              f"{(~same.groupby(m['payment_id']).any()).sum():,} under a surname the insured has since changed")


def recoveries_ahead(pay: pd.DataFrame) -> pd.Index:
    """The features that on some payment date had recovered (salvage and subrogation) more than they had paid in
    loss by then."""
    flow = pay[pay["payment_type"].isin(["Loss", "Salvage Recovery", "Subrogation Recovery"])]
    flow = flow.assign(paid=np.where(flow["payment_type"] == "Loss", flow["amount"], 0.0),
                       back=np.where(flow["payment_type"] == "Loss", 0.0, -flow["amount"]))
    run = flow.groupby(["claim_feature_id", "payment_date"])[["paid", "back"]].sum().groupby(level=0).cumsum()
    return run[run["back"] > run["paid"] + 0.005].index.get_level_values(0).unique()


# Passive immobilizers on 2015-19 Kias and Hyundais as HLDI Bulletin 38(28), December 2021, Table 1 documents them:
# series where it was not available, and series where it was standard (those its table of optional and unavailable
# series leaves out, and two it marks standard)
KH_NO_IMMOBILIZER = [("Kia", "Rio", 2015, 2019), ("Hyundai", "Accent", 2015, 2017)]
KH_STANDARD_IMMOBILIZER = [("Kia", "Sorento", 2017, 2019), ("Hyundai", "Veloster", 2019, 2019)] + [
    (mk, md, 2015, 2019) for mk, md in (("Hyundai", "Azera"), ("Hyundai", "Equus"), ("Hyundai", "Genesis"),
                                         ("Hyundai", "Genesis Coupe"), ("Hyundai", "Ioniq"), ("Kia", "Cadenza"),
                                         ("Kia", "K900"), ("Kia", "Niro"), ("Kia", "Stinger"))]


def integrity_vehicles(rep, vmy, veh, risk, clm, vtruth=None) -> None:
    """The make, model and model-year catalog and the vehicles that point to it."""
    rep.check("each make, model and model year appears once in the vehicle catalog",
              not vmy.duplicated(["make", "model", "model_year"]).any() and vmy["vehicle_model_year_id"].is_unique,
              f"{len(vmy):,} model years of {vmy.groupby(['make', 'model']).ngroups:,} models from {vmy['make'].nunique()} makes")
    known = vmy.set_index("vehicle_model_year_id")
    rep.check("insured vehicles and claims point to catalog rows, a claim to its vehicle's",
              veh["vehicle_model_year_id"].isin(known.index).all() and clm["vehicle_model_year_id"].isin(known.index).all()
              and (veh.set_index("insured_vehicle_id")["vehicle_model_year_id"].reindex(clm["insured_vehicle_id"]).to_numpy()
                   == clm["vehicle_model_year_id"].to_numpy()).all())
    years = risk.groupby("model_year")["earned_exposure"].sum()
    first = int(vmy["model_year"].min())
    at, after = years.get(first, 0.0), years.reindex(range(first + 1, first + 4)).fillna(0).mean()
    rep.check("no pile-up of older cars at the catalog's first model year", at <= 1.5 * after + 10,
              f"{first}: {at:,.0f} car-years, the next three years {after:,.0f} each on average", statistical=True)
    x = veh.merge(vmy, on="vehicle_model_year_id")
    cohort = x["make"].isin(["Kia", "Hyundai"]) & (x["fuel_type"] != "Electric") & x["model_year"].between(2011, 2021)
    has = x["anti_theft_device"] == "Y"
    of = lambda spans: np.logical_or.reduce([(x["make"] == mk) & (x["model"] == md) & x["model_year"].between(y0, y1)
                                             for mk, md, y0, y1 in spans])
    none_, std_ = of(KH_NO_IMMOBILIZER), of(KH_STANDARD_IMMOBILIZER)
    # where it was an option some cars have it and some not (the book has enough of the big series to show both)
    opt_ = cohort & ~none_ & ~std_ & x["model"].isin(["Elantra", "Sonata", "Optima", "Forte", "Soul", "Sportage", "Tucson"])
    exposure = "" if vtruth is None else "; the answer key's theft-wave exposure is exactly the 2011-21 Kias and Hyundais without one"
    ok_truth = True
    if vtruth is not None:
        flag = vtruth.set_index("insured_vehicle_id")["kia_hyundai_theft_exposure"].reindex(x["insured_vehicle_id"]).to_numpy() == "Y"
        ok_truth = bool((flag == (cohort & ~has).to_numpy()).all())
    rep.check("2011-21 Kias and Hyundais have an immobilizer as their series did that model year (HLDI): none on the "
              "series without one, always on those with it standard, on some cars of those offering it" + exposure,
              bool((~has[none_]).all() and has[std_].all() and has[opt_].any() and (~has[opt_]).any()) and ok_truth,
              f"{cohort.sum():,} cars, {has[cohort].mean():.0%} with an immobilizer ({(~has[cohort]).sum():,} without, the theft "
              f"wave's); {none_.sum():,} on series without one, {std_.sum():,} on series with it standard; anti-theft on "
              f"{has[~cohort].mean():.0%} of other cars, automatic emergency braking on {(x['automatic_emergency_braking'] == 'Y').mean():.0%}")
    lease = x[x["replaces_insured_vehicle_id"].notna() & (x["ownership"] == "Leased")]
    rep.check("a replacement car taken on a new lease is new (its model year no older than the year before)",
              (pd.to_datetime(lease["added_date"]).dt.year - lease["model_year"] <= 1).all(), f"{len(lease):,} leased replacements")
    drawn = vmy[vmy["vehicle_model_year_id"].isin(veh["vehicle_model_year_id"])]
    print(f"  {drawn.groupby(['make', 'model']).ngroups:,} models from {drawn['make'].nunique()} makes are insured; "
          f"top makes {veh.merge(vmy, on='vehicle_model_year_id')['make'].value_counts(normalize=True).head(6).round(3).to_dict()}")


def integrity_telematics(rep, enrol, scores, risk, term, valuation, pol=None, veh=None, drv=None) -> None:
    """The telematics program: enrollments, scores and the discounts rated on each exposure row."""
    dt = lambda x: pd.to_datetime(x)
    e = enrol.set_index("enrollment_id")
    if pol is not None:
        inception = dt(pol.set_index("policy_id")["original_inception_date"])
        added_v = dt(veh.set_index("insured_vehicle_id")["added_date"]).reindex(scores["insured_vehicle_id"]).to_numpy()
        added_d = dt(drv.set_index("driver_id")["added_date"]).reindex(scores["driver_id"]).to_numpy()
        start = dt(scores["period_start_date"]).to_numpy()
        rep.check("a policy joins the program after it was written, and a car is scored only while it and its "
                  "driver are on the policy",
                  (dt(enrol["enrollment_date"]).to_numpy() >= inception.reindex(enrol["policy_id"]).to_numpy()).all()
                  and (start >= added_v).all() and (start >= added_d).all())
    rep.check("enrollments end after they start and by the valuation date",
              (e["end_date"].isna() | (dt(e["end_date"]) >= dt(e["enrollment_date"]))).all()
              and (dt(e["enrollment_date"]) <= valuation).all() and (dt(e["end_date"]).dropna() <= valuation).all(),
              f"{len(enrol):,} enrollments; {enrol['device_type'].value_counts().to_dict()}; ended {enrol['end_reason'].value_counts().to_dict()}")
    s_ = scores
    within = (dt(s_["period_start_date"]) >= dt(e["enrollment_date"]).reindex(s_["enrollment_id"]).to_numpy()) \
        & (dt(s_["period_end_date"]) <= dt(e["end_date"]).reindex(s_["enrollment_id"]).fillna(pd.Timestamp.max).to_numpy())
    rule = np.round(np.clip((s_["driving_score"] - 45) / 50, 0, 1) * 30)
    scored = s_["driving_score"].notna()
    rep.check("scores fall inside their enrollment, cover their stated days, and earn the published discount",
              within.all() and ((dt(s_["period_end_date"]) - dt(s_["period_start_date"])).dt.days == s_["days_monitored"]).all()
              and s_.loc[scored, "driving_score"].between(1, 100).all()
              and ((s_.loc[scored, "earned_discount_pct"] == rule[scored]) | (s_.loc[scored, "earned_discount_pct"] == 0)).all(),
              f"{len(s_):,} scores, mean {s_['driving_score'].mean():.1f}, average earned discount {s_['earned_discount_pct'].mean():.1f}%")
    # the device counts whole events over whole miles: each rate per 100 miles is a whole number of events over the
    # miles driven (none over none)
    whole = []
    for col in ("hard_brakes_per_100_miles", "rapid_accelerations_per_100_miles"):
        miles, rate = s_["miles_driven"].to_numpy(dtype=float), s_[col].to_numpy(dtype=float)
        events = np.round(rate * miles / 100)
        again = np.where(miles > 0, np.round(100 * events / np.maximum(miles, 1), 2), 0.0)
        whole.append(np.isclose(again, rate, rtol=0, atol=1e-9))
    rep.check("each hard-braking and rapid-acceleration rate is a whole number of events over the miles driven",
              bool(np.logical_and(*whole).all()),
              f"{(~whole[0]).sum():,} and {(~whole[1]).sum():,} rates that are not; "
              f"{(s_['hard_brakes_per_100_miles'] == 0).sum():,} periods without a hard brake")
    plug = e["device_type"].reindex(s_["enrollment_id"]).to_numpy() == "Plug-in Device"
    phone = s_["phone_use_minutes_per_100_miles"]
    rep.check("a plug-in device records no phone use and the other devices always do; any mileage takes a trip",
              phone[plug].isna().all() and phone[~plug].notna().all()
              and ((s_["miles_driven"] > 0) == (s_["trips"] > 0)).all(),
              f"{plug.sum():,} plug-in scores without phone use")
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
    rep.check("rows rated in the program belong to an enrollment that began by the row's start and was live when its term "
              "was offered; other rows carry no telematics discount",
              on["exposure_id"].isin(j.loc[ok, "exposure_id"]).all() and (risk.loc[risk["telematics_enrolled"] == "N", "telematics_discount_pct"] == 0).all()
              and risk["telematics_discount_pct"].between(0, 30).all())


def writeoff_known(veh, clm, feat) -> pd.DataFrame:
    """The day the company knew a car written off or wrecked had gone, where that was later than its removal: a car
    claimed here (a physical damage, rental or towing feature) is taken off once the claim is reported, its removal
    backdated to the day after the loss. One row per such car: insured_vehicle_id, removed_date and known (the
    claim's report date)."""
    gone = veh[veh["removal_reason"].isin(["Total Loss", "Destroyed or Stolen"])][["insured_vehicle_id", "removed_date"]]
    pdc = feat.loc[feat["coverage_code"].isin(["COLL", "COMP", "RENT", "TOW"]), "claim_id"]
    c = clm.loc[clm["claim_id"].isin(pdc), ["insured_vehicle_id", "loss_date", "report_date"]]
    c = c.assign(removed_date=(pd.to_datetime(c["loss_date"]) + pd.Timedelta(days=1)).dt.strftime("%Y-%m-%d"))
    hit = gone.merge(c, on=["insured_vehicle_id", "removed_date"])
    return hit.groupby(["insured_vehicle_id", "removed_date"])["report_date"].max().rename("known").reset_index()


def known_in_force(rows, day, gone_known=None) -> np.ndarray:
    """Which exposure rows (with every row of their terms) were in force on `day` (aligned with rows) as the company
    knew the policy then: rows rated by that day, and a row that ended at a change learned of later still running (a
    car written off before the day but reported after it, and the other cars' rows re-rated from the day after the
    loss once it was reported). A row's end is known when the term's rows starting where it ends were rated, or, with
    none, when its car was known to have gone (`gone_known`, by exposure row; otherwise its end)."""
    key = ["policy_term_id", "coverage_start_date"]
    nxt = rows.groupby(key)["rating_date"].min()
    succ = nxt.reindex(pd.MultiIndex.from_arrays([rows["policy_term_id"], rows["coverage_end_date"]])).to_numpy()
    end = rows["coverage_end_date"].to_numpy()
    if gone_known is not None:
        end = np.where(pd.isna(gone_known), end, gone_known)
    end_known = np.where(pd.isna(succ), end, succ)
    day = np.asarray(day)
    return ((rows["coverage_start_date"].to_numpy() <= day) & (rows["rating_date"].to_numpy() <= day)
            & ((rows["coverage_end_date"].to_numpy() > day) | (end_known > day)))


def integrity_renewals(rep, offers, term, risk, valuation, veh=None, clm=None, feat=None) -> None:
    """Renewal offers: each is dated inside its expiring term and made from the policy as it stood on the offer date,
    as the company knew it then (the expiring term's exposure rows in force that day, rated by then: a car written off
    before the offer but reported after it is still on it), and its outcome agrees with the policy terms."""
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
    # the snapshot: the vehicles and the premium in force on the offer date, as the company knew them that day
    cols = ["policy_term_id", "insured_vehicle_id", "coverage_start_date", "coverage_end_date", "rating_date", "total_premium"]
    r = risk[cols].merge(o[["renewal_offer_id", "expiring_policy_term_id", "offer_date"]], left_on="policy_term_id",
                         right_on="expiring_policy_term_id")
    gk = None
    if veh is not None:
        wk = writeoff_known(veh, clm, feat)
        gk = r[["insured_vehicle_id", "coverage_end_date"]].merge(
            wk, left_on=["insured_vehicle_id", "coverage_end_date"], right_on=["insured_vehicle_id", "removed_date"],
            how="left")["known"].to_numpy()
    held = known_in_force(r, r["offer_date"].to_numpy(), gk)
    later = held & (r["coverage_end_date"] <= r["offer_date"])
    r = r[held]
    g = r.groupby("renewal_offer_id").agg(n=("total_premium", "size"), prem=("total_premium", "sum")).reindex(o["renewal_offer_id"]).fillna(0)
    rep.check("each offer covers the vehicles in force on its offer date as the company then knew them, at the premium "
              "they were then insured for (a car written off before the offer and reported after it is still on it)",
              (g["n"].to_numpy() == o["vehicles_offered"].to_numpy()).all()
              and np.allclose(g["prem"].to_numpy(), o["expiring_premium"].to_numpy(), atol=0.05),
              f"{(o['vehicles_offered'] == 0).sum():,} offers with no vehicle on the policy that day (a replacement to come); "
              f"{later.sum():,} rows ended by a change learned of after the offer")
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
    rep.check("an offer ends 'Canceled Before Renewal' exactly when its expiring term was canceled after the offer date",
              ((o["outcome"] == "Canceled Before Renewal").to_numpy() == cx).all()
              and (exp.loc[cx, "cancel_date"].to_numpy() > o.loc[cx, "offer_date"].to_numpy()).all())
    pending = o["outcome"] == "Pending"
    company = o["underwriting_decision"] == "Non-Renew"
    rep.check("a renewal is pending only when it takes effect after the valuation date; a company non-renewal is never "
              "sent a telematics offer or a revision",
              (o.loc[pending, "renewal_effective_date"] > val).all() and (ren["renewal_effective_date"] <= val).all()
              and (company == (o["outcome"] == "Company Non-Renewal") | (company & (o["outcome"] == "Canceled Before Renewal"))).all()
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
    rep.check("underinsured motorist claims arise only on policies whose uninsured motorist limits are above the "
              "25/50 minimum (215 ILCS 5/143a-2(4))", not (uim & (f["um_limit"] == "25/50")).any(),
              f"{uim.sum():,} underinsured features: {f.loc[uim, 'um_limit'].value_counts().to_dict()}")
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


def integrity_reserve_sharing(rep, f, pay, reserves) -> None:
    """At the end of every day with a payment or reserve change, an accident's injury claimants under one coverage
    have been paid, and are reserved for, no more than the coverage's per-accident limit in total (for underinsured
    motorist, less what the at-fault driver's insurer paid). `f` is the coverage features joined to their risk rows."""
    cent = 0.005
    inj = f[f["coverage_code"].isin(["BI", "UM"])].copy()
    inj["g"] = inj.groupby(["claim_id", "coverage_code"]).ngroup()
    inj = inj[inj.groupby("g")["claim_feature_id"].transform("size") > 1]
    lim = np.where(inj["coverage_code"] == "BI", inj["bi_limit"].str.split("/").str[1].astype(float) * 1000,
                   inj["um_limit"].str.split("/").str[1].astype(float) * 1000)
    limit = pd.Series(lim, index=inj.index).groupby(inj["g"]).first() \
        - inj["other_insurer_payment"].fillna(0).groupby(inj["g"]).sum()
    group = inj.set_index("claim_feature_id")["g"]
    r = reserves[(reserves["reserve_type"] == "Loss") & reserves["claim_feature_id"].isin(group.index)]
    r = r.sort_values(["claim_feature_id", "transaction_date", "reserve_transaction_id"], kind="stable") \
        .groupby(["claim_feature_id", "transaction_date"])["outstanding_reserve"].last()
    p = pay[(pay["payment_type"] == "Loss") & pay["claim_feature_id"].isin(group.index)] \
        .groupby(["claim_feature_id", "payment_date"])["amount"].sum()
    p.index.names = r.index.names
    st = pd.concat([r.rename("out"), p.rename("pay")], axis=1).reset_index().rename(columns={"transaction_date": "date"})
    st["g"] = st["claim_feature_id"].map(group).to_numpy()
    grid = st[["g", "date"]].drop_duplicates().merge(st[["g", "claim_feature_id"]].drop_duplicates(), on="g")
    grid = grid.merge(st, on=["g", "claim_feature_id", "date"], how="left").sort_values(["claim_feature_id", "date"])
    grid["paid"] = grid["pay"].fillna(0).groupby(grid["claim_feature_id"]).cumsum()
    grid["out"] = grid.groupby("claim_feature_id")["out"].ffill().fillna(0)
    tot = (grid["paid"] + grid["out"]).groupby([grid["g"], grid["date"]]).sum()
    over = tot > limit.reindex(tot.index.get_level_values(0)).to_numpy() + cent
    shared = tot.index.get_level_values(0).unique()
    full = (tot >= limit.reindex(tot.index.get_level_values(0)).to_numpy() - 1.0).groupby(level=0).any()
    rep.check("on every day, paid loss plus case reserve across an accident's injury claimants under one coverage stays "
              "within its per-accident limit", not over.any(),
              f"{len(shared):,} accidents with several claimants under one coverage; {full.sum():,} of them reserved or "
              f"paid up to the limit at some point; {over.sum():,} days over")


def integrity_records(rep, risk, veh, pay, stmt, quotes, inv, rec, vend, feat, reserves, offers, term) -> None:
    """Record-level consistency the audits of November 2026 asked for: discounts that match the policy as it stood,
    one firm of each kind per claim, keys in creation order and no leak of the outcome into a quote's number."""
    v = veh[["policy_id", "added_date", "removed_date"]].merge(risk[["exposure_id", "policy_id", "coverage_start_date",
                                                                     "multi_car_discount"]], on="policy_id")
    on = (v["added_date"] <= v["coverage_start_date"]) & ~(v["removed_date"] <= v["coverage_start_date"])
    cars = on.groupby(v["exposure_id"]).sum().reindex(risk["exposure_id"]).fillna(0).to_numpy()
    multi = (risk["multi_car_discount"] == "Y").to_numpy()
    rep.check("the multi-car discount is on a row only while the policy has two or more cars (a car totaled and not yet "
              "replaced does not count)", (cars[multi] >= 2).all(),
              f"{multi.sum():,} rows with the discount; {(cars[multi] < 2).sum():,} with fewer than two cars")
    firms = pay[pay["transaction_type"].isin(["DCC Expense", "A&O Expense"])]
    kind = vend.set_index("vendor_id")["vendor_type"].reindex(firms["vendor_id"]).to_numpy()
    per = firms.groupby([firms["claim_id"].to_numpy(), kind])["vendor_id"].nunique()
    rep.check("a claim uses one firm of each kind: one defense counsel, one bill review service, one appraiser",
              (per <= 1).all(), f"{len(per):,} claim and expense kinds")
    order = stmt.sort_values("statement_id")
    rep.check("agency statements are numbered in the order they were drawn up (by month), paid or not",
              pd.to_datetime(order["statement_month"] + "-01").is_monotonic_increasing,
              f"{stmt['payment_date'].isna().sum():,} unpaid")
    q = quotes.assign(rank=quotes.groupby("quote_date")["quote_id"].rank(pct=True))
    gap = q.loc[q["bound"] == "Y", "rank"].mean() - q.loc[q["bound"] == "N", "rank"].mean()
    rep.check("a quote's number says nothing about whether it bound: within a day bound and lost quotes are mixed",
              abs(gap) < 0.05, f"mean within-day rank of bound quotes less lost ones {gap:+.3f}")
    claims_open = feat[feat["feature_status"] == "Open"]
    fin = pay[pay["transaction_type"] == "Final Payment"].groupby("claim_feature_id")["payment_date"].min()
    settled = claims_open[claims_open["claim_feature_id"].isin(fin.index) & claims_open["reopen_date"].isna()]
    rev = reserves[(reserves["transaction_type"] == "Reserve Review") & (reserves["reserve_type"] == "Loss")]
    rev = rev.assign(fin=fin.reindex(rev["claim_feature_id"]).to_numpy(),
                     reo=feat.set_index("claim_feature_id")["reopen_date"].reindex(rev["claim_feature_id"]).to_numpy())
    after = (rev["transaction_date"] > rev["fin"]) & ~(rev["transaction_date"] >= rev["reo"])
    rep.check("a final payment settles a feature: no loss reserve is held, or reviewed, after it (until a reopening)",
              (settled["case_reserve"] == 0).all() and not after.any(),
              f"{len(settled):,} open features awaiting closure after their final payment")
    offers_ok = (offers["vehicles_offered"] >= 1).all() and (offers["renewal_premium"] > 0).all()
    rep.check("every renewal offer is for at least one car and a premium; every term has cars on it",
              offers_ok and term["policy_term_id"].isin(risk["policy_term_id"]).all(),
              f"{len(offers):,} offers, {len(term):,} terms")
    paid_in = rec.groupby("invoice_id")["amount"].sum()
    can = inv[inv["invoice_status"] == "Canceled"]["invoice_id"]
    rep.check("a canceled bill keeps no money: what was received on it was returned or refunded",
              (paid_in.reindex(can).fillna(0).abs() < 0.005).all(), f"{len(can):,} canceled bills")


def integrity_people(rep, pol, term, drv, inc) -> None:
    """Who is on a policy, and what the insurer learns about them, while they are on it."""
    d = drv.merge(pol[["policy_id", "named_insured_driver_id"]], on="policy_id")
    current = d[(d["driver_role"] == "Named Insured") & d["removed_date"].isna()]
    rep.check("a policy has one current named insured, the one it names (a deceased one keeps the role, removed)",
              current.groupby("policy_id").size().max() <= 1
              and (current["driver_id"] == current["named_insured_driver_id"]).all())
    dead = term[term["cancel_reason"] == "Insured Deceased"][["policy_id", "cancel_date"]]
    ni = dead.merge(pol[["policy_id", "named_insured_driver_id"]], on="policy_id").merge(
        drv[["driver_id", "removed_date", "removal_reason"]], left_on="named_insured_driver_id", right_on="driver_id")
    rep.check("every policy cancelled because its insured died shows that named insured as deceased on that day",
              ((ni["removal_reason"] == "Deceased") & (ni["removed_date"] == ni["cancel_date"])).all(), f"{len(ni):,} policies")
    adults = drv[drv["driver_role"].isin(["Named Insured", "Spouse", "Other Adult"])]
    joined_at = (pd.to_datetime(adults["added_date"]) - pd.to_datetime(adults["date_of_birth"])).dt.days / 365.25
    rep.check("adults join a policy at 18 or older, and no two drivers on a policy share a full name",
              (joined_at >= 18).all() and not drv.duplicated(["policy_id", "first_name", "last_name"]).any(),
              f"youngest adult on joining {joined_at.min():.2f}")
    # the last day each driver was insured here: their removal or the end of the policy's cover
    last = term.sort_values(["policy_id", "effective_date"]).groupby("policy_id").tail(1).set_index("policy_id")
    pol_end = last["cancel_date"].where(last["cancel_date"].notna(),
                                        last["expiration_date"].where(last["nonrenewal_reason"].notna(), "9999-12-31"))
    end = drv.set_index("driver_id")["removed_date"].fillna("9999-12-31")
    a, b = end.to_numpy().astype(str), pol_end.reindex(drv.set_index("driver_id")["policy_id"]).to_numpy().astype(str)
    end = np.where(a < b, a, b)
    end = pd.Series(end, index=drv["driver_id"].to_numpy())
    mvr = inc[inc["source"].isin(["Motor Vehicle Record", "Prior Carrier Report"])]
    late = mvr["known_date"].to_numpy().astype(str) > end.reindex(mvr["driver_id"]).to_numpy()
    sr = drv[drv["sr22_filed_date"].notna()]
    rep.check("violations and prior-carrier losses reach the insurer, and SR-22s are filed, only while the driver is "
              "insured here", not late.any() and (sr["sr22_filed_date"].to_numpy().astype(str) <= end.reindex(sr["driver_id"]).to_numpy()).all(),
              f"{len(mvr):,} driving-record violations and prior-carrier losses, {len(sr):,} SR-22 filings")


def integrity_links(rep, risk, term, veh, drv, clm, feat, pay, reserves) -> None:
    """Every key points to an existing row, and keys that a row carries more than once (a claim's policy and its
    exposure row's policy, a payment's claim and its feature's claim) agree. A key can exist and still name the
    wrong record, so agreement is checked as well as existence."""
    rep.check("risk rows reference valid policy terms", risk["policy_term_id"].isin(term["policy_term_id"]).all())
    rep.check("risk rows reference valid vehicles and drivers", risk["insured_vehicle_id"].isin(veh["insured_vehicle_id"]).all()
              and risk["driver_id"].isin(drv["driver_id"]).all())
    t = term.set_index("policy_term_id")
    v = veh.set_index("insured_vehicle_id")
    rep.check("each risk row's policy is its term's and its vehicle's policy",
              (t["policy_id"].reindex(risk["policy_term_id"]).to_numpy() == risk["policy_id"].to_numpy()).all()
              and (v["policy_id"].reindex(risk["insured_vehicle_id"]).to_numpy() == risk["policy_id"].to_numpy()).all())
    rep.check("claims reference valid risk rows", clm["exposure_id"].isin(risk["exposure_id"]).all())
    c = clm.merge(risk[["exposure_id", "policy_id", "policy_term_id", "insured_vehicle_id", "vehicle_model_year_id"]],
                  on="exposure_id", how="left", suffixes=("", "_r"))
    rep.check("claim policy, term, vehicle and model year match the risk row",
              len(c) == len(clm) and (c["policy_id"] == c["policy_id_r"]).all()
              and (c["policy_term_id"] == c["policy_term_id_r"]).all()
              and (c["insured_vehicle_id"] == c["insured_vehicle_id_r"]).all()
              and (c["vehicle_model_year_id"] == c["vehicle_model_year_id_r"]).all())
    rep.check("features, payments and reserve changes reference valid claims and features",
              feat["claim_id"].isin(clm["claim_id"]).all() and pay["claim_feature_id"].isin(feat["claim_feature_id"]).all()
              and reserves["claim_feature_id"].isin(feat["claim_feature_id"]).all())
    f = feat.set_index("claim_feature_id")["claim_id"]
    rep.check("each payment's and reserve change's claim is its feature's claim",
              (f.reindex(pay["claim_feature_id"]).to_numpy() == pay["claim_id"].to_numpy()).all()
              and (f.reindex(reserves["claim_feature_id"]).to_numpy() == reserves["claim_id"].to_numpy()).all())


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

    # the policy as it stands: its status is its latest term's; on the valuation date if in force, else on its last
    # day of cover, the cars its exposure rows cover are the cars the vehicle table lists
    latest = term.assign(es=dt(term["effective_date"])).sort_values(["policy_id", "es"], kind="stable").groupby("policy_id").tail(1) \
        .set_index("policy_id").reindex(pol["policy_id"])
    status = np.where(latest["cancel_date"].notna(), "Canceled", np.where(latest["nonrenewal_reason"].notna(), "Non-Renewed", "In Force"))
    rep.check("each policy's status is its latest term's (canceled, not renewed or in force)",
              (pol["policy_status"].to_numpy() == status).all(), f"{pol['policy_status'].value_counts().to_dict()}")
    end = dt(latest["cancel_date"].fillna(latest["expiration_date"])).to_numpy()
    as_at = np.where(status == "In Force", valuation.to_datetime64(), end - np.timedelta64(1, "D"))
    as_at = pd.Series(np.minimum(as_at, valuation.to_datetime64()), index=pol["policy_id"].to_numpy())
    day = as_at.reindex(risk["policy_id"]).to_numpy()
    covered = risk[(cov_s.to_numpy() <= day) & (cov_e.to_numpy() > day)].groupby("policy_id")["insured_vehicle_id"].nunique()
    day = as_at.reindex(veh["policy_id"]).to_numpy()
    listed = veh[(dt(veh["added_date"]).to_numpy() <= day) & ~(dt(veh["removed_date"]).to_numpy() <= day)].groupby("policy_id").size()
    count = lambda g: g.reindex(pol["policy_id"]).fillna(0).to_numpy()
    in_force = (status == "In Force")
    rep.check("the cars covered at each policy's latest status are the cars the vehicle table lists on it then",
              (count(covered) == count(listed)).all(),
              f"{count(covered)[in_force].sum():,.0f} vehicles on {in_force.sum():,} policies in force, "
              f"{(count(covered)[in_force] == 0).sum():,} of them waiting for a replacement car")
    at_start = cov_s.to_numpy() == dt(term.set_index("policy_term_id")["effective_date"]).reindex(risk["policy_term_id"]).to_numpy()
    rep.check("a term's first exposure rows (endorsement 0) are the ones starting on its effective date",
              ((risk["endorsement_number"] == 0) == at_start).all())

    # information timing: every rated record is exactly the incidents with a known date on or before the
    # row's rating date (the term's rating date, before it takes effect, or the day of a mid-term change),
    # dated in the three years up to the row's cover start. Dates carry no time of day, so the order of
    # events on one day is fixed by convention: a known date of D means usable by any rating dated D or
    # later, and the company's own claim is known the day after the payment that makes it chargeable, so a
    # loss or payment on the rating date itself is never part of that rating.
    t = term.set_index("policy_term_id")
    eff, rdate = dt(t["effective_date"]), dt(t["rating_date"])
    rep.check("every term is offered, then rated, before it takes effect", (dt(t["offer_date"]) <= rdate).all()
              and (rdate <= eff).all(),
              f"{(dt(t['offer_date']) < rdate).sum():,} renewals re-rated after a change between offer and effective date")
    # a renewal or endorsement is rated with the household as it stood that day: its car and rated driver are
    # already on the policy, and its address is the one in force (new business is quoted before its first day)
    later = (risk["endorsement_number"] > 0) | (t["business_type"].reindex(risk["policy_term_id"]).to_numpy() == "Renewal")
    r_ = risk[later]
    # (a row re-rated after a car's backdated removal is rated later than it starts, for the household of its own
    # period: judged as of its start)
    rated = np.minimum(dt(r_["rating_date"]).to_numpy(), dt(r_["coverage_start_date"]).to_numpy())
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
    # a rated age is the driver's age in completed years on the day the row starts, and the class is filed by it
    ra = risk[["rated_driver_age", "rated_driver_class", "coverage_start_date", "driver_id"]].merge(
        drv[["driver_id", "date_of_birth"]], on="driver_id", how="left")
    want = completed_age(ra["coverage_start_date"], ra["date_of_birth"])
    band = ra["rated_driver_class"].str.split(" ").str[0].map(CLASS_AGES)
    lo, hi = band.str[0].to_numpy(dtype=float), band.str[1].to_numpy(dtype=float)
    rep.check("each row's rated age is its driver's completed age on the day the row starts, and its class is the "
              "filed class for that age (a driver moves class on the birthday)",
              bool((ra["rated_driver_age"].to_numpy() == want).all()
                   and ((ra["rated_driver_age"] >= lo) & (ra["rated_driver_age"] <= hi)).all()),
              f"{(ra['rated_driver_age'].to_numpy() != want).sum():,} rows whose age is not; "
              f"{(~((ra['rated_driver_age'] >= lo) & (ra['rated_driver_age'] <= hi))).sum():,} outside their class")
    in_force = drv["policy_id"].isin(pol.loc[pol["policy_status"] == "In Force", "policy_id"])
    known = drv[drv["removed_date"].notna() | in_force]
    last_day = np.where(known["removed_date"].notna(), known["removed_date"], str(valuation.date()))
    age_then = completed_age(last_day, known["date_of_birth"])
    rep.check("a driver's good-student status is as of their last day insured (by the valuation date), as the rest "
              "of the driver record", not ((known["good_student"] == "Y") & (age_then >= 25)).any())

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

    # premium: written + endorsements + returns = earned before the extract + earned in it, for terms finished long
    # enough before the valuation date that every change to them has been processed (premium_transaction holds only
    # transactions processed by then)
    ended = dt(term["cancel_date"].fillna(term["expiration_date"]))
    done = ended <= valuation - pd.Timedelta(days=90)
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
    adjustment expense. Collision and comprehensive are restricted to risk rows with a $500 deductible, are net
    of the year's salvage and subrogation recoveries (see BENCHMARK), and comprehensive leaves out wind and water
    losses. What still differs is printed with the table."""
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
        kinds = ["Loss", "Expense"] if k in ("BI", "PD") else ["Loss", "Salvage Recovery", "Subrogation Recovery"]
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
                note = "   (not held: short of payments on accidents before the warm-up year)"
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
    print("  single-carrier benchmark. The first calendar year has payments on the year before (the warm-up) but none on")
    print("  earlier accidents, which matters for bodily injury. Glass claims under full glass cover carry no deductible here. The table's")
    print("  claim-counting rules (per claimant or per accident, and when a claim counts as paid) are not published, nor")
    print("  is its treatment of salvage and subrogation: they are taken off collision and comprehensive payments here.")


def illinois(rep, risk, s, e) -> None:
    """Average premium per insured car-year by coverage and physical damage take-up, against Illinois (NAIC)."""
    cols = {"liability": ["bi_premium", "pd_premium", "um_premium", "med_pay_premium"], "collision": ["collision_premium"],
            "comprehensive": ["comprehensive_premium"]}
    days = np.maximum((e - s).astype("timedelta64[D]").astype(int), 0)
    earned_share = (risk["earned_premium"] / risk["total_premium"].where(risk["total_premium"] > 0)).fillna(0).to_numpy()
    print("  average premium per insured car-year against Illinois (NAIC Auto Insurance Database):")
    for k, c in cols.items():
        prem, has = risk[c].sum(axis=1).to_numpy() * earned_share, (risk[c].sum(axis=1) > 0).to_numpy()
        rate = np.divide(prem, days, out=np.zeros(len(risk)), where=days > 0)
        ours, theirs = 0.0, 0.0
        for y, state in ILLINOIS[k].items():
            a, b = np.datetime64(f"{y}-01-01"), np.datetime64(f"{y + 1}-01-01")
            overlap = (np.minimum(e, b) - np.maximum(s, a)).astype("timedelta64[D]").astype(int).clip(0)
            cy = (overlap * has).sum() / 365.25
            if cy == 0:
                continue
            ours, theirs = ours + (overlap * rate).sum(), theirs + state * cy
            print(f"    {k:14s}{y}: ${(overlap * rate).sum() / cy:7,.0f}   Illinois ${state:7,.0f}   ratio {(overlap * rate).sum() / cy / state:.2f}")
        if theirs:
            rep.band(f"{k} premium per insured car-year relative to Illinois, {min(ILLINOIS[k])}-{max(ILLINOIS[k])}", ours / theirs,
                     ILLINOIS_PREMIUM_BAND[k])
    a, b = np.datetime64("2023-01-01"), np.datetime64("2024-01-01")
    overlap = (np.minimum(e, b) - np.maximum(s, a)).astype("timedelta64[D]").astype(int).clip(0)
    if overlap.sum():
        for k, state in ILLINOIS_TAKE_UP.items():
            share = (overlap * (risk[cols[k][0]] > 0)).sum() / overlap.sum()
            rep.check(f"share of 2023 car-years carrying {k} ({share:.1%}) against Illinois ({state:.1%})",
                      ILLINOIS_TAKE_UP_BAND[0] <= share - state <= ILLINOIS_TAKE_UP_BAND[1], statistical=True)


def market_cycle(rep, quotes, term, clm, offers, plan_changes, valuation) -> None:
    """What the market model leaves in the data: seasonal shopping, conversion that dips after the company's own
    rate increases, customers who leave after a claim, and the company's own non-renewals."""
    q = quotes.assign(month=quotes["quote_date"].str[5:7].astype(int), bound=quotes["bound"] == "Y")
    full = q[q["quote_date"].str[:4].isin(q["quote_date"].str[:4].value_counts().loc[lambda n: n > 0].index)]
    by_month = full.groupby("month").size()
    if len(by_month) == 12:
        rep.band("quotes in February to April relative to October to December", by_month[[2, 3, 4]].sum() / by_month[[10, 11, 12]].sum(),
                 (1.08, 1.40))
    qd = pd.to_datetime(q["quote_date"])
    before = after = n_before = n_after = 0
    for d, chg in plan_changes:
        d = pd.Timestamp(d)
        if chg < 5 or d - pd.Timedelta(days=75) < qd.min() or d + pd.Timedelta(days=75) > pd.Timestamp(valuation):
            continue
        b, a = q[(qd >= d - pd.Timedelta(days=75)) & (qd < d - pd.Timedelta(days=15))], q[(qd >= d) & (qd < d + pd.Timedelta(days=60))]
        before, n_before, after, n_after = before + b["bound"].sum(), n_before + len(b), after + a["bound"].sum(), n_after + len(a)
    if n_before and n_after:
        print(f"  quote conversion in the two months before a rate increase of 5% or more {before / n_before:.1%}, in the two months after {after / n_after:.1%}")
        rep.band("conversion after a rate increase relative to before it", (after / n_after) / (before / n_before), (0.60, 0.92))
    ended = term[pd.to_datetime(term["cancel_date"].fillna(term["expiration_date"])) <= pd.Timestamp(valuation)]
    lost = ended["cancel_date"].notna() | ended["nonrenewal_reason"].notna()
    years = (pd.to_datetime(ended["cancel_date"].fillna(ended["expiration_date"])) - pd.to_datetime(ended["effective_date"])).dt.days / 365.25
    had = ended["policy_term_id"].isin(clm["policy_term_id"])
    ann = lambda m: 1 - np.exp(-lost[m].sum() / years[m].sum())
    print(f"  policies lost per year: {ann(had):.1%} of terms with a claim, {ann(~had):.1%} of terms without")
    # a real motor portfolio lost contracts with a claim 1.45 times as often (docs/real_data_comparison.md)
    rep.band("terms with a claim end the policy more often than terms without (ratio)", ann(had) / ann(~had), (1.20, 1.70))
    out = offers["outcome"].value_counts()
    share = out.get("Company Non-Renewal", 0) / max(out.get("Company Non-Renewal", 0) + out.get("Insured Did Not Renew", 0), 1)
    rep.band("share of non-renewals that are the company's decision", share, (0.03, 0.15), "{:.1%}")


def integrity_audit_records(rep, t: dict, valuation) -> None:
    """Record-level consistency found by the audit of the merged PR #16 (each is a check of what the records say
    together): payees and vendors, bills and refunds, reserves after a close or a supplement, endorsements,
    drivers at inception, quotes, crash deaths, the vehicle snapshot and the catalog."""
    pol, term, risk, drv, veh = t["policy"], t["policy_term"], t["exposure"], t["driver"], t["insured_vehicle"]
    clm, feat, pay, res = t["claim"], t["claim_feature"], t["claim_payment"], t["claim_reserve_transaction"]
    inv, rec, ledger, contact, vend = t["billing_invoice"], t["billing_receipt"], t["premium_transaction"], t["customer_contact"], t["vendor"]
    offers, quotes, vmy = t["renewal_offer"], t["quote"], t["vehicle_model_year"]
    V = str(np.datetime64(valuation, "D"))
    cov = feat.set_index("claim_feature_id")["coverage_code"]
    loss = pay[pay["payment_type"] == "Loss"]

    # medical payments go to the medical provider or to the person (their estate, once they have died)
    med = loss[loss["claim_feature_id"].map(cov).eq("MED")]
    vshare = (med["payee_type"] == "Vendor").mean() if len(med) else np.nan
    mp = vend.loc[vend["vendor_type"] == "Medical Provider", "vendor_id"]
    rep.check("medical payments are paid to medical providers or the injured person, never jointly with an attorney",
              len(med) < 200 or (pay["vendor_id"].isin(mp).any() and 0.35 <= vshare <= 0.85
                                 and not med["payee_type"].isin(["Insured and Attorney", "Claimant and Attorney"]).any()),
              f"{len(med):,} medical payments, {vshare:.0%} to a provider" if len(med) else "none")
    # no vendor type is all one vendor
    pv = pay.dropna(subset=["vendor_id"]).merge(vend[["vendor_id", "vendor_type"]], on="vendor_id")
    top = pv.groupby("vendor_type")["vendor_id"].agg(lambda x: x.value_counts(normalize=True).iloc[0])
    big = pv.groupby("vendor_type").size()
    n_v = vend.groupby("vendor_type").size()
    # (rentals excepted: an insurer bills most replacement rentals directly through one main rental company)
    worst = top[(big >= 200) & (n_v.reindex(top.index) >= 6) & (top.index != "Rental Company")]
    rep.check("no vendor trade is all one vendor: where a trade has six or more vendors, none takes three quarters of its "
              "work (rentals, mostly with one main rental company, apart)",
              bool((worst <= 0.75).all()), f"largest share {worst.max():.0%} ({worst.idxmax()})" if len(worst) else "too few payments")
    # a payment to an estate is a cheque
    est = pay[pay["payee_name"].fillna("").str.startswith("Estate of ")]
    rep.check("a payment to an estate is by check", bool((est["payment_method"] == "Check").all()), f"{len(est):,} payments to an estate")

    # bills and cash: the first bill after the term is rated, a refund only once the cash received covers it, the
    # final balance only once any bank draft has come back, every cancellation in force by the valuation date booked
    first = inv[inv["invoice_type"].isin(["Paid in Full", "Down Payment"])].merge(term[["policy_term_id", "rating_date"]], on="policy_term_id")
    paid = inv[inv["paid_date"].notna()]
    cum = rec.groupby(["policy_term_id", "receipt_date"])["amount"].sum().groupby(level=0).cumsum()
    fb = inv[inv["invoice_type"] == "Final Balance"].groupby("policy_term_id")["issue_date"].min()
    back = rec[rec["receipt_type"] == "Returned Payment"].groupby("policy_term_id")["receipt_date"].max()
    both = pd.concat([fb, back], axis=1, keys=["fb", "back"]).dropna()
    gone = term[term["cancel_date"].notna() & (term["cancel_date"] <= V)]
    booked = gone["policy_term_id"].isin(ledger.loc[ledger["transaction_type"] == "Cancellation", "policy_term_id"])
    rep.check("a term's first bill goes out on or after its rating date (a revised renewal bills its revised premium), and "
              "no bill is paid before it is sent", bool((first["issue_date"] >= first["rating_date"]).all()
                                                        and (paid["paid_date"] >= paid["issue_date"]).all()),
              f"{len(first):,} first bills")
    rep.check("a term's cash received never goes below zero (a refund goes out once what was paid covers it), and a final "
              "balance is billed only after any returned bank draft", bool((cum >= -0.01).all() and (both["fb"] > both["back"]).all()),
              f"lowest running balance ${cum.min():,.2f}; {len(both):,} final balances after a returned draft")
    rep.check("every cancellation in effect by the valuation date is booked in the premium ledger",
              bool(booked.all()), f"{len(gone):,} cancellations, {(~booked).sum():,} not booked")

    # reserves: none after a supplemental payment settles a reopening, no expense reserve on a closed feature
    sup = pay[pay["transaction_type"] == "Supplemental Payment"].groupby("claim_feature_id")["payment_date"].max()
    lr = res[(res["reserve_type"] == "Loss") & res["claim_feature_id"].isin(sup.index)]
    after = lr[lr["transaction_date"] >= lr["claim_feature_id"].map(sup)]
    held = after.sort_values(["claim_feature_id", "transaction_date", "reserve_transaction_id"]).groupby("claim_feature_id").tail(1)
    er = res[res["reserve_type"] == "Expense"].sort_values(["claim_feature_id", "transaction_date", "reserve_transaction_id"])
    first_close = res[(res["reserve_type"] == "Loss") & (res["transaction_type"] == "Close")].groupby("claim_feature_id")["transaction_date"].min()
    er = er[er["claim_feature_id"].isin(first_close.index)]
    e_at = er[er["transaction_date"] <= er["claim_feature_id"].map(first_close)].groupby("claim_feature_id").tail(1)
    closed = feat.loc[feat["feature_status"] == "Closed", "expense_reserve"]
    rep.check("a supplemental payment settles a reopening (no loss reserve after it), and a feature holds no expense "
              "reserve once closed", bool((held["outstanding_reserve"] == 0).all() and (e_at["outstanding_reserve"] == 0).all()
                                          and (closed == 0).all()),
              f"{len(sup):,} supplements; {len(e_at):,} litigated features closed")

    # endorsements record their change; a revised offer is known by the valuation date
    e_rows = risk[risk["endorsement_number"] > 0]
    e_tx = ledger[ledger["transaction_type"] == "Endorsement"]
    rep.check("every endorsement records its change (no period ends at a change that did not happen)",
              bool(e_rows["change_reason"].notna().all() and e_tx["change_reason"].notna().all()),
              f"{len(e_tx):,} endorsements, {e_rows['change_reason'].isna().sum():,} rows without a reason")
    rep.check("a revised renewal offer is dated by the valuation date",
              bool((offers["revised_offer_date"].dropna() <= V).all()), f"{offers['revised_offer_date'].notna().sum():,} revised offers")

    # injuries: a claim closed without payment is an alleged soft-tissue injury; a fatal crash has a police report
    loss_paid = loss.groupby("claim_feature_id")["amount"].sum()
    inj = feat[feat["coverage_code"].isin(["BI", "UM", "MED"]) & (feat["feature_status"] == "Closed")]
    unpaid = inj[inj["claim_feature_id"].map(loss_paid).fillna(0) <= 0.005]
    fatal = clm[clm["claim_id"].isin(feat.loc[feat["injury_type"] == "Fatality", "claim_id"])]
    rep.check("an injury claim closed without payment is an alleged soft-tissue injury, and a crash that killed someone "
              "has a police report", bool((unpaid["injury_type"] == "Soft Tissue").all() and (fatal["police_report"] == "Y").all()),
              f"{len(unpaid):,} injury features closed without payment, {len(fatal):,} fatal crashes")
    # no rental after a crash that killed every driver of the household
    own = feat.dropna(subset=["injured_driver_id"])
    died = own[own["injury_type"] == "Fatality"].groupby("claim_id")["injured_driver_id"].nunique()
    c = clm[clm["claim_id"].isin(died.index)][["claim_id", "policy_id", "loss_date"]]
    on = c.merge(drv[["driver_id", "policy_id", "added_date", "removed_date"]], on="policy_id")
    on = on[(on["added_date"] <= on["loss_date"]) & ~(on["removed_date"] < on["loss_date"])]
    n_on = on.groupby("claim_id").size()
    all_dead = died[died >= n_on.reindex(died.index).fillna(0)].index
    rent = feat[(feat["coverage_code"] == "RENT") & feat["claim_id"].isin(all_dead)]
    rep.check("no rental car is paid after a crash that killed every driver of the household",
              len(rent) == 0, f"{len(all_dead):,} crashes that left no driver")

    # people: the first driver is the named insured, an adult and licensed when the policy was first written
    d1 = drv[drv["driver_number"] == 1].merge(pol[["policy_id", "original_inception_date"]], on="policy_id")
    dob = pd.to_datetime(d1["date_of_birth"])
    age = (pd.to_datetime(d1["original_inception_date"]) - dob).dt.days / 365.25
    rep.check("each policy's first driver joined it at its inception, licensed and at least 18",
              bool((d1["added_date"] == d1["original_inception_date"]).all() and (d1["date_first_licensed"] <= d1["original_inception_date"]).all()
                   and (age >= 18).all()), f"{len(d1):,} policies; youngest first driver {age.min():.1f} at inception")
    rep.check("a quote's youngest driver is no older than its named insured (the same person on a one-driver quote)",
              bool((quotes["youngest_driver_age"] <= quotes["named_insured_age"]).all()
                   and (quotes.loc[quotes["number_of_drivers"] == 1, "youngest_driver_age"]
                        == quotes.loc[quotes["number_of_drivers"] == 1, "named_insured_age"]).all()), f"{len(quotes):,} quotes")

    # cars: every car insured has a row; its main driver is the one on its last row; a multi-car discount lasts only
    # while the policy has another car
    rows = risk[risk["coverage_start_date"] <= V].sort_values(["insured_vehicle_id", "coverage_start_date", "exposure_id"])
    lastrow = rows.groupby("insured_vehicle_id").tail(1).set_index("insured_vehicle_id")["driver_id"]
    rep.check("every insured vehicle has exposure, and its main driver is the driver on its latest exposure row",
              bool(veh["insured_vehicle_id"].isin(risk["insured_vehicle_id"]).all()
                   and (veh.set_index("insured_vehicle_id")["primary_driver_id"].reindex(lastrow.index) == lastrow).all()),
              f"{len(veh):,} vehicles")
    y = risk.loc[risk["multi_car_discount"] == "Y", ["exposure_id", "policy_id", "insured_vehicle_id", "coverage_end_date"]]
    other = risk[["policy_id", "insured_vehicle_id", "coverage_start_date", "coverage_end_date"]].rename(
        columns={"insured_vehicle_id": "insured_vehicle_id_o", "coverage_start_date": "coverage_start_date_o",
                 "coverage_end_date": "coverage_end_date_o"})
    m = y.merge(other, on="policy_id")
    lastday = (pd.to_datetime(m["coverage_end_date"]) - pd.Timedelta(days=1)).dt.strftime("%Y-%m-%d")
    m = m[(m["insured_vehicle_id_o"] != m["insured_vehicle_id"]) & (m["coverage_start_date_o"] <= lastday) & (m["coverage_end_date_o"] > lastday)]
    alone = ~y["exposure_id"].isin(m["exposure_id"])
    rep.check("a multi-car discount lasts only while the policy has another car (a car written off ends it that day)",
              not alone.any(), f"{len(y):,} multi-car rows, {alone.sum():,} with no other car on their last day")

    # contacts after a policy ended with its insured's death are letters to the estate
    dead = term[term["cancel_reason"] == "Insured Deceased"].groupby("policy_id")["cancel_date"].max()
    late = contact[contact["policy_id"].isin(dead.index)]
    late = late[late["contact_date"] >= late["policy_id"].map(dead)]
    rep.check("after a policy ends with its insured's death, contacts are letters to the estate, with no notice of "
              "cancellation or change confirmation", bool((late["contact_method"] == "Written Letter").all()
                                                          and not late.loc[late["contact_date"] > late["policy_id"].map(dead), "purpose"]
                                                          .isin(["Notice of Cancellation", "Policy Change Confirmation"]).any()),
              f"{len(late):,} contacts after such a cancellation")

    # one claim's subrogation comes back together: the repair, the rental and the tow
    sub = pay[pay["payment_type"] == "Subrogation Recovery"].assign(cov=lambda d: d["claim_feature_id"].map(cov))
    sub = sub[sub["claim_feature_id"].isin(feat.loc[feat["reopen_date"].isna(), "claim_feature_id"])]
    firsts = sub.groupby(["claim_id", "cov"])["payment_date"].min().unstack()
    pair = [c for c in ("RENT", "TOW") if c in firsts and "COLL" in firsts]
    same = all((firsts.dropna(subset=["COLL", c])[c] == firsts.dropna(subset=["COLL", c])["COLL"]).all() for c in pair)
    rep.check("a claim's subrogation is recovered together: the rental and the tow with the repair", bool(same),
              ", ".join(f"{len(firsts.dropna(subset=['COLL', c])):,} claims with {c}" for c in pair) or "none")

    # the catalog gives every combustion model year its engine
    gas = vmy[~vmy["fuel_type"].isin(["Electric", "Hydrogen"])]
    rep.check("every combustion model year in the catalog has its engine (cylinders and displacement)",
              bool(gas[["engine_cylinders", "engine_displacement_l"]].notna().all().all()), f"{len(gas):,} model years")


def integrity_audit_v119(rep, t: dict, valuation, out: Path = None) -> None:
    """Record-level consistency found by the audit of v1.1.9: a write-off is removed (backdated) only once the
    company knows of it; occasional youthful operators; marital status on divorce; fatal crashes; endorsement bills
    on a lapsing policy; contacts after a cancellation; company placement on the quote day; opening telematics
    enrollment dates; and a salvage car's later losses."""
    pol, term, risk, drv, veh = t["policy"], t["policy_term"], t["exposure"], t["driver"], t["insured_vehicle"]
    clm, feat, pay, ledger, contact = t["claim"], t["claim_feature"], t["claim_payment"], t["premium_transaction"], t["customer_contact"]
    inv, inc, enrol = t["billing_invoice"], t["driver_incident"], t["telematics_enrollment"]
    V = str(np.datetime64(valuation, "D"))
    nextday = lambda col: (pd.to_datetime(col) + pd.Timedelta(days=1)).dt.strftime("%Y-%m-%d")

    # a car written off or wrecked, claimed here, is taken off once the claim is reported: its removal is backdated
    # to the day after the loss, but booked, re-rated and cancelled no earlier than the report
    gone = veh[veh["removal_reason"].isin(["Total Loss", "Destroyed or Stolen"])][["insured_vehicle_id", "policy_id", "removed_date"]]
    # (a wreck claimed here only through liability features, presented later, is the customer taking it off)
    pdc = feat.loc[feat["coverage_code"].isin(["COLL", "COMP", "RENT", "TOW"]), "claim_id"]
    c = clm.loc[clm["claim_id"].isin(pdc), ["claim_id", "policy_id", "insured_vehicle_id", "loss_date", "report_date"]].assign(
        next_=lambda d: nextday(d["loss_date"]))
    hit = gone.merge(c, left_on=["insured_vehicle_id", "removed_date"], right_on=["insured_vehicle_id", "next_"], suffixes=("", "_c"))
    hit = hit.groupby(["policy_id", "removed_date"])["report_date"].max().reset_index()
    # (a cancellation for a death or for non-payment that day is not the removal's, and a car lost on a term's last
    # day is simply not renewed: the renewal was rated when it was offered)
    # (a cancellation is the removal's when the policy had no other car left that day)
    left_cars = veh[["policy_id", "added_date", "removed_date"]].merge(hit[["policy_id", "removed_date"]].rename(
        columns={"removed_date": "on"}), on="policy_id")
    left_cars = left_cars[(left_cars["added_date"] <= left_cars["on"]) & ~(left_cars["removed_date"] <= left_cars["on"])]
    emptied = hit[~pd.MultiIndex.from_frame(hit[["policy_id", "removed_date"]]).isin(
        pd.MultiIndex.from_frame(left_cars[["policy_id", "on"]]))][["policy_id", "removed_date"]]
    canc = ledger[(ledger["transaction_type"] == "Cancellation") & (ledger["change_reason"] == "Insured Request")].merge(
        emptied, left_on=["policy_id", "effective_date"], right_on=["policy_id", "removed_date"])[ledger.columns]
    tx = pd.concat([ledger[ledger["transaction_type"] == "Endorsement"], canc]).merge(
        hit, left_on=["policy_id", "effective_date"], right_on=["policy_id", "removed_date"])
    rr = risk.loc[risk["endorsement_number"] > 0, ["policy_id", "coverage_start_date", "rating_date"]].merge(
        hit, left_on=["policy_id", "coverage_start_date"], right_on=["policy_id", "removed_date"])
    path = (out / "answer_key" / "unreported_claim.csv") if out is not None else None
    unrep = pd.read_csv(path) if path is not None and path.exists() else pd.DataFrame(columns=["insured_vehicle_id", "loss_date", "coverage_code"])
    # (a car traded or sold the day after a loss its owner has not reported yet left for its own reason)
    u = unrep[unrep["coverage_code"].isin(["COLL", "COMP"])].merge(
        veh.loc[veh["removal_reason"].isin(["Total Loss", "Destroyed or Stolen"]) | veh["removal_reason"].isna(),
                ["insured_vehicle_id", "removed_date"]], on="insured_vehicle_id")
    early_known = u["removed_date"].notna() & (u["removed_date"] == nextday(u["loss_date"])) if len(u) else pd.Series([], dtype=bool)
    rep.check("a car lost in a physical damage claim is taken off, re-rated and booked only once the claim is reported "
              "(backdated), and one whose claim is not yet reported is still on the policy",
              bool((tx["processed_date"] >= tx["report_date"]).all() and (rr["rating_date"] >= rr["report_date"]).all()
                   and not early_known.any()), f"{len(hit):,} removals after a claim, {len(u):,} unreported physical damage claims")
    # rows are rated on or before they start, except a period re-rated by a write-off removal, rated on the report
    late = risk[risk["rating_date"] > risk["coverage_start_date"]]
    lt = late.merge(clm[["policy_id", "report_date", "loss_date"]], on="policy_id")
    ok = lt[(lt["report_date"] == lt["rating_date"]) & (lt["loss_date"] < lt["coverage_start_date"])]["exposure_id"].unique()
    rep.check("an exposure row is rated by the day it starts, unless it follows a car's backdated removal (rated the "
              "day the claim was reported)", bool(late["exposure_id"].isin(ok).all()), f"{len(late):,} rows rated after they start")

    # occasional youthful operator: one car a period, and only when a young listed driver has no car of their own
    key = ["policy_term_id", "endorsement_number"]
    oy = risk.groupby(key)["occasional_youthful_operator"].apply(lambda x: (x == "Y").sum())
    per = risk.drop_duplicates(key)[key + ["policy_id", "coverage_start_date"]]
    d = per.merge(drv[["driver_id", "policy_id", "date_of_birth", "added_date", "removed_date"]], on="policy_id")
    d = d[(d["added_date"] <= d["coverage_start_date"]) & ~(d["removed_date"] <= d["coverage_start_date"])]
    young = completed_age(d["coverage_start_date"], d["date_of_birth"]) < 25
    d = d[young].merge(risk[key + ["driver_id"]].drop_duplicates().assign(own=1), on=key + ["driver_id"], how="left")
    free = d[d["own"].isna()].groupby(key).size()
    want = pd.Series(pd.MultiIndex.from_frame(per[key]).isin(free.index), index=pd.MultiIndex.from_frame(per[key]))
    rep.check("an occasional youthful operator is charged on one car, and only when a listed driver under 25 has no car "
              "of their own", bool((oy <= 1).all() and ((oy.reindex(want.index) > 0) == want).all()),
              f"{(oy > 0).sum():,} periods charged, {int(want.sum()):,} with a young driver without a car")

    # marital status: a divorced spouse is divorced; a couple killed together leaves no widow
    div = drv[drv["removal_reason"] == "Divorce"]
    dead = drv[drv["removal_reason"] == "Deceased"]
    pair = dead.merge(dead, on=["policy_id", "removed_date"])
    pair = pair[pair["driver_id_x"] != pair["driver_id_y"]]
    rep.check("a spouse who leaves in a divorce is divorced, and a couple killed together leaves no widow",
              bool((div["marital_status"] == "D").all() and not (pair["marital_status_x"] == "W").any()),
              f"{len(div):,} divorces, {len(pair) // 2:,} couples killed together")

    # a crash whose driver died by the next day has a police report; a rental stops at the death of the only driver
    crash = clm[clm["cause_of_loss"].isin(["AF_MV", "AF_SV", "NAF"])].merge(
        dead[["driver_id", "removed_date"]], left_on="involved_driver_id", right_on="driver_id")
    nd = crash[crash["removed_date"] == nextday(crash["loss_date"])]
    ends = term[term["cancel_reason"] == "Insured Deceased"][["policy_id", "cancel_date"]]
    rent = feat[feat["coverage_code"] == "RENT"].merge(clm[["claim_id", "policy_id", "loss_date", "exposure_id"]], on="claim_id").merge(ends, on="policy_id")
    rent = rent[rent["cancel_date"] >= rent["loss_date"]].merge(risk[["exposure_id", "rental_reimbursement"]], on="exposure_id")
    # (only where no listed driver was left: a household member who survives may still need the car)
    on_loss = rent[["claim_id", "policy_id", "loss_date", "cancel_date"]].merge(drv[["policy_id", "added_date", "removed_date"]], on="policy_id")
    on_loss = on_loss[(on_loss["added_date"] <= on_loss["loss_date"]) & ~(on_loss["removed_date"] < on_loss["loss_date"])]
    survivor = on_loss[on_loss["removed_date"].isna() | (on_loss["removed_date"] > on_loss["cancel_date"])]["claim_id"].unique()
    rent = rent[~rent["claim_id"].isin(survivor)]
    loss = pay[pay["payment_type"] == "Loss"].groupby("claim_feature_id")["amount"].sum()
    paid = rent["claim_feature_id"].map(loss).fillna(0)
    days = (pd.to_datetime(rent["cancel_date"]) - pd.to_datetime(rent["loss_date"])).dt.days
    daily = rent["rental_reimbursement"].str.split("/").str[0].astype(float)
    rep.check("a crash whose driver died by the next day has a police report, and a rental stops when the household's "
              "only driver dies", bool((nd["police_report"] == "Y").all() and (paid <= days * daily + 0.01).all()),
              f"{len(nd):,} crashes with a death the next day, {len(rent):,} rentals on a policy ended by a death")

    # a lapsing policy pays no endorsement bill due after the installment it missed
    npt = term.loc[term["cancel_reason"] == "Non-Payment", "policy_term_id"]
    iv = inv[inv["policy_term_id"].isin(npt)]
    regular = iv[iv["invoice_type"].isin(["Installment", "Down Payment", "Paid in Full"])]
    missed = regular[regular["invoice_status"] != "Paid"].groupby("policy_term_id")["due_date"].min()
    after = iv[(iv["invoice_type"] != "Final Balance") & (iv["due_date"] >= iv["policy_term_id"].map(missed))]
    rep.check("a policy cancelled for non-payment pays no bill due after the installment it missed",
              bool((after["invoice_status"] != "Paid").all()), f"{len(npt):,} lapsed terms, {len(after):,} later bills")

    # contacts: no staff call on a Sunday or a holiday; nothing confirmed or chased once a policy is cancelled
    calls = contact[contact["contact_method"] == "Phone Call"]
    cdays = pd.to_datetime(calls["contact_date"])
    from pandas.tseries.holiday import USFederalHolidayCalendar
    observed = USFederalHolidayCalendar().holidays(cdays.min() - pd.Timedelta(days=7), cdays.max() + pd.Timedelta(days=7)) \
        if len(calls) else pd.DatetimeIndex([])
    # (the holidays themselves too: a Saturday New Year's Day is observed on the Friday, but no one calls that Saturday)
    fixed = calls["contact_date"].str[5:].isin(["01-01", "06-19", "07-04", "11-11", "12-25"]) & (cdays.dt.year >= 2021)
    hol = set(observed.strftime("%Y-%m-%d")) | set(calls.loc[fixed, "contact_date"])
    ended = term.dropna(subset=["cancel_date"]).groupby("policy_id")["cancel_date"].max()
    after_end = contact[contact["purpose"].isin(["Policy Change Confirmation", "Past Due Notice", "Notice of Cancellation"])]
    after_end = after_end[after_end["contact_date"] >= after_end["policy_id"].map(ended).fillna("9999")]
    rep.check("no staff call on a Sunday or a holiday, and no change confirmation, past-due notice or notice of "
              "cancellation once the policy is cancelled", bool(not ((cdays.dt.weekday == 6) | calls["contact_date"].isin(hol)).any()
                                                               and len(after_end) == 0),
              f"{len(calls):,} calls; {len(after_end):,} contacts after a cancellation")

    # a new policy is placed with its company on what the insurer knew on the quote day
    nb = term[term["business_type"] == "New"][["policy_id", "offer_date", "effective_date"]]
    p = pol.merge(nb, on="policy_id")
    first = drv.merge(p[["policy_id", "effective_date"]], on="policy_id")
    first = first[first["added_date"] <= first["effective_date"]][["driver_id", "policy_id"]]
    i = inc.merge(first, on="driver_id").merge(p[["policy_id", "offer_date"]], on="policy_id")
    back = (pd.to_datetime(i["offer_date"]) - pd.Timedelta(days=3 * 365)).dt.strftime("%Y-%m-%d")
    i = i[(i["incident_date"] <= i["offer_date"]) & (i["incident_date"] > back) & (i["known_date"] <= i["offer_date"])]
    pts = i["incident_type"].map({"Minor Violation": 1, "Major Violation": 4}).fillna(3).groupby(i["policy_id"]).sum()
    pts = p["policy_id"].map(pts).fillna(0).to_numpy()
    score, no_hit, prior = p["insurance_score"].to_numpy(), p["insurance_score"].isna().to_numpy(), (p["prior_insurance"] == "Y").to_numpy()
    weak = (score < 680) | no_hit | (pts >= 2)
    tier = np.where((pts >= 5) | ((score < 560) & ~no_hit) | (~prior & weak), "Non-Standard",
                    np.where((score >= 740) & ~no_hit & (pts == 0) & prior, "Preferred", "Standard"))
    placed = p["company_id"].map(t["underwriting_company"].set_index("company_id")["tier"]).to_numpy()
    rep.check("a new policy is placed with its company on the score, prior insurance and record known on its quote day",
              bool((placed == tier).all()), f"{len(p):,} new policies, {(placed != tier).sum():,} placed otherwise")

    # an enrollment begins with a term: the policy's effective date then (an earlier one, before the extract)
    e = enrol.merge(pol[["policy_id", "original_inception_date", "term_months"]], on="policy_id")
    a, b_ = pd.to_datetime(e["original_inception_date"]), pd.to_datetime(e["enrollment_date"])
    months = (b_.dt.year - a.dt.year) * 12 + (b_.dt.month - a.dt.month)
    day_ok = (b_.dt.day == a.dt.day) | (b_.dt.is_month_end & (b_.dt.day < a.dt.day))
    rep.check("a telematics enrollment begins on one of the policy's term effective dates",
              bool(((months % e["term_months"] == 0) & day_ok & (months >= 0)).all()), f"{len(e):,} enrollments")

    # a car its owner kept after a total loss has no further loss in that term
    kept = feat[feat["owner_retained_salvage"] == "Y"].merge(clm[["claim_id", "policy_term_id", "insured_vehicle_id", "loss_date"]], on="claim_id")
    more = kept.merge(clm[["claim_id", "policy_term_id", "insured_vehicle_id", "loss_date"]], on=["policy_term_id", "insured_vehicle_id"],
                      suffixes=("", "_later"))
    more = more[(more["loss_date_later"] > more["loss_date"]) | ((more["loss_date_later"] == more["loss_date"]) & (more["claim_id_later"] > more["claim_id"]))]
    rep.check("a car its owner kept after a total loss has no further loss in that term", len(more) == 0,
              f"{len(kept):,} owner-retained total losses")


def integrity_animal_drivers(rep, clm, risk, pol) -> None:
    """A collision with an animal happens while someone drives the car: its claim names one of the car's drivers, drawn
    as for other crashes, not the named insured by default."""
    x = clm[["claim_id", "policy_id", "exposure_id", "involved_driver_id", "cause_of_loss"]].merge(
        risk[["exposure_id", "driver_id"]], on="exposure_id").merge(pol[["policy_id", "named_insured_driver_id"]], on="policy_id")
    other = x[x["driver_id"] != x["named_insured_driver_id"]]          # cars mostly driven by someone else
    share = lambda cause: (other.loc[other["cause_of_loss"] == cause, "involved_driver_id"]
                           != other.loc[other["cause_of_loss"] == cause, "named_insured_driver_id"]).mean()
    n = int((other["cause_of_loss"] == "ANIMAL").sum())
    rep.check("a collision with an animal names the driver at the wheel, as other crashes do: on cars whose rated driver "
              "is not the named insured, most animal claims name someone other than the named insured",
              n == 0 or share("ANIMAL") > 0.5,
              f"{n:,} such animal claims, {share('ANIMAL'):.0%} naming another driver (not-at-fault crashes {share('NAF'):.0%})"
              if n else "no animal claims on such cars")


def integrity_ledger(rep, gl, acct, stmt, ledger, pol, term, inv, rec, pay, clm, feat, reserves, agency, start, valuation) -> None:
    """The general ledger balances and ties to the subledgers it summarizes."""
    j = gl.groupby("journal_number")[["debit", "credit"]].sum()
    rep.check("every journal entry balances, uses the chart of accounts and posts on one side of each line",
              ((j["debit"] - j["credit"]).abs() < 0.005).all() and gl["account_number"].isin(acct["account_number"]).all()
              and ((gl["debit"] >= 0) & (gl["credit"] >= 0) & ((gl["debit"] == 0) | (gl["credit"] == 0))).all()
              and gl["journal_number"].str.count("-").ge(4).all(), f"{len(j):,} journals, {len(gl):,} lines")
    opening, closing = gl["journal_type"] == "Opening balances", gl["journal_type"] == "Year-end closing"
    net = lambda rows: (rows["debit"] - rows["credit"]).groupby(rows["account_number"]).sum()
    activity, balance = net(gl[~opening & ~closing]), net(gl)
    get = lambda s_, a: float(s_.get(a, 0.0))
    booked = np.maximum(pd.to_datetime(ledger["effective_date"]).to_numpy(), pd.to_datetime(ledger["processed_date"]).to_numpy())
    inside = (booked >= start) & (booked <= valuation)
    close = lambda a, b, tol=0.05: abs(a - b) <= tol + 2e-9 * abs(b)
    income = acct.loc[acct["financial_statement"] == "Income statement", "account_number"]
    year = gl["accounting_period"].str[:4]
    closed = sorted(year[closing].unique())
    on_income = gl[gl["account_number"].isin(income) & year.isin(closed)]
    left = (on_income["debit"] - on_income["credit"]).groupby([year[on_income.index], on_income["company_id"]]).sum()
    moved = gl[closing & (gl["account_number"] == 3000)]
    # a year is closed on its 31 December and only once that day is in the extract: a year the valuation date falls in
    # (in December too) is left open, every year before it closed
    V = pd.Timestamp(valuation)
    want = [str(y) for y in range(pd.Timestamp(start).year, V.year + 1) if pd.Timestamp(f"{y}-12-31") <= V]
    rep.check("each year-end closes the year's income statement accounts to surplus, on 31 December, once for each "
              "company and only for years ended by the valuation date",
              (left.abs() < 0.005).all() and (gl.loc[closing, "accounting_period"].str[5:] == "12").all()
              and (gl.loc[closing, "posting_date"].str[5:] == "12-31").all() and closed == want
              and not gl[closing & (gl["account_number"] == 3000)].duplicated(["company_id", "accounting_period"]).any()
              and close(-(moved["debit"] - moved["credit"]).sum(),
                           -(gl.loc[~opening & ~closing & gl["account_number"].isin(income) & year.isin(closed), "debit"]
                             - gl.loc[~opening & ~closing & gl["account_number"].isin(income) & year.isin(closed), "credit"]).sum()),
              f"years closed {closed}; surplus at the valuation date ${-get(balance, 3000):,.0f}")
    rep.check("premiums written and commission expense in the ledger are the premium transactions booked in the extract "
              "(on the later of their effective and processed dates)",
              close(-get(activity, 4000), ledger.loc[inside, "written_premium"].sum(), 1.0)
              and close(get(activity, 6100), ledger.loc[inside, "commission_amount"].sum(), 1.0),
              f"written ${-get(activity, 4000):,.0f}, commission ${get(activity, 6100):,.0f}")
    earned = -(get(activity, 4000) + get(activity, 4010))
    rep.check("earned premium in the ledger (written less the change in unearned) is the earned premium of the policy terms",
              abs(earned - term["earned_premium"].sum()) <= 2e-5 * term["earned_premium"].sum(),
              f"${earned:,.0f} against ${term['earned_premium'].sum():,.0f}; unearned at the valuation date ${-get(balance, 2100):,.0f}")
    r_in = (pd.to_datetime(rec["receipt_date"]).to_numpy() >= start)
    p_ = pay[pd.to_datetime(pay["payment_date"]).to_numpy() >= start]        # earlier payments belong to earlier years
    kinds = p_.groupby("payment_type")["amount"].sum()
    paid_stmt = stmt[stmt["payment_date"].notna()]
    cash = rec.loc[r_in, "amount"].sum() - kinds.get("Loss", 0) - kinds.get("Expense", 0) \
        - kinds.get("Salvage Recovery", 0) - kinds.get("Subrogation Recovery", 0) - paid_stmt["commission_amount"].sum()
    rep.check("cash in the ledger moves with the receipts, claim payments, recoveries and commission payments",
              close(get(activity, 1000), cash, 1.0) and close(get(activity, 5000), kinds.get("Loss", 0), 1.0)
              and close(get(activity, 5100) + get(activity, 5110), kinds.get("Expense", 0), 1.0)
              and close(get(activity, 5010) + get(activity, 5020), kinds.get("Salvage Recovery", 0) + kinds.get("Subrogation Recovery", 0), 1.0),
              f"net cash flow ${get(activity, 1000):,.0f}")
    rep.check("case reserves in the ledger are the reserves outstanding on the claim features",
              close(-get(balance, 2500), feat["case_reserve"].sum(), 1.0) and close(-get(balance, 2510), feat["expense_reserve"].sum(), 1.0),
              f"loss ${-get(balance, 2500):,.0f}, expense ${-get(balance, 2510):,.0f}")
    unpaid = stmt[stmt["payment_date"].isna()]
    agent = agency.loc[agency["channel"] != "Direct", "agency_id"]
    by_pol = pol.set_index("policy_id")["agency_id"].reindex(ledger["policy_id"]).to_numpy()
    first_month = (start.astype("M8[M]") - np.timedelta64(1, "M")).astype("M8[D]")
    in_stmt = (booked >= first_month) & (booked <= valuation) & np.isin(by_pol, agent)
    rep.check("commission statements hold every agent's commission from the month before the extract; those not yet paid "
              "are the ledger's commissions payable",
              close(stmt["commission_amount"].sum(), ledger.loc[in_stmt, "commission_amount"].sum(), 1.0)
              and close(-get(balance, 2200), unpaid["commission_amount"].sum(), 1.0) and stmt["agency_id"].isin(agent).all()
              and not stmt.duplicated(["agency_id", "statement_month"]).any()
              and (paid_stmt["payment_date"] > paid_stmt["statement_month"] + "-31").all(),
              f"{len(stmt):,} statements, ${-get(balance, 2200):,.0f} payable")
    # premiums receivable: written by the valuation date, less premium collected (through the bill each receipt pays),
    # plus refunds, less write-offs
    bill = inv.set_index("invoice_id")["premium_amount"]
    on_bill = bill.reindex(rec["invoice_id"]).fillna(0).to_numpy()
    kind = rec["receipt_type"].to_numpy()
    collected = np.where(kind == "Refund", rec["amount"], np.where(kind == "Returned Payment", -on_bill, on_bill)).sum()
    owed = ledger.loc[booked <= valuation, "written_premium"].sum() - collected - inv.loc[inv["write_off_date"].notna(), "amount_due"].sum()
    fees = rec.loc[r_in, "amount"].sum() - np.where(kind == "Refund", rec["amount"], np.where(kind == "Returned Payment", -on_bill, on_bill))[r_in].sum()
    rep.check("premiums receivable in the ledger is premium written less premium collected, refunded and written off; "
              "fee income is the fees collected", close(get(balance, 1200), owed, 1.0) and close(-get(activity, 4200), fees, 1.0)
              and close(get(activity, 6300), inv.loc[pd.to_datetime(inv["write_off_date"]).to_numpy() >= start, "amount_due"].sum(), 1.0),
              f"receivable ${get(balance, 1200):,.0f}, fees ${-get(activity, 4200):,.0f}, written off ${get(activity, 6300):,.0f}")
    rep.check("the ledger's periods run month by month from the start to the valuation date",
              sorted(gl.loc[~opening, "accounting_period"].unique()) == [str(m) for m in np.arange(start.astype("M8[M]"), valuation.astype("M8[M]") + np.timedelta64(1, "M"))]
              and (gl["posting_date"].str[:7] == gl["accounting_period"]).all())


MIN_POLICIES_FOR_CALIBRATION = 20_000   # smaller books have too few claims for the calibration bands
MIN_AGENCY_CAR_YEARS = 500              # agencies compared with each other on their expected loss ratio


class Report:
    """Integrity checks (check) always count. Calibration bands (band) are statistical: on a small book
    a miss is reported as a warning rather than a failure."""

    def __init__(self, calibrate: bool = True) -> None:
        self.failures = self.warnings = 0
        self.calibrate = calibrate
        self.bands = []                 # every band's figure, for --json (scripts/seed_spread.py)

    def check(self, label: str, ok: bool, detail: str = "", statistical: bool = False) -> None:
        soft = statistical and not self.calibrate
        self.failures += not ok and not soft
        self.warnings += not ok and soft
        print(f"  [{'ok' if ok else 'warn' if soft else 'FAIL'}] {label}{(': ' + detail) if detail else ''}")

    def band(self, label: str, value: float, band: tuple[float, float], fmt: str = "{:,.2f}", key: str = None) -> None:
        """key: a name for the figure that stays the same from run to run, where the label includes figures."""
        ok = bool(band[0] <= value <= band[1])
        self.bands.append({"key": key or label, "value": float(value), "low": band[0], "high": band[1], "ok": ok,
                           "percent": "%" in fmt})
        self.check(label, ok, f"{fmt.format(value)} (target {fmt.format(band[0])} to {fmt.format(band[1])})", statistical=True)


def payload_hash(folder: Path, pattern: str) -> str:
    """The generator's content hash (run_summary.json "hash_method"), worked out here independently."""
    digest = hashlib.sha256()
    for f in sorted(folder.glob(pattern)):
        digest.update(f.relative_to(folder).as_posix().encode() + f.read_bytes())
    return digest.hexdigest()[:16]


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", type=Path, default=Path(__file__).resolve().parent / "output")
    ap.add_argument("--json", type=Path, help="also write every calibration band's figure to this file")
    args = ap.parse_args()
    out = args.out
    summary = json.loads((out / "run_summary.json").read_text())
    start, valuation = np.datetime64(summary["start"]), np.datetime64(summary["valuation"])
    t = rebuild(load(out), start, valuation)          # the totals an analyst works out from the records
    pol, term, risk = t["policy"], t["policy_term"], t["exposure"]
    drv, veh, loc = t["driver"], t["insured_vehicle"], t["location"]
    clm, feat, pay = t["claim"], t["claim_feature"], t["claim_payment"]
    inc, ledger = t["driver_incident"], t["premium_transaction"]
    reserves, quotes, vmy = t["claim_reserve_transaction"], t["quote"], t["vehicle_model_year"]
    enrol, tscores = t["telematics_enrollment"], t["telematics_score"]
    offers = t["renewal_offer"]
    inv, rec, emp, vend = t["billing_invoice"], t["billing_receipt"], t["employee"], t["vendor"]
    agency, contact = t["agency"], t["customer_contact"]
    gl, acct, stmt, rates = t["gl_journal"], t["gl_account"], t["agency_statement"], t["rate_change"]
    truth = pd.read_csv(out / "answer_key" / "exposure_truth.csv")
    plan = json.loads((out / "answer_key" / "rating_plan.json").read_text())
    pd.set_option("display.width", 200)
    rep = Report(calibrate=len(pol) >= MIN_POLICIES_FOR_CALIBRATION)
    if not rep.calibrate:
        print(f"note: {len(pol):,} policies is too few to hold calibration bands; misses are warnings, integrity checks still count")
    if "tables_hash" in summary:
        build = summary.get("build", {})
        print(f"\nBUILD\n  source {build.get('source_revision')} (modified: {build.get('source_modified')}), python {build.get('python')}, "
              f"numpy {build.get('numpy')}, pandas {build.get('pandas')}")
        key = out / "answer_key"
        rep.check("the CSV files are the ones the generator wrote (their hashes match run_summary.json)",
                  payload_hash(out, "*.csv") == summary["tables_hash"]
                  and (not key.is_dir() or payload_hash(key, "*.csv") == summary["answer_key_hash"]),
                  f"tables {summary['tables_hash']}" + (f", answer key {summary['answer_key_hash']}" if key.is_dir() else ""))

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
    integrity_links(rep, risk, term, veh, drv, clm, feat, pay, reserves)
    c = clm.merge(term, on="policy_term_id")
    end = c["cancel_date"].fillna(c["expiration_date"])
    rep.check("every loss date falls inside its policy term", ((c["loss_date"] >= c["effective_date"]) & (c["loss_date"] < end)).all())
    rep.check("report date is on or after loss date", (clm["report_date"] >= clm["loss_date"]).all())
    rep.check("no negative premiums", (risk[[x for x in risk.columns if x.endswith("_premium")]] >= 0).all().all())
    cov_ok = feat.merge(clm[["claim_id", "exposure_id", "cause_of_loss"]], on="claim_id").merge(risk, on="exposure_id")
    rep.check("physical damage, rental and towing claims only on risk rows carrying that coverage",
              all((cov_ok.loc[cov_ok["coverage_code"] == k, col] > 0).all() for k, col in
                  (("COLL", "collision_premium"), ("COMP", "comprehensive_premium"), ("RENT", "rental_premium"),
                   ("TOW", "towing_premium"))))
    integrity_limits(rep, cov_ok)
    integrity_reserve_sharing(rep, cov_ok, pay, reserves)
    integrity_records(rep, risk, veh, pay, stmt, quotes, inv, rec, vend, feat, reserves, offers, term)
    integrity_people(rep, pol, term, drv, inc)
    age = (pd.to_datetime(drv["added_date"]) - pd.to_datetime(drv["date_of_birth"])).dt.days.to_numpy() / 365.25
    rep.check("all drivers are 16 or older when first insured", age.min() >= 16, f"youngest {age.min():.1f}, oldest {age.max():.1f}")
    integrity_lifecycle(rep, risk, term, pol, veh, drv, clm, feat, pay, inc, r_start, r_end, valuation)
    integrity_claims_and_quotes(rep, term, veh, clm, feat, reserves, quotes)
    vt = out / "answer_key" / "insured_vehicle_truth.csv"
    integrity_vehicles(rep, vmy, veh, risk, clm, pd.read_csv(vt) if vt.exists() else None)
    # a car's use and mileage are what its last period rated by the valuation date was rated on
    by_v = risk[risk["coverage_start_date"] <= str(pd.Timestamp(valuation).date())]
    last = by_v[by_v["coverage_start_date"] == by_v.groupby("insured_vehicle_id")["coverage_start_date"].transform("max")]
    both = last.merge(veh[["insured_vehicle_id", "annual_mileage", "primary_use"]], on="insured_vehicle_id")
    match = ((both["annual_mileage"] == both["rated_annual_mileage"]) & (both["primary_use"] == both["rated_primary_use"]))
    changed = risk.groupby("insured_vehicle_id")["rated_annual_mileage"].nunique()
    rep.check("each vehicle's use and mileage are those its latest period by the valuation date was rated on",
              bool(match.groupby(both["insured_vehicle_id"]).any().all()),
              f"{(changed > 1).sum():,} vehicles rated on more than one mileage over time")
    # recoveries repay what has been paid: on no day has a feature recovered more than it had paid in loss by then
    ahead = recoveries_ahead(pay)
    rep.check("on no day has a feature recovered (salvage and subrogation) more than it had paid in loss by then",
              len(ahead) == 0, f"{len(ahead):,} features ahead on some day")
    # a car handed to another driver is driven as they drive: its mileage or use is declared again
    e = risk.sort_values(["insured_vehicle_id", "coverage_start_date", "exposure_id"], kind="stable")
    before = e.groupby("insured_vehicle_id")[["driver_id", "rated_annual_mileage", "rated_primary_use"]].shift(1)
    switch = before["driver_id"].notna() & (e["driver_id"] != before["driver_id"])
    redrawn = ((e["rated_annual_mileage"] != before["rated_annual_mileage"])
               | (e["rated_primary_use"] != before["rated_primary_use"]))[switch]
    rep.check("most cars that pass to another driver are rated on a newly declared mileage or use (a redraw can land "
              "on the same rounded figure)", len(redrawn) == 0 or redrawn.mean() >= 0.5,
              f"{switch.sum():,} driver switches on kept cars, {redrawn.mean():.0%} re-rated" if len(redrawn) else "none")
    # the policy's own people's features (medical payments, uninsured motorist) name the listed driver they are for:
    # the claim's driver as the first claimant, or a household member on the policy riding along
    own = feat.dropna(subset=["injured_driver_id"]).astype({"injured_driver_id": "int64"}).merge(clm[["claim_id", "policy_id", "involved_driver_id", "loss_date"]],
                                                          on="claim_id")
    who = drv.set_index("driver_id").reindex(own["injured_driver_id"])
    loss = pd.to_datetime(own["loss_date"]).to_numpy()
    aboard = ((who["policy_id"].to_numpy() == own["policy_id"].to_numpy())
              & (pd.to_datetime(who["added_date"]).to_numpy() <= loss) & ~(pd.to_datetime(who["removed_date"]).to_numpy() <= loss))
    first = own["claimant_number"] == 1
    rep.check("a feature's injured driver is on the claim's policy on the loss date, only on medical payments and "
              "uninsured motorist features, and the first claimant is the claim's driver",
              bool(aboard.all() and own["coverage_code"].isin(["MED", "UM"]).all()
                   and (own.loc[first, "injured_driver_id"] == own.loc[first, "involved_driver_id"]).all()),
              f"{len(own):,} features for the policy's own people, {(~first).sum():,} for a household member riding along")
    # someone killed in a crash, at the wheel or riding along, is recorded as deceased, leaving the policy within a
    # month of the crash (or after the valuation date), and drives in no later claim
    fatal = own[own["injury_type"] == "Fatality"].drop_duplicates(["claim_id", "injured_driver_id"]).merge(
        drv[["driver_id", "removal_reason", "removed_date"]], left_on="injured_driver_id", right_on="driver_id", how="left")
    after = (pd.to_datetime(fatal["removed_date"]) - pd.to_datetime(fatal["loss_date"])).dt.days
    not_yet = fatal["removed_date"].isna() & ((pd.Timestamp(valuation) - pd.to_datetime(fatal["loss_date"])).dt.days < 31)
    passenger = fatal["injured_driver_id"] != fatal["involved_driver_id"]
    later = clm.merge(fatal[["injured_driver_id", "loss_date"]].rename(columns={"loss_date": "died_in"}),
                      left_on="involved_driver_id", right_on="injured_driver_id")
    later = later[(later["loss_date"] > later["died_in"]) & later["cause_of_loss"].isin(["AF_MV", "AF_SV", "NAF"])]
    rep.check("someone killed in a crash, at the wheel or riding along, is recorded as deceased, leaving the policy "
              "within a month of the crash, and drives in no later crash",
              bool((((fatal["removal_reason"] == "Deceased") & after.between(1, 31)) | not_yet).all()) and len(later) == 0,
              f"{len(fatal):,} people killed in {fatal['claim_id'].nunique():,} crashes ({int(passenger.sum()):,} riding "
              f"along); {(feat['injury_type'] == 'Fatality').sum():,} fatality features in all")
    # a rental is paid once the car is returned: no sooner after the loss than its cost at the daily limit allows
    rent = feat.loc[feat["coverage_code"] == "RENT", ["claim_feature_id", "claim_id"]].merge(
        clm[["claim_id", "loss_date", "exposure_id"]], on="claim_id").merge(risk[["exposure_id", "rental_reimbursement"]], on="exposure_id")
    lp = pay[pay["payment_type"] == "Loss"]
    rent = rent.assign(paid=rent["claim_feature_id"].map(lp.groupby("claim_feature_id")["amount"].sum()).fillna(0),
                       last=rent["claim_feature_id"].map(lp[lp["transaction_type"] != "Void"].groupby("claim_feature_id")["payment_date"].max()))
    rent = rent[rent["paid"] > 0]
    least = np.ceil(rent["paid"] / rent["rental_reimbursement"].str.split("/").str[0].astype(float) - 1e-9)
    elapsed = (pd.to_datetime(rent["last"]) - pd.to_datetime(rent["loss_date"])).dt.days
    rep.check("a rental is paid in full only once enough days have passed since the loss for it to cost that much at "
              "its daily limit", bool((elapsed >= least).all()),
              f"{len(rent):,} paid rentals, median {elapsed.median():.0f} days from loss to payment")
    storm = clm.dropna(subset=["catastrophe_id"]).merge(t["catastrophe"], on="catastrophe_id")
    rep.check("a catastrophe claim's loss is on its event's day, within the storm's hours",
              (storm["loss_date"] == storm["event_date"]).all()
              and storm["loss_time"].between(storm["start_time"], storm["end_time"]).all(),
              f"{len(storm):,} catastrophe claims")
    integrity_telematics(rep, enrol, tscores, risk, term, pd.Timestamp(valuation), pol, veh, drv)
    integrity_renewals(rep, offers, term, risk, valuation, veh, clm, feat)
    integrity_calendar(rep, term, clm, feat, pay, reserves, inc, drv, ledger, contact, emp, agency, t["producer"], inv)
    integrity_identifiers(rep, pol, term, drv, veh, risk, clm, feat, quotes, vmy)
    integrity_billing(rep, inv, rec, term, ledger, pol, valuation, contact)
    integrity_payments(rep, pay, clm, feat, emp, vend, ledger, agency, pol, term)
    integrity_payees(rep, pay, clm, feat, veh, drv)
    integrity_audit_records(rep, t, valuation)
    integrity_audit_v119(rep, t, valuation, out)
    integrity_animal_drivers(rep, clm, risk, pol)
    integrity_ledger(rep, gl, acct, stmt, ledger, pol, term, inv, rec, pay, clm, feat, reserves, agency, start, valuation)
    filed = plan["filed_discounts"]
    rep.check("the rating plan charges the filed discounts and surcharges, on the coverages they are filed for",
              all(list(plan["relativities"][cov][k].values()) == (list(d["factors"].values()) if cov in d["coverages"]
                                                                  else [1.0] * len(d["factors"]))
                  for k, d in filed.items() for cov in plan["relativities"]),
              "; ".join(f"{k} {list(d['factors'].values())}" for k, d in filed.items()))
    agent_of = pol.merge(t["agency"][["agency_id", "appointment_date"]], on="agency_id", how="left").merge(
        t["producer"][["producer_id", "agency_id", "start_date"]], on="producer_id", how="left", suffixes=("", "_producer"))
    sold = agent_of[agent_of["producer_id"].notna()]
    rep.check("a policy is written by an appointed agency, and by a producer of that agency working there by then",
              (agent_of["original_inception_date"] >= agent_of["appointment_date"]).all()
              and (sold["agency_id"] == sold["agency_id_producer"]).all()
              and (sold["original_inception_date"] >= sold["start_date"]).all(),
              f"{len(t['producer']):,} producers, {(t['producer']['start_date'] >= '2022').sum():,} hired since 2022")
    first_tx = ledger[ledger["transaction_type"].isin(["New Business", "Renewal"])].groupby("policy_term_id")["written_premium"].sum()
    gap = term["written_premium"] - first_tx.reindex(term["policy_term_id"]).fillna(0).to_numpy()
    rep.check("each term's written premium is its new-business or renewal transaction",
              (gap.abs() <= 0.005).all(), f"{ledger['transaction_type'].value_counts().to_dict()}")

    print("\nFREQUENCY AND SEVERITY (paid claims by coverage: accidents in the extract, every deductible and cause, loss only)")
    f_all = feat.merge(clm[["claim_id", "exposure_id", "loss_date", "catastrophe_id", "cause_of_loss"]], on="claim_id")
    # claims open when the extract begins come from accidents before it, outside the exposure it earns: measures by
    # accident leave them out; the calendar-year benchmark counts their payments, as the published figures do
    f = f_all[pd.to_datetime(f_all["loss_date"]).to_numpy() >= start]
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
          f"physical damage at a ${BENCHMARK_DEDUCTIBLE} deductible net of salvage and subrogation, comprehensive without wind and water)")
    benchmark(rep, risk, f_all, pay, r_start, r_end, pd.Timestamp(valuation).year - 1)
    illinois(rep, risk, r_start, r_end)

    print("\nLOSS RATIO BY ACCIDENT YEAR (net incurred as of the valuation date / earned premium; losses exclude LAE,\n"
          "which is shown beside it; add the two for a loss-and-LAE ratio; neither is a combined ratio)")
    s, e, days = r_start, r_end, r_days
    rate = np.divide(risk["earned_premium"].to_numpy(), days, out=np.zeros(len(risk)), where=days > 0)
    loss_year = pd.to_datetime(clm["loss_date"]).dt.year
    years = sorted(loss_year[loss_year >= pd.Timestamp(start).year].unique())
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
                 f"({expected_lr:.1%})", (lr[y] - cat_lr[y]) / expected_lr, ACTUAL_TO_EXPECTED_BAND, "{:.2f}",
                 key=f"{y} loss ratio excluding catastrophes relative to its expected")
    for y, b in INDUSTRY_LOSS_RATIO_BAND.items():
        a_, b_ = np.datetime64(f"{y}-01-01"), np.datetime64(f"{y + 1}-01-01")
        overlap = (np.minimum(e, b_) - np.maximum(s, a_)).astype("timedelta64[D]").astype(int).clip(0)
        if y in years and y < years[-1]:     # industry ratios include catastrophes: the year's are added
            rep.band(f"{y} expected loss ratio (answer key) plus catastrophes vs industry",
                     (overlap * exp_rate).sum() / (overlap * rate).sum() + cat_lr[y], b, "{:.1%}")
    in_extract = pd.to_datetime(clm["loss_date"]) >= pd.Timestamp(start)      # the warm-up's 2021 accidents earned no premium here
    rep.band("overall loss ratio", clm.loc[in_extract, "net_incurred_loss"].sum() / ep, OVERALL_LOSS_RATIO_BAND, "{:.1%}")
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
    now = risk[(pd.to_datetime(risk["coverage_start_date"]) <= valuation) & (pd.to_datetime(risk["coverage_end_date"]) > valuation)]
    print(f"  BI limits of the cars in force at the valuation date: {now['bi_limit'].value_counts(normalize=True).round(3).to_dict()}")
    print(f"  underwriting company mix: {pol['company_id'].value_counts(normalize=True).sort_index().round(3).to_dict()}")
    ended = term[(pd.to_datetime(term["expiration_date"]) <= pd.Timestamp(valuation))]
    lapsed = ended["cancel_date"].notna() | ended["nonrenewal_reason"].notna()
    months = (pd.to_datetime(ended["expiration_date"]) - pd.to_datetime(ended["effective_date"])).dt.days / 30.44
    annual_retention = float(np.exp(np.log(1 - lapsed.mean()) * 12 / months.mean()))
    rep.band("annualized policy retention", annual_retention, (0.78, 0.90), "{:.1%}")
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
    # agencies with enough business for their own mix not to dominate (most independent agencies are small)
    big = r.groupby("agency_id")["earned_exposure"].sum().loc[lambda x: x >= MIN_AGENCY_CAR_YEARS].index
    by_agency = r[r["agency_id"].isin(big)].groupby("agency_id").apply(elr, include_groups=False)
    rep.band(f"spread of expected loss ratio across the {len(by_agency)} agencies with {MIN_AGENCY_CAR_YEARS:,}+ car-years "
             "(90th less 10th percentile, points)", (by_agency.quantile(0.9) - by_agency.quantile(0.1)) * 100, (6.0, 25.0), "{:.1f}",
             key=f"spread of expected loss ratio across agencies with {MIN_AGENCY_CAR_YEARS:,}+ car-years (90th less 10th percentile, points)")
    market_cycle(rep, quotes, term, clm, offers, list(zip(rates.iloc[:, 0], rates.iloc[:, 1])), valuation)
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
    if args.json:
        args.json.write_text(json.dumps({"seed": summary["seed"], "policies": summary["policies"], "failures": rep.failures,
                                         "warnings": rep.warnings, "bands": rep.bands}, indent=1) + "\n")
    sys.exit(1 if rep.failures else 0)


if __name__ == "__main__":
    main()
