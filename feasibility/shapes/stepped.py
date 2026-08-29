"""Staircase and balloon: one construction, two segment-cap values.

Both shapes keep every position at its natural per-tier floor for as long as
the segment budget allows, then concentrate the exact-sum remainder into the
fewest, latest position(s) possible (SOLUTION.md has the full
reasoning, including why this is the cash-flow-dominant construction among
every valid split for a given k):

- staircase: cap = rules.max_segments (a hard limit on distinct payment levels)
- balloon:   cap = None (unbounded — every position but the last sits at its
  own individual floor, and the final position absorbs the remainder)
"""

from __future__ import annotations

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


def _merge_tail(runs: list[tuple[int, int, int]], cap: int) -> list[tuple[int, int, int]]:
    """Keep the first cap-1 runs distinct; merge everything from the cap-th
    run onward into one tail run at the toughest floor in that range. The
    most front-loaded grouping *when it's achievable* — see
    _min_cost_partition for what happens when it isn't.
    """
    head = runs[: cap - 1]
    tail_start = head[-1][1] if head else 0
    tail_end = runs[-1][1]
    tail_level = runs[-1][2]
    return head + [(tail_start, tail_end, tail_level)]


def _min_cost_partition(runs: list[tuple[int, int, int]], cap: int) -> list[tuple[int, int, int]]:
    """The *cheapest* way to partition `runs` into at most `cap` contiguous
    groups — i.e. the true minimum total this k can possibly reach under the
    segment cap, over every valid grouping, not just the front-loaded one.

    Since floors only increase, a group's level is always its last run's
    floor, so this is the classic "partition a sorted sequence into <= cap
    contiguous segments minimizing sum(segment_max * segment_size)" — solved
    by DP over (how many runs considered, how many groups used so far).
    Only ever called as a fallback (see _build_stepped) when the
    front-loaded grouping alone can't reach offer_total, to guarantee a
    valid shape is found whenever one exists at all for this k.
    """
    t = len(runs)
    counts = [end - start for start, end, _ in runs]
    levels = [level for _, _, level in runs]
    prefix = [0] * (t + 1)
    for i in range(t):
        prefix[i + 1] = prefix[i] + counts[i]

    inf = float("inf")
    dp = [[inf] * (t + 1) for _ in range(cap + 1)]
    parent = [[-1] * (t + 1) for _ in range(cap + 1)]
    dp[0][0] = 0
    for groups_used in range(1, cap + 1):
        for i in range(groups_used, t + 1):
            for p in range(groups_used - 1, i):
                prev = dp[groups_used - 1][p]
                if prev == inf:
                    continue
                cost = prev + levels[i - 1] * (prefix[i] - prefix[p])
                if cost < dp[groups_used][i]:
                    dp[groups_used][i] = cost
                    parent[groups_used][i] = p

    best_groups = min(range(1, cap + 1), key=lambda j: dp[j][t])
    boundaries: list[tuple[int, int]] = []
    j, i = best_groups, t
    while j > 0:
        p = parent[j][i]
        boundaries.append((p, i))
        i, j = p, j - 1
    boundaries.reverse()
    return [(runs[p][0], runs[i - 1][1], runs[i - 1][2]) for p, i in boundaries]


def _build_stepped(floors: list[int], offer_total: int, cap: int | None) -> ShapeResult:
    k = len(floors)
    runs = _grouped_runs(floors)

    if cap is not None and len(runs) > cap:
        front_loaded = _merge_tail(runs, cap)
        if offer_total >= _run_cost(front_loaded):
            runs = front_loaded
        else:
            # The most front-loaded grouping can't reach offer_total on its
            # own; fall back to the total-minimizing partition, which is
            # achievable whenever *any* <=cap grouping is (see docstring).
            runs = _min_cost_partition(runs, cap)

    levels = [r[2] for r in runs]
    counts = [r[1] - r[0] for r in runs]
    minimal_total = sum(l * c for l, c in zip(levels, counts))
    remainder = offer_total - minimal_total
    if remainder < 0:
        return ShapeResult([], False, "offer_total below minimal total for this k")

    if remainder == 0:
        return validate_payments(_flatten(runs, k), offer_total, floors, cap)

    spare = None if cap is None else cap - len(runs)
    last_start, last_end, last_level = runs[-1]

    if spare is None or spare >= 1:
        # Front-load: absorb the whole remainder into a single trailing
        # position, leaving the rest of the run at its natural floor.
        if last_end - last_start > 1:
            runs[-1:] = [
                (last_start, last_end - 1, last_level),
                (last_end - 1, last_end, last_level + remainder),
            ]
        else:
            runs[-1] = (last_start, last_end, last_level + remainder)
        return validate_payments(_flatten(runs, k), offer_total, floors, cap)

    # No spare distinct level: raise the whole final run together, spreading
    # any leftover cents onto its latest positions.
    count = last_end - last_start
    add_base, add_rem = divmod(remainder, count)
    runs[-1] = (last_start, last_end, last_level + add_base)
    payments = _flatten(runs, k)
    for i in range(k - add_rem, k):
        payments[i] += 1
    return validate_payments(payments, offer_total, floors, cap)


def build_staircase(floors: list[int], offer_total: int, rules: CreditorRules) -> ShapeResult:
    """`floors` is this k's per-position floor array — see solve/search.py."""
    return _build_stepped(floors, offer_total, cap=rules.max_segments)


def build_balloon(floors: list[int], offer_total: int) -> ShapeResult:
    """`floors` is this k's per-position floor array — see solve/search.py."""
    return _build_stepped(floors, offer_total, cap=None)
