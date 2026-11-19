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
| [`agency.csv`](synthetic/agency.csv) | 100 | 136 | 10 |
| [`agency_statement.csv`](synthetic/agency_statement.csv) | 100 | 7,841 | 7 |
| [`billing_invoice.csv`](synthetic/billing_invoice.csv) | 100 | 886,817 | 15 |
| [`billing_receipt.csv`](synthetic/billing_receipt.csv) | 100 | 895,732 | 8 |
| [`catastrophe.csv`](synthetic/catastrophe.csv) | 8 | 8 | 5 |
| [`claim.csv`](synthetic/claim.csv) | 100 | 22,313 | 31 |
| [`claim_feature.csv`](synthetic/claim_feature.csv) | 100 | 39,292 | 30 |
| [`claim_office.csv`](synthetic/claim_office.csv) | 6 | 6 | 3 |
| [`claim_payment.csv`](synthetic/claim_payment.csv) | 100 | 62,146 | 15 |
| [`claim_reserve_transaction.csv`](synthetic/claim_reserve_transaction.csv) | 100 | 125,764 | 8 |
| [`customer_contact.csv`](synthetic/customer_contact.csv) | 100 | 367,259 | 5 |
| [`driver.csv`](synthetic/driver.csv) | 100 | 76,698 | 21 |
| [`driver_incident.csv`](synthetic/driver_incident.csv) | 100 | 47,006 | 9 |
| [`employee.csv`](synthetic/employee.csv) | 46 | 46 | 10 |
| [`exposure.csv`](synthetic/exposure.csv) | 100 | 441,637 | 49 |
| [`gl_account.csv`](synthetic/gl_account.csv) | 19 | 19 | 5 |
| [`gl_journal.csv`](synthetic/gl_journal.csv) | 100 | 4,182 | 10 |
| [`insured_vehicle.csv`](synthetic/insured_vehicle.csv) | 100 | 110,406 | 24 |
| [`location.csv`](synthetic/location.csv) | 100 | 290 | 13 |
| [`policy.csv`](synthetic/policy.csv) | 100 | 43,368 | 26 |
| [`policy_term.csv`](synthetic/policy_term.csv) | 100 | 197,979 | 18 |
| [`premium_transaction.csv`](synthetic/premium_transaction.csv) | 100 | 269,243 | 10 |
| [`producer.csv`](synthetic/producer.csv) | 100 | 223 | 6 |
| [`quote.csv`](synthetic/quote.csv) | 100 | 117,297 | 20 |
| [`rate_change.csv`](synthetic/rate_change.csv) | 7 | 7 | 3 |
| [`renewal_offer.csv`](synthetic/renewal_offer.csv) | 100 | 171,349 | 14 |
| [`telematics_enrollment.csv`](synthetic/telematics_enrollment.csv) | 100 | 12,361 | 8 |
| [`telematics_score.csv`](synthetic/telematics_score.csv) | 100 | 62,278 | 18 |
| [`underwriting_company.csv`](synthetic/underwriting_company.csv) | 3 | 3 | 7 |
| [`vehicle_model_year.csv`](synthetic/vehicle_model_year.csv) | 100 | 8,750 | 15 |
| [`vendor.csv`](synthetic/vendor.csv) | 100 | 684 | 8 |
| [`zip_demographics.csv`](synthetic/zip_demographics.csv) | 100 | 290 | 17 |
| [`answer_key/agency_truth.csv`](synthetic/answer_key/agency_truth.csv) | 100 | 136 | 3 |
| [`answer_key/claim_feature_truth.csv`](synthetic/answer_key/claim_feature_truth.csv) | 100 | 39,292 | 6 |
| [`answer_key/driver_truth.csv`](synthetic/answer_key/driver_truth.csv) | 100 | 76,698 | 3 |
| [`answer_key/exposure_truth.csv`](synthetic/answer_key/exposure_truth.csv) | 100 | 441,637 | 10 |
| [`answer_key/insured_vehicle_truth.csv`](synthetic/answer_key/insured_vehicle_truth.csv) | 100 | 110,406 | 3 |
| [`answer_key/location_truth.csv`](synthetic/answer_key/location_truth.csv) | 100 | 290 | 8 |
| [`answer_key/policy_truth.csv`](synthetic/answer_key/policy_truth.csv) | 100 | 43,368 | 3 |
| [`answer_key/renewal_offer_truth.csv`](synthetic/answer_key/renewal_offer_truth.csv) | 100 | 171,349 | 2 |
| [`answer_key/unreported_claim.csv`](synthetic/answer_key/unreported_claim.csv) | 100 | 116 | 10 |

## real_data

| File | Sample rows | Total rows | Columns |
|---|---|---|---|
| [`mendeley_motor_portfolio/motor_vehicle_insurance_data.csv`](real_data/mendeley_motor_portfolio/motor_vehicle_insurance_data.csv) | 100 | 105,555 | 30 |
| [`mendeley_motor_portfolio/sample_type_claim.csv`](real_data/mendeley_motor_portfolio/sample_type_claim.csv) | 100 | 7,366 | 4 |
