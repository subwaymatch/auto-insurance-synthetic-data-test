---
title: Auto insurance in Illinois and Chicago
nav: 3
nav_title: Illinois
eyebrow: The setting
lede: Every state writes its own auto insurance rules, and Lakefront works under Illinois’. This page covers the laws and the local risks that shape the data, as they stand in November 2026, including changes already enacted for 2027.
description: Illinois auto insurance law (minimum limits, uninsured motorist coverage, fault, deadlines, proof of insurance, SR-22, cancellation and rate regulation) and Chicago’s risks, with sources, and how each shows up in the Lakefront data.
---

!!! note "Not legal advice"
    This is a summary for understanding the data, checked against the statutes on the Illinois General Assembly’s site in November 2026. Before acting on it, read the law itself or ask the [Illinois Department of Insurance](https://idoi.illinois.gov/).

## What a driver must carry

Every vehicle registered or driven in Illinois must carry liability insurance of at least **25/50/20**: $25,000 for injury or death of one person, $50,000 for all injuries in one crash, and $20,000 for property damage in one crash. These minimums have applied to policies issued or renewed since 1 January 2015. ([625 ILCS 5/7-203](https://www.ilga.gov/Documents/legislation/ilcs/documents/062500050K7-203.htm), [7-601](https://www.ilga.gov/Documents/legislation/ilcs/documents/062500050K7-601.htm))

Two more coverages are tied to that liability policy:

- **Uninsured motorist (UM) bodily injury is mandatory**, including hit-and-run, at no less than 25/50. By default it equals the policy’s bodily injury limits; the named insured can reject, in writing, only the part above the minimum. ([215 ILCS 5/143a](https://www.ilga.gov/Documents/legislation/ilcs/documents/021500050K143a.htm), [143a-2](https://www.ilga.gov/Documents/legislation/ilcs/documents/021500050K143a-2.htm))
- **Underinsured motorist (UIM) coverage is required when UM limits exceed the minimum**, at the same limits as the UM coverage. A policy with only 25/50 UM need not include it. (143a-2(4))

**Uninsured motorist property damage** must be offered but need not be bought. It has a deductible of at most $250 and pays nothing if the at-fault driver can’t be identified. (143a(2))

**Nothing else is required.** Illinois has no no-fault law, so personal injury protection (PIP) isn’t required, and neither is medical payments coverage. Collision and comprehensive are optional by law, though lenders require them on financed cars. ([IDOI shopping guide](https://idoi.illinois.gov/consumers/consumerinsurance/auto-insurance-shopping-guide.html))

<div class="in-the-data" markdown="1">
Lakefront’s lowest liability option is the state minimum, 25/50/20 (`exposure.bi_limit`, `exposure.pd_limit`). UM limits usually match the liability limits, but some customers with higher liability limits keep UM at the 25/50 minimum (`exposure.um_limit`). UM cover includes UIM, and `claim_feature.um_uim_type` tells the two apart; on an underinsured claim, `claim_feature.other_insurer_payment` is what the at-fault driver’s insurer paid. Medical payments is optional (`exposure.med_pay_limit`). The data leaves out uninsured motorist property damage.
</div>

## Fault and comparative negligence

Illinois is an **at-fault** (tort) state: a person injured in a crash claims against the at-fault driver, whose liability insurance pays. The share of blame matters under **modified comparative negligence**: a person more than 50% at fault recovers nothing; anyone 50% or less at fault recovers their damages reduced by their own share. Someone 20% at fault with $10,000 of damages recovers $8,000. ([735 ILCS 5/2-1116](https://www.ilga.gov/Documents/legislation/ilcs/documents/073500050K2-1116.htm))

<div class="in-the-data" markdown="1">
`claim.at_fault` and `claim.insured_fault_pct` record the insured driver’s share of blame. At-fault insureds are 51% to 100% at fault and others 0% to 49%, so the data has no evenly shared accidents. The percentage describes the accident but doesn’t reduce what is paid: settlements are not cut for a claimant’s own share of fault.
</div>

## Deadlines for claims

A lawsuit for personal injury must be filed within **two years**, and one for property damage, such as a damaged car, within **five years**. ([735 ILCS 5/13-202](https://www.ilga.gov/Documents/legislation/ilcs/documents/073500050K13-202.htm), [13-205](https://www.ilga.gov/Documents/legislation/ilcs/documents/073500050K13-205.htm)) Suits against a local public body, such as the City of Chicago, have one year. ([745 ILCS 10/8-101](https://www.ilga.gov/Documents/legislation/ilcs/documents/074500100K8-101.htm))

<div class="in-the-data" markdown="1">
Injury claims can be presented weeks or months after the accident, a few near the two-year limit, and every suit (`claim_feature.suit_date`) is filed within it. This is why the newest accident years in the data are not yet complete.
</div>

## Proof of insurance, and driving without it

Drivers must carry proof of insurance in the car (a phone image counts) and show it when police ask, though police may not stop a car only to check. Driving uninsured is a petty offense with a fine of more than $500 and up to $1,000, and a conviction brings a three-month license suspension. The Secretary of State also suspends the registration of a vehicle found uninsured. ([625 ILCS 5/3-707](https://www.ilga.gov/Documents/legislation/ilcs/documents/062500050K3-707.htm), [7-602](https://www.ilga.gov/Documents/legislation/ilcs/documents/062500050K7-602.htm), [7-606](https://www.ilga.gov/Documents/legislation/ilcs/documents/062500050K7-606.htm))

Since July 2021 the **Illinois Insurance Verification System** has checked electronically, at least twice a year, that every registered vehicle is insured, using policy data insurers report. An owner who can’t prove coverage within 30 days of a notice loses the registration. ([7-603.5](https://www.ilga.gov/Documents/legislation/ilcs/documents/062500050K7-603.5.htm), [IDOI](https://idoi.illinois.gov/consumers/consumerinsurance/sos.html))

Even so, the Insurance Research Council estimates that **15.2% of Illinois drivers were uninsured in 2023**, close to the national 15.4%. ([IRC, via Triple-I](https://www.iii.org/fact-statistic/facts-statistics-uninsured-motorists)) That is why UM coverage matters.

<div class="in-the-data" markdown="1">
Uninsured motorist claims arise when the other driver in a crash had no insurance. The answer key’s `location_truth.other_driver_uninsured_probability` gives the chance of that in each ZIP code.
</div>

## SR-22: proof of financial responsibility

After some serious events, a driver must prove to the Secretary of State that they are insured, usually through a certificate their insurer files electronically, known as an **SR-22**. A driver whose license is revoked, for example after a DUI, must keep that proof for three years; so must a driver convicted a third time of driving uninsured. The insurer must tell the state before canceling a certified policy. ([625 ILCS 5/7-304](https://www.ilga.gov/Documents/legislation/ilcs/documents/062500050K7-304.htm), [7-305](https://www.ilga.gov/Documents/legislation/ilcs/documents/062500050K7-305.htm), [3-707](https://www.ilga.gov/Documents/legislation/ilcs/documents/062500050K3-707.htm))

<div class="in-the-data" markdown="1">
`driver.sr22_filed_date` and `driver.sr22_end_date` record SR-22 filings: three years after a conviction for DUI, driving while suspended or leaving the scene. That is a simplified version of the state’s rules.
</div>

## Cancellation and non-renewal

Illinois limits when an insurer can end an auto policy. In a new policy’s **first 60 days**, it can cancel for almost any reason. After that, or on a renewal, it can cancel only for listed reasons: non-payment, misrepresentation or fraud, or a driver whose license was suspended or who was convicted of serious offenses such as DUI, among others. ([215 ILCS 5/143.19](https://www.ilga.gov/Documents/legislation/ilcs/documents/021500050K143.19.htm))

Notice must be mailed at least **10 days** ahead for non-payment and **30 days** for other reasons, with the reasons stated. A **non-renewal** needs 30 days’ notice; once a policy has been in force five years or more, the insurer may non-renew only for the same listed reasons or with 60 days’ notice. ([143.15](https://www.ilga.gov/Documents/legislation/ilcs/documents/021500050K143.15.htm), [143.17](https://www.ilga.gov/Documents/legislation/ilcs/documents/021500050K143.17.htm), [143.19.1](https://www.ilga.gov/Documents/legislation/ilcs/documents/021500050K143.19.1.htm)) Drivers who can’t find an insurer can apply to the **Illinois Automobile Insurance Plan**, the state’s market of last resort.

<div class="in-the-data" markdown="1">
Lakefront’s underwriters cancel some new business in its first 60 days. A missed installment leads to a past-due notice, then a notice of cancellation mailed at least ten days before cover ends, three to four weeks after the due date; a missed bank draft gets its notice the day the bank returns it (`policy_term.cancel_reason`, `billing_invoice`, `customer_contact`). The company non-renews some policies whose drivers have had several at-fault accidents or major violations (`renewal_offer.underwriting_decision`); the data doesn’t apply the five-year rule.
</div>

## How prices are regulated

For decades Illinois was unusual: the state did not review or approve auto insurance rates, leaving prices to competition. ([Capitol News Illinois](https://capitolnewsillinois.com/news/pritzker-signs-bills-allowing-state-to-review-insurance-rate-hikes/)) That is changing. **Public Act 104-0753**, signed on 4 August 2026, gives the Department of Insurance power to review private passenger auto rates filed **from 1 July 2027**. ([P.A. 104-0753](https://www.ilga.gov/Documents/legislation/publicacts/104/104-0753.htm))

- Rates must not be “excessive, inadequate, or unfairly discriminatory”.
- It is not prior approval. A filed rate can be used; the Department has 40 days to object, and if it doesn’t, the filing is deemed compliant. An objected-to rate stays in effect through a hearing, and a final order can require rebates.
- Customers must get 30 days’ notice of a renewal increase over 10%.

**Credit-based insurance scores** are allowed, with limits, under the [Use of Credit Information in Personal Insurance Act](https://www.ilga.gov/Documents/legislation/ilcs/documents/021501570K20.htm). An insurer may not deny, cancel or non-renew a policy, or set a renewal rate, on credit alone, and the score may not use income, gender, address, ethnic group, religion, marital status or nationality. Bills in 2026 to ban credit and ZIP code as rating factors did not pass.

On price, Illinois sits near the middle: the average driver spent **$1,264** on auto insurance in 2024, against **$1,432** nationally. ([NAIC](https://content.naic.org/sites/default/files/2024-adb-average-premium-supplement.pdf))

<div class="in-the-data" markdown="1">
The data ends in December 2026, before the new law takes effect, so Lakefront changes its rates on its own judgment (`rate_change`). It uses an insurance score (`policy.insurance_score`) and rates by territory (`location.liability_territory`).
</div>

## Chicago’s risks

### Where risk is higher

Lakefront prices by **territory**. It groups its 290 ZIP codes into twelve territories for liability, by their crash records, and twelve for comprehensive, by their vehicle-theft records. T01 is the lowest hazard and T12 the highest, and each territory holds about the same number of households with a car. A ZIP code’s two territories often differ.

<!-- territory-map -->

### Crashes

Crash and theft risk vary sharply across the city and suburbs, with traffic density, road design, parking and how much people drive. Lakefront rates by territory, grouping its 290 ZIP codes by their crash and theft records.

<div class="in-the-data" markdown="1">
Claims rise on Fridays, holidays and snow days, as crashes do. Each ZIP code’s rating territories are on `location`, with its Census profile on `zip_demographics`; the true hazards behind the territories are in the answer key’s `location_truth`.
</div>

### The Kia and Hyundai theft wave

Many Kia and Hyundai models sold in the US from 2011 to 2022 lacked engine immobilizers. In 2022, social media spread a way to start them with a USB cable, and thefts soared. In Chicago, Kia and Hyundai thefts rose from about 500 in the first half of 2022 to more than 8,350 in the second half, and the city sued both automakers in August 2023. ([City of Chicago](https://www.chicago.gov/city/en/depts/mayor/press_room/press_releases/2023/august/SuitAgainstAutomakersKiaAndHyundai.html))

Motor vehicle thefts recorded by the Chicago Police Department ([City of Chicago Data Portal](https://data.cityofchicago.org/Public-Safety/Crimes-2001-to-Present/ijzp-q8t2)):

| Year | 2019 | 2020 | 2021 | 2022 | 2023 | 2024 | 2025 |
|---|---:|---:|---:|---:|---:|---:|---:|
| Thefts | 8,979 | 9,962 | 10,605 | 21,476 | 29,257 | 21,715 | 17,261 |

<div class="in-the-data" markdown="1">
The theft wave is in the claims: look for whole-vehicle thefts (`claim.cause_of_loss` `THEFT_TOTAL`) of the affected makes and model years (`vehicle_model_year`). The answer key’s `insured_vehicle_truth.kia_hyundai_theft_exposure` marks the affected cars.
</div>

## Changes coming in 2027

None of these applies to the data, which ends on 31 December 2026, but they matter for anyone working in Illinois insurance now:

| From | Change | Law |
|---|---|---|
| 1 January 2027 | Non-renewal notice for auto and other personal policies rises from 30 to 60 days | [P.A. 104-0534](https://www.ilga.gov/Documents/legislation/publicacts/104/104-0534.htm) |
| 1 January 2027 | Electric micromobility devices are exempt from the insurance mandate | P.A. 104-0854 |
| 1 July 2027 | Department of Insurance review of auto rate filings; 30 days’ notice of renewal increases over 10% | [P.A. 104-0753](https://www.ilga.gov/Documents/legislation/publicacts/104/104-0753.htm) |
| 1 July 2027 | The senior defensive-driving course for a premium discount drops from 8 hours to 4 | P.A. 104-0753 |

P.A. 104-0534 also lengthens cancellation notice periods for personal policies; how that interacts with the existing auto-specific rule (215 ILCS 5/143.15) was not clear from the statutes in November 2026.
