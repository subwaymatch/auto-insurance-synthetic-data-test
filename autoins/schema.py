"""Keys of the published tables: each table's primary key and the foreign keys that link the tables.

The CSV files carry the keys as plain columns; the SQLite release (scripts/release_formats.py) declares them, so
a database tool shows the links and `PRAGMA foreign_key_check` can prove every reference resolves. Keep this file
in step with tables.py: tests check that every `..._id` column of every table is a primary or foreign key here.
"""
from __future__ import annotations

# table -> primary key column. Every table has one.
PRIMARY_KEYS = {
    # reference
    "location": "location_id",
    "zip_demographics": "zip_code",
    "agency": "agency_id",
    "producer": "producer_id",
    "underwriting_company": "company_id",
    "claim_office": "claim_office_id",
    "catastrophe": "catastrophe_id",
    "coverage": "coverage_code",
    "cause_of_loss": "cause_of_loss",
    "rate_change": "effective_date",
    "vehicle_model_year": "vehicle_model_year_id",
    # policies, drivers and vehicles
    "policy": "policy_id",
    "policy_term": "policy_term_id",
    "premium_transaction": "transaction_id",
    "quote": "quote_id",
    "driver": "driver_id",
    "driver_incident": "incident_id",
    "insured_vehicle": "insured_vehicle_id",
    "exposure": "exposure_id",
    "telematics_enrollment": "enrollment_id",
    "telematics_score": "score_id",
    "renewal_offer": "renewal_offer_id",
    "customer_contact": "contact_id",
    "billing_invoice": "invoice_id",
    "billing_receipt": "receipt_id",
    "agency_statement": "statement_id",
    # general ledger
    "gl_account": "account_number",
    "gl_journal": "journal_line_id",
    # claims
    "claim": "claim_id",
    "claim_feature": "claim_feature_id",
    "claim_payment": "payment_id",
    "claim_reserve_transaction": "reserve_transaction_id",
    "employee": "employee_id",
    "vendor": "vendor_id",
    # answer key
    "exposure_truth": "exposure_id",
    "driver_truth": "driver_id",
    "insured_vehicle_truth": "insured_vehicle_id",
    "location_truth": "location_id",
    "claim_feature_truth": "claim_feature_id",
    "unreported_claim": "unreported_claim_id",
    "renewal_offer_truth": "renewal_offer_id",
    "policy_truth": "policy_id",
    "agency_truth": "agency_id",
}

# table -> {column: (referenced table, referenced column)}. A blank value is allowed (no reference).
FOREIGN_KEYS = {
    "zip_demographics": {"zip_code": ("location", "zip_code")},
    "agency": {"zip_code": ("location", "zip_code")},
    "producer": {"agency_id": ("agency", "agency_id")},
    "agency_statement": {"agency_id": ("agency", "agency_id")},
    "gl_journal": {"company_id": ("underwriting_company", "company_id"), "account_number": ("gl_account", "account_number")},
    "employee": {"claim_office_id": ("claim_office", "claim_office_id"), "supervisor_employee_id": ("employee", "employee_id")},
    "vendor": {"zip_code": ("location", "zip_code")},
    "billing_invoice": {"policy_id": ("policy", "policy_id"), "policy_term_id": ("policy_term", "policy_term_id")},
    "billing_receipt": {"policy_id": ("policy", "policy_id"), "policy_term_id": ("policy_term", "policy_term_id"),
                        "invoice_id": ("billing_invoice", "invoice_id")},
    "policy": {"location_id": ("location", "location_id"), "agency_id": ("agency", "agency_id"),
               "producer_id": ("producer", "producer_id"),
               "company_id": ("underwriting_company", "company_id"),
               "named_insured_driver_id": ("driver", "driver_id")},
    "policy_term": {"policy_id": ("policy", "policy_id")},
    "premium_transaction": {"policy_id": ("policy", "policy_id"), "policy_term_id": ("policy_term", "policy_term_id")},
    "quote": {"agency_id": ("agency", "agency_id"), "location_id": ("location", "location_id"),
              "policy_id": ("policy", "policy_id")},
    "driver": {"policy_id": ("policy", "policy_id")},
    "driver_incident": {"driver_id": ("driver", "driver_id"), "claim_id": ("claim", "claim_id")},
    "insured_vehicle": {"policy_id": ("policy", "policy_id"),
                        "vehicle_model_year_id": ("vehicle_model_year", "vehicle_model_year_id"),
                        "primary_driver_id": ("driver", "driver_id"),
                        "replaces_insured_vehicle_id": ("insured_vehicle", "insured_vehicle_id")},
    "exposure": {"policy_term_id": ("policy_term", "policy_term_id"), "policy_id": ("policy", "policy_id"),
                 "insured_vehicle_id": ("insured_vehicle", "insured_vehicle_id"),
                 "driver_id": ("driver", "driver_id"), "location_id": ("location", "location_id")},
    "telematics_enrollment": {"policy_id": ("policy", "policy_id")},
    "telematics_score": {"enrollment_id": ("telematics_enrollment", "enrollment_id"), "policy_id": ("policy", "policy_id"),
                         "insured_vehicle_id": ("insured_vehicle", "insured_vehicle_id"), "driver_id": ("driver", "driver_id"),
                         "applied_to_policy_term_id": ("policy_term", "policy_term_id")},
    "renewal_offer": {"policy_id": ("policy", "policy_id"),
                      "expiring_policy_term_id": ("policy_term", "policy_term_id"),
                      "renewal_policy_term_id": ("policy_term", "policy_term_id")},
    "customer_contact": {"policy_id": ("policy", "policy_id")},
    "claim": {"policy_id": ("policy", "policy_id"), "policy_term_id": ("policy_term", "policy_term_id"),
              "exposure_id": ("exposure", "exposure_id"), "involved_driver_id": ("driver", "driver_id"),
              "insured_vehicle_id": ("insured_vehicle", "insured_vehicle_id"),
              "vehicle_model_year_id": ("vehicle_model_year", "vehicle_model_year_id"),
              "catastrophe_id": ("catastrophe", "catastrophe_id"), "claim_office_id": ("claim_office", "claim_office_id"),
              "adjuster_id": ("employee", "employee_id"), "cause_of_loss": ("cause_of_loss", "cause_of_loss")},
    "claim_feature": {"claim_id": ("claim", "claim_id"), "coverage_code": ("coverage", "coverage_code")},
    "unreported_claim": {"policy_id": ("policy", "policy_id"), "exposure_id": ("exposure", "exposure_id"),
                         "insured_vehicle_id": ("insured_vehicle", "insured_vehicle_id"),
                         "coverage_code": ("coverage", "coverage_code"), "cause_of_loss": ("cause_of_loss", "cause_of_loss")},
    "claim_payment": {"claim_feature_id": ("claim_feature", "claim_feature_id"), "claim_id": ("claim", "claim_id"),
                      "vendor_id": ("vendor", "vendor_id"), "approved_by_employee_id": ("employee", "employee_id")},
    "claim_reserve_transaction": {"claim_feature_id": ("claim_feature", "claim_feature_id"), "claim_id": ("claim", "claim_id")},
    # answer key
    "exposure_truth": {"exposure_id": ("exposure", "exposure_id")},
    "driver_truth": {"driver_id": ("driver", "driver_id")},
    "insured_vehicle_truth": {"insured_vehicle_id": ("insured_vehicle", "insured_vehicle_id")},
    "location_truth": {"location_id": ("location", "location_id"), "zip_code": ("location", "zip_code")},
    "claim_feature_truth": {"claim_feature_id": ("claim_feature", "claim_feature_id")},
    "renewal_offer_truth": {"renewal_offer_id": ("renewal_offer", "renewal_offer_id")},
    "policy_truth": {"policy_id": ("policy", "policy_id")},
    "agency_truth": {"agency_id": ("agency", "agency_id")},
}

# Columns stored as text whatever their values look like (ZIP codes are labels, not numbers).
TEXT_COLUMNS = {"zip_code"}


def unique_columns(table: str) -> set[str]:
    """Columns other tables reference that are not the table's primary key; they must be unique."""
    return {col for fks in FOREIGN_KEYS.values() for t, col in fks.values() if t == table and col != PRIMARY_KEYS[t]}


def problems(columns: dict[str, list[str]]) -> list[str]:
    """What is wrong with the key map for tables with these columns: a table without a primary key, a key on a
    missing column or table, or an `..._id` column that is neither a primary nor a foreign key."""
    out = []
    for table, cols in columns.items():
        pk = PRIMARY_KEYS.get(table)
        if pk is None:
            out.append(f"{table}: no primary key")
        elif pk not in cols:
            out.append(f"{table}: primary key {pk} is not a column")
        fks = FOREIGN_KEYS.get(table, {})
        for col, (ref, ref_col) in fks.items():
            if col not in cols:
                out.append(f"{table}.{col}: foreign key on a missing column")
            if ref not in columns or ref_col not in columns[ref]:
                out.append(f"{table}.{col}: references missing {ref}.{ref_col}")
        for col in cols:
            if col.endswith("_id") and col != pk and col not in fks:
                out.append(f"{table}.{col}: an _id column that is neither a primary nor a foreign key")
    return out
