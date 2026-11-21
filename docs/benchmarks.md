# Benchmarks: what the data is compared with, and how far to trust each comparison

Every figure the generator is held to or compared with, where it comes from, what it counts, and whether the
generator was tuned to it or it was held out. Then how much each figure moves from seed to seed, a few tail and
joint diagnostics, and how the case reserves ran off. The figures in sections 2 to 4 are from five builds at the
default size (43,368 policies ever written; seeds 20250101, 7, 11, 23 and 42) and can be reproduced with:

```bash
python scripts/seed_spread.py --work /tmp/seeds --markdown
python scripts/reserve_diagnostics.py /tmp/seeds/seed_* --markdown
```

**Tuned** means a generator parameter was chosen so the book lands on the figure, so agreement is by
construction and is not evidence of realism. **Checked** means the figure was not used to set any parameter;
agreement is (weak) evidence. **Diagnostic** means there is no band: the figure is reported, with an outside
value where one is published on comparable terms. **Assumed** means the band is a judgment with no single
published source. None of the sources is a Chicago or a single-carrier figure, and the book is one metropolitan
area, so even a checked figure only says the data is in a plausible range.

## 1. The benchmark sheet

| Figure | Source, year | Geography | Units and inclusion rules | Band (validate.py) | Use |
|---|---|---|---|---|---|
| Claim frequency and severity: bodily injury, property damage, collision, comprehensive | Triple-I, "Private Passenger Auto Insurance Losses, 2015-2024" (source: ISO, a Verisk business); 2022-2024 | US, less Massachusetts, most no-fault states (BI) and Michigan and New Jersey (PD) | Paid claims per 100 earned car-years and paid per claim, calendar year, all limits combined. BI and PD severity include loss adjustment expense; collision and comprehensive at a $500 deductible, comprehensive without wind and water and with glass. Salvage and subrogation taken off physical damage (an ASSUMED reading: the table does not say). Counting rules (per claimant or per accident) unpublished | Tuning bands on the whole book; like for like, frequency 0.85 to 1.45 and severity 0.85 to 1.15 times national | Tuned (peril rates, severity medians and trend) |
| Loss ratio by accident year | APCIA (2022) and S&P Global (2023-2025), US private auto; Illinois Department of Insurance market share reports | US and Illinois | Incurred losses without LAE over earned premium, direct; catastrophes included. Compared with the answer key's expected loss ratio plus the year's catastrophes, so claim luck is left out | About 5 points either side of the US and Illinois figures | Tuned (target loss ratio, rate changes) |
| Actual against expected loss ratio by accident year | The answer key | This book | Actual incurred loss ratio without catastrophes over its expected one | 0.85 to 1.15 | Checked (consistency of the simulation, not realism) |
| Average premium per insured car-year: liability, collision, comprehensive | NAIC Auto Insurance Database, average premium supplement, 2024 edition; 2022-2024 | Illinois | Written premium per written car-year of each coverage | 0.90 to 1.30 (liability), 0.80 to 1.20 (collision), 0.75 to 1.20 (comprehensive) | Checked: premiums follow from the losses and the target loss ratio, not from these |
| Collision and comprehensive take-up | NAIC Auto Insurance Database, 2023 | Illinois | Cars with the coverage per liability car-year: 82.6% and 87.5% | ±4 points | Tuned (`FULL_COVERAGE`, `P_COMP_ONLY`) |
| Annualized policy retention | none | - | Ended terms lost to cancellation or non-renewal, annualized | 78% to 90% | Assumed |
| Drivers with no violation, no at-fault accident in 3 years | none | - | Share of drivers on the policy | 78% to 90%; 86% to 95% | Assumed |
| New business expected loss ratio above renewals | Wu and Lin, CAS E-Forum, Winter 2009 (13 points across 25 books) | US | Expected (answer key) loss ratio, points | 5 to 16 | Tuned (new-customer effect) |
| Terms with a claim lost more often than terms without | Lledó and Pavía, real portfolio (1.45 times; docs/real_data_comparison.md) | Spain | Policies lost per year, ratio | 1.20 to 1.70 | Tuned (claim effect on renewal) |
| Crashes on Thursdays and Fridays against Sundays and Mondays | City of Chicago Traffic Crashes (about 1.16) | Chicago | Crash claims by weekday | 1.05 to 1.28 | Tuned (loss days are drawn from the real crash days) |
| Quotes in February to April against October to December; conversion after a rate increase; company share of non-renewals; renewal of exclusive-agent customers above direct; agency spread of expected loss ratio; whole-dollar injury settlements; first month's exposure | none | - | See validate.py | See section 2 | Assumed |
| Claims closed without payment | Wall Street Journal analysis of insurer filings with the NAIC, 2025 | US | Share of closed claims: about 45% of liability and medical, just under 25% of collision and comprehensive | none | Tuned, then diagnostic (section 3) |
| Total-loss share; value and age of total losses | CCC Intelligent Solutions, Crash Course 2025 and 2026 | US | Share of appraised vehicle claims (first and third party, glass apart, paid or not): 22.1% in 2024, 22.8% in 2025. Average total-loss vehicle value $13,400 to $13,700 (2024-25); 72% of total-loss valuations on cars seven or more years old | none | Value informed the residual values; the rest held out (section 3) |
| Average age of cars | S&P Global Mobility: 12.6 years (2024), 12.8 (2025) | US light vehicles in operation | Registered vehicles, not insured ones | none | Held out (section 3); the fleet is tuned to Chicago crash records instead |
| Vehicle ages in force | City of Chicago Traffic Crashes - Vehicles, 2021-2025 | Chicago | Personal vehicles in crashes: mean age 8.9 to 9.8 years, 41% to 48% ten or more years old | none | Tuned (`FLEET_AGE`) |
| Claim report lags | CAS Loss Simulation Model Working Party (one insurer, 1996-2005) | US | Bodily injury report lags | none | Tuned |
| Attorney involvement | Insurance Research Council, 2026 | US | 57% of BI claimants in 2022 | none | Tuned |

## 2. How much the validator's figures move between seeds

| figure | mean | range | band | seeds inside |
|---|--:|--:|--:|--:|
| BI frequency per 100 car-years (tuning band) | 0.77 | 0.75 to 0.81 | 0.70 to 1.15 | 5 of 5 |
| BI average paid loss (tuning band) | 25,236 | 24,216 to 26,301 | 20,000 to 30,000 | 5 of 5 |
| PD frequency per 100 car-years (tuning band) | 2.72 | 2.66 to 2.79 | 2.40 to 3.40 | 5 of 5 |
| PD average paid loss (tuning band) | 6,824 | 6,643 to 6,897 | 5,800 to 7,400 | 5 of 5 |
| COLL frequency per 100 car-years (tuning band) | 5.35 | 5.29 to 5.42 | 4.00 to 6.20 | 5 of 5 |
| COLL average paid loss (tuning band) | 6,463 | 6,417 to 6,561 | 5,400 to 7,400 | 5 of 5 |
| COMP frequency per 100 car-years (tuning band) | 6.12 | 6.06 to 6.17 | 4.60 to 6.80 | 5 of 5 |
| COMP average paid loss (tuning band) | 2,911 | 2,855 to 2,956 | 2,200 to 3,400 | 5 of 5 |
| non-catastrophe incurred vs answer-key expected (all coverages) | 1.00 | 0.98 to 1.01 | 0.93 to 1.07 | 5 of 5 |
| BI frequency relative to national, like for like | 1.08 | 1.00 to 1.11 | 0.85 to 1.45 | 5 of 5 |
| BI severity relative to national, like for like | 0.95 | 0.88 to 1.01 | 0.85 to 1.15 | 5 of 5 |
| PD frequency relative to national, like for like | 1.11 | 1.07 to 1.13 | 0.85 to 1.45 | 5 of 5 |
| PD severity relative to national, like for like | 1.04 | 1.00 to 1.06 | 0.85 to 1.15 | 5 of 5 |
| COLL frequency relative to national, like for like | 1.32 | 1.28 to 1.36 | 0.85 to 1.45 | 5 of 5 |
| COLL severity relative to national, like for like | 0.90 | 0.87 to 0.92 | 0.85 to 1.15 | 5 of 5 |
| COMP frequency relative to national, like for like | 1.22 | 1.19 to 1.26 | 0.85 to 1.45 | 5 of 5 |
| COMP severity relative to national, like for like | 1.02 | 1.00 to 1.06 | 0.85 to 1.15 | 5 of 5 |
| liability premium per insured car-year relative to Illinois, 2022-2024 | 1.03 | 1.00 to 1.05 | 0.90 to 1.30 | 5 of 5 |
| collision premium per insured car-year relative to Illinois, 2022-2024 | 0.87 | 0.83 to 0.88 | 0.80 to 1.20 | 5 of 5 |
| comprehensive premium per insured car-year relative to Illinois, 2022-2024 | 0.90 | 0.88 to 0.93 | 0.75 to 1.20 | 5 of 5 |
| 2022 loss ratio excluding catastrophes relative to its expected | 1.00 | 0.98 to 1.01 | 0.85 to 1.15 | 5 of 5 |
| 2023 loss ratio excluding catastrophes relative to its expected | 0.99 | 0.97 to 1.02 | 0.85 to 1.15 | 5 of 5 |
| 2024 loss ratio excluding catastrophes relative to its expected | 1.03 | 0.97 to 1.08 | 0.85 to 1.15 | 5 of 5 |
| 2025 loss ratio excluding catastrophes relative to its expected | 1.01 | 0.94 to 1.06 | 0.85 to 1.15 | 5 of 5 |
| 2022 expected loss ratio (answer key) plus catastrophes vs industry | 80.7% | 79.5% to 82.1% | 74.0% to 85.0% | 5 of 5 |
| 2023 expected loss ratio (answer key) plus catastrophes vs industry | 77.8% | 76.3% to 78.9% | 68.0% to 80.0% | 5 of 5 |
| 2024 expected loss ratio (answer key) plus catastrophes vs industry | 67.5% | 66.1% to 68.4% | 59.0% to 70.0% | 5 of 5 |
| 2025 expected loss ratio (answer key) plus catastrophes vs industry | 64.4% | 63.3% to 65.2% | 55.0% to 67.0% | 5 of 5 |
| overall loss ratio | 72.4% | 71.1% to 73.8% | 62.0% to 76.0% | 5 of 5 |
| first month's exposure relative to the first year's average | 0.97 | 0.97 to 0.98 | 0.85 to 1.15 | 5 of 5 |
| share of drivers with no violation in 3 years | 88.5% | 88.3% to 88.7% | 78.0% to 90.0% | 5 of 5 |
| share of drivers with no at-fault accident in 3 years | 93.4% | 93.2% to 93.6% | 86.0% to 95.0% | 5 of 5 |
| annualized policy retention | 81.6% | 81.5% to 81.8% | 78.0% to 90.0% | 5 of 5 |
| new business expected loss ratio above renewals (points) | 9.22 | 8.38 to 9.85 | 5.00 to 16.00 | 5 of 5 |
| spread of expected loss ratio across agencies with 500+ car-years (90th less 10th percentile, points) | 15.68 | 14.94 to 16.76 | 6.00 to 25.00 | 5 of 5 |
| quotes in February to April relative to October to December | 1.20 | 1.19 to 1.21 | 1.08 to 1.40 | 5 of 5 |
| conversion after a rate increase relative to before it | 0.81 | 0.79 to 0.84 | 0.60 to 0.92 | 5 of 5 |
| terms with a claim end the policy more often than terms without (ratio) | 1.41 | 1.39 to 1.42 | 1.20 to 1.70 | 5 of 5 |
| share of non-renewals that are the company's decision | 8.0% | 7.5% to 8.6% | 3.0% to 15.0% | 5 of 5 |
| renewal rate of exclusive-agent customers above direct customers (points) | 4.02 | 3.48 to 4.46 | 1.00 to 8.00 | 5 of 5 |
| share of paid bodily injury settlements that are whole-dollar amounts | 86.7% | 85.3% to 88.4% | 75.0% to 95.0% | 5 of 5 |
| crashes on Thursdays and Fridays relative to Sundays and Mondays | 1.16 | 1.12 to 1.18 | 1.05 to 1.28 | 5 of 5 |

Every integrity check passes on every seed. The calibration figures that matter most for analysis are the
frequencies, severities and loss ratios; their spread across seeds is claim luck on a book of this size, and it
is the yardstick for any difference a case study finds between segments of one build.

## 3. Tail and joint diagnostics

| figure | mean | range | published | source |
|---|--:|--:|--:|--:|
| total-loss share, paid collision and comprehensive claims (glass apart) | 27.3% | 26.6% to 27.8% | 22.1% (2024), 22.8% (2025) | CCC Crash Course, US: all appraised vehicle claims |
| total-loss share, paid collision claims | 31.2% | 30.6% to 31.6% | - | no US figure for collision alone |
| total losses on cars 7+ model years old | 81.0% | 80.5% to 81.3% | 72% | CCC Crash Course, US, 2025 |
| average value of cars paid as total losses ($) | 10,472 | 10,390 to 10,638 | 13,400 to 13,700 | CCC Crash Course, US, 2024-25 (used in setting values) |
| closed liability and medical payments claims without payment | 42.7% | 42.0% to 43.3% | about 45% | WSJ analysis of NAIC filings, 2025 (tuned) |
| closed collision and comprehensive claims without payment | 15.5% | 15.3% to 15.9% | just under 25% | WSJ analysis of NAIC filings, 2025 (tuned) |
| closed collision claims without payment | 22.8% | 22.4% to 23.5% | - | (collision alone) |
| average age of insured cars in force, last full year (years) | 10.66 | 10.61 to 10.72 | 12.6 (2024), 12.8 (2025) | S&P Global Mobility, US light vehicles in operation |
| share of claim cost in the costliest 1% of risk rows with a claim | 15.8% | 15.4% to 16.4% | - | no US figure on these terms |
| coefficient of variation of claim cost per risk row with a claim | 2.07 | 2.00 to 2.15 | - | no US figure on these terms |
| bodily injury claimants paid the full per-person limit | 20.3% | 19.3% to 21.3% | - | no public US figure |
| bodily injury paid per claimant, median ($) | 16,937 | 16,500 to 17,500 | - | no public US figure |
| bodily injury paid per claimant, 90th percentile ($) | 50,490 | 50,000 to 52,450 | - | no public US figure |
| bodily injury paid per claimant, 99th percentile ($) | 125,715 | 100,000 to 148,300 | - | no public US figure |

What they show:

- **Total losses are too common, and on older, cheaper cars.** About 27% of paid collision and comprehensive
  claims (glass apart) are total losses, against 22.1% to 22.8% of CCC's appraisals; 81% of total losses are
  on cars seven or more model years old (CCC: 72%), and the average car written off is worth about $10,500
  (CCC: $13,400 to $13,700). CCC's count also includes third-party property damage appraisals and claims
  appraised but not paid, which are more often repairable, so part of the gap is definition. The rest is the
  generator's damage model: a repair bill depends on the car's original price, not its age, while its value
  falls with age, so an old car totals more easily than real older cars seem to. It was not tuned away here:
  collision severity and frequency are held to the national table, and a new damage model would need its own
  evidence on repair cost by vehicle age.
- **The insured fleet is younger than all registered cars** (10.7 years against 12.6 to 12.8): the fleet is
  tuned to the cars in Chicago crashes, which are younger than the national stock, and insured cars are
  younger than registered ones, which include cars off the road.
- **Physical damage claims close without payment less often than the industry's** (about 15% of collision
  and comprehensive, against just under 25%; 23% of collision alone). Comprehensive claims here are mostly glass,
  theft and hail, which are rarely denied. Liability and medical claims match (43% against about 45%).
- **The tail is thinner than a real book's.** The costliest 1% of risk rows with a claim carry about 16% of
  claim cost, and the coefficient of variation of cost per row is about 2.1. The Spanish portfolio in
  docs/real_data_comparison.md gives 24% and 4.4, but its limits and products differ, so it is not a target.
  One in five paid injury claimants is paid the full per-person limit, which reflects the many 25/50 policies
  in a Chicago book; there is no published US rate to compare with.

## 4. How the case reserves ran off

At each year-end from December 2021 to December 2025, every loss feature with a case reserve is followed to its
ultimate paid loss in the answer key. "Later paid / reserve" sums over the features (above 1.00, the reserves
were short); the percentiles are of single features; "within 2x" is the share whose later payments fell
between half and double their reserve. Ranges are across the five seeds.

| coverage | age | features | later paid / reserve | 10th pct | median | 90th pct | within 2x |
|---|---|--:|--:|--:|--:|--:|--:|
| BI | 0-3 months | 880 | 1.52 (1.39-1.60) | 0.00 (0.00-0.00) | 0.00 (0.00-0.00) | 2.85 (2.61-3.11) | 16% (14%-17%) |
| BI | 3-12 months | 976 | 1.12 (1.08-1.15) | 0.00 (0.00-0.00) | 0.90 (0.83-0.95) | 1.85 (1.70-1.92) | 51% (49%-52%) |
| BI | 1-2 years | 251 | 1.16 (1.14-1.19) | 0.13 (0.00-0.66) | 1.12 (1.08-1.14) | 1.71 (1.63-1.78) | 83% (80%-88%) |
| BI | over 2 years | 58 | 1.15 (1.08-1.20) | 0.72 (0.00-0.95) | 1.11 (1.06-1.17) | 1.53 (1.45-1.65) | 92% (83%-96%) |
| BI | all ages | 2,165 | 1.21 (1.18-1.24) | 0.00 (0.00-0.00) | 0.59 (0.41-0.81) | 2.04 (1.87-2.16) | 41% (39%-43%) |
| PD | 0-3 months | 440 | 1.17 (1.06-1.29) | 0.00 (0.00-0.00) | 0.86 (0.81-0.94) | 2.36 (2.03-2.59) | 49% (45%-53%) |
| PD | all ages | 452 | 1.17 (1.06-1.28) | 0.00 (0.00-0.00) | 0.87 (0.80-0.94) | 2.33 (2.02-2.58) | 50% (46%-54%) |
| UM | 0-3 months | 50 | 1.66 (1.20-1.96) | 0.03 (0.00-0.15) | 0.93 (0.63-1.20) | 4.81 (3.16-5.90) | 37% (32%-43%) |
| UM | 3-12 months | 68 | 1.24 (1.14-1.35) | 0.32 (0.00-0.74) | 1.13 (1.05-1.23) | 1.91 (1.67-2.23) | 80% (72%-87%) |
| UM | 1-2 years | 23 | 1.11 (1.03-1.19) | 0.79 (0.63-0.94) | 1.10 (1.03-1.18) | 1.68 (1.39-2.04) | 87% (79%-92%) |
| UM | all ages | 148 | 1.29 (1.24-1.39) | 0.08 (0.00-0.19) | 1.10 (1.03-1.18) | 2.43 (2.21-2.67) | 67% (64%-70%) |
| MED | 0-3 months | 84 | 1.09 (0.99-1.15) | 0.17 (0.04-0.36) | 1.00 (1.00-1.00) | 2.29 (1.79-2.60) | 63% (54%-70%) |
| MED | 3-12 months | 27 | 1.08 (1.03-1.14) | 0.34 (0.16-0.68) | 1.02 (0.99-1.05) | 1.60 (1.31-2.06) | 77% (67%-84%) |
| MED | all ages | 111 | 1.09 (1.01-1.13) | 0.21 (0.09-0.35) | 1.00 (1.00-1.00) | 2.15 (1.61-2.50) | 66% (60%-72%) |
| COLL | 0-3 months | 565 | 1.04 (0.98-1.08) | 0.00 (0.00-0.00) | 0.93 (0.90-0.99) | 2.55 (2.46-2.62) | 49% (47%-52%) |
| COLL | all ages | 582 | 1.04 (0.98-1.08) | 0.00 (0.00-0.00) | 0.94 (0.90-0.99) | 2.51 (2.43-2.59) | 50% (47%-53%) |
| COMP | 0-3 months | 304 | 1.13 (1.09-1.18) | 0.00 (0.00-0.00) | 0.70 (0.61-0.82) | 2.58 (2.37-2.85) | 43% (41%-44%) |
| COMP | all ages | 311 | 1.13 (1.08-1.18) | 0.00 (0.00-0.00) | 0.70 (0.61-0.82) | 2.55 (2.36-2.84) | 43% (42%-44%) |
| RENT | 0-3 months | 325 | 0.91 (0.86-0.94) | 0.25 (0.20-0.29) | 0.93 (0.85-0.97) | 1.59 (1.44-1.73) | 74% (69%-78%) |
| RENT | all ages | 333 | 0.91 (0.87-0.94) | 0.24 (0.16-0.29) | 0.93 (0.88-0.97) | 1.58 (1.43-1.70) | 74% (69%-77%) |
| TOW | 0-3 months | 39 | 0.89 (0.86-0.94) | 0.45 (0.00-0.72) | 1.00 (1.00-1.00) | 1.00 (1.00-1.00) | 90% (85%-93%) |
| TOW | all ages | 39 | 0.89 (0.86-0.94) | 0.45 (0.00-0.72) | 1.00 (1.00-1.00) | 1.00 (1.00-1.00) | 90% (85%-93%) |

Reserve reviews raise the reserve about as often as they lower it, at every age. Property claims open at a
year-end later paid within about 20% of what was reserved for them in aggregate (collision 1.04, comprehensive
1.13, property damage 1.17); rental reserves are a little redundant. Young injury reserves are short, by design: early injury
estimates average about 86% of ultimate and many injury claimants present or grow later, so bodily injury
incurred develops upward as in industry triangles. Individual features scatter widely (most claims either
close for nothing or settle well away from the reserve), which is what case reserves look like. They are,
though, the generator's draws around the eventual outcome rather than an adjuster's reading of a file, so their
errors are better behaved than real ones: no reserve is ever set far off for a reason a later fact reveals.

Reserve reviews, by age at the review: the share raising and the share lowering the reserve (cells with
fewer than 20 reviews left out).

| coverage | age | reviews | up | down |
|---|---|--:|--:|--:|
| BI | 0-3 months | 1,680 | 54% (52%-56%) | 46% (44%-48%) |
| BI | 3-12 months | 4,238 | 55% (55%-56%) | 45% (44%-45%) |
| BI | 1-2 years | 1,104 | 57% (56%-58%) | 43% (42%-44%) |
| BI | over 2 years | 269 | 58% (54%-61%) | 42% (39%-46%) |
| PD | 0-3 months | 2,771 | 47% (46%-48%) | 53% (52%-54%) |
| PD | 3-12 months | 62 | 47% (44%-52%) | 53% (48%-56%) |
| UM | 0-3 months | 101 | 48% (45%-50%) | 52% (50%-55%) |
| UM | 3-12 months | 299 | 54% (51%-57%) | 46% (43%-49%) |
| UM | 1-2 years | 101 | 55% (47%-59%) | 45% (41%-53%) |
| UM | over 2 years | 30 | 59% (47%-70%) | 41% (30%-53%) |
| MED | 0-3 months | 261 | 38% (32%-42%) | 62% (58%-68%) |
| MED | 3-12 months | 87 | 57% (51%-64%) | 43% (36%-49%) |
| COLL | 0-3 months | 2,917 | 52% (51%-54%) | 48% (46%-49%) |
| COLL | 3-12 months | 39 | 57% (50%-67%) | 43% (33%-50%) |
| COMP | 0-3 months | 1,213 | 54% (52%-54%) | 46% (46%-48%) |
| RENT | 0-3 months | 2,191 | 41% (40%-41%) | 59% (59%-60%) |
| RENT | 3-12 months | 46 | 55% (48%-67%) | 45% (33%-52%) |

## 5. What is not benchmarked

Severity percentiles, limit-hit rates and the concentration of cost in the largest claims have no published US
figure on terms this data can match; section 3 reports them without a target. How variables depend on each other
(tenure and channel, age and mileage, value and total loss, claims and retention) is assumed in the generator and
reported, not validated, apart from the few relationships above. Model performance on held-out policies or later
years is left to the case studies: the data supports both splits (policy and date keys on every row).
