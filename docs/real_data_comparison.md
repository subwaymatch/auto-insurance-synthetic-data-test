# How the synthetic data compares with a real motor portfolio

This note checks whether the synthetic Chicago book looks like real insurance data. The benchmark is
"Dataset of an actual motor vehicle insurance portfolio" (Lledó and Pavía, Mendeley Data 2024, CC BY 4.0),
kept in [`real_data/mendeley_motor_portfolio/`](../real_data/mendeley_motor_portfolio/README.md). It covers a
non-life insurer, almost certainly Spanish, from November 2015 to December 2018: 105,555 rows, one per
vehicle contract per annual period.

Every figure below comes from one script. Section numbers like "§6" refer to its report:

```bash
python scripts/compare_real_data.py --synthetic output --real real_data/mendeley_motor_portfolio
```

The synthetic figures are from the default run (seed 20250101, 43,368 policies, 1 January 2022 to 31 December
2026), generated after the vehicle catalogue, fleet age, telematics and name changes described in the changelog
and the fixes in [review_response.md](review_response.md). An earlier run of the same script
on the previous generator (30,000 policies) gave the figures marked "was" where they differ materially.

## Verdict

**The synthetic data is useful and looks realistic where a fair comparison is possible, with four gaps worth
fixing.** The two books come from different countries, currencies, products and years, so levels (how many
claims, how many dollars) cannot be compared. What can be compared is the *shape* of things: how risk changes
with the driver, vehicle and policy, how claim costs and premiums spread, and how customers leave.

**Where it looks realistic**

- **Risk relationships that both books record point the same way, with similar strength.** Drivers under 25
  claim 1.37 times the book average in the real data and 1.29 times in the synthetic (was 1.22). Drivers
  licensed under five years claim 1.37 and 1.38 times. Urban vehicles claim 1.14 and 1.13 times, and frequency
  rises with vehicle value in both (§6).
- **Claim costs are skewed in the same way up to the 99th percentile.** The 90th percentile is 5.5 times the
  median in the real data and 6.7 in the synthetic, and the 99th percentile is 28.8 and 29.1 times (§4).
- **Premiums spread in a similar way**, a little wider in the synthetic book, as expected with US territory
  and credit rating (coefficient of variation 0.41 real, 0.48 synthetic; §5).
- **Loss ratios and retention are in a plausible range.** Real mature years run 57% to 102% (78% overall);
  synthetic years run 61% to 80% (68% overall; §5). The real book loses 25% of contracts a year and the
  synthetic 17.1%, which is in line with US retention (§8).
- **The premium ranks risk.** On the synthetic book it captures most of the ranking that the answer key's true
  expected loss can achieve (Gini 0.215 against 0.251 on claim counts; §7).
- **The fleet's age is now realistic for Chicago.** Vehicles are drawn from a catalogue of every make, model
  and model year since 1997, weighted by Chicago crash records, and their ages are tuned to the same records:
  9.2 years on average across vehicle-terms, 39% ten or more years old (was 7.6 years and 29%). The real
  Spanish book's vehicles are older still (11.2 years, 65%), as Spain's fleet is; the US average is about 12.6
  years (S&P Global Mobility, 2024) and Chicago's crash-involved personal vehicles average 9.4 to 10.2 (§2).

**Where it differs materially**

1. **Factors that both books share carry less predictive signal.** The same simple frequency model, fitted on
   the nine factors both books record, ranks held-out real data with a Gini of 0.22. That rises to 0.25 using
   2017 periods alone, where no claim can be counted twice. On held-out synthetic data the Gini is 0.16 (was
   0.12). Adding the US rating factors (insurance score, violations, accidents, territory) raises it to 0.19
   (§7). The gap comes from three effects that are strong in the real data and absent from the synthetic:
   - **Payment method.** Half-yearly payers claim 1.61 times as often as annual payers, other factors held
     equal; synthetic instalment payers claim 1.03 times as often.
   - **Tenure.** Customers of 10 or more years claim 0.69 times as often as those of under two years in the
     real data, other factors held equal, and 0.98 times as often in the synthetic.
   - **Channel.** Real broker business runs 12% above the book's average frequency and 20% above its average
     loss cost; the synthetic book shows no difference by channel.
2. **Claims do not drive customers away enough.** In the real data a contract with a claim is 1.45 times as
   likely to end as one without (32.5% against 22.4%); in the synthetic book only 1.12 times (18.9% against
   16.9%; §8). Only 121 of the 12,230 synthetic non-renewals are the company's decision. This weak selection
   is also why synthetic tenure carries no protective effect.
3. **The very largest claims are smaller.** The costliest 1% of claim-years make up 24% of real claim cost but
   16% of synthetic cost (coefficient of variation 4.4 against 2.2; §4). Part of this is structural: US
   liability limits cap claims, while Spanish compulsory injury cover is effectively unlimited.
4. **The synthetic data is spotless, and real data is not.** The real extract has non-renewal "stub" rows
   with premium but no cover (14%), dates out of order, `NA` text, zeros standing for missing values, and
   fields taken at extraction time that leak later information into earlier rows (§10). The synthetic tables
   have none of these, so they cannot teach data cleaning.

Frequency falls with vehicle age in the synthetic book (0.61 for 15 or more years) but not in the real one
(1.02). Most of that is coverage: older synthetic cars drop collision and comprehensive cover. Synthetic
liability claims alone rise slightly with age (1.06), as real claims do (§6).

There is also a smaller visibility gap: the synthetic tables record only renewals that were accepted, so
the price behind a non-renewal cannot be seen. The real data shows a clear response to price: 11% of
contracts leave after a premium cut of more than 5%, against 28.5% after an increase of 10% or more (§8).

**What the real data cannot tell us.** The real claim counts have a defect of their own (§10). Within a
contract, `N_claims_year` almost never rises from one period to the next (98.8% of consecutive periods).
A claim-free period is followed by one with a claim only 1.5% of the time, although 26% of periods have a
claim. Claim frequency also halves between periods starting in 2016 and 2017, which nothing in the data
explains. So the real data cannot benchmark claim-count overdispersion, year-to-year claim persistence or the
frequency level, and this note does not judge the synthetic data on them. The synthetic book's own figures
(claim counts very close to Poisson; frequency after a claim 1.27 times frequency after none) are plausible
but unverified here.

### Suggested changes to the generator, most valuable first

| # | Change | Why (evidence) | Status |
|---|---|---|---|
| 1 | Make attrition respond to claims: customers with a recent claim or surcharge shop more, and the company non-renews repeat at-fault drivers. Tenure then becomes protective through selection, as in real books. | Real: leaving after a claim is 1.45 times as likely, and 10+ year customers claim 0.69 times as often. Synthetic: 1.12 times and 0.98 times, and only 121 company non-renewals (§6, §7, §8). | Open |
| 2 | Let payment plan carry real risk, for example through the latent risk factor or financial stress beyond the insurance score. | Real half-yearly payers claim 1.61 times as often, other factors held equal; synthetic instalment payers claim 1.03 times as often (§7). The synthetic paid-in-full discount has nothing behind it. | Open |
| 3 | Age the fleet, keeping physical damage take-up falling with age. | Was 7.6 years with 29% aged 10+ (§2). | Done: tuned to Chicago crash-involved personal vehicles (about 10 years in force, 41% aged 10+) |
| 4 | Record renewal offers, including those declined: the offered premium, the change and the outcome. | The real data supports price-elasticity exercises (11% to 28.5% leaving across price changes); the synthetic tables cannot (§8). | Open |
| 5 | Add a modest channel effect, for example selection on independent-agent business. | Real broker business: 1.12 times the book's average frequency and 1.20 times its average loss cost. Synthetic: none (§6). | Open |
| 6 | Check the bodily injury severity tail against US large-loss data, such as the share of claims at the policy limit. | The top 1% of claim-years make up 24% of real cost against 16% of synthetic; limits explain part of this (§4). | Open |
| 7 | Optionally, a "messy extract" mode that injects documented defects (stub rows, out-of-order dates, `NA` text, zeros for missing values, snapshot fields) and logs each one in the answer key. | Real extracts need this cleaning (§10); the synthetic tables are perfectly clean. | Open |

Things *not* to change on this evidence: the frequency level (the real counts include breakdown assistance
calls and have the defect above), claim-count dispersion (the same defect), and the coverage mix (the
products differ; §9).

## Evidence

### The two books (§1)

| | Real | Synthetic |
|---|---|---|
| Market | Spain (inferred), euros | Chicago area, US dollars |
| Years | Annual periods starting Nov 2015 to Nov 2018 | 1 Jan 2022 to 31 Dec 2026 |
| Grain | One row per vehicle contract per annual period | 23 linked tables; rolled up to one row per policy term and vehicle |
| Size | 105,555 rows, 53,502 contracts | 389,510 vehicle-terms, 43,365 policies, 184,498 vehicle-years |
| Vehicles | 79% cars, 13% vans, 8% motorbikes, 1% agricultural | Private passenger cars and light trucks |
| Terms | 12 months | 6 months (66% of exposure) or 12 months |
| Used here | Passenger cars, periods starting by end of 2017: 46,376 rows, 45,197 vehicle-years | All vehicle-terms with exposure in the extract |

How the real rows were prepared: 14,836 rows (14.1%) have a lapse date on or before their own start. Nearly
all of them are periods the contract never entered because it was not renewed, so they are dropped. Exposure
ends at the lapse date, the next renewal or 31 December 2018, whichever comes first, because claim counts for
periods starting in 2018 fall away as if observation ended then. Real "urban" (a town of more than 30,000
people, judged on traffic) is matched to the City of Chicago in the synthetic book (28% and 24% of
exposure).

### Who is insured (§2)

| | Real | Synthetic |
|---|---|---|
| Mean driver age | 46.7 | 51.0 |
| Under 25 / 65 and over | 2.1% / 9.5% | 5.7% / 24.0% |
| Median years licensed | 23.0 | 33.6 |
| Mean vehicle age / share 10+ years | 11.2 / 65% | 9.2 / 39% |
| More than one driver | 14% | 70% |
| Pays in instalments | 34% | 63% |
| Median years with the company | 5 | 3 |

Most differences are market differences. US households list every driver; Spanish contracts declare a second
regular driver only if there is one. Monthly payment is the US norm; the real data's alternative is
half-yearly. The real driver is the policyholder, the synthetic one is the vehicle's rated driver. The
remaining vehicle age gap reflects the two markets: the synthetic fleet is tuned to Chicago's.

### Claim frequency (§3)

| Period start | Real claims per vehicle-year | Synthetic |
|---|---|---|
| 2015 / 2016 | 0.84 / 0.82 | |
| 2017 / 2018 (cut off) | 0.45 / 0.31 | |
| 2022 to 2025 | | 0.089 to 0.097 |

Levels differ by a factor of four to eight. Real counts include breakdown assistance, which is 56% of
claim-type lines (§9), glass and legal claims, and they carry the counting defect described above. Synthetic
counts are claims with a cost (0.110 per vehicle-year if claims closed without payment are included). On
full-year rows, 72% of real vehicles have no claim and 8% have three or more; for synthetic 12-month terms
the figures are 93.5% and under 0.1%.

### Claim cost (§4): vehicle-years with a claim

| | Real | Synthetic |
|---|---|---|
| Median | EUR 311 | USD 2,670 |
| Coefficient of variation | 4.39 | 2.18 |
| 90th percentile / median | 5.5 | 6.7 |
| 99th percentile / median | 28.8 | 29.1 |
| Share of cost in the costliest 1% / 10% | 23.8% / 58.7% | 16.3% / 55.7% |

### Premium and loss ratio (§5)

| | Real (annual premium) | Synthetic (annual rate) |
|---|---|---|
| Median | EUR 298 | USD 931 |
| Coefficient of variation | 0.41 | 0.48 |
| 90th / 10th percentile | 2.21 | 3.23 |
| 99th percentile / median | 2.85 | 2.88 |

Loss ratio by period start year: real 101.5% (2015), 98.3% (2016) and 56.9% (2017), 78.4% over all three;
synthetic 77.9% (2022), 79.7% (2023), 60.6% (2024), 65.3% (2025) and 60.9% (2026), 68.3% over all years.
The real drop between 2016 and 2017 matches the unexplained drop in claim counts.

### Risk relationships (§6 and §7)

A *relativity* is a group's claim frequency divided by the book average: 1.37 means 37% more claims per
vehicle-year than average. The "model" columns are multipliers from the Poisson model in §7, which holds the
other factors equal; they compare each level with the first level shown.

| Factor | Level | Real relativity | Synthetic relativity | Real model | Synthetic model |
|---|---|---|---|---|---|
| Driver age | under 25 / 65+ | 1.37 / 0.72 | 1.29 / 0.87 | 1 / 0.86 | 1 / 0.69 |
| Years licensed | 0-4 / 30+ | 1.37 / 0.89 | 1.38 / 0.94 | 1 / 0.76 | 1 / 0.95 |
| Vehicle value | lowest / highest fifth | 0.81 / 1.21 | 0.62 / 1.19 | 1 / 1.58 | 1 / 1.45 |
| Urban | yes | 1.14 | 1.13 | 1.15 | 1.21 |
| Vehicle age | 0-2 / 15+ years | 0.87 / 1.02 | 1.19 / 0.61 | 1 / 1.50 | 1 / 0.72 |
| Pays in instalments | yes | 1.41 | 1.01 | 1.61 | 1.03 |
| Years with the company | 0-1 / 10+ | 1.03 / 0.70 | 1.03 / 0.98 | 1 / 0.69 | 1 / 0.98 |
| Channel | broker (independent agent) | 1.12 | 0.98 | 1.02 | 0.99 |
| More than one driver | yes | 1.22 | 1.03 | 1.28 | 1.08 |

The last row is not comparable: the books define it differently.

**How much signal there is (§7).** The *Gini* score measures how well a ranking puts claims on the risks it
rates highest: 0 means no better than random, and higher is better. The top/bottom ratio is the claim
frequency of the riskiest tenth divided by that of the safest tenth.

| Ranked by | Real Gini | Real top/bottom | Synthetic Gini | Synthetic top/bottom |
|---|---|---|---|---|
| Premium | 0.129 | 1.9 | 0.215 | 4.7 |
| True expected loss (answer key) | | | 0.251 | 6.0 |
| Model on the nine shared factors, held-out data | 0.222 (2017 only: 0.253) | 4.0 | 0.161 | 3.0 |
| Same model plus US rating factors | | | 0.188 | 3.1 |

The real insurer's premium ranks claims less well than a nine-factor model does, which suggests that payment
method, vehicle age and tenure were not fully priced. The synthetic premium ranks well because the rating plan
is fitted to the true costs (see the README's "Assumptions and limits").

### Retention (§8)

| | Real | Synthetic |
|---|---|---|
| Contracts or policies lost per year | 25.3% | 17.1% |
| of which mid-term cancellation / not renewed | 5.3% / 20.0% | 6.9% / 10.9% |
| Lost in a period with a claim / without | 32.5% / 22.4% | 18.9% / 16.9% |

Real renewal offers and how many were declined: price cut of more than 5%, 11.1%; cut of 0% to 5%, 13.1%;
rise of 0% to 2%, 18.4%; 2% to 5%, 21.7%; 5% to 10%, 26.4%; 10% or more, 28.5%. The synthetic tables
cannot produce this table (suggestion 4).

### What a claim is (§9)

Real claim types (a sample of rows with claims) are dominated by number by breakdown assistance (56% of
lines, 10% of cost). By cost, *negligence*, probably liability to third parties, is 46%. Synthetic cost is
35% bodily injury liability, 27% property damage liability, 20% collision and 12% comprehensive. The products
differ, so this section explains why frequency levels cannot be compared; it does not suggest a fix.

### Data quality (§10)

| Real data | Count |
|---|---|
| Non-renewal stub rows (lapse date equals the period start) | 14,432 |
| Lapse date before the period start | 404 |
| Contract start after the period start | 68 |
| Licence issued after the period start | 31 |
| Policyholder aged 95 or more | 11 |
| `Power` = 0 (all with `Type_fuel` = `NA`) | 1,764 |
| `Length` = `NA` | 10,329 |
| `Lapse` above 0 with no lapse date (it counts the customer's other policies too) | 2,376 |
| Claim history, tenure and vehicle value identical on every row of a contract (snapshot fields) | 100% of multi-row contracts |
| `N_claims_history` at least the contract's claims in all rows (includes later claims) | 95.5% of rows |
| Claim counts that do not rise from one period to the next | 98.8% of consecutive pairs |

The equivalent synthetic checks find nothing, and `validate.py` runs a much larger set of integrity checks
on every build.

## Limits of this comparison

- Different market, currency, products, years (2015 to 2018 against 2022 to 2026) and legal setting (Spanish
  compulsory third-party cover against US limits and optional physical damage cover).
- One real insurer and one synthetic seed. Synthetic results move by a few points from seed to seed.
- The real file is a simplified single-table extract with undocumented counting rules (§10), so it is a
  sanity check, not a gold standard. A second real source with clean annual claim counts would be needed to
  judge claim-count dispersion and persistence.
- Factors are matched as closely as the fields allow: years licensed, payment method, channel, "urban" and
  "more than one driver" are approximate equivalents, not identical definitions.
