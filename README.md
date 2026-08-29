# Settlement Feasibility & Fee Engine — Take-home

Welcome, and thanks for taking the time. The full problem is in
[`ASSIGNMENT.md`](./ASSIGNMENT.md). This README is just orientation — for
the full write-up (approach, alternatives, assumptions, edge cases, why it's
correct, and the implementation architecture), see
[`SOLUTION.md`](./SOLUTION.md).

## The task in one line

Given a client's escrow account, a settlement offer, and a creditor's rules,
decide whether the offer is affordable (and schedule it, collecting our fee as
early as allowed) or — if not — compute the minimum extra funding needed.

## Setup

```bash
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt
```

## Layout

```
retape_ai_takehome/
├── ASSIGNMENT.md            # full specification
├── SOLUTION.md              # approach, alternatives, assumptions, architecture — start here
├── feasibility/
│   ├── money.py, dates.py, models.py, loaders.py, output.py   # utilities, data model, JSON I/O
│   ├── shapes/               # payment-shape construction (even / staircase / balloon)
│   ├── simulation/           # ledger replay + front-loaded fee placement
│   ├── solve/                # k-search (Part 1) + binary-search minima (Part 2)
│   └── engine.py             # evaluate_offer() — the one entry point
├── cases/                   # four example cases (client.json / offer.json / creditor_rules.json)
│   ├── case1_feasible_even
│   ├── case2_infeasible_minima
│   ├── case3_balloon
│   └── case4_tiers
├── tests/                    # 46 tests
├── run.py                   # python run.py cases/<case>
└── requirements.txt
```

## Run

```bash
# evaluate a single case (prints the Result as JSON)
python run.py cases/case1_feasible_even

# tests
pytest -q
```

All 46 tests pass — the 4 provided cases plus coverage for shapes, floors,
the ledger simulation, fee placement, and both Part 2 minima. See
`SOLUTION.md` for what each test file covers.

## What to submit

Covered in full in [`SOLUTION.md`](./SOLUTION.md): approach and the
alternatives considered, the payment-shape interpretation (even / staircase
/ balloon), assumptions made, and known edge cases / limitations.
