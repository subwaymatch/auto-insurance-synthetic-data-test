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

Dates are merge dates (US Central time). A version is the first dataset release (a git tag, with the data
attached to its GitHub release) that includes the change; pull requests #2 and #3 were first released in
v1.1.0. Figures for stages 1 to 4 are for the default run at the time (seed 20250101, 30,000 policies,
1 January 2022 to 30 September 2026), for stage 5 the new default of 51,391 policies, and from stage 6 on
43,368 policies to 31 December 2026, unless stated otherwise.

1. **2026-11-13, Starting point.** The repository is created; the aim is to replace the old dataset
   (California geography, a loss ratio near 20%, no link between driver risk and claims).
2. **2026-11-13, [v1.0.0](https://github.com/subwaymatch/auto-insurance-synthetic-data-test/releases/tag/v1.0.0): A simulated Chicago-area book ([PR #1](https://github.com/subwaymatch/auto-insurance-synthetic-data-test/pull/1)).**
   A seeded generator built on real ZIP data, with hidden driver risk, a deliberately imperfect
   rating plan and full claim lifecycles; loss ratios by year move to about 61% to 83%.
3. **2026-11-14, Record-level realism, household changes and industry calibration ([PR #2](https://github.com/subwaymatch/auto-insurance-synthetic-data-test/pull/2)).**
   Individual records made consistent, mid-term household changes, reserve history, claim detail,
   more coverages and a quote funnel; expected loss ratios recalibrated to follow US and Illinois
   industry figures; data published as GitHub releases.
4. **2026-11-15, Audit fixes and like-for-like calibration ([PR #3](https://github.com/subwaymatch/auto-insurance-synthetic-data-test/pull/3)).**
   A second review fixed coverage-limit, claim-timeline and policy-count errors, and claim rates are
   now compared with national figures on those figures' own definitions.
5. **2026-11-16, [v1.1.0](https://github.com/subwaymatch/auto-insurance-synthetic-data-test/releases/tag/v1.1.0): Real vehicles, a real-data benchmark, telematics, names and a cleaner schema ([PR #4](https://github.com/subwaymatch/auto-insurance-synthetic-data-test/pull/4), [PR #5](https://github.com/subwaymatch/auto-insurance-synthetic-data-test/pull/5)).**
   The data is compared with a real insurer's portfolio; the 110 hand-picked car models become a catalog of
   every US make, model and model year, weighted by Chicago's roads, and the fleet ages to match; a telematics
   program, realistic names and a consistent table layout are added; the default book grows to 51,391
   policies, and `docs/limitations.md` collects every limit of the dataset.
6. **2026-11-17, [v1.1.1](https://github.com/subwaymatch/auto-insurance-synthetic-data-test/releases/tag/v1.1.1): Fixes from an external review ([PR #6](https://github.com/subwaymatch/auto-insurance-synthetic-data-test/pull/6)).** An outside review's defects are fixed;
   releases add a SQLite database; the default book becomes 43,368 policies over five full years (2022 to 2026).
7. **2026-11-18, [v1.1.2](https://github.com/subwaymatch/auto-insurance-synthetic-data-test/releases/tag/v1.1.2): Decisions on what was known at the time ([PR #7](https://github.com/subwaymatch/auto-insurance-synthetic-data-test/pull/7)).** A third review's findings:
   renewals and telematics scores are decided only on what was known on the day, and every renewal offer is
   kept.
8. **2026-11-19, [v1.1.3](https://github.com/subwaymatch/auto-insurance-synthetic-data-test/releases/tag/v1.1.3): An operating company's data ([PR #8](https://github.com/subwaymatch/auto-insurance-synthetic-data-test/pull/8)).** A realism audit asked whether the data
   looks like an operating company's: discounts are filed and only roughly right, new customers and some
   agencies cost more than they are charged, staff work business days and losses follow Chicago's real days,
   records carry policy numbers, claim numbers and VINs, every premium is billed and collected and every claim
   payment has a payee, a check number and an approver. A second round added a market cycle for quotes and new
   business, customers who leave after claims, used-car values that bring physical damage premiums to Illinois'
   averages, 120 independent agencies of very unequal size, and a general ledger.
9. **2026-11-20, [v1.1.4](https://github.com/subwaymatch/auto-insurance-synthetic-data-test/releases/tag/v1.1.4): The website, data dictionary fixes and American spelling ([PR #9](https://github.com/subwaymatch/auto-insurance-synthetic-data-test/pull/9), [PR #10](https://github.com/subwaymatch/auto-insurance-synthetic-data-test/pull/10)).**
   A website with a data dictionary for every column; writing it found two data errors, fixed; the data and
   its documentation use American spelling.
10. **2026-11-21, [v1.1.5](https://github.com/subwaymatch/auto-insurance-synthetic-data-test/releases/tag/v1.1.5): A dataset realism audit ([PR #11](https://github.com/subwaymatch/auto-insurance-synthetic-data-test/pull/11)).** Payees and identities that contradicted
    the record are fixed (lienholders without a loan, attorneys before retention, a later named insured on
    earlier claims), as are non-payment cancellations without a bill and a validator check that could not fail;
    the run summary records provenance. A follow-up made the tables hold records rather than totals, opened the
    extract with the claims then open, replaced the fictional catastrophes with real storms, extended the
    vehicle catalog back to 1981, made the keys system counters, set case reserves and the rating plan from what
    the company knows rather than from the truth, and added a benchmark sheet that says how far to trust each
    figure.
11. **2026-11-21, A logo with waves ([PR #12](https://github.com/subwaymatch/auto-insurance-synthetic-data-test/pull/12), [PR #13](https://github.com/subwaymatch/auto-insurance-synthetic-data-test/pull/13)).** Website and brand only; no data change.
12. **2026-11-22, [v1.1.6](https://github.com/subwaymatch/auto-insurance-synthetic-data-test/releases/tag/v1.1.6): Two further realism audits ([PR #14](https://github.com/subwaymatch/auto-insurance-synthetic-data-test/pull/14)).** Records that contradicted their context are removed (driving
    records after a driver left, notices after payment, lenders paid on kept wrecks, reviews after a final
    payment), a crash's costs are tied together, competitors price near the true risk, vehicles get equipment
    by model year, and the ledger closes each year-end.
13. **2026-11-22, [v1.1.7](https://github.com/subwaymatch/auto-insurance-synthetic-data-test/releases/tag/v1.1.7): Follow-up checks ([PR #15](https://github.com/subwaymatch/auto-insurance-synthetic-data-test/pull/15)).** Rentals are paid only once the car is back, payments due to someone who
    has died go to the estate, telematics periods are measured on the mileage driven then, renewals use the
    named insured of the offer day, and the exposure rows publish the mileage and use each period was rated on.
14. **2026-11-24, [v1.1.8](https://github.com/subwaymatch/auto-insurance-synthetic-data-test/releases/tag/v1.1.8): A further audit ([PR #16](https://github.com/subwaymatch/auto-insurance-synthetic-data-test/pull/16)).** Subrogation recovers only what has been paid by then, a car passed to
    another driver is rated on their mileage and use, and a crash can kill the insured at the wheel and the
    household's other drivers riding along, who then leave the policy as any death does.
15. **2026-11-24, [v1.1.9](https://github.com/subwaymatch/auto-insurance-synthetic-data-test/releases/tag/v1.1.9): An audit of v1.1.8 ([PR #17](https://github.com/subwaymatch/auto-insurance-synthetic-data-test/pull/17)).** Medical providers are paid again, revised renewals are billed when they
    are rated, refunds wait for the cash, every endorsement records a change, a car written off re-rates the
    others that day, the first driver is an adult and licensed at inception, a fatal crash has a police report,
    and a crash's subrogation comes back together.
16. **Unreleased, An audit of v1.1.9.** A car lost in a claim is taken off once the claim is reported (backdated),
    spare cars pass to drivers without one, divorced spouses are divorced, fatal crashes have police reports,
    lapsing policies pay no later endorsement bills, nothing is confirmed or chased after a cancellation, new
    policies are placed on what was known on their quote day, and opening telematics enrollments start with a term.

### Releases

For citing a version of the data. The content hash (in `run_summary.json`) identifies the default run's
published files; it is given where the changelog recorded it.

| Version | Date (tag) | Commit | Pull requests | Default run | Content hash |
|---|---|---|---|---|---|
| [v1.0.0](https://github.com/subwaymatch/auto-insurance-synthetic-data-test/releases/tag/v1.0.0) | 2026-11-13 | `7257f2f` | #1 | 30,000 policies to 2026-09-30 | - |
| [v1.1.0](https://github.com/subwaymatch/auto-insurance-synthetic-data-test/releases/tag/v1.1.0) | 2026-11-16 | `ccd1d9d` | #2 to #5 | 51,391 policies to 2026-09-30 | - |
| [v1.1.1](https://github.com/subwaymatch/auto-insurance-synthetic-data-test/releases/tag/v1.1.1) | 2026-11-17 | `9fe6062` | #6 | 43,368 policies to 2026-12-31 | - |
| [v1.1.2](https://github.com/subwaymatch/auto-insurance-synthetic-data-test/releases/tag/v1.1.2) | 2026-11-18 | `bba5687` | #7 | 43,368 policies to 2026-12-31 | `4b5bca69599df49e` |
| [v1.1.3](https://github.com/subwaymatch/auto-insurance-synthetic-data-test/releases/tag/v1.1.3) | 2026-11-19 | `b4917aa` | #8 | 43,368 policies to 2026-12-31 | `a64d95db973613fa` |
| [v1.1.4](https://github.com/subwaymatch/auto-insurance-synthetic-data-test/releases/tag/v1.1.4) | 2026-11-20 | `03c2634` | #9, #10 | 43,368 policies to 2026-12-31 | `7b4b15d1dcb53b95` |
| [v1.1.5](https://github.com/subwaymatch/auto-insurance-synthetic-data-test/releases/tag/v1.1.5) | 2026-11-21 | `4a13b9f` | #11 (#12 and #13 change no data) | 43,368 policies to 2026-12-31 | `963889a73f229de8` |
| [v1.1.6](https://github.com/subwaymatch/auto-insurance-synthetic-data-test/releases/tag/v1.1.6) | 2026-11-22 | `c28d1cd` | #14 | 43,368 policies to 2026-12-31 | `4a1f9ef22b9bc813` |
| [v1.1.7](https://github.com/subwaymatch/auto-insurance-synthetic-data-test/releases/tag/v1.1.7) | 2026-11-22 | `529956c` | #15 | 43,368 policies to 2026-12-31 | `6a360e75d7d87f3f` |
| [v1.1.8](https://github.com/subwaymatch/auto-insurance-synthetic-data-test/releases/tag/v1.1.8) | 2026-11-24 | `635ea6f` | #16 | 43,368 policies to 2026-12-31 | `4a9b0599022f5117` |
| [v1.1.9](https://github.com/subwaymatch/auto-insurance-synthetic-data-test/releases/tag/v1.1.9) | 2026-11-24 | `de3495e` | #17 | 43,368 policies to 2026-12-31 | `4612b99cdbc9e521` |
| Unreleased | | | this branch | 43,368 policies to 2026-12-31 | `9774ec39a673aeea` |

Every release is seed 20250101 from 1 January 2022, and the same seed and options always produce
byte-identical files with the pinned library versions (`requirements.txt`).

## Unreleased: an audit of v1.1.9

An audit of v1.1.9 (default run and seed 101) found ten issues that no check covered; both books passed every
check. Figures are for the default run after these changes (content hash `9774ec39a673aeea`).
`docs/review_response.md` ("Audit of v1.1.9") answers each finding.

- **A car lost in a claim is taken off once the company knows.** Its removal, the other cars' re-rating, the
  endorsement, the cancellation of an emptied policy and their confirmations all came the day after the loss, before
  the claim was reported (up to 221 days before), and eight cars whose claims would only be reported in 2027 were
  already off the policy. The simulation now draws the claim's first notice when the loss happens. A car lost in a
  claim with a physical damage, rental or towing feature is removed, backdated to the day after the loss, once the
  claim is reported: the re-rated rows' `rating_date` is the report date (so it can follow the row's start), and
  the endorsement, the cancellation and their letters come no earlier. A car whose claim is not reported by the
  valuation date stays on the policy, with no further losses. A removal not known before a renewal takes effect
  does not revise it.
- **Spare cars.** Ranks are never reused (two cars had shared the last rank and both carried the occasional
  youthful operator surcharge); a driver left with only a spare car drives it as their main car; and a newly
  licensed teenager or a new spouse without a car takes over a spare car the household already has. The surcharge
  now falls on one car, and only when a listed driver under 25 has no car of their own (98 periods had it without
  one).
- **People and claims.** A divorcing spouse is divorced (all 646 had stayed married), and a couple who die on the
  same day leave no widow (the spouse no longer takes the policy over as a widow first). A crash that killed
  someone has a police report even with no claim of the victim's own, as does a crash whose driver died by the
  next day; a rental ends when the household's only driver dies, even when the death falls early in the next term.
  A car its owner kept after a total loss has no losses for the rest of the term, storms included.
- **Billing and contacts.** A policy cancelled for non-payment pays no bill due after the installment it missed
  (14 endorsement bills had been paid, five by bank draft). Changes and cancellations are confirmed when they are
  booked; nothing is confirmed, chased or warned of once a policy is canceled (844 change confirmations had gone out
  on or after a cancellation); no staff calls on a Saturday holiday.
- **Placement and telematics.** A new policy is placed with its company on what was known on its quote day (drawn
  with the population and used by the simulation and the quote table); 30 had been placed on a violation that
  reached the record after the quote. A policy already renewing when the extract opens is placed on its record as it
  entered the extract (documented: its record when first written is not retained). A telematics enrollment from
  before 2022 begins on one of the policy's earlier term effective dates.
- **Dictionary and website.** Prior-carrier reports, `telematics_enrolled`, the claim table's "totals" and the ZIP
  code example are corrected; v1.1.9 is dated here.
- **Checks.** `validate.py` adds ten checks, one for each finding (203 in all); on v1.1.9 eight fail on the default
  run and nine on seed 101. Two existing checks allow the backdated re-rating: a row may be rated after it starts
  when it follows a car's backdated removal (rated the day the claim was reported), and its household is judged as of
  its start. Unit tests cover the cut's wait for the report, the rental's end (in the term and after it), a couple
  dying together and spare-car promotion.
- **The default run** (content hash `9774ec39a673aeea`): loss ratios by accident year 83.7%, 80.3%, 65.0%, 60.2% and
  69.1% for 2022 to 2026, of which catastrophes 0.0%, 4.0%, 2.7%, 0.9% and 5.9%; overall 70.5% (was 70.1% in v1.1.9;
  68.3% to 71.3% across five seeds); annualized retention 81.2%. 195,405 policy terms, 444,330 exposure rows, $212.2
  million earned premium, 22,670 claims, 39,879 features, 60,877 claim payments, 103,972 reserve transactions,
  878,791 bills and 890,425 receipts, 118,697 quotes and 168,956 renewal offers. These changes move later random
  draws, so every figure moves a little. All 203 checks pass on the default run and on seeds 7, 11, 23 and 101, and
  every integrity check on seed 42 (content hashes `5ff437dce260e4d6`, `93fdb528bf233db7`, `a52b495b7b6dbc05`,
  `ccf9e0445a89c5c8` and `3a724fa8524920b2`); seed 42's bodily injury frequency, 0.67 paid claims per 100 car-years,
  is just below its tuning band's floor of 0.70, from the book that seed drew rather than claim luck (its injury
  losses are 0.97 times the answer key's expected; `docs/benchmarks.md`). Checking the seeds found three more defects,
  fixed here: a storm could strike a car on a salvage title, a rental settled late in a term could run past the
  death of the household's only driver early in the next, and a spouse could take the policy over as a widow before
  dying the same day. The test suite has 88 tests (87 pass, and one needs `pyarrow`).

## 2026-11-24, [v1.1.9](https://github.com/subwaymatch/auto-insurance-synthetic-data-test/releases/tag/v1.1.9): An audit of v1.1.8 ([PR #17](https://github.com/subwaymatch/auto-insurance-synthetic-data-test/pull/17))

An audit of v1.1.8 (default run and seed 101) found 18 record-level issues that no check covered; both books
passed every check. Figures are for the default run after these changes (content hash `4612b99cdbc9e521`).
`docs/review_response.md` ("Audit of v1.1.8") answers each finding.

- **Payees and vendors.** Medical payments go to the medical provider about 60% of the time again (PR #16's
  injured-driver link had sent all of them to the insured, some jointly with an attorney). Payments to an estate
  are checks, and go to the estate from the day the person is removed. Vendor sizes are log-normal, so no trade is
  nearly all one vendor (one appraiser had taken 99.7% of seed 101's appraisals). A crash's repair, rental and tow
  subrogation come back together, after the last of them closes.
- **Claims.** An injury claim closed without payment is an alleged soft-tissue injury (its type and attorney
  odds read what was paid, not the gross damages). A crash that killed someone always has a police report, and a
  medical payments claim counts as someone hurt at the scene. A supplemental payment ends the loss reserve, and a
  litigated feature's expense reserve closes at its first close. No rental is paid after a crash that killed
  every driver of the household.
- **Policies.** A scheduled change that could not happen as the policy stands (a trade of a car already written
  off, a sale from a one-car household, a teenager whose parents are too young) no longer ends a period: there
  were 458 endorsements with no change, some charging premium. A car written off while another stays is removed by
  an endorsement that day, so the multi-car discount ends with it (it lasted months before). A household that loses
  its cars one after the other and will not have a replacement before its renewal can be offered cancels, as one
  losing its only car does. A death that ends the policy is applied before other same-day changes and hands no cars
  over; `insured_vehicle.primary_driver_id` is the driver on the car's latest row. A change after the valuation date
  no longer revises a pending offer.
- **People and quotes.** The named insured is an adult and licensed at the policy's inception (a tenure that would
  have begun earlier is shortened), so every policy's first driver joined at inception. A quote's named insured age
  uses the birth day, as the youngest driver's does. Prior-carrier reports, like driving records, stop when the
  driver leaves.
- **Billing.** A term's first bill goes out on its rating date: a revised renewal bills its revised premium then,
  not on the original offer day (8,583 had billed it early, 1,027 were paid early). A refund goes out once the
  bills already sent are paid and the cash received covers it, so a term's cash never goes below zero. A final
  balance waits for any bank draft still in flight, and goes out the business day after the cancellation is
  booked. A cancellation at the customer's request is keyed within ten days, and any cancellation or change in
  effect by the valuation date is booked by then.
- **Catalog and dictionary.** The 1985 Subaru RX Turbo has its engine (EPA's record is blank). The dictionary lists
  `Insured and Attorney`, the estate payee, the first bill's date and the final balance's.
- **Checks.** `validate.py` adds 18 checks and extends one (prior-carrier reports), so each finding has one (193 in
  all); 17 fail on v1.1.8's default run, and the other two (vendor concentration, a rental after every driver died)
  on its seed 101. Unit tests cover the write-off cut, the change guards, refund timing and quote ages.
- **The default run** (content hash `4612b99cdbc9e521`): loss ratios by accident year 82.5%, 81.0%, 67.4%, 59.5% and
  66.4% for 2022 to 2026, of which catastrophes 0.0%, 3.5%, 2.4%, 1.0% and 6.4%; overall 70.1% (was 69.8% in
  v1.1.8; 69.6% to 72.2% across five seeds); annualized retention 81.3%. 195,621 policy terms, 446,579 exposure rows
  (more: a write-off now re-rates the other cars), $211.5 million earned premium, 22,725 claims, 39,867 features,
  61,127 claim payments, 104,023 reserve transactions, 882,139 bills and 893,899 receipts, 118,829 quotes and
  169,123 renewal offers. These changes move later random draws, so every figure moves a little. 193 checks pass
  on the default run and on seeds 7, 11, 23, 42 and 101 (content hashes `7aae95a615ec68b2`, `c4d294f697cf6dec`, `f509671da5a88d1f`, `7c84c721d975916a`, `edd0a9d11cbe5828`), with every calibration figure inside its band. The test suite
  has 83 tests (82 pass, and one needs `pyarrow`).

## 2026-11-24, [v1.1.8](https://github.com/subwaymatch/auto-insurance-synthetic-data-test/releases/tag/v1.1.8): A further audit ([PR #16](https://github.com/subwaymatch/auto-insurance-synthetic-data-test/pull/16))

A realism audit of v1.1.7 (default run and an independent seed, 101) found three record-level issues; both books
passed every check. Figures are for the default run after these changes (content hash `4a9b0599022f5117`).
`docs/review_response.md` ("Audit of v1.1.7") answers each finding.

- **Subrogation recovers what has been paid.** A feature's subrogation was set on its eventual paid loss and
  received after its first close, so when a feature later reopened for a supplement the receipt already included
  the supplement's share: 15 collision features in v1.1.7 had recovered more than they had paid on some day
  ($7,934 in all). The share for the payments to the first close (never more than they come to, less the salvage)
  is now received after that close, and a reopening's share after its supplement is paid; the total is the same.
  A wreck that would fetch more than had been paid before a reopening (a cheap car with a high deductible) is sold
  once the supplement is paid.
- **A car passed to another driver takes their mileage and use.** When a driver left and another took over the
  car, it kept the old driver's mileage and use: all 1,295 such switches in v1.1.7 kept them, so a commuter could
  be rated on the leaver's 1,500 miles of pleasure use. The new driver's commute, age, employment and whether the
  car is an extra one for them now give its mileage and use from the handover (dated, so earlier telematics
  periods keep theirs), and a child under 16 is not given the car.
- **Deaths in crashes.** Injury types followed a claim's cost, so a very costly uninsured motorist claim of the
  policy's own driver could be labeled a fatality while the driver kept driving (once on seed 101). A crash can now
  kill the insured at the wheel (`config.CRASH_DEATH_*`, assumed rates sized on NHTSA's counts, higher in
  single-vehicle and severe crashes and for older drivers). The death enters the household's record like any other:
  the driver leaves the policy the day after dying (the day of the crash or within a month), a surviving spouse takes
  the policy over or it is canceled, their cars pass to the other drivers, and the policy is re-rated from that day
  (`simulate._crash_deaths`). Their own claims (medical payments, uninsured or underinsured motorist) are
  fatalities paid to the limit, to their estate after the death; any other first-party injury is at worst a head
  or spinal one.
- **Household members riding along can die too.** The household's other listed drivers (the named insured when
  someone else drives, a spouse, another adult, a teenager) ride along in some crashes (`config.RIDE_ALONG_P`,
  assumed) and can die in the same crash, at a little less than the driver's risk and with their own age's
  frailty (`PASSENGER_DEATH_FACTOR`). All of a crash's dead leave the policy on the same day, the named insured
  last, so a spouse killed with them does not take the policy over; none of them drives after the crash. Each gets
  a medical payments claim of their own (claimant 2 and up) and, in a crash caused by an uninsured or underinsured
  driver, an uninsured motorist claim, paid to the limit and to their estate. There is no bodily injury claim for
  them on the policy when another household member drove: Illinois enforces the household exclusion then
  (215 ILCS 5/143.01). New column `claim_feature.injured_driver_id`: the listed driver a medical payments or
  uninsured motorist feature is for (the driver as claimant 1, or a household member riding along), so a payment
  to an injured person is made out to them, and the deaths can be followed to `driver`.
- **Checks.** `validate.py`: on no day has a feature recovered more than it had paid; most cars that pass to
  another driver are rated on a newly declared mileage or use; a feature's injured driver was on the claim's policy
  on the loss date, and the first claimant is the claim's driver; someone killed in a crash, at the wheel or riding
  along, is recorded as deceased within a month and drives in no later crash. Unit tests feed the recovery check
  the audit's example and check how a crash death cuts a policy's period, a driver and a passenger killed together
  included.
- **A driver already gone when their leave event falls due** (a teenager killed riding along who was to move out
  later) is now skipped without breaking the batch; seed 101 failed to build on it.
- **The default run** (content hash `4a9b0599022f5117`): loss ratios by accident year 84.5%, 79.5%, 65.6%, 62.9% and
  63.3% for 2022 to 2026, of which catastrophes 0.0%, 4.0%, 2.3%, 0.8% and 5.7%; overall 69.8% (was 67.6% in
  v1.1.7; 69.5% to 71.5% across five seeds); annualized retention 81.3%. 195,658 policy terms, 439,321 exposure
  rows, $211.8 million earned premium, 22,933 claims, 39,983 features, 61,078 claim payments, 104,420 reserve
  transactions, 880,013 bills and 891,776 receipts, 118,642 quotes and 168,997 renewal offers; 11 people killed in
  crashes, 2 of them riding along. The handover redraws and crash deaths move later random draws, so every figure
  moves a little. 175 checks pass on the default run and on seeds 7, 11, 23, 42 and 101 (content hashes
  `ac814ba495cca749`, `42e90cdaa2e9139a`, `8b597ae79e5f36ab`, `1a276372cec59eab`, `df2bb4217f33dc5e`), with every
  calibration figure inside its band. The test suite has 79 tests (78 pass, and one needs `pyarrow`).

## 2026-11-22, [v1.1.7](https://github.com/subwaymatch/auto-insurance-synthetic-data-test/releases/tag/v1.1.7): Follow-up checks ([PR #15](https://github.com/subwaymatch/auto-insurance-synthetic-data-test/pull/15))

Independent checks of v1.1.6 found records still at odds with their timing, and a way later events could reach
back into earlier telematics scores. The release is content hash `6a360e75d7d87f3f`. `docs/review_response.md` ("Follow-up checks") answers each finding.

- **Rentals paid once the car is back.** A rental was paid at a time drawn without regard to how long the
  car was kept, so 868 of 4,095 paid rentals in v1.1.6 were paid in full before enough days had passed since
  the loss for the rental to cost that much at its daily limit. A rental now closes, and is paid, after the
  car is returned (the loss day plus the days it was kept, then the invoice).
- **Estates.** Six payments in v1.1.6 named a named insured who had died before the payment, on a policy
  that ended with the death. A payment due to someone who has died now goes to "Estate of" them.
- **Telematics on the mileage of the time.** Renewal scores are calculated when the renewal is offered, but
  the simulation had already applied the rest of the expiring term's household changes: a move after the
  offer day, which redraws the cars' mileage, changed the mileage behind the score of the driving before it,
  and a move inside a scoring period applied its new mileage to the whole period. Each car's mileage changes
  are now recorded with their dates, and a period is measured on the mileage driven in it, day by day.
- **Renewals on the named insured of the offer day.** The renewal decision used the age of the policy's
  current named insured, which could be a surviving spouse who took the policy over after the offer was made.
  It now uses the named insured on the offer day.
- **Mileage and use over time.** Mileage and use change with a move or a new main driver, but only their last
  values were published. `exposure` gains `rated_annual_mileage` and `rated_primary_use` (what each period
  was rated on), and `exposure_truth` the true annual mileage of each period. `insured_vehicle` shows use,
  mileage and parking as of the valuation date (or when the car left), not the simulation's last state, which
  could include a move after the valuation date.
- **Checks.** `validate.py` checks each: a rental is paid no sooner after the loss than its amount at the daily
  limit allows, a payment to someone who has died goes to the estate, and each vehicle's use and mileage are
  those of its latest period by the valuation date. A unit test checks the mileage history.
- **The default run** (content hash `6a360e75d7d87f3f`): loss ratios by accident year 81.3%, 70.4%, 67.5%, 58.2% and 65.5% for
  2022 to 2026, of which catastrophes 0.0%, 3.6%, 2.3%, 0.9% and 6.1%; overall 67.6% (was 69.1%; 67.6% to 70.5%
  across five seeds); annualized retention 81.3% (was 81.2%). 195,901 policy terms, 438,620 exposure rows,
  $211.9 million earned premium, 23,097 claims, 39,960 features, 60,784 claim payments, 103,928 reserve
  transactions, 882,461 bills and 894,386 receipts, 118,642 quotes and 169,426 renewal offers. The timing fixes
  move later random draws, so every figure moves a little. 171 checks pass on the default run and on seeds 7,
  11, 23 and 42 (content hashes `f07863e71fc8380c`, `b36c9e866dab6246`, `51021c0f161c0528`, `9bfa31600329b3cd`).
  The test suite has 75 tests (74 pass, and one needs `pyarrow`).

## 2026-11-22, [v1.1.6](https://github.com/subwaymatch/auto-insurance-synthetic-data-test/releases/tag/v1.1.6): Fixes from two further realism audits ([PR #14](https://github.com/subwaymatch/auto-insurance-synthetic-data-test/pull/14))

The release is content hash `4a1f9ef22b9bc813`.

### Fixes from two further realism audits

Two more audits of the default run listed records that still contradicted their context, modeling shortcuts
and statutory gaps (40 findings, six shared). `docs/review_response.md` ("Two further realism audits") answers
each.

- **Keys and numbers.** Unpaid agency statements are keyed by the month they are drawn up (they had the
  founding day's keys); quotes are numbered in the order asked for within a day (bound ones had come first);
  each year's sequence numbers start near 1; vendor keys no longer run by vendor type.
- **Claim payments.** One defense firm, appraiser, bill reviewer, salvage auction and subrogation insurer per
  claim. An uninsured motorist claim's first claimant is the policy's own injured person, paid as "Insured" or
  "Insured and Attorney"; other occupants are claimants. Only a car owned outright can be kept as salvage, and
  a leased car's fees and supplements go to the lessor. When the other driver's insurer repays a collision, it
  repays the rental and the tow in the same share.
- **Reserves.** Each coverage's formula reserve follows its own severity trend (all had followed bodily
  injury's). A final payment settles a feature: no reserve and no review after it unless it reopens. No
  appraisal fee on glass or on stolen cars never recovered. Fraud referrals are made while the claim is open,
  rarely on routine glass and catastrophe claims, from what is known at report.
- **Crashes.** A crash's costs move together through a shared severity (a Gaussian copula): collision, the
  other car, injuries, medical payments, the tow and the rental's length. Underinsured motorist claims arise
  only above the 25/50 minimum (215 ILCS 5/143a-2(4)). New customers' extra claims follow the daily calendar.
  Towing pays for floods, fires and storms as well as crashes, and catastrophe losses fall in their storm's
  hours (from NOAA's report times; `catastrophe.start_time` and `end_time` are new).
- **People and records.** Driving records and SR-22 filings stop when the driver or the policy does; a
  named insured who dies is marked deceased on the cancellation day; good-student status is as of the
  driver's last day insured; adults join a policy at 18 or older, parents were at least 18 at a child's
  birth, and no two people in a household share a full name. A move redraws commutes and mileage, and a
  replacement car going to another driver takes theirs. The surviving spouse's age rates the policy; the car
  count follows the cars on it.
- **Vehicles.** Automatic emergency braking and immobilisers follow the model year (and every Tesla has both
  from 2015); the theft-wave Kias and Hyundais have no immobiliser. A replacement on a new lease is new. The
  used-car index lifts a car's value only by how far used prices ran ahead of the new-car prices its model
  year sold at, from a year old, so new cars are no longer all at the 115% cap. The catalog's sales priors for
  models the crash data never names are smaller and price-damped (no price cap, by the owner's decision);
  electric versions are tagged `ev`.
- **Pricing and quotes.** The planted young-driver distortions apply only to driver-rated coverages, and the
  insurance-score tiers never rise with the score. Competitors price near the true risk, so under-priced
  segments convert more; lost quotes get the bound policies' channel mix by age (a spurious under-35 step in
  direct conversion is gone). Agencies take no quotes on New Year's Day, July 4, Thanksgiving or Christmas.
- **Renewals and cancellations.** A policy left with no car is not offered a renewal. An underwriting
  cancellation comes 36 to 60 days after inception with at least 30 days' notice (215 ILCS 5/143.15).
- **Billing.** A notice of cancellation is dated on the business day it is mailed and sent only while the bill
  is unpaid; paid-in-full renewals are paid within the grace period; an endorsement re-spreads the balance to
  bill, a larger return is refunded at once, and a small balance is not split into micro-bills.
- **Telematics.** A plug-in device records no phone use (its score reweights the other behaviors); any
  mileage takes at least one trip.
- **Calendar and staff.** Hires, terminations, appointments, producer start dates and write-offs fall on
  business days; a fixed holiday at a weekend is a holiday. Producers are hired over the years, some during
  the extract, and write only policies incepting after they start; an agency is appointed by its first policy.
- **Ledger.** Each December 31 closes the income-statement accounts to surplus (journal `CL`).
- **Found while checking seeds.** Two cars 30 model years apart could share a VIN: position 7 is now a digit
  to 2009 and a letter from 2010, as in real VINs. Injury and medical costs, once tied to the crash's severity,
  ran above their calibration (the claims that happen are the severe crashes' ones); they are scaled back by
  that selection's known lift, so each coverage's expected cost holds.
- **Checks.** `validate.py` checks each of these (168 checks on the default run); its overall loss
  ratio counts only accidents in the extract.
- **The default run** (content hash `4a1f9ef22b9bc813`): loss ratios by accident year 77.9%, 77.7%, 68.8%, 59.7%
  and 66.3% for 2022 to 2026, of which catastrophes 0.0%, 3.4%, 2.1%, 0.6% and 6.0%; overall 69.1% (was
  72.1%; 69.1% to 70.2% across five seeds); annualized retention 81.2% (was 81.6%). 195,367 policy terms, 438,440
  exposure rows, $212.0 million earned premium, 22,845 claims, 40,062 features, 61,032 claim payments, 104,316
  reserve transactions (was 129,559), 879,886 bills and 891,769 receipts, 118,642 quotes and 168,899 renewal
  offers. 168 checks pass on the default run and on seeds 7, 11, 23 and 42. The test suite has 74 tests (73
  pass, and one needs `pyarrow`). The README, `docs/limitations.md`, `docs/real_data_comparison.md`,
  `docs/benchmarks.md` and the website give the new run's figures.

## 2026-11-21: A logo with waves, and icons on the website ([PR #12](https://github.com/subwaymatch/auto-insurance-synthetic-data-test/pull/12), [PR #13](https://github.com/subwaymatch/auto-insurance-synthetic-data-test/pull/13))

Website and brand only: the data and its release are unchanged (still [v1.1.5](https://github.com/subwaymatch/auto-insurance-synthetic-data-test/releases/tag/v1.1.5)).

- **Logo.** The sunrise o of the Lakefront wordmark gains two waves in its lower half, rising and falling in
  step with a wavy horizon, keeping the circle's outline (`brand/logo/`, built by `brand/make_logos.py`; the
  variations tried are in `brand/waves/`). The website's hero sun is drawn from the same mark, the hero has no
  background, and the header logo is 20 px tall (the footer's stays 22 px).
- **Icons.** Arrow characters on the home page cards and in the data dictionary's links become Lucide's
  arrow-right icon (`lucide-static`, ISC license), with hidden text for screen readers where the arrow carries
  meaning.

## 2026-11-21, [v1.1.5](https://github.com/subwaymatch/auto-insurance-synthetic-data-test/releases/tag/v1.1.5): A dataset realism audit ([PR #11](https://github.com/subwaymatch/auto-insurance-synthetic-data-test/pull/11))

Each subsection gives the default run after its changes; the release is content hash `963889a73f229de8`.

### Fixes from a dataset realism audit

A realism audit (20 November 2026, at `03c2634`) found records that contradicted their own business context
although every check passed, and a validator check that could not fail. All are fixed;
`docs/review_response.md` gives the before-and-after counts for the default run and seed 7.

- **Lenders are paid only when there is a loan.** A total loss was split between a lienholder and the owner
  at random, whatever the car's ownership: 1,176 of 1,547 lienholder payments went to cars owned outright.
  The car's ownership at the loss now travels with the claim. A financed car's total loss pays off the loan
  first (an assumed 35% to 120% of the settlement, never more than the settlement), a leased car's goes to
  the leasing company, an owned car's to its owner; one lender per car. 578 lienholder payments remain.
- **Non-payment cancellations always have an unpaid bill.** 17 terms were canceled for non-payment of an
  installment that a return premium had reduced to nothing, so no bill existed. A household that leaves
  with no bill to miss is now recorded as canceling at its own request on the same day, and the validator's
  98% tolerance is a rule every record must meet.
- **Attorneys are paid only once retained.** 20 joint claimant-and-attorney payments predated the attorney;
  an injury payment's payee is now decided on its date, and a void follows the check it cancels.
- **The past keeps its named insured.** A loss with no driver named the policy's final named insured, and so
  did payments to the insured: 2 claims and 1 payment named someone who joined later, and 95 more claims a
  later named insured already on the policy. The cause was also in the simulator: its effective-dated
  histories stored the caller's array rather than a copy, so the named insured recorded for the opening day
  changed whenever a surviving spouse took a policy over. Histories now keep a copy, and claims and payments
  use the named insured on their own date. No renewal offer, telematics record or exposure row changed.
- **Final-balance checks are banked on business days** (83 were dated at a weekend).
- **Checks that can fail.** `validate.py` compared a claim's policy with itself; it now checks a claim's
  policy, term, vehicle and model year against its exposure row, and every redundant key against its parent.
  New checks cover lienholders, attorney payees, identities on the loss and payment dates, and receipts on
  business days. A new test corrupts one record for each and shows the check fails.
- **Provenance.** `run_summary.json` now records hashes of the CSVs (`content_hash`, `tables_hash`,
  `answer_key_hash`, and how they are computed) and, under `build`, the source revision, whether the
  generator's files had uncommitted changes, the Python, NumPy and pandas versions, and fingerprints of the
  columns and reference files. It is written after the CSVs, so the hash is in it. `validate.py` recomputes
  the hashes.
- **Taken up afterwards.** The audit's modeling suggestions (reserve allocation and pricing that do not see
  eventual outcomes, independent US tail benchmarks) were taken up after these fixes (see the next
  subsection); its suggested degraded "messy" edition is still not adopted.
- **The default run** (content hash `06932bb41e745579`): only payees, 17 cancellation reasons, 97 claims'
  `involved_driver_id` and some dates changed. Every loss and premium amount, the loss ratio (67.4%),
  frequencies, severities and retention are as before. Claim payments 60,542 (was 61,678), reserve
  transactions 124,306 (was 125,378), bills 887,706 and receipts 896,585. 147 checks pass (was 140) on the
  default run and seed 7; 67 tests (was 64).

### After the dataset realism audit: real storms, older cars, records not totals, reserves and rates from what is known

After the fixes above, the owner asked for further realism changes, and the audit's two remaining modeling
suggestions (A7 and A8) were taken up. `docs/review_response.md` lists them under "Follow-up changes".

- **Notices of cancellation.** Every cancellation for non-payment now has a notice of cancellation mailed at
  least ten days before it, as 215 ILCS 5/143.15 requires. A missed bank draft is attempted on its due date
  and returned, and the notice goes out the day it comes back. `validate.py` checks every one (5,009
  cancellations whose missed bill fell due in the extract, none without).
- **Vehicles back to 1981.** The catalog reaches model year 1981, the first year of the 17-character VIN:
  12,176 model years of 1,209 models from 81 makes (were 8,750, 940 and 74). EPA's data starts in 1984, so
  1981 to 1983 carry 1984's models and specifications back. Old cars thin out with a scrappage taper
  (`config.FLEET_AGE`), so they no longer pile up at the first model year: 9 car-years of 1981 cars in the
  default run, against 10 a year for the next three.
- **Surnames.** Whether a wife keeps her own surname depends on the household's race and ethnicity group, at
  the Pew Research Center's 2023 rates: about 10% of white, 9% of Black, 30% of Hispanic and 14% of other
  wives, and an assumed 25% of Asian wives (Pew had too few to report). Children take their father's surname,
  or their mother's new husband's when she has remarried.
- **Identifiers.** Integer keys are the company's system counters, not row numbers (`identifiers.KEY_SYSTEMS`,
  ASSUMED). The company was founded in 2000; policy, driver, vehicle, exposure, premium transaction, agency,
  producer, statement, ledger and employee keys count from then, billing from July 2008, claims from October
  2012, quoting from March 2014, customer correspondence from January 2016 (`contact_id` is `CM` and nine
  digits) and telematics from April 2018; vendor keys are undated. Keys start far above 1, have gaps, and
  still rise with the day each record was created.
- **Real catastrophes.** Ten storms from NOAA's Storm Events Database (Chicago-area counties, 2023 to 2026:
  hail, flash floods and derechos) replace the nine fictional events (`config.CAT_EVENTS`, derived by
  `scripts/build_catastrophe_events.py`). Their date, place, peril and relative size are real; the claims and
  losses on them are simulated. None falls in 2022.
- **Claims open at the start.** The part of each opening term before 1 January 2022 is simulated as a warm-up,
  so the extract opens with open claims, case reserves and payments on 2021 accidents (287 claims in the
  default run), and at-fault claims settled before 2022 appear on the driver's record as "Company Claim
  (Before Extract)" incidents. The ledger's opening entry carries their case reserves ($1.4 million). There
  are still no accidents before 2021, so 2022 lacks payments on older accidents, which matters for bodily
  injury.
- **Records, not totals.** Derived and aggregated columns were removed, so the tables keep what an insurer's
  systems record: paid, reserved and incurred amounts and litigation flags on claims and features, earned
  exposure and premium, endorsement and return premium, counts of drivers and vehicles, the limits on
  `policy`, rate levels, premium changes, drivers' prior violations and accidents, VIN prefixes and the model
  year on exposure rows are worked out from the records instead. `docs/schema_changes.md` ("Records, not
  totals") lists every column and how to rebuild it; `validate.rebuild` does it in pandas, and the website's
  data model page gives two SQLite views (`earned`, `loss_run`). Two lookup tables are new: `coverage`
  (`coverage_code`, `coverage_name`) and `cause_of_loss` (`cause_of_loss`, `description`).
- **Case reserves from what is known (A7).** The claimants of one accident share its per-accident limit from
  what is known each day (payments to date and current estimates), rebalanced at the end of each business day
  with news, where before the room was shared using their eventual payments. Property formula reserves now sit
  near the average paid per claim, glass separately.
- **A rating plan fitted to experience (A7).** Relativities other than the filed discounts are fitted to
  three years of simulated claims experience (compound Poisson-gamma around the true expected costs), not to
  the true expected cost itself. Each level is credibility-weighted (limited fluctuation, full credibility at
  1,082 claims times one plus the squared coefficient of variation of claim size) with a bureau complement,
  the true relativity off by a random 5%, and the base rates come from the book's experience.
- **Rate change dates.** The 2023 increases take effect on 1 January and 1 July 2023 (were 1 March and 1
  September).
- **Owner-retained salvage.** A car its owner keeps after a total loss has no further losses in that term: a
  salvage car may not be driven until it is rebuilt.
- **Benchmarks (A8).** `docs/benchmarks.md` is a benchmark sheet: each figure's source, year, geography,
  units and band, and whether the generator was tuned to it, it was checked or held out, or the band is
  assumed; the spread of every validator band over five seeds; tail and joint diagnostics against CCC, S&P
  Global Mobility and the WSJ's analysis of NAIC filings; and how the case reserves ran off.
  `scripts/seed_spread.py` builds several seeds and reports each band's spread and the diagnostics,
  `scripts/reserve_diagnostics.py` reports case reserve runoff and revision rates by coverage and age, and
  `validate.py --json` writes the band figures to a file.
- **The default run** (content hash `963889a73f229de8`): loss ratios by accident year 82.2%, 77.3%, 66.3%,
  67.3% and 66.1% for 2022 to 2026, of which catastrophes 0.0%, 3.8%, 2.2%, 1.0% and 6.5%; overall 72.1%
  (was 67.4%; 71.1% to 73.8% across five seeds); annualized retention 81.6% (was 81.9%). 197,003 policy
  terms (was 198,479), 440,655 exposure rows (was 442,749), $214.3 million earned premium (was $220.8
  million), 23,135 claims (was 22,392), 40,414 features (was 39,173), 62,875 claim payments (was 60,542),
  129,559 reserve transactions (was 124,306), 879,257 bills and 890,607 receipts (were 887,706 and 896,585),
  119,541 quotes and 170,522 renewal offers. 145 checks pass on the default run and on seed 7 (content hash
  `6718177c0b52ab2e`); there were 147, but the checks on stored totals went with the totals, and new ones
  cover notices of cancellation, the daily sharing of per-accident limits and the catalog's oldest model
  years. The test suite has 74 tests (73 pass, and one needs `pyarrow`). The README,
  `docs/limitations.md`, `docs/real_data_comparison.md` and the website give the new run's figures.

## 2026-11-20, [v1.1.4](https://github.com/subwaymatch/auto-insurance-synthetic-data-test/releases/tag/v1.1.4): The website, fixes found writing its data dictionary, and American spelling ([PR #9](https://github.com/subwaymatch/auto-insurance-synthetic-data-test/pull/9), [PR #10](https://github.com/subwaymatch/auto-insurance-synthetic-data-test/pull/10))

### The Lakefront website

- A static website (`site/`, built by `site/build.py` and published to GitHub Pages by a workflow) presents the
  data: the fictional company, auto insurance and Illinois' rules for readers new to them, the data model, and
  a data dictionary for every table and column (`site/dictionary/*.toml`, with examples from `samples/`). It
  describes the data only, not a real company.
- A logo, favicon and social preview card for the fictional company (`brand/`): the wordmark in Inter with a
  sunrise over the lake in its o.

### Fixes found while writing the data dictionary

Describing every table and column turned up two errors in the published data. Both are fixed, and a new
test covers the first (64 in all).

- **Where an accident in a driver's history came from.** `driver_incident.source` and `description` called
  an at-fault accident "Company Claim (Before Extract)" whenever it fell on or after the policy's original
  inception. That also caught accidents adults brought from a previous insurer when they joined a policy
  mid-term, some of them dated 2022 or later, inside the extract, and opening-book drivers' accidents from
  before they joined the policy. An accident is now a company claim before the extract only if it happened
  while the driver was on the policy and before the start date; the rest are "Prior Carrier Report". In the
  previous default run 100 of the 2,474 accidents so labeled were not company claims: 80 were dated 2022 or
  later and 94 happened before the driver joined (most were both). Only the label changed; when each
  accident became known, and so every rating, is as it was.
- **Two SUVs in the wrong segment.** `reference/vehicle_curation.csv` had `truck` one column to the
  right for the Chevrolet Avalanche and the Hummer H3, in the vehicle class instead of the segment. Their 17
  model years in `vehicle_model_year` therefore had the vehicle class `truck`, in lower case and not one of
  the catalog's classes, and were rated in the mainstream (Avalanche) and luxury (H3) segments, although
  the curation meant both to rate with trucks, as the Hummer H1 and H2 and full-size body-on-frame SUVs do.
  Both now rate in the truck segment, with the class `Standard SUV` for the Avalanche (5.3 to 5.8 liters)
  and `Small SUV` for the H3 (3.5 to 3.7 liters), by the catalog builder's own rule for EPA's generic
  pre-2011 SUV class (4.0 liters and up is Standard). `reference/vehicle_catalogue.csv` was corrected to
  match.
- **The default run's figures were refreshed.** Segment is a rating variable, so the rating plan was
  refitted and the whole default run moved (content hash `b53e744195b60240`): 442,749 exposure rows (was
  441,637), $220.8 million earned premium (was $220.6 million), 22,392 claims (was 22,313) and an overall
  loss ratio of 67.4% (was 68.7%). Every integrity check and calibration band still holds. The README,
  `docs/limitations.md`, `docs/real_data_comparison.md` and `samples/` now give the new run's figures.

### American spelling

The data and its documentation now use American spelling throughout, as its US setting and its column
names (`installment_number`, `check_number`, `license_state`) already did.

- **Values.** `Cancelled` is now `Canceled` in `policy.policy_status` and `billing_invoice.invoice_status`,
  and in `Canceled Before Renewal` (`renewal_offer.outcome`) and `Policy Canceled`
  (`telematics_enrollment.end_reason`); `Claim Acknowledgement` is `Claim Acknowledgment` in
  `customer_contact.purpose`; and `location_truth.hazard_basis` is `observed` or `modeled` (was
  `modelled`; `reference/zip_reference.csv` follows).
- **One column renamed.** `telematics_enrollment.programme` is now `program`.
- **Nothing else moved.** Only those labels changed: every number in the default run is as before (content
  hash `7b4b15d1dcb53b95`). The README, this changelog, `docs/`, the messages `validate.py` writes to the
  validation report and the real-data comparison's output use American spelling too.

## 2026-11-19, [v1.1.3](https://github.com/subwaymatch/auto-insurance-synthetic-data-test/releases/tag/v1.1.3): A realism audit: an operating company's data ([PR #8](https://github.com/subwaymatch/auto-insurance-synthetic-data-test/pull/8))

Each subsection gives the default run after its changes; the release is content hash `a64d95db973613fa`.

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
| Non-payment cancellations spread evenly over the term from day 35 | | Three to four weeks after an installment that was never paid |
| No cash, payees or people | 24 tables | 29: bills, receipts, employees, vendors and producers, and payee, check and approver on every claim payment |

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
  receipts): installments, fees, late and returned payments, endorsements spread over the remaining
  installments, cancellation settlements, refunds and write-offs. Non-payment cancellations follow a missed
  installment (`simulate._missed_installment`), and billing notices in `customer_contact` come from the bills.
- **Commission.** `premium_transaction.commission_rate_pct` and `commission_amount`; each agency's rates and
  appointment date in `agency`; a `producer` table and `policy.producer_id`.
- **Claim payments** (`autoins/payments.py`): `employee` (desks, turnover, payment authority) and `vendor`
  (684 fictional organizations); `claim.adjuster_id`; and on `claim_payment` the payee type and name,
  vendor, method, check number, status, cleared date and approver.
- **Answer key.** `policy_truth` (stability, household risk factor) and `agency_truth` (book quality,
  retention effect).
- **Calibration.** Crash base rates up 9%, the target loss ratio at day-one cost levels 82.5% (was 77.5%:
  the fit now includes new customers' first-year claims), renewal base odds up a little, comprehensive
  severities up about 7% (like-for-like comprehensive severity had been at the bottom of its band).
- **Checks.** `validate.py` gains checks on the calendar, identifiers and their check digits, creation
  order, billing against the ledger and the cash, non-payment timing, check sequence, approval and
  employment, payees and vendors, commission and the filed discounts, and bands on the new-business gap,
  the spread across agencies, retention by channel, round settlements and the weekday pattern of crashes.
  14 new tests (56 in all). The SQLite loader keeps ZIP codes as text where a table has blanks.
- **The default run after these changes** (content hash `ee6e59c038858485`): 202,389 policy terms, 451,997
  exposure rows, 179,915 earned car-years, $181.2 million earned premium ($1,007 per car-year, was $1,028),
  19,784 claims. Frequency 1.03 to 1.24 times national and severity 0.88 to 1.03 times; expected loss ratios
  (plus catastrophes) of 80.4%, 78.2%, 68.1% and 65.4% for 2022 to 2025; an overall loss ratio of 68.6%;
  annualized retention 82.6%. Two other builds (seed 7; 20,000 policies with seed 99) pass every check.
  Generation takes about 85 seconds (was 60) and the files are 435 MB (were 245 MB), a third of it billing.

**Left as it was.** New business and quote volumes are still level through the year and across years;
physical damage premiums and take-up are still below Illinois' averages (collision and comprehensive about a
third lower per covered car; collision carried on 67% of cars against 83% statewide); claims still barely
drive customers away; there is no general ledger and no planted error or fraud. All are in
[docs/limitations.md](docs/limitations.md). (The next subsection takes up all of these but planted errors.)

### After the audit: a market, Illinois-level physical damage, claims that cost customers, a ledger, 120 agencies

**Why.** The audit above left four things undone, and a question about the agencies followed it: would a
carrier of this size really place its independent business through 44 agencies of similar size? It would
not. A regional carrier appoints many small agencies and gets most of its premium from a few.

| Finding | Before | After |
|---|---|---|
| Independent agencies few and alike | 44, averaging 224 policies in force and about $400,000 of premium a year each | 120: a median of 45 policies in force, the largest 483; in 2026 a mean of $193,000 and a median of $115,000 of premium; the largest tenth write 36% |
| Quotes level through the year and from year to year | The same every month | March a third above December; 21,277 quotes in 2022, 25,184 in 2024, 23,076 in 2026 |
| Conversion constant | 18.8% throughout | 21.9% in 2022, 17.5% in 2024, 21.2% in 2026; 21.5% in the two months before a rate increase of 5% or more, 17.0% in the two months after |
| The book grew evenly | | 20,385 policies in force at the end of 2022, 19,968 a year later, 22,650 at the end of 2026 |
| Claims barely drove customers away (policies lost per year: terms with a claim against terms without) | 19.0% against 17.9%: 1.06 times (a real portfolio: 1.45) | 25.2% against 17.9%: 1.41 times; renewal offers taken up 94.4% of the time with no claim, 87.2% with one, 79.0% with an at-fault one |
| The company almost never refused a renewal | 165 of 10,958 non-renewals | 965 of 11,462 |
| Collision premium per insured car against Illinois (2022, 2023, 2024) | About a third below | 0.87, 0.86 and 0.94 times ($332, $378, $445 against $384, $440, $473) |
| Comprehensive premium per insured car against Illinois | About a third below | 0.98, 0.87 and 0.86 times ($167, $191, $223 against $172, $219, $261) |
| Collision and comprehensive carried on fewer cars than in Illinois (82.6% and 87.5%) | 67% to 71% and 77% to 80% | 83.0% and 88.0% of 2023 car-years |
| Cars worth about half what they fetched | Average insured car $9,900 in 2024; a 2015 car with a $23,400 base price $5,700 | $14,600; that car $9,100 |
| Paid collision claims small | $4,937 on average; total losses $7,800 | $6,762; total losses $10,530, repairs $4,951 |
| Premium per car-year | $1,007 | $1,251 ($988 in 2022, $1,121 in 2023, $1,314 in 2024; Illinois' average expenditure $993, $1,153, $1,264) |
| No general ledger | Subledgers only | `gl_account` (19 accounts), `gl_journal` (4,182 lines in 1,603 monthly journals) and `agency_statement` (7,841) |

**What changed.**

- **Agencies** (`config.N_AGENCIES`, `population._agencies`). 120 independent agencies and 14 exclusive
  agents' offices, with long-tailed sizes (lognormal, wider for independents). An independent agency is
  named after its owner, two partners, its town or a trade name; an exclusive agent's office carries the
  agent's name; the owner is the agency's first producer. No two agencies share a name.
- **A market** (`autoins/market.py`, `config.MARKET_*`, `SHOPPING_*`). The number of households asking
  for a quote follows the month and the year. The market's rate level rises smoothly by the industry's
  yearly changes while the company's increases land on their effective dates, so each increase leaves the
  company dearer than its competitors until they catch up. Every quote's competitive position is spread
  around that gap, new business arrives in each month in proportion to shoppers times conversion (by
  channel), prospects who did not buy arrive as shoppers do, and the gap also nudges renewals.
- **Claims and renewals** (`config.CLAIM_RETENTION`, `simulate.evaluate_offers`). A claim reported since
  the last offer lowers the chance of renewing; an at-fault claim and a second claim lower it further. The
  underwriting review now flags two at-fault accidents, two major violations, or one of each, in three
  years (was three accidents or two majors), and half of those flagged are not renewed (was 60%). Renewal
  base odds were raised to keep overall retention where it was.
- **What a car is worth** (`config.RESIDUAL_VALUE`, `USED_CAR_VALUE_INDEX`, `truth.actual_cash_value`).
  The depreciation curve is now a table by age, flatter for older cars, and the used-car index follows the
  Manheim Used Vehicle Value Index (half as high again as before the pandemic in 2022, a third higher from
  2024) in place of an assumed 10% to 20%. A used car is never worth more than 1.15 times its base price.
- **Physical damage** (`config.COLL_SEV`, `COMP_SEV`, `BASE_RATE`, `FULL_COVERAGE`, `DROP_PD_RATE`). Collision
  repair costs up (median $6,900 for a reference car, was $5,000) with a slightly narrower spread and a total-loss
  threshold of 75% of value (was 72%); comprehensive severities up 8% to 11% and glass, theft of parts,
  vandalism, weather and other comprehensive frequencies up 5% to 20%; fewer at-fault and parked-car
  collision claims filed (86% and 70%, were 90% and 75%) and more not-at-fault ones (48%, was 42%), which
  brings subrogation to 13% of collision payments (Verisk: 14.0%; salvage 10.9% against 10.1%). Take-up of
  collision now falls more slowly with the car's age, and older cars drop it less often. Bodily injury
  severity median $21,000 (was $20,000).
- **The national comparison takes salvage and subrogation off physical damage payments**
  (`validate.BENCHMARK`). The published table does not say whether it does. Insurers report recoveries
  to statistical agents as negative paid losses, and Verisk's own report on the same data shows collision
  severity before recoveries a quarter higher than the table, with recoveries of that size. Compared before
  recoveries, as it was until now, the book had to pay too little on collision to sit on the table, which
  is why its premiums were a third below Illinois'. The reading is an assumption and is documented as one.
- **The general ledger** (`autoins/ledger.py`). Built from the published tables after everything else:
  premiums written and the change in unearned premium, cash receipts split into premium and fees through
  the bill each receipt pays, write-offs, commission expense and payment, claim payments, recoveries and
  case reserve changes, by month and underwriting company, with an opening entry the day before the extract.
  A premium transaction is booked on the later of its effective and processed dates. `agency_statement`
  is each agency's monthly commission and the day it was paid.
- **Checks.** `validate.py` gains the ledger checks (every journal balances; written and earned premium,
  cash, case reserves, commissions payable, premiums receivable, fees and write-offs tie to their
  subledgers), premiums by coverage and take-up against Illinois, and bands on seasonal quote volume,
  conversion after a rate increase, policies lost after a claim and the company's share of non-renewals.
  The agency spread is measured on agencies with 500 or more car-years. Six new tests (62 in all).
  `scripts/readme_figures.py` prints the agency, market, physical damage and ledger figures quoted here.
- **The default run after these changes** (content hash `a64d95db973613fa`): 197,979 policy terms, 441,637
  exposure rows, 176,381 earned car-years, $220.6 million earned premium, 22,313 claims. Frequency 1.08 to
  1.34 times national and severity 0.94 to 1.05 times; expected loss ratios (plus catastrophes) of 80.3%,
  78.0%, 66.6% and 64.0% for 2022 to 2025; an overall loss ratio of 68.7%; annualized retention 81.8%. Two
  other builds (seed 7; 20,000 policies with seed 99) pass every check. Generation still takes about 85
  seconds, and the files are 419 MB (were 435 MB): the three new tables add 1 MB.

**File sizes, and a Parquet release.** The data had grown to a size that is awkward to work with. Nothing
was cut. Two things make it lighter:

- **Parquet is a release format** (`scripts/release_formats.py`, `parquet_zip`; `pyarrow` pinned in
  `requirements-release.txt`), published with CSV and SQLite by the release workflow. One file per table,
  103 MB unzipped against 419 MB of CSV (70 MB to download), loading every table in half a second against
  eight. Columns are typed: whole numbers are integers even where some are blank, every `..._date` column is
  a date, ZIP codes are text. Parquet cannot declare keys, so the SQLite database remains the format that
  enforces them. The same data gives the same bytes. One new test (63 in all; it is skipped where `pyarrow`
  is not installed).
- **A smaller book for the classroom.** The README documents a 10,000-policy build (97 MB of CSV, 27 MB as
  Parquet, no table over 209,000 rows, every integrity check passing) and what it costs in noise.

**Side effects worth knowing.** Customers who stay after a claim are a selected group, so a claim one year
now predicts a claim the next less well overall (1.16 times, was 1.42), though an at-fault claim still
predicts another (1.48 times). Comprehensive claims are a larger share of all claims, which lowers the
ranking power of any frequency model that counts every claim (Gini of the premium on claim counts 0.192,
was 0.213). Collision frequency on the national comparison rose to 1.34 times national (was 1.24), near the
top of its band, because more claims clear the deductible and more old cars carry collision.

**Left as it is.** No planted errors or fraud; one market rate level for every competitor; no agency
appointments or terminations during the extract; the ledger is monthly totals without investments, other
expenses, taxes, reinsurance or a reserve for unreported claims. All are in
[docs/limitations.md](docs/limitations.md).

## 2026-11-18, [v1.1.2](https://github.com/subwaymatch/auto-insurance-synthetic-data-test/releases/tag/v1.1.2): Renewals and telematics scores decided on what was known at the time ([PR #7](https://github.com/subwaymatch/auto-insurance-synthetic-data-test/pull/7))

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
  they leave before the renewal. Fixed along the way: 4 scores of customers who had left the program were
  linked to a term that began before them.
- **Renewals decided on the offer date.** The underwriting review, the telematics offer, the renewal premium
  and the customer's decision now use only the policy as it stood on the offer date (the expiring term's
  exposure rows in force that day), records known by then and claims reported by then, with their own
  random stream. A change before the effective date still re-rates the renewal (a revised offer), but cannot
  rewrite the offer or the decision. Holding the draws fixed, the old information would have changed 315 of
  174,487 decisions and the premium of 12,013 offers.
- **New table `renewal_offer`** (179,620 rows): every renewal evaluated, renewed or not, with its offer
  date, vehicles, expiring and renewal premium, premium change, telematics opt-in, underwriting decision,
  revised offer date and outcome (renewed, not renewed by the insured, company non-renewal, canceled
  before renewal, or pending at the valuation date). The answer key's `renewal_offer_truth` has each
  offer's true acceptance probability. Customer contacts now include the offers that were declined and a
  notice for each company non-renewal. An opt-in to telematics at a renewal that was not taken is no
  longer an enrollment ending the day it began (257 were).
- **Checks.** `validate.py` checks scores against the exposure rows' driver on every day scored, the
  discount rule, and each offer against the exposure in force on its offer date and the policy terms'
  outcomes. Seven new tests, including a counterfactual one: every offer evaluated again at the end of the
  run, with the whole later history present, is the same offer and decision.
- **The default run after these fixes** (content hash `4b5bca69599df49e`): 205,742 policy terms, 460,831
  exposure rows, 184,833 earned car-years, $190.1 million earned premium, 20,343 claims, 12,298 telematics
  enrollments and 59,553 scores. Every calibration band holds: frequency 1.05 to 1.34 times national and
  severity 0.87 to 1.03 times; expected loss ratios (plus catastrophes) of 79.3%, 77.6%, 67.9% and 64.7%
  for 2022 to 2025; an overall loss ratio of 66.9%; annualized retention 83.4% (was 83.3%).

## 2026-11-17, [v1.1.1](https://github.com/subwaymatch/auto-insurance-synthetic-data-test/releases/tag/v1.1.1): Fixes from an external review, a SQLite format, 43,368 policies through 2026 ([PR #6](https://github.com/subwaymatch/auto-insurance-synthetic-data-test/pull/6))

This release moves the default run to 43,368 policies to 31 December 2026 and gives that run's figures; later
sections use that size.

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
  policy (6,741 did), and enrollments from before the extract no earlier than the policy's inception.
- **Quotes and telematics.** Every quote now offers the program; prospects who did not bind opt in at the
  same modeled rate and get the same discount. New column `quote.telematics_opt_in`.
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

### Data publishing

- **SQLite release format.** Each release now also carries the data as one SQLite database
  (`...-sqlite.zip`) with every table, a primary key on each and every foreign key declared, indexed
  and checked at build time (the build fails if any reference does not resolve). The instructor's
  database also holds every data table, so the answer key links to it. `autoins/schema.py` records the
  keys; tests check it covers every `..._id` column. The answer key's `unreported_claim` gained an
  `unreported_claim_id` so that every table has a primary key. Releases publish `csv,sqlite` by default.

## 2026-11-16, [v1.1.0](https://github.com/subwaymatch/auto-insurance-synthetic-data-test/releases/tag/v1.1.0): Real vehicles, a real-data benchmark, telematics, names and a cleaner schema ([PR #4](https://github.com/subwaymatch/auto-insurance-synthetic-data-test/pull/4), [PR #5](https://github.com/subwaymatch/auto-insurance-synthetic-data-test/pull/5))

Figures in this section are for the 51,391-policy default run (to 30 September 2026) unless stated otherwise.

### Benchmarked against a real insurer's data

- A real motor portfolio was added for comparison: "Dataset of an actual motor vehicle insurance
  portfolio" (Lledó and Pavía, Mendeley Data 2024, CC BY 4.0), 105,555 rows from what is almost
  certainly a Spanish insurer, 2015 to 2018. It is kept unmodified in `real_data/` with its license and a
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

### Telematics: a voluntary usage-based program

- **Why.** Most large US insurers now offer a usage-based ("drive safe and save" style) discount, and its
  data is among the most important new rating information. It was listed as not modeled.
- **What.** Lakefront DriveCheck is offered at new business and renewal; about a fifth to 30% of new
  customers join, and enrolled cars grow from 13% of car-years in 2022 to 25% in 2026. Members get 5%
  for joining, then a discount of up to 30% earned by a 1-100 driving score built from miles, trips,
  hard braking, rapid acceleration, speeding, phone use and night driving. Scores never raise the premium.
  About one member in ten leaves each year, more after poor scores.
- **What it teaches.** The device sees the driver's true risk and the car's true mileage, which the
  rating plan cannot. Safer drivers join (favorable selection) and monitored drivers take more care (7%
  fewer at-fault crashes), so members run an expected loss ratio of 62% against 70.5% for everyone else,
  and the discount under-reacts to the score (48% for cars earning the top band). Telematics mileage is
  above reported mileage for two cars in three.
- **New tables.** `telematics_enrollment` and `telematics_score`; each exposure row records whether it
  was rated in the program and the discount applied.

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
- New checks in `validate.py` cover the vehicle catalog (one row per model year, every vehicle pointing
  to one) and the telematics program (scores inside their enrollment and earning the published
  discount, discounts only on enrolled rows); three new tests cover them and the names.
- **Fixed:** two replacement cars joining one policy on different days of the same term were rated at
  once, so the later one could miss a claim on the earlier one. Cars are now rated in date order.

### Documentation

- `docs/limitations.md` collects every limit of the dataset in one shareable page: what it leaves out,
  where it differs from a real insurer's data, the assumptions that drive its results, how far its
  numbers can be trusted, and its appropriate and inappropriate uses.

### Data publishing

- The release workflow accepts a version typed without its leading `v` (`1.1.0` is released as
  `v1.1.0`); an earlier manual run with `1.0.1` had stopped at the input check.
- `.github/workflows/samples.yml` commits the first 100 rows of every table, the answer key and the real
  data to `samples/`, so the data can be browsed on GitHub; it reruns when the generator changes.
- `scripts/fetch_public_data.py --only vehicles` and `scripts/build_vehicle_catalogue.py` rebuild the
  vehicle catalog from its sources; `scripts/build_name_reference.py` rebuilds the name tables
  (`reference/surnames.csv`, `reference/first_names.csv`).

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
  had shown a removal dated the next day, and a removal was labeled "Total Loss" (written off by the
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
findings, modeled what the audit had left to judgment, recalibrated loss ratios against sourced industry
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
| Opening-book policies on term 1 but labeled "Renewal" | 1,946 | 0 |

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
  pointing back to the old one; a one-car policy with no replacement is canceled.
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
- **Claim expenses** are split into defense and cost containment (DCC, such as legal bills) and
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

## 2026-11-13, [v1.0.0](https://github.com/subwaymatch/auto-insurance-synthetic-data-test/releases/tag/v1.0.0): A simulated Chicago-area book ([PR #1](https://github.com/subwaymatch/auto-insurance-synthetic-data-test/pull/1))

The old dataset was replaced by a seeded simulation built on real ZIP-level data for Cook, DuPage,
Lake, Will, Kane, McHenry and Kendall counties. Commits `030d09d` (generator) and `ff2a955` (dataset
and release workflow).

### Geography and households

- 290 real ZIP codes with Census demographics (ACS 2020-2024). Crash and theft hazard for city ZIPs
  comes from City of Chicago police records; suburban hazard is modeled from income, because the city
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
  ASSUMED (judgment).
- `validate.py` reports calibration and integrity; it passed for the default seed and seeds 1, 2 and
  3, and 4 unit tests passed. The same seed gives byte-identical files.
- Not yet modeled at this stage: mid-term endorsements, drivers leaving a policy, fraud and reopened
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
