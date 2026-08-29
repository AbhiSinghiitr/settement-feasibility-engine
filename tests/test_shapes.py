"""Unit tests for feasibility/shapes.py: floors, token-pay/tiers, max_segments,
exact-sum, and the even/staircase/balloon constructions."""

from __future__ import annotations

from feasibility.models import CreditorRules
from feasibility.shapes.even import build_even
from feasibility.shapes.floors import build_floors
from feasibility.shapes.stepped import build_balloon, build_staircase


def _rules(**overrides) -> CreditorRules:
    base = dict(
        max_terms=12,
        max_payments=12,
        min_payment_cents=2500,
        max_token_pays=6,
        min_payment_tiers=[],
        even_pays=False,
        is_ballooning_allowed=False,
        max_segments=2,
        bank_fee_cents=500,
        program_fee_pct=0.2,
    )
    base.update(overrides)
    return CreditorRules(**base)


def test_build_floors_flat_no_tiers_no_token_limit():
    rules = _rules(max_token_pays=100)
    assert build_floors(4, rules) == [2500, 2500, 2500, 2500]


def test_build_floors_token_pay_cap():
    # only 2 positions may sit exactly at the base minimum; position 3+ must exceed it
    rules = _rules(max_token_pays=2, min_payment_tiers=[])
    floors = build_floors(4, rules)
    assert floors == [2500, 2500, 2501, 2501]


def test_build_floors_tier_step_up():
    rules = _rules(max_token_pays=100, min_payment_tiers=[(3, 5000)])
    floors = build_floors(5, rules)
    assert floors == [2500, 2500, 5000, 5000, 5000]


def test_build_floors_tier_and_token_pay_combine():
    # tier floor at position 3+, token cap also forces >base from position 3+;
    # the max of the two applies at every position
    rules = _rules(max_token_pays=2, min_payment_tiers=[(4, 5000)])
    floors = build_floors(5, rules)
    assert floors == [2500, 2500, 2501, 5000, 5000]


def test_build_floors_tricky_multi_tier_case():
    # Unsorted tiers, two tiers landing on the very same position (must
    # merge via max, not overwrite one another), and a tier past k that
    # should have no effect at all.
    rules = _rules(
        min_payment_cents=1000,
        max_token_pays=3,
        min_payment_tiers=[(6, 5000), (4, 4000), (4, 4500), (20, 9000)],
    )
    assert build_floors(8, rules) == [1000, 1000, 1000, 4500, 4500, 5000, 5000, 5000]


def test_even_pays_remainder_goes_to_latest_payments():
    rules = _rules(even_pays=True, min_payment_cents=25)
    result = build_even(build_floors(3, rules), 100)
    assert result.valid
    assert sum(result.payments) == 100
    assert result.payments == [33, 33, 34]
    assert all(a <= b for a, b in zip(result.payments, result.payments[1:]))


def test_even_pays_exact_division():
    rules = _rules(even_pays=True, min_payment_cents=25)
    result = build_even(build_floors(4, rules), 400)
    assert result.payments == [100, 100, 100, 100]


def test_even_pays_rejects_when_below_floor():
    rules = _rules(even_pays=True, min_payment_cents=2500)
    result = build_even(build_floors(4, rules), 1000)  # 250/payment < floor 2500
    assert not result.valid


def test_staircase_uses_at_most_max_segments_distinct_levels():
    rules = _rules(min_payment_tiers=[(7, 5000)], max_segments=2, max_token_pays=6)
    result = build_staircase(build_floors(12, rules), 60000, rules)
    assert result.valid
    assert len(set(result.payments)) <= 2
    # tier floor for positions 7+ must be respected
    assert all(p >= 5000 for p in result.payments[6:])
    assert sum(result.payments) == 60000


def test_staircase_non_decreasing_and_exact_sum():
    rules = _rules(min_payment_tiers=[(4, 4000)], max_segments=3)
    result = build_staircase(build_floors(6, rules), 25000, rules)
    assert result.valid
    assert sum(result.payments) == 25000
    assert all(a <= b for a, b in zip(result.payments, result.payments[1:]))


def test_staircase_falls_back_to_min_cost_partition_when_front_load_ungrouping_unreachable():
    # 3 natural tiers (floors [100,100,200,200,500,500]), max_segments=2:
    # merging the *last* two tiers (front-loading's preference) needs a
    # minimum of 100*2+500*4=2200. Merging the *first* two tiers instead
    # only needs 200*4+500*2=1800. For offer_total=2000, the front-loaded
    # grouping alone can't reach it, but a <=2-segment staircase genuinely
    # exists — the fallback must find it rather than reporting infeasible.
    rules = _rules(
        min_payment_cents=100,
        max_token_pays=100,
        min_payment_tiers=[(3, 200), (5, 500)],
        max_segments=2,
    )
    result = build_staircase(build_floors(6, rules), 2000, rules)
    assert result.valid
    assert result.payments == [200, 200, 200, 200, 600, 600]
    assert len(set(result.payments)) <= 2


def test_staircase_prefers_front_loaded_grouping_when_it_is_reachable():
    # Same tiers/cap as above, but offer_total=2200 is exactly what the
    # front-loaded grouping (merge the last two tiers) needs on its own —
    # no fallback required, and it stays the most front-loaded choice.
    rules = _rules(
        min_payment_cents=100,
        max_token_pays=100,
        min_payment_tiers=[(3, 200), (5, 500)],
        max_segments=2,
    )
    result = build_staircase(build_floors(6, rules), 2200, rules)
    assert result.valid
    assert result.payments == [100, 100, 500, 500, 500, 500]


def test_staircase_tries_an_alternative_grouping_when_the_first_ones_remainder_does_not_divide_evenly():
    # Same tiers/cap as above (floors [100,100,200,200,500,500], max_segments=2,
    # so there's no spare segment budget — whichever grouping is used must
    # move its whole final group together). offer_total=2202: the
    # front-loaded grouping (merge tiers 2+3) costs a minimum of 2200,
    # leaving a remainder of 2 that does NOT divide evenly across its
    # 4-position final group — naively bumping 2 of those 4 positions by a
    # cent each would silently exceed the segment cap. Merging tiers 1+2
    # instead costs 1800, leaving a remainder of 402 that DOES divide evenly
    # across its 2-position final group (201 each) — a genuinely valid
    # 2-segment staircase that the construction must find instead of
    # reporting this k infeasible.
    rules = _rules(
        min_payment_cents=100,
        max_token_pays=100,
        min_payment_tiers=[(3, 200), (5, 500)],
        max_segments=2,
    )
    result = build_staircase(build_floors(6, rules), 2202, rules)
    assert result.valid
    assert result.payments == [200, 200, 200, 200, 701, 701]
    assert len(set(result.payments)) <= 2
    assert sum(result.payments) == 2202


def test_staircase_front_loads_when_spare_segment_budget_available():
    # No tiers (flat floor), 2 segments allowed: should concentrate the whole
    # remainder into the single trailing payment rather than raising everyone
    # together — this is the spec's own worked micro-example for the
    # front-loading objective.
    rules = _rules(min_payment_tiers=[], max_segments=2, max_token_pays=100, min_payment_cents=2500)
    result = build_staircase(build_floors(3, rules), 25000, rules)
    assert result.valid
    assert result.payments == [2500, 2500, 20000]


def test_staircase_max_segments_one_requires_exact_divisibility():
    rules = _rules(min_payment_tiers=[], max_segments=1, min_payment_cents=2500, max_token_pays=100)
    floors = build_floors(4, rules)
    ok = build_staircase(floors, 10000, rules)  # divides evenly: 2500 each
    assert ok.valid
    assert ok.payments == [2500, 2500, 2500, 2500]

    bad = build_staircase(floors, 10001, rules)  # remainder cent can't be absorbed with 1 segment
    assert not bad.valid


def test_balloon_ignores_segment_cap_and_uses_individual_floors():
    rules = _rules(
        is_ballooning_allowed=True,
        max_segments=1,  # should be irrelevant for balloon
        min_payment_tiers=[(4, 5000)],
        max_token_pays=100,
        min_payment_cents=2500,
    )
    result = build_balloon(build_floors(5, rules), 40000)
    assert result.valid
    # positions 1-3 at their own floor (tier only kicks in from position 4),
    # position 4 at its own tier floor, position 5 (final) absorbs the remainder
    assert result.payments[:4] == [2500, 2500, 2500, 5000]
    assert result.payments[4] >= 5000
    assert sum(result.payments) == 40000


def test_balloon_final_payment_respects_token_pay_cap():
    # k=4, max_token_pays=2: floor(3) and floor(4) must exceed base even under
    # ballooning (the per-position floor applies uniformly, balloon or not).
    rules = _rules(is_ballooning_allowed=True, max_token_pays=2, min_payment_tiers=[], min_payment_cents=2500)
    result = build_balloon(build_floors(4, rules), 20000)
    assert result.valid
    assert result.payments[0] == 2500
    assert result.payments[1] == 2500
    assert result.payments[2] >= 2501
    assert result.payments[3] >= 2501


def test_shape_rejects_when_offer_total_below_minimal_floor_sum():
    rules = _rules(min_payment_cents=2500, max_token_pays=100, min_payment_tiers=[])
    result = build_staircase(build_floors(4, rules), 5000, rules)  # 4 * 2500 = 10000 > 5000
    assert not result.valid


def test_shape_builders_accept_a_prefix_slice_of_a_larger_floor_array():
    # search.py builds one floors array up to k_upper and slices a prefix per
    # k, rather than recomputing build_floors(k, rules) for every k — the
    # slice must be equivalent to computing that k's floors directly.
    rules = _rules(min_payment_tiers=[(4, 5000)], max_segments=2, max_token_pays=2)
    floors_upper = build_floors(8, rules)
    assert floors_upper[:5] == build_floors(5, rules)
    via_slice = build_staircase(floors_upper[:5], 30000, rules)
    via_direct = build_staircase(build_floors(5, rules), 30000, rules)
    assert via_slice == via_direct
