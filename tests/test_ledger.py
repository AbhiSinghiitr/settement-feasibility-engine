"""Unit tests for feasibility/ledger.py: same-day ordering, as_of_date baking,
and balances hitting exactly zero."""

from __future__ import annotations

from datetime import date

from feasibility.simulation.ledger import simulate
from feasibility.models import Client, LedgerEntry


def _client(ledger, current_balance=0, as_of=date(2025, 12, 31)):
    return Client(
        draft_amount_cents=10000,
        draft_day=1,
        first_draft_date=date(2026, 1, 1),
        last_draft_date=date(2026, 3, 1),
        as_of_date=as_of,
        current_balance_cents=current_balance,
        ledger=ledger,
    )


def test_same_day_credits_apply_before_debits():
    # A same-day credit + debit that would go negative if debit applied first
    # must succeed, since all credits land before all debits.
    d = date(2026, 1, 5)
    client = _client([LedgerEntry(d, 5000, "credit")], current_balance=0)
    feasible, balances = simulate(
        client, extra_credits=None, creditor_payments={d: 5000}, bank_fees={}, program_fees={}
    )
    assert feasible
    assert balances[d] == 0


def test_balance_hitting_exactly_zero_is_feasible():
    d = date(2026, 1, 5)
    client = _client([LedgerEntry(d, 10000, "credit")], current_balance=0)
    feasible, balances = simulate(
        client, extra_credits=None, creditor_payments={d: 9500}, bank_fees={d: 500}, program_fees={}
    )
    assert feasible
    assert balances[d] == 0


def test_balance_one_cent_negative_is_infeasible():
    d = date(2026, 1, 5)
    client = _client([LedgerEntry(d, 10000, "credit")], current_balance=0)
    feasible, _ = simulate(
        client, extra_credits=None, creditor_payments={d: 9500}, bank_fees={d: 501}, program_fees={}
    )
    assert not feasible


def test_entries_on_or_before_as_of_date_are_ignored():
    # These are already baked into current_balance_cents; replaying them would
    # double-count.
    as_of = date(2025, 12, 31)
    old_entry = LedgerEntry(as_of, 999999, "credit")
    future_entry = LedgerEntry(date(2026, 1, 1), 10000, "credit")
    client = _client([old_entry, future_entry], current_balance=500, as_of=as_of)
    feasible, balances = simulate(
        client, extra_credits=None, creditor_payments={}, bank_fees={}, program_fees={}
    )
    assert feasible
    assert balances[date(2026, 1, 1)] == 500 + 10000  # old_entry never replayed


def test_fixed_committed_debits_are_respected():
    d1, d2 = date(2026, 1, 1), date(2026, 1, 15)
    client = _client(
        [LedgerEntry(d1, 20000, "credit"), LedgerEntry(d2, 15000, "debit")], current_balance=0
    )
    feasible, balances = simulate(
        client, extra_credits=None, creditor_payments={}, bank_fees={}, program_fees={}
    )
    assert feasible
    assert balances[d2] == 5000


def test_extra_credits_from_part_two_are_applied():
    d = date(2026, 1, 1)
    client = _client([LedgerEntry(d, 10000, "credit")], current_balance=0)
    feasible, balances = simulate(
        client, extra_credits={d: 5000}, creditor_payments={d: 14000}, bank_fees={}, program_fees={}
    )
    assert feasible
    assert balances[d] == 1000
