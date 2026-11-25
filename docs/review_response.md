# Responses to the external reviews of November 2026

An outside reviewer (another AI coding assistant) has reviewed the generator three times, a dataset
realism audit followed on 20 November 2026, two further realism audits on 22 November 2026, follow-up checks
of the release that fixed them, an audit of v1.1.7 on 23 November 2026, and audits of v1.1.8 on 24 November and
v1.1.9 on 25 November 2026. The newest is answered first, then the earlier ones in reverse order: the audits of
v1.1.8 and v1.1.7, the follow-up checks, the two audits, the 20 November audit at commit `03c2634` and the third
review at `9fe6062`; the first two follow. Each finding is answered: **confirmed and fixed**, **already
addressed**, **not adopted** (a suggestion outside this dataset's scope, now listed in
[limitations.md](limitations.md)), or **agreed, already documented**.

## Audit of v1.1.9 (25 November 2026)

An audit of v1.1.9 (`main` at `de3495e`) rebuilt the default run (content hash `4612b99cdbc9e521`) and seed 101
(`edd0a9d11cbe5828`); both passed all 193 checks, with the previous round's 18 fixes holding. It reported ten
findings no check covered. All reproduce (F9 on seed 101 only) and all are **confirmed and fixed**; for F7 the
opening book's placement is documented rather than reconstructed (below). "After" figures are from the default run
after this change (content hash `9774ec39a673aeea`) and seed 101 (`{H_101}`). Each finding has a check in `validate.py`; on
v1.1.9 the new checks fail on the default run (8) and seed 101 (9; the salvage check fails only there).

| # | Finding | Before (default; seed 101) | After (default; seed 101) |
|---|---|---|---|
| F1 | A car lost in a claim removed, re-rated, booked and confirmed before the claim was reported (some unreported at the valuation date) | 8 unreported claims' cars removed, 1,113 bookings and 1,810 re-rated rows before the report; 6, 1,145, 1,768 | 0; 0 |
| F2 | Occasional youthful operator surcharge with no young driver lacking a car, or on two cars | 98 periods, 3 with two cars; 124, 19 | 0; 0 |
| F3 | Divorced spouses still married; a couple killed together leaving a widow | 646 of 646; 650 of 650 and 1 couple | 0; 0 |
| F4 | Fatal crashes without a police report; a rental after the only driver died | 3 and 1 rental ($680); 7 and 1 ($640) | 0; 0 |
| F5 | A lapsing policy paying endorsement bills due after its missed installment | 14 (5 by bank draft); 10 | 0; 0 |
| F6 | Staff calls on Saturday holidays; change confirmations and billing notices on or after a cancellation | 15, 844, 11; 17, 825, 15 | 0; 0 |
| F7 | New policies placed with a company on incidents known after the quote | 85 with such an incident, 30 placed otherwise; 93, 31 | 0; 0 |
| F8 | Opening telematics enrollments on random days rather than a term's effective date | 1,602; 1,568 | 0; 0 |
| F9 | A car its owner kept after a total loss claiming again in the same term | 0; 2 | 0; 0 |
| F10 | Dictionary and website wording | 5 items | fixed |

**F1. Removals before the claim is reported.** Confirmed: a car's removal, the other cars' re-rating, the
endorsement and the cancellation of an emptied policy all happened the day after the loss, whenever the claim was
reported. The simulation now draws the claim's first notice when the loss happens (`claims.first_notice`, used by
claims development too). A car lost in a claim with a physical damage, rental or towing feature (all opened at first
notice, so on the claim's report date) is taken off once the company knows: the removal is still backdated to the day
after the loss, as insurers do, but the re-rated rows carry the report date as their `rating_date`, and the
endorsement, the cancellation and their confirmations are booked no earlier. A car whose claim is not reported by
the valuation date stays on the policy, as far as the extract knows, with no further losses (its renewal includes
it). A wreck with only liability claims, presented later, is the customer taking the car off, the next day.
`validate.py`'s rule that a row is rated by its start now allows exactly these backdated rows.

**F2. Occasional youthful operators.** Confirmed, all three causes. Ranks are never reused (a car written off keeps
its rank for its replacement); a driver left with only a spare car drives it as their main car, re-rated from the
change (`simulate._promote_spares`); and a newly licensed teenager or a new spouse without a car takes over a spare
car the household already has (`_give_spare_car`). The surcharge now falls on one car, and only when a listed driver
under 25 has no car of their own.

**F3. Marital status.** Confirmed. A divorcing spouse is now divorced too, and when a couple dies on the same day
neither is recorded as widowed: the spouse of a named insured who dies that day does not take the policy over as a
widow, and the policy ends with its named insured.

**F4. Fatal crashes.** Confirmed. A crash that killed an insured carries that fact to its claim even when no claim of
the victim's own records it (no medical payments cover), so it has a police report; so does a crash whose driver
died by the next day, whatever the death is put down to. A rental ends when the household's only driver dies
(`simulate._rentals_until_death`), and one already settled from a loss late in a term is cut back when the death
falls early in the next (`claims.Development.stop_rentals`: the payment and the other insurer's repayment shrink to the
days before the death).

**F5. Endorsement bills on a lapsing policy.** Confirmed. Every bill due on or after the missed installment of a
policy cancelled for non-payment now goes unpaid; only the missed installment's own draft is attempted.

**F6. Contacts.** Confirmed. No staff calls on a Saturday holiday; a change and a cancellation are confirmed when they
are booked (`premium_transaction.processed_date`); and nothing is confirmed, chased or warned of from a policy's
cancellation day on.

**F7. Company placement.** Confirmed. A new policy's quote day is now drawn with the population, and its company is
chosen on the score, prior insurance and record known that day; the simulation and the quote table use the same day.
**Opening book, documented:** a policy already renewing when the extract begins is placed on its record as it
entered the extract (known before its opening term could be offered), because its record when first written, often
years before, is not retained (driving records go back three years). `limitations.md` and the dictionary say so.

**F8. Opening telematics enrollments.** Confirmed. A policy already enrolled on 1 January 2022 joined on one of its
earlier term effective dates, within about three years.

**F9. Salvage cars.** Confirmed on seed 101: a car kept on a salvage certificate lost no further claims in its own
period but could in a later period of the same term. It now has none for the rest of the term, a storm's included
(a catastrophe no longer strikes a car on a salvage certificate).

**F10. Documentation.** Confirmed and fixed: the prior-carrier report source, `telematics_enrolled`, the claim table's
"totals", the ZIP code example and the v1.1.9 changelog entry.

### What changed in the data

Removals after a claim are booked and confirmed later, at the report, and a few cars lost late in 2026 stay on
their policies; spare cars pass to drivers without one, so fewer cars carry the occasional youthful operator
surcharge; lapsing policies collect less; contacts after cancellations drop; a few new policies change company.
These change later random draws, so every figure of the default run moves a little: loss ratios by accident year
83.7%, 80.3%, 65.0%, 60.2% and 69.1% for 2022 to 2026 (were 82.5%, 81.0%, 67.4%, 59.5% and 66.4%), overall 70.5%
(was 70.1%; {SEED_RANGE} across five seeds), annualized retention 81.2%; 22,670 claims (was 22,725).
`validate.py` runs 203 checks (was 193), all passing on the default run and on seeds 7, 11, 23, 42 and 101; the test
suite has 88 tests.

## Audit of v1.1.8 (24 November 2026)

An audit of v1.1.8 (`main` at `635ea6f`, the merged PR #16) rebuilt the default run (content hash `4a9b0599022f5117`) and
seed 101 (`df2bb4217f33dc5e`); both passed all 175 checks. It found the previous round's fixes holding and
reported 18 record-level findings that no check covered. All 18 reproduce on both books (F6 and F14 on the
default only in the form reported; F14 measured as rows that span a write-off) and all are **confirmed and
fixed**, F10's third part in part (below). "After" figures are from the default run after this change (content
hash `4612b99cdbc9e521`) and seed 101 (`edd0a9d11cbe5828`). Each finding now has a check in `validate.py`; the new checks fail on the
old default run (17 of them; the vendor-concentration and solo-death rental checks pass there and failed only on
seed 101).

| # | Finding | Before (default; seed 101) | After (default; seed 101) |
|---|---|---|---|
| F1 | Medical providers never paid: every medical payment went to the insured (some jointly with an attorney) | 0 of 220 providers used; 0 of 220 | 154 of 220 providers used, 54% of medical payments to a provider; 147 of 220, 61% |
| F2 | A revised renewal billed, and paid, its re-rated premium before the change that re-rated it | 8,583 first bills before the rating date, 1,027 paid; 8,450, 955 | 0; 0 |
| F3 | Expense reserve left open on a litigated feature between its close and a reopening | 2 features; 2 (one at the valuation date) | 0; 0 |
| F4 | Loss reserve held after the supplemental payment that settles a reopening | 325 of 692 reopenings; 305 of 613 | 0; 0 |
| F5 | Endorsements with no change: a period ended at a change that could not happen, re-rating the policy and sending a change confirmation | 458 endorsements (785 rows); 509 | 0; 0 |
| F6 | A revised offer dated after the valuation date | 1; 0 | 0; 0 |
| F7 | Fatal crashes without a police report; a rental after a crash that killed the household's only driver | 3 of 13; 9 of 20 and 2 rentals | 0; 0 |
| F8 | A car traded in on the day the policy ended with its insured's death (no exposure); main driver reassigned on a policy that had ended | 1 car, 3 drivers; 0, 8 | 0; 0 |
| F9 | Injury claims closed without payment labeled as fractures, head injuries or a fatality | 139; 128 (one fatality) | 0; 0 |
| F10 | Cash below zero (refunds before payment); a final balance before a returned draft; cancellations keyed after the valuation date | 75 terms, 2, 9; 74, 1, 9 | 0, 0, 0; 0, 0, 0 |
| F11 | Named insured not yet licensed, or under 18, at inception; policies with no driver at inception | 84 policies, 15 with another driver first; 93, 26 | 0; 0 |
| F12 | A quote's youngest driver a year older than its named insured | 125; 129 | 0; 0 |
| F13 | Prior-carrier reports known after the driver left | 2; 3 | 0; 0 |
| F14 | Multi-car discount kept after a write-off left one car | 3,042 rows; 2,892 | 0; 0 |
| F15 | One vendor taking almost a whole trade (Pareto weights with no mean) | top rental firm 58%, 3 of 6 unused; top appraiser 99.7% | top rental firm 67%, all 6 used; top appraiser 22%, all 10 used |
| F16 | A crash's rental and tow subrogation months apart from its repair's | 1.5% the same day; 1.1% | 100%; 100% (a reopening's share apart) |
| F17 | Payments to an estate by EFT; calls and notices to a dead insured after the cancellation | 9 of 26 by EFT, 6 contacts; 26 of 60, 4 | 0; 0 |
| F18 | 1985 Subaru RX Turbo without engine data; dictionary drift | 1 row; 1 | 0; 0 |

**F1. Medical payments.** Confirmed: once every medical payments feature named its injured driver (PR #16), the
step that pays the policy's own people as the insured overwrote the 60% of medical payments meant for providers.
It now applies to uninsured motorist claims only; medical payments go to a provider or to the person (their estate
after a death), never jointly with an attorney. `claim_payment.payee_type` now lists `Insured and Attorney`.

**F2. Revised renewals billed early.** Confirmed. The first bill was dated the offer day but billed the premium
booked on the rating day. It is now issued on the rating day (the revised offer, for a renewal re-rated before it
took effect), so it bills a premium known that day and cannot be paid before it.

**F3 and F4. Reserves after a close or a supplement.** Confirmed. The expense reserve now closes at the feature's
first close (every legal bill is paid by then; a reopening pays no expense), and a supplemental payment ends the
loss reserve as a final payment does.

**F5. Endorsements with no change.** Confirmed: a scheduled change that would be refused when applied (a trade of a
car already written off, a sale from a one-car household, a teenager whose parents are too young) still ended the
period. Changes are now checked against the policy as it stands before they can set a boundary (`simulate._feasible`),
and a boundary set by a change to a car lost in the same period is moved to the next change that can still happen.
A car written off the day before its own scheduled sale or trade is recorded as removed on that boundary.

**F6. Revised offer after the valuation date.** Confirmed: a car wrecked on the valuation date leaves the next day,
and that change reached the pending offer. A change after the valuation date no longer revises an offer.

**F7. Fatal crashes.** Confirmed. Every crash that killed someone now has a police report, and an injury or medical
payments claim counts as someone hurt at the scene. A crash that killed every listed driver of the household pays
no rental.

**F8. Same-day death and changes.** Confirmed. Drivers leaving are now applied first each day; a death that ends the
policy (no one to take it over) stops that day's other changes, and its cars are not handed over.
`insured_vehicle.primary_driver_id` is the driver on the car's latest exposure row, as its use and mileage are.

**F9. Unpaid injuries.** Confirmed: injury type and attorney involvement read the claim's gross damages rather
than what was paid, so a claim closed without payment could be labeled severe. Both now read the payment.

**F10. Billing timing.** Confirmed. (1) A refund now goes out once the bills already sent are paid and the premium
received covers it and the refunds before it (`billing._covered`); one that is never covered is settled by the
cancellation. (2) A final balance waits for any bank draft still in flight. (3) A cancellation at the customer's
request is keyed within at most ten days, and one in effect by the valuation date (as is any endorsement) is booked
by then. **In part:** a cancellation is still keyed a few days after it took effect, backdated, as in practice, so
a bill sent in between is canceled and anything paid on it refunded; the check is that no cancellation in effect
is missing from the ledger and that cash never goes below zero.

**F11. Named insured at inception.** Confirmed. A tenure that would have begun before the named insured turned 18 is
shortened, and one written after a late licence means they were licensed by then, so every policy's first driver
joined it at its inception.

**F12. Quote ages.** Confirmed: the named insured's age used the unrounded age, the youngest driver's the whole-day
birth day. Both now use the birth day (`quotes._age_on`).

**F13. Prior-carrier reports.** Confirmed. A prior-carrier claims report, like a driving record, is ordered only
while the driver is insured here.

**F14. Multi-car discount after a write-off.** Confirmed. A car written off while another stays is now removed by an
endorsement on the day it leaves (`simulate._cut_at_removal`, as a crash death cuts a period), re-rating the other
cars. When a household loses two cars this way, one after the other, and is left with none, a replacement that
would come after its renewal can be offered now cancels the policy, as it does when it loses its only car (found
while fixing this: a renewal offer for no cars).

**F15. Vendor concentration.** Confirmed. Vendor sizes are now log-normal: a few vendors take more than their share
of a trade, none nearly all of it, and every vendor gets work in a full-size run. Rentals stay the most concentrated
trade on purpose (an insurer bills most replacement rentals directly through one main rental company: 67% in the
default run, up to 91% on another seed); the check that no vendor takes three quarters of a trade leaves rentals
out.

**F16. Subrogation timing.** Confirmed. The other insurer repays a crash's repair, rental and tow together, after the
last of them closes; a reopening's share still comes after its own supplement.

**F17. Estates.** Confirmed. Payments to an estate are checks, from the day the person is removed (`<=`). After a
policy ends with its insured's death every contact is a letter to the estate, with no notice of cancellation or
change confirmation.

**F18. Catalog and dictionary.** Confirmed. The 1985 Subaru RX Turbo has its engine (four cylinders, 1.8 litres:
EPA's record is blank, filled in `build_vehicle_catalogue.ENGINE_GAPS`), and the dictionary's payee types, first
bill date, final balance date and change reasons match the data.

### What changed in the data

Medical payments go to providers again; revised renewals are billed later and refunds wait for the cash, so
receipts move; write-offs on multi-car policies add an endorsement (exposure rows 446,579, was 439,321) and end
the multi-car discount sooner, which changes premiums a little; drivers who were added after their policy's
inception now join at it, shortening a few opening-book tenures. These change later random draws, so every figure
of the default run moves a little: loss ratios by accident year 82.5%, 81.0%, 67.4%, 59.5% and 66.4% for 2022 to
2026 (were 84.5%, 79.5%, 65.6%, 62.9% and 63.3%), overall 70.1% (was 69.8%; 69.6% to 72.2% across five seeds),
annualized retention 81.3%; 22,725 claims (was 22,933). `validate.py` runs 193 checks (was 175), all passing on
the default run and on seeds 7, 11, 23, 42 and 101; the test suite has 83 tests.

## Audit of v1.1.7 (23 November 2026)

An audit of v1.1.7 (commit `529956c`) rebuilt the default run (content hash `6a360e75d7d87f3f`) and an
independent seed (101, `dc2325b798e03cb4`), found the previous round's five fixes holding, and reported three
record-level issues; both books passed every check. All three reproduce and are **confirmed and fixed**; for
the third, at the owner's request, crash deaths are now modeled rather than excluded: of the insured at the
wheel, and of the household's other drivers riding along. "After" figures are from the default run after
this change (content hash `4a9b0599022f5117`) and seed 101 (`df2bb4217f33dc5e`).

| # | Finding | Verdict | Before (default; seed 101) | After |
|---|---|---|---|---|
| F1 | Subrogation received before a reopening's supplement had been paid | Confirmed and fixed | 15 features ($7,934); 15 | 0; 0 |
| F2 | A car handed to another driver keeps the old driver's mileage and use | Confirmed and fixed | 1,295 of 1,295 switches unchanged; 1,421 of 1,421 | 1,339 switches, 93% re-rated; seed 101: 1,431, 92% |
| F3 | A first-party fatality whose driver keeps driving | Confirmed and fixed: crash deaths modeled | 0; 1 | 0; 0 (everyone killed in a crash, at the wheel or riding along, recorded as deceased) |

**F1. Recoveries ahead of payments.** Confirmed, and the cause is as described: subrogation was set on the
feature's eventual paid loss and received after its first close, so a feature that later reopened had already
received the supplement's share. The other insurer repays a claim as it is shown it: the share for the payments
to the first close (never more than they come to, less the salvage) is now received after that close, and a
reopening's share after its supplement is paid (`claims._schedule`). The total recovered, and so every ultimate,
is unchanged. Salvage is the sale of the wreck, one sale received after the settlement and never more than the
whole settlement; on a cheap car with a high deductible it can fetch more than the payments before a reopening,
and then the wreck is sold once the supplement is paid (found on seeds 7 and 101 after the first fix). `validate.py` checks the cumulative position on every payment date, and a unit test feeds the check
the audit's example (claim 133163).

**F2. Handover without new usage.** Confirmed. `_hand_over_cars` gave the car a new main driver but never
redrew its mileage and use, as moves and replacement cars already did. It now does, from the new driver's
commute, age, employment and whether the car is an extra one for them, dated to the handover so earlier
telematics periods keep their mileage (`Sim.mile_changes`); the re-rated row starts that day. A child under 16 is
no longer given the car. Not every switch changes the rated figures (a redraw can land on the same rounded
mileage); `validate.py` checks that most do.

**F3. First-party fatality.** Confirmed on seed 101: an uninsured motorist claim's first claimant, the policy's
own driver, was labeled a fatality while staying on the policy. Injury types were set from a claim's eventual cost
after the simulation, so a death never reached the household's records. A crash can now kill the insured at the
wheel (`config.CRASH_DEATH_*`: assumed rates sized on NHTSA's counts, higher in single-vehicle and severe crashes
and for older drivers), and the death is fed back into the simulation as the audit recommends: the driver leaves
the policy the day after dying, on the day of the crash or within a month (a LEAVE event, `simulate._crash_deaths`),
so a surviving spouse takes the policy over or it is canceled, their cars pass to the household's other drivers,
the policy's rows end that day and it is re-rated without them, and they drive nothing after the crash. Their own
claims (medical payments, uninsured or underinsured motorist) are fatalities, valued above the limit and so paid
it, and paid to their estate after the death; any other first-party injury is at worst a head or spinal one, and
third-party claimants, whom the data does not follow, can still be killed. A death that cannot be placed
coherently (in a replacement car that joined mid-period, or on a term's last day) leaves the driver badly hurt
instead. At the owner's further request, the household's other listed drivers riding along (`config.RIDE_ALONG_P`)
can die in the same crash, at a little less than the driver's risk: all of a crash's dead leave the policy the same
day, each has a medical payments claim of their own (and an uninsured motorist claim when the other driver was
uninsured or underinsured), and the new column `claim_feature.injured_driver_id` names the listed driver each such
feature is for. A household member killed while another drove has no bodily injury claim on the policy (Illinois
enforces the household exclusion then, 215 ILCS 5/143.01). `validate.py` checks that everyone killed in a crash
is recorded as deceased within a month of it and drives in no later crash, and that a feature's injured driver was
on the policy; unit tests check how a death cuts a policy's period, with a driver and a passenger killed together.
Children under 16 and passengers from outside the household are not followed, and the answer key's expected
losses leave out the deaths' own claims, a small amount ([limitations.md](limitations.md)).

### What changed in the data

Recoveries move later on reopened features (their totals are unchanged); cars passed to another driver are
re-rated on new mileage and use, which changes their premiums and true claim rates a little; drivers and the
household's other drivers riding along can die in crashes (11 in the default run, 2 of them riding along; 6 with a
claim of their own), which ends or passes on their policies. Because these change later random draws, every
figure of the default run moves a little: loss ratios by accident year 84.5%, 79.5%, 65.6%, 62.9% and 63.3% for
2022 to 2026 (were 81.3%, 70.4%, 67.5%, 58.2% and 65.5%), overall 69.8% (was 67.6%; 69.5% to 71.5% across five
seeds), annualized retention 81.3%; 22,933 claims (was 23,097). `validate.py` runs 175 checks (was 171), all
passing on the default run and on seeds 7, 11, 23, 42 and 101; the test suite has 79 tests.

Seed 101, rebuilt after these changes, is inside every calibration band. Before them, it had missed one: its bodily
injury frequency came to 0.66 per 100 car-years against a floor of 0.70, with its bodily injury losses 0.89 times
the answer key's expected ones, which is claim luck (calibration moves expected and actual together). Across the
five seeds in [benchmarks.md](benchmarks.md) that frequency runs 0.72 to 0.79; the band is not widened.

## Follow-up checks (22 November 2026)

Independent checks of v1.1.6 (content hash `4a1f9ef22b9bc813`) reported four reproducible defects and one
statistical miss. Each defect reproduces and is **confirmed and fixed**; "before" figures are from v1.1.6 and
"after" from the default run after this change (content hash `6a360e75d7d87f3f`).

| Finding | Verdict | Before | After |
|---|---|---|---|
| Rental reimbursements paid in full before enough rental days could have passed | Confirmed and fixed | 868 of 4,095 paid rentals | 0 |
| Payments to named insureds after their death | Confirmed and fixed | 6 payments | Paid to the estate (11 payments) |
| Later household changes alter earlier telematics measurements and discounts | Confirmed and fixed | A move after the offer day changed the mileage scored before it | Each period is measured on the mileage driven in it |
| Renewal decided on a later named insured's age | Confirmed and fixed | The current named insured at the time of simulation | The named insured on the offer day |
| Mileage and use published only as their last values | Confirmed and fixed | `insured_vehicle` only, at the simulation's last state | Rated values on every exposure row; `insured_vehicle` as of the valuation date |
| A seed narrowly outside one calibration band | Agreed: statistical, not a defect | | See below |

**Rentals.** A rental feature closed, and was paid, after a delay drawn without regard to how long the car was
kept: in v1.1.6 a fifth of paid rentals were paid before enough days had passed since the loss for the rental to
cost that much at its daily limit (the lowest number of days its amount allows). The rental's length now
travels with the claim (`truth.py`), the feature closes after the car is returned plus the invoice, and its
payment is made only after the return (`claims.py`). `validate.py`: "a rental is paid in full only once enough
days have passed since the loss for it to cost that much at its daily limit".

**Estates.** When the named insured dies and the policy ends with them, a claim already open was still paid to
them by name. A payment due to someone who has died before the payment day now goes to "Estate of" them, as it
would in practice; the insured-name check reads through the prefix, and a new check requires the estate exactly
when the person had died.

**Telematics and later changes.** Confirmed as described. A renewal's telematics scores are calculated on its
offer day for the driving up to it, but the simulation reaches that step after it has applied the rest of the
expiring term's household changes. Since v1.1.6 a move redraws the cars' mileage, so a move between the offer
day and the renewal changed the mileage behind the score of the driving before it, and with it the discount;
a move inside a scoring period also applied its new mileage to the whole period. Each mileage change is now
recorded with its day (`Sim.mile_changes`), and a period is measured on the day-weighted mileage of the days in
it (`simulate._miles_then`); a unit test checks that a later change leaves an earlier period unchanged. Drivers
and garaging were already read as they were on the days scored.

**Renewal age.** The renewal decision used the age of the policy's named insured as the simulation then held
it, which could be a surviving spouse who took the policy over after the offer day. It now uses the named
insured on the offer day, from the dated history the claim and payment records already use.

**Mileage and use over time.** Mileage and use change with a move or a new main driver, but `insured_vehicle`
showed only their last values, from the end of the simulation (which runs past the valuation date for terms in
force). `exposure` now has `rated_annual_mileage` and `rated_primary_use`, the values each period was rated on,
and `exposure_truth` has `true_annual_mileage` for each period. `insured_vehicle`'s use, mileage and parking
(and `insured_vehicle_truth.true_annual_mileage`) are as of the valuation date or the car's removal: those of
its latest exposure row starting by then. `validate.py` checks they match.

**The calibration miss.** Every calibration band is a statistical check on one draw of the book: a different
seed has different claim luck, and `validate.py` reports a band missed on a full-size book as a failure so it is
not overlooked. Across the five seeds in [benchmarks.md](benchmarks.md) the closest to an edge are bodily injury frequency per 100 car-years (0.71 to 0.83 against a band from 0.70),
bodily injury severity relative to national (0.87 to 0.99 against 0.85 to 1.15) and incurred against the
answer key's expected losses (0.94 to 1.01 against 0.93 to 1.07); bodily injury, with a few hundred paid claims
a year, is the noisiest.
An independent seed just outside one band, with every integrity check passing, is within that spread; the bands
are not widened for it, and [benchmarks.md](benchmarks.md) gives the spread to judge such a miss by.

### What changed in the data

Rental and estate fixes change dates and payee names only; the telematics fix changes some scores and so some
telematics discounts; the renewal fix changes a few renewal decisions. Because the rental timing and the
mileage records change later random draws, every figure of the default run moves a little: loss ratios by
accident year 81.3%, 70.4%, 67.5%, 58.2% and 65.5% for 2022 to 2026 (were 77.9%, 77.7%, 68.8%, 59.7% and 66.3%),
overall 67.6% (was 69.1%; 67.6% to 70.5% across five seeds), annualized retention 81.3% (was 81.2%); 23,097
claims (was 22,845) and 103,928 reserve transactions (was 104,316). `validate.py` runs 171 checks (was 168), all
passing on the default run and on seeds 7, 11, 23 and 42; the test suite has 75 tests.

## Two further realism audits (22 November 2026)

Two more audits, independent runs of another AI assistant, both read the default run at content hash
`963889a73f229de8` (all 145 checks passing) and listed records that still contradict their business context,
modeling shortcuts and statutory gaps. The first had 17 findings (numbered 1 to 17 below), the second 23
(F1 to F23); six of the second's repeat the first's. Each is answered as above. "After" figures are from the
default run after this change (content hash `4a1f9ef22b9bc813`).

### First audit

| # | Finding | Verdict | After |
|---|---|---|---|
| 1 | Unpaid December 2026 agency statements keyed as if created in 2000 | Confirmed and fixed | A statement's key follows the month it is drawn up |
| 2 | Bound quotes numbered first within each day | Confirmed and fixed | Quotes are numbered in the order asked for, bound and lost mixed |
| 3 | Formula reserves for every coverage trended at bodily injury's rate | Confirmed and fixed | Each coverage's formula reserve follows its own severity trend |
| 4 | Several defense firms on one lawsuit | Confirmed and fixed | One defense firm, appraiser, bill reviewer, salvage auction and subrogation insurer per claim |
| 5 | Represented uninsured motorist claimants paid under a stranger's name | Confirmed and fixed | The first claimant is the policy's own injured person ("Insured" or "Insured and Attorney") |
| 6 | Underinsured motorist claims on 25/50 minimum UM limits | Confirmed and fixed | Underinsured motorist only above the 25/50 minimum (215 ILCS 5/143a-2(4)) |
| 7 | Fraud referrals after the claim closed | Confirmed and fixed | Referred while the claim is open |
| 8 | A surviving spouse rated at the deceased's age; cars written off still counted | Confirmed and fixed | Current named insured's age; the car count follows the cars on the policy |
| 9 | Weekend hires, appointments and write-offs; fixed holidays at weekends; agents quoting on holidays | Confirmed and fixed | Business days throughout; agencies closed on four major holidays |
| 10 | A crash's coverages independent of one another | Confirmed and fixed | A crash severity shared by collision, property damage, injury, medical, tow and rental days (Gaussian copula) |
| 11 | Competitors copy our planted pricing errors; a December 2026 quote cliff | First part fixed; second agreed, documented | Competitors price near the true risk, so under-priced segments convert more |
| 12 | Appraisal fees booked as A&O; appraisals on glass and stolen cars | Partly adopted | No appraisal on glass or unrecovered theft; outside appraisers stay A&O (see below) |
| 13 | Commutes and mileage unchanged by a move or a new driver; employment never changes | Mostly fixed | A move redraws commutes and mileage; a replacement car takes its new driver's; employment documented |
| 14 | Warm-up drops 2021 total-loss liability claims; validator's overall loss ratio counts 2021 claims | Second part fixed; first documented | The overall loss ratio counts accidents in the extract |
| 15 | New customers' extra claims ignore the daily calendar | Confirmed and fixed | They follow Chicago's daily crash pattern |
| 16 | Hypercars in the catalog; EV tagging | Partly adopted | Catalog weights corrected rather than a price cap (see below); electric models tagged `ev` |
| 17 | Vendor keys by type; yearly numbers starting in the thousands; daily index ends 2026-09-30; a cancelled bill with an unreversed draft | Fixed (one documented) | Vendor keys mixed; yearly numbers start near 1; cancelled bills net to zero; the index ending is documented |

**12. A&O or DCC.** Not adopted as proposed. Since Schedule P's 1998 split, adjusting and other expense
(A&O) includes adjusters' and appraisers' fees whether staff or independent, and defense and cost containment
(DCC) is defense, litigation and medical cost containment (NAIC SSAP No. 55). An outside appraiser's fee is
therefore A&O. What was wrong was where it was charged: glass claims and stolen cars never recovered, which no
appraiser inspects, now carry none.

**16. Expensive cars.** The owner decided against an eligibility cap on price: real books do insure the odd
exotic car, and a cap would make the catalog less realistic, not more. The problem was the catalog's weights:
models the Chicago crash data never names (early EV pilots, fuel-cell cars, a $450,000 Ford GT) carried
default sales priors far above their real sales. They now get small, price-damped priors (and fuel-cell and
pre-2011 electric cars a hundredth), so no car over $1 million is insured in the default run.

**11 (second part), 14 (first part), 17.3.** Documented in [limitations.md](limitations.md): quoting stops
with the policies the extract writes, so late December 2026 has fewer quotes; the warm-up keeps no accident on
a car written off before 2022; Chicago's daily index ends on 30 September 2026 and later days use the
average day-of-week pattern.

### Second audit

| # | Finding | Verdict | After |
|---|---|---|---|
| F1 | Driving records and SR-22s after the driver or policy had gone | Confirmed and fixed | Records and filings only while the driver is insured here |
| F2 | A deceased named insured left unmarked; several current named insureds | Confirmed and fixed | Marked deceased on the cancellation day; one current named insured per policy |
| F3 | = 1 | Fixed | |
| F4 | = 4 | Fixed | |
| F5 | = 5 | Fixed | |
| F6 | Reviews and open reserves after a final payment | Confirmed and fixed | A final payment settles the feature: no reserve or review after it until a reopening |
| F7 | Fraud referrals after closing, on routine glass claims, from outcomes | Confirmed and fixed | Referred while open; routine glass and catastrophe claims rarely; from what is known at report |
| F8 | Renewal offers for no car and $0 | Confirmed and fixed | A policy left with no car is not offered a renewal; every term has exposure rows |
| F9 | Lenders paid on retained salvage; a lessee paid on a leased total loss | Confirmed and fixed | Only a car owned outright can be kept as salvage; a leased car's fees and supplements go to the lessor |
| F10 | = 3 | Fixed | |
| F11 | = 10 | Fixed | |
| F12 | Young drivers discounted on comprehensive; credit tiers not monotone | Confirmed and fixed | Distortions only on the driver coverages; insurance-score relativities never rise with the score |
| F13 | Plug-in devices recording phone use; trips of zero with miles | Confirmed and fixed | Phone use blank for plug-in devices (the score reweights); any mileage takes a trip |
| F14 | Low opening case reserves; no year-end closing entries | Second part fixed; first agreed, documented | Each December 31 closes the income-statement accounts to surplus |
| F15 | December 2026 cliffs in renewals, bills and quotes | Agreed, documented | |
| F16 | Notices of cancellation after payment; paid-in-full notices; monthly refunds from one change; micro-bills | Confirmed and fixed | See below |
| F17 | Underwriting cancellations without 30 days' notice; deductibles on subrogation | First fixed; second partly | 30 days' notice in the first 60 days; rental and tow recovered with the collision |
| F18 | = 11; a spurious under-35 step in direct conversion | Confirmed and fixed | Lost quotes get the bound policies' channel mix by age |
| F19 | Good-student status at joining; producers who started after their policies; Preferred tier fixed | First two fixed; third documented | Good student as of the driver's last day insured; producers hired through 2026 and assigned only policies written after they started |
| F20 | Theft-wave Kias and Hyundais with immobilisers; equipment drawn at random; old leased replacements; new cars over MSRP; exotics | Fixed except the price cap | Equipment by make and model year; new leases on near-new cars; values that do not count new-car inflation twice |
| F21 | Spouses added at 16; parents under 18 at a birth; duplicate names; repeat claims within days | First three fixed; last documented | Adults join at 18; parents at least 18 at the birth; no duplicate full names in a household |
| F22 | No 2022 catastrophe; storm losses at any hour; no tows | Second and third fixed; first explained | Loss times in each storm's NOAA hours (`catastrophe.start_time`, `end_time`); tows on flood, fire and wind |
| F23 | Documentation wording | Confirmed and fixed | |

**F6.** A feature's "Final Payment" now ends its case reserve: reserve reviews stop the day before it, the
estimate before closing leaves out a later reopening's supplement, and on a day with both, the payment is
booked after the reviews.

**F12.** The planted class distortions (under-charging young drivers, over-charging the middle-aged) apply
only to the driver-rated coverages (bodily injury, property damage, uninsured motorist, medical payments,
collision); comprehensive, rental and towing keep their fitted relativities. The fitted insurance-score
relativities are made non-increasing in the score (pool-adjacent-violators, "No Hit" apart), as a filed tier
table would be.

**F14.** Opening case reserves stay as they are: the warm-up simulates only the opening terms' 2021 part, so
older injury claims are missing on 1 January 2022, as [limitations.md](limitations.md) already says. A full
run-off inventory would need several more simulated years.

**F16.** A notice of cancellation is dated on the business day it is mailed and sent only if the bill is still
unpaid that day. A paid-in-full household that pays a renewal late pays within the grace period, before a
notice would go. An endorsement re-spreads the balance still to bill evenly over the installments not yet
issued; a return larger than that balance is refunded at once in one payment, and a balance too small to split
(under $25 an installment) is billed on the next installment alone, so installment bills of a few cents all but
disappear (5 under $1 in the default run, where the whole balance left was under $1). An additional premium on a
paid-in-full policy is still billed whatever its size (291 under $1), as some insurers do; others waive amounts
that small.
`validate.py` checks that every billing notice of cancellation went while a bill was past due and unpaid.

**F17.** Illinois requires 30 days' notice for a cancellation other than for non-payment. An underwriting
cancellation now takes effect 36 to 60 days after inception, with its notice mailed at least 31 days before
(`config.UW_CANCEL_DAYS`, `UW_NOTICE_DAYS`); `validate.py` checks each. Subrogation: when the other driver's
insurer pays back the repair, it now pays back the rental and the tow in the same share. A recovery is recorded
as the company's own share; the insured's deductible recovered with it is passed on outside these tables, as
[limitations.md](limitations.md) notes.

**F19.** The tier (company) is set at inception and does not change; a real company would move some policies
at renewal. Documented.

**F20.** Equipment now follows the model year: automatic emergency braking from about 5% of 2014 models to
nearly all from 2023, immobilisers spreading through the 1990s to nearly all by 2015, two or three years
earlier for luxury cars and EVs, every Tesla from 2015; the theft-wave Kias and Hyundais have none. A
replacement taken on a new lease is at most a year old. Values: the used-car index now lifts a car's value only
by how far used prices ran ahead of the new-car prices its model year sold at, and only once it is a year old,
so a one-year-old car is worth about 87% of its base price in 2025 instead of the 115% cap. No price cap on
eligibility, as for item 16.

**F21.** Two claims on one car within days stay possible (a car can be hit while parked the week after a
crash); not changed.

**F22.** The 13 June 2022 storm brought 56 damaging-wind reports, 3 tornadoes and 1-inch hail to the seven
counties, with no property damage reported to NOAA there, below the catastrophe rule
(`scripts/build_catastrophe_events.py`), so 2022 has no catastrophe by the same rule that picks the others.
Each storm's hours are now taken from NOAA's report times; the script prints them.

### What changed in the data

Most of the changes move records rather than money, but four change amounts: injuries and medical payments now
happen more in severe crashes (with their expected cost held), rental and towing are recovered by subrogation
with the collision, vehicle values for cars under a few years old are lower (new-car price inflation no longer
counted twice), and towing pays on floods, fires and storms. The rating plan is refitted to the new experience.

On the default run: loss ratios by accident year 77.9%, 77.7%, 68.8%, 59.7% and 66.3% for 2022 to 2026 (were
82.2%, 77.3%, 66.3%, 67.3% and 66.1%), of which catastrophes 0.0%, 3.4%, 2.1%, 0.6% and 6.0%; overall 69.1% (was
72.1%); annualized retention 81.2% (was 81.6%); earned premium $212.0 million (was $214.3 million). 195,367
policy terms (was 197,003), 438,440 exposure rows (was 440,655), 22,845 claims (was 23,135), 40,062 features
(was 40,414), 61,032 claim payments (was 62,875), 104,316 reserve transactions (was 129,559: no reviews after a
final payment), 879,886 bills and 891,769 receipts (were 879,257 and 890,607), 118,642 quotes (was 119,541) and
168,899 renewal offers (was 170,522). Every record-level finding of both audits is at zero, and `validate.py`
checks each: 168 checks pass on the default run (was 145) and on seeds 7, 11, 23 and 42 (content hashes `bb25cdc450625b55`, `f4c04822589267d0`, `5f1eb50ea0399d2c`, `7c5f8b927c449729`). The test suite has 74 tests
(73 pass, and one needs `pyarrow`).

Three more defects turned up while checking the five seeds and were fixed: two cars 30 model years apart could
share a VIN (position 7 now tells the year code's cycles apart, as real VINs do); a fraud referral could fall
while a claim was closed, before a late feature reopened it (referrals now come before the claim first closes);
and a new spouse could share the named insured's first name, or a teen an older sibling's who had moved out
(a newcomer's name now differs from everyone's who has been on the policy, and a spouse's first name from the
named insured's).

## Dataset realism audit (20 November 2026)

The audit regenerated the default run at `03c2634` (content hash `7b4b15d1dcb53b95`) and a second full-size
seed (7), found the economics, coverage mix, risk relationships and keys credible, and listed records that
contradict their own business context although every check passed. All five record-level findings and the
validator defect reproduce exactly and are **confirmed and fixed**. "Before" figures are from the audited
commit and "after" from this change, on the default run (content hash `06932bb41e745579`) and seed 7
(`1addd020a2ad50c6`).

| # | Finding | Verdict | Before (default; seed 7) | After |
|---|---|---|---|---|
| A1 | Lienholders paid on total losses of cars owned outright | Confirmed and fixed | 1,176 of 1,547 lienholder payments ($6,603,284.68); 1,240 | 0; a lender is paid on every paid total loss of a financed or leased car and on no other (578 payments) |
| A2 | Non-payment cancellations with no unpaid installment behind them | Confirmed and fixed | 17 of 5,267; 15 of 5,395 | 0 of 5,250; 0 of 5,380 |
| A3 | Joint claimant-and-attorney payments before the attorney was retained | Confirmed and fixed | 20 payments ($251,604.23); 23 | 0; 0 |
| A4 | Claims and payments naming a named insured who joined the policy later | Confirmed and fixed | 2 claims and 1 payment; 1 claim | 0; 0 (and 95 more claims named a later named insured who was already a driver) |
| A5 | Final-balance checks received at weekends | Confirmed and fixed | 83; 80 | 0; 0 |
| A6 | A validator check compared a column with itself | Confirmed and fixed | Could not fail | Fails on a claim moved to another policy (unit test) |
| - | Effective-dated histories stored the caller's array, not a copy | Found while fixing A4; fixed | The opening named insured read as the final one | Each history keeps what was recorded |
| A7 | Case-reserve allocation and the rating plan know eventual outcomes | Agreed and changed | Reserve shares from eventual payments; plan fitted to the true costs | Shares from what is known each day; plan fitted to simulated experience with credibility |
| A8 | Tails and joint relationships need independent calibration | Agreed and changed | No benchmark sheet or seed spread | [benchmarks.md](benchmarks.md): sources and use of every benchmark, spread across five seeds, tail and reserve diagnostics |
| A9 | A separately labeled messy extract | Not adopted | | The clean baseline stays the only edition |
| A10 | `run_summary.json` lacks the source revision, versions and content hash | Confirmed and fixed | Seed, size, dates and counts only | Hashes, source revision, library versions and fingerprints; `validate.py` checks the hashes |

### A1. Lienholder payments ignored whether a loan existed

**What we found.** Confirmed: a total loss was split between a lienholder and the owner at random (45% of
settlements of $200 or more), whatever the car's ownership, and the lienholder was picked per payment.

**Fix.** The car's ownership at the loss (owned, financed or leased) now travels with the claim
(`simulate._simulate_rows` to `claims.Development`). A total loss on a financed car pays off the loan first:
the balance is an assumed share of the settlement, from 35% to 120% (`claims.LOAN_PAYOFF_SHARE`); above
100% the loan is worth more than the car, the lender takes the whole settlement and gap cover, not this
policy, pays the rest (20% of the default run's financed payoffs). A leased car's settlement all goes to the
leasing company, which owns it. The owner gets the balance; a car owned outright is paid to its owner only.
When the lender takes the whole settlement its payment is the final one. Each car has one lender or lessor
(`payments.details`). A car whose owner keeps the wreck after a total loss has had its loan or lease paid off
by the settlement, and is shown as owned from then on.

**Checks.** `validate.py`: "a lienholder or lessor is paid only on a total loss of a financed or leased car,
never more than the settlement and one lender per car; every closed, paid total loss of a financed or leased
car pays one". Seed 7 turned up a financed car whose settlement was $72.25, which the old $200 threshold
had paid to the owner alone; the lender is now paid first whatever the amount.

### A2. Non-payment cancellation without an unpaid bill

**What we found.** Confirmed, and the cause is as the audit describes: the simulation chooses the
installment a leaving household will not pay when the term begins, before the term's changes are known. In
15 of the 17 terms a car left the policy before that installment was issued (in 13 it was written off,
destroyed or stolen) and the return premium left nothing on it; the other 2 began with no car while a
replacement was awaited, and the installment was issued before the replacement's premium was added. Either
way no bill was sent.

**Fix.** Moving a cancellation later would mean simulating cover, claims and changes the term never had, so
the rule is applied where the bills are known (`billing.without_a_bill_to_miss`, called by `tables.build`):
a household that leaves when it has no bill to miss is recorded as canceling at its own request on the same
day. Its cancellation is then keyed by staff, its unpaid bills are canceled and its balance settled like any
other request. In the default run these are the same 17 terms; the remaining 5,250 non-payment
cancellations each follow a billed, unpaid installment by 21 to 28 days.

**Checks.** The validator's 98% tolerance is replaced by a record-level rule: "every cancellation for
non-payment follows an unpaid installment, billed and due three to four weeks before it".

### A3. Attorney payees before the attorney was retained

**Fix.** The payee of an injury payment is decided on its own date (`payments.details`): before the attorney
is retained it is the claimant alone, from that day jointly with the attorney, the same law firm every time.
A void is made out like the check it cancels; its reissue goes to whoever is paid on the reissue date. In
the default run 20 advances now go to the claimant alone; 853 joint payments remain.

**Checks.** "a claimant is paid jointly with an attorney only on or after the day the attorney was retained,
and always after it".

### A4. Current insured identity rewrote historical records

**What we found.** Confirmed, and the cause was deeper than the extraction step. `tables.build` used the
policy's final named insured for a loss with no driver and for payments to the insured. Switching to the
simulation's effective-dated history of named insureds did not fix it at first: `History.add` stored the
array it was given rather than a copy, and the opening record had been given the policies' live
named-insured array, which the simulation later changes when a named insured dies and the spouse takes
over. So "the named insured before any change" always read as the final one. The same history is read when
a renewal offer decides whether to offer telematics to a young named insured, so a change after the offer
date could in principle have leaked into it; in the default run no offer or enrollment changed (the
`renewal_offer`, `telematics_enrollment` and `exposure` files are byte-identical before and after).

**Fix.** `History.add` copies what it is given. A loss with no driver is recorded against the named insured
on the loss date, and a payment to the insured is made out to the named insured on the payment date.
`involved_driver_id` changed on 97 claims: the 2 the audit found, and 95 that named a later named insured
who was already a driver on the policy at the loss (so no check could see it).

**Checks.** "each claim's driver was on the policy on the loss date, and each payment to the insured names
someone on the policy on the payment date" (every claim, not only at-fault ones). A unit test changes the
caller's array after recording it.

### A5. Final-balance check receipts at weekends

**Fix.** A check paying a final balance is banked on a business day, like every other check
(`billing.build`). **Checks.** "check and bank-draft receipts, returned drafts and refunds are dated on
business days"; card, online and agency payments can be made any day.

### A6. A validator check compared a column with itself

**Fix.** The key checks are now one function, `validate.integrity_links`, and test agreement as well as
existence: a claim's policy, term, vehicle and model year against its exposure row; each exposure row's
policy against its term's and its vehicle's; each payment's and reserve change's claim against its
feature's. **Negative controls.** A new test (`test_checks_catch_a_corrupted_record`) makes one record wrong
for each new or repaired check (a claim moved to another policy, a payment filed under another claim, a
lender paid on a car owned outright or left unpaid on a financed one, a joint payment a day before the
attorney, a claim driver or insured payee who joined later, a non-payment cancellation without its unpaid
bill, a check banked on a Saturday) and asserts that the check fails (for most, that it is the only one).

### A7. Information in reserves and pricing

**Agreed and changed.** Both points were documented limitations; on review they were worth fixing.

*Case reserves.* `truth.reserve_caps` gave each injury claimant a static share of the accident's per-accident
limit computed from their eventual payments and true damages. It is gone. A feature now carries its contractual
per-person (or per-claim) limit, which stays exact, and the accident's per-accident room. The reserve history
(`claims._share_accident_limit`) applies the shared limit from what is known on each day: a reserve set during
the day (a new claimant's formula reserve, say) takes no more than the room left by the accident's payments to
date and the other claimants' reserves; at the end of each business day with news the adjuster rebalances, so
if paid to date plus the reserves wanted would exceed the room, the room left after payments is shared in
proportion to the current estimates, and when a settlement frees room the others get their full estimates back.
A change made to another claimant's reserve this way is a "Reserve Review" on that day. A new validator check
holds every accident, on every day with a payment or reserve change, to its per-accident limit; unit tests
cover a claimant arriving, a settlement freeing room, a weekend report, and random estimates.

The audit's acceptance test (reserve error by coverage and age, revision rates, runoff, spread across seeds)
is `scripts/reserve_diagnostics.py`; its results are in [benchmarks.md](benchmarks.md), section 4. It found
one real fault, now fixed: property formula reserves were well below the average claim, so collision,
comprehensive and property damage claims still on their opening reserve at a year-end went on to pay 1.5 to 2.2
times that reserve. Formula reserves for property coverages are now set near the average paid per claim opened
(glass separately), as carriers set average reserves; injury reserves still start low, by design.

*Rating plan.* The relativities were fitted directly to the true expected loss cost. They are now fitted to
the company's claims experience (`rating.experience`): three years of claims on the book as first written,
drawn as a compound Poisson-gamma sum around the true expected costs. Each level is credibility-weighted
(limited fluctuation: full credibility at 1,082 claims times one plus the squared coefficient of variation of
claim size) with a bureau complement, which is the relativity the true costs indicate off by a random 5%; the
base rates come from the whole book's experience. Sparse levels now lean on the bureau and well-populated ones
carry the company's own luck: for example the cheapest bodily injury territory is priced at 0.69 where 0.77 is
indicated, and a collision territory at 1.03 against 1.17. `relativities_indicated` in the answer key still says
what each level is worth. Filing lags are already in the data as the rate-change history and the market cycle
(the book starts under-priced and catches up), so they were not added again.

### A8. Tails and joint relationships

**Agreed and changed.** [benchmarks.md](benchmarks.md) is the benchmark sheet the audit asked for: every
figure the validator holds the data to, with source, year, geography, units and inclusion rules, band, and
whether it was used for tuning, checked, assumed or held out. `validate.py --json` writes every band's figure, and
`scripts/seed_spread.py` builds several seeds and reports each figure's mean and range and how many seeds land
inside its band (section 2), with tail and joint diagnostics computed from the tables (section 3). New sourced
comparisons, held out from tuning: CCC's total-loss share of appraisals and the age of total losses, and S&P
Global Mobility's average vehicle age. They show departures that are reported rather than tuned away: total
losses are more frequent here than CCC's 22% (about 27% of paid collision and comprehensive claims, glass apart,
on a narrower definition) and fall on older, cheaper cars; the average written-off car is worth about $10,500
against CCC's $13,400 to $13,700. Severity percentiles, the share of injury claimants paid the full limit and
the concentration of cost in the costliest risks have no US figure on matching terms and are reported without a
target. Policy-grouped and time-based holdouts are left to case studies.

### A9. A messy extract

**Not adopted.** The tables are clean by design and stay the only edition; the owner does not want
deliberately degraded data. [limitations.md](limitations.md) (section 6) suggests pairing the data with the
real portfolio in `real_data/` for cleaning exercises.

### A10. Provenance inside each generated dataset

**Fix.** `pipeline.generate` writes `run_summary.json` after the CSVs, with `content_hash` (every CSV, as
the generator prints it), `tables_hash` (the data tables) and `answer_key_hash`, `hash_method`, and under
`build` the source revision and whether the generator's files had uncommitted changes, the Python, NumPy and
pandas versions, a fingerprint of every table's columns and of each reference file. Nothing in it depends
on when or where the run happened. `validate.py` recomputes the hashes ("the CSV files are the ones the
generator wrote"), checking the answer key only when it is present, so a student's copy can be checked too.

### What changed in the data

Only who is paid, how a few records are labeled and a few dates. Every loss and premium amount, every
exposure row, claim feature, renewal offer and telematics record is as before; the loss ratio (67.4%),
frequencies, severities, premiums and retention are unchanged. Claim payments 61,678 → 60,542 and reserve
transactions 125,378 → 124,306 (fewer split settlements); bills 887,710 → 887,706 and receipts 896,571 →
896,585 (the 17 relabeled cancellations); 97 claims' `involved_driver_id`; payees of 1,547 lienholder,
20 attorney and some insured payments. `validate.py` runs 147 checks (was 140), all passing on both seeds;
the test suite has 67 tests (was 64).

### Follow-up changes asked for by the owner

After the fixes above, the owner asked for further realism changes, made in the same pull request:

- **Notices of cancellation.** Every non-payment cancellation now has a notice of cancellation mailed at least
  ten days before it (215 ILCS 5/143.15), including a missed bank draft, which is attempted and returned first.
  `validate.py` checks every one (5,009 in the default run, none without).
- **Vehicles back to 1981.** The catalog reaches model year 1981 (EPA data starts in 1984; earlier years carry
  1984's specifications back), and old cars thin out with a scrappage taper, so model year 1997 no longer piles
  up the cars that would be older.
- **Surnames.** Whether a wife keeps her surname depends on the household's group (Pew Research Center, 2023);
  children take their father's surname.
- **Identifiers.** Integer keys are the company's system counters (founded 2000; billing 2008, claims 2012,
  quoting 2014, correspondence 2016, telematics 2018), so they start far above 1 and have gaps.
- **Real catastrophes.** Ten storms from NOAA's Storm Events Database for the seven counties (2023 to 2026)
  replace the fictional events; their losses are simulated.
- **Claims open at the start.** A warm-up year (2021) is simulated, so the extract opens with claims, reserves
  and payments on earlier accidents, and the ledger's opening entry carries their reserves.
- **Records, not totals.** Derived and aggregated columns were removed; [schema_changes.md](schema_changes.md)
  lists them and how to rebuild each.
- **A7 and A8**, above.

The default run is now content hash `963889a73f229de8` (seed 7: `6718177c0b52ab2e`); 145 checks pass on both,
and on seeds 11, 23 and 42, with every calibration figure inside its band on all five. Every record-level
finding A1 to A5 stays at zero (the validator checks each). The test suite has 74 tests.

## Third review (18 November 2026)

The reviewer regenerated the default run at `9fe6062` (content hash `bfb1ac64b90c932b`), confirmed the four
fixes of the second review (renewal rating dates, conviction dates, reserves within limits, underinsured
motorist), and found two remaining problems of the same kind: decisions dated in the past that used
information from later. Both are confirmed and fixed. "Before" figures are from the reviewed commit and
"after" from this change, on the default run (seed 20250101, 43,368 policies, 1 January 2022 to 31
December 2026; content hash `4b5bca69599df49e`).

| # | Finding | Verdict | Before | After |
|---|---|---|---|---|
| F1 | Telematics scores attributed to a driver assigned to the car after the driving | Confirmed and fixed | 211 scores overlap another driver's exposure; 48 name a driver first assigned after the window | 0 and 0; 165 scoring periods split where the car's driver changed |
| F2 | Renewal decisions use the household, claims and premium as they stood after the offer date | Confirmed and fixed | Offer-date and inception-date inputs mixed; declined renewals left no record of their offer | Every input as at the offer date; 179,620 offers kept, declined ones included, in the new `renewal_offer` table |
| - | A score of a customer who left the program linked to a term that began before it | Found while checking F1; fixed | 4 scores | 0 |
| - | Opt-ins at a renewal that was not taken recorded as enrollments that ended the day they began | Found while fixing F2; fixed | 257 enrollments | 0 (the opt-in is on the renewal offer instead) |

### F1. Telematics uses a driver assigned after the driving occurred

**Finding.** A car's score was generated from, and published against, the car's primary driver as it stood
when the score was calculated, after the whole expiring term had been simulated. A car taken over by
another household driver after (or during) the scoring window was scored as the new driver's driving.

**What we found.** Confirmed: 211 of 56,491 scores overlap an exposure row of the same car rated to a
different driver, and 48 scores with windows starting in 2022 or later name a driver whose first exposure
on that car begins after the window ends (the reviewer's example, score 6564, was such a takeover). Two
smaller leaks of the same kind: the take-up of the program used the drivers on the policy at the renewal
date rather than on the offer date, and a driver's propensity used their current marital status. Cars sold
or written off between the scoring date and the renewal were not scored at all, although they were on the
policy that day.

**Fix.** The simulator now keeps effective-dated histories: each car's rated driver and garaging ZIP (from
the exposure rows, plus an explicit opening assignment for the days before the first simulated period),
each driver's marital status, each policy's named insured and homeowner status. Scoring reads them, not the
current state:

- **One score, one driver.** A scoring window in which the car's assigned driver changed is split at the
  change, and each part is scored as that driver's driving (their propensity and age at the time, the ZIP
  the car was kept in). A part shorter than the 45-day minimum earns no score. A window before the car's
  first exposure row uses the opening assignment.
- **The car's discount** for the next term is the average of the discounts its scored parts earned,
  weighted by the days each was monitored and rounded half up to a whole percent, or the 5% participation
  discount if no part was monitored long enough. Nearly all windows have one part, so for them nothing
  changes.
- **Who is scored.** Every monitored car on the policy on the scoring date, including one that leaves
  before the renewal (its score applies to no term).
- **Take-up** of the program uses the household on the offer date (as quoted, for new business).

**Checks.** `validate.py`: "each score is the driving of the driver assigned to the car on the days scored"
(against the exposure rows' rated driver, the reviewer's interval check, plus the opening assignment for
periods before a car's first row); "each enrolled car starts a term on the days-weighted discount its
scores for that term earned"; "a score's discount applies to a later term of the same policy". Tests in
`TelematicsAssignmentTest`: a spouse taking the car over after the window leaves the earlier score and its
driver unchanged; moving that takeover to any later date changes nothing, metrics included, with the same
draws; a change inside the window splits it, and a move alone (same driver) does not. The existing
membership checks still pass.

**Found along the way.** A customer who left the program earned no discount, and their last score was
marked with day `-1` for "applies to no term". Day `-1` is a real day, 31 December 2021, the start of some
opening terms, so 4 such scores were linked to that term. A sentinel that cannot be a day replaces it.

### F2. Renewal decisions use information from after the offer date

**Finding.** The renewal was described as decided with the offer in hand, but its premium, household and
"still has a car" test came from the policy as it stood at the end of the expiring term; claims counted if
reported before the effective date; only driving records were taken as at the offer date. The published
rating date was corrected for re-rated renewals, but the decision itself was not. Declined renewals left no
record of the offer.

**What we found.** Confirmed by source. The reviewer did not quantify it; a controlled counterfactual now
does. Holding every random draw fixed, evaluating each of the 174,487 renewals decided in the new default
run with the old information (the policy at the end of the expiring term, claims up to the effective
date) instead of the offer-date snapshot gives a different premium for 12,013, a different set of cars for
4,223 and a different claim count for 3,223, and changes 315 renew-or-leave decisions (263 that renew on
the offer-date information would have been lost, 52 the other way) and 16 company non-renewals. Few
decisions change because most late changes move the premium modestly, but the inputs a retention model
would be given were not those the decision used.

**Fix.** An explicit timeline. On the offer date, 30 to 45 days before the renewal:

1. **Underwriting review.** Drivers on the policy that day, with incidents known by then, dated in the
   three years before the renewal. A flagged policy may be non-renewed by the company (a notice, not an
   offer).
2. **Telematics.** Enrolled cars are scored (F1), and the program is offered to non-members.
3. **The offer.** The renewal premium is evaluated from the expiring term's exposure rows in force on the
   offer date (cars, rated drivers, address, homeowner status, limits and deductibles), rated for the new
   term at its rates, with the records known that day and the telematics discounts just earned. It is
   compared with what the same cars cost on the expiring term (like for like).
4. **The customer's decision**, on that offer: its premium change, tenure, the claims the customer
   reported since the previous offer and by this one, and the other renewal-model terms.

Nothing after the offer date changes these. Later events remain later events: a household change before
the effective date re-rates the pending renewal (a revised offer, as before), a cancellation before the
effective date ends the policy ("Canceled Before Renewal"), and a household with no car left has nothing to
renew. Decisions draw from a dedicated random stream, one pair of draws per policy per term, so a policy's
decision depends only on its own history up to the offer. Customers do not re-decide on a revised offer;
that is a stated simplification ([limitations.md](limitations.md)).

**New table `renewal_offer`**: one row per renewal evaluated, 179,620 in the default run: 162,374
renewed, 11,979 not renewed by the insured, 134 company non-renewals, 1,146 canceled before the renewal
date and 3,987 pending (taking effect after the valuation date). Each row has the offer date (the decision
date and snapshot date), the vehicles offered, the expiring and renewal premium for a full term, the
premium change, the telematics opt-in, the underwriting decision, the revised offer date (10,393 offers,
881 of them not renewed), the outcome and the renewal term. The snapshot is the expiring term's exposure
rows in force on the offer date, which `validate.py` checks row by row. The answer key's
`renewal_offer_truth` gives each offer's true acceptance probability. `customer_contact` now has a renewal
offer for every offer sent (not only those taken up), a "Notice of Non-Renewal" for company non-renewals,
and a revised offer for every revision.

**Final-rating corrections versus the decision timeline.** The second review's finding 1 corrected the
*final rating* of a renewal changed after its offer (its premium and `rating_date`), and that correction
stands: 9,512 renewal terms in the new run are re-rated after a household change. It did not touch *when
the renewal was decided*, which is what F2 fixes: the original offer and the decision on it now use only
what was known on the offer date, whatever the revision brings later.

**Checks.** `validate.py`: each offer is made during its expiring term and by the valuation date; each
covers the vehicles in force on its offer date at the premium they were then insured for; every renewal
term after a policy's first in the data is a renewed offer with the term's offer date and revised offer
date; every non-renewed term has one offer whose outcome is its non-renewal reason; "Canceled Before
Renewal" exactly when the expiring term was canceled after the offer; pending only after the valuation
date; no telematics offer or revision for a company non-renewal. Tests in `RenewalTimelineTest`: every
offer of a run, evaluated again at the end of the run with the whole later history present (later claims,
moves, cars, drivers and records, and the scrambled current state of the policy), gives the same premium,
probability and decision with the same draws; adding a claim reported the day after the offer, or records
known the day after, or later exposure rows changes nothing, while a claim reported on the offer date
itself counts; three at-fault accidents known on the offer date trigger the underwriting review, the same
known a day later do not. The existing rating-date checks and the revised-offer contacts are kept.

### What changed in the data

The order of random draws changed, so every table differs by sampling noise; every calibration band still
holds. Policy terms 205,616 → 205,742; exposure rows 460,536 → 460,831; claims 20,381 → 20,343; telematics
scores 56,491 → 59,553 (split windows and cars scored on their last scoring date) and enrollments 12,607 →
12,298 (no enrollment for an opt-in whose renewal was not taken); customer contacts 329,368 → 347,405
(renewal offers that were declined). Retention is unchanged in substance: annualized policy retention 83.3%
→ 83.4%, insured non-renewals 12,109 → 11,979, company non-renewals 121 → 134. The renewal rate falls with the
offered change, from about 95% for changes of 5% or less to 87.5% for 10% to 20% and 75% above 20%. The
overall loss ratio is 66.9% (was 68.3%), and the expected loss ratios plus catastrophes for 2022 to 2025
are 79.3%, 77.6%, 67.9% and 64.7% (were 79.1%, 77.1%, 67.9%, 64.8%).

### Tables, realism and follow-up work

The reviewer's assessment of the table structure and statistical realism (a credible teaching extract, not
an operational database; effective-dated exposure; a recognizable claims structure; missing billing, party
and status histories; national calibration that does not validate Chicago subgroups; immature 2026
losses) is **agreed**; the limits are in [limitations.md](limitations.md). Of the recommended follow-up
work, the offer and decision history is done (`renewal_offer`). Not done in this change, and listed as next
steps: a fixed matrix of seeds and sizes separating accounting invariants from stochastic tolerances;
rebuilding paid-plus-outstanding against limits at every historical transaction date (validated now at the
valuation date); further cross-table ownership checks; and subgroup frequency, severity and development
with uncertainty intervals. The reserve caps' use of eventual paid amounts and latent damages
(`autoins/truth.py`, `reserve_caps`) is a simplifying assumption, now stated in the limitations.

## First and second reviews (at `5232739` and `ccd1d9d`)

The first review was at commit `5232739` (30,000 policies, the old table names), the second at commit
`ccd1d9d` on `main` (51,391 policies). The second review's written report was never delivered, because its
session ended first, so its findings are reconstructed here from the checks it ran.

"Before" and "after" figures in this section are measured on the default run at the time (seed 20250101,
43,368 policies, 1 January 2022 to 31 December 2026), generated with the code before and after the fixes.
Each fix has a check of its own in `validate.py` or a test in `tests/`, so the problem cannot come back
unnoticed.

### Summary

| # | Finding | Verdict | Before | After |
|---|---|---|---|---|
| 1 | Renewals rated with changes made after their rating date | Confirmed and fixed (partly a dating artifact) | 1,738 rows at an address not yet in force; 34,493 rows whose car joined after the rating date | 0 and 0 |
| 2 | Conviction dates before 2022 moved to 1 January 2022 | Confirmed and fixed | 7,982 convictions dated after the day they became known; 210 SR-22 filings moved too | 0 |
| 3 | Case reserves above the coverage limit | Confirmed and fixed | 61 features and 9 accidents above a limit | 0 |
| 4 | Underinsured motorist ignores the at-fault insurer's per-accident limit | Confirmed and fixed | $45,000 paid instead of $70,000 in the reviewer's example | Correct, in claims and expected losses |
| 5 | Telematics scores before the driver joined the policy | Confirmed and fixed (mostly the same dating artifact as 1) | 6,741 score windows | 0 |
| 6 | Bound quotes carry the telematics discount, lost quotes never can | Confirmed and fixed | 6,233 of 23,315 bound quotes discounted, no lost quote | Both offered alike; new `quote.telematics_opt_in` |
| 7 | Real-data comparison scales expected losses down twice | Confirmed and fixed | Gini 0.247, top/bottom decile 5.22 | 0.251 and 5.97 |
| 8 | Release files leave out the documents the README links to | Confirmed and fixed | `README.md` only | `README.md`, `CHANGELOG.md` and `docs/` in every zip |
| 9 | Documentation claims more than the checks prove | Confirmed and fixed | Four statements | Reworded |
| 10 | Loss-ratio checks mix catastrophe and non-catastrophe losses | Found while checking finding 9; fixed | Actual (with catastrophes) against expected (without) | Like for like |
| - | `claim_expense_dimension` is not a real dimension | Already addressed | The table was removed when the schema was restructured | - |
| - | Party records, billing, quote versions, claim status history, payees | Not adopted; listed in limitations | - | - |
| - | Effective-dated driver and vehicle relationships; coverage records | Already present in another form | - | - |
| - | Circular calibration, quotes built around the bound book, no opening claim inventory, national benchmarks, Illinois scope | Agreed, already documented | - | - |

### Defects

#### 1. Renewals rated with changes made after their rating date

**Finding.** A renewal is rated 30 to 45 days before it takes effect, but the simulator applied the
household as it stood on the effective date. The reviewer found renewal rows rated at an address the
household moved to after the rating date, and cars added after it.

**What we found.** Two causes, one real and one a dating artifact:

- *Real:* a move, a car bought or sold, or a driver joining or leaving in the last weeks of a term
  reached the renewal without changing its rating date. Real policy systems re-rate the pending
  renewal when such a change is processed, and send a revised offer.
- *Artifact:* drivers and cars on policies already renewing on 1 January 2022 were all dated as added
  on the start of their first term in the data, after that term's rating date, although they had been on
  the policy for years. That accounted for 28,440 of the 34,493 flagged car rows and most of the 28,503
  flagged driver rows.

**Fix.**

- A renewal changed between its offer and its effective date is re-rated on the day of the change: its
  rating date moves to that day and a "Revised Renewal Offer" contact is sent: 9,727 of 179,382
  renewals (5.4%) are re-rated. `policy_term` gains `offer_date` (when the term was quoted) beside `rating_date` (when it
  was last rated), separating the original offer from the re-rating, as the reviewer suggested.
- Drivers and cars on policies renewing on the start date now join at the policy's inception, on being
  licensed, or when the car was bought (after its model year went on sale), whichever is later, and
  always before the first rating in the data. A rare one that joined later re-rates that renewal too.

**Check.** `validate.py`: "renewals and changes are rated with the car, driver and address on the
policy on the rating date" and "every term is offered, then rated, before it takes effect".

#### 2. Conviction dates before 2022 moved to 1 January 2022

**Finding.** `tables.py` clipped negative day numbers (dates before the start) to zero before writing
conviction dates, so convictions from before 2022 became 1 January 2022, after the day the
violation reached the driving record.

**What we found.** Confirmed: 7,982 convictions fell after their known date and 8,043 were dated 1
January 2022. The same clipping moved 210 SR-22 filing dates. (After the fix, 13 convictions fall on 1
January 2022 by chance.)

**Fix.** Dates before the start are written as they are. A conviction now always falls after the
violation and on or before the day it reaches the driving record.

**Check.** `validate.py`: "a conviction falls after the violation and on or before it reaches the
driving record"; "an SR-22 is filed before it ends, and only after the driver joined the policy". Test:
`test_conviction_and_sr22_dates_before_the_start_are_kept`.

#### 3. Case reserves above the coverage limit

**Finding.** Reserve estimates (and the $250 minimum reserve) had no limit cap, so paid plus case
reserve could exceed a per-person limit, a per-accident limit or a $100 towing limit.

**What we found.** Confirmed on the valuation date: 36 bodily injury, 4 medical payments, 3 rental,
17 towing and 1 underinsured motorist features, and 9 accidents above their per-accident limit.

**Fix.** Every claim feature now carries the most it could pay: its per-person or per-claim limit, the
car's value less the deductible for physical damage, and for injury coverages a share of the
per-accident limit that is never less than what that claimant is eventually paid (so claimants' caps
add up to no more than the per-accident limit). Reserve estimates, the minimum reserve and reopening
reserves are held within it. Expense reserves stay separate. Excess-of-limits exposure is not
modeled.

**Check.** `validate.py`: "paid loss plus case reserve stays within every per-person, per-accident and
per-claim limit". Test: `test_reserve_caps_stay_within_the_limits`.

#### 4. Underinsured motorist ignores the at-fault insurer's per-accident limit

**Finding.** When an underinsured at-fault driver injured several people, the simulator assumed their
insurer paid each up to its per-person limit, ignoring its per-accident limit. With three $40,000
injuries and an at-fault policy of 25/50, it assumed that insurer paid $75,000 although it can pay only
$50,000, so our underinsured motorist cover paid $25,000 too little.

**What we found.** Confirmed. The reviewer found no case in the default output; it needs several
injured occupants and an at-fault policy whose per-accident limit binds, which is rare.

**Fix.** The at-fault insurer's payments are shared under its per-accident limit before our benefit is
worked out, in the simulated claims and in the answer key's expected losses (the accident-level
adjustment for underinsured motorist now rises up to 1.035 where several claimants leave more to pay).
The reviewer's example now gives $70,000.

**Check.** Test: `test_underinsured_allows_for_the_other_insurers_per_accident_limit`.

#### 5. Telematics scores before the driver joined the policy

**Finding.** Some score windows started before the scored car's primary driver was on the policy.

**What we found.** Confirmed: 6,741 windows, all but two before 2022, mostly caused by the dating
artifact in finding 1. Two related problems: a policy already in the program on the start date could have
joined it before the policy was written, and a car's window could start before the car was added.

**Fix.** A window starts no earlier than the day the car and its primary driver were both on the policy,
and an enrollment from before the extract starts no earlier than the policy's inception.

**Check.** `validate.py`: "a policy joins the program after it was written, and a car is scored only
while it and its driver are on the policy".

#### 6. Bound quotes carry the telematics discount, lost quotes never can

**Finding.** A bound quote shows the premium the policy was written with, including the 5%
participation discount when the customer joined the program. Quotes that did not bind were priced
without the program, so a discounted quote was always a bound one.

**What we found.** Confirmed: 6,233 of 23,315 bound quotes were discounted and no lost quote was.

**Fix.** Every quote now offers the program. Prospects who did not bind opt in at the rate the
program's take-up model gives new business, and are quoted with the participation discount. A new
column, `quote.telematics_opt_in`, shows who said yes: 26.7% of bound quotes and 28.7% of the others
(62% of lost quotes come through the direct channel, where take-up is highest; within each channel the two
rates agree to within half a point).

**Check.** Test: `test_renewals_changed_after_the_offer_are_re_rated` (which also checks the quote
column).

#### 7. Real-data comparison scales expected losses down twice

**Finding.** `scripts/compare_real_data.py` divided each row's answer-key expected loss by the row's
full cover period and multiplied by its earned exposure.

**What we found.** Confirmed. The answer key's expected loss already covers only the earned part of
each row (inside the extract, up to any cancellation), so rows that started before 2022 were scaled
down a second time. Only the comparison's "true expected loss" line was affected: on the same data its
Gini on claim counts moves from 0.247 to 0.251, on cost from 0.362 to 0.366, and the top-to-bottom
decile frequency ratio from 5.22 to 5.97. `validate.py` was not affected (it already works on the earned
window).

**Fix.** The expected loss is summed as it is. `docs/real_data_comparison.md` is regenerated.

#### 8. Release files leave out the documents the README links to

**Finding.** The reviewer listed the release zip's contents and found `docs/limitations.md`,
`docs/schema_changes.md`, `docs/real_data_comparison.md` and `CHANGELOG.md` missing.

**What we found.** Confirmed: the zips carried `README.md`, whose links to those files were broken for
anyone with only the release.

**Fix.** Every release zip (data and answer key, CSV and SQLite) now carries `README.md`,
`CHANGELOG.md` and `docs/` at the paths the README links to, and the release notes point readers to
`docs/limitations.md`.

#### 9. Documentation claims more than the checks prove

**Finding.** The reviewer searched the limitations page for overstated claims.

**What we found and fixed.**

- "Income, insurance score, limits, payment plan and multi-policy status stay fixed for a policy's
  life" was wrong: liability limits can change at renewal. Corrected in the README and the limitations
  page.
- "The synthetic tables have none [of the errors of a real extract]: `validate.py` checks every record
  reconciles" overstated what passing the checks proves, as findings 1 to 5 showed. Reworded: the
  checks show their rules hold, not that no other inconsistency exists.
- "Internally consistent" became "checked for internal consistency".
- Frequency and severity are compared with the national table "approximately, on its published
  definitions", not "on its own definitions": the source does not publish how it counts claims with
  several payments.

#### 10. Loss-ratio checks mix catastrophe and non-catastrophe losses

This came up while checking finding 9, and may or may not be one of the second review's findings. The
answer key's expected losses leave out catastrophes (fictional, dated hail, wind and flood events),
but `validate.py` compared them with each year's actual losses including catastrophes, and with
industry loss ratios that include them. Both comparisons are now like for like: actual losses
excluding catastrophes against expected, and expected plus the year's catastrophe losses against
industry.

### Suggestions about the table structure

| Suggestion | Response |
|---|---|
| `claim_expense_dimension` is a compatibility summary, not a dimension | **Already addressed.** It was removed when the tables were restructured; expenses are on `claim_feature` and `claim_payment`. |
| Effective-dated policy-driver and driver-vehicle relationships | **Already present in another form.** `driver.added_date` and `removed_date` date each driver's time on the policy, and each `exposure` row names the rated driver of one car for one period. A person never appears on two policies here: drivers who leave a policy leave the company, so there is no cross-policy identity to keep. |
| Coverage records with identifiers | **Already present in another form.** Each `exposure` row is the coverage record for one car and period (every limit, deductible and option, with its premium), and a claim feature points to it through `claim.exposure_id` and `claim_feature.coverage_code`. A separate coverage table would hold the same facts in a longer layout. |
| Party records and roles (claimants, passengers, attorneys, repairers, payees) | **Not adopted.** A sizeable addition; listed in [limitations.md](limitations.md) (claimants are numbered within their claim only). |
| Billing accounts, invoices, installments and receipts | **Not adopted.** Listed in limitations; non-payment cancellations are present without the billing trail behind them. |
| Quote versions and underwriting decisions | **Partly adopted.** Renewals now show an offer and, when re-rated, a later rating date and a revised offer. New-business quote revisions, referrals and declines are listed in limitations. |
| Claim status and assignment history; payees and reversal links | **Not adopted.** Payments already record voids and reissues as transaction types; adjuster assignments, status history and payees are listed in limitations. |

### Observations about realism

The reviewer noted that the rating plan is fitted to the simulator's own expected losses, that quotes
are built around a book already generated, that claims open before 2022 are missing, that national
benchmarks do not validate Chicago subgroups or large-loss tails, and that the scope is Illinois personal
auto. **Agreed; all are already documented** in [limitations.md](limitations.md) (sections 2, 4 and 5).
The reviewer's size figures (122,684 car-years, $136.5 million earned premium, a 65.6% loss ratio) were
for the earlier 30,000-policy default; the current figures are in the README.
