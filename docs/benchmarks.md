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
| BI frequency per 100 car-years (tuning band) | 0.74 | 0.71 to 0.78 | 0.70 to 1.15 | 5 of 5 |
| BI average paid loss (tuning band) | 25,461 | 23,920 to 27,097 | 20,000 to 30,000 | 5 of 5 |
| PD frequency per 100 car-years (tuning band) | 2.64 | 2.60 to 2.68 | 2.40 to 3.40 | 5 of 5 |
| PD average paid loss (tuning band) | 6,813 | 6,677 to 6,949 | 5,800 to 7,400 | 5 of 5 |
| COLL frequency per 100 car-years (tuning band) | 5.27 | 5.14 to 5.35 | 4.00 to 6.20 | 5 of 5 |
| COLL average paid loss (tuning band) | 6,524 | 6,409 to 6,616 | 5,400 to 7,400 | 5 of 5 |
| COMP frequency per 100 car-years (tuning band) | 6.12 | 6.05 to 6.26 | 4.60 to 6.80 | 5 of 5 |
| COMP average paid loss (tuning band) | 2,905 | 2,862 to 2,948 | 2,200 to 3,400 | 5 of 5 |
| non-catastrophe incurred vs answer-key expected (all coverages) | 1.00 | 0.97 to 1.02 | 0.93 to 1.07 | 5 of 5 |
| BI frequency relative to national, like for like | 1.06 | 0.99 to 1.13 | 0.85 to 1.45 | 5 of 5 |
| BI severity relative to national, like for like | 0.98 | 0.94 to 1.05 | 0.85 to 1.15 | 5 of 5 |
| PD frequency relative to national, like for like | 1.07 | 1.05 to 1.11 | 0.85 to 1.45 | 5 of 5 |
| PD severity relative to national, like for like | 1.04 | 1.02 to 1.06 | 0.85 to 1.15 | 5 of 5 |
| COLL frequency relative to national, like for like | 1.31 | 1.25 to 1.37 | 0.85 to 1.45 | 5 of 5 |
| COLL severity relative to national, like for like | 0.91 | 0.89 to 0.92 | 0.85 to 1.15 | 5 of 5 |
| COMP frequency relative to national, like for like | 1.21 | 1.17 to 1.27 | 0.85 to 1.45 | 5 of 5 |
| COMP severity relative to national, like for like | 1.02 | 0.97 to 1.08 | 0.85 to 1.15 | 5 of 5 |
| liability premium per insured car-year relative to Illinois, 2022-2024 | 1.03 | 1.00 to 1.05 | 0.90 to 1.30 | 5 of 5 |
| collision premium per insured car-year relative to Illinois, 2022-2024 | 0.85 | 0.82 to 0.87 | 0.80 to 1.20 | 5 of 5 |
| comprehensive premium per insured car-year relative to Illinois, 2022-2024 | 0.91 | 0.89 to 0.94 | 0.75 to 1.20 | 5 of 5 |
| 2022 loss ratio excluding catastrophes relative to its expected | 1.01 | 0.97 to 1.05 | 0.85 to 1.15 | 5 of 5 |
| 2023 loss ratio excluding catastrophes relative to its expected | 1.01 | 0.98 to 1.04 | 0.85 to 1.15 | 5 of 5 |
| 2024 loss ratio excluding catastrophes relative to its expected | 1.00 | 0.95 to 1.06 | 0.85 to 1.15 | 5 of 5 |
| 2025 loss ratio excluding catastrophes relative to its expected | 0.98 | 0.94 to 1.03 | 0.85 to 1.15 | 5 of 5 |
| 2022 expected loss ratio (answer key) plus catastrophes vs industry | 80.2% | 79.5% to 81.0% | 74.0% to 85.0% | 5 of 5 |
| 2023 expected loss ratio (answer key) plus catastrophes vs industry | 77.3% | 76.6% to 78.1% | 68.0% to 80.0% | 5 of 5 |
| 2024 expected loss ratio (answer key) plus catastrophes vs industry | 67.1% | 65.8% to 68.0% | 59.0% to 70.0% | 5 of 5 |
| 2025 expected loss ratio (answer key) plus catastrophes vs industry | 63.5% | 62.7% to 64.0% | 55.0% to 67.0% | 5 of 5 |
| overall loss ratio | 70.6% | 68.9% to 72.2% | 62.0% to 76.0% | 5 of 5 |
| first month's exposure relative to the first year's average | 0.98 | 0.97 to 0.98 | 0.85 to 1.15 | 5 of 5 |
| share of drivers with no violation in 3 years | 88.4% | 88.3% to 88.5% | 78.0% to 90.0% | 5 of 5 |
| share of drivers with no at-fault accident in 3 years | 93.3% | 93.2% to 93.6% | 86.0% to 95.0% | 5 of 5 |
| annualized policy retention | 81.1% | 80.9% to 81.3% | 78.0% to 90.0% | 5 of 5 |
| new business expected loss ratio above renewals (points) | 9.69 | 9.13 to 10.07 | 5.00 to 16.00 | 5 of 5 |
| spread of expected loss ratio across agencies with 500+ car-years (90th less 10th percentile, points) | 15.08 | 13.98 to 15.78 | 6.00 to 25.00 | 5 of 5 |
| quotes in February to April relative to October to December | 1.20 | 1.20 to 1.21 | 1.08 to 1.40 | 5 of 5 |
| conversion after a rate increase relative to before it | 0.81 | 0.78 to 0.84 | 0.60 to 0.92 | 5 of 5 |
| terms with a claim end the policy more often than terms without (ratio) | 1.57 | 1.55 to 1.59 | 1.20 to 1.70 | 5 of 5 |
| share of non-renewals that are the company's decision | 7.7% | 7.4% to 7.8% | 3.0% to 15.0% | 5 of 5 |
| renewal rate of exclusive-agent customers above direct customers (points) | 4.10 | 3.72 to 4.55 | 1.00 to 8.00 | 5 of 5 |
| share of paid bodily injury settlements that are whole-dollar amounts | 86.5% | 85.1% to 88.0% | 75.0% to 95.0% | 5 of 5 |
| crashes on Thursdays and Fridays relative to Sundays and Mondays | 1.15 | 1.11 to 1.19 | 1.05 to 1.28 | 5 of 5 |

Every integrity check passes on every seed. The calibration figures that matter most for analysis are the
frequencies, severities and loss ratios; their spread across seeds is claim luck on a book of this size, and it
is the yardstick for any difference a case study finds between segments of one build.

## 3. Tail and joint diagnostics

| figure | mean | range | published | source |
|---|--:|--:|--:|--:|
| total-loss share, paid collision and comprehensive claims (glass apart) | 27.8% | 27.2% to 28.1% | 22.1% (2024), 22.8% (2025) | CCC Crash Course, US: all appraised vehicle claims |
| total-loss share, paid collision claims | 32.0% | 31.3% to 32.5% | - | no US figure for collision alone |
| total losses on cars 7+ model years old | 79.3% | 78.7% to 80.4% | 72% | CCC Crash Course, US, 2025 |
| average value of cars paid as total losses ($) | 10,587 | 10,286 to 10,811 | 13,400 to 13,700 | CCC Crash Course, US, 2024-25 (used in setting values) |
| closed liability and medical payments claims without payment | 43.1% | 42.4% to 43.4% | about 45% | WSJ analysis of NAIC filings, 2025 (tuned) |
| closed collision and comprehensive claims without payment | 15.3% | 14.8% to 15.5% | just under 25% | WSJ analysis of NAIC filings, 2025 (tuned) |
| closed collision claims without payment | 22.5% | 22.3% to 22.6% | - | (collision alone) |
| average age of insured cars in force, last full year (years) | 10.67 | 10.64 to 10.70 | 12.6 (2024), 12.8 (2025) | S&P Global Mobility, US light vehicles in operation |
| share of claim cost in the costliest 1% of risk rows with a claim | 16.7% | 16.5% to 16.9% | - | no US figure on these terms |
| coefficient of variation of claim cost per risk row with a claim | 2.20 | 2.15 to 2.28 | - | no US figure on these terms |
| bodily injury claimants paid the full per-person limit | 21.1% | 19.4% to 22.1% | - | no public US figure |
| bodily injury paid per claimant, median ($) | 17,545 | 16,750 to 17,954 | - | no public US figure |
| bodily injury paid per claimant, 90th percentile ($) | 52,110 | 50,000 to 58,550 | - | no public US figure |
| bodily injury paid per claimant, 99th percentile ($) | 116,040 | 100,000 to 140,000 | - | no public US figure |

What they show:

- **Total losses are too common, and on older, cheaper cars.** About 28% of paid collision and comprehensive
  claims (glass apart) are total losses, against 22.1% to 22.8% of CCC's appraisals; 79% of total losses are
  on cars seven or more model years old (CCC: 72%), and the average car written off is worth about $10,600
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
| BI | 0-3 months | 863 | 1.58 (1.45-1.67) | 0.00 (0.00-0.00) | 0.00 (0.00-0.00) | 2.93 (2.85-3.09) | 15% (14%-17%) |
| BI | 3-12 months | 922 | 1.14 (1.09-1.17) | 0.00 (0.00-0.00) | 0.93 (0.88-0.95) | 1.89 (1.81-1.95) | 50% (50%-51%) |
| BI | 1-2 years | 229 | 1.18 (1.15-1.23) | 0.28 (0.00-0.72) | 1.11 (1.10-1.13) | 1.76 (1.68-1.82) | 83% (80%-88%) |
| BI | over 2 years | 64 | 1.12 (1.07-1.16) | 0.77 (0.67-0.88) | 1.11 (1.06-1.16) | 1.50 (1.42-1.54) | 90% (87%-96%) |
| BI | all ages | 2,078 | 1.23 (1.20-1.26) | 0.00 (0.00-0.00) | 0.62 (0.55-0.70) | 2.06 (2.00-2.12) | 41% (40%-41%) |
| PD | 0-3 months | 411 | 1.15 (1.11-1.19) | 0.00 (0.00-0.00) | 0.88 (0.79-0.95) | 2.23 (2.10-2.33) | 54% (51%-56%) |
| PD | 3-12 months | 12 | 1.02 (0.99-1.08) | 0.60 (0.06-0.92) | 1.00 (0.97-1.06) | 1.26 (1.17-1.38) | 93% (77%-100%) |
| PD | all ages | 423 | 1.15 (1.11-1.19) | 0.00 (0.00-0.00) | 0.89 (0.83-0.96) | 2.18 (2.07-2.30) | 55% (52%-57%) |
| UM | 0-3 months | 53 | 1.65 (1.33-1.95) | 0.01 (0.00-0.06) | 0.88 (0.65-1.01) | 4.75 (3.48-6.34) | 33% (31%-35%) |
| UM | 3-12 months | 77 | 1.17 (1.04-1.28) | 0.61 (0.42-0.75) | 1.17 (1.10-1.24) | 2.02 (1.94-2.11) | 82% (79%-85%) |
| UM | 1-2 years | 26 | 1.11 (1.06-1.15) | 0.92 (0.81-0.98) | 1.17 (1.13-1.22) | 1.70 (1.58-1.86) | 95% (91%-100%) |
| UM | over 2 years | 6 | 1.05 (0.84-1.16) | 0.90 (0.75-1.05) | 1.07 (1.00-1.21) | 1.42 (1.26-1.74) | 95% (75%-100%) |
| UM | all ages | 162 | 1.25 (1.10-1.40) | 0.20 (0.00-0.45) | 1.14 (1.05-1.17) | 2.42 (2.25-2.76) | 69% (65%-73%) |
| MED | 0-3 months | 84 | 1.14 (1.09-1.23) | 0.30 (0.25-0.34) | 1.00 (1.00-1.00) | 2.32 (2.03-2.64) | 66% (61%-73%) |
| MED | 3-12 months | 27 | 1.13 (1.01-1.28) | 0.73 (0.56-0.92) | 1.08 (0.99-1.18) | 1.73 (1.27-2.69) | 90% (83%-94%) |
| MED | 1-2 years | 1 | 1.00 (1.00-1.00) | 1.00 (1.00-1.00) | 1.00 (1.00-1.00) | 1.00 (1.00-1.00) | 100% (100%-100%) |
| MED | all ages | 111 | 1.14 (1.08-1.21) | 0.33 (0.28-0.40) | 1.01 (1.00-1.05) | 2.17 (1.72-2.51) | 72% (67%-77%) |
| COLL | 0-3 months | 540 | 1.03 (0.98-1.06) | 0.00 (0.00-0.00) | 0.95 (0.89-1.00) | 2.54 (2.22-2.77) | 52% (49%-55%) |
| COLL | 3-12 months | 16 | 1.03 (0.98-1.11) | 0.50 (0.00-0.82) | 1.00 (0.81-1.08) | 1.29 (1.14-1.47) | 91% (77%-100%) |
| COLL | 1-2 years | 2 | 1.01 (1.01-1.01) | 1.00 (1.00-1.00) | 1.02 (1.02-1.02) | 1.03 (1.03-1.03) | 100% (100%-100%) |
| COLL | all ages | 556 | 1.03 (0.98-1.06) | 0.00 (0.00-0.00) | 0.96 (0.91-1.00) | 2.49 (2.20-2.69) | 53% (51%-56%) |
| COMP | 0-3 months | 257 | 1.25 (1.22-1.37) | 0.01 (0.00-0.06) | 0.86 (0.74-0.97) | 2.99 (2.72-3.14) | 48% (46%-50%) |
| COMP | 3-12 months | 10 | 0.72 (0.43-0.87) | 0.08 (0.00-0.39) | 0.56 (0.35-0.72) | 1.04 (0.78-1.24) | 55% (36%-78%) |
| COMP | all ages | 266 | 1.25 (1.21-1.37) | 0.01 (0.00-0.06) | 0.83 (0.72-0.96) | 2.88 (2.69-3.08) | 48% (47%-50%) |
| RENT | 0-3 months | 318 | 0.93 (0.90-1.00) | 0.39 (0.34-0.46) | 0.94 (0.91-1.00) | 1.58 (1.39-1.71) | 79% (72%-82%) |
| RENT | 3-12 months | 7 | 0.99 (0.96-1.01) | 0.88 (0.84-0.92) | 0.99 (0.94-1.03) | 1.06 (1.04-1.11) | 100% (100%-100%) |
| RENT | all ages | 325 | 0.93 (0.90-1.00) | 0.40 (0.34-0.48) | 0.94 (0.92-1.00) | 1.56 (1.38-1.69) | 79% (72%-83%) |
| TOW | 0-3 months | 36 | 0.93 (0.92-0.95) | 0.82 (0.72-0.91) | 1.00 (1.00-1.00) | 1.00 (1.00-1.00) | 96% (94%-98%) |
| TOW | all ages | 36 | 0.93 (0.92-0.95) | 0.82 (0.72-0.91) | 1.00 (1.00-1.00) | 1.00 (1.00-1.00) | 96% (94%-98%) |

Reserve reviews raise the reserve about as often as they lower it, at every age. Property claims open at a
year-end later paid within about a quarter of what was reserved for them in aggregate (collision 1.03,
comprehensive 1.25, property damage 1.15); rental reserves are a little redundant. Young injury reserves are short, by design: early injury
estimates average about 86% of ultimate and many injury claimants present or grow later, so bodily injury
incurred develops upward as in industry triangles. Individual features scatter widely (most claims either
close for nothing or settle well away from the reserve), which is what case reserves look like. They are,
though, the generator's draws around the eventual outcome rather than an adjuster's reading of a file, so their
errors are better behaved than real ones: no reserve is ever set far off for a reason a later fact reveals.

Reserve reviews, by age at the review: the share raising and the share lowering the reserve (cells with
fewer than 20 reviews left out).

| coverage | age | reviews | up | down |
|---|---|--:|--:|--:|
| BI | 0-3 months | 1,610 | 54% (53%-55%) | 46% (45%-47%) |
| BI | 3-12 months | 4,105 | 55% (54%-56%) | 45% (44%-46%) |
| BI | 1-2 years | 1,044 | 58% (57%-60%) | 42% (40%-43%) |
| BI | over 2 years | 309 | 59% (55%-61%) | 41% (39%-45%) |
| PD | 0-3 months | 2,462 | 47% (46%-48%) | 53% (52%-54%) |
| PD | 3-12 months | 55 | 47% (39%-55%) | 53% (45%-61%) |
| UM | 0-3 months | 112 | 47% (40%-58%) | 53% (42%-60%) |
| UM | 3-12 months | 338 | 56% (54%-61%) | 44% (39%-46%) |
| UM | 1-2 years | 119 | 60% (55%-64%) | 40% (36%-45%) |
| UM | over 2 years | 23 | 61% (48%-72%) | 39% (28%-52%) |
| MED | 0-3 months | 259 | 40% (36%-43%) | 60% (57%-64%) |
| MED | 3-12 months | 92 | 57% (54%-59%) | 43% (41%-46%) |
| COLL | 0-3 months | 2,635 | 53% (52%-55%) | 47% (45%-48%) |
| COLL | 3-12 months | 36 | 67% (54%-78%) | 33% (22%-46%) |
| COMP | 0-3 months | 1,111 | 55% (53%-59%) | 45% (41%-47%) |
| COMP | 3-12 months | 5 | 51% (20%-78%) | 49% (22%-80%) |
| RENT | 0-3 months | 2,334 | 44% (43%-46%) | 56% (54%-57%) |
| RENT | 3-12 months | 42 | 47% (42%-55%) | 53% (45%-58%) |

## 5. What is not benchmarked

Severity percentiles, limit-hit rates and the concentration of cost in the largest claims have no published US
figure on terms this data can match; section 3 reports them without a target. How variables depend on each other
(tenure and channel, age and mileage, value and total loss, claims and retention) is assumed in the generator and
reported, not validated, apart from the few relationships above. Model performance on held-out policies or later
years is left to the case studies: the data supports both splits (policy and date keys on every row).
