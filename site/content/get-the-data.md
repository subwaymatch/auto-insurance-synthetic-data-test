---
title: Get the data
nav: 9
nav_title: Get the Data
nav_style: button
eyebrow: Downloads
lede: The data is published as GitHub releases in three formats with the same contents. The links below always point at the latest build.
description: Download the Lakefront data as CSV, SQLite or Parquet, the instructor answer key, and code to load it in Python, R, SQL and DuckDB.
---

## Downloads

| | CSV | SQLite | Parquet |
|---|---|---|---|
| **Student data** | [%ICON(file-spreadsheet)%CSV zip](%RELEASE%/chicago-auto-insurance-data-latest-csv.zip) | [%ICON(database)%SQLite zip](%RELEASE%/chicago-auto-insurance-data-latest-sqlite.zip) | [%ICON(columns-3)%Parquet zip](%RELEASE%/chicago-auto-insurance-data-latest-parquet.zip) |
| **Instructor answer key** | [%ICON(file-spreadsheet)%CSV zip](%RELEASE%/chicago-auto-insurance-answer-key-latest-csv.zip) | [%ICON(database)%SQLite zip](%RELEASE%/chicago-auto-insurance-answer-key-latest-sqlite.zip) | [%ICON(columns-3)%Parquet zip](%RELEASE%/chicago-auto-insurance-answer-key-latest-parquet.zip) |
| Size, zipped | 95 MB | 163 MB (182 MB with the answer key) | 70 MB |
| Size, unzipped | 404 MB | 520 MB (575 MB) | 96 MB |

Each student zip holds the 34 tables, `run_summary.json`, the README, the changelog and the documentation. Each answer-key zip holds the 9 answer-key tables and `rating_plan.json`, the full rating plan; in the SQLite format the instructor’s database also holds every data table, linked to the answer key.

!!! warning "Keep the answer key from students"
    It holds what the insurer couldn’t see: each driver’s hidden risk, each household’s stability, the expected loss on every exposure row, the claims not yet reported. Give students the data zip only.

The `latest` release always holds the current data. Fixed versions (`v1.0.0` and so on) are listed on the [releases page](%REPO%/releases), each with a validation report and checksums. To look at the data before downloading anything, browse the [first 100 rows of every table](%REPO%/tree/main/samples/synthetic) on GitHub.

## Which format?

**CSV** opens anywhere, including Excel, but is the largest and slowest. The billing tables have close to 900,000 rows each, near Excel’s limit of 1,048,576.

**SQLite** is one file with every table, its primary and foreign keys declared and indexed. Open it with the `sqlite3` command line, DB Browser for SQLite, DBeaver, DuckDB, Python’s `sqlite3` or R’s `RSQLite`. Turn on key checking with `PRAGMA foreign_keys = ON;` if you change anything.

**Parquet** is a quarter of the size of the CSV files, loads every table in half a second against about eight for CSV, and keeps column types: whole numbers stay integers even with blanks, and dates are dates. pandas, R’s `arrow`, Polars, DuckDB and Power BI read it; Excel doesn’t.

## Loading it

### Python (pandas)

```python
import pandas as pd

# Parquet: ask pandas to keep integer and date types
claim = pd.read_parquet("claim.parquet", dtype_backend="pyarrow")

# CSV: read ZIP codes as text and parse the dates you need
policy = pd.read_csv("policy.csv", dtype={"zip_code": str},
                     parse_dates=["original_inception_date"])

# SQLite
import sqlite3
con = sqlite3.connect("chicago_auto_insurance.db")
exposure = pd.read_sql("SELECT * FROM exposure", con)
```

### R

```r
library(arrow)
claim <- read_parquet("claim.parquet")   # dates arrive as Date

library(DBI)
con <- dbConnect(RSQLite::SQLite(), "chicago_auto_insurance.db")
dbGetQuery(con, "SELECT region, COUNT(*) FROM location GROUP BY region")
```

### DuckDB

DuckDB queries Parquet and CSV files where they are, with no loading step:

```sql
-- car-years and premium earned in the extract (1 January 2022 to 31 December 2026), by region
SELECT l.region,
       SUM(days) / 365.25 AS car_years,
       SUM(e.total_premium * days / term_days) AS earned_premium
FROM (SELECT e.*, t.expiration_date - t.effective_date AS term_days,
             GREATEST(LEAST(e.coverage_end_date, DATE '2027-01-01') - GREATEST(e.coverage_start_date, DATE '2022-01-01'), 0) AS days
      FROM 'exposure.parquet' AS e JOIN 'policy_term.parquet' AS t USING (policy_term_id)) AS e
JOIN 'location.parquet' AS l USING (location_id)
GROUP BY l.region
ORDER BY earned_premium DESC;
```

The database file’s name inside the SQLite zip may differ from the one used above; use whatever the zip contains.

