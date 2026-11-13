"""Run with:  python -m unittest discover tests"""
from __future__ import annotations

import sys
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from autoins import config as C  # noqa: E402
from autoins.pipeline import generate  # noqa: E402


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

    def test_same_seed_is_byte_identical(self) -> None:
        files = sorted(p.relative_to(self.root / "a") for p in (self.root / "a").rglob("*") if p.is_file())
        self.assertGreater(len(files), 20)
        for f in files:
            self.assertEqual((self.root / "a" / f).read_bytes(), (self.root / "b" / f).read_bytes(), f"{f} differs")

    def test_different_seed_changes_the_data(self) -> None:
        self.assertNotEqual(self.a["content_hash"], self.c["content_hash"])

    def test_claims_fall_inside_their_policy_term(self) -> None:
        read = lambda n: pd.read_csv(self.root / "a" / f"{n}.csv")
        clm, term = read("claims_fact"), read("policy_term_fact")
        m = clm.merge(term, on="Policy Term ID")
        end = m["Cancel Date"].fillna(m["Policy Expiration Date"])
        self.assertTrue(((m["Loss Date"] >= m["Policy Effective Date"]) & (m["Loss Date"] < end)).all())
        self.assertTrue((clm["Report Date"] >= clm["Loss Date"]).all())
        self.assertTrue((clm["Loss Date"] <= self.a["valuation"]).all())

    def test_premium_and_exposure_are_sane(self) -> None:
        risk = pd.read_csv(self.root / "a" / "risk_fact.csv")
        self.assertTrue((risk["Total Premium"] > 0).all())
        self.assertTrue((risk["Earned Premium"] <= risk["Total Premium"] + 0.01).all())
        self.assertTrue(risk["Earned Exposure"].between(0, 1.01).all())


if __name__ == "__main__":
    unittest.main()
