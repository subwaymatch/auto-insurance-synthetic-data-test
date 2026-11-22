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
| [`agency_statement.csv`](synthetic/agency_statement.csv) | 100 | 7,854 | 7 |
| [`billing_invoice.csv`](synthetic/billing_invoice.csv) | 100 | 882,461 | 15 |
| [`billing_receipt.csv`](synthetic/billing_receipt.csv) | 100 | 894,386 | 8 |
| [`catastrophe.csv`](synthetic/catastrophe.csv) | 10 | 10 | 7 |
| [`cause_of_loss.csv`](synthetic/cause_of_loss.csv) | 16 | 16 | 2 |
| [`claim.csv`](synthetic/claim.csv) | 100 | 23,097 | 21 |
| [`claim_feature.csv`](synthetic/claim_feature.csv) | 100 | 39,960 | 16 |
| [`claim_office.csv`](synthetic/claim_office.csv) | 6 | 6 | 3 |
| [`claim_payment.csv`](synthetic/claim_payment.csv) | 100 | 60,784 | 15 |
| [`claim_reserve_transaction.csv`](synthetic/claim_reserve_transaction.csv) | 100 | 103,928 | 8 |
| [`coverage.csv`](synthetic/coverage.csv) | 8 | 8 | 2 |
| [`customer_contact.csv`](synthetic/customer_contact.csv) | 100 | 362,221 | 5 |
| [`driver.csv`](synthetic/driver.csv) | 100 | 76,624 | 19 |
| [`driver_incident.csv`](synthetic/driver_incident.csv) | 100 | 38,854 | 9 |
| [`employee.csv`](synthetic/employee.csv) | 46 | 46 | 10 |
| [`exposure.csv`](synthetic/exposure.csv) | 100 | 438,620 | 47 |
| [`gl_account.csv`](synthetic/gl_account.csv) | 19 | 19 | 5 |
| [`gl_journal.csv`](synthetic/gl_journal.csv) | 100 | 4,430 | 10 |
| [`insured_vehicle.csv`](synthetic/insured_vehicle.csv) | 100 | 109,952 | 23 |
| [`location.csv`](synthetic/location.csv) | 100 | 290 | 13 |
| [`policy.csv`](synthetic/policy.csv) | 100 | 43,368 | 16 |
| [`policy_term.csv`](synthetic/policy_term.csv) | 100 | 195,901 | 12 |
| [`premium_transaction.csv`](synthetic/premium_transaction.csv) | 100 | 267,328 | 10 |
| [`producer.csv`](synthetic/producer.csv) | 100 | 223 | 6 |
| [`quote.csv`](synthetic/quote.csv) | 100 | 118,642 | 20 |
| [`rate_change.csv`](synthetic/rate_change.csv) | 7 | 7 | 2 |
| [`renewal_offer.csv`](synthetic/renewal_offer.csv) | 100 | 169,426 | 13 |
| [`telematics_enrollment.csv`](synthetic/telematics_enrollment.csv) | 100 | 12,475 | 8 |
| [`telematics_score.csv`](synthetic/telematics_score.csv) | 100 | 61,994 | 18 |
| [`underwriting_company.csv`](synthetic/underwriting_company.csv) | 3 | 3 | 7 |
| [`vehicle_model_year.csv`](synthetic/vehicle_model_year.csv) | 100 | 12,176 | 15 |
| [`vendor.csv`](synthetic/vendor.csv) | 100 | 684 | 8 |
| [`zip_demographics.csv`](synthetic/zip_demographics.csv) | 100 | 290 | 17 |
| [`answer_key/agency_truth.csv`](synthetic/answer_key/agency_truth.csv) | 100 | 136 | 3 |
| [`answer_key/claim_feature_truth.csv`](synthetic/answer_key/claim_feature_truth.csv) | 100 | 39,960 | 6 |
| [`answer_key/driver_truth.csv`](synthetic/answer_key/driver_truth.csv) | 100 | 76,624 | 3 |
| [`answer_key/exposure_truth.csv`](synthetic/answer_key/exposure_truth.csv) | 100 | 438,620 | 11 |
| [`answer_key/insured_vehicle_truth.csv`](synthetic/answer_key/insured_vehicle_truth.csv) | 100 | 109,952 | 3 |
| [`answer_key/location_truth.csv`](synthetic/answer_key/location_truth.csv) | 100 | 290 | 8 |
| [`answer_key/policy_truth.csv`](synthetic/answer_key/policy_truth.csv) | 100 | 43,368 | 3 |
| [`answer_key/renewal_offer_truth.csv`](synthetic/answer_key/renewal_offer_truth.csv) | 100 | 169,426 | 2 |
| [`answer_key/unreported_claim.csv`](synthetic/answer_key/unreported_claim.csv) | 100 | 134 | 10 |

## real_data

| File | Sample rows | Total rows | Columns |
|---|---|---|---|
| [`mendeley_motor_portfolio/motor_vehicle_insurance_data.csv`](real_data/mendeley_motor_portfolio/motor_vehicle_insurance_data.csv) | 100 | 105,555 | 30 |
| [`mendeley_motor_portfolio/sample_type_claim.csv`](real_data/mendeley_motor_portfolio/sample_type_claim.csv) | 100 | 7,366 | 4 |
