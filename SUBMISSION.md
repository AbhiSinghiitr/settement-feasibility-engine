# Settlement Feasibility & Fee Engine — Submission Notes

`README.md` is the original scaffold and is kept as-shipped, so its "Layout"
section and setup instructions are now slightly out of date against the
actual repo. This file is the up-to-date entry point: what's here, how to
run it, and the write-up the task asks for (approach, shape interpretation,
assumptions, edge cases, and why it's correct). For a short, plain-language
walkthrough of how the algorithm and data flow work, see
**[ARCHITECTURE.md](./ARCHITECTURE.md)**.

## Setup & run

```bash
pip install -r requirements.txt

python run.py cases/case1_feasible_even   # evaluate a single case, prints the Result as JSON
pytest -q                                  # 42 tests
```

## Current layout

```
feasibility/
├── money.py, dates.py, models.py, loaders.py, output.py   # utilities, data model, JSON I/O, output contract
├── shapes/       floors.py, validate.py, even.py, stepped.py   # payment-shape construction
├── simulation/   ledger.py, fee_placement.py                    # ledger replay + front-loaded fee placement
├── solve/        search.py, minima.py                            # k-search (Part 1), binary-search minima (Part 2)
└── engine.py                                                       # evaluate_offer() — orchestration only
cases/            four provided example cases
tests/            46 tests across 6 files (see ARCHITECTURE.md for the module map)
```

## Approach and alternatives considered

The core idea: **fee front-loading is the only real optimization target**;
the shape (even/staircase/balloon) is a side effect of which flags the
creditor sets, not a separate algorithm to design per shape. So the solver
has one shape-construction function that both staircase and balloon reduce
to (parameterized by whether the segment count is capped), one ledger
simulator, one greedy fee-placement routine, and a brute-force search over
the number of payments `k`. Full reasoning, including a construction bug
caught before writing code, is in ARCHITECTURE.md.

Alternatives considered and rejected:
- **A smarter (DP / pruned) search over `k`** instead of trying every value
  1..k_upper — rejected because `k_upper` is small in every realistic case
  (a multi-year plan has on the order of tens of payments), so brute force
  is both fast enough and much easier to verify correct than a cleverer
  formulation would be.
- **Re-simulating the ledger once per candidate date** in the fee-placement
  greedy (the first working version did this — `O(D²log D)`) — replaced with
  one simulation pass plus a suffix-min precomputation (`O(D log D)`), since
  "how much fee can I take here" turned out to depend only on a suffix
  minimum that doesn't change shape as the greedy proceeds, only shifts by a
  constant.
- **Recomputing each `k`'s floor array from scratch** inside the shape
  constructors — since a position's floor never actually depends on `k`,
  the original per-`k` `build_floors(k, rules)` call redid the same work up
  to `k` times across the search. Replaced with computing the floor array
  once up to `k_upper` and slicing a `[:k]` prefix per `k`.
- **Recomputing every rule at every position** inside `build_floors` itself
  (`O(k · T)` for `T` tiers — each position rescanned the whole tier list)
  — replaced with writing each breakpoint's bump (a tier's `from_position`,
  or the token-pay cutoff) directly into the output list at its own index,
  then one forward pass carrying the running floor across the flat gaps
  between them (`O(k + T)`). No intermediate dict — the output list doubles
  as the breakpoint scratch space. Exercised by
  `test_build_floors_tricky_multi_tier_case` (unsorted tiers, two tiers
  landing on the same position, one tier past `k`).
- **Closed-form formulas for the front-loaded fee split** instead of a
  greedy walk — rejected because the greedy is provably optimal and much
  easier to reason about than deriving a formula that has to account for
  arbitrary ledger activity (fixed debits, uneven draft cadence) in between.
- **Splitting the staircase remainder evenly across all spare segments**
  instead of concentrating it into one trailing position — the initial
  design did this and it under-front-loads (caught by hand-tracing the
  spec's own worked example before writing any implementation code).

## Shape interpretation (even / staircase / balloon)

For every shape, once the payment array is fixed, the **fee** on top is
placed the same way: greedily, earliest date first — take as much fee as
possible without ever risking a later date going negative, then move to the
next date. What differs between the three is only how the *payment array
itself* is built, which changes how much cash is left free for that greedy
fee placement to work with.

- **`even_pays`**: all payments equal; remainder cents (when `offer_total`
  doesn't divide evenly by `k`) go onto the *latest* payments so the
  sequence stays non-decreasing. There's no per-payment greedy choice here
  — the shape is fixed by the spec. The greedy lever is `k` itself: more
  payments means each one is smaller, which frees more cash earlier for the
  fee — so the search naturally favors the largest `k` that's still
  cash-flow-feasible.
- **`is_ballooning_allowed`**: every payment but the last sits at its own
  individual minimum (token-pay and tier rules applied per-position, no
  merging), and the final payment absorbs whatever's left. This *is* the
  greedy answer: each early position takes the smallest amount the rules
  allow, so nothing more than necessary is ever paid out early — no other
  valid balloon array can free up more cash sooner. No segment cap
  constrains it.
- **Neither flag set (staircase)**: same greedy idea as balloon — stay at
  the true minimum for as long as the segment budget allows — but capped at
  `max_segments` distinct payment levels. Positions are grouped into runs by
  their natural tier floor; if there are more natural tiers than
  `max_segments` allows, the excess tail tiers get merged into one raised
  level (falling back to whichever grouping is cheapest overall, if the
  greedy grouping alone can't reach `offer_total` — see "Why this is
  correct" below). If there's spare segment budget left over instead, the
  single trailing position absorbs the remainder rather than raising the
  whole tail run together — this is what makes the staircase front-load as
  aggressively as the segment cap permits.
- **Token pays and tiers interacting with a final balloon payment**: both
  rules are folded into the one floor computation (`shapes/floors.py::build_floors`),
  applied uniformly regardless of whether a position ends up being the final
  balloon payment — so a balloon's last payment automatically respects the
  token-pay cap and any tier that applies at its position, with no special
  case needed.

## Assumptions

1. The offer's balance field is read as `creditor_balance_cents` (matching
   the spec's intent to avoid colliding with the client's
   `current_balance_cents`); the loader also accepts the older
   `current_balance_cents` key for compatibility with existing fixtures.
2. Ties among equally front-loaded `(k, shape)` candidates are broken toward
   the smallest `k`.
3. The Part 2 lump sum is placed at `as_of_date + 1 day` (the earliest
   modifiable date) rather than searched over every possible date — an
   earlier lump is always at least as useful as a later one of the same size.
4. "Every future draft" (for the monthly increment) means every ledger entry
   with `type=credit` dated after `as_of_date`, counted per entry.
5. When there's spare segment budget beyond what tiers require, the entire
   staircase remainder is concentrated into a single trailing position
   rather than spread across multiple elevated positions (the most
   front-loaded choice — see "Why this is correct" below).

## Known edge cases / limitations

- If `first_payment_date` falls after the horizon (`last_draft_date`), no
  schedule can ever be placed — this is reported as infeasible with
  `within_guardrail: false` and an explanatory reason, since no amount of
  extra funding can fix a structural scheduling impossibility.
- If `min_payment_cents` alone exceeds `offer_total` for every possible `k`,
  the same applies — unfixable by money, reported accordingly rather than
  as a misleading guardrail failure.
- `max_segments = 1` without `even_pays` only produces a valid staircase
  when `offer_total` divides `k` exactly (one shared level can't absorb a
  remainder without becoming a second level) — this falls out of the
  generic validator, not special-cased.
- The `k`-search itself is brute-force — every `k` from 1 to `k_upper`, no
  pruning (see ARCHITECTURE.md for why that's the right call at realistic
  sizes). It would need pruning or a smarter search if a creditor's
  `max_payments` ever ran into the thousands.
- A rare edge case (a creditor with more pricing tiers than `max_segments`
  allows) is where the greedy construction isn't provably optimal, though it
  still always finds a valid schedule — see the closing caveat below.

## Why this is correct

Short version, meant for explaining out loud.

**Is it deterministic?** Yes. Every step is a plain function of the input —
no randomness, no I/O, no dependence on set/dict iteration order. Same
input always produces the same schedule.

**Does it collect the fee as early as possible?** Yes, for two reasons.
First, the payment array itself is built to be as cheap as possible early
on (see "Shape interpretation" above) — no other valid array for that `k`
can free up more cash sooner. Second, given that fixed array, the fee
placement is greedy and safe: at each date, take the most fee possible
without risking a future date going negative — checked by simulating the
ledger once and seeing how low the balance ever dips downstream. Since
delaying fee collection can only ever help future dates, never hurt them,
grabbing the max right now is always the safe — and best — choice.

**If a feasible schedule exists, will we find it?** Yes. For each `k`, we
build the most forgiving array possible for the account's cash flow — the
one that uses the least money as early as possible. If even that one can't
keep the balance non-negative, no other valid array for that `k` could
either. So checking just that one array per `k` is enough to know whether
`k` can ever work, and every `k` up to the max allowed gets checked.

**Are the minimum lump sum and monthly increase actually the minimum?**
Yes, via binary search — which works here because adding money never hurts.
More cash on any date can only raise the balance from that point on, never
lower it. So as the extra amount increases from 0, the answer flips from
"not enough" to "enough" exactly once, never back and forth — exactly what
binary search needs, and it lands on the exact cent where the flip happens,
not an estimate. Same as Part 1, this is just repeated calls to a pure
feasibility check, so it's deterministic too.

**One honest caveat.** In the rare edge case flagged above — a creditor
with more pricing tiers than `max_segments` allows, *and* an `offer_total`
that lands in a narrow band where the greedy grouping alone can't reach it
— the construction falls back to whichever grouping is cheapest overall.
That fallback always produces *a* valid, working schedule, just not
guaranteed to be the most front-loaded one possible in that one narrow
scenario. Doesn't come up in any of the provided test cases.

## Tests

46 tests across `tests/test_smoke.py`, `test_cases.py` (the 4 provided
cases), `test_shapes.py`, `test_ledger.py`, `test_fee_placement.py`, and
`test_minima.py` — covering even/staircase/balloon construction, token-pay
and tier floors, the `max_segments` cap, exact-sum, the date-by-date
simulation (same-day ordering, a balance hitting exactly $0), the horizon
limit, fee-before-first-payment compliance, and both Part 2 minima with
their guardrails. Run with `pytest -q`.
