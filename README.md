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
`output/answer_key/` in about 15 seconds. The default run is committed in `output/`, so the
data can be used without running anything. `validate.py` re-reads those files and checks them
against the calibration targets and for record-level consistency (vehicle lifecycles, what was
known when each term was rated, policy dates, premium accounting and payments).

| Option | Default | Meaning |
|---|---|---|
| `--seed` | `20250101` | Same seed and options give byte-identical files |
| `--policies` | `30000` | Distinct policies ever written (in-force book plus new business) |
| `--start` | `2022-01-01` | First day simulated |
| `--valuation` | `2026-09-30` | "As of" date of the extract; nothing later is known |
| `--out` | `output/` | Output folder |

The calibration targets are tuned for the default dates. Other windows between 2021 and 2026
work, but may land outside a tolerance band.

Library versions are pinned in `requirements.txt` because a newer numpy or pandas may draw
random numbers or format floats slightly differently, which would change the generated values.

## Releases

`.github/workflows/release.yml` builds the dataset from source, runs the tests and
`validate.py`, and publishes a GitHub release. To release the default configuration, push a tag:

```bash
git tag v1.0.0
```

```bash
git push origin v1.0.0
```

To release another seed or size, open the Actions tab, choose "Release dataset", then
"Run workflow", and enter a tag, seed and policy count. Re-running for an existing tag replaces
that release's files.

Each release carries:

| File | Contents |
|---|---|
| `chicago-auto-insurance-data-<tag>.zip` | The tables, `run_summary.json` and this README. Give this to students. |
| `chicago-auto-insurance-answer-key-<tag>.zip` | The answer key. Instructors only. |
| `validation-report-<tag>.txt` | Full output of `validate.py` |
| `SHA256SUMS.txt` | Checksums |

The release fails if a test or validation check fails. For the default settings, it also
reports whether the freshly built data matches the committed `output/` folder; a mismatch
raises a warning, not a failure, because floating-point details can differ between machines.

## What the default run produces

| | |
|---|---|
| Policies / policy terms | 30,000 / 139,418 (13,747 of the terms were already in force on the start date) |
| Drivers / vehicles | 52,070 / 64,342 (12,981 traded in at renewal, 1,848 written off as total losses) |
| Earned exposure | 122,154 car-years |
| Earned premium | $126.6 million ($1,036 per car-year, $1,720 per policy-year) |
| Claims / coverage features | 10,409 / 14,208 |

Paid claim frequency and severity against the national figures they are tuned toward
(Triple-I / ISO, 2022 to 2024):

| Coverage | Claims per 100 car-years | National | Average paid claim | National |
|---|---|---|---|---|
| Bodily injury | 0.74 | 0.70 to 0.80 | $24,599 | $24,681 to $28,278 |
| Property damage | 2.69 | 2.50 to 2.59 | $6,817 | $6,024 to $6,770 |
| Collision | 5.04 | 4.16 to 4.48 | $5,037 | $5,377 to $5,521 |
| Comprehensive | 3.95 | 3.78 to 4.08 | $2,285 | $2,175 to $2,306 |

Frequencies sit at or a little above national on purpose, because the book is urban.

Loss ratio by accident year (net incurred as of the valuation date, over earned premium):

| 2022 | 2023 | 2024 | 2025 | 2026 (nine months) |
|---|---|---|---|---|
| 70.4% | 75.3% | 59.0% | 61.1% | 64.4% |

This mirrors the industry cycle: under-priced entering 2022, then rate increases catching up. The
answer key's expected loss ratio, which is free of claim luck, falls from 73% (2022) and 72% (2023)
to 64% (2024) and 60% (2025 and 2026).
For comparison, Illinois ran about 78% (liability) and 82% (physical damage) in 2022, and the
national first-half direct loss ratio was 77% in 2023, 68% in 2024 and 61% in 2025. A book
this size moves several points a year on large injury claims alone, so other seeds give
different year-by-year figures within the same range.

## Tables

Names follow the old dataset where an equivalent exists, so existing case material still maps.

| File | One row per | Notes |
|---|---|---|
| `policy_dimension` | Policy | Location, agency, company, limits, insurance score, status |
| `policy_term_fact` | Policy term (6 or 12 months) | Dates (including the rating date), cancellation, written, endorsement, return and earned premium, rate level |
| `driver_dimension` | Driver | Demographics; violations and accidents in the 3 years before joining; good-student status when added |
| `driver_incident_fact` | Violation or at-fault accident | Motor vehicle record, prior carrier, or the company's own claim, with the date the insurer learned of it |
| `vehicles_dimension` | Make and model | 110 models, as in the old file |
| `insured_vehicle_dimension` | Insured vehicle | Model year, use, mileage, parking, coverages, deductibles, added and removed dates, why it left, the vehicle it replaced |
| `risk_fact` | Policy term and vehicle | Rated characteristics, premium by coverage, cover dates, earned exposure |
| `claims_fact` | Claim | Loss, report and close dates, cause, paid, reserve, recoveries |
| `claim_coverage_fact` | Coverage (and injured claimant) on a claim | Paid, case reserve, salvage, subrogation, expense, reopen date |
| `claim_payment_fact` | Payment or recovery | Payment type and transaction type; supports paid development triangles |
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
5. **Policy life.** Each term is rated at the rate level in force, on a rating date before it
   starts, using only what the insurer knows by then. Customers renew or leave (more often
   after a price increase), cancel mid-term, trade in vehicles and add teenage drivers at
   renewal, and replace vehicles written off in a total loss.
6. **Claims.** Losses are simulated by cause, then split into coverages with limits and
   deductibles applied. Each claim is developed as it happens: report and close dates,
   payments, expenses, salvage, subrogation, occasional reopenings, and a case reserve if
   still open.
7. **Valuation cut-off.** Payments after the valuation date have not happened, and claims not
   yet reported are left out, as in a real extract.

### Dates and timing

- **Opening book.** Policies in force on the start date enter with the term that spans it,
  which was written before the extract. Their exposure and premium count only from the start
  date: `Earned Premium` is earned inside the extract, `Earned Before Extract` before it, and
  `risk_fact` gives each row's `Coverage Start Date` (which can be before the start, as can
  `policy_dimension.Policy Effective Date`, the start of a policy's first term in the data).
- **Anniversaries.** Policies can be written on any day, including the 29th to 31st. In a
  shorter month the term starts on the last day, and the next one returns to the original day
  (a policy written on 31 August renews on 28 or 29 February, then on 31 August).
- **What the insurer knows.** `Rating Date` is when a term was quoted: 30 to 45 days before a
  renewal (the renewal offer) and up to 14 days before new business. Rating, underwriting
  non-renewals and the customer's renewal decision use only incidents known by then.
  `driver_incident_fact.Known Date` is when each became known: a violation when the conviction
  posts to the driving record (about two months), an earlier accident when it reaches a
  claims-history report, and the company's own at-fault claim on the day its payments reach the
  $1,000 surcharge threshold. A claim that is reported or paid after a renewal's rating date
  first counts at the next renewal.
- **Total losses.** A vehicle written off ends its cover the day after the loss
  (`Removal Reason` = Total Loss). About five in six households buy a replacement, which joins
  the policy with a new `Insured Vehicle ID` (`Replaces Vehicle ID` points back) on the day it
  is bought, or at renewal if the term has ended. A one-car policy with no replacement is
  cancelled. Claims on the old vehicle keep developing after it leaves.
- **Premium.** Vehicles added or removed mid-term are endorsements charged or returned pro rata.
  For every finished term, written + endorsement + return premium = earned before the extract
  + earned premium.
- **Good student.** The discount applies while a driver with B grades is still in full-time
  school and under 25, judged on each term's effective date; `risk_fact.Rated Good Student`
  keeps the status each term was rated with.
- **Payments.** Glass and most injury claims settle in one payment. Physical damage is often
  paid on the first estimate and topped up later; property damage may pay loss of use first;
  injury claims sometimes get an advance; medical payments follow the bills. Total losses may be
  split between lienholder and owner, with fees paid later. A few payments are voided and
  reissued, and about 3% of paid features reopen for a supplement. Payments always add up to the
  feature's paid loss to the cent.

## What a case study can find (instructor notes)

`output/answer_key/` (and the separate answer-key zip in each release) holds the truth behind the data: each vehicle's expected loss by
coverage, each driver's hidden risk factor, true mileage, true ZIP hazard, the full rating
plan before and after distortion, and the claims not yet reported. Withhold it from students:
give them the data zip from a release, not access to this repository, because the answer key is
committed here.

Deliberate and emergent findings in the default run:

| Finding | What the data shows |
|---|---|
| Young drivers are under-priced | Expected loss ratio 72% to 87% for classes under 25, against about 65% for ages 25 to 64 |
| Mileage is under-used | Expected loss ratio rises from 60% under 5,000 miles to 80% at 16,000+ |
| Kia/Hyundai theft wave is unpriced | Whole-vehicle thefts per 1,000 vehicle-years: 6.1 and 5.6 for affected models in 2022 and 2023, against 1.0 to 1.6 for others |
| Automatic emergency braking is unpriced | Expected loss ratio 62.5% with it, 67.5% without |
| Rates lagged costs, then caught up | Loss ratio falls from the 70s (2022, 2023) to about 60% (2024, 2025) |
| Insurance score is priced correctly | Premium more than doubles from best to worst tier; expected loss ratio is flat |
| The newest year is not fully known | Late-reported claims are missing, open claims carry imperfect reserves, and closed claims can reopen |
| Price increases cost retention | Renewal probability falls with the size of the increase |
| Records reach the insurer late | A violation or chargeable claim shortly before a renewal's rating date is surcharged a term later |

Reported mileage is understated relative to true mileage, on-street parking raises theft and
hit-while-parked claims, and each ZIP has a hazard component the territories do not capture.

### Geography and race

Premiums are higher in ZIP codes with more non-white residents (ZIP-level correlation 0.70),
because the real crash and theft data behind the hazard indices is higher there. This follows
real-world premium patterns and was left in deliberately. The expected loss ratio barely varies
with a ZIP's racial make-up (correlation -0.09): the model plants no over- or under-charging by
area. ZIP-level correlations say nothing about individuals, causes or actuarial fairness. No person-level race field exists, and names are drawn at random with no link to ZIP.

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
- **Household changes happen at renewal**, apart from replacing a vehicle written off in a total
  loss. There are no other mid-term endorsements, no drivers leaving a policy and no address
  changes, and many household and coverage attributes stay fixed.
- **Total losses the company does not pay are not modelled.** A car without collision cover that
  is wrecked, or one the owner keeps as salvage, stays on the policy as if undamaged; every total
  loss the company pays leaves the policy.
- **Reporting lags are short.** The median claim is reported a day after the loss and few take
  more than 90 days (injury features open a little later). Check the tail against suitable
  experience before using the data to teach IBNR.
- **Timing assumptions** (rating lead times, driving-record posting lags, replacement delays,
  payment patterns) are judgement calls, marked ASSUMED in `autoins/config.py` and
  `autoins/claims.py`.
- **Not modelled:** fraud, telematics, rental and towing coverages.
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
output/                  the default run (seed 20250101), committed
reference/               ZIP reference data, vehicle catalogue, name lists
scripts/                 build reference/ from public sources; package release files
.github/workflows/       release workflow
tests/                   python -m unittest discover tests
```
