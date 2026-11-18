# Limitations of the dataset

This page collects, in one place, everything a user of the synthetic Chicago-area auto insurance data should
know about its limits: what it leaves out, where it differs from a real insurer's data, which assumptions
drive its results, how far its numbers can be trusted, and what it should and should not be used for. The
evidence behind each point is in the [README](../README.md) ("Assumptions and limits"), the
[comparison with a real portfolio](real_data_comparison.md), the output of `validate.py`, and the
assumptions in `autoins/config.py` and `autoins/telematics.py`, each marked ANCHORED (a published
figure), TUNED (set to hit an anchored target) or ASSUMED (judgement).

Figures are for the default run: seed 20250101, 43,368 policies, 1 January 2022 to 31 December 2026.

## In brief

The data is a realistic teaching dataset, checked for internal consistency: a regional insurer's Chicago-area auto
book with policies, drivers, vehicles, premiums, claims, reserves, quotes and telematics, calibrated to
national frequency and severity and to the industry's loss ratios. Its people, policies and claims are
simulated, and its rating plan is fitted to the simulator's own truth, so it is cleaner and more
predictable than real data. Compared with a real insurer's portfolio, its risk relationships and cost
distributions look realistic, but claims barely drive customers away, payment plan carries no risk, its
largest claims are smaller, and it has none of the errors and gaps of a real extract. Use it to learn
methods, not to draw conclusions about real insurers, real people or real neighbourhoods.

## 1. What is real and what is simulated

| Real | Simulated |
|---|---|
| ZIP codes, counties and Census demographics (ACS 2020-2024) | Every person, household, policy, premium, claim and payment |
| Chicago police crash and vehicle-theft counts behind the hazard indices | The insurer ("Lakefront"), its agencies, offices and catastrophes |
| Vehicle makes, models and model years (EPA), and how common each is (Chicago crash records) | Which household owns which vehicle, its use, mileage and coverages |
| Name frequencies (Census 2010 surnames, Social Security first names) | Which name each driver has, and each household's race and ethnicity group |
| Calibration targets: national frequency and severity (Triple-I / ISO), US and Illinois loss ratios, published rates for moves, marriage, divorce, mortality, licensing, report lags | Everything those targets are applied to |

No record describes a real person, policy or claim. Identifiers (policy numbers, VIN prefixes, vehicle
symbols) are fictional and cannot be matched to anything real.

## 2. What the dataset leaves out

| Not in the data | Why it matters | Where real insurers hold it |
|---|---|---|
| Claims open on the start date, and payments on accidents before 2022 | Calendar-year paid and incurred figures for the whole company are too low in 2022; bodily injury in 2022 is not held to the national benchmark | Claim systems |
| Third-party claimants as people who can be followed across claims | No claimant-level fraud or repeat-claimant analysis | Claim systems |
| Billing and instalment events, reinstatements after a lapse | Non-payment cancellations appear, but not the billing trail behind them | Billing systems |
| Renewal offers that were declined, with the offered premium | Price elasticity can be studied only on accepted renewals and on new-business quotes | Policy systems |
| Excluded drivers; separate mailing and garaging addresses | Every listed driver is rated; the garaging ZIP is the only address | Policy systems |
| Uninsured motorist property damage; custom equipment and loan or lease gap cover | The coverage menu is narrower than Illinois' | Policy systems |
| Medical diagnosis codes, recovery reserves, fraud outcomes | Only referrals to the special investigations unit, not proven fraud | Claim systems; Medicare reporting |
| Claim handling history: adjuster assignments, status changes, and who each payment went to | No adjuster workload or payee analysis; status changes show only as open, close and reopen dates | Claim systems |
| Quote revisions, underwriting referrals and declines | One quote per prospect, bound or not; only renewals show a revision (`offer_date` before `rating_date`) | Rating and policy systems |
| Trip-level telematics data | Only per-period summaries and scores | Telematics vendors |
| Reinsurance | No ceded premium or recoveries | Ceded statistical data |
| Edit errors, out-of-sequence bookings, missing values | See section 6 | Every production system |

## 3. Where it differs from a real insurer's data

`docs/real_data_comparison.md` compares the book with a real motor portfolio (Lledó and Pavía, Mendeley
Data 2024, CC BY 4.0; almost certainly a Spanish insurer, 2015 to 2018). The two markets, currencies and
products differ, so only shapes are compared, not levels. Where a fair comparison is possible the synthetic
data looks realistic: drivers under 25 claim 1.37 times the book average in the real data and 1.29 times
in the synthetic, newly licensed drivers 1.37 and 1.38 times, urban vehicles 1.14 and 1.13 times, and
claim costs and premiums spread alike. These differences remain:

1. **Claims barely drive customers away.** A real contract with a claim is 1.45 times as likely to end as
   one without; a synthetic one 1.12 times. Few synthetic non-renewals are the company's decision (121 of
   12,230), so long-standing customers are not safer than new ones, as they are in real books (0.69 times
   the claim frequency after ten years in the real data, 0.98 in the synthetic).
2. **Payment plan carries no risk.** Real half-yearly payers claim 1.61 times as often as annual payers,
   other things equal; synthetic instalment payers 1.03 times.
3. **The largest claims are smaller.** The costliest 1% of claim-years make up 24% of real claim cost and
   16% of synthetic. US policy limits explain part of this; the synthetic large-loss tail is not
   checked against US data.
4. **Channel makes no difference.** Real broker business runs 12% above average frequency; synthetic
   business is the same in every channel.
5. **Shared factors carry less predictive signal.** A simple model on the factors both books record ranks
   held-out real claims better (Gini 0.22) than synthetic ones (0.16), largely because of points 1, 2 and 4.

The real portfolio has defects of its own (its claim counts do not change from one year to the next as
they should), so it cannot benchmark claim-count dispersion, claim persistence or the frequency level.
Those synthetic figures are plausible but unverified.

## 4. Assumptions that shape the results

**Geography and hazard**

- Chicago's crash data covers the city only. Suburban hazard is modelled from the city's income
  gradient at an assumed lower level, not observed.
- City crash rates vary about sevenfold across ZIP codes in police records; an exponent narrows that to a
  range typical of rating territories.
- Each ZIP has a random hazard component the territories cannot see; catastrophes (hail, wind, flood)
  are fictional events with plausible dates and footprints.

**Pricing**

- The rating plan is fitted directly to the simulator's true expected losses, then distorted on purpose
  (young drivers under-priced, mileage under-used). A real carrier estimates costs from noisy past losses
  with filing and implementation lags, so this plan is cleaner and more adequate than a real one.
- The rate schedule is stylised: +48% cumulative between April 2022 and March 2025, then a 2% cut in
  June 2026.
- Telematics discounts are not offset in the base rates, so later years run a little above the industry
  loss ratio path.
- Income, insurance score, payment plan and multi-policy status stay fixed for a policy's life; liability
  limits change only at renewal, and homeowner status only with a move.

**Claims**

- No claims from before the start date (see section 2).
- `insured_fault_pct` describes the accident only: settlements are not reduced for the claimant's own
  share of fault, and fault is not allocated among several parties.
- Report lags rest on one published study of one insurer (1996 to 2005); lags beyond a year are probably
  understated, so treat the late-reported (IBNR) tail as indicative.
- Claimants are not people: a liability or injury feature has a claimant number within its claim only.
- Payment patterns, reserve review cycles and timing (rating lead times, driving-record posting lags,
  replacement delays, endorsement processing) are judgement calls.

**Policies and households**

- Mover, divorce, marriage, mortality, licensing and vehicle-ownership rates come from public data; how
  often households add or sell cars, how often a leaving driver takes a car, and the shapes by age are
  judgement calls.

**Vehicles**

- How common each make, model and model year is comes from vehicles in Chicago crashes. Crashes
  over-represent cars that are driven more and crash more, and city cars over suburban ones (a density
  tilt for pickups partly corrects this). The crash records' pick list lacks some models and mislabels
  others, so some shares rest on a sales prior.
- Prices are approximate base prices in 2024 dollars (about 900 curated, the rest estimated from class,
  make and engine), used only to scale repair and total-loss costs and to set rating bands and symbols. A
  model year's engine, drive and body are its most common configuration.
- Vehicle ages are tuned to Chicago's roads (about ten years in force); the US fleet average is a little
  older (about 12.6 years in 2024).
- Vehicle symbols are this dataset's own scales, not ISO's licensed ones.

**Telematics**

- Take-up, discounts, drop-out, the score formula and the 7% behaviour effect are ASSUMED, shaped on
  published descriptions of US programmes, not fitted to any insurer's data.
- A member who leaves mid-term keeps the discount, and the behaviour effect, until the next renewal. A
  car added mid-term is monitored only from the next renewal.

**Names and race**

- Each household's race and ethnicity group is drawn from its ZIP code's Census mix, not from any
  person. Surnames and first names are drawn for that group from published frequencies; the first-name
  weights come from mortgage applicants (Tzioumis 2018), re-based to the 2010 population but not to
  each birth cohort, and about a third of names given since 2000 are not in that source and get the
  population's mix.
- The group is used for nothing but names. Risk, prices and claims never depend on it.

## 5. How far to trust the numbers

- **Calibration is national.** Frequency and severity are held to Triple-I / ISO national figures,
  approximately on their published definitions (paid claims, a $500 deductible for physical damage, wind and
  water excluded from comprehensive; the source does not publish how it counts claims with several
  payments), and loss ratios to the US and Illinois path. Nothing is checked against a Chicago
  benchmark or a single carrier's experience, and results by subgroup, how variables depend on each other,
  large-loss tails and local geography are assumed or tuned, not validated.
- **Claim luck is real.** A year of this book has about 250 paid bodily injury claims, and one standard
  deviation of their total is 1.5 to 3 loss-ratio points. In the default run 2022 comes in below its
  expected loss ratio (75.1% against 78.8%, both without catastrophes) and 2023 above it (78.1% against
  75.2%). Other seeds and sizes give other years their luck; `validate.py` holds each year's actual,
  without catastrophes, to 0.85 to 1.15 times its expected.
- **The last year is immature.** 2026 is the least developed year: young injury claims are reserved low,
  and claims not yet reported are missing (they are in the answer key).
- **Single-year severities move.** About 300 paid bodily injury claims and 600 comprehensive claims a year
  fall in the national comparison, so single-year severities move by 10% or more by chance.
- **Physical damage severity runs low.** Like-for-like comprehensive severity has come in at 0.81 to 0.88
  times national across recent runs, and collision at 0.86 to 0.92 (an older city fleet, whose claims are
  capped by modest vehicle values). In the default run they are 0.85 and 0.86, at the bottom of
  `validate.py`'s 0.85 to 1.15 band, so a different seed or size can fall just outside it.
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

## 7. Appropriate and inappropriate uses

**Good uses**

- Teaching and practising ratemaking (exposure, earned premium, relativities, GLMs, rate adequacy),
  reserving (paid and incurred triangles, IBNR, reserve development), claims analytics, retention and
  quote conversion, telematics pricing and the separation of selection from behaviour.
- SQL and data-modelling exercises on a realistic, multi-table insurance schema.
- Fairness auditing: estimating race and ethnicity from surname and address (BISG) and testing prices
  for disparate impact, checked against the answer key.
- Testing analytical code and pipelines on data of realistic size and structure.

**Not appropriate**

- Conclusions about real insurers, their prices, profitability or practices: the insurer and its rating
  plan are fictional, and the plan is fitted to the simulator's own truth.
- Conclusions about real people or real Chicago neighbourhoods beyond the public crash, theft and Census
  data the hazards are built on. ZIP-level patterns in premiums are planted from that data and say nothing
  about individuals, causes or actuarial fairness.
- Benchmarking a real carrier, or evidence in a legal, regulatory or rate-filing setting.
- Using names, or the race and ethnicity group in the answer key, as rating or decision variables. A name
  stands in for race and ethnicity, which is why it must never be one.

**Handling the answer key.** It holds the truth behind the data (expected losses, hidden driver risk, true
mileage, synthetic race and ethnicity, unreported claims). Give students the data release, not the answer
key or this repository, from which the answer key can be regenerated.
