# Sample CSV files

The first 100 rows of every CSV file, so the data can be browsed on GitHub without downloading anything.
They are written by `.github/workflows/samples.yml` (`scripts/make_samples.py`); do not edit them by hand.

- `synthetic/` is the default build of this repository's generator (`python generate.py`), the same data as the
  `latest` release. `synthetic/answer_key/` is the instructor answer key.
- `real_data/` is the real motor insurance portfolio kept in `real_data/` for comparison (see its README).

Rows are simply the first ones in each file, so samples of different tables do not join up: the first 100
claims belong to policies that are mostly not among the first 100 policies. Download a release for the full
data.


## synthetic

| File | Sample rows | Total rows | Columns |
|---|---|---|---|
| [`agency.csv`](synthetic/agency.csv) | 26 | 26 | 6 |
| [`catastrophe.csv`](synthetic/catastrophe.csv) | 8 | 8 | 5 |
| [`claim.csv`](synthetic/claim.csv) | 100 | 22,677 | 28 |
| [`claim_feature.csv`](synthetic/claim_feature.csv) | 100 | 40,071 | 29 |
| [`claim_office.csv`](synthetic/claim_office.csv) | 6 | 6 | 3 |
| [`claim_payment.csv`](synthetic/claim_payment.csv) | 100 | 63,082 | 7 |
| [`claim_reserve_transaction.csv`](synthetic/claim_reserve_transaction.csv) | 100 | 131,510 | 8 |
| [`customer_contact.csv`](synthetic/customer_contact.csv) | 100 | 356,642 | 5 |
| [`driver.csv`](synthetic/driver.csv) | 100 | 88,655 | 18 |
| [`driver_incident.csv`](synthetic/driver_incident.csv) | 100 | 49,371 | 9 |
| [`exposure.csv`](synthetic/exposure.csv) | 100 | 515,155 | 49 |
| [`insured_vehicle.csv`](synthetic/insured_vehicle.csv) | 100 | 129,371 | 22 |
| [`location.csv`](synthetic/location.csv) | 100 | 290 | 13 |
| [`policy.csv`](synthetic/policy.csv) | 100 | 50,000 | 24 |
| [`policy_term.csv`](synthetic/policy_term.csv) | 100 | 229,767 | 17 |
| [`premium_transaction.csv`](synthetic/premium_transaction.csv) | 100 | 313,537 | 8 |
| [`quote.csv`](synthetic/quote.csv) | 100 | 142,043 | 18 |
| [`rate_change.csv`](synthetic/rate_change.csv) | 7 | 7 | 3 |
| [`telematics_enrollment.csv`](synthetic/telematics_enrollment.csv) | 100 | 14,207 | 8 |
| [`telematics_score.csv`](synthetic/telematics_score.csv) | 100 | 61,904 | 18 |
| [`underwriting_company.csv`](synthetic/underwriting_company.csv) | 3 | 3 | 5 |
| [`vehicle_model_year.csv`](synthetic/vehicle_model_year.csv) | 100 | 8,750 | 15 |
| [`zip_demographics.csv`](synthetic/zip_demographics.csv) | 100 | 290 | 17 |
| [`answer_key/claim_feature_truth.csv`](synthetic/answer_key/claim_feature_truth.csv) | 100 | 40,071 | 6 |
| [`answer_key/driver_truth.csv`](synthetic/answer_key/driver_truth.csv) | 100 | 88,655 | 3 |
| [`answer_key/exposure_truth.csv`](synthetic/answer_key/exposure_truth.csv) | 100 | 515,155 | 10 |
| [`answer_key/insured_vehicle_truth.csv`](synthetic/answer_key/insured_vehicle_truth.csv) | 100 | 129,371 | 3 |
| [`answer_key/location_truth.csv`](synthetic/answer_key/location_truth.csv) | 100 | 290 | 8 |
| [`answer_key/unreported_claim.csv`](synthetic/answer_key/unreported_claim.csv) | 100 | 130 | 9 |

## real_data

| File | Sample rows | Total rows | Columns |
|---|---|---|---|
| [`mendeley_motor_portfolio/motor_vehicle_insurance_data.csv`](real_data/mendeley_motor_portfolio/motor_vehicle_insurance_data.csv) | 100 | 105,555 | 30 |
| [`mendeley_motor_portfolio/sample_type_claim.csv`](real_data/mendeley_motor_portfolio/sample_type_claim.csv) | 100 | 7,366 | 4 |
