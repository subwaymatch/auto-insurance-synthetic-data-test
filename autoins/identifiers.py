"""Identifiers as an insurer's systems issue them.

Two things happen here, after every table is built:

* Business keys. A policy gets a policy number (a serial issued in the order policies were written, the
  underwriting company's code and two check digits), a quote a quote number, a claim a claim number (report
  year and a sequence) and each of its features a suffix, a vehicle a 17-character VIN with a valid check
  digit and a unit number on its policy, a driver a driver number and a masked licence number, an agency a
  producer code. Serial numbers have gaps: this extract is the Chicago-area part of a regional carrier, and
  the rest of the company draws numbers from the same counters.

* Surrogate keys. The integer ..._id columns are renumbered in the order the records were created (a policy
  by the day it was written, a term by the day it was offered, a driver or vehicle by the day it joined, an
  exposure row by the day it was rated, a claim feature by the day it was opened), as an auto-increment key
  would be. The simulation builds its records in another order (the opening book first, then one pass per
  term), and that order must not show in the data.

* Key counters (surrogate_keys, run last). An integer key is the auto-increment counter of the system that
  creates the record, shared by the whole company, so it does not start at 1. The company was founded in 2000
  and its systems went live over the years (KEY_SYSTEMS, ASSUMED); each counter runs from its go-live. Between
  two records of this book the rest of the company creates records of its own, as many as its size implies
  (this book's share of new policies, against the SERIALS_PER_DAY the company issues, and the company's growth
  since 2000), so keys have gaps that track time. Records created before a system went live were migrated into
  it that day, in their original order. Reference tables (ZIP codes, the vehicle catalogue, the three companies,
  the claim offices, the chart of accounts) keep their own codes.

Everything is fictional. VINs keep the catalogue's made-up manufacturer prefix (position 1 is "0", which no
real manufacturer uses); licence numbers are masked and are NOT computed the way Illinois computes real ones
(from the name, birth date and sex), so no synthetic driver carries a real person's number.
"""
from __future__ import annotations

import zlib

import numpy as np
import pandas as pd

from . import config as C
from . import schema
from .refdata import stream

COMPANY_CODE = ["LFP", "LFM", "PPC"]             # Lakefront Preferred, Lakefront Mutual, Prairie Path Casualty
NAIC_STYLE_CODE = [98412, 98413, 98427]          # fictional five-digit company codes, in the NAIC's format
SERIAL_START, SERIALS_PER_DAY = 100_000, 60.0    # policy serials the whole company issues, of which this book is part
VIN_VALUE = {**{str(d): d for d in range(10)},
             **dict(zip("ABCDEFGH", range(1, 9))), **dict(zip("JKLMN", range(1, 6))), "P": 7, "R": 9,
             **dict(zip("STUVWXYZ", range(2, 10)))}
VIN_WEIGHT = np.array([8, 7, 6, 5, 4, 3, 2, 10, 0, 9, 8, 7, 6, 5, 4, 3, 2])
PLANT_CODES = "ABCDEFGHJKLMNPRSTUVWXYZ"


# table: (the column dating each record's creation, the day the system that keys it went live). ASSUMED history:
# the policy, agency, ledger and personnel systems date from the founding; billing was replaced in 2008 and claims
# in 2012; comparative-rater and online quoting came in 2014, the correspondence system in 2016 and the telematics
# program in 2018.
KEY_SYSTEMS = {
    "policy": ("written", C.FOUNDED), "policy_term": ("offer_date", C.FOUNDED), "driver": ("added_date", C.FOUNDED),
    "insured_vehicle": ("added_date", C.FOUNDED), "exposure": ("rating_date", C.FOUNDED),
    "premium_transaction": ("processed_date", C.FOUNDED), "renewal_offer": ("offer_date", C.FOUNDED),
    "driver_incident": ("known_date", C.FOUNDED), "agency": ("appointment_date", C.FOUNDED),
    "producer": ("start_date", C.FOUNDED), "agency_statement": ("payment_date", C.FOUNDED),
    "gl_journal": ("posting_date", C.FOUNDED), "employee": ("hire_date", C.FOUNDED),
    "billing_invoice": ("issue_date", "2008-07-01"), "billing_receipt": ("receipt_date", "2008-07-01"),
    "claim": ("report_date", "2012-10-01"), "claim_feature": ("open_date", "2012-10-01"),
    "claim_payment": ("payment_date", "2012-10-01"), "claim_reserve_transaction": ("transaction_date", "2012-10-01"),
    "vendor": (None, "2012-10-01"), "quote": ("quote_date", "2014-03-01"), "customer_contact": ("contact_date", "2016-01-01"),
    "telematics_enrollment": ("enrollment_date", "2018-04-01"), "telematics_score": ("period_end_date", "2018-04-01"),
}


# ------------------------------------------------------------------------------------------- check digits
def mod97_check(serial: np.ndarray, code: list[str]) -> np.ndarray:
    """Two check digits for serial + company code, as an IBAN's are (ISO 7064 MOD 97-10): the letters count as
    A = 10 ... Z = 35, and the digits are chosen so that the whole number, check digits last, leaves 1 when
    divided by 97."""
    letters = np.array([int("".join(str(ord(ch) - 55) for ch in c)) for c in code], dtype=np.int64)
    width = np.array([10 ** len(str(x)) for x in letters], dtype=np.int64)
    return 98 - (np.asarray(serial, dtype=np.int64) * width + letters) * 100 % 97


def policy_number_is_valid(number: str) -> bool:
    """Check a policy number of the form 0830512-LFM-47."""
    serial, code, check = number.split("-")
    return int(serial + "".join(str(ord(ch) - 55) for ch in code) + check) % 97 == 1


def vin_check_digit(vin17) -> np.ndarray:
    """The check digit (position 9) of each 17-character VIN: the weighted sum of its characters' values,
    modulo 11, with 10 written X (49 CFR 565)."""
    chars = np.array([list(v) for v in vin17])
    lut = np.zeros(128, dtype=np.int64)
    for ch, val in VIN_VALUE.items():
        lut[ord(ch)] = val
    values = lut[chars.view(np.uint32).reshape(chars.shape)]
    r = (values * VIN_WEIGHT).sum(axis=1) % 11
    return np.where(r == 10, "X", r.astype(str))


def full_vins(patterns: np.ndarray, makes: np.ndarray, group: np.ndarray, rng: np.random.Generator) -> np.ndarray:
    """A 17-character VIN for each vehicle from its catalogue pattern (positions 1-8, a masked check digit, the
    model-year code): a plant letter from the make, a six-digit serial unique within the model year, and the
    check digit computed last. `group` is the vehicle's catalogue row."""
    n = len(patterns)
    plant = np.array([PLANT_CODES[zlib.crc32(m.encode()) % len(PLANT_CODES)] for m in pd.unique(makes)])
    plant = pd.Series(plant, index=pd.unique(makes)).reindex(makes).to_numpy()
    order = np.lexsort((rng.random(n), group))
    seq = np.empty(n, dtype=np.int64)
    seq[order] = pd.Series(group[order]).groupby(group[order]).cumcount().to_numpy()
    start = pd.Series(rng.integers(0, 900_000, len(pd.unique(group))), index=pd.unique(group)).reindex(group).to_numpy()
    serial = 100_000 + (start + seq * 7_919) % 900_000            # 7,919 is prime: no repeats within a model year
    body = np.char.add(np.char.add(np.char.replace(patterns.astype(str), "*", "0"), plant.astype(str)), serial.astype(str))
    check = vin_check_digit(body)
    return np.char.add(np.char.add(np.array([b[:8] for b in body]), check), np.array([b[9:] for b in body]))


# ------------------------------------------------------------------------------------------- numbering
def _gapped(order_key: np.ndarray, rng: np.random.Generator, mean_gap: float, start: int = 0, by=None) -> np.ndarray:
    """Sequence numbers in the order of `order_key`, with random gaps (other business draws from the same
    counter), restarting within each `by` group (a year) if given."""
    idx = np.argsort(order_key, kind="stable")
    step = 1 + rng.geometric(1 / mean_gap, len(idx)) - 1 if mean_gap > 1 else np.ones(len(idx), dtype=np.int64)
    out = np.empty(len(idx), dtype=np.int64)
    if by is None:
        out[idx] = start + np.cumsum(step)
    else:
        g = np.asarray(by)[idx]
        cs = np.cumsum(step)
        first = np.r_[True, g[1:] != g[:-1]]
        base = np.maximum.accumulate(np.where(first, cs - step, 0))
        offs = pd.Series(rng.integers(1_000, 9_000, len(pd.unique(g))), index=pd.unique(g)).reindex(g).to_numpy()
        out[idx] = cs - base + offs
    return out


def _rank(*keys) -> np.ndarray:
    """1-based rank of each row when sorted by the keys (first key most significant); ties keep row order."""
    order = np.lexsort(tuple(reversed(keys)))
    r = np.empty(len(order), dtype=np.int64)
    r[order] = np.arange(1, len(order) + 1)
    return r


def _remap(tables: dict, table: str, new_id: np.ndarray) -> None:
    """Give `table` new primary key values (aligned with its rows) and carry them to every foreign key that
    points at it, in the data tables and the answer key alike. The table is then sorted by its key."""
    pk = schema.PRIMARY_KEYS[table]
    mapping = pd.Series(new_id, index=tables[table][pk].to_numpy())
    for t, fks in schema.FOREIGN_KEYS.items():
        if t not in tables:
            continue
        for col, (ref, ref_col) in fks.items():
            if ref == table and ref_col == pk:
                old = tables[t][col]
                mapped = old.map(mapping)
                tables[t][col] = mapped.astype("Int64") if old.isna().any() else mapped.astype(np.int64)
    tables[table][pk] = new_id
    for t in tables:                                    # the table itself, and the answer-key table keyed like it
        if schema.PRIMARY_KEYS.get(t) == pk:
            tables[t] = tables[t].sort_values(pk, kind="stable").reset_index(drop=True)


def finish(cfg: C.Config, cal, T: dict, K: dict) -> None:
    """Add the business keys and renumber the surrogate keys (see the module docstring). T and K are the data
    tables and the answer key; both are changed in place."""
    R = stream(cfg.seed, "identifiers")
    both = {**T, **K}
    day = lambda s: (pd.to_datetime(s).to_numpy().astype("M8[D]") - cal.start.astype("M8[D]")).astype(np.int64)
    pol, term = T["policy"], T["policy_term"]

    # ---- policies: numbered in the order they were written (the opening book by its original inception, new
    # business by the day its quote was bound); the company issues serials at a steady rate, so the number
    # tracks the date with gaps
    first = term.sort_values(["policy_id", "term_number"], kind="stable").groupby("policy_id").head(1).set_index("policy_id")
    written = np.where(first.business_type.reindex(pol.policy_id).to_numpy() == "New",
                       day(first.offer_date.reindex(pol.policy_id)), day(pol.original_inception_date))
    order = np.argsort(written, kind="stable")
    elapsed = np.diff(np.r_[written[order][0], written[order]])
    serial = np.empty(len(pol), dtype=np.int64)
    serial[order] = SERIAL_START + np.cumsum(1 + R.poisson(SERIALS_PER_DAY * elapsed))
    code = np.array(COMPANY_CODE)[pol.company_id.to_numpy() - 1]
    check = mod97_check(serial, list(code))
    number = [f"{s:07d}-{c}-{k:02d}" for s, c, k in zip(serial, code, check)]
    pol.insert(1, "policy_number", number)
    _remap(both, "policy", 1_000_000 + _rank(serial))
    pol = both["policy"]

    # ---- terms, drivers, vehicles, exposure rows: in the order they were created
    t = both["policy_term"]
    _remap(both, "policy_term", _rank(day(t.offer_date), t.policy_id.to_numpy(), t.term_number.to_numpy()))
    d = both["driver"]
    d.insert(2, "driver_number", d.assign(a=day(d.added_date)).sort_values(["policy_id", "a", "driver_id"], kind="stable")
             .groupby("policy_id").cumcount().add(1).reindex(d.index).to_numpy())
    initial = d.last_name.str[0].str.upper().where(d.last_name.str[0].str.upper().str.match("[A-Z]"), "X")
    d.insert(d.columns.get_loc("date_first_licensed"), "license_state", "IL")
    d.insert(d.columns.get_loc("date_first_licensed"), "license_number_masked",
             initial.to_numpy() + "***-****-*" + pd.Series(R.integers(0, 1000, len(d))).astype(str).str.zfill(3).to_numpy())
    _remap(both, "driver", _rank(day(d.added_date), d.policy_id.to_numpy(), d.driver_id.to_numpy()))
    v = both["insured_vehicle"]
    v.insert(2, "unit_number", v.assign(a=day(v.added_date)).sort_values(["policy_id", "a", "insured_vehicle_id"], kind="stable")
             .groupby("policy_id").cumcount().add(1).reindex(v.index).to_numpy())
    make = both["vehicle_model_year"].set_index("vehicle_model_year_id").make.reindex(v.vehicle_model_year_id).to_numpy()
    v.insert(v.columns.get_loc("vin_prefix"), "vin",
             full_vins(v.vin_prefix.to_numpy(), make, v.vehicle_model_year_id.to_numpy(), R))
    both["insured_vehicle"] = v = v.drop(columns="vin_prefix")       # the catalogue's pattern: the VIN's first ten characters
    _remap(both, "insured_vehicle", _rank(day(v.added_date), v.policy_id.to_numpy(), v.insured_vehicle_id.to_numpy()))
    e = both["exposure"]
    _remap(both, "exposure", _rank(day(e.rating_date), e.policy_term_id.to_numpy(), e.endorsement_number.to_numpy(),
                                   e.insured_vehicle_id.to_numpy()))

    # ---- claims: a number from the report year and a sequence; features opened later are numbered later
    c = both["claim"]
    yy = pd.to_datetime(c.report_date).dt.year.to_numpy() % 100
    seq = _gapped(c.claim_id.to_numpy(), R, mean_gap=7.0, by=yy)
    c.insert(1, "claim_number", [f"{y:02d}-{s:07d}" for y, s in zip(yy, seq)])
    f = both["claim_feature"]
    k = f.assign(o=day(f.open_date)).sort_values(["claim_id", "o", "claim_feature_id"], kind="stable").groupby("claim_id").cumcount().add(1)
    f.insert(2, "feature_number", c.set_index("claim_id").claim_number.reindex(f.claim_id).to_numpy()
             + "-" + k.reindex(f.index).astype(str).str.zfill(2).to_numpy())
    _remap(both, "claim_feature", _rank(day(f.open_date), f.claim_id.to_numpy(), f.claim_feature_id.to_numpy()))
    en = both["telematics_enrollment"]
    _remap(both, "telematics_enrollment", _rank(day(en.enrollment_date), en.policy_id.to_numpy()))

    # ---- quotes, agencies, companies
    q = both["quote"]
    yy = pd.to_datetime(q.quote_date).dt.year.to_numpy() % 100
    q.insert(1, "quote_number", [f"Q{y:02d}-{s:07d}" for y, s in zip(yy, _gapped(q.quote_id.to_numpy(), R, mean_gap=5.0, by=yy))])
    a = both["agency"]
    codes = np.sort(R.choice(np.arange(1_000, 99_000), len(a), replace=False))
    direct = (a.channel == "Direct").to_numpy()
    a.insert(1, "agency_code", np.where(direct, [f"HO-{i:05d}" for i in np.cumsum(direct)], [f"IL-{x:05d}" for x in codes]))
    pr = both["producer"]
    k = pr.groupby("agency_id").cumcount().add(1)
    pr.insert(1, "producer_code", a.set_index("agency_id").agency_code.reindex(pr.agency_id).to_numpy() + "-" + k.astype(str).str.zfill(2).to_numpy())
    u = both["underwriting_company"]
    u.insert(1, "company_code", COMPANY_CODE[:len(u)])
    u.insert(2, "naic_style_code", NAIC_STYLE_CODE[:len(u)])

    for name in T:
        T[name] = both[name]
    for name in K:
        K[name] = both[name]


def surrogate_keys(cfg: C.Config, cal, T: dict, K: dict) -> None:
    """Give every table in KEY_SYSTEMS the keys its system's counter would have issued (see the module docstring),
    carrying them to every foreign key. Runs after every table, the ledger included, is built. Changes T and K."""
    R = stream(cfg.seed, "key counters")
    both = {**T, **K}
    V = cal.valuation_day
    day = lambda s: (pd.to_datetime(s).to_numpy().astype("M8[D]") - cal.start.astype("M8[D]")).astype(np.int64)
    # the company's size by day, relative to its size from 2022 on: growing evenly from the founding
    founded = int(day([C.FOUNDED])[0])
    days = np.arange(founded, cal.horizon + 2)
    size = np.where(days < 0, C.COMPANY_SIZE_AT_FOUNDING + (1 - C.COMPANY_SIZE_AT_FOUNDING) * (days - founded) / -founded, 1.0)
    cum = np.r_[0.0, np.cumsum(size)]                  # company-days from the founding to the start of each day
    # this book's share of the company: its new policies a day against the serials the company issues
    pol, term = both["policy"], both["policy_term"]
    first = term.sort_values(["policy_id", "term_number"], kind="stable").groupby("policy_id").head(1).set_index("policy_id")
    written = np.where(first.business_type.reindex(pol.policy_id).to_numpy() == "New",
                       day(first.offer_date.reindex(pol.policy_id)), day(pol.original_inception_date))
    share = min(((written >= 0) & (written <= V)).sum() / (V + 1) / SERIALS_PER_DAY, 1.0)
    for table, (col, live) in KEY_SYSTEMS.items():
        if table not in both:
            continue
        t, pk = both[table], schema.PRIMARY_KEYS[table]
        live = int(day([live])[0])
        n = len(t)
        if table == "policy":
            created = written
        elif col:
            created = day(t[col])
        else:                                                    # undated (the vendor file): spread from go-live on
            created = live + (np.arange(n) * (V - live) / max(n, 1)).astype(np.int64)
        created = np.clip(created, live, cal.horizon)            # a record older than its system was migrated in
        # the company's records a day from 2022 on: from this book's own rate in the extract, or over the system's
        # life for a table the book rarely adds to (agencies, staff)
        rate = max(((created >= 0) & (created <= V)).sum() / (V + 1), n / (V + 1 - live)) / share
        order = np.lexsort((np.arange(n), created))              # tables are in creation order already: ties keep it
        c = created[order]
        new_day = np.r_[True, c[1:] != c[:-1]]
        pos = np.arange(n) - np.maximum.accumulate(np.where(new_day, np.arange(n), 0))
        per_day = np.bincount(c - live)[c - live]
        moment = cum[c - founded] + size[c - founded] * (pos + 0.5) / per_day          # a day's records spread over it
        so_far = rate * (moment - cum[live - founded])           # records the company created since go-live
        between = np.diff(np.r_[0.0, so_far]) * (1 - share)      # the rest of the company's, between two of this book's
        key = np.empty(n, dtype=np.int64)
        key[order] = np.cumsum(1 + R.poisson(between))
        if pd.api.types.is_integer_dtype(t[pk]):
            _remap(both, table, key)
        else:                                                    # a coded key: the counter behind the code
            prefix = t[pk].astype(str).str.extract(r"^([A-Z]+)")[0].fillna("").to_numpy()
            t[pk] = [f"{p_}{k:09d}" for p_, k in zip(prefix, key)]
            both[table] = t.sort_values(pk, kind="stable").reset_index(drop=True)
    for name in T:
        T[name] = both[name]
    for name in K:
        K[name] = both[name]
