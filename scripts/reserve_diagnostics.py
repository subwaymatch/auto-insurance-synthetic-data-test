#!/usr/bin/env python3
"""How well the case reserves predicted what was later paid, by coverage and by the feature's age.

    python scripts/reserve_diagnostics.py OUT [OUT ...]        # one or more generated datasets (say, several seeds)
    python scripts/reserve_diagnostics.py OUT ... --markdown   # the tables as Markdown
    python scripts/reserve_diagnostics.py OUT ... --min 10     # leave out cells with fewer than 10 features (reviews)

Each year-end from the day before the extract starts to the year before the valuation date is an evaluation date.
Every loss feature with a case reserve open on that date is followed to its ultimate paid loss
(answer_key/claim_feature_truth.csv, which includes payments after the valuation date). By coverage and by the
feature's age on the evaluation date (days since it was opened) the script reports:

* runoff: what was later paid over the case reserve held, summed over the features (above 1, the reserves were
  short; below 1, redundant);
* the spread of single features: the 10th, 50th and 90th percentiles of later paid over case reserve, and the share
  whose later payments fell between half and double their reserve;
* revisions: of the reserve reviews made at that age, the share that raised the reserve and the share that lowered it.

The reserves in the data are set from what the adjuster knows on each day (claims._reserve_history): this is the
check that they behave like case reserves (short early on injury claims, revised in both directions, closer to the
outcome as a claim matures) rather than knowing the answer. With several datasets each figure is the mean, with the
lowest and highest in brackets.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd

AGES = [(0, 90, "0-3 months"), (91, 365, "3-12 months"), (366, 730, "1-2 years"), (731, 10 ** 6, "over 2 years")]
COVERAGES = ["BI", "PD", "UM", "MED", "COLL", "COMP", "RENT", "TOW"]


def age_band(days: np.ndarray) -> np.ndarray:
    out = np.full(len(days), "", dtype=object)
    for lo, hi, name in AGES:
        out[(days >= lo) & (days <= hi)] = name
    return out


def diagnose(out: Path) -> tuple[pd.DataFrame, pd.DataFrame]:
    """(runoff by coverage and age, revisions by coverage and age) for one dataset."""
    read = lambda name: pd.read_csv(out / f"{name}.csv")
    run = json.loads((out / "run_summary.json").read_text())
    start, valuation = pd.Timestamp(run["start"]), pd.Timestamp(run["valuation"])
    feat = read("claim_feature")[["claim_feature_id", "coverage_code", "open_date"]] \
        .merge(pd.read_csv(out / "answer_key" / "claim_feature_truth.csv")[["claim_feature_id", "ultimate_paid_loss"]])
    feat["open_date"] = pd.to_datetime(feat["open_date"])
    res = read("claim_reserve_transaction")
    res = res[res["reserve_type"] == "Loss"].assign(transaction_date=lambda d: pd.to_datetime(d["transaction_date"]))
    res = res.sort_values(["claim_feature_id", "transaction_date", "reserve_transaction_id"], kind="stable")
    pay = read("claim_payment")
    pay = pay[pay["payment_type"] == "Loss"].assign(payment_date=lambda d: pd.to_datetime(d["payment_date"]))

    rows = []
    for E in pd.date_range(start - pd.Timedelta(days=1), valuation - pd.DateOffset(years=1), freq="YE"):
        case = res[res["transaction_date"] <= E].groupby("claim_feature_id")["outstanding_reserve"].last()
        case = case[case > 0]
        paid = pay[pay["payment_date"] <= E].groupby("claim_feature_id")["amount"].sum()
        f = feat[feat["claim_feature_id"].isin(case.index)].copy()
        f["case"] = case.reindex(f["claim_feature_id"]).to_numpy()
        f["later"] = f["ultimate_paid_loss"] - paid.reindex(f["claim_feature_id"]).fillna(0).to_numpy()
        f["age"] = age_band((E - f["open_date"]).dt.days.to_numpy())
        rows.append(f)
    f = pd.concat(rows, ignore_index=True)
    f["ratio"] = f["later"] / f["case"]
    g = f.groupby(["coverage_code", "age"])
    runoff = pd.DataFrame({
        "features": g.size(),
        "runoff": g["later"].sum() / g["case"].sum(),
        "p10": g["ratio"].quantile(0.10), "p50": g["ratio"].median(), "p90": g["ratio"].quantile(0.90),
        "within_2x": g["ratio"].apply(lambda r: ((r >= 0.5) & (r <= 2.0)).mean())})
    total = f.groupby("coverage_code")
    runoff = pd.concat([runoff, pd.DataFrame({
        "features": total.size(), "runoff": total["later"].sum() / total["case"].sum(),
        "p10": total["ratio"].quantile(0.10), "p50": total["ratio"].median(), "p90": total["ratio"].quantile(0.90),
        "within_2x": total["ratio"].apply(lambda r: ((r >= 0.5) & (r <= 2.0)).mean())})
        .assign(age="all ages").set_index("age", append=True)])

    rev = res[res["transaction_type"] == "Reserve Review"].merge(feat[["claim_feature_id", "coverage_code", "open_date"]])
    rev["age"] = age_band((rev["transaction_date"] - rev["open_date"]).dt.days.to_numpy())
    g = rev.groupby(["coverage_code", "age"])["change_amount"]
    revisions = pd.DataFrame({"reviews": g.size(), "up": g.apply(lambda x: (x > 0).mean()),
                              "down": g.apply(lambda x: (x < 0).mean())})
    return runoff, revisions


def combine(frames: list[pd.DataFrame]) -> pd.DataFrame:
    """Mean, lowest and highest of each figure across datasets."""
    stacked = pd.concat(frames, keys=range(len(frames)))
    g = stacked.groupby(level=[1, 2])
    return pd.concat({"mean": g.mean(), "low": g.min(), "high": g.max()}, axis=1)


def order(df: pd.DataFrame) -> pd.DataFrame:
    ages = [a for *_, a in AGES] + ["all ages"]
    key = [(c, a) for c in COVERAGES for a in ages if (c, a) in df.index]
    return df.loc[key]


def show(df: pd.DataFrame, cols: dict, markdown: bool, n: int, least: int = 0) -> str:
    """cols: column -> (heading, format); the first is the count that `least` applies to."""
    head = ["coverage", "age"] + [h for h, _ in cols.values()]
    lines = []
    count = next(iter(cols))
    for (cov, age), r in order(df).iterrows():
        if r[("mean", count)] < least:
            continue
        cells = [cov, age]
        for c, (_, fmt) in cols.items():
            if n > 1 and c not in ("features", "reviews"):
                cells.append(f"{fmt.format(r[('mean', c)])} ({fmt.format(r[('low', c)])}-{fmt.format(r[('high', c)])})")
            else:
                cells.append(fmt.format(r[("mean", c)]))
        lines.append(cells)
    if markdown:
        out = ["| " + " | ".join(head) + " |", "|" + "|".join(["---"] * 2 + ["--:"] * len(cols)) + "|"]
        return "\n".join(out + ["| " + " | ".join(c) + " |" for c in lines])
    w = [max(len(str(x)) for x in col) for col in zip(head, *lines)]
    return "\n".join("  ".join(str(x).ljust(k) for x, k in zip(row, w)) for row in [head] + lines)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("out", type=Path, nargs="+")
    ap.add_argument("--markdown", action="store_true")
    ap.add_argument("--min", type=int, default=0, help="leave out cells with fewer features (reviews) than this")
    a = ap.parse_args()
    results = [diagnose(o) for o in a.out]
    runoff = combine([r for r, _ in results])
    revisions = combine([v for _, v in results])
    runoff[("mean", "features")] = runoff[("mean", "features")].round()
    revisions[("mean", "reviews")] = revisions[("mean", "reviews")].round()
    print(f"Case reserves against later payments ({len(a.out)} dataset{'s' if len(a.out) > 1 else ''}; features per "
          "dataset, summed over the evaluation dates)\n")
    print(show(runoff, {"features": ("features", "{:,.0f}"), "runoff": ("later paid / reserve", "{:.2f}"),
                        "p10": ("10th pct", "{:.2f}"), "p50": ("median", "{:.2f}"), "p90": ("90th pct", "{:.2f}"),
                        "within_2x": ("within 2x", "{:.0%}")}, a.markdown, len(a.out), a.min))
    print("\nReserve reviews: share raising and lowering the reserve\n")
    print(show(revisions, {"reviews": ("reviews", "{:,.0f}"), "up": ("up", "{:.0%}"), "down": ("down", "{:.0%}")},
               a.markdown, len(a.out), a.min))


if __name__ == "__main__":
    main()
