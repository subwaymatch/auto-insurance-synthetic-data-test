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
| [`claim.csv`](synthetic/claim.csv) | 100 | 20,343 | 28 |
| [`claim_feature.csv`](synthetic/claim_feature.csv) | 100 | 35,789 | 29 |
| [`claim_office.csv`](synthetic/claim_office.csv) | 6 | 6 | 3 |
| [`claim_payment.csv`](synthetic/claim_payment.csv) | 100 | 56,302 | 7 |
| [`claim_reserve_transaction.csv`](synthetic/claim_reserve_transaction.csv) | 100 | 113,768 | 8 |
| [`customer_contact.csv`](synthetic/customer_contact.csv) | 100 | 347,405 | 5 |
| [`driver.csv`](synthetic/driver.csv) | 100 | 77,040 | 18 |
| [`driver_incident.csv`](synthetic/driver_incident.csv) | 100 | 43,337 | 9 |
| [`exposure.csv`](synthetic/exposure.csv) | 100 | 460,831 | 49 |
| [`insured_vehicle.csv`](synthetic/insured_vehicle.csv) | 100 | 113,317 | 22 |
| [`location.csv`](synthetic/location.csv) | 100 | 290 | 13 |
| [`policy.csv`](synthetic/policy.csv) | 100 | 43,368 | 24 |
| [`policy_term.csv`](synthetic/policy_term.csv) | 100 | 205,742 | 18 |
| [`premium_transaction.csv`](synthetic/premium_transaction.csv) | 100 | 280,689 | 8 |
| [`quote.csv`](synthetic/quote.csv) | 100 | 124,106 | 19 |
| [`rate_change.csv`](synthetic/rate_change.csv) | 7 | 7 | 3 |
| [`renewal_offer.csv`](synthetic/renewal_offer.csv) | 100 | 179,620 | 14 |
| [`telematics_enrollment.csv`](synthetic/telematics_enrollment.csv) | 100 | 12,298 | 8 |
| [`telematics_score.csv`](synthetic/telematics_score.csv) | 100 | 59,553 | 18 |
| [`underwriting_company.csv`](synthetic/underwriting_company.csv) | 3 | 3 | 5 |
| [`vehicle_model_year.csv`](synthetic/vehicle_model_year.csv) | 100 | 8,750 | 15 |
| [`zip_demographics.csv`](synthetic/zip_demographics.csv) | 100 | 290 | 17 |
| [`answer_key/claim_feature_truth.csv`](synthetic/answer_key/claim_feature_truth.csv) | 100 | 35,789 | 6 |
| [`answer_key/driver_truth.csv`](synthetic/answer_key/driver_truth.csv) | 100 | 77,040 | 3 |
| [`answer_key/exposure_truth.csv`](synthetic/answer_key/exposure_truth.csv) | 100 | 460,831 | 10 |
| [`answer_key/insured_vehicle_truth.csv`](synthetic/answer_key/insured_vehicle_truth.csv) | 100 | 113,317 | 3 |
| [`answer_key/location_truth.csv`](synthetic/answer_key/location_truth.csv) | 100 | 290 | 8 |
| [`answer_key/renewal_offer_truth.csv`](synthetic/answer_key/renewal_offer_truth.csv) | 100 | 179,620 | 2 |
| [`answer_key/unreported_claim.csv`](synthetic/answer_key/unreported_claim.csv) | 100 | 145 | 10 |

## real_data

| File | Sample rows | Total rows | Columns |
|---|---|---|---|
| [`mendeley_motor_portfolio/motor_vehicle_insurance_data.csv`](real_data/mendeley_motor_portfolio/motor_vehicle_insurance_data.csv) | 100 | 105,555 | 30 |
| [`mendeley_motor_portfolio/sample_type_claim.csv`](real_data/mendeley_motor_portfolio/sample_type_claim.csv) | 100 | 7,366 | 4 |
