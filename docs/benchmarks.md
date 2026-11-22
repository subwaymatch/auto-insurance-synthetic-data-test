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
| BI frequency per 100 car-years (tuning band) | 0.76 | 0.71 to 0.83 | 0.70 to 1.15 | 5 of 5 |
| BI average paid loss (tuning band) | 24,760 | 23,899 to 25,131 | 20,000 to 30,000 | 5 of 5 |
| PD frequency per 100 car-years (tuning band) | 2.66 | 2.59 to 2.73 | 2.40 to 3.40 | 5 of 5 |
| PD average paid loss (tuning band) | 6,816 | 6,702 to 6,899 | 5,800 to 7,400 | 5 of 5 |
| COLL frequency per 100 car-years (tuning band) | 5.27 | 5.17 to 5.34 | 4.00 to 6.20 | 5 of 5 |
| COLL average paid loss (tuning band) | 6,443 | 6,393 to 6,485 | 5,400 to 7,400 | 5 of 5 |
| COMP frequency per 100 car-years (tuning band) | 6.12 | 6.03 to 6.20 | 4.60 to 6.80 | 5 of 5 |
| COMP average paid loss (tuning band) | 2,876 | 2,823 to 2,918 | 2,200 to 3,400 | 5 of 5 |
| non-catastrophe incurred vs answer-key expected (all coverages) | 0.98 | 0.94 to 1.01 | 0.93 to 1.07 | 5 of 5 |
| BI frequency relative to national, like for like | 1.06 | 0.96 to 1.15 | 0.85 to 1.45 | 5 of 5 |
| BI severity relative to national, like for like | 0.95 | 0.87 to 0.99 | 0.85 to 1.15 | 5 of 5 |
| PD frequency relative to national, like for like | 1.08 | 1.06 to 1.12 | 0.85 to 1.45 | 5 of 5 |
| PD severity relative to national, like for like | 1.04 | 1.01 to 1.07 | 0.85 to 1.15 | 5 of 5 |
| COLL frequency relative to national, like for like | 1.28 | 1.26 to 1.35 | 0.85 to 1.45 | 5 of 5 |
| COLL severity relative to national, like for like | 0.91 | 0.88 to 0.93 | 0.85 to 1.15 | 5 of 5 |
| COMP frequency relative to national, like for like | 1.22 | 1.19 to 1.25 | 0.85 to 1.45 | 5 of 5 |
| COMP severity relative to national, like for like | 1.00 | 0.97 to 1.01 | 0.85 to 1.15 | 5 of 5 |
| liability premium per insured car-year relative to Illinois, 2022-2024 | 1.03 | 1.00 to 1.05 | 0.90 to 1.30 | 5 of 5 |
| collision premium per insured car-year relative to Illinois, 2022-2024 | 0.85 | 0.83 to 0.87 | 0.80 to 1.20 | 5 of 5 |
| comprehensive premium per insured car-year relative to Illinois, 2022-2024 | 0.92 | 0.89 to 0.94 | 0.75 to 1.20 | 5 of 5 |
| 2022 loss ratio excluding catastrophes relative to its expected | 1.02 | 0.99 to 1.08 | 0.85 to 1.15 | 5 of 5 |
| 2023 loss ratio excluding catastrophes relative to its expected | 0.96 | 0.89 to 0.99 | 0.85 to 1.15 | 5 of 5 |
| 2024 loss ratio excluding catastrophes relative to its expected | 1.01 | 0.97 to 1.06 | 0.85 to 1.15 | 5 of 5 |
| 2025 loss ratio excluding catastrophes relative to its expected | 0.97 | 0.90 to 1.04 | 0.85 to 1.15 | 5 of 5 |
| 2022 expected loss ratio (answer key) plus catastrophes vs industry | 80.3% | 79.4% to 81.1% | 74.0% to 85.0% | 5 of 5 |
| 2023 expected loss ratio (answer key) plus catastrophes vs industry | 77.6% | 76.8% to 78.3% | 68.0% to 80.0% | 5 of 5 |
| 2024 expected loss ratio (answer key) plus catastrophes vs industry | 67.3% | 66.5% to 68.1% | 59.0% to 70.0% | 5 of 5 |
| 2025 expected loss ratio (answer key) plus catastrophes vs industry | 63.7% | 62.9% to 64.4% | 55.0% to 67.0% | 5 of 5 |
| overall loss ratio | 69.4% | 67.6% to 70.5% | 62.0% to 76.0% | 5 of 5 |
| first month's exposure relative to the first year's average | 0.98 | 0.97 to 0.98 | 0.85 to 1.15 | 5 of 5 |
| share of drivers with no violation in 3 years | 88.4% | 88.3% to 88.5% | 78.0% to 90.0% | 5 of 5 |
| share of drivers with no at-fault accident in 3 years | 93.3% | 93.2% to 93.6% | 86.0% to 95.0% | 5 of 5 |
| annualized policy retention | 81.2% | 81.0% to 81.4% | 78.0% to 90.0% | 5 of 5 |
| new business expected loss ratio above renewals (points) | 9.48 | 8.84 to 10.07 | 5.00 to 16.00 | 5 of 5 |
| spread of expected loss ratio across agencies with 500+ car-years (90th less 10th percentile, points) | 14.90 | 12.89 to 16.58 | 6.00 to 25.00 | 5 of 5 |
| quotes in February to April relative to October to December | 1.20 | 1.20 to 1.21 | 1.08 to 1.40 | 5 of 5 |
| conversion after a rate increase relative to before it | 0.81 | 0.78 to 0.84 | 0.60 to 0.92 | 5 of 5 |
| terms with a claim end the policy more often than terms without (ratio) | 1.56 | 1.53 to 1.57 | 1.20 to 1.70 | 5 of 5 |
| share of non-renewals that are the company's decision | 7.7% | 7.5% to 8.0% | 3.0% to 15.0% | 5 of 5 |
| renewal rate of exclusive-agent customers above direct customers (points) | 4.04 | 3.56 to 4.47 | 1.00 to 8.00 | 5 of 5 |
| share of paid bodily injury settlements that are whole-dollar amounts | 86.7% | 85.6% to 87.7% | 75.0% to 95.0% | 5 of 5 |
| crashes on Thursdays and Fridays relative to Sundays and Mondays | 1.18 | 1.13 to 1.25 | 1.05 to 1.28 | 5 of 5 |

Every integrity check passes on every seed. The calibration figures that matter most for analysis are the
frequencies, severities and loss ratios; their spread across seeds is claim luck on a book of this size, and it
is the yardstick for any difference a case study finds between segments of one build.

## 3. Tail and joint diagnostics

| figure | mean | range | published | source |
|---|--:|--:|--:|--:|
| total-loss share, paid collision and comprehensive claims (glass apart) | 28.2% | 27.8% to 28.7% | 22.1% (2024), 22.8% (2025) | CCC Crash Course, US: all appraised vehicle claims |
| total-loss share, paid collision claims | 32.3% | 31.7% to 33.2% | - | no US figure for collision alone |
| total losses on cars 7+ model years old | 80.0% | 79.7% to 80.4% | 72% | CCC Crash Course, US, 2025 |
| average value of cars paid as total losses ($) | 10,418 | 10,329 to 10,572 | 13,400 to 13,700 | CCC Crash Course, US, 2024-25 (used in setting values) |
| closed liability and medical payments claims without payment | 42.7% | 42.0% to 43.2% | about 45% | WSJ analysis of NAIC filings, 2025 (tuned) |
| closed collision and comprehensive claims without payment | 15.5% | 15.2% to 15.7% | just under 25% | WSJ analysis of NAIC filings, 2025 (tuned) |
| closed collision claims without payment | 22.7% | 22.4% to 23.0% | - | (collision alone) |
| average age of insured cars in force, last full year (years) | 10.67 | 10.65 to 10.70 | 12.6 (2024), 12.8 (2025) | S&P Global Mobility, US light vehicles in operation |
| share of claim cost in the costliest 1% of risk rows with a claim | 16.3% | 15.6% to 16.7% | - | no US figure on these terms |
| coefficient of variation of claim cost per risk row with a claim | 2.14 | 2.09 to 2.21 | - | no US figure on these terms |
| bodily injury claimants paid the full per-person limit | 20.4% | 19.3% to 21.8% | - | no public US figure |
| bodily injury paid per claimant, median ($) | 16,633 | 15,500 to 17,750 | - | no public US figure |
| bodily injury paid per claimant, 90th percentile ($) | 50,000 | 50,000 to 50,000 | - | no public US figure |
| bodily injury paid per claimant, 99th percentile ($) | 121,035 | 100,000 to 141,500 | - | no public US figure |

What they show:

- **Total losses are too common, and on older, cheaper cars.** About 28% of paid collision and comprehensive
  claims (glass apart) are total losses, against 22.1% to 22.8% of CCC's appraisals; 80% of total losses are
  on cars seven or more model years old (CCC: 72%), and the average car written off is worth about $10,400
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
| BI | 0-3 months | 891 | 1.60 (1.38-1.77) | 0.00 (0.00-0.00) | 0.00 (0.00-0.00) | 2.91 (2.23-3.24) | 16% (15%-17%) |
| BI | 3-12 months | 926 | 1.12 (1.08-1.15) | 0.00 (0.00-0.00) | 0.90 (0.85-0.97) | 1.90 (1.84-1.99) | 50% (48%-51%) |
| BI | 1-2 years | 243 | 1.18 (1.15-1.21) | 0.28 (0.00-0.69) | 1.11 (1.08-1.14) | 1.72 (1.67-1.85) | 83% (78%-86%) |
| BI | over 2 years | 67 | 1.11 (1.08-1.16) | 0.84 (0.70-0.93) | 1.08 (1.07-1.10) | 1.49 (1.29-1.72) | 92% (89%-95%) |
| BI | all ages | 2,127 | 1.23 (1.19-1.28) | 0.00 (0.00-0.00) | 0.64 (0.57-0.76) | 2.08 (1.93-2.15) | 41% (40%-42%) |
| PD | 0-3 months | 413 | 1.18 (1.12-1.22) | 0.00 (0.00-0.00) | 0.90 (0.87-0.91) | 2.29 (2.06-2.50) | 55% (53%-57%) |
| PD | 3-12 months | 9 | 1.01 (0.92-1.07) | 0.61 (0.00-0.93) | 1.02 (0.92-1.10) | 1.31 (1.13-1.57) | 92% (82%-100%) |
| PD | all ages | 422 | 1.17 (1.11-1.22) | 0.00 (0.00-0.00) | 0.90 (0.87-0.92) | 2.25 (2.04-2.44) | 56% (54%-58%) |
| UM | 0-3 months | 53 | 1.39 (1.07-1.70) | 0.07 (0.00-0.20) | 0.80 (0.60-1.09) | 3.40 (2.35-4.51) | 34% (30%-38%) |
| UM | 3-12 months | 73 | 1.15 (1.01-1.33) | 0.53 (0.00-0.79) | 1.11 (1.01-1.25) | 1.88 (1.60-2.10) | 83% (77%-90%) |
| UM | 1-2 years | 23 | 1.23 (1.12-1.36) | 0.84 (0.61-0.97) | 1.20 (1.14-1.26) | 1.78 (1.60-2.00) | 93% (88%-100%) |
| UM | over 2 years | 6 | 1.31 (1.03-1.54) | 0.98 (0.76-1.06) | 1.27 (1.04-1.54) | 1.54 (1.23-1.99) | 95% (75%-100%) |
| UM | all ages | 155 | 1.22 (1.16-1.34) | 0.21 (0.04-0.59) | 1.10 (1.04-1.15) | 2.39 (2.14-2.79) | 68% (64%-77%) |
| MED | 0-3 months | 80 | 1.13 (1.02-1.26) | 0.32 (0.26-0.38) | 1.00 (1.00-1.00) | 2.57 (1.71-3.07) | 69% (63%-76%) |
| MED | 3-12 months | 26 | 1.07 (1.02-1.12) | 0.59 (0.37-0.85) | 0.99 (0.96-1.01) | 1.60 (1.22-1.93) | 85% (75%-90%) |
| MED | 1-2 years | 2 | 0.48 (0.48-0.48) | 0.10 (0.10-0.10) | 0.50 (0.50-0.50) | 0.90 (0.90-0.90) | 50% (50%-50%) |
| MED | all ages | 106 | 1.11 (1.03-1.21) | 0.36 (0.31-0.39) | 1.00 (1.00-1.00) | 2.30 (1.64-2.91) | 73% (69%-79%) |
| COLL | 0-3 months | 546 | 1.06 (0.95-1.09) | 0.00 (0.00-0.00) | 0.98 (0.92-1.00) | 2.66 (2.47-2.82) | 52% (50%-55%) |
| COLL | 3-12 months | 17 | 0.99 (0.90-1.06) | 0.22 (0.00-0.53) | 0.98 (0.87-1.01) | 1.23 (1.00-1.33) | 78% (67%-88%) |
| COLL | 1-2 years | 2 | 0.90 (0.80-1.00) | 0.58 (0.16-1.00) | 0.90 (0.80-1.00) | 1.21 (1.00-1.42) | 83% (67%-100%) |
| COLL | all ages | 563 | 1.06 (0.95-1.09) | 0.00 (0.00-0.00) | 0.98 (0.92-1.00) | 2.61 (2.44-2.77) | 53% (51%-56%) |
| COMP | 0-3 months | 254 | 1.25 (1.14-1.62) | 0.00 (0.00-0.00) | 0.83 (0.66-0.96) | 2.88 (2.46-3.63) | 45% (39%-51%) |
| COMP | 3-12 months | 8 | 0.66 (0.52-0.85) | 0.06 (-0.00-0.30) | 0.53 (0.43-0.71) | 0.97 (0.77-1.12) | 49% (33%-71%) |
| COMP | all ages | 262 | 1.25 (1.14-1.62) | 0.00 (0.00-0.00) | 0.80 (0.65-0.91) | 2.84 (2.45-3.61) | 45% (39%-50%) |
| RENT | 0-3 months | 323 | 0.93 (0.90-0.96) | 0.39 (0.38-0.40) | 0.94 (0.90-0.96) | 1.58 (1.45-1.71) | 78% (76%-80%) |
| RENT | 3-12 months | 8 | 0.98 (0.91-1.02) | 0.87 (0.68-1.00) | 1.00 (0.96-1.04) | 1.06 (1.01-1.11) | 100% (100%-100%) |
| RENT | all ages | 330 | 0.93 (0.90-0.96) | 0.39 (0.38-0.42) | 0.94 (0.92-0.96) | 1.57 (1.45-1.71) | 79% (76%-80%) |
| TOW | 0-3 months | 36 | 0.92 (0.90-0.96) | 0.73 (0.61-0.85) | 1.00 (1.00-1.00) | 1.00 (1.00-1.00) | 95% (91%-100%) |
| TOW | all ages | 36 | 0.92 (0.90-0.96) | 0.73 (0.61-0.85) | 1.00 (1.00-1.00) | 1.00 (1.00-1.00) | 95% (91%-100%) |

Reserve reviews raise the reserve about as often as they lower it, at every age. Property claims open at a
year-end later paid within about a quarter of what was reserved for them in aggregate (collision 1.06,
comprehensive 1.25, property damage 1.17); rental reserves are a little redundant. Young injury reserves are short, by design: early injury
estimates average about 86% of ultimate and many injury claimants present or grow later, so bodily injury
incurred develops upward as in industry triangles. Individual features scatter widely (most claims either
close for nothing or settle well away from the reserve), which is what case reserves look like. They are,
though, the generator's draws around the eventual outcome rather than an adjuster's reading of a file, so their
errors are better behaved than real ones: no reserve is ever set far off for a reason a later fact reveals.

Reserve reviews, by age at the review: the share raising and the share lowering the reserve (cells with
fewer than 20 reviews left out).

| coverage | age | reviews | up | down |
|---|---|--:|--:|--:|
| BI | 0-3 months | 1,614 | 54% (52%-56%) | 46% (44%-48%) |
| BI | 3-12 months | 4,162 | 55% (54%-57%) | 45% (43%-46%) |
| BI | 1-2 years | 1,081 | 58% (56%-60%) | 42% (40%-44%) |
| BI | over 2 years | 313 | 56% (51%-58%) | 44% (42%-49%) |
| PD | 0-3 months | 2,512 | 48% (48%-49%) | 52% (51%-52%) |
| PD | 3-12 months | 55 | 52% (47%-57%) | 48% (43%-53%) |
| UM | 0-3 months | 103 | 46% (42%-52%) | 54% (48%-58%) |
| UM | 3-12 months | 318 | 54% (51%-56%) | 46% (44%-49%) |
| UM | 1-2 years | 111 | 58% (54%-63%) | 42% (37%-46%) |
| UM | over 2 years | 29 | 53% (38%-65%) | 47% (35%-62%) |
| MED | 0-3 months | 256 | 38% (35%-41%) | 62% (59%-65%) |
| MED | 3-12 months | 81 | 58% (55%-68%) | 42% (32%-45%) |
| COLL | 0-3 months | 2,628 | 52% (52%-54%) | 48% (46%-48%) |
| COLL | 3-12 months | 40 | 66% (61%-68%) | 34% (32%-39%) |
| COMP | 0-3 months | 1,095 | 55% (54%-57%) | 45% (43%-46%) |
| COMP | 3-12 months | 7 | 45% (30%-60%) | 55% (40%-70%) |
| RENT | 0-3 months | 2,332 | 45% (44%-47%) | 55% (53%-56%) |
| RENT | 3-12 months | 49 | 56% (46%-62%) | 44% (38%-54%) |

## 5. What is not benchmarked

Severity percentiles, limit-hit rates and the concentration of cost in the largest claims have no published US
figure on terms this data can match; section 3 reports them without a target. How variables depend on each other
(tenure and channel, age and mileage, value and total loss, claims and retention) is assumed in the generator and
reported, not validated, apart from the few relationships above. Model performance on held-out policies or later
years is left to the case studies: the data supports both splits (policy and date keys on every row).
