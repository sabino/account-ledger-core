# Decision coverage for the Go service

Status: planned demonstrations and tests, not existing functionality. Companion to [the implementation plan](go-service-plan.md). The Python assessment and submitted PDF remain historical evidence; this matrix records preserved behavior, explicit extensions and deferred work.

## Ambiguities

| Source | Go contract / status | Visual exercise and evidence |
| --- | --- | --- |
| AMB-01 received order | Preserve fixture order; live concurrent acceptance order recorded | Timeline shows received, booked, value and committed positions; E10 stays last |
| AMB-02 historical balance | Preserve two-axis view with explicitly ordered commits | Value-day and known-through selectors; compare same date at two knowledge cutoffs |
| AMB-03 daily close | Preserve fixture; live profile has explicit virtual calendar and durable close jobs | Open-day rescue, quiet negative day, backdated rescan, account close progress |
| AMB-04 reversal scope | Principal-only reversal preserved; fee refunds require another command/policy | E9 link to E7 and separate retained fee legs; optional refund clearly an extension |
| AMB-05 final partial capture | One final capture, unused hold released | AED 200 hold -> AED 185 posted + AED 15 released; second capture rejected |
| AMB-06 unknown authorization | Reject without financial movement | E6 error and empty monetary effect |
| AMB-07 approval | Check locked current availability for new holds | Two requests of 80 against 100; one approval |
| AMB-08 hold endings | Initial compatibility remains narrow; expiry/void/reversal are phase-7 extensions | State diagram labels unsupported transitions; later buttons require implemented tests |
| AMB-09 BHD installments | Exact deterministic allocation | 3.334 + 3.333 + 3.333 and why identical parts are impossible |
| AMB-10 BHD fee absent | No implicit FX or invented fee | Controlled unsupported close; other account continues |
| AMB-11 interest order | Fees reconciled, final-known daily bases, rounded sum | Daily basis/accrual table, complete capitalization link |
| AMB-12 interest currency | Separate AED/BHD amounts and precision | No mixed-currency monetary total; two capitalization legs per currency's balanced transaction |
| AMB-13 idempotency/policy | Durable command key + payload and immutable policy configuration | Identical retry, conflicting payload, policy mismatch, original result |
| AMB-14 post-finalization correction | Compatibility rejects; Python red test unchanged | Explain missing workflow; phase-7 correction preserves original result and adds linked deltas |
| AMB-15 money size/input | Explicit extension: checked bounded stored integers | Precision errors and overflow rejection; exact intermediates |
| AMB-16 report semantics | Preserve fixture report; live views disclose cutoff and freshness | Rejected event day, authorization state, late-known close versus issued statement |
| AMB-17 ordinary debit | Preserve assessment overdraft; ordinary live transfers enforce availability | Separate debit/overdraft scenario from transfer command |
| AMB-18 subledger | Explicit extension: balanced bank-side accounts | Deposit, fee, interest and transfer diagrams with both sides and reconciliation |
| AMB-19 decline/rejection | Accepted business decline vs invalid command distinguished | Outcome filter and explanation; both leave posted money unchanged |
| AMB-20 authorization dates | Preserve hardening; live calendar replaces arrival-based day inference | Historical/future hold rejected, existing hold remains reserved |

## Other submitted documents

| Document/decision | Planned evidence |
| --- | --- |
| README runnable replay | One local Compose command and fixture scenario; exact run instructions tested in CI |
| NUMBERS mandated values | Formula popovers with source, precision, rate and daily rounded result |
| NUMBERS chosen values | Settings registry records value, rationale, enforcement, measured/tentative status; runtime and resource limits have derivations |
| REJECTED Claims 1, 3, 4, 5 | Executable accepted claims, with input/decision/effect |
| REJECTED Claim 2 | Three fee identities; Day-5 fee occurs before E9 rather than inside E7 |
| REJECTED Claim 6 | Principal correction plus surviving fees; append-only does not forbid an explicit fee refund |
| REJECTED Claim 7 | Show proposed total 10.002 against supplied 10.000 |
| REJECTED Claim 8 | Sum rounded daily accruals to exact capitalization; no discarded remainder |
| REJECTED abandoned parsing | Explain bounded integer implementation and exact rounding; no ambient decimal context |
| REJECTED close-on-posting | Same-day rescue scenario with no premature fee |
| REJECTED generic reversal | Unsupported targets reject; same-date versus later-date reversal remains explicit policy, not a universal law |
| REJECTED incomplete close identity | Different window/policy cannot masquerade as the original finalized operation |
| WORKLOG | Timestamped implementation evidence and AI disclosure; no generated retrospective claim of completed testing |
| ARCHITECTURE append-only growth | Python retained-prefix benchmark contrasted with measured SQL append/index costs; do not imply removing all scaling limits |
| ARCHITECTURE concurrency | Trace two instances, account locks, short journal-order lock, idempotency and retries |
| ARCHITECTURE value dating | Immutable past records and changing reconstructed view; issued outputs remain identifiable |
| ARCHITECTURE UAE considerations | Explanation with original sources and declared assumptions; no claim that a demo proves compliance |
| ARCHITECTURE closed-period control | Initially a blocked capability; later controlled correction with preserved original and explicit downstream status |
| ARCHITECTURE authorization lifecycle | Current vs proposed transitions distinguished; payment-rail late settlement remains a separate domain question |
| ARCHITECTURE missing double-entry | Account normal sides, explicit counterparts, atomic balancing; external matching is a distinct check |
| ARCHITECTURE no persistence | Local database restart and separate backup/restore exercise |
| ARCHITECTURE thin product/time rules | Versioned policy and simulation clock; no implied real bank calendar/FX implementation |
| ARCHITECTURE one writer/distribution | Actual lock contention and measured boundary; partitioning/sharding plan clearly unimplemented |

## Follow-on decisions

| Decision | Demonstration |
| --- | --- |
| Outbox | Committed money with pending delivery; sink accepts then response is lost; retry deduplicates |
| CDC | Pause consumer, show backlog/WAL, resume safely or explicitly resnapshot |
| Iceberg snapshots | Source position, complete batches, snapshot selection and duplicate-safe views |
| Analytical lag | Public report is stale while authoritative account view is current |
| Public workload control | Multiple browsers change one shared rate; direct API cannot exceed the budget |
| Resource limits | Requested versus admitted rate, CPU/memory ceilings, queue caps, safe pause reason |
| Synthetic data | Reproducible seed and real recorded race order; no personal information |
| Retention | Run age/size and export/cleanup status; bounded simulation is not an indefinite audit archive |
| Local/remote parity | Same image and schema in Compose and CapRover; deployment differences documented |
| Storage adapter | Local lake vs experimental rclone/Seafile path, verified checksums and restart visibility |

Acceptance rule: an explanatory panel alone marks a decision as explained, not tested. Each implemented claim links to a passing test or captured experiment with revision, parameters and timestamp. Unsupported functionality stays visibly unsupported. No more than the tested workload and failure model may be described as proven.
