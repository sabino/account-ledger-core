# Numbers

I use this file to separate values mandated by the assessment from numeric and structural constants I selected. A mandated value is not an arbitrary design choice: halving it would change the supplied problem. For a selected value, I explain its derivation, why I did not use a smaller or halved value, and the boundary enforced by the code.

## Mandated values

| Value | Meaning | Why not half? |
| --- | --- | --- |
| Day 1 through Day 6 | Evaluation and interest window | The supplied stream and capitalization boundary require all six days. |
| AED 25.00 | Daily overdraft fee | AED 12.50 would implement a different fee. I apply this amount only to AED closes and invent no BHD conversion. |
| 0.04% per day | Positive-balance daily interest rate | 0.02% would under-accrue every eligible day. The exact reduced fraction is `1 / 2500`. |
| 2 decimal places | AED precision | One decimal place cannot represent supplied AED 0.01 increments. |
| 3 decimal places | BHD precision | Reducing it loses supplied BHD 0.001 units. |
| AED 0.00 | ACC-001 opening balance | Any other opening balance changes every downstream result. |
| BHD 0.000 | ACC-002 opening balance | Any other opening balance changes every downstream result. |
| One fee per account per assessed day | Fee cardinality | A lower cardinality can omit an eligible account/day; a higher one can duplicate charges. |
| Three E10 installments | Supplied posting count | Halving three is not an integer, and another count changes the supplied event. |

All E1–E10 identifiers, account and authorization identifiers, booked days, value days, and transaction amounts are supplied fixture data. I keep them in `ledger_core/scenario.py` instead of presenting them as configurable business constants.

## Exact monetary representation

I store authoritative monetary amounts as Python integers in each currency's smallest supported unit. No binary floating-point value enters ledger arithmetic, and I parse decimal text lexically rather than under a finite decimal arithmetic context.

| Source reference | Value | Derivation or reason | Why not half? | Enforced boundary |
| --- | ---: | --- | --- | --- |
| `AED.minor_unit_factor` | `100` | `10²`, derived from mandated AED precision | `50` cannot represent every AED 0.01 amount and would redefine the minor unit | Reject decimal text with more than two fractional digits |
| `BHD.minor_unit_factor` | `1000` | `10³`, derived from mandated BHD precision | `500` cannot represent every BHD 0.001 amount and would redefine the minor unit | Reject decimal text with more than three fractional digits |
| `AssessmentPolicy().daily_interest_rate.numerator` | `1` | Reduced numerator of `0.04% = 1 / 2500` | A half-integer numerator would abandon integer rational arithmetic and halve the mandated rate | Numerator must be an exact integer and nonnegative |
| `AssessmentPolicy().daily_interest_rate.denominator` | `2500` | Reduced denominator of the mandated rate | `1250` would double the mandated rate | Denominator must be an exact integer and positive |
| `round_ratio_half_even` | ties to even | Explicit deterministic midpoint rule over an exact rational value | “Half a rounding mode” has no meaning; another mode changes midpoint outcomes | Denominator must be positive; tests cover positive and negative ties |
| `allocate_evenly` remainder order | left to right from ordinal `1` | Divide into quotient-sized parts and give one indivisible unit to each of the first `remainder` parts | There is no fractional posting ordinal; choosing a stable order avoids an external tie-breaker | Part count must be positive and the generic allocation amount nonnegative |

For E10, `divmod(10000, 3)` yields quotient `3333` and remainder `1`. I therefore produce BHD 3.334, BHD 3.333, and BHD 3.333: exact sum BHD 10.000, with the one spare unit assigned to installment ordinal 1.

Python integers have no fixed-width overflow boundary. I leave capacity bounded by available memory instead of inventing an assessment-only amount ceiling.

## Selected environment and structural constants

| Source reference | Selected value | Why this value rather than half or smaller? | Enforced boundary |
| --- | ---: | --- | --- |
| `pyproject.toml` minimum Python | `3.12` | I use Python 3.12 `type` statement syntax; Python 3.11 cannot parse it | Package metadata and strict type configuration both declare 3.12 |
| `AssessmentPolicy.version` | `assessment-v1` | I need one nonempty label to distinguish the bounded rule set and make idempotent finalization comparisons; there is no meaningful half-version | The engine records the supplied policy's label, the journal rejects empty labels, and a repeated finalization must match the stored label; the label is not a policy definition, digest, or registry |
| `Credit.installments` default | `1` | One is the smallest positive count and makes an ordinary credit exactly one posting | Counts at or below zero, or above the credit's available minor units, are rejected so no child posting can be zero |
| `Ledger.next_commit_sequence` initial value | `1` | One-based positions are human-readable; `0` denotes that an empty ledger has no committed batch | Nonpositive next-sequence values are rejected |
| Stored-fact batch ordinal start | `1` | One is the smallest positive position and keeps batch ordering human-readable; stored-fact ordinals are independent of posting record-ID ordinals, and a fractional half-ordinal is impossible | Every appended batch assigns consecutive positive ordinals |
| Zero-total capitalization behavior | no posting | A zero posting carries no financial effect and the journal rejects zero-valued postings | Each nonzero account/currency total produces one posting; a zero total produces none |
| Capitalization grouping | one Day 6 posting per account/currency with a nonzero rounded total | This is my bounded interpretation of the singular capitalization instruction while preserving currency isolation; one shared AED/BHD posting would be invalid | Each capitalization must equal that account's stored rounded daily accruals and link to the complete finalization window |
| Architecture volume scenario | `100x` input events | The architecture question explicitly asks what fails at 100 times the volume; `50x` would answer a different question | Used for asymptotic analysis only, not as a measured capacity result |
| Architecture scale checkpoints | `100`, `1,000`, `10,000`, `100,000`, and `10,000,000` active customer accounts | These are the requested order-of-magnitude comparison points; halving them would remove that comparison | The headline dimension is stated as active accounts, never silently treated as requests per second |
| Planning activity assumption | `10` input commands per active account per day | I need one explicit workload assumption to translate accounts into ingress; `5` would merely halve an illustrative scenario without evidence that it is more accurate | Clearly labelled as planning input, not a forecast, benchmark, or service-level objective |
| Planning peak multiplier | `10x` the 24-hour average ingress | A round stress multiplier makes burst sensitivity visible; `5x` would narrow the same unmeasured scenario without stronger evidence | Peak RPS is derived as `accounts x 10 x 10 / 86,400` and excludes reads, retries, and derived-fact fan-out |
| Architecture PDF length | `4` pages | Four is the assessment's maximum and leaves readable space for the requested scale perspective; two pages would force denser text and diagrams | Generation is checked for exactly four A4 pages and a size below 25 MB |

The commands/day and peak multiplier produce the scale table's daily-command and peak-RPS columns; those outputs are derived values, not additional constants. I derive generated identities from stable dimensions rather than a retry counter: fees use account/day, interest accruals use account/day, capitalizations use account/through-day, and finalization uses both start and through day. External string components are percent-encoded before delimiters are added, so delimiter-bearing IDs cannot collapse into the same generated identity. The capitalization ID omits the start day because this bounded core permits only one finalized window; the full-window finalization marker prevents a second, conflicting window. I introduce no retry counts, queue capacities, timeouts, tolerances, floating-point epsilons, or fixed-width amount limit.

## Chosen failing-test witness

My required intentionally failing test finalizes Days 1–6, then supplies on booked Day 7 an AED 100.00 credit value-dated Day 3.

| Value | Why I selected it | Why not half? |
| --- | --- | --- |
| AED 100.00 late credit | At 0.04%, it yields an exact AED 0.04 additional accrual on each of Days 3–6, so the missing AED 0.16 correction is transparent without a rounding edge case | AED 50.00 would also reveal the boundary, but AED 100.00 is the natural percentage base and makes the four-day proof directly readable; it is test evidence, not policy |
| Day 7 booked day | It makes the witness self-evidently later than the Day 1–6 window; processing against an already-finalized ledger is what establishes lateness | An earlier positive booked day could still exercise the same finalized-ledger boundary but would communicate it less clearly |
| Day 3 value day | It affects four finalized positive-balance days, Days 3–6 | Halving a day is invalid; a later integer day would exercise fewer corrected accruals |

I require both the AED 100.00 principal and the AED 0.16 interest delta in the red test, producing AED 491.09. Accepting only the principal would not satisfy the asserted correction contract.
