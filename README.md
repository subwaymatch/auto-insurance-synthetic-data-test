# Synthetic auto insurance data for Chicago and its suburbs

A seeded generator that produces a realistic personal auto insurance book for one fictional
carrier writing in the seven-county Chicago area (Cook, DuPage, Lake, Will, Kane, McHenry,
Kendall). It replaces an older synthetic dataset whose loss ratio (about 20%) and risk
relationships were not credible. [CHANGELOG.md](CHANGELOG.md) records every step taken to make
the data more realistic, and [docs/limitations.md](docs/limitations.md) collects everything it
still leaves out or simplifies, and what it should and should not be used for.

Everything about people, policies, premiums and claims is simulated. No record describes a
real person. The geography is real (ZIP codes, Census demographics, and Chicago police crash
and vehicle-theft counts), and so are the vehicles: every make, model and model year sold in
the US since 1997, weighted by how often each appears on Chicago's roads.

**The insurer.** "Lakefront" is a small regional group: three underwriting companies
(preferred, standard and non-standard) selling through independent agents, exclusive agents and
direct. The default book writes 43,368 policies over five years (2022 to 2026), about 24,000 of
them in force at the end with some 41,000 cars and $47 million of premium a year: roughly 1% of the
area's household vehicles. Read it as the Chicago-area part of a regional carrier, not a national one.

## Getting the data

The data is published as GitHub releases, not committed to the repository. The `latest`
release is rebuilt automatically whenever the generator changes on `main`:

| | CSV files | SQLite database |
|---|---|---|
| Student data | [chicago-auto-insurance-data-latest-csv.zip](https://github.com/subwaymatch/auto-insurance-synthetic-data-test/releases/download/latest/chicago-auto-insurance-data-latest-csv.zip) | [chicago-auto-insurance-data-latest-sqlite.zip](https://github.com/subwaymatch/auto-insurance-synthetic-data-test/releases/download/latest/chicago-auto-insurance-data-latest-sqlite.zip) |
| Instructor answer key | [chicago-auto-insurance-answer-key-latest-csv.zip](https://github.com/subwaymatch/auto-insurance-synthetic-data-test/releases/download/latest/chicago-auto-insurance-answer-key-latest-csv.zip) | [chicago-auto-insurance-answer-key-latest-sqlite.zip](https://github.com/subwaymatch/auto-insurance-synthetic-data-test/releases/download/latest/chicago-auto-insurance-answer-key-latest-sqlite.zip) |

Both formats hold the same data. The SQLite database is one file with every table, its primary and
foreign keys declared (see "SQLite database" below); the instructor's database also holds every data
table, linked to the answer key. Every zip also carries this README, the changelog and `docs/`; read
[docs/limitations.md](docs/limitations.md) before drawing conclusions from the data.

Versioned releases (`v1.0.0` and so on) are listed on the [releases page](https://github.com/subwaymatch/auto-insurance-synthetic-data-test/releases).
To look at the data without downloading it, browse [`samples/`](samples/README.md): the first 100
rows of every table. To build the data yourself, see below.

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

`generate.py` writes 23 CSV tables to `output/` and an instructor answer key to
`output/answer_key/` in about a minute. `output/` is ignored by git: the published copy of the
data is the releases above. `validate.py` re-reads those files and checks them
for record-level consistency (vehicle lifecycles, what was known when each term was rated, policy
dates, premium accounting, payments, every coverage's limits and deductibles, the vehicle catalogue
and the telematics programme) and against the calibration targets, including an approximate
comparison with national figures on their published definitions (the source does not publish every
counting rule, so the match is close but not exact).

| Option | Default | Meaning |
|---|---|---|
| `--seed` | `20250101` | Same seed and options give byte-identical files |
| `--policies` | `43368` | Distinct policies ever written (in-force book plus new business) |
| `--start` | `2022-01-01` | First day simulated |
| `--valuation` | `2026-12-31` | "As of" date of the extract; nothing later is known |
| `--out` | `output/` | Output folder |

The calibration targets are tuned for the default dates. Other windows between 2021 and 2026
work, but may land outside a tolerance band.

Library versions are pinned in `requirements.txt` because a newer numpy or pandas may draw
random numbers or format floats slightly differently, which would change the generated values.

## Releases and samples

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
  "Release dataset", then "Run workflow", and enter a tag (`v1.1.0`, or `1.1.0`: the `v` is added),
  seed, policy count and formats (default `csv,sqlite`). Re-running for an existing tag replaces
  that release's files.

Each release carries, for each format:

| File | Contents |
|---|---|
| `chicago-auto-insurance-data-<tag>-<format>.zip` | The tables, `run_summary.json`, this README, the changelog and `docs/`. Give this to students. |
| `chicago-auto-insurance-answer-key-<tag>-<format>.zip` | The answer key, `rating_plan.json` and the same documents. Instructors only. In the SQLite format the database also holds every data table, linked to the answer key. |

The formats are `csv` (one CSV file per table, about 57 MB zipped) and `sqlite` (one database with
every table, about 97 MB zipped and 300 MB unzipped for students; 114 MB and 347 MB for
instructors).

and once:

| File | Contents |
|---|---|
| `validation-report-<tag>.txt` | Full output of `validate.py` |
| `SHA256SUMS.txt` | Checksums |

To package the same files locally:

```bash
python scripts/package_release.py --data output --tag v1.0.0 --validation report.txt --dist dist --formats csv,sqlite
```

**Adding a format** (Parquet, Excel and so on) takes one function in
`scripts/release_formats.py`, registered under the format's name, plus its library in
`requirements-release.txt`; the file explains the pattern with examples. The workflow then
publishes it when its name is listed in the formats input.

The release fails if a test or an integrity check fails. Calibration bands only count for books of
20,000 policies or more; on smaller books they are reported as warnings, because a few hundred
claims are too few to hold them. The same seed and settings give byte-identical files on any
machine with the pinned library versions, so a release can always be rebuilt exactly.

**Samples.** `.github/workflows/samples.yml` builds the default dataset and commits the first 100
rows of every CSV file (every table, the answer key and the real portfolio in `real_data/`) to
[`samples/`](samples/README.md), so the data can be browsed on GitHub. It runs on every push to
`main` that changes the generator, its reference data or `real_data/`, and from the Actions tab
("Sample CSVs", "Run workflow"), where another number of rows can be chosen. Locally:

```bash
python scripts/make_samples.py --rows 100 --out samples synthetic=output real_data=real_data
```

## What the default run produces

| | |
|---|---|
| Policies / policy terms | 43,368 / 205,616 (19,848 of the terms were already in force on the start date) |
| Drivers / vehicles | 77,040 / 113,371 (3,616 drivers left a policy; 25,538 vehicles traded in, 5,335 sold, 7,975 destroyed or stolen, 1,283 taken by a leaving driver) |
| Vehicle models | 750 of the catalogue's 940 models (58 makes) are insured |
| Exposure rows / premium transactions | 460,536 (24.4% start at a mid-term change) / 280,654 (67,901 endorsements) |
| Earned exposure | 184,498 car-years |
| Earned premium | $189.7 million ($1,028 per car-year, $1,736 per policy-year) |
| Claims / coverage features / reserve transactions | 20,381 / 36,052 / 115,059 (43% of closed liability and medical features and 17% of closed physical damage features paid nothing) |
| Quotes | 124,106, of which 18.8% bound |
| Telematics | 12,607 enrolments and 56,491 driving scores; enrolled cars are 13% of car-years in 2022, rising to 25% in 2026 |

### Frequency and severity against national figures, like for like

The national figures are Triple-I's table of ISO data, "Private Passenger Auto Insurance Losses,
2015-2024". Its footnotes define them: paid claims per 100 earned car years, for all limits combined;
bodily injury and property damage severity **include loss adjustment expenses**; collision and
comprehensive are for coverage with a **$500 deductible**; and comprehensive **excludes wind and water
losses** (and includes glass). The comparison below puts this dataset on the same definitions: claims
are counted in the calendar year of their first loss payment, severity is that year's payments over
those claims, liability payments include the expense booked to the claim, collision and comprehensive
use only exposure rows with a $500 deductible, and comprehensive leaves out hail, wind, flood and
catastrophe claims.

| Coverage | Year | Claims per 100 car-years | National | Average paid | National |
|---|---|---|---|---|---|
| Bodily injury (with LAE) | 2022 | 0.38 | 0.70 | $18,232 | $24,681 |
| | 2023 | 0.79 | 0.78 | $22,637 | $26,178 |
| | 2024 | 0.86 | 0.80 | $30,647 | $28,278 |
| Property damage (with LAE) | 2022 | 2.54 | 2.54 | $6,372 | $6,024 |
| | 2023 | 2.92 | 2.59 | $7,026 | $6,554 |
| | 2024 | 2.87 | 2.50 | $6,984 | $6,770 |
| Collision ($500 deductible) | 2022 | 5.46 | 4.48 | $4,808 | $5,377 |
| | 2023 | 5.65 | 4.48 | $4,637 | $5,521 |
| | 2024 | 5.96 | 4.16 | $4,724 | $5,489 |
| Comprehensive ($500 deductible, no wind or water) | 2022 | 3.61 | 3.78 | $1,696 | $2,175 |
| | 2023 | 4.09 | 4.08 | $2,093 | $2,305 |
| | 2024 | 4.41 | 3.95 | $1,983 | $2,306 |

Over the years held to a band (2022 to 2024; 2023 and 2024 for bodily injury), frequency runs 1.05
times national for bodily injury, 1.09 for property damage, 1.30 for collision and 1.03 for
comprehensive, and severity 0.98, 1.05, 0.86 and 0.85 times national. `validate.py` prints this table
for any run and holds frequency to 0.85 to 1.45 times national and severity to 0.85 to 1.15 times.

What still differs, and how to read it:

- **Geography.** The national table covers the whole country (less a few states). This book is one
  metropolitan area, so it is tuned to run above national on frequency, most of all for collision.
  National figures set a reasonable scale. They are not a Chicago benchmark or a single carrier's
  experience, and nothing here has been checked against either.
- **Bodily injury in 2022.** The extract has no claims from accidents before its start date, so the
  first calendar year's payments are too few (injury claims take a year or more to settle). That
  year is shown but not held to a band.
- **Sampling.** A year has about 300 paid bodily injury claims and 600 comprehensive claims in the
  $500 slice, so single-year severities move 10% or more by chance (bodily injury in 2024, at 1.08
  times national, and comprehensive in 2022, at 0.78, are high and low in this run for that reason).
- **An older fleet.** Vehicles are about ten years old on average, as on Chicago's roads, so more
  collision and comprehensive claims are capped by a modest vehicle value; physical damage severity
  sits at the low end of its band.
- **Glass.** Glass claims under full glass cover carry no deductible here and are counted.
- **Counting rules.** The source does not publish how it counts a claim (per claimant or per accident,
  or when a claim counts as paid).

Whole-extract figures on the dataset's own basis (every deductible and cause, loss only), which
`validate.py` also holds to bands so that the book stays stable from seed to seed: bodily injury 0.76
paid claims per 100 car-years at $24,866; property damage 2.76 at $6,769; collision 5.29 at $4,921;
comprehensive 4.98 at $2,272. These are not comparable with the national table.

### Loss ratios

Loss ratio by accident year (net incurred losses excluding LAE as of the valuation date, over earned
premium), against industry pure loss ratios (incurred losses excluding LAE over earned premium, direct,
calendar year):

| | 2022 | 2023 | 2024 | 2025 | 2026 |
|---|---|---|---|---|---|
| This dataset, actual | 75.5% | 80.0% | 67.3% | 63.6% | 61.3% |
| This dataset, expected (answer key, free of claim luck; excludes catastrophes) | 78.8% | 75.2% | 66.2% | 63.9% | 65.1% |
| This dataset, catastrophe losses | 0.4% | 1.9% | 1.7% | 0.8% | 1.4% |
| US private passenger auto | 80.2% | 75.4% | 66.1% | 61.5% | 60.4% (Q1) |
| Illinois private passenger auto | 79.6% | 72.8% | 63.4% | 60.1% | |

The book enters 2022 under-priced, as the industry did after pandemic-era rate cuts, and rate
increases (+48% cumulative, close to the industry's +12.1% in 2022, +16.5% in 2023, +7.6% in 2024
and +3.7% in 2025) bring it back. Overall it runs 68.3%, against about 70% for the US and 68% for
Illinois over 2022 to 2025. The expected loss ratio plus each year's catastrophe losses is held to the
industry path by `validate.py`. Telematics discounts take 1.5% off the premium in 2022, rising to 3.0%
in 2026, so later years run a little above the industry figures. The actual figures move several points
a year on large injury claims alone (one standard deviation of a year's bodily injury total is 1.5 to 3
points of premium).
In this run 2022 came in below its expected (75.1% against 78.8%, both without catastrophes) and 2023
above it (78.1% against 75.2%); other seeds and sizes give different years their luck. `validate.py`
holds each full year's actual loss ratio, without catastrophes, to 0.85 to 1.15 times its expected one.
The 2026 figure is immature: young injury claims are reserved low and late-reported claims are missing.

These are pure loss ratios. Three different ratios are easy to confuse:

- **Pure loss ratio** (above): losses only.
- **Loss and LAE ratio**: add loss adjustment expense. The expense booked to individual claims in
  this dataset is 4.7% to 5.9% of premium for accident years 2022 to 2024 (`claim.paid_expense`, shown
  beside each year by `validate.py`). Industry LAE, which also includes claim department overhead not
  booked to any claim, ran 8.0% to 10.2% of premium in 2022 to 2025.
- **Combined ratio**: also adds commissions, other underwriting expenses and dividends. Nothing in
  this dataset supports one; do not compare these figures with combined ratios.

Sources: APCIA (2022), S&P Global Market Intelligence (2023 to 2026), Illinois Department of
Insurance market share reports, S&P Global RateWatch, AM Best, Texas DOI Insurance Expense Exhibit.

### Compared with a real insurer's data

[docs/real_data_comparison.md](docs/real_data_comparison.md) compares the book with a real motor
portfolio (a Spanish insurer, 2015 to 2018, published on Mendeley Data under CC BY 4.0 and kept in
[`real_data/`](real_data/mendeley_motor_portfolio/README.md)). Where the two can fairly be compared,
the synthetic data looks realistic: young and newly licensed drivers, urban vehicles and vehicle value
carry similar relativities, and claim costs and premiums spread in the same way. It also lists what the
synthetic data still lacks, most of all claims that drive customers away, risk behind the payment plan,
and the messiness of a real extract. Rerun it on any build:

```bash
python scripts/compare_real_data.py --synthetic output --real real_data/mendeley_motor_portfolio
```

## Tables

Table names are singular nouns and columns are lower-case `snake_case`; a key has the same name in
every table that holds it. [docs/schema_changes.md](docs/schema_changes.md) maps every table and
column of the previous layout (`risk_fact`, `claims_fact`, "Policy Number" and so on) to this one.

| File | One row per | Notes |
|---|---|---|
| `policy` | Policy | Location, agency, company, limits, insurance score, status, and the drivers and vehicles on it at its latest status |
| `policy_term` | Policy term (6 or 12 months) | Dates (including the rating date), cancellation, vehicles at the term start, written, endorsement, return and earned premium, rate level |
| `premium_transaction` | Premium transaction | New business, renewal, endorsement or cancellation, with effective and processed (accounting) dates and the written premium booked |
| `quote` | Quote | Every new-business quote, bound or not: prospect profile, quoted premium, the competing premium on independent-agent quotes, and the policy it became |
| `driver` | Driver | Demographics; violations and accidents in the 3 years before joining; good-student status when added; removed date and reason; SR-22 filing |
| `driver_incident` | Violation or at-fault accident | Motor vehicle record, prior carrier, or the company's own claim, with the conviction date and the date the insurer learned of it |
| `vehicle_model_year` | Make, model and model year | 8,750 model years of 940 models from 74 makes: body type, size class, segment, fuel, drive, engine, price new, VIN pattern and rating symbols |
| `insured_vehicle` | Insured vehicle | Its make, model and model year (`vehicle_model_year_id`), VIN prefix, use, mileage, parking, current coverages (including rental and towing) and deductibles, added and removed dates, why it left, the vehicle it replaced |
| `exposure` | Policy term, vehicle and endorsement period | Endorsement number and change reason, garaging location, rating date, rated characteristics and discounts (including telematics), the coverage terms in force (limits, deductibles, full glass, rental option, towing), premium by coverage, cover dates, earned exposure |
| `telematics_enrollment` | Enrolment in the telematics programme | Device, enrolment date, participation discount, when and why it ended |
| `telematics_score` | Vehicle and scoring period | Miles, trips, hard braking, rapid acceleration, speeding, phone use, night driving, the driving score and the discount it earned, and the term it applies to |
| `claim` | Claim | Loss, report and close dates, cause, police report, the insured's share of fault, fraud referral, paid, reserves, recoveries, expense, handling office |
| `claim_feature` | Coverage (and injured claimant) on a claim | Paid, case and expense reserves, salvage, subrogation, expense by type (DCC and A&O), uninsured or underinsured motorist type and the other insurer's payment, injury type, attorney and suit dates, reopen date, owner-retained salvage |
| `claim_payment` | Payment or recovery | Payment type and transaction type; supports paid development triangles |
| `claim_reserve_transaction` | Reserve change | Every change to a feature's loss or expense reserve, with the balance after it; with the payments, supports incurred development triangles |
| `location` | ZIP code | County, region, rating territories |
| `zip_demographics` | ZIP code | Census age, race and ethnicity, tenure, commuting |
| `agency`, `underwriting_company`, `claim_office` | | Fictional names |
| `catastrophe` | Catastrophe | Fictional hail, wind and flood events |
| `rate_change` | Rate change | Filed overall changes |
| `customer_contact` | Customer contact | Tied to renewals, policy changes, billing, cancellations and claims |

Keys: `policy_id`, `policy_term_id`, `driver_id`, `insured_vehicle_id`, `vehicle_model_year_id`,
`location_id`, `exposure_id`, `claim_id`, `claim_feature_id`, `enrollment_id`, `agency_id`,
`company_id`, `claim_office_id`. A claim's `involved_driver_id` is the insured driver involved, or the
named insured. `autoins/schema.py` lists every table's primary key and every foreign key; the SQLite
release declares them.

### SQLite database

The `sqlite` release format puts every table in one SQLite file, which any SQL tool opens (the `sqlite3`
command line, DB Browser for SQLite, DBeaver, DuckDB, Python's `sqlite3`, R's `RSQLite`):

- **Primary keys.** Every table has one, usually its `..._id` column (`zip_demographics` is keyed by
  `zip_code`, `rate_change` by `effective_date`, the answer key's `unreported_claim` by
  `unreported_claim_id`).
- **Foreign keys.** Every reference is declared, for example `claim.exposure_id` references
  `exposure.exposure_id` and `insured_vehicle.replaces_insured_vehicle_id` references
  `insured_vehicle.insured_vehicle_id`, so database tools draw the diagram, and every foreign-key column
  is indexed for fast joins. The build runs SQLite's `foreign_key_check` and `integrity_check` and fails
  if any reference does not resolve. A blank reference (a quote that never became a policy) is `NULL`.
- **Types.** Whole numbers are `INTEGER`, amounts and rates `REAL`, and dates (ISO `YYYY-MM-DD`), flags
  (`Y`/`N`), codes and ZIP codes `TEXT`.
- **Enforcement.** SQLite checks foreign keys on changes only when a connection asks:
  `PRAGMA foreign_keys = ON;`.
- **The instructor's database** holds every data table and the answer key in one file, linked: for
  example `exposure_truth.exposure_id` references `exposure.exposure_id`.

```sql
SELECT l.region, SUM(e.earned_exposure) AS car_years, SUM(e.earned_premium) AS premium
FROM exposure AS e JOIN location AS l ON l.location_id = e.location_id
GROUP BY l.region;
```

**Current versus historical values.** The dimensions describe each policy, driver and vehicle as it
stands at its latest status: on the valuation date if the policy is in force, otherwise on its last day
of cover. That covers `policy` (location, homeowner, named insured, limits, `number_of_drivers`,
`number_of_vehicles`) and the coverages on `insured_vehicle`. `exposure` is the effective-dated record:
each row keeps the location, rated characteristics, limits, deductibles, full glass, rental option,
towing and telematics discount that were in force for its dates. Use it, through `exposure_id`, for
anything historical. Joining a claim straight to `policy` gives today's address and limits, not those on
the loss date. `policy_term.vehicles_at_term_start` is the count when the term began (its endorsement 0
rows); `policy.number_of_vehicles` is the count now. For a policy in force the two differ whenever a car
was added or removed during the latest term.

**Vehicles.** `vehicle_model_year` is a catalogue, like the vehicle tables insurers license: one row for
every make, model and model year, whether or not this book insures one, including rare and exotic
models. Price new (`msrp`), the VIN pattern and both rating symbols belong to the model year, so they
live there; an insured vehicle points to its row. `exposure.model_year` repeats the model year as a
rated characteristic, and `exposure.vehicle_value` is the vehicle's actual cash value when rated.

## How it works

1. **Geography.** 290 real ZIP codes with Census demographics. Each has a crash hazard index
   and a theft hazard index (see "Sources").
2. **Households.** Policies are placed in ZIPs in proportion to vehicle-owning households.
   Drivers, vehicles and coverages are drawn from each ZIP's age, income, vehicle and
   commuting profile. Names follow the ZIP's Census make-up (see "Geography, names and race").
3. **Vehicles.** Each car's model year comes from a vehicle-age distribution tuned to the cars on
   Chicago's roads; its make and model are drawn among those sold that year, in proportion to how often
   they appear in Chicago crash records, with luxury and electric models commoner in richer households
   and pickups commoner where it is less dense (see "The vehicle catalogue").
4. **True risk.** Every driver has a hidden risk factor. Claim frequency depends on it and on
   age, experience, mileage, vehicle, parking and ZIP. Prior violations and accidents are
   generated from the same hidden factor, so they predict claims, imperfectly.
5. **Rating plan.** Premiums come from a rating plan that only sees what an insurer would see.
   It is fitted to the true expected loss cost, then deliberately distorted (see "What a case
   study can find").
6. **Policy life.** Each term is rated at the rate level in force, on a rating date before it
   starts, using only what the insurer knows by then. Customers renew or leave (more often
   after a price increase) or cancel mid-term. During a term households move, buy, sell and
   trade cars, add newly licensed teenagers and new spouses, and lose drivers who move out,
   divorce or die; each change is an endorsement that re-rates the policy from that day. At
   renewal loans are paid off, older cars drop collision and some customers raise deductibles.
7. **Telematics.** Customers are offered a usage-based programme, Lakefront DriveCheck, when a
   policy is written and at each renewal. Safer drivers are likelier to join; members are scored on
   their driving and earn renewal discounts (see "Telematics").
8. **Claims.** Losses are simulated by cause, then split into coverages with limits and
   deductibles applied. Each claim is developed as it happens: report and close dates,
   payments, expenses, salvage, subrogation, occasional reopenings, and a case reserve if
   still open.
9. **Valuation cut-off.** Payments after the valuation date have not happened, and claims not
   yet reported are left out, as in a real extract.

### The vehicle catalogue

`reference/vehicle_catalogue.csv` (published as `vehicle_model_year`) is built by
`scripts/build_vehicle_catalogue.py` from public data:

- **Which models exist.** The EPA and Department of Energy fuel economy list (fueleconomy.gov) has
  every light-duty car, SUV, pickup and passenger van sold in the US, by model year, with its size
  class, drive, engine and fuel. Its names are cleaned (2WD and 4WD versions and trims merged; cargo
  vans, hearses, limousines and test codes dropped; battery-electric versions of petrol models, such
  as the Kona Electric or F-150 Lightning, kept as their own models). Heavier vehicles EPA does not
  list (heavy-duty pickups, Hummer H1 and H2, Ford Excursion) come from
  `reference/vehicle_supplement.csv`.
- **How common each is.** The City of Chicago's Traffic Crashes - Vehicles records (2021 to 2025) give
  the make, model and model year of about 1.1 million vehicles in crashes. Only vehicles in personal
  use are counted (police cars, taxis, buses and delivery vans would otherwise inflate the Explorer,
  the Crown Victoria and the Transit). Each record is matched to a catalogue model and year; records
  naming a model the pick list lacks, or no model, are shared among the make's models the records never
  name, in proportion to a sales prior. A model's share of its model year is smoothed over neighbouring
  years, and models the records never mention keep a small floor weight, so even a Ferrari can turn up.
- **Prices and theft.** `reference/vehicle_curation.csv` holds approximate base prices (in 2024
  dollars) for about 900 models, theft factors shaped on published theft rankings, and corrections where
  EPA files a crossover as a car. Other models are priced from their class, make and engine. Each model
  year's price new grows 2.4% a year toward 2024.
- **Segments.** Seven rating segments (economy, mainstream, luxury, truck, sports, electric, minivan)
  come from size class, make, price and fuel; full-size body-on-frame SUVs rate with trucks.

To rebuild it (needs network access):

```bash
python scripts/fetch_public_data.py --only vehicles
```

```bash
python scripts/build_vehicle_catalogue.py
```

### Telematics

Lakefront DriveCheck (`autoins/telematics.py`) is a voluntary usage-based insurance programme of the
kind most US insurers now run:

- **Joining.** The programme is offered when a policy is written and at each renewal. About a fifth of
  new customers join in 2022, rising to 30% by 2025; existing customers join at about 2% a renewal.
  Households with a lower true at-fault propensity, younger named insureds and direct customers are
  likelier to join, so members are safer than average before any discount: favourable selection.
  Every quote offers it too: `quote.telematics_opt_in` shows who said yes, bound or not, and those
  quotes carry the participation discount.
- **Devices.** A phone app (most new members by 2026), a plug-in device or a windshield beacon, on
  every car on the policy.
- **Discounts.** 5% from the day a policy joins. At each rating date every monitored car is scored
  (1 to 100) on its driving since the last score: miles and trips, hard braking and rapid
  acceleration per 100 miles, the share of driving well over the speed limit, phone handling and
  late-night driving. The score earns a discount from the term being rated: none at 45 or below,
  rising evenly to 30% at 95 and above. Scores never raise the premium. A car added mid-term is
  monitored from the next renewal.
- **Leaving.** About one member in ten leaves the programme each year, more after poor scores; they keep
  the rated discount until the next renewal and are not offered the programme again for two years.
- **What the device sees.** The metrics are noisy readings of the primary driver's true at-fault
  propensity and of the car's true annual mileage, which the customer usually under-reports. So the
  score carries risk the rating plan cannot see.
- **Behaviour.** Being monitored makes people drive a little more carefully: at-fault crash frequency
  is 7% lower while a car is enrolled. The answer key's expected losses include it.

### Dates and timing

- **Opening book.** Policies in force on the start date enter with the term that spans it,
  which was written before the extract. Their exposure and premium count only from the start
  date: `earned_premium` is earned inside the extract, `earned_premium_before_extract` before it, and
  `exposure` gives each row's `coverage_start_date` (which can be before the start, as can
  `policy.first_effective_date`, the start of a policy's first term in the data). Policies already in
  the telematics programme then carry an enrolment date and a first score from before the start.
- **Anniversaries.** Policies can be written on any day, including the 29th to 31st. In a
  shorter month the term starts on the last day, and the next one returns to the original day
  (a policy written on 31 August renews on 28 or 29 February, then on 31 August).
- **What the insurer knows.** `policy_term.offer_date` is when a term was quoted: 30 to 45 days
  before a renewal (the renewal offer) and up to 14 days before new business. `rating_date` is when
  it was last rated: the offer date, unless the household changed between the offer and the
  effective date (a move, or a car or driver added or gone), in which case the pending renewal was
  re-rated on the day of the change and a revised offer sent (about 5% of renewals). Rating,
  underwriting non-renewals, telematics scores and the customer's renewal decision use only what
  is known by then. Drivers and cars on policies renewing on the start date joined them before the
  first rating in the data (at inception, on being licensed, or when the car was bought).
  `driver_incident.known_date` is when each incident became known: a violation when the conviction
  posts to the driving record (about two months), an earlier accident when it reaches a
  claims-history report, and the company's own at-fault claim the day after the payment that takes
  it to the $1,000 surcharge threshold. A claim that is reported or paid after a renewal's rating
  date first counts at the next renewal.
- **Order of events on one day.** The data holds dates, not times, so the order within a day is fixed
  by one rule, used by the simulation and by `validate.py` alike: a rating dated D uses every record
  whose `known_date` is D or earlier, and a loss or a payment on D can never have a `known_date` of
  D, because a company claim posts the day after its payment. A policy change rated on the day of
  an accident is therefore rated without that accident, whichever happened first that day. Cars that
  join a policy on different days of one term are rated in date order.
- **Household changes.** Mid-term changes happen on their own dates and each is an
  endorsement: the policy's exposure rows end that day and new rows, re-rated with what is known
  that day, start (`exposure.endorsement_number`, `change_reason`, `rating_date`). Rates come
  from public data: moves within the metro (5.5% of owners and 20% of renters move each year,
  73% within the metro; ACS 2024), divorce (12.9 per 1,000 married women) and marriage in Illinois
  (ACS 2024), mortality by age (CDC 2024), children leaving home (58% of 18-24s and 16% of 25-34s
  live with parents; CPS 2025), teen licensing ages (FHWA 2024), and vehicle ownership spells of
  five to six and a half years. A driver who leaves usually takes their own car.
- **Total losses.** A car destroyed or stolen ends its cover the day after the loss, whether the
  company pays a total loss (`removal_reason` = Total Loss) or not (Destroyed or Stolen: a car
  without collision cover, a loss the other driver's insurer paid, or a claim not pursued). About
  four in five households buy a replacement, which joins with a new `insured_vehicle_id`
  (`replaces_insured_vehicle_id` points back) when it is bought, about five weeks later on average. A
  one-car policy with no replacement is cancelled; one waiting for a replacement stays in force with
  no vehicle until it arrives. Claims on the old vehicle keep developing. The extract shows a
  removal as a total loss only once the company has that claim; until then the car is shown as
  destroyed or stolen, and a car lost on the valuation date itself is still on the policy.
  A few owners keep a car the company paid as a total loss (`owner_retained_salvage`); as Illinois
  law requires, only for hail damage or a car nine or more model years old. The salvage value
  comes off the settlement and the car loses physical damage cover at the next renewal.
- **Premium.** Changes mid-term are endorsements charged or returned pro rata to the end of the
  term. `premium_transaction` books each transaction on a processed date a few days after it
  takes effect; transactions not processed by the valuation date are not in the extract. For every
  finished term, written + endorsement + return premium = earned before the extract + earned
  premium, and the ledger adds up to the same.
- **Good student.** The discount applies while a driver with B grades is still in full-time
  school and under 25, judged on each term's effective date; `exposure.rated_good_student`
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
  1.12 to 1.21) while collision barely moves; payments erode reserves, closing releases them, and
  precautionary injury claims carry a nominal reserve. Litigated features also carry an expense
  reserve. `claim_reserve_transaction` records every change, so incurred can be rebuilt as of any date.
- **Claim detail.** About half of paid bodily injury claimants are represented by an attorney (57%
  industry-wide in 2022, Insurance Research Council), mostly within days or weeks of the accident.
  A litigated feature follows an ordered timeline: the attorney is retained, suit is filed after
  both that and the claim being presented and within Illinois' two-year limit, and the feature
  closes at least 30 days after the suit (a feature drawn to close sooner stays open longer).
  At-fault insureds are 51% to 100% at fault, as Illinois' modified comparative fault rule requires
  for a liability payment. `insured_fault_pct` describes the accident only: settlements are not
  reduced for the other party's share of fault (see "Assumptions and limits"). Injury type follows
  severity. Police reports, fraud referrals and SR-22 filings (three years after a DUI, driving while
  suspended or leaving the scene) are included.
- **Coverages and limits.** Every payment respects the terms on the exposure row it arose under, which
  `validate.py` checks coverage by coverage. Bodily injury and uninsured motorist payments are held
  to the per-person limit and, across an accident's claimants, to the per-accident limit, shared pro
  rata in whole cents so they total the limit exactly. Uninsured motorist cover includes underinsured
  motorist, as in Illinois (`um_uim_type` tells the two apart): when the at-fault driver's limit is
  too low, the policy pays each claimant's damages up to its per-person limit less what that
  driver's insurer paid (`other_insurer_payment`), and for the accident no more than its
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
behind the data: each exposure row's expected loss by coverage, each driver's hidden risk factor and
synthetic race and ethnicity, true mileage, true ZIP hazard, the full rating plan before and after
distortion, and the claims not yet reported. Withhold it from students: give them the data zip from a
release, not access to this repository, because anyone with the code can regenerate the answer key.

Deliberate and emergent findings in the default run:

| Finding | What the data shows |
|---|---|
| Young drivers are under-priced | Expected loss ratio 74% to 86% for classes under 25, against 68% for ages 25 to 64 |
| Mileage is under-used | Expected loss ratio rises from 64% under 5,000 reported miles to 83% at 16,000+ |
| Kia/Hyundai theft wave is unpriced | Whole-vehicle thefts per 1,000 comprehensive-covered vehicle-years for affected models peak at 10.2 in 2023, against 0.9 to 1.3 for others |
| Automatic emergency braking is unpriced | Expected loss ratio 65.7% with it, 71.0% without |
| Telematics members are safer than they are charged for | Enrolled cars run an expected loss ratio of 61.6%, against 70.3% for the rest; selection and the 7% behaviour effect can be separated only with the answer key |
| The telematics discount under-reacts to the score | Expected loss ratio 65% for cars earning 10% or less, 48% for those earning 21% to 30% |
| Telematics mileage exposes under-reporting | Annualised `telematics_score.miles_driven` is above the car's reported `insured_vehicle.annual_mileage` for two cars in three (10% above for the median car) |
| Rates lagged costs, then caught up | Expected loss ratio falls from 79% (2022) and 75% (2023) to 66% and 64% (2024, 2025), as the industry's did |
| Case reserves develop | Bodily injury incurred grows by 9% to 21% from 12 to 24 months as early, low reserves are corrected; collision moves 1% to 2% |
| New business is price-sensitive | Independent-agent quotes priced below the best competitor bind 36% of the time, those above 12% |
| Insurance score is priced roughly right | Premium per car-year falls by almost half from scores under 600 ($1,491) to 800 and above ($796); expected loss ratio drifts only from 66% to 71%, partly because telematics discounts go mostly to good-score customers |
| The newest year is not fully known | Late-reported claims are missing, open claims carry imperfect reserves, and closed claims can reopen |
| Price increases cost retention | Renewal probability falls with the size of the increase |
| Records reach the insurer late | A violation or chargeable claim shortly before a renewal's rating date is surcharged a term later |
| Exposure moves | Moves, trade-ins and new drivers change a policy's territory, vehicles and rated drivers mid-term; a vehicle's history spans several exposure rows and sometimes several ZIP codes |

Reported mileage is understated relative to true mileage, on-street parking raises theft and
hit-while-parked claims, and each ZIP has a hazard component the territories do not capture.

### Geography, names and race

Premiums are higher in ZIP codes with more non-white residents, because the real crash and theft data
behind the hazard indices is higher there. This follows real-world premium patterns and was left in
deliberately. The expected loss ratio barely varies with a ZIP's racial make-up: the model plants no
over- or under-charging by area. ZIP-level correlations say nothing about individuals, causes or
actuarial fairness, and a relationship planted in synthetic data is not evidence about how real
insurers price.

Names are realistic for the place and the person. Each household is given a synthetic race and
ethnicity group drawn from its ZIP code's Census mix (spouses share it about 90% of the time). Surnames
come from the Census 2010 surname table for that group, and first names from Social Security first-name
frequencies for the driver's sex and decade of birth, weighted to the group with Tzioumis' (2018) data
(`autoins/names.py`): a man born in the 1950s is likely a Robert or a David, a woman born in the 2000s an
Olivia or an Emily. The group is used for nothing else: risk,
prices and claims depend on ZIP-level crash and theft data and on the driver, never on it. It appears
only in the answer key (`driver_truth.race_ethnicity`), so instructors can set a fairness audit: estimate
each driver's race from surname and address with BISG (Bayesian Improved Surname Geocoding, the method
Colorado's rules for insurers under SB21-169 and the CFPB use), test premiums for disparate impact, and
check the estimates against the truth. A name works as a stand-in for race and ethnicity, which is
exactly why it must never be a rating variable. The first-name weights are statistical patterns in the
sources, with their limits: Tzioumis' shares come from adult mortgage applicants and are re-based to the
2010 population, not to each birth cohort, and about a third of names given since 2000 are missing from
that list and get the population's mix.

## Assumptions and limits

[docs/limitations.md](docs/limitations.md) collects these, the data's gaps and its appropriate uses in
one place, for sharing.

All assumptions live in `autoins/config.py` and `autoins/telematics.py`, each marked ANCHORED (published
figure), TUNED (set to hit an anchored target) or ASSUMED (judgement). The ones that matter most:

- **Suburban hazard is modelled, not observed.** Chicago's crash data covers the city only.
  Suburban ZIPs get the city's income gradient at an assumed lower level.
- **City hazard is damped.** Raw police-record rates vary about sevenfold across city ZIPs; an
  exponent narrows that to a range typical of rating territories.
- **Benchmarks are national**, not Illinois-specific or carrier-specific, and cost trends for 2025
  and 2026 are assumed. Frequency and severity are compared approximately on the national table's
  published definitions (see "Frequency and severity against national figures"), which shows the overall scale is
  reasonable. It does not validate anything finer: results by subgroup, how variables depend on
  each other, large-loss tails or local geography are assumed or tuned, not checked against data.
- **The rating plan is fitted to the truth.** Relativities are fitted directly to the simulator's
  true expected losses on the opening book, then distorted on purpose. A real carrier estimates its
  costs from noisy past losses, with filing and implementation lags, so the plan here is cleaner
  and more adequate than a real one. It is a teaching design, not evidence about a real carrier.
- **Vehicle popularity comes from crashes.** Model shares are measured on vehicles in Chicago crashes,
  which over-represent cars that are driven more and crash more, and city cars over suburban ones (the
  density tilt for pickups partly corrects this). The crash records' pick list lacks some models and
  mislabels others, so some shares rest on a sales prior. Prices are approximate base prices, used only
  to scale repair and total-loss costs and to set the price and symbol bands; a model year's engine,
  drive and body are its most common configuration.
- **Vehicle ages are tuned to Chicago.** About ten years on average in force, as on Chicago's roads in
  2021 to 2025; the US fleet average is a little older (about 12.6 years in 2024).
- **Fault is descriptive.** `insured_fault_pct` is drawn for each accident after its losses and does
  not change what is paid. Liability settlements are not reduced for a claimant's own share of fault,
  and there is no allocation of fault among several parties. Treat it as a scenario attribute, not
  as a comparative-negligence model.
- **No claims from before the start date.** Loss events begin on the start date, even for policies
  already in force. There is no opening inventory of open claims and no payments or reserve changes
  on earlier accident years. Development triangles for accident years 2022 onward are complete;
  whole-company calendar-year payments and reserves are not (the first calendar year pays too
  little). Moving the start date does not create that history.
- **The rate schedule is stylised**: +48% cumulative between April 2022 and March 2025, then a 2%
  cut in June 2026. Telematics discounts are not offset in the base rates.
- **Telematics is a stylised programme.** Take-up, discounts, drop-out, the score formula and the 7%
  behaviour effect are ASSUMED, shaped on published descriptions of US programmes. A member who leaves
  mid-term keeps the discount until the renewal, and the behaviour effect applies until then too.
- **Catastrophes are fictional.** Dates and footprints are plausible for northern Illinois but
  do not correspond to actual storms.
- **Household dynamics are partly sourced.** Mover, divorce, marriage, mortality, licensing and
  vehicle-ownership rates come from public data (see "Dates and timing"); how often households add
  or sell cars, how often a leaving driver takes a car, and the shapes by age are judgement calls.
  Income, insurance score, payment plan and multi-policy status stay fixed for a policy's life;
  liability limits change only at renewal, and homeowner status only with a move.
- **Report lags rest on one published study** (one insurer, 1996 to 2005). Lags beyond a year are
  probably understated there, so treat the IBNR tail as indicative.
- **Timing assumptions** (rating lead times, driving-record posting lags, replacement delays,
  payment patterns, endorsement processing lags) are judgement calls, marked ASSUMED in
  `autoins/config.py` and `autoins/claims.py`.
- **Identifiers and symbols are fictional.** VIN prefixes have the statistical-plan shape but begin
  with `0`, which no manufacturing region uses, and the vehicle symbols are this dataset's own scales,
  not ISO's licensed ones.
- **Claimants are not people.** A liability or injury feature has a claimant number within its claim,
  and `claim.involved_driver_id` is the insured driver involved. There is no table of third-party
  claimants who can be followed from one claim to another.
- **Not modelled:** fraud itself (only referrals), uninsured motorist property damage, billing and
  installment events, reinstatements, excluded drivers, separate mailing and garaging addresses,
  reinsurance, renewal offers that were declined, and the edit errors and out-of-sequence bookings of
  production data. The dataset is an analytical extract for teaching: it is not a model of a policy
  administration, billing or claims system.

## How it compares with an insurer's own data

The structure follows how insurers hold their data. `exposure` is the policy-level exposure
database actuaries build for ratemaking: one record per vehicle per period, split at mid-term
changes, carrying the characteristics in force (as in the CAS ratemaking text, Werner and Modlin).
`claim_feature` is one row per coverage and claimant, the grain of a claim system's
exposures and of NAIC market conduct claim counts. Claims link to the rating record they arose
under, as statistical plans require; payments, voids and recoveries form a transaction ledger; and
premium is booked as policy transactions with effective and accounting dates. `vehicle_model_year` is
the kind of make, model and model-year table insurers license for rating, and the telematics tables
hold what a usage-based programme records. Public alternatives are far thinner: French motor data
(`freMTPL2`) has one row per policy and undated claims, the CAS Loss Reserve Database holds
company-level triangles only, and the real portfolio in `real_data/` is a single table with one row per
vehicle per year (see "Compared with a real insurer's data").

It also has what reserving, claims and pricing work rely on: case reserve history (`claim_reserve_transaction`,
as in claim systems' reserve transactions and statistical plans' outstanding-loss records), expense
split into defence and cost containment versus adjusting and other with expense reserves, limits and
deductibles on each rating record, VIN prefixes and vehicle symbols (fictional, in the shape
statistical plans use), underinsured motorist, rental and towing coverages, claim detail (attorney and
suit dates, fault percentage, injury type, police report, fraud referral), applied discounts, SR-22
filings, telematics scores, and a quote funnel with quotes that never bound.

Real data would still have, and this dataset does not:

| Gap | Real-world source |
|---|---|
| Claims open on the start date and their later payments (an opening claim inventory) | Claim systems |
| Third-party claimants as people who can be followed across claims | Claim systems |
| Billing and installment events, reinstatements after a lapse | Billing systems |
| Renewal offers that were declined, with the offered premium | Policy systems |
| Excluded drivers; separate mailing and garaging addresses | Policy systems; statistical plans report the garaging ZIP |
| Uninsured motorist property damage; custom equipment and loan/lease gap coverages | Illinois coverage menu |
| Medical diagnosis codes, recovery reserves, fraud outcomes | Claim systems; Medicare Section 111 reporting |
| Trip-level telematics data and reinsurance | Telematics vendors; ceded statistical data |
| Edit errors, out-of-sequence bookings, missing values | Every production system |

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
| Vehicle makes, models and model years; size class, drive, engine, fuel | US EPA and Department of Energy, fuel economy data (fueleconomy.gov, `vehicles.csv`) |
| Vehicle popularity and vehicle age | City of Chicago Data Portal, Traffic Crashes - Vehicles (2021-2025, vehicles in personal use) |
| Surnames by race and ethnicity | US Census Bureau, Frequently Occurring Surnames from the 2010 Census |
| First names by sex, decade of birth and race and ethnicity | Social Security Administration national baby names (1880-2025); Tzioumis (2018), "Demographic aspects of first names", Scientific Data (Harvard Dataverse, CC0), re-based to the Census 2010 population mix |
| Frequency and severity benchmark | Triple-I, "Facts + Statistics: Auto insurance", table "Private Passenger Auto Insurance Losses, 2015-2024" (source: ISO, a Verisk business), with its footnotes on expenses, deductible and excluded losses |
| Real-portfolio comparison | Lledó and Pavía, "Dataset of an actual motor vehicle insurance portfolio", Mendeley Data v2 (2024), doi:10.17632/5cxyb5fp4f.2, CC BY 4.0 |
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

```bash
python scripts/build_vehicle_catalogue.py
```

```bash
python -I scripts/build_name_reference.py
```

ssa.gov refuses some automated downloads; if the name builder reports that, download
`https://www.ssa.gov/oact/babynames/names.zip` in a browser, save it as
`reference/_cache/ssa_names.zip` and run it again.

## Layout

```
generate.py              command-line entry point
validate.py              calibration and integrity report
autoins/config.py        every assumption
autoins/population.py    households, drivers, vehicles, coverages
autoins/names.py         driver names from ZIP-level Census make-up (used for nothing else)
autoins/truth.py         true frequency and severity, expected loss, claim simulation
autoins/rating.py        the insurer's rating plan
autoins/telematics.py    the Lakefront DriveCheck usage-based programme
autoins/simulate.py      term-by-term simulation: rating, telematics, retention, household changes, claims
autoins/claims.py        claim lifecycle: payments, reserves, claim detail, valuation cut-off
autoins/quotes.py        the new-business quote funnel
autoins/tables.py        output tables and answer key
autoins/schema.py        each table's primary key and foreign keys (declared in the SQLite release)
output/                  where generate.py writes (ignored by git; published as releases)
samples/                 first 100 rows of every table (written by the samples workflow)
reference/               ZIP reference data, vehicle catalogue and its curation, names
real_data/               a real motor insurance portfolio, for comparison (CC BY 4.0)
docs/                    limitations; comparison with the real portfolio; old-to-new schema map; review response
scripts/                 build reference/ from public sources; package releases (CSV, SQLite); samples; real-data comparison;
                         readme_figures.py prints the run figures the documentation quotes
.github/workflows/       release and samples workflows
tests/                   python -m unittest discover tests
CHANGELOG.md             what changed, and why, since the first version
```
