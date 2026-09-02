# In-Memory Account Ledger Core

Status: implemented and verified.

I implemented a typed, in-memory ledger core that replays the supplied six-day event stream in its original order. It reports daily closing balances, fee assessments, authorization states, errors, rounded interest accruals, and Day 6 capitalization.

## Requirements

- CPython 3.12 or newer.
- No third-party Python package or external service is required for the runtime, replay, or tests.
- Run every command from the repository root.

## How to run

### Green correctness suite

```bash
python3 -m unittest discover -s tests -p 'test_*.py' -v
```

Expected result: 57 tests pass and the process exits with status 0. This suite covers exact money, immutable journal invariants, policy decisions, all eight acceptance claims, the complete six-day projection, and boundary behavior.

### Assessment replay and report

```bash
python3 replay.py
```

Expected result: E1 through E10 appear in the supplied order, followed by the complete Day 1 through Day 6 financial report. The process exits with status 0.

### Required intentionally failing test

```bash
python3 -m unittest discover -s known_limitation -p 'test_*.py' -v
```

Expected result: exactly one test runs and fails, and the process exits with status 1. This is deliberate assessment evidence, not a broken correctness suite. It exposes that my bounded core rejects a post-finalization backdated credit instead of admitting it through a controlled append-only workflow that also corrects already-capitalized interest.

### Optional strict type check

```bash
pyright
```

Pyright is an optional, separately installed developer tool; it is not a runtime dependency. Pyright reports 0 errors and 0 warnings on the current tree in strict Python 3.12 mode.

## How to read the output

I print two views because this problem has two time axes plus immutable ingestion order.

1. The **processing trace** lists events in received order together with their outcomes and derived facts. `commit=N` is the atomic in-memory journal commit, not a Git commit. `booked=DN` is when the event was recorded; `value=DN` determines which historical closes its monetary effect changes.
2. The **daily financial view** is a final-known, value-dated projection using event knowledge through journal commit 10, followed by interest finalization at commit 11. It is not a reconstruction of only what was known on each original calendar day.

I never date-sort the events. E10 is therefore processed after E9 even though E10 is booked and value-dated Day 5. Its BHD postings still contribute to the Day 5 and Day 6 value-dated projections.

Claim-1's AED -370.00 is the Day 2 projection at `known_through=7` with `OVERDRAFT_FEE` postings excluded. E7 and its derived fees share atomic journal commit 7, so I do not claim that a separately stored pre-fee commit exists. The final-known Day 2 row is AED 225.00 because it includes the retained Day 2 fee and E9's later AED 620.00 compensating reversal. Those values answer different temporal questions.

In the daily rows:

- `close=` is the final-known closing ledger balance for that value day.
- `fees=` displays positive assessment amounts; their journal postings are negative charges.
- `interest=` is that day's rounded accrual. Daily accruals are evidence, not daily balance postings; I credit their exact sum once at Day 6.
- `pre-capitalization basis` appears when the Day 6 capitalization changes the displayed final close.
- authorizations are end-of-day state snapshots.
- an error appears only on the rejected event's recorded/booked day.

I do not delete an already-booked fee merely because a later value-dated reversal makes that day's final-known close positive. Reversing a fee would require a separate compensating fee-refund event and policy, neither of which is supplied.

## Expected replay results

| Result | Expected value |
| --- | --- |
| ACC-001 pre-capitalization closes, Days 1–6 | AED 250.00, 225.00, 625.00, 415.00, 390.00, 390.00 |
| ACC-001 Day 6 final close | AED 390.93 |
| ACC-002 pre-capitalization closes, Days 1–6 | BHD 0.000, 0.000, 0.000, 0.000, 10.000, 10.000 |
| ACC-002 Day 6 final close | BHD 10.008 |
| Overdraft fees | AED 25.00 on Days 2, 4, and 5 |
| Auth-A | Active Days 2–3; settled Days 4–6; AED 185.00 captured and AED 15.00 released |
| Auth-B | Declined at E8; no hold |
| Auth-Z / E6 | `authorization_not_found`; no debit and no implicit authorization |
| E10 installments | BHD 3.334 + 3.333 + 3.333 = BHD 10.000 |
| Day 6 capitalization | ACC-001 AED 0.93; ACC-002 BHD 0.008 |

## Design map

- `ledger_core/model.py` defines frozen domain values, exact minor-unit money, events, journal facts, and half-even integer rounding.
- `ledger_core/journal.py` provides the append-only storage boundary and projections by both value day and knowledge commit.
- `ledger_core/policy.py` contains the bounded fee, interest, authorization, settlement, and installment decisions.
- `ledger_core/engine.py` appends each input's receipt and direct outcome atomically, separately reconciles prior day-close fees when needed, and finalizes interest.
- `ledger_core/scenario.py` contains only the supplied accounts and E1–E10 fixture.
- `ledger_core/report.py` builds and renders the processing and daily views.
- `tests/` is the green correctness suite.
- `known_limitation/` contains only the separately invoked required red test.

## Decision record

- [NUMBERS.md](NUMBERS.md) explains every mandated or selected numeric constant I use.
- [AMBIGUITIES.md](AMBIGUITIES.md) records each underspecified behavior and the bounded policy I chose.
- [REJECTED.md](REJECTED.md) gives my final acceptance-claim verdicts and records implementation approaches I genuinely abandoned during the build.
- [WORKLOG.md](WORKLOG.md) reconstructs the timestamped work from contemporaneous Git evidence and explicitly distinguishes my pauses from active checkpoints.
- [ARCHITECTURE.md](ARCHITECTURE.md) is my working source for the separate Architecture & Trade-offs deliverable.
