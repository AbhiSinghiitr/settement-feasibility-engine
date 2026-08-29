"""Front-loaded program-fee placement for a fixed creditor-payment schedule.

`deferred_feasible` is the yes/no oracle (dump all remaining fee on the last
eligible date — provably the most forgiving placement, since moving fee
later only ever raises earlier balances); `front_loaded_fee_placement` is the
actual constructive greedy used for the produced schedule.
"""

from __future__ import annotations

from datetime import date

from feasibility.models import Client
from feasibility.simulation.ledger import simulate


def deferred_feasible(
    client: Client,
    creditor_payments: dict[date, int],
    bank_fees: dict[date, int],
    fee_total: int,
    fee_eligible_dates: list[date],
    extra_credits: dict[date, int] | None = None,
) -> bool:
    """Is there *any* fee placement that keeps the whole ledger non-negative?

    Dumping the entire remaining fee at the latest eligible date maximizes
    every intermediate balance (moving fee later only ever raises balances
    before that date), so if this placement fails, no placement can succeed.
    """
    if not fee_eligible_dates:
        if fee_total != 0:
            return False
        return simulate(client, extra_credits, creditor_payments, bank_fees, {})[0]
    program_fees = {fee_eligible_dates[-1]: fee_total}
    return simulate(client, extra_credits, creditor_payments, bank_fees, program_fees)[0]


def front_loaded_fee_placement(
    client: Client,
    creditor_payments: dict[date, int],
    bank_fees: dict[date, int],
    fee_total: int,
    fee_eligible_dates: list[date],
    extra_credits: dict[date, int] | None = None,
) -> dict[date, int] | None:
    """Collect as much fee as possible at the earliest eligible dates.

    Returns None if infeasible even with the fee fully deferred. Otherwise
    returns {date: fee_cents} summing to fee_total, front-loaded as much as
    the ledger allows.

    One simulation pass, not one per date: run the ledger once with zero fee
    anywhere (every eligible date forced in as a checkpoint), take a
    suffix-min of the resulting balances, then walk forward. The most fee
    takeable at date d is the lowest point the balance ever dips to between
    d and the last eligible date, minus whatever fee is already committed at
    earlier dates — moving fee later only ever raises a balance, so that
    dip is the binding constraint regardless of how the rest gets split.
    """
    if not deferred_feasible(
        client, creditor_payments, bank_fees, fee_total, fee_eligible_dates, extra_credits
    ):
        return None
    if fee_total == 0 or not fee_eligible_dates:
        return {}

    last = fee_eligible_dates[-1]
    zero_fee_checkpoints = {d: 0 for d in fee_eligible_dates}
    _, raw_balances = simulate(client, extra_credits, creditor_payments, bank_fees, zero_fee_checkpoints)

    # Dates at/after `last` always end up with the full fee_total subtracted
    # eventually (whatever isn't taken earlier gets dumped there), so how
    # earlier dates split the remainder can't affect them — deferred_feasible
    # already confirmed they're fine. Only dates strictly before `last`
    # constrain how much can be taken early.
    suffix_min: dict[date, int] = {}
    running_min = None
    for d in sorted((dt for dt in raw_balances if dt < last), reverse=True):
        running_min = raw_balances[d] if running_min is None else min(running_min, raw_balances[d])
        suffix_min[d] = running_min

    placement: dict[date, int] = {}
    remaining = fee_total
    for d in fee_eligible_dates:
        if remaining == 0:
            break
        if d == last:
            placement[d] = remaining
            break
        already_committed = fee_total - remaining
        take = max(0, min(remaining, suffix_min[d] - already_committed))
        if take:
            placement[d] = take
            remaining -= take

    return placement
