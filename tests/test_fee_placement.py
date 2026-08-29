"""Unit tests for feasibility/fee_placement.py: fee-before-first-payment
compliance, front-loading, and spillover into fee-only dates past k."""

from __future__ import annotations

from datetime import date

from feasibility.simulation.fee_placement import deferred_feasible, front_loaded_fee_placement
from feasibility.models import Client, LedgerEntry


def _client(ledger, current_balance=0, as_of=date(2025, 12, 31), last_draft=date(2026, 6, 1)):
    return Client(
        draft_amount_cents=10000,
        draft_day=1,
        first_draft_date=date(2026, 1, 1),
        last_draft_date=last_draft,
        as_of_date=as_of,
        current_balance_cents=current_balance,
        ledger=ledger,
    )


def _monthly_drafts(amount, dates):
    return [LedgerEntry(d, amount, "credit") for d in dates]


def test_worked_micro_example_from_assignment():
    # Horizon = 3 cadence dates; $100 lands before each; offer_total=$250,
    # program_fee=$50, bank_fee=$0, flat min $25. Expected: [$50,$100,$100],
    # fee fully collected on day one, balance lands at $0 each date.
    dates = [date(2026, 1, 31), date(2026, 2, 28), date(2026, 3, 31)]
    draft_dates = [date(2026, 1, 15), date(2026, 2, 15), date(2026, 3, 15)]
    client = _client(_monthly_drafts(10000, draft_dates), last_draft=date(2026, 3, 15))
    creditor_payments = {dates[0]: 5000, dates[1]: 10000, dates[2]: 10000}
    placement = front_loaded_fee_placement(
        client, creditor_payments, bank_fees={}, fee_total=5000, fee_eligible_dates=dates
    )
    assert placement is not None
    assert placement == {dates[0]: 5000}


def test_fee_never_placed_before_first_payment_date():
    dates = [date(2026, 1, 31), date(2026, 2, 28), date(2026, 3, 31)]
    draft_dates = [date(2026, 1, 15), date(2026, 2, 15), date(2026, 3, 15)]
    client = _client(_monthly_drafts(10000, draft_dates), last_draft=date(2026, 3, 15))
    creditor_payments = {dates[0]: 2500, dates[1]: 2500, dates[2]: 2500}
    placement = front_loaded_fee_placement(
        client, creditor_payments, bank_fees={}, fee_total=20000, fee_eligible_dates=dates
    )
    assert placement is not None
    assert min(placement) >= dates[0]  # eligible dates already exclude anything before first payment


def test_fee_spills_into_fee_only_dates_past_k_when_needed():
    # Only 1 creditor payment date, but the fee cadence extends further to
    # the horizon; a fee-only date must carry no bank fee.
    payment_date = date(2026, 1, 31)
    fee_only_date = date(2026, 2, 28)
    draft_dates = [date(2026, 1, 15), date(2026, 2, 15)]
    client = _client(_monthly_drafts(10000, draft_dates), last_draft=date(2026, 2, 15))
    creditor_payments = {payment_date: 9000}
    placement = front_loaded_fee_placement(
        client,
        creditor_payments,
        bank_fees={payment_date: 500},
        fee_total=10500,
        fee_eligible_dates=[payment_date, fee_only_date],
    )
    assert placement is not None
    assert sum(placement.values()) == 10500
    # not everything fits on the payment date (only $500 free after the
    # $9000 payment + $500 bank fee against a $10000 draft), so some fee
    # must spill onto the fee-only date
    assert placement[payment_date] == 500
    assert placement[fee_only_date] == 10000


def test_deferred_infeasible_when_fee_total_exceeds_all_available_cash():
    payment_date = date(2026, 1, 31)
    client = _client(_monthly_drafts(10000, [date(2026, 1, 15)]), last_draft=date(2026, 1, 15))
    creditor_payments = {payment_date: 9000}
    ok = deferred_feasible(
        client, creditor_payments, bank_fees={}, fee_total=5000, fee_eligible_dates=[payment_date]
    )
    assert not ok
    placement = front_loaded_fee_placement(
        client, creditor_payments, bank_fees={}, fee_total=5000, fee_eligible_dates=[payment_date]
    )
    assert placement is None


def test_zero_fee_total_returns_empty_placement():
    payment_date = date(2026, 1, 31)
    client = _client(_monthly_drafts(10000, [date(2026, 1, 15)]), last_draft=date(2026, 1, 15))
    placement = front_loaded_fee_placement(
        client, {payment_date: 9000}, bank_fees={}, fee_total=0, fee_eligible_dates=[payment_date]
    )
    assert placement == {}
