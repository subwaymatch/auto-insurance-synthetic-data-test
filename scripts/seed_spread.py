#!/usr/bin/env python3
"""How much the validator's benchmark figures, and a few tail and joint diagnostics, move from one seed to another.

    python scripts/seed_spread.py --work /tmp/seeds                      # five seeds at the default size
    python scripts/seed_spread.py --work /tmp/seeds --seeds 1 2 3 --jobs 3
    python scripts/seed_spread.py --work /tmp/seeds --markdown > spread.md

Each seed is generated into WORK/seed_<seed> (skipped if it is already there) and validated with --json. The
report gives, for every calibration band in validate.py, the mean, lowest and highest figure across the seeds and
how many seeds land inside the band; then the diagnostics below, with an outside figure where one is published.
docs/benchmarks.md says where each benchmark comes from and whether it was used for tuning or held out.

Diagnostics (computed here from the tables, the way an analyst would):

* total-loss share: paid collision and comprehensive features (glass apart) that are total losses, and collision
  alone. CCC Intelligent Solutions' Crash Course puts total loss frequency at 22.1% of the vehicle claims it
  appraised in 2024 and 22.8% in 2025 (all US; first-party and third-party property damage appraisals together,
  glass apart, paid or not);
* total losses on cars seven or more model years old: 72% of total-loss valuations in CCC's 2025 report;
* average value of the cars paid as total losses (paid plus deductible, owner-retained salvage apart): CCC puts the
  average total-loss vehicle value at $13,400 to $13,700 in 2024-25 (it informed the residual values, see config);
* claims closed without payment: about 45% of liability and medical payments claims and just under 25% of
  collision and comprehensive ones in 2025 (Wall Street Journal analysis of insurer filings with the NAIC; the
  generator's rates of unpaid claims were set to land near these);
* average age of insured cars in force, car-year weighted, in the last full year: S&P Global Mobility puts US light
  vehicles in operation at 12.6 years (2024) and 12.8 years (2025), all vehicles registered rather than insured ones;
* the tail of claim cost per risk row (exposure row) with a claim: the share of cost in the costliest 1% and the
  coefficient of variation; no US figure is published on these terms;
* bodily injury: the share of paid claimants paid the full per-person limit, and the 50th, 90th and 99th
  percentiles of paid claimants' payments; no public US figure on these terms either.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
import validate  # noqa: E402

SEEDS = [20250101, 7, 11, 23, 42]
DIAGNOSTICS = {   # name -> (published figure, what it is)
    "total-loss share, paid collision and comprehensive claims (glass apart)": ("22.1% (2024), 22.8% (2025)", "CCC Crash Course, US: all appraised vehicle claims"),
    "total-loss share, paid collision claims": ("-", "no US figure for collision alone"),
    "total losses on cars 7+ model years old": ("72%", "CCC Crash Course, US, 2025"),
    "average value of cars paid as total losses ($)": ("13,400 to 13,700", "CCC Crash Course, US, 2024-25 (used in setting values)"),
    "closed liability and medical payments claims without payment": ("about 45%", "WSJ analysis of NAIC filings, 2025 (tuned)"),
    "closed collision and comprehensive claims without payment": ("just under 25%", "WSJ analysis of NAIC filings, 2025 (tuned)"),
    "closed collision claims without payment": ("-", "(collision alone)"),
    "average age of insured cars in force, last full year (years)": ("12.6 (2024), 12.8 (2025)", "S&P Global Mobility, US light vehicles in operation"),
    "share of claim cost in the costliest 1% of risk rows with a claim": ("-", "no US figure on these terms"),
    "coefficient of variation of claim cost per risk row with a claim": ("-", "no US figure on these terms"),
    "bodily injury claimants paid the full per-person limit": ("-", "no public US figure"),
    "bodily injury paid per claimant, median ($)": ("-", "no public US figure"),
    "bodily injury paid per claimant, 90th percentile ($)": ("-", "no public US figure"),
    "bodily injury paid per claimant, 99th percentile ($)": ("-", "no public US figure"),
}
PERCENT = {k for k in DIAGNOSTICS if "share" in k or k.startswith("total losses") or "full per-person" in k or "without" in k}


def build(seed: int, work: Path, policies: int | None) -> Path:
    out = work / f"seed_{seed}"
    if not (out / "run_summary.json").exists():
        cmd = [sys.executable, str(ROOT / "generate.py"), "--seed", str(seed), "--out", str(out)]
        if policies:
            cmd += ["--policies", str(policies)]
        subprocess.run(cmd, check=True, capture_output=True)
    bands = work / f"seed_{seed}.bands.json"
    if not bands.exists():
        r = subprocess.run([sys.executable, str(ROOT / "validate.py"), "--out", str(out), "--json", str(bands)],
                           capture_output=True, text=True)
        if not bands.exists():
            raise RuntimeError(f"validation of seed {seed} did not finish:\n{r.stdout[-2000:]}\n{r.stderr[-2000:]}")
    return out


def diagnostics(out: Path) -> dict:
    run = json.loads((out / "run_summary.json").read_text())
    start, valuation = np.datetime64(run["start"]), np.datetime64(run["valuation"])
    t = validate.rebuild(validate.load(out), start, valuation)
    clm, feat, risk, veh, vmy = t["claim"], t["claim_feature"], t["exposure"], t["insured_vehicle"], t["vehicle_model_year"]
    d = {}
    paid = feat[feat["coverage_code"].isin(["COLL", "COMP"]) & (feat["paid_loss"] > 0)].merge(clm[["claim_id", "cause_of_loss"]])
    paid = paid[paid["cause_of_loss"] != "GLASS"]
    d["total-loss share, paid collision and comprehensive claims (glass apart)"] = (paid["total_loss"] == "Y").mean()
    d["total-loss share, paid collision claims"] = (paid.loc[paid["coverage_code"] == "COLL", "total_loss"] == "Y").mean()
    total = feat[feat["coverage_code"].isin(["COLL", "COMP"]) & (feat["total_loss"] == "Y") & (feat["paid_loss"] > 0)]
    c = total.merge(clm[["claim_id", "loss_date", "vehicle_model_year_id"]], on="claim_id").merge(vmy[["vehicle_model_year_id", "model_year"]])
    d["total losses on cars 7+ model years old"] = (pd.to_datetime(c["loss_date"]).dt.year - c["model_year"] >= 7).mean()

    tl = total[total["owner_retained_salvage"] == "N"].merge(clm[["claim_id", "exposure_id", "cause_of_loss"]]) \
        .merge(risk[["exposure_id", "collision_deductible", "comprehensive_deductible", "full_glass_coverage"]])
    tl = tl[tl["cause_of_loss"] != "GLASS"]
    ded = np.where(tl["coverage_code"] == "COLL", tl["collision_deductible"], tl["comprehensive_deductible"])
    d["average value of cars paid as total losses ($)"] = (tl["paid_loss"] + np.nan_to_num(ded.astype(float))).mean()
    closed = feat[feat["feature_status"] == "Closed"]
    nil = lambda codes: (closed.loc[closed["coverage_code"].isin(codes), "paid_loss"] <= 0).mean()
    d["closed liability and medical payments claims without payment"] = nil(["BI", "PD", "MED"])
    d["closed collision and comprehensive claims without payment"] = nil(["COLL", "COMP"])
    d["closed collision claims without payment"] = nil(["COLL"])

    year = int(str(valuation)[:4]) - (0 if str(valuation)[5:] == "12-31" else 1)
    a, b = pd.Timestamp(f"{year}-01-01"), pd.Timestamp(f"{year + 1}-01-01")
    s = pd.to_datetime(risk["coverage_start_date"])
    e = pd.to_datetime(risk["coverage_end_date"]).fillna(pd.Timestamp(valuation) + pd.Timedelta(days=1))
    days = (np.minimum(e, b) - np.maximum(s, a)).dt.days.clip(lower=0)
    my = risk[["insured_vehicle_id"]].merge(veh[["insured_vehicle_id", "vehicle_model_year_id"]], how="left") \
        .merge(vmy[["vehicle_model_year_id", "model_year"]], how="left")["model_year"].to_numpy()
    d["average age of insured cars in force, last full year (years)"] = np.average(year + 0.5 - (my - 0.5), weights=days)

    cost = clm.groupby("exposure_id")["net_incurred_loss"].sum()
    cost = np.sort(cost[cost > 0].to_numpy())[::-1]
    d["share of claim cost in the costliest 1% of risk rows with a claim"] = cost[:max(int(np.ceil(len(cost) * 0.01)), 1)].sum() / cost.sum()
    d["coefficient of variation of claim cost per risk row with a claim"] = cost.std() / cost.mean()

    bi = feat[(feat["coverage_code"] == "BI") & (feat["paid_loss"] > 0)].merge(clm[["claim_id", "exposure_id"]]) \
        .merge(risk[["exposure_id", "bi_limit"]])
    per_person = bi["bi_limit"].str.split("/").str[0].astype(float) * 1000
    d["bodily injury claimants paid the full per-person limit"] = (bi["paid_loss"] >= per_person - 0.005).mean()
    for q, name in ((0.5, "median"), (0.9, "90th percentile"), (0.99, "99th percentile")):
        d[f"bodily injury paid per claimant, {name} ($)"] = bi["paid_loss"].quantile(q)
    return d


def fmt(x: float, percent: bool) -> str:
    if percent:
        return f"{x:.1%}"
    return f"{x:,.0f}" if abs(x) >= 100 else f"{x:.2f}"


def table(head: list[str], rows: list[list[str]], markdown: bool) -> str:
    if markdown:
        lines = ["| " + " | ".join(head) + " |", "|" + "|".join("---" if i == 0 else "--:" for i in range(len(head))) + "|"]
        return "\n".join(lines + ["| " + " | ".join(r) + " |" for r in rows])
    w = [max(len(x) for x in col) for col in zip(head, *rows)]
    return "\n".join("  ".join(x.ljust(k) for x, k in zip(r, w)) for r in [head] + rows)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--work", type=Path, required=True, help="folder for the generated datasets")
    ap.add_argument("--seeds", type=int, nargs="+", default=SEEDS)
    ap.add_argument("--policies", type=int, help="policies per dataset (default: the generator's)")
    ap.add_argument("--jobs", type=int, default=2, help="datasets generated at once (each needs about 3 GB of memory)")
    ap.add_argument("--markdown", action="store_true")
    a = ap.parse_args()
    a.work.mkdir(parents=True, exist_ok=True)
    with ThreadPoolExecutor(a.jobs) as pool:
        outs = list(pool.map(lambda s: build(s, a.work, a.policies), a.seeds))
    reports = [json.loads((a.work / f"seed_{s}.bands.json").read_text()) for s in a.seeds]
    n = len(reports)

    keys = list(dict.fromkeys(b["key"] for r in reports for b in r["bands"]))
    rows = []
    for k in keys:
        found = [b for r in reports for b in r["bands"] if b["key"] == k]
        v = np.array([b["value"] for b in found])
        pct = found[0]["percent"]
        rows.append([k, fmt(v.mean(), pct), f"{fmt(v.min(), pct)} to {fmt(v.max(), pct)}",
                     f"{fmt(found[0]['low'], pct)} to {fmt(found[0]['high'], pct)}", f"{sum(b['ok'] for b in found)} of {len(found)}"])
    print(f"Validator bands across {n} seeds ({', '.join(map(str, a.seeds))}); "
          f"{sum(r['failures'] for r in reports)} integrity failures in all\n")
    print(table(["figure", "mean", "range", "band", "seeds inside"], rows, a.markdown))

    diag = [diagnostics(o) for o in outs]
    rows = []
    for k, (published, what) in DIAGNOSTICS.items():
        v = np.array([d[k] for d in diag])
        rows.append([k, fmt(v.mean(), k in PERCENT), f"{fmt(v.min(), k in PERCENT)} to {fmt(v.max(), k in PERCENT)}", published, what])
    print(f"\nTail and joint diagnostics across {n} seeds\n")
    print(table(["figure", "mean", "range", "published", "source"], rows, a.markdown))


if __name__ == "__main__":
    main()
