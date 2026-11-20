---
title: Teaching with the data
nav: 5
nav_title: Teaching
eyebrow: For instructors and learners
lede: One consistent company supports a whole curriculum, from a first SQL join to a reserve review or a fairness audit. Here are questions it can answer, grouped by course, and how to use the answer key.
description: Questions the Lakefront data can answer in data analysis, actuarial pricing and reserving, marketing, insurance accounting, audit analytics and fairness courses, and how to use the instructor answer key.
---

## What makes it good for teaching

- **The answers exist.** The rating plan has weaknesses to find, and an answer key records what the insurer couldn’t see, so students’ findings can be checked against what is really there, not just against each other.
- **It rewards care.** Questions only come out right if students join at the right grain, use the values in force at the time, and allow for claims still to be reported. Those are the habits that matter at work.
- **It scales.** The same data serves a one-hour SQL lab and a semester project.

## Questions it can answer

None of the answers are given here. The repository’s [instructor notes](%REPO%#what-a-case-study-can-find-instructor-notes) list what the data shows, with figures.

### Data analysis and SQL

- How many policies, cars and drivers were in force at the end of each year? (Which table, and which dates?)
- Which ZIP codes, territories and regions have the most claims per car-year? The highest average premium?
- On which days of the week and hours of the day do crashes happen? Thefts? What happened on the busiest days?
- How long do claims take to be reported, and to close, by cause of loss?
- Which cars are most common on the book, and how old is the average insured car?

### Actuarial pricing

- For each discount and surcharge, compare what it gives away with what the risk justifies. Which are earned?
- Are young drivers priced adequately? Drivers over 75? How does the loss ratio move with reported mileage?
- Is there a risk the rating plan doesn’t see? Look at vehicle safety features, parking, particular models and model years, and the new customer’s first months.
- Fit frequency and severity models (GLMs) by coverage. Which variables matter, and how do your relativities compare with the plan’s?
- Does the telematics discount follow the driving score closely enough? How much of the members’ better results is selection, and how much is better driving while monitored?

### Reserving

- Build paid and incurred development triangles by accident year and coverage, as of each year end.
- Estimate ultimate losses and IBNR for each accident year with the chain ladder and one other method. Check your IBNR against the claims not yet reported in the answer key.
- How adequate are early case reserves on bodily injury claims? How does that show up in the triangles?
- What is each accident year’s loss ratio at ultimate, and how much does the newest year’s still have to develop?

### Marketing and retention

- How does the share of quotes that bind change with the quoted price against the best competitor? Around rate increases?
- How does retention change with the size of the renewal increase? After a claim? On the first renewal?
- Which channel and which agencies bring customers who stay?
- When in the year do people shop, and why might that be?

### Insurance accounting

- Rebuild written, earned and unearned premium by month and company from `premium_transaction`, and tie them to the general ledger.
- Age the premium receivables at each year end. How much was written off, and from which customers?
- Reconcile case reserves and paid losses in `gl_journal` to `claim_reserve_transaction` and `claim_payment`.
- Why do calendar-year loss ratios from the ledger differ from accident-year ones?

### Audit analytics

- Is the check sequence complete? Explain every voided and outstanding check.
- Was every payment approved by someone with the authority, employed on that day?
- Test payment amounts with Benford’s law. Which vendors receive the most, and is that concentration a concern?
- Which tests would you run on a claims payment file, and what would a finding look like?

### Agency and distribution management

- Rank agencies by loss ratio. Which differences are real and which are luck? How much business does an agency need before its results mean something?
- How much commission does each channel cost per policy, and per policy kept?

### Fairness and ethics

- Premiums vary by ZIP code. How do they relate to each ZIP’s racial and ethnic make-up, and does the loss ratio vary the same way?
- Estimate each driver’s race and ethnicity from surname and address with BISG (Bayesian Improved Surname Geocoding, the method regulators use), test the premiums for disparate impact, and check your estimates against the answer key.
- A name works as a stand-in for race and ethnicity. What does that mean for which variables an insurer may use?

## The answer key

The answer key is a separate download for instructors. It holds what the insurer could never see:

| Table | What it reveals |
|---|---|
| `exposure_truth` | Each exposure row’s true expected loss by coverage |
| `driver_truth` | Each driver’s hidden risk multiplier, and race and ethnicity for the fairness exercise |
| `policy_truth` | Each household’s hidden stability and risk |
| `insured_vehicle_truth` | Each car’s true annual mileage, and whether it is one of the models in the Kia and Hyundai theft wave |
| `location_truth` | Each ZIP code’s true crash and theft hazard beside the public indices the territories use, and the chance the other driver is uninsured |
| `agency_truth` | Each agency’s true book quality and hold on its customers |
| `claim_feature_truth` | What each reported feature will finally cost, including payments, recoveries, reopenings and closes after the valuation date |
| `renewal_offer_truth` | Each renewal offer’s true chance of being accepted |
| `unreported_claim` | Losses that had happened by the valuation date but were not yet reported |
| `rating_plan.json` | The full rating plan: the filed discounts, what each is really worth, and every other factor before and after distortion |

!!! warning "Keep it from students"
    Give students the data download only, not the answer key or access to the repository.

## Practical tips

- **Start with the [data model](/data-model/).** Ten minutes on grain and on current versus historical values saves hours of wrong answers.
- **Pick the format for the course.** CSV for spreadsheets; SQLite for SQL courses (it enforces the keys); Parquet for Python and R.
