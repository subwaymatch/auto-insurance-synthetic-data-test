# Synthetic auto insurance data for Chicago and its suburbs

A seeded generator that produces a realistic personal auto insurance book for one fictional
carrier writing in the seven-county Chicago area (Cook, DuPage, Lake, Will, Kane, McHenry,
Kendall). It replaces an older synthetic dataset whose loss ratio (about 20%) and risk
relationships were not credible.

Everything about people, policies, premiums and claims is simulated. No record describes a
real person. The geography is real: ZIP codes, Census demographics, and Chicago police crash
and vehicle-theft counts.

## Getting the data

The data is published as GitHub releases, not committed to the repository. The `latest`
release is rebuilt automatically whenever the generator changes on `main`:

- Student data: [chicago-auto-insurance-data-latest-csv.zip](https://github.com/subwaymatch/auto-insurance-synthetic-data-test/releases/download/latest/chicago-auto-insurance-data-latest-csv.zip)
- Instructor answer key: [chicago-auto-insurance-answer-key-latest-csv.zip](https://github.com/subwaymatch/auto-insurance-synthetic-data-test/releases/download/latest/chicago-auto-insurance-answer-key-latest-csv.zip)

Versioned releases (`v1.0.0` and so on) are listed on the [releases page](https://github.com/subwaymatch/auto-insurance-synthetic-data-test/releases). To build the data
yourself instead, see below.

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

`generate.py` writes 22 CSV tables to `output/` and an instructor answer key to
`output/answer_key/` in about 45 seconds. `output/` is ignored by git: the published copy of the
data is the releases above. `validate.py` re-reads those files and checks them
for record-level consistency (vehicle lifecycles, what was known when each term was rated, policy
dates, premium accounting, payments, and every coverage's limits and deductibles) and against the
calibration targets, including a comparison with national figures on those figures' own definitions.

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
`validate.py`, and publishes a GitHub release. It runs in three ways:

- **Automatically, on every push to `main`** that changes the generator, its reference data, the
  release scripts or this README: it rebuilds the default configuration and replaces the rolling
  `latest` pre-release, so the download links above always point at the current build. The release
  notes record the commit it was built from.
- **On a version tag**, for a fixed release of the default configuration:

```bash
git tag v1.0.0
```

```bash
git push origin v1.0.0
```

- **By hand**, for another seed, size or set of file formats: open the Actions tab, choose
  "Release dataset", then "Run workflow", and enter a tag, seed, policy count and formats (default
  `csv`). Re-running for an existing tag replaces that release's files.

Each release carries, for each format:

| File | Contents |
|---|---|
| `chicago-auto-insurance-data-<tag>-<format>.zip` | The tables, `run_summary.json` and this README. Give this to students. |
| `chicago-auto-insurance-answer-key-<tag>-<format>.zip` | The answer key. Instructors only. |

and once:

| File | Contents |
|---|---|
| `validation-report-<tag>.txt` | Full output of `validate.py` |
| `SHA256SUMS.txt` | Checksums |

To package the same files locally:

```bash
python scripts/package_release.py --data output --tag v1.0.0 --validation report.txt --dist dist --formats csv
```

**Adding a format** (Parquet, SQLite, Excel and so on) takes one function in
`scripts/release_formats.py`, registered under the format's name, plus its library in
`requirements-release.txt`; the file explains the pattern with examples. The workflow then
publishes it when its name is listed in the formats input.

The release fails if a test or an integrity check fails. Calibration bands only count for books of
20,000 policies or more; on smaller books they are reported as warnings, because a few hundred
claims are too few to hold them. The same seed and settings give byte-identical files on any
machine with the pinned library versions, so a release can always be rebuilt exactly.

## What the default run produces

| | |
|---|---|
| Policies / policy terms | 30,000 / 137,467 (13,747 of the terms were already in force on the start date) |
| Drivers / vehicles | 53,108 / 76,043 (2,423 drivers left a policy; 16,398 vehicles traded in, 3,553 sold, 4,503 destroyed or stolen, 854 taken by a leaving driver) |
| Risk rows / premium transactions | 305,578 (23.8% start at a mid-term change) / 185,204 (42,967 endorsements) |
| Earned exposure | 122,684 car-years |
| Earned premium | $136.5 million ($1,113 per car-year, $1,882 per policy-year) |
| Claims / coverage features / reserve transactions | 14,042 / 24,847 / 81,313 (42% of closed liability and medical features and 17% of closed physical damage features paid nothing) |
| Quotes | 85,273, of which 18.9% bound |

### Frequency and severity against national figures, like for like

The national figures are Triple-I's table of ISO data, "Private Passenger Auto Insurance Losses,
2015-2024". Its footnotes define them: paid claims per 100 earned car years, for all limits combined;
bodily injury and property damage severity **include loss adjustment expenses**; collision and
comprehensive are for coverage with a **$500 deductible**; and comprehensive **excludes wind and water
losses** (and includes glass). The comparison below puts this dataset on the same definitions: claims
are counted in the calendar year of their first loss payment, severity is that year's payments over
those claims, liability payments include the expense booked to the claim, collision and comprehensive
use only risk rows with a $500 deductible, and comprehensive leaves out hail, wind, flood and
catastrophe claims.

| Coverage | Year | Claims per 100 car-years | National | Average paid | National |
|---|---|---|---|---|---|
| Bodily injury (with LAE) | 2022 | 0.36 | 0.70 | $18,793 | $24,681 |
| | 2023 | 0.87 | 0.78 | $23,110 | $26,178 |
| | 2024 | 0.88 | 0.80 | $28,825 | $28,278 |
| Property damage (with LAE) | 2022 | 2.48 | 2.54 | $6,308 | $6,024 |
| | 2023 | 2.91 | 2.59 | $6,254 | $6,554 |
| | 2024 | 2.77 | 2.50 | $6,511 | $6,770 |
| Collision ($500 deductible) | 2022 | 5.30 | 4.48 | $4,976 | $5,377 |
| | 2023 | 5.56 | 4.48 | $5,637 | $5,521 |
| | 2024 | 5.81 | 4.16 | $5,450 | $5,489 |
| Comprehensive ($500 deductible, no wind or water) | 2022 | 4.02 | 3.78 | $2,168 | $2,175 |
| | 2023 | 4.34 | 4.08 | $2,157 | $2,305 |
| | 2024 | 4.34 | 3.95 | $1,842 | $2,306 |

Over the years held to a band (2022 to 2024; 2023 and 2024 for bodily injury), frequency runs 1.10
times national for bodily injury, 1.07 for property damage, 1.27 for collision and 1.08 for
comprehensive, and severity 0.95, 0.98, 0.98 and 0.90 times national. `validate.py` prints this table
for any run and holds frequency to 0.85 to 1.45 times national and severity to 0.85 to 1.15 times.

What still differs, and how to read it:

- **Geography.** The national table covers the whole country (less a few states). This book is one
  metropolitan area, so it is tuned to run above national on frequency, most of all for collision.
  National figures set a reasonable scale. They are not a Chicago benchmark or a single carrier's
  experience, and nothing here has been checked against either.
- **Bodily injury in 2022.** The extract has no claims from accidents before its start date, so the
  first calendar year's payments are too few (injury claims take a year or more to settle). That
  year is shown but not held to a band.
- **Sampling.** A year has about 200 paid bodily injury claims and 450 comprehensive claims in the
  $500 slice, so single-year severities move 10% or more by chance (comprehensive in 2024 is low in
  this seed for that reason).
- **Glass.** Glass claims under full glass cover carry no deductible here and are counted.
- **Counting rules.** The source does not publish how it counts a claim (per claimant or per accident,
  or when a claim counts as paid).

Whole-extract figures on the dataset's own basis (every deductible and cause, loss only), which
`validate.py` also holds to bands so that the book stays stable from seed to seed: bodily injury 0.76
paid claims per 100 car-years at $24,383; property damage 2.65 at $6,487; collision 5.10 at $5,322;
comprehensive 5.08 at $2,460. These are not comparable with the national table.

### Loss ratios

Loss ratio by accident year (net incurred losses excluding LAE as of the valuation date, over earned
premium), against industry pure loss ratios (incurred losses excluding LAE over earned premium, direct,
calendar year):

| | 2022 | 2023 | 2024 | 2025 | 2026 (nine months) |
|---|---|---|---|---|---|
| This dataset, actual | 78.8% | 73.9% | 64.0% | 60.4% | 56.5% |
| This dataset, expected (answer key, free of claim luck) | 77.8% | 73.8% | 64.2% | 62.0% | 63.3% |
| US private passenger auto | 80.2% | 75.4% | 66.1% | 61.5% | 60.4% (Q1) |
| Illinois private passenger auto | 79.6% | 72.8% | 63.4% | 60.1% | |

The book enters 2022 under-priced, as the industry did after pandemic-era rate cuts, and rate
increases (+48% cumulative, close to the industry's +12.1% in 2022, +16.5% in 2023, +7.6% in 2024
and +3.7% in 2025) bring it back. Overall it runs 65.6%, against about 70% for the US and 68% for
Illinois over 2022 to 2025. The expected loss ratio is held to the industry path by `validate.py`.
The actual figures move several points a year on large injury claims alone, so other seeds give
different year-by-year figures within the same range (2022 ran 77% to 85% across four seeds). The
2026 figure is low because it is immature: young injury claims are reserved low and late-reported
claims are missing.

These are pure loss ratios. Three different ratios are easy to confuse:

- **Pure loss ratio** (above): losses only.
- **Loss and LAE ratio**: add loss adjustment expense. The expense booked to individual claims in
  this dataset is 4% to 6% of premium for mature accident years (`claims_fact.Expense Amount`, shown
  beside each year by `validate.py`). Industry LAE, which also includes claim department overhead not
  booked to any claim, ran 8.0% to 10.2% of premium in 2022 to 2025.
- **Combined ratio**: also adds commissions, other underwriting expenses and dividends. Nothing in
  this dataset supports one; do not compare these figures with combined ratios.

Sources: APCIA (2022), S&P Global Market Intelligence (2023 to 2026), Illinois Department of
Insurance market share reports, S&P Global RateWatch, AM Best, Texas DOI Insurance Expense Exhibit.

## Tables

Names follow the old dataset where an equivalent exists, so existing case material still maps.

| File | One row per | Notes |
|---|---|---|
| `policy_dimension` | Policy | Location, agency, company, limits, insurance score, status, and the drivers and vehicles on it at its latest status |
| `policy_term_fact` | Policy term (6 or 12 months) | Dates (including the rating date), cancellation, vehicles at the term start, written, endorsement, return and earned premium, rate level |
| `policy_transaction_fact` | Premium transaction | New business, renewal, endorsement or cancellation, with effective and processed (accounting) dates and the written premium booked |
| `quote_fact` | Quote | Every new-business quote, bound or not: prospect profile, quoted premium, the competing premium on independent-agent quotes, and the policy it became |
| `driver_dimension` | Driver | Demographics; violations and accidents in the 3 years before joining; good-student status when added; removed date and reason; SR-22 filing |
| `driver_incident_fact` | Violation or at-fault accident | Motor vehicle record, prior carrier, or the company's own claim, with the conviction date and the date the insurer learned of it |
| `vehicles_dimension` | Make and model | 110 models, as in the old file |
| `insured_vehicle_dimension` | Insured vehicle | VIN prefix and vehicle symbols, model year, use, mileage, parking, current coverages (including rental and towing) and deductibles, added and removed dates, why it left, the vehicle it replaced |
| `risk_fact` | Policy term, vehicle and endorsement period | Endorsement number and change reason, garaging location, rating date, rated characteristics and discounts, the coverage terms in force (limits, deductibles, full glass, rental option, towing), premium by coverage, cover dates, earned exposure |
| `claims_fact` | Claim | Loss, report and close dates, cause, police report, the insured's share of fault, fraud referral, paid, reserves, recoveries |
| `claim_coverage_fact` | Coverage (and injured claimant) on a claim | Paid, case and expense reserves, salvage, subrogation, expense by type (DCC and A&O), uninsured or underinsured motorist type and the other insurer's payment, injury type, attorney and suit dates, reopen date, owner-retained salvage |
| `claim_payment_fact` | Payment or recovery | Payment type and transaction type; supports paid development triangles |
| `claim_reserve_fact` | Reserve change | Every change to a feature's loss or expense reserve, with the balance after it; with the payments, supports incurred development triangles |
| `claim_expense_dimension` | Claim | Kept for compatibility with the old layout |
| `location_dimension` | ZIP code | County, region, rating territories |
| `population_distribution` | ZIP code | Census age, race and ethnicity, tenure, commuting |
| `agency_dimension`, `company_dimension`, `claim_branches` | | Fictional names |
| `catastrophe_dimension` | Catastrophe | Fictional hail, wind and flood events |
| `rate_change_history` | Rate change | Filed overall changes |
| `communication_data` | Customer contact | Tied to renewals, policy changes, billing, cancellations and claims |

Keys: `Policy Number` (called `Policy ID` on claims and communications, as before),
`Policy Term ID`, `Driver ID`, `Insured Vehicle ID`, `Vehicle ID` (make/model), `Location ID`,
`Record ID` (risk row), `Claim ID`, `Claim Feature ID`, `Transaction ID`.

**Current versus historical values.** The dimensions describe each policy, driver and vehicle as it
stands at its latest status: on the valuation date if the policy is in force, otherwise on its last day
of cover. That covers `policy_dimension` (location, homeowner, named insured, limits, `Number of
Drivers`, `Number of Vehicles`) and the coverages on `insured_vehicle_dimension`. `risk_fact` is the
effective-dated record: each row keeps the location, rated characteristics, limits, deductibles, full
glass, rental option and towing that were in force for its dates. Use it, through `Record ID`, for
anything historical. Joining a claim straight to `policy_dimension` gives today's address and
limits, not those on the loss date: in the default run 33,220 risk rows (11%) have a different
location from their policy's current one. `policy_term_fact.Vehicles at Term Start` is the count
when the term began (its endorsement 0 rows); `policy_dimension.Number of Vehicles` is the count now.
For a policy in force the two differ whenever a car was added or removed during the latest term.

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
  claims-history report, and the company's own at-fault claim the day after the payment that takes
  it to the $1,000 surcharge threshold. A claim that is reported or paid after a renewal's rating
  date first counts at the next renewal.
- **Order of events on one day.** The data holds dates, not times, so the order within a day is fixed
  by one rule, used by the simulation and by `validate.py` alike: a rating dated D uses every record
  whose `Known Date` is D or earlier, and a loss or a payment on D can never have a `Known Date` of
  D, because a company claim posts the day after its payment. A policy change rated on the day of
  an accident is therefore rated without that accident, whichever happened first that day.
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
  one-car policy with no replacement is cancelled; one waiting for a replacement stays in force with
  no vehicle until it arrives. Claims on the old vehicle keep developing. The extract shows a
  removal as a total loss only once the company has that claim; until then the car is shown as
  destroyed or stolen, and a car lost on the valuation date itself is still on the policy.
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
  reissued, and about 2% of paid features reopen for a supplement. Payments always add up to the
  feature's paid loss to the cent.
- **Claims that pay nothing.** As in real claim files, many features close without payment:
  liability claims against an insured who was not at fault, injury claims opened as a precaution
  and never pursued, and damage reported then withdrawn. They carry a nominal reserve while open.
  About 42% of closed liability and medical features and 17% of closed collision and comprehensive
  features pay nothing (industry 2025: about 45% and just under 25%).
- **Reserves.** Each feature opens with a formula reserve and is re-estimated on a review cycle (every
  90 days for injury, 30 for physical damage). Early injury estimates average about 86% of ultimate and
  improve as claims mature, so bodily injury incurred develops upward (12-to-24-month factors of about
  1.05 to 1.2) while collision barely moves; payments erode reserves, closing releases them, and
  precautionary injury claims carry a nominal reserve. Litigated features also carry an expense
  reserve. `claim_reserve_fact` records every change, so incurred can be rebuilt as of any date.
- **Claim detail.** About half of paid bodily injury claimants are represented by an attorney (57%
  industry-wide in 2022, Insurance Research Council), mostly within days or weeks of the accident.
  A litigated feature follows an ordered timeline: the attorney is retained, suit is filed after
  both that and the claim being presented and within Illinois' two-year limit, and the feature
  closes at least 30 days after the suit (a feature drawn to close sooner stays open longer).
  At-fault insureds are 51% to 100% at fault, as Illinois' modified comparative fault rule requires
  for a liability payment. `Insured Fault %` describes the accident only: settlements are not
  reduced for the other party's share of fault (see "Assumptions and limits"). Injury type follows
  severity. Police reports, fraud referrals and SR-22 filings (three years after a DUI, driving while
  suspended or leaving the scene) are included.
- **Coverages and limits.** Every payment respects the terms on the risk row it arose under, which
  `validate.py` checks coverage by coverage. Bodily injury and uninsured motorist payments are held
  to the per-person limit and, across an accident's claimants, to the per-accident limit, shared pro
  rata in whole cents so they total the limit exactly. Uninsured motorist cover includes underinsured
  motorist, as in Illinois (`UM/UIM Type` tells the two apart): when the at-fault driver's limit is
  too low, the policy pays each claimant's damages up to its per-person limit less what that
  driver's insurer paid (`Other Insurer Payment`), and for the accident no more than its
  per-accident limit less everything that insurer paid. Rental reimbursement (daily limit and
  per-claim maximum) pays while a car is repaired or replaced, and towing and labor pays for tows
  after crashes. Liability limits can change at renewal.
- **Quotes.** New business is a funnel: every policy began as a bound quote, and unbound quotes come
  from prospects rated with the same plan. Conversion depends on the channel (about 12% direct, 24%
  through independent agents, 41% through exclusive agents) and falls as the quote rises above the
  best competing premium, which independent agents see on their comparative raters.
- **Reporting lags.** Injury claims are often presented weeks or months after the accident, and a
  few near Illinois' two-year statute of limitations. Lags follow a US insurer's experience: 84% of
  bodily injury claims reported within 5 days, 97.5% within 90 and 99.2% within a year (CAS Loss
  Simulation Model Working Party); collision claims are reported faster.

## What a case study can find (instructor notes)

The answer-key zip in each release (and `output/answer_key/` when you build locally) holds the truth
behind the data: each vehicle's expected loss by coverage, each driver's hidden risk factor, true
mileage, true ZIP hazard, the full rating plan before and after distortion, and the claims not yet
reported. Withhold it from students: give them the data zip from a release, not access to this
repository, because anyone with the code can regenerate the answer key.

Deliberate and emergent findings in the default run:

| Finding | What the data shows |
|---|---|
| Young drivers are under-priced | Expected loss ratio 75% to 89% for classes under 25, against about 66% for ages 25 to 64 |
| Mileage is under-used | Expected loss ratio rises from 62% under 5,000 miles to 82% at 16,000+ |
| Kia/Hyundai theft wave is unpriced | Whole-vehicle thefts per 1,000 vehicle-years for affected models peak at 9.7 in 2023, against about 1.0 for others |
| Automatic emergency braking is unpriced | Expected loss ratio 64.8% with it, 69.7% without |
| Rates lagged costs, then caught up | Expected loss ratio falls from 78% (2022) and 74% (2023) to 64% and 62% (2024, 2025), as the industry's did |
| Case reserves develop | Bodily injury incurred grows by 5% to 16% from 12 to 24 months as early, low reserves are corrected; collision moves 1% to 3% |
| New business is price-sensitive | Independent-agent quotes priced below the best competitor bind 36% of the time, those above 12% |
| Insurance score is priced correctly | Premium more than doubles from best to worst tier; expected loss ratio is flat |
| The newest year is not fully known | Late-reported claims are missing, open claims carry imperfect reserves, and closed claims can reopen |
| Price increases cost retention | Renewal probability falls with the size of the increase |
| Records reach the insurer late | A violation or chargeable claim shortly before a renewal's rating date is surcharged a term later |
| Exposure moves | Moves, trade-ins and new drivers change a policy's territory, vehicles and rated drivers mid-term; a vehicle's history spans several risk rows and sometimes several ZIP codes |

Reported mileage is understated relative to true mileage, on-street parking raises theft and
hit-while-parked claims, and each ZIP has a hazard component the territories do not capture.

### Geography and race

Premiums are higher in ZIP codes with more non-white residents (ZIP-level correlation 0.73),
because the real crash and theft data behind the hazard indices is higher there. This follows
real-world premium patterns and was left in deliberately. The expected loss ratio barely varies
with a ZIP's racial make-up (correlation -0.07): the model plants no over- or under-charging by
area. ZIP-level correlations say nothing about individuals, causes or actuarial fairness, and a
relationship planted in synthetic data is not evidence about how real insurers price. No person-level race field exists, and names are drawn at random with no link to ZIP.

## Assumptions and limits

All assumptions live in `autoins/config.py`, each marked ANCHORED (published figure), TUNED
(set to hit an anchored target) or ASSUMED (judgement). The ones that matter most:

- **Suburban hazard is modelled, not observed.** Chicago's crash data covers the city only.
  Suburban ZIPs get the city's income gradient at an assumed lower level.
- **City hazard is damped.** Raw police-record rates vary about sevenfold across city ZIPs; an
  exponent narrows that to a range typical of rating territories.
- **Benchmarks are national**, not Illinois-specific or carrier-specific, and cost trends for 2025
  and 2026 are assumed. Frequency and severity are compared on the national table's own definitions
  (see "Frequency and severity against national figures"), which shows the overall scale is
  reasonable. It does not validate anything finer: results by subgroup, how variables depend on
  each other, large-loss tails or local geography are assumed or tuned, not checked against data.
- **The rating plan is fitted to the truth.** Relativities are fitted directly to the simulator's
  true expected losses on the opening book, then distorted on purpose. A real carrier estimates its
  costs from noisy past losses, with filing and implementation lags, so the plan here is cleaner
  and more adequate than a real one. It is a teaching design, not evidence about a real carrier.
- **Fault is descriptive.** `Insured Fault %` is drawn for each accident after its losses and does
  not change what is paid. Liability settlements are not reduced for a claimant's own share of fault,
  and there is no allocation of fault among several parties. Treat it as a scenario attribute, not
  as a comparative-negligence model.
- **No claims from before the start date.** Loss events begin on the start date, even for policies
  already in force. There is no opening inventory of open claims and no payments or reserve changes
  on earlier accident years. Development triangles for accident years 2022 onward are complete;
  whole-company calendar-year payments and reserves are not (the first calendar year pays too
  little). Moving the start date does not create that history.
- **The rate schedule is stylised**: +48% cumulative between April 2022 and March 2025, then a 2%
  cut in June 2026.
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
- **Vehicle prices are approximate** list prices, used only to scale repair and total-loss costs.
- **Identifiers and symbols are fictional.** VIN prefixes have the statistical-plan shape but begin
  with `0`, which no manufacturing region uses, and the vehicle symbols are this dataset's own scales,
  not ISO's licensed ones.
- **Claimants are not people.** A liability or injury feature has a claimant number within its claim,
  and `claims_fact.Claimant Id` is the insured driver involved. There is no table of third-party
  claimants who can be followed from one claim to another.
- **Not modelled:** fraud itself (only referrals), telematics, uninsured motorist property damage,
  billing and installment events, reinstatements, excluded drivers, separate mailing and garaging
  addresses, reinsurance, and the edit errors and out-of-sequence bookings of production data. The
  dataset is an analytical extract for teaching: it is not a model of a policy administration,
  billing or claims system.

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

It also has what reserving, claims and pricing work rely on: case reserve history (`claim_reserve_fact`,
as in claim systems' reserve transactions and statistical plans' outstanding-loss records), expense
split into defence and cost containment versus adjusting and other with expense reserves, limits and
deductibles on each rating record, VIN prefixes and vehicle symbols (fictional, in the shape
statistical plans use), underinsured motorist, rental and towing coverages, claim detail (attorney and
suit dates, fault percentage, injury type, police report, fraud referral), applied discounts, SR-22
filings, and a quote funnel with quotes that never bound.

Real data would still have, and this dataset does not:

| Gap | Real-world source |
|---|---|
| Claims open on the start date and their later payments (an opening claim inventory) | Claim systems |
| Third-party claimants as people who can be followed across claims | Claim systems |
| Billing and installment events, reinstatements after a lapse | Billing systems |
| Excluded drivers; separate mailing and garaging addresses | Policy systems; statistical plans report the garaging ZIP |
| Uninsured motorist property damage; custom equipment and loan/lease gap coverages | Illinois coverage menu |
| Medical diagnosis codes, recovery reserves, fraud outcomes | Claim systems; Medicare Section 111 reporting |
| Telematics and reinsurance | Usage-based programmes; ceded statistical data |
| Edit errors, out-of-sequence bookings | Every production system |

Real data never contains the answer key (true expected losses, latent risk, true mileage,
unreported claims), and analytic extracts usually drop names. Insurer data is rarely public
because of privacy law (Gramm-Leach-Bliley, the Illinois Insurance Information and Privacy
Protection article, the Driver's Privacy Protection Act, and the Fair Credit Reporting Act for
claims-history reports), competitive confidentiality, and licensing of statistical plan layouts and
vehicle symbols.

## Sources

| Used for | Source |
|---|---|
| ZIP demographics | US Census Bureau, American Community Survey 2020-2024 5-year tables |
| ZIP to county, land area, coordinates | US Census Bureau 2020 ZCTA relationship file and 2024 gazetteer |
| ZIP place names | GeoNames postal code data, CC BY 4.0 |
| City crash hazard, seasonality | City of Chicago Data Portal, Traffic Crashes (drivers by home ZIP, 2021-2025) |
| City theft hazard, seasonality, yearly trend | City of Chicago Data Portal, Crimes (motor vehicle theft, 2021-2026) |
| Frequency and severity benchmark | Triple-I, "Facts + Statistics: Auto insurance", table "Private Passenger Auto Insurance Losses, 2015-2024" (source: ISO, a Verisk business), with its footnotes on expenses, deductible and excluded losses |
| Underinsured motorist limits | 215 ILCS 5/143a-2(4) (limits less amounts recovered from the at-fault driver's insurer) |
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
| Attorney involvement and litigation | Insurance Research Council, auto injury claims study (2026) and survey of claimants (2026) |
| Comparative fault | 735 ILCS 5/2-1116 (no recovery above 50% fault) |

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
autoins/simulate.py      term-by-term simulation: rating, retention, household changes, claims
autoins/claims.py        claim lifecycle: payments, reserves, claim detail, valuation cut-off
autoins/quotes.py        the new-business quote funnel
autoins/tables.py        output tables and answer key
output/                  where generate.py writes (ignored by git; published as releases)
reference/               ZIP reference data, vehicle catalogue, name lists
scripts/                 build reference/ from public sources; package release files in each format
                         (release_formats.py)
.github/workflows/       release workflow
tests/                   python -m unittest discover tests
```
