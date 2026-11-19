# Changelog

This repository generates a synthetic personal auto insurance dataset: the policy, premium and
claim records of one fictional insurer selling car insurance in the seven-county Chicago area. The
people, policies, premiums and claims are simulated, but the geography behind them is real: ZIP
codes, Census demographics, and Chicago police crash and vehicle-theft counts. It replaced an older
synthetic dataset whose loss ratio (claim costs as a share of premium) was about 20%, far below the
roughly 60% to 80% that US auto insurers reported for 2022 to 2025, and whose risk relationships
were not credible. This log records, stage by stage, what was changed to make the data more
realistic and more useful for teaching, and why.

## At a glance

Dates are merge dates (US Central time). Figures for stages 1 to 4 are for the default run at the
time (seed 20250101, 30,000 policies, 1 January 2022 to 30 September 2026), and for stage 5 the new
default of 51,391 policies (later 43,368 policies to 31 December 2026; see stage 5), unless stated
otherwise.

1. **2026-11-13, Starting point.** The repository is created; the aim is to replace the old dataset
   (California geography, a loss ratio near 20%, no link between driver risk and claims).
2. **2026-11-13, A simulated Chicago-area book ([PR #1](https://github.com/subwaymatch/auto-insurance-synthetic-data-test/pull/1)).**
   A seeded generator built on real ZIP data, with hidden driver risk, a deliberately imperfect
   rating plan and full claim lifecycles; loss ratios by year move to about 61% to 83%.
3. **2026-11-14, Record-level realism, household changes and industry calibration ([PR #2](https://github.com/subwaymatch/auto-insurance-synthetic-data-test/pull/2)).**
   Individual records made consistent, mid-term household changes, reserve history, claim detail,
   more coverages and a quote funnel; expected loss ratios recalibrated to follow US and Illinois
   industry figures; data published as GitHub releases.
4. **2026-11-15, Audit fixes and like-for-like calibration ([PR #3](https://github.com/subwaymatch/auto-insurance-synthetic-data-test/pull/3)).**
   A second review fixed coverage-limit, claim-timeline and policy-count errors, and claim rates are
   now compared with national figures on those figures' own definitions.
5. **Unreleased, Real vehicles, real-data benchmark, telematics and a cleaner schema.** The data is
   compared with a real insurer's portfolio; the 110 hand-picked car models become a catalogue of every
   US make, model and model year since 1997, weighted by Chicago's roads; the fleet ages to match; a
   telematics programme, realistic names and a consistent table layout are added; two external reviews'
   findings are fixed, the second by deciding renewals and telematics scores only on what was known at the
   time and keeping every renewal offer; the default book becomes 43,368 policies over five full years
   (2022 to 2026). A realism audit then asked whether the data looks like an operating company's: discounts
   are now filed and only roughly right, new customers and some agencies cost more than they are charged,
   staff work business days and losses follow Chicago's real days, records carry policy numbers, claim
   numbers and VINs, and every premium is billed and collected and every claim payment has a payee, a cheque
   number and an approver.

## Unreleased (in progress)

Figures in this section were measured on the 51,391-policy default run (to 30 September 2026) unless
stated otherwise; "Fixes from an external review" and "Size and dates" move the default to 43,368 policies to
31 December 2026 and give that run's figures, and the last subsection gives the run after the third review's
fixes.

### Benchmarked against a real insurer's data

- A real motor portfolio was added for comparison: "Dataset of an actual motor vehicle insurance
  portfolio" (Lledó and Pavía, Mendeley Data 2024, CC BY 4.0), 105,555 rows from what is almost
  certainly a Spanish insurer, 2015 to 2018. It is kept unmodified in `real_data/` with its licence and a
  data dictionary.
- `scripts/compare_real_data.py` compares the two books on what can fairly be compared (the shape of
  risk relationships, claim-cost and premium spread, retention, signal strength and data quality,
  not levels, since the markets and currencies differ), and `docs/real_data_comparison.md` reports it.
- **Verdict.** The synthetic data looks realistic where a fair comparison is possible: drivers under 25
  claim 1.37 times the average in the real book and 1.27 times in the synthetic one; urban vehicles
  1.14 and 1.13 times; claim costs and premiums spread alike. Four gaps remain open: claims barely drive
  customers away, payment plan carries no risk, the largest claims are smaller, and the data is too clean
  to teach data cleaning. A fifth, a fleet that was too young, is fixed below.

### Vehicles: from 110 models to every model year since 1997

- **Why.** The old list of 110 models, typed in by hand, had no rare models and no model years: every
  Camry was the same Camry. Real insurers rate on a make, model and model-year table.
- **What.** `vehicle_model_year` now holds 8,750 model years of 940 models from 74 makes, from the
  Toyota Camry to the Bugatti Chiron, each with its body type, size class, rating segment, fuel, drive,
  engine, price new, VIN pattern and rating symbols. 761 of the models from 58 makes appear in the
  default book. Price new, symbols and the model year moved here from the insured-vehicle table.
- **Sources.** The EPA and Department of Energy fuel economy list (every light-duty model sold in the
  US), plus heavy-duty pickups and other vehicles EPA does not list. How common each model year is comes
  from about a million vehicles in personal use in Chicago crash records, 2021 to 2025, after removing
  police, taxi, bus and delivery vehicles. Prices for about 900 models were curated by hand.
- **Fleet age.** Vehicle ages are tuned to the same Chicago records: about 10 years on average in force
  and 41% ten or more years old (was 7.6 years and 29%, which the real-data comparison flagged). Pickups
  are now commoner in the less dense suburbs than in the city.

### Telematics: a voluntary usage-based programme

- **Why.** Most large US insurers now offer a usage-based ("drive safe and save" style) discount, and its
  data is among the most important new rating information. It was listed as not modelled.
- **What.** Lakefront DriveCheck is offered at new business and renewal; about a fifth to 30% of new
  customers join, and enrolled cars grow from 13% of car-years in 2022 to 25% in 2026. Members get 5%
  for joining, then a discount of up to 30% earned by a 1-100 driving score built from miles, trips,
  hard braking, rapid acceleration, speeding, phone use and night driving. Scores never raise the premium.
  About one member in ten leaves each year, more after poor scores.
- **What it teaches.** The device sees the driver's true risk and the car's true mileage, which the
  rating plan cannot. Safer drivers join (favourable selection) and monitored drivers take more care (7%
  fewer at-fault crashes), so members run an expected loss ratio of 62% against 70.5% for everyone else,
  and the discount under-reacts to the score (48% for cars earning the top band). Telematics mileage is
  above reported mileage for two cars in three.
- **New tables.** `telematics_enrollment` and `telematics_score`; each exposure row records whether it
  was rated in the programme and the discount applied.

### Names that fit the place, and a fairness exercise

- **Why.** Names were drawn evenly from about 570 names (218 first names), unrelated to place, age or
  each other.
- **What.** Each household gets a synthetic race and ethnicity group drawn from its ZIP code's Census
  mix. Surnames come from the Census 2010 surname table for that group, and first names from Social
  Security first-name counts for the driver's sex and decade of birth (1880-2025), weighted to the group
  with Tzioumis' (2018) first-name data re-based to the 2010 population. The default book now has 2,801
  distinct first names that follow birth year: Mary and Linda for women born in the 1950s, Olivia and
  Emma for the 2000s.
- **Fairness exercise.** The group affects nothing else (risk, prices and claims never use it) and
  appears only in the instructor answer key, so a fairness audit with BISG (estimating race from surname
  and address) can be checked against the truth. Only `driver.first_name` and `driver.last_name` changed;
  every other table is identical with or without the new names.

### A consistent table layout

- Tables have singular names (`policy`, `policy_term`, `exposure`, `claim`, `claim_feature`, and so on,
  replacing names such as `risk_fact`, `claims_fact` and `communication_data`), columns are
  `snake_case`, and each key has one name everywhere (`policy_id` was "Policy Number" in some tables and
  "Policy ID" in others). `claim_expense_dimension`, which only repeated the claims table, was removed.
  `docs/schema_changes.md` maps every old table and column to the new one.

### A regional insurer of realistic size

- The default book grew to 51,391 policies (was 30,000; a deliberately unround number), then settled at
  43,368 policies (see "Size and dates" below). The README now describes the insurer as the Chicago-area
  part of a small regional group.

### Calibration, checks and fixes

- Every calibration band still holds on the larger book: frequency and severity against national figures
  (1.03 to 1.24 times national frequency, 0.86 to 1.04 times severity), expected loss ratios on the
  industry path (79% in 2022 falling to 64% in 2025), and an overall loss ratio of 72.1%.
- Each full accident year's actual loss ratio is now held to 0.85 to 1.15 times its expected one,
  replacing an absolute band of 52% to 88%, which mixed calibration with claim luck. In the default run
  2022 is 88.6% against 78.9% expected (1.12), because bodily injury came in at 1.21 times its expected
  cost; calibration itself is still held by the expected loss ratio against industry.
- New checks in `validate.py` cover the vehicle catalogue (one row per model year, every vehicle pointing
  to one) and the telematics programme (scores inside their enrolment and earning the published
  discount, discounts only on enrolled rows); three new tests cover them and the names.
- **Fixed:** two replacement cars joining one policy on different days of the same term were rated at
  once, so the later one could miss a claim on the earlier one. Cars are now rated in date order.

### Documentation

- `docs/limitations.md` collects every limit of the dataset in one shareable page: what it leaves out,
  where it differs from a real insurer's data, the assumptions that drive its results, how far its
  numbers can be trusted, and its appropriate and inappropriate uses.

### Data publishing

- **SQLite release format.** Each release now also carries the data as one SQLite database
  (`...-sqlite.zip`) with every table, a primary key on each and every foreign key declared, indexed
  and checked at build time (the build fails if any reference does not resolve). The instructor's
  database also holds every data table, so the answer key links to it. `autoins/schema.py` records the
  keys; tests check it covers every `..._id` column. The answer key's `unreported_claim` gained an
  `unreported_claim_id` so that every table has a primary key. Releases publish `csv,sqlite` by default.
- The release workflow accepts a version typed without its leading `v` (`1.1.0` is released as
  `v1.1.0`); an earlier manual run with `1.0.1` had stopped at the input check.
- `.github/workflows/samples.yml` commits the first 100 rows of every table, the answer key and the real
  data to `samples/`, so the data can be browsed on GitHub; it reruns when the generator changes.
- `scripts/fetch_public_data.py --only vehicles` and `scripts/build_vehicle_catalogue.py` rebuild the
  vehicle catalogue from its sources; `scripts/build_name_reference.py` rebuilds the name tables
  (`reference/surnames.csv`, `reference/first_names.csv`).

### Fixes from an external review

An outside review (another AI coding assistant) checked the generator twice. Every finding was
confirmed and fixed; `docs/review_response.md` answers each one with before-and-after counts. Each fix
has a new check in `validate.py` or a new test.

- **Renewals re-rated after late changes.** A move, or a car or driver added or gone, between a
  renewal offer and its effective date now re-rates the pending renewal that day (9,727 of 179,382
  renewals, 5.4%), with a "Revised Renewal Offer" contact. `policy_term` gains `offer_date` beside
  `rating_date`. Before, 1,738 renewal rows were rated at an address not yet in force.
- **When the opening book's drivers and cars joined.** Drivers and cars on policies already renewing on
  the start date were dated as added on their first term's start, after it was rated; they now join at
  inception, on being licensed, or when the car was bought, before the first rating in the data.
- **Conviction and SR-22 dates.** Dates before 2022 were clipped to 1 January 2022, putting 7,982
  convictions after the day they became known; they keep their real dates.
- **Case reserves within limits.** Paid loss plus case reserve could exceed a per-person, per-accident or
  per-claim limit (61 features and 9 accidents); every reserve now stays inside what the coverage can pay.
- **Underinsured motorist.** The at-fault driver's insurer now pays within its per-accident limit too, so
  an accident with several injured occupants leaves more to our cover (the reviewer's example: $70,000,
  not $45,000), in the claims and the answer key's expected losses.
- **Telematics chronology.** Score windows start no earlier than the car and its driver joined the
  policy (6,741 did), and enrolments from before the extract no earlier than the policy's inception.
- **Quotes and telematics.** Every quote now offers the programme; prospects who did not bind opt in at the
  same modelled rate and get the same discount. New column `quote.telematics_opt_in`.
- **Real-data comparison.** `scripts/compare_real_data.py` scaled the answer key's expected losses down
  twice for rows starting before 2022 (its "true expected loss" Gini moves from 0.247 to 0.251).
- **Release contents.** Every release zip now carries `README.md`, `CHANGELOG.md` and `docs/`, which the
  README links to.
- **Like-for-like loss-ratio checks.** The answer key's expected losses exclude catastrophes, so
  `validate.py` now compares them with actual losses without catastrophes, and adds the year's
  catastrophe losses before comparing with industry loss ratios.
- **Documentation.** Statements that claimed more than the checks prove were corrected (liability limits
  do change at renewal; passing `validate.py` shows its rules hold, not that the data has no other flaw;
  the national comparison is approximate). New gaps the review named (claim handling history, payees,
  quote revisions) are listed in `docs/limitations.md`.

### Size and dates

- The default run is now **43,368 policies from 1 January 2022 to 31 December 2026**: five full calendar
  years, and smaller release files. About 24,000 policies are in force at the end, with 41,000 cars and
  $47 million of premium a year. 205,616 policy terms, 184,498 earned car-years, $189.7 million earned
  premium, 20,381 claims.
- Every calibration band holds: frequency 1.03 to 1.30 times national and severity 0.85 to 1.05 times;
  expected loss ratios (plus catastrophes) of 79.1%, 77.1%, 67.9% and 64.8% for 2022 to 2025 against the
  industry path; an overall loss ratio of 68.3%. Comprehensive and collision severity sit at the bottom
  of their band (0.85 and 0.86), as physical damage severity has run low in every recent run.
- `scripts/readme_figures.py` prints every run figure the README, changelog and limitations quote, so
  they can be refreshed after any change.

### Fixes from a third external review

A third review (at `9fe6062`) confirmed the earlier fixes and found two more decisions dated in the past
that used later information. Both are fixed; `docs/review_response.md` gives the before-and-after counts
and a controlled counterfactual.

- **Telematics scores belong to the driver who drove.** A car's score was generated from, and published
  against, the car's driver as it stood after the whole term had been simulated: 211 scores overlapped
  another driver's exposure and 48 named a driver who took the car over after the window. The simulator
  now keeps effective-dated histories (each car's rated driver and ZIP, each driver's marital status, each
  policy's named insured and homeowner status), and a window in which the car's driver changed is split
  there and each part scored as that driver's (165 splits in the default run). A car's discount is the
  days-weighted average of what its parts earned. Cars on the policy on the scoring date are scored even if
  they leave before the renewal. Fixed along the way: 4 scores of customers who had left the programme were
  linked to a term that began before them.
- **Renewals decided on the offer date.** The underwriting review, the telematics offer, the renewal premium
  and the customer's decision now use only the policy as it stood on the offer date (the expiring term's
  exposure rows in force that day), records known by then and claims reported by then, with their own
  random stream. A change before the effective date still re-rates the renewal (a revised offer), but cannot
  rewrite the offer or the decision. Holding the draws fixed, the old information would have changed 315 of
  174,487 decisions and the premium of 12,013 offers.
- **New table `renewal_offer`** (179,620 rows): every renewal evaluated, renewed or not, with its offer
  date, vehicles, expiring and renewal premium, premium change, telematics opt-in, underwriting decision,
  revised offer date and outcome (renewed, not renewed by the insured, company non-renewal, cancelled
  before renewal, or pending at the valuation date). The answer key's `renewal_offer_truth` has each
  offer's true acceptance probability. Customer contacts now include the offers that were declined and a
  notice for each company non-renewal. An opt-in to telematics at a renewal that was not taken is no
  longer an enrolment ending the day it began (257 were).
- **Checks.** `validate.py` checks scores against the exposure rows' driver on every day scored, the
  discount rule, and each offer against the exposure in force on its offer date and the policy terms'
  outcomes. Seven new tests, including a counterfactual one: every offer evaluated again at the end of the
  run, with the whole later history present, is the same offer and decision.
- **The default run after these fixes** (content hash `4b5bca69599df49e`): 205,742 policy terms, 460,831
  exposure rows, 184,833 earned car-years, $190.1 million earned premium, 20,343 claims, 12,298 telematics
  enrolments and 59,553 scores. Every calibration band holds: frequency 1.05 to 1.34 times national and
  severity 0.87 to 1.03 times; expected loss ratios (plus catastrophes) of 79.3%, 77.6%, 67.9% and 64.7%
  for 2022 to 2025; an overall loss ratio of 66.9%; annualised retention 83.4% (was 83.3%).

### A realism audit: an operating company's data

**Why.** An audit of the default run (at `ee55aa1`) asked a different question from the earlier reviews:
not whether the records are consistent, but whether they look like the data of a company that sells
insurance, employs people and pays its bills. Measured on the data, they did not:

| Finding | Before | After |
|---|---|---|
| Discounts ran backwards or were nil (effect on bodily injury premium) | Homeowner +13.7%, prior insurance +7.3%, good student +3.7%, six years' tenure +3.9%, multi-car +0.4%, multi-policy +0.7%, paid in full -2.0% | Filed: homeowner -5%, no prior insurance +8%, good student -10%, tenure -2% to -6%, multi-car -10%, multi-policy -8%, paid in full -6% |
| New business cost the same as renewals (expected loss ratio) | 69.2% against 68.8% | 77.9% against 68.0% |
| Claims no likelier early in a policy's life (per 100 policy-years) | 18.6 in the first 30 days, 18.9 after a year | 24.7 in the first 30 days, 18.2 after two years |
| Channels alike (expected loss ratio: direct, exclusive, independent) | 68.1%, 69.3%, 69.2% | 69.8%, 64.0%, 72.6% |
| Agencies alike | 24 agencies, expected loss ratios 65% to 73% | 58 agencies and two direct units, 56% to 91% (10th to 90th percentile 64% to 80%) |
| No week: claim payments dated on a Saturday or Sunday | 28.6% ($36.6 million) | None |
| Suits and convictions dated at a weekend | 28.5% and 28.8% | None |
| Winter crash claims a day no more varied than chance | Variance 5.25 against a mean of 5.29 | 6.09 against 4.99; 18 on the busiest day |
| Identifiers were counters that showed how the data was built | Policy IDs up to 1019949 were exactly the opening book; every policy's first term ID was its policy ID less 1,000,000; no business keys | IDs follow creation dates; policy, quote, claim and feature numbers, full VINs with check digits, unit and driver numbers |
| Injury settlements paid to the cent | About 1% of settlements below a limit were whole dollars | 86% of paid bodily injury features are whole dollars, 72% multiples of $250 |
| Non-payment cancellations spread evenly over the term from day 35 | | Three to four weeks after an instalment that was never paid |
| No cash, payees or people | 24 tables | 29: bills, receipts, employees, vendors and producers, and payee, cheque and approver on every claim payment |

**What changed.**

- **Hidden household stability** (`autoins/population.py`, `config.STABILITY_*`). Each household has a
  hidden trait, how settled it is, that lowers claim frequency and missed payments, raises retention, and
  makes it likelier to own its home, bundle, have had prior insurance, pay in full and have been a customer
  for longer. The book in force at the start is more stable than new business. The insurance score no longer
  uses homeownership (which made homeowners look worse at a given score) and reflects stability instead.
- **Filed discounts** (`config.FILED_DISCOUNTS`, `autoins/rating.py`). The eight discounts and surcharges
  are filed as round percentages; every other relativity is fitted around them. The answer key's
  `rating_plan.json` adds `filed_discounts` and `relativities_indicated` (each factor fitted freely), so each
  discount can be compared with what the risk justifies: multi-car and multi-policy are about right,
  the loyalty discount is a third of what tenure is worth, and the good-student and married discounts have
  no support once class and record are rated. Company placement no longer depends on homeownership or
  tenure, and a customer without prior insurance goes to the non-standard company only if the score or
  record is weak too; the companies now hold 30%, 58% and 12% of policies (were 25%, 66% and 9%).
- **New customers claim more** (`config.NEW_CUSTOMER`, `autoins/truth.py`): a burst in the first weeks and a
  fade over two or three years, on at-fault, parked, theft and vandalism losses, sized to the 13-point gap
  between new and renewal loss ratios a CAS study found across 25 books. Car on a multi-car policy: 10% fewer
  crashes each. Good students: 20% fewer (was 8%).
- **Channels and agencies** (`config.CHANNEL_*`, `AGENCY_*`). 44 independent and 14 exclusive agencies
  (were 16 and 8), each with a hidden book quality and hold on its customers; independent-agent business is
  a little worse, exclusive-agent customers stay longer, direct customers shop more.
- **The working calendar** (`autoins/refdata.py`, `reference/daily_index.csv`, `reference/hour_of_day.csv`).
  Crash and theft intensity follows Chicago's daily counts from 2021 to September 2026 (new downloads in
  `scripts/fetch_public_data.py --only calendar`, built by `scripts/build_calendar_reference.py`), so
  weekdays, holidays and storm days are real. A business-day calendar (federal holidays and the day after
  Thanksgiving) governs payments and their clearing, closes, reserve reviews, suits, fraud referrals,
  convictions and their posting, SR-22 filings, renewal offers, keyed policy changes and letters; weekend
  work is spread over the next week. About half of weekend first notices are held over. Agents quote on
  weekdays; 8.9% of new policies start on the 1st. `claim.loss_time` is new.
- **Round settlements** (`config.SETTLEMENT_STEPS`). Agreed bodily injury and uninsured motorist damages
  are rounded to steps that grow with size ($50 to $5,000); advances and supplements are round too.
- **Identifiers** (`autoins/identifiers.py`). `policy.policy_number` (serial, company code, two MOD 97-10
  check digits), `quote.quote_number`, `claim.claim_number`, `claim_feature.feature_number`,
  `insured_vehicle.vin` (17 characters, valid check digit, still beginning with `0`) and `unit_number`,
  `driver.driver_number`, `license_state` and `license_number_masked`, `agency.agency_code`,
  `underwriting_company.company_code` and `naic_style_code`. Integer keys are renumbered in creation order
  through the key map in `autoins/schema.py`.
- **Billing** (`autoins/billing.py`): `billing_invoice` (906,326 bills) and `billing_receipt` (917,096
  receipts): instalments, fees, late and returned payments, endorsements spread over the remaining
  instalments, cancellation settlements, refunds and write-offs. Non-payment cancellations follow a missed
  instalment (`simulate._missed_installment`), and billing notices in `customer_contact` come from the bills.
- **Commission.** `premium_transaction.commission_rate_pct` and `commission_amount`; each agency's rates and
  appointment date in `agency`; a `producer` table and `policy.producer_id`.
- **Claim payments** (`autoins/payments.py`): `employee` (desks, turnover, payment authority) and `vendor`
  (684 fictional organisations); `claim.adjuster_id`; and on `claim_payment` the payee type and name,
  vendor, method, cheque number, status, cleared date and approver.
- **Answer key.** `policy_truth` (stability, household risk factor) and `agency_truth` (book quality,
  retention effect).
- **Calibration.** Crash base rates up 9%, the target loss ratio at day-one cost levels 82.5% (was 77.5%:
  the fit now includes new customers' first-year claims), renewal base odds up a little, comprehensive
  severities up about 7% (like-for-like comprehensive severity had been at the bottom of its band).
- **Checks.** `validate.py` gains checks on the calendar, identifiers and their check digits, creation
  order, billing against the ledger and the cash, non-payment timing, cheque sequence, approval and
  employment, payees and vendors, commission and the filed discounts, and bands on the new-business gap,
  the spread across agencies, retention by channel, round settlements and the weekday pattern of crashes.
  14 new tests (56 in all). The SQLite loader keeps ZIP codes as text where a table has blanks.
- **The default run after these changes** (content hash `ee6e59c038858485`): 202,389 policy terms, 451,997
  exposure rows, 179,915 earned car-years, $181.2 million earned premium ($1,007 per car-year, was $1,028),
  19,784 claims. Frequency 1.03 to 1.24 times national and severity 0.88 to 1.03 times; expected loss ratios
  (plus catastrophes) of 80.4%, 78.2%, 68.1% and 65.4% for 2022 to 2025; an overall loss ratio of 68.6%;
  annualised retention 82.6%. Two other builds (seed 7; 20,000 policies with seed 99) pass every check.
  Generation takes about 85 seconds (was 60) and the files are 435 MB (were 245 MB), a third of it billing.

**Left as it was.** New business and quote volumes are still level through the year and across years;
physical damage premiums and take-up are still below Illinois' averages (collision and comprehensive about a
third lower per covered car; collision carried on 67% of cars against 83% statewide); claims still barely
drive customers away; there is no general ledger and no planted error or fraud. All are in
[docs/limitations.md](docs/limitations.md).

## 2026-11-15: Audit fixes and like-for-like calibration ([PR #3](https://github.com/subwaymatch/auto-insurance-synthetic-data-test/pull/3))

A second review of the generated data raised five findings. All five were confirmed and fixed,
three more defects turned up while fixing them, and two items were documented as limits rather
than built. Commit `5232739`.

### Calibration and validation

- **Comparing like with like.** The national benchmark (Triple-I's table of ISO data, "Private
  Passenger Auto Insurance Losses") defines its figures in specific ways: bodily injury and property
  damage costs include loss adjustment expense (LAE, the cost of handling a claim), collision and
  comprehensive are for a $500 deductible, and comprehensive excludes wind and water losses.
  `validate.py` now builds the same slices from the dataset (claims counted in the calendar year of
  their first payment, liability with expense, only cars with a $500 deductible, comprehensive
  without hail, wind, flood and catastrophe claims) and holds them to tolerance bands.
- **What that revealed.** On matching definitions the data was further off than it had looked.
  Comprehensive had matched only because it counted weather claims the benchmark leaves out. Glass,
  theft, vandalism, animal and other comprehensive claims were retuned, and collision severity was
  raised about 6%. Ratios to national (frequency = paid claims per 100 car-years, a car-year being
  one car insured for one year; severity = average paid per claim):

  | Ratio to national | Before | After |
  |---|---|---|
  | Comprehensive frequency | 0.66 to 0.76 | 1.08 |
  | Comprehensive severity | 0.80 to 0.89 | 0.90 |
  | Collision severity | 0.79 to 1.03 | 0.98 |

- Average premium moved from $1,050 to $1,113 per car-year; loss ratios by year stayed on the
  industry path. `validate.py` now holds frequency to 0.85 to 1.45 times national and severity to
  0.85 to 1.15 times, checks every coverage's limits and deductibles, and reconciles vehicle counts
  across tables.

### Coverage limits and the answer key

- **Underinsured motorist limits.** Underinsured motorist (UIM) cover pays for the insured's own
  injuries when the at-fault driver's insurance is too small. UIM payments now stay within the
  per-accident limit less what the at-fault driver's insurer paid, as Illinois law sets it out.
  Per-accident limits are shared among claimants in whole cents, so an accident totals its limit
  exactly (a one-cent overage is gone). `claim_coverage_fact` gains `UM/UIM Type` (uninsured or
  underinsured) and `Other Insurer Payment`.
- **Expected losses now allow for per-accident limits.** The answer key (the instructor-only truth
  behind the data) overstated bodily injury expected loss by about 2.4% on 25/50 policies ($25,000 per
  person, $50,000 per accident). Simulated over expected is now 1.000 at that limit over 600
  simulated years.

### Claims and timing

- **Lawsuits in order.** A litigated claim now follows attorney, then suit, then closing at least 30
  days later. A claim drawn to close too soon stays open longer instead of the suit moving ahead of
  the attorney (a case found in seed 7, now a unit test).
- **Same-day ordering.** The data holds dates, not times. A company claim now reaches the driving
  record the day after the payment that makes it chargeable (counted against the driver at
  renewal), so a loss or payment on a rating date (the day a term is priced) is never part of that
  rating. The simulation and the validator apply the same rule.
- **Nothing after the valuation date** (the "as of" date of the extract). A car lost on that date
  had shown a removal dated the next day, and a removal was labelled "Total Loss" (written off by the
  insurer) before the claim was reported, which revealed claims the insurer could not yet know about.

### Policies and drivers

- **Current counts.** `policy_dimension.Number of Vehicles` is now counted as at the policy's latest
  status; 997 in-force policies were wrong before. The count at the start of a term is kept as
  `policy_term_fact.Vehicles at Term Start` (renamed from `Vehicle Count`).
- **No departed rated driver.** When two drivers left a policy on the same day (the named insured,
  i.e. the policyholder, died and the spouse divorced that day), the policy was left with no active
  driver. Fixed.
- `risk_fact` (the rating record: one row per car for each period of a term) now carries full glass,
  rental option and towing for each period, so these coverage terms are dated like the others.

### Documentation

- The README explains current versus historical values, the three kinds of loss ratio (pure loss
  ratio, loss plus claim-handling expense, and combined ratio, which also adds the insurer's other
  costs), and the limits left in place: no claims from before the start date (no "opening claim
  inventory"), fault percentage is descriptive and does not reduce payments, and the rating plan is
  fitted to the simulator's truth, so it is cleaner than a real insurer's.

### Checks and compatibility

- 27 unit tests pass (8 new). `validate.py` passes on full runs for seeds 20250101, 7, 42 and 99;
  seed 7 had failed two checks before.
- Breaking for users of the previous release: `Vehicle Count` is renamed, `risk_fact` and
  `claim_coverage_fact` have new columns, and all values change.

| Default run | Before ([PR #2](https://github.com/subwaymatch/auto-insurance-synthetic-data-test/pull/2)) | After |
|---|---|---|
| Earned premium | $128.8M ($1,050 per car-year) | $136.5M ($1,113 per car-year) |
| Claims / coverage features (one per coverage and injured person on a claim) | 12,776 / 23,579 | 14,042 / 24,847 |
| Expected loss ratio (answer key), 2022 to 2025 | 78.0%, 74.2%, 64.7%, 62.3% | 77.8%, 73.8%, 64.2%, 62.0% |

## 2026-11-14: Record-level realism, household changes and industry calibration ([PR #2](https://github.com/subwaymatch/auto-insurance-synthetic-data-test/pull/2))

This stage began with a record-level realism audit of the [PR #1](https://github.com/subwaymatch/auto-insurance-synthetic-data-test/pull/1) data. It fixed the audit's
findings, modelled what the audit had left to judgement, recalibrated loss ratios against sourced industry
figures, filled the main gaps against how insurers actually hold their data, and moved the data out
of the repository into releases. Overall calibration and the teaching signals were kept, and the same
seed still gives identical files. Commits `07718b1`, `2131252`, `145593f`, `821e1dd`, `2e471ae`.

### The audit, before and after

| Finding | Before | After |
|---|---|---|
| Vehicles still rated after their total-loss claim closed | 1,053 | 0 |
| Vehicles with claims after their total loss | 213 (245 claims) | 0 |
| Risk rows rated with information not yet known on the rating date | not tracked | 0 (checked on every row) |
| Exposure, January vs December 2022 (car-years) | 183 vs 2,225 | about 1,950 vs 2,100 |
| Terms starting on the 29th to 31st | 0 | about 7.6%, no anniversary drift |
| Loss payments made on the close date | 86.6% | about 43% |
| Good-student discount at age 25 or over | 312 risk rows | 0 |
| Opening-book policies on term 1 but labelled "Renewal" | 1,946 | 0 |

### Policies and exposure

- **Opening book** (policies already in force when the data begins). Policies in force on 1 January
  2022 now enter part-way through their term; only premium and exposure after that date count, and
  earlier premium is reported separately (`Earned Before Extract`). This removed the artificial
  ramp-up in 2022 exposure.
- **Anniversaries** can fall on any day; in short months a term starts on the last day and the next
  one returns to the original day.
- **Mid-term household changes.** Households now move within the metro, trade in, buy and sell cars,
  add newly licensed teenagers and new spouses, and lose drivers who move out, divorce or die. Each
  change is an endorsement (a change to a policy during its term, charged or refunded pro rata) that
  re-rates the policy from that day. Rates come from public data (ACS, CPS, CDC, FHWA and
  auto-market data); for example 5.5% of homeowners and 20% of renters move each year. Before, all
  household changes happened only at renewal.
- **Renewal coverage changes:** loans paid off, older cars dropping collision cover, and deductibles
  raised after large price increases.
- **Good-student discount** ends when school ends or at 25, judged term by term.
- A new `policy_transaction_fact` premium ledger records every new business, renewal, endorsement
  and cancellation with its effective and processed (accounting) dates.

### Vehicles and total losses

- A total loss (a car the insurer writes off) now ends the car's cover the day after the loss, and
  nothing later happens to it. Most households buy a replacement, which joins with a new vehicle ID
  pointing back to the old one; a one-car policy with no replacement is cancelled.
- Cars destroyed or stolen without the insurer paying (no collision cover, the other driver's insurer
  paid, or the claim not pursued) also leave the policy. An owner keeps a car the insurer paid as a
  total loss only where Illinois law allows it.

### What the insurer knew, and when

- Each term now has a rating date (30 to 45 days before a renewal). Pricing, non-renewal decisions and
  the customer's choice to renew use only what was known by then. A traffic violation counts once it
  posts to the driving record (about two months); the insurer's own at-fault claim counts once its
  payments reach the $1,000 surcharge threshold. So a violation or claim that arrives shortly before
  a renewal's rating date is surcharged a term later.

### Claims

- **Payment histories** follow the coverage: first estimates and later supplements, loss-of-use
  payments, injury advances, medical bills, total-loss payments split between the car loan lender
  and the owner, voided and reissued payments, and reopened claims, all adding up to the cent.
- **Claims that pay nothing** (liability denied, injury never pursued, damage withdrawn) are now
  included: 42% of closed liability features and about 20% of physical damage features close
  without payment, near the industry's 2025 figures of about 45% and just under 25%.
- **Reporting delays** for injury claims follow a published actuarial study (CAS): 84% of bodily
  injury claims reported within 5 days, 97.5% within 90 days and 99.2% within a year, bounded by
  Illinois' statutes of limitations. They set how many claims are still unreported at the valuation
  date (IBNR, "incurred but not reported").
- **Reserve history.** A new `claim_reserve_fact` records every change to a claim's case reserve (the
  adjuster's estimate of what is still to be paid). Early injury estimates average about 86% of the
  final cost, so bodily injury losses develop upward as claims mature while collision barely moves.
  Incurred losses (paid plus reserves) can be rebuilt as of any date, so development triangles, the
  basic reserving tool, can be built from the data.
- **Claim expenses** are split into defence and cost containment (DCC, such as legal bills) and
  adjusting and other (A&O), with expense reserves on litigated claims.
- **Claim detail:** attorney representation and dates (at Insurance Research Council levels), suits
  within Illinois' two-year limit, injury type, police reports, the insured's share of fault under
  Illinois' modified comparative fault rule, and fraud referrals.

### Coverages, pricing detail and new business

- New coverages: underinsured motorist (within uninsured motorist, as in Illinois), rental
  reimbursement, and towing and labor, each with premium, expected loss and claims.
- Fictional VIN prefixes and vehicle symbols, limits on each rating row (with limit changes at
  renewal), applied discounts, SR-22 filings (proof of insurance some drivers must file with the
  state, for example after a DUI) and conviction dates on violations.
- A new `quote_fact` table holds the new-business funnel: 85,273 quotes, 18.9% bound. Conversion
  varies by sales channel and falls as a quote rises above competitors' prices.

### Calibration and validation

- The opening price adequacy and the rate schedule were recalibrated so the expected loss ratio by
  accident year (claims grouped by the year the accident happened; the expected figure comes from
  the answer key and is free of claim luck) follows industry figures. Before this, it ran 73%
  (2022), 72% (2023), 64% (2024) and 60% (2025). `validate.py` now guards the path.

  | Loss ratio by accident year | 2022 | 2023 | 2024 | 2025 |
  |---|---|---|---|---|
  | This dataset, expected | 78.0% | 74.2% | 64.7% | 62.3% |
  | This dataset, actual (default seed) | 74.8% | 74.5% | 71.1% | 61.4% |
  | US private passenger auto | 80.2% | 75.4% | 66.1% | 61.5% |
  | Illinois private passenger auto | 79.6% | 72.8% | 63.4% | 60.1% |

- `validate.py` checks each audit criterion (57 checks pass on the default build) and 19 unit tests
  pass. The README gained an industry comparison with sources and a comparison with insurers' own
  data models.

### Data publishing (infrastructure only)

- Release files are built per format through a small registry; CSV ships now, and Parquet, SQLite or
  Excel can be added as one function each. On books under 20,000 policies, calibration bands become
  warnings, because a few hundred claims are too few to hold them.
- The generated data is no longer committed. Every push to `main` that changes the generator, its
  reference data, the release scripts or the README rebuilds the default dataset as a rolling
  `latest` pre-release with stable download links; version tags and manual runs publish fixed
  releases. Release notes record the source commit. Older committed copies remain in the git
  history, which stays at about 150 MB.

| Default run | Before ([PR #1](https://github.com/subwaymatch/auto-insurance-synthetic-data-test/pull/1)) | After |
|---|---|---|
| CSV tables | 19 | 22 (premium ledger, reserve history, quotes) |
| Policy terms | 130,794 | 137,729 (13,747 already in force on the start date) |
| Drivers / vehicles | 52,021 / 61,710 | 53,114 / 75,749 |
| Risk rows starting at a mid-term change | none (no mid-term changes) | 23.6% (42,351 endorsements) |
| Earned premium | $125.5M ($1,043 per car-year) | $128.8M ($1,050 per car-year) |
| Claims / coverage features | 10,407 / 14,356 | 12,776 / 23,579 |

## 2026-11-13: A simulated Chicago-area book ([PR #1](https://github.com/subwaymatch/auto-insurance-synthetic-data-test/pull/1))

The old dataset was replaced by a seeded simulation built on real ZIP-level data for Cook, DuPage,
Lake, Will, Kane, McHenry and Kendall counties. Commits `030d09d` (generator) and `ff2a955` (dataset
and release workflow).

### Geography and households

- 290 real ZIP codes with Census demographics (ACS 2020-2024). Crash and theft hazard for city ZIPs
  comes from City of Chicago police records; suburban hazard is modelled from income, because the city
  data does not cover the suburbs.
- Policies are placed in ZIPs in proportion to vehicle-owning households, and drivers, vehicles and
  coverages are drawn from each ZIP's age, income, vehicle and commuting profile.

### Risk and claims

- **True risk first.** Every driver has a hidden risk factor. Claims, prior accidents and violations
  are all generated from it, so the driving record predicts claims, imperfectly, as in real data. The
  old dataset had no such link.
- **Claim lifecycle.** Losses are simulated by cause and split into coverages with limits and
  deductibles. Each claim gets report and close dates, payments, expenses, salvage (money from selling
  the wreck), subrogation (money recovered from the party at fault) and a case reserve if still open.
  Claims not yet reported by the valuation date are left out, as in a real extract.

### Pricing and policies

- **A separate, imperfect rating plan.** Premiums come from a plan that sees only what an insurer
  would see. It is fitted by minimum bias (a classic actuarial method for setting rating factors) to
  the true expected cost, then deliberately distorted, leaving real pricing gaps for students to find:
  young drivers under-priced, mileage under-used, the Kia/Hyundai theft wave and automatic emergency
  braking unpriced, and insurance score priced correctly.
- **Policy life.** Renewals, lapses that rise after price increases, mid-term cancellations, vehicle
  replacement and teenage drivers added at renewal.
- Premiums are higher in ZIP codes with more non-white residents (ZIP-level correlation 0.71) because
  the underlying crash and theft data is; this was left in on request. The expected loss ratio does
  not vary with it (-0.02), so no over- or under-charging by area is planted.

### Calibration and validation

- Loss ratio by accident year: 82.6%, 76.3%, 63.4%, 65.1% and 60.7% (2022 to 2026, the last nine
  months), against about 20% in the old dataset. This mirrors the industry cycle: under-priced
  entering 2022, then rate increases catching up.
- Paid claim frequency and severity land close to Triple-I / ISO national figures for 2022 to 2024.
- Every assumption sits in one file, marked ANCHORED (published figure), TUNED (set to hit one) or
  ASSUMED (judgement).
- `validate.py` reports calibration and integrity; it passed for the default seed and seeds 1, 2 and
  3, and 4 unit tests passed. The same seed gives byte-identical files.
- Not yet modelled at this stage: mid-term endorsements, drivers leaving a policy, fraud and reopened
  claims.

| Default run | |
|---|---|
| Policies / terms | 30,000 / 130,794 |
| Earned car-years | 120,398 |
| Earned premium | $125.5M ($1,043 per car-year) |
| Claims | 10,407 |

### Data publishing (infrastructure only)

- The default dataset, including the answer key, was committed under `output/` (with a warning that
  anyone with repository access can see the answer key).
- A release workflow, run on a version tag or by hand, tests, generates and validates the data and
  publishes a GitHub release: a student data zip, a separate answer-key zip, the validation report and
  checksums. numpy and pandas versions are pinned so a seed always reproduces the same values.

## 2026-11-13: Starting point

The repository was created on GitHub with a one-line README (commit `129e31c`, no pull request).
The goal was to replace an older synthetic dataset that:

- used California geography rather than the Chicago area;
- had a loss ratio near 20%, where real US private auto insurers ran about 60% to 80% in 2022 to 2025;
- showed no relationship between driver risk and claims.

Its table names were kept where an equivalent exists, so existing case material still maps (the
README's "Mapping from the old dataset" lists the changes, such as one row per policy term becoming a
policy table plus a term table).
