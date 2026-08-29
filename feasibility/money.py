"""Money rounding helpers.

The spec requires round-half-up (ties away from zero) everywhere, and
explicitly warns against relying on a language default (Python's builtin
``round`` is round-half-to-even). We route every rounding decision through
here so there's exactly one place that gets it right.
"""

from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal


def round_half_up(value: Decimal | float | int) -> int:
    """Round to the nearest integer, ties away from zero."""
    d = value if isinstance(value, Decimal) else Decimal(str(value))
    return int(d.quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def pct_of_cents(pct: float, cents: int) -> int:
    """round_half_up(pct * cents), computed in Decimal to avoid binary-float drift.

    ``pct`` typically comes from JSON as a short decimal literal (e.g. 0.2,
    0.125); routing it through ``Decimal(str(pct))`` before multiplying keeps
    the arithmetic exact instead of inheriting float noise like
    ``0.2 * 120000 == 24000.000000000004``.
    """
    return round_half_up(Decimal(str(pct)) * Decimal(cents))
