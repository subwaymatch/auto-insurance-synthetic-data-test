---
title: Lakefront
layout: home
description: Five years of a Chicago-area auto insurer’s data for teaching and analysis: policies, drivers, vehicles, premiums, bills, claims and a general ledger, in CSV, SQLite and Parquet.
---

## What the data holds

The data covers the whole company, so answering a question means finding the right table, joining on the right key, and knowing what was known when.

<div class="feature-grid" markdown="1">
<div markdown="1">
### Places, cars and days
290 ZIP codes across the seven counties with their Census demographics; every make, model and model year sold in the US since 1997; and claims that rise on Fridays, holidays and snow days, as crashes do.
</div>
<div markdown="1">
### Business keys
Policy numbers with check digits, claim and feature numbers, VINs, invoice numbers and an unbroken check sequence, as printed on the company’s documents, beside the integer keys that join the tables.
</div>
<div markdown="1">
### History, not a snapshot
Policies renew, move, change cars and add teenagers mid-term. Each change re-rates the policy from that day, and `exposure` keeps every version, so you can see exactly what was in force on the day of a loss.
</div>
<div markdown="1">
### Claims that develop
Each claim has coverages, payments, salvage and subrogation recoveries, and a case reserve that is re-estimated over time. Every reserve change is recorded, so development triangles can be built as of any date.
</div>
<div markdown="1">
### The money adds up
Every premium is billed and collected, every claim payment has a payee, a check number and an approver, and a monthly general ledger ties to each subledger, from written premium to case reserves.
</div>
<div markdown="1">
### Three formats
CSV files, one SQLite database with every primary and foreign key declared, and Parquet files with their column types set: the same tables in each.
</div>
</div>

## Who it’s for

Students and instructors in data analysis, SQL, actuarial ratemaking and reserving, insurance accounting, audit analytics and fairness testing, and anyone learning how an insurer’s data fits together.
