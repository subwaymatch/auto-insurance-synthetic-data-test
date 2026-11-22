"""Billing: what each policyholder was billed and what they paid.

The premium ledger (tables._transactions) says what was written; this module turns it into the bills a
billing system sends and the cash it receives:

* A term on the paid-in-full plan gets one bill, due on its effective date. A term on a monthly plan gets one
  instalment a month (six or twelve), the first due on the effective date and the rest on the anniversary day
  of each following month, each issued about three weeks ahead. Instalments after the first carry an
  instalment fee.
* A mid-term change (an endorsement) is spread over the instalments not yet issued; with none left (or on the
  paid-in-full plan) an additional premium is billed on its own and a return premium is refunded.
* Customers pay by automatic bank draft (the EFT plan), card, online bank payment, cheque or through their
  agent. Most pay on time. Some pay late, more often the less settled households (the hidden stability of
  population.py), and pay a late fee; a few bank drafts are returned unpaid and collected again with a fee.
* A cancellation for non-payment is the instalment that was never paid (simulate._missed_installment). A bill
  gets a past-due notice and then a notice of cancellation; a bank draft is attempted and returned, and its
  returned-payment notice and notice of cancellation go out the day it comes back. Either way the notice of
  cancellation is mailed at least ten days before cover ends, as Illinois requires. When any cancellation is
  processed, bills still unpaid are cancelled and the account is settled against the premium earned: a balance still owed is billed (and, after a non-payment cancellation, mostly never
  collected and written off), and money paid ahead is refunded.

For every finished term, the premium on its bills (less cancelled ones) minus the premium refunded equals its
written, endorsement and return premium in the ledger. Nothing dated after the valuation date is shown: a bill
not yet issued, a payment not yet received.

All rates and amounts are ASSUMED (typical of personal auto billing plans).
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from . import config as C
from .refdata import stream

ISSUE_LEAD_DAYS = 20                       # an instalment is billed this many days before it falls due
MIN_INSTALLMENT = 2_500                    # cents: a balance that would split into smaller instalments is billed at once
INSTALLMENT_FEE = {0: 0, 1: 200, 2: 500}   # cents per instalment after the first, by plan (paid in full, EFT, bill)
LATE_FEE, RETURNED_PAYMENT_FEE = 1_000, 2_500      # cents
LATE_FEE_AFTER_DAYS = 5
LATE_P = dict(base=0.13, stability=-0.60, low=0.02, high=0.60)          # a billed instalment paid after its due date
RETURNED_P = dict(base=0.012, stability=-0.70, low=0.002, high=0.08)    # a bank draft returned unpaid
MAX_DAYS_LATE = 16                         # a customer who is going to pay does so before cover would end
METHODS = ["Credit Card", "Online Bank Payment", "Check", "Agency"]
METHOD_P = {"agent": [0.42, 0.28, 0.20, 0.10], "direct": [0.55, 0.33, 0.12, 0.0]}
FINAL_BALANCE_DUE_DAYS = 15
COLLECT_P = {"Non-Payment": 0.30, "other": 0.88}   # a balance billed after cancellation that is paid
WRITE_OFF_DAYS = 120
NO_DAY = -10 ** 9                          # "no such day": day numbers before the start are real days, so -1 will not do
NOTICE_DAYS = dict(past_due=4, cancellation=7)     # days after a missed due date (a notice of cancellation
                                                   # reaches the customer at least 10 days before cover would end)


def _cents(x) -> np.ndarray:
    return np.round(np.asarray(x, dtype=float) * 100).astype(np.int64)


def _schedule(cal, pol: pd.DataFrame, terms: pd.DataFrame, tx: pd.DataFrame):
    """The bills each term is sent before anyone pays: its instalments (with endorsements spread over those not yet
    issued) and endorsement bills, none issued once a cancellation is processed. Returns (terms in term order, bills,
    refunds owed so far, net premium per term in cents, the day each term's cancellation was processed)."""
    t = terms.sort_values("term", kind="stable").reset_index(drop=True)
    assert (t.term.to_numpy() == np.arange(len(t))).all()
    nt = len(t)
    tp = t.pol.to_numpy()
    plan = pol.pay_plan.to_numpy()[tp]
    n_inst = np.where(plan == 0, 1, pol.term_months.to_numpy()[tp]).astype(np.int64)
    s, offer = t.s.to_numpy(), t.offer_day.to_numpy()

    amount = _cents(tx.amount)
    start = tx.kind.isin(["New Business", "Renewal"]).to_numpy()
    w0 = np.bincount(tx.term.to_numpy()[start], amount[start], nt).astype(np.int64)
    net = np.bincount(tx.term.to_numpy(), amount, nt).astype(np.int64)            # written + endorsements + returns
    can = tx[tx.kind == "Cancellation"]
    pc = np.full(nt, 10 ** 9)                         # the day each term's cancellation was processed
    pc[can.term.to_numpy()] = can.processed.to_numpy()

    # ---- the instalment schedule
    base = np.cumsum(n_inst) - n_inst
    I = np.repeat(np.arange(nt), n_inst)
    j = np.arange(len(I)) - base[I]
    due = np.where(j == 0, s[I], cal.day_of(t.month0.to_numpy()[I] + j, pol.dom.to_numpy()[tp][I]))
    issue = np.where(j == 0, offer[I], due - ISSUE_LEAD_DAYS)
    prem = w0[I] // n_inst[I]
    prem[base + n_inst - 1] += w0 - (w0 // n_inst) * n_inst                       # the last instalment takes the cents

    # ---- endorsements, in the order processed: each re-spreads the balance still to bill evenly over the instalments
    # not yet issued (the last takes the cents). A return larger than that balance leaves nothing more to bill and is
    # refunded at once; a balance too small to split goes on the next bill alone
    en = tx[tx.kind == "Endorsement"]
    order = np.lexsort((en.processed.to_numpy(), en.term.to_numpy()))
    et, ep = en.term.to_numpy()[order], en.processed.to_numpy()[order]
    ea = amount[(tx.kind == "Endorsement").to_numpy()][order]
    k = np.arange(1, 12)
    later_due = cal.day_of(t.month0.to_numpy()[et][:, None] + k[None, :], pol.dom.to_numpy()[tp][et][:, None])
    j0 = 1 + ((later_due - ISSUE_LEAD_DAYS <= ep[:, None]) & (k[None, :] < n_inst[et][:, None])).sum(axis=1)
    left = np.maximum(n_inst[et] - j0, 0)
    spread = left > 0
    rank = np.arange(len(et)) - np.searchsorted(et, et)
    back = np.zeros(len(et), dtype=np.int64)                          # the part of a return refunded on its own
    for r in range(int(rank.max()) + 1 if len(et) else 0):
        e_ = np.flatnonzero((rank == r) & spread)
        L, first = left[e_], base[et[e_]] + j0[e_]
        row = np.repeat(np.arange(len(e_)), L)
        idx = np.repeat(first, L) + np.arange(L.sum()) - np.repeat(np.cumsum(L) - L, L)
        bal = np.rint(np.bincount(row, prem[idx], len(e_))).astype(np.int64) + ea[e_]
        back[e_] = np.minimum(bal, 0)
        bal = np.maximum(bal, 0)
        per = bal // L
        lump = per < MIN_INSTALLMENT
        last = idx == np.repeat(first + L - 1, L)
        prem[idx] = np.where(lump[row], np.where(idx == first[row], bal[row], 0),
                             np.where(last, bal[row] - per[row] * (L[row] - 1), per[row]))
    extra = pd.DataFrame(dict(term=et[~spread], day=ep[~spread], cents=ea[~spread]))    # billed or refunded on their own
    extra = pd.concat([extra, pd.DataFrame(dict(term=et[back < 0], day=ep[back < 0], cents=back[back < 0]))], ignore_index=True)
    extra = extra[extra.day.to_numpy() < pc[extra.term.to_numpy()]]       # after a cancellation, the settlement covers it
    assert (prem >= 0).all()
    refunds = [pd.DataFrame(dict(term=extra.term[extra.cents < 0], day=extra.day[extra.cents < 0], cents=-extra.cents[extra.cents < 0]))]

    inv = pd.DataFrame(dict(term=I, inst=j + 1, kind=np.where(n_inst[I] == 1, "Paid in Full", np.where(j == 0, "Down Payment", "Installment")),
                            issue=issue, due=due, prem=prem, fee=np.where(j > 0, np.vectorize(INSTALLMENT_FEE.get)(plan[I]), 0)))
    bill = extra[extra.cents > 0]
    inv = pd.concat([inv, pd.DataFrame(dict(term=bill.term, inst=0, kind="Endorsement", issue=bill.day,
                                            due=bill.day + ISSUE_LEAD_DAYS, prem=bill.cents, fee=0))], ignore_index=True)
    inv = inv[(inv.prem > 0) & (inv.issue < pc[inv.term.to_numpy()])].reset_index(drop=True)     # never issued once cancelled
    return t, inv, refunds, net, pc


def without_a_bill_to_miss(cal, pol: pd.DataFrame, terms: pd.DataFrame, tx: pd.DataFrame) -> np.ndarray:
    """Terms cancelled for non-payment whose designated unpaid instalment (simulate._missed_installment) has nothing
    to pay: a return premium processed before it was issued (a car written off and not yet replaced, say) left
    nothing on it, so no bill was sent. The simulation chooses that instalment before the term's changes happen."""
    t, inv, _, _, _ = _schedule(cal, pol, terms, tx)
    miss = t.missed_installment.to_numpy()
    cand = t.term.to_numpy()[(t.cancel_reason.to_numpy() == "Non-Payment") & (miss >= 0)]
    regular = inv[inv.kind.isin(["Installment", "Down Payment"])]
    billed = pd.MultiIndex.from_arrays([regular.term.to_numpy(), regular.inst.to_numpy()])
    return cand[~pd.MultiIndex.from_arrays([cand, miss[cand] + 1]).isin(billed)]


def build(cfg: C.Config, cal, pol: pd.DataFrame, terms: pd.DataFrame, tx: pd.DataFrame):
    """Returns (billing_invoice, billing_receipt, contacts): the two tables keyed by the simulation's policy and
    term indices (tables.build turns them into IDs), and the notices billing sent (pol, day, purpose).

    pol: policies (pay_plan, term_months, dom, channel, stab). terms: one row per term (term, pol, s, e,
    offer_day, new_business, month0, missed_installment). tx: the premium ledger before formatting (term, kind,
    day, processed, amount), already cut off at the valuation date."""
    R = stream(cfg.seed, "billing")
    V = cal.valuation_day
    t, inv, refunds, net, pc = _schedule(cal, pol, terms, tx)
    nt = len(t)
    tp = t.pol.to_numpy()
    plan = pol.pay_plan.to_numpy()[tp]
    stab = pol.stab.to_numpy()[tp]
    s, offer = t.s.to_numpy(), t.offer_day.to_numpy()
    reason = pd.Series(t.cancel_reason.to_numpy()).where(pc < 10 ** 9, "").to_numpy()

    # ---- how each bill is paid
    n = len(inv)
    it = inv.term.to_numpy()
    ip, idue, iissue = plan[it], inv.due.to_numpy(), inv.issue.to_numpy()
    first = inv.inst.to_numpy() == 1
    pick = lambda p_: R.choice(len(METHODS), len(pol), p=p_)
    own = np.where(pol.channel.to_numpy() == 2, pick(METHOD_P["direct"]), pick(METHOD_P["agent"]))     # each household's habit
    method = np.where((ip == 1) & ~(first & t.new_business.to_numpy()[it]), "EFT", np.array(METHODS)[own[tp[it]]])
    u, v = R.random(n), R.random(n)
    lp, rp = LATE_P, RETURNED_P
    p_late = np.clip(lp["base"] * np.exp(lp["stability"] * stab[it]), lp["low"], lp["high"])
    late = (u < p_late) & (method != "EFT")
    late_days = 1 + np.minimum(np.floor(R.exponential(5.0, n)), MAX_DAYS_LATE - 1).astype(np.int64)
    # a household paying in full never lets cover lapse: a late renewal payment arrives within the grace period,
    # before a notice of cancellation would go out
    late_days = np.where(ip == 0, np.minimum(late_days, NOTICE_DAYS["cancellation"] - 1), late_days)
    early = np.floor(v * np.minimum(np.maximum(idue - iissue, 0), 14) + 0.999).astype(np.int64).clip(0)
    paid = np.where(late, idue + late_days, idue - early)
    # a new customer pays the first bill when the policy is bound, between the quote and the effective date
    bind = first & t.new_business.to_numpy()[it]
    paid = np.where(bind, offer[it] + np.floor(v * (s[it] - offer[it] + 1)).astype(np.int64).clip(0, None), paid)
    paid = np.where(bind, np.minimum(paid, s[it]), paid)
    late &= ~bind
    eft = method == "EFT"
    paid = np.where(eft, cal.next_business(idue), np.where(method == "Check", cal.next_business(paid), paid))
    returned = eft & (R.random(n) < np.clip(rp["base"] * np.exp(rp["stability"] * stab[it]), rp["low"], rp["high"]))
    bounce = cal._offset(paid, 1 + R.integers(1, 4, n))                           # the bank returns the draft
    redraft = cal.next_business(bounce + R.integers(3, 8, n))
    fee2 = np.where(returned, RETURNED_PAYMENT_FEE, np.where(late & (paid - idue > LATE_FEE_AFTER_DAYS), LATE_FEE, 0))
    final = np.where(returned, redraft, paid)                                     # the day the bill is settled

    # the instalment that was never paid, and anything unpaid when a cancellation is processed
    miss = t.missed_installment.to_numpy()[it]
    never = (reason[it] == "Non-Payment") & (miss >= 0) & (inv.inst.to_numpy() - 1 >= miss) & (inv.kind.to_numpy() != "Endorsement")
    settled = ~(never | (final > pc[it]))
    inv["late_fee"] = np.where(settled, fee2, 0)
    inv["total"] = inv.prem + inv.fee + inv.late_fee
    inv["paid_day"] = np.where(settled, final, NO_DAY)
    inv["status"] = np.where(settled, "Paid", np.where(pc[it] < 10 ** 9, "Canceled", "Open"))
    inv["method"] = method
    # a returned draft leaves its first attempt and the bank's reversal on the account, even if the term is
    # cancelled before it is collected again. The draft for the instalment a leaving household does not pay is
    # attempted on its due date too, and comes back (the account is closed or the authorisation withdrawn)
    inv["missed"] = never & (inv.inst.to_numpy() - 1 == miss)
    inv["try_day"] = np.where(((returned & ~never) | (inv.missed.to_numpy() & eft)) & (paid < pc[it]), paid, NO_DAY)
    inv["bounce_day"] = np.where(inv.try_day != NO_DAY, bounce, NO_DAY)
    inv["stop"] = pc[it]                                 # nothing is chased once the cancellation is processed
    inv["write_off"] = NO_DAY

    # ---- settling a cancelled account: premium kept against premium paid (less anything already refunded)
    paid_prem = np.bincount(it[settled], inv.prem.to_numpy()[settled], nt).astype(np.int64)
    ref0 = pd.concat(refunds, ignore_index=True)
    refunded = np.bincount(ref0.term.to_numpy(), ref0.cents.to_numpy(), nt).astype(np.int64)
    c = np.flatnonzero(pc < 10 ** 9)
    owed = net[c] - (paid_prem[c] - refunded[c])
    bal = owed > 0
    # the account is settled once the term's last transaction is booked (a change keyed after the cancellation)
    booked = np.maximum(pc, pd.Series(tx.processed.to_numpy()).groupby(tx.term.to_numpy()).max().reindex(np.arange(nt)).fillna(0).to_numpy().astype(np.int64))
    fb_issue = cal.next_business(booked[c])
    collect = R.random(len(c)) < np.where(reason[c] == "Non-Payment", COLLECT_P["Non-Payment"], COLLECT_P["other"])
    fb_paid = fb_issue + 3 + np.floor(R.exponential(12.0, len(c))).astype(np.int64)
    fb_method = np.array(METHODS)[own[tp[c]]]
    fb_paid = np.where(fb_method == "Check", cal.next_business(fb_paid), fb_paid)     # as for any bill: a cheque is banked on a business day
    fb = pd.DataFrame(dict(term=c[bal], inst=0, kind="Final Balance", issue=fb_issue[bal], due=fb_issue[bal] + FINAL_BALANCE_DUE_DAYS,
                           prem=owed[bal], fee=0, late_fee=0, total=owed[bal], paid_day=np.where(collect[bal], fb_paid[bal], NO_DAY),
                           status=np.where(collect[bal], "Paid", "Written Off"),
                           method=np.where(collect[bal], fb_method[bal], ""),
                           try_day=NO_DAY, bounce_day=NO_DAY, stop=10 ** 9, missed=False,
                           write_off=np.where(collect[bal], NO_DAY, cal.next_business(fb_issue[bal] + WRITE_OFF_DAYS))))
    inv = pd.concat([inv, fb], ignore_index=True)
    back = owed < 0
    refunds.append(pd.DataFrame(dict(term=c[back], day=booked[c][back], cents=-owed[back])))
    ref = pd.concat(refunds, ignore_index=True)
    ref["day"] = cal.spread_business(ref.day.to_numpy() + 3 + R.integers(0, 8, len(ref)), R.random(len(ref)))

    # ---- what the extract shows: nothing after the valuation date
    inv = inv[inv.issue <= V].sort_values(["issue", "term", "inst"], kind="stable").reset_index(drop=True)
    inv["invoice"] = np.arange(len(inv))
    number = 100_000 + np.cumsum(R.geometric(1 / 4.0, len(inv)))                  # other regions' bills fall between
    yy = (cal.date(inv.issue.to_numpy()).astype("M8[Y]").astype(int) + 1970) % 100
    inv["number"] = [f"INV-{y:02d}-{x:09d}" for y, x in zip(yy, number)]
    ok, rt = inv[inv.status == "Paid"], inv[inv.try_day != NO_DAY]
    rec = pd.concat([
        pd.DataFrame(dict(term=ok.term, invoice=ok.invoice, day=ok.paid_day, kind="Payment", method=ok.method, cents=ok.total)),
        pd.DataFrame(dict(term=rt.term, invoice=rt.invoice, day=rt.try_day, kind="Payment", method="EFT", cents=rt.prem + rt.fee)),
        pd.DataFrame(dict(term=rt.term, invoice=rt.invoice, day=rt.bounce_day, kind="Returned Payment", method="EFT", cents=-(rt.prem + rt.fee))),
        pd.DataFrame(dict(term=ref.term, invoice=-1, day=ref.day, kind="Refund", method="Check", cents=-ref.cents))], ignore_index=True)
    rec = rec[rec.day <= V].sort_values(["day", "term", "invoice", "kind"], kind="stable").reset_index(drop=True)
    rec["receipt"] = np.arange(len(rec))
    # a draft taken by the valuation date whose return has not yet come back looks paid on that date
    in_flight = (inv.try_day != NO_DAY) & (inv.try_day <= V) & (inv.bounce_day > V) & (inv.status != "Canceled")
    inv.loc[in_flight, "paid_day"] = inv.try_day[in_flight]
    inv.loc[in_flight, "total"] = inv.prem[in_flight] + inv.fee[in_flight]
    inv.loc[in_flight, "late_fee"], inv.loc[in_flight, "status"] = 0, "Paid"
    not_yet = (inv.status == "Paid") & (inv.paid_day > V)                         # paid after the valuation date
    inv.loc[not_yet, "status"], inv.loc[not_yet, "paid_day"] = "Open", NO_DAY
    inv.loc[not_yet, "total"] = inv.total[not_yet] - inv.late_fee[not_yet]
    inv.loc[not_yet, "late_fee"] = 0
    pending = (inv.status == "Written Off") & (inv.write_off > V)
    inv.loc[pending, "status"], inv.loc[pending, "write_off"] = "Open", NO_DAY
    return inv, rec, _notices(cal, inv, V)


def _notices(cal, inv: pd.DataFrame, V: int) -> pd.DataFrame:
    """What billing sent the customer: a past-due notice when a bill is still unpaid some days after its due
    date, a notice of cancellation after that (rescinded if the customer pays), and a notice when a bank draft
    comes back unpaid. A bank draft for the instalment that is never paid gets its notice of cancellation the
    day the bank returns it, as well as the returned-payment notice. Returns (term, day, purpose)."""
    reg = inv[inv.kind != "Final Balance"]
    unpaid_on = lambda d: ((reg.paid_day == NO_DAY) | (reg.paid_day > d)) & (d < reg.stop) & (d <= V)
    out = []
    for purpose, lag in (("Past Due Notice", NOTICE_DAYS["past_due"]), ("Notice of Cancellation", NOTICE_DAYS["cancellation"])):
        d = pd.Series(cal.next_business(reg.due.to_numpy() + lag), index=reg.index)     # mailed on a business day
        m = unpaid_on(d) & (reg.method != "EFT")
        out.append(pd.DataFrame(dict(term=reg.term[m], day=d[m], purpose=purpose)))
    rt = reg[(reg.bounce_day != NO_DAY) & (reg.bounce_day <= V)]
    out.append(pd.DataFrame(dict(term=rt.term, day=rt.bounce_day, purpose="Returned Payment Notice")))
    lost = rt[rt.missed & (rt.method == "EFT")]
    out.append(pd.DataFrame(dict(term=lost.term, day=lost.bounce_day, purpose="Notice of Cancellation")))
    return pd.concat(out, ignore_index=True)
