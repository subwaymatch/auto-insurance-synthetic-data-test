---
title: How auto insurance works
nav: 2
nav_title: Auto Insurance
eyebrow: The basics
lede: A short course in personal auto insurance, from the policy to the claim to the accounts. Each idea comes with the tables and columns that record it, so you can see it in the data.
description: Policies, coverages, limits, deductibles, rating, written and earned premium, billing, claims, reserves and loss ratios, each linked to where it appears in the Lakefront data.
---

## The policy

A personal auto policy is a contract between an insurer and a household. The **named insured** buys it; it lists the household’s **drivers** and **vehicles**, the **coverages** on each vehicle, and the price. It runs for a **term**, usually six or twelve months, and then **renews** for another term at a new price unless the customer or the company ends it.

Things change during a term. A household moves, buys a car, adds a newly licensed teenager. Each change is an **endorsement**: the policy is re-rated from that day, and the customer pays more or gets money back for the rest of the term (**pro rata**). A policy can also be **cancelled** mid-term, by the customer or by the company (most often for non-payment), or **non-renewed** at the end of a term.

<div class="in-the-data" markdown="1">
`policy` has one row per policy and `policy_term` one per term. `driver` and `insured_vehicle` list who and what each policy covers, with the dates they joined and left. Every change of premium is a row in `premium_transaction` (new business, renewal, endorsement or cancellation), and `renewal_offer` records each renewal the company offered and what the customer decided.
</div>

One thing to keep in mind from the start: `policy`, `driver` and `insured_vehicle` describe each policy, driver and car as it stands *now* (or when it ended). What was true on a past date, such as the address, the cars, the limits and the price, lives in `exposure`. The [data model](/data-model/#current-versus-historical-values) explains why.

## Coverages

A policy is a bundle of separate coverages. Each pays for a different kind of loss, has its own limit or deductible, and has its own price.

### Liability: harm you cause to others

**Bodily injury liability (BI)** pays for injuries the insured driver causes to other people: medical bills, lost wages, pain and suffering, and the cost of defending a lawsuit. **Property damage liability (PD)** pays for damage to other people’s cars and property. Liability is the coverage states require (see [Illinois](/illinois/)).

Liability limits are written as three numbers in thousands of dollars. **25/50/20** means the policy pays at most $25,000 for any one person’s injuries, $50,000 for all injuries in one accident, and $20,000 for property damage in one accident. Anything above the limits is the driver’s own problem.

### Uninsured and underinsured motorist: harm others cause you

**Uninsured motorist (UM)** coverage pays for the insured’s own injuries when the at-fault driver has no insurance, or in a hit-and-run. **Underinsured motorist (UIM)** pays when the at-fault driver’s insurance is too small: the policy pays the difference between the injured person’s damages and what the other driver’s insurer paid, up to the UM/UIM limit.

### Medical payments

**Medical payments (MedPay)** pays medical bills for people in the insured car, whoever was at fault, up to a small limit such as $5,000.

### Physical damage: harm to your own car

**Collision** pays to repair or replace the insured’s own car after a crash, whoever caused it. **Comprehensive** (also called “other than collision”) pays for damage from almost everything else: theft, vandalism, hail, flood, fire, falling trees, hitting a deer, and broken glass. Both are optional by law, but a lender or lessor usually requires them. A policy with liability, collision and comprehensive is often called “full coverage.”

Physical damage coverage pays the cost of repair or the car’s **actual cash value** (what it was worth just before the loss), whichever is less, minus the **deductible**: the part of each claim the customer pays. A higher deductible means a lower premium. When repair would cost more than the car is worth, it is a **total loss**: the insurer pays the value, takes the wreck and sells it for **salvage**.

### Extras

**Rental reimbursement** pays for a rental car while the insured car is being repaired, up to a daily limit and a maximum per claim. **Towing and labor** pays for a tow. **Full glass** removes the deductible for glass repairs and replacement.

<div class="in-the-data" markdown="1">
Each `exposure` row holds the coverage terms in force for one car for a period: `exposure.bi_limit`, `exposure.pd_limit`, `exposure.um_limit`, `exposure.med_pay_limit`, `exposure.collision_deductible` and `exposure.comprehensive_deductible` (`0` when the car has no such coverage), `exposure.full_glass_coverage`, `exposure.rental_reimbursement` and `exposure.towing_and_labor`, and the premium for each coverage. On a claim, each coverage that responds is a separate **feature** in `claim_feature`, identified by `claim_feature.coverage_code`.
</div>

## How a premium is set

An insurer can’t know what a particular driver will cost. It can estimate what drivers *like them* cost on average, and charge that. The **rating plan** does this with a few steps:

1. **Base rate.** Each coverage has a base rate: the price for a standard driver and car.
2. **Rating factors.** The base rate is multiplied by a factor, or **relativity**, for each characteristic that predicts losses: where the car is kept (the **territory**), the driver’s age, sex, marital status and experience (the **driver class**), their violations and at-fault accidents, the car (its **symbol**, a rating of its damage cost or injury risk), its use and mileage, the household’s **insurance score** (a credit-based score), and the limits or deductible chosen.
3. **Discounts and surcharges.** Further factors for multi-car, bundling, paying in full, loyalty, good students and so on.
4. **Rate level.** When costs rise, the insurer files a **rate change** that moves every price by a percentage from an effective date.

The plan’s goal is that premiums match expected losses plus expenses and profit, segment by segment. When a segment pays less than it costs, the company loses money on it; when it pays more, a competitor can take it away. Testing whether a plan gets this right is the actuary’s core job, and the Lakefront plan has weaknesses for students to find.

A term is rated on its **rating date**, using only what the insurer knows by then. A speeding ticket that hasn’t reached the driving record yet doesn’t count until the next renewal.

<div class="in-the-data" markdown="1">
`exposure` holds each car’s rated characteristics (`exposure.rated_driver_class`, `exposure.rated_violation_points`, `exposure.rated_at_fault_accidents`, `exposure.tenure_years` and more), the discounts applied and the resulting premium by coverage. Territories are on `location` (`location.liability_territory`, `location.comprehensive_territory`); vehicle symbols on `vehicle_model_year` (`vehicle_model_year.physical_damage_symbol`, `vehicle_model_year.liability_symbol`). `rate_change` lists every overall change. `driver_incident.known_date` says when each violation or accident became known.
</div>

## Written, earned and unearned premium

Premium is counted in three ways, and mixing them up is the most common mistake with insurance data.

- **Written premium** is booked when a policy is sold or changed: a $1,200 twelve-month policy writes $1,200 on its effective date.
- **Earned premium** is the part of written premium for cover already given. One month into that policy, $100 is earned. Insurers earn premium evenly over the term.
- **Unearned premium** is the rest ($1,100 here), which the insurer owes back if the policy is cancelled. It is a liability on the balance sheet.

**Exposure** measures how much cover was given, in **car-years**: one car insured for a full year is one car-year; two cars for six months is also one. Claim frequency is claims per car-year, so the denominator of almost every rate in insurance analytics comes from exposure.

<div class="in-the-data" markdown="1">
`policy_term.written_premium`, `policy_term.endorsement_premium` and `policy_term.return_premium` hold what was written on each term; `policy_term.earned_premium` what was earned in the extract. At a finer level, each `exposure` row has `exposure.earned_exposure` (car-years) and `exposure.earned_premium` for its dates. `premium_transaction` is the written premium journal, dated by `premium_transaction.effective_date` and `premium_transaction.processed_date`.
</div>

## Selling and keeping customers

New business starts with a **quote**. Some quotes are **bound** (become policies); the share that do is the **conversion** or **close rate**. It depends on price: a quote far above what competitors charge rarely binds. Insurers sell through **independent agents** (who also sell other insurers’ policies and earn a **commission**), **exclusive** or **captive agents** (who sell only one insurer’s), and **direct** online or by phone.

Keeping customers matters as much. **Retention** is the share of renewal offers the customer accepts. A big price increase, a claim, or a cheaper offer elsewhere makes a customer likelier to leave. Insurers also choose not to renew some policies, for example after several at-fault accidents.

<div class="in-the-data" markdown="1">
`quote` holds every new-business quote, bound or not, with `quote.quoted_annual_premium`, the best competing premium an independent agent saw (`quote.competitor_annual_premium`), and `quote.bound`. `renewal_offer` has each renewal’s expiring and offered premium, `renewal_offer.underwriting_decision` and `renewal_offer.outcome`. Commission is on `premium_transaction` and summed by agency and month in `agency_statement`.
</div>

## Billing and collections

Customers pay in full or in **instalments**. Each bill has a due date; a payment can be on time, late, returned by the bank, or never made. An unpaid instalment leads to a past-due notice and then a **cancellation for non-payment**. When a policy ends, the account is settled: money paid in advance is refunded, and a balance still owed is billed and, if never paid, **written off**. Premium written but not yet collected is a **premium receivable**.

<div class="in-the-data" markdown="1">
`billing_invoice` has every bill with `billing_invoice.due_date`, `billing_invoice.amount_due`, `billing_invoice.invoice_status`, `billing_invoice.paid_date` and `billing_invoice.write_off_date`. `billing_receipt` has every payment, returned draft and refund.
</div>

## Claims

### From accident to closed file

1. **The loss.** Something happens on the **loss date**: a crash, a theft, a hailstorm.
2. **First notice of loss.** The insured reports it, on the **report date**. Most claims are reported within days, but injury claims can arrive months later, which is why recent years always have claims still to come.
3. **Coverage and features.** The adjuster checks the policy was in force and which coverages respond. One crash can open several **features**: collision for the insured’s car, property damage for the other car, bodily injury for each injured person.
4. **Investigation.** Who was at fault, what is damaged, how badly people are hurt. Illinois’ fault rule decides whether the insured’s liability coverage pays (see [Illinois](/illinois/#fault-and-comparative-negligence)).
5. **Reserving.** The adjuster sets a **case reserve** on each feature: an estimate of what is still to be paid. It is revised as facts emerge.
6. **Payment.** Payments go to the insured, a body shop, a hospital, a claimant or their lawyer, a lienholder. Each payment reduces the reserve.
7. **Recovery.** The insurer recovers money through **salvage** (selling a totalled car) and **subrogation** (collecting from the at-fault driver’s insurer after paying its own customer).
8. **Closing.** The file closes when nothing more is owed. Many features close without payment, for example a liability claim when the insured wasn’t at fault. A closed claim can **reopen** if a new bill arrives.

<div class="in-the-data" markdown="1">
`claim` has one row per claim, with `claim.loss_date`, `claim.report_date`, `claim.close_date`, `claim.cause_of_loss` and totals. `claim.exposure_id` points to the exposure row in force on the loss date. `claim_feature` has one row per coverage and claimant. `claim_payment` lists every payment and recovery, and `claim_reserve_transaction` every change to a reserve.
</div>

### Claim costs

What a claim costs the insurer has several parts:

- **Paid loss**: money paid to or for claimants.
- **Case reserve**: what the adjuster expects still to pay on open features.
- **Incurred loss** = paid loss + case reserve. Net incurred also takes off salvage and subrogation.
- **Loss adjustment expense (LAE)**: the cost of settling claims. Part is booked to individual claims: **defense and cost containment (DCC)**, mostly lawyers and experts, and **adjusting and other (A&O)**, such as independent appraisers. The rest is the claims department’s overhead.

<div class="in-the-data" markdown="1">
`claim_feature.paid_loss`, `claim_feature.case_reserve`, `claim_feature.salvage_recovery`, `claim_feature.subrogation_recovery`, `claim_feature.net_incurred_loss`, `claim_feature.paid_dcc_expense` and `claim_feature.paid_ao_expense` are all valued at the end of the extract.
</div>

## Measuring results

The basic measures every insurance analyst uses:

| Measure | Formula | What it tells you |
|---|---|---|
| Frequency | Claims ÷ car-years | How often losses happen |
| Severity | Losses ÷ claims | How big they are |
| Pure premium (loss cost) | Losses ÷ car-years = frequency × severity | What cover costs, before expenses |
| Average premium | Earned premium ÷ car-years | What customers pay |
| Loss ratio | Losses ÷ earned premium | Whether premiums cover losses |
| Loss and LAE ratio | (Losses + LAE) ÷ earned premium | The same, with the cost of settling claims |
| Combined ratio | Loss and LAE ratio + expense ratio | Whether the business makes an underwriting profit (below 100%) |

Losses are grouped by **accident year** (the year the loss happened), by **calendar year** (the year a payment or reserve change was booked) or by **policy year**. An accident year’s losses keep changing for years after it ends, as late claims are reported and reserves are revised: this is **loss development**. Actuaries track it in **development triangles** (losses by accident year and age) and use them to estimate **IBNR**, the losses **incurred but not reported** yet, and the **ultimate** cost of each year.

<div class="in-the-data" markdown="1">
Payments (`claim_payment.payment_date`) and reserve changes (`claim_reserve_transaction.transaction_date`) are dated, so paid and incurred triangles can be built as of any date. The data has no IBNR: estimating it is an exercise, and the answer key’s `unreported_claim` lists the claims that had happened but not been reported at the end of 2026. Lakefront’s ledger has commission but no other expenses, so it supports loss ratios but not a combined ratio.
</div>

## The accounts

Insurers keep accounts by **statutory accounting** rules set by state regulators. The core entries follow from everything above: written premium creates a receivable and income; the change in **unearned premium reserve** turns written into earned; cash receipts settle receivables; claim payments and the change in case reserves make up losses incurred; commission is an expense. A **general ledger** summarizes these entries by account and month, and each figure in it should tie back to the detailed records, or **subledgers**, behind it.

<div class="in-the-data" markdown="1">
`gl_account` is the chart of accounts and `gl_journal` the monthly journal entries for each underwriting company; `gl_journal.source_table` names the subledger each entry summarizes. The [company page](/company/#what-the-books-leave-out) lists what the ledger leaves out.
</div>

## Telematics

**Usage-based insurance** measures how a car is actually driven, through a phone app or a device in the car, and prices on it. Programmes typically give a discount for joining and a further discount at renewal for a good driving score. They change who buys (careful drivers are likelier to sign up) as well as how people drive while monitored.

<div class="in-the-data" markdown="1">
`telematics_enrollment` has each policy’s enrollment, and `telematics_score` each scored period: miles, trips, hard braking, speeding, phone use, the `telematics_score.driving_score` and the `telematics_score.earned_discount_pct`.
</div>

For definitions of these and other terms, see the [glossary](/glossary/).
