"""Ledger simulation: fixed base timeline + variable schedule entries."""

from __future__ import annotations

from datetime import date

from feasibility.models import Client


def base_flows(client: Client) -> dict[date, tuple[int, int]]:
    """date -> (credit_cents, debit_cents) from ledger entries after as_of_date.

    Entries on or before as_of_date are already baked into
    current_balance_cents; including them again would double-count.
    """
    flows: dict[date, list[int]] = {}
    for entry in client.ledger:
        if entry.date <= client.as_of_date:
            continue
        pair = flows.setdefault(entry.date, [0, 0])
        if entry.type == "credit":
            pair[0] += entry.amount_cents
        else:
            pair[1] += entry.amount_cents
    return {d: (c, deb) for d, (c, deb) in flows.items()}


def simulate(
    client: Client,
    extra_credits: dict[date, int] | None,
    creditor_payments: dict[date, int],
    bank_fees: dict[date, int],
    program_fees: dict[date, int],
) -> tuple[bool, dict[date, int]]:
    """Chronological simulation, all credits before all debits on each date.

    Returns (feasible, balance_after_date) where the balance is recorded once
    per date that has any activity — sufficient since balance is flat between
    activity dates, so only those need checking against >= 0.
    """
    flows = base_flows(client)
    extra_credits = extra_credits or {}
    all_dates = (
        set(flows) | set(extra_credits) | set(creditor_payments) | set(bank_fees) | set(program_fees)
    )
    balance = client.current_balance_cents
    feasible = True
    balances: dict[date, int] = {}
    for d in sorted(all_dates):
        base_credit, base_debit = flows.get(d, (0, 0))
        credit = base_credit + extra_credits.get(d, 0)
        debit = base_debit + creditor_payments.get(d, 0) + bank_fees.get(d, 0) + program_fees.get(d, 0)
        balance += credit
        balance -= debit
        balances[d] = balance
        if balance < 0:
            feasible = False
    return feasible, balances
