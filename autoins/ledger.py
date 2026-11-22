"""The general ledger: what the subledgers add up to, month by month.

Three small tables, built from the published tables alone, so every figure can be rebuilt by a reader:

* gl_account: the chart of accounts.
* gl_journal: one balanced journal entry for each month, underwriting company and kind of activity, summarising
  that month's rows of a subledger. The activities, the subledger behind each and the accounts they move:

  ============================  =============================  ======================================================
  journal                       subledger                      entry
  ============================  =============================  ======================================================
  Premiums written              premium_transaction            Dr premiums receivable, Cr premiums written
  Change in unearned premium    premium_transaction            Dr change in unearned premium, Cr unearned premium
  Premium cash receipts         billing_receipt, _invoice      Dr cash, Cr premiums receivable, Cr fees
  Premiums written off          billing_invoice                Dr premiums written off, Cr premiums receivable
  Commission expense            premium_transaction            Dr commission expense, Cr commissions payable
  Commissions paid              agency_statement               Dr commissions payable, Cr cash
  Claim payments                claim_payment                  Dr losses paid and adjustment expenses paid, Cr cash
  Claim recoveries              claim_payment                  Dr cash, Cr salvage and subrogation recoveries
  Case reserve changes          claim_reserve_transaction      Dr change in case reserves, Cr case reserves
  ============================  =============================  ======================================================

* agency_statement: the commission each agency earned in a month and the day it was paid: the subledger behind
  commissions payable.

How the entries are dated. A premium transaction is booked on its accounting date, the later of its effective
and processed dates (a renewal keyed in November for January is January's premium; an endorsement keyed late
is booked when it is keyed). Each transaction is earned evenly from its effective date to the end of its term,
so unearned premium at a month end is what remains to be earned of everything booked by then. Cash moves on
the receipt or payment date, a reserve change on its transaction date, a write-off on its write-off date. A
month's commission is paid to the agency in the middle of the next month.

The books open on the day before the extract begins with one entry: the premiums receivable, unearned premium
and commissions payable that the policies in force bring with them, the case reserves on the claims then open
(claim payments and reserve changes before the start belong to earlier years), cash, and the surplus that
balances them.
Cash and surplus on that day are ASSUMED (config.OPENING_SURPLUS_SHARE); everything else follows from the
tables. The ledger holds only what the tables support: there are no investments, general expenses, taxes,
reinsurance or reserves for claims not yet reported, and acquisition costs are expensed as written. Fees are
income when collected. Premiums receivable is one account: premium written and not yet collected, whether
billed or not, less premium paid ahead and refunds on their way.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from . import config as C

# (number, name, type, normal balance, statement line)
ACCOUNTS = [
    (1000, "Cash and short-term investments", "Asset", "Debit", "Balance sheet"),
    (1200, "Premiums receivable", "Asset", "Debit", "Balance sheet"),
    (2100, "Unearned premium reserve", "Liability", "Credit", "Balance sheet"),
    (2200, "Commissions payable", "Liability", "Credit", "Balance sheet"),
    (2500, "Case loss reserves", "Liability", "Credit", "Balance sheet"),
    (2510, "Case loss adjustment expense reserves", "Liability", "Credit", "Balance sheet"),
    (3000, "Policyholders' surplus", "Equity", "Credit", "Balance sheet"),
    (4000, "Premiums written", "Revenue", "Credit", "Income statement"),
    (4010, "Change in unearned premium", "Revenue", "Debit", "Income statement"),
    (4200, "Installment, late and returned-payment fees", "Revenue", "Credit", "Income statement"),
    (5000, "Losses paid", "Expense", "Debit", "Income statement"),
    (5010, "Salvage recoveries", "Expense", "Credit", "Income statement"),
    (5020, "Subrogation recoveries", "Expense", "Credit", "Income statement"),
    (5100, "Defense and cost containment expenses paid", "Expense", "Debit", "Income statement"),
    (5110, "Adjusting and other expenses paid", "Expense", "Debit", "Income statement"),
    (5200, "Change in case loss reserves", "Expense", "Debit", "Income statement"),
    (5210, "Change in case loss adjustment expense reserves", "Expense", "Debit", "Income statement"),
    (6100, "Commission expense", "Expense", "Debit", "Income statement"),
    (6300, "Premiums written off", "Expense", "Debit", "Income statement"),
]
NORMAL = {a[0]: a[3] for a in ACCOUNTS}
# journal -> (code, subledger). Lines are (account, sign): +1 posts a positive amount to the account's debit side.
JOURNALS = {
    "Opening balances": ("OB", "premium_transaction, billing_receipt"),
    "Premiums written": ("PW", "premium_transaction"),
    "Change in unearned premium": ("UP", "premium_transaction"),
    "Premium cash receipts": ("CR", "billing_receipt"),
    "Premiums written off": ("WO", "billing_invoice"),
    "Commission expense": ("CE", "premium_transaction"),
    "Commissions paid": ("CP", "agency_statement"),
    "Claim payments": ("LP", "claim_payment"),
    "Claim recoveries": ("LR", "claim_payment"),
    "Case reserve changes": ("RS", "claim_reserve_transaction"),
    "Year-end closing": ("CL", "gl_journal"),
}
COMMISSION_PAY_DAY = 15            # a month's commission is paid on this day of the next month (or the next business day)


def _cents(x) -> np.ndarray:
    return np.round(np.asarray(x, dtype=float) * 100).astype(np.int64)


def accounting_day(effective, processed) -> np.ndarray:
    """The day a premium transaction is booked: the later of its effective and processed days."""
    return np.maximum(effective, processed)


def unearned(amount, effective, expiration, booked, as_of: int) -> np.ndarray:
    """What is left to earn at the end of day `as_of` of each transaction booked by then (in the amount's units):
    a transaction earns evenly from its effective day to the term's expiration day."""
    left = np.clip((expiration - np.maximum(as_of + 1, effective)) / np.maximum(expiration - effective, 1), 0, 1)
    return np.round(amount * left * (booked <= as_of)).astype(np.int64)


def build(cfg: C.Config, cal, T: dict) -> dict:
    """Returns {"gl_account", "gl_journal", "agency_statement"} from the published tables T."""
    start = cal.start.astype("M8[D]")
    V = cal.valuation_day
    day = lambda s: (pd.to_datetime(s).to_numpy().astype("M8[D]") - start).astype(np.int64)
    month0 = start.astype("M8[M]")
    first_of = lambda m: int(((month0 + np.timedelta64(int(m), "M")).astype("M8[D]") - start).astype(int))   # day number
    month_of = lambda d: ((start + np.asarray(d).astype("timedelta64[D]")).astype("M8[M]") - month0).astype(np.int64)
    n_months = int(month_of(V)) + 1
    month_end = np.array([min(first_of(m + 1) - 1, V) for m in range(n_months)])

    pol = T["policy"]
    company_of = pd.Series(pol.company_id.to_numpy(), index=pol.policy_id.to_numpy())
    companies = np.sort(T["underwriting_company"].company_id.to_numpy())
    ci = lambda policy_id: np.searchsorted(companies, company_of.reindex(policy_id).to_numpy())
    nc = len(companies)

    def by_month(m, c, cents) -> np.ndarray:
        """(company, month) totals of cents for rows dated in the extract; month -1 collects everything earlier."""
        keep = m < n_months
        out = np.zeros((nc, n_months + 1), dtype=np.int64)
        np.add.at(out, (c[keep], np.maximum(m[keep], -1) + 1), cents[keep])
        return out

    # ---- premium: written, unearned, commission
    tx = T["premium_transaction"]
    eff, booked = day(tx.effective_date), accounting_day(day(tx.effective_date), day(tx.processed_date))
    exp = day(T["policy_term"].set_index("policy_term_id").expiration_date.reindex(tx.policy_term_id))
    tc, tm = ci(tx.policy_id), month_of(booked)
    wp, com = _cents(tx.written_premium), _cents(tx.commission_amount)
    written, commission = by_month(tm, tc, wp), by_month(tm, tc, com)
    upr = np.zeros((nc, n_months + 1), dtype=np.int64)          # column 0: the day before the extract begins
    for k, d in enumerate(np.r_[-1, month_end]):
        np.add.at(upr[:, k], tc, unearned(wp, eff, exp, booked, int(d)))

    # ---- billing: cash, split into premium and fees through the bill each receipt pays
    rec, inv = T["billing_receipt"], T["billing_invoice"]
    bill_premium = pd.Series(_cents(inv.premium_amount), index=inv.invoice_id.to_numpy())
    amount = _cents(rec.amount)
    kind = rec.receipt_type.to_numpy()
    billed = pd.to_numeric(rec.invoice_id, errors="coerce").fillna(-1).astype(np.int64).to_numpy()     # blank on refunds
    on_bill = bill_premium.reindex(billed).fillna(0).to_numpy().astype(np.int64)
    prem_part = np.where(kind == "Refund", amount, np.where(kind == "Returned Payment", -on_bill, on_bill))
    rc, rm = ci(rec.policy_id), month_of(day(rec.receipt_date))
    cash_in, collected = by_month(rm, rc, amount), by_month(rm, rc, prem_part)
    wo = inv[inv.write_off_date.notna() & ~inv.write_off_date.astype(str).isin(["", "nan", "None", "<NA>"])]
    written_off = by_month(month_of(day(wo.write_off_date)), ci(wo.policy_id), _cents(wo.amount_due))

    # ---- commission statements: each agency's month, paid in the middle of the next month
    agency_of = pd.Series(pol.agency_id.to_numpy(), index=pol.policy_id.to_numpy()).reindex(tx.policy_id).to_numpy()
    ag = T["agency"]
    agent = ag.agency_id[ag.channel != "Direct"].to_numpy()
    s = pd.DataFrame(dict(agency_id=agency_of, m=tm, wp=wp, com=com))
    s = s[np.isin(s.agency_id, agent) & (s.m >= -1) & (s.m < n_months)]
    s = s.groupby(["m", "agency_id"], as_index=False)[["wp", "com"]].sum()
    s = s[(s.wp != 0) | (s.com != 0)].reset_index(drop=True)
    pay = cal.next_business(np.array([first_of(m + 1) + COMMISSION_PAY_DAY - 1 for m in s.m.to_numpy()], dtype=np.int64))
    paid = pay <= V
    D = lambda d: pd.Series(cal.date(np.asarray(d))).dt.strftime("%Y-%m-%d").to_numpy()
    period = lambda m: np.array([str(month0 + np.timedelta64(int(k), "M")) for k in np.asarray(m)])
    statement = pd.DataFrame({
        "statement_id": np.arange(1, len(s) + 1), "agency_id": s.agency_id.to_numpy(), "statement_month": period(s.m),
        "written_premium": s.wp.to_numpy() / 100, "commission_amount": s.com.to_numpy() / 100,
        "payment_date": pd.array(np.where(paid, D(pay), None), dtype="object"),
        "payment_method": pd.array(np.where(paid, "EFT", None), dtype="object")})
    # the ledger pays each company's share of a month's commission when the statements are paid
    com_paid = np.zeros_like(commission)
    for m in range(-1, n_months - 1):
        pay_m = cal.next_business(first_of(m + 1) + COMMISSION_PAY_DAY - 1)
        if pay_m <= V:
            com_paid[:, int(month_of(pay_m)) + 1] += _agents_commission(tc, tm, com, agency_of, agent, m, nc)

    # ---- claims: payments, recoveries, case reserves
    clm_pol = pd.Series(T["claim"].policy_id.to_numpy(), index=T["claim"].claim_id.to_numpy())
    cp = T["claim_payment"]
    pc_, pm = ci(clm_pol.reindex(cp.claim_id).to_numpy()), month_of(day(cp.payment_date))
    amt, ptype, ttype = _cents(cp.amount), cp.payment_type.to_numpy(), cp.transaction_type.to_numpy()
    pick = lambda mask: by_month(pm[mask], pc_[mask], amt[mask])
    loss, dcc = pick(ptype == "Loss"), pick((ptype == "Expense") & (ttype == "DCC Expense"))
    ao = pick((ptype == "Expense") & (ttype != "DCC Expense"))
    salvage, subro = -pick(ptype == "Salvage Recovery"), -pick(ptype == "Subrogation Recovery")
    rs = T["claim_reserve_transaction"]
    rc_, rsm = ci(clm_pol.reindex(rs.claim_id).to_numpy()), month_of(day(rs.transaction_date))
    chg, rtype = _cents(rs.change_amount), rs.reserve_type.to_numpy()
    res_loss, res_exp = by_month(rsm[rtype == "Loss"], rc_[rtype == "Loss"], chg[rtype == "Loss"]), \
        by_month(rsm[rtype != "Loss"], rc_[rtype != "Loss"], chg[rtype != "Loss"])

    # ---- the journal
    lines = []

    def post(name, c, k, entries):
        """One journal for company index c in month column k (0 = opening). entries: (account, cents), positive
        meaning a debit; lines of zero are left out and an entry with no lines is not written."""
        entries = [(a, int(v)) for a, v in entries if v != 0]
        if entries:
            lines.extend((name, c, k, a, max(v, 0), max(-v, 0)) for a, v in entries)

    # opening balances, the day before the extract begins: what the policies in force bring, cash and surplus
    term_months = pd.Series(pol.term_months.to_numpy(), index=pol.policy_id.to_numpy()).reindex(tx.policy_id).to_numpy()
    opening = tx.transaction_type.isin(["New Business", "Renewal"]).to_numpy() & (tm < 0)
    annual = np.bincount(tc[opening], (wp * 12 / term_months)[opening], nc)
    for c in range(nc):
        receivable = written[c, 0] - collected[c, 0] - written_off[c, 0]
        payable = _agents_commission(tc, tm, com, agency_of, agent, -1, nc)[c]
        surplus = int(round(C.OPENING_SURPLUS_SHARE * annual[c] / 100, -5)) * 100
        reserved = res_loss[c, 0] + res_exp[c, 0]          # case reserves on the claims open when the extract begins
        cash = surplus - receivable + upr[c, 0] + payable + reserved
        post("Opening balances", c, 0, [(1000, cash), (1200, receivable), (2100, -upr[c, 0]), (2200, -payable),
                                        (2500, -res_loss[c, 0]), (2510, -res_exp[c, 0]), (3000, -surplus)])
        for k in range(1, n_months + 1):
            d_upr = upr[c, k] - upr[c, k - 1]
            fees = cash_in[c, k] - collected[c, k]
            post("Premiums written", c, k, [(1200, written[c, k]), (4000, -written[c, k])])
            post("Change in unearned premium", c, k, [(4010, d_upr), (2100, -d_upr)])
            post("Premium cash receipts", c, k, [(1000, cash_in[c, k]), (1200, -collected[c, k]), (4200, -fees)])
            post("Premiums written off", c, k, [(6300, written_off[c, k]), (1200, -written_off[c, k])])
            post("Commission expense", c, k, [(6100, commission[c, k]), (2200, -commission[c, k])])
            post("Commissions paid", c, k, [(2200, com_paid[c, k]), (1000, -com_paid[c, k])])
            paid_out = loss[c, k] + dcc[c, k] + ao[c, k]
            post("Claim payments", c, k, [(5000, loss[c, k]), (5100, dcc[c, k]), (5110, ao[c, k]), (1000, -paid_out)])
            back = salvage[c, k] + subro[c, k]
            post("Claim recoveries", c, k, [(1000, back), (5010, -salvage[c, k]), (5020, -subro[c, k])])
            post("Case reserve changes", c, k, [(5200, res_loss[c, k]), (2500, -res_loss[c, k]),
                                                (5210, res_exp[c, k]), (2510, -res_exp[c, k])])
    # each 31 December the year's income statement accounts are closed to surplus (a year not ended by the valuation
    # date is left open): after closing they stand at zero, and surplus has moved by the year's net income
    income = [a[0] for a in ACCOUNTS if a[4] == "Income statement"]
    j = pd.DataFrame(lines, columns=["journal", "c", "k", "account", "debit", "credit"])
    act = j[(j.k > 0) & j.account.isin(income)]
    year_end = {p_[:4]: k + 1 for k, p_ in enumerate(period(np.arange(n_months))) if p_.endswith("-12")}
    net = (act.debit - act.credit).groupby([act.c.to_numpy(), period(act.k.to_numpy() - 1).astype("U4"), act.account.to_numpy()]).sum()
    for (c, y), g in net.groupby(level=[0, 1]):
        if y in year_end:
            post("Year-end closing", c, year_end[y], [(a, -v) for (_, _, a), v in g.items()] + [(3000, g.sum())])
    j = pd.DataFrame(lines, columns=["journal", "c", "k", "account", "debit", "credit"])
    order = {name: i for i, name in enumerate(JOURNALS)}
    j["o"] = j.journal.map(order)
    j = j.sort_values(["k", "c", "o"], kind="stable").reset_index(drop=True)
    post_day = np.where(j.k.to_numpy() == 0, -1, month_end[np.maximum(j.k.to_numpy() - 1, 0)])
    code = T["underwriting_company"].set_index("company_id").company_code.reindex(companies[j.c.to_numpy()]).to_numpy()
    per = period(j.k.to_numpy() - 1)
    journal = pd.DataFrame({
        "journal_line_id": np.arange(1, len(j) + 1),
        "journal_number": [f"JE-{p}-{k}-{JOURNALS[n][0]}" for p, k, n in zip(per, code, j.journal)],
        "accounting_period": per, "posting_date": D(post_day), "company_id": companies[j.c.to_numpy()],
        "journal_type": j.journal.to_numpy(), "source_table": j.journal.map(lambda n: JOURNALS[n][1]).to_numpy(),
        "account_number": j.account.to_numpy(), "debit": j.debit.to_numpy() / 100, "credit": j.credit.to_numpy() / 100})
    accounts = pd.DataFrame(ACCOUNTS, columns=["account_number", "account_name", "account_type", "normal_balance", "financial_statement"])
    return {"gl_account": accounts, "gl_journal": journal, "agency_statement": statement}


def _agents_commission(tc, tm, com, agency_of, agent, m: int, nc: int) -> np.ndarray:
    """Each company's commission booked in month m on agents' business (direct business earns none). tc, tm, com
    and agency_of are each premium transaction's company index, booking month, commission and agency."""
    k = (tm == m) & np.isin(agency_of, agent)
    return np.bincount(tc[k], com[k], nc).astype(np.int64)
