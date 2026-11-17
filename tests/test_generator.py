"""Run with:  python -m unittest discover tests"""
from __future__ import annotations

import contextlib
import io
import sys
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import validate  # noqa: E402
from autoins import config as C  # noqa: E402
from autoins import names, truth  # noqa: E402
from autoins.claims import SUIT_LIMIT_DAYS, chargeable_days, litigation_timeline  # noqa: E402
from autoins.pipeline import generate  # noqa: E402
from autoins.refdata import Calendar  # noqa: E402


class GeneratorTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.tmp = tempfile.TemporaryDirectory()
        root = Path(cls.tmp.name)
        base = replace(C.Config(), n_policies=1500)
        cls.a = generate(replace(base, seed=11, out_dir=root / "a"))
        cls.b = generate(replace(base, seed=11, out_dir=root / "b"))
        cls.c = generate(replace(base, seed=12, out_dir=root / "c"))
        cls.root = root

    @classmethod
    def tearDownClass(cls) -> None:
        cls.tmp.cleanup()

    def read(self, name: str) -> pd.DataFrame:
        return pd.read_csv(self.root / "a" / f"{name}.csv", keep_default_na=False, na_values=[""], low_memory=False,
                           dtype={"change_reason": str})

    def test_same_seed_is_byte_identical(self) -> None:
        files = sorted(p.relative_to(self.root / "a") for p in (self.root / "a").rglob("*") if p.is_file())
        self.assertGreater(len(files), 20)
        for f in files:
            self.assertEqual((self.root / "a" / f).read_bytes(), (self.root / "b" / f).read_bytes(), f"{f} differs")

    def test_different_seed_changes_the_data(self) -> None:
        self.assertNotEqual(self.a["content_hash"], self.c["content_hash"])

    def test_claims_fall_inside_their_policy_term(self) -> None:
        clm, term = self.read("claim"), self.read("policy_term")
        m = clm.merge(term, on="policy_term_id")
        end = m["cancel_date"].fillna(m["expiration_date"])
        self.assertTrue(((m["loss_date"] >= m["effective_date"]) & (m["loss_date"] < end)).all())
        self.assertTrue((clm["report_date"] >= clm["loss_date"]).all())
        self.assertTrue((clm["loss_date"] <= self.a["valuation"]).all())
        self.assertTrue((clm["loss_date"] >= self.a["start"]).all())

    def test_premium_and_exposure_are_sane(self) -> None:
        risk = self.read("exposure")
        self.assertTrue((risk["total_premium"] > 0).all())
        self.assertTrue((risk["earned_premium"] <= risk["total_premium"] + 0.01).all())
        self.assertTrue(risk["earned_exposure"].between(0, 1.01).all())

    def test_record_level_integrity_checks_pass(self) -> None:
        """The validator's lifecycle, timing, date, premium and payment checks all hold."""
        t = {n: self.read(n) for n in ("exposure", "policy_term", "policy", "insured_vehicle",
                                       "driver", "claim", "claim_feature", "claim_payment",
                                       "driver_incident")}
        start = np.datetime64(self.a["start"])
        r_start = np.maximum(pd.to_datetime(t["exposure"]["coverage_start_date"]).to_numpy(), start)
        r_end = r_start + np.round(t["exposure"]["earned_exposure"].to_numpy() * 365.25).astype("timedelta64[D]")
        rep, out = validate.Report(), io.StringIO()
        with contextlib.redirect_stdout(out):
            validate.integrity_lifecycle(rep, *t.values(), r_start, r_end, self.a["valuation"])
            validate.integrity_claims_and_quotes(rep, t["policy_term"], t["insured_vehicle"], t["claim"],
                                                 t["claim_feature"], self.read("claim_reserve_transaction"), self.read("quote"))
            validate.integrity_limits(rep, t["claim_feature"].merge(
                t["claim"][["claim_id", "exposure_id", "cause_of_loss"]], on="claim_id").merge(t["exposure"], on="exposure_id"))
        self.assertEqual(rep.failures, 0, out.getvalue())

    def test_vehicle_catalogue_and_telematics_checks_pass(self) -> None:
        """Every vehicle points to a make, model and model year; telematics discounts follow the published rules."""
        risk, term, veh, clm = self.read("exposure"), self.read("policy_term"), self.read("insured_vehicle"), self.read("claim")
        vmy = self.read("vehicle_model_year")
        rep, out = validate.Report(), io.StringIO()
        with contextlib.redirect_stdout(out):
            validate.integrity_vehicles(rep, vmy, veh, risk, clm)
            validate.integrity_telematics(rep, self.read("telematics_enrollment"), self.read("telematics_score"), risk, term,
                                          pd.Timestamp(self.a["valuation"]))
        self.assertEqual(rep.failures, 0, out.getvalue())
        self.assertGreater(len(vmy), 5000)                       # the full catalogue, not just the models insured
        self.assertGreater((risk["telematics_enrolled"] == "Y").mean(), 0.02)

    def test_names_follow_the_household_and_race_is_only_in_the_answer_key(self) -> None:
        drv, truth_ = self.read("driver"), pd.read_csv(self.root / "a" / "answer_key" / "driver_truth.csv")
        published = [pd.read_csv(p, nrows=0).columns for p in (self.root / "a").glob("*.csv")]
        self.assertFalse(any("race" in c for cols in published for c in cols))
        self.assertEqual(set(truth_["race_ethnicity"]) <= set(names.GROUP_LABELS), True)
        adults = set(zip(drv.loc[drv["driver_role"] != "Child", "policy_id"], drv.loc[drv["driver_role"] != "Child", "last_name"]))
        kids = drv[drv["driver_role"] == "Child"]
        self.assertTrue(all(k in adults for k in zip(kids["policy_id"], kids["last_name"])))     # a child shares an adult's surname

    def test_policy_counts_are_as_at_the_latest_status(self) -> None:
        """Number of Vehicles is the cars on the policy now (or on its last day of cover), not at the term start."""
        pol, veh, term = self.read("policy"), self.read("insured_vehicle"), self.read("policy_term")
        live = pol[pol["policy_status"] == "In Force"].set_index("policy_id")
        on_now = veh[veh["removed_date"].isna()].groupby("policy_id").size().reindex(live.index).fillna(0)
        self.assertTrue((live["number_of_vehicles"] == on_now).all())
        self.assertFalse((veh["removed_date"].dropna() > self.a["valuation"]).any())
        # the latest term's opening count is kept under its own name, and differs when a car came or went mid-term
        opening = term.sort_values("effective_date").groupby("policy_id")["vehicles_at_term_start"].last().reindex(live.index)
        self.assertGreater((opening != live["number_of_vehicles"]).sum(), 10)

    def test_same_day_events_have_a_defined_order(self) -> None:
        """A company claim reaches the driving record the day after the payment that makes it chargeable, so
        a loss or payment on a rating date is never part of that rating."""
        inc, clm = self.read("driver_incident"), self.read("claim")
        own = inc[inc.source == "Company Claim"].merge(clm[["claim_id", "loss_date"]], on="claim_id")
        self.assertTrue((own["known_date"] > own["loss_date"]).all())
        pay = self.read("claim_payment")
        first = pay[pay["payment_type"] == "Loss"].groupby("claim_id")["payment_date"].min()
        self.assertTrue((own["known_date"] > own["claim_id"].map(first)).all())

    def test_uninsured_and_underinsured_motorist_are_told_apart(self) -> None:
        feat = self.read("claim_feature")
        um = feat[feat["coverage_code"] == "UM"]
        self.assertTrue(set(um["um_uim_type"]) <= {"Uninsured", "Underinsured"})
        self.assertTrue(feat.loc[feat["coverage_code"] != "UM", "um_uim_type"].isna().all())
        self.assertTrue((feat["other_insurer_payment"].notna() == (feat["um_uim_type"] == "Underinsured")).all())

    def test_total_losses_end_the_vehicle(self) -> None:
        clm, feat, veh, risk = self.read("claim"), self.read("claim_feature"), self.read("insured_vehicle"), self.read("exposure")
        tl = feat[(feat["total_loss"] == "Y") & (feat["owner_retained_salvage"] == "N")].merge(
            clm[["claim_id", "insured_vehicle_id", "loss_date"]], on="claim_id")
        self.assertGreater(len(tl), 20)
        last_loss = clm.groupby("insured_vehicle_id")["loss_date"].max()
        last_cover = risk.groupby("insured_vehicle_id")["coverage_end_date"].max()
        for vid, day in tl.groupby("insured_vehicle_id")["loss_date"].min().items():
            self.assertEqual(last_loss[vid], day, f"vehicle {vid} has a loss after its total loss")
            self.assertLessEqual(last_cover[vid], str(np.datetime64(day) + np.timedelta64(1, "D")))
        replaced = veh[veh["replaces_insured_vehicle_id"].isin(tl["insured_vehicle_id"])]
        self.assertGreater(len(replaced), 0)
        self.assertTrue(veh["insured_vehicle_id"].is_unique)
        self.assertTrue((replaced["insured_vehicle_id"] > replaced["replaces_insured_vehicle_id"]).all())   # a new ID, added later
        old = veh.set_index("insured_vehicle_id").loc[replaced["replaces_insured_vehicle_id"]]
        self.assertTrue((old["removed_date"].to_numpy() <= replaced["added_date"].to_numpy()).all())

    def test_opening_book_is_in_force_on_the_start_date(self) -> None:
        pol, term, risk = self.read("policy"), self.read("policy_term"), self.read("exposure")
        start = self.a["start"]
        old = pol[pol["original_inception_date"] < start]
        self.assertGreater(len(old), 500)
        first = term.sort_values("effective_date").groupby("policy_id").head(1).set_index("policy_id")
        f = first.reindex(old["policy_id"])
        self.assertTrue(((f["effective_date"] <= start) & (f["expiration_date"] > start)).all())
        opening = term[term["effective_date"] < start]
        self.assertTrue((opening["earned_premium_before_extract"] > 0).all())
        r = risk[risk["policy_term_id"].isin(opening["policy_term_id"])]
        days = (pd.to_datetime(r["coverage_end_date"]).clip(upper=pd.Timestamp(self.a["valuation"]) + pd.Timedelta(days=1))
                - pd.to_datetime(r["coverage_start_date"]).clip(lower=pd.Timestamp(start))).dt.days / 365.25
        self.assertTrue(np.allclose(r["earned_exposure"], days, atol=1e-3))      # only the part after the start is earned
        # new business is exactly the first term of a policy
        self.assertTrue(((term["business_type"] == "New") == (term["term_number"] == 1)).all())
        self.assertTrue((pol["original_inception_date"] <= pol["first_effective_date"]).all())

    def test_rating_uses_only_information_known_on_the_rating_date(self) -> None:
        term, inc = self.read("policy_term"), self.read("driver_incident")
        self.assertTrue((term["rating_date"] <= term["effective_date"]).all())
        own = inc[inc.source == "Company Claim"]
        self.assertGreater(len(own), 20)
        self.assertTrue((own["known_date"] >= own["incident_date"]).all())
        self.assertGreater((own["known_date"] > own["incident_date"]).mean(), 0.95)

    def test_household_changes_are_endorsements(self) -> None:
        risk, drv, veh = self.read("exposure"), self.read("driver"), self.read("insured_vehicle")
        mid = risk[risk["endorsement_number"] > 0]
        self.assertGreater(len(mid), 100)
        reasons = set("; ".join(mid["change_reason"].dropna()).split("; "))
        self.assertTrue({"Address Change", "Vehicle Replaced", "Driver Removed"} <= reasons, reasons)
        self.assertTrue((mid["rating_date"] == mid["coverage_start_date"]).all())       # re-rated on the day of the change
        # a vehicle's rows within a term are consecutive: each starts where the previous one ended
        r = risk.sort_values(["insured_vehicle_id", "coverage_start_date"])
        prev = r.groupby(["insured_vehicle_id", "policy_term_id"])["coverage_end_date"].shift()
        self.assertTrue((prev.isna() | (prev == r["coverage_start_date"])).all())
        left = drv[drv["removed_date"].notna()]
        self.assertGreater(len(left), 10)
        self.assertTrue(set(left["removal_reason"]) <= {"Moved Out", "Divorce", "Deceased"})
        self.assertTrue({"Sold", "Destroyed or Stolen"} <= set(veh["removal_reason"].dropna()))
        moved = risk.groupby("policy_id")["location_id"].nunique()
        self.assertGreater((moved > 1).sum(), 10)

    def test_owner_retained_salvage_follows_illinois_rules(self) -> None:
        feat, clm, veh = self.read("claim_feature"), self.read("claim"), self.read("insured_vehicle")
        kept = feat[feat["owner_retained_salvage"] == "Y"].merge(clm, on="claim_id").merge(
            veh[["insured_vehicle_id", "removal_reason"]], on="insured_vehicle_id").merge(
            self.read("vehicle_model_year")[["vehicle_model_year_id", "model_year"]], on="vehicle_model_year_id")
        age = pd.to_datetime(kept["loss_date"]).dt.year - kept["model_year"]
        self.assertTrue(((age >= 9) | kept["cause_of_loss"].isin(["WEATHER", "HAIL_CAT"])).all())
        self.assertTrue((kept["salvage_recovery"] == 0).all())
        self.assertFalse((kept["removal_reason"] == "Total Loss").any())

    def test_premium_ledger_reconciles(self) -> None:
        ledger, term = self.read("premium_transaction"), self.read("policy_term")
        self.assertTrue({"New Business", "Renewal", "Endorsement", "Cancellation"} <= set(ledger["transaction_type"]))
        self.assertTrue((ledger["processed_date"] <= self.a["valuation"]).all())
        done = term[term["expiration_date"] < "2026-04-01"].set_index("policy_term_id")
        w = ledger[ledger["transaction_type"] != "Cancellation"].groupby("policy_term_id")["written_premium"].sum()
        gap = (done["written_premium"] + done["endorsement_premium"] - w.reindex(done.index).fillna(0)).abs()
        self.assertLess(gap.max(), 0.05 + 0.01 * done["vehicles_at_term_start"].max())

    def test_reserve_history_rebuilds_past_incurred(self) -> None:
        feat, res, pay = self.read("claim_feature"), self.read("claim_reserve_transaction"), self.read("claim_payment")
        self.assertTrue({"Initial Reserve", "Reserve Review", "Payment", "Close"} <= set(res["transaction_type"]))
        # an earlier evaluation: open features then carried a reserve that later closed to zero
        on = "2024-06-30"
        os_ = res[(res["reserve_type"] == "Loss") & (res["transaction_date"] <= on)].groupby("claim_feature_id")["outstanding_reserve"].last()
        self.assertGreater(os_.sum(), 0)
        later_closed = feat.set_index("claim_feature_id").reindex(os_[os_ > 0].index)["feature_status"] == "Closed"
        self.assertGreater(later_closed.mean(), 0.5)
        expense = pay[pay["payment_type"] == "Expense"]
        self.assertTrue(set(expense["transaction_type"]) == {"DCC Expense", "A&O Expense"})

    def test_quote_funnel(self) -> None:
        q = self.read("quote")
        self.assertTrue(0.10 < (q["bound"] == "Y").mean() < 0.35)
        ia = q[q["competitor_annual_premium"].notna()]
        cheap = ia["quoted_annual_premium"] < ia["competitor_annual_premium"]
        self.assertGreater((ia.loc[cheap, "bound"] == "Y").mean(), (ia.loc[~cheap, "bound"] == "Y").mean())
        self.assertTrue(q.loc[q["bound"] == "N", "policy_id"].isna().all())

    def test_optional_coverages(self) -> None:
        feat, clm, risk = self.read("claim_feature"), self.read("claim"), self.read("exposure")
        f = feat.merge(clm[["claim_id", "exposure_id"]], on="claim_id").merge(risk, on="exposure_id")
        for code, col, cap in (("RENT", "rental_premium", 1_500), ("TOW", "towing_premium", 100)):
            g = f[f["coverage_code"] == code]
            self.assertGreater(len(g), 5, code)
            self.assertTrue((g[col] > 0).all() and (g["paid_loss"] <= cap + 0.01).all(), code)

    def test_month_end_anniversaries(self) -> None:
        term = self.read("policy_term")
        day = pd.to_datetime(term["effective_date"]).dt.day
        self.assertTrue((day >= 29).any() and (day == 31).any())

    def test_payments_are_varied_and_reconcile(self) -> None:
        feat, pay = self.read("claim_feature"), self.read("claim_payment")
        loss = pay[pay["payment_type"] == "Loss"]
        n = loss.groupby("claim_feature_id").size()
        self.assertGreater(n.max(), 2)
        paid = loss.groupby("claim_feature_id").amount.sum().reindex(feat["claim_feature_id"]).fillna(0)
        self.assertTrue(np.allclose(paid.to_numpy(), feat["paid_loss"].to_numpy(), atol=0.005))
        self.assertTrue(set(loss["transaction_type"]) >= {"Partial Payment", "Final Payment"})


class CalendarTest(unittest.TestCase):
    def setUp(self) -> None:
        self.cal = Calendar(start=np.datetime64("2022-01-01"), valuation_day=2000, horizon=2001)

    def date(self, months, dom) -> str:
        return str(self.cal.date(self.cal.day_of(np.array([months]), np.array([dom])))[0])

    def test_month_end_dates_clamp_and_return(self) -> None:
        self.assertEqual(self.date(0, 31), "2022-01-31")
        self.assertEqual(self.date(1, 31), "2022-02-28")
        self.assertEqual(self.date(2, 31), "2022-03-31")      # back to the 31st: no drift
        self.assertEqual(self.date(3, 31), "2022-04-30")
        self.assertEqual(self.date(25, 29), "2024-02-29")     # leap year
        self.assertEqual(self.date(37, 29), "2025-02-28")
        self.assertEqual(self.date(-4, 30), "2021-09-30")     # before the start

    def test_six_month_anniversaries_never_drift(self) -> None:
        for dom in (28, 29, 30, 31):
            days = [int(pd.Timestamp(self.date(m, dom)).day) for m in range(-6, 60, 6)]
            self.assertTrue(all(d == dom or d == pd.Timestamp(self.date(m, 1)).days_in_month
                                for d, m in zip(days, range(-6, 60, 6))), (dom, days))


class LitigationTimelineTest(unittest.TestCase):
    def test_a_short_claim_runs_longer_instead_of_suing_before_the_attorney(self) -> None:
        """Seed 7 produced a bodily injury feature opened on its loss date and drawn to close 171 days later,
        with an attorney retained on day 156. Fitting the suit 30 days before that close put it on day 141,
        before the attorney. The close now moves instead."""
        day, opened, close = np.array([0]), np.array([0]), np.array([171])
        attorney, suit, close = litigation_timeline(day, opened, close, np.array([156]), np.array([60]), np.array([30]))
        self.assertEqual((attorney[0], suit[0], close[0]), (156, 216, 246))

    def test_order_holds_for_any_draw(self) -> None:
        r = np.random.default_rng(7)
        n = 200_000
        day = r.integers(0, 1500, n)
        opened = day + np.where(r.random(n) < 0.8, 0, r.integers(0, 701, n))        # claims presented up to 700 days on
        close = opened + r.integers(1, 900, n)                                       # including far too short to litigate
        attorney, suit, closed = litigation_timeline(day, opened, close, r.integers(1, 181, n), r.integers(60, 421, n),
                                                     30 + r.integers(0, 400, n))
        self.assertTrue((attorney >= day).all() and (suit >= attorney).all() and (suit >= opened).all())
        self.assertTrue((suit <= day + SUIT_LIMIT_DAYS).all())
        self.assertTrue((closed >= suit + 30).all() and (closed >= close).all())


class LimitTest(unittest.TestCase):
    def test_per_accident_limit_is_shared_to_the_cent(self) -> None:
        paid = np.array([30_000.00, 30_000.00, 0.0, 10_000.01, 5.0, 5.0, 100.0, 40.0])
        accident = np.array([0, 0, 0, 0, 1, 1, 2, 3])
        out = truth.cap_per_accident(paid, accident, 4, np.array([50_000.0, 20.0, 0.0, 100.0]))
        cents = np.round(out * 100).astype(int)
        self.assertEqual(np.bincount(accident, cents).tolist(), [5_000_000, 1_000, 0, 4_000])   # exactly the limit, or less
        self.assertEqual(cents[2], 0)                               # a claimant paid nothing stays at nothing
        self.assertTrue((out <= paid).all())
        self.assertEqual(out[4:6].tolist(), [5.0, 5.0])             # under the limit: untouched

    def test_random_accidents_never_exceed_their_limit(self) -> None:
        r = np.random.default_rng(3)
        k = r.integers(1, 5, 20_000)
        accident = np.repeat(np.arange(len(k)), k)
        paid = np.round(np.minimum(20_000 * np.exp(1.4 * r.standard_normal(len(accident))), 25_000), 2) * (r.random(len(accident)) > 0.14)
        out = truth.cap_per_accident(paid, accident, len(k), np.full(len(k), 50_000.0))
        total = np.bincount(accident, np.round(out * 100).astype(int))
        before = np.bincount(accident, np.round(paid * 100).astype(int))
        self.assertTrue((total <= 5_000_000).all())
        self.assertTrue((total[before > 5_000_000] == 5_000_000).all())
        self.assertTrue((total[before <= 5_000_000] == before[before <= 5_000_000]).all())

    def test_underinsured_benefit_is_reduced_by_the_other_insurer(self) -> None:
        benefit, other = truth.underinsured(np.array([80_000.0, 20_000.0, 300_000.0]), 100_000, np.array([25_000, 25_000, 250_000]))
        self.assertEqual(benefit.tolist(), [55_000.0, 0.0, 0.0])
        self.assertEqual(other.tolist(), [25_000.0, 20_000.0, 250_000.0])


class ChargeabilityTest(unittest.TestCase):
    def test_a_later_settlement_cannot_change_an_earlier_status(self) -> None:
        fid_occ = pd.DataFrame({"fid": [1, 2], "occ": [10, 10]})
        pays = pd.DataFrame({"fid": [1, 2, 1], "day": [5, 20, 40], "amount": [400.0, 700.0, 50.0], "seq": [0, 1, 2]})
        self.assertEqual(chargeable_days(pays, fid_occ)[10], 20)
        bigger = pays.assign(amount=[400.0, 700.0, 90_000.0])          # change only the payment after day 20
        self.assertEqual(chargeable_days(bigger, fid_occ)[10], 20)
        small = pays.assign(amount=[400.0, 100.0, 50.0])               # never reaches the threshold
        self.assertNotIn(10, chargeable_days(small, fid_occ).index)


if __name__ == "__main__":
    unittest.main()
