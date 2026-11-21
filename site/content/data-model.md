---
title: Data model
nav: 4
nav_title: Data Model
eyebrow: The data
lede: How the 32 tables fit together, which ones hold history, and how to join them without counting anything twice.
wide: true
description: The Lakefront data model: a diagram of how the tables link, their keys, current versus historical values, dates and the valuation cut-off, and safe ways to join them.
---

## The tables and how they link

Each box is a table; a line joins a table to the one its key points to (the dot marks the table being pointed to). Click a box to open the table in the data dictionary. The diagram shows the main links only: the [data dictionary](/data-dictionary/) lists every key, and the SQLite release declares them all.

<!-- data-model-diagram -->

The spine of the data runs from left to right: an **agency** sells a **policy**; the policy has **terms**, **drivers** and **vehicles**; each vehicle’s cover for each stretch of time is an **exposure** row; a **claim** arises under one exposure row and has **features**, **payments** and **reserve changes**. Billing hangs off the policy terms, and the **general ledger** summarizes premiums, billing, commission and claims by month.

## What one row is

The first question to ask of any table is what one row represents: its **grain**. Most mistakes with this data come from summing a column at the wrong grain.

<!-- table-list -->

## Keys and identifiers

Every record has two kinds of identifier:

- **Integer keys** (`..._id`) join the tables. A key has the same name in every table that holds it: `policy_id` in `policy`, `driver`, `claim` and so on. Keys are numbered in the order records were created and say nothing else about a record.
- **Business keys** are what the company prints on documents: `policy.policy_number` (`0830512-LFM-47`, with check digits), `claim.claim_number` (`24-0022944`), `quote.quote_number`, `billing_invoice.invoice_number`, `claim_payment.check_number`, and each car’s `insured_vehicle.vin`, with its check digit.

Join on the integer keys. The business keys are for reading, validating and searching.

## Current versus historical values

This is the most important thing to understand about the data.

`policy`, `driver` and `insured_vehicle` describe each policy, driver and car **as it stands at its latest status**: on the valuation date if the policy is in force, otherwise on its last day of cover. A policy’s address, limits and number of cars are today’s; a car’s coverages and deductibles are today’s.

`exposure` is the **effective-dated** record. A policy gets new exposure rows at every renewal and every mid-term change, and each row keeps the address, rated driver, characteristics, limits, deductibles, discounts and premium that were in force for its dates (`exposure.coverage_start_date` to `exposure.coverage_end_date`). Use it for anything historical.

Two consequences:

- **Join claims through `exposure_id`, not `policy_id`.** `claim.exposure_id` is the row in force on the loss date. Joining a claim straight to `policy` gives the address and limits the policy has now, not those on the day of the accident.
- **Totals are worked out, not stored.** As in an insurer's own systems, the tables hold the records (payments, reserve changes, premium transactions, dates of cover) and not the totals an analyst makes from them: a claim's paid and incurred loss, a term's earned premium, a policy's count of cars. [Working out totals](#working-out-totals) below shows how.

## Dates and what was known when

The data is an **extract** taken on a valuation date, 31 December 2026, and covers 1 January 2022 onward. As in any extract:

- **Nothing after the valuation date exists.** Payments not yet made, claims not yet reported and renewals not yet effective are missing or shown as pending. Open claims carry a case reserve.
- **Policies in force on 1 January 2022** enter with the term that spans that day. Some of their exposure rows start before 2022, and only the days from 1 January 2022 are earned in the extract. The claims those policies still had open on that day (or reported later) from losses in late 2021 are in the data, with their earlier payments; claims settled before then are not, though an at-fault one stays on the driver's record in `driver_incident`.
- **Information arrives late.** A term is rated on its `policy_term.rating_date` with only what was known by then; `driver_incident.known_date` says when each violation or accident reached the insurer, which can be months after it happened.
- **Several dates for one event.** A claim has a `claim.loss_date` and a later `claim.report_date`; a premium transaction an `premium_transaction.effective_date` and a `premium_transaction.processed_date`; a bill a `billing_invoice.issue_date`, `billing_invoice.due_date` and `billing_invoice.paid_date`. Pick the one your question is about.

Dates are written `YYYY-MM-DD`. Staff, banks and courts work business days, so payments, closes and letters never fall on weekends or holidays; losses can happen any day.

## Working out totals

The tables keep what the insurer's systems record, so a few totals are worked out from them. These two SQLite views (the same SQL runs in DuckDB with `GREATEST`, `LEAST` and date subtraction in place of `MAX`, `MIN` and `julianday`) give the car-years and premium each exposure row earned inside the extract, and each claim feature's amounts at the valuation date, a loss run. `validate.py` (`rebuild`) works them out the same way in pandas.

```sql
-- Car-years and premium each exposure row earned in the extract (1 January 2022 to 31 December 2026):
-- its days of cover inside it, and its full-term premium pro rata over its term's days
CREATE VIEW earned AS
SELECT e.exposure_id,
       MAX(0, julianday(MIN(e.coverage_end_date, '2027-01-01')) - julianday(MAX(e.coverage_start_date, '2022-01-01'))) AS days,
       MAX(0, julianday(MIN(e.coverage_end_date, '2027-01-01')) - julianday(MAX(e.coverage_start_date, '2022-01-01'))) / 365.25 AS car_years,
       e.total_premium * MAX(0, julianday(MIN(e.coverage_end_date, '2027-01-01')) - julianday(MAX(e.coverage_start_date, '2022-01-01')))
         / (julianday(t.expiration_date) - julianday(t.effective_date)) AS earned_premium
FROM exposure AS e
JOIN policy_term AS t ON t.policy_term_id = e.policy_term_id;

-- Each claim feature at the valuation date: payments by type, and the latest reserve balance of each type
CREATE VIEW loss_run AS
SELECT f.claim_feature_id, f.claim_id, f.coverage_code,
       COALESCE(SUM(CASE WHEN p.payment_type = 'Loss' THEN p.amount END), 0) AS paid_loss,
       -COALESCE(SUM(CASE WHEN p.payment_type IN ('Salvage Recovery', 'Subrogation Recovery') THEN p.amount END), 0) AS recoveries,
       COALESCE(SUM(CASE WHEN p.payment_type = 'Expense' THEN p.amount END), 0) AS paid_expense,
       COALESCE((SELECT r.outstanding_reserve FROM claim_reserve_transaction AS r
                 WHERE r.claim_feature_id = f.claim_feature_id AND r.reserve_type = 'Loss'
                 ORDER BY r.transaction_date DESC, r.reserve_transaction_id DESC LIMIT 1), 0) AS case_reserve
FROM claim_feature AS f
LEFT JOIN claim_payment AS p ON p.claim_feature_id = f.claim_feature_id
GROUP BY f.claim_feature_id;
```

Incurred loss is `paid_loss + case_reserve`, net incurred that less `recoveries`. For a past date, add `p.payment_date <= :date` and `r.transaction_date <= :date`: that is how a development triangle is built.

## Joining without double counting

Two habits prevent most errors.

**Aggregate each table at its own grain, then join the results.** Joining `exposure` to `claim` and then summing car-years counts a car-year once for every claim on it. Sum exposure and claims separately, then join the totals:

```sql
-- Collision claims per 100 car-years, by liability territory (accidents inside the extract)
WITH cover AS (
  SELECT l.liability_territory AS territory, SUM(x.car_years) AS car_years
  FROM exposure AS e
  JOIN earned AS x ON x.exposure_id = e.exposure_id
  JOIN location AS l ON l.location_id = e.location_id
  WHERE e.collision_deductible > 0          -- only cars with collision cover
  GROUP BY 1
), claims AS (
  SELECT l.liability_territory AS territory, COUNT(DISTINCT r.claim_id) AS claims
  FROM loss_run AS r
  JOIN claim AS c ON c.claim_id = r.claim_id
  JOIN exposure AS e ON e.exposure_id = c.exposure_id
  JOIN location AS l ON l.location_id = e.location_id
  WHERE r.coverage_code = 'COLL' AND r.paid_loss > 0 AND c.loss_date >= '2022-01-01'
  GROUP BY 1
)
SELECT cover.territory, car_years, claims,
       ROUND(100.0 * claims / car_years, 2) AS claims_per_100_car_years
FROM cover LEFT JOIN claims USING (territory)
ORDER BY cover.territory;
```

**Use the table that matches your question.**

| Question | Use |
|---|---|
| Losses by coverage, claimant or injury type | `claim_feature` with its payments and reserves (the loss run) |
| Losses by claim, cause or day | `claim`, with its features' loss run |
| Losses as of a past date (development) | `claim_payment` and `claim_reserve_transaction`, up to that date |
| Earned premium and car-years by any rated characteristic | `exposure` (and its term's dates) |
| Written premium by month, channel or transaction type | `premium_transaction` |
| Premium by policy term, renewal or cancellation | `policy_term` and its `premium_transaction` rows |
| Cash collected, receivables and write-offs | `billing_invoice` and `billing_receipt` |
| The company’s books by month | `gl_journal` |

## File formats

The same tables come as CSV files, one SQLite database, or Parquet files. The SQLite database declares every primary and foreign key, so database tools draw the links. Parquet files arrive with their types set: whole numbers as integers, amounts as decimals, and every column named `..._date` as a date. In CSV, blanks are empty fields; in SQLite and Parquet they are `NULL`. See [Get the data](/get-the-data/).
