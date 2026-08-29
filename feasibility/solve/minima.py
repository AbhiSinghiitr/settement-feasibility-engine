"""Part 2: minimum additional funds (lump sum and monthly increment).

Feasibility is monotonic in extra cash (more money never hurts), so both
minima are found by integer binary search over search.is_feasible. Returns
plain tuples rather than a FundsOption dataclass (which lives in output.py,
downstream of this module) to keep the dependency graph one-directional.
"""

from __future__ import annotations

from datetime import date, timedelta

from feasibility.models import Client, CreditorRules, Offer, offer_total_cents, program_fee_cents
from feasibility.solve.search import is_feasible

# Small safety margin added on top of the theoretical worst case, so the cap
# strictly exceeds the true break-even point rather than landing exactly on it.
SEARCH_CAP_BUFFER_CENTS = 100


def _future_draft_entries(client: Client):
    return [e for e in client.ledger if e.type == "credit" and e.date > client.as_of_date]


def _search_cap(client: Client, offer: Offer, rules: CreditorRules) -> int:
    """Enough to cover the entire settlement in one shot; if even this amount
    is infeasible, the problem is structural, not financial."""
    return (
        offer_total_cents(offer)
        + program_fee_cents(offer, rules)
        + rules.bank_fee_cents * rules.max_payments
        + SEARCH_CAP_BUFFER_CENTS
    )


def _binary_search_min(feasible_at, hi: int) -> int | None:
    if not feasible_at(hi):
        return None
    lo = 0
    while lo < hi:
        mid = (lo + hi) // 2
        if feasible_at(mid):
            hi = mid
        else:
            lo = mid + 1
    return lo


def find_min_lump_sum(
    client: Client, offer: Offer, rules: CreditorRules, first_payment_date: date
) -> tuple[int | None, date]:
    """Smallest single extra credit L, placed at the earliest modifiable date
    (as_of_date + 1 day dominates any later placement per the "earlier is
    weakly more useful" property of extra cash). Returns (L or None, the date)."""
    on_date = client.as_of_date + timedelta(days=1)
    cap = _search_cap(client, offer, rules)

    def feasible_at(amount: int) -> bool:
        return is_feasible(client, offer, rules, first_payment_date, extra_credits={on_date: amount})

    amount = _binary_search_min(feasible_at, cap)
    return amount, on_date


def find_min_monthly_increment(
    client: Client, offer: Offer, rules: CreditorRules, first_payment_date: date
) -> tuple[int | None, int]:
    """Smallest uniform X added to every future draft. Returns (X or None, N)."""
    entries = _future_draft_entries(client)
    n = len(entries)
    if n == 0:
        return None, 0
    cap = _search_cap(client, offer, rules)

    def feasible_at(per_draft: int) -> bool:
        extra: dict[date, int] = {}
        for e in entries:
            extra[e.date] = extra.get(e.date, 0) + per_draft
        return is_feasible(client, offer, rules, first_payment_date, extra_credits=extra)

    amount = _binary_search_min(feasible_at, cap)
    return amount, n
