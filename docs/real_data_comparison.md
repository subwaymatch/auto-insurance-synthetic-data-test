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
2026), generated after the realism changes described in the changelog (hidden household stability, filed
discounts, a new-customer effect, channel and agency effects, the working calendar, billing, and then a
market cycle, claims that cost customers, and physical damage premiums and take-up at Illinois levels).
"Was" marks the figure before the first of those rounds of changes, or before the second where it says so.

## Verdict

**The synthetic data is useful and looks realistic where a fair comparison is possible. Of the gaps this note
first found, claims now drive customers away about as they do in the real book, and payment plan, tenure and
channel carry risk, though less; two remain (the largest claims, and the cleanliness of the data).** The two books come from different countries, currencies, products and years, so levels (how many
claims, how many dollars) cannot be compared. What can be compared is the *shape* of things: how risk changes
with the driver, vehicle and policy, how claim costs and premiums spread, and how customers leave.

**Where it looks realistic**

- **Risk relationships that both books record point the same way, with similar strength.** Drivers under 25
  claim 1.37 times the book average in the real data and 1.28 times in the synthetic (the same as before). Drivers
  licensed under five years claim 1.37 and 1.37 times. Urban vehicles claim 1.14 and 1.15 times, and frequency
  rises with vehicle value in both (§6).
- **Claim costs are skewed in the same way up to the 99th percentile.** The 90th percentile is 5.5 times the
  median in the real data and 6.3 in the synthetic, and the 99th percentile is 28.8 and 24.5 times (§4).
- **Premiums spread in a similar way**, wider in the synthetic book, as expected with US territory and credit
  rating and a full set of discounts (coefficient of variation 0.41 real, 0.53 synthetic, was 0.48; §5).
- **Loss ratios and retention are in a plausible range.** Real mature years run 57% to 102% (78% overall);
  synthetic years run 62% to 79% (67% overall; §5). The real book loses 25% of contracts a year and the
  synthetic 18.7%, which is in line with US retention (§8).
- **A claim costs customers in both books.** A real contract with a claim in the period is 1.45 times as
  likely to end as one without (32.5% against 22.4%); a synthetic one 1.40 times (25.1% against 17.9%; was
  1.06 before the second round). 1,000 of the 11,500 synthetic non-renewals are the company's decision (was
  165 of 10,958).
- **The premium ranks risk.** On the synthetic book it captures most of the ranking that the answer key's true
  expected loss can achieve (Gini 0.193 against 0.239 on claim counts; §7). The gap between the two is wider than
  it first was (0.211 against 0.247) because the plan now files round discounts and cannot see household
  stability, the new-customer effect or an agency's book quality. Both are lower than before the second round
  (0.213 and 0.255): comprehensive claims, which owe little to the driver, are now a larger share of all claims.
- **Customers who pay in instalments, newer customers and independent-agent business now run worse**, as in
  the real book, though less strongly (below).
- **The fleet's age is now realistic for Chicago.** Vehicles are drawn from a catalogue of every make, model
  and model year since 1997, weighted by Chicago crash records, and their ages are tuned to the same records:
  9.3 years on average across vehicle-terms, 39% ten or more years old (was 7.6 years and 29%). The real
  Spanish book's vehicles are older still (11.2 years, 65%), as Spain's fleet is; the US average is about 12.6
  years (S&P Global Mobility, 2024) and Chicago's crash-involved personal vehicles average 9.4 to 10.2 (§2).

**Where it differs materially**

1. **Factors that both books share carry less predictive signal.** The same simple frequency model, fitted on
   the nine factors both books record, ranks held-out real data with a Gini of 0.22. That rises to 0.25 using
   2017 periods alone, where no claim can be counted twice. On held-out synthetic data the Gini is 0.12 (was
   0.15). Adding the US rating factors (insurance score, violations, accidents, territory) raises it to 0.15
   (§7). Part of the shortfall is the claim mix: 29% of synthetic claims with a cost are comprehensive
   (glass, theft, weather), which the driver's characteristics barely predict. Three effects that are strong
   in the real data were absent from the synthetic and are now present, but weaker:
   - **Payment method.** Half-yearly payers claim 1.61 times as often as annual payers, other factors held
     equal; synthetic instalment payers claim 1.15 times as often (was 1.04).
   - **Tenure.** Customers of 10 or more years claim 0.69 times as often as those of under two years in the
     real data, other factors held equal, and 0.86 times as often in the synthetic (was 1.00).
   - **Channel.** Real broker business runs 12% above the book's average frequency and 20% above its average
     loss cost. Synthetic independent-agent business runs 2% above average frequency and 4% above average
     loss cost, and 8% above exclusive-agent business with other factors held equal (was no difference).
2. **The very largest claims are smaller.** The costliest 1% of claim-years make up 24% of real claim cost but
   15% of synthetic cost (coefficient of variation 4.4 against 2.1; §4). Part of this is structural: US
   liability limits cap claims, while Spanish compulsory injury cover is effectively unlimited.
3. **The synthetic data is spotless, and real data is not.** The real extract has non-renewal "stub" rows
   with premium but no cover (14%), dates out of order, `NA` text, zeros standing for missing values, and
   fields taken at extraction time that leak later information into earlier rows (§10). The synthetic tables
   have none of these, so they cannot teach data cleaning.

Frequency falls with vehicle age in the synthetic book (0.73 for 15 or more years, was 0.61) but not in the
real one (1.02). Most of that is coverage: fewer old synthetic cars carry collision and comprehensive cover
(37% of those 16 and older carry collision). Synthetic liability claims alone do not fall with age (1.08), as
real claims do not (§6).

The response to price can now be compared too: `renewal_offer` (added after the third external review)
records every renewal offer, declined ones included. The real data shows a clear response: 11% of contracts
leave after a premium cut of more than 5%, against 28.5% after an increase of 10% or more. Synthetic
customers respond only above about a 5% increase: 4.5% to 4.8% leave after anything from a cut of more than
5% to a 5% rise, 6.2% after 5% to 10% and 14.0% after 10% or more (§8). The synthetic response is weaker for
small changes and lower overall, in line with its lower attrition.

**What the real data cannot tell us.** The real claim counts have a defect of their own (§10). Within a
contract, `N_claims_year` almost never rises from one period to the next (98.8% of consecutive periods).
A claim-free period is followed by one with a claim only 1.5% of the time, although 26% of periods have a
claim. Claim frequency also halves between periods starting in 2016 and 2017, which nothing in the data
explains. So the real data cannot benchmark claim-count overdispersion, year-to-year claim persistence or the
frequency level, and this note does not judge the synthetic data on them. The synthetic book's own figures
(claim counts very close to Poisson; frequency after a claim 1.29 times frequency after none, and 1.42
before customers with claims began to leave: those who stay after a claim are a selected group, and those
with an at-fault claim leave most) are plausible but unverified here. A car with an at-fault claim is 1.6
times as likely to have another the following year.

### Suggested changes to the generator, most valuable first

| # | Change | Why (evidence) | Status |
|---|---|---|---|
| 1 | Make attrition respond to claims: customers with a recent claim or surcharge shop more, and the company non-renews repeat at-fault drivers. Tenure then becomes protective through selection, as in real books. | Real: leaving after a claim is 1.45 times as likely, and 10+ year customers claim 0.69 times as often. Synthetic: was 1.06 times and 0.84 times, with only 165 company non-renewals (§6, §7, §8). | Done: a claim since the last offer lowers the chance of renewing, an at-fault or second claim more, and the underwriting review non-renews half the policies with two at-fault accidents (or two major violations, or one of each) in three years. Leaving after a claim is now 1.40 times as likely and there are 1,000 company non-renewals. Tenure is protective through hidden household stability (0.86 times) |
| 2 | Let payment plan carry real risk, for example through the latent risk factor or financial stress beyond the insurance score. | Real half-yearly payers claim 1.61 times as often, other factors held equal; synthetic instalment payers claim 1.15 times as often (was 1.04; §7). | Partly done: household stability drives the payment plan, so the filed 6% paid-in-full discount now has risk behind it; the effect is weaker than in the real book |
| 3 | Age the fleet, keeping physical damage take-up falling with age. | Was 7.6 years with 29% aged 10+ (§2). | Done: tuned to Chicago crash-involved personal vehicles (about 10 years in force, 41% aged 10+) |
| 4 | Record renewal offers, including those declined: the offered premium, the change and the outcome. | The real data supports price-elasticity exercises (11% to 28.5% leaving across price changes); the synthetic `renewal_offer` table now does too, with a flatter response (4.5% to 14.0%; §8). | Done (`renewal_offer`) |
| 5 | Add a modest channel effect, for example selection on independent-agent business. | Real broker business: 1.12 times the book's average frequency and 1.20 times its average loss cost. Synthetic independent-agent business: 1.02 times, and 1.08 times exclusive-agent business with other factors equal (§6, §7). | Done: channels differ in risk and retention, and each agency has its own book quality |
| 6 | Check the bodily injury severity tail against US large-loss data, such as the share of claims at the policy limit. | The top 1% of claim-years make up 24% of real cost against 15% of synthetic; limits explain part of this (§4). | Open |
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
| Grain | One row per vehicle contract per annual period | 32 linked tables; rolled up to one row per policy term and vehicle |
| Size | 105,555 rows, 53,502 contracts | 374,979 vehicle-terms, 43,366 policies, 176,758 vehicle-years |
| Vehicles | 79% cars, 13% vans, 8% motorbikes, 1% agricultural | Private passenger cars and light trucks |
| Terms | 12 months | 6 months (66% of exposure) or 12 months |
| Used here | Passenger cars, periods starting by end of 2017: 46,376 rows, 45,197 vehicle-years | All vehicle-terms with exposure in the extract |

How the real rows were prepared: 14,836 rows (14.1%) have a lapse date on or before their own start. Nearly
all of them are periods the contract never entered because it was not renewed, so they are dropped. Exposure
ends at the lapse date, the next renewal or 31 December 2018, whichever comes first, because claim counts for
periods starting in 2018 fall away as if observation ended then. Real "urban" (a town of more than 30,000
people, judged on traffic) is matched to the City of Chicago in the synthetic book (28% and 25% of
exposure).

### Who is insured (§2)

| | Real | Synthetic |
|---|---|---|
| Mean driver age | 46.7 | 51.3 |
| Under 25 / 65 and over | 2.1% / 9.5% | 5.7% / 24.2% |
| Median years licensed | 23.0 | 34.0 |
| Mean vehicle age / share 10+ years | 11.2 / 65% | 9.3 / 39% |
| More than one driver | 14% | 70% |
| Pays in instalments | 34% | 56% |
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
| 2022 to 2025 | | 0.108 to 0.113 |

Levels differ by a factor of four to seven. Real counts include breakdown assistance, which is 56% of
claim-type lines (§9), glass and legal claims, and they carry the counting defect described above. Synthetic
counts are claims with a cost (0.127 per vehicle-year if claims closed without payment are included). On
full-year rows, 72% of real vehicles have no claim and 8% have three or more; for synthetic 12-month terms
the figures are 92.0% and under 0.1%.

### Claim cost (§4): vehicle-years with a claim

| | Real | Synthetic |
|---|---|---|
| Median | EUR 311 | USD 3,023 |
| Coefficient of variation | 4.39 | 2.06 |
| 90th percentile / median | 5.5 | 6.3 |
| 99th percentile / median | 28.8 | 24.5 |
| Share of cost in the costliest 1% / 10% | 23.8% / 58.7% | 15.4% / 53.3% |

### Premium and loss ratio (§5)

| | Real (annual premium) | Synthetic (annual rate) |
|---|---|---|
| Median | EUR 298 | USD 1,109 |
| Coefficient of variation | 0.41 | 0.53 |
| 90th / 10th percentile | 2.21 | 3.53 |
| 99th percentile / median | 2.85 | 3.15 |

Loss ratio by period start year: real 101.5% (2015), 98.3% (2016) and 56.9% (2017), 78.4% over all three;
synthetic 79.2% (2022), 67.5% (2023), 65.2% (2024), 62.1% (2025) and 63.2% (2026), 67.4% over all years.
The real drop between 2016 and 2017 matches the unexplained drop in claim counts.

### Risk relationships (§6 and §7)

A *relativity* is a group's claim frequency divided by the book average: 1.37 means 37% more claims per
vehicle-year than average. The "model" columns are multipliers from the Poisson model in §7, which holds the
other factors equal; they compare each level with the first level shown.

| Factor | Level | Real relativity | Synthetic relativity | Real model | Synthetic model |
|---|---|---|---|---|---|
| Driver age | under 25 / 65+ | 1.37 / 0.72 | 1.28 / 0.85 | 1 / 0.86 | 1 / 0.75 |
| Years licensed | 0-4 / 30+ | 1.37 / 0.89 | 1.37 / 0.94 | 1 / 0.76 | 1 / 0.79 |
| Vehicle value | lowest / highest fifth | 0.81 / 1.21 | 0.76 / 1.10 | 1 / 1.58 | 1 / 1.21 |
| Urban | yes | 1.14 | 1.15 | 1.15 | 1.25 |
| Vehicle age | 0-2 / 15+ years | 0.87 / 1.02 | 1.13 / 0.73 | 1 / 1.50 | 1 / 0.76 |
| Pays in instalments | yes | 1.41 | 1.07 | 1.61 | 1.15 |
| Years with the company | 0-1 / 10+ | 1.03 / 0.70 | 1.13 / 0.88 | 1 / 0.69 | 1 / 0.86 |
| Channel | broker (independent agent) | 1.12 | 1.02 | 1.02 | 1.08 |
| More than one driver | yes | 1.22 | 1.01 | 1.28 | 1.01 |

The last row is not comparable: the books define it differently.

**How much signal there is (§7).** The *Gini* score measures how well a ranking puts claims on the risks it
rates highest: 0 means no better than random, and higher is better. The top/bottom ratio is the claim
frequency of the riskiest tenth divided by that of the safest tenth.

| Ranked by | Real Gini | Real top/bottom | Synthetic Gini | Synthetic top/bottom |
|---|---|---|---|---|
| Premium | 0.129 | 1.9 | 0.193 | 3.8 |
| True expected loss (answer key) | | | 0.239 | 5.1 |
| Model on the nine shared factors, held-out data | 0.222 (2017 only: 0.253) | 4.0 | 0.121 | 2.3 |
| Same model plus US rating factors | | | 0.145 | 2.5 |

The real insurer's premium ranks claims less well than a nine-factor model does, which suggests that payment
method, vehicle age and tenure were not fully priced. The synthetic premium ranks well because most of the
rating plan is fitted to the true costs (see the README's "Assumptions and limits").

### Retention (§8)

| | Real | Synthetic |
|---|---|---|
| Contracts or policies lost per year | 25.3% | 18.7% |
| of which mid-term cancellation / not renewed | 5.3% / 20.0% | 8.9% / 10.8% |
| Lost in a period with a claim / without | 32.5% / 22.4% | 25.1% / 17.9% |

Real renewal offers and how many were declined: price cut of more than 5%, 11.1%; cut of 0% to 5%, 13.1%;
rise of 0% to 2%, 18.4%; 2% to 5%, 21.7%; 5% to 10%, 26.4%; 10% or more, 28.5%. Synthetic offers the company
made that reached their renewal date (`renewal_offer`), on the same bands: 4.5%, 4.6%, 4.6%, 4.8%, 6.2% and
14.0% (suggestion 4).

### What a claim is (§9)

Real claim types (a sample of rows with claims) are dominated by number by breakdown assistance (56% of
lines, 10% of cost). By cost, *negligence*, probably liability to third parties, is 46%. Synthetic cost is
30% bodily injury liability, 21% property damage liability, 28% collision and 16% comprehensive. The products
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
