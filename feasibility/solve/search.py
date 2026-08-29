"""k-search: pick the number of creditor payments that best serves the
front-loading objective (Part 1), and a cheap yes/no oracle reusing the same
construction for Part 2's binary searches.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from feasibility.dates import cadence_dates_through_horizon
from feasibility.models import Client, CreditorRules, Offer, offer_total_cents, program_fee_cents
from feasibility.shapes.even import build_even
from feasibility.shapes.floors import build_floors
from feasibility.shapes.stepped import build_balloon, build_staircase
from feasibility.shapes.validate import ShapeResult
from feasibility.simulation.fee_placement import deferred_feasible, front_loaded_fee_placement
from feasibility.simulation.ledger import simulate


@dataclass(frozen=True)
class SolvedSchedule:
    shape: str
    k: int
    payment_dates: list[date]
    payments: list[int]
    fee_placement: dict[date, int]
    bank_fees: dict[date, int]
    balances: dict[date, int]


def shape_name(rules: CreditorRules) -> str:
    if rules.even_pays:
        return "even"
    if rules.is_ballooning_allowed:
        return "balloon"
    return "staircase"


def _build_payments(floors: list[int], offer_total: int, rules: CreditorRules) -> ShapeResult:
    if rules.even_pays:
        return build_even(floors, offer_total)
    if rules.is_ballooning_allowed:
        return build_balloon(floors, offer_total)
    return build_staircase(floors, offer_total, rules)


def _k_upper(rules: CreditorRules, all_cadence: list[date]) -> int:
    return min(rules.max_payments, rules.max_terms, len(all_cadence))


def _fee_finish_index(placement: dict[date, int], all_cadence: list[date]) -> int:
    """Index into all_cadence of the last date any fee was collected on;
    -1 if no fee was collected anywhere (e.g. program_fee_pct == 0)."""
    finish = -1
    for i, d in enumerate(all_cadence):
        if placement.get(d, 0):
            finish = i
    return finish


def find_best_schedule(
    client: Client,
    offer: Offer,
    rules: CreditorRules,
    first_payment_date: date,
    extra_credits: dict[date, int] | None = None,
) -> SolvedSchedule | None:
    """Search k in [1, k_upper]; keep the one that finishes collecting the
    fee on the earliest possible date (ties broken toward the smallest k)."""
    horizon = client.last_draft_date
    offer_total = offer_total_cents(offer)
    fee_total = program_fee_cents(offer, rules)
    shape = shape_name(rules)

    all_cadence = cadence_dates_through_horizon(first_payment_date, horizon)
    k_upper = _k_upper(rules, all_cadence)
    # A position's floor doesn't depend on k, so build the floor array once
    # up to k_upper and take a prefix slice per k instead of recomputing it
    # k times.
    floors_upper = build_floors(k_upper, rules)

    best: SolvedSchedule | None = None
    best_finish_index: int | None = None

    for k in range(1, k_upper + 1):
        result = _build_payments(floors_upper[:k], offer_total, rules)
        if not result.valid:
            continue
        payment_dates = all_cadence[:k]
        creditor_payments = dict(zip(payment_dates, result.payments))
        bank_fees = {d: rules.bank_fee_cents for d in payment_dates} if rules.bank_fee_cents else {}

        placement = front_loaded_fee_placement(
            client, creditor_payments, bank_fees, fee_total, all_cadence, extra_credits
        )
        if placement is None:
            continue

        finish_index = _fee_finish_index(placement, all_cadence)
        if best_finish_index is None or finish_index < best_finish_index:
            _, balances = simulate(client, extra_credits, creditor_payments, bank_fees, placement)
            best = SolvedSchedule(shape, k, payment_dates, result.payments, placement, bank_fees, balances)
            best_finish_index = finish_index

    return best


def is_feasible(
    client: Client,
    offer: Offer,
    rules: CreditorRules,
    first_payment_date: date,
    extra_credits: dict[date, int] | None = None,
) -> bool:
    """Cheap yes/no oracle: does *any* k admit a feasible schedule?

    Reuses the same (cash-flow-dominant) construction as find_best_schedule,
    so this is exact, not an approximation — no alternative valid shape for
    the same k could do better on cash-flow.
    """
    horizon = client.last_draft_date
    offer_total = offer_total_cents(offer)
    fee_total = program_fee_cents(offer, rules)

    all_cadence = cadence_dates_through_horizon(first_payment_date, horizon)
    k_upper = _k_upper(rules, all_cadence)
    floors_upper = build_floors(k_upper, rules)

    for k in range(1, k_upper + 1):
        result = _build_payments(floors_upper[:k], offer_total, rules)
        if not result.valid:
            continue
        payment_dates = all_cadence[:k]
        creditor_payments = dict(zip(payment_dates, result.payments))
        bank_fees = {d: rules.bank_fee_cents for d in payment_dates} if rules.bank_fee_cents else {}
        if deferred_feasible(client, creditor_payments, bank_fees, fee_total, all_cadence, extra_credits):
            return True
    return False
