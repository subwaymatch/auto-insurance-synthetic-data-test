"""Turn the simulation results into the published tables and the answer key."""
from __future__ import annotations

import json
import zlib
from pathlib import Path

import numpy as np
import pandas as pd

from . import config as C
from . import names, rating, telematics, truth
from .refdata import stream
from .simulate import DRIVER_REMOVAL_REASONS, END_ENDORSED, END_GONE, REMOVAL_REASONS

POLICY_BASE = 1_000_000
VIN_CHARS = "ABCDEFGHJKLMNPRSTUVWXYZ0123456789"           # characters allowed in a VIN (no I, O or Q)
VIN_YEAR = "ABCDEFGHJKLMNPRSTVWXY123456789"                 # model-year codes (position 10), 1980 = A, cycling every 30
SR22_VIOLATIONS = ["DUI", "Driving while suspended", "Leaving the scene"]   # convictions that require an SR-22 filing
SR22_YEARS = 3
YN = np.array(["N", "Y"])


def _limit(pair) -> str:
    return f"{pair[0] // 1000}/{pair[1] // 1000}"


def build(cfg: C.Config, ref, pop, res, dev) -> tuple[dict, dict]:
    """Returns (tables, answer_key): two dicts of DataFrames keyed by file name (without .csv)."""
    cal, z, mdl = ref.cal, ref.zips, ref.models
    pol, drv, veh = pop.pol, pop.drv, pop.veh
    terms, rows = res.terms, res.rows
    claims, feats, pays = dev["claims"], dev["features"], dev["payments"]
    opt_date = lambda day: np.where(np.asarray(day) >= 0, D(np.clip(np.asarray(day), 0, None)), "")
    V = cal.valuation_day
    D = lambda day: pd.Series(cal.date(np.asarray(day))).dt.strftime("%Y-%m-%d").to_numpy()
    polno = lambda p: POLICY_BASE + np.asarray(p) + 1
    T, K = {}, {}

    # ---- geography ---------------------------------------------------------------------
    terr_l, terr_c = res.plan.terr_liab, res.plan.terr_comp
    T["location"] = pd.DataFrame({
        "location_id": z.location_id, "zip_code": z.zip, "city": z.city, "state": "IL",
        "county": z.county + " County", "region": z.region, "latitude": z.lat.round(4), "longitude": z.lon.round(4),
        "population": z.population, "median_household_income": z.median_household_income.astype(int),
        "population_density_per_sq_mile": z.population_density_sqmi.round(0).astype(int),
        "liability_territory": np.array(rating.LEVELS["territory"])[terr_l],
        "comprehensive_territory": np.array(rating.LEVELS["territory"])[terr_c]})
    share = lambda cols: (z[[f"age_share_{c}" for c in cols]].sum(axis=1) * 100).round(1)
    T["zip_demographics"] = pd.DataFrame({
        "zip_code": z.zip, "population": z.population,
        "pct_age_16_24": share(["16_17", "18_20", "21_24"]),
        "pct_age_25_39": share(["25_29", "30_34", "35_39"]),
        "pct_age_40_64": share(["40_44", "45_49", "50_54", "55_59", "60_64"]),
        "pct_age_65_plus": share(["65_69", "70_74", "75_79", "80_84", "85_plus"]),
        "pct_white_non_hispanic": (z.pct_white_nh * 100).round(1),
        "pct_black_non_hispanic": (z.pct_black_nh * 100).round(1),
        "pct_hispanic": (z.pct_hispanic * 100).round(1),
        "pct_asian_non_hispanic": (z.pct_asian_nh * 100).round(1),
        "households": z.households, "pct_households_owner_occupied": (z.pct_owner_occupied * 100).round(1),
        "pct_households_with_vehicle": (z.households_with_vehicle / z.households * 100).round(1),
        "pct_workers_commute_by_car": (z.pct_commute_drive * 100).round(1),
        "pct_workers_commute_by_transit": (z.pct_commute_transit * 100).round(1),
        "pct_workers_from_home": (z.pct_work_from_home * 100).round(1),
        "mean_commute_minutes": z.mean_commute_minutes.round(1)})

    ag = pop.agencies
    az = z.iloc[ag.zi.clip(0)]
    T["agency"] = pd.DataFrame({
        "agency_id": ag.agency_id, "agency_name": ag.name, "channel": ag.channel,
        "city": np.where(ag.zi >= 0, az.city.to_numpy(), "Chicago"), "state": "IL",
        "zip_code": np.where(ag.zi >= 0, az.zip.to_numpy(), "60606")})
    T["underwriting_company"] = pd.DataFrame(C.COMPANIES, columns=["company_id", "company_name",
                                                                "tier", "city"]).assign(**{"state": "IL"})
    T["claim_office"] = pd.DataFrame(C.BRANCHES, columns=["claim_office_id", "office_name", "city"])
    T["catastrophe"] = pd.DataFrame(
        [(e[0], e[1], e[2], C.PERIL_DESCRIPTION[e[3]]) for e in C.CAT_EVENTS
         if cfg.start <= e[1] <= cfg.valuation],
        columns=["catastrophe_id", "event_date", "description", "peril"]).assign(note="Fictional event")
    level, out = 1.0, []
    for d, chg in C.RATE_CHANGES:
        if cfg.start <= d <= cfg.valuation:
            level *= 1 + chg
            out.append((d, round(chg * 100, 1), round(level, 4)))
    T["rate_change"] = pd.DataFrame(out, columns=["effective_date", "rate_change_pct", "cumulative_rate_level"])

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
    T["policy_term"] = pd.DataFrame({
        "policy_term_id": terms.term + 1, "policy_id": polno(terms.pol), "term_number": terms.term_no,
        "business_type": np.where(terms.new_business, "New", "Renewal"),
        "effective_date": D(terms.s), "expiration_date": D(terms.e), "offer_date": D(terms.offer_day),
        "rating_date": D(terms.rate_day),
        "cancel_date": np.where(cancelled, D(terms.cancel_day.clip(0)), ""), "cancel_reason": terms.cancel_reason,
        "nonrenewal_reason": terms.nonrenewal_reason, "vehicles_at_term_start": terms.vehicles.astype(int),
        "written_premium": terms.written.round(2), "endorsement_premium": (terms.net_written - terms.written).round(2),
        "return_premium": (-terms.returned).round(2) + 0.0, "earned_premium_before_extract": terms.before.round(2),
        "earned_premium": terms.earned.round(2), "rate_level_index": (terms.rate_level / cal.rate_level[0]).round(4)})

    last = terms.sort_values(["pol", "s"], kind="stable").groupby("pol").tail(1).set_index("pol").reindex(pol["pol"])
    status = np.where(last.cancel_day >= 0, "Cancelled", np.where(last.nonrenewal_reason != "", "Non-Renewed", "In Force"))
    end_day = np.where(last.cancel_day >= 0, last.cancel_day, last.e)
    reason = np.where(last.cancel_day >= 0, last.cancel_reason, last.nonrenewal_reason)
    ni_drv = pol.ni_drv.to_numpy()
    inception = cal.day_of(pol.first_month - pol.tenure_terms * pol.term_months, pol.dom)
    bi = [C.BI_LIMITS[i] for i in pol.bi_opt]
    # Vehicles and drivers on the policy at its latest status: on the valuation date if it is in force,
    # otherwise on its last day of cover. Counted from each vehicle's and driver's own dates, so a car
    # added or removed during the latest term is counted as it stands, not as the term began.
    as_at = np.minimum(np.where(status == "In Force", V, end_day - 1), V)
    removed_v = np.where(veh.removed_day.to_numpy() > V, -1, veh.removed_day.to_numpy())    # nothing after the valuation date is known
    removed_d = np.where(drv.removed_day.to_numpy() > V, -1, drv.removed_day.to_numpy())

    def on_policy(member_pol, added, removed):
        day = as_at[member_pol]
        return np.bincount(member_pol[(added <= day) & ((removed < 0) | (removed > day))], minlength=len(pol))
    score = pol.insurance_score
    T["policy"] = pd.DataFrame({
        "policy_id": polno(pol["pol"]), "location_id": z.location_id.to_numpy()[pol.zi],
        "agency_id": pol.agency_id, "company_id": pol.tier + 1,
        "distribution_channel": np.array(C.CHANNELS)[pol.channel],
        "original_inception_date": pd.Series(cal.start + inception.astype("timedelta64[D]")).dt.strftime("%Y-%m-%d").to_numpy(),
        "first_effective_date": D(pol.first_day), "latest_expiration_date": D(end_day),
        "term_months": pol.term_months, "policy_status": status, "status_reason": reason,
        "cancel_date": np.where(status == "Cancelled", D(end_day), ""),
        "named_insured_driver_id": ni_drv + 1,
        "number_of_drivers": on_policy(drv.pol.to_numpy(), drv.added_day.to_numpy(), removed_d),
        "number_of_vehicles": on_policy(veh.pol.to_numpy(), veh.added_day.to_numpy(), removed_v),
        "homeowner": YN[pol.homeowner.astype(int)], "multi_policy": YN[pol.multi_policy.astype(int)],
        "prior_insurance": YN[pol.prior_insurance.astype(int)],
        "insurance_score": score.astype("Int64"), "payment_plan": np.array(C.PAY_PLANS)[pol.pay_plan],
        "bi_limit": [_limit(b) for b in bi], "pd_limit": np.array(C.PD_LIMITS)[pol.bi_opt],
        "um_limit": [_limit(C.BI_LIMITS[i]) for i in pol.um_opt], "med_pay_limit": np.array(C.MED_LIMITS)[pol.med_opt]})

    # ---- drivers ------------------------------------------------------------------------------
    inc = pop.incidents
    fd = drv.added_day.to_numpy()
    recent = (inc.day.to_numpy() <= fd[inc.drv]) & (inc.day.to_numpy() > fd[inc.drv] - C.LOOKBACK_DAYS) \
        & (inc.known_day.to_numpy() <= fd[inc.drv])
    good_student = truth.good_student(drv.good_grades, drv.school_end_day, drv.dob_day, drv.added_day)
    n_viol = np.bincount(inc.drv[recent & (inc.kind != "accident")], minlength=len(drv))
    n_acc = np.bincount(inc.drv[recent & (inc.kind == "accident")], minlength=len(drv))
    T["driver"] = pd.DataFrame({
        "driver_id": drv.drv + 1, "policy_id": polno(drv.pol),
        "driver_role": np.array(["Named Insured", "Spouse", "Other Adult", "Child"])[drv.role],
        "first_name": drv.first_name, "last_name": drv.last_name, "date_of_birth": D(drv.dob_day),
        "gender": np.where(drv.male, "M", "F"), "marital_status": drv.marital, "date_first_licensed": D(drv.licensed_day),
        "added_date": D(drv.added_day), "removed_date": np.where(removed_d >= 0, D(removed_d.clip(0)), ""),
        "removal_reason": np.where(removed_d >= 0, np.array(DRIVER_REMOVAL_REASONS)[drv.removal_reason], ""),
        "good_student": YN[good_student.astype(int)], "miles_to_work": drv.commute_miles.astype(int),
        "prior_violations": n_viol, "prior_accidents": n_acc, **_sr22(cfg, inc, drv, V, D)})

    # Each incident carries the day the insurer learned of it: a violation when the conviction posts to the
    # driving record, an earlier accident when it appears on a claims-history report, and the company's own
    # claim when its payments make it chargeable. Rating uses an incident only from that day on.
    own = claims[claims.chargeable & (claims.drv >= 0)]
    acc = (inc.kind == "accident").to_numpy()
    with_us = acc & (inc.day.to_numpy() >= inception[inc.pol.to_numpy()])     # in-force book, before the extract
    records = pd.concat([
        pd.DataFrame({"drv": inc.drv, "day": inc.day, "known": inc.known_day,
                      "incident_type": inc.kind.map({"minor": "Minor Violation", "major": "Major Violation", "accident": "At-Fault Accident"}),
                      "description": np.where(with_us, "At-fault accident (company claim before the extract)",
                                              np.where(acc, "At-fault accident (prior carrier)", inc.description)),
                      "source": np.where(with_us, "Company Claim (Before Extract)", np.where(acc, "Prior Carrier Report", "Motor Vehicle Record")),
                      "claim_id": pd.array([pd.NA] * len(inc), dtype="Int64")}),
        pd.DataFrame({"drv": own.drv, "day": own.day, "known": own.chargeable_day, "incident_type": "At-Fault Accident",
                      "description": "At-fault accident (company claim)", "source": "Company Claim",
                      "claim_id": own.claim_id.astype("Int64")})], ignore_index=True)
    records = records[(records.day <= V) & (records.known <= V)].sort_values(["day", "drv"], kind="stable").reset_index(drop=True)
    T["driver_incident"] = pd.DataFrame({
        "incident_id": np.arange(1, len(records) + 1), "driver_id": records.drv + 1, "incident_date": D(records.day),
        "known_date": D(records.known), "conviction_date": _conviction_dates(cfg, records, D),
        "incident_type": records["incident_type"], "description": records.description,
        "source": records.source, "claim_id": records["claim_id"]})

    # ---- vehicles -----------------------------------------------------------------------------
    codes = _vehicle_codes(mdl)
    T["vehicle_model_year"] = pd.DataFrame({
        "vehicle_model_year_id": mdl.vehicle_id, "make": mdl.make, "model": mdl.model, "model_year": mdl.model_year,
        "body_type": mdl.body_type, "vehicle_class": mdl.vehicle_class,
        "segment": mdl.segment.str.title().replace({"Ev": "Electric"}), "fuel_type": mdl.fuel_type, "drive_type": mdl.drive,
        "engine_cylinders": mdl.cylinders.astype("Int64"), "engine_displacement_l": mdl.displacement,
        "msrp": mdl.msrp, **codes})
    vid = mdl.vehicle_id.to_numpy()[veh.model_idx]
    # A removal is recorded as a total loss only once the company has the total-loss claim. Until then the
    # extract shows what the insurer knows: the customer took a destroyed or stolen car off the policy.
    reason_v = np.where(removed_v >= 0, veh.removal_reason.to_numpy(), 0)
    claimed = np.zeros(len(veh), dtype=bool)
    tl = feats[feats.total.to_numpy().astype(bool) & ~feats.retained.to_numpy().astype(bool)]
    claimed[claims.set_index("claim_id").veh.reindex(tl.claim_id).to_numpy()] = True
    reason_v = np.where((reason_v == REMOVAL_REASONS.index("Total Loss")) & ~claimed,
                        REMOVAL_REASONS.index("Destroyed or Stolen"), reason_v)
    T["insured_vehicle"] = pd.DataFrame({
        "insured_vehicle_id": veh.veh + 1, "policy_id": polno(veh.pol), "vehicle_model_year_id": vid,
        "primary_driver_id": veh.primary_drv + 1, "ownership": veh.ownership,
        "added_date": D(veh.added_day), "removed_date": np.where(removed_v >= 0, D(removed_v.clip(0)), ""),
        "primary_use": veh.use, "annual_mileage": veh.reported_miles.astype(int),
        "parking": np.array(C.PARKING)[veh.parking], "anti_theft_device": YN[veh.anti_theft.astype(int)],
        "automatic_emergency_braking": YN[veh.adas.astype(int)],
        "collision_coverage": YN[veh.has_coll.astype(int)],
        "collision_deductible": np.where(veh.has_coll, np.array(C.COLL_DEDUCTIBLES)[veh.coll_ded_opt], 0),
        "comprehensive_coverage": YN[veh.has_comp.astype(int)],
        "comprehensive_deductible": np.where(veh.has_comp, np.array(C.COMP_DEDUCTIBLES)[veh.comp_ded_opt], 0),
        "full_glass_coverage": YN[veh.full_glass.astype(int)],
        "rental_reimbursement": np.where(veh.has_rent, [f"{d}/{m}" for d, m in np.array(C.RENTAL_OPTIONS)[veh.rent_opt]], ""),
        "towing_and_labor": YN[veh.has_tow.astype(int)], "vin_prefix": codes["vin_pattern"].to_numpy()[veh.model_idx],
        "removal_reason": np.array(REMOVAL_REASONS)[reason_v],
        "replaces_insured_vehicle_id": pd.Series(veh.replaces + 1).where(veh.replaces >= 0).astype("Int64")})

    # One row per vehicle per endorsement period: a mid-term change ends the policy's rows and re-rates it.
    rv = rows.veh.to_numpy()
    tcan = terms.set_index("term").cancel_day.reindex(rows.term).to_numpy()
    cover_end = np.where(tcan >= 0, np.minimum(rows.sched, tcan), rows.sched)
    # endorsement 0 is the term as written; a term that starts with no car (a replacement still to come) has none
    late = rows.groupby("term").s.transform("min").to_numpy() > terms.set_index("term").s.reindex(rows.term).to_numpy()
    endorsement = rows.groupby("term").s.rank(method="dense").astype(int) - 1 + late
    T["exposure"] = pd.DataFrame({
        "exposure_id": rows.row + 1, "policy_term_id": rows.term + 1, "policy_id": polno(rows.pol),
        "endorsement_number": endorsement, "change_reason": rows.reason,
        "insured_vehicle_id": rv + 1, "vehicle_model_year_id": vid[rv], "model_year": veh.model_year.to_numpy()[rv],
        "driver_id": rows.drv + 1, "location_id": z.location_id.to_numpy()[rows.zi], "rating_date": D(rows.rated_on),
        "rated_driver_age": np.floor(rows.driver_age).astype(int),
        "rated_driver_class": np.array(rating.CLASS_LEVELS)[rows.class_code],
        "rated_violation_points": rows.violation_points, "rated_at_fault_accidents": rows.at_fault_accidents,
        "rated_good_student": YN[rows.good_student.astype(int)], "rated_married": YN[rows.married.astype(int)],
        "rated_homeowner": YN[rows.homeowner.astype(int)], "inexperienced_operator": YN[rows.inexperienced.astype(int)],
        "occasional_youthful_operator": YN[rows.occasional_youthful.astype(int)],
        "multi_car_discount": YN[rows.multi_car.astype(int)], "multi_policy_discount": YN[rows.multi_policy.astype(int)],
        "paid_in_full_discount": YN[rows.paid_in_full.astype(int)],
        "bi_limit": [_limit(C.BI_LIMITS[i]) for i in rows.bi_opt], "pd_limit": np.array(C.PD_LIMITS)[rows.bi_opt],
        "um_limit": [_limit(C.BI_LIMITS[i]) for i in rows.um_opt], "med_pay_limit": np.array(C.MED_LIMITS)[rows.med_opt],
        "collision_deductible": rows.coll_ded, "comprehensive_deductible": rows.comp_ded,
        "full_glass_coverage": YN[rows.full_glass.to_numpy().astype(int)],
        "rental_reimbursement": np.where(rows.rent_opt >= 0, np.array([f"{d}/{m}" for d, m in C.RENTAL_OPTIONS])[rows.rent_opt.clip(0)], ""),
        "towing_and_labor": YN[rows.has_tow.to_numpy().astype(int)],
        "telematics_enrolled": YN[rows.tele_on.to_numpy().astype(int)],
        "telematics_discount_pct": np.round(rows.tele_disc.to_numpy() * 100).astype(int),
        "tenure_years": rows.tenure_years.round(1), "vehicle_value": rows.acv.round(-1).astype(int),
        "bi_premium": rows.prem_BI, "pd_premium": rows.prem_PD, "um_premium": rows.prem_UM,
        "med_pay_premium": rows.prem_MED, "collision_premium": rows.prem_COLL, "comprehensive_premium": rows.prem_COMP,
        "rental_premium": rows.prem_RENT, "towing_premium": rows.prem_TOW,
        "total_premium": rows.total_premium.round(2), "coverage_start_date": D(rows.s), "coverage_end_date": D(cover_end),
        "earned_exposure": rows.earned_exposure.round(4), "earned_premium": rows.earned_premium})

    # ---- claims ---------------------------------------------------------------------------------
    f = feats
    f = f.assign(incurred=f.paid_loss + f.case_reserve, recovery=f.salvage_rec + f.subro_rec)
    f["net_incurred"] = f.incurred - f.recovery
    T["claim_feature"] = pd.DataFrame({
        "claim_feature_id": f.feature_id, "claim_id": f.claim_id, "coverage_code": f.cvg,
        "coverage": f.cvg.map(C.COVERAGE_NAMES), "um_uim_type": f.um_type, "claimant_number": f.claimant,
        "feature_status": np.where(f.closed, "Closed", np.where(f.reopened, "Reopened", "Open")), "open_date": D(f.open_day),
        "close_date": np.where(f.closed, D(f.status_close_day.clip(upper=V)), ""),
        "reopen_date": np.where(f.reopened, D(f.reopen_day.clip(0)), ""),
        "paid_loss": f.paid_loss.round(2), "case_reserve": f.case_reserve.round(2), "incurred_loss": f.incurred.round(2),
        "salvage_recovery": f.salvage_rec.round(2), "subrogation_recovery": f.subro_rec.round(2),
        "net_incurred_loss": f.net_incurred.round(2),
        "other_insurer_payment": pd.Series(f.offset.to_numpy()).where(f.um_type.to_numpy() == "Underinsured").round(2).to_numpy(),
        "paid_expense": f.paid_expense.round(2),
        "paid_dcc_expense": f.paid_dcc.round(2), "paid_ao_expense": f.paid_ao.round(2),
        "expense_reserve": f.expense_reserve.round(2),
        "injury_type": f.injury_type, "attorney_represented": YN[f.attorney.astype(int)],
        "attorney_date": np.where(f.attorney, opt_date(f.attorney_day), ""),
        "litigation": YN[f.litigated.astype(int)], "suit_date": np.where(f.litigated, opt_date(f.suit_day), ""),
        "total_loss": YN[f.total.astype(int)],
        "closed_without_payment": YN[(f.closed & (f.paid_loss == 0)).astype(int)],
        "owner_retained_salvage": YN[f.retained.astype(bool).astype(int)]})
    cg = f.groupby("claim_id").agg(paid=("paid_loss", "sum"), reserve=("case_reserve", "sum"), recovery=("recovery", "sum"),
                                   net=("net_incurred", "sum"), expense=("paid_expense", "sum"), n=("fid", "size"),
                                   exp_reserve=("expense_reserve", "sum"),
                                   open=("closed", lambda s: (~s).any()), close_day=("status_close_day", "max"),
                                   lit=("litigated", "any"), injury=("cvg", lambda s: s.isin(["BI", "UM"]).any()),
                                   total=("total", "any")).reindex(claims.claim_id)
    zi_at_loss = rows.set_index("row").zi.reindex(claims.row).to_numpy()
    city = (z.region.to_numpy() == "City of Chicago")[zi_at_loss]
    peril = claims.peril.to_numpy()
    branch = np.select([claims.cat.to_numpy() >= 0, cg.injury.to_numpy(), (peril == "THEFT_TOTAL") | cg.total.to_numpy(),
                        peril == "GLASS", city], [6, 3, 5, 4, 1], default=2)
    claimant = np.where(claims.drv >= 0, claims.drv, ni_drv[claims.pol]) + 1
    cat_id = np.where(claims.cat >= 0, np.array([e[0] for e in C.CAT_EVENTS])[claims.cat.clip(0)], "")
    T["claim"] = pd.DataFrame({
        "claim_id": claims.claim_id, "policy_id": polno(claims.pol), "policy_term_id": claims.term + 1,
        "exposure_id": claims.row + 1, "involved_driver_id": claimant, "insured_vehicle_id": claims.veh + 1,
        "vehicle_model_year_id": vid[claims.veh], "loss_date": D(claims.day), "report_date": D(claims.report_day),
        "close_date": np.where(cg.open.to_numpy(), "", D(cg.close_day.clip(upper=V))),
        "claim_status": np.where(cg.open.to_numpy(), "Open", "Closed"), "cause_of_loss": claims.peril,
        "claim_description": claims.peril.map(C.PERIL_DESCRIPTION), "at_fault": YN[claims.at_fault.astype(int)],
        "catastrophe_id": cat_id, "feature_count": cg.n.to_numpy(), "paid_loss": cg.paid.round(2).to_numpy(),
        "case_reserve": cg.reserve.round(2).to_numpy(), "recoveries": cg.recovery.round(2).to_numpy(),
        "net_incurred_loss": cg.net.round(2).to_numpy(), "paid_expense": cg.expense.round(2).to_numpy(),
        "expense_reserve": cg.exp_reserve.round(2).to_numpy(),
        "litigation": YN[cg.lit.to_numpy().astype(int)], "claim_office_id": branch,
        "police_report": YN[claims.police_report.astype(int)],
        "insured_fault_pct": pd.array(np.where(claims.fault_pct >= 0, claims.fault_pct, 0), dtype="Int64"),
        "siu_referral": YN[(claims.siu_day >= 0).astype(int)], "siu_referral_date": opt_date(claims.siu_day)})
    T["claim"].loc[claims.fault_pct.to_numpy() < 0, "insured_fault_pct"] = pd.NA
    T["claim_payment"] = pd.DataFrame({
        "payment_id": pays.payment_id, "claim_feature_id": pays.feature_id, "claim_id": pays.claim_id,
        "payment_date": D(pays.day), "payment_type": pays.kind, "transaction_type": pays.txn, "amount": pays.amount})
    rs = dev["reserves"]
    T["claim_reserve_transaction"] = pd.DataFrame({
        "reserve_transaction_id": rs.reserve_id, "claim_feature_id": rs.feature_id, "claim_id": rs.claim_id,
        "transaction_date": D(rs.day), "reserve_type": rs.rtype, "transaction_type": rs.txn,
        "change_amount": rs.delta.round(2), "outstanding_reserve": rs.outstanding.round(2)})

    T.update(_telematics_tables(res.tele, terms, V, D, polno))
    known_veh = veh.assign(removal_reason=reason_v)
    T["premium_transaction"] = _transactions(cfg, cal, terms, rows, known_veh, D, polno)
    T["customer_contact"] = _communications(cfg, cal, pol, terms, rows, claims, cg, known_veh, D, polno)

    # ---- answer key ---------------------------------------------------------------------------------
    exp_cols = [f"exp_{c}" for c in C.COVERAGES]
    K["exposure_truth"] = pd.DataFrame({"exposure_id": rows.row + 1, **{f"expected_loss_{c.lower()}": rows[f"exp_{c}"].round(2) for c in C.COVERAGES},
                                    "expected_loss_total": rows[exp_cols].sum(axis=1).round(2)})
    K["driver_truth"] = pd.DataFrame({"driver_id": drv.drv + 1, "latent_risk_factor": drv.latent.round(4),
                                      "race_ethnicity": np.array(names.GROUP_LABELS)[drv.race_group.to_numpy().astype(int)]})
    K["insured_vehicle_truth"] = pd.DataFrame({"insured_vehicle_id": veh.veh + 1, "true_annual_mileage": veh.true_miles.round(0).astype(int),
                                       "kia_hyundai_theft_exposure": YN[veh.kia_hyundai.astype(int)]})
    zt = pop.zip_truth
    K["location_truth"] = pd.DataFrame({
        "location_id": zt.location_id, "zip_code": zt.zip, "hazard_basis": z.hazard_basis,
        "public_crash_hazard_index": z.crash_hazard_index.round(4), "true_crash_hazard": zt.true_crash_hazard.round(4),
        "public_theft_hazard_index": z.theft_hazard_index.round(4), "true_theft_hazard": zt.true_theft_hazard.round(4),
        "other_driver_uninsured_probability": zt.p_other_driver_uninsured.round(4)})
    un = dev["unreported"]
    K["unreported_claim"] = pd.DataFrame({
        "unreported_claim_id": np.arange(1, len(un) + 1), "policy_id": polno(un.pol), "exposure_id": un.row + 1, "insured_vehicle_id": un.veh + 1, "coverage_code": un.cvg,
        "cause_of_loss": un.peril, "loss_date": D(un.day), "eventual_report_date": D(un.open_day),
        "ultimate_paid_loss": un.paid.round(2), "ultimate_recovery": (un.salvage + un.subro).round(2)})
    fu = feats
    K["claim_feature_truth"] = pd.DataFrame({
        "claim_feature_id": fu.feature_id, "ultimate_paid_loss": fu.paid.round(2),
        "ultimate_recovery": (fu.salvage + fu.subro).round(2), "ultimate_expense": fu.expense.round(2),
        "eventual_reopen_date": np.where(fu.reopen_day >= 0, D(fu.reopen_day.clip(0)), ""),
        "eventual_close_date": D(fu.final_close_day)})
    return T, K


def _vehicle_codes(mdl: pd.DataFrame) -> dict:
    """Synthetic VIN patterns and vehicle rating symbols, one per make, model and model year.

    The VIN pattern has the shape statistical plans and symbol tables use (positions 1-10, with the check digit in
    position 9 masked) but is fictional: position 1 is "0", which no manufacturing region uses, and positions 2-8
    are derived from the make and model, so it can be joined on but identifies no real vehicle. The symbols are
    this dataset's own scales, not ISO's (which are licensed): a physical damage symbol from 1 to 30 that rises
    with the model year's price new (and for sports, luxury and electric models), and a liability symbol from 1
    to 5 from the model's segment and body type, which drive true liability costs."""
    code = lambda x, k: "".join(VIN_CHARS[(x // len(VIN_CHARS) ** j) % len(VIN_CHARS)] for j in range(k))
    wmi = {m: "0" + code(zlib.crc32(m.encode()), 2) for m in mdl.make.unique()}
    vds = {(a, b): code(zlib.crc32(f"model-{a}-{b}".encode()), 5) for a, b in zip(mdl.make, mdl.model)}
    pattern = [wmi[a] + vds[(a, b)] + "*" + VIN_YEAR[(y - 1980) % len(VIN_YEAR)] for a, b, y in zip(mdl.make, mdl.model, mdl.model_year)]
    seg, body = mdl.segment.to_numpy(), mdl.body_type.to_numpy()
    pd_symbol = np.floor(np.log(np.maximum(mdl.msrp.to_numpy(), 9_000) / 9_000) / np.log(1.09)) + 1 \
        + np.select([seg == "sports", np.isin(seg, ["luxury", "ev"])], [2, 1], default=0)
    liab = np.array([C.SEGMENT_FREQ[x] for x in seg]) * (np.array([C.SEGMENT_PD_SEV.get(x, 1.0) for x in seg])
                                                         * np.where(body == "SUV", C.SUV_PD_SEV, 1.0)
                                                         + np.array([C.SEGMENT_BI_SEV.get(x, 1.0) for x in seg])) / 2
    return {"vin_pattern": pd.Series(pattern), "physical_damage_symbol": np.clip(pd_symbol, 1, 30).astype(int),
            "liability_symbol": 1 + np.searchsorted([0.95, 1.03, 1.10, 1.20], liab)}


def _telematics_tables(tele: dict, terms: pd.DataFrame, V: int, D, polno) -> dict:
    """The telematics programme as the insurer records it: enrolments, and each car's driving scores. A score is
    calculated on a policy's rating date for the driving since the last one, and its discount applies from the
    term being rated. What happened after the valuation date is not shown."""
    en, sc = tele["enrol"], tele["scores"]
    en = en[en.start <= V]
    ended = (en.end >= 0) & (en.end <= V)
    out = {"telematics_enrollment": pd.DataFrame({
        "enrollment_id": en.eid + 1, "policy_id": polno(en.pol), "programme": telematics.PROGRAMME,
        "device_type": np.array(telematics.DEVICE_TYPES)[en.device], "enrollment_date": D(en.start),
        "participation_discount_pct": int(round(telematics.PARTICIPATION_DISCOUNT * 100)),
        "end_date": np.where(ended, D(en.end.clip(0)), ""), "end_reason": np.where(ended, en.reason, "")})}
    sc = sc[sc.e <= V].sort_values(["e", "eid", "veh"], kind="stable").reset_index(drop=True)
    term_id = terms.set_index(["pol", "s"]).term
    applied = term_id.reindex(pd.MultiIndex.from_arrays([sc.pol, sc.applies_s])).to_numpy()
    per100 = lambda x: np.round(x, 2)
    out["telematics_score"] = pd.DataFrame({
        "score_id": np.arange(1, len(sc) + 1), "enrollment_id": sc.eid + 1, "policy_id": polno(sc.pol),
        "insured_vehicle_id": sc.veh + 1, "driver_id": sc.drv + 1, "period_start_date": D(sc.s), "period_end_date": D(sc.e),
        "days_monitored": sc.days, "trips": sc.trips, "miles_driven": np.round(sc.miles).astype(int),
        "hard_brakes_per_100_miles": per100(sc.hard_brakes), "rapid_accelerations_per_100_miles": per100(sc.rapid_accels),
        "speeding_pct": per100(sc.speeding_pct), "phone_use_minutes_per_100_miles": per100(sc.phone_minutes),
        "night_driving_pct": per100(sc.night_pct),
        "driving_score": pd.array(np.where(sc.score >= 0, sc.score, pd.NA), dtype="Int64"),
        "earned_discount_pct": pd.array(np.where(sc.score >= 0, np.round(sc.discount * 100), pd.NA), dtype="Int64"),
        "applied_to_policy_term_id": pd.array(np.where(np.isnan(applied), pd.NA, applied + 1), dtype="Int64")})
    return out


def _sr22(cfg, inc: pd.DataFrame, drv: pd.DataFrame, V: int, D) -> dict:
    """SR-22 filings: after a conviction for driving under the influence, driving while suspended or leaving
    the scene, the insurer files proof of insurance with the state for three years (the latest filing shown)."""
    q = inc[inc.description.isin(SR22_VIOLATIONS) & (inc.known_day <= V)]
    latest = q.groupby("drv").known_day.max().reindex(drv.drv).to_numpy()
    R = stream(cfg.seed, "sr22")
    filed = np.maximum(np.nan_to_num(latest, nan=-10 ** 6), drv.added_day.to_numpy()) + R.integers(0, 8, len(drv))
    end = np.nan_to_num(latest, nan=-10 ** 6) + int(SR22_YEARS * 365.25)
    on = ~np.isnan(latest) & (end > filed) & (filed <= V) & ((drv.removed_day.to_numpy() < 0) | (drv.removed_day.to_numpy() > filed))
    # dates before the start are real dates (day numbers count back from it), so they are written as they are
    return {"sr22_filed_date": np.where(on, D(np.where(on, filed, 0)), ""), "sr22_end_date": np.where(on, D(np.where(on, end, 0)), "")}


def _conviction_dates(cfg, records: pd.DataFrame, D) -> np.ndarray:
    """Court conviction date for violations: a few days to two weeks before it posts to the driving record."""
    R = stream(cfg.seed, "convictions")
    mvr = records.source.to_numpy() == "Motor Vehicle Record"
    day, known = records.day.to_numpy(), records.known.to_numpy()
    # on or after the day after the incident, and before the record posts (a conviction before the start keeps
    # its own date: clipping it to the start would put it after the day it became known)
    conv = np.minimum(np.maximum(known - R.integers(3, 15, len(records)), day + 1), known)
    return np.where(mvr, D(conv), "")


def _transactions(cfg, cal, terms, rows, veh, D, polno) -> pd.DataFrame:
    """The premium ledger: one row per policy transaction, as a policy system books it. New business and
    renewals write the premium for the vehicles on the policy at the start; each mid-term change is an
    endorsement adding or returning premium pro rata to the end of the term; a cancellation returns the
    rest. Transactions are booked on a processed (accounting) date, a few days after the change for most
    endorsements and cancellations; those not yet processed at the valuation date are not in the extract."""
    R = stream(cfg.seed, "transactions")
    t = terms.set_index("term")
    e, s0 = t.e.reindex(rows.term).to_numpy(), t.s.reindex(rows.term).to_numpy()
    span = e - s0
    tp = rows.total_premium.to_numpy()
    x, a = rows.x.to_numpy(), rows.s.to_numpy()
    kind = rows.end_kind.to_numpy()
    starts = a > s0
    ends = np.isin(kind, [END_ENDORSED, END_GONE])
    removal = np.where(kind == END_GONE, np.array(REMOVAL_REASONS)[veh.removal_reason.to_numpy()[rows.veh.to_numpy()]], "")
    removal = np.where(removal == "", "", "Vehicle Removed (" + removal + ")")
    endorse = pd.concat([
        pd.DataFrame({"term": rows.term[starts], "day": a[starts], "amount": (tp * (e - a) / span)[starts],
                      "reason": rows.reason[starts].fillna("")}),
        pd.DataFrame({"term": rows.term[ends], "day": x[ends], "amount": -(tp * (e - x) / span)[ends], "reason": removal[ends]})])
    endorse = endorse.groupby(["term", "day"], sort=True).agg(
        amount=("amount", "sum"), reason=("reason", lambda r: "; ".join(dict.fromkeys(x_ for x_ in r if x_)))).reset_index()
    endorse["kind"] = "Endorsement"
    endorse["processed"] = endorse.day + np.floor(R.exponential(5.0, len(endorse))).astype(int)
    start = pd.DataFrame({"term": terms.term, "day": terms.s, "amount": terms.written, "reason": "",
                          "kind": np.where(terms.new_business, "New Business", "Renewal"), "processed": terms.rate_day})
    c = terms[terms.cancel_day >= 0]
    cancel = pd.DataFrame({"term": c.term, "day": c.cancel_day, "amount": -c.returned, "reason": c.cancel_reason,
                           "kind": "Cancellation", "processed": c.cancel_day + np.floor(R.exponential(3.0, len(c))).astype(int)})
    tx = pd.concat([start, endorse, cancel], ignore_index=True)
    tx = tx[tx.processed <= cal.valuation_day]
    tx["order"] = tx.kind.map({"New Business": 0, "Renewal": 0, "Endorsement": 1, "Cancellation": 2})
    tx = tx.sort_values(["processed", "term", "day", "order"], kind="stable").reset_index(drop=True)
    pol = t.pol.reindex(tx.term).to_numpy()
    return pd.DataFrame({
        "transaction_id": np.arange(1, len(tx) + 1), "policy_id": polno(pol), "policy_term_id": tx.term + 1,
        "transaction_type": tx.kind, "effective_date": D(tx.day), "processed_date": D(tx.processed),
        "change_reason": tx.reason, "written_premium": tx.amount.round(2) + 0.0})


def _communications(cfg, cal, pol, terms, rows, claims, cg, veh, D, polno) -> pd.DataFrame:
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
    add(rn.pol, rn.offer_day, "Renewal Offer")
    rr = rn[rn.rate_day > rn.offer_day]
    add(rr.pol, rr.rate_day, "Revised Renewal Offer")
    bill = terms[(pol.pay_plan.to_numpy()[terms.pol] == 2) & (R.random(len(terms)) < 0.45)]
    add(bill.pol, bill.s + R.integers(25, 150, len(bill)), "Payment Reminder", phone=0.10)
    npay = terms[terms.cancel_reason == "Non-Payment"]
    add(npay.pol, npay.cancel_day - 21, "Past Due Notice", phone=0.25)
    add(npay.pol, npay.cancel_day - 10, "Notice of Cancellation", digital_ok=False)
    other = terms[(terms.cancel_day >= 0) & (terms.cancel_reason != "Non-Payment")]
    add(other.pol, other.cancel_day, "Cancellation Confirmation")
    # every endorsement (a mid-term change re-rating the policy) and every car taken off after a loss
    term_start = terms.set_index("term").s.reindex(rows.term).to_numpy()
    changes = rows.loc[rows.s.to_numpy() > term_start, ["pol", "s"]].rename(columns={"s": "day"})
    lost = veh[veh.removal_reason.isin([REMOVAL_REASONS.index("Total Loss"), REMOVAL_REASONS.index("Destroyed or Stolen")])]
    changes = pd.concat([changes, pd.DataFrame({"pol": lost.pol, "day": lost.removed_day})]).drop_duplicates()
    add(changes.pol, changes.day, "Policy Change Confirmation")
    add(claims.pol, claims.report_day, "Claim Acknowledgement", phone=0.45)
    closed = ~cg.open.to_numpy()
    add(claims.pol[closed], cg.close_day.to_numpy()[closed], "Claim Closure Notice", phone=0.10)

    c = pd.concat(parts, ignore_index=True)
    c = c[(c.day >= 0) & (c.day <= V)].sort_values(["day", "pol", "purpose"], kind="stable").reset_index(drop=True)
    return pd.DataFrame({"contact_id": [f"CM{i:07d}" for i in range(1, len(c) + 1)], "contact_method": c.kind,
                         "policy_id": polno(c.pol), "contact_date": D(c.day), "purpose": c.purpose})


def write(tables: dict, key: dict, plan, cfg: C.Config, summary: dict) -> None:
    out = Path(cfg.out_dir)
    (out / "answer_key").mkdir(parents=True, exist_ok=True)
    for name, df in tables.items():
        df.to_csv(out / f"{name}.csv", index=False, lineterminator="\n")
    for name, df in key.items():
        df.to_csv(out / "answer_key" / f"{name}.csv", index=False, lineterminator="\n")
    (out / "answer_key" / "rating_plan.json").write_text(json.dumps(rating.to_json(plan), indent=1) + "\n")
    (out / "run_summary.json").write_text(json.dumps(summary, indent=1) + "\n")
