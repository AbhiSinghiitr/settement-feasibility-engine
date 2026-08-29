"""Per-position payment floor: base minimum, token-pay rule, and tiers."""

from __future__ import annotations

from feasibility.models import CreditorRules


def build_floors(k: int, rules: CreditorRules) -> list[int]:
    """Position ``i`` (1-based, for i in 1..k) -> minimum allowed payment at
    that position: the max of the base minimum; the token-pay rule
    (positions beyond max_token_pays must strictly exceed the base minimum
    — and since every payment is an integer number of cents, "strictly
    exceed N" has exactly one smallest satisfying value, N + 1, not an
    arbitrary bump: for integers, x > N is equivalent to x >= N + 1); and
    any applicable min_payment_tiers step-up. Non-decreasing in position
    (tiers only step up, the token-pay cutoff is a fixed threshold), which
    is what lets a final balloon payment automatically respect the
    token-pay and tier rules too, with no separate check needed.

    The floor only *changes* at a handful of positions — a tier's
    from_position, or the token-pay cutoff — and is flat everywhere else.
    So rather than recomputing every rule at every position (O(k * T) for T
    tiers), each breakpoint's bump is written directly into the (otherwise
    zero) output list at its own index, then one forward pass carries the
    running floor across the gaps: O(k + T).
    """
    floors = [0] * k

    token_pay_cutoff = rules.max_token_pays + 1
    if token_pay_cutoff <= k:
        floors[token_pay_cutoff - 1] = max(floors[token_pay_cutoff - 1], rules.min_payment_cents + 1)

    for from_position, min_cents in rules.min_payment_tiers:
        start = max(from_position, 1)
        if start <= k:
            floors[start - 1] = max(floors[start - 1], min_cents)

    floor = rules.min_payment_cents
    for i in range(k):
        floor = max(floor, floors[i])
        floors[i] = floor
    return floors
