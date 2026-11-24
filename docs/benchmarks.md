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
| BI frequency per 100 car-years (tuning band) | 0.75 | 0.74 to 0.79 | 0.70 to 1.15 | 5 of 5 |
| BI average paid loss (tuning band) | 25,227 | 24,631 to 25,553 | 20,000 to 30,000 | 5 of 5 |
| PD frequency per 100 car-years (tuning band) | 2.66 | 2.61 to 2.68 | 2.40 to 3.40 | 5 of 5 |
| PD average paid loss (tuning band) | 6,816 | 6,601 to 7,007 | 5,800 to 7,400 | 5 of 5 |
| COLL frequency per 100 car-years (tuning band) | 5.28 | 5.10 to 5.42 | 4.00 to 6.20 | 5 of 5 |
| COLL average paid loss (tuning band) | 6,470 | 6,408 to 6,524 | 5,400 to 7,400 | 5 of 5 |
| COMP frequency per 100 car-years (tuning band) | 6.12 | 6.07 to 6.17 | 4.60 to 6.80 | 5 of 5 |
| COMP average paid loss (tuning band) | 2,897 | 2,835 to 2,943 | 2,200 to 3,400 | 5 of 5 |
| non-catastrophe incurred vs answer-key expected (all coverages) | 1.00 | 0.98 to 1.01 | 0.93 to 1.07 | 5 of 5 |
| BI frequency relative to national, like for like | 1.07 | 0.99 to 1.14 | 0.85 to 1.45 | 5 of 5 |
| BI severity relative to national, like for like | 0.97 | 0.94 to 1.03 | 0.85 to 1.15 | 5 of 5 |
| PD frequency relative to national, like for like | 1.08 | 1.05 to 1.10 | 0.85 to 1.45 | 5 of 5 |
| PD severity relative to national, like for like | 1.03 | 1.01 to 1.05 | 0.85 to 1.15 | 5 of 5 |
| COLL frequency relative to national, like for like | 1.29 | 1.22 to 1.32 | 0.85 to 1.45 | 5 of 5 |
| COLL severity relative to national, like for like | 0.91 | 0.88 to 0.93 | 0.85 to 1.15 | 5 of 5 |
| COMP frequency relative to national, like for like | 1.23 | 1.18 to 1.27 | 0.85 to 1.45 | 5 of 5 |
| COMP severity relative to national, like for like | 1.02 | 0.98 to 1.07 | 0.85 to 1.15 | 5 of 5 |
| liability premium per insured car-year relative to Illinois, 2022-2024 | 1.03 | 1.00 to 1.05 | 0.90 to 1.30 | 5 of 5 |
| collision premium per insured car-year relative to Illinois, 2022-2024 | 0.85 | 0.82 to 0.87 | 0.80 to 1.20 | 5 of 5 |
| comprehensive premium per insured car-year relative to Illinois, 2022-2024 | 0.91 | 0.89 to 0.94 | 0.75 to 1.20 | 5 of 5 |
| 2022 loss ratio excluding catastrophes relative to its expected | 1.01 | 0.97 to 1.04 | 0.85 to 1.15 | 5 of 5 |
| 2023 loss ratio excluding catastrophes relative to its expected | 1.02 | 0.96 to 1.06 | 0.85 to 1.15 | 5 of 5 |
| 2024 loss ratio excluding catastrophes relative to its expected | 0.98 | 0.95 to 1.02 | 0.85 to 1.15 | 5 of 5 |
| 2025 loss ratio excluding catastrophes relative to its expected | 1.01 | 0.98 to 1.04 | 0.85 to 1.15 | 5 of 5 |
| 2022 expected loss ratio (answer key) plus catastrophes vs industry | 80.2% | 79.4% to 81.0% | 74.0% to 85.0% | 5 of 5 |
| 2023 expected loss ratio (answer key) plus catastrophes vs industry | 77.3% | 76.5% to 78.4% | 68.0% to 80.0% | 5 of 5 |
| 2024 expected loss ratio (answer key) plus catastrophes vs industry | 67.0% | 66.1% to 67.8% | 59.0% to 70.0% | 5 of 5 |
| 2025 expected loss ratio (answer key) plus catastrophes vs industry | 63.4% | 63.1% to 64.0% | 55.0% to 67.0% | 5 of 5 |
| overall loss ratio | 70.5% | 69.5% to 71.5% | 62.0% to 76.0% | 5 of 5 |
| first month's exposure relative to the first year's average | 0.98 | 0.97 to 0.98 | 0.85 to 1.15 | 5 of 5 |
| share of drivers with no violation in 3 years | 88.4% | 88.3% to 88.5% | 78.0% to 90.0% | 5 of 5 |
| share of drivers with no at-fault accident in 3 years | 93.3% | 93.2% to 93.6% | 86.0% to 95.0% | 5 of 5 |
| annualized policy retention | 81.2% | 81.0% to 81.4% | 78.0% to 90.0% | 5 of 5 |
| new business expected loss ratio above renewals (points) | 9.79 | 9.17 to 10.40 | 5.00 to 16.00 | 5 of 5 |
| spread of expected loss ratio across agencies with 500+ car-years (90th less 10th percentile, points) | 15.25 | 14.88 to 15.75 | 6.00 to 25.00 | 5 of 5 |
| quotes in February to April relative to October to December | 1.20 | 1.20 to 1.21 | 1.08 to 1.40 | 5 of 5 |
| conversion after a rate increase relative to before it | 0.81 | 0.78 to 0.84 | 0.60 to 0.92 | 5 of 5 |
| terms with a claim end the policy more often than terms without (ratio) | 1.54 | 1.53 to 1.56 | 1.20 to 1.70 | 5 of 5 |
| share of non-renewals that are the company's decision | 7.7% | 7.4% to 8.0% | 3.0% to 15.0% | 5 of 5 |
| renewal rate of exclusive-agent customers above direct customers (points) | 3.94 | 3.47 to 4.34 | 1.00 to 8.00 | 5 of 5 |
| share of paid bodily injury settlements that are whole-dollar amounts | 85.7% | 84.7% to 87.6% | 75.0% to 95.0% | 5 of 5 |
| crashes on Thursdays and Fridays relative to Sundays and Mondays | 1.14 | 1.08 to 1.18 | 1.05 to 1.28 | 5 of 5 |

Every integrity check passes on every seed. The calibration figures that matter most for analysis are the
frequencies, severities and loss ratios; their spread across seeds is claim luck on a book of this size, and it
is the yardstick for any difference a case study finds between segments of one build.

## 3. Tail and joint diagnostics

| figure | mean | range | published | source |
|---|--:|--:|--:|--:|
| total-loss share, paid collision and comprehensive claims (glass apart) | 27.8% | 27.6% to 27.9% | 22.1% (2024), 22.8% (2025) | CCC Crash Course, US: all appraised vehicle claims |
| total-loss share, paid collision claims | 31.9% | 31.6% to 32.1% | - | no US figure for collision alone |
| total losses on cars 7+ model years old | 79.5% | 78.6% to 80.0% | 72% | CCC Crash Course, US, 2025 |
| average value of cars paid as total losses ($) | 10,535 | 10,414 to 10,641 | 13,400 to 13,700 | CCC Crash Course, US, 2024-25 (used in setting values) |
| closed liability and medical payments claims without payment | 43.0% | 42.5% to 43.5% | about 45% | WSJ analysis of NAIC filings, 2025 (tuned) |
| closed collision and comprehensive claims without payment | 15.2% | 15.1% to 15.4% | just under 25% | WSJ analysis of NAIC filings, 2025 (tuned) |
| closed collision claims without payment | 22.5% | 21.9% to 23.3% | - | (collision alone) |
| average age of insured cars in force, last full year (years) | 10.64 | 10.60 to 10.67 | 12.6 (2024), 12.8 (2025) | S&P Global Mobility, US light vehicles in operation |
| share of claim cost in the costliest 1% of risk rows with a claim | 16.7% | 16.2% to 17.0% | - | no US figure on these terms |
| coefficient of variation of claim cost per risk row with a claim | 2.18 | 2.15 to 2.22 | - | no US figure on these terms |
| bodily injury claimants paid the full per-person limit | 19.9% | 17.4% to 22.4% | - | no public US figure |
| bodily injury paid per claimant, median ($) | 17,364 | 17,000 to 17,750 | - | no public US figure |
| bodily injury paid per claimant, 90th percentile ($) | 51,007 | 50,000 to 53,783 | - | no public US figure |
| bodily injury paid per claimant, 99th percentile ($) | 125,063 | 110,212 to 144,131 | - | no public US figure |

What they show:

- **Total losses are too common, and on older, cheaper cars.** About 28% of paid collision and comprehensive
  claims (glass apart) are total losses, against 22.1% to 22.8% of CCC's appraisals; 80% of total losses are
  on cars seven or more model years old (CCC: 72%), and the average car written off is worth about $10,500
  (CCC: $13,400 to $13,700). CCC's count also includes third-party property damage appraisals and claims
  appraised but not paid, which are more often repairable, so part of the gap is definition. The rest is the
  generator's damage model: a repair bill depends mostly on the car's original price, falling only mildly with
  its age (1.2% a year, to no less than 80% of a new car's), while its value falls much faster, so an old car
  totals more easily than real older cars seem to. It was not tuned away here:
  collision severity and frequency are held to the national table, and a new damage model would need its own
  evidence on repair cost by vehicle age.
- **The insured fleet is younger than all registered cars** (10.6 years against 12.6 to 12.8): the fleet is
  tuned to the cars in Chicago crashes, which are younger than the national stock, and insured cars are
  younger than registered ones, which include cars off the road.
- **Physical damage claims close without payment less often than the industry's** (about 15% of collision
  and comprehensive, against just under 25%; about 22% of collision alone). Comprehensive claims here are mostly glass,
  theft and hail, which are rarely denied. Liability and medical claims match (43% against about 45%).
- **The tail is thinner than a real book's.** The costliest 1% of risk rows with a claim carry about 17% of
  claim cost, and the coefficient of variation of cost per row is about 2.2. The Spanish portfolio in
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
| BI | 0-3 months | 864 | 1.65 (1.54-1.75) | 0.00 (0.00-0.00) | 0.00 (0.00-0.00) | 3.08 (2.91-3.36) | 16% (13%-17%) |
| BI | 3-12 months | 904 | 1.10 (1.09-1.15) | 0.00 (0.00-0.00) | 0.85 (0.80-0.91) | 1.83 (1.74-1.94) | 50% (49%-51%) |
| BI | 1-2 years | 241 | 1.15 (1.11-1.18) | 0.11 (0.00-0.57) | 1.10 (1.09-1.13) | 1.76 (1.72-1.88) | 82% (80%-83%) |
| BI | over 2 years | 60 | 1.16 (1.08-1.28) | 0.85 (0.78-0.92) | 1.13 (1.04-1.23) | 1.61 (1.41-1.89) | 94% (90%-96%) |
| BI | all ages | 2,068 | 1.23 (1.21-1.26) | 0.00 (0.00-0.00) | 0.61 (0.48-0.78) | 2.09 (1.98-2.22) | 41% (40%-42%) |
| PD | 0-3 months | 393 | 1.15 (1.10-1.20) | 0.00 (0.00-0.00) | 0.89 (0.79-0.92) | 2.23 (2.04-2.38) | 55% (52%-58%) |
| PD | 3-12 months | 16 | 0.95 (0.86-1.01) | 0.18 (0.00-0.47) | 0.91 (0.79-1.02) | 1.18 (1.08-1.31) | 75% (67%-80%) |
| PD | 1-2 years | 1 | 1.10 (1.10-1.10) | 1.10 (1.10-1.10) | 1.10 (1.10-1.10) | 1.10 (1.10-1.10) | 100% (100%-100%) |
| PD | all ages | 410 | 1.15 (1.10-1.20) | 0.00 (0.00-0.00) | 0.89 (0.79-0.93) | 2.18 (1.94-2.38) | 56% (53%-59%) |
| UM | 0-3 months | 51 | 1.80 (1.40-2.43) | 0.01 (0.00-0.04) | 0.95 (0.67-1.20) | 5.55 (4.24-6.51) | 30% (26%-38%) |
| UM | 3-12 months | 73 | 1.24 (1.20-1.29) | 0.67 (0.58-0.76) | 1.20 (1.11-1.26) | 2.13 (1.77-2.33) | 80% (78%-84%) |
| UM | 1-2 years | 29 | 1.19 (1.09-1.27) | 0.84 (0.75-0.94) | 1.13 (1.09-1.17) | 1.63 (1.35-1.89) | 93% (90%-100%) |
| UM | over 2 years | 6 | 1.15 (0.99-1.43) | 0.90 (0.60-1.09) | 1.09 (1.00-1.34) | 1.39 (1.11-1.98) | 97% (83%-100%) |
| UM | all ages | 159 | 1.31 (1.28-1.36) | 0.19 (0.07-0.29) | 1.14 (1.11-1.18) | 2.61 (2.18-2.90) | 67% (63%-72%) |
| MED | 0-3 months | 81 | 1.14 (1.02-1.29) | 0.30 (0.25-0.36) | 1.00 (1.00-1.01) | 2.71 (2.07-3.78) | 69% (63%-74%) |
| MED | 3-12 months | 26 | 1.10 (0.99-1.27) | 0.75 (0.63-0.80) | 1.04 (1.00-1.11) | 1.73 (1.24-2.64) | 86% (71%-93%) |
| MED | 1-2 years | 1 | 1.00 (1.00-1.00) | 1.00 (1.00-1.00) | 1.00 (1.00-1.00) | 1.00 (1.00-1.00) | 100% (100%-100%) |
| MED | all ages | 107 | 1.13 (1.03-1.25) | 0.36 (0.26-0.40) | 1.01 (1.00-1.03) | 2.32 (1.91-2.77) | 73% (70%-78%) |
| COLL | 0-3 months | 516 | 1.04 (0.92-1.12) | 0.00 (0.00-0.00) | 0.99 (0.97-1.00) | 2.60 (2.07-2.98) | 52% (48%-54%) |
| COLL | 3-12 months | 19 | 1.00 (0.96-1.03) | 0.34 (0.06-0.62) | 1.00 (0.98-1.01) | 1.29 (1.14-1.47) | 83% (70%-94%) |
| COLL | 1-2 years | 1 | 0.76 (0.76-0.76) | 0.76 (0.76-0.76) | 0.76 (0.76-0.76) | 0.76 (0.76-0.76) | 100% (100%-100%) |
| COLL | all ages | 535 | 1.04 (0.92-1.12) | 0.00 (0.00-0.00) | 0.99 (0.97-1.00) | 2.55 (1.96-2.95) | 53% (49%-55%) |
| COMP | 0-3 months | 264 | 1.15 (1.11-1.20) | 0.00 (0.00-0.00) | 0.86 (0.80-0.94) | 2.66 (2.56-2.74) | 48% (44%-52%) |
| COMP | 3-12 months | 5 | 0.55 (0.26-0.72) | 0.15 (-0.00-0.49) | 0.45 (0.13-0.90) | 0.90 (0.83-1.00) | 50% (25%-80%) |
| COMP | all ages | 269 | 1.14 (1.11-1.20) | 0.00 (0.00-0.00) | 0.85 (0.80-0.92) | 2.64 (2.55-2.74) | 49% (45%-52%) |
| RENT | 0-3 months | 316 | 0.94 (0.91-0.96) | 0.39 (0.36-0.42) | 0.96 (0.94-0.97) | 1.56 (1.43-1.67) | 80% (77%-81%) |
| RENT | 3-12 months | 5 | 0.99 (0.92-1.07) | 0.87 (0.70-0.96) | 0.99 (0.93-1.05) | 1.06 (0.98-1.19) | 100% (100%-100%) |
| RENT | all ages | 321 | 0.94 (0.91-0.96) | 0.39 (0.36-0.42) | 0.96 (0.94-0.97) | 1.56 (1.42-1.67) | 80% (77%-82%) |
| TOW | 0-3 months | 39 | 0.91 (0.88-0.95) | 0.73 (0.56-0.91) | 1.00 (1.00-1.00) | 1.00 (1.00-1.00) | 95% (91%-97%) |
| TOW | all ages | 39 | 0.91 (0.88-0.95) | 0.73 (0.56-0.91) | 1.00 (1.00-1.00) | 1.00 (1.00-1.00) | 95% (91%-97%) |

Reserve reviews raise the reserve about as often as they lower it, at every age. Property claims open at a
year-end later paid within about 15% of what was reserved for them in aggregate (collision 1.04,
comprehensive 1.14, property damage 1.15); rental reserves are a little redundant. Young injury reserves are short, by design: early injury
estimates average about 86% of ultimate and many injury claimants present or grow later, so bodily injury
incurred develops upward as in industry triangles. Individual features scatter widely (most claims either
close for nothing or settle well away from the reserve), which is what case reserves look like. They are,
though, the generator's draws around the eventual outcome rather than an adjuster's reading of a file, so their
errors are better behaved than real ones: no reserve is ever set far off for a reason a later fact reveals.

Reserve reviews, by age at the review: the share raising and the share lowering the reserve (cells with
fewer than 20 reviews left out).

| coverage | age | reviews | up | down |
|---|---|--:|--:|--:|
| BI | 0-3 months | 1,624 | 54% (52%-56%) | 46% (44%-48%) |
| BI | 3-12 months | 4,069 | 55% (54%-56%) | 45% (44%-46%) |
| BI | 1-2 years | 1,066 | 57% (56%-58%) | 43% (42%-44%) |
| BI | over 2 years | 282 | 58% (55%-61%) | 42% (39%-45%) |
| PD | 0-3 months | 2,550 | 46% (46%-49%) | 54% (51%-54%) |
| PD | 3-12 months | 63 | 47% (40%-55%) | 53% (45%-60%) |
| UM | 0-3 months | 101 | 52% (45%-59%) | 48% (41%-55%) |
| UM | 3-12 months | 339 | 56% (55%-58%) | 44% (42%-45%) |
| UM | 1-2 years | 128 | 61% (57%-67%) | 39% (33%-43%) |
| UM | over 2 years | 27 | 60% (52%-68%) | 40% (32%-48%) |
| MED | 0-3 months | 262 | 39% (38%-39%) | 61% (61%-62%) |
| MED | 3-12 months | 95 | 57% (50%-64%) | 43% (36%-50%) |
| MED | 1-2 years | 2 | 100% (100%-100%) | 0% (0%-0%) |
| COLL | 0-3 months | 2,682 | 53% (52%-54%) | 47% (46%-48%) |
| COLL | 3-12 months | 37 | 66% (56%-76%) | 34% (24%-44%) |
| COMP | 0-3 months | 1,095 | 55% (55%-56%) | 45% (44%-45%) |
| COMP | 3-12 months | 8 | 59% (40%-83%) | 41% (17%-60%) |
| RENT | 0-3 months | 2,297 | 45% (45%-46%) | 55% (54%-55%) |
| RENT | 3-12 months | 45 | 54% (44%-67%) | 46% (33%-56%) |

## 5. What is not benchmarked

Severity percentiles, limit-hit rates and the concentration of cost in the largest claims have no published US
figure on terms this data can match; section 3 reports them without a target. How variables depend on each other
(tenure and channel, age and mileage, value and total loss, claims and retention) is assumed in the generator and
reported, not validated, apart from the few relationships above. Model performance on held-out policies or later
years is left to the case studies: the data supports both splits (policy and date keys on every row).
