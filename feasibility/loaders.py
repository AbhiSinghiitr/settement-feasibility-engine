"""JSON loaders for a case folder's three files: client.json, offer.json,
creditor_rules.json.
"""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

from feasibility.models import Client, CreditorRules, LedgerEntry, Offer

# Used when creditor_rules.json omits max_segments entirely.
DEFAULT_MAX_SEGMENTS = 4


def _d(s: str) -> date:
    return date.fromisoformat(s)


def load_client(path: str | Path) -> Client:
    raw = json.loads(Path(path).read_text())
    return Client(
        draft_amount_cents=int(raw["draft_amount_cents"]),
        draft_day=int(raw["draft_day"]),
        first_draft_date=_d(raw["first_draft_date"]),
        last_draft_date=_d(raw["last_draft_date"]),
        as_of_date=_d(raw["as_of_date"]),
        current_balance_cents=int(raw["current_balance_cents"]),
        ledger=[
            LedgerEntry(_d(e["date"]), int(e["amount_cents"]), e["type"])
            for e in raw.get("ledger", [])
        ],
    )


def load_offer(path: str | Path) -> Offer:
    raw = json.loads(Path(path).read_text())
    fpd = raw.get("first_payment_date")
    # The spec renamed this field to creditor_balance_cents to avoid
    # colliding with the client's current_balance_cents; the shipped
    # fixtures still use the old key, so accept either.
    balance = raw.get("creditor_balance_cents", raw.get("current_balance_cents"))
    return Offer(
        creditor=raw["creditor"],
        creditor_balance_cents=int(balance),
        original_balance_cents=int(raw["original_balance_cents"]),
        settlement_pct=float(raw["settlement_pct"]),
        first_payment_date=_d(fpd) if fpd else None,
    )


def load_creditor_rules(path: str | Path) -> CreditorRules:
    raw = json.loads(Path(path).read_text())
    return CreditorRules(
        max_terms=int(raw["max_terms"]),
        max_payments=int(raw["max_payments"]),
        min_payment_cents=int(raw["min_payment_cents"]),
        max_token_pays=int(raw["max_token_pays"]),
        min_payment_tiers=[(int(a), int(b)) for a, b in raw.get("min_payment_tiers", [])],
        even_pays=bool(raw.get("even_pays", False)),
        is_ballooning_allowed=bool(raw.get("is_ballooning_allowed", False)),
        max_segments=int(raw.get("max_segments", DEFAULT_MAX_SEGMENTS)),
        bank_fee_cents=int(raw["bank_fee_cents"]),
        program_fee_pct=float(raw["program_fee_pct"]),
    )


def load_case(case_dir: str | Path) -> tuple[Client, Offer, CreditorRules]:
    p = Path(case_dir)
    return (
        load_client(p / "client.json"),
        load_offer(p / "offer.json"),
        load_creditor_rules(p / "creditor_rules.json"),
    )
