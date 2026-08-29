"""Core data model: the four input dataclasses, plus the two money values
derived directly from them (offer_total_cents, program_fee_cents).

Everything money-related is in integer cents; dates are ``datetime.date``.
JSON loading lives in loaders.py, calendar/cadence helpers in dates.py — kept
separate so this file is just "what a case *is*", not how it's read or
scheduled.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Literal

from feasibility.money import pct_of_cents

EntryType = Literal["credit", "debit"]


@dataclass(frozen=True)
class LedgerEntry:
    date: date
    amount_cents: int
    type: EntryType


@dataclass
class Client:
    draft_amount_cents: int
    draft_day: int
    first_draft_date: date
    last_draft_date: date
    as_of_date: date
    current_balance_cents: int
    ledger: list[LedgerEntry] = field(default_factory=list)


@dataclass
class Offer:
    creditor: str
    creditor_balance_cents: int
    original_balance_cents: int
    settlement_pct: float
    # Optional. When omitted, default to the end of the month of first_draft_date
    # (see dates.default_first_payment_date()).
    first_payment_date: date | None = None


@dataclass
class CreditorRules:
    max_terms: int
    max_payments: int
    min_payment_cents: int
    max_token_pays: int
    min_payment_tiers: list[tuple[int, int]]  # [(from_payment_1based, min_cents), ...]
    # Two independent creditor flags (both default False):
    #   even_pays            -> every creditor payment must be equal (ballooning is irrelevant).
    #   is_ballooning_allowed -> the final payment may absorb the remainder (a "balloon").
    # When NOT ballooning (and not even), the payment structure is bounded to at most
    # `max_segments` distinct payment levels so it can't fan out into an arbitrarily
    # complex staircase. The actual shape is whatever the objective produces
    # (maximize fee collected upfront / keep creditor payments low early).
    even_pays: bool
    is_ballooning_allowed: bool
    max_segments: int
    bank_fee_cents: int
    program_fee_pct: float


def offer_total_cents(offer: Offer) -> int:
    return pct_of_cents(offer.settlement_pct, offer.creditor_balance_cents)


def program_fee_cents(offer: Offer, rules: CreditorRules) -> int:
    return pct_of_cents(rules.program_fee_pct, offer.original_balance_cents)
