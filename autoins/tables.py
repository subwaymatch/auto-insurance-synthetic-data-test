"""Turn the simulation results into the published tables and the answer key."""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

from . import config as C
from . import rating, truth
from .refdata import stream
from .simulate import REMOVAL_REASONS

POLICY_BASE = 1_000_000
YN = np.array(["N", "Y"])


def _limit(pair) -> str:
    return f"{pair[0] // 1000}/{pair[1] // 1000}"


def build(cfg: C.Config, ref, pop, res, dev) -> tuple[dict, dict]:
    """Returns (tables, answer_key): two dicts of DataFrames keyed by file name (without .csv)."""
    cal, z, mdl = ref.cal, ref.zips, ref.models
    pol, drv, veh = pop.pol, pop.drv, pop.veh
    terms, rows = res.terms, res.rows
    claims, feats, pays = dev["claims"], dev["features"], dev["payments"]
    V = cal.valuation_day
    D = lambda day: pd.Series(cal.date(np.asarray(day))).dt.strftime("%Y-%m-%d").to_numpy()
    polno = lambda p: POLICY_BASE + np.asarray(p) + 1
    T, K = {}, {}

    # ---- geography ---------------------------------------------------------------------
    terr_l, terr_c = res.plan.terr_liab, res.plan.terr_comp
    T["location_dimension"] = pd.DataFrame({
        "Location ID": z.location_id, "ZIP": z.zip, "Primary_City": z.city, "State": "IL",
        "County": z.county + " County", "Region": z.region, "Latitude": z.lat.round(4), "Longitude": z.lon.round(4),
        "Estimated_Population": z.population, "Median Household Income": z.median_household_income.astype(int),
        "Population Density Per Sq Mile": z.population_density_sqmi.round(0).astype(int),
        "Liability Territory": np.array(rating.LEVELS["territory"])[terr_l],
        "Comprehensive Territory": np.array(rating.LEVELS["territory"])[terr_c]})
    share = lambda cols: (z[[f"age_share_{c}" for c in cols]].sum(axis=1) * 100).round(1)
    T["population_distribution"] = pd.DataFrame({
        "ZIP": z.zip, "Estimated_Population": z.population,
        "Driving Age Population % 16-24": share(["16_17", "18_20", "21_24"]),
        "Driving Age Population % 25-39": share(["25_29", "30_34", "35_39"]),
        "Driving Age Population % 40-64": share(["40_44", "45_49", "50_54", "55_59", "60_64"]),
        "Driving Age Population % 65+": share(["65_69", "70_74", "75_79", "80_84", "85_plus"]),
        "Population % White Non-Hispanic": (z.pct_white_nh * 100).round(1),
        "Population % Black Non-Hispanic": (z.pct_black_nh * 100).round(1),
        "Population % Hispanic": (z.pct_hispanic * 100).round(1),
        "Population % Asian Non-Hispanic": (z.pct_asian_nh * 100).round(1),
        "Households": z.households, "Households % Owner Occupied": (z.pct_owner_occupied * 100).round(1),
        "Households % With a Vehicle": (z.households_with_vehicle / z.households * 100).round(1),
        "Workers % Commute by Car": (z.pct_commute_drive * 100).round(1),
        "Workers % Commute by Transit": (z.pct_commute_transit * 100).round(1),
        "Workers % Work From Home": (z.pct_work_from_home * 100).round(1),
        "Mean Commute Minutes": z.mean_commute_minutes.round(1)})

    ag = pop.agencies
    az = z.iloc[ag.zi.clip(0)]
    T["agency_dimension"] = pd.DataFrame({
        "Agency ID": ag.agency_id, "Agency Name": ag.name, "Channel": ag.channel,
        "Agency City": np.where(ag.zi >= 0, az.city.to_numpy(), "Chicago"), "Agency State": "IL",
        "Agency ZIP": np.where(ag.zi >= 0, az.zip.to_numpy(), "60606")})
    T["company_dimension"] = pd.DataFrame(C.COMPANIES, columns=["Underwriting Company ID", "Underwriting Company Name",
                                                                "Underwriting Tier", "Company City"]).assign(**{"Company State": "IL"})
    T["claim_branches"] = pd.DataFrame(C.BRANCHES, columns=["Branch Id", "Branch Name", "Branch City"])
    T["catastrophe_dimension"] = pd.DataFrame(
        [(e[0], e[1], e[2], C.PERIL_DESCRIPTION[e[3]]) for e in C.CAT_EVENTS
         if cfg.start <= e[1] <= cfg.valuation],
        columns=["Catastrophe ID", "Event Date", "Description", "Peril"]).assign(Note="Fictional event")
    level, out = 1.0, []
    for d, chg in C.RATE_CHANGES:
        if cfg.start <= d <= cfg.valuation:
            level *= 1 + chg
            out.append((d, round(chg * 100, 1), round(level, 4)))
    T["rate_change_history"] = pd.DataFrame(out, columns=["Effective Date", "Overall Rate Change %", "Cumulative Rate Level"])

    # ---- policies and terms ---------------------------------------------------------------
    # Premium accounting. Each risk row's premium is a full-term rate; a vehicle added or removed
    # mid-term is an endorsement charged or returned pro rata, and a cancellation returns the rest.
    # For every term: written + endorsement + return = earned before the extract + earned in it
    # (+ unearned, while the term is still running at the valuation date).
    prem_cols = [f"prem_{c}" for c in C.COVERAGES]
    rows = rows.assign(total_premium=rows[prem_cols].sum(axis=1))
    tp = rows.total_premium
    rows["earned_premium"] = (tp * rows.earned_share).round(2)
    rows = rows.assign(written=tp * rows.at_start, net_written=tp * rows.written_share, returned=tp * rows.return_share,
                       before=tp * rows.before_share)
    tg = rows.groupby("term").agg(written=("written", "sum"), net_written=("net_written", "sum"), returned=("returned", "sum"),
                                  earned=("earned_premium", "sum"), before=("before", "sum"), vehicles=("at_start", "sum"))
    terms = terms.join(tg, on="term")
    terms[list(tg.columns)] = terms[list(tg.columns)].fillna(0)
    cancelled = terms.cancel_day >= 0
    T["policy_term_fact"] = pd.DataFrame({
        "Policy Term ID": terms.term + 1, "Policy Number": polno(terms.pol), "Term Number": terms.term_no,
        "Business Type": np.where(terms.new_business, "New", "Renewal"),
        "Policy Effective Date": D(terms.s), "Policy Expiration Date": D(terms.e), "Rating Date": D(terms.rate_day),
        "Cancel Date": np.where(cancelled, D(terms.cancel_day.clip(0)), ""), "Cancel Reason": terms.cancel_reason,
        "Non-Renewal Reason": terms.nonrenewal_reason, "Vehicle Count": terms.vehicles.astype(int),
        "Written Premium": terms.written.round(2), "Endorsement Premium": (terms.net_written - terms.written).round(2),
        "Return Premium": (-terms.returned).round(2) + 0.0, "Earned Before Extract": terms.before.round(2),
        "Earned Premium": terms.earned.round(2), "Rate Level Index": (terms.rate_level / cal.rate_level[0]).round(4)})

    last = terms.sort_values(["pol", "s"], kind="stable").groupby("pol").tail(1).set_index("pol").reindex(pol["pol"])
    status = np.where(last.cancel_day >= 0, "Cancelled", np.where(last.nonrenewal_reason != "", "Non-Renewed", "In Force"))
    end_day = np.where(last.cancel_day >= 0, last.cancel_day, last.e)
    reason = np.where(last.cancel_day >= 0, last.cancel_reason, last.nonrenewal_reason)
    first_drv = drv.groupby("pol").drv.first().to_numpy()
    inception = cal.day_of(pol.first_month - pol.tenure_terms * pol.term_months, pol.dom)
    bi = [C.BI_LIMITS[i] for i in pol.bi_opt]
    score = pol.insurance_score
    T["policy_dimension"] = pd.DataFrame({
        "Policy Number": polno(pol["pol"]), "Location ID": z.location_id.to_numpy()[pol.zi],
        "Agency ID": pol.agency_id, "Underwriting Company ID": pol.tier + 1,
        "Distribution Channel": np.array(C.CHANNELS)[pol.channel],
        "Original Inception Date": pd.Series(cal.start + inception.astype("timedelta64[D]")).dt.strftime("%Y-%m-%d").to_numpy(),
        "Policy Effective Date": D(pol.first_day), "Policy Expiration Date": D(end_day),
        "Term Length Months": pol.term_months, "Policy Status": status, "Status Reason": reason,
        "Cancel Date": np.where(status == "Cancelled", D(end_day), ""),
        "Named Insured Driver ID": first_drv + 1, "Number of Drivers": pol.n_drv,
        "Number of Vehicles": last.vehicles.fillna(0).astype(int).to_numpy(),
        "Homeowner": YN[pol.homeowner.astype(int)], "Multi-Policy": YN[pol.multi_policy.astype(int)],
        "Prior Insurance": YN[pol.prior_insurance.astype(int)],
        "Insurance Score": score.astype("Int64"), "Payment Plan": np.array(C.PAY_PLANS)[pol.pay_plan],
        "BI Limit": [_limit(b) for b in bi], "PD Limit": np.array(C.PD_LIMITS)[pol.bi_opt],
        "UM Limit": [_limit(C.BI_LIMITS[i]) for i in pol.um_opt], "Med Pay Limit": np.array(C.MED_LIMITS)[pol.med_opt]})

    # ---- drivers ------------------------------------------------------------------------------
    inc = pop.incidents
    fd = drv.added_day.to_numpy()
    recent = (inc.day.to_numpy() <= fd[inc.drv]) & (inc.day.to_numpy() > fd[inc.drv] - C.LOOKBACK_DAYS) \
        & (inc.known_day.to_numpy() <= fd[inc.drv])
    good_student = truth.good_student(drv.good_grades, drv.school_end_day, drv.dob_day, drv.added_day)
    n_viol = np.bincount(inc.drv[recent & (inc.kind != "accident")], minlength=len(drv))
    n_acc = np.bincount(inc.drv[recent & (inc.kind == "accident")], minlength=len(drv))
    T["driver_dimension"] = pd.DataFrame({
        "Driver ID": drv.drv + 1, "Policy Number": polno(drv.pol),
        "Driver Role": np.array(["Named Insured", "Spouse", "Other Adult", "Child"])[drv.role],
        "First Name": drv.first_name, "Last Name": drv.last_name, "Date of Birth": D(drv.dob_day),
        "Gender": np.where(drv.male, "M", "F"), "Marital Status": drv.marital, "Date First Licensed": D(drv.licensed_day),
        "Added Date": D(drv.added_day), "Good Student": YN[good_student.astype(int)], "Miles to work": drv.commute_miles.astype(int),
        "Number of Violations": n_viol, "Number of Accidents": n_acc})

    # Each incident carries the day the insurer learned of it: a violation when the conviction posts to the
    # driving record, an earlier accident when it appears on a claims-history report, and the company's own
    # claim when its payments make it chargeable. Rating uses an incident only from that day on.
    own = claims[claims.chargeable & (claims.drv >= 0)]
    acc = (inc.kind == "accident").to_numpy()
    with_us = acc & (inc.day.to_numpy() >= inception[inc.pol.to_numpy()])     # in-force book, before the extract
    records = pd.concat([
        pd.DataFrame({"drv": inc.drv, "day": inc.day, "known": inc.known_day,
                      "Incident Type": inc.kind.map({"minor": "Minor Violation", "major": "Major Violation", "accident": "At-Fault Accident"}),
                      "Description": np.where(with_us, "At-fault accident (company claim before the extract)",
                                              np.where(acc, "At-fault accident (prior carrier)", inc.description)),
                      "Source": np.where(with_us, "Company Claim (Before Extract)", np.where(acc, "Prior Carrier Report", "Motor Vehicle Record")),
                      "Claim ID": pd.array([pd.NA] * len(inc), dtype="Int64")}),
        pd.DataFrame({"drv": own.drv, "day": own.day, "known": own.chargeable_day, "Incident Type": "At-Fault Accident",
                      "Description": "At-fault accident (company claim)", "Source": "Company Claim",
                      "Claim ID": own.claim_id.astype("Int64")})], ignore_index=True)
    records = records[(records.day <= V) & (records.known <= V)].sort_values(["day", "drv"], kind="stable").reset_index(drop=True)
    T["driver_incident_fact"] = pd.DataFrame({
        "Incident ID": np.arange(1, len(records) + 1), "Driver ID": records.drv + 1, "Incident Date": D(records.day),
        "Known Date": D(records.known), "Incident Type": records["Incident Type"], "Description": records.Description,
        "Source": records.Source, "Claim ID": records["Claim ID"]})

    # ---- vehicles -----------------------------------------------------------------------------
    T["vehicles_dimension"] = pd.DataFrame({
        "Vehicle ID": mdl.model_id, "Car Make": mdl.make, "Model": mdl.model, "Body Type": mdl.body_type,
        "Segment": mdl.segment.str.title().replace({"Ev": "Electric"}), "Average Price": mdl.msrp_2024})
    vid = mdl.model_id.to_numpy()[veh.model_idx]
    T["insured_vehicle_dimension"] = pd.DataFrame({
        "Insured Vehicle ID": veh.veh + 1, "Policy Number": polno(veh.pol), "Vehicle ID": vid,
        "Vehicle Model Year": veh.model_year, "Primary Driver ID": veh.primary_drv + 1, "Ownership": veh.ownership,
        "Added Date": D(veh.added_day), "Removed Date": np.where(veh.removed_day >= 0, D(veh.removed_day.clip(0)), ""),
        "Primary Vehicle Use": veh.use, "Annual Mileage": veh.reported_miles.astype(int),
        "Parking": np.array(C.PARKING)[veh.parking], "Anti-Theft Device": YN[veh.anti_theft.astype(int)],
        "Automatic Emergency Braking": YN[veh.adas.astype(int)], "Original MSRP": veh.msrp.round(-2).astype(int),
        "Collision Coverage": YN[veh.has_coll.astype(int)],
        "Collision Deductible": np.where(veh.has_coll, np.array(C.COLL_DEDUCTIBLES)[veh.coll_ded_opt], 0),
        "Comprehensive Coverage": YN[veh.has_comp.astype(int)],
        "Comprehensive Deductible": np.where(veh.has_comp, np.array(C.COMP_DEDUCTIBLES)[veh.comp_ded_opt], 0),
        "Full Glass Coverage": YN[veh.full_glass.astype(int)],
        "Removal Reason": np.array(REMOVAL_REASONS)[veh.removal_reason],
        "Replaces Vehicle ID": pd.Series(veh.replaces + 1).where(veh.replaces >= 0).astype("Int64")})

    rv = rows.veh.to_numpy()
    tcan = terms.set_index("term").cancel_day.reindex(rows.term).to_numpy()
    cover_end = np.where(tcan >= 0, np.minimum(rows.sched, tcan), rows.sched)
    T["risk_fact"] = pd.DataFrame({
        "Record ID": rows.row + 1, "Policy Term ID": rows.term + 1, "Policy Number": polno(rows.pol),
        "Insured Vehicle ID": rv + 1, "Vehicle ID": vid[rv], "Vehicle Model Year": veh.model_year.to_numpy()[rv],
        "Driver ID": rows.drv + 1, "Location ID": z.location_id.to_numpy()[pol.zi.to_numpy()[rows.pol]],
        "Rated Driver Age": np.floor(rows.driver_age).astype(int),
        "Rated Driver Class": np.array(rating.CLASS_LEVELS)[rows.class_code],
        "Rated Violation Points": rows.violation_points, "Rated At-Fault Accidents": rows.at_fault_accidents,
        "Rated Good Student": YN[rows.good_student.astype(int)],
        "Tenure Years": rows.tenure_years.round(1), "Vehicle Value": rows.acv.round(-1).astype(int),
        "BI Premium": rows.prem_BI, "PD Premium": rows.prem_PD, "UM Premium": rows.prem_UM,
        "Med Pay Premium": rows.prem_MED, "Collision Premium": rows.prem_COLL, "Comprehensive Premium": rows.prem_COMP,
        "Total Premium": rows.total_premium.round(2), "Coverage Start Date": D(rows.s), "Coverage End Date": D(cover_end),
        "Earned Exposure": rows.earned_exposure.round(4), "Earned Premium": rows.earned_premium})

    # ---- claims ---------------------------------------------------------------------------------
    f = feats
    f = f.assign(incurred=f.paid_loss + f.case_reserve, recovery=f.salvage_rec + f.subro_rec)
    f["net_incurred"] = f.incurred - f.recovery
    T["claim_coverage_fact"] = pd.DataFrame({
        "Claim Feature ID": f.feature_id, "Claim ID": f.claim_id, "Coverage Code": f.cvg,
        "Coverage": f.cvg.map(C.COVERAGE_NAMES), "Claimant Number": f.claimant,
        "Feature Status": np.where(f.closed, "Closed", np.where(f.reopened, "Reopened", "Open")), "Open Date": D(f.open_day),
        "Close Date": np.where(f.closed, D(f.status_close_day.clip(upper=V)), ""),
        "Reopen Date": np.where(f.reopened, D(f.reopen_day.clip(0)), ""),
        "Paid Loss": f.paid_loss.round(2), "Case Reserve": f.case_reserve.round(2), "Incurred Loss": f.incurred.round(2),
        "Salvage Recovery": f.salvage_rec.round(2), "Subrogation Recovery": f.subro_rec.round(2),
        "Net Incurred Loss": f.net_incurred.round(2), "Paid Expense": f.paid_expense.round(2),
        "Litigation": YN[f.litigated.astype(int)], "Total Loss": YN[f.total.astype(int)],
        "Closed Without Payment": YN[(f.closed & (f.paid_loss == 0)).astype(int)]})
    cg = f.groupby("claim_id").agg(paid=("paid_loss", "sum"), reserve=("case_reserve", "sum"), recovery=("recovery", "sum"),
                                   net=("net_incurred", "sum"), expense=("paid_expense", "sum"), n=("fid", "size"),
                                   open=("closed", lambda s: (~s).any()), close_day=("status_close_day", "max"),
                                   lit=("litigated", "any"), injury=("cvg", lambda s: s.isin(["BI", "UM"]).any()),
                                   total=("total", "any")).reindex(claims.claim_id)
    city = (z.region.to_numpy() == "City of Chicago")[pol.zi.to_numpy()[claims.pol]]
    peril = claims.peril.to_numpy()
    branch = np.select([claims.cat.to_numpy() >= 0, cg.injury.to_numpy(), (peril == "THEFT_TOTAL") | cg.total.to_numpy(),
                        peril == "GLASS", city], [6, 3, 5, 4, 1], default=2)
    claimant = np.where(claims.drv >= 0, claims.drv, first_drv[claims.pol]) + 1
    cat_id = np.where(claims.cat >= 0, np.array([e[0] for e in C.CAT_EVENTS])[claims.cat.clip(0)], "")
    T["claims_fact"] = pd.DataFrame({
        "Claim ID": claims.claim_id, "Policy ID": polno(claims.pol), "Policy Term ID": claims.term + 1,
        "Record ID": claims.row + 1, "Claimant Id": claimant, "Insured Vehicle ID": claims.veh + 1,
        "Vehicle ID": vid[claims.veh], "Loss Date": D(claims.day), "Report Date": D(claims.report_day),
        "Close Date": np.where(cg.open.to_numpy(), "", D(cg.close_day.clip(upper=V))),
        "Claim Status": np.where(cg.open.to_numpy(), "Open", "Closed"), "Cause of Loss": claims.peril,
        "Claim Description": claims.peril.map(C.PERIL_DESCRIPTION), "At Fault": YN[claims.at_fault.astype(int)],
        "Catastrophe ID": cat_id, "Coverage Count": cg.n.to_numpy(), "Paid Loss": cg.paid.round(2).to_numpy(),
        "Case Reserve": cg.reserve.round(2).to_numpy(), "Recoveries": cg.recovery.round(2).to_numpy(),
        "Claim Amount": cg.net.round(2).to_numpy(), "Expense Amount": cg.expense.round(2).to_numpy(),
        "Litigation": YN[cg.lit.to_numpy().astype(int)], "Claim Handling Branch": branch})
    T["claim_expense_dimension"] = T["claims_fact"][["Claim ID", "Expense Amount", "Claim Handling Branch"]].copy()
    T["claim_payment_fact"] = pd.DataFrame({
        "Payment ID": pays.payment_id, "Claim Feature ID": pays.feature_id, "Claim ID": pays.claim_id,
        "Payment Date": D(pays.day), "Payment Type": pays.kind, "Transaction Type": pays.txn, "Amount": pays.amount})

    T["communication_data"] = _communications(cfg, cal, pol, terms, claims, cg, veh, D, polno)

    # ---- answer key ---------------------------------------------------------------------------------
    exp_cols = [f"exp_{c}" for c in C.COVERAGES]
    K["risk_truth"] = pd.DataFrame({"Record ID": rows.row + 1, **{f"Expected Loss {c}": rows[f"exp_{c}"].round(2) for c in C.COVERAGES},
                                    "Expected Loss Total": rows[exp_cols].sum(axis=1).round(2)})
    K["driver_truth"] = pd.DataFrame({"Driver ID": drv.drv + 1, "Latent Risk Factor": drv.latent.round(4)})
    K["vehicle_truth"] = pd.DataFrame({"Insured Vehicle ID": veh.veh + 1, "True Annual Mileage": veh.true_miles.round(0).astype(int),
                                       "Kia/Hyundai Theft Exposure": YN[veh.kia_hyundai.astype(int)]})
    zt = pop.zip_truth
    K["zip_truth"] = pd.DataFrame({
        "Location ID": zt.location_id, "ZIP": zt.zip, "Hazard Basis": z.hazard_basis,
        "Public Crash Hazard Index": z.crash_hazard_index.round(4), "True Crash Hazard": zt.true_crash_hazard.round(4),
        "Public Theft Hazard Index": z.theft_hazard_index.round(4), "True Theft Hazard": zt.true_theft_hazard.round(4),
        "Other Driver Uninsured Probability": zt.p_other_driver_uninsured.round(4)})
    un = dev["unreported"]
    K["unreported_claims"] = pd.DataFrame({
        "Policy ID": polno(un.pol), "Record ID": un.row + 1, "Insured Vehicle ID": un.veh + 1, "Coverage Code": un.cvg,
        "Cause of Loss": un.peril, "Loss Date": D(un.day), "Eventual Report Date": D(un.open_day),
        "Ultimate Paid Loss": un.paid.round(2), "Ultimate Recovery": (un.salvage + un.subro).round(2)})
    fu = feats
    K["claim_feature_truth"] = pd.DataFrame({
        "Claim Feature ID": fu.feature_id, "Ultimate Paid Loss": fu.paid.round(2),
        "Ultimate Recovery": (fu.salvage + fu.subro).round(2), "Ultimate Expense": fu.expense.round(2),
        "Eventual Reopen Date": np.where(fu.reopen_day >= 0, D(fu.reopen_day.clip(0)), ""),
        "Eventual Close Date": D(fu.final_close_day)})
    return T, K


def _communications(cfg, cal, pol, terms, claims, cg, veh, D, polno) -> pd.DataFrame:
    """Customer contacts tied to real events in the data (welcome kits, renewals, billing, claims)."""
    R = stream(cfg.seed, "communications")
    V = cal.valuation_day
    paperless = R.random(len(pol)) < 0.62
    parts = []

    def add(p, day, purpose, digital_ok=True, phone=0.0):
        p, day = np.asarray(p), np.asarray(day)
        u = R.random(len(p))
        kind = np.where(u < phone, "Phone Call", np.where(paperless[p] & digital_ok, "Email", "Written Letter"))
        parts.append(pd.DataFrame(dict(pol=p, day=day, kind=kind, purpose=purpose)))

    nb = terms[terms.new_business]
    add(nb.pol, nb.s, "New Business Welcome")
    rn = terms[~terms.new_business]
    add(rn.pol, rn.rate_day, "Renewal Offer")
    bill = terms[(pol.pay_plan.to_numpy()[terms.pol] == 2) & (R.random(len(terms)) < 0.45)]
    add(bill.pol, bill.s + R.integers(25, 150, len(bill)), "Payment Reminder", phone=0.10)
    npay = terms[terms.cancel_reason == "Non-Payment"]
    add(npay.pol, npay.cancel_day - 21, "Past Due Notice", phone=0.25)
    add(npay.pol, npay.cancel_day - 10, "Notice of Cancellation", digital_ok=False)
    other = terms[(terms.cancel_day >= 0) & (terms.cancel_reason != "Non-Payment")]
    add(other.pol, other.cancel_day, "Cancellation Confirmation")
    added = veh[veh.added_day.to_numpy() > pol.first_day.to_numpy()[veh.pol.to_numpy()]]      # replacement vehicles
    add(added.pol, added.added_day, "Policy Change Confirmation")
    totalled = veh[veh.removal_reason == REMOVAL_REASONS.index("Total Loss")]
    add(totalled.pol, totalled.removed_day, "Policy Change Confirmation")
    add(claims.pol, claims.report_day, "Claim Acknowledgement", phone=0.45)
    closed = ~cg.open.to_numpy()
    add(claims.pol[closed], cg.close_day.to_numpy()[closed], "Claim Closure Notice", phone=0.10)

    c = pd.concat(parts, ignore_index=True)
    c = c[(c.day >= 0) & (c.day <= V)].sort_values(["day", "pol", "purpose"], kind="stable").reset_index(drop=True)
    return pd.DataFrame({"ID": [f"CM{i:07d}" for i in range(1, len(c) + 1)], "Type": c.kind,
                         "Policy ID": polno(c.pol), "Date": D(c.day), "Purpose": c.purpose})


def write(tables: dict, key: dict, plan, cfg: C.Config, summary: dict) -> None:
    out = Path(cfg.out_dir)
    (out / "answer_key").mkdir(parents=True, exist_ok=True)
    for name, df in tables.items():
        df.to_csv(out / f"{name}.csv", index=False, lineterminator="\n")
    for name, df in key.items():
        df.to_csv(out / "answer_key" / f"{name}.csv", index=False, lineterminator="\n")
    (out / "answer_key" / "rating_plan.json").write_text(json.dumps(rating.to_json(plan), indent=1) + "\n")
    (out / "run_summary.json").write_text(json.dumps(summary, indent=1) + "\n")
