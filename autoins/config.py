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
    n_policies: int = 43_368          # distinct policies ever written (initial book + new business)
    out_dir: Path = REPO / "output"
    start: str = "2022-01-01"         # first day simulated
    valuation: str = "2026-12-31"     # "as of" date of the extract; nothing later is known
    initial_book_share: float = 0.46  # share of policies already in force on the start date (their term in
                                      # force on that date is included, with only the part after it earned)


# --------------------------------------------------------------------------
# Claims open when the extract begins (simulate._warm_up). The book in force on the start date has been insured
# since its current term began, up to a year earlier. That part of the term is simulated too, so the extract
# opens with the claims still open from it (and those reported later), as a real claims system does. Claims from
# earlier terms are not simulated: their accidents stay in the drivers' histories only. The reference calendars
# begin on WARM_UP_FROM, which limits how far back the warm-up can reach.
# --------------------------------------------------------------------------
WARM_UP_FROM = "2021-01-01"


def warm_up_days(cfg: "Config") -> int:
    """How many days before the start the warm-up covers: a year, or back to WARM_UP_FROM (0: none)."""
    start = np.datetime64(cfg.start, "D")
    month = start.astype("M8[M]")
    first = max((month - np.timedelta64(12, "M")).astype("M8[D]") + (start - month.astype("M8[D]")), np.datetime64(WARM_UP_FROM, "D"))
    return int(max((start - first).astype(int), 0))


# --------------------------------------------------------------------------
# Book structure (ASSUMED)
# --------------------------------------------------------------------------
TERM_MONTHS_P = {6: 0.65, 12: 0.35}
ZIP_PENETRATION_SIGMA = 0.35          # lognormal spread of market share by ZIP
CHANNELS = ["Independent Agent", "Exclusive Agent", "Direct"]
CHANNEL_P = [0.45, 0.25, 0.30]

# Household stability (ASSUMED). A hidden trait of each household, standard normal before the shifts below: how
# settled it is, financially and otherwise. It lowers claim frequency, raises retention and payment discipline,
# and makes a household likelier to own its home, bundle other policies, have had continuous insurance, pay in
# full and have been a customer for longer. The insurer never sees it; it sees those consequences, which is why
# the discounts built on them (FILED_DISCOUNTS) carry real signal, and why new business, which arrives less
# stable than the customers who stayed, costs more than it is charged.
STABILITY_FREQ = 0.30                 # log at-fault propensity per unit of stability (lower is safer)
STABILITY_SHIFT = {"opening": 0.30, "new": -0.30}      # the book in force at the start has already been selected
STABILITY_CHANNEL = {"Independent Agent": -0.05, "Exclusive Agent": 0.20, "Direct": -0.15}
STABILITY_ON = dict(homeowner=1.00, married=0.25, multi_policy=0.70, prior_insurance=1.00, paid_in_full=0.16,
                    eft=0.20, tenure=0.40, score=0.25)     # log-odds (or as noted in population.py) per unit
STABILITY_RETENTION = 0.45            # renewal logit per unit of stability
STABILITY_CANCEL = {"nonpay": -0.55, "request": -0.30}    # log mid-term cancellation rate per unit
# Channel and agency effects beyond stability (ASSUMED). Independent agents place harder-to-place risks; direct
# customers shop more at renewal. Each agency also has a hidden book quality (a multiplier on its customers'
# at-fault propensity, lognormal) and a retention effect, correlated: a careless agency also churns its book.
CHANNEL_FREQ = {"Independent Agent": 1.05, "Exclusive Agent": 0.97, "Direct": 1.00}
CHANNEL_RETENTION = {"Independent Agent": 0.0, "Exclusive Agent": 0.15, "Direct": -0.25}   # renewal logit
AGENCY_QUALITY_SIGMA = 0.11           # spread of agencies' book quality (log at-fault propensity)
AGENCY_RETENTION_SIGMA = 0.18         # spread of agencies' retention effect (renewal logit)
AGENCY_QUALITY_RETENTION_CORR = -0.5
# Agencies appointed in the area (ASSUMED). A carrier this size places its independent business through many
# small appointments: about 120 agencies averaging some $150,000 of premium a year each, near the volume
# regional carriers commonly ask of an appointed agency, with a few large ones writing a multiple of that.
N_AGENCIES = {"Independent Agent": 120, "Exclusive Agent": 14}
MULTI_CAR_FREQ = 0.90                 # at-fault and not-at-fault crash frequency of each car on a multi-car policy
# New customers claim more (ASSUMED shape; sized to the new-business penalty real books show: a CAS study of 25
# books, Wu and Lin 2009, found new business loss ratios 13 points above renewal, improving for three to five
# years). The multiplier on the perils below is 1 + sum of amplitude * exp(-days since inception / days): a
# short burst after a policy is written (damage that was already there, claims soon after buying cover) and a
# slow fade as the customers who shopped around settle in. The rating plan sees only its loyalty discount.
NEW_CUSTOMER = {"early": (0.25, 45.0), "slow": (0.26, 540.0)}
NEW_CUSTOMER_PERILS = ["AF_MV", "AF_SV", "PARKED", "THEFT_TOTAL", "THEFT_PARTIAL", "VANDALISM"]

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
# Vehicle ages. The household fleet (gamma, years, before an income tilt: richer households drive newer cars)
# is TUNED so the cars in force match Chicago personal vehicles in crashes 2021-2025 (City of Chicago Traffic
# Crashes - Vehicles: mean age 9.4 years in 2021 rising to 10.2 in 2025; 41-48% ten or more years old, about
# 21% fifteen or more). The ages are truncated at the vehicle catalogue's first model year (1997): a car drawn
# older is drawn again. Replacements are a mix of new and used purchases (ASSUMED).
FLEET_AGE = dict(shape=2.1, scale=5.5, cap=30.0)
REPLACEMENT_AGE = dict(shape=1.6, scale=4.2)   # age of the vehicle bought as a replacement or an added car
# Model popularity in reference/vehicle_catalogue.csv is measured on vehicles in Chicago crashes, mostly garaged
# in the city (vehicle-weighted density about 16,000 people per square mile). Pickups are commoner where it is
# less dense: their weight scales with (density / this) ** -0.45 (ASSUMED shape).
VEHICLE_DENSITY_REF = 16_000
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
DROP_PD_RATE = [0.003, 0.01, 0.03, 0.06, 0.08]
# Collision on a car the owner is free to insure as they like (financed and leased cars must carry it): the
# log-odds fall with the car's age and rise with income and insurance score (ASSUMED shape; TUNED with
# P_COMP_ONLY to Illinois' take-up: collision on 82.6% and comprehensive on 87.5% of insured cars, NAIC Auto
# Insurance Database 2023).
FULL_COVERAGE = dict(base=4.55, per_year=-0.26, income=0.5, score=0.3, non_standard=-0.6)
KEEP_COMP_WHEN_DROPPING_COLL_P = 0.35                # (ASSUMED)
RAISE_DEDUCTIBLE = dict(base=0.02, per_increase=0.40, cap=0.25)   # after a renewal increase above 10%
LIMIT_CHANGE = dict(up=0.03, down=0.01, down_per_increase=0.15)  # liability limit changes at renewal, per year (ASSUMED)

# Good-student discount: the insurer's eligibility rule, evaluated on each term's effective date (ASSUMED).
# A driver qualifies while under GOOD_STUDENT_MAX_AGE, still in full-time school and keeping B grades.
GOOD_STUDENT_MAX_AGE = 25
GOOD_STUDENT_GRADES_P = 0.40         # children on the policy who keep a B average
P_COLLEGE = 0.60                     # of those, the share who go on to college
SCHOOL_END_AGE = {"high_school": (18.2, 18.8), "college": (21.5, 23.5)}   # age range when full-time school ends

# The working week (ASSUMED weights; the days losses happen on come from Chicago's daily counts, see
# refdata._daily_index). Relative weight of a (weekday, Saturday, Sunday or holiday) for the day a quote is
# given and the day a new policy starts, by channel: agents' offices keep business hours, the website does not.
DAY_WEIGHTS = {
    "quote": {"Independent Agent": (1.0, 0.25, 0.08), "Exclusive Agent": (1.0, 0.35, 0.08), "Direct": (1.0, 0.80, 0.70)},
    "effective": {"Independent Agent": (1.0, 0.55, 0.40), "Exclusive Agent": (1.0, 0.55, 0.40), "Direct": (1.0, 0.90, 0.85)},
}
FIRST_OF_MONTH_WEIGHT = 3.0          # policies are more often written to start on the 1st
ENDORSEMENT_SAME_DAY_P = 0.60        # changes keyed the day they take effect (else a few days later: backdated)
LOSS_MINUTE_HEAPING = {0: 0.22, 30: 0.14, 15: 0.06, 45: 0.06}   # reported loss times bunch on round minutes

# When information reaches the insurer (ASSUMED). Every rating, underwriting and renewal decision uses
# only what is known on its decision date.
RENEWAL_OFFER_LEAD_DAYS = (30, 45)   # renewal offers are rated and mailed this many days before the effective date
OPENING_CAR_HELD_YEARS = 4.0         # cars on policies renewing at the start: mean years on the policy before the
                                     # first rating in the extract, cut at the policy's inception (ASSUMED)
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

# Optional physical damage add-ons (ASSUMED take-up and terms, typical of filed plans). Rental reimbursement
# pays a daily amount up to a per-claim maximum while a covered car is repaired or replaced; towing and labor
# pays for towing after a crash. Both need comprehensive (rental needs collision too).
RENTAL_OPTIONS = [(30, 900), (40, 1_200), (50, 1_500)]       # (daily limit, maximum per claim)
RENTAL_OPTION_P = [0.45, 0.40, 0.15]
RENTAL_FACTOR = [1.00, 1.25, 1.45]
P_RENTAL = 0.50                      # of vehicles with collision
P_TOWING = 0.55                      # of vehicles with comprehensive
TOWING_LIMIT = 100
RENTAL_USE_P = 0.65                  # covered repairs or replacements where the insured rents a car
RENTAL_DAILY_COST = dict(median=48.0, sigma=0.20)
RENTAL_DAYS = {"repair": dict(median=11.0, sigma=0.55), "total": dict(median=21.0, sigma=0.40)}
TOW_P = {"AF_MV": 0.40, "AF_SV": 0.60, "NAF": 0.35, "PARKED": 0.05, "ANIMAL": 0.30}   # crashes needing a tow
TOW_COST = dict(median=135.0, sigma=0.40)
# Underinsured motorist (part of the UM coverage, as in Illinois): when an insured hurt by an insured driver
# has damages above that driver's bodily injury limit, the policy pays the excess up to its own UM limit,
# less what the other driver's insurer paid. Other drivers' per-person limits (ASSUMED; Illinois minimum $25,000):
OTHER_DRIVER_BI_LIMIT = {25_000: 0.30, 50_000: 0.22, 100_000: 0.30, 250_000: 0.13, 500_000: 0.05}

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
GOOD_STUDENT_FACTOR = 0.80
INEXPERIENCE_KNOTS = [0, 1, 3, 5]
INEXPERIENCE_FACTOR = [1.35, 1.25, 1.10, 1.0]
MILEAGE_ELASTICITY = 0.45             # frequency ~ (miles / 10,000) ** elasticity
BUSINESS_USE_FACTOR = 1.10
ADAS_FREQ_FACTOR = {"AF_MV": 0.86, "AF_SV": 0.95}   # automatic emergency braking (ASSUMED, direction per IIHS)
ZIP_RANDOM_EFFECT_SIGMA = {"crash": 0.12, "theft": 0.20}   # true ZIP hazard the insurer cannot see

# Base annual occurrence rates by peril (TUNED to the frequency targets in validate.py). The national
# benchmark for comprehensive excludes wind and water losses and is for a $500 deductible, so glass, theft,
# vandalism, animal and other losses are tuned against it on that basis, and weather comes on top.
BASE_RATE = {
    "AF_MV": 0.0411,        # insured at fault, another vehicle involved
    "AF_SV": 0.0134,        # insured at fault, single vehicle
    "NAF": 0.0379,          # insured not at fault
    "PARKED": 0.0166,       # hit while parked / unoccupied
    "GLASS": 0.0400,
    "THEFT_TOTAL": 0.0011,
    "THEFT_PARTIAL": 0.0060,
    "VANDALISM": 0.0048,
    "ANIMAL": 0.0046,
    "WEATHER": 0.0062,      # non-catastrophe hail, wind, falling limbs
    "FLOOD": 0.0004,
    "FIRE": 0.0004,
    "OTHER_COMP": 0.0050,
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
KIA_HYUNDAI_MODEL_YEARS = (2011, 2021)   # key-start models; electric models were not affected
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
    "COLL": {2021: 0.85, 2022: 0.96, 2023: 0.99, 2024: 1.00, 2025: 1.03, 2026: 1.06},
    "COMP": {2021: 0.82, 2022: 0.90, 2023: 0.97, 2024: 1.00, 2025: 1.03, 2026: 1.06},
}
# What a car is worth. RESIDUAL_VALUE is its value as a share of the model year's base price at each age, at
# pre-pandemic used-car prices (ASSUMED shape: buyers pay about a tenth over the base price for trim and
# options, and a car kept roughly half its price at five years and three tenths at ten). USED_CAR_VALUE_INDEX
# lifts it to each year's used-car market: the Manheim Used Vehicle Value Index (Cox Automotive, January 1997
# = 100) stood in the low 150s before the pandemic, 257.7 at the end of 2021, 219.3 at the end of 2022, 204.0
# at the end of 2023, 204.8 at the end of 2024 and 205.5 at the end of 2025; the mid-year levels here are read
# off that path (2026 ASSUMED flat). A used car is never worth more than NEW_VALUE_CAP times the base price.
# Together they put a ten-year-old car at about 40% of its base price in 2024, in line with the vehicles
# insurers wrote off (CCC Crash Course: average total-loss vehicle value $13,400 to $13,700 in 2024-25).
RESIDUAL_VALUE_AGE = [0, 1, 3, 5, 10, 15, 20, 30]
RESIDUAL_VALUE = [1.10, 0.92, 0.71, 0.54, 0.30, 0.17, 0.11, 0.07]
NEW_VALUE_CAP = 1.15
MIN_VEHICLE_VALUE = 1_500.0
USED_CAR_VALUE_INDEX = {2021: 1.39, 2022: 1.52, 2023: 1.42, 2024: 1.31, 2025: 1.34, 2026: 1.34}

# Severity medians/sigmas at the 2024 level (lognormal; TUNED to the severity targets, compared with the
# national figures on their own definitions: see BENCHMARK in validate.py)
PD_SEV = dict(median=4_450, sigma=0.95)
BI_SEV = dict(median=21_000, sigma=1.40)
UM_SEV = dict(median=9_500, sigma=1.35)
MED_SEV = dict(median=1_900, sigma=0.95)
COLL_SEV = dict(median=6_900, sigma=0.90)          # ground-up repair cost for a reference vehicle
COLL_PERIL_SEV = {"AF_MV": 1.00, "AF_SV": 1.30, "NAF": 0.95, "PARKED": 0.55}
TOTAL_LOSS_THRESHOLD = 0.75                         # repair cost / actual cash value
SALVAGE_RANGE = (0.12, 0.32)                        # share of actual cash value recovered on a total loss
COMP_SEV = {                                        # lognormal (median, sigma) unless noted
    "GLASS": (800, 0.60), "THEFT_PARTIAL": (3_100, 0.90), "VANDALISM": (2_500, 0.90),
    "ANIMAL": (6_400, 0.70), "WEATHER": (3_000, 0.90), "OTHER_COMP": (2_150, 0.90),
    "HAIL_CAT": (4_300, 0.75), "WIND_CAT": (2_500, 0.85),
}
GLASS_ADAS_FACTOR = 1.7                             # windshield camera recalibration
SEGMENT_PD_SEV = {"truck": 1.15}                    # heavier striking vehicle does more damage
SEGMENT_BI_SEV = {"truck": 1.10}
SUV_PD_SEV = 1.05

# Injury settlements are negotiated, so they land on round figures (ASSUMED): each agreed amount is rounded to
# the step for its size, or to twice that step half the time; one in eight keeps its exact amount (a claim
# settled for its medical bills). Steps divide every policy limit. (upper bound of the size band, step)
SETTLEMENT_STEPS = [(1_000, 50), (5_000, 100), (25_000, 250), (100_000, 500), (np.inf, 2_500)]
SETTLEMENT_EXACT_P = 0.125

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
P_FILE_COLL = {"AF_MV": 0.86, "AF_SV": 0.86, "NAF": 0.48, "NAF_UNINSURED": 0.90, "PARKED": 0.70}
P_SUBROGATION = {"NAF": 0.85, "PARKED": 0.10}
SUBROGATION_SHARE = (0.75, 1.00)
P_FILE_BELOW_DEDUCTIBLE = 0.75      # claims opened then closed without payment
CWP = {"PD": 0.05, "BI": 0.14, "UM": 0.14, "MED": 0.05, "COLL": 0.03, "COMP": 0.04, "RENT": 0.02, "TOW": 0.02}
# Claims opened and closed without payment, beyond those above (ASSUMED rates). Together they bring the share
# of closed claims without payment near the 2025 industry figures: about 45% for liability and medical
# claims and just under 25% for collision and comprehensive (WSJ analysis of insurer filings with the NAIC).
P_LIABILITY_DENIED = {"PD": 0.45, "BI": 0.12}        # the other driver claims against an insured not at fault
P_INJURY_NOT_PURSUED = {"AF_MV": 0.55, "AF_SV": 0.08}   # an injury claim is opened but never paid
P_FIRST_PARTY_WITHDRAWN = 0.60                       # damage reported, then not pursued (or paid by the other insurer)
P_COMP_ONLY = 0.29     # vehicles without collision that carry comprehensive (Illinois: 82.6% collision and 87.5%
                       # comprehensive per liability car-year, NAIC Auto Insurance Database 2023)
CHARGEABLE_THRESHOLD = 1_000        # paid amount that makes an at-fault claim surchargeable: cumulative PD, BI
                                    # and collision payments reaching it
CHARGEABLE_POSTING_DAYS = 1         # the claim goes on the driver's record this many days after that payment is
                                    # booked. With dates only, this fixes the order of events on one day: a
                                    # rating dated D uses records with a known date of D or earlier, and nothing
                                    # that happens on D itself (a loss or a payment) can carry a known date of D

# --------------------------------------------------------------------------
# Driver record (ASSUMED rates; tuned so ~84% of drivers have no violation in 3 years)
# --------------------------------------------------------------------------
VIOLATION_RATE = 0.064              # minor moving violations per driver-year for a reference driver
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
TARGET_LOSS_RATIO = 0.825           # at day-one cost levels, before catastrophes: the book starts under-priced,
                                    # as the industry was entering 2022 after pandemic-era rate cuts (TUNED so
                                    # accident-year loss ratios follow the industry: about 80% in 2022, 73-75%
                                    # in 2023, 63-66% in 2024 and about 61% in 2025; see validate.py)
COMP_CAT_LOAD = 1.16                # catastrophe provision in comprehensive rates
N_TERRITORIES = 12
PLANTED_DISTORTIONS = {
    "class": {"16-17 M": 0.80, "16-17 F": 0.80, "18-20 M": 0.82, "18-20 F": 0.82,
              "21-24 M": 0.90, "21-24 F": 0.90, "75+": 0.88},
    "mileage_exponent": 0.5,        # mileage relativities are flattened (square root of the fitted value)
}
# Filed discounts and surcharges (ASSUMED, typical of filed personal auto plans). Unlike the class, territory,
# vehicle and insurance-score relativities, these are not fitted to the true expected cost: a real carrier files
# them as round percentages, partly for marketing and retention, and they are only roughly what the risk
# justifies. The rest of the plan is fitted around them. (levels in the order of rating.LEVELS; coverages they
# apply to). The answer key's rating_plan.json gives what each is truly worth beside what is filed.
LIABILITY_AND_COLLISION = ["BI", "PD", "UM", "MED", "COLL"]
DRIVER_COVERAGES = ["BI", "PD", "MED", "COLL"]
MAIN_COVERAGES = ["BI", "PD", "UM", "MED", "COLL", "COMP"]
FILED_DISCOUNTS = {
    "multi_car": ([1.00, 0.90], MAIN_COVERAGES),                 # 10% multi-car discount
    "multi_policy": ([1.00, 0.92], MAIN_COVERAGES),              # 8% multi-policy (bundling) discount
    "homeowner": ([1.00, 0.95], LIABILITY_AND_COLLISION),        # 5% homeowner discount
    "paid_in_full": ([1.00, 0.94], MAIN_COVERAGES),              # 6% paid-in-full discount
    "prior_insurance": ([1.08, 1.00], LIABILITY_AND_COLLISION),  # 8% surcharge without prior insurance
    "tenure": ([1.00, 0.98, 0.96, 0.94], MAIN_COVERAGES),        # loyalty discount: 2%, 4%, 6%
    "good_student": ([1.00, 0.90], DRIVER_COVERAGES),            # 10% good-student discount
    "married": ([1.00, 0.95], DRIVER_COVERAGES),                 # 5% married discount
}

# Filed rate changes, by effective date (ASSUMED timing; sized to the industry cycle). US private auto rates
# rose 12.1% in 2022, 16.5% in 2023 and 7.6% in 2024 (S&P Global RateWatch), approved increases slowed to
# 3.7% in 2025 (AM Best), and Illinois' largest writer cut rates in 2025 (State Farm). Cumulative here: +48%.
RATE_CHANGES = [("2022-04-01", 0.04), ("2022-10-01", 0.08), ("2023-03-01", 0.10), ("2023-09-01", 0.09),
                ("2024-03-01", 0.08), ("2025-03-01", 0.02), ("2026-06-01", -0.02)]

# --------------------------------------------------------------------------
# Retention and cancellation (ASSUMED)
# --------------------------------------------------------------------------
RENEWAL_BASE_LOGIT = {6: 2.57, 12: 1.90}
# A customer who had a claim since the last renewal offer is likelier to leave: any claim, more if it was
# at fault (a surcharge is coming, on top of the price effect below), more again after a second (renewal
# logit; ASSUMED, sized to a real motor portfolio in which a contract with a claim in the period was 1.45
# times as likely to end as one without: docs/real_data_comparison.md).
CLAIM_RETENTION = dict(any=-0.55, at_fault=-0.45, repeat=-0.30)
PRICE_ELASTICITY = 6.0              # logit points per 100% premium increase above the tolerance
PRICE_TOLERANCE = 0.03
MIDTERM_INSURED_REQUEST_RATE = 0.030   # per year
NONPAY_RATE = {"Paid in Full": 0.0, "Monthly EFT": 0.022, "Monthly Bill": 0.065}   # per year, mid score
NONPAY_NEW_BUSINESS = 1.6            # new customers miss payments more often in their first term
# A cancellation for non-payment follows a missed instalment (billing.py): instalments fall due monthly on the
# policy's anniversary day, and cover ends some days after the one that went unpaid (a past-due notice, then a
# notice of cancellation at least 10 days ahead, as Illinois requires). Which instalment is missed: each later
# one is this much less likely than the one before (new customers default early).
NONPAY_INSTALLMENT_DECAY = {"new": 0.55, "renewal": 0.85}
NONPAY_GRACE_DAYS = (21, 28)         # from the missed due date to the cancellation taking effect
UW_CANCEL_NEW_BUSINESS_P = 0.008

# --------------------------------------------------------------------------
# Quotes (ASSUMED). Conversion at the market price by channel, how strongly it falls as our price rises
# above the best competing quote, and how widely our price varies around that quote.
# --------------------------------------------------------------------------
QUOTE_CONVERSION = {"Independent Agent": 0.22, "Exclusive Agent": 0.38, "Direct": 0.12}   # at the market's price level
QUOTE_PRICE_ELASTICITY = 5.0         # logit points per unit of log(our price / best competing price)
COMPETITOR_PRICE_SIGMA = 0.18
COMPARATIVE_RATER_CHANNELS = ["Independent Agent"]   # competing quotes are seen only through agents' comparative raters
# The market (see market.py). Its rate level: US private auto rates rose 12.1% in 2022, 16.5% in 2023 and 7.6% in
# 2024 (S&P Global RateWatch) and approved increases slowed to 3.7% in 2025 (AM Best); 2026 is ASSUMED. Each
# year's change is spread evenly over the year, while the company's own filed changes (RATE_CHANGES) land on
# their effective dates, so the company is dearer than the market after each increase until the market catches up.
MARKET_RATE_CHANGE = {2021: 0.0, 2022: 0.121, 2023: 0.165, 2024: 0.076, 2025: 0.037, 2026: -0.005}
MARKET_REFERENCE_DATE = "2022-01-01"     # the day the company's rate level and the market's are level
MARKET_RETENTION = 1.5                   # renewal logit per unit of log(own rate level / market's) on the offer day
# How many households shop (ASSUMED shapes). By month: most in late winter and spring, when tax refunds arrive
# and cars are bought, fewest around the year-end holidays. By year: shopping rose as premiums did, to record
# levels in 2024 (as LexisNexis' Insurance Demand Meter reported), and eased afterwards.
SHOPPING_SEASONALITY = [0.98, 1.06, 1.14, 1.08, 1.03, 1.01, 1.00, 1.02, 0.97, 0.95, 0.91, 0.85]
SHOPPING_YEAR = {2021: 0.90, 2022: 0.92, 2023: 1.00, 2024: 1.12, 2025: 1.08, 2026: 1.02}

# --------------------------------------------------------------------------
# The company's history (ASSUMED). It was founded in January 2000: no policy, agency appointment or producer is
# older. Its systems went live over the years (identifiers.KEY_SYSTEMS), and each numbers its records from then.
# --------------------------------------------------------------------------
FOUNDED = "2000-01-01"
COMPANY_SIZE_AT_FOUNDING = 0.25     # its size in 2000 as a share of its size from 2022, growing evenly in between

# --------------------------------------------------------------------------
# General ledger (ledger.py). The books open the day before the extract begins with surplus of this share of the
# annual premium then in force (ASSUMED; US personal auto carriers write roughly two dollars of premium per
# dollar of surplus), held as cash.
# --------------------------------------------------------------------------
OPENING_SURPLUS_SHARE = 0.50

# --------------------------------------------------------------------------
# Catastrophes: REAL storms in the seven counties, from NOAA's Storm Events Database (scripts/
# build_catastrophe_events.py, which states the thresholds: hail, flash flooding and wind days big enough to
# damage many cars). The date, place, peril and footprint are NOAA's reports; how likely a car is to be hit
# (the peak, at the centre) is ASSUMED, scaled by the storm's severity; the claims are simulated. NOAA's data
# ran to mid-August 2026 when the list was built.
# (id, date, description, peril, centre lat, centre lon, radius miles, peak hit probability)
# --------------------------------------------------------------------------
CAT_EVENTS = [
    ("CAT-2023-01", "2023-04-04", "Large hail - Fox Valley, Kendall County and the North Shore", "HAIL_CAT", 41.91, -88.20, 20.0, 0.0500),
    ("CAT-2023-02", "2023-07-02", "Record rainfall and flash flooding - Cook County and the west suburbs", "FLOOD_CAT", 41.80, -87.87, 10.0, 0.0140),
    ("CAT-2024-01", "2024-02-27", "Hail and tornadoes - southwest suburbs", "HAIL_CAT", 41.72, -88.01, 15.7, 0.0370),
    ("CAT-2024-02", "2024-07-15", "Derecho and 27 tornadoes - metro wide", "WIND_CAT", 41.76, -87.92, 26.5, 0.0120),
    ("CAT-2025-01", "2025-06-08", "Large hail - Batavia and central Kane County", "HAIL_CAT", 41.85, -88.34, 6.0, 0.0400),
    ("CAT-2025-02", "2025-07-25", "Flash flooding - southeast DuPage and central Cook", "FLOOD_CAT", 41.73, -88.06, 7.5, 0.0116),
    ("CAT-2025-03", "2025-08-17", "Flash flooding - Chicago and the south and west suburbs", "FLOOD_CAT", 41.78, -87.87, 10.0, 0.0123),
    ("CAT-2026-01", "2026-03-10", "Giant hail - Fox Valley, Joliet and Chicago", "HAIL_CAT", 41.74, -88.11, 20.0, 0.0350),
    ("CAT-2026-02", "2026-06-10", "Derecho - metro wide", "WIND_CAT", 41.79, -88.05, 24.1, 0.0100),
    ("CAT-2026-03", "2026-07-27", "Hail, wind and flooding - DuPage and the west and southwest suburbs", "HAIL_CAT", 41.80, -87.97, 20.0, 0.0480),
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
                  "COLL": "Collision", "COMP": "Comprehensive", "RENT": "Rental Reimbursement",
                  "TOW": "Towing and Labor"}
COVERAGES = list(COVERAGE_NAMES)


def year_series(table: dict[int, float], years: np.ndarray) -> np.ndarray:
    """Look up a per-year table for an array of calendar years (clamped to the table's range)."""
    ks = np.array(sorted(table))
    vals = np.array([table[k] for k in ks])
    return vals[np.clip(np.searchsorted(ks, years), 0, len(ks) - 1)]
