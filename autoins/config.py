"""All assumptions for the synthetic auto insurance generator, in one place.

Three kinds of numbers live here:

* ANCHORED  - tied to a published figure (source named in the comment).
* TUNED     - chosen so the simulated book lands on an anchored target
              (see validate.py for the targets it is checked against).
* ASSUMED   - a judgement call with no direct public source. These are the
              numbers to revisit first if a result looks wrong.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parent.parent
REFERENCE_DIR = REPO / "reference"


@dataclass(frozen=True)
class Config:
    seed: int = 20250101
    n_policies: int = 30_000          # distinct policies ever written (initial book + new business)
    out_dir: Path = REPO / "output"
    start: str = "2022-01-01"         # first day simulated
    valuation: str = "2026-09-30"     # "as of" date of the extract; nothing later is known
    initial_book_share: float = 0.46  # share of policies already in force on the start date (their term in
                                      # force on that date is included, with only the part after it earned)


# --------------------------------------------------------------------------
# Book structure (ASSUMED)
# --------------------------------------------------------------------------
TERM_MONTHS_P = {6: 0.65, 12: 0.35}
ZIP_PENETRATION_SIGMA = 0.35          # lognormal spread of market share by ZIP
CHANNELS = ["Independent Agent", "Exclusive Agent", "Direct"]
CHANNEL_P = [0.45, 0.25, 0.30]

AGE_TILT_IN_FORCE = 0.008            # customers already on the books skew older ...
AGE_TILT_NEW_BUSINESS = -0.016       # ... and new customers younger (per year of age from 45)
KID_RATE_BY_VEHICLES = [0.10, 0.30, 0.75, 0.90]   # expected driving-age children for parents 36-62, by cars owned
TEEN_YEARS_AT_HOME = 9               # a household's teen-driver "slot" turns over about every nine years
PRIOR_ACCIDENT_FACTOR = 0.62         # prior-carrier accidents per true at-fault rate (TUNED to match own-claim experience)
# Trade-ins (a car replaced by another, on any day of a term): annual probability by vehicle age. About
# 13% a year overall, in line with US ownership spells of 5.5 to 6.5 years (S&P Global Mobility / IHS
# Markit: 79 months for new cars, 66 for used) and ~0.4 vehicle purchases per household a year.
REPLACE_AGE_KNOTS = [0, 3, 6, 10, 15, 20]
REPLACE_HAZARD = [0.05, 0.11, 0.13, 0.15, 0.17, 0.20]
LEASE_END_HAZARD = 0.70              # leased vehicles three or more years old
REPLACEMENT_AGE = dict(shape=1.5, scale=2.3)   # age of the vehicle bought as a replacement
# After a total loss the wrecked or stolen vehicle leaves the policy on the day after the loss. Most
# households buy a replacement, which joins the policy (as a new insured vehicle) when it is bought.
P_REPLACE_AFTER_TOTAL_LOSS = {"single": 0.93, "multi": 0.80}   # by vehicles on the policy (ASSUMED)
# days from the loss until the replacement is bought (mean ~37). Valuation takes ~12 days and release of a
# total loss ~20 (CCC Crash Course 2020; Hi Marley 2023); buying follows the settlement (ASSUMED).
TOTAL_LOSS_REPLACEMENT_DELAY = dict(min_days=7, shape=2.0, scale=15.0)

# A few owners keep a car the company paid as a total loss (the salvage value comes off the settlement);
# it stays on the policy, without physical damage cover from the next renewal. Illinois allows this only
# for hail damage or a vehicle 9 or more model years old (625 ILCS 5/3-117.1(b)(1)); the share of eligible
# owners who do is ASSUMED.
P_OWNER_RETAINED_SALVAGE = 0.10
OWNER_RETAINED_MIN_AGE = 9

# Household changes during a term. Annual rates; each change happens on a random day of the term and is
# an endorsement: the policy is re-rated from that day (ASSUMED unless a source is named).
# Moves within the area: Chicago metro mover rates of 5.5% (owners) and 20.0% (renters) a year, of which
# 73% stay in the metro (ACS 2024 1-year, tables B07013 and B07201). Moves out of the area are among the
# insured-request cancellations.
MOVE_RATE = {"owner": 0.040, "renter": 0.146}
OWNER_AFTER_MOVE_P = {"owner": 0.85, "renter": 0.22}   # chance of owning the new home (ASSUMED)
MOVE_DISTANCE_MILES = 8.0                            # most moves are short: ZIP weight ~ exp(-distance / this) (ASSUMED)
VEHICLE_ADD_RATE = 0.025                             # household buys an additional car (ASSUMED)
VEHICLE_ADD_RATE_NO_CAR = 0.30                       # ... when a driver aged 17+ has no car of their own (ASSUMED)
VEHICLE_SELL_RATE = 0.04                             # per vehicle on a multi-car policy: sold, not replaced (ASSUMED)
# Children moving out (and onto a policy of their own). Calibrated to 58% of 18-24s and 16% of 25-34s
# living with parents (Census CPS ASEC 2025, table AD-1).
CHILD_LEAVE_AGE_KNOTS = [18, 21, 24, 27, 30]
CHILD_LEAVE_RATE = [0.04, 0.08, 0.14, 0.18, 0.20]
OTHER_ADULT_LEAVE_RATE = 0.12                        # (ASSUMED)
DIVORCE_RATE = 0.013                                 # Illinois: 12.9 divorces per 1,000 married women (ACS 2024)
# Unmarried named insureds marrying (spouse added). Shape ASSUMED; level matches Illinois' 27 to 30
# marriages per 1,000 unmarried women and men (ACS 2024, tables B12001 and B12503).
MARRIAGE_AGE_KNOTS = [21, 25, 30, 35, 45, 60]
MARRIAGE_RATE = [0.02, 0.06, 0.07, 0.05, 0.025, 0.01]
SPOUSE_BRINGS_CAR_P = 0.45                           # (ASSUMED)
TAKES_CAR_P = {"child": 0.55, "other": 0.70, "divorce": 0.80, "death": 0.0}   # a leaving driver's own car goes too (ASSUMED)
# Annual mortality, 2024: 1.77% at 65-74, 4.26% at 75-84, 13.8% at 85+ (CDC NCHS Data Brief 548)
MORTALITY_AGE_KNOTS = [65, 70, 80, 90, 95]
MORTALITY_RATE = [0.012, 0.0177, 0.0426, 0.138, 0.22]
# Age at which a newly licensed teenager joins: 26% of 16-year-olds, 44% of 17s and 60% of 18s hold a
# licence (FHWA Highway Statistics 2024, table DL-20), so many teenagers license after 16.
TEEN_LICENCE_AGE_P = {16: 0.35, 17: 0.24, 18: 0.21, 19: 0.11, 20: 0.09}
# Coverage changes at renewal
LOAN_YEARS = 5.75                                    # average auto loan ~69 months (Experian, Q2 2026)
# Owned vehicles dropping collision as they age, per year (shape ASSUMED). Overall about 2% of vehicles a
# year, near the 1.9% of drivers who dropped collision or comprehensive in a 2026 consumer survey.
DROP_PD_AGE_KNOTS = [0, 6, 10, 15, 20]
DROP_PD_RATE = [0.005, 0.02, 0.06, 0.10, 0.12]
KEEP_COMP_WHEN_DROPPING_COLL_P = 0.35                # (ASSUMED)
RAISE_DEDUCTIBLE = dict(base=0.02, per_increase=0.40, cap=0.25)   # after a renewal increase above 10%

# Good-student discount: the insurer's eligibility rule, evaluated on each term's effective date (ASSUMED).
# A driver qualifies while under GOOD_STUDENT_MAX_AGE, still in full-time school and keeping B grades.
GOOD_STUDENT_MAX_AGE = 25
GOOD_STUDENT_GRADES_P = 0.40         # children on the policy who keep a B average
P_COLLEGE = 0.60                     # of those, the share who go on to college
SCHOOL_END_AGE = {"high_school": (18.2, 18.8), "college": (21.5, 23.5)}   # age range when full-time school ends

# When information reaches the insurer (ASSUMED). Every rating, underwriting and renewal decision uses
# only what is known on its decision date.
RENEWAL_OFFER_LEAD_DAYS = (30, 45)   # renewal offers are rated and mailed this many days before the effective date
NEW_BUSINESS_QUOTE_LEAD_DAYS = (0, 14)
MVR_POSTING_LAG = dict(min_days=14, shape=2.0, scale=25.0)   # violation date to conviction on the driving record (mean ~64)
PRIOR_CARRIER_REPORT_LAG = dict(min_days=7, mean=30.0)        # accident date to appearing on the claims-history report

# Named-insured propensity by age band (relative odds of being a policyholder)
HOUSEHOLDER_WEIGHT = {"16_17": 0.0, "18_20": 0.12, "21_24": 0.45, "25_29": 0.85, "30_34": 1.0, "35_39": 1.0,
                      "40_44": 1.0, "45_49": 1.0, "50_54": 1.0, "55_59": 1.0, "60_64": 1.0, "65_69": 1.0,
                      "70_74": 0.95, "75_79": 0.85, "80_84": 0.65, "85_plus": 0.35}
AGE_BAND_BOUNDS = {"16_17": (16, 18), "18_20": (18, 21), "21_24": (21, 25), "25_29": (25, 30), "30_34": (30, 35),
                   "35_39": (35, 40), "40_44": (40, 45), "45_49": (45, 50), "50_54": (50, 55), "55_59": (55, 60),
                   "60_64": (60, 65), "65_69": (65, 70), "70_74": (70, 75), "75_79": (75, 80), "80_84": (80, 85),
                   "85_plus": (85, 93)}

# --------------------------------------------------------------------------
# Coverage options
# --------------------------------------------------------------------------
# Illinois minimum is 25/50/20 with uninsured motorist BI of 25/50 (ANCHORED: Illinois DOI).
BI_LIMITS = [(25_000, 50_000), (50_000, 100_000), (100_000, 300_000), (250_000, 500_000), (500_000, 500_000)]
BI_LIMIT_P = [0.24, 0.20, 0.40, 0.13, 0.03]
PD_LIMITS = [20_000, 50_000, 100_000, 100_000, 250_000]   # goes with the BI option of the same index
MED_LIMITS = [0, 1_000, 2_000, 5_000, 10_000]
MED_LIMIT_P = [0.35, 0.15, 0.15, 0.25, 0.10]
COLL_DEDUCTIBLES = [250, 500, 1_000, 2_000]
COLL_DED_P = [0.08, 0.52, 0.35, 0.05]
COMP_DEDUCTIBLES = [100, 250, 500, 1_000]
COMP_DED_P = [0.10, 0.28, 0.44, 0.18]
FULL_GLASS_P = 0.35

# Rating factors for limits and deductibles (fixed tables, not fitted; ASSUMED, typical of filed plans)
BI_LIMIT_FACTOR = [1.00, 1.24, 1.50, 1.74, 1.86]
PD_LIMIT_FACTOR = [1.00, 1.05, 1.08, 1.08, 1.10]
UM_LIMIT_FACTOR = [1.00, 1.28, 1.62, 1.95, 2.10]
MED_LIMIT_FACTOR = [0.0, 1.00, 1.45, 2.20, 2.80]
COLL_DED_FACTOR = [1.14, 1.00, 0.83, 0.66]
COMP_DED_FACTOR = [1.32, 1.14, 1.00, 0.80]
FULL_GLASS_FACTOR = 1.12

# --------------------------------------------------------------------------
# True risk model: frequency (per vehicle-year, for a reference risk)
# --------------------------------------------------------------------------
LATENT_GAMMA_SHAPE = 2.5              # driver frailty ~ Gamma(shape, 1/shape); CV 0.63 (ASSUMED)
HOUSEHOLD_SIGMA = 0.25                # shared household component of frailty

# Driver age curve for at-fault accidents (ASSUMED shape, in line with published age relativities)
AGE_KNOTS = [16, 17, 18, 19, 20, 22, 25, 30, 40, 50, 60, 65, 70, 75, 80, 85, 92]
AGE_FACTOR = [3.6, 3.1, 2.7, 2.4, 2.15, 1.75, 1.30, 1.05, 0.95, 0.90, 0.90, 0.95, 1.02, 1.15, 1.35, 1.65, 2.0]
YOUNG_MALE_EXTRA = 0.30               # +30% at 18 and under, fading to zero by 27
MARRIED_FACTOR = 0.93
GOOD_STUDENT_FACTOR = 0.92
INEXPERIENCE_KNOTS = [0, 1, 3, 5]
INEXPERIENCE_FACTOR = [1.35, 1.25, 1.10, 1.0]
MILEAGE_ELASTICITY = 0.45             # frequency ~ (miles / 10,000) ** elasticity
BUSINESS_USE_FACTOR = 1.10
ADAS_FREQ_FACTOR = {"AF_MV": 0.86, "AF_SV": 0.95}   # automatic emergency braking (ASSUMED, direction per IIHS)
ZIP_RANDOM_EFFECT_SIGMA = {"crash": 0.12, "theft": 0.20}   # true ZIP hazard the insurer cannot see

# Base annual occurrence rates by peril (TUNED to the frequency targets in validate.py)
BASE_RATE = {
    "AF_MV": 0.0377,        # insured at fault, another vehicle involved
    "AF_SV": 0.0123,        # insured at fault, single vehicle
    "NAF": 0.0348,          # insured not at fault
    "PARKED": 0.0152,       # hit while parked / unoccupied
    "GLASS": 0.0300,
    "THEFT_TOTAL": 0.0011,
    "THEFT_PARTIAL": 0.0030,
    "VANDALISM": 0.0024,
    "ANIMAL": 0.0034,
    "WEATHER": 0.0052,      # non-catastrophe hail, wind, falling limbs
    "FLOOD": 0.0004,
    "FIRE": 0.0004,
    "OTHER_COMP": 0.0028,
}
SEGMENT_FREQ = {"economy": 1.05, "mainstream": 1.00, "luxury": 1.00, "truck": 0.97, "sports": 1.25,
                "ev": 1.05, "minivan": 0.88}
PARKING = ["Street", "Driveway/Lot", "Garage"]
PARKING_HIT_FACTOR = [1.5, 1.0, 0.6]      # hit-while-parked, vandalism
PARKING_THEFT_FACTOR = [1.3, 1.0, 0.5]
PARKING_WEATHER_FACTOR = [1.0, 1.0, 0.45]
ANTI_THEFT_FACTOR = 0.80

# Calendar effects. Seasonality and the theft year index come from Chicago police data
# (reference/month_seasonality.csv, reference/year_indices.csv). The rest is below.
FREQ_TREND_CRASH = {2021: 0.96, 2022: 0.98, 2023: 1.01, 2024: 1.00, 2025: 0.99, 2026: 0.98}   # ASSUMED, near flat
THEFT_YEAR_DAMPING = 0.55            # non-Kia/Hyundai theft follows the Chicago index ** damping (ASSUMED)
KIA_HYUNDAI_THEFT = {2021: 1.0, 2022: 4.0, 2023: 6.0, 2024: 3.5, 2025: 2.5, 2026: 1.8}   # extra multiplier (ASSUMED, stylised)
KIA_HYUNDAI_MODEL_YEARS = (2011, 2021)
ANIMAL_SEASONALITY = [0.75, 0.65, 0.70, 0.80, 1.05, 1.10, 0.85, 0.75, 0.85, 1.40, 1.95, 1.20]
WEATHER_SEASONALITY = [0.55, 0.60, 0.90, 1.30, 1.55, 1.65, 1.55, 1.35, 0.85, 0.65, 0.55, 0.50]
GLASS_SEASONALITY = [1.20, 1.15, 1.10, 1.00, 0.95, 0.90, 0.90, 0.90, 0.90, 0.95, 1.00, 1.05]

# --------------------------------------------------------------------------
# True risk model: who gets paid, and how much
# --------------------------------------------------------------------------
# Ground-up severity trend, 2024 = 1.00 (TUNED). Triple-I/ISO paid severity rose about 15% for BI,
# 12% for PD and 6% for comprehensive from 2022 to 2024, with collision roughly flat. Policy limits
# and total-loss caps mute the trend in what is actually paid, so the ground-up indices are steeper.
SEVERITY_TREND = {
    "BI":   {2021: 0.66, 2022: 0.75, 2023: 0.87, 2024: 1.00, 2025: 1.10, 2026: 1.18},
    "PD":   {2021: 0.76, 2022: 0.86, 2023: 0.955, 2024: 1.00, 2025: 1.04, 2026: 1.08},
    "COLL": {2021: 0.82, 2022: 0.93, 2023: 0.985, 2024: 1.00, 2025: 1.03, 2026: 1.06},
    "COMP": {2021: 0.82, 2022: 0.90, 2023: 0.97, 2024: 1.00, 2025: 1.03, 2026: 1.06},
}
USED_CAR_VALUE_INDEX = {2021: 1.10, 2022: 1.20, 2023: 1.15, 2024: 1.10, 2025: 1.10, 2026: 1.11}   # ASSUMED shape

# Severity medians/sigmas at the 2024 level (lognormal; TUNED to the severity targets)
PD_SEV = dict(median=4_450, sigma=0.95)
BI_SEV = dict(median=20_000, sigma=1.40)
UM_SEV = dict(median=9_500, sigma=1.35)
MED_SEV = dict(median=1_900, sigma=0.95)
COLL_SEV = dict(median=4_700, sigma=0.95)          # ground-up repair cost for a reference vehicle
COLL_PERIL_SEV = {"AF_MV": 1.00, "AF_SV": 1.30, "NAF": 0.95, "PARKED": 0.55}
TOTAL_LOSS_THRESHOLD = 0.72                         # repair cost / actual cash value
SALVAGE_RANGE = (0.12, 0.32)                        # share of actual cash value recovered on a total loss
COMP_SEV = {                                        # lognormal (median, sigma) unless noted
    "GLASS": (520, 0.60), "THEFT_PARTIAL": (1_700, 0.90), "VANDALISM": (1_400, 0.90),
    "ANIMAL": (4_500, 0.70), "WEATHER": (2_700, 0.90), "OTHER_COMP": (1_200, 0.90),
    "HAIL_CAT": (3_900, 0.75), "WIND_CAT": (2_300, 0.85),
}
GLASS_ADAS_FACTOR = 1.7                             # windshield camera recalibration
SEGMENT_PD_SEV = {"truck": 1.15}                    # heavier striking vehicle does more damage
SEGMENT_BI_SEV = {"truck": 1.10}
SUV_PD_SEV = 1.05

# Claim propensities (ASSUMED unless noted)
P_PD_GIVEN_AF_MV = 0.96
P_PD_GIVEN_AF_SV = 0.15
P_BI_GIVEN_AF_MV = 0.26            # TUNED; scaled by ZIP below
P_BI_GIVEN_AF_SV = 0.03
BI_TERRITORY_EXPONENT = 0.6         # injury claims are more common per crash in high-hazard ZIPs
BI_CLAIMANTS_P = [0.72, 0.20, 0.06, 0.02]
P_MED = {"AF_MV": 0.12, "AF_SV": 0.15, "NAF": 0.06}
P_UNINSURED_BASE = 0.16             # other driver uninsured or fled; Chicago hit-and-run share is ~31% of crashes
P_UM_INJURY = 0.20
P_FILE_COLL = {"AF_MV": 0.90, "AF_SV": 0.90, "NAF": 0.42, "NAF_UNINSURED": 0.90, "PARKED": 0.75}
P_SUBROGATION = {"NAF": 0.85, "PARKED": 0.10}
SUBROGATION_SHARE = (0.75, 1.00)
P_FILE_BELOW_DEDUCTIBLE = 0.75      # claims opened then closed without payment
CWP = {"PD": 0.05, "BI": 0.14, "UM": 0.14, "MED": 0.05, "COLL": 0.03, "COMP": 0.04}
# Claims opened and closed without payment, beyond those above (ASSUMED rates). Together they bring the share
# of closed claims without payment near the 2025 industry figures: about 45% for liability and medical
# claims and just under 25% for collision and comprehensive (WSJ analysis of insurer filings with the NAIC).
P_LIABILITY_DENIED = {"PD": 0.45, "BI": 0.12}        # the other driver claims against an insured not at fault
P_INJURY_NOT_PURSUED = {"AF_MV": 0.55, "AF_SV": 0.08}   # an injury claim is opened but never paid
P_FIRST_PARTY_WITHDRAWN = 0.60                       # damage reported, then not pursued (or paid by the other insurer)
P_COMP_ONLY = 0.29     # vehicles without collision that carry comprehensive (Illinois: 82.6% collision and 87.5%
                       # comprehensive per liability car-year, NAIC Auto Insurance Database 2023)
CHARGEABLE_THRESHOLD = 1_000        # paid amount that makes an at-fault claim surchargeable; the claim becomes
                                    # chargeable on the day cumulative PD, BI and collision payments reach it

# --------------------------------------------------------------------------
# Driver record (ASSUMED rates; tuned so ~84% of drivers have no violation in 3 years)
# --------------------------------------------------------------------------
VIOLATION_RATE = 0.060              # minor moving violations per driver-year for a reference driver
MAJOR_VIOLATION_RATE = 0.0035
VIOLATION_LATENT_EXPONENT = 0.8     # how strongly violations follow the latent risk
MINOR_VIOLATIONS = ["Speeding 1-14 mph over", "Speeding 15-25 mph over", "Disobeyed traffic signal",
                    "Disobeyed stop sign", "Improper lane usage", "Following too closely",
                    "Using phone while driving", "Failure to yield"]
MINOR_VIOLATION_P = [0.34, 0.16, 0.12, 0.10, 0.09, 0.05, 0.08, 0.06]
MAJOR_VIOLATIONS = ["DUI", "Reckless driving", "Driving while suspended", "Speeding 26+ mph over",
                    "Leaving the scene"]
MAJOR_VIOLATION_P = [0.40, 0.18, 0.17, 0.17, 0.08]
LOOKBACK_DAYS = 3 * 365

# --------------------------------------------------------------------------
# Rating plan (what the insurer charges)
# --------------------------------------------------------------------------
# The plan is fitted to the true expected loss cost by minimum bias, then the
# deliberate distortions below are applied. They are the "answers" a case study
# can look for; they are also written to answer_key/rating_plan.json.
TARGET_LOSS_RATIO = 0.775           # at day-one cost levels, before catastrophes: the book starts under-priced,
                                    # as the industry was entering 2022 after pandemic-era rate cuts (TUNED so
                                    # accident-year loss ratios follow the industry: about 80% in 2022, 73-75%
                                    # in 2023, 63-66% in 2024 and about 61% in 2025; see validate.py)
COMP_CAT_LOAD = 1.22                # catastrophe provision in comprehensive rates
N_TERRITORIES = 12
PLANTED_DISTORTIONS = {
    "class": {"16-17 M": 0.80, "16-17 F": 0.80, "18-20 M": 0.82, "18-20 F": 0.82,
              "21-24 M": 0.90, "21-24 F": 0.90, "75+": 0.88},
    "mileage_exponent": 0.5,        # mileage relativities are flattened (square root of the fitted value)
}
# Filed rate changes, by effective date (ASSUMED timing; sized to the industry cycle). US private auto rates
# rose 12.1% in 2022, 16.5% in 2023 and 7.6% in 2024 (S&P Global RateWatch), approved increases slowed to
# 3.7% in 2025 (AM Best), and Illinois' largest writer cut rates in 2025 (State Farm). Cumulative here: +48%.
RATE_CHANGES = [("2022-04-01", 0.04), ("2022-10-01", 0.08), ("2023-03-01", 0.10), ("2023-09-01", 0.09),
                ("2024-03-01", 0.08), ("2025-03-01", 0.02), ("2026-06-01", -0.02)]

# --------------------------------------------------------------------------
# Retention and cancellation (ASSUMED)
# --------------------------------------------------------------------------
RENEWAL_BASE_LOGIT = {6: 2.30, 12: 1.65}
PRICE_ELASTICITY = 6.0              # logit points per 100% premium increase above the tolerance
PRICE_TOLERANCE = 0.03
MIDTERM_INSURED_REQUEST_RATE = 0.030   # per year
NONPAY_RATE = {"Paid in Full": 0.0, "Monthly EFT": 0.022, "Monthly Bill": 0.065}   # per year, mid score
UW_CANCEL_NEW_BUSINESS_P = 0.008

# --------------------------------------------------------------------------
# Catastrophes: FICTIONAL events with realistic seasonality for northern Illinois.
# (id, date, description, peril, centre lat, centre lon, radius miles, peak hit probability)
# --------------------------------------------------------------------------
CAT_EVENTS = [
    ("CAT-2021-01", "2021-06-21", "Severe thunderstorm, hail and wind - southwest suburbs", "HAIL_CAT", 41.74, -88.10, 14, 0.040),
    ("CAT-2022-01", "2022-05-19", "Hailstorm - northern Lake County", "HAIL_CAT", 42.33, -87.95, 12, 0.035),
    ("CAT-2023-01", "2023-04-04", "Hailstorm - Fox Valley and western DuPage", "HAIL_CAT", 41.90, -88.28, 16, 0.050),
    ("CAT-2023-02", "2023-07-02", "Flash flooding - West Side and near west suburbs", "FLOOD_CAT", 41.86, -87.76, 7, 0.014),
    ("CAT-2024-01", "2024-03-13", "Hailstorm - south suburbs and Will County", "HAIL_CAT", 41.53, -87.85, 15, 0.035),
    ("CAT-2024-02", "2024-07-15", "Derecho, wind and tree damage - metro wide", "WIND_CAT", 41.85, -87.90, 34, 0.012),
    ("CAT-2025-01", "2025-05-28", "Hailstorm - McHenry County and northwest Cook", "HAIL_CAT", 42.18, -88.20, 15, 0.040),
    ("CAT-2025-02", "2025-08-16", "Flash flooding - South Side and south suburbs", "FLOOD_CAT", 41.72, -87.62, 8, 0.010),
    ("CAT-2026-01", "2026-06-09", "Hailstorm - DuPage and west Cook", "HAIL_CAT", 41.88, -87.98, 13, 0.040),
]

# --------------------------------------------------------------------------
# Claim handling (ASSUMED)
# --------------------------------------------------------------------------
BRANCHES = [(1, "Chicago City Field Office", "Chicago"), (2, "Suburban Auto Damage Center", "Schaumburg"),
            (3, "Casualty and Injury Unit", "Oak Brook"), (4, "Express and Glass Desk", "Naperville"),
            (5, "Total Loss and Theft Unit", "Chicago"), (6, "Catastrophe Response Team", "Aurora")]
COMPANIES = [(1, "Lakefront Preferred Insurance Company", "Preferred", "Chicago"),
             (2, "Lakefront Mutual Automobile Insurance Company", "Standard", "Chicago"),
             (3, "Prairie Path Casualty Company", "Non-Standard", "Oak Brook")]
TIER_NAMES = ["Preferred", "Standard", "Non-Standard"]
PAY_PLANS = ["Paid in Full", "Monthly EFT", "Monthly Bill"]

PERIL_DESCRIPTION = {
    "AF_MV": "Collision with another vehicle - insured at fault",
    "AF_SV": "Single-vehicle collision - insured at fault",
    "NAF": "Collision with another vehicle - insured not at fault",
    "PARKED": "Struck while parked or unoccupied",
    "GLASS": "Glass damage", "THEFT_TOTAL": "Theft of vehicle", "THEFT_PARTIAL": "Theft of parts or contents",
    "VANDALISM": "Vandalism", "ANIMAL": "Collision with animal", "WEATHER": "Hail, wind or falling object",
    "FLOOD": "Flood or water damage", "FIRE": "Fire", "OTHER_COMP": "Other comprehensive loss",
    "HAIL_CAT": "Hail (catastrophe)", "WIND_CAT": "Wind or tree damage (catastrophe)",
    "FLOOD_CAT": "Flood (catastrophe)",
}
COVERAGE_NAMES = {"BI": "Bodily Injury Liability", "PD": "Property Damage Liability",
                  "UM": "Uninsured/Underinsured Motorist BI", "MED": "Medical Payments",
                  "COLL": "Collision", "COMP": "Comprehensive"}
COVERAGES = list(COVERAGE_NAMES)


def year_series(table: dict[int, float], years: np.ndarray) -> np.ndarray:
    """Look up a per-year table for an array of calendar years (clamped to the table's range)."""
    ks = np.array(sorted(table))
    vals = np.array([table[k] for k in ks])
    return vals[np.clip(np.searchsorted(ks, years), 0, len(ks) - 1)]
