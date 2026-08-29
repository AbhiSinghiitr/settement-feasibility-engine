"""Tests for solve/search.py's k-selection: find_best_schedule keeps whichever
k finishes collecting the program fee on the earliest cadence date, ties
broken toward the smallest k.
"""

from __future__ import annotations

from datetime import date

from feasibility.models import Client, CreditorRules, LedgerEntry, Offer
from feasibility.solve.search import find_best_schedule


def _client(ledger, last_draft):
    return Client(
        draft_amount_cents=10000,
        draft_day=1,
        first_draft_date=date(2026, 1, 1),
        last_draft_date=last_draft,
        as_of_date=date(2025, 12, 31),
        current_balance_cents=0,
        ledger=ledger,
    )


def _offer(creditor_balance, original_balance, settlement_pct, program_fee_pct):
    return Offer(
        creditor="TestCo",
        creditor_balance_cents=creditor_balance,
        original_balance_cents=original_balance,
        settlement_pct=settlement_pct,
        first_payment_date=date(2026, 1, 31),
    )


def _rules(program_fee_pct):
    return CreditorRules(
        max_terms=2,
        max_payments=2,
        min_payment_cents=1000,
        max_token_pays=100,
        min_payment_tiers=[],
        even_pays=False,
        is_ballooning_allowed=True,
        max_segments=4,
        bank_fee_cents=0,
        program_fee_pct=program_fee_pct,
    )


# Shared ledger for both tests: $100 on Jan1, $10 on Feb1. Cadence (from
# first_payment_date=Jan31) gives exactly 2 fee-eligible dates: Jan31, Feb28.
_LEDGER = [
    LedgerEntry(date(2026, 1, 1), 10000, "credit"),
    LedgerEntry(date(2026, 2, 1), 1000, "credit"),
]
_HORIZON = date(2026, 2, 28)


def test_prefers_the_k_that_finishes_collecting_fee_earliest():
    # offer_total=$85 (8500c), fee_total=$20 (2000c).
    # k=1: single $8500 payment on Jan31 leaves only $1500 free there (raw
    #   balance 10000-8500=1500) — takes $1500, defers the remaining $500 to
    #   Feb28. Finishes on the *second* eligible date.
    # k=2 (balloon, floor $1000): payments [$1000, $7500] on Jan31/Feb28.
    #   Jan31's much smaller payment leaves $9000 free there — comfortably
    #   covers the whole $2000 fee in one shot. Finishes on the *first* date.
    # k=2 must win, even though this is also what plain lexicographic
    # comparison would have picked for this particular scenario.
    client = _client(_LEDGER, _HORIZON)
    offer = _offer(creditor_balance=8500, original_balance=10000, settlement_pct=1.0, program_fee_pct=0.2)
    rules = _rules(program_fee_pct=0.2)

    solved = find_best_schedule(client, offer, rules, date(2026, 1, 31))

    assert solved is not None
    assert solved.k == 2
    assert solved.payments == [1000, 7500]
    assert solved.fee_placement == {date(2026, 1, 31): 2000}
    assert solved.balances[date(2026, 1, 31)] == 7000
    assert solved.balances[date(2026, 2, 28)] == 500


def test_ties_on_finish_date_break_toward_smallest_k():
    # offer_total=$60 (6000c), fee_total=$20 (2000c) — small enough that
    # *both* k=1 (single $6000 payment, $4000 free on Jan31) and k=2
    # ($1000/$5000 split, $9000 free on Jan31) can collect the entire fee
    # immediately on Jan31. Genuine tie on "finishes earliest" — the smaller
    # k must win.
    client = _client(_LEDGER, _HORIZON)
    offer = _offer(creditor_balance=6000, original_balance=10000, settlement_pct=1.0, program_fee_pct=0.2)
    rules = _rules(program_fee_pct=0.2)

    solved = find_best_schedule(client, offer, rules, date(2026, 1, 31))

    assert solved is not None
    assert solved.k == 1
    assert solved.payments == [6000]
    assert solved.fee_placement == {date(2026, 1, 31): 2000}
