"""Tests for Part 2 (minimum additional funds) and the horizon limit, using a
hand-built scenario independent of the provided cases/ fixtures."""

from __future__ import annotations

from datetime import date

from feasibility.engine import evaluate_offer
from feasibility.models import Client, CreditorRules, LedgerEntry, Offer
from feasibility.solve.search import find_best_schedule, is_feasible


def _drafts(amount, dates):
    return [LedgerEntry(d, amount, "credit") for d in dates]


def _client(draft_dates, draft_amount=10000, last_draft=None, as_of=date(2025, 12, 31)):
    return Client(
        draft_amount_cents=draft_amount,
        draft_day=1,
        first_draft_date=draft_dates[0],
        last_draft_date=last_draft or draft_dates[-1],
        as_of_date=as_of,
        current_balance_cents=0,
        ledger=_drafts(draft_amount, draft_dates),
    )


def _offer(creditor_balance, original_balance, settlement_pct, first_payment_date):
    return Offer(
        creditor="TestCo",
        creditor_balance_cents=creditor_balance,
        original_balance_cents=original_balance,
        settlement_pct=settlement_pct,
        first_payment_date=first_payment_date,
    )


def _rules(**overrides):
    base = dict(
        max_terms=4,
        max_payments=4,
        min_payment_cents=2500,
        max_token_pays=4,
        min_payment_tiers=[],
        even_pays=False,
        is_ballooning_allowed=False,
        max_segments=3,
        bank_fee_cents=0,
        program_fee_pct=0.125,
    )
    base.update(overrides)
    return CreditorRules(**base)


def test_infeasible_case_reports_lump_sum_and_increment_minima():
    # Mirrors cases/case2_infeasible_minima by hand: offer_total=40000,
    # fee_total=10000, 4 drafts of 10000, k_upper=4.
    draft_dates = [date(2026, 1, 1), date(2026, 2, 1), date(2026, 3, 1), date(2026, 4, 1), date(2026, 5, 1)]
    client = _client(draft_dates, last_draft=date(2026, 5, 1))
    offer = _offer(80000, 80000, 0.5, date(2026, 1, 31))
    rules = _rules()

    result = evaluate_offer(client, offer, rules)

    assert result.feasible is False
    assert result.schedule is None
    af = result.additional_funds
    assert af.lump_sum.amount_cents == 10000
    assert af.lump_sum.within_guardrail is True
    assert af.monthly_increment.amount_cents == 2500
    assert af.monthly_increment.num_drafts == 5
    assert af.monthly_increment.within_guardrail is True


def test_lump_sum_actually_flips_feasibility():
    draft_dates = [date(2026, 1, 1), date(2026, 2, 1), date(2026, 3, 1), date(2026, 4, 1), date(2026, 5, 1)]
    client = _client(draft_dates, last_draft=date(2026, 5, 1))
    offer = _offer(80000, 80000, 0.5, date(2026, 1, 31))
    rules = _rules()

    assert is_feasible(client, offer, rules, date(2026, 1, 31)) is False
    on_date = date(2026, 1, 1)
    assert is_feasible(client, offer, rules, date(2026, 1, 31), extra_credits={on_date: 9999}) is False
    assert is_feasible(client, offer, rules, date(2026, 1, 31), extra_credits={on_date: 10000}) is True


def test_monthly_increment_actually_flips_feasibility():
    draft_dates = [date(2026, 1, 1), date(2026, 2, 1), date(2026, 3, 1), date(2026, 4, 1), date(2026, 5, 1)]
    client = _client(draft_dates, last_draft=date(2026, 5, 1))
    offer = _offer(80000, 80000, 0.5, date(2026, 1, 31))
    rules = _rules()

    extra_short = {d: 2499 for d in draft_dates}
    extra_ok = {d: 2500 for d in draft_dates}
    assert is_feasible(client, offer, rules, date(2026, 1, 31), extra_credits=extra_short) is False
    assert is_feasible(client, offer, rules, date(2026, 1, 31), extra_credits=extra_ok) is True


def test_lump_sum_guardrail_rejects_when_too_large():
    # A tiny draft with a huge offer_total forces a lump sum well beyond 65%
    # of offer_total.
    draft_dates = [date(2026, 1, 1)]
    client = _client(draft_dates, draft_amount=100, last_draft=date(2026, 1, 1))
    offer = _offer(1000000, 1000000, 0.9, date(2026, 1, 1))
    rules = _rules(max_terms=1, max_payments=1, min_payment_cents=100, max_token_pays=1, program_fee_pct=0.0)

    result = evaluate_offer(client, offer, rules)
    assert result.feasible is False
    assert result.additional_funds.lump_sum.within_guardrail is False
    assert result.additional_funds.lump_sum.reason != ""


def test_monthly_increment_guardrail_rejects_when_too_large():
    draft_dates = [date(2026, 1, 1)]
    client = _client(draft_dates, draft_amount=100, last_draft=date(2026, 1, 1))
    offer = _offer(1000000, 1000000, 0.9, date(2026, 1, 1))
    rules = _rules(max_terms=1, max_payments=1, min_payment_cents=100, max_token_pays=1, program_fee_pct=0.0)

    result = evaluate_offer(client, offer, rules)
    assert result.feasible is False
    assert result.additional_funds.monthly_increment.within_guardrail is False


def test_horizon_limit_no_schedule_scheduled_past_last_draft_date():
    draft_dates = [date(2026, 1, 1)]
    client = _client(draft_dates, draft_amount=100000, last_draft=date(2026, 1, 1))
    # first_payment_date is after the horizon: structurally no schedule can
    # ever be placed, regardless of funding.
    offer = _offer(10000, 10000, 0.5, date(2026, 2, 28))
    rules = _rules(max_terms=6, max_payments=6, min_payment_cents=100, max_token_pays=6)

    solved = find_best_schedule(client, offer, rules, date(2026, 2, 28))
    assert solved is None
    assert is_feasible(client, offer, rules, date(2026, 2, 28), extra_credits={date(2026, 1, 1): 10 ** 9}) is False

    result = evaluate_offer(client, offer, rules)
    assert result.feasible is False
    assert result.additional_funds.lump_sum.within_guardrail is False
    assert result.additional_funds.monthly_increment.within_guardrail is False


def test_feasible_schedule_never_uses_a_date_past_the_horizon():
    draft_dates = [date(2026, 1, 1), date(2026, 2, 1), date(2026, 3, 1)]
    client = _client(draft_dates, draft_amount=50000, last_draft=date(2026, 3, 1))
    offer = _offer(60000, 60000, 0.5, date(2026, 1, 31))
    rules = _rules(max_terms=12, max_payments=12, min_payment_cents=2500, max_token_pays=12, program_fee_pct=0.0)

    result = evaluate_offer(client, offer, rules)
    assert result.feasible is True
    assert all(row.date <= client.last_draft_date for row in result.schedule)
