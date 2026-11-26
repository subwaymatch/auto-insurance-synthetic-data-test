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
| BI frequency per 100 car-years (tuning band) | 0.77 | 0.74 to 0.80 | 0.70 to 1.15 | 5 of 5 |
| BI average paid loss (tuning band) | 25,890 | 24,418 to 27,581 | 20,000 to 30,000 | 5 of 5 |
| PD frequency per 100 car-years (tuning band) | 2.69 | 2.61 to 2.73 | 2.40 to 3.40 | 5 of 5 |
| PD average paid loss (tuning band) | 6,775 | 6,605 to 6,928 | 5,800 to 7,400 | 5 of 5 |
| COLL frequency per 100 car-years (tuning band) | 5.32 | 5.21 to 5.40 | 4.00 to 6.20 | 5 of 5 |
| COLL average paid loss (tuning band) | 6,433 | 6,358 to 6,493 | 5,400 to 7,400 | 5 of 5 |
| COMP frequency per 100 car-years (tuning band) | 6.16 | 6.09 to 6.28 | 4.60 to 6.80 | 5 of 5 |
| COMP average paid loss (tuning band) | 2,888 | 2,859 to 2,914 | 2,200 to 3,400 | 5 of 5 |
| non-catastrophe incurred vs answer-key expected (all coverages) | 1.00 | 0.98 to 1.03 | 0.93 to 1.07 | 5 of 5 |
| BI frequency relative to national, like for like | 1.13 | 1.02 to 1.21 | 0.85 to 1.45 | 5 of 5 |
| BI severity relative to national, like for like | 0.97 | 0.88 to 1.04 | 0.85 to 1.15 | 5 of 5 |
| PD frequency relative to national, like for like | 1.09 | 1.05 to 1.12 | 0.85 to 1.45 | 5 of 5 |
| PD severity relative to national, like for like | 1.04 | 1.01 to 1.09 | 0.85 to 1.15 | 5 of 5 |
| COLL frequency relative to national, like for like | 1.32 | 1.29 to 1.38 | 0.85 to 1.45 | 5 of 5 |
| COLL severity relative to national, like for like | 0.90 | 0.88 to 0.94 | 0.85 to 1.15 | 5 of 5 |
| COMP frequency relative to national, like for like | 1.21 | 1.15 to 1.25 | 0.85 to 1.45 | 5 of 5 |
| COMP severity relative to national, like for like | 1.00 | 0.95 to 1.04 | 0.85 to 1.15 | 5 of 5 |
| liability premium per insured car-year relative to Illinois, 2022-2024 | 1.03 | 0.99 to 1.05 | 0.90 to 1.30 | 5 of 5 |
| collision premium per insured car-year relative to Illinois, 2022-2024 | 0.85 | 0.82 to 0.88 | 0.80 to 1.20 | 5 of 5 |
| comprehensive premium per insured car-year relative to Illinois, 2022-2024 | 0.89 | 0.89 to 0.90 | 0.75 to 1.20 | 5 of 5 |
| 2022 loss ratio excluding catastrophes relative to its expected | 1.03 | 0.97 to 1.07 | 0.85 to 1.15 | 5 of 5 |
| 2023 loss ratio excluding catastrophes relative to its expected | 1.02 | 0.96 to 1.07 | 0.85 to 1.15 | 5 of 5 |
| 2024 loss ratio excluding catastrophes relative to its expected | 1.02 | 0.93 to 1.07 | 0.85 to 1.15 | 5 of 5 |
| 2025 loss ratio excluding catastrophes relative to its expected | 0.99 | 0.91 to 1.07 | 0.85 to 1.15 | 5 of 5 |
| 2022 expected loss ratio (answer key) plus catastrophes vs industry | 80.6% | 79.9% to 81.1% | 74.0% to 85.0% | 5 of 5 |
| 2023 expected loss ratio (answer key) plus catastrophes vs industry | 77.6% | 76.8% to 78.6% | 68.0% to 80.0% | 5 of 5 |
| 2024 expected loss ratio (answer key) plus catastrophes vs industry | 67.6% | 66.9% to 68.4% | 59.0% to 70.0% | 5 of 5 |
| 2025 expected loss ratio (answer key) plus catastrophes vs industry | 64.0% | 63.1% to 64.9% | 55.0% to 67.0% | 5 of 5 |
| overall loss ratio | 71.5% | 69.3% to 73.4% | 62.0% to 76.0% | 5 of 5 |
| first month's exposure relative to the first year's average | 0.97 | 0.97 to 0.98 | 0.85 to 1.15 | 5 of 5 |
| share of drivers with no violation in 3 years | 88.4% | 88.3% to 88.5% | 78.0% to 90.0% | 5 of 5 |
| share of drivers with no at-fault accident in 3 years | 93.3% | 93.2% to 93.6% | 86.0% to 95.0% | 5 of 5 |
| annualized policy retention | 81.4% | 81.2% to 81.6% | 78.0% to 90.0% | 5 of 5 |
| new business expected loss ratio above renewals (points) | 9.28 | 8.37 to 9.74 | 5.00 to 16.00 | 5 of 5 |
| spread of expected loss ratio across agencies with 500+ car-years (90th less 10th percentile, points) | 14.91 | 13.67 to 16.01 | 6.00 to 25.00 | 5 of 5 |
| quotes in February to April relative to October to December | 1.20 | 1.20 to 1.21 | 1.08 to 1.40 | 5 of 5 |
| conversion after a rate increase relative to before it | 0.80 | 0.78 to 0.84 | 0.60 to 0.92 | 5 of 5 |
| terms with a claim end the policy more often than terms without (ratio) | 1.53 | 1.48 to 1.55 | 1.20 to 1.70 | 5 of 5 |
| share of non-renewals that are the company's decision | 4.6% | 4.4% to 4.8% | 3.0% to 15.0% | 5 of 5 |
| renewal rate of exclusive-agent customers above direct customers (points) | 4.05 | 3.62 to 4.53 | 1.00 to 8.00 | 5 of 5 |
| share of paid bodily injury settlements that are whole-dollar amounts | 87.6% | 86.3% to 89.9% | 75.0% to 95.0% | 5 of 5 |
| crashes on Thursdays and Fridays relative to Sundays and Mondays | 1.17 | 1.12 to 1.21 | 1.05 to 1.28 | 5 of 5 |

Every integrity check passes on every seed, and every calibration band holds on all five (seed 42's bodily injury
frequency, below its tuning floor in the two previous rounds, is now inside it). The calibration figures that matter most for analysis are the frequencies, severities and loss ratios;
their spread across seeds is claim luck and the draw of the book at this size, and it is the yardstick for any
difference a case study finds between segments of one build.

## 3. Tail and joint diagnostics

| figure | mean | range | published | source |
|---|--:|--:|--:|--:|
| total-loss share, paid collision and comprehensive claims (glass apart) | 27.8% | 27.6% to 28.3% | 22.1% (2024), 22.8% (2025) | CCC Crash Course, US: all appraised vehicle claims |
| total-loss share, paid collision claims | 32.1% | 31.5% to 32.9% | - | no US figure for collision alone |
| total losses on cars 7+ model years old | 79.6% | 78.3% to 81.2% | 72% | CCC Crash Course, US, 2025 |
| average value of cars paid as total losses ($) | 10,451 | 10,272 to 10,636 | 13,400 to 13,700 | CCC Crash Course, US, 2024-25 (used in setting values) |
| closed liability and medical payments claims without payment | 42.9% | 42.3% to 43.2% | about 45% | WSJ analysis of NAIC filings, 2025 (tuned) |
| closed collision and comprehensive claims without payment | 15.4% | 15.3% to 15.6% | just under 25% | WSJ analysis of NAIC filings, 2025 (tuned) |
| closed collision claims without payment | 22.7% | 22.5% to 22.9% | - | (collision alone) |
| average age of insured cars in force, last full year (years) | 10.66 | 10.63 to 10.73 | 12.6 (2024), 12.8 (2025) | S&P Global Mobility, US light vehicles in operation |
| share of claim cost in the costliest 1% of risk rows with a claim | 16.8% | 15.5% to 17.6% | - | no US figure on these terms |
| coefficient of variation of claim cost per risk row with a claim | 2.19 | 2.04 to 2.26 | - | no US figure on these terms |
| bodily injury claimants paid the full per-person limit | 21.3% | 20.1% to 23.2% | - | no public US figure |
| bodily injury paid per claimant, median ($) | 17,850 | 17,000 to 19,000 | - | no public US figure |
| bodily injury paid per claimant, 90th percentile ($) | 53,025 | 50,000 to 59,927 | - | no public US figure |
| bodily injury paid per claimant, 99th percentile ($) | 136,559 | 111,024 to 162,597 | - | no public US figure |

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
- **The insured fleet is younger than all registered cars** (10.7 years against 12.6 to 12.8): the fleet is
  tuned to the cars in Chicago crashes, which are younger than the national stock, and insured cars are
  younger than registered ones, which include cars off the road.
- **Physical damage claims close without payment less often than the industry's** (about 15% of collision
  and comprehensive, against just under 25%; about 23% of collision alone). Comprehensive claims here are mostly glass,
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
| BI | 0-3 months | 894 | 1.66 (1.60-1.71) | 0.00 (0.00-0.00) | 0.00 (0.00-0.00) | 3.02 (2.84-3.29) | 16% (14%-18%) |
| BI | 3-12 months | 944 | 1.12 (1.10-1.13) | 0.00 (0.00-0.00) | 0.91 (0.89-0.93) | 1.83 (1.79-1.93) | 51% (49%-53%) |
| BI | 1-2 years | 254 | 1.17 (1.15-1.21) | 0.11 (0.00-0.34) | 1.11 (1.08-1.14) | 1.73 (1.67-1.89) | 84% (81%-86%) |
| BI | over 2 years | 60 | 1.11 (1.05-1.13) | 0.86 (0.74-0.97) | 1.08 (1.05-1.11) | 1.56 (1.41-1.68) | 93% (88%-98%) |
| BI | all ages | 2,152 | 1.23 (1.22-1.25) | 0.00 (0.00-0.00) | 0.67 (0.64-0.72) | 2.06 (2.01-2.11) | 41% (40%-42%) |
| PD | 0-3 months | 417 | 1.13 (1.08-1.16) | 0.00 (0.00-0.00) | 0.88 (0.85-0.91) | 2.23 (1.87-2.61) | 54% (50%-57%) |
| PD | 3-12 months | 10 | 1.00 (0.93-1.10) | 0.68 (0.61-0.83) | 0.98 (0.89-1.06) | 1.27 (1.09-1.65) | 98% (89%-100%) |
| PD | all ages | 427 | 1.13 (1.08-1.16) | 0.00 (0.00-0.00) | 0.89 (0.87-0.91) | 2.18 (1.85-2.60) | 55% (52%-58%) |
| UM | 0-3 months | 54 | 1.44 (1.04-1.90) | 0.00 (0.00-0.00) | 0.87 (0.74-1.07) | 3.72 (2.46-5.48) | 39% (35%-45%) |
| UM | 3-12 months | 68 | 1.20 (1.10-1.41) | 0.68 (0.44-0.89) | 1.18 (1.11-1.31) | 2.05 (1.87-2.20) | 82% (76%-87%) |
| UM | 1-2 years | 24 | 1.26 (1.18-1.37) | 0.89 (0.78-1.02) | 1.20 (1.08-1.47) | 1.86 (1.61-2.06) | 87% (81%-93%) |
| UM | over 2 years | 6 | 1.21 (1.01-1.64) | 0.97 (0.90-1.05) | 1.12 (1.06-1.16) | 1.34 (1.14-1.60) | 100% (100%-100%) |
| UM | all ages | 151 | 1.26 (1.15-1.35) | 0.09 (0.01-0.17) | 1.11 (1.08-1.16) | 2.32 (2.17-2.40) | 68% (66%-69%) |
| MED | 0-3 months | 85 | 1.08 (0.91-1.24) | 0.35 (0.34-0.36) | 1.00 (1.00-1.00) | 2.28 (1.94-2.51) | 68% (59%-73%) |
| MED | 3-12 months | 27 | 1.06 (0.95-1.18) | 0.67 (0.48-0.97) | 1.02 (1.00-1.04) | 1.38 (1.27-1.46) | 94% (89%-96%) |
| MED | 1-2 years | 1 | 0.49 (0.17-0.81) | 0.49 (0.17-0.81) | 0.49 (0.17-0.81) | 0.49 (0.17-0.81) | 50% (0%-100%) |
| MED | all ages | 112 | 1.07 (0.94-1.17) | 0.38 (0.35-0.44) | 1.00 (1.00-1.00) | 2.11 (1.66-2.35) | 74% (67%-78%) |
| COLL | 0-3 months | 531 | 1.04 (0.99-1.08) | 0.00 (0.00-0.00) | 0.98 (0.95-1.00) | 2.56 (2.37-2.82) | 53% (51%-54%) |
| COLL | 3-12 months | 16 | 1.05 (1.01-1.07) | 0.77 (0.61-0.98) | 1.03 (1.00-1.08) | 1.35 (1.23-1.53) | 92% (85%-100%) |
| COLL | 1-2 years | 1 | 0.72 (0.72-0.72) | 0.72 (0.72-0.72) | 0.72 (0.72-0.72) | 0.72 (0.72-0.72) | 100% (100%-100%) |
| COLL | all ages | 546 | 1.04 (0.99-1.08) | 0.00 (0.00-0.00) | 0.99 (0.97-1.00) | 2.52 (2.34-2.82) | 54% (52%-55%) |
| COMP | 0-3 months | 258 | 1.22 (1.11-1.44) | 0.00 (0.00-0.00) | 0.86 (0.78-1.00) | 2.92 (2.46-3.49) | 46% (42%-51%) |
| COMP | 3-12 months | 6 | 0.93 (0.76-1.08) | 0.38 (0.19-0.69) | 0.80 (0.40-1.10) | 1.12 (0.97-1.23) | 68% (33%-100%) |
| COMP | 1-2 years | 1 | 0.44 (0.16-0.72) | 0.44 (0.16-0.72) | 0.44 (0.16-0.72) | 0.44 (0.16-0.72) | 50% (0%-100%) |
| COMP | all ages | 264 | 1.22 (1.11-1.43) | 0.00 (0.00-0.00) | 0.86 (0.80-1.00) | 2.88 (2.45-3.46) | 46% (43%-51%) |
| RENT | 0-3 months | 324 | 0.94 (0.89-0.96) | 0.38 (0.35-0.43) | 0.95 (0.92-0.96) | 1.65 (1.60-1.71) | 78% (76%-81%) |
| RENT | 3-12 months | 7 | 0.97 (0.93-1.06) | 0.80 (0.58-0.94) | 1.00 (0.97-1.08) | 1.09 (1.05-1.17) | 95% (86%-100%) |
| RENT | all ages | 331 | 0.94 (0.89-0.96) | 0.39 (0.35-0.44) | 0.95 (0.92-0.96) | 1.65 (1.60-1.71) | 78% (76%-81%) |
| TOW | 0-3 months | 39 | 0.93 (0.90-0.95) | 0.75 (0.64-0.86) | 1.00 (1.00-1.00) | 1.00 (1.00-1.00) | 96% (92%-98%) |
| TOW | all ages | 39 | 0.93 (0.90-0.95) | 0.75 (0.64-0.86) | 1.00 (1.00-1.00) | 1.00 (1.00-1.00) | 96% (92%-98%) |

Reserve reviews raise the reserve about as often as they lower it, at every age. Property claims open at a
year-end later paid within about a fifth of what was reserved for them in aggregate (collision 1.04,
comprehensive 1.22, property damage 1.13); rental reserves are a little redundant. Young injury reserves are short, by design: early injury
estimates average about 86% of ultimate and many injury claimants present or grow later, so bodily injury
incurred develops upward as in industry triangles. Individual features scatter widely (most claims either
close for nothing or settle well away from the reserve), which is what case reserves look like. They are,
though, the generator's draws around the eventual outcome rather than an adjuster's reading of a file, so their
errors are better behaved than real ones: no reserve is ever set far off for a reason a later fact reveals.

Reserve reviews, by age at the review: the share raising and the share lowering the reserve (cells with
fewer than 20 reviews left out).

| coverage | age | reviews | up | down |
|---|---|--:|--:|--:|
| BI | 0-3 months | 1,649 | 54% (53%-56%) | 46% (44%-47%) |
| BI | 3-12 months | 4,241 | 56% (54%-56%) | 44% (44%-46%) |
| BI | 1-2 years | 1,102 | 57% (56%-59%) | 43% (41%-44%) |
| BI | over 2 years | 297 | 60% (56%-63%) | 40% (37%-44%) |
| PD | 0-3 months | 2,545 | 47% (46%-47%) | 53% (53%-54%) |
| PD | 3-12 months | 63 | 45% (40%-49%) | 55% (51%-60%) |
| UM | 0-3 months | 106 | 48% (42%-51%) | 52% (49%-58%) |
| UM | 3-12 months | 310 | 57% (56%-58%) | 43% (42%-44%) |
| UM | 1-2 years | 98 | 60% (51%-70%) | 40% (30%-49%) |
| UM | over 2 years | 25 | 66% (47%-92%) | 34% (8%-53%) |
| MED | 0-3 months | 264 | 39% (33%-43%) | 61% (57%-67%) |
| MED | 3-12 months | 93 | 58% (53%-64%) | 42% (36%-47%) |
| COLL | 0-3 months | 2,668 | 53% (52%-55%) | 47% (45%-48%) |
| COLL | 3-12 months | 36 | 65% (53%-74%) | 35% (26%-47%) |
| COMP | 0-3 months | 1,076 | 55% (54%-56%) | 45% (44%-46%) |
| COMP | 3-12 months | 11 | 56% (33%-67%) | 44% (33%-67%) |
| RENT | 0-3 months | 2,310 | 46% (45%-47%) | 54% (53%-55%) |
| RENT | 3-12 months | 46 | 49% (46%-55%) | 51% (45%-54%) |

## 5. What is not benchmarked

Severity percentiles, limit-hit rates and the concentration of cost in the largest claims have no published US
figure on terms this data can match; section 3 reports them without a target. How variables depend on each other
(tenure and channel, age and mileage, value and total loss, claims and retention) is assumed in the generator and
reported, not validated, apart from the few relationships above. Model performance on held-out policies or later
years is left to the case studies: the data supports both splits (policy and date keys on every row).
