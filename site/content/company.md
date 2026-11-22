---
title: The company
nav: 1
nav_title: Company
eyebrow: About Lakefront
lede: A small regional insurance group that writes personal auto insurance in the seven-county Chicago area, through independent agents, its own exclusive agents and direct.
description: Who Lakefront is: three underwriting companies, 134 agencies and two direct units, six claim offices, a telematics program, and five years of results from 2022 to 2026.
---

## At a glance

| | |
|---|---|
| Business | Personal auto insurance only: private passenger cars, SUVs, pickups and vans |
| Territory | Cook, DuPage, Lake, Will, Kane, McHenry and Kendall counties: 290 ZIP codes |
| Size | About 22,300 policies and 39,000 cars in force at the end of 2026, and some $51 million of premium a year: roughly 1% of the area’s household vehicles |
| History in the data | 1 January 2022 to 31 December 2026. 19,747 policies were already in force on the first day; 43,368 policies were written or renewed in all |
| Companies | Three underwriting companies, for preferred, standard and non-standard risks |
| Distribution | 120 independent agencies, 14 exclusive agents’ offices, and direct sales online and by phone |
| Claims | Six claim offices and 46 claims staff |

Read it as the Chicago-area book of a regional carrier, not a national one.

## Three underwriting companies

An insurance group often writes through several legally separate companies, each with its own rates, so that it can place customers of different risk with the company priced for them. Lakefront has three. Every policy belongs to one (`policy.company_id`), and each company’s books are kept separately in the general ledger.

| Company | Code | Tier | Who it insures |
|---|---|---|---|
| Lakefront Preferred Insurance Company | `LFP` | Preferred | Insurance score of 740 or more, a clean driving record and continuous prior insurance |
| Lakefront Mutual Automobile Insurance Company | `LFM` | Standard | Everyone the other two companies don’t take |
| Prairie Path Casualty Company | `PPC` | Non-standard | A poor driving record, an insurance score under 560, or no prior insurance together with a weak score or record |

The company’s three-letter code is part of every policy number: `0830512-LFM-47` is a Lakefront Mutual policy. See `underwriting_company`.

## How it sells

Customers reach Lakefront in three ways. The channel matters: it changes who buys, how much they pay in commission, and how long they stay.

**Independent agents.** 120 agencies that also sell other insurers’ policies. Most are small: half have 46 or fewer Lakefront policies in force, the largest has 495, and the largest tenth write over a third of the channel’s premium. Their comparative raters show them competitors’ prices, so their quotes record the best competing premium (`quote.competitor_annual_premium`). They earn 10% to 15% commission on new business and two or three points less on renewals, depending on the agency.

**Exclusive agents.** 14 offices that sell only Lakefront, each carrying its agent’s name. They average about 427 policies each and earn somewhat less commission.

**Direct.** Two in-house units, `Direct - Online` and `Direct - Contact Center`, which pay no commission.

Each agency has licensed producers (`producer`), and each month’s commission is settled on an agency statement (`agency_statement`), paid on the 15th of the following month.

<div class="in-the-data" markdown="1">
`agency` has one row per agency or direct unit, with its channel and commission rates. `policy.agency_id` and `policy.producer_id` record who sold each policy, and `premium_transaction` holds the commission on every transaction.
</div>

## What it sells

A Lakefront policy covers the household’s cars and drivers for six months (about two policies in three) or twelve. Each car can carry:

| Coverage | Options |
|---|---|
| Bodily injury and property damage liability | 25/50/20 (Illinois’ minimum), 50/100/50, 100/300/100, 250/500/100 or 500/500/250, in thousands of dollars |
| Uninsured and underinsured motorist bodily injury | Usually at the liability limits; some customers keep the 25/50 minimum |
| Medical payments | None, $1,000, $2,000, $5,000 or $10,000 |
| Collision | Deductible of $250, $500, $1,000 or $2,000 |
| Comprehensive | Deductible of $100, $250, $500 or $1,000, with optional full glass cover (no deductible for glass) |
| Rental reimbursement | A daily limit and a per-claim maximum |
| Towing and labor | Towing after a crash |

[How auto insurance works](/auto-insurance/#coverages) explains what each coverage pays for.

### Discounts and surcharges

The rating plan multiplies a base rate by factors for the driver, the car, where it is kept and the coverage chosen (see [How auto insurance works](/auto-insurance/#how-a-premium-is-set)). On top of those, Lakefront files these round-number discounts, as carriers do:

| Discount or surcharge | Amount |
|---|---|
| Multi-car | 10% off |
| Multi-policy (bundling another policy) | 8% off |
| Homeowner | 5% off |
| Paid in full | 6% off |
| Loyalty (tenure) | 2%, 4% and 6% off after one, three and six years |
| Good student | 10% off for a driver under 25 in full-time school with B grades |
| Married | 5% off |
| No prior insurance | 8% surcharge |
| Lakefront DriveCheck (telematics) | 5% for joining, then up to 30% depending on the driving score |

### Paying for it

Customers pay in full or by monthly installments, either by automatic bank draft (EFT) or by bill. Installments after the first carry a $2 fee by draft or $5 by bill; a payment more than five days late costs $10, and a returned draft $25. An unpaid installment leads to a past-due notice, then a notice of cancellation, and cover ends three to four weeks after the missed due date. See `billing_invoice` and `billing_receipt`.

## Lakefront DriveCheck

DriveCheck is Lakefront’s usage-based (telematics) program, of the kind most US insurers now run. It is offered when a policy is written and at every renewal. Members install a phone app, a plug-in device or a windshield beacon, and each car is scored from 1 to 100 on its miles, trips, hard braking, rapid acceleration, speeding, phone handling and late-night driving. Joining earns 5% off; at each renewal the score earns a discount from none (45 or below) to 30% (95 and above). A score never raises the premium.

About a fifth of new customers joined in 2022, rising to 30% by 2025, and enrolled cars grew from 14% of car-years in 2022 to 26% in 2026. See `telematics_enrollment` and `telematics_score`.

## How it handles claims

Each claim goes to the first office in this list that fits it (`claim.claim_office_id`):

| Office | Where | Handles |
|---|---|---|
| Catastrophe Response Team | Aurora | Claims from a catastrophe: hail, wind and flood events |
| Casualty and Injury Unit | Oak Brook | Claims with an injury |
| Total Loss and Theft Unit | Chicago | Stolen cars and total losses |
| Express and Glass Desk | Naperville | Glass claims |
| Chicago City Field Office | Chicago | Other claims from losses in the city |
| Suburban Auto Damage Center | Schaumburg | Other claims from losses in the suburbs |

Adjusters, senior adjusters, supervisors, investigators and a claims manager (46 people over the five years, `employee`) work the files. Each person can approve payments up to an authority limit: $10,000 for an adjuster ($2,500 on the glass desk), $25,000 for a senior adjuster, $75,000 for a supervisor, and more for the manager. Body shops, glass companies, rental and towing firms, medical providers, appraisers, law firms and salvage auctions are paid as vendors (`vendor`); some body shops belong to Lakefront’s repair network.

## Five years in brief

Lakefront entered 2022 under-priced, as much of the industry did after the pandemic: used-car prices and repair costs had soared while rates had been cut. It raised rates six times, 48% in all by March 2025, then cut them 2% in June 2026 (`rate_change`).

| Effective | Change | Rate level |
|---|---:|---:|
| 1 April 2022 | +4% | 1.040 |
| 1 October 2022 | +8% | 1.123 |
| 1 January 2023 | +10% | 1.236 |
| 1 July 2023 | +9% | 1.347 |
| 1 March 2024 | +8% | 1.455 |
| 1 March 2025 | +2% | 1.484 |
| 1 June 2026 | −2% | 1.454 |

Each increase made Lakefront dearer than its competitors until they caught up, so fewer quotes became policies and more customers left at renewal. The book shrank in 2023 and grew again once the market’s rates caught up:

| Year end | 2022 | 2023 | 2024 | 2025 | 2026 |
|---|---:|---:|---:|---:|---:|
| Policies in force | 20,556 | 19,504 | 20,000 | 21,143 | 22,301 |
| Loss ratio, by accident year | 81.3% | 70.4% | 67.5% | 58.2% | 65.5% |

The loss ratio is losses incurred on that year’s accidents, without adjustment expenses, as a share of earned premium, valued at the end of 2026; the 2026 figure is still immature. Over the same years the US industry ran 80.2%, 75.4%, 66.1% and 61.5% (2022 to 2025). Ten catastrophes, all real storms from NOAA’s Storm Events Database (hailstorms, two derechos and flash floods, from 2023 on), add between 0.9 and 6 points a year from 2023 (`catastrophe`); the storms are real, the claims on them simulated.

## What the books leave out

Lakefront’s general ledger covers premiums, billing, commission and claims, which is everything the published tables support. It has no investments, salaries, rent, taxes, reinsurance or reserve for claims not yet reported. So the data supports loss ratios but not a combined ratio, and the company’s profit cannot be computed from it.
