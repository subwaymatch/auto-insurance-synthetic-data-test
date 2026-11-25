# Realism audit of the Chicago auto insurance dataset, v1.1.10

Reviewed November 25, 2026. The audited revision of `main` and tag `v1.1.10` is `7f6f4d1c393e3873365b3e7474dd98dfcc036849`, which includes the fixes from PRs #16–18. This report covers fresh builds from that revision. [Audited source](https://github.com/subwaymatch/auto-insurance-synthetic-data-test/tree/7f6f4d1c393e3873365b3e7474dd98dfcc036849) · [Prior findings and responses](review_response.md)

**Verdict.** The book is credible for teaching portfolio-level premium, loss ratios, and retention. The claim-cost distribution resembles the real comparison portfolio through much of its range, and the simulated book reproduces the expected direction of customer attrition after a claim. Two uses need particular care. A small set of original renewal offers uses information received weeks later. Roughly two-thirds of the published hard-braking rates cannot have come from a whole number of events over the recorded miles. Fix the renewal history first for point-in-time modeling, and the event rates first for driving-behavior exercises.

## What reproduced

The default and alternate runs each contain 43,368 policies, 34 operational tables and nine answer-key tables, with coverage observed from January 1, 2022 through the simulated valuation date of December 31, 2026. Both hashes match the previous audit's post-fix baseline. Python 3.13.5, NumPy 2.5.3 and pandas 3.0.5 produced these results.

| Measure | Default seed 20250101 | Seed 101 |
|---|---:|---:|
| CSV content hash, including the answer key | `9774ec39a673aeea` | `ccf9e0445a89c5c8` |
| Earned car-years | 174,150 | 172,911 |
| Claims / coverage features | 22,670 / 39,879 | 22,528 / 39,188 |
| Earned premium | $212.15m | $207.86m |
| Net incurred loss / earned premium | 70.5% | 69.0% |
| Annualized retention, as reported by the validator | 81.2% | 81.1% |
| Repository validation checks passed | 203 / 203 | 203 / 203 |

All 88 unit tests passed. In particular, the recent checks passed for the booking of backdated removals, the occasional youthful operator surcharge, notices after cancellation and repeat losses on owner-retained salvage. The default removal check covered 4,384 reported removals and examined 40 unreported physical-damage features in the answer key. Finding 1 concerns the **original offer sent between the effective removal and its booking**, a different observable consequence.

**External comparisons.** On the default run, collision coverage was carried for 83.3% of 2023 exposure against 82.6% in Illinois, and comprehensive for 88.2% against 87.5%. The national calendar-year comparison put collision frequency at 1.31 times the benchmark and severity at 0.90 times it. These are tuning targets. A fresh run of the repository's comparison with the real motor portfolio found that the costliest 1% of positive-cost vehicle-periods account for 16.0% of synthetic losses and 23.8% of real losses. A frequency model using shared factors achieved a held-out claim-count Gini of 0.106 on synthetic policies and 0.222 on real contracts. Different markets, coverages, limits, period lengths and defects in the real claim counts limit the comparison. The evidence supports exercises in portfolio analysis. It gives less confidence in extreme-loss estimates or model performance for an actual Chicago insurer. [Benchmark methods and sources](benchmarks.md) · [Real portfolio and definitions](real_data_comparison.md) · [Lledó and Pavía, Mendeley Data](https://doi.org/10.17632/5cxyb5fp4f.2)

## Findings for the next coding agent

Counts below use the default run first and seed 101 second. Record IDs identify the default run unless stated otherwise. The SQL runs against the release-format SQLite database. The same predicates work against the generated CSVs.

### 1. High priority · Original renewal offers use backdated removals before first notice

**Evidence.** In each seed, 41 original offers exclude a car whose removal was backdated to the day after loss and whose claim was first reported after the offer. The offers include 51 and 60 surviving-car exposure rows, respectively, that were rated after the offer. The total offer populations are 168,956 and 168,279. The portfolio effect is small, but the error directly affects an exercise about what the insurer knew when it priced a renewal.

Policy `48529` gives a full example. The two cars on term `1670508` carried full-term premiums of $830.85 and $1,008.36, both with the multi-car discount. The April 8, 2022 offer `1733691` shows one vehicle and an expiring premium of $923.17. That is precisely the surviving car's premium **without** the discount, calculated May 9 when claim `136723` was reported. The removal was then effective back to January 26. The original offer should show two cars and $1,839.21 in expiring premium. May 9 is a legitimate date for the revised offer.

```sql
SELECT COUNT(DISTINCT o.renewal_offer_id) AS affected_offers,
       COUNT(*) AS rows_rated_later
FROM renewal_offer AS o
JOIN exposure AS e ON e.policy_term_id = o.expiring_policy_term_id
WHERE e.coverage_start_date <= o.offer_date
  AND o.offer_date < e.coverage_end_date
  AND e.rating_date > o.offer_date;
```

**Repair and acceptance.** In `autoins/simulate.py::evaluate_offers`, rebuild the original car list and rating inputs from events known on the offer day. A filter on `rating_date` alone loses the superseded versions of both cars. Preserve or replay the pre-endorsement state, including the discount and expiring premium. Change `validate.py::integrity_renewals`, which currently validates the offer against the same retrospectively shortened coverage intervals. The query above identifies the old symptom. After a repair, backdated exposure rows can still match it. Test the **offer values** against an independently constructed two-car fixture with loss, offer, report and renewal in that order. Moving first notice later must leave the original offer unchanged and affect the revision on the appropriate date.

### 2. High priority for telematics · Published event rates imply fractional events

**Evidence.** Of 61,927 default score windows, 40,916 have a hard-brake rate incompatible with any integer count and 41,213 have an incompatible rapid-acceleration rate. Seed 101 gives 40,431 and 40,652 out of 61,062. This affects scored windows too, including 39,964 default hard-brake rows with a nonblank driving score. Score row `282508` records 3 miles in one day, 0.70 hard brakes per 100 miles and 1.34 rapid accelerations per 100 miles. Even allowing half a mile and 0.005 events per 100 miles for rounding, neither rate can represent zero or one event.

```sql
WITH bounds AS (
  SELECT MAX(0, miles_driven - 0.5) *
           MAX(0, hard_brakes_per_100_miles - 0.005) / 100 AS lo,
         (miles_driven + 0.5) *
           (hard_brakes_per_100_miles + 0.005) / 100 AS hi
  FROM telematics_score
)
SELECT COUNT(*) FROM bounds
WHERE CAST(hi + 1e-10 AS INTEGER) < lo - 1e-10;
```

**Repair and acceptance.** `autoins/telematics.py::metrics` draws a continuous rate independently of the window's actual miles. Use it as an underlying intensity, draw whole events over the driven miles, and compute the published rates from those counts. Apply the same logic to the shortened windows in `autoins/simulate.py::_record_scores`. Make zero-event windows valid in the logarithmic score formula and define the zero-mile convention. The feasibility query should return zero for both event fields. Check score and discount distributions across short and long windows after the change.

### 3. Medium priority · A historical report's posting date is labeled as the insurer's knowledge date

**Evidence.** Restrict to bound new-business quotes, drivers added on the proposed effective date, and incidents sourced from a motor vehicle record or prior carrier report. Of 16,644 qualifying default incident rows, 12,233 have `known_date < quote_date`. In 7,777 cases across 6,151 policies, the date leads the quote by more than a year. The alternate counts are 12,058 of 16,538, with 7,693 more than a year early. For incident `212131` the prior carrier report date is February 26, 2019. Lakefront's quote `604121` is dated January 29, 2022.

**Repair and acceptance.** `autoins/population.py::prior_accidents` and `violations` generate a date when the source record becomes available. `autoins/tables.py::build` publishes that date under a dictionary definition of “Date the insurer learned of the incident.” Choose the intended field meaning. A source-availability field can preserve the values with explicit documentation. If the exercise needs carrier knowledge, retain the posting date separately and record receipt at the quote, driver addition or later modeled inquiry. Records already available on the quote day must still inform placement. Test a pre-quote posting and a post-quote posting separately. [Current field definition](../site/dictionary/policies.toml)

### 4. Medium priority · The vehicle-theft answer key flags an entire make/year cohort

**Evidence.** Every non-electric 2011–2021 Kia or Hyundai in the two books has `anti_theft_device = 'N'` and `kia_hyundai_theft_exposure = 'Y'` (6,216 of 6,216 and 6,248 of 6,248). For model year 2015 alone, the default includes 528 cars across 19 model names. HLDI reports that passive immobilizers were standard on 26% of 2015 Hyundai and Kia **vehicle series**, rising to 78% for 2021. Those percentages count series. Applying them directly to insured vehicles would introduce a different error. The existing check confirms that flagged cars lack the device, while the cohort rule decides both flags. The issue matters for the README's theft pricing exercise. [HLDI bulletin, pp. 1–2](https://www.iihs.org/media/0e14ba17-a3c2-4375-8e66-081df9101ed2/opm7QA/HLDI%20Research/Bulletins/hldi_bulletin_38-28.pdf)

**Repair and acceptance.** In `autoins/population.py::draw_vehicles`, start from documented series/model-year equipment, use a documented assumption for mixed trims, and derive risk and both flags from that assignment. Verify at least one corroborated equipped series and one exposed series, and report the model-series mix separately from the insured-car mix. Retain the insured-exposure denominator when rerunning the theft comparison.

### 5. Medium priority · Calendar birthdays sometimes move a driver into the wrong rating class

**Evidence.** Joining exposure to driver and calculating completed calendar years at `coverage_start_date` gives 577 discrepancies across 315 default drivers, and 521 across 305 alternate drivers. Of these rows, 70 and 58 cross a filed rating-class boundary. None of the discrepant rows involves a February 29 birth. Exposure `4189920` rates a driver born January 19, 2001 as age 20, class `18-20 F`, on January 19, 2022, her 21st birthday.

**Repair and acceptance.** `autoins/rating.py::codes` and the age published from `autoins/simulate.py::_simulate_rows` divide elapsed days by 365.25. For completed age, subtract birth year from coverage year and subtract one if the birthday is still ahead that year. Use the same definition for quoted age and age-dependent rating boundaries. Test the day before, on, and after a class-changing birthday, and document a February 29 convention. Verify the published class as well as the age.

### 6. Medium priority for claims accounting · A void can precede the check it reverses

**Evidence.** Eight of 75 voids on the default run and nine of 59 on seed 101 have a lower payment ID than the original check. Both rows are dated the same day. On February 8, 2022, payment `353990` voids check `3418697` for $1,090.09. The original issue has the later ID `354005`. Replaying loss rows by payment ID produces a negative paid-to-date balance on the affected example, even though the daily result reconciles.

```sql
SELECT v.payment_id AS void_id, p.payment_id AS issue_id, v.check_number
FROM claim_payment AS v
JOIN claim_payment AS p USING (check_number)
WHERE v.transaction_type = 'Void' AND p.transaction_type <> 'Void'
  AND v.payment_id < p.payment_id;
```

**Repair and acceptance.** `autoins/claims.py::_schedule` orders same-day legs by signed cents before assigning their sequence. Give linked check legs a causal order (issue, void, reissue), carry that ordering through `develop` and ID assignment, and preserve date and amount reconciliation. The query should return zero. Test an original payment, void and reissue on one day and an unrelated payment on the same feature.

### 7. Medium priority for custom extracts · A mid-December valuation closes the financial year early

**Evidence.** On seed 11 with 1,500 policies valued December 15, 2025, the ledger posted all three company year-end closings on December 15 (36 lines). Account 3000 received $891,643.64 in credits across the three journals. The validator passed the build with 14 small-book calibration warnings. The two full-year books correctly show zero early closing rows.

```sql
SELECT journal_number, posting_date, credit - debit AS surplus_change
FROM gl_journal
WHERE journal_type = 'Year-end closing' AND account_number = 3000
  AND substr(posting_date, 6) <> '12-31';
```

**Repair and acceptance.** `autoins/ledger.py::build` treats every December accounting period as a year-end, while its posting date is capped at valuation. Gate closing on the actual December 31 falling inside the observed interval. Check the date and the unclosed current-year income balances in `validate.py::integrity_ledger`. A December 15 build should retain earlier years' closings and leave the current year's income open. A December 31 build should close each company once.

### 8. Lower priority · Animal collisions inherit the named insured as driver

**Evidence.** The default has 529 `ANIMAL` claims and seed 101 has 579. The cause dictionary calls these “Collision with animal.” In `autoins/truth.py::simulate`, the comprehensive-loss path passes a missing driver for every occurrence. `autoins/tables.py::build` then fills in the named insured on the date of loss. In 167 and 181 claims respectively, that ID differs from the vehicle's rated main driver. The actual driver can differ from the main driver. What the code establishes is that no operator is drawn for any animal collision.

**Repair and acceptance.** For an animal strike while driving, select an active operator using the car's usage distribution and carry that ID through to the claim. Keep the comprehensive coverage and its fault treatment. If animal damage while parked is intended too, distinguish that event in the model or document the proxy explicitly. Test a car shared by two drivers, plus a parked loss for which the named-insured fallback is appropriate.

## Reproduction and verification

Run from a checkout of the audited revision with the pinned dependencies in `requirements.txt`. Use fresh output directories. The small December build isolates finding 7.

```bash
python -m unittest discover tests
python generate.py --seed 20250101 --out work/default
python validate.py --out work/default
python generate.py --seed 101 --out work/seed101
python validate.py --out work/seed101
python scripts/compare_real_data.py --synthetic work/default --real real_data/mendeley_motor_portfolio
python generate.py --seed 11 --policies 1500 --valuation 2025-12-15 --out work/dec15
python validate.py --out work/dec15
```

The IDs and content hashes above identify **pre-fix** fixtures. Once generation changes, preserve the business conditions in small deterministic tests and rerun the two full books to measure prevalence and calibration. The cross-market comparison and the two full-size seeds bound what this review can say about aggregate realism. Local subgroup experience, extreme losses and an individual carrier's workflows still need independent evidence.
