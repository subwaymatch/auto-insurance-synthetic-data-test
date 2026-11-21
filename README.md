# Synthetic auto insurance data for Chicago and its suburbs

A seeded generator that produces a realistic personal auto insurance book for one fictional
carrier writing in the seven-county Chicago area (Cook, DuPage, Lake, Will, Kane, McHenry,
Kendall). It replaces an older synthetic dataset whose loss ratio (about 20%) and risk
relationships were not credible. [CHANGELOG.md](CHANGELOG.md) records every step taken to make
the data more realistic, and [docs/limitations.md](docs/limitations.md) collects everything it
still leaves out or simplifies, and what it should and should not be used for.

Everything about people, policies, premiums and claims is simulated. No record describes a
real person. The geography is real (ZIP codes, Census demographics, and Chicago police crash
and vehicle-theft counts), and so are the vehicles (every make, model and model year sold in
the US since 1997, weighted by how often each appears on Chicago's roads) and the calendar
(crashes and thefts follow Chicago's own counts day by day, so Fridays, holidays and snow days
are where they really fell).

**The insurer.** "Lakefront" is a small regional group: three underwriting companies
(preferred, standard and non-standard) selling through 120 independent agencies (most of them small),
14 exclusive agents' offices and direct. The default book writes 43,368 policies over five years (2022
to 2026), about 22,600 of them in force at the end with some 39,000 cars and $54 million of premium a
year: roughly 1% of the area's household vehicles. Read it as the Chicago-area part of a regional
carrier, not a national one.

**Built to look like an operating company's data.** Policies, claims and vehicles carry business
keys (a policy number with check digits, a claim number, a full VIN with a valid check digit).
Staff, banks and courts work business days only. Discounts are filed as round percentages and are
only roughly right. New customers, installment payers and some agencies cost more than they are
charged. Quotes and new business follow the season and the company's prices against the market's, and
customers who have had a claim leave more often. Every premium is billed and collected, every claim
payment has a payee, a check number and an approver, and a general ledger adds the subledgers up
month by month. Premiums by coverage sit close to Illinois' published averages. See "What a case study
can find".

## Getting the data

The data is published as GitHub releases, not committed to the repository. The `latest`
release is rebuilt automatically whenever the generator changes on `main`:

| | CSV files | SQLite database | Parquet files |
|---|---|---|---|
| Student data | [chicago-auto-insurance-data-latest-csv.zip](https://github.com/subwaymatch/auto-insurance-synthetic-data-test/releases/download/latest/chicago-auto-insurance-data-latest-csv.zip) | [chicago-auto-insurance-data-latest-sqlite.zip](https://github.com/subwaymatch/auto-insurance-synthetic-data-test/releases/download/latest/chicago-auto-insurance-data-latest-sqlite.zip) | [chicago-auto-insurance-data-latest-parquet.zip](https://github.com/subwaymatch/auto-insurance-synthetic-data-test/releases/download/latest/chicago-auto-insurance-data-latest-parquet.zip) |
| Instructor answer key | [chicago-auto-insurance-answer-key-latest-csv.zip](https://github.com/subwaymatch/auto-insurance-synthetic-data-test/releases/download/latest/chicago-auto-insurance-answer-key-latest-csv.zip) | [chicago-auto-insurance-answer-key-latest-sqlite.zip](https://github.com/subwaymatch/auto-insurance-synthetic-data-test/releases/download/latest/chicago-auto-insurance-answer-key-latest-sqlite.zip) | [chicago-auto-insurance-answer-key-latest-parquet.zip](https://github.com/subwaymatch/auto-insurance-synthetic-data-test/releases/download/latest/chicago-auto-insurance-answer-key-latest-parquet.zip) |

All three formats hold the same data. The SQLite database is one file with every table, its primary and
foreign keys declared (see "SQLite database" below); the instructor's database also holds every data
table, linked to the answer key. The Parquet release is one file per table, a quarter of the size of the
CSV files and much quicker to load, with column types already set (see "Parquet files" below). Every zip also carries this README, the changelog and `docs/`; read
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

`generate.py` writes 32 CSV tables to `output/` and an instructor answer key (9 tables and the
rating plan) to `output/answer_key/` in about a minute and a half. `output/` is ignored by git: the
published copy of the data is the releases above. `validate.py` re-reads those files and checks them
for record-level consistency (vehicle lifecycles, what was known when each term was rated, policy
dates, premium accounting, payments, every coverage's limits and deductibles, the vehicle catalog,
the telematics program, identifiers and their check digits, the working calendar, billing against
the premium ledger and the cash, check numbers and payment approvals, and the general ledger against
every subledger) and against the calibration targets, including an approximate comparison with
national figures on their published definitions (the source does not publish every counting rule, so
the match is close but not exact) and with Illinois' average premiums by coverage.

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
  seed, policy count and formats (default `csv,sqlite,parquet`). Re-running for an existing tag replaces
  that release's files.

Each release carries, for each format:

| File | Contents |
|---|---|
| `chicago-auto-insurance-data-<tag>-<format>.zip` | The tables, `run_summary.json`, this README, the changelog and `docs/`. Give this to students. |
| `chicago-auto-insurance-answer-key-<tag>-<format>.zip` | The answer key, `rating_plan.json` and the same documents. Instructors only. In the SQLite format the database also holds every data table, linked to the answer key. |

The formats are `csv` (one CSV file per table, about 97 MB zipped and 419 MB unzipped), `sqlite`
(one database with every table, about 164 MB zipped and 536 MB unzipped for students; 183 MB
and 589 MB for instructors) and `parquet` (one Parquet file per table, about 70 MB zipped and 103 MB
unzipped; 10 MB and 15 MB for the answer key). The two billing tables are about a third of each. See
"File sizes, and a smaller build for the classroom" below.

and once:

| File | Contents |
|---|---|
| `validation-report-<tag>.txt` | Full output of `validate.py` |
| `SHA256SUMS.txt` | Checksums |

To package the same files locally:

```bash
python scripts/package_release.py --data output --tag v1.0.0 --validation report.txt --dist dist --formats csv,sqlite,parquet
```

(The Parquet format needs `pip install -r requirements-release.txt`.)

**Adding a format** (Excel and so on) takes one function in
`scripts/release_formats.py`, registered under the format's name, plus its library in
`requirements-release.txt`; the file explains the pattern, and the Parquet exporter is an example. The
workflow then publishes it when its name is listed in the formats input.

The release fails if a test or an integrity check fails. Calibration bands only count for books of
20,000 policies or more; on smaller books they are reported as warnings, because a few hundred
claims are too few to hold them. The same seed and settings give byte-identical files on any
machine with the pinned library versions, so a release can always be rebuilt exactly.

**Provenance.** `run_summary.json` records the seed, size and dates, the row counts, hashes of the CSV
files (`tables_hash` for the data tables, `answer_key_hash` for the answer key, `content_hash` for both;
`hash_method` says how they are computed) and, under `build`, the generator's source revision (and whether
its files had uncommitted changes), the Python, NumPy and pandas versions, a fingerprint of every table's
columns and of each reference file. Nothing in it depends on when or where the run happened.
`validate.py` recomputes the hashes, so a copied output folder can be checked on its own.

**Samples.** `.github/workflows/samples.yml` builds the default dataset and commits the first 100
rows of every CSV file (every table, the answer key and the real portfolio in `real_data/`) to
[`samples/`](samples/README.md), so the data can be browsed on GitHub. It runs on every push to
`main` that changes the generator, its reference data or `real_data/`, and from the Actions tab
("Sample CSVs", "Run workflow"), where another number of rows can be chosen. Locally:

```bash
python scripts/make_samples.py --rows 100 --out samples synthetic=output real_data=real_data
```

### File sizes, and a smaller build for the classroom

The default build is 419 MB of CSV. That is small for Python, R, SQL or Power BI, and awkward for
Excel: `exposure` (443,000 rows, 104 MB), `billing_invoice` (888,000 rows, 100 MB) and
`billing_receipt` (897,000 rows, 55 MB) are most of it, and although no table passes Excel's 1,048,576
rows, the billing tables come close. Three ways to make it lighter without leaving anything out:

- **Parquet, for anyone working in code.** The Parquet release is 103 MB unzipped (70 MB to download)
  and loads every table in half a second, against eight seconds for the CSV files; pandas, R's `arrow`,
  Polars, DuckDB and Power BI read it. Excel does not (see "Parquet files").

- **A smaller book.** `--policies` scales everything together, and a smaller book is still one
  consistent company: the ledger ties, every key resolves, the same findings are there.

```bash
python generate.py --policies 10000 --out classroom
```

  That takes about 20 seconds and writes 97 MB of CSV (23 MB zipped); its largest table has 209,000
  rows and the claim table about 5,000. All integrity checks pass. The price is noise: with a quarter of
  the claims, loss ratios and small segments move more from seed to seed, a few agencies have no
  customers, and `validate.py` reports calibration misses as warnings below 20,000 policies. The release
  workflow builds any size from the Actions tab (see above).
- **A shorter window.** `--valuation 2024-12-31` keeps three years instead of five, at full size.

| Build | CSV | Zipped CSV | Parquet | Zipped Parquet | Largest table | Claims |
|---|---|---|---|---|---|---|
| Default (43,368 policies) | 419 MB | 97 MB | 103 MB | 70 MB | 897,000 rows | 22,392 |
| `--policies 10000` | 97 MB | 23 MB | 27 MB | 19 MB | 209,000 rows | about 5,200 |

## What the default run produces

| | |
|---|---|
| Policies / policy terms | 43,368 / 198,479 (19,745 of the terms were already in force on the start date) |
| Policies in force at each year end | 19,745 at the start; 20,429 (2022), 20,089 (2023), 20,261 (2024), 21,475 (2025), 22,640 (2026) |
| Drivers / vehicles | 76,787 / 110,309 (3,438 drivers left a policy; 24,123 vehicles traded in, 5,215 sold, 6,209 destroyed or stolen, 1,188 taken by a leaving driver) |
| Vehicle models | 746 of the catalog's 940 models (59 makes) are insured |
| Exposure rows / premium transactions | 442,749 (23.9% start at a mid-term change) / 269,766 (62,038 endorsements) |
| Earned exposure | 176,758 car-years |
| Earned premium | $220.8 million ($1,249 per car-year, $2,132 per policy-year) |
| Claims / coverage features / reserve transactions | 22,392 / 39,173 / 124,306 (43% of closed liability and medical features and 16% of closed physical damage features paid nothing) |
| Claim payments | 60,542 rows, 19,247 of them checks in one unbroken number sequence; 684 vendors; 46 claims staff |
| Quotes | 117,297, of which 19.9% bound (21.9% in 2022, 17.5% in 2024, 21.2% in 2026) |
| Renewal offers | 171,979 (155,111 renewed, 10,500 not renewed by the insured, 1,000 company non-renewals, 1,399 canceled before the renewal date, 3,969 pending at the valuation date) |
| Bills / receipts | 887,706 / 896,585 (865,663 bills paid, 11,346 canceled, 3,434 written off, 7,263 open at the valuation date) |
| Commission | $17.4 million on $249.5 million of written premium (independent agents 11.4%, exclusive agents 8.4%, direct none); 7,885 monthly agency statements |
| General ledger | 19 accounts; 1,605 monthly journals (4,193 lines) for the three companies |
| Telematics | 12,412 enrollments and 61,537 driving scores; enrolled cars are 14% of car-years in 2022, rising to 26% in 2026 |

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

**Salvage and subrogation come off collision and comprehensive payments in this comparison.** The table
does not say whether they do, and it matters: a quarter of what is paid on collision claims comes back.
They are taken off here for two reasons. Insurers report recoveries to statistical agents as negative
paid losses. And Verisk's own report on the same data (2024 Executive Insights: Personal Auto) puts
collision severity at a $500 deductible at $6,951 for the year to March 2024, with salvage and
subrogation offsetting 10.1% and 14.0% of collision payments; what is left is about the $5,500 the
table shows. That report's figures are developed accident-year ones, so the match is not exact, and the
reading is an assumption. It is the reading under which the dataset's payments, loss ratios and
Illinois' average premiums (below) agree with each other: compared before recoveries, collision
premiums came out a third below Illinois'.

| Coverage | Year | Claims per 100 car-years | National | Average paid | National |
|---|---|---|---|---|---|
| Bodily injury (with LAE) | 2022 | 0.40 | 0.70 | $19,528 | $24,681 |
| | 2023 | 0.70 | 0.78 | $23,120 | $26,178 |
| | 2024 | 0.88 | 0.80 | $25,811 | $28,278 |
| Property damage (with LAE) | 2022 | 2.60 | 2.54 | $6,091 | $6,024 |
| | 2023 | 2.76 | 2.59 | $6,584 | $6,554 |
| | 2024 | 2.74 | 2.50 | $7,060 | $6,770 |
| Collision ($500 deductible, net of recoveries) | 2022 | 5.51 | 4.48 | $5,479 | $5,377 |
| | 2023 | 5.78 | 4.48 | $5,131 | $5,521 |
| | 2024 | 5.79 | 4.16 | $5,000 | $5,489 |
| Comprehensive ($500 deductible, no wind or water, net of recoveries) | 2022 | 4.61 | 3.78 | $2,294 | $2,175 |
| | 2023 | 4.88 | 4.08 | $2,459 | $2,305 |
| | 2024 | 4.64 | 3.95 | $2,253 | $2,306 |

Over the years held to a band (2022 to 2024; 2023 and 2024 for bodily injury), frequency runs 1.00
times national for bodily injury, 1.06 for property damage, 1.30 for collision and 1.20 for
comprehensive, and severity 0.90, 1.02, 0.95 and 1.03 times national. `validate.py` prints this table
for any run and holds frequency to 0.85 to 1.45 times national and severity to 0.85 to 1.15 times.

What still differs, and how to read it:

- **Geography.** The national table covers the whole country (less a few states). This book is one
  metropolitan area, so it is tuned to run above national on frequency, most of all for collision.
  National figures set a reasonable scale. They are not a Chicago benchmark or a single carrier's
  experience, and nothing here has been checked against either.
- **Bodily injury in 2022.** The extract has no claims from accidents before its start date, so the
  first calendar year's payments are too few (injury claims take a year or more to settle). That
  year is shown but not held to a band.
- **Sampling.** A year has 240 to 300 paid bodily injury claims and 700 comprehensive claims in the
  $500 slice, so single-year severities move 10% or more by chance.
- **An older fleet.** Vehicles are about nine years old on average, as on Chicago's roads, so more
  collision claims end as total losses than nationally (30% of paid collision claims, against the 22%
  to 23% of all appraisals that CCC reports for 2024 and 2025).
- **Glass.** Glass claims under full glass cover carry no deductible here and are counted.
- **Counting rules.** The source does not publish how it counts a claim (per claimant or per accident,
  or when a claim counts as paid).

Whole-extract figures on the dataset's own basis (every deductible and cause, loss only), which
`validate.py` also holds to bands so that the book stays stable from seed to seed: bodily injury 0.76
paid claims per 100 car-years at $24,779; property damage 2.68 at $6,624; collision 5.33 at $6,738;
comprehensive 5.66 at $2,790. These are not comparable with the national table.

### Premiums and coverage against Illinois

The NAIC's Auto Insurance Database gives each state's average premium per insured car-year by coverage
and the share of insured cars carrying collision and comprehensive. Against Illinois:

| | 2022 | 2023 | 2024 | Illinois 2022 | 2023 | 2024 |
|---|---|---|---|---|---|---|
| Liability (bodily injury, property damage, uninsured motorist, medical payments) | $550 | $620 | $722 | $524 | $598 | $649 |
| Collision, per car carrying it | $332 | $377 | $443 | $384 | $440 | $473 |
| Comprehensive, per car carrying it | $167 | $191 | $223 | $172 | $219 | $261 |

Collision is carried on 83.5% of 2023 car-years and comprehensive on 88.4% (Illinois: 82.6% and 87.5%).
Liability runs 7% above the state over the three years and collision and comprehensive 11% below.
`validate.py` holds each to a band around the state's figure. The book is the Chicago area and one
carrier, not the state, so an exact match is not the aim; the point is that a student comparing these
premiums with public figures finds them in the right place.

What a car is worth drives the physical damage figures. A car's value is its model year's base price
run down a depreciation curve and lifted by each year's used-car prices (the Manheim index: half as
high again as before the pandemic in 2022, a third higher since 2024). The average insured car is worth
$15,700 in 2022 and $14,500 in 2024; a ten-year-old car about 40% of its base price. Paid collision
claims average $6,542 ($4,896 for repairs and $10,414 for the 30% that are total losses), with salvage
returning 10.9% and subrogation 13.1% of what is paid.

### Loss ratios

Loss ratio by accident year (net incurred losses excluding LAE as of the valuation date, over earned
premium), against industry pure loss ratios (incurred losses excluding LAE over earned premium, direct,
calendar year):

| | 2022 | 2023 | 2024 | 2025 | 2026 |
|---|---|---|---|---|---|
| This dataset, actual | 80.1% | 72.5% | 66.5% | 61.2% | 62.4% |
| This dataset, expected (answer key, free of claim luck; excludes catastrophes) | 79.8% | 75.5% | 65.2% | 62.6% | 63.8% |
| This dataset, catastrophe losses | 0.6% | 2.4% | 1.9% | 1.0% | 1.5% |
| US private passenger auto | 80.2% | 75.4% | 66.1% | 61.5% | 60.4% (Q1) |
| Illinois private passenger auto | 79.6% | 72.8% | 63.4% | 60.1% | |

The book enters 2022 under-priced, as the industry did after pandemic-era rate cuts, and rate
increases (+48% cumulative, close to the industry's +12.1% in 2022, +16.5% in 2023, +7.6% in 2024
and +3.7% in 2025) bring it back. Overall it runs 67.4%, against about 70% for the US and 68% for
Illinois over 2022 to 2025. The expected loss ratio plus each year's catastrophe losses is held to the
industry path by `validate.py`. Telematics discounts take 1.7% off the premium in 2022, rising to 3.4%
in 2026, so later years run a little above the industry figures. The actual figures move several points
a year on large injury claims alone (one standard deviation of a year's bodily injury total is 1.3 to 2.0
points of premium).
In this run every full year came in at or below its expected (2022: 79.5% against 79.8%, both without
catastrophes; 2023: 70.0% against 75.5%); other seeds and sizes give different years their luck. `validate.py`
holds each full year's actual loss ratio, without catastrophes, to 0.85 to 1.15 times its expected one.
The 2026 figure is immature: young injury claims are reserved low and late-reported claims are missing.

These are pure loss ratios. Three different ratios are easy to confuse:

- **Pure loss ratio** (above): losses only.
- **Loss and LAE ratio**: add loss adjustment expense. The expense booked to individual claims in
  this dataset is 3.6% to 5.5% of premium for accident years 2022 to 2024 (`claim.paid_expense`, shown
  beside each year by `validate.py`). Industry LAE, which also includes claim department overhead not
  booked to any claim, ran 8.0% to 10.2% of premium in 2022 to 2025.
- **Combined ratio**: also adds commissions, other underwriting expenses and dividends. The general
  ledger holds commission (about 7% of earned premium) but no other underwriting expense, so nothing in
  this dataset supports one; do not compare these figures with combined ratios.

Sources: APCIA (2022), S&P Global Market Intelligence (2023 to 2026), Illinois Department of
Insurance market share reports, S&P Global RateWatch, AM Best, Texas DOI Insurance Expense Exhibit.

### Compared with a real insurer's data

[docs/real_data_comparison.md](docs/real_data_comparison.md) compares the book with a real motor
portfolio (a Spanish insurer, 2015 to 2018, published on Mendeley Data under CC BY 4.0 and kept in
[`real_data/`](real_data/mendeley_motor_portfolio/README.md)). Where the two can fairly be compared,
the synthetic data looks realistic: young and newly licensed drivers, urban vehicles and vehicle value
carry similar relativities, and claim costs and premiums spread in the same way. Installment payers, newer
customers and independent-agent business run worse in both books, more strongly in the real one, and a
contract with a claim is more likely to end (1.45 times as likely in the real book, 1.40 in this one). It
also lists what the synthetic data still lacks, most of all the messiness of a real extract. Rerun it on
any build:

```bash
python scripts/compare_real_data.py --synthetic output --real real_data/mendeley_motor_portfolio
```

## Tables

Table names are singular nouns and columns are lower-case `snake_case`; a key has the same name in
every table that holds it. [docs/schema_changes.md](docs/schema_changes.md) maps every table and
column of the previous layout (`risk_fact`, `claims_fact`, "Policy Number" and so on) to this one.

| File | One row per | Notes |
|---|---|---|
| `policy` | Policy | Policy number, location, agency and producer, company, limits, insurance score, status, and the drivers and vehicles on it at its latest status |
| `policy_term` | Policy term (6 or 12 months) | Dates (including the rating date), cancellation, vehicles at the term start, written, endorsement, return and earned premium, rate level |
| `premium_transaction` | Premium transaction | New business, renewal, endorsement or cancellation, with effective and processed dates (the later of the two is the accounting date), the written premium booked, and the commission rate and amount |
| `billing_invoice` | Bill | Each bill sent: paid in full, down payment, installment, endorsement or final balance; issue and due dates, premium, installment and late fees, status (paid, open, canceled, written off), paid and write-off dates |
| `billing_receipt` | Cash movement | Each payment received (with its method), bank draft returned unpaid, and refund, tied to its bill |
| `quote` | Quote | Every new-business quote, bound or not: quote number, prospect profile, quoted premium, the competing premium on independent-agent quotes, and the policy it became |
| `driver` | Driver | Driver number on the policy, demographics, license state and masked license number; violations and accidents in the 3 years before joining; good-student status when added; removed date and reason; SR-22 filing |
| `driver_incident` | Violation or at-fault accident | Motor vehicle record, prior carrier, or the company's own claim, with the conviction date and the date the insurer learned of it |
| `vehicle_model_year` | Make, model and model year | 8,750 model years of 940 models from 74 makes: body type, size class, segment, fuel, drive, engine, price new, VIN pattern and rating symbols |
| `insured_vehicle` | Insured vehicle | Unit number on the policy, make, model and model year (`vehicle_model_year_id`), VIN, use, mileage, parking, current coverages (including rental and towing) and deductibles, added and removed dates, why it left, the vehicle it replaced |
| `exposure` | Policy term, vehicle and endorsement period | Endorsement number and change reason, garaging location, rating date, rated characteristics and discounts (including telematics), the coverage terms in force (limits, deductibles, full glass, rental option, towing), premium by coverage, cover dates, earned exposure |
| `telematics_enrollment` | Enrollment in the telematics program | Device, enrollment date, participation discount, when and why it ended |
| `telematics_score` | Vehicle, driver and scoring period | Miles, trips, hard braking, rapid acceleration, speeding, phone use, night driving, the driving score and the discount it earned, and the term it applies to |
| `renewal_offer` | Renewal evaluated (renewed or not) | Offer date, vehicles offered, expiring and renewal premium for a full term, premium change, telematics opt-in, underwriting decision, revised offer date, outcome, and the term it renewed into |
| `claim` | Claim | Claim number, loss date and time, report and close dates, cause, police report, the insured's share of fault, fraud referral, paid, reserves, recoveries, expense, handling office and adjuster |
| `claim_feature` | Coverage (and injured claimant) on a claim | Feature number, paid, case and expense reserves, salvage, subrogation, expense by type (DCC and A&O), uninsured or underinsured motorist type and the other insurer's payment, injury type, attorney and suit dates, reopen date, owner-retained salvage |
| `claim_payment` | Payment or recovery | Payment type and transaction type; payee type and name, vendor, method (check, EFT or deposit), check number, status (cleared, outstanding, voided) and cleared date, and who approved it; supports paid development triangles |
| `claim_reserve_transaction` | Reserve change | Every change to a feature's loss or expense reserve, with the balance after it; with the payments, supports incurred development triangles |
| `employee` | Claims employee | Adjusters, supervisors, the claims manager and investigators: office, title, hire and termination dates, payment authority, supervisor |
| `vendor` | Vendor | Body shops, glass, rental and towing companies, medical providers, appraisers, law firms, salvage auctions, lienholders and other insurers (all fictional), with type, place and repair-network flag |
| `location` | ZIP code | County, region, rating territories |
| `zip_demographics` | ZIP code | Census age, race and ethnicity, tenure, commuting |
| `agency`, `producer` | Agency; producer | Agency code, channel, place, appointment date and commission rates; the licensed agents at each agency, its owner first |
| `agency_statement` | Agency and month | The written premium and commission an agency's business booked in the month, and the day the commission was paid |
| `gl_account` | General ledger account | The chart of accounts: number, name, type, normal balance, financial statement |
| `gl_journal` | Journal line | Monthly journal entries by underwriting company: accounting period, posting date, journal type, the subledger table it summarizes, account, debit and credit |
| `underwriting_company`, `claim_office` | | Fictional names; each company's code and NAIC-style number |
| `catastrophe` | Catastrophe | Fictional hail, wind and flood events |
| `rate_change` | Rate change | Filed overall changes |
| `customer_contact` | Customer contact | Tied to renewals, policy changes, billing (past-due and cancellation notices), cancellations and claims |

Keys: `policy_id`, `policy_term_id`, `driver_id`, `insured_vehicle_id`, `vehicle_model_year_id`,
`location_id`, `exposure_id`, `claim_id`, `claim_feature_id`, `enrollment_id`, `renewal_offer_id`, `agency_id`,
`producer_id`, `company_id`, `claim_office_id`, `employee_id`, `vendor_id`, `invoice_id`, `statement_id`,
`account_number`. A claim's
`involved_driver_id` is the insured driver involved or, for a loss with no driver (a parked car, a theft, the
weather), the named insured on the loss date. `autoins/schema.py` lists every
table's primary key and every foreign key; the SQLite release declares them.

### Identifiers

Each record has two kinds of identifier, as in an insurer's warehouse:

- **Integer keys** (`..._id`) join the tables. They are numbered in the order records were created: a
  policy by the day it was written, a term by the day it was offered, a driver or vehicle by the day it
  joined, an exposure row by the day it was rated, a claim by the day it was reported. They say nothing
  else about a record.
- **Business keys** are what the company prints on documents:

| Key | Example | How it is built |
|---|---|---|
| `policy.policy_number` | `0830512-LFM-47` | A seven-digit serial issued in the order policies were written (the company issues them at a steady rate, so numbers track dates, with gaps for business outside this book), the underwriting company's code (`LFP`, `LFM`, `PPC`) and two check digits: read the letters as A = 10 to Z = 35, and the whole number leaves 1 when divided by 97, as an IBAN does |
| `quote.quote_number` | `Q24-0067681` | Year and a sequence |
| `claim.claim_number`, `claim_feature.feature_number` | `24-0022944`, `24-0022944-02` | Report year and a sequence; a feature adds its number on the claim |
| `insured_vehicle.vin` | `0B1PVGZY12M415986` | The catalog's 10-character pattern, a plant letter and a serial, with the standard check digit in position 9 (49 CFR 565). Position 1 is `0`, which no real manufacturer uses, so no VIN is a real car's |
| `insured_vehicle.unit_number`, `driver.driver_number` | `1`, `2` | Order on the policy |
| `driver.license_number_masked` | `M***-****-*725` | Masked, as analytic extracts hold it. It is not computed the way Illinois computes a real license number (from name, birth date and sex), so no synthetic driver carries a real person's number |
| `agency.agency_code`, `producer.producer_code` | `IL-04417`, `IL-04417-02` | |
| `claim_payment.check_number` | `3418207` | One unbroken sequence in the order checks were cut |
| `billing_invoice.invoice_number` | `INV-24-000512345` | Year and a sequence |

### Parquet files

The `parquet` release format is a zip of one Parquet file per table, named as the CSV files are
(`policy.parquet`, `exposure.parquet`, `claim.parquet` and so on; a Parquet file holds one table). The
data is the same; what differs is that the columns arrive typed:

- **Whole numbers** are 64-bit integers, null where blank, so a key that is sometimes blank
  (`quote.policy_id`, `policy.producer_id`) stays an integer.
- **Dates** (every column named `..._date` or `date_...`) are dates, not text. `claim.loss_time` and the
  ledger's `accounting_period` and `agency_statement.statement_month` stay text.
- **Amounts and rates** are doubles; **flags, codes and ZIP codes** are text.
- **Keys are not declared**: Parquet has no way to. The key list under "Tables" and `autoins/schema.py`
  say how the tables join; the SQLite database is the format that enforces it.

In Python, ask pandas to keep those types (by default it turns dates into plain objects and integers
with blanks into decimals):

```python
import pandas as pd
claim = pd.read_parquet("claim.parquet", dtype_backend="pyarrow")
claim.loss_date.dt.year.value_counts()
```

In R, `arrow::read_parquet("claim.parquet")` gives dates as `Date`. DuckDB and Polars read the files as
they are (`SELECT * FROM 'claim.parquet'`). The files use Snappy compression, which every Parquet
reader supports.

### SQLite database

The `sqlite` release format puts every table in one SQLite file, which any SQL tool opens (the `sqlite3`
command line, DB Browser for SQLite, DBeaver, DuckDB, Python's `sqlite3`, R's `RSQLite`):

- **Primary keys.** Every table has one, usually its `..._id` column (`zip_demographics` is keyed by
  `zip_code`, `rate_change` by `effective_date`, `billing_receipt` by `receipt_id`, the answer key's
  `unreported_claim` by `unreported_claim_id`).
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

**Vehicles.** `vehicle_model_year` is a catalog, like the vehicle tables insurers license: one row for
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
   Each household also has a hidden **stability**: how settled it is. Settled households own
   their homes, bundle other policies, have had continuous insurance, pay in full and stay
   longer, and they claim less and miss fewer payments (see "Hidden traits").
3. **Vehicles.** Each car's model year comes from a vehicle-age distribution tuned to the cars on
   Chicago's roads; its make and model are drawn among those sold that year, in proportion to how often
   they appear in Chicago crash records, with luxury and electric models commoner in richer households
   and pickups commoner where it is less dense (see "The vehicle catalog").
4. **True risk.** Every driver has a hidden risk factor. Claim frequency depends on it and on
   age, experience, mileage, vehicle, parking and ZIP, on the household's stability, on the channel
   and agency the policy came through, and on how new the customer is. Prior violations and
   accidents are generated from the same hidden factor, so they predict claims, imperfectly.
5. **Rating plan.** Premiums come from a rating plan that only sees what an insurer would see.
   Its discounts are filed as round percentages; the rest is fitted to the true expected loss
   cost, then deliberately distorted (see "The rating plan" and "What a case study can find").
6. **Policy life.** Each term is rated at the rate level in force, on a rating date before it
   starts, using only what the insurer knows by then. Customers renew or leave (more often
   after a price increase, after a claim, and when the company is dearer than the market) or cancel
   mid-term. New customers arrive as households shop and the company's quotes win them (see "The
   market"). During a term households move, buy, sell and
   trade cars, add newly licensed teenagers and new spouses, and lose drivers who move out,
   divorce or die; each change is an endorsement that re-rates the policy from that day. At
   renewal loans are paid off, older cars drop collision and some customers raise deductibles.
7. **Telematics.** Customers are offered a usage-based program, Lakefront DriveCheck, when a
   policy is written and at each renewal. Safer drivers are likelier to join; members are scored on
   their driving and earn renewal discounts (see "Telematics").
8. **Claims.** Losses are simulated by cause, on days that follow Chicago's daily crash and theft
   counts, then split into coverages with limits and deductibles applied. Each claim is developed
   as it happens: report and close dates, payments, expenses, salvage, subrogation, occasional
   reopenings, and a case reserve if still open.
9. **The working calendar.** Staff, banks and courts work business days: payments, closes, reserve
   reviews, suits, convictions, renewal offers and letters never fall on a weekend or a holiday
   (see "The working calendar").
10. **Billing and payments.** Every premium transaction is billed and collected (see "Billing and
    commission"), and every claim payment gets a payee, a method, a check number and an approver
    (see "Claim payments, vendors and staff").
11. **Identifiers.** Business keys are issued and the integer keys numbered in creation order (see
    "Identifiers").
12. **General ledger.** The premium, billing, commission and claim subledgers are summarized into
    monthly journal entries (see "The general ledger").
13. **Valuation cut-off.** Payments after the valuation date have not happened, and claims not
    yet reported are left out, as in a real extract.

### The rating plan

`answer_key/rating_plan.json` holds the whole plan. Two kinds of factor make it up:

- **Filed discounts and surcharges** (`autoins/config.py`, `FILED_DISCOUNTS`) are round percentages, as
  carriers file them, and are not fitted to anything:

| Factor | Filed | Applies to | What the risk would justify (bodily injury) |
|---|---|---|---|
| Multi-car | 10% discount | Liability, medical, collision, comprehensive | 7% |
| Multi-policy | 8% discount | The same | 6% |
| Homeowner | 5% discount | Liability, medical, collision | 1% |
| Paid in full | 6% discount | Liability, medical, collision, comprehensive | 8% |
| No prior insurance | 8% surcharge | Liability, medical, collision | None: the company these customers are placed with already charges for it |
| Tenure | 2%, 4% and 6% off at 1, 3 and 6 years | Liability, medical, collision, comprehensive | 12%, 18% and 21% |
| Good student | 10% discount | Bodily injury, property damage, medical, collision | None (1% more) |
| Married | 5% discount | The same | None (1% more) |

  "What the risk would justify" is `relativities_indicated` in the same file: every factor fitted freely to
  the true expected cost. A discount is a finding when the two differ.
- **Everything else** (driver class, record, insurance score, company, vehicle, mileage, use, territory) is
  fitted around the filed discounts to the true expected loss cost by minimum bias, then the planted
  distortions are applied (young drivers and drivers over 75 under-priced, mileage relativities flattened).

### The vehicle catalog

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
  the Crown Victoria and the Transit). Each record is matched to a catalog model and year; records
  naming a model the pick list lacks, or no model, are shared among the make's models the records never
  name, in proportion to a sales prior. A model's share of its model year is smoothed over neighboring
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

Lakefront DriveCheck (`autoins/telematics.py`) is a voluntary usage-based insurance program of the
kind most US insurers now run:

- **Joining.** The program is offered when a policy is written and at each renewal. About a fifth of
  new customers join in 2022, rising to 30% by 2025; existing customers join at about 2% a renewal.
  Households with a lower true at-fault propensity, younger named insureds and direct customers are
  likelier to join, so members are safer than average before any discount: favorable selection.
  Every quote offers it too: `quote.telematics_opt_in` shows who said yes, bound or not, and those
  quotes carry the participation discount.
- **Devices.** A phone app (most new members by 2026), a plug-in device or a windshield beacon, on
  every car on the policy.
- **Discounts.** 5% from the day a policy joins. At each rating date every monitored car on the
  policy that day is scored (1 to 100) on its driving since the last score: miles and trips, hard
  braking and rapid acceleration per 100 miles, the share of driving well over the speed limit, phone
  handling and late-night driving. The score earns a discount from the term being rated: none at 45 or
  below, rising evenly to 30% at 95 and above. Scores never raise the premium. A car added mid-term is
  monitored from the next renewal.
- **One score, one driver.** A score is the driving of the driver assigned to the car at the time (the
  exposure rows' rated driver). If the car's driver changed during the scoring period, the period is
  split there and each part scored as its own driver's (a part under 45 days earns no score); the car's
  discount is the average of the discounts its parts earned, weighted by days and rounded half up to a
  whole percent, or 5% if no part was monitored long enough.
- **Leaving.** About one member in ten leaves the program each year, more after poor scores; they keep
  the rated discount until the next renewal and are not offered the program again for two years.
- **What the device sees.** The metrics are noisy readings of the assigned driver's true at-fault
  propensity at the time and of the car's true annual mileage, which the customer usually under-reports. So the
  score carries risk the rating plan cannot see.
- **Behavior.** Being monitored makes people drive a little more carefully: at-fault crash frequency
  is 7% lower while a car is enrolled. The answer key's expected losses include it.

### Hidden traits

Three things the insurer cannot see drive much of what a case study can find. All are in the answer key.

- **Household stability** (`policy_truth.stability`, standard normal apart from the shifts below). It lowers
  claim frequency (about 26% per unit), raises the chance of renewing and of paying on time, and makes a
  household likelier to own its home, bundle, have had prior insurance, pay in full and, in the book in force
  at the start, to have been a customer for longer. The book in force at the start is more stable than new
  business (it has been selected by years of renewals), and exclusive-agent customers more than direct ones.
- **New customers claim more.** For the first weeks of a policy there is a burst of claims (damage that was
  already there, claims soon after buying cover), and for two or three years a slower fade as customers who
  shopped around settle in. Claims per 100 policy-years run 27.4 in a new policy's first 30 days, about 24 for
  the rest of its first year and 21 to 23 after that. The rating plan sees only its loyalty discount.
- **Agencies differ.** Each agency writes a better or worse book than its rating variables show
  (`agency_truth.book_quality_factor`), and keeps its customers better or worse (`retention_effect`).
  Independent agents place somewhat harder risks; direct customers shop more at renewal. Agencies also
  differ greatly in size, as a carrier's appointments do: the 120 independent agencies have a median of 47
  policies in force and the largest has 491; they wrote $23 million in 2026, a mean of $192,000 and a
  median of $116,000 each, and the largest tenth wrote 36% of it. The 14 exclusive agents' offices average
  437 policies. An independent agency is named for its owner, its town or a trade name; an exclusive
  agent's office carries the agent's name, and that person is its first producer.

### The working calendar

- **Losses** fall on days in proportion to Chicago's daily counts of crashes and of vehicle thefts
  (`reference/daily_index.csv`): 15.3% of crash claims happen on a Friday and 13.4% on a Sunday, and real
  bad-weather days stand out (11 crash claims on 14 January 2026, the worst day in Chicago's counts, against 5.7 on an average day). `claim.loss_time` is the time the insured reported:
  crashes peak in the late afternoon, thefts overnight, and minutes bunch on the hour and half hour.
- **First notice** arrives every day, but about half of a weekend's or a holiday's is held over: 21% of
  claims are reported on a Monday and 16% at a weekend.
- **Business days only** (weekdays that are not US federal holidays or the day after Thanksgiving): claim
  payments and their clearing, file closes, reserve reviews, suits, fraud referrals, convictions and their
  posting to the driving record, SR-22 filings, renewal offers, keyed policy changes and letters. Work that
  falls due on a weekend is spread over the following week, not piled on the Monday.
- **Quotes and new policies**: agents quote on weekdays (5% of agent quotes on a Saturday, 1.5% on a Sunday);
  the website quotes every day. 8.8% of new policies start on the 1st of a month.
- **Not on the calendar**: loss dates of other causes (glass, animal, weather, vandalism) follow monthly
  seasonality only, and there is no month-end or quarter-end bunching of closes or reserve changes.

### Billing and commission

`autoins/billing.py` turns the premium ledger into bills and cash.

- **Plans.** Paid in full: one bill, due on the effective date. Monthly (by bank draft, "EFT", or by bill):
  one installment a month, six or twelve, the first due on the effective date and the rest on the anniversary
  day of each month, each issued 20 days ahead. Installments after the first carry a fee ($2 by draft, $5 by
  bill).
- **Changes.** An endorsement is spread over the installments not yet issued. With none left, or on the
  paid-in-full plan, an additional premium is billed on its own and a return premium refunded.
- **Paying.** Drafts are taken on the due date (the next business day at a weekend). Other customers pay by
  card, online bank payment, check or through their agent, most a few days early (a check, including one for a
  final balance, is banked on a business day); 3.2% of bills are paid
  more than five days late and carry a $10 late fee. About 1% of drafts are returned unpaid and collected
  again with a $25 fee. Less stable households pay late more often.
- **Non-payment.** A cancellation for non-payment is an installment that was billed and never paid: a
  past-due notice four days after the due date, a notice of cancellation at seven, and cover ends three to
  four weeks after the due date. New customers miss their early installments most. The simulation picks the
  installment a leaving household will not pay when the term begins; if a change leaves nothing on it (a car
  written off and not yet replaced, say), no bill is sent, and the household is recorded as canceling at its
  own request on the same day instead (17 terms in the default run).
- **Settling a canceled account.** Unpaid bills are canceled and the account is settled against the
  premium earned: money paid ahead is refunded; a balance still owed is billed, and after a non-payment
  cancellation most of those balances are never collected and are written off 120 days later.
- **What reconciles.** For every finished term, the premium on its bills (less canceled bills) minus the
  premium refunded equals its written, endorsement and return premium in `premium_transaction`. Cash received
  on a paid bill equals its amount due. `validate.py` checks both.
- **Commission.** `premium_transaction` carries the agency's rate (new business 10% to 15%, renewals 2 or 3
  points less, by agency; none for direct business) and the commission on each transaction, so a return
  premium takes its commission back. `agency_statement` adds each agency's month up (written premium and
  commission booked in the month, on the accounting date) and gives the day it was paid: the 15th of the
  next month, or the next business day. A month in which return commission exceeds commission earned shows
  a negative amount, which the agency repays (123 of 7,885 statements; in practice it would usually be set
  against the next statement). December 2026's statements are unpaid at the valuation date.

### The market: quotes, new business and renewals

`autoins/market.py` gives the book a market to sell into, so volumes move as a real carrier's do.

- **Shopping.** The number of households asking for a quote follows the season (most in February to
  April, when tax refunds arrive and cars are bought; fewest in November and December: March has a third
  more quotes than December) and the year (shopping rose as premiums did, to a peak in 2024).
- **Price against the market.** The market's rate level rises smoothly (12.1% in 2022, 16.5% in 2023, 7.6%
  in 2024, 3.7% in 2025), while the company's own increases land on their effective dates. After each
  increase the company is dearer than its competitors until they catch up. Every quote's competitive
  position (`quoted_annual_premium` against `competitor_annual_premium`, on independent-agent quotes) is
  spread around that gap: the median quote is 1% below the best competitor in 2022, 5.5% above in 2024
  and 1% above in 2026.
- **Conversion and growth.** The share of quotes that bind falls as the gap opens: 21.9% in 2022, 17.5% in
  2024 and 21.2% in 2026, and from 21.5% in the two months before a rate increase of 5% or more to 17.0%
  in the two months after. So quotes rose 18% from 2022 to 2024 while policies written fell 6%, and the
  book shrank in 2023 (20,429 policies in force at the end of 2022, 20,089 a year later) before growing
  again to 22,640.
- **Renewals.** A customer who had a claim since the last offer is likelier to leave, more so if it was
  at fault or the second: offers are taken up 94.4% of the time with no claim in the expiring term, 87.5%
  with one and 79.7% with an at-fault one, and a term with a claim is 1.39 times as likely to end the
  policy as one without (1.45 times in the real portfolio of `real_data/`). Being dearer than the market
  on the offer day also costs a little retention.
- **Company non-renewals.** The underwriting review flags a policy whose drivers have, in the three years
  before the renewal and known on the offer day, two or more at-fault accidents, two or more major
  violations, or one of each; half of those flagged are not renewed (1,000 of 11,500 non-renewals).

### The general ledger

`autoins/ledger.py` adds the books an accounting case needs, built only from the published tables, so
every figure can be traced back to rows a student can see.

- **`gl_account`**: 19 accounts (cash, premiums receivable, unearned premium, commissions payable, case
  reserves, surplus, premiums written, the change in unearned premium, fees, losses and adjustment expenses
  paid, recoveries, reserve changes, commission expense, premiums written off).
- **`gl_journal`**: one balanced journal entry for each month, underwriting company and kind of activity
  (4,193 lines in 1,605 journals). `journal_number` is `JE-2024-03-LFM-PW`: period, company, journal.

| Journal | Subledger | Entry |
|---|---|---|
| Premiums written (`PW`) | `premium_transaction` | Dr premiums receivable, Cr premiums written |
| Change in unearned premium (`UP`) | `premium_transaction` | Dr change in unearned premium, Cr unearned premium reserve |
| Premium cash receipts (`CR`) | `billing_receipt`, `billing_invoice` | Dr cash, Cr premiums receivable, Cr fees |
| Premiums written off (`WO`) | `billing_invoice` | Dr premiums written off, Cr premiums receivable |
| Commission expense (`CE`) | `premium_transaction` | Dr commission expense, Cr commissions payable |
| Commissions paid (`CP`) | `agency_statement` | Dr commissions payable, Cr cash |
| Claim payments (`LP`) | `claim_payment` | Dr losses paid, Dr adjustment expenses paid, Cr cash |
| Claim recoveries (`LR`) | `claim_payment` | Dr cash, Cr salvage and subrogation recoveries |
| Case reserve changes (`RS`) | `claim_reserve_transaction` | Dr change in case reserves, Cr case reserves |
| Opening balances (`OB`) | | Dr cash, Dr premiums receivable, Cr unearned premium, Cr commissions payable, Cr surplus |

- **Dating.** A premium transaction is booked on its accounting date, the later of its effective and
  processed dates: a renewal keyed in November for January is January's premium. Each transaction earns
  evenly from its effective date to the end of its term, so unearned premium at a month end is what is
  left to earn of everything booked by then. Cash moves on the receipt or payment date, a reserve change
  on its transaction date, a write-off on its write-off date.
- **What ties.** Premiums written and commission expense are the transactions booked in the extract.
  Written premium less the change in unearned premium is the policy terms' earned premium ($220.8
  million, to within a few hundred dollars of rounding). Case reserves are the reserves outstanding on
  the claim features ($13.3 million and $0.9 million of expense reserves). Commissions payable is the
  unpaid statements. Premiums receivable ($9.8 million) is premium written less premium collected,
  refunded and written off: bills not yet paid, installments not yet billed, less premium paid ahead.
  Fees are income when collected. `validate.py` checks each of these and that every journal balances.
- **Calendar-year results** from the ledger: losses incurred (paid, less recoveries, plus the change in
  case reserves) are 74.9% of earned premium in 2022, 74.8% in 2023, 63.2% in 2024, 63.2% in 2025 and
  64.9% in 2026; adjustment expenses 3.7% to 4.5%; commission about 7.2%; fees $0.4 million a year.
  These are calendar-year figures and differ from the accident-year loss ratios above.
- **Opening balances.** The books open on the day before the extract with what the policies in force
  bring (premiums receivable $5.9 million, unearned premium $10.9 million, December's commissions
  payable), cash and surplus. Surplus is ASSUMED at half the annual premium then in force ($16.1 million),
  and cash is the balancing figure.
- **What is not there.** No investments or investment income, general expenses, taxes, dividends,
  reinsurance, or reserve for claims not yet reported (estimating one from the triangles is an exercise);
  acquisition costs are expensed as written. Cash therefore only accumulates ($87 million by the end).
  The ledger is a summary by month: there is no journal line per transaction, and no planted error.

### Claim payments, vendors and staff

`autoins/payments.py` adds what a claim system and a bank record around each payment.

- **Staff.** Each claim office has adjusters' desks, a supervisor, and above them a claims manager; people
  are hired and leave. A claim belongs to a desk, so when an adjuster leaves, whoever takes the desk takes the
  file (`claim.adjuster_id` is the current holder). Payment authority: adjusters $10,000 (the glass desk
  $2,500), senior adjusters $25,000, supervisors $75,000, the manager above that.
- **Approval.** Each payment is approved by the adjuster on the file if it is within their authority,
  otherwise by the supervisor or the manager, and always by someone employed that day.
- **Payees.** First-party repairs are paid to the body shop about half the time, glass mostly to the glass
  company, rentals and tows mostly to the vendor, total losses to the owner (a financed or leased car's
  lender or lessor is paid off first, one lender per car), liability claims to the claimant, their shop or
  their insurer, represented injury claims to the claimant and attorney jointly from the day the attorney is
  retained (an advance before that goes to the claimant alone), payments to the insured to the named insured
  on the payment date, expenses to appraisers, law firms and medical review services. Recoveries come from salvage
  auctions and other insurers.
- **Vendors** are fictional. Local trades are placed in the area's ZIP codes and used by nearby claimants;
  the company's repair network gets more of the work; a few vendors take most of each trade's business.
- **Method and bank.** Vendors are mostly paid electronically, people mostly by check (insureds
  increasingly electronically). Checks are numbered in one unbroken sequence; a voided check keeps its
  number and its void entry repeats it. `cleared_date` is when the bank paid it; checks not yet cleared at
  the valuation date are "Outstanding", and a few sent to people are never cashed.

### Dates and timing

- **Opening book.** Policies in force on the start date enter with the term that spans it,
  which was written before the extract. Their exposure and premium count only from the start
  date: `earned_premium` is earned inside the extract, `earned_premium_before_extract` before it, and
  `exposure` gives each row's `coverage_start_date` (which can be before the start, as can
  `policy.first_effective_date`, the start of a policy's first term in the data). Policies already in
  the telematics program then carry an enrollment date and a first score from before the start.
- **Anniversaries.** Policies can be written on any day, including the 29th to 31st. In a
  shorter month the term starts on the last day, and the next one returns to the original day
  (a policy written on 31 August renews on 28 or 29 February, then on 31 August).
- **What the insurer knows.** `policy_term.offer_date` is when a term was quoted: 30 to 45 days
  before a renewal (the renewal offer) and up to 14 days before new business. `rating_date` is when
  it was last rated: the offer date, unless the household changed between the offer and the
  effective date (a move, or a car or driver added or gone), in which case the pending renewal was
  re-rated on the day of the change and a revised offer sent (about 5% of renewals). Rating uses
  only what is known by then. Drivers and cars on policies renewing on the start date joined them
  before the first rating in the data (at inception, on being licensed, or when the car was bought).
  `driver_incident.known_date` is when each incident became known: a violation when the conviction
  posts to the driving record (about two months), an earlier accident when it reaches a
  claims-history report, and the company's own at-fault claim the day after the payment that takes
  it to the $1,000 surcharge threshold. A claim that is reported or paid after a renewal's rating
  date first counts at the next renewal.
- **Renewal decisions.** Everything about a renewal is decided on its offer date, from the policy as it
  stood that day: the underwriting review (the drivers on the policy then and the records known
  then), the telematics score and program offer, the renewal premium, and the customer's decision on
  it (the premium change against what the same cars cost, and the claims reported since the last offer).
  `renewal_offer` keeps every renewal evaluated, renewed or not. Its snapshot is the expiring term's
  `exposure` rows in force on the offer date, and its `expiring_premium` and `renewal_premium` are for
  those cars for a full term. Later events cannot change the offer or the decision: a household change
  before the effective date re-rates the renewal (`revised_offer_date`, the renewal term's
  `rating_date`), and the written premium can also differ from the offer when the customer changes
  deductibles or limits at renewal. A cancellation before the effective date ends the policy
  (outcome "Canceled Before Renewal"), and renewals taking effect after the valuation date are
  "Pending". The answer key's `renewal_offer_truth` gives each offer's true chance of acceptance.
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
  one-car policy with no replacement is canceled; one waiting for a replacement stays in force with
  no vehicle until it arrives. Claims on the old vehicle keep developing. The extract shows a
  removal as a total loss only once the company has that claim; until then the car is shown as
  destroyed or stolen, and a car lost on the valuation date itself is still on the policy.
  A few owners keep a car the company paid as a total loss (`owner_retained_salvage`); as Illinois
  law requires, only for hail damage or a car nine or more model years old. The salvage value
  comes off the settlement and the car loses physical damage cover at the next renewal.
- **Premium.** Changes mid-term are endorsements charged or returned pro rata to the end of the
  term. `premium_transaction` books each transaction on a processed date: a new policy when it is
  quoted and bound, a renewal when it is offered (30 to 45 days ahead, so before its effective date;
  statutory accounting records written premium on the effective date, the later of the two), a policy
  change the day it takes effect if that is a business day (four in ten) and otherwise within a week
  or two, a non-payment cancellation the day it takes effect. Transactions not processed by the
  valuation date are not in the extract. For every
  finished term, written + endorsement + return premium = earned before the extract + earned
  premium, and the ledger adds up to the same.
- **Good student.** The discount applies while a driver with B grades is still in full-time
  school and under 25, judged on each term's effective date; `exposure.rated_good_student`
  keeps the status each term was rated with.
- **Injury settlements are round.** A bodily injury or uninsured motorist settlement is a negotiated
  figure: $7,500 or $22,250, not $7,512.38. 85% of paid bodily injury features are whole-dollar amounts
  and 72% multiples of $250; the rest settled for their exact medical bills or were cut pro rata by a
  per-accident limit. Repair, medical and rental payments follow their bills to the cent.
- **Payments.** Glass and most injury claims settle in one payment. Physical damage is often
  paid on the first estimate and topped up later; property damage may pay loss of use first;
  injury claims sometimes get an advance; medical payments follow the bills. A total loss on a
  financed car pays off the loan first (never more than the settlement; about a quarter of loans
  owe more than the car is worth, and gap cover pays the rest) and the owner gets the balance; a
  leased car's settlement all goes to the leasing company; title and fees may be paid later. A few payments are voided and
  reissued, and about 2% of paid features reopen for a supplement. Payments always add up to the
  feature's paid loss to the cent.
- **Claims that pay nothing.** As in real claim files, many features close without payment:
  liability claims against an insured who was not at fault, injury claims opened as a precaution
  and never pursued, and damage reported then withdrawn. They carry a nominal reserve while open.
  About 43% of closed liability and medical features and 16% of closed collision and comprehensive
  features pay nothing (industry 2025: about 45% and just under 25%).
- **Reserves.** Each feature opens with a formula reserve and is re-estimated on a review cycle (every
  90 days for injury, 30 for physical damage). Early injury estimates average about 86% of ultimate and
  improve as claims mature, so bodily injury incurred develops upward (12-to-24-month factors of about
  1.03 to 1.22) while collision barely moves; payments erode reserves, closing releases them, and
  precautionary injury claims carry a nominal reserve. Litigated features also carry an expense
  reserve. `claim_reserve_transaction` records every change, so incurred can be rebuilt as of any date.
- **Claim detail.** About half of paid bodily injury claimants are represented by an attorney (57%
  industry-wide in 2022, Insurance Research Council), mostly within days or weeks of the accident.
  A litigated feature follows an ordered timeline: the attorney is retained, suit is filed after
  both that and the claim being presented and within Illinois' two-year limit, and the feature
  closes at least 30 days after the suit (a feature drawn to close sooner stays open longer).
  At-fault insureds are 51% to 100% at fault and others 0% to 49%, so the data has no evenly shared
  (50/50) accidents, a simplification: under Illinois' modified comparative fault rule a claimant
  recovers only if no more than 50% at fault. `insured_fault_pct` describes the accident only:
  settlements are not reduced for the other party's share of fault (see "Assumptions and limits").
  Injury type follows severity. Police reports, fraud referrals and SR-22 filings (three years after a
  DUI, driving while suspended or leaving the scene) are included.
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
  from prospects rated with the same plan. Conversion depends on the channel (at the market's price
  level, about 12% direct, 22% through independent agents and 38% through exclusive agents) and falls
  as the quote rises above the best competing premium, which independent agents see on their
  comparative raters (see "The market").
- **Cancellations.** For non-payment, cover ends three to four weeks after an installment goes unpaid (see
  "Billing and commission"); new customers miss early installments most. Underwriting cancels new business in
  its first 60 days. Other cancellations are at the insured's request, on any day.
- **Reporting lags.** Injury claims are often presented weeks or months after the accident, and a
  few near Illinois' two-year statute of limitations. Lags follow a US insurer's experience: 84% of
  bodily injury claims reported within 5 days, 97.5% within 90 and 99.2% within a year (CAS Loss
  Simulation Model Working Party); collision claims are reported faster.

## What a case study can find (instructor notes)

The answer-key zip in each release (and `output/answer_key/` when you build locally) holds the truth
behind the data: each exposure row's expected loss by coverage, each driver's hidden risk factor and
synthetic race and ethnicity, each household's stability, each agency's book quality and hold on its
customers, true mileage, true ZIP hazard, the full rating plan (filed discounts, what each is truly worth,
and the rest before and after distortion), the claims not yet reported, and each renewal offer's true chance
of acceptance. Withhold it from students: give them the data zip from a
release, not access to this repository, because anyone with the code can regenerate the answer key.

Deliberate and emergent findings in the default run:

| Finding | What the data shows |
|---|---|
| New business costs more than it is charged | Expected loss ratio 76.1% for new business against 66.8% for renewals, falling with tenure: 70.7% in the first year after, 67.1% at one to three years, 65.1% at six or more. The loyalty discount (2% to 6%) is a fraction of what the risk justifies (12% to 21%) |
| New policies claim early | 27.4 claims per 100 policy-years in a new policy's first 30 days, against about 24 for the rest of the first year and 21 to 23 after that |
| Channels differ | Expected loss ratio 70.8% for independent-agent business, 67.1% direct, 65.6% exclusive agents; renewal rates 93.8%, 91.8% and 95.7% |
| Some agencies write a worse book | Among the 61 agencies with 500 or more car-years (books of 108 to 1,446 policies), expected loss ratio runs from 57% to 90% (10th to 90th percentile: 63% to 79%); `agency_truth` says which differences are real and which are claim luck. The other 73 agencies are too small to judge on their own results: that is a finding too |
| A few agencies write most of the premium | The largest tenth of the 120 independent agencies write 36% of their premium; half of them have 47 or fewer policies in force |
| Billed installment payers run worse | Expected loss ratio 70.0% on the monthly bill plan, 66.7% by bank draft, 68.9% paid in full; renewal rates 90.8%, 93.2% and 95.4%; non-payment cancellations and write-offs concentrate there |
| Some discounts are not earned | The good-student and married discounts (10% and 5%) have no support once class and record are rated (good students run an expected loss ratio of 83%); the no-prior-insurance surcharge is more than those customers cost; the multi-car discount is more than those households save and the paid-in-full discount less (see "The rating plan") |
| Rate increases cost new business | Conversion falls from 21.5% in the two months before an increase of 5% or more to 17.0% in the two months after, and recovers as the market's rates catch up; quotes rise 18% from 2022 to 2024 while new policies fall 6% (see "The market") |
| Shopping is seasonal | March has a third more quotes than December |
| Claims cost customers | Renewal offers are taken up 94.4% of the time with no claim in the expiring term, 87.5% with a claim and 79.7% with an at-fault claim; 1,000 renewals were refused by the company for the drivers' records |
| Young drivers are under-priced | Expected loss ratio 75% to 90% for classes under 25, against 67% for ages 25 to 64 |
| Mileage is under-used | Expected loss ratio rises from 63% under 5,000 reported miles to 83% at 16,000+ |
| Kia/Hyundai theft wave is unpriced | Whole-vehicle thefts per 1,000 comprehensive-covered vehicle-years for affected models peak at 7.5 in 2023, against 0.7 to 1.7 for others; the counts are small, so the year of the peak moves from run to run |
| Automatic emergency braking is unpriced | Expected loss ratio 65.7% with it, 70.0% without |
| Telematics members are safer than they are charged for | Enrolled cars run an expected loss ratio of 62.3%, against 69.6% for the rest; selection and the 7% behavior effect can be separated only with the answer key |
| The telematics discount under-reacts to the score | Expected loss ratio 66% for cars earning 10% or less, 52% for those earning 21% to 30% |
| Telematics mileage exposes under-reporting | Annualized `telematics_score.miles_driven` is above the car's reported `insured_vehicle.annual_mileage` for two cars in three (10% above for the median car) |
| Rates lagged costs, then caught up | Expected loss ratio falls from 80% (2022) and 75% (2023) to 65% and 63% (2024, 2025), as the industry's did |
| Case reserves develop | Bodily injury incurred grows by 3% to 22% from 12 to 24 months as early, low reserves are corrected; collision moves 2% to 4% |
| New business is price-sensitive | Independent-agent quotes priced below the best competitor bind 38% of the time, those above 14% |
| Insurance score is priced roughly right | Premium per car-year falls by more than half from scores under 600 ($2,204) to 800 and above ($893); expected loss ratio drifts only from 66% to 71%, partly because telematics discounts go mostly to good-score customers |
| The newest year is not fully known | Late-reported claims are missing, open claims carry imperfect reserves, and closed claims can reopen |
| Price increases cost retention | In `renewal_offer`, offers the insurer was willing to renew are taken up 95% of the time when the premium changes by 5% or less, 87% at a 10% to 20% increase and 74% above 20% |
| First renewals are the weakest | On six-month terms, 90.7% of first renewals are taken up against 95.4% of later ones |
| Records reach the insurer late | A violation or chargeable claim shortly before a renewal's rating date is surcharged a term later |
| Exposure moves | Moves, trade-ins and new drivers change a policy's territory, vehicles and rated drivers mid-term; a vehicle's history spans several exposure rows and sometimes several ZIP codes |
| Cash follows premium, late | Receivables by age, late payers, returned drafts, refunds and write-offs can all be built from `billing_invoice` and `billing_receipt`: $1.64 million was owed on 7,263 bills at the valuation date, and $0.68 million had been written off |
| The books tie to the subledgers | Written and earned premium, unearned premium, receivables, commissions payable, paid losses and case reserves in `gl_journal` can each be rebuilt from the tables behind them, by month and company; calendar-year results differ from accident-year ones for reasons a student can explain |
| Physical damage follows the used-car market | Vehicle values, and with them total-loss payments, peak in 2022 and fall as used-car prices ease; total losses rise from 26% of paid collision claims in 2022 to 32% in 2026 as repair costs climb and values fall |
| Payments leave an audit trail | Check sequence, voids, outstanding checks, payments by approver against authority, vendor concentration (the ten busiest body shops take 29% of body-shop payments) and Benford's law can all be tested; the data holds no planted errors or fraud, so every test should come back clean |

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
figure), TUNED (set to hit an anchored target) or ASSUMED (judgment). The ones that matter most:

- **Suburban hazard is modeled, not observed.** Chicago's crash data covers the city only.
  Suburban ZIPs get the city's income gradient at an assumed lower level.
- **City hazard is damped.** Raw police-record rates vary about sevenfold across city ZIPs; an
  exponent narrows that to a range typical of rating territories.
- **Benchmarks are national or statewide**, not Chicago-specific or carrier-specific, and cost trends
  for 2025 and 2026 are assumed. Frequency and severity are compared approximately on the national table's
  published definitions (see "Frequency and severity against national figures"), and premiums by coverage
  and physical damage take-up with Illinois' averages, which shows the overall scale is reasonable. It
  does not validate anything finer: results by subgroup, how variables depend on each other, large-loss
  tails or local geography are assumed or tuned, not checked against data.
- **Physical damage rests on a reading of the benchmark.** The national table is taken to be net of
  salvage and subrogation (see that section for why). If it is not, collision and comprehensive payments
  here are about a quarter too high against it, and they would then sit below Illinois' premiums at
  industry loss ratios; the two cannot both be matched on that reading.
- **Vehicle values are modeled.** A car's value is its model year's base price, a depreciation curve
  (ASSUMED shape) and the Manheim used-vehicle index by year. It is not a valuation service's figure for
  the car, and trim levels, mileage and condition are not modeled.
- **The market is stylized.** One market rate level stands for every competitor, shopping follows an
  assumed season and year, and the company's price position is the same for every customer on a given
  day apart from random spread. There are no competitor names, no advertising, and no agency
  appointments or terminations during the extract: the 134 agencies are there throughout. Agency sizes,
  the claim and market effects on renewal and the underwriting rule for non-renewal are ASSUMED.
- **The ledger is a summary.** It holds what the published tables support and nothing else (see "The
  general ledger"): opening cash and surplus are assumed, there are no investments, expenses other than
  commission, taxes, reinsurance or reserve for unreported claims, and entries are monthly totals.
- **Most of the rating plan is fitted to the truth.** Apart from the filed discounts, relativities are
  fitted directly to the simulator's true expected losses on the opening book, then distorted on purpose.
  A real carrier estimates its costs from noisy past losses, with filing and implementation lags, so the
  plan here is cleaner and more adequate than a real one. It is a teaching design, not evidence about a
  real carrier.
- **The hidden traits are assumed.** Household stability, the new-customer effect, and the channel and
  agency effects (sizes, shapes and what each drives) are ASSUMED. The new-customer effect is sized to a
  published gap between new and renewal loss ratios (13 points across 25 books; Wu and Lin 2009); nothing
  else about them is checked against data. The filed discount percentages are typical of filed plans, not
  taken from one.
- **The working calendar is partly real.** Crash and theft days follow Chicago's daily counts, which are
  police reports for the city, not insurance claims for the metro area. Hold-over of weekend notices, the
  weekday mix of quotes and effective dates, and loss times for causes other than crashes and thefts are
  ASSUMED.
- **Billing and payment detail are stylized.** Plans, fees, how often customers pay late, how balances are
  collected, vendor shares, payment methods, clearing times, staffing and authority limits are ASSUMED
  (`autoins/billing.py`, `autoins/payments.py`). They change no premium, loss or date in the other tables.
  Bills and receipts before the start date exist only for the terms in the data.
- **Vehicle popularity comes from crashes.** Model shares are measured on vehicles in Chicago crashes,
  which over-represent cars that are driven more and crash more, and city cars over suburban ones (the
  density tilt for pickups partly corrects this). The crash records' pick list lacks some models and
  mislabels others, so some shares rest on a sales prior. Prices are approximate base prices, used only
  to scale repair and total-loss costs and to set the price and symbol bands; a model year's engine,
  drive and body are its most common configuration.
- **Vehicle ages are tuned to Chicago.** About nine years on average in force, as on Chicago's roads in
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
- **The rate schedule is stylized**: +48% cumulative between April 2022 and March 2025, then a 2%
  cut in June 2026. Telematics discounts are not offset in the base rates.
- **Telematics is a stylized program.** Take-up, discounts, drop-out, the score formula and the 7%
  behavior effect are ASSUMED, shaped on published descriptions of US programs. A member who leaves
  mid-term keeps the discount until the renewal, and the behavior effect applies until then too.
- **Catastrophes are fictional.** Dates and footprints are plausible for northern Illinois but
  do not correspond to actual storms.
- **Household dynamics are partly sourced.** Mover, divorce, marriage, mortality, licensing and
  vehicle-ownership rates come from public data (see "Dates and timing"); how often households add
  or sell cars, how often a leaving driver takes a car, and the shapes by age are judgment calls.
  Income, insurance score, payment plan and multi-policy status stay fixed for a policy's life;
  liability limits change only at renewal, and homeowner status only with a move.
- **Report lags rest on one published study** (one insurer, 1996 to 2005). Lags beyond a year are
  probably understated there, so treat the IBNR tail as indicative.
- **Timing assumptions** (rating lead times, driving-record posting lags, replacement delays,
  payment patterns, endorsement processing lags) are judgment calls, marked ASSUMED in
  `autoins/config.py` and `autoins/claims.py`.
- **Identifiers and symbols are fictional.** VINs have a valid check digit but begin with `0`, which
  no manufacturing region uses; policy, claim, quote, invoice and check numbers follow this dataset's
  own formats; license numbers are masked; company codes only look like NAIC codes; and the vehicle
  symbols are this dataset's own scales, not ISO's licensed ones.
- **Claimants are not people.** A liability or injury feature has a claimant number within its claim,
  the payments name a (fictional) claimant, and `claim.involved_driver_id` is the insured driver involved.
  There is no table of third-party claimants who can be followed from one claim to another.
- **Not modeled:** fraud itself (only referrals), planted errors or irregularities for audit tests,
  uninsured motorist property damage, reinstatements after a cancellation, excluded
  drivers, separate mailing and garaging addresses, reinsurance, and the edit errors and out-of-sequence
  bookings of production data. The dataset is an analytical extract for teaching: it is not a model of a policy
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
hold what a usage-based program records. Public alternatives are far thinner: French motor data
(`freMTPL2`) has one row per policy and undated claims, the CAS Loss Reserve Database holds
company-level triangles only, and the real portfolio in `real_data/` is a single table with one row per
vehicle per year (see "Compared with a real insurer's data").

Around those sit the records operations and accounting keep: a bill and a receipt for every premium
dollar, commission on every premium transaction and a monthly statement for every agency, for every claim
payment a payee, a method, a check number, a clearing date and an approver with a payment authority, and
a general ledger whose monthly entries add those subledgers up. Vehicles are identified by VIN, as
policies are written; there are no license plates, which insurers meet mostly in claim files.

It also has what reserving, claims and pricing work rely on: case reserve history (`claim_reserve_transaction`,
as in claim systems' reserve transactions and statistical plans' outstanding-loss records), expense
split into defense and cost containment versus adjusting and other with expense reserves, limits and
deductibles on each rating record, VIN prefixes and vehicle symbols (fictional, in the shape
statistical plans use), underinsured motorist, rental and towing coverages, claim detail (attorney and
suit dates, fault percentage, injury type, police report, fraud referral), applied discounts, SR-22
filings, telematics scores, and a quote funnel with quotes that never bound.

Real data would still have, and this dataset does not:

| Gap | Real-world source |
|---|---|
| Claims open on the start date and their later payments (an opening claim inventory) | Claim systems |
| Third-party claimants as people who can be followed across claims | Claim systems |
| Reinstatements after a lapse; billing accounts that span several policies | Billing systems |
| Journal entries for each transaction; investments, expenses, taxes, reinsurance and a reserve for unreported claims in the ledger | Accounting systems |
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
| Physical damage take-up and average premiums by coverage | NAIC Auto Insurance Database, average premium supplement (Illinois, 2022 to 2024: average premium per insured car-year for liability, collision and comprehensive; collision and comprehensive per liability car-year) |
| Salvage and subrogation; collision severity by deductible | Verisk, "2024 Executive Insights: Personal Auto", 1st edition (salvage 10.1% and subrogation 14.0% of collision indemnity over five years; severity by deductible) |
| Used-car prices | Cox Automotive, Manheim Used Vehicle Value Index (year-end levels 2021 to 2025) |
| Repair costs and total losses | CCC Intelligent Solutions, Crash Course reports (average repair cost about $4,730 in 2024; average total-loss vehicle value $13,400 to $13,700; 22% to 23% of appraisals total losses) |
| Market rate level | S&P Global RateWatch (2022 to 2024) and AM Best (2025), as for the rate changes |
| Claim report lags | CAS Loss Simulation Model Working Party (Ball State University paper), bodily injury and collision report lags |
| Loss days and times of day | City of Chicago Data Portal: Traffic Crashes (crashes by day, 2021 to 2026, and by weekday and hour) and Crimes (motor vehicle theft, the same) |
| Holidays | US federal holidays (5 U.S.C. 6103), as observed, and the day after Thanksgiving |
| New business against renewals | Wu and Lin, "Large Scale Analysis of Persistency and Renewal Discounts for Property and Casualty Insurance", CAS E-Forum, Winter 2009 (new business loss ratios 13 points above renewal across 25 books) |
| Check digits | VIN: 49 CFR 565. Policy number: ISO 7064 MOD 97-10, as IBANs use |
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
python scripts/build_calendar_reference.py
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
autoins/population.py    households (and their hidden stability), agencies, drivers, vehicles, coverages
autoins/names.py         driver names from ZIP-level Census make-up (used for nothing else)
autoins/truth.py         true frequency and severity, expected loss, claim simulation
autoins/rating.py        the insurer's rating plan: filed discounts, and the rest fitted around them
autoins/telematics.py    the Lakefront DriveCheck usage-based program
autoins/simulate.py      term-by-term simulation: rating, telematics, retention (price, claims, the market),
                         underwriting review, household changes, claims
autoins/claims.py        claim lifecycle: payments, reserves, claim detail, valuation cut-off
autoins/quotes.py        the new-business quote funnel
autoins/market.py        the market: seasonal shopping, the company's rates against the market's, conversion
autoins/ledger.py        the general ledger and agency commission statements, from the published tables
autoins/billing.py       bills and cash: installments, late and returned payments, refunds, write-offs
autoins/payments.py      claims staff, vendors, and each claim payment's payee, check and approver
autoins/identifiers.py   business keys (policy, claim and quote numbers, VINs) and creation-order IDs
autoins/refdata.py       reference data and the calendar: seasonality, real crash days, business days
autoins/tables.py        output tables and answer key
autoins/schema.py        each table's primary key and foreign keys (declared in the SQLite release)
output/                  where generate.py writes (ignored by git; published as releases)
samples/                 first 100 rows of every table (written by the samples workflow)
reference/               ZIP reference data, vehicle catalog and its curation, names, Chicago's daily crash and
                         theft index and hour-of-day profiles
real_data/               a real motor insurance portfolio, for comparison (CC BY 4.0)
docs/                    limitations; comparison with the real portfolio; old-to-new schema map; review response
scripts/                 build reference/ from public sources (ZIPs, vehicles, names, calendar); package releases (CSV,
                         SQLite, Parquet); samples; real-data comparison; readme_figures.py prints the run figures the
                         documentation quotes
.github/workflows/       release and samples workflows
tests/                   python -m unittest discover tests
CHANGELOG.md             what changed, and why, since the first version
```
