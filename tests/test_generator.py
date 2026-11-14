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
from autoins.claims import chargeable_days  # noqa: E402
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
                           dtype={"Change Reason": str})

    def test_same_seed_is_byte_identical(self) -> None:
        files = sorted(p.relative_to(self.root / "a") for p in (self.root / "a").rglob("*") if p.is_file())
        self.assertGreater(len(files), 20)
        for f in files:
            self.assertEqual((self.root / "a" / f).read_bytes(), (self.root / "b" / f).read_bytes(), f"{f} differs")

    def test_different_seed_changes_the_data(self) -> None:
        self.assertNotEqual(self.a["content_hash"], self.c["content_hash"])

    def test_claims_fall_inside_their_policy_term(self) -> None:
        clm, term = self.read("claims_fact"), self.read("policy_term_fact")
        m = clm.merge(term, on="Policy Term ID")
        end = m["Cancel Date"].fillna(m["Policy Expiration Date"])
        self.assertTrue(((m["Loss Date"] >= m["Policy Effective Date"]) & (m["Loss Date"] < end)).all())
        self.assertTrue((clm["Report Date"] >= clm["Loss Date"]).all())
        self.assertTrue((clm["Loss Date"] <= self.a["valuation"]).all())
        self.assertTrue((clm["Loss Date"] >= self.a["start"]).all())

    def test_premium_and_exposure_are_sane(self) -> None:
        risk = self.read("risk_fact")
        self.assertTrue((risk["Total Premium"] > 0).all())
        self.assertTrue((risk["Earned Premium"] <= risk["Total Premium"] + 0.01).all())
        self.assertTrue(risk["Earned Exposure"].between(0, 1.01).all())

    def test_record_level_integrity_checks_pass(self) -> None:
        """The validator's lifecycle, timing, date, premium and payment checks all hold."""
        t = {n: self.read(n) for n in ("risk_fact", "policy_term_fact", "policy_dimension", "insured_vehicle_dimension",
                                       "driver_dimension", "claims_fact", "claim_coverage_fact", "claim_payment_fact",
                                       "driver_incident_fact")}
        start = np.datetime64(self.a["start"])
        r_start = np.maximum(pd.to_datetime(t["risk_fact"]["Coverage Start Date"]).to_numpy(), start)
        r_end = r_start + np.round(t["risk_fact"]["Earned Exposure"].to_numpy() * 365.25).astype("timedelta64[D]")
        rep, out = validate.Report(), io.StringIO()
        with contextlib.redirect_stdout(out):
            validate.integrity_lifecycle(rep, *t.values(), r_start, r_end)
        self.assertEqual(rep.failures, 0, out.getvalue())

    def test_total_losses_end_the_vehicle(self) -> None:
        clm, feat, veh, risk = self.read("claims_fact"), self.read("claim_coverage_fact"), self.read("insured_vehicle_dimension"), self.read("risk_fact")
        tl = feat[(feat["Total Loss"] == "Y") & (feat["Owner Retained Salvage"] == "N")].merge(
            clm[["Claim ID", "Insured Vehicle ID", "Loss Date"]], on="Claim ID")
        self.assertGreater(len(tl), 20)
        last_loss = clm.groupby("Insured Vehicle ID")["Loss Date"].max()
        last_cover = risk.groupby("Insured Vehicle ID")["Coverage End Date"].max()
        for vid, day in tl.groupby("Insured Vehicle ID")["Loss Date"].min().items():
            self.assertEqual(last_loss[vid], day, f"vehicle {vid} has a loss after its total loss")
            self.assertLessEqual(last_cover[vid], str(np.datetime64(day) + np.timedelta64(1, "D")))
        replaced = veh[veh["Replaces Vehicle ID"].isin(tl["Insured Vehicle ID"])]
        self.assertGreater(len(replaced), 0)
        self.assertTrue(veh["Insured Vehicle ID"].is_unique)
        self.assertTrue((replaced["Insured Vehicle ID"] > replaced["Replaces Vehicle ID"]).all())   # a new ID, added later
        old = veh.set_index("Insured Vehicle ID").loc[replaced["Replaces Vehicle ID"]]
        self.assertTrue((old["Removed Date"].to_numpy() <= replaced["Added Date"].to_numpy()).all())

    def test_opening_book_is_in_force_on_the_start_date(self) -> None:
        pol, term, risk = self.read("policy_dimension"), self.read("policy_term_fact"), self.read("risk_fact")
        start = self.a["start"]
        old = pol[pol["Original Inception Date"] < start]
        self.assertGreater(len(old), 500)
        first = term.sort_values("Policy Effective Date").groupby("Policy Number").head(1).set_index("Policy Number")
        f = first.reindex(old["Policy Number"])
        self.assertTrue(((f["Policy Effective Date"] <= start) & (f["Policy Expiration Date"] > start)).all())
        opening = term[term["Policy Effective Date"] < start]
        self.assertTrue((opening["Earned Before Extract"] > 0).all())
        r = risk[risk["Policy Term ID"].isin(opening["Policy Term ID"])]
        days = (pd.to_datetime(r["Coverage End Date"]).clip(upper=pd.Timestamp(self.a["valuation"]) + pd.Timedelta(days=1))
                - pd.to_datetime(r["Coverage Start Date"]).clip(lower=pd.Timestamp(start))).dt.days / 365.25
        self.assertTrue(np.allclose(r["Earned Exposure"], days, atol=1e-3))      # only the part after the start is earned
        # new business is exactly the first term of a policy
        self.assertTrue(((term["Business Type"] == "New") == (term["Term Number"] == 1)).all())
        self.assertTrue((pol["Original Inception Date"] <= pol["Policy Effective Date"]).all())

    def test_rating_uses_only_information_known_on_the_rating_date(self) -> None:
        term, inc = self.read("policy_term_fact"), self.read("driver_incident_fact")
        self.assertTrue((term["Rating Date"] <= term["Policy Effective Date"]).all())
        own = inc[inc.Source == "Company Claim"]
        self.assertGreater(len(own), 20)
        self.assertTrue((own["Known Date"] >= own["Incident Date"]).all())
        self.assertGreater((own["Known Date"] > own["Incident Date"]).mean(), 0.95)

    def test_household_changes_are_endorsements(self) -> None:
        risk, drv, veh = self.read("risk_fact"), self.read("driver_dimension"), self.read("insured_vehicle_dimension")
        mid = risk[risk["Endorsement Number"] > 0]
        self.assertGreater(len(mid), 100)
        reasons = set("; ".join(mid["Change Reason"].dropna()).split("; "))
        self.assertTrue({"Address Change", "Vehicle Replaced", "Driver Removed"} <= reasons, reasons)
        self.assertTrue((mid["Rating Date"] == mid["Coverage Start Date"]).all())       # re-rated on the day of the change
        # a vehicle's rows within a term are consecutive: each starts where the previous one ended
        r = risk.sort_values(["Insured Vehicle ID", "Coverage Start Date"])
        prev = r.groupby(["Insured Vehicle ID", "Policy Term ID"])["Coverage End Date"].shift()
        self.assertTrue((prev.isna() | (prev == r["Coverage Start Date"])).all())
        left = drv[drv["Removed Date"].notna()]
        self.assertGreater(len(left), 10)
        self.assertTrue(set(left["Removal Reason"]) <= {"Moved Out", "Divorce", "Deceased"})
        self.assertTrue({"Sold", "Destroyed or Stolen"} <= set(veh["Removal Reason"].dropna()))
        moved = risk.groupby("Policy Number")["Location ID"].nunique()
        self.assertGreater((moved > 1).sum(), 10)

    def test_owner_retained_salvage_follows_illinois_rules(self) -> None:
        feat, clm, veh = self.read("claim_coverage_fact"), self.read("claims_fact"), self.read("insured_vehicle_dimension")
        kept = feat[feat["Owner Retained Salvage"] == "Y"].merge(clm, on="Claim ID").merge(
            veh[["Insured Vehicle ID", "Vehicle Model Year", "Removal Reason"]], on="Insured Vehicle ID")
        age = pd.to_datetime(kept["Loss Date"]).dt.year - kept["Vehicle Model Year"]
        self.assertTrue(((age >= 9) | kept["Cause of Loss"].isin(["WEATHER", "HAIL_CAT"])).all())
        self.assertTrue((kept["Salvage Recovery"] == 0).all())
        self.assertFalse((kept["Removal Reason"] == "Total Loss").any())

    def test_premium_ledger_reconciles(self) -> None:
        ledger, term = self.read("policy_transaction_fact"), self.read("policy_term_fact")
        self.assertTrue({"New Business", "Renewal", "Endorsement", "Cancellation"} <= set(ledger["Transaction Type"]))
        self.assertTrue((ledger["Processed Date"] <= self.a["valuation"]).all())
        done = term[term["Policy Expiration Date"] < "2026-04-01"].set_index("Policy Term ID")
        w = ledger[ledger["Transaction Type"] != "Cancellation"].groupby("Policy Term ID")["Written Premium"].sum()
        gap = (done["Written Premium"] + done["Endorsement Premium"] - w.reindex(done.index).fillna(0)).abs()
        self.assertLess(gap.max(), 0.05 + 0.01 * done["Vehicle Count"].max())

    def test_month_end_anniversaries(self) -> None:
        term = self.read("policy_term_fact")
        day = pd.to_datetime(term["Policy Effective Date"]).dt.day
        self.assertTrue((day >= 29).any() and (day == 31).any())

    def test_payments_are_varied_and_reconcile(self) -> None:
        feat, pay = self.read("claim_coverage_fact"), self.read("claim_payment_fact")
        loss = pay[pay["Payment Type"] == "Loss"]
        n = loss.groupby("Claim Feature ID").size()
        self.assertGreater(n.max(), 2)
        paid = loss.groupby("Claim Feature ID").Amount.sum().reindex(feat["Claim Feature ID"]).fillna(0)
        self.assertTrue(np.allclose(paid.to_numpy(), feat["Paid Loss"].to_numpy(), atol=0.005))
        self.assertTrue(set(loss["Transaction Type"]) >= {"Partial Payment", "Final Payment"})


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
