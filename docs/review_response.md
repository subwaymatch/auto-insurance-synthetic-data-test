# Response to the external review of November 2026

An outside reviewer (another AI coding assistant) reviewed the generator twice: first at commit
`5232739` (30,000 policies, the old table names), then at commit `ccd1d9d` on `main` (51,391
policies). The second review's written report was never delivered, because its session ended first,
so its findings are reconstructed here from the checks it ran. Each finding is answered below:
**confirmed and fixed**, **already addressed**, **not adopted** (a suggestion outside this dataset's
scope, now listed in [limitations.md](limitations.md)), or **agreed, already documented**.

"Before" and "after" figures are measured on the current default run (seed 20250101, 43,368 policies, 1
January 2022 to 31 December 2026), generated with the code before and after the fixes. Each fix now has a check of its own in `validate.py`
or a test in `tests/`, so the problem cannot come back unnoticed.

## Summary

| # | Finding | Verdict | Before | After |
|---|---|---|---|---|
| 1 | Renewals rated with changes made after their rating date | Confirmed and fixed (partly a dating artefact) | 1,738 rows at an address not yet in force; 34,493 rows whose car joined after the rating date | 0 and 0 |
| 2 | Conviction dates before 2022 moved to 1 January 2022 | Confirmed and fixed | 7,982 convictions dated after the day they became known; 210 SR-22 filings moved too | 0 |
| 3 | Case reserves above the coverage limit | Confirmed and fixed | 61 features and 9 accidents above a limit | 0 |
| 4 | Underinsured motorist ignores the at-fault insurer's per-accident limit | Confirmed and fixed | $45,000 paid instead of $70,000 in the reviewer's example | Correct, in claims and expected losses |
| 5 | Telematics scores before the driver joined the policy | Confirmed and fixed (mostly the same dating artefact as 1) | 6,741 score windows | 0 |
| 6 | Bound quotes carry the telematics discount, lost quotes never can | Confirmed and fixed | 6,233 of 23,315 bound quotes discounted, no lost quote | Both offered alike; new `quote.telematics_opt_in` |
| 7 | Real-data comparison scales expected losses down twice | Confirmed and fixed | Gini 0.247, top/bottom decile 5.22 | 0.251 and 5.97 |
| 8 | Release files leave out the documents the README links to | Confirmed and fixed | `README.md` only | `README.md`, `CHANGELOG.md` and `docs/` in every zip |
| 9 | Documentation claims more than the checks prove | Confirmed and fixed | Four statements | Reworded |
| 10 | Loss-ratio checks mix catastrophe and non-catastrophe losses | Found while checking finding 9; fixed | Actual (with catastrophes) against expected (without) | Like for like |
| - | `claim_expense_dimension` is not a real dimension | Already addressed | The table was removed when the schema was restructured | - |
| - | Party records, billing, quote versions, claim status history, payees | Not adopted; listed in limitations | - | - |
| - | Effective-dated driver and vehicle relationships; coverage records | Already present in another form | - | - |
| - | Circular calibration, quotes built around the bound book, no opening claim inventory, national benchmarks, Illinois scope | Agreed, already documented | - | - |

## Defects

### 1. Renewals rated with changes made after their rating date

**Finding.** A renewal is rated 30 to 45 days before it takes effect, but the simulator applied the
household as it stood on the effective date. The reviewer found renewal rows rated at an address the
household moved to after the rating date, and cars added after it.

**What we found.** Two causes, one real and one a dating artefact:

- *Real:* a move, a car bought or sold, or a driver joining or leaving in the last weeks of a term
  reached the renewal without changing its rating date. Real policy systems re-rate the pending
  renewal when such a change is processed, and send a revised offer.
- *Artefact:* drivers and cars on policies already renewing on 1 January 2022 were all dated as added
  on the start of their first term in the data, after that term's rating date, although they had been on
  the policy for years. That accounted for 28,440 of the 34,493 flagged car rows and most of the 28,503
  flagged driver rows.

**Fix.**

- A renewal changed between its offer and its effective date is re-rated on the day of the change: its
  rating date moves to that day and a "Revised Renewal Offer" contact is sent: 9,727 of 179,382
  renewals (5.4%) are re-rated. `policy_term` gains `offer_date` (when the term was quoted) beside `rating_date` (when it
  was last rated), separating the original offer from the re-rating, as the reviewer suggested.
- Drivers and cars on policies renewing on the start date now join at the policy's inception, on being
  licensed, or when the car was bought (after its model year went on sale), whichever is later, and
  always before the first rating in the data. A rare one that joined later re-rates that renewal too.

**Check.** `validate.py`: "renewals and changes are rated with the car, driver and address on the
policy on the rating date" and "every term is offered, then rated, before it takes effect".

### 2. Conviction dates before 2022 moved to 1 January 2022

**Finding.** `tables.py` clipped negative day numbers (dates before the start) to zero before writing
conviction dates, so convictions from before 2022 became 1 January 2022, after the day the
violation reached the driving record.

**What we found.** Confirmed: 7,982 convictions fell after their known date and 8,043 were dated 1
January 2022. The same clipping moved 210 SR-22 filing dates. (After the fix, 13 convictions fall on 1
January 2022 by chance.)

**Fix.** Dates before the start are written as they are. A conviction now always falls after the
violation and on or before the day it reaches the driving record.

**Check.** `validate.py`: "a conviction falls after the violation and on or before it reaches the
driving record"; "an SR-22 is filed before it ends, and only after the driver joined the policy". Test:
`test_conviction_and_sr22_dates_before_the_start_are_kept`.

### 3. Case reserves above the coverage limit

**Finding.** Reserve estimates (and the $250 minimum reserve) had no limit cap, so paid plus case
reserve could exceed a per-person limit, a per-accident limit or a $100 towing limit.

**What we found.** Confirmed on the valuation date: 36 bodily injury, 4 medical payments, 3 rental,
17 towing and 1 underinsured motorist features, and 9 accidents above their per-accident limit.

**Fix.** Every claim feature now carries the most it could pay: its per-person or per-claim limit, the
car's value less the deductible for physical damage, and for injury coverages a share of the
per-accident limit that is never less than what that claimant is eventually paid (so claimants' caps
add up to no more than the per-accident limit). Reserve estimates, the minimum reserve and reopening
reserves are held within it. Expense reserves stay separate. Excess-of-limits exposure is not
modelled.

**Check.** `validate.py`: "paid loss plus case reserve stays within every per-person, per-accident and
per-claim limit". Test: `test_reserve_caps_stay_within_the_limits`.

### 4. Underinsured motorist ignores the at-fault insurer's per-accident limit

**Finding.** When an underinsured at-fault driver injured several people, the simulator assumed their
insurer paid each up to its per-person limit, ignoring its per-accident limit. With three $40,000
injuries and an at-fault policy of 25/50, it assumed that insurer paid $75,000 although it can pay only
$50,000, so our underinsured motorist cover paid $25,000 too little.

**What we found.** Confirmed. The reviewer found no case in the default output; it needs several
injured occupants and an at-fault policy whose per-accident limit binds, which is rare.

**Fix.** The at-fault insurer's payments are shared under its per-accident limit before our benefit is
worked out, in the simulated claims and in the answer key's expected losses (the accident-level
adjustment for underinsured motorist now rises up to 1.035 where several claimants leave more to pay).
The reviewer's example now gives $70,000.

**Check.** Test: `test_underinsured_allows_for_the_other_insurers_per_accident_limit`.

### 5. Telematics scores before the driver joined the policy

**Finding.** Some score windows started before the scored car's primary driver was on the policy.

**What we found.** Confirmed: 6,741 windows, all but two before 2022, mostly caused by the dating
artefact in finding 1. Two related problems: a policy already in the programme on the start date could have
joined it before the policy was written, and a car's window could start before the car was added.

**Fix.** A window starts no earlier than the day the car and its primary driver were both on the policy,
and an enrolment from before the extract starts no earlier than the policy's inception.

**Check.** `validate.py`: "a policy joins the programme after it was written, and a car is scored only
while it and its driver are on the policy".

### 6. Bound quotes carry the telematics discount, lost quotes never can

**Finding.** A bound quote shows the premium the policy was written with, including the 5%
participation discount when the customer joined the programme. Quotes that did not bind were priced
without the programme, so a discounted quote was always a bound one.

**What we found.** Confirmed: 6,233 of 23,315 bound quotes were discounted and no lost quote was.

**Fix.** Every quote now offers the programme. Prospects who did not bind opt in at the rate the
programme's take-up model gives new business, and are quoted with the participation discount. A new
column, `quote.telematics_opt_in`, shows who said yes: 26.7% of bound quotes and 28.7% of the others
(62% of lost quotes come through the direct channel, where take-up is highest; within each channel the two
rates agree to within half a point).

**Check.** Test: `test_renewals_changed_after_the_offer_are_re_rated` (which also checks the quote
column).

### 7. Real-data comparison scales expected losses down twice

**Finding.** `scripts/compare_real_data.py` divided each row's answer-key expected loss by the row's
full cover period and multiplied by its earned exposure.

**What we found.** Confirmed. The answer key's expected loss already covers only the earned part of
each row (inside the extract, up to any cancellation), so rows that started before 2022 were scaled
down a second time. Only the comparison's "true expected loss" line was affected: on the same data its
Gini on claim counts moves from 0.247 to 0.251, on cost from 0.362 to 0.366, and the top-to-bottom
decile frequency ratio from 5.22 to 5.97. `validate.py` was not affected (it already works on the earned
window).

**Fix.** The expected loss is summed as it is. `docs/real_data_comparison.md` is regenerated.

### 8. Release files leave out the documents the README links to

**Finding.** The reviewer listed the release zip's contents and found `docs/limitations.md`,
`docs/schema_changes.md`, `docs/real_data_comparison.md` and `CHANGELOG.md` missing.

**What we found.** Confirmed: the zips carried `README.md`, whose links to those files were broken for
anyone with only the release.

**Fix.** Every release zip (data and answer key, CSV and SQLite) now carries `README.md`,
`CHANGELOG.md` and `docs/` at the paths the README links to, and the release notes point readers to
`docs/limitations.md`.

### 9. Documentation claims more than the checks prove

**Finding.** The reviewer searched the limitations page for overstated claims.

**What we found and fixed.**

- "Income, insurance score, limits, payment plan and multi-policy status stay fixed for a policy's
  life" was wrong: liability limits can change at renewal. Corrected in the README and the limitations
  page.
- "The synthetic tables have none [of the errors of a real extract]: `validate.py` checks every record
  reconciles" overstated what passing the checks proves, as findings 1 to 5 showed. Reworded: the
  checks show their rules hold, not that no other inconsistency exists.
- "Internally consistent" became "checked for internal consistency".
- Frequency and severity are compared with the national table "approximately, on its published
  definitions", not "on its own definitions": the source does not publish how it counts claims with
  several payments.

### 10. Loss-ratio checks mix catastrophe and non-catastrophe losses

This came up while checking finding 9, and may or may not be one of the second review's findings. The
answer key's expected losses leave out catastrophes (fictional, dated hail, wind and flood events),
but `validate.py` compared them with each year's actual losses including catastrophes, and with
industry loss ratios that include them. Both comparisons are now like for like: actual losses
excluding catastrophes against expected, and expected plus the year's catastrophe losses against
industry.

## Suggestions about the table structure

| Suggestion | Response |
|---|---|
| `claim_expense_dimension` is a compatibility summary, not a dimension | **Already addressed.** It was removed when the tables were restructured; expenses are on `claim_feature` and `claim_payment`. |
| Effective-dated policy-driver and driver-vehicle relationships | **Already present in another form.** `driver.added_date` and `removed_date` date each driver's time on the policy, and each `exposure` row names the rated driver of one car for one period. A person never appears on two policies here: drivers who leave a policy leave the company, so there is no cross-policy identity to keep. |
| Coverage records with identifiers | **Already present in another form.** Each `exposure` row is the coverage record for one car and period (every limit, deductible and option, with its premium), and a claim feature points to it through `claim.exposure_id` and `claim_feature.coverage_code`. A separate coverage table would hold the same facts in a longer layout. |
| Party records and roles (claimants, passengers, attorneys, repairers, payees) | **Not adopted.** A sizeable addition; listed in [limitations.md](limitations.md) (claimants are numbered within their claim only). |
| Billing accounts, invoices, instalments and receipts | **Not adopted.** Listed in limitations; non-payment cancellations are present without the billing trail behind them. |
| Quote versions and underwriting decisions | **Partly adopted.** Renewals now show an offer and, when re-rated, a later rating date and a revised offer. New-business quote revisions, referrals and declines are listed in limitations. |
| Claim status and assignment history; payees and reversal links | **Not adopted.** Payments already record voids and reissues as transaction types; adjuster assignments, status history and payees are listed in limitations. |

## Observations about realism

The reviewer noted that the rating plan is fitted to the simulator's own expected losses, that quotes
are built around a book already generated, that claims open before 2022 are missing, that national
benchmarks do not validate Chicago subgroups or large-loss tails, and that the scope is Illinois personal
auto. **Agreed; all are already documented** in [limitations.md](limitations.md) (sections 2, 4 and 5).
The reviewer's size figures (122,684 car-years, $136.5 million earned premium, a 65.6% loss ratio) were
for the earlier 30,000-policy default; the current figures are in the README.
