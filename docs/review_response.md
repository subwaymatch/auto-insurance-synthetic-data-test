# Responses to the external reviews of November 2026

An outside reviewer (another AI coding assistant) has reviewed the generator three times, and a dataset
realism audit followed on 20 November 2026. The audit, at commit `03c2634`, is answered first, then the third
review at `9fe6062`; the first two follow. Each finding is answered:
**confirmed and fixed**, **already addressed**, **not adopted** (a suggestion outside this dataset's scope,
now listed in [limitations.md](limitations.md)), or **agreed, already documented**.

## Dataset realism audit (20 November 2026)

The audit regenerated the default run at `03c2634` (content hash `7b4b15d1dcb53b95`) and a second full-size
seed (7), found the economics, coverage mix, risk relationships and keys credible, and listed records that
contradict their own business context although every check passed. All five record-level findings and the
validator defect reproduce exactly and are **confirmed and fixed**. "Before" figures are from the audited
commit and "after" from this change, on the default run (content hash `06932bb41e745579`) and seed 7
(`1addd020a2ad50c6`).

| # | Finding | Verdict | Before (default; seed 7) | After |
|---|---|---|---|---|
| A1 | Lienholders paid on total losses of cars owned outright | Confirmed and fixed | 1,176 of 1,547 lienholder payments ($6,603,284.68); 1,240 | 0; a lender is paid on every paid total loss of a financed or leased car and on no other (578 payments) |
| A2 | Non-payment cancellations with no unpaid installment behind them | Confirmed and fixed | 17 of 5,267; 15 of 5,395 | 0 of 5,250; 0 of 5,380 |
| A3 | Joint claimant-and-attorney payments before the attorney was retained | Confirmed and fixed | 20 payments ($251,604.23); 23 | 0; 0 |
| A4 | Claims and payments naming a named insured who joined the policy later | Confirmed and fixed | 2 claims and 1 payment; 1 claim | 0; 0 (and 95 more claims named a later named insured who was already a driver) |
| A5 | Final-balance checks received at weekends | Confirmed and fixed | 83; 80 | 0; 0 |
| A6 | A validator check compared a column with itself | Confirmed and fixed | Could not fail | Fails on a claim moved to another policy (unit test) |
| - | Effective-dated histories stored the caller's array, not a copy | Found while fixing A4; fixed | The opening named insured read as the final one | Each history keeps what was recorded |
| A7 | Case-reserve allocation and the rating plan know eventual outcomes | Agreed and changed | Reserve shares from eventual payments; plan fitted to the true costs | Shares from what is known each day; plan fitted to simulated experience with credibility |
| A8 | Tails and joint relationships need independent calibration | Agreed and changed | No benchmark sheet or seed spread | [benchmarks.md](benchmarks.md): sources and use of every benchmark, spread across five seeds, tail and reserve diagnostics |
| A9 | A separately labeled messy extract | Not adopted | | The clean baseline stays the only edition |
| A10 | `run_summary.json` lacks the source revision, versions and content hash | Confirmed and fixed | Seed, size, dates and counts only | Hashes, source revision, library versions and fingerprints; `validate.py` checks the hashes |

### A1. Lienholder payments ignored whether a loan existed

**What we found.** Confirmed: a total loss was split between a lienholder and the owner at random (45% of
settlements of $200 or more), whatever the car's ownership, and the lienholder was picked per payment.

**Fix.** The car's ownership at the loss (owned, financed or leased) now travels with the claim
(`simulate._simulate_rows` to `claims.Development`). A total loss on a financed car pays off the loan first:
the balance is an assumed share of the settlement, from 35% to 120% (`claims.LOAN_PAYOFF_SHARE`); above
100% the loan is worth more than the car, the lender takes the whole settlement and gap cover, not this
policy, pays the rest (20% of the default run's financed payoffs). A leased car's settlement all goes to the
leasing company, which owns it. The owner gets the balance; a car owned outright is paid to its owner only.
When the lender takes the whole settlement its payment is the final one. Each car has one lender or lessor
(`payments.details`). A car whose owner keeps the wreck after a total loss has had its loan or lease paid off
by the settlement, and is shown as owned from then on.

**Checks.** `validate.py`: "a lienholder or lessor is paid only on a total loss of a financed or leased car,
never more than the settlement and one lender per car; every closed, paid total loss of a financed or leased
car pays one". Seed 7 turned up a financed car whose settlement was $72.25, which the old $200 threshold
had paid to the owner alone; the lender is now paid first whatever the amount.

### A2. Non-payment cancellation without an unpaid bill

**What we found.** Confirmed, and the cause is as the audit describes: the simulation chooses the
installment a leaving household will not pay when the term begins, before the term's changes are known. In
15 of the 17 terms a car left the policy before that installment was issued (in 13 it was written off,
destroyed or stolen) and the return premium left nothing on it; the other 2 began with no car while a
replacement was awaited, and the installment was issued before the replacement's premium was added. Either
way no bill was sent.

**Fix.** Moving a cancellation later would mean simulating cover, claims and changes the term never had, so
the rule is applied where the bills are known (`billing.without_a_bill_to_miss`, called by `tables.build`):
a household that leaves when it has no bill to miss is recorded as canceling at its own request on the same
day. Its cancellation is then keyed by staff, its unpaid bills are canceled and its balance settled like any
other request. In the default run these are the same 17 terms; the remaining 5,250 non-payment
cancellations each follow a billed, unpaid installment by 21 to 28 days.

**Checks.** The validator's 98% tolerance is replaced by a record-level rule: "every cancellation for
non-payment follows an unpaid installment, billed and due three to four weeks before it".

### A3. Attorney payees before the attorney was retained

**Fix.** The payee of an injury payment is decided on its own date (`payments.details`): before the attorney
is retained it is the claimant alone, from that day jointly with the attorney, the same law firm every time.
A void is made out like the check it cancels; its reissue goes to whoever is paid on the reissue date. In
the default run 20 advances now go to the claimant alone; 853 joint payments remain.

**Checks.** "a claimant is paid jointly with an attorney only on or after the day the attorney was retained,
and always after it".

### A4. Current insured identity rewrote historical records

**What we found.** Confirmed, and the cause was deeper than the extraction step. `tables.build` used the
policy's final named insured for a loss with no driver and for payments to the insured. Switching to the
simulation's effective-dated history of named insureds did not fix it at first: `History.add` stored the
array it was given rather than a copy, and the opening record had been given the policies' live
named-insured array, which the simulation later changes when a named insured dies and the spouse takes
over. So "the named insured before any change" always read as the final one. The same history is read when
a renewal offer decides whether to offer telematics to a young named insured, so a change after the offer
date could in principle have leaked into it; in the default run no offer or enrollment changed (the
`renewal_offer`, `telematics_enrollment` and `exposure` files are byte-identical before and after).

**Fix.** `History.add` copies what it is given. A loss with no driver is recorded against the named insured
on the loss date, and a payment to the insured is made out to the named insured on the payment date.
`involved_driver_id` changed on 97 claims: the 2 the audit found, and 95 that named a later named insured
who was already a driver on the policy at the loss (so no check could see it).

**Checks.** "each claim's driver was on the policy on the loss date, and each payment to the insured names
someone on the policy on the payment date" (every claim, not only at-fault ones). A unit test changes the
caller's array after recording it.

### A5. Final-balance check receipts at weekends

**Fix.** A check paying a final balance is banked on a business day, like every other check
(`billing.build`). **Checks.** "check and bank-draft receipts, returned drafts and refunds are dated on
business days"; card, online and agency payments can be made any day.

### A6. A validator check compared a column with itself

**Fix.** The key checks are now one function, `validate.integrity_links`, and test agreement as well as
existence: a claim's policy, term, vehicle and model year against its exposure row; each exposure row's
policy against its term's and its vehicle's; each payment's and reserve change's claim against its
feature's. **Negative controls.** A new test (`test_checks_catch_a_corrupted_record`) makes one record wrong
for each new or repaired check (a claim moved to another policy, a payment filed under another claim, a
lender paid on a car owned outright or left unpaid on a financed one, a joint payment a day before the
attorney, a claim driver or insured payee who joined later, a non-payment cancellation without its unpaid
bill, a check banked on a Saturday) and asserts that the check fails (for most, that it is the only one).

### A7. Information in reserves and pricing

**Agreed and changed.** Both points were documented limitations; on review they were worth fixing.

*Case reserves.* `truth.reserve_caps` gave each injury claimant a static share of the accident's per-accident
limit computed from their eventual payments and true damages. It is gone. A feature now carries its contractual
per-person (or per-claim) limit, which stays exact, and the accident's per-accident room. The reserve history
(`claims._share_accident_limit`) applies the shared limit from what is known on each day: a reserve set during
the day (a new claimant's formula reserve, say) takes no more than the room left by the accident's payments to
date and the other claimants' reserves; at the end of each business day with news the adjuster rebalances, so
if paid to date plus the reserves wanted would exceed the room, the room left after payments is shared in
proportion to the current estimates, and when a settlement frees room the others get their full estimates back.
A change made to another claimant's reserve this way is a "Reserve Review" on that day. A new validator check
holds every accident, on every day with a payment or reserve change, to its per-accident limit; unit tests
cover a claimant arriving, a settlement freeing room, a weekend report, and random estimates.

The audit's acceptance test (reserve error by coverage and age, revision rates, runoff, spread across seeds)
is `scripts/reserve_diagnostics.py`; its results are in [benchmarks.md](benchmarks.md), section 4. It found
one real fault, now fixed: property formula reserves were well below the average claim, so collision,
comprehensive and property damage claims still on their opening reserve at a year-end went on to pay 1.5 to 2.2
times that reserve. Formula reserves for property coverages are now set near the average paid per claim opened
(glass separately), as carriers set average reserves; injury reserves still start low, by design.

*Rating plan.* The relativities were fitted directly to the true expected loss cost. They are now fitted to
the company's claims experience (`rating.experience`): three years of claims on the book as first written,
drawn as a compound Poisson-gamma sum around the true expected costs. Each level is credibility-weighted
(limited fluctuation: full credibility at 1,082 claims times one plus the squared coefficient of variation of
claim size) with a bureau complement, which is the relativity the true costs indicate off by a random 5%; the
base rates come from the whole book's experience. Sparse levels now lean on the bureau and well-populated ones
carry the company's own luck: for example the cheapest bodily injury territory is priced at 0.69 where 0.77 is
indicated, and a collision territory at 1.03 against 1.17. `relativities_indicated` in the answer key still says
what each level is worth. Filing lags are already in the data as the rate-change history and the market cycle
(the book starts under-priced and catches up), so they were not added again.

### A8. Tails and joint relationships

**Agreed and changed.** [benchmarks.md](benchmarks.md) is the benchmark sheet the audit asked for: every
figure the validator holds the data to, with source, year, geography, units and inclusion rules, band, and
whether it was used for tuning, checked, assumed or held out. `validate.py --json` writes every band's figure, and
`scripts/seed_spread.py` builds several seeds and reports each figure's mean and range and how many seeds land
inside its band (section 2), with tail and joint diagnostics computed from the tables (section 3). New sourced
comparisons, held out from tuning: CCC's total-loss share of appraisals and the age of total losses, and S&P
Global Mobility's average vehicle age. They show departures that are reported rather than tuned away: total
losses are more frequent here than CCC's 22% (about 27% of paid collision and comprehensive claims, glass apart,
on a narrower definition) and fall on older, cheaper cars; the average written-off car is worth about $10,500
against CCC's $13,400 to $13,700. Severity percentiles, the share of injury claimants paid the full limit and
the concentration of cost in the costliest risks have no US figure on matching terms and are reported without a
target. Policy-grouped and time-based holdouts are left to case studies.

### A9. A messy extract

**Not adopted.** The tables are clean by design and stay the only edition; the owner does not want
deliberately degraded data. [limitations.md](limitations.md) (section 6) suggests pairing the data with the
real portfolio in `real_data/` for cleaning exercises.

### A10. Provenance inside each generated dataset

**Fix.** `pipeline.generate` writes `run_summary.json` after the CSVs, with `content_hash` (every CSV, as
the generator prints it), `tables_hash` (the data tables) and `answer_key_hash`, `hash_method`, and under
`build` the source revision and whether the generator's files had uncommitted changes, the Python, NumPy and
pandas versions, a fingerprint of every table's columns and of each reference file. Nothing in it depends
on when or where the run happened. `validate.py` recomputes the hashes ("the CSV files are the ones the
generator wrote"), checking the answer key only when it is present, so a student's copy can be checked too.

### What changed in the data

Only who is paid, how a few records are labeled and a few dates. Every loss and premium amount, every
exposure row, claim feature, renewal offer and telematics record is as before; the loss ratio (67.4%),
frequencies, severities, premiums and retention are unchanged. Claim payments 61,678 → 60,542 and reserve
transactions 125,378 → 124,306 (fewer split settlements); bills 887,710 → 887,706 and receipts 896,571 →
896,585 (the 17 relabeled cancellations); 97 claims' `involved_driver_id`; payees of 1,547 lienholder,
20 attorney and some insured payments. `validate.py` runs 147 checks (was 140), all passing on both seeds;
the test suite has 67 tests (was 64).

### Follow-up changes asked for by the owner

After the fixes above, the owner asked for further realism changes, made in the same pull request:

- **Notices of cancellation.** Every non-payment cancellation now has a notice of cancellation mailed at least
  ten days before it (215 ILCS 5/143.15), including a missed bank draft, which is attempted and returned first.
  `validate.py` checks every one (5,009 in the default run, none without).
- **Vehicles back to 1981.** The catalog reaches model year 1981 (EPA data starts in 1984; earlier years carry
  1984's specifications back), and old cars thin out with a scrappage taper, so model year 1997 no longer piles
  up the cars that would be older.
- **Surnames.** Whether a wife keeps her surname depends on the household's group (Pew Research Center, 2023);
  children take their father's surname.
- **Identifiers.** Integer keys are the company's system counters (founded 2000; billing 2008, claims 2012,
  quoting 2014, correspondence 2016, telematics 2018), so they start far above 1 and have gaps.
- **Real catastrophes.** Ten storms from NOAA's Storm Events Database for the seven counties (2023 to 2026)
  replace the fictional events; their losses are simulated.
- **Claims open at the start.** A warm-up year (2021) is simulated, so the extract opens with claims, reserves
  and payments on earlier accidents, and the ledger's opening entry carries their reserves.
- **Records, not totals.** Derived and aggregated columns were removed; [schema_changes.md](schema_changes.md)
  lists them and how to rebuild each.
- **A7 and A8**, above.

The default run is now content hash `963889a73f229de8` (seed 7: `6718177c0b52ab2e`); 145 checks pass on both,
and on seeds 11, 23 and 42, with every calibration figure inside its band on all five. Every record-level
finding A1 to A5 stays at zero (the validator checks each). The test suite has 74 tests.

## Third review (18 November 2026)

The reviewer regenerated the default run at `9fe6062` (content hash `bfb1ac64b90c932b`), confirmed the four
fixes of the second review (renewal rating dates, conviction dates, reserves within limits, underinsured
motorist), and found two remaining problems of the same kind: decisions dated in the past that used
information from later. Both are confirmed and fixed. "Before" figures are from the reviewed commit and
"after" from this change, on the default run (seed 20250101, 43,368 policies, 1 January 2022 to 31
December 2026; content hash `4b5bca69599df49e`).

| # | Finding | Verdict | Before | After |
|---|---|---|---|---|
| F1 | Telematics scores attributed to a driver assigned to the car after the driving | Confirmed and fixed | 211 scores overlap another driver's exposure; 48 name a driver first assigned after the window | 0 and 0; 165 scoring periods split where the car's driver changed |
| F2 | Renewal decisions use the household, claims and premium as they stood after the offer date | Confirmed and fixed | Offer-date and inception-date inputs mixed; declined renewals left no record of their offer | Every input as at the offer date; 179,620 offers kept, declined ones included, in the new `renewal_offer` table |
| - | A score of a customer who left the program linked to a term that began before it | Found while checking F1; fixed | 4 scores | 0 |
| - | Opt-ins at a renewal that was not taken recorded as enrollments that ended the day they began | Found while fixing F2; fixed | 257 enrollments | 0 (the opt-in is on the renewal offer instead) |

### F1. Telematics uses a driver assigned after the driving occurred

**Finding.** A car's score was generated from, and published against, the car's primary driver as it stood
when the score was calculated, after the whole expiring term had been simulated. A car taken over by
another household driver after (or during) the scoring window was scored as the new driver's driving.

**What we found.** Confirmed: 211 of 56,491 scores overlap an exposure row of the same car rated to a
different driver, and 48 scores with windows starting in 2022 or later name a driver whose first exposure
on that car begins after the window ends (the reviewer's example, score 6564, was such a takeover). Two
smaller leaks of the same kind: the take-up of the program used the drivers on the policy at the renewal
date rather than on the offer date, and a driver's propensity used their current marital status. Cars sold
or written off between the scoring date and the renewal were not scored at all, although they were on the
policy that day.

**Fix.** The simulator now keeps effective-dated histories: each car's rated driver and garaging ZIP (from
the exposure rows, plus an explicit opening assignment for the days before the first simulated period),
each driver's marital status, each policy's named insured and homeowner status. Scoring reads them, not the
current state:

- **One score, one driver.** A scoring window in which the car's assigned driver changed is split at the
  change, and each part is scored as that driver's driving (their propensity and age at the time, the ZIP
  the car was kept in). A part shorter than the 45-day minimum earns no score. A window before the car's
  first exposure row uses the opening assignment.
- **The car's discount** for the next term is the average of the discounts its scored parts earned,
  weighted by the days each was monitored and rounded half up to a whole percent, or the 5% participation
  discount if no part was monitored long enough. Nearly all windows have one part, so for them nothing
  changes.
- **Who is scored.** Every monitored car on the policy on the scoring date, including one that leaves
  before the renewal (its score applies to no term).
- **Take-up** of the program uses the household on the offer date (as quoted, for new business).

**Checks.** `validate.py`: "each score is the driving of the driver assigned to the car on the days scored"
(against the exposure rows' rated driver, the reviewer's interval check, plus the opening assignment for
periods before a car's first row); "each enrolled car starts a term on the days-weighted discount its
scores for that term earned"; "a score's discount applies to a later term of the same policy". Tests in
`TelematicsAssignmentTest`: a spouse taking the car over after the window leaves the earlier score and its
driver unchanged; moving that takeover to any later date changes nothing, metrics included, with the same
draws; a change inside the window splits it, and a move alone (same driver) does not. The existing
membership checks still pass.

**Found along the way.** A customer who left the program earned no discount, and their last score was
marked with day `-1` for "applies to no term". Day `-1` is a real day, 31 December 2021, the start of some
opening terms, so 4 such scores were linked to that term. A sentinel that cannot be a day replaces it.

### F2. Renewal decisions use information from after the offer date

**Finding.** The renewal was described as decided with the offer in hand, but its premium, household and
"still has a car" test came from the policy as it stood at the end of the expiring term; claims counted if
reported before the effective date; only driving records were taken as at the offer date. The published
rating date was corrected for re-rated renewals, but the decision itself was not. Declined renewals left no
record of the offer.

**What we found.** Confirmed by source. The reviewer did not quantify it; a controlled counterfactual now
does. Holding every random draw fixed, evaluating each of the 174,487 renewals decided in the new default
run with the old information (the policy at the end of the expiring term, claims up to the effective
date) instead of the offer-date snapshot gives a different premium for 12,013, a different set of cars for
4,223 and a different claim count for 3,223, and changes 315 renew-or-leave decisions (263 that renew on
the offer-date information would have been lost, 52 the other way) and 16 company non-renewals. Few
decisions change because most late changes move the premium modestly, but the inputs a retention model
would be given were not those the decision used.

**Fix.** An explicit timeline. On the offer date, 30 to 45 days before the renewal:

1. **Underwriting review.** Drivers on the policy that day, with incidents known by then, dated in the
   three years before the renewal. A flagged policy may be non-renewed by the company (a notice, not an
   offer).
2. **Telematics.** Enrolled cars are scored (F1), and the program is offered to non-members.
3. **The offer.** The renewal premium is evaluated from the expiring term's exposure rows in force on the
   offer date (cars, rated drivers, address, homeowner status, limits and deductibles), rated for the new
   term at its rates, with the records known that day and the telematics discounts just earned. It is
   compared with what the same cars cost on the expiring term (like for like).
4. **The customer's decision**, on that offer: its premium change, tenure, the claims the customer
   reported since the previous offer and by this one, and the other renewal-model terms.

Nothing after the offer date changes these. Later events remain later events: a household change before
the effective date re-rates the pending renewal (a revised offer, as before), a cancellation before the
effective date ends the policy ("Canceled Before Renewal"), and a household with no car left has nothing to
renew. Decisions draw from a dedicated random stream, one pair of draws per policy per term, so a policy's
decision depends only on its own history up to the offer. Customers do not re-decide on a revised offer;
that is a stated simplification ([limitations.md](limitations.md)).

**New table `renewal_offer`**: one row per renewal evaluated, 179,620 in the default run: 162,374
renewed, 11,979 not renewed by the insured, 134 company non-renewals, 1,146 canceled before the renewal
date and 3,987 pending (taking effect after the valuation date). Each row has the offer date (the decision
date and snapshot date), the vehicles offered, the expiring and renewal premium for a full term, the
premium change, the telematics opt-in, the underwriting decision, the revised offer date (10,393 offers,
881 of them not renewed), the outcome and the renewal term. The snapshot is the expiring term's exposure
rows in force on the offer date, which `validate.py` checks row by row. The answer key's
`renewal_offer_truth` gives each offer's true acceptance probability. `customer_contact` now has a renewal
offer for every offer sent (not only those taken up), a "Notice of Non-Renewal" for company non-renewals,
and a revised offer for every revision.

**Final-rating corrections versus the decision timeline.** The second review's finding 1 corrected the
*final rating* of a renewal changed after its offer (its premium and `rating_date`), and that correction
stands: 9,512 renewal terms in the new run are re-rated after a household change. It did not touch *when
the renewal was decided*, which is what F2 fixes: the original offer and the decision on it now use only
what was known on the offer date, whatever the revision brings later.

**Checks.** `validate.py`: each offer is made during its expiring term and by the valuation date; each
covers the vehicles in force on its offer date at the premium they were then insured for; every renewal
term after a policy's first in the data is a renewed offer with the term's offer date and revised offer
date; every non-renewed term has one offer whose outcome is its non-renewal reason; "Canceled Before
Renewal" exactly when the expiring term was canceled after the offer; pending only after the valuation
date; no telematics offer or revision for a company non-renewal. Tests in `RenewalTimelineTest`: every
offer of a run, evaluated again at the end of the run with the whole later history present (later claims,
moves, cars, drivers and records, and the scrambled current state of the policy), gives the same premium,
probability and decision with the same draws; adding a claim reported the day after the offer, or records
known the day after, or later exposure rows changes nothing, while a claim reported on the offer date
itself counts; three at-fault accidents known on the offer date trigger the underwriting review, the same
known a day later do not. The existing rating-date checks and the revised-offer contacts are kept.

### What changed in the data

The order of random draws changed, so every table differs by sampling noise; every calibration band still
holds. Policy terms 205,616 → 205,742; exposure rows 460,536 → 460,831; claims 20,381 → 20,343; telematics
scores 56,491 → 59,553 (split windows and cars scored on their last scoring date) and enrollments 12,607 →
12,298 (no enrollment for an opt-in whose renewal was not taken); customer contacts 329,368 → 347,405
(renewal offers that were declined). Retention is unchanged in substance: annualized policy retention 83.3%
→ 83.4%, insured non-renewals 12,109 → 11,979, company non-renewals 121 → 134. The renewal rate falls with the
offered change, from about 95% for changes of 5% or less to 87.5% for 10% to 20% and 75% above 20%. The
overall loss ratio is 66.9% (was 68.3%), and the expected loss ratios plus catastrophes for 2022 to 2025
are 79.3%, 77.6%, 67.9% and 64.7% (were 79.1%, 77.1%, 67.9%, 64.8%).

### Tables, realism and follow-up work

The reviewer's assessment of the table structure and statistical realism (a credible teaching extract, not
an operational database; effective-dated exposure; a recognizable claims structure; missing billing, party
and status histories; national calibration that does not validate Chicago subgroups; immature 2026
losses) is **agreed**; the limits are in [limitations.md](limitations.md). Of the recommended follow-up
work, the offer and decision history is done (`renewal_offer`). Not done in this change, and listed as next
steps: a fixed matrix of seeds and sizes separating accounting invariants from stochastic tolerances;
rebuilding paid-plus-outstanding against limits at every historical transaction date (validated now at the
valuation date); further cross-table ownership checks; and subgroup frequency, severity and development
with uncertainty intervals. The reserve caps' use of eventual paid amounts and latent damages
(`autoins/truth.py`, `reserve_caps`) is a simplifying assumption, now stated in the limitations.

## First and second reviews (at `5232739` and `ccd1d9d`)

The first review was at commit `5232739` (30,000 policies, the old table names), the second at commit
`ccd1d9d` on `main` (51,391 policies). The second review's written report was never delivered, because its
session ended first, so its findings are reconstructed here from the checks it ran.

"Before" and "after" figures in this section are measured on the default run at the time (seed 20250101,
43,368 policies, 1 January 2022 to 31 December 2026), generated with the code before and after the fixes.
Each fix has a check of its own in `validate.py` or a test in `tests/`, so the problem cannot come back
unnoticed.

### Summary

| # | Finding | Verdict | Before | After |
|---|---|---|---|---|
| 1 | Renewals rated with changes made after their rating date | Confirmed and fixed (partly a dating artifact) | 1,738 rows at an address not yet in force; 34,493 rows whose car joined after the rating date | 0 and 0 |
| 2 | Conviction dates before 2022 moved to 1 January 2022 | Confirmed and fixed | 7,982 convictions dated after the day they became known; 210 SR-22 filings moved too | 0 |
| 3 | Case reserves above the coverage limit | Confirmed and fixed | 61 features and 9 accidents above a limit | 0 |
| 4 | Underinsured motorist ignores the at-fault insurer's per-accident limit | Confirmed and fixed | $45,000 paid instead of $70,000 in the reviewer's example | Correct, in claims and expected losses |
| 5 | Telematics scores before the driver joined the policy | Confirmed and fixed (mostly the same dating artifact as 1) | 6,741 score windows | 0 |
| 6 | Bound quotes carry the telematics discount, lost quotes never can | Confirmed and fixed | 6,233 of 23,315 bound quotes discounted, no lost quote | Both offered alike; new `quote.telematics_opt_in` |
| 7 | Real-data comparison scales expected losses down twice | Confirmed and fixed | Gini 0.247, top/bottom decile 5.22 | 0.251 and 5.97 |
| 8 | Release files leave out the documents the README links to | Confirmed and fixed | `README.md` only | `README.md`, `CHANGELOG.md` and `docs/` in every zip |
| 9 | Documentation claims more than the checks prove | Confirmed and fixed | Four statements | Reworded |
| 10 | Loss-ratio checks mix catastrophe and non-catastrophe losses | Found while checking finding 9; fixed | Actual (with catastrophes) against expected (without) | Like for like |
| - | `claim_expense_dimension` is not a real dimension | Already addressed | The table was removed when the schema was restructured | - |
| - | Party records, billing, quote versions, claim status history, payees | Not adopted; listed in limitations | - | - |
| - | Effective-dated driver and vehicle relationships; coverage records | Already present in another form | - | - |
| - | Circular calibration, quotes built around the bound book, no opening claim inventory, national benchmarks, Illinois scope | Agreed, already documented | - | - |

### Defects

#### 1. Renewals rated with changes made after their rating date

**Finding.** A renewal is rated 30 to 45 days before it takes effect, but the simulator applied the
household as it stood on the effective date. The reviewer found renewal rows rated at an address the
household moved to after the rating date, and cars added after it.

**What we found.** Two causes, one real and one a dating artifact:

- *Real:* a move, a car bought or sold, or a driver joining or leaving in the last weeks of a term
  reached the renewal without changing its rating date. Real policy systems re-rate the pending
  renewal when such a change is processed, and send a revised offer.
- *Artifact:* drivers and cars on policies already renewing on 1 January 2022 were all dated as added
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

#### 2. Conviction dates before 2022 moved to 1 January 2022

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

#### 3. Case reserves above the coverage limit

**Finding.** Reserve estimates (and the $250 minimum reserve) had no limit cap, so paid plus case
reserve could exceed a per-person limit, a per-accident limit or a $100 towing limit.

**What we found.** Confirmed on the valuation date: 36 bodily injury, 4 medical payments, 3 rental,
17 towing and 1 underinsured motorist features, and 9 accidents above their per-accident limit.

**Fix.** Every claim feature now carries the most it could pay: its per-person or per-claim limit, the
car's value less the deductible for physical damage, and for injury coverages a share of the
per-accident limit that is never less than what that claimant is eventually paid (so claimants' caps
add up to no more than the per-accident limit). Reserve estimates, the minimum reserve and reopening
reserves are held within it. Expense reserves stay separate. Excess-of-limits exposure is not
modeled.

**Check.** `validate.py`: "paid loss plus case reserve stays within every per-person, per-accident and
per-claim limit". Test: `test_reserve_caps_stay_within_the_limits`.

#### 4. Underinsured motorist ignores the at-fault insurer's per-accident limit

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

#### 5. Telematics scores before the driver joined the policy

**Finding.** Some score windows started before the scored car's primary driver was on the policy.

**What we found.** Confirmed: 6,741 windows, all but two before 2022, mostly caused by the dating
artifact in finding 1. Two related problems: a policy already in the program on the start date could have
joined it before the policy was written, and a car's window could start before the car was added.

**Fix.** A window starts no earlier than the day the car and its primary driver were both on the policy,
and an enrollment from before the extract starts no earlier than the policy's inception.

**Check.** `validate.py`: "a policy joins the program after it was written, and a car is scored only
while it and its driver are on the policy".

#### 6. Bound quotes carry the telematics discount, lost quotes never can

**Finding.** A bound quote shows the premium the policy was written with, including the 5%
participation discount when the customer joined the program. Quotes that did not bind were priced
without the program, so a discounted quote was always a bound one.

**What we found.** Confirmed: 6,233 of 23,315 bound quotes were discounted and no lost quote was.

**Fix.** Every quote now offers the program. Prospects who did not bind opt in at the rate the
program's take-up model gives new business, and are quoted with the participation discount. A new
column, `quote.telematics_opt_in`, shows who said yes: 26.7% of bound quotes and 28.7% of the others
(62% of lost quotes come through the direct channel, where take-up is highest; within each channel the two
rates agree to within half a point).

**Check.** Test: `test_renewals_changed_after_the_offer_are_re_rated` (which also checks the quote
column).

#### 7. Real-data comparison scales expected losses down twice

**Finding.** `scripts/compare_real_data.py` divided each row's answer-key expected loss by the row's
full cover period and multiplied by its earned exposure.

**What we found.** Confirmed. The answer key's expected loss already covers only the earned part of
each row (inside the extract, up to any cancellation), so rows that started before 2022 were scaled
down a second time. Only the comparison's "true expected loss" line was affected: on the same data its
Gini on claim counts moves from 0.247 to 0.251, on cost from 0.362 to 0.366, and the top-to-bottom
decile frequency ratio from 5.22 to 5.97. `validate.py` was not affected (it already works on the earned
window).

**Fix.** The expected loss is summed as it is. `docs/real_data_comparison.md` is regenerated.

#### 8. Release files leave out the documents the README links to

**Finding.** The reviewer listed the release zip's contents and found `docs/limitations.md`,
`docs/schema_changes.md`, `docs/real_data_comparison.md` and `CHANGELOG.md` missing.

**What we found.** Confirmed: the zips carried `README.md`, whose links to those files were broken for
anyone with only the release.

**Fix.** Every release zip (data and answer key, CSV and SQLite) now carries `README.md`,
`CHANGELOG.md` and `docs/` at the paths the README links to, and the release notes point readers to
`docs/limitations.md`.

#### 9. Documentation claims more than the checks prove

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

#### 10. Loss-ratio checks mix catastrophe and non-catastrophe losses

This came up while checking finding 9, and may or may not be one of the second review's findings. The
answer key's expected losses leave out catastrophes (fictional, dated hail, wind and flood events),
but `validate.py` compared them with each year's actual losses including catastrophes, and with
industry loss ratios that include them. Both comparisons are now like for like: actual losses
excluding catastrophes against expected, and expected plus the year's catastrophe losses against
industry.

### Suggestions about the table structure

| Suggestion | Response |
|---|---|
| `claim_expense_dimension` is a compatibility summary, not a dimension | **Already addressed.** It was removed when the tables were restructured; expenses are on `claim_feature` and `claim_payment`. |
| Effective-dated policy-driver and driver-vehicle relationships | **Already present in another form.** `driver.added_date` and `removed_date` date each driver's time on the policy, and each `exposure` row names the rated driver of one car for one period. A person never appears on two policies here: drivers who leave a policy leave the company, so there is no cross-policy identity to keep. |
| Coverage records with identifiers | **Already present in another form.** Each `exposure` row is the coverage record for one car and period (every limit, deductible and option, with its premium), and a claim feature points to it through `claim.exposure_id` and `claim_feature.coverage_code`. A separate coverage table would hold the same facts in a longer layout. |
| Party records and roles (claimants, passengers, attorneys, repairers, payees) | **Not adopted.** A sizeable addition; listed in [limitations.md](limitations.md) (claimants are numbered within their claim only). |
| Billing accounts, invoices, installments and receipts | **Not adopted.** Listed in limitations; non-payment cancellations are present without the billing trail behind them. |
| Quote versions and underwriting decisions | **Partly adopted.** Renewals now show an offer and, when re-rated, a later rating date and a revised offer. New-business quote revisions, referrals and declines are listed in limitations. |
| Claim status and assignment history; payees and reversal links | **Not adopted.** Payments already record voids and reissues as transaction types; adjuster assignments, status history and payees are listed in limitations. |

### Observations about realism

The reviewer noted that the rating plan is fitted to the simulator's own expected losses, that quotes
are built around a book already generated, that claims open before 2022 are missing, that national
benchmarks do not validate Chicago subgroups or large-loss tails, and that the scope is Illinois personal
auto. **Agreed; all are already documented** in [limitations.md](limitations.md) (sections 2, 4 and 5).
The reviewer's size figures (122,684 car-years, $136.5 million earned premium, a 65.6% loss ratio) were
for the earlier 30,000-policy default; the current figures are in the README.
