"""Staircase and balloon: one construction, two segment-cap values.

Both start from the same place — every position at its own natural per-tier
floor, remainder absorbed at the end (that's the balloon case, cap=None,
unconditionally). Staircase is the same thing capped at `max_segments`
distinct levels:

- if the creditor's tiers already fit the cap, nothing changes — same
  balloon-style construction, just fit directly.
- if there are more tiers than the cap allows, some have to merge; every way
  of merging them is tried, most front-loaded first, until one both reaches
  offer_total and fits the cap exactly (SOLUTION.md has the full reasoning
  for why the "obvious" merge alone isn't always enough).
"""

from __future__ import annotations

from itertools import combinations

from feasibility.models import CreditorRules
from feasibility.shapes.validate import ShapeResult, validate_payments


def _grouped_runs(floors: list[int]) -> list[tuple[int, int, int]]:
    """[(start, end_exclusive, floor_value), ...] over consecutive equal floors."""
    runs: list[tuple[int, int, int]] = []
    start = 0
    for i in range(1, len(floors) + 1):
        if i == len(floors) or floors[i] != floors[start]:
            runs.append((start, i, floors[start]))
            start = i
    return runs


def _flatten(runs: list[tuple[int, int, int]], k: int) -> list[int]:
    payments = [0] * k
    for start, end, level in runs:
        for i in range(start, end):
            payments[i] = level
    return payments


def _run_cost(runs: list[tuple[int, int, int]]) -> int:
    return sum(level * (end - start) for start, end, level in runs)


def _partitions(runs: list[tuple[int, int, int]], groups: int):
    """Every way to merge `runs` into exactly `groups` contiguous groups,
    each merged group taking its last run's floor (floors only increase, so
    that's always the toughest requirement in the group).

    Yielded from most to least front-loaded: combinations() enumerates
    cut-points in increasing order, and a low cut-point keeps the earliest
    runs distinct for as long as possible (merging only the later ones) —
    exactly the preference order we want to try things in.
    """
    t = len(runs)
    for cuts in combinations(range(1, t), groups - 1):
        bounds = (0,) + cuts + (t,)
        yield [
            (runs[bounds[i]][0], runs[bounds[i + 1] - 1][1], runs[bounds[i + 1] - 1][2])
            for i in range(groups)
        ]


def _fit_exactly(
    partition: list[tuple[int, int, int]], offer_total: int, cap: int | None
) -> list[tuple[int, int, int]] | None:
    """If `partition` can be adjusted to sum to exactly offer_total without
    exceeding `cap` distinct levels, return the adjusted run list; else None.
    """
    remainder = offer_total - _run_cost(partition)
    if remainder < 0:
        return None
    if remainder == 0:
        return partition

    spare = None if cap is None else cap - len(partition)
    last_start, last_end, last_level = partition[-1]

    if spare is None or spare >= 1:
        # Front-load: absorb the whole remainder into a single trailing
        # position, leaving the rest of the group at its floor.
        if last_end - last_start > 1:
            return partition[:-1] + [
                (last_start, last_end - 1, last_level),
                (last_end - 1, last_end, last_level + remainder),
            ]
        return partition[:-1] + [(last_start, last_end, last_level + remainder)]

    # No spare distinct level: the whole final group must move together,
    # uniformly — only possible if the remainder divides evenly across it.
    count = last_end - last_start
    if remainder % count != 0:
        return None
    return partition[:-1] + [(last_start, last_end, last_level + remainder // count)]


def _build_stepped(floors: list[int], offer_total: int, cap: int | None) -> ShapeResult:
    k = len(floors)
    natural_runs = _grouped_runs(floors)
    t = len(natural_runs)

    # Balloon (cap=None), and the common staircase case: the creditor's
    # segment budget already covers every tier it defined, so every
    # position can sit in a group of its own natural size — no merging
    # needed, just fit the remainder onto the natural groups directly.
    if cap is None or t <= cap:
        fitted = _fit_exactly(natural_runs, offer_total, cap)
        if fitted is not None:
            return validate_payments(_flatten(fitted, k), offer_total, floors, cap)
        return ShapeResult([], False, "offer_total below minimal total for this k")

    # More natural tiers than the segment budget allows: some must merge.
    # Try every way to do it, most front-loaded first, until one both
    # reaches offer_total and fits exactly within the cap — see SOLUTION.md
    # for why trying just the "obvious" single grouping isn't always enough.
    for groups in range(cap, 0, -1):
        for partition in _partitions(natural_runs, groups):
            fitted = _fit_exactly(partition, offer_total, cap)
            if fitted is not None:
                return validate_payments(_flatten(fitted, k), offer_total, floors, cap)

    return ShapeResult([], False, "offer_total below minimal total for this k")


def build_staircase(floors: list[int], offer_total: int, rules: CreditorRules) -> ShapeResult:
    """`floors` is this k's per-position floor array — see solve/search.py."""
    return _build_stepped(floors, offer_total, cap=rules.max_segments)


def build_balloon(floors: list[int], offer_total: int) -> ShapeResult:
    """`floors` is this k's per-position floor array — see solve/search.py."""
    return _build_stepped(floors, offer_total, cap=None)
