# In-Memory Account Ledger Core

The post-submission Go service experiment lives on `feat/go-ledger-service`. See [its local Docker Compose instructions and current limits](service/README.md). It is separate from the Python assessment below and does not change the submitted PDF.

The submitted revision is [5a15146](https://github.com/sabino/account-ledger-core/tree/5a15146c0b18a6e34a5c3deb5c18f29f67f42c25). Subsequent AI-assisted fixes reject authorization requests whose dates could bypass active holds and bind each policy label to its exact configuration within a ledger. These fixes were made after submission, not included in that revision. The architecture source and PDF remain the submitted versions; the supplied replay results are unchanged. See `AMBIGUITIES.md` and `WORKLOG.md` for the later behavior and its limitations.

This project replays the supplied ten events and answers four questions for each day: What is the balance? Which fees were charged? What happened to authorizations? Which events failed?

The design fits in one line:

```text
event -> decision -> immutable facts -> report
```

- An **event** is a request such as a credit, debit, authorization, settlement, or reversal.
- A **decision** applies the small set of assessment rules.
- A **fact** permanently records what was accepted, rejected, or posted.
- A **report** calculates balances and states from those facts.

The journal never edits a fact. Every batch is all-or-nothing: all facts in that batch are appended, or none are. Processing one event may first append a prior-day fee batch and then append the event-result batch; the returned result exposes everything appended by that call.

## Run it

CPython 3.12 or newer is required. Runtime and tests use only the standard library.

```bash
python3 -m unittest discover -s tests -p 'test_*.py' -v
python3 replay.py
```

The first command runs the green correctness suite. The second prints the ten events in received order and then the Day 1–6 report.

The assessment also requires one intentionally failing test:

```bash
python3 -m unittest discover -s known_limitation -p 'test_*.py' -v
```

Exactly one test should fail. Finalization ends this bounded replay, so every later event is rejected. The test demonstrates the missing controlled correction workflow for a backdated transaction after interest has been capitalized.

## Three kinds of time

The hardest part of this exercise is not arithmetic. It is time.

| Concept | Plain meaning |
| --- | --- |
| Received order | The order in which the program learns about events |
| Booked day | The day the institution recorded the request |
| Value day | The day the money economically affects the balance |

E7 is received on Day 5 but has value day 2, so it changes the reconstructed closes for Day 2 and later. E10 appears after the Day 6 event in the supplied list but retains booked day and value day 5. The program never sorts the input.

## Money and balances

Money is stored as integer minor units:

| Account | Currency | Precision |
| --- | --- | ---: |
| ACC-001 | AED | 2 decimal places |
| ACC-002 | BHD | 3 decimal places |

Different currencies cannot be combined or posted to the wrong account. Positive postings increase the customer's balance; negative postings decrease it. This is a customer-account subledger, not a complete bank general ledger: the assessment supplies no counterpart accounts, so this project invents none.

An authorization hold changes **available balance**, not **ledger balance**:

```text
available balance = ledger balance - active holds
```

## Expected result

| Result | Value |
| --- | --- |
| ACC-001 closes before capitalization, Days 1–6 | AED 250.00, 225.00, 625.00, 415.00, 390.00, 390.00 |
| ACC-001 final Day 6 close | AED 390.93 |
| ACC-002 closes before capitalization, Days 1–6 | BHD 0.000, 0.000, 0.000, 0.000, 10.000, 10.000 |
| ACC-002 final Day 6 close | BHD 10.008 |
| Fees caused by E7 | AED 25.00 on Days 2, 4, and 5 |
| Auth-A | AED 200.00 held; AED 185.00 captured; AED 15.00 released |
| Auth-B | Declined; no hold created |
| Auth-Z / E6 | Rejected; no money moved |
| E10 installments | BHD 3.334 + 3.333 + 3.333 = 10.000 |
| Day 6 capitalization | AED 0.93 and BHD 0.008 |

E9 restores E7's AED 620.00 principal effect. It does not erase the three fees already recorded as separate facts because the assessment supplies no fee refund event or rule.

## Project map

| File | Responsibility |
| --- | --- |
| `ledger_core/model.py` | Money, events, and facts |
| `ledger_core/policy.py` | Business decisions |
| `ledger_core/journal.py` | Atomic append and projections |
| `ledger_core/engine.py` | Event orchestration |
| `ledger_core/report.py` | Console report |
| `ledger_core/scenario.py` | Supplied accounts and E1–E10 |
| `tests/` | Green correctness evidence |
| `known_limitation/` | Required red test |

Each required document has one job:

- `NUMBERS.md`: numeric choices.
- `AMBIGUITIES.md`: underspecified behavior and selected policies.
- `REJECTED.md`: claim verdicts and abandoned approaches.
- `WORKLOG.md`: chronological work evidence.
- `ARCHITECTURE.md`: production evolution and trade-offs.

The four-page submission PDF is `output/pdf/architecture-and-trade-offs.pdf`. Rebuild it with `python3 tools/build_architecture_pdf.py` when ReportLab is available.
