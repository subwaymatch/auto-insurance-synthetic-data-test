# Synthetic auto insurance data for Chicago and its suburbs

A seeded generator that produces a realistic personal auto insurance book for one fictional
carrier writing in the seven-county Chicago area (Cook, DuPage, Lake, Will, Kane, McHenry,
Kendall). It replaces an older synthetic dataset whose loss ratio (about 20%) and risk
relationships were not credible.

Everything about people, policies, premiums and claims is simulated. No record describes a
real person. The geography is real: ZIP codes, Census demographics, and Chicago police crash
and vehicle-theft counts.

## Quick start

```bash
pip install -r requirements.txt
```

```bash
python generate.py
```

```bash
python validate.py
```

`generate.py` writes 19 CSV tables to `output/` and an instructor answer key to
`output/answer_key/` in about 15 seconds. `validate.py` re-reads those files and checks them
against the calibration targets.

| Option | Default | Meaning |
|---|---|---|
| `--seed` | `20250101` | Same seed and options give byte-identical files |
| `--policies` | `30000` | Distinct policies ever written (in-force book plus new business) |
| `--start` | `2022-01-01` | First day simulated |
| `--valuation` | `2026-09-30` | "As of" date of the extract; nothing later is known |
| `--out` | `output/` | Output folder |

The calibration targets are tuned for the default dates. Other windows between 2021 and 2026
work, but may land outside a tolerance band.

## What the default run produces

| | |
|---|---|
| Policies / policy terms | 30,000 / 130,794 |
| Drivers / vehicles | 52,021 / 61,710 (11,890 vehicles replaced during the period) |
| Earned exposure | 120,398 car-years |
| Earned premium | $125.5 million ($1,043 per car-year, $1,757 per policy-year) |
| Claims / coverage features | 10,407 / 14,356 |

Paid claim frequency and severity against the national figures they are tuned toward
(Triple-I / ISO, 2022 to 2024):

| Coverage | Claims per 100 car-years | National | Average paid claim | National |
|---|---|---|---|---|
| Bodily injury | 0.82 | 0.70 to 0.80 | $23,266 | $24,681 to $28,278 |
| Property damage | 2.73 | 2.50 to 2.59 | $6,848 | $6,024 to $6,770 |
| Collision | 5.20 | 4.16 to 4.48 | $5,113 | $5,377 to $5,521 |
| Comprehensive | 4.05 | 3.78 to 4.08 | $2,249 | $2,175 to $2,306 |

Frequencies sit a little above national on purpose, because the book is urban.

Loss ratio by accident year (net incurred as of the valuation date, over earned premium):

| 2022 | 2023 | 2024 | 2025 | 2026 (nine months) |
|---|---|---|---|---|
| 82.6% | 76.3% | 63.4% | 65.1% | 60.7% |

This mirrors the industry cycle: under-priced entering 2022, then rate increases catching up.
For comparison, Illinois ran about 78% (liability) and 82% (physical damage) in 2022, and the
national first-half direct loss ratio was 77% in 2023, 68% in 2024 and 61% in 2025. A book
this size moves several points a year on large injury claims alone, so other seeds give
different year-by-year figures within the same range.

## Tables

Names follow the old dataset where an equivalent exists, so existing case material still maps.

| File | One row per | Notes |
|---|---|---|
| `policy_dimension` | Policy | Location, agency, company, limits, insurance score, status |
| `policy_term_fact` | Policy term (6 or 12 months) | Dates, cancellation, written and earned premium, rate level |
| `driver_dimension` | Driver | Demographics; violations and accidents in the 3 years before joining |
| `driver_incident_fact` | Violation or at-fault accident | Motor vehicle record, prior carrier, or the company's own claim |
| `vehicles_dimension` | Make and model | 110 models, as in the old file |
| `insured_vehicle_dimension` | Insured vehicle | Model year, use, mileage, parking, coverages, deductibles |
| `risk_fact` | Policy term and vehicle | Rated characteristics, premium by coverage, earned exposure |
| `claims_fact` | Claim | Loss, report and close dates, cause, paid, reserve, recoveries |
| `claim_coverage_fact` | Coverage (and injured claimant) on a claim | Paid, case reserve, salvage, subrogation, expense |
| `claim_payment_fact` | Payment or recovery | Supports paid development triangles |
| `claim_expense_dimension` | Claim | Kept for compatibility with the old layout |
| `location_dimension` | ZIP code | County, region, rating territories |
| `population_distribution` | ZIP code | Census age, race and ethnicity, tenure, commuting |
| `agency_dimension`, `company_dimension`, `claim_branches` | | Fictional names |
| `catastrophe_dimension` | Catastrophe | Fictional hail, wind and flood events |
| `rate_change_history` | Rate change | Filed overall changes |
| `communication_data` | Customer contact | Tied to renewals, billing, cancellations and claims |

Keys: `Policy Number` (called `Policy ID` on claims and communications, as before),
`Policy Term ID`, `Driver ID`, `Insured Vehicle ID`, `Vehicle ID` (make/model), `Location ID`,
`Record ID` (risk row), `Claim ID`, `Claim Feature ID`.

### Mapping from the old dataset

| Old | New |
|---|---|
| `policy_dimension` (one row per term) | `policy_dimension` (per policy) plus `policy_term_fact` (per term) |
| `risk_fact.Total Premium` | Same column, now split by coverage, with `Earned Premium` and `Earned Exposure` |
| `risk_fact.Vehicle ID` + model year | Same, plus `Insured Vehicle ID` for the specific car |
| `claims_fact.Claim Amount` | Same column (net incurred), plus dates, status, paid, reserve and recoveries |
| `claims_fact.Claimant Id` | Same column: the insured driver involved, or the named insured |
| `claim_expense_dimension` | Same file; also on `claims_fact` |
| `driver_dimension.Primary Vehicle Use` | Moved to `insured_vehicle_dimension` |
| `population_distribution` | Same file, rebuilt from the Census |

## How it works

1. **Geography.** 290 real ZIP codes with Census demographics. Each has a crash hazard index
   and a theft hazard index (see "Sources").
2. **Households.** Policies are placed in ZIPs in proportion to vehicle-owning households.
   Drivers, vehicles and coverages are drawn from each ZIP's age, income, vehicle and
   commuting profile.
3. **True risk.** Every driver has a hidden risk factor. Claim frequency depends on it and on
   age, experience, mileage, vehicle, parking and ZIP. Prior violations and accidents are
   generated from the same hidden factor, so they predict claims, imperfectly.
4. **Rating plan.** Premiums come from a rating plan that only sees what an insurer would see.
   It is fitted to the true expected loss cost, then deliberately distorted (next section).
5. **Policy life.** Each term is rated at the rate level in force. Customers renew or leave
   (more often after a price increase), cancel mid-term, replace vehicles and add teenage
   drivers.
6. **Claims.** Losses are simulated by cause, then split into coverages with limits and
   deductibles applied. Each claim gets report and close dates, payments, expenses, salvage,
   subrogation and a case reserve if still open.
7. **Valuation cut-off.** Payments after the valuation date have not happened, and claims not
   yet reported are left out, as in a real extract.

## What a case study can find (instructor notes)

`output/answer_key/` holds the truth behind the data: each vehicle's expected loss by
coverage, each driver's hidden risk factor, true mileage, true ZIP hazard, the full rating
plan before and after distortion, and the claims not yet reported. Withhold that folder from
students.

Deliberate and emergent findings in the default run:

| Finding | What the data shows |
|---|---|
| Young drivers are under-priced | Expected loss ratio 71% to 88% for classes under 25, against about 64% for ages 25 to 64 |
| Mileage is under-used | Expected loss ratio rises from 60% under 5,000 miles to 80% at 16,000+ |
| Kia/Hyundai theft wave is unpriced | Thefts per 1,000 insured vehicles peak at 7.1 for affected models in 2023, against 2.1 for others |
| Automatic emergency braking is unpriced | Expected loss ratio 62% with it, 68% without |
| Rates lagged costs, then caught up | Loss ratio falls from 83% (2022) to the low 60s |
| Insurance score is priced correctly | Premium more than doubles from best to worst tier; expected loss ratio is flat |
| The newest year looks better than it is | Late-reported claims are missing and open claims carry imperfect reserves |
| Price increases cost retention | Renewal probability falls with the size of the increase |

Reported mileage is understated relative to true mileage, on-street parking raises theft and
hit-while-parked claims, and each ZIP has a hazard component the territories do not capture.

### Geography and race

Premiums are higher in ZIP codes with more non-white residents (ZIP-level correlation 0.71),
because the real crash and theft data behind the hazard indices is higher there. This follows
real-world premium patterns and was left in deliberately. The expected loss ratio does not vary
with a ZIP's racial make-up (correlation -0.02): the model plants no over- or under-charging by
area. No person-level race field exists, and names are drawn at random with no link to ZIP.

## Assumptions and limits

All assumptions live in `autoins/config.py`, each marked ANCHORED (published figure), TUNED
(set to hit an anchored target) or ASSUMED (judgement). The ones that matter most:

- **Suburban hazard is modelled, not observed.** Chicago's crash data covers the city only.
  Suburban ZIPs get the city's income gradient at an assumed lower level.
- **City hazard is damped.** Raw police-record rates vary about sevenfold across city ZIPs; an
  exponent narrows that to a range typical of rating territories.
- **Benchmarks are national**, not Illinois-specific, and cost trends for 2025 and 2026 are
  assumed.
- **The rate schedule is stylised**: about +44% cumulative between April 2022 and March 2025.
- **Catastrophes are fictional.** Dates and footprints are plausible for northern Illinois but
  do not correspond to actual storms.
- **Household changes happen only at renewal.** There are no mid-term endorsements, no drivers
  leaving a policy and no address changes.
- **Not modelled:** fraud, reopened claims, telematics, rental and towing coverages.
- **Vehicle prices are approximate** list prices, used only to scale repair and total-loss costs.

## Sources

| Used for | Source |
|---|---|
| ZIP demographics | US Census Bureau, American Community Survey 2020-2024 5-year tables |
| ZIP to county, land area, coordinates | US Census Bureau 2020 ZCTA relationship file and 2024 gazetteer |
| ZIP place names | GeoNames postal code data, CC BY 4.0 |
| City crash hazard, seasonality | City of Chicago Data Portal, Traffic Crashes (drivers by home ZIP, 2021-2025) |
| City theft hazard, seasonality, yearly trend | City of Chicago Data Portal, Crimes (motor vehicle theft, 2021-2026) |
| Frequency and severity targets | Triple-I / ISO, private passenger auto losses 2015-2024 |
| Loss ratio context | AM Best, S&P Global, Illinois Department of Insurance market share reports |
| Minimum limits | Illinois Department of Insurance (25/50/20, uninsured motorist 25/50) |

The small files under `reference/` are derived from these and are committed, so generating data
needs no network access. To rebuild them (needs `shapely` and network access):

```bash
python scripts/fetch_public_data.py
```

```bash
python scripts/build_reference_data.py
```

## Layout

```
generate.py              command-line entry point
validate.py              calibration and integrity report
autoins/config.py        every assumption
autoins/population.py    households, drivers, vehicles, coverages
autoins/truth.py         true frequency and severity, expected loss, claim simulation
autoins/rating.py        the insurer's rating plan
autoins/simulate.py      term-by-term simulation: rating, retention, claims
autoins/claims.py        claim lifecycle and valuation cut-off
autoins/tables.py        output tables and answer key
reference/               ZIP reference data, vehicle catalogue, name lists
scripts/                 one-off scripts that build reference/
tests/                   python -m unittest discover tests
```
