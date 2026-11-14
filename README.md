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

`generate.py` writes 20 CSV tables to `output/` and an instructor answer key to
`output/answer_key/` in about 35 seconds. The default run is committed in `output/`, so the
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
| Policies / policy terms | 30,000 / 138,032 (13,747 of the terms were already in force on the start date) |
| Drivers / vehicles | 53,095 / 75,726 (2,421 drivers left a policy; 16,372 vehicles traded in, 3,638 sold, 4,156 destroyed or stolen, 834 taken by a leaving driver) |
| Risk rows / premium transactions | 305,113 (23.5% start at a mid-term change) / 185,229 (42,394 endorsements) |
| Earned exposure | 122,615 car-years |
| Earned premium | $125.6 million ($1,024 per car-year, $1,726 per policy-year) |
| Claims / coverage features | 12,870 / 20,050 (42% of closed liability features and 20% of closed physical damage features paid nothing) |

Paid claim frequency and severity against the national figures they are tuned toward
(Triple-I / ISO, 2022 to 2024):

| Coverage | Claims per 100 car-years | National | Average paid claim | National |
|---|---|---|---|---|
| Bodily injury | 0.81 | 0.70 to 0.80 | $23,748 | $24,681 to $28,278 |
| Property damage | 2.80 | 2.50 to 2.59 | $6,640 | $6,024 to $6,770 |
| Collision | 5.15 | 4.16 to 4.48 | $5,054 | $5,377 to $5,521 |
| Comprehensive | 3.85 | 3.78 to 4.08 | $2,207 | $2,175 to $2,306 |

Frequencies sit at or a little above national on purpose, because the book is urban.

Loss ratio by accident year (net incurred losses excluding LAE as of the valuation date, over earned
premium), against industry pure loss ratios (incurred losses excluding LAE over earned premium, direct,
calendar year):

| | 2022 | 2023 | 2024 | 2025 | 2026 (nine months) |
|---|---|---|---|---|---|
| This dataset, actual | 76.0% | 74.4% | 63.3% | 67.0% | 68.6% |
| This dataset, expected (answer key, free of claim luck) | 78.0% | 74.2% | 64.5% | 62.1% | 63.2% |
| US private passenger auto | 80.2% | 75.4% | 66.1% | 61.5% | 60.4% (Q1) |
| Illinois private passenger auto | 79.6% | 72.8% | 63.4% | 60.1% | |

The book enters 2022 under-priced, as the industry did after pandemic-era rate cuts, and rate
increases (+48% cumulative, close to the industry's +12.1% in 2022, +16.5% in 2023, +7.6% in 2024
and +3.7% in 2025) bring it back. Overall it runs 69.2%, against about 70% for the US and 68% for
Illinois over 2022 to 2025. The expected loss ratio is held to the industry path by `validate.py`.
The actual figures move several points a year on large injury claims alone (2025 and 2026 drew
high in this seed), so other seeds give different year-by-year figures within the same range.
Add about 8 to 10 points of loss adjustment expense to compare with a loss-and-LAE ratio
(industry LAE ran 8.0% to 10.2% of premium in 2022 to 2025); do not compare with combined ratios.
Sources: APCIA (2022), S&P Global Market Intelligence (2023 to 2026), Illinois Department of
Insurance market share reports, S&P Global RateWatch, AM Best, Texas DOI Insurance Expense Exhibit.

## Tables

Names follow the old dataset where an equivalent exists, so existing case material still maps.

| File | One row per | Notes |
|---|---|---|
| `policy_dimension` | Policy | Location, agency, company, limits, insurance score, status |
| `policy_term_fact` | Policy term (6 or 12 months) | Dates (including the rating date), cancellation, written, endorsement, return and earned premium, rate level |
| `policy_transaction_fact` | Premium transaction | New business, renewal, endorsement or cancellation, with effective and processed (accounting) dates and the written premium booked |
| `driver_dimension` | Driver | Demographics; violations and accidents in the 3 years before joining; good-student status when added; removed date and reason |
| `driver_incident_fact` | Violation or at-fault accident | Motor vehicle record, prior carrier, or the company's own claim, with the date the insurer learned of it |
| `vehicles_dimension` | Make and model | 110 models, as in the old file |
| `insured_vehicle_dimension` | Insured vehicle | Model year, use, mileage, parking, current coverages and deductibles, added and removed dates, why it left, the vehicle it replaced |
| `risk_fact` | Policy term, vehicle and endorsement period | Endorsement number and change reason, garaging location, rating date, rated characteristics, deductibles, premium by coverage, cover dates, earned exposure |
| `claims_fact` | Claim | Loss, report and close dates, cause, paid, reserve, recoveries |
| `claim_coverage_fact` | Coverage (and injured claimant) on a claim | Paid, case reserve, salvage, subrogation, expense, reopen date, owner-retained salvage |
| `claim_payment_fact` | Payment or recovery | Payment type and transaction type; supports paid development triangles |
| `claim_expense_dimension` | Claim | Kept for compatibility with the old layout |
| `location_dimension` | ZIP code | County, region, rating territories |
| `population_distribution` | ZIP code | Census age, race and ethnicity, tenure, commuting |
| `agency_dimension`, `company_dimension`, `claim_branches` | | Fictional names |
| `catastrophe_dimension` | Catastrophe | Fictional hail, wind and flood events |
| `rate_change_history` | Rate change | Filed overall changes |
| `communication_data` | Customer contact | Tied to renewals, policy changes, billing, cancellations and claims |

Keys: `Policy Number` (called `Policy ID` on claims and communications, as before),
`Policy Term ID`, `Driver ID`, `Insured Vehicle ID`, `Vehicle ID` (make/model), `Location ID`,
`Record ID` (risk row), `Claim ID`, `Claim Feature ID`, `Transaction ID`. Policy-level attributes in
`policy_dimension` (location, homeowner, named insured, drivers) and coverages in
`insured_vehicle_dimension` describe the policy as it stands at its latest status; `risk_fact` keeps
the values each period was rated with.

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
   after a price increase) or cancel mid-term. During a term households move, buy, sell and
   trade cars, add newly licensed teenagers and new spouses, and lose drivers who move out,
   divorce or die; each change is an endorsement that re-rates the policy from that day. At
   renewal loans are paid off, older cars drop collision and some customers raise deductibles.
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
- **Household changes.** Mid-term changes happen on their own dates and each is an
  endorsement: the policy's risk rows end that day and new rows, re-rated with what is known
  that day, start (`risk_fact.Endorsement Number`, `Change Reason`, `Rating Date`). Rates come
  from public data: moves within the metro (5.5% of owners and 20% of renters move each year,
  73% within the metro; ACS 2024), divorce (12.9 per 1,000 married women) and marriage in Illinois
  (ACS 2024), mortality by age (CDC 2024), children leaving home (58% of 18-24s and 16% of 25-34s
  live with parents; CPS 2025), teen licensing ages (FHWA 2024), and vehicle ownership spells of
  five to six and a half years. A driver who leaves usually takes their own car.
- **Total losses.** A car destroyed or stolen ends its cover the day after the loss, whether the
  company pays a total loss (`Removal Reason` = Total Loss) or not (Destroyed or Stolen: a car
  without collision cover, a loss the other driver's insurer paid, or a claim not pursued). About
  four in five households buy a replacement, which joins with a new `Insured Vehicle ID`
  (`Replaces Vehicle ID` points back) when it is bought, about five weeks later on average. A
  one-car policy with no replacement is cancelled. Claims on the old vehicle keep developing.
  A few owners keep a car the company paid as a total loss (`Owner Retained Salvage`); as Illinois
  law requires, only for hail damage or a car nine or more model years old. The salvage value
  comes off the settlement and the car loses physical damage cover at the next renewal.
- **Premium.** Changes mid-term are endorsements charged or returned pro rata to the end of the
  term. `policy_transaction_fact` books each transaction on a processed date a few days after it
  takes effect; transactions not processed by the valuation date are not in the extract. For every
  finished term, written + endorsement + return premium = earned before the extract + earned
  premium, and the ledger adds up to the same.
- **Good student.** The discount applies while a driver with B grades is still in full-time
  school and under 25, judged on each term's effective date; `risk_fact.Rated Good Student`
  keeps the status each term was rated with.
- **Payments.** Glass and most injury claims settle in one payment. Physical damage is often
  paid on the first estimate and topped up later; property damage may pay loss of use first;
  injury claims sometimes get an advance; medical payments follow the bills. Total losses may be
  split between lienholder and owner, with fees paid later. A few payments are voided and
  reissued, and about 3% of paid features reopen for a supplement. Payments always add up to the
  feature's paid loss to the cent.
- **Claims that pay nothing.** As in real claim files, many features close without payment:
  liability claims against an insured who was not at fault, injury claims opened as a precaution
  and never pursued, and damage reported then withdrawn. They carry a nominal reserve while open.
  About 42% of closed liability and medical features and 20% of closed collision and comprehensive
  features pay nothing (industry 2025: about 45% and just under 25%).
- **Reporting lags.** Injury claims are often presented weeks or months after the accident, and a
  few near Illinois' two-year statute of limitations. Lags follow a US insurer's experience: 84% of
  bodily injury claims reported within 5 days, 97.5% within 90 and 99.2% within a year (CAS Loss
  Simulation Model Working Party); collision claims are reported faster.

## What a case study can find (instructor notes)

`output/answer_key/` (and the separate answer-key zip in each release) holds the truth behind the data: each vehicle's expected loss by
coverage, each driver's hidden risk factor, true mileage, true ZIP hazard, the full rating
plan before and after distortion, and the claims not yet reported. Withhold it from students:
give them the data zip from a release, not access to this repository, because the answer key is
committed here.

Deliberate and emergent findings in the default run:

| Finding | What the data shows |
|---|---|
| Young drivers are under-priced | Expected loss ratio 75% to 93% for classes under 25, against about 66% for ages 25 to 64 |
| Mileage is under-used | Expected loss ratio rises from 62% under 5,000 miles to 83% at 16,000+ |
| Kia/Hyundai theft wave is unpriced | Whole-vehicle thefts per 1,000 vehicle-years: 4.9 and 9.3 for affected models in 2022 and 2023, against about 1.0 for others |
| Automatic emergency braking is unpriced | Expected loss ratio 64.5% with it, 70.3% without |
| Rates lagged costs, then caught up | Expected loss ratio falls from 78% (2022) and 74% (2023) to 64% and 62% (2024, 2025), as the industry's did |
| Insurance score is priced correctly | Premium more than doubles from best to worst tier; expected loss ratio is flat |
| The newest year is not fully known | Late-reported claims are missing, open claims carry imperfect reserves, and closed claims can reopen |
| Price increases cost retention | Renewal probability falls with the size of the increase |
| Records reach the insurer late | A violation or chargeable claim shortly before a renewal's rating date is surcharged a term later |
| Exposure moves | Moves, trade-ins and new drivers change a policy's territory, vehicles and rated drivers mid-term; a vehicle's history spans several risk rows and sometimes several ZIP codes |

Reported mileage is understated relative to true mileage, on-street parking raises theft and
hit-while-parked claims, and each ZIP has a hazard component the territories do not capture.

### Geography and race

Premiums are higher in ZIP codes with more non-white residents (ZIP-level correlation 0.71),
because the real crash and theft data behind the hazard indices is higher there. This follows
real-world premium patterns and was left in deliberately. The expected loss ratio barely varies
with a ZIP's racial make-up (correlation -0.07): the model plants no over- or under-charging by
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
- **Household dynamics are partly sourced.** Mover, divorce, marriage, mortality, licensing and
  vehicle-ownership rates come from public data (see "Dates and timing"); how often households add
  or sell cars, how often a leaving driver takes a car, and the shapes by age are judgement calls.
  Income, insurance score, limits, payment plan and multi-policy status stay fixed for a policy's
  life; homeowner status changes only with a move.
- **Report lags rest on one published study** (one insurer, 1996 to 2005). Lags beyond a year are
  probably understated there, so treat the IBNR tail as indicative.
- **Timing assumptions** (rating lead times, driving-record posting lags, replacement delays,
  payment patterns, endorsement processing lags) are judgement calls, marked ASSUMED in
  `autoins/config.py` and `autoins/claims.py`.
- **Not modelled:** fraud, telematics, rental and towing coverages, underinsured motorist and
  uninsured motorist property damage, quotes that did not bind, reinsurance.

## How it compares with an insurer's own data

The structure follows how insurers hold their data. `risk_fact` is the policy-level exposure
database actuaries build for ratemaking: one record per vehicle per period, split at mid-term
changes, carrying the characteristics in force (as in the CAS ratemaking text, Werner and Modlin).
`claim_coverage_fact` is one row per coverage and claimant, the grain of a claim system's
exposures and of NAIC market conduct claim counts. Claims link to the rating record they arose
under, as statistical plans require; payments, voids and recoveries form a transaction ledger; and
premium is booked as policy transactions with effective and accounting dates. Public alternatives
are far thinner: French motor data (`freMTPL2`) has one row per policy and undated claims, and the
CAS Loss Reserve Database holds company-level triangles only.

Real data would also have, and this dataset does not:

| Gap | Real-world source |
|---|---|
| Case reserve history (reserve changes over time, for incurred triangles) | Claim system reserve transactions; statistical plan outstanding-loss records |
| Expense split into defence and cost containment versus adjusting and other, with expense reserves | Claim system cost types; Illinois cost-containment data call |
| Coverage-level policy records with limits that change at renewal | Statistical plan premium records; policy system coverages |
| VIN and vehicle rating symbols | Statistical plans, ACORD vehicle records, ISO symbols (licensed) |
| Underinsured motorist, uninsured motorist property damage, rental and towing coverages | Illinois coverage menu |
| Claim detail: attorney representation and suit dates, fault percentage, injury type, police report, fraud referral | ACORD claim records, claim systems |
| Quotes that did not bind, applied discounts, billing events, excluded drivers and SR-22 filings | Policy and billing systems |
| Edit errors, late and out-of-sequence bookings | Every production system |

Real data never contains the answer key (true expected losses, latent risk, true mileage,
unreported claims), and analytic extracts usually drop names. Insurer data is rarely public
because of privacy law (Gramm-Leach-Bliley, the Illinois Insurance Information and Privacy
Protection article, the Driver's Privacy Protection Act, and the Fair Credit Reporting Act for
claims-history reports), competitive confidentiality, and licensing of statistical plan layouts and
vehicle symbols.
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
| Loss ratio and rate change calibration | APCIA; S&P Global Market Intelligence and RateWatch; AM Best; Illinois Department of Insurance market share and cost containment reports; Texas DOI Insurance Expense Exhibit (LAE) |
| Minimum limits | Illinois Department of Insurance (25/50/20, uninsured motorist 25/50) |
| Physical damage take-up | NAIC Auto Insurance Database, average premium supplement 2023 (Illinois collision and comprehensive per liability car-year) |
| Claim report lags | CAS Loss Simulation Model Working Party (Ball State University paper), bodily injury and collision report lags |
| Claims closed without payment | WSJ analysis of insurer filings with the NAIC, 2025 |
| Statutes of limitations, owner-retained salvage | 735 ILCS 5/13-202 and 13-205; 625 ILCS 5/3-117.1 |
| Moves, living with parents, marriage and divorce | US Census Bureau ACS 2024 1-year (B07013, B07201, B12001, B12503) and CPS ASEC 2025 (table AD-1) |
| Mortality | CDC NCHS Data Brief 548 (2024 death rates by age) |
| Teen licensing | FHWA Highway Statistics 2024, table DL-20 |
| Vehicle ownership and loans | S&P Global Mobility / IHS Markit ownership spells; Experian State of the Automotive Finance Market (loan terms) |
| Total-loss handling | CCC Crash Course (valuation times, total-loss share); Hi Marley 2023 |

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
