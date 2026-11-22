"""Run with:  python -m unittest discover tests"""
from __future__ import annotations

import contextlib
import importlib.util
import io
import json
import shutil
import sqlite3
import sys
import tempfile
import unittest
import zipfile
from dataclasses import replace
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import release_formats  # noqa: E402
import validate  # noqa: E402
from autoins import config as C  # noqa: E402
from autoins import claims, identifiers, ledger, market, names, population, rating, refdata, schema, simulate, telematics, truth  # noqa: E402
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
        """A table of run "a", with the totals an analyst works out from its records (validate.rebuild)."""
        if not hasattr(type(self), "tables"):
            type(self).tables = validate.rebuild(validate.load(self.root / "a"), self.a["start"], self.a["valuation"])
        return type(self).tables[name].copy()

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

    def test_the_extract_opens_with_the_claims_then_open(self) -> None:
        """Claims from accidents before the start come from the in-force book's current term, and each was still
        open on the start date or had something happen on it later; a claim settled and closed before then is not
        in the extract."""
        clm, term, pay = self.read("claim"), self.read("policy_term"), self.read("claim_payment")
        early = clm[clm["loss_date"] < self.a["start"]].merge(term[["policy_term_id", "effective_date", "expiration_date"]],
                                                                 on="policy_term_id")
        self.assertGreater(len(early), 0)
        self.assertTrue(((early["effective_date"] < self.a["start"]) & (early["expiration_date"] > self.a["start"])).all())
        later_pay = pay[pay["payment_date"] >= self.a["start"]].groupby("claim_id").size()
        active = (early["report_date"] >= self.a["start"]) | early["close_date"].isna() | (early["close_date"] >= self.a["start"]) \
            | early["claim_id"].isin(later_pay.index)
        self.assertTrue(active.all())

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
            validate.integrity_links(rep, t["exposure"], t["policy_term"], t["insured_vehicle"], t["driver"], t["claim"],
                                     t["claim_feature"], t["claim_payment"], self.read("claim_reserve_transaction"))
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
        apart = kids[[k not in adults for k in zip(kids["policy_id"], kids["last_name"])]]
        # a child shares an adult's surname, unless their mother has since married and taken her husband's
        ni = drv[drv["driver_role"] == "Named Insured"].drop_duplicates("policy_id").set_index("policy_id")
        husband = drv[(drv["driver_role"] == "Spouse") & (drv["gender"] == "M")].drop_duplicates("policy_id", keep="last").set_index("policy_id")
        p_ = apart["policy_id"]
        self.assertTrue(((ni["gender"].reindex(p_) == "F").to_numpy() & (husband["added_date"].reindex(p_) >= self.a["start"]).to_numpy()
                         & (ni["last_name"].reindex(p_) == husband["last_name"].reindex(p_)).to_numpy()).all())

    def test_checks_catch_a_corrupted_record(self) -> None:
        """Negative controls: each record-level check passes on the data and fails when one record is made wrong
        (a check that cannot fail proves nothing)."""
        def failed(fn, *args) -> list:
            rep, out = validate.Report(), io.StringIO()
            with contextlib.redirect_stdout(out):
                fn(rep, *args)
            return [line.split("] ", 1)[1].split(":")[0] for line in out.getvalue().splitlines() if "[FAIL]" in line]

        names = ("exposure", "policy_term", "insured_vehicle", "driver", "claim", "claim_feature", "claim_payment",
                 "claim_reserve_transaction", "billing_invoice", "billing_receipt", "premium_transaction", "policy")
        t = {n: self.read(n) for n in names}
        links = lambda **x: failed(validate.integrity_links, *[x.get(n, t[n]) for n in names[:8]])
        payees = lambda **x: failed(validate.integrity_payees, *[x.get(n, t[n]) for n in
                                                                  ("claim_payment", "claim", "claim_feature", "insured_vehicle", "driver")])
        billing = lambda **x: failed(validate.integrity_billing, *[x.get(n, t[n]) for n in
                                                                   ("billing_invoice", "billing_receipt", "policy_term",
                                                                    "premium_transaction", "policy")], self.a["valuation"])
        self.assertEqual(links() + payees() + billing(), [])
        clm, pay, feat, veh, drv = t["claim"], t["claim_payment"], t["claim_feature"], t["insured_vehicle"], t["driver"]

        # a claim pointing at another (existing) policy; a payment filed under another claim than its feature's
        bad = clm.copy()
        bad.loc[0, "policy_id"] = bad.loc[bad["policy_id"] != bad.loc[0, "policy_id"], "policy_id"].iloc[0]
        self.assertEqual(links(claim=bad), ["claim policy, term, vehicle and model year match the risk row"])
        bad = pay.copy()
        bad.loc[0, "claim_id"] = bad.loc[bad["claim_id"] != bad.loc[0, "claim_id"], "claim_id"].iloc[0]
        self.assertEqual(links(claim_payment=bad), ["each payment's and reserve change's claim is its feature's claim"])

        # a lender paid on a car owned outright; a financed car's total loss paid without its lender
        lien = pay[pay["payee_type"] == "Lienholder"].merge(clm[["claim_id", "insured_vehicle_id"]], on="claim_id")
        lien = lien.merge(veh[["insured_vehicle_id", "ownership"]], on="insured_vehicle_id")
        self.assertGreater(len(lien), 0)
        car = lien.loc[lien["ownership"] != "Owned", "insured_vehicle_id"].iloc[0]
        lender_check = ("a lienholder or lessor is paid only on a total loss of a financed or leased car, never more than the "
                        "settlement and one lender per car; every closed, paid total loss of a financed or leased car pays one")
        self.assertEqual(payees(insured_vehicle=veh.assign(ownership=veh["ownership"].where(veh["insured_vehicle_id"] != car, "Owned"))),
                         [lender_check])
        self.assertEqual(payees(claim_payment=pay[pay["payment_id"] != lien["payment_id"].iloc[0]]), [lender_check])

        # a joint payment to a claimant and attorney dated before the attorney was retained
        joint = pay[pay["payee_type"] == "Claimant and Attorney"].iloc[0]
        late = (pd.Timestamp(joint["payment_date"]) + pd.Timedelta(days=1)).strftime("%Y-%m-%d")
        bad = feat.copy()
        bad.loc[bad["claim_feature_id"] == joint["claim_feature_id"], "attorney_date"] = late
        self.assertEqual(payees(claim_feature=bad),
                         ["a claimant is paid jointly with an attorney only on or after the day the attorney was retained, and always after it"])

        # a claim's driver who joined the policy after the loss; a payment to the insured naming someone who joined later
        who_check = ("each claim's driver was on the policy on the loss date, and each payment to the insured (an uninsured "
                     "motorist claimant's included) names someone on the policy on the loss or payment date")
        c0 = clm.iloc[0]
        later = drv[drv["added_date"] > c0["loss_date"]].iloc[0]
        bad = clm.copy()
        bad.loc[0, ["policy_id", "involved_driver_id"]] = [later["policy_id"], later["driver_id"]]
        self.assertIn(who_check, payees(claim=bad))
        p0 = pay[pay["payee_type"] == "Insured"].iloc[0]
        pol0 = clm.set_index("claim_id").loc[p0["claim_id"], "policy_id"]
        # (a driver who joins the policy after the payment, under a first name no one else on it has)
        bad_drv = pd.concat([drv, drv.iloc[[0]].assign(driver_id=drv["driver_id"].max() + 1, policy_id=pol0, first_name="Zebulon",
                                                     last_name="Later", added_date="2099-01-01", removed_date=None)])
        bad = pay.copy()
        bad.loc[bad["payment_id"] == p0["payment_id"], "payee_name"] = "Zebulon Later"
        self.assertEqual(payees(claim_payment=bad, driver=bad_drv), [who_check])

        # a cancellation for non-payment with no unpaid installment behind it
        inv, rec = t["billing_invoice"], t["billing_receipt"]
        np_term = t["policy_term"].loc[t["policy_term"]["cancel_reason"] == "Non-Payment", "policy_term_id"].iloc[0]
        missed = (inv["policy_term_id"] == np_term) & (inv["invoice_status"] == "Canceled") & (inv["invoice_type"] == "Installment")
        self.assertIn("every cancellation for non-payment follows an unpaid installment, billed and due three to four weeks before it",
                      billing(billing_invoice=inv[~missed]))
        # a check banked on a Saturday
        bad = rec.copy()
        i = bad.index[(bad["payment_method"] == "Check") & (bad["receipt_type"] == "Payment")][0]
        d = pd.Timestamp(bad.loc[i, "receipt_date"])
        bad.loc[i, "receipt_date"] = (d + pd.Timedelta(days=(5 - d.dayofweek) % 7)).strftime("%Y-%m-%d")
        self.assertIn("check and bank-draft receipts, returned drafts and refunds are dated on business days", billing(billing_receipt=bad))

    def test_keys_are_system_counters_not_row_numbers(self) -> None:
        """Integer keys continue the company's counters: they start well above 1, have gaps for the rest of the
        company's records, and rise with the day each record was created."""
        for table, pk, created in (("policy_term", "policy_term_id", "offer_date"), ("exposure", "exposure_id", "rating_date"),
                                   ("claim", "claim_id", "report_date"), ("claim_payment", "payment_id", "payment_date"),
                                   ("billing_invoice", "invoice_id", "issue_date"), ("quote", "quote_id", "quote_date")):
            t = self.read(table).sort_values(pk)
            self.assertGreater(t[pk].iloc[0], 1_000, table)
            self.assertGreater(t[pk].diff().mean(), 1.5, table)
            self.assertTrue(t[created].is_monotonic_increasing, table)
        self.assertTrue(self.read("customer_contact")["contact_id"].str.fullmatch(r"CM\d{9}").all())

    def test_no_record_is_older_than_the_company(self) -> None:
        agency = pd.read_csv(self.root / "a" / "agency.csv", dtype={"zip_code": str})
        self.assertGreaterEqual(self.read("policy")["original_inception_date"].min(), C.FOUNDED)
        self.assertGreaterEqual(agency["appointment_date"].min(), C.FOUNDED)
        self.assertGreaterEqual(self.read("producer")["start_date"].min(), C.FOUNDED)

    def test_wives_keep_their_surnames_at_their_groups_rates(self) -> None:
        """A married couple shares the husband's surname unless the wife kept hers, which Hispanic women do far more
        often than White women (names.KEPT_OWN_SURNAME)."""
        drv = self.read("driver").merge(pd.read_csv(self.root / "a" / "answer_key" / "driver_truth.csv"), on="driver_id")
        ni = drv[drv["driver_role"] == "Named Insured"].drop_duplicates("policy_id")
        sp = drv[drv["driver_role"] == "Spouse"].merge(ni, on="policy_id", suffixes=("", "_ni"))
        sp = sp[sp["gender"] != sp["gender_ni"]]
        wife_group = np.where(sp["gender"] == "F", sp["race_ethnicity"], sp["race_ethnicity_ni"])
        kept = pd.Series((sp["last_name"] != sp["last_name_ni"]).to_numpy()).groupby(wife_group).mean()
        self.assertGreater(kept["Hispanic"], kept["White (non-Hispanic)"] + 0.08, kept.to_dict())
        self.assertLess(kept["White (non-Hispanic)"], 0.2, kept.to_dict())

    def test_run_summary_identifies_the_build_and_its_files(self) -> None:
        """run_summary.json records what built the files and hashes that a copy of them can be checked against."""
        out = self.root / "a"
        summary = json.loads((out / "run_summary.json").read_text())
        self.assertEqual(summary["content_hash"], self.a["content_hash"])
        self.assertEqual(validate.payload_hash(out, "*.csv"), summary["tables_hash"])
        self.assertEqual(validate.payload_hash(out / "answer_key", "*.csv"), summary["answer_key_hash"])
        build = summary["build"]
        self.assertEqual((build["numpy"], build["pandas"]), (np.__version__, pd.__version__))
        self.assertEqual(set(build["reference_data"]), {f.name for f in C.REFERENCE_DIR.glob("*.csv")})
        self.assertIn("source_revision", build)
        with tempfile.TemporaryDirectory() as tmp:                     # a changed file no longer matches
            shutil.copytree(out, tmp, dirs_exist_ok=True)
            with open(Path(tmp) / "claim.csv", "a") as f:
                f.write("\n")
            self.assertNotEqual(validate.payload_hash(Path(tmp), "*.csv"), summary["tables_hash"])

    def test_key_map_covers_every_table(self) -> None:
        """autoins/schema.py names a primary key for every table and a key for every ..._id column."""
        cols = {p.stem: list(pd.read_csv(p, nrows=0).columns) for p in (self.root / "a").rglob("*.csv")}
        self.assertEqual(schema.problems(cols), [])

    def test_sqlite_release_links_every_table(self) -> None:
        """The SQLite release format loads every table with its keys; every foreign key resolves."""
        out = self.root / "a"
        tables = {p.stem: p for p in sorted(out.glob("*.csv"))} | {p.stem: p for p in sorted((out / "answer_key").glob("*.csv"))}
        db = self.root / "instructor.sqlite"
        release_formats.write_sqlite(tables, db)            # raises if a reference does not resolve
        con = sqlite3.connect(db)
        for name, path in tables.items():
            self.assertEqual(con.execute(f'SELECT COUNT(*) FROM "{name}"').fetchone()[0], len(pd.read_csv(path)), name)
        self.assertEqual(len(con.execute('PRAGMA foreign_key_list("claim")').fetchall()), 10)
        self.assertEqual(con.execute("SELECT DISTINCT typeof(zip_code) FROM vendor WHERE zip_code IS NOT NULL").fetchall(), [("text",)])
        self.assertEqual(con.execute("SELECT DISTINCT typeof(zip_code) FROM location").fetchall(), [("text",)])
        con.execute("PRAGMA foreign_keys = ON")
        with self.assertRaises(sqlite3.IntegrityError):
            con.execute("INSERT INTO claim (claim_id, policy_id) VALUES (-1, -1)")
        con.close()

    @unittest.skipUnless(importlib.util.find_spec("pyarrow"), "needs pyarrow (pip install -r requirements-release.txt)")
    def test_parquet_release_keeps_every_row_and_types_the_columns(self) -> None:
        """The Parquet release format writes one file per table with the CSV's rows and columns; whole numbers are
        integers even where some are blank, dates are dates, ZIP codes are text; the same data gives the same bytes."""
        import pyarrow as pa
        import pyarrow.parquet as pq
        out = self.root / "a"
        tables = {p.stem: p for p in sorted(out.glob("*.csv"))}
        bundle = release_formats.Bundle("students-parquet", tables, extras=[(out / "run_summary.json", "run_summary.json")])
        dest = self.root / "parquet"
        dest.mkdir(exist_ok=True)
        asset = release_formats.parquet_zip(bundle, dest)
        first = asset.read_bytes()
        self.assertEqual(release_formats.parquet_zip(bundle, dest).read_bytes(), first)
        with zipfile.ZipFile(asset) as z:
            self.assertEqual(sorted(z.namelist()), sorted([f"{t}.parquet" for t in tables] + ["run_summary.json"]))
            read = lambda name: pq.read_table(io.BytesIO(z.read(f"{name}.parquet")))
            for name, path in tables.items():
                t, csv = read(name), pd.read_csv(path, low_memory=False)
                self.assertEqual((t.num_rows, t.column_names), (len(csv), list(csv.columns)), name)
                for f in t.schema:      # every date column is a date, and nothing else is
                    self.assertEqual(pa.types.is_date32(f.type), release_formats.is_date_column(f.name), f"{name}.{f.name}")
            quote, risk, loc, pol = read("quote"), read("exposure"), read("location"), read("policy")
        q = pd.read_csv(tables["quote"])
        self.assertTrue(pa.types.is_int64(quote.schema.field("policy_id").type))          # blank on unbound quotes
        self.assertEqual(quote.column("policy_id").null_count, int(q["policy_id"].isna().sum()))
        self.assertGreater(quote.column("policy_id").null_count, 0)
        self.assertTrue(pa.types.is_string(loc.schema.field("zip_code").type))
        self.assertTrue(pa.types.is_string(pol.schema.field("policy_number").type))
        self.assertTrue(pa.types.is_float64(risk.schema.field("total_premium").type))
        e = pd.read_csv(tables["exposure"])
        self.assertAlmostEqual(risk.column("total_premium").to_pandas().sum(), e["total_premium"].sum(), places=6)
        self.assertEqual(risk.column("coverage_start_date").to_pandas().astype(str).tolist(), e["coverage_start_date"].tolist())

    def test_no_column_repeats_what_other_records_hold(self) -> None:
        """The tables hold what an insurer's systems record; totals an analyst works out from those records (a loss
        run, earned premium, counts, labels that restate a code) are not stored."""
        cols = {p.stem: set(pd.read_csv(p, nrows=0).columns) for p in (self.root / "a").glob("*.csv")}
        derived = {"claim": {"paid_loss", "case_reserve", "net_incurred_loss", "feature_count", "claim_description"},
                   "claim_feature": {"paid_loss", "case_reserve", "incurred_loss", "coverage", "closed_without_payment"},
                   "policy": {"number_of_vehicles", "number_of_drivers", "latest_expiration_date", "bi_limit"},
                   "policy_term": {"earned_premium", "endorsement_premium", "vehicles_at_term_start", "rate_level_index"},
                   "exposure": {"earned_exposure", "earned_premium", "model_year"}, "driver": {"prior_violations"},
                   "rate_change": {"cumulative_rate_level"}, "renewal_offer": {"premium_change_pct"}}
        for table, gone in derived.items():
            self.assertFalse(cols[table] & gone, table)
        self.assertTrue({"coverage", "cause_of_loss"} <= set(cols))
        self.assertFalse((self.read("insured_vehicle")["removed_date"].dropna() > self.a["valuation"]).any())

    def test_same_day_events_have_a_defined_order(self) -> None:
        """A company claim reaches the driving record the day after the payment that makes it chargeable, so
        a loss or payment on a rating date is never part of that rating."""
        inc, clm = self.read("driver_incident"), self.read("claim")
        own = inc[inc.source == "Company Claim"].merge(clm[["claim_id", "loss_date"]], on="claim_id")
        self.assertTrue((own["known_date"] > own["loss_date"]).all())
        pay = self.read("claim_payment")
        first = pay[pay["payment_type"] == "Loss"].groupby("claim_id")["payment_date"].min()
        self.assertTrue((own["known_date"] > own["claim_id"].map(first)).all())

    def test_incident_sources_match_when_and_where_they_happened(self) -> None:
        """A company claim before the extract happened before the start date, while the driver was on the policy;
        accidents an adult brings when joining a policy mid-term came from a previous insurer."""
        inc, drv, pol = self.read("driver_incident"), self.read("driver"), self.read("policy")
        inc = inc.merge(drv[["driver_id", "policy_id", "added_date"]], on="driver_id").merge(
            pol[["policy_id", "original_inception_date"]], on="policy_id")
        before = inc[inc.source == "Company Claim (Before Extract)"]
        self.assertGreater(len(before), 20)
        self.assertTrue((before["incident_date"] < self.a["start"]).all())
        self.assertTrue((before["incident_date"] >= before["added_date"]).all())
        self.assertTrue((before["incident_date"] >= before["original_inception_date"]).all())
        prior = inc[inc.source == "Prior Carrier Report"]
        joined_later = prior[prior["added_date"] > self.a["start"]]
        self.assertGreater(len(joined_later), 0)
        self.assertTrue((joined_later["incident_date"] <= joined_later["added_date"]).all())
        accidents = inc[inc.incident_type == "At-Fault Accident"]
        self.assertTrue(set(accidents.source) <= {"Company Claim", "Company Claim (Before Extract)", "Prior Carrier Report"})

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
        self.assertTrue((opening["earned_premium_before_extract"] > 0).all())   # (rebuilt from the exposure rows)
        r = risk[risk["policy_term_id"].isin(opening["policy_term_id"])]
        days = (pd.to_datetime(r["coverage_end_date"]).clip(upper=pd.Timestamp(self.a["valuation"]) + pd.Timedelta(days=1))
                - pd.to_datetime(r["coverage_start_date"]).clip(lower=pd.Timestamp(start))).dt.days / 365.25
        self.assertTrue(np.allclose(r["earned_exposure"], days, atol=1e-3))      # only the part after the start is earned
        # new business is exactly the first term of a policy
        self.assertTrue(((term["business_type"] == "New") == (term["term_number"] == 1)).all())
        first_effective = term.groupby("policy_id")["effective_date"].min().reindex(pol["policy_id"]).to_numpy()
        self.assertTrue((pol["original_inception_date"].to_numpy() <= first_effective).all())

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
        w = ledger[ledger["transaction_type"].isin(["New Business", "Renewal"])].groupby("policy_term_id")["written_premium"].sum()
        gap = (term.set_index("policy_term_id")["written_premium"] - w).abs()
        self.assertLess(gap.max(), 0.005)
        done = term[term["expiration_date"] < "2026-04-01"]          # every change to these terms has been processed
        earned = done["earned_premium_before_extract"] + done["earned_premium"]
        booked = done["written_premium"] + done["endorsement_premium"] + done["return_premium"]
        self.assertLess((earned - booked).abs().max(), 0.05 + 0.01 * done["vehicles_at_term_start"].max())

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
        self.assertTrue(set(loss["transaction_type"]) >= {"Partial Payment", "Final Payment"})

    def test_conviction_and_sr22_dates_before_the_start_are_kept(self) -> None:
        inc, drv = self.read("driver_incident"), self.read("driver")
        cv = inc[inc["conviction_date"].notna()]
        self.assertTrue((cv["conviction_date"] > cv["incident_date"]).all() and (cv["conviction_date"] <= cv["known_date"]).all())
        self.assertTrue((cv["conviction_date"] < "2022-01-01").any())
        s22 = drv[drv["sr22_filed_date"].notna()]
        self.assertTrue((s22["sr22_filed_date"] >= s22["added_date"]).all())

    def test_renewal_offers_keep_every_decision(self) -> None:
        """Every renewal evaluated is kept, declined and company non-renewals included, with the premium it was
        evaluated at, made from the exposure in force on its offer date; outcomes agree with the policy terms."""
        o, term, risk = self.read("renewal_offer"), self.read("policy_term"), self.read("exposure")
        rep, out = validate.Report(), io.StringIO()
        with contextlib.redirect_stdout(out):
            validate.integrity_renewals(rep, o, term, risk, self.a["valuation"])
        self.assertEqual(rep.failures, 0, out.getvalue())
        declined = o[o["outcome"].isin(["Insured Did Not Renew", "Company Non-Renewal"])]
        self.assertTrue({"Renewed", "Insured Did Not Renew", "Canceled Before Renewal", "Pending"} <= set(o["outcome"]))
        # (a household whose only car was written off, its replacement not yet bought, has nothing to price)
        self.assertTrue(((declined["renewal_premium"] > 0) | (declined["vehicles_offered"] == 0)).all()
                        and declined["offer_date"].notna().all())
        contact = self.read("customer_contact")
        self.assertIn("Notice of Non-Renewal", set(contact["purpose"])) if (o["outcome"] == "Company Non-Renewal").any() else None
        truth_ = pd.read_csv(self.root / "a" / "answer_key" / "renewal_offer_truth.csv")
        self.assertEqual(len(truth_), len(o))
        self.assertTrue(truth_["acceptance_probability"].dropna().between(0, 1).all())

    def test_calendar_identifier_billing_and_payment_checks_pass(self) -> None:
        """Staff, bank and court dates fall on business days; business keys are valid and IDs follow creation order;
        bills reconcile with the premium ledger and the cash; payments have a payee, a cheque sequence and an approver
        within authority; commissions follow the agency's rates."""
        t = {n: self.read(n) for n in ("policy_term", "claim", "claim_feature", "claim_payment", "claim_reserve_transaction",
                                       "driver_incident", "driver", "premium_transaction", "customer_contact", "policy",
                                       "insured_vehicle", "exposure", "quote", "vehicle_model_year", "billing_invoice",
                                       "billing_receipt", "employee", "vendor")}
        agency = pd.read_csv(self.root / "a" / "agency.csv", dtype={"zip_code": str})
        rep, out = validate.Report(), io.StringIO()
        with contextlib.redirect_stdout(out):
            validate.integrity_calendar(rep, t["policy_term"], t["claim"], t["claim_feature"], t["claim_payment"],
                                        t["claim_reserve_transaction"], t["driver_incident"], t["driver"], t["premium_transaction"],
                                        t["customer_contact"], t["employee"], agency, self.read("producer"), t["billing_invoice"])
            validate.integrity_identifiers(rep, t["policy"], t["policy_term"], t["driver"], t["insured_vehicle"], t["exposure"],
                                           t["claim"], t["claim_feature"], t["quote"], t["vehicle_model_year"])
            validate.integrity_billing(rep, t["billing_invoice"], t["billing_receipt"], t["policy_term"], t["premium_transaction"],
                                       t["policy"], self.a["valuation"], t["customer_contact"])
            validate.integrity_payments(rep, t["claim_payment"], t["claim"], t["claim_feature"], t["employee"], t["vendor"],
                                        t["premium_transaction"], agency, t["policy"], t["policy_term"])
            validate.integrity_payees(rep, t["claim_payment"], t["claim"], t["claim_feature"], t["insured_vehicle"], t["driver"])
        self.assertEqual(rep.failures, 0, out.getvalue())

    def test_general_ledger_balances_and_ties_to_the_subledgers(self) -> None:
        """Every journal balances; written and earned premium, cash, reserves, commissions and receivables in the
        ledger are the subledgers' own totals; the trial balance sums to zero."""
        t = {n: self.read(n) for n in ("gl_journal", "gl_account", "agency_statement", "premium_transaction", "policy",
                                       "policy_term", "billing_invoice", "billing_receipt", "claim_payment", "claim",
                                       "claim_feature", "claim_reserve_transaction")}
        agency = pd.read_csv(self.root / "a" / "agency.csv", dtype={"zip_code": str})
        rep, out = validate.Report(), io.StringIO()
        with contextlib.redirect_stdout(out):
            validate.integrity_ledger(rep, t["gl_journal"], t["gl_account"], t["agency_statement"], t["premium_transaction"],
                                      t["policy"], t["policy_term"], t["billing_invoice"], t["billing_receipt"], t["claim_payment"],
                                      t["claim"], t["claim_feature"], t["claim_reserve_transaction"], agency,
                                      np.datetime64(self.a["start"]), np.datetime64(self.a["valuation"]))
        self.assertEqual(rep.failures, 0, out.getvalue())
        gl = t["gl_journal"]
        self.assertAlmostEqual(float((gl["debit"] - gl["credit"]).sum()), 0.0, places=2)
        self.assertEqual(set(gl["journal_type"]), set(ledger.JOURNALS))
        self.assertEqual(sorted(gl["company_id"].unique()), [1, 2, 3])
        # the books open the day before the extract with an entry that balances for each company
        ob = gl[gl["journal_type"] == "Opening balances"]
        self.assertTrue((ob["posting_date"] == "2021-12-31").all() and len(ob) >= 12)

    def test_agencies_are_many_small_and_a_few_large(self) -> None:
        """About 120 independent agencies, most of them small; no two share a name; an agency named after its
        owner has that owner as its first producer."""
        ag, prod, pol = self.read("agency"), self.read("producer"), self.read("policy")
        n = ag["channel"].value_counts()
        self.assertEqual((n["Independent Agent"], n["Exclusive Agent"], n["Direct"]), (120, 14, 2))
        self.assertTrue(ag["agency_name"].is_unique and ag["agency_code"].is_unique)
        size = pol.groupby("agency_id").size().reindex(ag.loc[ag["channel"] == "Independent Agent", "agency_id"]).fillna(0)
        self.assertGreater(size.sort_values().tail(12).sum() / size.sum(), 0.25)        # the largest tenth write over a quarter
        first = prod.drop_duplicates("agency_id").set_index("agency_id")
        named = ag[ag["channel"] == "Exclusive Agent"].set_index("agency_id")
        full = (first["first_name"] + " " + first["last_name"]).reindex(named.index)
        self.assertTrue(all(name.startswith(owner) for name, owner in zip(named["agency_name"], full)))

    def test_no_work_is_dated_on_a_weekend(self) -> None:
        pay, clm = self.read("claim_payment"), self.read("claim")
        self.assertEqual(int((pd.to_datetime(pay["payment_date"]).dt.dayofweek >= 5).sum()), 0)
        self.assertEqual(int((pd.to_datetime(clm["close_date"].dropna()).dt.dayofweek >= 5).sum()), 0)
        # losses and first notices still happen at weekends
        self.assertGreater((pd.to_datetime(clm["loss_date"]).dt.dayofweek >= 5).mean(), 0.15)
        self.assertGreater((pd.to_datetime(clm["report_date"]).dt.dayofweek >= 5).mean(), 0.05)

    def test_identifiers_do_not_show_how_the_data_was_built(self) -> None:
        """Policy IDs follow the day a policy was written, so the book in force at the start is not a block of IDs and a
        policy's first term is not its policy ID less a constant."""
        pol, term = self.read("policy"), self.read("policy_term")
        self.assertTrue(all(identifiers.policy_number_is_valid(x) for x in pol["policy_number"].head(500)))
        first = term.sort_values("policy_term_id").groupby("policy_id").head(1)
        self.assertLess((first["policy_term_id"] == first["policy_id"] - 1_000_000).mean(), 0.01)
        written_in_window = pol["original_inception_date"] >= self.a["start"]
        opening_ids = pol.loc[~written_in_window, "policy_id"]
        self.assertLess(opening_ids.max(), pol.loc[written_in_window, "policy_id"].max())
        # (new business is numbered by the day it was bound, a few days before it takes effect)
        self.assertGreater(pol["policy_id"].rank().corr(pd.to_datetime(pol["original_inception_date"]).rank()), 0.999)

    def test_hidden_traits_are_only_in_the_answer_key(self) -> None:
        published = {p.stem: set(pd.read_csv(p, nrows=0).columns) for p in (self.root / "a").glob("*.csv")}
        self.assertFalse(any(c in cols for cols in published.values() for c in ("stability", "book_quality_factor")))
        truth_ = pd.read_csv(self.root / "a" / "answer_key" / "policy_truth.csv")
        pol = self.read("policy").merge(truth_, on="policy_id")
        opening = pol["original_inception_date"] < self.a["start"]
        self.assertGreater(pol.loc[opening, "stability"].mean(), pol.loc[~opening, "stability"].mean() + 0.3)
        # the traits the insurer does see follow it
        self.assertGreater(pol.loc[pol["homeowner"] == "Y", "stability"].mean(), pol.loc[pol["homeowner"] == "N", "stability"].mean())
        self.assertGreater(pol.loc[pol["multi_policy"] == "Y", "stability"].mean(), pol.loc[pol["multi_policy"] == "N", "stability"].mean())
        self.assertEqual(len(pd.read_csv(self.root / "a" / "answer_key" / "agency_truth.csv")), len(self.read("agency")))

    def test_filed_discounts_are_discounts(self) -> None:
        """Homeowner, multi-car, multi-policy, paid-in-full, loyalty, good-student and married factors are the filed
        ones (never above 1), and going without prior insurance is a surcharge."""
        import json
        plan = json.loads((self.root / "a" / "answer_key" / "rating_plan.json").read_text())
        bi = plan["relativities"]["BI"]
        for k in ("homeowner", "multi_car", "multi_policy", "paid_in_full", "good_student", "married"):
            self.assertEqual(bi[k]["No"], 1.0, k)
            self.assertLess(bi[k]["Yes"], 1.0, k)
        self.assertGreater(bi["prior_insurance"]["No"], bi["prior_insurance"]["Yes"])
        tenure = list(bi["tenure"].values())
        self.assertEqual(tenure, sorted(tenure, reverse=True))
        self.assertIn("relativities_indicated", plan)
        ex = self.read("exposure")
        self.assertIn("multi_car_discount", ex.columns)

    def test_bills_follow_the_payment_plan(self) -> None:
        inv, rec, pol, tx = self.read("billing_invoice"), self.read("billing_receipt"), self.read("policy"), self.read("premium_transaction")
        self.assertTrue({"Paid in Full", "Down Payment", "Installment", "Endorsement", "Final Balance"} <= set(inv["invoice_type"]))
        self.assertTrue({"Payment", "Refund"} <= set(rec["receipt_type"]))
        plan = pol.set_index("policy_id")["payment_plan"].reindex(inv["policy_id"]).to_numpy()
        self.assertTrue((inv.loc[inv["invoice_type"] == "Paid in Full", "installment_fee"] == 0).all())
        self.assertTrue((inv.loc[(inv["invoice_type"] == "Installment") & (plan == "Monthly Bill"), "installment_fee"] == 5).all())
        self.assertTrue((rec.loc[rec["receipt_type"] == "Refund", "amount"] < 0).all())
        direct = pol.set_index("policy_id")["distribution_channel"].reindex(tx["policy_id"]).to_numpy() == "Direct"
        self.assertTrue((tx.loc[direct, "commission_amount"] == 0).all() and (tx.loc[~direct, "commission_rate_pct"] > 0).all())

    def test_renewals_changed_after_the_offer_are_re_rated(self) -> None:
        t = self.read("policy_term")
        self.assertTrue((t["offer_date"] <= t["rating_date"]).all() and (t["rating_date"] <= t["effective_date"]).all())
        late = t[t["offer_date"] < t["rating_date"]]
        self.assertTrue(len(late) > 0 and (late["business_type"] == "Renewal").all())
        q = self.read("quote")
        self.assertEqual(set(q["telematics_opt_in"]), {"Y", "N"})
        self.assertTrue((q.loc[q["bound"] == "N", "telematics_opt_in"] == "Y").any())


class HistoryTest(unittest.TestCase):
    def test_a_later_change_to_the_callers_array_does_not_rewrite_the_past(self) -> None:
        h = simulate.History()
        ni = np.array([5, 6])
        h.add([0, 1], simulate.OPENING, ni)
        ni[0] = 9                         # the policy's named insured changes in place, as the simulation does
        h.add(0, 100, ni[0])
        self.assertEqual(h.at([0, 0, 1], [50, 100, 50])[0].tolist(), [5, 9, 6])


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


class WorkingCalendarTest(unittest.TestCase):
    def setUp(self) -> None:
        self.cal = Calendar(start=np.datetime64("2022-01-01"), valuation_day=2000, horizon=2001)     # day 0 is a Saturday

    def test_holidays_agree_with_an_independent_calendar(self) -> None:
        days = pd.date_range("2015-01-01", "2028-12-31")
        ours = ~np.isin(days.to_numpy().astype("M8[D]"), refdata.HOLIDAYS) & np.asarray(days.dayofweek < 5)
        np.testing.assert_array_equal(ours, validate.business_day(days))
        self.assertIn(np.datetime64("2024-11-29"), refdata.HOLIDAYS)       # the day after Thanksgiving
        self.assertNotIn(np.datetime64("2021-11-12"), refdata.HOLIDAYS)    # the day after Veterans Day is not

    def test_business_day_helpers(self) -> None:
        cal, d = self.cal, np.arange(-400, 2400)
        nxt, prv = cal.next_business(d), cal.prev_business(d)
        self.assertTrue(cal.is_business(nxt).all() and cal.is_business(prv).all())
        self.assertTrue((nxt >= d).all() and (prv <= d).all() and (nxt[cal.is_business(d)] == d[cal.is_business(d)]).all())
        self.assertEqual(int(cal.next_business(np.array([0]))[0]), 2)       # Saturday 1 January 2022 -> Monday the 3rd
        u = np.random.default_rng(1).random(len(d))
        spread = cal.spread_business(d, u)
        self.assertTrue(cal.is_business(spread).all() and (spread >= d).all() and (spread <= d + 11).all())
        self.assertGreater(len(np.unique(cal.weekday(spread[~cal.is_business(d)]))), 3)     # not all on Monday
        inside = cal.business_between(d, d - 2, d + 3, u)
        self.assertTrue(((inside >= d - 2) & (inside <= d + 3)).all())
        self.assertTrue(cal.is_business(inside)[cal.is_business(cal.next_business(d)) & (cal.next_business(d) <= d + 3)].all())
        np.testing.assert_array_equal(cal.business_between(d, d, d, u), d)               # nowhere to go: the day stays

    def test_weighted_lead_avoids_days_with_no_weight(self) -> None:
        cal = self.cal
        day = np.arange(100, 400)
        lead = cal.weighted_lead(day, 30, 45, lambda x: cal.is_business(x).astype(float), np.random.default_rng(2).random(len(day)))
        self.assertTrue(((lead >= 30) & (lead <= 45)).all() and cal.is_business(day - lead).all())


class IdentifierTest(unittest.TestCase):
    def test_vin_check_digit_matches_the_standard(self) -> None:
        # worked examples of the US VIN check digit: 1M8GDM9A_KP042788 -> X, and seventeen 1s -> 1
        self.assertEqual(identifiers.vin_check_digit(np.array(["1M8GDM9A0KP042788", "11111111111111111"])).tolist(), ["X", "1"])
        np.testing.assert_array_equal(validate.vin_check_digit(pd.Series(["1M8GDM9A0KP042788", "11111111111111111"])), ["X", "1"])

    def test_policy_number_check_digits(self) -> None:
        serial, code = np.array([830_512, 1_203_417, 9_999_999]), ["LFM", "PPC", "LFP"]
        check = identifiers.mod97_check(serial, code)
        numbers = [f"{s:07d}-{c}-{k:02d}" for s, c, k in zip(serial, code, check)]
        self.assertTrue(all(identifiers.policy_number_is_valid(x) for x in numbers))
        self.assertFalse(identifiers.policy_number_is_valid(numbers[0][:-2] + f"{(check[0] + 1) % 100:02d}"))
        self.assertFalse(identifiers.policy_number_is_valid("0830521" + numbers[0][7:]))      # two digits swapped

    def test_full_vins_are_unique_and_valid(self) -> None:
        r = np.random.default_rng(4)
        group = r.integers(0, 40, 5_000)
        pattern = np.array([f"0AB{g:05d}*K"[:8] + "*K" for g in group])
        vins = identifiers.full_vins(pattern, np.array(["Make"] * len(group)), group, r)
        self.assertEqual(len(set(vins)), len(vins))
        body = np.array([v[:8] + "0" + v[9:] for v in vins])
        np.testing.assert_array_equal(identifiers.vin_check_digit(body), np.array([v[8] for v in vins]))


class SettlementAndNewCustomerTest(unittest.TestCase):
    def test_settlements_are_round_and_within_one_step(self) -> None:
        r = np.random.default_rng(6)
        x = 20_000 * np.exp(1.4 * r.standard_normal(50_000))
        out = truth.round_settlement(x, r)
        cents = np.round(out * 100).astype(np.int64)
        self.assertGreater((cents % 5_000 == 0).mean(), 0.80)              # multiples of $50, but for the exact ones
        self.assertTrue((out > 0).all() and (np.abs(out - x) <= np.maximum(0.05 * x, 100)).all())
        self.assertLess(abs(out.sum() / x.sum() - 1), 0.002)               # rounding does not move the total
        for limit in (25_000, 50_000, 100_000, 250_000):                   # every step divides every limit
            self.assertTrue(all(limit % (2 * step) == 0 for _, step in C.SETTLEMENT_STEPS))

    def test_new_customer_multiplier_fades(self) -> None:
        t0 = np.zeros(4)
        f = truth.new_customer_factor(t0, np.array([0, 180, 365, 1825]), np.array([180, 365, 730, 2190]))
        self.assertTrue((np.diff(f) < 0).all() and f[0] > 1.25 and f[-1] < 1.02)
        days = truth.new_customer_days(np.zeros(20_000), np.zeros(20_000, dtype=int), np.full(20_000, 365), np.random.default_rng(8))
        self.assertTrue(((days >= 0) & (days < 365)).all())
        self.assertGreater((days < 90).mean(), 0.33)                        # the extra claims come early (a quarter would be even)


class MarketAndLedgerTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.cal = refdata.load(C.Config()).cal

    def test_a_rate_increase_opens_a_gap_that_the_market_closes(self) -> None:
        cal = self.cal
        day = lambda d: int((np.datetime64(d) - cal.start).astype(int))
        ref = day(C.MARKET_REFERENCE_DATE)
        self.assertAlmostEqual(float(market.gap(cal, ref)), 0.0, places=6)
        for d, change in C.RATE_CHANGES:
            if change >= 0.05:      # dearer than the market the day an increase lands, less so three months on
                before, on, later = (float(market.gap(cal, day(d) + k)) for k in (-1, 0, 90))
                self.assertAlmostEqual(on - before, np.log(1 + change), places=2)
                self.assertLess(later, on)
        # the market's level compounds each year's change
        year_end = cal.market_level[day("2023-01-01")] / cal.market_level[day("2022-01-01")]
        self.assertAlmostEqual(float(year_end), 1 + C.MARKET_RATE_CHANGE[2022], places=3)

    def test_conversion_falls_as_the_gap_widens_and_new_business_follows(self) -> None:
        cal = self.cal
        months = np.arange(60)
        conv, shop = market.conversion(cal, months), market.shopping(cal, months)
        gap = market.gap(cal, cal.day_of(months, 15))
        self.assertTrue((np.corrcoef(gap, conv[0])[0, 1] < -0.95) and (conv > 0).all() and (conv < 1).all())
        self.assertTrue((conv[1] > conv[0]).all() and (conv[0] > conv[2]).all())      # exclusive > independent > direct
        w = market.month_weights(cal, 60, shoppers=False)
        np.testing.assert_allclose(w, shop[None, :] * conv)
        np.testing.assert_allclose(market.month_weights(cal, 60, shoppers=True), np.tile(shop, (3, 1)))
        march, december = shop[2::12].mean(), shop[11::12].mean()
        self.assertGreater(march / december, 1.2)
        self.assertAlmostEqual(float(market.bind_p(np.array([0]), np.array([0.0]))[0]), C.QUOTE_CONVERSION["Independent Agent"], places=9)

    def test_unearned_premium_runs_off_evenly(self) -> None:
        amount, eff, exp, booked = (np.array(v) for v in ([36_500, 36_500, -7_300], [0, 0, 292], [365, 365, 365], [0, 400, 300]))
        self.assertEqual(ledger.unearned(amount, eff, exp, booked, -1).tolist(), [0, 0, 0])            # not yet booked
        self.assertEqual(ledger.unearned(amount, eff, exp, booked, 0).tolist(), [36_400, 0, 0])        # one day earned
        self.assertEqual(ledger.unearned(amount, eff, exp, booked, 299).tolist(), [6_500, 0, 0])
        self.assertEqual(ledger.unearned(amount, eff, exp, booked, 300).tolist(), [6_400, 0, -6_400])  # a return booked late
        self.assertEqual(ledger.unearned(amount, eff, exp, booked, 364).tolist(), [0, 0, 0])
        self.assertEqual(ledger.unearned(amount, eff, exp, booked, 400).tolist(), [0, 0, 0])           # booked after it expired
        self.assertEqual(int(ledger.accounting_day(np.array([10]), np.array([3]))[0]), 10)

    def test_a_car_loses_value_with_age_and_never_tops_a_new_one(self) -> None:
        cal = self.cal
        day = int((np.datetime64("2024-07-01") - cal.start).astype(int))
        years = np.arange(2025, 1995, -1)
        value = truth.actual_cash_value(np.full(len(years), 30_000.0), years, np.full(len(years), day), cal)
        self.assertTrue((np.diff(value) <= 0).all())
        self.assertLessEqual(value.max(), 30_000 * C.NEW_VALUE_CAP + 1e-6)
        ten = value[years == 2014][0]
        self.assertTrue(0.30 * 30_000 < ten < 0.50 * 30_000)                 # about 40% of the base price at ten years
        self.assertGreaterEqual(value.min(), C.MIN_VEHICLE_VALUE)
        dearer = truth.actual_cash_value(np.array([30_000.0]), np.array([2014]), np.array([day]), cal,
                                         level_day=np.array([int((np.datetime64("2022-07-01") - cal.start).astype(int))]))
        self.assertGreater(dearer[0], ten)                                   # used cars were dearer in 2022


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

    def test_underinsured_allows_for_the_other_insurers_per_accident_limit(self) -> None:
        # three injured occupants with $40,000 each against an at-fault driver insured for 25/50: that insurer
        # pays $50,000 in all, not 3 x $25,000, so our underinsured cover owes $70,000, not $45,000
        gross, accident = np.full(3, 40_000.0), np.zeros(3, dtype=int)
        benefit, other = truth.underinsured(gross, 100_000, np.full(3, 25_000.0), accident, 1, np.array([50_000.0]))
        self.assertAlmostEqual(other.sum(), 50_000.0, places=2)
        self.assertAlmostEqual(benefit.sum(), 70_000.0, places=2)
        self.assertGreater(truth.AGG_SHARE["UIM"].max(), 1.0)       # the expected loss allows for it too


class ReserveSharingTest(unittest.TestCase):
    """Claimants of one accident share its per-accident limit, from what is known on each day."""

    def setUp(self) -> None:
        self.cal = Calendar(start=np.datetime64("2022-01-01"), valuation_day=2000, horizon=2001)     # day 0 is a Saturday
        self.feat = pd.DataFrame(dict(occ=[0, 0], cvg=["BI", "BI"], room=[50_000.0, 50_000.0]), index=[10, 11])

    def share(self, rows) -> pd.DataFrame:
        """rows: (feature, day, order, transaction, the reserve it wants, paid to date)."""
        ev = pd.DataFrame(rows, columns=["fid", "day", "order", "txn", "want", "paid"]).assign(est=np.nan, pay=0.0)
        ev = ev.sort_values(["fid", "day", "order"], kind="stable").reset_index(drop=True)
        out, bal = claims._share_accident_limit(ev.drop(columns=["want", "paid"]), ev.want.to_numpy(float),
                                                ev.paid.to_numpy(float), self.feat, self.cal)
        return out.assign(bal=bal)

    def test_a_new_claimant_shares_the_limit_and_a_settlement_frees_it(self) -> None:
        # Monday: A reserved at $30,000. Tuesday: B too, so the two share $50,000. Wednesday: B settles for $10,000
        out = self.share([(10, 2, 0, "Initial Reserve", 30_000, 0), (11, 3, 0, "Initial Reserve", 30_000, 0),
                          (11, 4, 1, "Payment", 20_000, 10_000), (11, 4, 2, "Close", 0, 10_000)])
        a, b = out[out.fid == 10], out[out.fid == 11]
        self.assertEqual(a.bal.tolist(), [30_000, 25_000, 30_000])          # cut when B arrives, restored when B settles
        self.assertEqual(a.txn.tolist(), ["Initial Reserve", "Reserve Review", "Reserve Review"])
        self.assertEqual(a.day.tolist(), [2, 3, 4])
        self.assertEqual(b.bal.tolist(), [25_000, 15_000, 0])

    def test_a_weekend_reserve_takes_only_the_room_left(self) -> None:
        # B is reported on Saturday (day 7): its formula reserve gets what A leaves; Monday's review shares the limit
        out = self.share([(10, 2, 0, "Initial Reserve", 30_000, 0), (11, 7, 0, "Initial Reserve", 30_000, 0),
                          (11, 9, 0, "Reserve Review", 30_000, 0)])
        a, b = out[out.fid == 10], out[out.fid == 11]
        self.assertEqual(b.bal.tolist(), [20_000, 25_000])
        self.assertEqual(a.bal.tolist(), [30_000, 25_000])
        self.assertTrue(self.cal.is_business(a.day.to_numpy()[1:]).all())     # changes made by an adjuster: business days

    def test_never_more_than_the_limit_whatever_the_estimates(self) -> None:
        r = np.random.default_rng(4)
        rows = []
        for fid in (10, 11):
            days = np.sort(r.choice(np.arange(2, 200), 12, replace=False))
            paid = np.cumsum(np.where(r.random(12) < 0.3, r.uniform(0, 4_000, 12), 0.0))
            rows += [(fid, int(d), 0, "Reserve Review", float(w), float(p)) for d, w, p in zip(days, r.uniform(0, 60_000, 12), paid)]
        out = self.share(rows)
        ev = pd.DataFrame(rows, columns=["fid", "day", "order", "txn", "want", "paid"])
        for day in np.unique(out.day):
            state = out[out.day <= day].groupby("fid").bal.last()
            spent = ev[ev.day <= day].groupby("fid").paid.max()
            self.assertLessEqual(state.sum() + spent.sum(), 50_000 + 0.01)


class ExperienceRatingTest(unittest.TestCase):
    def test_experience_is_unbiased_and_credibility_grows_with_claims(self) -> None:
        y = {k: np.full(200_000, 50.0) for k in C.COVERAGES}
        loss, count = rating.experience(y, np.random.default_rng(8))
        for k in C.COVERAGES:
            self.assertAlmostEqual(loss[k].sum() / (y[k].sum() * C.EXPERIENCE_YEARS), 1.0, delta=0.05)
            self.assertTrue(((loss[k] > 0) == (count[k] > 0)).all())
        z = rating.credibility(np.array([0, 100, 1_082 * 2, 10 ** 6]), 1.0)
        self.assertEqual(z[0], 0.0)
        self.assertTrue(0 < z[1] < z[2] and z[2] == z[3] == 1.0)       # full credibility at 1,082 x (1 + CV^2) claims


class TelematicsAssignmentTest(unittest.TestCase):
    """A score is the driving of the driver assigned to the car at the time (simulate._scored_parts)."""
    log = dict(log_veh=[5, 5, 7], log_day=[simulate.OPENING, 100, simulate.OPENING], log_drv=[10, 11, 20])

    def split(self, log, ws=0, we=90):
        return [tuple(int(x) for x in a) for a in zip(*telematics.split_windows(
            log["log_veh"], log["log_day"], log["log_drv"], np.array([5]), np.array([ws]), np.array([we])))]

    def test_a_later_takeover_leaves_an_earlier_score_alone(self) -> None:
        # a spouse takes the car over on day 100, after the window ends on day 90
        self.assertEqual(self.split(self.log), [(0, 0, 90, 10)])
        for later in (91, 150, 400):         # moving the takeover anywhere after the window changes nothing
            self.assertEqual(self.split({**self.log, "log_day": [simulate.OPENING, later, simulate.OPENING]}), [(0, 0, 90, 10)])
        self.assertEqual(self.split({**self.log, "log_day": [simulate.OPENING, 90, simulate.OPENING]}), [(0, 0, 90, 10)])

    def test_a_change_inside_the_window_splits_it(self) -> None:
        log = {**self.log, "log_day": [simulate.OPENING, 50, simulate.OPENING]}
        self.assertEqual(self.split(log), [(0, 0, 50, 10), (0, 50, 90, 11)])
        # a move (same driver, new garaging ZIP) is not a change of driver
        log = dict(log_veh=[5, 5, 5], log_day=[simulate.OPENING, 30, 60], log_drv=[10, 10, 11])
        self.assertEqual(self.split(log), [(0, 0, 60, 10), (0, 60, 90, 11)])

    def test_scores_do_not_depend_on_later_assignments(self) -> None:
        """With the same draws, the metrics of an earlier window are the same however the car is assigned later."""
        def metrics(log):
            w, s, e, d = telematics.split_windows(log["log_veh"], log["log_day"], log["log_drv"], np.array([5, 7]),
                                                  np.array([0, 0]), np.array([90, 90]))
            prop = np.array([0.7, 1.4, 1.0])[d - 10 if (d < 20).all() else np.where(d < 20, d - 10, 2)]
            return telematics.metrics(np.random.default_rng(3), prop, np.full(len(d), 40.0), np.full(len(d), 9000.0),
                                      np.full(len(d), 5000.0), e - s)
        a = metrics(self.log)
        b = metrics({**self.log, "log_day": [simulate.OPENING, 300, simulate.OPENING]})
        for k in a:
            np.testing.assert_array_equal(a[k], b[k])


class MileageHistoryTest(unittest.TestCase):
    """A car's telematics period is measured on the mileage it was driven then (simulate._miles_then): a change
    inside the period counts for its days only, and a later change (a move after the offer day) not at all."""

    def test_day_weighted_and_later_changes_ignored(self):
        from types import SimpleNamespace
        change = lambda car, day, old, new: pd.DataFrame(dict(car=[car], day=[day], old=[old], new=[new]))
        sim = SimpleNamespace(st=SimpleNamespace(v={"true_miles": np.array([30_000.0, 8_000.0])}),
                              mile_changes=[change(0, 100, 10_000.0, 20_000.0), change(0, 300, 20_000.0, 30_000.0)])
        got = simulate._miles_then(sim, np.array([0, 0, 0, 0, 1]), np.array([0, 0, 150, 250, 0]),
                                   np.array([100, 200, 200, 350, 50]))
        np.testing.assert_allclose(got, [10_000, 15_000, 20_000, 25_000, 8_000])


class RenewalTimelineTest(unittest.TestCase):
    """A renewal offer and decision depend only on the policy's history up to the offer date (simulate._renewals).
    Re-evaluating each offer at the end of the run, with everything that happened later in the history (later claims,
    moves, cars, drivers and records, and the policy's current state), gives the offer and decision made at the time."""

    @classmethod
    def setUpClass(cls) -> None:
        cfg = replace(C.Config(), n_policies=1200, seed=21)
        ref = refdata.load(cfg)
        cls.res = simulate.run(cfg, ref, population.build(cfg, ref))
        cls.sim = cls.res.sim

    def evaluate(self, off, rows=None):
        """Evaluate the offers in `off` again, pass by pass, with each car's telematics discount from the offer day."""
        out = []
        for k, g in off.groupby("k"):
            g = g.sort_values("pol")
            cars = self.res.offer_cars[self.res.offer_cars.exp_term.isin(g.exp_term)]
            tele = np.zeros(len(self.sim.st.v["pol"]))
            tele[cars.veh.to_numpy()] = cars.tele_disc.to_numpy()
            a = lambda c: g[c].to_numpy()
            ev, _ = simulate.evaluate_offers(self.sim, a("pol"), a("exp_term"), a("offer_day"), a("eff"), a("since"), a("tenure"),
                                             a("ty"), a("ni_age"), self.res.rows if rows is None else rows, tele)
            flag = simulate.underwriting_review(self.sim, a("pol"), a("offer_day"), a("eff"))
            out.append(pd.DataFrame({"pol": a("pol"), "exp_term": a("exp_term"), "n_veh": ev["n_veh"], "expiring": ev["expiring"],
                                     "premium": ev["premium"], "p_accept": 1 / (1 + np.exp(-ev["logit"])),
                                     "prev_claims": ev["prev_claims"],
                                     "company": flag & (a("u_company") < simulate.UW_NONRENEW_P)}))
        return pd.concat(out).set_index("exp_term").reindex(off.exp_term)

    def assertSameOffers(self, off, again) -> None:
        for c in ("n_veh", "prev_claims", "company"):
            np.testing.assert_array_equal(again[c].to_numpy(), off[c].to_numpy(), c)
        for c in ("expiring", "premium", "p_accept"):
            np.testing.assert_allclose(again[c].to_numpy(), off[c].to_numpy(), rtol=0, atol=1e-6, err_msg=c)
        accept = again["p_accept"].to_numpy() > off["u_stay"].to_numpy()
        np.testing.assert_array_equal(accept, off["u_stay"].to_numpy() < off["p_accept"].to_numpy())

    def test_offers_are_the_same_with_the_whole_later_history(self) -> None:
        off = self.res.offers
        self.assertGreater(len(off), 2000)
        self.assertSameOffers(off, self.evaluate(off))
        self.assertTrue({"Insured Did Not Renew", "Renewed"} <= set(off.outcome))

    def test_later_claims_moves_and_records_cannot_change_an_offer(self) -> None:
        # one offer per policy (a claim the day after one offer would rightly count at the policy's next offer)
        sim, off = self.sim, self.res.offers.sample(frac=1, random_state=1).drop_duplicates("pol").sort_values("exp_term")
        p, v, drv = sim.st.p, sim.st.v, sim.pop.drv
        saved = (list(sim.clm_pol), list(sim.clm_report), list(sim.recs.parts), sim.recs._frame, p["homeowner"].copy(),
                 v["primary_drv"].copy(), drv["marital"].copy(), list(sim.af_pol), list(sim.af_report))
        try:
            pol, o = off.pol.to_numpy(), off.offer_day.to_numpy()
            # a claim reported the day after each offer, and a serious record known the day after it
            sim.clm_pol.append(pol)
            sim.clm_report.append(o + 1)
            d = drv.drv.to_numpy()[np.isin(drv.pol.to_numpy(), pol)]
            for _ in range(3):
                sim.recs.add(d, np.full(len(d), o.min() - 10), np.full(len(d), simulate.KIND["major"]), np.full(len(d), o.max() + 1))
            # later exposure: every car of the expiring term moves to another ZIP the day after the offer, with
            # another driver, and the household's current state is scrambled
            r = self.res.rows
            later = r[r.term.isin(off.exp_term)].copy()
            later["s"] = off.set_index("exp_term").offer_day.reindex(later.term).to_numpy() + 1
            later["zi"], later["drv"] = (later.zi + 1) % len(sim.ref.zips), later.drv[::-1].to_numpy()
            p["homeowner"][:] = 1 - p["homeowner"]
            v["primary_drv"][:] = v["primary_drv"][::-1]
            drv["marital"] = "M"
            self.assertSameOffers(off, self.evaluate(off, pd.concat([r, later], ignore_index=True)))
            # but a claim reported on the offer date itself counts, and lowers the chance of renewing
            fresh = off[off.prev_claims == 0]
            sim.clm_pol.append(fresh.pol.to_numpy())
            sim.clm_report.append(fresh.offer_day.to_numpy())
            again = self.evaluate(fresh)
            self.assertTrue((again.prev_claims.to_numpy() == 1).all() and (again.p_accept.to_numpy() < fresh.p_accept.to_numpy()).all())
            # and an at-fault one lowers it further
            sim.af_pol.append(fresh.pol.to_numpy())
            sim.af_report.append(fresh.offer_day.to_numpy())
            worse = self.evaluate(fresh)
            self.assertTrue((worse.p_accept.to_numpy() < again.p_accept.to_numpy()).all())
        finally:
            sim.clm_pol[:], sim.clm_report[:], sim.recs.parts[:] = saved[0], saved[1], saved[2]
            sim.af_pol[:], sim.af_report[:] = saved[7], saved[8]
            sim.recs._frame, p["homeowner"][:], v["primary_drv"][:], drv["marital"] = saved[3], saved[4], saved[5], saved[6]

    def test_records_count_from_the_day_they_become_known(self) -> None:
        sim = self.sim
        off = self.res.offers.drop_duplicates("pol")                # the review takes one offer per policy
        clean = ~simulate.underwriting_review(sim, off.pol.to_numpy(), off.offer_day.to_numpy(), off.eff.to_numpy())
        off = off[clean].iloc[:200]                                 # offers it does not flag as things stand
        pol, o, eff = off.pol.to_numpy(), off.offer_day.to_numpy(), off.eff.to_numpy()
        drv = sim.pop.drv
        dp, rem = drv.pol.to_numpy(), drv.removed_day.to_numpy()
        # one driver of each policy who is on it on the offer date
        i_of = pd.Series(np.arange(len(pol)), index=pol)
        on = np.isin(dp, pol) & (drv.added_day.to_numpy() <= o[i_of.reindex(dp).fillna(0).astype(int).to_numpy()])
        d = pd.DataFrame({"drv": drv.drv.to_numpy()[on], "pol": dp[on]}).drop_duplicates("pol")
        d = d[(rem[d.drv] < 0) | (rem[d.drv] > o[i_of[d.pol].to_numpy()])]
        when = o[i_of[d.pol].to_numpy()]
        saved = (list(sim.recs.parts), sim.recs._frame)
        try:
            for known, flagged in ((when + 1, False), (when, True)):
                sim.recs.parts[:] = saved[0]
                sim.recs._frame = None
                for _ in range(2):     # two at-fault accidents in the year before the renewal
                    sim.recs.add(d.drv, when - 200, np.full(len(d), simulate.KIND["accident"]), known)
                got = simulate.underwriting_review(sim, pol, o, eff)[i_of[d.pol].to_numpy()]
                self.assertEqual(bool(got.all()), flagged)
                self.assertEqual(bool(got.any()), flagged)
        finally:
            sim.recs.parts[:], sim.recs._frame = saved


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
