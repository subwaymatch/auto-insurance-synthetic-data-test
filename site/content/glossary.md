---
title: Glossary
eyebrow: Reference
lede: Insurance terms used on this site and in the data, in plain words, with where each one appears.
description: A glossary of personal auto insurance terms, from accident year to written premium, linked to the Lakefront tables and columns.
---

Accident year
:   The year a loss happened. Losses grouped by accident year show how the cost of each year’s accidents develops as claims are reported and settled. Compare *calendar year*. In the data: `claim.loss_date`.

Actual cash value (ACV)
:   What a car was worth just before a loss: its replacement cost less depreciation. Physical damage coverage pays the lesser of the repair cost and the ACV, minus the deductible. In the data: `exposure.vehicle_value`.

Adjuster
:   The claims employee who investigates a claim, sets its reserves and approves payments up to an authority limit. In the data: `employee`, `claim.adjuster_id`.

Bind
:   To put a policy in force. A quote that becomes a policy is *bound*. In the data: `quote.bound`.

Bodily injury liability (BI)
:   Coverage for injuries the insured driver causes to other people. In the data: `claim_feature.coverage_code` `BI`.

Calendar year
:   The year a transaction is booked, whatever year the loss happened. Calendar-year incurred losses are payments in the year plus the change in reserves during it. Compare *accident year*.

Car-year
:   One car insured for one year, the unit of *exposure*. In the data: `exposure.earned_exposure`.

Case reserve
:   An adjuster’s estimate of what is still to be paid on an open claim. In the data: `claim_feature.case_reserve`, with every change in `claim_reserve_transaction`.

Catastrophe
:   A single event, such as a hailstorm, that causes many claims at once. Insurers track catastrophe losses separately. In the data: `catastrophe`, `claim.catastrophe_id`.

Collision
:   Coverage for damage to the insured’s own car from a crash, whoever caused it. In the data: `claim_feature.coverage_code` `COLL`.

Combined ratio
:   Losses, loss adjustment expenses and underwriting expenses as a share of earned premium. Below 100% means an underwriting profit. The Lakefront ledger can’t produce one: it has no underwriting expenses other than commission.

Commission
:   What an agent is paid for selling and renewing policies, as a percentage of the premium. In the data: `premium_transaction.commission_amount`, `agency_statement`.

Comprehensive
:   Coverage for damage to the insured’s car from causes other than a crash: theft, vandalism, hail, flood, fire, animals and glass breakage. Also called *other than collision*. In the data: `claim_feature.coverage_code` `COMP`.

Conversion rate
:   The share of quotes that are bound. Also called the *close rate* or *hit rate*.

Deductible
:   The part of a physical damage claim the customer pays before the insurer pays anything. In the data: `exposure.collision_deductible`, `exposure.comprehensive_deductible`.

Defense and cost containment (DCC)
:   Claim expenses for defending and settling claims, mostly lawyers and experts. In the data: `claim_feature.paid_dcc_expense`.

Development
:   The change in an accident year’s losses as time passes, as late claims arrive and reserves are revised. Measured with *development triangles*.

Earned premium
:   The part of written premium for cover already given. A twelve-month policy earns a twelfth of its premium each month. In the data: `policy_term.earned_premium`, `exposure.earned_premium`.

Endorsement
:   A change to a policy during its term, such as adding a car or moving house, which re-rates it from that day. In the data: `exposure.endorsement_number`, `premium_transaction.transaction_type`.

Exposure
:   The amount of cover given, the denominator of claim frequency. For auto insurance it is measured in car-years. In the data: `exposure`.

Feature
:   One coverage, for one claimant, on a claim. A crash can open a collision feature for the insured’s car and a bodily injury feature for each injured person. In the data: `claim_feature`.

First notice of loss (FNOL)
:   The first report of a claim to the insurer. In the data: `claim.report_date`.

Frequency
:   Claims per unit of exposure, such as claims per 100 car-years.

IBNR (incurred but not reported)
:   Losses that have happened but haven’t been reported to the insurer yet, plus expected growth on known claims. Actuaries estimate it from development triangles. In the answer key: `unreported_claim`.

Incurred loss
:   Paid loss plus case reserves. *Net* incurred also deducts salvage and subrogation. In the data: `claim_feature.incurred_loss`, `claim_feature.net_incurred_loss`.

Installment
:   One of several payments of a policy’s premium. In the data: `billing_invoice`.

Insurance score
:   A score used in rating and underwriting that predicts insurance losses. It is usually based on credit information. In the data: `policy.insurance_score`.

Loss adjustment expense (LAE)
:   The cost of settling claims: DCC and adjusting and other expense (A&O) booked to claims, plus claims department overhead. In the data: `claim_feature.paid_expense`.

Loss ratio
:   Losses as a share of earned premium. A *pure* loss ratio excludes LAE.

Medical payments (MedPay)
:   Coverage for medical bills of people in the insured car, whoever was at fault, up to a small limit. In the data: `exposure.med_pay_limit`.

Named insured
:   The person who buys the policy and whose name is on it. In the data: `policy.named_insured_driver_id`.

Non-renewal
:   An insurer’s decision not to offer another term. In the data: `renewal_offer.underwriting_decision`, `policy_term.nonrenewal_reason`.

Pro rata
:   In proportion to time. A mid-term change is charged or refunded pro rata to the end of the term.

Property damage liability (PD)
:   Coverage for damage the insured driver causes to other people’s property, mostly their cars. In the data: `claim_feature.coverage_code` `PD`.

Pure premium
:   Losses per unit of exposure: frequency times severity. Also called *loss cost*.

Rate level
:   The overall level of an insurer’s prices, moved by rate changes. In the data: `rate_change`, `policy_term.rate_level_index`.

Rating date
:   The day a policy term was priced, using only what the insurer knew by then. In the data: `policy_term.rating_date`, `exposure.rating_date`.

Relativity
:   A rating factor’s multiplier for one level of a variable, relative to a base level. A relativity of 1.30 for a territory means 30% more than the base territory.

Renewal
:   A new term of an existing policy. In the data: `renewal_offer`, `policy_term.business_type`.

Retention
:   The share of renewal offers customers accept.

Salvage
:   Money recovered by selling a car the insurer has paid as a total loss. In the data: `claim_feature.salvage_recovery`.

Severity
:   The average cost of a claim.

SR-22
:   A certificate an insurer files with the state to prove a high-risk driver carries insurance, typically after a serious violation. In the data: `driver.sr22_filed_date`.

Subrogation
:   Recovering what the insurer paid its own customer from the party at fault, usually that party’s insurer. In the data: `claim_feature.subrogation_recovery`.

Symbol
:   A rating of a vehicle model’s damage cost or injury risk. In the data: `vehicle_model_year.physical_damage_symbol`, `vehicle_model_year.liability_symbol`.

Telematics
:   Measuring how a car is driven, through a phone app or a device, to price on it. Also called *usage-based insurance*. In the data: `telematics_enrollment`, `telematics_score`.

Term
:   The period a policy runs before renewal, usually six or twelve months. In the data: `policy_term`.

Territory
:   A group of places with similar risk, used as a rating factor. In the data: `location.liability_territory`, `location.comprehensive_territory`.

Total loss
:   A car that would cost more to repair than it is worth, or that was stolen and not recovered. The insurer pays its value and keeps the salvage. In the data: `claim_feature.total_loss`.

Underinsured motorist (UIM)
:   Coverage for the insured’s injuries when the at-fault driver’s insurance is too small to pay them. In the data: `claim_feature.um_uim_type`.

Underwriting
:   Deciding whether to insure a risk, on what terms and in which company. In the data: `policy.company_id`, `renewal_offer.underwriting_decision`.

Unearned premium
:   Written premium not yet earned, which the insurer would owe back if every policy were canceled. A liability on the balance sheet. In the data: the unearned premium accounts in `gl_journal`.

Uninsured motorist (UM)
:   Coverage for the insured’s injuries when the at-fault driver has no insurance or can’t be found. In the data: `exposure.um_limit`.

Valuation date
:   The “as of” date of a data extract; nothing after it is known. For this data, 31 December 2026.

Written premium
:   The premium on policies sold or changed in a period, booked when the transaction takes effect. In the data: `premium_transaction.written_premium`, `policy_term.written_premium`.
