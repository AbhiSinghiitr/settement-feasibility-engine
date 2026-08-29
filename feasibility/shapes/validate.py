"""Shared validator every payment-shape construction runs through.

Each shape builder (even/staircase/balloon) builds a candidate array from its
own construction rule, then hands it to `validate_payments` — construct,
then validate — so a bug in a construction rule shows up as a rejected shape
rather than a silently-wrong schedule.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ShapeResult:
    payments: list[int]
    valid: bool
    reason: str = ""


def validate_payments(
    payments: list[int], offer_total: int, floors: list[int], max_segments: int | None
) -> ShapeResult:
    """Check exact sum, per-position floors, non-decreasing order, and the
    distinct-level cap (when one applies)."""
    if sum(payments) != offer_total:
        return ShapeResult([], False, "sum mismatch")
    for i, (payment, floor) in enumerate(zip(payments, floors)):
        if payment < floor:
            return ShapeResult([], False, f"payment {i + 1} below floor")
        if i > 0 and payment < payments[i - 1]:
            return ShapeResult([], False, "not non-decreasing")
    if max_segments is not None and len(set(payments)) > max_segments:
        return ShapeResult([], False, "too many distinct segments")
    return ShapeResult(payments, True)
