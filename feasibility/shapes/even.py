"""The `even_pays` shape: all payments equal; remainder cents onto the latest
payments so the sequence stays non-decreasing when the total doesn't divide
evenly by k."""

from __future__ import annotations

from feasibility.shapes.validate import ShapeResult, validate_payments


def build_even(floors: list[int], offer_total: int) -> ShapeResult:
    """`floors` is this k's per-position floor array (see solve/search.py —
    it's a prefix slice of one array built once up to k_upper, since a
    position's floor doesn't depend on k)."""
    k = len(floors)
    base, remainder = divmod(offer_total, k)
    payments = [base] * k
    for i in range(k - remainder, k):
        payments[i] += 1
    return validate_payments(payments, offer_total, floors, max_segments=None)
