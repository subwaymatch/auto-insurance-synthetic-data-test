# Limitations of the dataset

This page collects, in one place, everything a user of the synthetic Chicago-area auto insurance data should
know about its limits: what it leaves out, where it differs from a real insurer's data, which assumptions
drive its results, how far its numbers can be trusted, and what it should and should not be used for. The
evidence behind each point is in the [README](../README.md) ("Assumptions and limits"), the
[comparison with a real portfolio](real_data_comparison.md), the output of `validate.py`, and the
assumptions in `autoins/config.py` and `autoins/telematics.py`, each marked ANCHORED (a published
figure), TUNED (set to hit an anchored target) or ASSUMED (judgment).

Figures are for the default run: seed 20250101, 43,368 policies, 1 January 2022 to 31 December 2026.

## In brief

The data is a realistic teaching dataset, checked for internal consistency: a regional insurer's Chicago-area auto
book with policies, drivers, vehicles, premiums, bills and cash, claims, payments, reserves, quotes,
telematics and a general ledger, calibrated to national frequency and severity, to the industry's loss
ratios and to Illinois' average premiums by coverage. Its people, policies and claims are simulated, and
most of its rating plan is fitted to claims simulated from the generator's own truth, so it is cleaner and
more predictable than real data. Compared with a real insurer's portfolio, its risk relationships and cost
distributions look realistic and claims cost it customers at a similar rate, but payment plan, tenure and channel carry less
risk than in the real book, its largest claims are smaller, and it has none of the errors and gaps of a real
extract. Use it to learn
methods, not to draw conclusions about real insurers, real people or real neighborhoods.

## 1. What is real and what is simulated

| Real | Simulated |
|---|---|
| ZIP codes, counties and Census demographics (ACS 2020-2024) | Every person, household, policy, premium, claim and payment |
| Chicago police crash and vehicle-theft counts behind the hazard indices, and by day behind the loss calendar | The insurer ("Lakefront"), its agencies, producers, offices, staff and vendors |
| The catastrophes: ten storms from NOAA's Storm Events Database, with their dates, places, perils and relative sizes | The claims and losses each storm causes |
| Vehicle makes, models and model years (EPA), and how common each is (Chicago crash records) | Which household owns which vehicle, its use, mileage and coverages |
| Name frequencies (Census 2010 surnames, Social Security first names) | Which name each driver has, and each household's race and ethnicity group |
| Calibration targets: national frequency and severity (Triple-I / ISO), US and Illinois loss ratios, Illinois' average premiums and physical damage take-up (NAIC), used-car prices (Manheim), the market's rate changes, published rates for moves, marriage, divorce, mortality, licensing, report lags | Everything those targets are applied to |

No record describes a real person, policy or claim. Identifiers are fictional and cannot be matched to
anything real: policy, claim, quote, invoice and check numbers follow this dataset's own formats; VINs carry
a valid check digit but begin with `0`, which no manufacturer uses; license numbers are masked and are not
computed as Illinois computes real ones; vendor and agency names are made up, and any resemblance to a real
business is accidental; vehicle symbols are this dataset's own scales.

## 2. What the dataset leaves out

| Not in the data | Why it matters | Where real insurers hold it |
|---|---|---|
| Claims from accidents before the terms in force on 1 January 2022 began (the part of those terms before that day is simulated, as a warm-up), and payments on them | Calendar-year paid and incurred figures for the whole company are a little low in 2022; bodily injury in 2022 is not held to the national benchmark | Claim systems |
| Third-party claimants as people who can be followed across claims | No claimant-level fraud or repeat-claimant analysis | Claim systems |
| Reinstatements after a lapse; billing accounts spanning several policies | A canceled policy never comes back; each term is billed on its own | Billing systems |
| Bills and receipts from before 2022, except for terms in the data | Receivables cannot be aged for the whole company before the start date | Billing systems |
| A journal entry for each transaction; investments, expenses other than commission, taxes, reinsurance and a reserve for unreported claims | The general ledger is monthly totals of the premium, cash, commission and claim subledgers, with assumed opening cash and surplus; it supports reconciliation and roll-forwards, not a full set of financial statements or journal-entry testing | Accounting systems |
| Agency appointments and terminations; agency statements netted from month to month | All 134 agencies are there throughout; a statement with more return commission than commission is repaid by the agency | Agency management systems |
| License plates | Vehicles are identified by VIN and unit number, as policies are written; plates would appear in claim files | Claim systems |
| Planted errors, irregularities or fraud | Audit tests (duplicate payments, payments over authority, gaps in check numbers) all come back clean | Real data has them |
| Named competitors, advertising and marketing spend | Quotes and new business follow an assumed season and one market rate level; nothing explains them further | Marketing systems |
| Excluded drivers; separate mailing and garaging addresses | Every listed driver is rated; the garaging ZIP is the only address | Policy systems |
| Uninsured motorist property damage; custom equipment and loan or lease gap cover | The coverage menu is narrower than Illinois' | Policy systems |
| Medical diagnosis codes, recovery reserves, fraud outcomes | Only referrals to the special investigations unit, not proven fraud | Claim systems; Medicare reporting |
| Claim handling history: reassignments and status changes | Each claim shows its current adjuster only; status changes show only as open, close and reopen dates | Claim systems |
| Quote revisions, underwriting referrals and declines | One quote per prospect, bound or not; a renewal has one offer (`renewal_offer`) and at most one revision after a household change | Rating and policy systems |
| Trip-level telematics data | Only per-period summaries and scores | Telematics vendors |
| Reinsurance | No ceded premium or recoveries | Ceded statistical data |
| Edit errors, out-of-sequence bookings, missing values | See section 6 | Every production system |

## 3. Where it differs from a real insurer's data

`docs/real_data_comparison.md` compares the book with a real motor portfolio (Lledó and Pavía, Mendeley
Data 2024, CC BY 4.0; almost certainly a Spanish insurer, 2015 to 2018). The two markets, currencies and
products differ, so only shapes are compared, not levels. Where a fair comparison is possible the synthetic
data looks realistic: drivers under 25 claim 1.37 times the book average in the real data and 1.33 times
in the synthetic, newly licensed drivers 1.37 and 1.36 times, urban vehicles 1.14 and 1.14 times, and
claim costs and premiums spread alike. These differences remain:

1. **Tenure protects less.** Long-standing customers are safer than new ones, but less than in the real book
   (0.69 times the claim frequency after ten years in the real data, 0.89 in the synthetic, other things
   equal). Claims do now cost customers as in the real book: a real contract with a claim is 1.45 times as
   likely to end as one without, a synthetic one 1.44 times, and 944 of 11,743 synthetic non-renewals are the
   company's decision.
2. **Payment plan carries less risk.** Real half-yearly payers claim 1.61 times as often as annual payers,
   other things equal; synthetic installment payers 1.08 times.
3. **The largest claims are smaller.** The costliest 1% of claim-years make up 24% of real claim cost and
   16% of synthetic. US policy limits explain part of this; the synthetic large-loss tail is not
   checked against US data (no US figure on comparable terms is published; see [benchmarks.md](benchmarks.md)).
4. **Channel makes less difference.** Real broker business runs 12% above average frequency; synthetic
   independent-agent business runs 3% above, and 6% above exclusive-agent business with other things equal.
5. **Shared factors carry less predictive signal.** A simple model on the factors both books record ranks
   held-out real claims better (Gini 0.22) than synthetic ones (0.115), because of points 1, 2 and 4 and
   because 30% of synthetic claims are comprehensive (glass, theft, weather), which the driver's
   characteristics barely predict.

The real portfolio has defects of its own (its claim counts do not change from one year to the next as
they should), so it cannot benchmark claim-count dispersion, claim persistence or the frequency level.
Those synthetic figures are plausible but unverified.

## 4. Assumptions that shape the results

**Geography and hazard**

- Chicago's crash data covers the city only. Suburban hazard is modeled from the city's income
  gradient at an assumed lower level, not observed.
- City crash rates vary about sevenfold across ZIP codes in police records; an exponent narrows that to a
  range typical of rating territories.
- Each ZIP has a random hazard component the territories cannot see.
- Catastrophes are ten real storms in the seven counties from NOAA's Storm Events Database (2023 to 2026:
  hail, flash floods and derechos). Their date, place, peril and relative size are real; how likely a car
  near a storm's center is to be hit is assumed, and the claims and losses are simulated
  (`scripts/build_catastrophe_events.py`). NOAA publishes with a lag of a few months, so the latest storms
  may be missing.

**Pricing**

- The plan's discounts and surcharges (multi-car, multi-policy, homeowner, paid in full, prior insurance,
  tenure, good student, married) are filed as round percentages typical of filed plans, not taken from any
  carrier's. Everything else is fitted to three years of claims simulated around the true expected losses,
  credibility-weighted with a bureau relativity (the truth off by a random 5%), then distorted on purpose
  (young drivers under-priced, mileage under-used). A real carrier's experience is older than the rates it
  sets, trended and developed with estimates, so this plan is still cleaner and more adequate than a real one.
- What the insurer cannot see is assumed: each household's stability (which lowers claims, raises retention
  and drives homeownership, bundling, prior insurance, the payment plan and tenure), a higher claim rate for
  new customers that fades over two or three years, and each channel's and agency's book quality. The
  new-customer effect is sized to a published gap between new and renewal loss ratios (13 points across 25
  books; Wu and Lin, CAS 2009); the rest is judgment.
- The rate schedule is stylized: +48% cumulative between April 2022 and March 2025, then a 2% cut in
  June 2026.
- The market is one number: a single rate level stands for every competitor (rising smoothly by the
  industry's published yearly changes), every quote's competitive position is spread around the gap
  between it and the company's own level, and shopping follows an assumed season and year. How strongly
  conversion and renewals respond to that gap is assumed.
- What a claim does to a renewal is assumed and sized to one real portfolio from another market: a claim
  since the last offer lowers the chance of renewing, an at-fault or second claim more. The underwriting
  rule for company non-renewals (two at-fault accidents, two major violations, or one of each, in three
  years; half of those flagged) is assumed.
- Telematics discounts are not offset in the base rates, so later years run a little above the industry
  loss ratio path.
- Income, insurance score, payment plan and multi-policy status stay fixed for a policy's life; liability
  limits change only at renewal, and homeowner status only with a move.
- A renewal is decided once, on its offer date. A revised offer after a household change re-rates the renewal
  but the customer does not decide again, and coverage changes the customer makes at renewal (deductibles,
  limits) are not offered back as a new quote, so the written premium can differ from `renewal_premium`.

**Claims**

- Claims before the start date go back one warm-up year only: the part of each opening term before 1 January
  2022 is simulated, so the extract opens with the claims then open, and earlier terms' claims survive only as
  incidents on the drivers' records (see section 2).
- A car its owner keeps after a total loss has no further losses in that term (a salvage car may not be driven
  until rebuilt) and loses physical damage cover at the next renewal; rebuilding it is not modeled.
- `insured_fault_pct` describes the accident only: settlements are not reduced for the claimant's own
  share of fault, and fault is not allocated among several parties.
- Report lags rest on one published study of one insurer (1996 to 2005); lags beyond a year are probably
  understated, so treat the late-reported (IBNR) tail as indicative.
- Claimants are not people: a liability or injury feature has a claimant number within its claim only.
- Payment patterns, reserve review cycles and timing (rating lead times, driving-record posting lags,
  replacement delays, endorsement processing) are judgment calls.
- Case reserves are capped so that paid plus reserve stays within each limit. Where an accident's
  injury claimants share a per-accident limit, the room is shared from what is known each day (payments to
  date and current estimates), rebalanced at the end of each business day with news
  (`autoins/claims.py`, `_share_accident_limit`). Estimates themselves are the generator's draws around the
  eventual outcome (log-normal error that shrinks as a claim matures), not an adjuster's reasoning from the
  file, so their errors are better behaved than real ones: `scripts/reserve_diagnostics.py` shows the
  runoff (docs/benchmarks.md).

**Operations**

- Loss days follow Chicago's daily crash and vehicle-theft counts: police reports for the city, not
  insurance claims for the metro area. Hold-over of weekend notices, the weekday mix of quotes and
  effective dates, and loss times for causes other than crashes and thefts are assumed. Losses from other
  causes follow monthly seasonality only, and nothing bunches at month or quarter ends.
- Billing is stylized: two monthly plans and paid in full, fixed fees, late payment and returned drafts at
  assumed rates that depend on household stability, balances after cancellation collected or written off at
  assumed rates. A cancellation for non-payment follows a billed, unpaid installment by three to four weeks
  and a notice of cancellation by at least ten days (215 ILCS 5/143.15); a missed bank draft is attempted
  and returned first.
  The simulation picks the installment a household will not pay when the term begins; when a later change
  leaves nothing on it, the household is recorded as canceling at its own request on that day instead (17
  terms in the default run) rather than having its cancellation moved later.
- Agencies are stylized: 120 independent and 14 exclusive, with assumed long-tailed sizes, commission
  schedules, hidden book quality and hold on customers, and names built from the area's surnames and towns
  (any resemblance to a real agency is accidental).
- The general ledger is a monthly summary built from the published tables. Its opening cash and surplus
  are assumed, it has no investments, expenses other than commission, taxes, reinsurance or reserve for
  unreported claims, acquisition costs are expensed as written, and fees are income when collected. One
  receivable account nets premium not yet collected against premium paid ahead and refunds on their way.
- Claim payment detail is stylized: who is paid (shop, person, lienholder, other insurer), by check or
  electronically, how fast it clears, staffing, turnover and payment authority are assumed. A financed car's
  loan balance at a total loss is an assumed share of the settlement, not an amortized loan, and the vehicle
  table shows only each car's latest ownership (loans paid off at renewal are not dated). Vendors are
  fictional and their shares of the work are assumed. None of this changes an amount or a date.
- Injury settlements are rounded to negotiated-looking figures by an assumed rule.

**Policies and households**

- Mover, divorce, marriage, mortality, licensing and vehicle-ownership rates come from public data; how
  often households add or sell cars, how often a leaving driver takes a car, and the shapes by age are
  judgment calls.

**Vehicles**

- The catalog runs from model year 1981 to 2026. EPA's data starts in 1984, so for 1981 to 1983 the models
  EPA lists in 1984 are carried back with their 1984 specifications: models dropped before 1984 are missing.
  Older cars thin out by an assumed scrappage curve.
- How common each make, model and model year is comes from vehicles in Chicago crashes. Crashes
  over-represent cars that are driven more and crash more, and city cars over suburban ones (a density
  tilt for pickups partly corrects this). The crash records' pick list lacks some models and mislabels
  others, so some shares rest on a sales prior.
- Prices are approximate base prices in 2024 dollars (about 900 curated, the rest estimated from class,
  make and engine), used only to scale repair and total-loss costs and to set rating bands and symbols. A
  model year's engine, drive and body are its most common configuration.
- Vehicle ages are tuned to Chicago's roads (about nine years in force); the US fleet average is older
  (about 12.6 years in 2024).
- What a car is worth is modeled: its model year's base price, a depreciation curve of assumed shape, and
  the Manheim used-vehicle index by year. Trim, mileage and condition are not modeled, so two cars of one
  model and year are worth the same. Values were raised by about half after the realism audit (they had
  been about half what such cars fetched in 2022 to 2024), which is what brought physical damage premiums
  up to Illinois' level.
- Collision and comprehensive take-up is tuned to Illinois' (83% and 88% of insured cars); how it falls
  with the car's age and varies with income and score is assumed.
- Vehicle symbols are this dataset's own scales, not ISO's licensed ones.

**Telematics**

- Take-up, discounts, drop-out, the score formula and the 7% behavior effect are ASSUMED, shaped on
  published descriptions of US programs, not fitted to any insurer's data.
- A member who leaves mid-term keeps the discount, and the behavior effect, until the next renewal. A
  car added mid-term is monitored only from the next renewal.
- A score reads only the driver assigned to the car (its rated driver): other household drivers who use
  the car are not seen. When the assigned driver changes, the period is split, and the car's discount
  averages the parts by days.

**Names and race**

- Each household's race and ethnicity group is drawn from its ZIP code's Census mix, not from any
  person. Surnames and first names are drawn for that group from published frequencies; the first-name
  weights come from mortgage applicants (Tzioumis 2018), re-based to the 2010 population but not to
  each birth cohort, and about a third of names given since 2000 are not in that source and get the
  population's mix. How often a wife keeps her own surname depends on the household's group, at the Pew
  Research Center's (2023) rates (the 25% for Asian wives is assumed); children take their father's
  surname, or their mother's new husband's.
- The group is used for nothing but names. Risk, prices and claims never depend on it.

## 5. How far to trust the numbers

- **Calibration is national and statewide.** Frequency and severity are held to Triple-I / ISO national
  figures, approximately on their published definitions (paid claims, a $500 deductible for physical damage,
  wind and water excluded from comprehensive; the source does not publish how it counts claims with several
  payments), loss ratios to the US and Illinois path, and premiums by coverage and physical damage take-up
  to Illinois' averages. Nothing is checked against a Chicago benchmark or a single carrier's experience,
  and results by subgroup, how variables depend on each other, large-loss tails and local geography are
  assumed or tuned, not validated. [benchmarks.md](benchmarks.md) gives each benchmark's source, year,
  geography and units, whether the generator was tuned to it or it was held out, how far each figure moves
  across five seeds, a few tail and joint diagnostics, and how the case reserves ran off.
- **Physical damage rests on one reading of the benchmark.** The national table does not say whether
  salvage and subrogation come off collision and comprehensive payments. They are taken off here, because
  insurers report recoveries as negative paid losses and because Verisk's own report on the same data shows
  collision severity before recoveries about a quarter higher, with recoveries of that size (see the
  README). On that reading collision severity is 0.91 times national in the default run (0.87 to 0.92
  across five seeds), frequency 1.36 times, and premiums per insured car 14% below Illinois' for collision,
  12% below for comprehensive and 5% above for liability. If the table is in fact before recoveries,
  physical damage payments here are about a quarter too high against it, and Illinois' premiums could not then be matched
  at industry loss ratios. The sources do not settle it.
- **Collision claims are frequent and often total losses.** Collision frequency runs 36% above
  national on the like-for-like comparison in the default run (28% to 36% across five seeds; an urban
  book), near the top of the band `validate.py` allows. About 31% of paid collision claims are total
  losses, and 27% of paid collision and comprehensive claims with glass left out, against 22% to 23% of
  all appraisals nationally (CCC); 81% of total losses are on cars seven or more model years old (CCC:
  72%), and the average car written off is worth about $10,500 (CCC: $13,400 to $13,700). CCC also counts
  appraisals that are not paid and third-party ones, which are more often repairable, so part of the gap
  is definition; the rest is the damage model, in which an old car totals more easily than real ones seem
  to (see [benchmarks.md](benchmarks.md)).
- **Claim luck is real.** A year of this book has about 210 to 260 paid bodily injury claims, and one
  standard deviation of their total is 1.7 to 2.6 loss-ratio points. In the default run each full year
  comes within 4% of its expected loss ratio, without catastrophes (2023: 73.5% against 74.7%; 2025: 66.3%
  against 63.9%); across five seeds a year's actual runs 0.94 to 1.08 times its expected. Other seeds and
  sizes give other years their luck; `validate.py` holds each year's actual, without catastrophes, to 0.85
  to 1.15 times its expected.
- **The last year is immature.** 2026 is the least developed year: young injury claims are reserved low,
  and claims not yet reported are missing (they are in the answer key).
- **Single-year severities move.** About 300 paid bodily injury claims and 700 comprehensive
  claims a year fall in the national comparison, so single-year severities move by 10% or more by chance.
- **Segment differences are expected values.** New business against renewals, channels, payment plans and
  agencies differ in their expected loss ratios (from the answer key). Actual loss ratios of small segments
  move far more with claim luck than with book quality, and most agencies are small: half of the 120
  independent agencies have 48 or fewer policies in force, and only 62 agencies have 500 car-years in the
  whole extract.
- **A claim predicts the next one weakly overall.** Vehicles with a claim one year have 1.27 times the
  claim frequency the next, because many claims are comprehensive and because customers with claims,
  at-fault ones most of all, are the likeliest to leave. A car with an at-fault claim is 1.6 times as
  likely to have another.
- **Smaller builds are noisier.** A 10,000-policy build passes every integrity check and its ledger ties,
  but has about 5,000 claims: loss ratios, small segments and single-year figures move more, some agencies
  have no customers, and `validate.py` reports calibration misses as warnings below 20,000 policies.
- **Seed and size matter.** The same seed and size give byte-identical files, but a different seed or
  policy count changes every random draw: compare methods across seeds before reading much into one
  figure.
- **Counting rules differ.** Glass claims under full glass cover carry no deductible and are counted; the
  national table's own counting rules are not published.

## 6. The data is too clean

A real extract has duplicate and stub rows, dates out of order, text such as `NA` in numeric fields,
zeros standing for missing values, fields taken at extraction time that leak later information into
earlier rows, and records that do not reconcile. The real portfolio in `real_data/` has all of these. The
synthetic tables have none of these on purpose, and `validate.py` checks a long list of rules every record
must follow. Passing those checks shows the rules hold, not that no other inconsistency exists: an external
review found several that the checks then missed (see [review_response.md](review_response.md)), and each
now has a check of its own. The tables teach analysis, not data cleaning; pair them with the real
portfolio, or degrade a copy, for cleaning exercises.

The same holds for audit analytics. Bills reconcile with the premium ledger and the cash to the cent, check
numbers run without a gap, every payment is approved within authority by someone employed that day, no
vendor is paid twice for one thing, and every journal balances and ties to its subledger. The data supports the tests, and every test comes back clean; to teach
exception finding, plant exceptions in a copy.

## 7. Appropriate and inappropriate uses

**Good uses**

- Teaching and practicing ratemaking (exposure, earned premium, relativities, GLMs, rate adequacy),
  reserving (paid and incurred triangles, IBNR, reserve development), claims analytics, retention and
  quote conversion, telematics pricing and the separation of selection from behavior.
- Accounting and audit analytics: written, earned and unearned premium; billed premium, cash, receivables
  by age, refunds and write-offs; commission and agency statements; paid and incurred losses and reserve
  roll-forwards; reconciling each subledger to the general ledger by month and company, and calendar-year
  against accident-year results; and tests on claim payments (check sequence, outstanding and voided
  checks, approval against authority, vendor concentration, Benford's law).
- Business analytics: profitability and retention by channel, agency, payment plan and tenure; quote
  volumes and conversion through the season and after rate changes; retention after a claim; what each
  discount is worth; how concentrated the agency force is.
- SQL and data-modeling exercises on a realistic, multi-table insurance schema.
- Fairness auditing: estimating race and ethnicity from surname and address (BISG) and testing prices
  for disparate impact, checked against the answer key.
- Testing analytical code and pipelines on data of realistic size and structure.

**Not appropriate**

- Conclusions about real insurers, their prices, profitability or practices: the insurer and its rating
  plan are fictional, and the plan is fitted to claims simulated from the generator's own truth.
- Conclusions about real people or real Chicago neighborhoods beyond the public crash, theft and Census
  data the hazards are built on. ZIP-level patterns in premiums are planted from that data and say nothing
  about individuals, causes or actuarial fairness.
- Benchmarking a real carrier, or evidence in a legal, regulatory or rate-filing setting.
- Using names, or the race and ethnicity group in the answer key, as rating or decision variables. A name
  stands in for race and ethnicity, which is why it must never be one.

**Handling the answer key.** It holds the truth behind the data (expected losses, hidden driver risk, true
mileage, synthetic race and ethnicity, unreported claims). Give students the data release, not the answer
key or this repository, from which the answer key can be regenerated.
