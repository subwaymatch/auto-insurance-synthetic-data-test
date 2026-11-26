# Chicago auto insurance dataset realism audit

**November 25, 2026 · Coding-agent handoff · v1.1.11**

The regenerated dataset is credible for teaching portfolio-level premium, loss ratios, billing reconciliation, and retention. The strongest remaining defects concern what the insurer knew when it acted. In both full-size runs, a total-loss report can change a renewal bill or suppress an offer before the report arrives. Fix those two paths together for point-in-time exercises. The nonrenewal rule also needs a tenure check and a recorded reason if the dataset is used to teach Illinois-specific underwriting workflows.

The fast-forward pull reported that the checkout already matched `origin/main`. The remote branch and released tag resolved to `04e6659d7f47733db58bb5666628edf6429aad96`. This audit follows PR #19 and uses fresh builds. All 34 operational and nine answer-key CSVs from the default run matched the published release byte for byte. [Audited source](https://github.com/subwaymatch/auto-insurance-synthetic-data-test/tree/04e6659d7f47733db58bb5666628edf6429aad96) · [v1.1.11 release](https://github.com/subwaymatch/auto-insurance-synthetic-data-test/releases/tag/v1.1.11) · [Previous audit](realism-audit-v1.1.10.md)

## Reproduction and regression checks

Both full books have 43,368 policies and run from January 1, 2022 through December 31, 2026. The runtime was Python 3.13.5, NumPy 2.5.3, pandas 3.0.5, and PyArrow 26.0.1. All 93 unit tests passed. The suite emitted one NumPy divide warning in the rating test run. [Test suite](../tests/test_generator.py) · [Pinned dependencies](../requirements.txt) · [Release dependencies](../requirements-release.txt)

| Measure | Default seed 20250101 | Seed 101 |
|---|---:|---:|
| Content hash, including answer-key CSVs | `f50d197acf7a40b4` | `f7c338f8f7c20dce` |
| Earned car-years | 174,189 | 172,308 |
| Earned premium | $211.58m | $206.01m |
| Claims / coverage features | 22,831 / 39,840 | 22,309 / 38,905 |
| Overall net incurred loss ratio | 71.2% | 70.1% |
| Annualized retention | 81.3% | 81.0% |
| Repository validator | 207 / 207 | 207 / 207 |

Independent CSV joins reproduced these results from the latest fixes.

- **Original renewal snapshot.** For 44 default and 32 alternate original offers made between a physical total loss's effective removal and its report, I could reconstruct the pre-removal exposure state without an intervening exposure start. The original vehicle count and expiring premium matched in all 76 offers. Findings 1 and 2 cover renewal issuance and offer eligibility. [Offer snapshot](../autoins/simulate.py#L1141)
- **Telematics event counts and driver ages.** Both braking and acceleration rates were compatible with integer events on the published miles in all 61,628 and 60,271 score windows. Completed calendar ages matched in all 443,856 and 439,209 exposure rows. [Telematics calculation](../autoins/telematics.py#L68) · [Calendar age](../autoins/refdata.py)
- **Payment ordering and year-end close.** All 47 and 46 matched voids followed the original check in payment ID order. A separate 1,500-policy build at December 15, 2025 closed 2022 through 2024 and left 2025 open. It passed integrity checks and emitted 10 small-book calibration warnings. [Payment ordering](../autoins/claims.py#L526) · [Ledger generation](../autoins/ledger.py#L106)

## How realistic is the book?

The real-portfolio comparison still supports portfolio analysis and gives weaker support to large-loss and model-performance exercises. The costliest 1% of positive-cost vehicle-periods accounted for 17.7% of synthetic cost and 23.8% of real cost. The held-out claim-count Gini for the shared-factor model was 0.104 synthetic and 0.222 real. The real portfolio comes from a different market and has known claim-count defects. Use these figures to discuss distribution shape and predictive signal. [Real portfolio comparison](real_data_comparison.md) · [Lledó and Pavía dataset](https://doi.org/10.17632/5cxyb5fp4f.2)

Policies with claims end more often in both books. Using the comparison script's definitions, the synthetic exit rates were 28.7% with a claim and 18.1% without, against 32.5% and 22.4% in the real portfolio. The generator was tuned to that relationship. Default 2023 collision and comprehensive take-up was 83.6% and 88.4%, against 82.6% and 87.5% in Illinois. Those values were calibration targets. Average written premium per insured car-year was 1.04, 0.85 and 0.90 times the Illinois liability, collision and comprehensive comparisons for 2022–2024, respectively. The benchmark sheet labels those premium comparisons as checked. The benchmark sheet records definitions, grouping, geography, and seed spread. Chicago carrier-level predictive accuracy, local subgroup results, and the extreme-loss tail remain unverified. [Benchmark methods](benchmarks.md) · [Comparison script](../scripts/compare_real_data.py)

## 1. High priority for point-in-time work · Renewal issuance uses a total-loss report that arrives later

**Evidence.** The default run has 36 renewed terms and seed 101 has 28 where a collision or comprehensive total loss removed a car before renewal, the claim report came after renewal took effect, and the renewal record and first bill already excluded that car before its report. In 8 and 4 cases respectively, the original offer was already between removal and report. In 28 and 24 cases the revised offer is dated exactly on the backdated removal, before the report. The limitation was documented on the prior pass. This review measures the issued-term, ledger, and billing consequences. [Documented limitation](limitations.md) · [Renewal rating date](../autoins/simulate.py#L922) · [First bill timing](../autoins/billing.py#L69)

**Default example.** Policy `250999` received three-car offer `1703764` on February 4, 2022 for $1,070.65. Car `789400` was lost March 13 and removed effective March 14. Claim `134987` was reported March 16. The release shows a revised offer on March 14, a renewal premium transaction `2537460` booked March 14 for $658.05, and invoice `6453681` issued that same day for $658.05. Renewal term `1795698` starts March 15 without the car. The expiring term correctly posts the backdated removal on March 16. The original offer amount alone cannot establish the correct renewed amount because coverages can also change at renewal.

**Cause.** `_simulate_rows` retires the car at effective removal. It protects `sim.last_change` against first notice after expiration, but `_simulate_term` writes the effective day into that field again when it applies the generated wreck endorsement. The new term then reads the latest active-vehicle array, and `_rerated`, `tables._transactions`, and `billing._schedule` use that snapshot to rate, book, and bill. [Removal](../autoins/simulate.py#L653) · [Endorsement boundary](../autoins/simulate.py#L529) · [Premium booking](../autoins/tables.py#L570)

**Acceptance.** Add a deterministic two-car fixture with loss, offer or revision, renewal inception, and report in chronological order. Preserve vehicle assignment, multi-car discount, and original billed premium as of issuance. On report, record a dated adjustment back to renewal inception and reconcile the existing bill or receivable. Keep post-loss physical exposure at zero for the wrecked car. A second fixture should move the report to before inception and verify that any loss-driven revision occurs on or after report. The audit query flags terms for a manual before/after comparison. After the fix, a retrospectively removed car may still be absent from the final exposure table.

```sql
WITH total_losses AS (
  SELECT DISTINCT c.claim_id, c.policy_term_id, c.insured_vehicle_id,
                  c.report_date, v.removed_date
  FROM claim c
  JOIN claim_feature f USING (claim_id)
  JOIN insured_vehicle v USING (insured_vehicle_id)
  WHERE f.coverage_code IN ('COLL', 'COMP')
    AND f.total_loss = 'Y' AND f.owner_retained_salvage = 'N'
    AND v.removal_reason = 'Total Loss'
    AND v.removed_date = date(c.loss_date, '+1 day')
), first_bill AS (
  SELECT policy_term_id, MIN(issue_date) AS first_issue_date
  FROM billing_invoice GROUP BY policy_term_id
)
SELECT o.renewal_offer_id, l.claim_id, l.insured_vehicle_id,
       o.renewal_policy_term_id, o.revised_offer_date,
       o.renewal_effective_date, l.report_date, pt.processed_date,
       b.first_issue_date
FROM total_losses l
JOIN renewal_offer o ON o.expiring_policy_term_id = l.policy_term_id
JOIN premium_transaction pt ON pt.policy_term_id = o.renewal_policy_term_id
JOIN first_bill b ON b.policy_term_id = o.renewal_policy_term_id
WHERE o.outcome = 'Renewed' AND pt.transaction_type = 'Renewal'
  AND l.removed_date < o.renewal_effective_date
  AND o.renewal_effective_date < l.report_date
  AND pt.processed_date < l.report_date AND b.first_issue_date < l.report_date
  AND NOT EXISTS (
    SELECT 1 FROM exposure e
    WHERE e.policy_term_id = o.renewal_policy_term_id
      AND e.insured_vehicle_id = l.insured_vehicle_id
  );
```

## 2. High priority for retention work · A backdated cancellation suppresses the original renewal offer

**Evidence.** Four default terms and five alternate terms have a qualifying non-retained physical total loss with same-day effective removal and cancellation, no renewal-offer row, and the claim report after the entire configured 30–45-day offer window. This is a conservative count. It excludes cases where only part of the window preceded report. For default policy `255940`, term `1836198` was due to expire December 15, 2022. Claim `149327` was reported November 19 and the October 31 cancellation was booked November 21. The entire offer window ended November 15. The booked cancellation is labeled `Insured Request`, the label assigned by the simulator's last-car cancellation branch. [Offer lead time](../autoins/config.py#L199) · [Renewal eligibility](../autoins/simulate.py#L318) · [Last-car cancellation](../autoins/simulate.py#L502)

**Cause and acceptance.** The next iteration carries the effective day in `last_cancel` and filters candidate renewals before evaluating the offer snapshot. `T.cancel_known` is available for transaction booking. Carry the cancellation knowledge date into the offer-selection step and keep the effective cancellation for exposure accounting. In a one-car fixture, move the report from before the offer to after it while holding the loss and removal dates fixed. The latter run should retain the sent offer and then record its cancellation outcome when that information arrives. Test first notice after expiry separately. Keep actual customer-request cancellations distinguishable from a cancellation inferred by the last-car rule.

**Reproduce.** Reuse the `total_losses` CTE above and join `policy_term` on `policy_term_id`. Require `cancel_reason = 'Insured Request'`, `cancel_date = removed_date`, `cancel_date <= date(expiration_date, '-45 days')`, and `report_date > date(expiration_date, '-30 days')`. Left join `renewal_offer` on `expiring_policy_term_id` and count terms with a missing offer ID.

## 3. Medium priority · Nonrenewal applies the same household trigger before and after five years

**Evidence.** Of 898 default and 855 alternate company nonrenewals, 178 and 175 had an in-extract notice date, a policy already at least five calendar years old on that date, and less than 60 days' notice. Thirty in each run had exactly two visible at-fault accidents across two different active drivers and zero recorded violations within the generator's three-year lookback. For default offer `1697337`, policy `116854` started August 30, 2013 and was sent notice January 20, 2022 for February 28, 2022. Its two qualifying records are incidents `221032` and `241458`, on different drivers. Counts identify cases the extract cannot substantiate with an operator-specific reason. Illinois's rule for a policy in force five years or more distinguishes specified grounds from the 60-day notice route. The public records contain the letter date and purpose but no specific grounds. [Illinois Department of Insurance, private passenger auto checklist, pp. 13–14](https://idoi.illinois.gov/content/dam/soi/en/web/insurance/companies/documents/private-passenger-auto-9-17-26.pdf#page=13) · [215 ILCS 5/143.19.1](https://www.ilga.gov/legislation/ilcs/fulltext?DocName=021500050K143.19.1)

**Cause and acceptance.** `underwriting_review` sums incidents over active drivers. It applies the same trigger across tenures. The communications builder sends a generic nonrenewal notice on the 30–45-day offer schedule. Add a calendar-tenure boundary and a reason with its qualifying event and operator for the modeled short-notice path. Use an earlier, independently scheduled review and mailing date for any modeled 60-day path. A deliberately narrower implementation can renew mature policies whose available record cannot support one of the modeled grounds. Include fixtures for an anniversary boundary, two drivers with one accident each, and any modeled longer notice. Remeasure the company share of nonrenewals and annualized retention after the change. [Underwriting review](../autoins/simulate.py#L1124) · [Notice generation](../autoins/tables.py#L671)

**Reproduce.** Join `renewal_offer` to `policy`. Filter to `Company Non-Renewal`, `offer_date >= '2022-01-01'`, five calendar years since `original_inception_date` by `offer_date`, and fewer than 60 days between offer and effective date. Match the notice by policy, day, and purpose. For the two-driver subset, join drivers on the policy who were active on the notice date. Include incidents known by notice and within 1,095 days before the effective date, using the generator's strict lower bound. Group by offer and count incidents, distinct drivers, and violation rows.

## Commands for the next pass

Run from the checkout with the pinned dependencies. The findings use the CSV tables or the release SQLite database. IDs above are examples for this commit and seed. Small deterministic fixtures should preserve the event order when full-book regeneration changes the IDs.

```bash
git fetch origin main
git rev-parse HEAD origin/main
python -m pip install -r requirements.txt -r requirements-release.txt
python -m unittest discover tests
python generate.py --seed 20250101 --out work/audit-default
python validate.py --out work/audit-default
python generate.py --seed 101 --out work/audit-101
python validate.py --out work/audit-101
python generate.py --seed 11 --policies 1500 --valuation 2025-12-15 --out work/audit-dec15
python validate.py --out work/audit-dec15
python scripts/compare_real_data.py --synthetic work/audit-default --real real_data/mendeley_motor_portfolio
```

After fixing renewal chronology, rerun both full books and compare written premium, reported renewal outcomes, the first-bill reconciliation, and the overall loss ratio. The existing green checks exercise ending balances and many within-term dates. Add assertions for the original offer, first bill, and subsequent adjustment so a correct ending balance cannot mask a premature transaction.
