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
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import validate  # noqa: E402  (load and rebuild: the totals worked out from the published records)


_TABLES: dict = {}


def read(folder: Path, name: str, **kw) -> pd.DataFrame:
    """A table of the output folder, with the totals validate.rebuild works out from the records (earned exposure and
    premium, each feature's and claim's paid and incurred amounts, ...) and a few more used below."""
    folder = Path(folder)
    if folder.name == "answer_key":
        return pd.read_csv(folder / f"{name}.csv", keep_default_na=False, na_values=[""], low_memory=False, **kw)
    if folder not in _TABLES:
        summary = json.loads((folder / "run_summary.json").read_text())
        t = validate.rebuild(validate.load(folder), summary["start"], summary["valuation"])
        f, term, pol, veh = t["claim_feature"], t["policy_term"], t["policy"], t["insured_vehicle"]
        f["closed_without_payment"] = np.where((f.feature_status == "Closed") & (f.paid_loss == 0), "Y", "N")
        ends = term.assign(end=term.cancel_date.fillna(term.expiration_date)).groupby("policy_id")
        pol["first_effective_date"] = pol.policy_id.map(ends.effective_date.min())
        pol["latest_expiration_date"] = pol.policy_id.map(ends.end.max())
        val = summary["valuation"]
        on = (veh.added_date <= val) & ~(veh.removed_date <= val)
        pol["number_of_vehicles"] = pol.policy_id.map(veh[on].groupby("policy_id").size()).fillna(0).astype(int)
        _TABLES[folder] = t
    return _TABLES[folder][name].copy()


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
    p("telematics", f"{len(enrol):,} enrollments, {len(score):,} scores")

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
    p("telematics mileage", f"annualized miles above reported for {(ratio > 1).mean():.0%} of scored windows (median {ratio.median() - 1:+.0%})")

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


def operations(out: Path) -> None:
    """Figures on the segments, the calendar, identifiers, billing and claim payments."""
    p = lambda label, value: print(f"  {label}: {value}")
    pol, term, ex, clm, feat = read(out, "policy"), read(out, "policy_term"), read(out, "exposure"), read(out, "claim"), read(out, "claim_feature")
    truth = read(out / "answer_key", "exposure_truth")
    offers, tx, pay = read(out, "renewal_offer"), read(out, "premium_transaction"), read(out, "claim_payment")
    inv, rec, emp, vend, agency = (read(out, n) for n in ("billing_invoice", "billing_receipt", "employee", "vendor", "agency"))
    plan = json.loads((out / "answer_key" / "rating_plan.json").read_text())

    print("DISCOUNTS (bodily injury: filed, and what the risk would justify)")
    for k, d in plan["filed_discounts"].items():
        ind = plan["relativities_indicated"]["BI"][k]
        base = max(ind.values()) if k != "tenure" else list(ind.values())[0]
        p(k, f"filed {list(d['factors'].values())}; indicated {[round(v / base, 3) for v in ind.values()]}")

    print("SEGMENTS (expected loss ratio from the answer key; actual in brackets)")
    j = ex.merge(truth[["exposure_id", "expected_loss_total"]], on="exposure_id").merge(
        term[["policy_term_id", "business_type"]], on="policy_term_id").merge(
        pol[["policy_id", "distribution_channel", "payment_plan", "agency_id", "homeowner", "multi_policy", "prior_insurance"]], on="policy_id")
    inside = clm[clm.loss_date >= "2022-01-01"]           # accidents in the extract, against the exposure it earns
    j["loss"] = inside.groupby("exposure_id").net_incurred_loss.sum().reindex(j.exposure_id).fillna(0).to_numpy()
    j["tenure"] = pd.cut(j.tenure_years, [-1, 0.01, 1, 3, 6, 100], labels=["new", "up to 1 year", "1 to 3", "3 to 6", "6 or more"])
    show = lambda col: "; ".join(f"{k} {g.expected_loss_total.sum() / g.earned_premium.sum():.1%} ({g.loss.sum() / g.earned_premium.sum():.1%})"
                                 for k, g in j.groupby(col, observed=True))
    for col in ("business_type", "tenure", "distribution_channel", "payment_plan", "multi_car_discount", "rated_homeowner",
                "multi_policy", "prior_insurance"):
        p(col, show(col))
    g = j.groupby("agency_id").agg(prem=("earned_premium", "sum"), exp=("expected_loss_total", "sum"), cy=("earned_exposure", "sum"))
    elr = g.exp / g.prem
    big = elr[g.cy >= 500]
    p("agencies", f"{len(agency)}; the {len(big)} with 500+ car-years: expected loss ratio {big.min():.1%} to {big.max():.1%} "
      f"(10th percentile {big.quantile(.1):.1%}, 90th {big.quantile(.9):.1%})")
    d = pol[pd.to_datetime(pol.first_effective_date) >= "2022-01-01"]
    c = clm.merge(d[["policy_id", "first_effective_date"]], on="policy_id")
    c["d"] = (pd.to_datetime(c.loss_date) - pd.to_datetime(c.first_effective_date)).dt.days
    life = (pd.to_datetime(d.latest_expiration_date).clip(upper=pd.Timestamp("2026-12-31")) - pd.to_datetime(d.first_effective_date)).dt.days
    early = []
    for a_, b_ in ((0, 30), (30, 90), (90, 180), (180, 365), (365, 730), (730, 1460)):
        expo = (np.clip(life, a_, b_) - a_).clip(lower=0).sum() / 365.25
        early.append(f"days {a_}-{b_}: {((c.d >= a_) & (c.d < b_)).sum() / expo * 100:.1f}")
    p("claims per 100 policy-years since a new policy began", "; ".join(early))
    o = offers[(offers.underwriting_decision == "Renew") & offers.outcome.isin(["Renewed", "Insured Did Not Renew"])].merge(
        pol[["policy_id", "distribution_channel", "payment_plan"]], on="policy_id").merge(
        term[["policy_term_id", "term_number"]], left_on="expiring_policy_term_id", right_on="policy_term_id")
    o["kept"] = o.outcome == "Renewed"
    pol_term = pol.set_index("policy_id").term_months.reindex(o.policy_id).to_numpy()
    p("renewal rate by channel", (o.groupby("distribution_channel").kept.mean() * 100).round(1).to_dict())
    p("renewal rate by payment plan", (o.groupby("payment_plan").kept.mean() * 100).round(1).to_dict())
    p("renewal rate, first renewal against later (six-month terms)",
      (o[pol_term == 6].groupby(o.term_number[pol_term == 6] == 1).kept.mean() * 100).round(1).to_dict())

    print("CALENDAR")
    wd = lambda s_: (pd.to_datetime(s_.dropna()).dt.dayofweek.value_counts(normalize=True).sort_index() * 100).round(1).tolist()
    crash = clm[clm.cause_of_loss.isin(["AF_MV", "AF_SV", "NAF"])]
    p("crash loss dates, Monday to Sunday (%)", wd(crash.loss_date))
    p("report dates", wd(clm.report_date))
    p("claim payment dates", wd(pay.payment_date))
    q = read(out, "quote")
    p("agent quote dates", wd(q[q.distribution_channel != "Direct"].quote_date))
    nb = term[(term.business_type == "New") & (term.effective_date >= "2022-01-01")]
    p("new business starting on the 1st", f"{(pd.to_datetime(nb.effective_date).dt.day == 1).mean():.1%}")
    daily = pd.Series(0, index=pd.date_range("2022-01-01", "2026-12-31")).add(pd.to_datetime(crash.loss_date).value_counts(), fill_value=0)
    top = daily.nlargest(3)
    p("crash claims a day", f"mean {daily.mean():.1f}, variance {daily.var():.1f}; busiest days "
      + ", ".join(f"{k.date()} ({int(v)})" for k, v in top.items()))
    xmas = daily[daily.index.strftime("%m-%d") == "12-25"].mean()
    p("crash claims on Christmas Day against the December average", f"{xmas:.1f} against {daily[daily.index.month == 12].mean():.1f}")
    bi = feat[(feat.coverage_code == "BI") & (feat.paid_loss > 0)].paid_loss
    p("paid bodily injury settlements", f"{len(bi):,}; whole dollars {(np.round(bi * 100) % 100 == 0).mean():.1%}; "
      f"multiples of $250 {(np.round(bi * 100) % 25_000 == 0).mean():.1%}")

    print("IDENTIFIERS")
    p("policy numbers", f"{pol.policy_number.min()} to {pol.policy_number.max()}")
    p("examples", f"claim {clm.claim_number.iloc[len(clm) // 2]}, feature {feat.feature_number.iloc[len(feat) // 2]}, "
      f"VIN {read(out, 'insured_vehicle').vin.iloc[1000]}, quote {q.quote_number.iloc[len(q) // 2]}")

    print("BILLING AND COMMISSION")
    p("bills / receipts", f"{len(inv):,} / {len(rec):,}; {inv.invoice_status.value_counts().to_dict()}; {inv.invoice_type.value_counts().to_dict()}")
    paid = inv[inv.invoice_status == "Paid"]
    late = (pd.to_datetime(paid.paid_date) - pd.to_datetime(paid.due_date)).dt.days
    p("paid more than 5 days late", f"{(late > 5).mean():.1%}")
    p("receipts", f"{rec.receipt_type.value_counts().to_dict()}; methods {rec.payment_method.value_counts(normalize=True).round(3).to_dict()}")
    p("fees collected", f"installment ${paid.installment_fee.sum():,.0f}, late and returned-payment ${paid.late_fee.sum():,.0f}")
    op, wo = inv[inv.invoice_status == "Open"], inv[inv.invoice_status == "Written Off"]
    p("receivable at the valuation date", f"${op.amount_due.sum():,.0f} on {len(op):,} bills; written off ${wo.amount_due.sum():,.0f} on {len(wo):,}")
    p("refunds", f"${-rec[rec.receipt_type == 'Refund'].amount.sum():,.0f}")
    ch = pol.set_index("policy_id").distribution_channel.reindex(tx.policy_id).to_numpy()
    p("commission", f"${tx.commission_amount.sum():,.0f} on ${tx.written_premium.sum():,.0f} written "
      + "; ".join(f"{k} {tx.commission_amount[ch == k].sum() / tx.written_premium[ch == k].sum():.1%}" for k in sorted(set(ch))))

    print("CLAIM PAYMENTS")
    p("payees", pay.payee_type.value_counts().to_dict())
    p("methods and status", f"{pay.payment_method.value_counts().to_dict()}; {pay.payment_status.value_counts().to_dict()}")
    cut = pay[pay.check_number.notna() & (pay.transaction_type != "Void")]
    p("checks", f"{len(cut):,}, numbers {int(cut.check_number.min())} to {int(cut.check_number.max())}")
    e = emp.set_index("employee_id")
    p("approved by", e.job_title.reindex(pay.approved_by_employee_id).value_counts().to_dict())
    p("staff", f"{len(emp)}: {emp.job_title.value_counts().to_dict()}; {emp.termination_date.notna().sum()} left")
    used = pay[pay.vendor_id.notna()].merge(vend, on="vendor_id")
    shops = used[used.vendor_type == "Body Shop"].groupby("vendor_id").size().sort_values(ascending=False)
    p("vendors", f"{len(vend)} on file, {used.vendor_id.nunique()} paid; the ten busiest body shops take {shops.head(10).sum() / shops.sum():.0%} of body-shop payments")


def market_and_ledger(out: Path) -> None:
    """Figures on agencies, the market cycle, retention after a claim, physical damage and the general ledger."""
    p = lambda label, value: print(f"  {label}: {value}")
    pol, term, ex, clm, feat = read(out, "policy"), read(out, "policy_term"), read(out, "exposure"), read(out, "claim"), read(out, "claim_feature")
    agency, quote, tx, stmt = read(out, "agency"), read(out, "quote"), read(out, "premium_transaction"), read(out, "agency_statement")
    gl, acct, offers = read(out, "gl_journal"), read(out, "gl_account"), read(out, "renewal_offer")
    summary = json.loads((out / "run_summary.json").read_text())
    start, val = pd.Timestamp(summary["start"]), pd.Timestamp(summary["valuation"])
    eff, end = pd.to_datetime(term.effective_date), pd.to_datetime(term.cancel_date.fillna(term.expiration_date))

    print("AGENCIES")
    live = term[(eff <= val) & (end > val)].merge(pol[["policy_id", "agency_id"]], on="policy_id")
    n = live.groupby("agency_id").size().reindex(agency.agency_id).fillna(0)
    year = str(val.year)
    wp = tx[tx.effective_date.str[:4] == year].merge(pol[["policy_id", "agency_id"]], on="policy_id").groupby("agency_id").written_premium.sum()
    wp = wp.reindex(agency.agency_id).fillna(0)
    for ch in ("Independent Agent", "Exclusive Agent", "Direct"):
        k = (agency.channel == ch).to_numpy()
        a, w = n[k].sort_values(ascending=False), wp[k].sort_values(ascending=False)
        top = max(len(a) // 10, 1)
        p(ch, f"{k.sum()} agencies, {int(a.sum()):,} policies in force (mean {a.mean():.0f}, median {a.median():.0f}, largest {a.max():.0f}, "
              f"{int((a < 25).sum())} under 25); {year} written premium ${w.sum() / 1e6:.1f}M (mean ${w.mean() / 1e3:,.0f}K, median "
              f"${w.median() / 1e3:,.0f}K); the largest tenth write {w.head(top).sum() / w.sum():.0%}")
    p("names", "; ".join(agency.agency_name.sample(8, random_state=5)))
    p("commission statements", f"{len(stmt):,}; {(stmt.commission_amount < 0).sum()} negative; unpaid at valuation ${stmt[stmt.payment_date.isna()].commission_amount.sum():,.0f}")

    print("MARKET")
    q = quote.assign(y=quote.quote_date.str[:4], m=quote.quote_date.str[5:7].astype(int), b=quote.bound == "Y")
    by = q.groupby("y").agg(quotes=("b", "size"), bound=("b", "sum"))
    p("quotes, bound and conversion by year", "; ".join(f"{y}: {r.quotes:,} / {r.bound:,} / {r.bound / r.quotes:.1%}" for y, r in by.iterrows()))
    mo = q.groupby("m").size()
    p("quotes by month, relative to the average month", [round(v, 2) for v in (mo / mo.mean())])
    ym = q.groupby(q.quote_date.str[:7]).b.mean()
    p("conversion by month, lowest and highest", f"{ym.idxmin()} {ym.min():.1%}; {ym.idxmax()} {ym.max():.1%}")
    ia = q[q.distribution_channel == "Independent Agent"]
    p("independent-agent quotes, median premium relative to the best competitor, by year",
      (ia.quoted_annual_premium / ia.competitor_annual_premium).groupby(ia.y).median().round(3).to_dict())
    dates = [f"{y}-12-31" for y in range(int(eff.dt.year.min()), val.year + 1)]
    p("policies in force", "; ".join(f"{d[:4]}: {int(((eff <= d) & (end > d)).sum()):,}" for d in dates))
    done = term[end <= val]
    lost = done.cancel_date.notna() | done.nonrenewal_reason.notna()
    yrs = (end[done.index] - eff[done.index]).dt.days / 365.25
    had = done.policy_term_id.isin(clm.policy_term_id)
    ann = lambda m: 1 - np.exp(-lost[m].sum() / yrs[m].sum())
    p("policies lost per year", f"{ann(had):.1%} of terms with a claim, {ann(~had):.1%} without ({ann(had) / ann(~had):.2f} times)")
    p("non-renewals", term.nonrenewal_reason.value_counts().to_dict())
    o = offers[(offers.underwriting_decision == "Renew") & offers.outcome.isin(["Renewed", "Insured Did Not Renew"])]
    af = clm[clm.at_fault == "Y"].policy_term_id
    kept = lambda m: (o[m].outcome == "Renewed").mean()
    with_claim, at_fault = o.expiring_policy_term_id.isin(clm.policy_term_id), o.expiring_policy_term_id.isin(af)
    p("renewal rate of offers", f"no claim in the expiring term {kept(~with_claim):.1%}; a claim {kept(with_claim):.1%}; an at-fault claim {kept(at_fault):.1%}")

    print("PHYSICAL DAMAGE")
    ex = ex.assign(y=ex.coverage_start_date.str[:4].astype(int), age=ex.coverage_start_date.str[:4].astype(int) - ex.model_year)
    for y in (2022, 2024, 2026):
        g = ex[ex.y == y]
        w = g.earned_exposure
        p(f"{y} vehicles", f"mean value ${np.average(g.vehicle_value, weights=w):,.0f} (with collision ${np.average(g.vehicle_value[g.collision_premium > 0], weights=w[g.collision_premium > 0]):,.0f}); "
                           f"collision on {w[g.collision_premium > 0].sum() / w.sum():.1%}, comprehensive on {w[g.comprehensive_premium > 0].sum() / w.sum():.1%}")
    g = ex[ex.y == 2024]
    bands = pd.cut(g.age, [-2, 2, 5, 8, 11, 15, 40], labels=["0-2", "3-5", "6-8", "9-11", "12-15", "16+"])
    p("2024 by vehicle age: mean value, collision take-up", "; ".join(
        f"{k} ${np.average(d.vehicle_value, weights=d.earned_exposure):,.0f} {d.earned_exposure[d.collision_premium > 0].sum() / d.earned_exposure.sum():.0%}"
        for k, d in g.groupby(bands, observed=True)))
    f = feat.merge(clm[["claim_id", "loss_date"]], on="claim_id")
    for cov in ("COLL", "COMP"):
        d = f[(f.coverage_code == cov) & (f.paid_loss > 0) & (f.loss_date >= f"{start.year}-01-01") & (f.loss_date < f"{val.year}-01-01")]
        tl = d[d.total_loss == "Y"]
        p(cov, f"paid claims {len(d):,}; average ${d.paid_loss.mean():,.0f}; total losses {len(tl) / len(d):.1%} averaging ${tl.paid_loss.mean():,.0f}, "
               f"others ${d[d.total_loss != 'Y'].paid_loss.mean():,.0f}; salvage {d.salvage_recovery.sum() / d.paid_loss.sum():.1%} and subrogation "
               f"{d.subrogation_recovery.sum() / d.paid_loss.sum():.1%} of payments")

    print("GENERAL LEDGER")
    p("size", f"{len(acct)} accounts, {gl.journal_number.nunique():,} journals, {len(gl):,} lines; {gl.journal_type.value_counts().to_dict()}")
    name = acct.set_index("account_number").account_name
    bal = (gl.debit - gl.credit).groupby(gl.account_number).sum()
    p("balances at the valuation date (debit positive)", "; ".join(f"{a} {name[a]} {v:,.0f}" for a, v in bal.items()))
    ob = gl[gl.journal_type == "Opening balances"]
    p("opening entry", "; ".join(f"{a} {v:,.0f}" for a, v in (ob.debit - ob.credit).groupby(ob.account_number).sum().items()))
    act = gl[gl.journal_type != "Opening balances"].assign(y=lambda d: d.accounting_period.str[:4])
    net = (act.credit - act.debit).groupby([act.y, act.account_number]).sum().unstack(fill_value=0)
    for y, r in net.iterrows():
        earned = r[4000] + r[4010]
        incurred = -(r[5000] + r[5010] + r[5020] + r[5200])
        lae = -(r[5100] + r[5110] + r[5210])
        p(y, f"written ${r[4000] / 1e6:.1f}M, earned ${earned / 1e6:.1f}M, fees ${r[4200] / 1e6:.2f}M, losses incurred ${incurred / 1e6:.1f}M "
             f"({incurred / earned:.1%}), adjustment expenses ${lae / 1e6:.1f}M ({lae / earned:.1%}), commission ${-r[6100] / 1e6:.1f}M "
             f"({-r[6100] / earned:.1%}), written off ${-r[6300] / 1e6:.2f}M")


if __name__ == "__main__":
    main()
    import sys
    folder = Path(sys.argv[sys.argv.index("--out") + 1]) if "--out" in sys.argv else Path("output")
    operations(folder)
    market_and_ledger(folder)
