#!/usr/bin/env python3
"""Compare the synthetic book with a real motor insurance portfolio.

    python scripts/compare_real_data.py --synthetic output --real real_data/mendeley_motor_portfolio

The real data is "Dataset of an actual motor vehicle insurance portfolio" (Lledó and Pavía, Mendeley Data,
2024, CC BY 4.0): one row per vehicle contract per annual period, November 2015 to December 2018, from a
non-life insurer that is almost certainly Spanish. See real_data/mendeley_motor_portfolio/README.md.

The two books differ in country, currency, coverages and grain, so the report compares shapes and
relationships rather than levels: claim-count distributions, severity and premium dispersion, how
frequency moves with driver, vehicle and policy characteristics, how much signal the premium and a simple
model carry, retention, and data quality. It prints numbered sections that docs/real_data_comparison.md
quotes. Only numpy and pandas are needed; the frequency model is a Poisson GLM fitted here by IRLS.

How each book is put on the same footing:

* Real: passenger cars only (Type_risk 3). A row whose lapse date is on or before its own start is a
  contract that was not renewed (or a bad date) and has no exposure; it is dropped. Exposure runs from the
  renewal date to the earliest of the next renewal, the lapse date and 31 December 2018, the end of the
  observation window (claim counts fall away for annual periods that start in 2018, consistent with claims
  being observed to about then). Most comparisons use periods starting before 2018 ("mature" rows).
* Synthetic: the exposure table rolled up to one row per policy term and vehicle (the same grain as a real row,
  except that many synthetic terms last six months), with the exposure and premium earned inside the
  extract. A claim counts if it has a cost (net incurred loss above zero), as in the real data, where every
  counted claim has a cost. "Urban" is the City of Chicago (29% of policies; the real "urban" flag, towns
  of more than 30,000 people judged on traffic conditions, covers 27% of rows).
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd

REAL_FILE = "motor_vehicle_insurance_data.csv"
REAL_TYPES_FILE = "sample_type_claim.csv"
REAL_OBS_END = pd.Timestamp("2018-12-31")      # inferred end of the real claim observation window
REAL_MATURE_END = pd.Timestamp("2017-12-31")   # periods starting after this are not fully observed
SEED = 20240730

# Every synthetic table, column and value this script reads, in one place. Keys on the left are the names used
# below; the strings on the right are the file (without .csv, relative to the generate.py output folder) and
# column names in the published tables.
SYN_SUMMARY = "run_summary.json"                  # keys used: seed, policies, start, valuation
SYN_TABLES = {
    "exposure": ("exposure", {
        "record_id": "exposure_id", "term_id": "policy_term_id", "policy_id": "policy_id",
        "endorsement": "endorsement_number", "vehicle_id": "insured_vehicle_id", "model_year": "model_year",
        "driver_id": "driver_id", "location_id": "location_id", "tenure_years": "tenure_years",
        "vehicle_value": "vehicle_value", "violation_points": "rated_violation_points",
        "at_fault_accidents": "rated_at_fault_accidents", "cover_start": "coverage_start_date",
        "cover_end": "coverage_end_date", "earned_exposure": "earned_exposure", "earned_premium": "earned_premium"}),
    "term": ("policy_term", {
        "term_id": "policy_term_id", "effective": "effective_date", "expiration": "expiration_date",
        "cancel_date": "cancel_date", "non_renewal_reason": "nonrenewal_reason"}),
    "policy": ("policy", {
        "policy_id": "policy_id", "distribution_channel": "distribution_channel", "payment_plan": "payment_plan",
        "term_months": "term_months", "insurance_score": "insurance_score"}),
    "location": ("location", {
        "location_id": "location_id", "region": "region", "liability_territory": "liability_territory"}),
    "driver": ("driver", {
        "driver_id": "driver_id", "policy_id": "policy_id", "birth_date": "date_of_birth",
        "licensed_date": "date_first_licensed", "added_date": "added_date", "removed_date": "removed_date"}),
    "claim": ("claim", {
        "claim_id": "claim_id", "term_id": "policy_term_id", "vehicle_id": "insured_vehicle_id",
        "claim_amount": "net_incurred_loss"}),
    "feature": ("claim_feature", {
        "claim_id": "claim_id", "coverage_code": "coverage_code", "coverage": "coverage", "net_incurred": "net_incurred_loss"}),
    "exposure_truth": ("answer_key/exposure_truth", {"record_id": "exposure_id", "expected_loss": "expected_loss_total"}),
}
SYN_VALUES = {
    "urban_region": "City of Chicago",
    "paid_in_full": "Paid in Full",
    "channel": {"Exclusive Agent": "Agent", "Independent Agent": "Broker", "Direct": "Direct"},
    "liability_codes": ["BI", "PD"],
}

INF = np.inf
AGE = ([-INF, 25, 35, 45, 55, 65, INF], ["<25", "25-34", "35-44", "45-54", "55-64", "65+"])
LIC = ([-INF, 5, 10, 20, 30, INF], ["0-4", "5-9", "10-19", "20-29", "30+"])      # a few real licences post-date the period
VAGE = ([-INF, 3, 6, 10, 15, INF], ["0-2", "3-5", "6-9", "10-14", "15+"])
TEN = ([-INF, 2, 5, 10, INF], ["0-1", "2-4", "5-9", "10+"])
FACTORS = ["age_band", "lic_band", "vage_band", "value_band", "urban", "multi_driver", "instalments",
           "channel", "tenure_band"]
US_FACTORS = ["score_band", "points_band", "accidents_band", "territory"]
FACTOR_NAMES = {"age_band": "Driver age", "lic_band": "Years licensed", "vage_band": "Vehicle age",
                "value_band": "Vehicle value (quintile within book)", "urban": "Urban",
                "multi_driver": "More than one driver", "instalments": "Pays in instalments",
                "channel": "channel", "tenure_band": "Years with the company"}


# ------------------------------------------------------------------------------------------------ loading
def years_between(a: pd.Series, b: pd.Series) -> pd.Series:
    return (b - a).dt.days / 365.25


def bands(df: pd.DataFrame) -> pd.DataFrame:
    cut = lambda x, spec: pd.cut(x, spec[0], labels=spec[1], right=False).astype(str)
    df["age_band"] = cut(df.age, AGE)
    df["lic_band"] = cut(df.lic_years, LIC)
    df["vage_band"] = cut(df.veh_age, VAGE)
    df["tenure_band"] = cut(df.tenure, TEN)
    q = weighted_quantile(df.veh_value.to_numpy(), df.expo.to_numpy(), [0.2, 0.4, 0.6, 0.8])
    df["value_band"] = np.array(["Q1 low", "Q2", "Q3", "Q4", "Q5 high"])[np.searchsorted(q, df.veh_value, side="right")]
    for c in ["urban", "multi_driver", "instalments"]:
        df[c] = np.where(df[c], "Y", "N")
    return df


def load_real(folder: Path) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Returns (all rows with derived fields, passenger-car analysis rows, claim types)."""
    raw = pd.read_csv(folder / REAL_FILE, sep=";", keep_default_na=False, na_values=[""])
    d = raw.copy()
    for c in ["Date_start_contract", "Date_last_renewal", "Date_next_renewal", "Date_birth", "Date_driving_licence", "Date_lapse"]:
        d[c] = pd.to_datetime(d[c], format="%d/%m/%Y")
    d["period_days"] = (d.Date_next_renewal - d.Date_last_renewal).dt.days
    d["lapse_rel"] = (d.Date_lapse - d.Date_last_renewal).dt.days
    d["stub"] = d.lapse_rel <= 0                              # not renewed (lapse on the start date) or lapse before it
    stop = d.Date_next_renewal.where(d.Date_lapse.isna() | (d.Date_lapse > d.Date_next_renewal), d.Date_lapse)
    stop = stop.clip(upper=REAL_OBS_END)
    d["expo"] = np.where(d.stub, 0.0, ((stop - d.Date_last_renewal).dt.days.clip(lower=0) / 365.25).to_numpy())
    d["terminated"] = ~d.stub & d.lapse_rel.between(1, d.period_days)
    d["year"] = d.Date_last_renewal.dt.year
    d["pid"] = d.ID
    d["claims"] = d.N_claims_year
    d["cost"] = d.Cost_claims_year
    d["premium"] = d.Premium
    d["earned"] = d.Premium * d.expo
    d["age"] = years_between(d.Date_birth, d.Date_last_renewal)
    d["lic_years"] = years_between(d.Date_driving_licence, d.Date_last_renewal)
    d["veh_age"] = d.year - d.Year_matriculation
    d["veh_value"] = d.Value_vehicle
    d["urban"] = d.Area == 1
    d["multi_driver"] = d.Second_driver == 1
    d["instalments"] = d.Payment == 1
    d["channel"] = np.where(d.Distribution_channel == 1, "Broker", "Agent")
    d["tenure"] = d.Seniority
    cars = d[(d.Type_risk == 3) & ~d.stub & (d.expo > 0)].copy()
    cars = bands(cars)
    types = pd.read_csv(folder / REAL_TYPES_FILE, sep=";")
    return d, cars, types


def load_synthetic(folder: Path) -> tuple[pd.DataFrame, dict]:
    """One row per policy term and insured vehicle, with exposure, premium and claims inside the extract."""
    def read(table: str) -> pd.DataFrame:
        file, cols = SYN_TABLES[table]
        df = pd.read_csv(folder / f"{file}.csv", usecols=list(cols.values()), keep_default_na=False, na_values=[""], low_memory=False)
        return df.rename(columns={v: k for k, v in cols.items()})

    summary = json.loads((folder / SYN_SUMMARY).read_text())
    rf = read("exposure").sort_values(["term_id", "vehicle_id", "endorsement"], kind="stable")
    key = ["term_id", "vehicle_id"]
    g = rf.groupby(key, sort=False)
    s = g[["policy_id", "model_year", "driver_id", "location_id", "tenure_years", "vehicle_value", "violation_points",
           "at_fault_accidents"]].first()
    s["expo"] = g.earned_exposure.sum()
    s["earned"] = g.earned_premium.sum()
    s = s.reset_index()
    s = s[s.expo > 0].copy()

    terms = read("term")
    for c in ["effective", "expiration", "cancel_date"]:
        terms[c] = pd.to_datetime(terms[c])
    pol = read("policy")
    loc = read("location")
    drv = read("driver")
    for c in ["birth_date", "licensed_date", "added_date", "removed_date"]:
        drv[c] = pd.to_datetime(drv[c])

    # drivers on the policy when the term started
    t = terms[["term_id", "effective"]].merge(s[["term_id", "policy_id"]].drop_duplicates(), on="term_id")
    td = t.merge(drv[["policy_id", "added_date", "removed_date"]], on="policy_id")
    on = (td.added_date <= td.effective) & (td.removed_date.isna() | (td.removed_date > td.effective))
    n_drivers = on.groupby(td.term_id).sum()

    s = s.merge(terms, on="term_id").merge(pol, on="policy_id").merge(loc, on="location_id") \
        .merge(drv[["driver_id", "birth_date", "licensed_date"]], on="driver_id")
    eff = s.effective
    s["pid"] = s.policy_id
    s["year"] = eff.dt.year
    s["premium"] = s.earned / s.expo                       # annual rate
    s["age"] = years_between(s.birth_date, eff)
    s["lic_years"] = years_between(s.licensed_date, eff)
    s["veh_age"] = s.year - s.model_year
    s["veh_value"] = s.vehicle_value
    s["urban"] = s.region == SYN_VALUES["urban_region"]
    s["multi_driver"] = s.term_id.map(n_drivers).fillna(0).to_numpy() > 1
    s["instalments"] = s.payment_plan != SYN_VALUES["paid_in_full"]
    s["channel"] = s.distribution_channel.map(SYN_VALUES["channel"])
    s["tenure"] = s.tenure_years
    # US rating fields the real data has no counterpart for, used in a second synthetic model
    s["score_band"] = pd.cut(s.insurance_score, [-INF, 600, 700, 800, INF], labels=["<600", "600-699", "700-799", "800+"],
                             right=False).astype(str).replace("nan", "no score")
    s["points_band"] = pd.cut(s.violation_points, [-INF, 1, 3, INF], labels=["0", "1-2", "3+"], right=False).astype(str)
    s["accidents_band"] = np.minimum(s.at_fault_accidents, 2).astype(int).astype(str)
    s["territory"] = s.liability_territory

    cl = read("claim")
    cl["has_cost"] = cl.claim_amount > 0
    features = read("feature")
    paid_liab = features.loc[features.coverage_code.isin(SYN_VALUES["liability_codes"]) & (features.net_incurred > 0), "claim_id"].unique()
    cl["liability"] = cl.claim_id.isin(paid_liab)            # a bodily injury or property damage liability cost
    agg = cl.groupby(key).agg(claims=("has_cost", "sum"), claims_all=("claim_id", "size"), cost=("claim_amount", "sum"),
                              liab_claims=("liability", "sum"))
    s = s.merge(agg, left_on=key, right_index=True, how="left")
    s[["claims", "claims_all", "cost", "liab_claims"]] = s[["claims", "claims_all", "cost", "liab_claims"]].fillna(0)
    s["claims"] = s.claims.astype(int)

    if (folder / f"{SYN_TABLES['exposure_truth'][0]}.csv").exists():   # expected loss per car-year, from the answer key
        # the answer key's expected loss already covers each row's earned window (the part inside the extract,
        # up to any cancellation), the same window as earned_exposure, so it is summed as it is
        rt = read("exposure_truth").merge(rf[["record_id", "term_id", "vehicle_id"]], on="record_id")
        s = s.merge(rt.groupby(key).expected_loss.sum().rename("true_el"), left_on=key, right_index=True, how="left")
        s["true_el"] = s.true_el / s.expo
    s = bands(s)
    extra = {"summary": summary, "terms": terms, "claims": cl, "features": features, "drivers": drv, "risk_rows": len(rf)}
    return s, extra


# ------------------------------------------------------------------------------------------------ helpers
def weighted_quantile(x: np.ndarray, w: np.ndarray, q) -> np.ndarray:
    o = np.argsort(x, kind="stable")
    cw = np.cumsum(w[o])
    return np.interp(np.asarray(q) * cw[-1], cw, x[o])


def gini(score: np.ndarray, expo: np.ndarray, loss: np.ndarray) -> float:
    """Ordered-Lorenz Gini: rows sorted from lowest to highest score; cumulative share of exposure against
    cumulative share of losses. 0 means the score does not rank risk at all; ties are treated as one block."""
    df = pd.DataFrame({"s": score, "e": expo, "l": loss}).groupby("s", sort=True)[["e", "l"]].sum()
    x = np.concatenate([[0], np.cumsum(df.e.to_numpy()) / df.e.sum()])
    y = np.concatenate([[0], np.cumsum(df.l.to_numpy()) / df.l.sum()])
    return float(1 - 2 * np.trapezoid(y, x))


def decile_lift(score: np.ndarray, expo: np.ndarray, claims: np.ndarray) -> float:
    """Claim frequency in the riskiest tenth of exposure divided by that in the safest tenth."""
    o = np.argsort(score, kind="stable")
    ce = np.cumsum(expo[o]) / expo.sum()
    lo, hi = o[ce <= 0.1], o[ce > 0.9]
    return float((claims[hi].sum() / expo[hi].sum()) / (claims[lo].sum() / expo[lo].sum()))


def design(df: pd.DataFrame, cols: list[str], levels: dict | None = None) -> tuple[np.ndarray, list[str], dict]:
    levels = levels or {c: sorted(df[c].astype(str).unique(), key=_level_key) for c in cols}
    mats, names = [np.ones((len(df), 1))], ["intercept"]
    for c in cols:
        v = df[c].astype(str).to_numpy()
        for lev in levels[c][1:]:
            mats.append((v == lev).astype(float)[:, None])
            names.append(f"{c}={lev}")
    return np.hstack(mats), names, levels


def poisson_glm(X: np.ndarray, y: np.ndarray, offset: np.ndarray, iters: int = 50) -> np.ndarray:
    """Poisson regression with a log link, fitted by iteratively reweighted least squares."""
    beta = np.zeros(X.shape[1])
    beta[0] = np.log(y.sum() / np.exp(offset).sum())
    for _ in range(iters):
        eta = X @ beta + offset
        mu = np.exp(eta)
        z = eta - offset + (y - mu) / mu
        XtW = X.T * mu
        new = np.linalg.solve(XtW @ X + 1e-8 * np.eye(X.shape[1]), XtW @ z)
        if np.max(np.abs(new - beta)) < 1e-9:
            return new
        beta = new
    return beta


def glm_holdout(df: pd.DataFrame, factors: list[str]) -> tuple[float, float, float, dict]:
    """Fit a Poisson frequency GLM on 70% of policies and rank the other 30% with it (period year excluded)."""
    rng = np.random.default_rng(SEED)
    ids = df.pid.unique()
    tr = df.pid.isin(set(ids[rng.random(len(ids)) < 0.7])).to_numpy()
    df = df.assign(year_f=df.year.astype(str))
    X, names, _ = design(df, factors + ["year_f"])
    beta = poisson_glm(X[tr], df.claims.to_numpy()[tr].astype(float), np.log(df.expo.to_numpy()[tr]))
    risk = np.array([not n.startswith("year_f=") for n in names])
    score = X[~tr][:, risk] @ beta[risk]
    e, y, c = df.expo.to_numpy()[~tr], df.claims.to_numpy()[~tr], df.cost.to_numpy()[~tr]
    return gini(score, e, y), gini(score, e, c), decile_lift(score, e, y), dict(zip(names, beta))


def fmt_pct(x: float, d: int = 1) -> str:
    return "n/a" if x is None or not np.isfinite(x) else f"{100 * x:.{d}f}%"


def table(rows: list[list], header: list[str]) -> str:
    cells = [header] + [[str(c) for c in r] for r in rows]
    w = [max(len(r[i]) for r in cells) for i in range(len(header))]
    line = lambda r: "  " + "  ".join(c.ljust(w[i]) if i == 0 else c.rjust(w[i]) for i, c in enumerate(r))
    return "\n".join([line(cells[0]), "  " + "  ".join("-" * x for x in w)] + [line(r) for r in cells[1:]])


def section(n: int, title: str) -> None:
    print(f"\n[{n}] {title}\n" + "=" * (len(title) + 4 + len(str(n))))


# ------------------------------------------------------------------------------------------------ report
def report(real_all: pd.DataFrame, real: pd.DataFrame, types: pd.DataFrame, syn: pd.DataFrame, extra: dict) -> None:
    summ = extra["summary"]
    start, valuation = pd.Timestamp(summ["start"]), pd.Timestamp(summ["valuation"])
    mature = real[real.Date_last_renewal <= REAL_MATURE_END]

    # [1] grain ------------------------------------------------------------------------------------------
    section(1, "Size and grain")
    per_id = real_all.groupby("ID").size()
    print(f"Real: {len(real_all):,} rows, {real_all.ID.nunique():,} contracts (rows per contract: "
          + ", ".join(f"{k}: {v:,}" for k, v in per_id.value_counts().sort_index().items()) + ")")
    print(f"  risk type mix: " + ", ".join(f"{n} {fmt_pct((real_all.Type_risk == k).mean())}" for k, n in
                                          [(3, "passenger car"), (2, "van"), (1, "motorbike"), (4, "agricultural")]))
    print(f"  {real_all.stub.sum():,} rows ({fmt_pct(real_all.stub.mean())}) have a lapse date on or before their own start "
          f"(not renewed); they carry no exposure")
    print(f"  analysis rows (passenger cars with exposure): {len(real):,}, {real.expo.sum():,.0f} vehicle-years; "
          f"periods starting by {REAL_MATURE_END.date()}: {len(mature):,} rows, {mature.expo.sum():,.0f} vehicle-years")
    print(f"Synthetic: {extra['risk_rows']:,} risk rows rolled up to {len(syn):,} vehicle-terms, {syn.pid.nunique():,} policies, "
          f"{syn.vehicle_id.nunique():,} vehicles, {syn.expo.sum():,.0f} vehicle-years ({summ['start']} to {summ['valuation']})")
    print(f"  term length: " + ", ".join(f"{m} months {fmt_pct(v)}" for m, v in
                                         syn.groupby("term_months").expo.sum().div(syn.expo.sum()).items()) + " of exposure")

    # [2] mix --------------------------------------------------------------------------------------------
    section(2, "Portfolio mix (exposure-weighted; real = mature passenger-car rows)")
    def mix(df):
        w = df.expo.to_numpy()
        wm = lambda x: float(np.average(x, weights=w))
        return [f"{wm(df.age):.1f}", fmt_pct(wm(df.age < 25)), fmt_pct(wm(df.age >= 65)),
                f"{weighted_quantile(df.lic_years.to_numpy(), w, 0.5):.1f}", f"{wm(df.veh_age):.1f}",
                fmt_pct(wm(df.veh_age >= 10)), fmt_pct(wm(df.multi_driver == "Y")), fmt_pct(wm(df.instalments == "Y")),
                fmt_pct(wm(df.urban == "Y")), f"{weighted_quantile(df.tenure.to_numpy().astype(float), w, 0.5):.1f}"]
    hdr = ["Book", "Mean age", "Under 25", "65+", "Median yrs licensed", "Mean veh age", "Veh 10+ yrs", "2+ drivers",
           "Instalments", "Urban", "Median tenure"]
    print(table([["Real"] + mix(mature), ["Synthetic"] + mix(syn)], hdr))
    print("  Real age and licence are the policyholder's; synthetic are the vehicle's rated driver. Real 'second driver'"
          " means another regular driver was declared; synthetic counts every listed household driver.")

    # [3] frequency --------------------------------------------------------------------------------------
    section(3, "Claim frequency and claim counts")
    rows = []
    for y, g in real.groupby("year"):
        rows.append(["Real", y, f"{g.expo.sum():,.0f}", f"{g.claims.sum():,}", f"{g.claims.sum() / g.expo.sum():.3f}"])
    for y, g in syn.groupby("year"):
        rows.append(["Synthetic", y, f"{g.expo.sum():,.0f}", f"{g.claims.sum():,}", f"{g.claims.sum() / g.expo.sum():.3f}"])
    print(table(rows, ["Book", "Period start year", "Vehicle-years", "Claims", "Claims per vehicle-year"]))
    print(f"  Synthetic, counting every reported claim including those closed without payment: "
          f"{syn.claims_all.sum() / syn.expo.sum():.3f} per vehicle-year.")
    print("  Real 2018 periods are cut off by the end of observation; the real level also halves between 2016 and 2017"
          " periods for no reason the data documents.")

    full_r = mature[mature.expo >= 0.99]
    full_s = syn[(syn.term_months == 12) & (syn.expo >= 0.99)]
    rows = []
    for name, df in [("Real", full_r), ("Synthetic (12-month terms)", full_s)]:
        c = df.claims.to_numpy()
        m, v = c.mean(), c.var()
        rows.append([name, f"{len(df):,}", fmt_pct((c == 0).mean()), fmt_pct((c == 1).mean()), fmt_pct((c == 2).mean()),
                     fmt_pct((c >= 3).mean()), f"{m:.3f}", f"{v / m:.2f}", f"{(v - m) / m ** 2:.2f}",
                     f"{(c >= 2).sum() / max((c >= 1).sum(), 1):.2f}", f"{m / 2:.2f}"])
    print("\n  Claim counts on full-year rows (one vehicle, one whole annual period):")
    print(table(rows, ["Book", "Rows", "0 claims", "1", "2", "3+", "Mean", "Variance/mean", "Risk spread",
                       "P(2+ | 1+)", "Same if Poisson"]))
    print("  Risk spread = (variance - mean) / mean^2, the squared coefficient of variation of the underlying claim rate")
    print("  across vehicles; it does not depend on the frequency level. 0 means every vehicle has the same risk (Poisson).")
    print("  'Same if Poisson' is roughly what P(2+ | 1+) would be with no differences in risk.")

    # persistence: does a claim in one year predict claims in the next?
    r = real_all[(real_all.Type_risk == 3) & ~real_all.stub & (real_all.expo > 0)].sort_values(["ID", "Date_last_renewal"])
    nxt = r.groupby("ID")[["claims", "expo", "Date_last_renewal"]].shift(-1)
    pr = r.assign(n_claims=nxt.claims, n_expo=nxt.expo)[(r.expo >= 0.99) & nxt.expo.gt(0)
                                                         & (nxt.Date_last_renewal <= REAL_MATURE_END)]
    sv = syn.groupby(["vehicle_id", "year"]).agg(claims=("claims", "sum"), expo=("expo", "sum")).reset_index()
    sv_next = sv.assign(year=sv.year - 1).rename(columns={"claims": "n_claims", "expo": "n_expo"})
    ps = sv.merge(sv_next, on=["vehicle_id", "year"])
    ps = ps[(ps.expo >= 0.9) & (ps.n_expo > 0) & (ps.year >= start.year)]
    rows = []
    for name, df in [("Real (consecutive annual periods)", pr), ("Synthetic (consecutive calendar years)", ps)]:
        hit = df.claims > 0
        f1 = df.n_claims[hit].sum() / df.n_expo[hit].sum()
        f0 = df.n_claims[~hit].sum() / df.n_expo[~hit].sum()
        rows.append([name, f"{len(df):,}", f"{f1:.3f}", f"{f0:.3f}", f"{f1 / f0:.2f}"])
    print("\n  Claim persistence: next year's frequency for vehicles with and without a claim this year:")
    print(table(rows, ["Book", "Pairs", "After a claim", "After none", "Ratio"]))
    print("  The real counts are not independent from one period to the next (section 10), which inflates the real risk")
    print("  spread, P(2+ | 1+) and persistence; treat those three real figures as artefacts, not benchmarks.")

    # [4] severity ---------------------------------------------------------------------------------------
    section(4, "Severity shape (annual claim cost of vehicle-years with a claim; levels are not comparable)")
    def shape(cost: np.ndarray) -> list[str]:
        cost = np.sort(cost)
        p50, p90, p99 = np.quantile(cost, [0.5, 0.9, 0.99])
        top1 = cost[-max(1, int(round(0.01 * len(cost)))):].sum() / cost.sum()
        top10 = cost[-max(1, int(round(0.10 * len(cost)))):].sum() / cost.sum()
        return [f"{len(cost):,}", f"{cost.mean():,.0f}", f"{p50:,.0f}", f"{cost.std() / cost.mean():.2f}", f"{p90 / p50:.1f}",
                f"{p99 / p50:.1f}", fmt_pct(top1), fmt_pct(top10)]
    hdr = ["Book", "Rows", "Mean", "Median", "CV", "p90/p50", "p99/p50", "Top 1% share", "Top 10% share"]
    rows = [["Real (EUR)"] + shape(mature.cost[mature.claims > 0].to_numpy()),
            ["Synthetic (USD)"] + shape(syn.cost[syn.claims > 0].to_numpy())]
    c = extra["claims"]
    rows.append(["Synthetic, per claim"] + shape(c.loc[c.has_cost, "claim_amount"].to_numpy()))
    rows.append(["Real, per claim (row avg)"] + shape((mature.cost / mature.claims)[mature.claims > 0].to_numpy()))
    print(table(rows, hdr))
    print("  CV = standard deviation / mean. 'Top 1% share' = share of all cost from the costliest 1% of rows.")

    # [5] premium and loss ratio -------------------------------------------------------------------------
    section(5, "Premium dispersion and loss ratio")
    def prem(df):
        w, p = df.expo.to_numpy(), df.premium.to_numpy()
        q10, q50, q90, q99 = weighted_quantile(p, w, [0.1, 0.5, 0.9, 0.99])
        m = np.average(p, weights=w)
        sd = np.sqrt(np.average((p - m) ** 2, weights=w))
        return [f"{m:,.0f}", f"{q50:,.0f}", f"{sd / m:.2f}", f"{q90 / q10:.2f}", f"{q99 / q50:.2f}"]
    print(table([["Real (EUR, annual)"] + prem(mature), ["Synthetic (USD, annual rate)"] + prem(syn)],
                ["Book", "Mean", "Median", "CV", "p90/p10", "p99/p50"]))
    rows = []
    for name, df in [("Real", real), ("Synthetic", syn)]:
        for y, g in df.groupby("year"):
            rows.append([name, y, fmt_pct(g.cost.sum() / g.earned.sum())])
        sub = df if name == "Synthetic" else mature
        rows.append([name, "all" if name == "Synthetic" else "all mature", fmt_pct(sub.cost.sum() / sub.earned.sum())])
    print("\n  Loss ratio (claim cost / earned premium) by period start year:")
    print(table(rows, ["Book", "Year", "Loss ratio"]))
    print("  Real premium is 'net premium' and real cost is the year's claim cost as extracted; synthetic is net incurred"
          " loss (excluding expense) as of the valuation date over earned premium.")

    # [6] relativities -----------------------------------------------------------------------------------
    section(6, "Risk relationships: frequency and loss-cost relativities (1.00 = book average)")
    for f in FACTORS:
        out = {}
        for name, df in [("real", mature), ("syn", syn)]:
            base_f, base_c = df.claims.sum() / df.expo.sum(), df.cost.sum() / df.expo.sum()
            g = df.groupby(f).agg(expo=("expo", "sum"), claims=("claims", "sum"), cost=("cost", "sum"))
            out[name] = pd.DataFrame({"share": g.expo / g.expo.sum(), "freq": g.claims / g.expo / base_f,
                                      "lc": g.cost / g.expo / base_c, "n": g.claims})
        levs = sorted(set(out["real"].index) | set(out["syn"].index), key=_level_key)
        rows = []
        for lev in levs:
            r = []
            for name in ["real", "syn"]:
                t = out[name]
                r += ([fmt_pct(t.share[lev], 0), f"{t.freq[lev]:.2f}", f"{t.lc[lev]:.2f}", f"{int(t.n[lev]):,}"]
                      if lev in t.index else ["-", "-", "-", "-"])
            rows.append([lev] + r)
        print(f"\n  {FACTOR_NAMES[f]}")
        print(table(rows, ["Level", "Real expo", "Real freq", "Real cost", "Real claims",
                           "Syn expo", "Syn freq", "Syn cost", "Syn claims"]))
        if f == "vage_band":
            base = syn.liab_claims.sum() / syn.expo.sum()
            g = syn.groupby(f).agg(expo=("expo", "sum"), n=("liab_claims", "sum"))
            print("  Synthetic, liability claims only (bodily injury or property damage paid): "
                  + ", ".join(f"{k} {v.n / v.expo / base:.2f}" for k, v in g.sort_index(key=lambda i: i.map(_level_key)).iterrows()))

    # [7] signal strength --------------------------------------------------------------------------------
    section(7, "Signal strength: how well premium and a simple model rank risk")
    rows = []
    for name, df in [("Real", mature), ("Synthetic", syn)]:
        e = df.expo.to_numpy()
        rows.append([name, "premium", f"{gini(df.premium.to_numpy(), e, df.claims.to_numpy()):.3f}",
                     f"{gini(df.premium.to_numpy(), e, df.cost.to_numpy()):.3f}", f"{decile_lift(df.premium.to_numpy(), e, df.claims.to_numpy()):.2f}"])
    if "true_el" in syn:
        e = syn.expo.to_numpy()
        rows.append(["Synthetic", "true expected loss (answer key)", f"{gini(syn.true_el.to_numpy(), e, syn.claims.to_numpy()):.3f}",
                     f"{gini(syn.true_el.to_numpy(), e, syn.cost.to_numpy()):.3f}", f"{decile_lift(syn.true_el.to_numpy(), e, syn.claims.to_numpy()):.2f}"])
    coefs = {}
    one_year = mature[mature.year == 2017]          # one period per contract, so no claim can be counted twice
    for name, df, factors, label in [("Real", mature, FACTORS, "GLM, shared factors"),
                                     ("Real", one_year, FACTORS, "GLM, shared factors, 2017 periods only"),
                                     ("Synthetic", syn, FACTORS, "GLM, shared factors"),
                                     ("Synthetic", syn, FACTORS + US_FACTORS, "GLM, shared + US rating factors")]:
        g_claims, g_cost, lift, beta = glm_holdout(df, factors)
        rows.append([name, label, f"{g_claims:.3f}", f"{g_cost:.3f}", f"{lift:.2f}"])
        coefs.setdefault(name, beta)
    print(table(rows, ["Book", "Ranked by", "Gini (claims)", "Gini (cost)", "Top/bottom decile frequency"]))
    print("  Gini: 0 = no ranking power, higher = premium or model puts more of the claims on the risks it rates highest.")
    print("  Each GLM is a Poisson frequency model fitted on 70% of policies and scored on the other 30%. 'Shared factors' are")
    print("  the nine in section 6; the US rating factors are insurance score, violation points, at-fault accidents and")
    print("  liability territory, which the real data does not have. Period year is fitted but left out of the ranking.")
    print("\n  GLM frequency multipliers (exp(coefficient)) against each factor's first level:")
    allnames = [n for n in dict.fromkeys(list(coefs["Real"]) + list(coefs["Synthetic"])) if n != "intercept" and not n.startswith("year_f")]
    allnames.sort(key=lambda n: (FACTORS.index(n.split("=")[0]), _level_key(n.split("=")[1])))
    print(table([[n, f"{np.exp(coefs['Real'][n]):.2f}" if n in coefs["Real"] else "-",
                  f"{np.exp(coefs['Synthetic'][n]):.2f}" if n in coefs["Synthetic"] else "-"] for n in allnames],
                ["Term", "Real", "Synthetic"]))

    # [8] retention --------------------------------------------------------------------------------------
    section(8, "Retention")
    obs = real_all[(real_all.Type_risk == 3) & ~real_all.stub & (real_all.Date_next_renewal <= pd.Timestamp("2018-11-30"))]
    mid = obs.terminated & (obs.lapse_rel < obs.period_days)
    rows = [["Real (contract-years)", f"{len(obs):,}", fmt_pct(obs.terminated.mean()), fmt_pct(mid.mean()),
             fmt_pct((obs.terminated & ~mid).mean())]]
    terms = extra["terms"].merge(syn[["term_id", "term_months"]].drop_duplicates(), on="term_id")
    end = terms.cancel_date.fillna(terms.expiration)
    done = terms[(terms.effective >= start) & (end <= valuation)]
    t_cancel = done.cancel_date.notna()
    t_nonren = done.non_renewal_reason.notna() & ~t_cancel
    yrs = (done.cancel_date.fillna(done.expiration) - done.effective).dt.days / 365.25
    per_year = lambda k: k.sum() / yrs.sum()
    ann = lambda r: 1 - np.exp(-r)
    rows.append(["Synthetic (policies, annualised)", f"{len(done):,} terms", fmt_pct(ann(per_year(t_cancel | t_nonren))),
                 fmt_pct(ann(per_year(t_cancel))), fmt_pct(ann(per_year(t_nonren)))])
    print(table(rows, ["Book", "Basis", "Lost per year", "Mid-term cancellation", "Not renewed"]))
    print("  Synthetic rates are terminations per policy-year turned into an annual probability (six-month terms renew twice a year).")
    reasons = extra["terms"].non_renewal_reason.value_counts()
    print(f"  Synthetic non-renewals by reason (all terms): " + ", ".join(f"{k} {v:,}" for k, v in reasons.items())
          + f", total {reasons.sum():,}")

    with_claim = obs.claims > 0
    rows = [["Real", fmt_pct(obs.terminated[with_claim].mean()), fmt_pct(obs.terminated[~with_claim].mean())]]
    tc = syn.groupby("term_id").claims.sum()
    dc = done.assign(claim=done.term_id.map(tc).fillna(0) > 0, lost=(t_cancel | t_nonren).to_numpy(), yrs=yrs.to_numpy())
    r_c = dc[dc.claim].lost.sum() / dc[dc.claim].yrs.sum()
    r_n = dc[~dc.claim].lost.sum() / dc[~dc.claim].yrs.sum()
    rows.append(["Synthetic (annualised)", fmt_pct(ann(r_c)), fmt_pct(ann(r_n))])
    print("\n  Share of periods that end the contract, with and without a claim in the period:")
    print(table(rows, ["Book", "With a claim", "Without"]))

    r = real_all[real_all.Type_risk == 3].sort_values(["ID", "Date_last_renewal"])
    prev = r.groupby("ID").Premium.shift()
    chg = (r.Premium / prev - 1)
    ok = prev.notna() & ~r.groupby("ID").stub.shift(fill_value=False)
    bins = [-np.inf, -0.05, 0, 0.02, 0.05, 0.10, np.inf]
    labels = ["below -5%", "-5% to 0", "0 to +2%", "+2% to +5%", "+5% to +10%", "+10% or more"]
    b = pd.cut(chg[ok], bins, labels=labels, right=False)
    lr = r.stub[ok].groupby(b, observed=False).agg(["size", "mean"])
    print("\n  Real: renewal offers (premium change on the previous year) and the share not renewed:")
    print(table([[k, f"{int(v['size']):,}", fmt_pct(v['mean'])] for k, v in lr.iterrows()], ["Premium change", "Offers", "Not renewed"]))
    print("  Synthetic: the tables record only renewals that were accepted, so the offer behind a non-renewal is not visible.")

    # [9] claim mix --------------------------------------------------------------------------------------
    section(9, "What a claim is: claim types and coverages")
    t = types.groupby("Claims_type").Cost_claims_by_type.agg(["size", "sum"])
    t = t.assign(cnt=t["size"] / t["size"].sum(), cost=t["sum"] / t["sum"].sum()).sort_values("cost", ascending=False)
    print("  Real (sample_type_claim.csv, a sample of rows with claims; one line per claim type per row):")
    print(table([[k, f"{int(v['size']):,}", fmt_pct(v.cnt), fmt_pct(v.cost), f"{v['sum'] / v['size']:,.0f}"] for k, v in t.iterrows()],
                ["Type", "Lines", "Share of lines", "Share of cost", "Average"]))
    cc = extra["features"]
    cc = cc[cc.net_incurred > 0]
    t = cc.groupby("coverage").net_incurred.agg(["size", "sum"])
    t = t.assign(cnt=t["size"] / t["size"].sum(), cost=t["sum"] / t["sum"].sum()).sort_values("cost", ascending=False)
    print(f"\n  Synthetic ({SYN_TABLES['feature'][0]}, features with a cost):")
    print(table([[k, f"{int(v['size']):,}", fmt_pct(v.cnt), fmt_pct(v.cost), f"{v['sum'] / v['size']:,.0f}"] for k, v in t.iterrows()],
                ["coverage", "Features", "Share of features", "Share of cost", "Average"]))

    # [10] data quality ----------------------------------------------------------------------------------
    section(10, "Data quality: what an analyst has to clean")
    d = real_all
    multi = d[d.ID.duplicated(keep=False)]
    const = lambda c: fmt_pct((multi.groupby("ID")[c].nunique() == 1).mean())
    cum_all = d.groupby("ID").N_claims_year.transform("sum")
    ds = d.sort_values(["ID", "Date_last_renewal"])
    nxt = ds.groupby("ID").N_claims_year.shift(-1)
    pair = nxt.notna()
    this0 = pair & (ds.N_claims_year == 0)
    first = ds.groupby("ID").first()
    checks = [
        ("Rows that are a non-renewal stub (lapse date = period start)", f"{(d.lapse_rel == 0).sum():,}"),
        ("Rows with a lapse date before the period start", f"{(d.lapse_rel < 0).sum():,}"),
        ("Rows whose contract start is after the period start", f"{(d.Date_start_contract > d.Date_last_renewal).sum():,}"),
        ("Rows where the licence was issued after the period start", f"{(d.Date_driving_licence > d.Date_last_renewal).sum():,}"),
        ("Rows with the policyholder aged 95 or more", f"{(d.age >= 95).sum():,}"),
        ("'NA' text in Length", f"{(d.Length.astype(str) == 'NA').sum():,}"),
        ("'NA' text in Type_fuel", f"{(d.Type_fuel.astype(str) == 'NA').sum():,}"),
        ("Power recorded as 0 (of which Type_fuel is 'NA')",
         f"{(d.Power == 0).sum():,} ({((d.Power == 0) & (d.Type_fuel.astype(str) == 'NA')).sum():,})"),
        ("Passenger cars with 0 doors", f"{((d.Type_risk == 3) & (d.N_doors == 0)).sum():,}"),
        ("Lapse > 0 but no lapse date", f"{((d.Lapse > 0) & d.Date_lapse.isna()).sum():,}"),
        ("Multi-row contracts with the same N_claims_history on every row", const("N_claims_history")),
        ("... same Seniority on every row", const("Seniority")),
        ("... same Value_vehicle on every row (valued at 31/12/2019)", const("Value_vehicle")),
        ("Rows where N_claims_history >= all the contract's claims in the extract", fmt_pct((d.N_claims_history >= cum_all).mean())),
        ("Consecutive periods of a contract where N_claims_year does not rise", fmt_pct((nxt[pair] <= ds.N_claims_year[pair]).mean())),
        ("... share of periods with a claim", fmt_pct((ds.N_claims_year[pair] > 0).mean())),
        ("... share of claim-free periods followed by a period with a claim", fmt_pct((nxt[this0] > 0).mean())),
        ("Contracts whose first N_claims_year exceeds N_claims_history", f"{(first.N_claims_year > first.N_claims_history).sum():,}"),
    ]
    print("  Real:")
    print(table([[a, b] for a, b in checks], ["Check", "Result"]))

    drv = extra["drivers"]
    lic_age = years_between(drv.birth_date, drv.licensed_date)
    s_checks = [
        ("Blank cells in the analysis fields above", f"{int(syn[['age', 'lic_years', 'veh_age', 'veh_value', 'premium']].isna().sum().sum()):,}"),
        ("Drivers licensed before 16", f"{(lic_age < 16).sum():,}"),
        ("Vehicle-terms with negative earned premium", f"{(syn.earned < 0).sum():,}"),
        ("Claims with a cost but no premium earned on the vehicle-term", f"{((syn.claims > 0) & (syn.earned <= 0)).sum():,}"),
    ]
    print("\n  Synthetic (validate.py runs the full set of integrity checks; these mirror the real ones):")
    print(table([[a, b] for a, b in s_checks], ["Check", "Result"]))


def _level_key(x: str):
    """Order band labels numerically where they start with a number."""
    s = str(x)
    if s.startswith("<"):
        return (0, -1.0, s)
    num = "".join(ch for ch in s.lstrip("Q").split("-")[0].split(" ")[0].rstrip("+") if ch.isdigit() or ch == ".")
    return (0, float(num), s) if num else (1, 0.0, s)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--synthetic", type=Path, default=Path("output"), help="folder written by generate.py")
    ap.add_argument("--real", type=Path, default=Path("real_data/mendeley_motor_portfolio"))
    a = ap.parse_args()
    real_all, real, types = load_real(a.real)
    syn, extra = load_synthetic(a.synthetic)
    print(f"Real portfolio vs synthetic book (synthetic seed {extra['summary'].get('seed')}, "
          f"{extra['summary'].get('policies'):,} policies)")
    report(real_all, real, types, syn, extra)


if __name__ == "__main__":
    main()
