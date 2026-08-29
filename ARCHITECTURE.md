# How It Works

## The problem, in one line

Given a client's account, a settlement offer, and a creditor's rules — build
a payment schedule that never lets the account go negative and collects our
fee as early as possible. If no schedule works, find the smallest amount of
extra money that would fix it.

## The approach, in 4 steps

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
   collects the fee earliest.

If step 4 never finds a working option, binary-search for the smallest lump
sum (or smallest monthly increase) that would make one exist — see "Part 2"
below.

## Flow

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

## Part 2: minimum extra funding

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

## Where the code lives

- `shapes/` — builds the payment array for a given `k`
- `simulation/` — replays the ledger, places the fee
- `solve/search.py` — tries every `k` (Part 1's loop; also reused as the
  cheap yes/no check Part 2's binary search calls)
- `solve/minima.py` — the two binary searches (Part 2)
- `engine.py` — wires it all together

## Design choices worth knowing

- **Floors computed once, not per-`k`.** A position's minimum payment
  doesn't depend on `k`, so it's built once up to the max `k` and sliced,
  instead of recomputed on every loop iteration.
- **Fee placement is one pass, not one simulation per date.** Simulate the
  ledger once with zero fee, take a running minimum from the end backward,
  then walk forward taking as much fee as that minimum allows.
- **Brute-force over `k`, on purpose.** The max number of payments is
  always small in practice (tens, not thousands), so trying every `k` is
  fast and trivially easy to verify — no need for anything cleverer.

## Speed

Roughly `O(k_max × number of ledger dates)` for the whole search — the cost
is one ledger replay per candidate `k`. Never a real bottleneck at the
sizes this problem actually has.
