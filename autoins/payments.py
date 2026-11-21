"""Who handles each claim and who each claim payment goes to.

The claim simulation (claims.py) decides what is paid and when. This module adds what a claim system and a
bank record around those payments, without changing an amount or a date:

* Employees. Each claim office has adjusters' desks, a supervisor, and above them a claims manager. People
  are hired and leave over time; a claim belongs to a desk, so when an adjuster leaves, whoever takes the desk
  takes the files. Every position has a payment authority.
* Vendors. Body shops, glass, rental and towing companies, medical providers, appraisers, defence and
  plaintiffs' law firms, salvage auctions, lienholders and other insurers: fictional organisations, the local
  ones placed in the area's ZIP codes, with a few large ones taking most of the business as in real vendor
  files.
* Payment detail. Each payment's payee (the insured, a claimant, a claimant jointly with an attorney, a
  vendor, a lienholder, another insurer), how it was paid (cheque or electronic transfer), a cheque number
  from one unbroken sequence, when it cleared the bank (or that it is still outstanding at the valuation
  date, or was voided), and who approved it: the adjuster on the file if the amount is within their authority,
  otherwise the supervisor or the claims manager.

Every share and amount here is ASSUMED. Names are made up; any resemblance to a real business is accidental.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from . import config as C
from .claims import NO_DAY
from .refdata import stream

# ------------------------------------------------------------------------------------------- staffing
CASELOAD = {1: 230, 2: 260, 3: 110, 4: 750, 5: 220, 6: 240}      # new claims a year one adjuster handles, by office
SENIOR_SHARE = 0.35
AUTHORITY = {"Claims Adjuster": 10_000, "Senior Claims Adjuster": 25_000, "Claims Supervisor": 75_000,
             "Claims Manager": 1_000_000, "SIU Investigator": 0}
GLASS_DESK_AUTHORITY = 2_500
TURNOVER = {"Claims Adjuster": 0.12, "Senior Claims Adjuster": 0.08, "Claims Supervisor": 0.06, "Claims Manager": 0.04,
            "SIU Investigator": 0.07}                               # share leaving each year
VACANCY_DAYS = (5, 45)                                              # a desk stays empty this long before it is filled

# ------------------------------------------------------------------------------------------- vendors
WORDS = ["Lakeland", "Prairie", "Midwest", "Heartland", "Great Lakes", "Tri-State", "Windy City", "Fox Valley", "North Shore",
         "Blackhawk", "Illini", "Calumet", "Riverside", "Parkside", "Cornerstone", "Keystone", "Summit", "Beacon", "Liberty",
         "Premier", "Reliable", "Precision", "Allied", "Central", "Metro", "Suburban", "Lakeshore", "Crosstown", "Heritage",
         "Capitol", "Pioneer", "Sterling", "Guardian", "Frontier", "Compass", "Anchor", "Evergreen", "Meridian", "Union"]
VENDOR_TYPES = {
    # type: (how many, local to a ZIP, concentration of business (higher = a few vendors take most), name patterns)
    "Body Shop": (150, True, 0.9, ["{s}'s Auto Body", "{c} Collision Center", "{w} Auto Rebuilders", "{s} & Sons Collision", "{w} Collision Repair"]),
    "Glass Vendor": (10, True, 2.0, ["{w} Auto Glass", "{w} Glass & Mirror", "{c} Windshield Repair"]),
    "Rental Company": (6, False, 2.2, ["{w} Car Rental", "{w} Rent-A-Car", "{w} Car & Truck Rental"]),
    "Towing Company": (60, True, 0.8, ["{s} Towing", "{c} Towing & Recovery", "{w} Towing Service"]),
    "Medical Provider": (220, True, 1.1, ["{c} Community Medical Group", "{s} Chiropractic", "{c} Physical Therapy Associates",
                                           "{w} Orthopedics", "{w} Health Clinic of {c}", "{w} Imaging Center"]),
    "Independent Appraiser": (10, False, 1.5, ["{w} Appraisal Service", "{w} Claims Services", "{s} Adjusting Company"]),
    "Medical Review Service": (6, False, 1.5, ["{w} Medical Review", "{w} Records Retrieval", "{w} Medical Examiners"]),
    "Defense Law Firm": (14, False, 1.3, ["{s}, {s2} & {s3} LLP", "{s} & {s2} LLC", "{s} {s2} Attorneys at Law"]),
    "Plaintiff Law Firm": (150, False, 1.4, ["Law Offices of {f} {s}", "{s} & {s2}, P.C.", "{s} Injury Law", "{s} Law Group"]),
    "Salvage Auction": (3, False, 1.0, ["{w} Auto Auction", "{w} Salvage Pool", "{w} Vehicle Auctions"]),
    "Lienholder": (30, False, 1.6, ["{w} Federal Credit Union", "{w} Bank & Trust", "{w} Auto Finance", "First {w} Savings Bank"]),
    "Other Insurer": (25, False, 1.7, ["{w} Mutual Insurance Company", "{w} Casualty Company", "{w} Fire & Casualty", "{w} Indemnity Insurance"]),
}
NETWORK_SHARE = {"Body Shop": 0.35, "Glass Vendor": 0.6}             # vendors in the company's repair network
OUT_OF_AREA = [("Columbus", "OH"), ("Indianapolis", "IN"), ("Milwaukee", "WI"), ("Des Moines", "IA"), ("St. Louis", "MO"),
               ("Springfield", "IL"), ("Chicago", "IL"), ("Chicago", "IL")]
LOCAL_REACH_MILES = 5.0                                             # a claimant uses a shop or provider this near

# ------------------------------------------------------------------------------------------- payees
# share of a coverage's payments made to a vendor rather than to the person (first-party physical damage is
# often paid straight to the shop; glass almost always to the glass company)
VENDOR_SHARE = {"COLL": 0.55, "COMP": 0.50, "GLASS": 0.85, "MED": 0.60, "RENT": 0.70, "TOW": 0.50}
PD_PAYEE = {"Claimant": 0.45, "Vendor": 0.20, "Other Insurer": 0.35}  # the other party, their body shop, their insurer
EFT_SHARE = {"Vendor": 0.80, "Lienholder": 0.70, "Other Insurer": 0.60, "Insured": (0.35, 0.60), "Claimant": 0.12,
             "Claimant and Attorney": 0.05}                         # insureds: rising from the first to the last year
CLEARING_DAYS = {"EFT": (1, 2), "Vendor": (3, 8), "Lienholder": (3, 9), "Other Insurer": (4, 12), "Insured": (4, 20),
                 "Claimant": (4, 25), "Claimant and Attorney": (3, 12)}   # business days, low to high (cheques)
NEVER_CASHED_P = 0.004                                              # cheques to people that are simply never cashed
FIRST_CHECK_NUMBER = 3_418_207


def _people(ref, r: np.random.Generator, zi: np.ndarray, birth_year: np.ndarray):
    """First name, surname and sex for people living in ZIPs zi (names.py: realistic for the place)."""
    ns = ref.names
    group = ns.draw_group(r, ns.zip_mix(ref.zips.iloc[zi]))
    male = r.random(len(zi)) < 0.5
    return ns.first_name(r, group, male, birth_year), ns.surname(r, group), group


def employees(cfg: C.Config, cal, ref, claims_by_office: pd.Series) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Returns (employee, desks). employee: one row per person, with the desk held and the days it was held
    (end -1: still there). desks: one row per desk (desk, office, title)."""
    R = stream(cfg.seed, "employees")
    years = max((cal.valuation_day + 1) / 365.25, 0.5)
    desks = []
    for office, _, _ in C.BRANCHES:
        n = max(2, int(np.ceil(claims_by_office.get(office, 0) / years / CASELOAD[office])))
        senior = int(round(n * SENIOR_SHARE))
        desks += [(office, "Senior Claims Adjuster" if i < senior else "Claims Adjuster") for i in range(n)]
        desks.append((office, "Claims Supervisor"))
    desks += [(3, "SIU Investigator"), (3, "SIU Investigator"), (0, "Claims Manager")]      # office 0: head office
    desks = pd.DataFrame(desks, columns=["office", "title"]).assign(desk=lambda d: np.arange(len(d)))
    rows = []
    for desk, office, title in zip(desks.desk, desks.office, desks.title):
        start, first = -int(R.integers(200, 6_000)), True
        while True:
            stay = int(R.exponential(365.25 / TURNOVER[title]))
            end = (0 if first else start) + stay              # the first holder was already there on day 0
            left = end <= cal.valuation_day
            rows.append((desk, office, title, start, end if left else -1))
            if not left:
                break
            # the manager's desk is never empty; others wait for a hire
            start, first = end + (0 if title == "Claims Manager" else int(R.integers(*VACANCY_DAYS))), False
    e = pd.DataFrame(rows, columns=["desk", "office", "title", "start", "end"])
    e = e.sort_values(["start", "desk"], kind="stable").reset_index(drop=True)
    e["emp"] = np.arange(len(e))
    zi = R.choice(len(ref.zips), len(e), p=(ref.zips.population / ref.zips.population.sum()).to_numpy())
    age = R.integers(24, 58, len(e))
    e["first_name"], e["last_name"], _ = _people(ref, R, zi, np.floor(cal.year_frac(e.start.to_numpy())).astype(int) - age)
    e["authority"] = np.where((e.office == 4) & e.title.str.contains("Adjuster"), GLASS_DESK_AUTHORITY, e.title.map(AUTHORITY))
    e["number"] = [f"E{x:05d}" for x in 10_000 + np.cumsum(R.integers(3, 60, len(e)))]
    return e, desks


class Roster:
    """Who holds each desk on each day."""

    def __init__(self, emp: pd.DataFrame, desks: pd.DataFrame) -> None:
        e = emp.sort_values(["desk", "start"], kind="stable")
        self.desk, self.start, self.end, self.emp = (e[c].to_numpy() for c in ("desk", "start", "end", "emp"))
        self.key = self.desk * 10 ** 7 + self.start + 10 ** 6
        self.authority = emp.set_index("emp").authority.to_numpy()
        self.supervisor = desks[desks.title == "Claims Supervisor"].set_index("office").desk
        self.manager = int(desks.desk[desks.title == "Claims Manager"].iloc[0])

    def holder(self, desk, day) -> np.ndarray:
        """The employee at `desk` on `day`, or -1 while the desk is empty."""
        desk, day = np.asarray(desk, dtype=np.int64), np.asarray(day, dtype=np.int64)
        j = np.searchsorted(self.key, desk * 10 ** 7 + day + 10 ** 6, "right") - 1
        j = np.clip(j, 0, len(self.key) - 1)
        ok = (self.desk[j] == desk) & (self.start[j] <= day) & ((self.end[j] < 0) | (day < self.end[j]))
        return np.where(ok, self.emp[j], -1)

    def handler(self, desk, office, day) -> np.ndarray:
        """Who works a file on `day`: the adjuster at its desk, the office's supervisor while the desk is empty,
        the claims manager if the supervisor's desk is empty too."""
        h = self.holder(desk, day)
        sup = self.holder(self.supervisor.reindex(office).to_numpy(), day)
        mgr = self.holder(np.full(len(h), self.manager), day)
        return np.where(h >= 0, h, np.where(sup >= 0, sup, mgr))

    def approver(self, desk, office, day, amount) -> np.ndarray:
        """Who approves a payment: the handler if it is within their authority, else the supervisor, else the
        claims manager."""
        h = self.handler(desk, office, day)
        sup = self.holder(self.supervisor.reindex(office).to_numpy(), day)
        mgr = self.holder(np.full(len(h), self.manager), day)
        amount = np.abs(np.asarray(amount, dtype=float))
        out = np.where(amount <= self.authority[h], h, np.where((sup >= 0) & (amount <= self.authority[np.maximum(sup, 0)]), sup, mgr))
        return out


def vendors(cfg: C.Config, ref) -> pd.DataFrame:
    """The vendor file: one row per organisation the company pays or collects from."""
    R = stream(cfg.seed, "vendors")
    z = ref.zips
    pz = (z.population / z.population.sum()).to_numpy()
    rows, used = [], set()
    for vtype, (count, local, conc, patterns) in VENDOR_TYPES.items():
        zi = R.choice(len(z), count, p=pz) if local else np.full(count, -1)
        _, s1, _ = _people(ref, R, R.choice(len(z), count, p=pz), np.full(count, 1970))
        first, s2, _ = _people(ref, R, R.choice(len(z), count, p=pz), np.full(count, 1970))
        _, s3, _ = _people(ref, R, R.choice(len(z), count, p=pz), np.full(count, 1970))
        size = R.pareto(1.0 / conc if conc > 1 else 3.0, count) + 0.3 if conc > 1 else np.exp(R.normal(0, conc, count))
        for i in range(count):
            city = z.city.iloc[zi[i]] if local else R.choice(WORDS)
            for attempt in range(50):
                name = patterns[int(R.integers(len(patterns)))].format(
                    s=str(s1[i]).title(), s2=str(s2[i]).title(), s3=str(s3[i]).title(), f=str(first[i]).title(),
                    c=city, w=WORDS[int(R.integers(len(WORDS)))])
                if name not in used:
                    break
            else:
                name = f"{name} {i + 1}"
            used.add(name)
            where = (z.city.iloc[zi[i]], "IL", z.zip.iloc[zi[i]]) if local else (*OUT_OF_AREA[int(R.integers(len(OUT_OF_AREA)))], "")
            rows.append(dict(vendor_type=vtype, name=name, zi=int(zi[i]), city=where[0], state=where[1], zip=where[2],
                             size=float(size[i]), network=bool(R.random() < NETWORK_SHARE.get(vtype, 0.0))))
    v = pd.DataFrame(rows)
    v["size"] = v["size"] * np.where(v.network, 3.0, 1.0)             # network shops get the steered work
    v["vendor"] = np.arange(len(v))
    v["number"] = [f"V{x:06d}" for x in 100_000 + np.cumsum(R.integers(1, 40, len(v)))]
    return v


def _pick_vendor(v: pd.DataFrame, vtype: str, zi: np.ndarray, ref, r: np.random.Generator) -> np.ndarray:
    """A vendor of the given type for each of len(zi) jobs: by size, and for local trades by distance from zi."""
    c = v[v.vendor_type == vtype]
    w = np.tile(c["size"].to_numpy(), (len(zi), 1))
    if (c.zi >= 0).all() and len(zi):
        z = ref.zips
        lat, lon = z.lat.to_numpy(), z.lon.to_numpy()
        dist = 69 * np.hypot(lat[zi, None] - lat[c.zi.to_numpy()][None, :], (lon[zi, None] - lon[c.zi.to_numpy()][None, :]) * 0.745)
        w = w * np.exp(-dist / LOCAL_REACH_MILES) + 1e-9
    cum = np.cumsum(w, axis=1)
    k = (r.random(len(zi))[:, None] * cum[:, -1:] > cum).sum(axis=1).clip(0, len(c) - 1)
    return c.vendor.to_numpy()[k]


def details(cfg: C.Config, cal, ref, pays: pd.DataFrame, feats: pd.DataFrame, claims: pd.DataFrame, office: np.ndarray,
            claim_zi: np.ndarray, insured_name: np.ndarray, close_day: np.ndarray, emp: pd.DataFrame, desks: pd.DataFrame,
            vend: pd.DataFrame) -> tuple[dict, np.ndarray]:
    """Payee, method, cheque number, clearing and approval for every payment row of `pays` (as cut off at the
    valuation date and sorted for the claim_payment table), and each claim's current adjuster.

    feats: the reported features (feature_id, claim_id, cvg, claimant, attorney, attorney_day, litigated, total).
    claims: the reported claims in claim_id order (peril, veh), with `office`, `claim_zi` (ZIP index at the loss)
    and `close_day` (the claim's close, or beyond the horizon if open) aligned to them. `insured_name` is aligned to
    the payments: the policy's named insured on each payment's date, so a later change of named insured leaves an
    earlier payment alone. Returns (columns for the payment table, adjuster employee index per claim)."""
    R = stream(cfg.seed, "payment detail")
    V = cal.valuation_day
    nC, nF = len(claims), len(feats)
    roster = Roster(emp, desks)

    # ---- each claim's desk, and who holds it now
    desk = np.zeros(nC, dtype=np.int64)
    adj = desks[desks.title.str.contains("Adjuster")]
    for o, d in adj.groupby("office"):
        m = office == o
        desk[m] = d.desk.to_numpy()[R.integers(0, len(d), m.sum())]
    adjuster = roster.handler(desk, office, np.minimum(close_day, V))

    # ---- each feature's usual payee
    f = feats.reset_index(drop=True)
    ci = f.claim_id.to_numpy() - 1                       # claims are numbered 1..n in order
    cvg, peril = f.cvg.to_numpy(), claims.peril.to_numpy()[ci]
    zi = claim_zi[ci]
    u = R.random(nF)
    share = np.select([cvg == "COLL", (cvg == "COMP") & (peril == "GLASS"), cvg == "COMP", cvg == "MED", cvg == "RENT", cvg == "TOW"],
                      [VENDOR_SHARE["COLL"], VENDOR_SHARE["GLASS"], VENDOR_SHARE["COMP"], VENDOR_SHARE["MED"],
                       VENDOR_SHARE["RENT"], VENDOR_SHARE["TOW"]], default=0.0)
    total = f.total.to_numpy().astype(bool)
    kind = np.where((u < share) & ~total, "Vendor", "Insured").astype(object)
    pd_ = cvg == "PD"
    cuts = np.cumsum(list(PD_PAYEE.values()))
    kind[pd_] = np.array(list(PD_PAYEE))[np.searchsorted(cuts, u[pd_], side="right").clip(0, len(cuts) - 1)]
    inj = np.isin(cvg, ["BI", "UM"])
    represented = f.attorney.to_numpy().astype(bool)
    kind[inj] = np.where(represented[inj], "Claimant and Attorney", np.where(cvg[inj] == "BI", "Claimant", "Insured"))
    vtype = np.select([np.isin(cvg, ["COLL", "COMP"]) & (peril == "GLASS"), np.isin(cvg, ["COLL", "COMP", "PD"]), cvg == "MED",
                       cvg == "RENT", cvg == "TOW"],
                      ["Glass Vendor", "Body Shop", "Medical Provider", "Rental Company", "Towing Company"], default="")
    vendor = np.full(nF, -1)
    for t in np.unique(vtype[kind == "Vendor"]):
        m = (kind == "Vendor") & (vtype == t)
        vendor[m] = _pick_vendor(vend, t, zi[m], ref, R)
    m = kind == "Other Insurer"
    vendor[m] = _pick_vendor(vend, "Other Insurer", zi[m], ref, R)
    m = kind == "Claimant and Attorney"
    vendor[m] = _pick_vendor(vend, "Plaintiff Law Firm", zi[m], ref, R)

    # claimants are people: the same person for every coverage they claim under on one claim
    who = pd.MultiIndex.from_arrays([f.claim_id.to_numpy(), f.claimant.to_numpy()]).factorize()[0]
    n_who = who.max() + 1 if nF else 0
    first_zi = np.zeros(n_who, dtype=np.int64)
    first_zi[who] = zi
    fn, ln, _ = _people(ref, R, first_zi, R.integers(1945, 2006, n_who))
    claimant_name = (pd.Series(fn).str.title() + " " + pd.Series(ln).str.title()).to_numpy()[who]

    # ---- each payment
    p = pays.reset_index(drop=True)
    fi = pd.Series(np.arange(nF), index=f.feature_id.to_numpy()).reindex(p.feature_id).to_numpy()
    pc = f.claim_id.to_numpy()[fi] - 1
    n = len(p)
    pk, role, txn = p.kind.to_numpy(), p.role.to_numpy(), p.txn.to_numpy()
    payee = kind[fi].copy()
    pv = vendor[fi].copy()
    pzi = zi[fi]
    # an injury claimant is paid jointly with their attorney only once the attorney is retained; an advance before
    # that goes to the claimant alone (the same person, and the same law firm on every later joint payment)
    early = (payee == "Claimant and Attorney") & (p.day.to_numpy() < f.attorney_day.to_numpy()[fi])
    payee[early], pv[early] = "Claimant", -1
    # a total loss on a financed or leased car pays its lender (claims.py decides that and the amount): one
    # lender or lessor per car, whatever else is paid on the claim
    lien = role == "lien"
    payee[lien] = "Lienholder"
    car = claims.veh.to_numpy()[pc]
    cars, first = np.unique(car[lien], return_index=True)
    lender = _pick_vendor(vend, "Lienholder", pzi[lien][first], ref, R)
    pv[lien] = lender[np.searchsorted(cars, car[lien])]
    ex = pk == "Expense"
    lit = f.litigated.to_numpy().astype(bool)[fi]
    for m, t in ((ex & (txn == "A&O Expense"), "Independent Appraiser"), (ex & (txn == "DCC Expense") & lit, "Defense Law Firm"),
                 (ex & (txn == "DCC Expense") & ~lit, "Medical Review Service"), (pk == "Salvage Recovery", "Salvage Auction"),
                 (pk == "Subrogation Recovery", "Other Insurer")):
        payee[m] = "Other Insurer" if t == "Other Insurer" else "Vendor"
        pv[m] = _pick_vendor(vend, t, pzi[m], ref, R)
    # a void is made out to the payee of the cheque it cancels (its reissue goes to whoever is paid on its own date)
    pair = pd.MultiIndex.from_arrays([p.fid.to_numpy(), p.ref.to_numpy()])
    cheque = np.flatnonzero((p.ref.to_numpy() >= 0) & ~np.isin(txn, ["Void", "Reissue"]))
    vrow = np.flatnonzero(txn == "Void")
    src = pd.Series(cheque, index=pair[cheque]).reindex(pair[vrow]).to_numpy()
    payee[vrow], pv[vrow] = payee[src], pv[src]
    vname = vend.set_index("vendor").name.reindex(np.where(pv >= 0, pv, 0)).to_numpy()
    name = np.select([payee == "Insured", payee == "Claimant", payee == "Claimant and Attorney"],
                     [insured_name, claimant_name[fi], claimant_name[fi] + " and " + vname], default=vname)

    # method: one per payee per feature; a voided payment and its reissue are cheques
    incoming = np.isin(pk, ["Salvage Recovery", "Subrogation Recovery"])
    year_pos = np.clip(p.day.to_numpy() / max(V, 1), 0, 1)
    lo, hi = EFT_SHARE["Insured"]
    p_eft = np.select([payee == k for k in ("Vendor", "Lienholder", "Other Insurer", "Claimant", "Claimant and Attorney")],
                      [EFT_SHARE[k] for k in ("Vendor", "Lienholder", "Other Insurer", "Claimant", "Claimant and Attorney")],
                      default=lo + (hi - lo) * year_pos)
    per_feature = pd.Series(R.random(n)).groupby([p.feature_id.to_numpy(), payee]).transform("first").to_numpy()
    voided_pair = pd.MultiIndex.from_arrays([p.fid.to_numpy(), p.ref.to_numpy()])
    is_void, is_reissue = txn == "Void", txn == "Reissue"
    in_void = (p.ref.to_numpy() >= 0) & voided_pair.isin(voided_pair[is_void])       # the original, its void and its reissue
    method = np.where(incoming, "Deposit", np.where((per_feature < p_eft) & ~in_void, "EFT", "Check"))

    # cheque numbers: one unbroken sequence in the order the cheques were cut; a void carries its cheque's number
    cut = (method == "Check") & ~is_void
    order = np.flatnonzero(cut)                                     # payments are already in date order
    check = np.full(n, -1, dtype=np.int64)
    check[order] = FIRST_CHECK_NUMBER + np.arange(len(order))
    original = cut & in_void & ~is_reissue
    orig_no = pd.Series(check[original], index=voided_pair[original])
    check[is_void] = orig_no.reindex(voided_pair[is_void]).to_numpy()

    # clearing: electronic payments in a day or two, cheques when the payee banks them (a few never do)
    key = np.where(method == "EFT", "EFT", payee)
    lo_d = np.array([CLEARING_DAYS.get(k, (1, 2))[0] for k in key])
    hi_d = np.array([CLEARING_DAYS.get(k, (1, 2))[1] for k in key])
    wait = lo_d + np.floor(R.random(n) ** 2 * (hi_d - lo_d + 1)).astype(np.int64)       # most clear quickly
    cleared = cal._offset(p.day.to_numpy(), wait)
    never = (method == "Check") & np.isin(payee, ["Insured", "Claimant"]) & (R.random(n) < NEVER_CASHED_P)
    voided = original | is_void
    cleared = np.where(incoming, p.day.to_numpy(), cleared)
    is_cleared = ~voided & ~never & (cleared <= V)
    status = np.where(voided, "Voided", np.where(incoming, "Deposited", np.where(is_cleared, "Cleared", "Outstanding")))
    approver = roster.approver(desk[pc], office[pc], p.day.to_numpy(), p.amount.to_numpy())
    cols = dict(payee_type=payee, payee_name=name, vendor=pv, method=method, check=check,
                cleared=np.where(is_cleared, cleared, NO_DAY), status=status, approver=approver)
    return cols, adjuster
