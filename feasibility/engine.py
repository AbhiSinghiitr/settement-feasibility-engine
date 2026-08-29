"""Top-level entry point: evaluate_offer().

Wires the pieces together — pick the first payment date, ask the solver for
the best feasible schedule, and either report it or fall back to the Part 2
minimum-funding search. See SOLUTION.md for the full data-flow and
algorithm write-up.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from feasibility.dates import default_first_payment_date
from feasibility.models import Client, CreditorRules, Offer, offer_total_cents
from feasibility.money import round_half_up
from feasibility.output import AdditionalFunds, FundsOption, Result, ScheduleRow
from feasibility.solve.minima import find_min_lump_sum, find_min_monthly_increment
from feasibility.solve.search import SolvedSchedule, find_best_schedule

# Part 2 guardrails: reject an amount that's unreasonably large relative to
# the draft/offer size, even if it would technically make the offer work.
LUMP_SUM_GUARDRAIL_PCT = Decimal("0.65")  # cap: 65% of offer_total
MONTHLY_INCREMENT_GUARDRAIL_PCT = Decimal("0.40")  # cap: 40% of draft_amount_cents
MONTHLY_INCREMENT_GUARDRAIL_FLOOR_CENTS = 10000  # ...but the cap is never below $100


def evaluate_offer(client: Client, offer: Offer, rules: CreditorRules) -> Result:
    """Decide whether the offer is affordable and, if so, produce a payment
    schedule that collects the program fee as early as possible; if not,
    compute the minimum extra funding (lump sum and monthly increment) that
    would make it affordable.
    """
    first_payment_date = offer.first_payment_date or default_first_payment_date(client)

    solved = find_best_schedule(client, offer, rules, first_payment_date)
    if solved is not None:
        return Result(
            feasible=True,
            pay_shape_used=solved.shape,
            schedule=_build_schedule_rows(solved),
            additional_funds=None,
        )

    return Result(
        feasible=False,
        pay_shape_used=None,
        schedule=None,
        additional_funds=_compute_additional_funds(client, offer, rules, first_payment_date),
    )


def _build_schedule_rows(solved: SolvedSchedule) -> list[ScheduleRow]:
    payment_by_date = dict(zip(solved.payment_dates, solved.payments))
    used_dates = sorted(set(solved.payment_dates) | set(solved.fee_placement))
    return [
        ScheduleRow(
            date=d,
            creditor_payment_cents=payment_by_date.get(d, 0),
            program_fee_cents=solved.fee_placement.get(d, 0),
            bank_fee_cents=solved.bank_fees.get(d, 0),
            balance_cents=solved.balances[d],
        )
        for d in used_dates
    ]


def _compute_additional_funds(
    client: Client, offer: Offer, rules: CreditorRules, first_payment_date: date
) -> AdditionalFunds:
    offer_total = offer_total_cents(offer)
    draft_amount = client.draft_amount_cents

    lump_amount, lump_date = find_min_lump_sum(client, offer, rules, first_payment_date)
    incr_amount, num_drafts = find_min_monthly_increment(client, offer, rules, first_payment_date)

    return AdditionalFunds(
        lump_sum=_lump_sum_option(lump_amount, lump_date, offer_total),
        monthly_increment=_monthly_increment_option(incr_amount, num_drafts, draft_amount),
    )


def _lump_sum_option(amount: int | None, on_date: date, offer_total: int) -> FundsOption:
    guardrail = round_half_up(LUMP_SUM_GUARDRAIL_PCT * offer_total)
    if amount is None:
        return FundsOption(
            amount_cents=0,
            within_guardrail=False,
            reason="no feasible schedule exists at any funding level",
            date=on_date,
        )
    within = amount <= guardrail
    reason = "" if within else f"lump sum {amount} exceeds guardrail {guardrail} (65% of offer total)"
    return FundsOption(amount_cents=amount, within_guardrail=within, reason=reason, date=on_date)


def _monthly_increment_option(amount: int | None, num_drafts: int, draft_amount: int) -> FundsOption:
    guardrail = max(
        MONTHLY_INCREMENT_GUARDRAIL_FLOOR_CENTS,
        round_half_up(MONTHLY_INCREMENT_GUARDRAIL_PCT * draft_amount),
    )
    if num_drafts == 0:
        return FundsOption(
            amount_cents=0, within_guardrail=False, reason="no future drafts to increment", num_drafts=0
        )
    if amount is None:
        return FundsOption(
            amount_cents=0,
            within_guardrail=False,
            reason="no feasible schedule exists at any funding level",
            num_drafts=num_drafts,
        )
    within = amount <= guardrail
    reason = "" if within else f"monthly increment {amount} exceeds guardrail {guardrail}"
    return FundsOption(amount_cents=amount, within_guardrail=within, reason=reason, num_drafts=num_drafts)
