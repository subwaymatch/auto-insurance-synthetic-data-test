# Dataset of an actual motor vehicle insurance portfolio

Real data from a motor insurer, used here as a benchmark for the synthetic book
(`scripts/compare_real_data.py`, findings in `docs/real_data_comparison.md`). It is not used by the generator.

| | |
|---|---|
| Title | Dataset of an actual motor vehicle insurance portfolio |
| Authors | Josep Lledó and Jose M. Pavía (Universitat de València) |
| Publisher | Mendeley Data, version 2, published 30 July 2024 |
| DOI | [10.17632/5cxyb5fp4f.2](https://doi.org/10.17632/5cxyb5fp4f.2) |
| Page | <https://data.mendeley.com/datasets/5cxyb5fp4f/2> |
| Licence | [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/): free to share and adapt with attribution |
| Period | November 2015 to December 2018 |
| Size | 105,555 rows and 30 columns (53,502 contracts) |

**Attribution.** Lledó, J. and Pavía, J. M. (2024). *Dataset of an actual motor vehicle insurance portfolio*
(Version 2) [Data set]. Mendeley Data. https://doi.org/10.17632/5cxyb5fp4f.2. Licensed under CC BY 4.0.

**Country.** The dataset page does not name the country or the insurer. It is almost certainly Spanish: the
authors are at the University of Valencia, the vehicle registration field is called "matriculation"
(Spanish *matriculación*), amounts are on a euro scale, and one risk type is agricultural vehicles. That is an
inference, not something the source states.

## Files

The files are byte-for-byte the published ones. Only the names have changed, to drop the spaces:

| File here | Original name | Size | SHA-256 |
|---|---|---|---|
| `motor_vehicle_insurance_data.csv` | `Motor vehicle insurance data.csv` | 14,527,177 bytes | `00061a64e355a7f9bbd06f1bcd3f0846b1f849955119a812acf2bc7781ee293a` |
| `sample_type_claim.csv` | `sample type claim.csv` | 258,094 bytes | `d35d967d66563ea291fd6d450cbfdf52f5118c5e7b3625b7b3a9bfa5a9361c3d` |
| `variable_descriptions.xlsx` | `Descriptive of the variables.xlsx` | 12,283 bytes | `8b451e1898ca42e7092d4011c8e7071235fdc6e859a4e24070960580df433cc2` |

`.gitattributes` marks this folder `-text` so git never rewrites the line endings.

**Format.** Semicolon-delimited, Windows (CRLF) line endings, a header row, dates as `DD/MM/YYYY`, decimal
point `.`. Missing values are either empty (`Date_lapse`) or the text `NA` (`Length`, `Type_fuel`). Read it
with, for example:

```python
pd.read_csv("motor_vehicle_insurance_data.csv", sep=";", keep_default_na=False, na_values=["", "NA"])
```

## Variables

From `variable_descriptions.xlsx` (wording lightly edited; the workbook spells the second column
`Date_start _contract`, the CSV `Date_start_contract`).

`motor_vehicle_insurance_data.csv`, one row per contract per annual period:

| Column | Description |
|---|---|
| `ID` | Identifier of each annual contract taken out by a policyholder. A contract has one row per annual period ("annuity"). |
| `Date_start_contract` | Start date of the policyholder's contract. |
| `Date_last_renewal` | Date of the last renewal (the start of this row's period). |
| `Date_next_renewal` | Date of the next renewal (the end of this row's period). |
| `Distribution_channel` | 0 = agent, 1 = insurance broker. |
| `Date_birth` | Date of birth of the insured declared on the policy. |
| `Date_driving_licence` | Date the insured's driving licence was issued. |
| `Seniority` | Total years the insured has been with the insurer. |
| `Policies_in_force` | Number of policies the insured holds with the insurer in the reference period. |
| `Max_policies` | Maximum number of policies the insured has ever had in force with the insurer. |
| `Max_products` | Maximum number of products the insured has held at the same time. |
| `Lapse` | Number of the customer's policies cancelled (by the customer or for non-payment) in the current year, excluding those replaced by another policy. |
| `Date_lapse` | Lapse date: when the contract ended. |
| `Payment` | Last payment method: 1 = half-yearly, 0 = annual. |
| `Premium` | Net premium for the policy in the current year. |
| `Cost_claims_year` | Total cost of the policy's claims in the current year. |
| `N_claims_year` | Number of the policy's claims in the current year. |
| `N_claims_history` | Number of claims over the policy's whole life. |
| `R_Claims_history` | Claims over the policy's life divided by its duration in whole years. |
| `Type_risk` | 1 = motorbike, 2 = van, 3 = passenger car, 4 = agricultural vehicle. |
| `Area` | 0 = rural, 1 = urban (more than 30,000 inhabitants), judged on traffic conditions. |
| `Second_driver` | 1 = more than one regular driver declared, 0 = one. |
| `Year_matriculation` | Year the vehicle was registered. |
| `Power` | Vehicle power, horsepower. |
| `Cylinder_capacity` | Engine size (cylinder capacity). |
| `Value_vehicle` | Market value of the vehicle on 31/12/2019. |
| `N_doors` | Number of doors. |
| `Type_fuel` | P = petrol, D = diesel. |
| `Length` | Vehicle length, metres. |
| `Weight` | Vehicle weight, kilograms. |

`sample_type_claim.csv`, a sample of rows with claims (7,366 lines, 5,255 contracts), one line per claim type
per contract-period:

| Column | Description |
|---|---|
| `ID` | Contract identifier, as above. |
| `Cost_claims_year` | Total cost of the policy's claims in the current year (matches the main file). |
| `Cost_claims_by_type` | Cost of the claims of this type in the current year. |
| `Claims_type` | One of: travel assistance, broken windows, complaint, negligence, theft, fire, all risks, injuries, other. |

## Things to know before using it

These come from `scripts/compare_real_data.py` (section 10 of its report) and are explained in
`docs/real_data_comparison.md`:

- 14,432 rows (13.7%) are periods the contract never entered: the lapse date equals the period's start date
  (the contract was not renewed). They carry a premium but no exposure. Another 404 rows have a lapse date
  before their own start.
- `N_claims_history`, `R_Claims_history`, `Seniority` and `Value_vehicle` are the same on every row of a
  contract: they were taken once, at extraction (vehicle value on 31/12/2019, after the period), so they
  contain information from after each row's period.
- `N_claims_year` does not behave like an independent count for each year: within a contract it almost never
  rises from one period to the next (98.8% of consecutive periods), and a claim-free period is followed by
  one with a claim only 1.5% of the time, against 26% of periods having a claim. Claim frequency also falls
  by about half between periods that start in 2016 and those that start in 2017, and periods starting in
  2018 are cut off by the end of observation.
- `Power` is 0 and `Type_fuel` is `NA` on the same 1,764 rows; `Length` is `NA` on 10,329 (mostly
  motorbikes and agricultural vehicles).
- `Lapse` counts the customer's lapsed policies of any kind, so 2,376 rows have `Lapse` above 0 and no
  `Date_lapse`.
