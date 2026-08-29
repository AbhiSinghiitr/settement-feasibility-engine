# Settlement Feasibility & Fee Engine — Solution

The full write-up: setup, approach, alternatives, assumptions, edge cases,
why the solution is correct, and the implementation architecture.
`README.md` has the quick orientation and points here for everything else.

## Setup & run

```bash
pip install -r requirements.txt

python run.py cases/case1_feasible_even   # evaluate a single case, prints the Result as JSON
pytest -q                                  # 46 tests
```

---

## Submission

### Approach and alternatives considered

The core idea: **fee front-loading is the only real optimization target**;
the shape (even/staircase/balloon) is a side effect of which flags the
creditor sets, not a separate algorithm to design per shape. So the solver
has one shape-construction function that both staircase and balloon reduce
to (parameterized by whether the segment count is capped), one ledger
simulator, one greedy fee-placement routine, and a brute-force search over
the number of payments `k`. Full reasoning, including a construction bug
caught before writing code, is in the **Architecture** section below.

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

### Shape interpretation (even / staircase / balloon)

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
  their natural tier floor, and if there's spare segment budget left over,
  the single trailing position absorbs the remainder rather than raising the
  whole tail run together — this is what makes the staircase front-load as
  aggressively as the segment cap permits. If there are more natural tiers
  than `max_segments` allows, some tiers must merge; every way of grouping
  them is tried, most front-loaded first, until one both reaches
  `offer_total` and can be split without exceeding the segment cap — see
  "Why this is correct" below for why a single "obvious" grouping isn't
  always enough.
- **Token pays and tiers interacting with a final balloon payment**: both
  rules are folded into the one floor computation (`shapes/floors.py::build_floors`),
  applied uniformly regardless of whether a position ends up being the final
  balloon payment — so a balloon's last payment automatically respects the
  token-pay cap and any tier that applies at its position, with no special
  case needed.

### Assumptions

1. The offer's balance field is read as `creditor_balance_cents` (matching
   the spec's intent to avoid colliding with the client's
   `current_balance_cents`); the loader also accepts the older
   `current_balance_cents` key for compatibility with existing fixtures.
2. Ties among equally front-loaded `(k, shape)` candidates are broken toward
   the smallest `k`.
3. The lump sum (below) is placed at `as_of_date + 1 day` (the earliest
   modifiable date) rather than searched over every possible date — an
   earlier lump is always at least as useful as a later one of the same size.
4. "Every future draft" (for the monthly increment) means every ledger entry
   with `type=credit` dated after `as_of_date`, counted per entry.
5. When there's spare segment budget beyond what tiers require, the entire
   staircase remainder is concentrated into a single trailing position
   rather than spread across multiple elevated positions (the most
   front-loaded choice — see "Why this is correct" below).

### Known edge cases / limitations

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
  pruning (see the **Architecture** section below for why that's the right
  call at realistic sizes). It would need pruning or a smarter search if a
  creditor's `max_payments` ever ran into the thousands.
- When a creditor has more pricing tiers than `max_segments` allows, the
  "obvious" grouping (merge the latest tiers together) can sometimes leave a
  leftover remainder that doesn't divide evenly across the merged group —
  naively spreading it would silently exceed the segment cap. The
  construction handles this by trying every way to group the tiers, most
  front-loaded first, until one both reaches `offer_total` and respects the
  cap — see the closing note below.

### Why this is correct

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

**If a feasible schedule exists, will we find it?** Yes, at two levels.
Structurally, for a given `k`, the construction doesn't just try one way of
grouping the creditor's tiers into `max_segments` levels — it tries every
way, from most to least front-loaded, until one both sums exactly to
`offer_total` and respects the cap. (An earlier version tried only the
"obvious" grouping and could wrongly reject a `k` that a different, equally
valid grouping would have made to work — fixed by searching all of them.)
Then, cash-flow-wise: whichever grouping is found builds the most forgiving
array possible for the account's cash flow — the one that uses the least
money as early as possible. If even that can't keep the balance
non-negative, no other valid array for that `k` could either. So checking
one array per `k` is enough to know whether `k` can ever work, and every
`k` up to the max allowed gets checked.

**Are the minimum lump sum and monthly increase actually the minimum?**
Yes, via binary search — which works here because adding money never hurts.
More cash on any date can only raise the balance from that point on, never
lower it. So as the extra amount increases from 0, the answer flips from
"not enough" to "enough" exactly once, never back and forth — exactly what
binary search needs, and it lands on the exact cent where the flip happens,
not an estimate. Same as above, this is just repeated calls to a pure
feasibility check, so it's deterministic too.

**One honest caveat.** When a creditor has more tiers than `max_segments`
allows, the search tries every way to group them, most front-loaded first,
and stops at the first one that reaches `offer_total` exactly without
exceeding the cap — so it's exhaustive, not a guess. What isn't formally
proven here is that the *first* grouping to succeed is always the most
front-loaded one *among every alternative that would also have worked* —
that's true whenever the top-priority grouping itself succeeds (the common
case, and every provided test case), but for the rarer situation where it
has to fall through to a later, less-preferred grouping, front-loading
optimality is a well-justified design intent rather than a proven theorem.

### Tests

46 tests across `tests/test_smoke.py`, `test_cases.py` (the 4 provided
cases), `test_shapes.py`, `test_ledger.py`, `test_fee_placement.py`, and
`test_minima.py` — covering even/staircase/balloon construction, token-pay
and tier floors, the `max_segments` cap, exact-sum, the date-by-date
simulation (same-day ordering, a balance hitting exactly $0), the horizon
limit, fee-before-first-payment compliance, and both Part 2 minima with
their guardrails. Run with `pytest -q`.

---

## Architecture

### The problem, in one line

Given a client's account, a settlement offer, and a creditor's rules — build
a payment schedule that never lets the account go negative and collects our
fee as early as possible. If no schedule works, find the smallest amount of
extra money that would fix it.

### The approach, in 4 steps

1. **Build a payment shape** for a chosen number of payments `k` — an array
   that's non-decreasing, respects every minimum, and sums exactly to the
   settlement amount. "Staircase" and "balloon" are the *same* construction;
   balloon is just staircase with no cap on how many different payment
   amounts it's allowed to use.
2. **Replay the ledger** day by day (credits before debits) to check the
   balance never goes negative.
3. **Place the fee greedily** — for that fixed payment schedule, collect as
   much fee as possible on the earliest date, then the next, and so on,
   without ever risking a later date going negative.
4. **Try every `k`** from 1 up to the max allowed, and keep whichever one
   finishes collecting the fee on the earliest possible date (ties broken
   toward the smallest `k`).

If step 4 never finds a working option, binary-search for the smallest lump
sum (or smallest monthly increase) that would make one exist — see "Part 2
implementation" below.

### Flow

```
client.json / offer.json / rules.json
        │  parsed into Client / Offer / CreditorRules
        ▼
engine.evaluate_offer()
        │
        ▼
solve/search.py — Part 1
        │
        │   for k = 1, 2, 3, ... up to k_max:
        │       shapes/          build the payment array for this k
        │       simulation/      check it against the ledger,
        │                        place the fee as early as possible
        │       keep the best (most front-loaded) k seen so far
        │
        ├── some k worked  ──────────────────────────► return that schedule
        │
        └── nothing worked
                    │
                    ▼
            solve/minima.py — Part 2
                    │
                    │   binary-search the smallest lump sum
                    │   binary-search the smallest monthly increase
                    │   (both re-use the *same* "try every k" loop above,
                    │    just with the extra money added to the ledger first)
                    │
                    ▼
            apply guardrails ──────────────────────────► return both amounts
```

### Part 2 implementation: minimum extra funding

When no `k` produces a working schedule, two numbers are computed
independently:

- **Minimum lump sum** — the smallest one-time deposit, placed on the
  earliest possible date, that would make some `k` work.
- **Minimum monthly increase** — the smallest amount added to *every* future
  draft that would make some `k` work.

**How:** binary search. `feasible_at(amount)` adds that much extra money to
the ledger and re-runs the exact same "try every `k`" loop from Part 1 — but
using a cheaper check: instead of front-loading the fee, just dump the
*entire* fee on the very last possible date and see if the ledger still
stays non-negative. That's the most forgiving placement possible, so it's
the right question to ask when all you need is a yes/no answer.

**Why binary search works here:** adding money never hurts — more cash on
any date can only raise the balance from that point on, never lower it. So
as the extra amount increases from `0`, the answer flips from "not enough"
to "enough" exactly once, never back and forth. That's exactly the
condition binary search needs, and it lands on the exact cent where the
flip happens.

**Guardrails:** both numbers are then checked against a cap (a lump sum
above 65% of the settlement amount, or a monthly increase above the larger
of a flat $100 or 40% of the draft amount, is rejected as unreasonable even
if it would technically work).

### Where the code lives

```
feasibility/
├── money.py, dates.py, models.py, loaders.py, output.py   # utilities, data model, JSON I/O, output contract
├── shapes/       floors.py, validate.py, even.py, stepped.py   # payment-shape construction
├── simulation/   ledger.py, fee_placement.py                    # ledger replay + front-loaded fee placement
├── solve/        search.py, minima.py                            # k-search (Part 1), binary-search minima (Part 2)
└── engine.py                                                       # evaluate_offer() — orchestration only
cases/            four provided example cases
tests/            46 tests across 6 files
```

`solve/search.py`'s "try every `k`" loop is reused twice: once in full (front
loading the fee) for Part 1, and once as a cheap yes/no check for Part 2's
binary search — no separate feasibility algorithm exists.

### Design choices worth knowing

- **Floors computed once, not per-`k`.** A position's minimum payment
  doesn't depend on `k`, so it's built once up to the max `k` and sliced,
  instead of recomputed on every loop iteration.
- **Fee placement is one pass, not one simulation per date.** Simulate the
  ledger once with zero fee, take a running minimum from the end backward,
  then walk forward taking as much fee as that minimum allows.
- **Brute-force over `k`, on purpose.** The max number of payments is
  always small in practice (tens, not thousands), so trying every `k` is
  fast and trivially easy to verify — no need for anything cleverer.

