"""Claim lifecycle: reporting, expenses, closure, payments, recoveries and reserves.

The simulation knows the ultimate cost of every claim. `Development` decides when each dollar
moves, as the claims happen, so the simulation can tell when the insurer learns of a claim and
when it becomes chargeable. `develop` then cuts everything off at the valuation date: later
payments are not yet made, open claims carry an (imperfect) case reserve, and claims not yet
reported are left out of the extract entirely and written to the answer key instead.

Payment patterns (ASSUMED, by coverage). Glass and most injury claims settle in one payment.
Physical damage is often paid on the first estimate and topped up by supplements; property
damage liability may pay loss of use before the repair; injury claims sometimes get an advance;
medical payments follow the bills. A total loss on a financed or leased car pays off the lender
first (a leasing company, which owns the car, takes the whole settlement) and the owner gets what
is left; a car owned outright is paid to its owner. Title and fee costs may be paid later. A few
payments are voided and reissued, and a few closed features reopen for a supplemental payment.
Every feature's payments add up to its ultimate paid loss to the cent.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from . import config as C

REPORT_LAG_MEAN = {"AF_MV": 2.0, "AF_SV": 2.0, "NAF": 2.5, "PARKED": 3.0, "GLASS": 4.0, "THEFT_TOTAL": 1.0,
                   "THEFT_PARTIAL": 2.0, "VANDALISM": 3.0, "ANIMAL": 1.5, "WEATHER": 6.0, "FLOOD": 3.0, "FIRE": 1.0,
                   "OTHER_COMP": 4.0, "HAIL_CAT": 9.0, "WIND_CAT": 5.0, "FLOOD_CAT": 3.0}
# Days from first notice until a coverage is claimed: (probability opened at first notice, mean days for
# most later ones, share opened much later, median days for those). Injury claimants often present weeks or
# months later; a few only near the statute of limitations (2 years for injury, 5 for property damage in
# Illinois: 735 ILCS 5/13-202 and 13-205). Fitted to a US insurer's BI report lags, 27% on the accident
# day, 84% within 5 days, 97.5% within 90 and 99.2% within a year (CAS Loss Simulation Model Working
# Party, Ball State University paper); the other shapes are ASSUMED.
OPEN_LAG = {"BI": (0.80, 8.0, 0.045, 160.0), "UM": (0.78, 12.0, 0.05, 170.0), "MED": (0.90, 20.0, 0.0, 1.0),
            "PD": (0.92, 20.0, 0.02, 90.0)}
OPEN_LAG_SIGMA = 1.0
OPEN_LAG_CAP = {"BI": 700, "UM": 700, "MED": 700, "PD": 1800}      # days after the accident, inside the statute
# The formula (average) reserve set at first notice, at 2024 cost levels (ASSUMED), moved with each coverage's own
# severity trend (RESERVE_TREND, config.SEVERITY_TREND: 2024 = 1.00); rental and towing, paid within fixed dollar
# limits, do not move. Property coverages' are near the average paid per claim opened, nil payments included, as
# carriers set average reserves to be adequate in aggregate (glass separately: GLASS_FORMULA_RESERVE); injury ones
# start low, as injury case reserves do
FORMULA_RESERVE = {"BI": 12_000, "UM": 10_000, "MED": 1_700, "PD": 5_000, "COLL": 5_000, "COMP": 3_000, "RENT": 600, "TOW": 100}
RESERVE_TREND = {"BI": "BI", "UM": "BI", "MED": "BI", "PD": "PD", "COLL": "COLL", "COMP": "COMP"}
GLASS_FORMULA_RESERVE = 900
# precautionary injury claims and claims against an insured not at fault get a nominal reserve (ASSUMED)
NOMINAL_RESERVE = {"BI": 2_500, "PD": 750}
# log-scale (bias, noise) of an adjuster's early estimate of ultimate. Injury estimates start at about 86% of
# ultimate on average (exp(bias + noise^2 / 2)), so injury case incurred develops upward as claims mature
RESERVE_ERROR = {"BI": (-0.30, 0.55), "UM": (-0.30, 0.55), "MED": (-0.10, 0.35), "PD": (0.0, 0.20),
                 "COLL": (0.0, 0.20), "COMP": (0.0, 0.20), "RENT": (0.0, 0.20), "TOW": (0.0, 0.20)}
EXPENSE = {"PD": (0.60, 220), "COLL": (0.80, 260), "COMP": (0.40, 120), "MED": (0.30, 150)}   # (share with expense, median)

# Interim payments before the final one: (probability of a first, probability of a second)
INTERIM_P = {"PD": (0.30, 0.10), "COLL": (0.28, 0.07), "COMP": (0.15, 0.04), "BI": (0.12, 0.0), "UM": (0.12, 0.0)}
MED_BILLS_MEAN = 1.6                  # extra medical-payments bills beyond the first (Poisson, at most 6)
# A financed car's loan payoff at a total loss, as a share of the settlement (ASSUMED). Above 1 the loan is
# worth more than the car (negative equity, about a quarter of loans here): the lender takes the whole
# settlement and gap cover, not this policy, pays the rest. A leased car's settlement all goes to the lessor.
LOAN_PAYOFF_SHARE = (0.35, 1.20)
TOTAL_LOSS_FEES_P = 0.20              # title, tax and fees paid after the settlement
REOPEN_P = {"PD": 0.03, "COLL": 0.04, "COMP": 0.02, "BI": 0.04, "UM": 0.04, "MED": 0.05}
VOID_P = 0.012                        # an interim payment is voided and reissued
TXN = ["Partial Payment", "Final Payment", "Supplemental Payment", "Void", "Reissue", "DCC Expense", "A&O Expense", "Recovery"]

# Expense categories, as in statutory reporting: defence and cost containment (DCC: litigation, medical
# examinations and records, medical bill review) and adjusting and other (A&O: appraisals and
# independent adjusters). Litigated features carry an expense (DCC) reserve from the suit date.
DCC_COVERAGES = {"BI", "UM", "MED"}

# Reserve history (ASSUMED). An adjuster sets a formula reserve when a feature opens, then re-estimates the
# ultimate on a review cycle. The estimate's error (RESERVE_ERROR: log bias and noise, injury reserves
# starting low) is strongly correlated from one review to the next and shrinks as the claim matures,
# which produces case development in the incurred triangles. Payments erode the reserve; closing takes
# it to zero; a reopening sets it again for the expected supplement. Paid plus case reserve never exceeds
# what the coverage could pay (the feature's `cap`: its per-person or per-claim limit, or the car's value less
# the deductible): adjusters reserve within the policy limits, and expected legal costs are carried in the
# separate expense reserve. Where several claimants of one accident share a per-accident limit, the limit
# left after what has been paid is shared among their open reserves whenever they would add up to more,
# using only what is known that day (claims._share_accident_limit).
RESERVE_REVIEW_DAYS = {"BI": 90, "UM": 90, "MED": 60, "PD": 30, "COLL": 30, "COMP": 30, "RENT": 30, "TOW": 30}
RESERVE_PERSISTENCE = 0.75           # correlation of successive estimate errors
MIN_RESERVE = 250                    # an open feature carries at least this, unless less is left under its limit
RESERVE_ROUNDING = 50

# Claim detail (ASSUMED shapes). Bodily injury attorney involvement was 57% in 2022 and the litigation rate
# 10% to 18% (Insurance Research Council, 2026); about half of represented claimants hire an attorney
# within days of the accident and 80% within weeks (IRC survey, 2026). Suits are filed within the
# two-year statute of limitations (735 ILCS 5/13-202). Illinois bars recovery by a party more than 50%
# at fault (735 ILCS 5/2-1116), so an insured paying a liability claim is 51% to 100% at fault.
ATTORNEY_LAG_DAYS = ((0.5, 1, 8), (0.3, 8, 31), (0.2, 31, 181))   # (share, from, before) days after the accident
SUIT_LAG_DAYS = (60, 421)            # from the later of retaining an attorney and presenting the claim to filing suit
SUIT_LIMIT_DAYS = 729                # suits are filed inside the two-year statute
SUIT_TO_CLOSE = dict(min_days=30, mean_extra=90.0)   # a filed suit runs at least this long before the feature closes
POLICE_REPORT_P = {"AF_MV": 0.60, "AF_SV": 0.55, "NAF": 0.60, "PARKED": 0.35, "THEFT_TOTAL": 0.97,
                   "THEFT_PARTIAL": 0.85, "VANDALISM": 0.60, "FIRE": 0.70, "ANIMAL": 0.15, "GLASS": 0.02,
                   "WEATHER": 0.05, "FLOOD": 0.10, "OTHER_COMP": 0.20, "HAIL_CAT": 0.01, "WIND_CAT": 0.03, "FLOOD_CAT": 0.05}
SIU_REFERRAL_P = 0.012               # base rate of referral to the special investigations unit
INJURY_TYPES = ["Soft Tissue", "Laceration", "Fracture", "Head or Spinal Injury", "Fatality"]
# "No such day" for a claim's optional dates (attorney, suit, reopening, fraud referral, chargeable). Not -1: claims
# open when the extract begins have real dates before its first day, which are negative day numbers.
NO_DAY = -10 ** 9


class Development:
    """Develops claims to ultimate as the simulation produces them. Timing and payments come from one
    random stream; reserve estimates and claim detail from another, so they never move the amounts paid.
    The one link back is a litigated feature's close, which waits for its suit (litigation_timeline)."""

    def __init__(self, cal, rng: np.random.Generator, rng_detail: np.random.Generator) -> None:
        self.cal, self.R, self.R2 = cal, rng, rng_detail
        self.occs, self.feats, self.pays, self.reserves = [], [], [], []
        self.n_feat = 0
        self.rentals = []           # paid rentals: batch, feature, policy, loss day, days kept (stop_rentals)

    def add(self, occ: pd.DataFrame, feat: pd.DataFrame) -> pd.DataFrame:
        """Develop a batch of new claims. Returns occ with report_day (first notice the company has of any
        feature) and chargeable_day (the day an at-fault claim's payments reach the surcharge threshold, or NO_DAY).
        occ.notice, when given, is the first notice (simulate draws it when the loss happens, since a car written
        off leaves the policy only once the company knows of it)."""
        R = self.R
        occ = occ.copy()
        notice = occ.notice.to_numpy().astype(np.int64) if "notice" in occ else first_notice(self.cal, occ, R)

        # the car's ownership at the loss (Owned, Financed or Leased) decides whether a lender is paid
        keep = ["occ", "day", "peril", "cat", "at_fault"] + (["ownership"] if "ownership" in occ else [])
        f = feat.merge(occ[keep].assign(notice=notice), on="occ", how="left")
        n = len(f)
        f["fid"] = self.n_feat + np.arange(n)
        self.n_feat += n
        cvg = f.cvg.to_numpy()
        f["paid"] = np.round(f.paid.to_numpy(), 2)
        paid = f.paid.to_numpy()
        injury = np.isin(cvg, ["BI", "UM"])
        cap = f.day.to_numpy() + np.array([OPEN_LAG_CAP.get(c, 3650) for c in cvg])
        # a coverage claimed after the first notice is set up by staff, on a business day
        later = _open_lag(cvg, R)
        opened = np.where(later > 0, self.cal.spread_business(f.notice.to_numpy() + later, R.random(n)), f.notice.to_numpy())
        f["open_day"] = np.minimum(opened, np.maximum(cap, f.notice.to_numpy()))

        # litigation and loss adjustment expense
        lit = injury & (paid > 0) & (R.random(n) < 0.07 + 0.10 * (paid > 15_000) + 0.22 * (paid > 50_000))
        expense = np.zeros(n)
        z, u = R.standard_normal(n), R.random(n)
        expense = np.where(lit, (3_500 + 0.16 * paid) * np.exp(0.5 * z - 0.125), expense)
        expense = np.where(injury & ~lit & (u < 0.70), 500 * np.exp(0.8 * z), expense)
        for k, (share, median) in EXPENSE.items():
            expense = np.where((cvg == k) & (u < share), median * np.exp(0.5 * z), expense)
        # no outside appraisal for glass (the glass shop's invoice is the estimate) or for a stolen car paid as a
        # total loss (valued at the desk from market data: there is no car to inspect)
        peril, total = f.peril.to_numpy(), f.total.to_numpy().astype(bool)
        desk = np.isin(cvg, ["PD", "COLL", "COMP"]) & ((peril == "GLASS") | ((peril == "THEFT_TOTAL") & total))
        expense = np.where(desk, 0.0, expense)
        f["litigated"], f["expense"] = lit, np.round(expense, 2)

        # time to close
        g = R.gamma(2.0, 0.5, n)                       # mean 1
        ln = R.standard_normal(n)
        peril = f.peril.to_numpy()
        total = f.total.to_numpy()
        mean = np.select([cvg == "RENT", cvg == "TOW", cvg == "PD", (cvg == "COLL") & total, cvg == "COLL", peril == "GLASS",
                          peril == "THEFT_TOTAL", f.cat.to_numpy() >= 0, cvg == "COMP", cvg == "MED"],
                         [35, 8, 32, 34, 24, 6, 18, 28, 16, 80], default=0.0)
        dur = mean * g + 30 * ((peril == "THEFT_TOTAL") & (cvg != "TOW"))
        # a rental is paid once the car is returned: the days it was kept after the loss, then the invoice (2 to about
        # 10 days)
        rent_days = np.nan_to_num(f["rent_days"].to_numpy(dtype=float)) if "rent_days" in f else np.zeros(n)
        returned = f.day.to_numpy() + np.ceil(rent_days)
        f["pay_from"] = np.where(cvg == "RENT", returned + 1, -10 ** 9)          # nothing to pay before the car is back
        dur = np.where(cvg == "RENT", np.maximum(dur, returned + 2 + np.floor(3 * g) - f.open_day.to_numpy()), dur)
        inj_dur = 200 * np.exp(0.8 * ln) * np.clip(paid / 15_000, 0.2, 8) ** 0.15 + lit * 420 * np.exp(0.5 * R.standard_normal(n))
        dur = np.where(injury, np.where(paid > 0, inj_dur, 110 * np.exp(0.7 * ln)), dur)
        dur = np.where(~injury & f.cwp.to_numpy(), 14 * g, dur)
        dur = np.maximum(dur, 1).astype(int)
        f["close_day"] = self.cal.spread_business(f.open_day.to_numpy() + dur, R.random(n))      # files are closed on business days

        f = _injury_detail(f, self.cal, self.R2)          # may move a litigated feature's close later
        pays, f = _schedule(f, R, self.cal)
        occ["report_day"] = occ.occ.map(f.groupby("occ").open_day.min()).to_numpy()
        # a claim goes on the driver's record the day after the payment that makes it chargeable is booked
        posted = _chargeable(f, pays) + C.CHARGEABLE_POSTING_DAYS
        occ["chargeable_day"] = occ.occ.map(posted).fillna(NO_DAY).astype(np.int64).to_numpy()
        occ = _claim_detail(occ, f, self.R2, self.cal)
        rent = np.flatnonzero((cvg == "RENT") & (f.paid.to_numpy() > 0))
        if len(rent) and "pol" in occ:
            pol_of = pd.Series(occ.pol.to_numpy(), index=occ.occ.to_numpy())
            self.rentals.append(pd.DataFrame(dict(b=len(self.feats), fid=f.fid.to_numpy()[rent],
                                                  pol=pol_of.reindex(f.occ.to_numpy()[rent]).to_numpy(),
                                                  day=f.day.to_numpy()[rent], days=rent_days[rent])))
        self.reserves.append(_reserve_history(f, pays, self.cal, self.R2))
        self.occs.append(occ)
        self.feats.append(f.drop(columns=["notice", "at_fault"]))
        self.pays.append(pays)
        return occ

    def stop_rentals(self, pol: np.ndarray, death: np.ndarray) -> None:
        """A rental under way when the household's only driver dies (policy pol, on day death) is paid for the days
        until the death: the car goes back then. For a death drawn after the rental was developed (one early in the
        next term); simulate cuts a rental short of a death due in its own term before it is developed. The rental's
        payment and its share of the other insurer's repayment shrink with it; its reserve history, set before the
        death, stands (the settlement takes the reserve to nothing either way)."""
        if not self.rentals or len(pol) == 0:
            return
        r = pd.concat(self.rentals, ignore_index=True)
        end = pd.Series(np.asarray(death), index=np.asarray(pol)).groupby(level=0).min()
        left = r.pol.map(end).to_numpy(dtype=float) - r.day.to_numpy()
        hit = (left > 0) & (left < r.days.to_numpy())               # (NaN, no death, compares False)
        if not hit.any():
            return
        r = r[hit].assign(left=left[hit])
        for b, g in r.groupby("b"):
            share = pd.Series((g.left / g.days).to_numpy(), index=g.fid.to_numpy())
            kept = pd.Series(g.left.to_numpy(), index=g.fid.to_numpy())
            f = self.feats[b]
            m = f.fid.isin(share.index).to_numpy()
            s = f.fid[m].map(share).to_numpy()
            paid = np.round(f.paid.to_numpy()[m] * s, 2)
            subro = np.round(f.subro.to_numpy()[m] * s, 2)
            f = f.copy()
            f.loc[m, "gross"] = f.gross.to_numpy()[m] * s
            f.loc[m, "paid"], f.loc[m, "subro"] = paid, subro
            f.loc[m, "rent_days"] = f.fid[m].map(kept).to_numpy()
            self.feats[b] = f
            new_paid = pd.Series(paid, index=f.fid.to_numpy()[m])
            new_subro = pd.Series(subro, index=f.fid.to_numpy()[m])
            p = self.pays[b].copy()
            on = p.fid.isin(share.index).to_numpy()
            loss = on & (p.kind.to_numpy() == "Loss")                 # a rental is one payment, once the car is back
            p.loc[loss, "amount"] = p.fid[loss].map(new_paid).to_numpy()
            rec = on & (p.kind.to_numpy() == "Subrogation Recovery")
            p.loc[rec, "amount"] = -p.fid[rec].map(new_subro).to_numpy()
            self.pays[b] = p[~(on & (p.amount.to_numpy() == 0))].reset_index(drop=True)
        done = pd.MultiIndex.from_frame(r[["b", "fid"]])
        self.rentals = [x[~pd.MultiIndex.from_frame(x[["b", "fid"]]).isin(done)] if len(x) else x for x in self.rentals]

    def result(self):
        cat = lambda parts: pd.concat(parts, ignore_index=True)
        return cat(self.occs), cat(self.feats), cat(self.pays), cat(self.reserves)


def litigation_timeline(day, open_day, close_day, attorney_lag, suit_lag, run):
    """Order a litigated feature's events. The attorney is retained `attorney_lag` days after the accident;
    suit is filed `suit_lag` days after the later of that and the claim being presented, but inside the
    statute of limitations; and the feature closes no sooner than `run` days after the suit. A feature whose
    drawn close would come too soon stays open longer: the suit is never moved ahead of the attorney or the
    claim to make it fit. Returns (attorney day, suit day, close day)."""
    attorney = day + attorney_lag
    ready = np.maximum(attorney, open_day)
    suit = np.maximum(np.minimum(ready + suit_lag, day + SUIT_LIMIT_DAYS), ready)
    return attorney, suit, np.maximum(close_day, suit + run)


def _injury_detail(f: pd.DataFrame, cal, R: np.random.Generator) -> pd.DataFrame:
    """Injury type, attorney representation and suit date for injury and medical features. Litigated
    features get an ordered timeline, which can move their close later."""
    n = len(f)
    cvg, gross, day = f.cvg.to_numpy(), f.gross.to_numpy(), f.day.to_numpy()
    od, cd, lit = f.open_day.to_numpy(), f.close_day.to_numpy(), f.litigated.to_numpy()
    injury = np.isin(cvg, ["BI", "UM", "MED"])
    median = np.select([cvg == "BI", cvg == "UM"], [C.BI_SEV["median"], C.UM_SEV["median"]], default=C.MED_SEV["median"])
    sigma = np.select([cvg == "BI", cvg == "UM"], [C.BI_SEV["sigma"], C.UM_SEV["sigma"]], default=C.MED_SEV["sigma"])
    z = np.log(np.maximum(gross, 1) / (median * cal.sev_trend["BI"][np.clip(day, 0, cal.horizon)])) / sigma
    paid = f.paid.to_numpy()
    z = np.where(paid > 0, z, -9)                      # claims closed without payment: alleged soft-tissue injuries
    kind = np.searchsorted([0.25, 1.9, 2.75], z) + (z >= 1.9)       # 0 soft, 2 fracture, 3 head/spinal, 4 fatality
    kind = np.where((z >= 0.25) & (z < 1.9), np.where(R.random(n) < 0.4, 1, 2), kind)
    # the policy's own people (its listed drivers claiming medical payments or uninsured motorist cover) are in the
    # policy's records: their claim is a fatality exactly when they died in the crash (truth.simulate,
    # simulate._crash_deaths), and otherwise at worst a head or spinal injury. Other claimants are not people the
    # data follows, so their worst injuries can be fatal
    own = ((cvg == "UM") & (f.claimant.to_numpy() == 1)) | (cvg == "MED")
    if "injured" in f:
        own |= f["injured"].fillna(-1).to_numpy().astype(np.int64) >= 0
    died = f["death"].to_numpy().astype(bool) if "death" in f else np.zeros(n, dtype=bool)
    kind = np.where(own, np.where(died, INJURY_TYPES.index("Fatality"), np.minimum(kind, INJURY_TYPES.index("Head or Spinal Injury"))), kind)
    f["injury_type"] = np.where(injury, np.array(INJURY_TYPES)[np.clip(kind, 0, 4)], "")
    p_att = np.where(cvg == "MED", 0.05, np.where(paid > 0, 0.30 + 0.25 * (z > 0) + 0.15 * (z > 1), 0.08))
    attorney = injury & (lit | (R.random(n) < p_att))
    u = R.random(n)
    (p1, a1, b1), (p2, a2, b2), (_, a3, b3) = ATTORNEY_LAG_DAYS
    lag = np.where(u < p1, R.integers(a1, b1, n), np.where(u < p1 + p2, R.integers(a2, b2, n), R.integers(a3, b3, n)))
    run = SUIT_TO_CLOSE["min_days"] + np.floor(R.exponential(SUIT_TO_CLOSE["mean_extra"], n)).astype(int)
    att_lit, suit, cd_lit = litigation_timeline(day, od, cd, lag, R.integers(*SUIT_LAG_DAYS, n), run)
    # courts sit on business days: the suit is filed on one, still inside the statute and after the attorney and
    # the claim; the feature then closes (on a business day) no sooner than `run` days after the suit
    ready = np.maximum(att_lit, od)
    suit = cal.business_between(suit, ready, day + SUIT_LIMIT_DAYS, R.random(n))
    cd_lit = cal.spread_business(np.maximum(cd, suit + run), R.random(n))
    cd = np.where(lit, cd_lit, cd)
    # without a suit the attorney is simply retained before the feature closes
    att = np.where(lit, att_lit, np.minimum(day + lag, np.maximum(cd - 1, day)))
    f["close_day"] = cd
    f["attorney"] = attorney
    f["attorney_day"] = np.where(attorney, att, NO_DAY)
    f["suit_day"] = np.where(lit, suit, NO_DAY)
    return f


def _claim_detail(occ: pd.DataFrame, f: pd.DataFrame, R: np.random.Generator, cal) -> pd.DataFrame:
    """Police report, the insured's share of fault, and referral to the special investigations unit."""
    n = len(occ)
    peril = occ.peril.to_numpy()
    # what is known at the scene and the first notice, not how the claim turns out: someone was hurt (an injury
    # or medical payments claim with damages, paid in the end or not). A crash that killed someone always has a
    # police report: the police investigate every fatal crash
    injured = occ.occ.isin(f.occ[np.isin(f.cvg.to_numpy(), ["BI", "UM", "MED"]) & (f.gross.to_numpy() > 0)]).to_numpy()
    fatal = occ.occ.isin(f.occ[f.injury_type.to_numpy() == "Fatality"]).to_numpy() if "injury_type" in f else np.zeros(n, dtype=bool)
    if "fatal_crash" in occ:                  # an insured killed with no claim of their own (no medical payments)
        fatal = fatal | occ.fatal_crash.fillna(False).to_numpy().astype(bool)
    occ["police_report"] = fatal | (R.random(n) < np.clip(occ.peril.map(POLICE_REPORT_P).fillna(0.1).to_numpy() + 0.30 * injured, 0, 0.98))
    fault = np.select([peril == "AF_MV", peril == "AF_SV", peril == "NAF"],
                      [np.where(R.random(n) < 0.7, 100, R.integers(51, 100, n)), np.full(n, 100),
                       np.where(R.random(n) < 0.8, 0, R.integers(5, 50, n))], default=-1)
    occ["fault_pct"] = fault
    # referral signals an adjuster sees early: a total theft, a late report, an injury claimed on a crash; a glass
    # chip or a storm loss is almost never referred
    routine = np.isin(peril, ["GLASS", "HAIL_CAT", "WIND_CAT", "FLOOD_CAT", "WEATHER"])
    p_siu = (SIU_REFERRAL_P + 0.07 * (peril == "THEFT_TOTAL") + 0.06 * (occ.report_day.to_numpy() - occ.day.to_numpy() > 30)
             + 0.02 * injured) * np.where(routine, 0.1, 1.0)
    # a referral is made while the claim is open: 5 to 45 days after the report, or before it first closes, on a
    # business day (on the close day itself only if the claim closes on the first business day after its report).
    # It first closes when every feature opened by then has closed (a later feature, even one opened after the
    # valuation date, reopens it)
    report = occ.report_day.to_numpy()
    g = f[["occ", "open_day", "close_day"]].sort_values(["occ", "open_day"], kind="stable")
    run = g.groupby("occ").close_day.cummax()
    nxt = g.groupby("occ").open_day.shift(-1).fillna(np.inf)
    closes = occ.occ.map(run[run.to_numpy() < nxt.to_numpy()].groupby(g.occ[run.to_numpy() < nxt.to_numpy()]).min()).to_numpy()
    hi = np.maximum(closes - 1, cal.next_business(report))
    when = cal.business_between(np.minimum(report + R.integers(5, 46, n), hi), report, hi, R.random(n))
    occ["siu_day"] = np.where(R.random(n) < p_siu, when, NO_DAY)
    return occ


def _reserve_history(f: pd.DataFrame, pays: pd.DataFrame, cal, R: np.random.Generator) -> pd.DataFrame:
    """Every change to each feature's loss reserve (and, for litigated features, expense reserve), with the
    reserve outstanding after it. Returns columns fid, day, rtype, txn, delta, outstanding."""
    n = len(f)
    cvg, U = f.cvg.to_numpy(), f.paid.to_numpy()
    od, cd = f.open_day.to_numpy(), f.close_day.to_numpy()
    at = np.clip(f.day.to_numpy(), 0, cal.horizon)
    trend = np.ones(n)
    for c, k in RESERVE_TREND.items():
        trend = np.where(cvg == c, cal.sev_trend[k][at], trend)
    formula = np.where(f.peril.to_numpy() == "GLASS", GLASS_FORMULA_RESERVE, pd.Series(cvg).map(FORMULA_RESERVE).to_numpy()) * trend
    nominal_amt = pd.Series(cvg).map(NOMINAL_RESERVE).fillna(0).to_numpy() * trend
    nominal = f.nominal.to_numpy().astype(bool)
    mu = pd.Series(cvg).map(lambda k: RESERVE_ERROR[k][0]).to_numpy()
    sg = pd.Series(cvg).map(lambda k: RESERVE_ERROR[k][1]).to_numpy()
    fid = f.fid.to_numpy()
    cap = f["cap"].fillna(np.inf).to_numpy() if "cap" in f else np.full(n, np.inf)
    # before the first close the adjuster is estimating the settlement, not a supplement a later reopening will
    # bring; and the final payment settles the feature, taking its reserve to nothing however long the file takes
    # to close
    main = U - (f.supp.to_numpy() if "supp" in f else 0.0)
    loss = pays[pays.kind == "Loss"]
    final = loss[loss.txn == "Final Payment"].groupby("fid").day.min()
    fin_day = pd.Series(fid).map(final).to_numpy(dtype=float)
    settled = np.where(np.isnan(fin_day), cd, np.minimum(cd, np.nan_to_num(fin_day))).astype(np.int64)

    # reviews: at opening, then on the coverage's review cycle until the settlement (or the first close)
    life = np.maximum(settled - od, 1)
    interval = pd.Series(cvg).map(RESERVE_REVIEW_DAYS).to_numpy()
    m = np.clip(1 + (life - 1) // interval, 1, 24).astype(int)
    i = np.repeat(np.arange(n), m)
    k = np.arange(len(i)) - np.repeat(np.cumsum(m) - m, m)
    day = np.where(k == 0, od[i], np.minimum(od[i] + np.floor(k * interval[i] * R.uniform(0.8, 1.2, len(i))).astype(int),
                                              settled[i] - 1))
    day = np.where(k == 0, day, cal.business_between(day, od[i], settled[i] - 1, R.random(len(i))))      # reviews are done on business days
    eta = R.standard_normal(len(i))
    z = eta.copy()
    rho = RESERVE_PERSISTENCE
    for kk in range(1, int(m.max())):                  # errors persist from one review to the next
        sel = np.flatnonzero(k == kk)
        z[sel] = rho * z[sel - 1] + np.sqrt(1 - rho ** 2) * eta[sel]
    phi = (day - od[i]) / life[i]
    est = np.where(U[i] > 0, main[i] * np.exp((mu[i] + sg[i] * z) * (1 - phi) ** 0.7), formula[i] * np.exp(0.3 * z))
    est = np.where((k == 0) & (U[i] > 0), formula[i] * np.exp(0.3 * z), est)      # formula reserve at first notice
    est = np.where(nominal[i], nominal_amt[i] * np.exp(0.3 * z), est)
    est = np.minimum(est, cap[i])
    parts = [pd.DataFrame(dict(fid=fid[i], day=day, order=0, est=est, pay=0.0,
                               txn=np.where(k == 0, "Initial Reserve", "Reserve Review")))]
    ro = np.flatnonzero(f.reopen_day.to_numpy() > NO_DAY)
    supp = f.supp.to_numpy()[ro]
    parts.append(pd.DataFrame(dict(fid=fid[ro], day=f.reopen_day.to_numpy()[ro], order=0,
                                   est=np.minimum(U[ro] - supp + supp * np.exp(0.3 * R.standard_normal(len(ro))), cap[ro]),
                                   pay=0.0, txn="Reopen")))
    closes = np.r_[cd, f.final_close_day.to_numpy()[ro]]
    parts.append(pd.DataFrame(dict(fid=np.r_[fid, fid[ro]], day=closes, order=2, est=np.nan, pay=0.0, txn="Close")))
    # (order 2: a final payment ends the reserve, and so does the supplemental payment that settles a reopening)
    settles = np.isin(loss.txn.to_numpy(), ["Final Payment", "Supplemental Payment"])
    parts.append(pd.DataFrame(dict(fid=loss.fid, day=loss.day, order=np.where(settles, 2, 1), est=np.nan,
                                   pay=loss.amount, txn="Payment")))
    room = f["room"].fillna(np.inf).to_numpy() if "room" in f else np.full(n, np.inf)
    shared = pd.DataFrame(dict(occ=f.occ.to_numpy(), cvg=cvg, room=room), index=fid)
    out = [_outstanding(pd.concat(parts, ignore_index=True), "Loss", MIN_RESERVE, pd.Series(cap, index=fid),
                        lambda ev, bal, paid: _share_accident_limit(ev, bal, paid, shared, cal))]

    # expense reserve on litigated features: set when the suit is filed, eroded by legal bills, closed with the
    # feature's first close (the legal bills are all paid by then; a reopening pays no further expense)
    li = np.flatnonzero(f.suit_day.to_numpy() > NO_DAY)
    if len(li):
        ep = pays[(pays.kind == "Expense") & pays.fid.isin(fid[li])]
        e_est = f.expense.to_numpy()[li] * np.exp(0.3 * R.standard_normal(len(li)))
        ev = pd.concat([pd.DataFrame(dict(fid=fid[li], day=f.suit_day.to_numpy()[li], order=0, est=e_est, pay=0.0, txn="Initial Reserve")),
                        pd.DataFrame(dict(fid=ep.fid, day=ep.day, order=1, est=np.nan, pay=ep.amount, txn="Payment")),
                        pd.DataFrame(dict(fid=fid[li], day=cd[li], order=2, est=np.nan, pay=0.0, txn="Close"))],
                       ignore_index=True)
        out.append(_outstanding(ev, "Expense", 0))
    return pd.concat(out, ignore_index=True)


def _outstanding(ev: pd.DataFrame, rtype: str, floor: float, cap: pd.Series = None, share=None) -> pd.DataFrame:
    """Turn dated reserve events (estimates, payments, closes) into reserve changes and balances. With `cap` (by
    feature), a balance never exceeds the cap less what has been paid, even after rounding or the floor. `share`,
    given the events and each one's balance and paid to date, returns the events again with any limit shared
    between features applied (and changes it makes to other features added)."""
    ev = ev.sort_values(["fid", "day", "order"], kind="stable").reset_index(drop=True)
    g = ev.groupby("fid")
    paid = g.pay.cumsum().to_numpy()
    est = g.est.ffill().to_numpy()
    is_open = pd.Series(np.where(ev.order == 0, 1.0, np.where(ev.order == 2, 0.0, np.nan))).groupby(ev.fid.to_numpy()).ffill().fillna(0)
    started = ~np.isnan(est)
    bal = np.where((is_open.to_numpy() > 0) & started,
                   np.maximum(np.round((np.nan_to_num(est) - paid) / RESERVE_ROUNDING) * RESERVE_ROUNDING, floor), 0.0)
    if cap is not None:
        left = np.floor(np.maximum(cap.reindex(ev.fid).to_numpy() - paid, 0.0) * 100) / 100
        bal = np.minimum(bal, left)
    if share is not None:
        ev, bal = share(ev, bal, paid)
    prev = pd.Series(bal).groupby(ev.fid.to_numpy()).shift().fillna(0).to_numpy()
    ev = ev.assign(rtype=rtype, delta=bal - prev, outstanding=bal)
    return ev.loc[ev.delta != 0, ["fid", "day", "rtype", "txn", "delta", "outstanding"]]


def _share_accident_limit(ev: pd.DataFrame, bal: np.ndarray, paid: np.ndarray, feat: pd.DataFrame, cal):
    """Keep the case reserves of an accident's claimants within its per-accident limit, using only what is known
    on each day. `ev` holds each feature's loss reserve events in order, `bal` the reserve each sets within the
    feature's own limit and `paid` its payments to date; `feat` (by feature id) gives each feature's accident,
    coverage and the room the coverage's per-accident limit allows. A reserve set during the day takes no more
    than the room the accident's payments and other reserves leave. At the end of each business day on which
    something happened, the adjuster rebalances: if the accident's paid to date plus the reserves wanted would
    exceed the room, the room left after payments is shared among the open reserves in proportion to the
    estimates, in whole dollars; if not, each gets its full estimate back. A change this makes to another
    claimant's reserve is a reserve review that day. Returns the events, with those added, and their balances."""
    f = feat.reindex(ev.fid.to_numpy())
    key = f.groupby(["occ", "cvg"], sort=False).ngroup().to_numpy()          # the accident and coverage
    room = f.room.to_numpy()
    many = (pd.Series(ev.fid.to_numpy()).groupby(key).transform("nunique").to_numpy() > 1) & np.isfinite(room)
    if not many.any():
        return ev, bal
    rows = np.flatnonzero(many)
    sub = pd.DataFrame(dict(row=rows, g=key[rows], fid=ev.fid.to_numpy()[rows], day=ev.day.to_numpy()[rows],
                            order=ev.order.to_numpy()[rows])).sort_values(["g", "day", "order", "fid"], kind="stable")
    sub["pt"] = np.arange(len(sub))                   # position in the accident's sequence of events
    sub["end"] = cal.is_business(sub.day.to_numpy()) & ((sub.g != sub.g.shift(-1)) | (sub.day != sub.day.shift(-1))).to_numpy()
    new_bal = bal.copy()
    added = []                                          # (fid, day, order, pt, balance) of changes made to other claimants
    for _, grp in sub.groupby("g", sort=False):
        lim = float(room[grp.row.iloc[0]])
        want, got, spent = {}, {}, {}                   # each feature's own estimate, its reserve after sharing, paid
        for r, fid, day, order, pt, end in zip(grp.row.to_numpy(), grp.fid.to_numpy(), grp.day.to_numpy(),
                                               grp.order.to_numpy(), grp.pt.to_numpy(), grp.end.to_numpy()):
            want[fid], spent[fid] = float(bal[r]), float(paid[r])
            free = max(lim - sum(spent.values()), 0.0)
            if end:
                total = sum(want.values())
                target = dict(want) if total <= free else {k: float(np.floor(w * free / total + 1e-7)) for k, w in want.items()}
                added += [(k, day, order, pt, t) for k, t in target.items() if k != fid and t != got.get(k, 0.0)]
                got = target
            else:
                got[fid] = min(want[fid], max(float(np.floor(free - sum(v for k, v in got.items() if k != fid) + 1e-7)), 0.0))
            new_bal[r] = got[fid]
    if not added:
        return ev, new_bal
    pt = np.zeros(len(ev), dtype=np.int64)
    pt[sub.row.to_numpy()] = sub.pt.to_numpy()
    extra = pd.DataFrame(added, columns=["fid", "day", "order", "pt", "bal"]).assign(txn="Reserve Review", est=np.nan, pay=0.0)
    both = pd.concat([ev.assign(bal=new_bal, pt=pt), extra], ignore_index=True)
    both = both.sort_values(["fid", "day", "order", "pt"], kind="stable").reset_index(drop=True)
    return both.drop(columns=["bal", "pt"]), both.bal.to_numpy()


def first_notice(cal, occ: pd.DataFrame, R: np.random.Generator) -> np.ndarray:
    """The day the company first hears of each loss: a few days after it by cause, a few much later. First notice
    comes in every day (app, website, call centre), but much of a weekend's or a holiday's is held over to the next
    business day. A physical damage coverage is opened on this day (OPEN_LAG), so it is the claim's report day when
    the claim has one."""
    lag = np.floor(R.exponential(occ.peril.map(REPORT_LAG_MEAN).to_numpy()))
    lag += (R.random(len(occ)) < 0.03) * np.floor(R.exponential(45, len(occ)))
    return cal.intake_day(occ.day.to_numpy() + lag.astype(int), R.random(len(occ)))


def _open_lag(cvg: np.ndarray, R: np.random.Generator) -> np.ndarray:
    """Extra days from the claim's first notice until each coverage is opened."""
    n = len(cvg)
    spec = np.array([OPEN_LAG.get(c, (1.0, 1.0, 0.0, 1.0)) for c in cvg]).reshape(n, 4)
    u = R.random(n)
    mid = np.floor(R.exponential(spec[:, 1]))
    tail = np.floor(spec[:, 3] * np.exp(OPEN_LAG_SIGMA * R.standard_normal(n)))
    return np.where(u < spec[:, 0], 0, np.where(u < 1 - spec[:, 2], mid, tail)).astype(int)


def _chargeable(f: pd.DataFrame, pays: pd.DataFrame) -> pd.Series:
    """Day each at-fault occurrence's cumulative PD, BI and collision loss payments reach the threshold."""
    m = f.at_fault.to_numpy().astype(bool) & np.isin(f.cvg.to_numpy(), ["PD", "BI", "COLL"])
    return chargeable_days(pays[pays.kind == "Loss"], f.loc[m, ["fid", "occ"]])


def chargeable_days(loss_pays: pd.DataFrame, fid_occ: pd.DataFrame, threshold: float = C.CHARGEABLE_THRESHOLD) -> pd.Series:
    """For each occurrence, the first day its loss payments (on the features in fid_occ) add up to the
    threshold. Only payments up to that day matter, so a later settlement cannot change it."""
    p = loss_pays.merge(fid_occ, on="fid").sort_values(["occ", "day", "seq"], kind="stable")
    cum = p.groupby("occ").amount.cumsum()
    return p[cum.to_numpy() >= threshold - 0.005].groupby("occ").day.min()


def _legs(f_idx, day, cents, txn, role="", ref=-1) -> pd.DataFrame:
    """Payment legs of features f_idx. role marks who a leg is for when that differs from the feature's usual
    payee (a lienholder); ref numbers an interim payment within its batch so a void and its reissue can point
    back to the payment they replace."""
    return pd.DataFrame(dict(i=f_idx, day=np.asarray(day).astype(int), cents=np.asarray(cents).astype(np.int64), txn=txn,
                             role=role, ref=ref))


def _schedule(f: pd.DataFrame, R: np.random.Generator, cal):
    """Every loss payment, expense payment and recovery of each feature, through to its final close.
    Adds reopen_day and final_close_day to f. Returns (payments, f). Payments are issued, files reopened and
    closed, and recoveries banked on business days (cal.business_between keeps each inside its feature's dates)."""
    n = len(f)
    cvg, peril = f.cvg.to_numpy(), f.peril.to_numpy()
    total = f.total.to_numpy().astype(bool)
    od, cd = f.open_day.to_numpy(), f.close_day.to_numpy()
    dur = cd - od
    P = np.round(f.paid.to_numpy() * 100).astype(np.int64)          # ultimate paid, in cents
    has = P > 0
    injury = np.isin(cvg, ["BI", "UM"])

    # ---- reopening: a closed feature reopens for a supplement carved out of the ultimate
    reopen = has & (R.random(n) < pd.Series(cvg).map(REOPEN_P).to_numpy())
    reopen_day = cal.spread_business(cd + 20 + np.floor(R.exponential(75, n)).astype(int), R.random(n))
    supp_day = cal.spread_business(reopen_day + 3 + np.floor(R.exponential(20, n)).astype(int), R.random(n))
    final_close = cal.spread_business(supp_day + np.where(R.random(n) < 0.5, 0, 1 + np.floor(R.exponential(7, n))).astype(int), R.random(n))
    supp = np.where(reopen, np.maximum(np.round(P * R.uniform(0.05, 0.25, n)), 100), 0).astype(np.int64)
    supp = np.where(injury, np.maximum(supp // 10_000, 1) * 10_000, supp)       # injury supplements are round amounts
    reopen &= supp < P
    supp = np.where(reopen, supp, 0)
    main = P - supp                                                  # paid before the first close

    # ---- the main settlement: day and shape
    lag_long = np.where(injury, 12, 6)
    final_day = cd - np.where(R.random(n) < np.where(injury, 0.5, 0.55), 0,
                              np.minimum(1 + np.floor(R.exponential(lag_long)), dur)).astype(int)
    lo = np.maximum(od, f["pay_from"].to_numpy()) if "pay_from" in f else od     # a rental only once returned
    final_day = cal.business_between(np.maximum(final_day, lo), lo, cd, R.random(n))
    u1, u2 = R.random(n), R.random(n)
    p1 = pd.Series(cvg).map(lambda c: INTERIM_P.get(c, (0.0, 0.0))[0]).to_numpy()
    p2 = pd.Series(cvg).map(lambda c: INTERIM_P.get(c, (0.0, 0.0))[1]).to_numpy()
    k = (u1 < p1).astype(int) + ((u1 < p1) & (u2 < p2))
    k = np.where(cvg == "MED", np.minimum(R.poisson(MED_BILLS_MEAN, n), 6), k)
    k = np.where(total | (peril == "GLASS"), 0, k)
    k = np.where(has, np.minimum(k, np.maximum(main // 5_000 - 1, 0)), 0)      # at least ~$50 a payment
    # a total loss on a financed or leased car pays off the lender (the ownership at the loss, from the vehicle)
    loan = f["ownership"].to_numpy() if "ownership" in f else np.full(n, "Owned")
    R.random(n)        # (once drew whether a lender was paid; still drawn so the draws after it do not move)
    split = has & total & (loan != "Owned")
    leased = split & (loan == "Leased")
    fees = has & total & (R.random(n) < TOTAL_LOSS_FEES_P) & (final_day - od >= 10) & (main >= 50_000)

    # interim payments: physical damage is paid early on the estimate, injury advances mid-way, bills throughout
    i = np.repeat(np.arange(n), k)
    pos = np.arange(len(i)) - np.repeat(np.cumsum(k) - k, k)
    c_i = cvg[i]
    t = np.select([np.isin(c_i, ["COLL", "COMP"]), c_i == "PD", np.isin(c_i, ["BI", "UM"])],
                  [R.random(len(i)) ** 2 * 0.9, R.uniform(0.05, 0.9, len(i)), R.uniform(0.15, 0.6, len(i))],
                  default=R.random(len(i)))
    order = np.lexsort((t, i))
    t = t[order]                                                     # times ascend within each feature
    settle_day = np.where(fees, final_day - R.integers(7, 31, n).clip(max=np.maximum(final_day - od, 1)), final_day)
    settle_day = cal.business_between(settle_day, od, final_day, R.random(n))
    span = np.maximum(settle_day - od, 0)
    inspect = np.where(np.isin(c_i, ["PD", "COLL", "COMP"]), np.minimum(3, span[i]), 0)   # paid after an appraisal
    interim_day = cal.business_between(od[i] + inspect + np.floor(t * (span[i] - inspect)).astype(int), od[i], settle_day[i], R.random(len(i)))
    w_int = np.select([np.isin(c_i, ["COLL", "COMP"]) & (pos == 0), np.isin(c_i, ["COLL", "COMP"]), c_i == "PD",
                       np.isin(c_i, ["BI", "UM"])], [4.0, 1.0, 0.5, 0.6], default=1.5)
    w_fin = np.select([np.isin(cvg, ["COLL", "COMP"]), cvg == "PD", injury], [1.0, 3.0, 3.0], default=1.5)
    g_int = R.gamma(w_int)
    g_fin = R.gamma(w_fin)
    g_fee = np.where(fees, R.uniform(0.02, 0.06, n), 0.0)
    tot_g = np.bincount(i, g_int, n) + g_fin                          # shares are Dirichlet; the final payment takes the rounding
    int_cents = np.floor(main[i] * g_int / tot_g[i] * (1 - g_fee[i])).astype(np.int64)
    int_cents = np.where(injury[i], int_cents // 10_000 * 10_000, int_cents)    # an injury advance is a round amount
    fee_cents = np.where(fees, np.floor(main * g_fee), 0).astype(np.int64)
    fin_cents = main - np.bincount(i, int_cents, n).astype(np.int64) - fee_cents
    # the lender's payoff and the owner's balance go out on the settlement day. The payoff is the loan balance,
    # never more than the settlement; a lessor owns the car and takes all of it. When the lender takes the whole
    # settlement its payment is the final one (unless title and fees follow)
    owed = np.where(loan == "Leased", 1.0, np.minimum(R.uniform(*LOAN_PAYOFF_SHARE, n), 1.0))
    lien = np.where(split, np.minimum(np.ceil(fin_cents * owed), fin_cents), 0).astype(np.int64)    # at least a cent
    lien_txn = np.where(split & (lien == fin_cents) & ~fees, "Final Payment", "Partial Payment")

    legs = [
        _legs(i, interim_day, int_cents, "Partial Payment", ref=np.arange(len(i))),
        _legs(np.flatnonzero(split), settle_day[split], lien[split], lien_txn[split], role="lien"),
        _legs(np.flatnonzero(has), settle_day[has], (fin_cents - lien)[has],
              np.where(fees[has], "Partial Payment", "Final Payment")),
        # a leased car's whole settlement goes to the leasing company: its title and fees and any supplement too
        _legs(np.flatnonzero(fees), final_day[fees], fee_cents[fees], "Final Payment",
              role=np.where(leased[fees], "lien", "")),
        _legs(np.flatnonzero(reopen), supp_day[reopen], supp[reopen], "Supplemental Payment",
              role=np.where(leased[reopen], "lien", "")),
    ]
    # voided and reissued interim payments (net zero)
    vd = R.random(len(i)) < VOID_P
    void_day = np.minimum(interim_day + 2 + np.floor(R.exponential(5, len(i))).astype(int), settle_day[i])
    void_day = cal.business_between(void_day, interim_day, settle_day[i], R.random(len(i)))
    legs += [_legs(i[vd], void_day[vd], -int_cents[vd], "Void", ref=np.flatnonzero(vd)),
             _legs(i[vd], void_day[vd], int_cents[vd], "Reissue", ref=np.flatnonzero(vd))]
    loss = pd.concat(legs, ignore_index=True)
    loss = loss[loss.cents != 0]
    loss["kind"] = "Loss"

    # expenses: appraisal fees early on physical damage, others at close, litigation costs as the suit runs
    exp_c = np.round(f.expense.to_numpy() * 100).astype(np.int64)
    lit = f.suit_day.to_numpy() > NO_DAY
    early = np.isin(cvg, ["PD", "COLL", "COMP"])
    e_day = cal.business_between(np.where(early, od + np.floor(R.uniform(0.05, 0.6, n) * dur).astype(int), cd), od, cd, R.random(n))
    e_legs = [_legs(np.flatnonzero((exp_c > 0) & ~lit), e_day[(exp_c > 0) & ~lit], exp_c[(exp_c > 0) & ~lit], "")]
    li = np.flatnonzero(lit & (exp_c > 0))
    done = np.zeros(len(li), dtype=np.int64)
    suit = f.suit_day.to_numpy()[li]
    for j, (share, when) in enumerate(((0.25, 0.15), (0.35, 0.55), (0.40, 1.0))):      # legal bills as the suit runs
        amt = np.round(exp_c[li] * share).astype(np.int64) if j < 2 else exp_c[li] - done
        done += amt
        e_legs.append(_legs(li, cal.business_between(suit + ((cd[li] - suit) * when).astype(int), suit, cd[li], R.random(len(li))), amt, ""))
    expense = pd.concat(e_legs, ignore_index=True)
    expense["txn"] = np.where(np.isin(cvg[expense.i.to_numpy()], list(DCC_COVERAGES)), "DCC Expense", "A&O Expense")
    expense["kind"] = "Expense"

    salv = np.round(f.salvage.to_numpy() * 100).astype(np.int64)
    subro = np.round(f.subro.to_numpy() * 100).astype(np.int64)
    # subrogation recovers what has been paid: the part for the payments to the first close (never more than they
    # come to, less the salvage) after that close, and a reopening's share after its supplement is paid. The other
    # insurer repays a claim it is shown; the total recovered is the same
    # the wreck is sold after the settlement, or, if it would fetch more than had been paid before a reopening, once
    # the reopening's supplement is paid
    late_sale = reopen & (salv > main)
    salvage_day = cal.spread_business(np.where(late_sale, supp_day, cd) + R.integers(20, 70, n), R.random(n))
    lag = np.exp(np.log(110) + 0.6 * R.standard_normal(n)).astype(int)
    sub_main = np.minimum(np.floor(subro * main / np.maximum(P, 1)).astype(np.int64), np.maximum(main - salv, 0))
    sub_main = np.where(reopen, sub_main, subro)
    sub_supp = subro - sub_main
    u_sub = R.random(n)
    # the other insurer repays one claim at once: the repair, the rental and the tow of a crash come back together,
    # after the last of them has closed (each reopening's share still after its own supplement)
    occ_ = f.occ.to_numpy()
    anchor = pd.Series(np.where(sub_main > 0, cd, NO_DAY)).groupby(occ_).transform("max").to_numpy()
    first_ = lambda x: pd.Series(x).groupby(occ_).transform("first").to_numpy()
    sub_day = cal.spread_business(anchor + first_(lag), first_(u_sub))
    rec = pd.concat([
        _legs(np.flatnonzero(salv > 0), salvage_day[salv > 0], -salv[salv > 0], "Recovery").assign(kind="Salvage Recovery"),
        _legs(np.flatnonzero(sub_main > 0), sub_day[sub_main > 0],
              -sub_main[sub_main > 0], "Recovery").assign(kind="Subrogation Recovery"),
        _legs(np.flatnonzero(sub_supp > 0), cal.spread_business(supp_day + lag, u_sub)[sub_supp > 0],
              -sub_supp[sub_supp > 0], "Recovery").assign(kind="Subrogation Recovery")], ignore_index=True)

    pays = pd.concat([loss, expense, rec], ignore_index=True)
    pays["fid"] = f.fid.to_numpy()[pays.i.to_numpy()]
    pays["amount"] = pays.cents / 100
    pays = pays.sort_values(["fid", "day", "kind", "cents"], kind="stable").reset_index(drop=True)
    pays["seq"] = np.arange(len(pays))
    f = f.assign(paid=P / 100, reopen_day=np.where(reopen, reopen_day, NO_DAY), final_close_day=np.where(reopen, final_close, cd),
                 supp=supp / 100)
    return pays[["fid", "day", "kind", "txn", "amount", "seq", "role", "ref"]], f


def develop(cfg: C.Config, ref, res) -> dict:
    """Cut the developed claims off at the valuation date."""
    cal = ref.cal
    V = cal.valuation_day
    occ, f, pay_all = res.occ.copy(), res.feat.copy().reset_index(drop=True), res.pays
    # a claim from before the start (the warm-up) is in the extract only if something happened on it on or after the
    # start date: still open then, reported later, or paid, recovered or re-reserved later. Claims settled and
    # closed before the start are not
    acts = [pay_all[["fid", "day"]], res.reserves[["fid", "day"]], f[["fid", "final_close_day"]].rename(columns={"final_close_day": "day"})]
    last = pd.concat(acts, ignore_index=True).groupby("fid").day.max()
    over = f.assign(last=f.fid.map(last).to_numpy()).groupby("occ")["last"].max()
    f = f[~f.occ.isin(over.index[over < 0])].reset_index(drop=True)
    # (an at-fault one stays on the driver's record: tables.py lists it as a company claim before the extract)
    settled = occ[~occ.occ.isin(f.occ) & (occ.chargeable_day > NO_DAY) & (occ.drv >= 0)]
    occ, pay_all = occ[occ.occ.isin(f.occ)], pay_all[pay_all.fid.isin(f.fid)]
    n = len(f)
    pos = pd.Series(np.arange(n), index=f.fid.to_numpy())

    known = pay_all[pay_all.day <= V]
    idx = pos.reindex(known.fid).to_numpy()
    tot = lambda m: np.round(np.bincount(idx[m], known.amount.to_numpy()[m], n), 2)
    kind, txn = known.kind.to_numpy(), known.txn.to_numpy()
    f["paid_loss"], f["paid_expense"] = tot(kind == "Loss"), tot(kind == "Expense")
    f["paid_dcc"], f["paid_ao"] = tot(txn == "DCC Expense"), tot(txn == "A&O Expense")
    f["salvage_rec"], f["subro_rec"] = np.abs(tot(kind == "Salvage Recovery")), np.abs(tot(kind == "Subrogation Recovery"))
    f["reported"] = f.open_day <= V
    reopened = (f.reopen_day > NO_DAY) & (f.reopen_day <= V)
    f["reopened"] = reopened
    f["closed"] = np.where(reopened, f.final_close_day <= V, f.close_day <= V)
    f["status_close_day"] = np.where(reopened, f.final_close_day, f.close_day)
    # case and expense reserves: the balance after the last reserve change on or before the valuation date
    hist = res.reserves[res.reserves.day <= V]
    last = hist.sort_values(["fid", "rtype", "day"], kind="stable").groupby(["fid", "rtype"]).outstanding.last()
    f["case_reserve"] = last.xs("Loss", level="rtype").reindex(f.fid).fillna(0).to_numpy() if len(last) else 0.0
    f["expense_reserve"] = (last.xs("Expense", level="rtype").reindex(f.fid).fillna(0).to_numpy()
                            if "Expense" in last.index.get_level_values("rtype") else 0.0)
    f["litigated"] = (f.suit_day > NO_DAY) & (f.suit_day <= V)          # a suit not yet filed is not known
    f["attorney"] = f.attorney & (f.attorney_day <= V)

    rep = f[f.reported].copy()
    occ["report_day"] = occ.occ.map(rep.groupby("occ").open_day.min())       # first notice the company has
    claims = occ[occ.report_day.notna()].copy()
    claims["report_day"] = claims.report_day.astype(int)
    claims = claims.sort_values(["report_day", "occ"], kind="stable").reset_index(drop=True)
    claims["claim_id"] = np.arange(1, len(claims) + 1)
    claims["chargeable"] = (claims.chargeable_day > NO_DAY) & (claims.chargeable_day <= V)
    claims["siu_day"] = np.where(claims.siu_day <= V, claims.siu_day, NO_DAY)
    rep["claim_id"] = rep.occ.map(claims.set_index("occ").claim_id)
    order = {k: i for i, k in enumerate(C.COVERAGES)}
    rep["cvg_order"] = rep.cvg.map(order)
    rep = rep.sort_values(["claim_id", "cvg_order", "claimant"], kind="stable").reset_index(drop=True)
    rep["feature_id"] = np.arange(1, len(rep) + 1)

    payments = known.merge(rep[["fid", "feature_id", "claim_id"]], on="fid")
    payments["kind_order"] = payments.kind.map({"Loss": 0, "Expense": 1, "Salvage Recovery": 2, "Subrogation Recovery": 3})
    payments = payments.sort_values(["day", "feature_id", "kind_order", "seq"], kind="stable").reset_index(drop=True)
    payments["payment_id"] = np.arange(1, len(payments) + 1)
    reserves = hist.merge(rep[["fid", "feature_id", "claim_id"]], on="fid")
    reserves["rtype_order"] = (reserves.rtype == "Expense").astype(int)
    reserves = reserves.sort_values(["day", "feature_id", "rtype_order"], kind="stable").reset_index(drop=True)
    reserves["reserve_id"] = np.arange(1, len(reserves) + 1)

    unreported = f[~f.reported].merge(occ[["occ", "pol", "veh", "row"]], on="occ")
    return dict(claims=claims, features=rep, payments=payments, reserves=reserves, unreported=unreported,
                settled_before=settled[["drv", "day", "chargeable_day"]])
