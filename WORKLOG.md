# Worklog

All timestamps use America/Sao_Paulo (`UTC-03:00`).

## How I kept the log

I used a lightweight Plan–Do–Check–Act loop. I planned by turning uncertain wording into explicit questions, did the smallest useful piece, checked it against arithmetic and tests, and acted on what the checks exposed.

The times below are real checkpoints, not claims that I worked continuously between them. When several related changes landed at the same recorded second, I describe them as one checkpoint instead of inventing a false minute-by-minute sequence. I made the final policy choices and remain responsible for the result.

## 2026-09-01 — Preparation

### 11:12:59 — Plan · Keep exploration separate from delivery

I opened a private place for rough research before starting the deliverable. I knew I would have tentative calculations, copied references, and ideas I might later reject, and I did not want any of that to look like an accepted design by accident. My rule was simple: explore freely there, but move only reasoning I could explain and defend into the deliverable.

## 2026-09-02 — Requirements and design

### 11:11:00–12:05:57 — Plan · Learn where a ledger stops

I spent this period trying to understand which parts of the problem belonged to ledger mechanics and which parts were business policy. I looked at write paths, read models, corrections, reconciliation, effective dates, issued reports, regulatory controls, and multicurrency boundaries.

The important realization was that an append-only journal can preserve facts and enforce balanced movements, but it cannot decide what an ambiguous settlement or reversal should mean. I would need to state those choices myself. I also decided that a newly learned historical fact should change a current reconstruction without pretending the fact had always been known.

### 12:16:28 — Plan · Read the prompt without changing the live form

I started the assessment timer and read the prompt while the page showed `1d 23h left` and `0/2 complete`. I did not type into an answer field, upload anything, save, or submit. On the first pass I marked hard requirements, claims that looked deliberately wrong, and phrases such as “as of” and “exactly” that could change the result.

### 12:19:21 — Plan · List the policy questions before choosing answers

I wrote down the points I could not honestly derive from arithmetic alone: capture below a hold, missing authorizations, late value-dated fees, the reach of a reversal, installment remainders, and rounded interest. I resisted choosing a language at this stage because a convenient implementation should not decide the accounting contract.

### 12:24:07 — Check · Preserve the wording I was reasoning from

I kept an exact copy of the visible assessment text. I wanted to be able to return to the source wording whenever my interpretation started feeling obvious, because “obvious” was exactly where I was most likely to smuggle in an assumption.

### 12:24:19 — Act · Start with the explanation, not the code

I laid out the required documents, an architecture outline, an ambiguity log, and provisional refusals. I had not selected a language or framework. Starting this way forced me to show where judgment entered the solution and made it harder to retrofit a clean story after seeing the program output.

### 13:55:10 — Check · Challenge my reading before implementation

I used three separate AI review passes on the untouched specification, with different focuses: arithmetic and time, adversarial specification reading, and implementation choices. I compared their anonymized answers with mine rather than asking them to confirm my preferred result.

The reviews converged on accepting Claim-1, Claim-3, Claim-4, and Claim-5 and refusing Claim-2, Claim-6, Claim-7, and Claim-8. Under the policy I was considering, they also reproduced three AED 25.00 fees, AED 0.93 interest, and BHD 0.008 interest. That agreement gave me confidence in the arithmetic, while the disagreements helped me identify which conclusions still depended on disclosed policy.

### 14:05:26 — Act · Choose Python and avoid a framework

I chose Python because the deliverable needed to be readable under discussion, not impressive through infrastructure. Arbitrary-size integers fit exact minor-unit money, dataclasses could keep the model explicit, and the standard test tools were enough. A framework or database would have added setup while hiding the decisions I actually needed to defend.

### 14:26:55 — Act · Fix the language of the model before it spreads

While writing out the mental model, I noticed that short acceptance labels could be confused with authorization identifiers. I renamed them to `Claim-1` through `Claim-8` and moved ambiguity labels to `AMB-*`. I also wrote down the difference between an input event, a policy decision, a journal fact, and a projection. No arithmetic changed; I was removing vocabulary that could make correct behavior hard to explain.

### 14:45:56 — Check · Work the scenario by hand

Before trusting code, I worked through authorizations, accepted and rejected events, postings, fees, daily closes, and interest separately. I used that hand-worked result as the oracle for implementation. If the program disagreed, I wanted to investigate the transition where the disagreement began instead of adjusting an expected final balance until a test turned green.

## 2026-09-02 — Reference experiments

### 16:44:20 — Check · See what a real ledger engine would enforce

I replayed the scenario in Formance Ledger v2.4.12. Balanced movements, metadata, and atomic execution mapped well to the model, and the numbers agreed with my selected interpretation. The useful lesson was the boundary: the engine could reject an invalid movement, but it could not tell me whether the assessment intended a partial capture or an automatic fee refund.

### 17:39:30 — Check · Push schema and atomicity harder

I repeated the experiment with stricter Numscript templates, schemas, and rejection probes. That made me more comfortable keeping the journal narrow and uncompromising while placing the assessment-specific choices in pure policy functions. I kept the architectural lesson and dropped the external dependency from the deliverable.

## 2026-09-02 — Implementation

### 18:14:06 — Do · Model money and events first

I started with immutable money values and typed events because every later calculation depended on them. Amounts became integer minor units with an explicit currency scale and round-half-even behavior. I deliberately rejected exponent notation, excess precision, and cross-currency arithmetic rather than guessing what the caller meant.

### 18:14:07 — Do · Make the journal append-only by construction

I added a functional journal that returns new state instead of mutating old state. A batch either validates completely or contributes no facts, posting identities are unique, and every posting amount must match its account's currency. This gave the replay engine a small trusted core and made earlier states available for knowledge-time questions.

### 18:21:56 — Do · Keep policy decisions outside atomic replay

I encoded authorization, settlement, reversal, fee, installment, and interest choices as pure decisions, then applied those decisions through an atomic replay step. Accepted inputs produce their complete set of facts; rejected inputs move no money and retain a reason. This separation let me test “what should happen?” without also exercising storage mechanics, then test that the chosen effect was applied all-or-nothing.

### 18:26:40 — Check · Make the program explain the whole result

I added the complete daily view and executable verdicts for all eight claims, then hardened malformed money and repeated finalization behavior. I also chose the required red test: a backdated credit after interest finalization. It fails for a real reason—the bounded core cannot reopen the period and reconcile principal with capitalized interest—not because I deliberately broke a correct path.

Seeing the day-by-day projection was more useful than seeing only final balances. It exposed when knowledge arrived, which value date changed, when a fee became eligible, and why a later compensating entry did not erase an independent fee.

### 18:27:21 — Act · Replace context-sensitive amount parsing

An arbitrary-size input exposed a flaw in my first parser. Multiplying a `Decimal` by the currency scale could consult the ambient decimal context before conversion to an integer, so a large exact value could be rounded unexpectedly. I replaced that path with lexical validation and direct integer construction of whole and fractional minor units.

### 18:31:05 — Check · Test boundaries and all six days

I expanded the suite beyond the happy path: invalid batches, duplicate identities, policy failures, idempotency, knowledge cutoffs, and the complete six-day report. I wanted a broken invariant to fail near its cause. The full projection also acted as a reconciliation table, making it difficult for one correct headline number to hide a wrong intermediate day.

### 18:35:01 — Act · Treat fees as a closing process

My first fee pass was too closely tied to the arrival of a monetary event. That could miss a quiet negative day and could treat a temporary same-day balance as though the day were finished. I changed the flow to close earlier days when booked time advances, immediately rescan accepted backdated effects, and sweep the requested window during finalization.

At the same checkpoint I strengthened the late-correction limitation. A plausible correction has to reconcile both the newly changed principal and interest that was already capitalized; testing only the principal would understate the real problem.

### 18:36:20 — Act · Separate activity during a day from the final close

A day can contain several postings before its final closing balance exists. I corrected the model so generated closing fees do not make the first negative posting look like a finished day. This was a small distinction in code but an important one in the accounting story.

### 18:43:02 — Act · Fail safely when fee policy is unsupported

I tried fee functions that returned the wrong currency, zero, or a negative amount. Those results should not leak partial facts or crash halfway through replay. The core now contains them as a structured rejection during event processing or an atomic typed failure during finalization. I preferred a narrow, explicit failure over pretending arbitrary policy code was valid.

## 2026-09-02 — Final reconciliation

### 19:48:09 — Act · Make the explanation match the implementation

I read the requirements, ambiguity choices, arithmetic, tests, report, and architecture together. I made each accepted or refused claim explicit and described only approaches I had genuinely considered and then replaced. I also removed statements that were broader than the code could prove.

The result is intentionally bounded. It demonstrates exact money, append-only replay, two-axis historical reconstruction, explicit business policy, deterministic reporting, and honest failure behavior. It does not pretend that an in-memory assessment core is a production banking platform.

## 2026-09-02 — Architecture document

### 22:02:15 — Plan · Resume after a long pause

I paused for more than two hours after the Part 1 reconciliation. I spent that time with my children, had dinner, and returned rested before starting the architecture document.

I reread the four required sections and chose to keep the argument anchored to the implementation: identify the first measured or structural limit, make the smallest credible improvement, state what it does not solve, and describe distribution only as a later step with explicit ordering and atomicity costs. I also began a fresh review of the UAE value-date surface, authorization terminal states, and every production risk deferred by the Part 1 cuts.

### 22:12:47 — Check · Reconcile the architecture argument

I compared the implementation with AI reviews of its storage complexity, authorization state machine, UAE value-date obligations, and scope cuts. The reviews changed the emphasis in useful ways. I separated event-volume growth from concurrent-writer correctness, described 10,000x only as the quadratic component of a 100x input increase, and made clear that a declined request is the only non-settlement terminal outcome represented while an approved hold has no non-settlement ending in this model.

I then drafted the architecture document in first person. I chose one closed-period correction gate rather than a loose compliance checklist, connected it to the known failing test, and kept distribution on a staged path: remove retained prefixes, establish a durable ordered append boundary and indexes, measure it, then partition by account only when an explicit objective requires it. I grouped the deliberate cuts by the production risk they defer so the list remains complete enough to challenge without turning into a catalogue of infrastructure.

### 22:28:30 — Check · Challenge, render, and verify the document

I put the completed draft through three AI review passes against the code and decision logs. They caught distinctions I wanted to be able to defend precisely: replay retention is quadratic in event count only under bounded fact fan-out; temporary full-log allocations are not retained state; the current close and finalization loops must become account-local before `account_id` is an honest partition boundary; and decline is a terminal request outcome, not a transition out of an active hold. I corrected each point, narrowed the UAE claims to their applicable consumer, error, and control contexts, and reduced the source to 1,794 words without dropping a production-risk category.

I rendered the source as a three-page A4 PDF and inspected every page at 180 DPI. I verified its page count, 15,315-byte size, text, page bounds, and four source-link annotations. The 57-test correctness suite, complete replay, and strict type check remained green. The separate known-limitation test still failed for the intended reason: the finalized-period correction is rejected instead of posting the principal and reconciled interest delta. I left the Markdown, renderer, PDF, and worklog changes uncommitted for review.

## 2026-09-03 — Final hardening and explanation

### 01:11:18 — Plan · Reconcile the whole submission before changing it

I reread the captured requirements, implementation, tests, decision records, architecture draft, renderer, and existing PDF before editing. I preserved the prior uncommitted work and used the current green suite and rendered document as a baseline. I confirmed that the required currency model is two independent account currencies—AED at two decimal places and BHD at three—not foreign exchange between them.

The review left me with three bounded goals: remove incorrect author identity from the PDF path, close the malformed-posting gap at the journal boundary without turning the exercise into a general ledger, and make the implementation simple enough to explain before discussing production evolution.

### 01:29:59 — Do · Tighten the existing boundary and simplify the architecture story

I kept the customer subledger model and strengthened the place where complete fact batches enter its journal. Event receipts now lead their batch and agree with booked time; accepted monetary events, authorization outcomes, settlements, and reversals must carry their matching facts and causes together. Installment children must equal the deterministic allocation, and reversal targets are exact and single-use. At this checkpoint I also made the journal recalculate policy-derived fees and interest before append; a later AI adversarial review showed that this duplicated too much of the engine, so I removed that part while retaining the structural boundary. I also rejected invalid currency-precision metadata instead of allowing it to fail later during parsing.

I added focused regression tests for each bypass and kept the original ledger unchanged whenever validation fails. The six-day behavior and existing policy choices did not change. In parallel, I rewrote the architecture source to begin with the five-step in-memory flow, state the customer debit/credit boundary plainly, separate required AED/BHD support from FX, and make scale assumptions explicit before discussing persistence, read models, partitioning, or coordination. I corrected the authored-document identity to Felipe Sabino in the renderer and reserved final artifact regeneration for the completed source.

### 02:18:53 — Act · Keep one owner for policy decisions

An AI adversarial lifecycle review found that a second settlement could supply a value day earlier than the first settlement and see the authorization as historically active. That allowed a second capture and then made later authorization projection fail. I separated two checks: terminal state now follows everything already known, while the effective-date view still proves that an otherwise active authorization existed on the requested value day. I added both supported-path and raw-batch regressions for the case.

The same AI review showed that my first hardening pass had made the journal recalculate too much fee, interest, and authorization policy already owned by the engine. That duplication made the core larger and had helped the two settlement paths diverge. I removed the duplicated policy evaluator and transient close context from `append_batch`. I retained atomic uniqueness, types, currencies, nonzero amounts, debit/credit direction, receipt shape, direct-event causality, deterministic installments, exact single-use reversals, and authorization-history consistency. Policy functions and the engine again own business outcomes, with scenario and boundary tests checking their results.

### 02:26:23 — Check · Verify the frozen local deliverables

A final AI out-of-order review found one more fee-close edge: an event whose booked day regressed below the previously recorded high-water mark could skip the historical rescan when its value day equaled its own booked day. I corrected the condition and added a regression that moves from Day 6 back to Day 5, assesses the resulting Day 5 and Day 6 fees, and reconciles the final close. AI rechecks then found no remaining material defect in the supported event and finalization paths.

I ran the complete 80-test correctness suite successfully, received zero strict type errors or warnings, and replayed E1–E10 with the expected six-day report and exit status 0. I ran the known-limitation command separately: exactly one annotated test failed with exit status 1 for the intentionally unsupported finalized-period correction workflow.

I regenerated the architecture artifact from the final source. It is exactly four A4 pages and 17,072 bytes, has `Felipe Sabino` as its author metadata and footer identity, contains four distinct official source links, and has no encryption or JavaScript. I rendered all four pages at 180 DPI and inspected them for clipping, overlap, legibility, and stale text. Source, history, filename, artifact-text, metadata, and secret-pattern checks found no stale invented identity or unintended personal material. I removed the temporary page images after inspection and left every project change uncommitted for review.

## 2026-09-04 — Disclosure wording

### 00:51:46 — Check · Make AI assistance explicit

I replaced vague references to independent or adversarial reviewers with explicit AI review wording. This only clarifies how the existing checks were performed; no code, tests, calculations, behavior, or design decisions changed.

## 2026-09-04 — Final adversarial correction

### 02:01:12 — Act · Charge closed days, not an open day

A contextual AI review found that a backdated posting could assess a fee for its still-open booked day. I reproduced it with an AED 100.00 credit, a booked-Day-5 debit value-dated Day 1, and a rescue credit later on booked Day 5. The old path retained a premature Day-5 fee and closed at AED 25.00; the correct close is AED 50.00. I changed the rescan to stop at the latest closed day and added that exact regression.

The same pass exposed two related boundaries. Prior-day fee work could reject an event for another account, and a processing result could hide the maintenance commit created before its event commit. Event-time closing is now account-local, same-account configuration failure consumes no event ID, and `ProcessResult` exposes every fact appended by the call while identifying the receipt's own commit separately. In the supplied replay, E7 now records the already-closed Day-2 and Day-4 fees; the arrival of E9 closes Day 5 in commit 9 before the reversal is recorded in commit 10. The three fees, balances, and interest totals do not change.

I also made finalization an explicit end to this bounded replay, removed unused policy parameters, made reversal dispatch explicit, separated authorization endings from adjustments and post-settlement events, removed scale constants left by an older architecture draft, and renamed the project metadata to `account-ledger-core`.

I ran all 84 correctness tests normally and with Python optimization enabled, replayed E1–E10 successfully, and confirmed that the separate known-limitation suite still has exactly its intended failure. Pyright was not installed in this environment, so I did not claim a new static-check result. I regenerated the architecture PDF as four A4 pages and 17,320 bytes, verified all five source links, and inspected every page at 180 DPI for clipping, overlap, and stale wording.

### 02:25:09 — Check · Answer each architecture question directly

A final rubric audit found a few answers that were present only by implication. I made the first 100x limit, the unbounded journal and replay state, and the cheapest structural change explicit. I also stated the decline scenario and action in text, and expanded the scope cuts to include the AED-only fee rule, direct-debit-principal reversal, and the limits of a caller-supplied policy label. I clarified that linked replacement of an issued result is a production requirement, that this customer subledger could sit behind a balanced general-ledger boundary, and that journal sequence orders committed batches.

The first rebuild showed that fixed section breaks wasted space on the opening pages and crowded the final page. I removed those breaks and kept one deliberate split between the conceptual double-entry diagram and its guarantees. The final artifact remains four A4 pages, now 17,465 bytes, with all five source links, consistent footers, and no clipped or overlapping content at 180 DPI. All 84 tests passed normally and with Python optimization enabled, and the complete replay still exited successfully. No runtime behavior changed in this pass.

## 2026-09-04 — Post-submission branch

### 17:35:00 — Check · Bound authorization dates and policy identity

After submission, an AI-assisted review reproduced a new authorization gap: an AED 100 balance could support two AED 80 holds when the second request carried a value day before the first hold. Its historical availability check omitted the already-active hold. On `codex/post-submission-hardening`, I limited new authorization requests to the current booked day, with matching value day, and added regression coverage for historical and future dates. A previously tested late authorization now receives a date rejection rather than a business decline; prior-day fee maintenance remains visible.

The same review confirmed that a different interest rate could reuse the original policy label and silently receive the original finalization result. The engine now retains exact immutable policy configurations in each ledger value and rejects conflicting reuse during event processing or finalization. This avoids hashing and global mutable state; it does not implement effective-dated production policy management.

All 87 correctness tests passed normally and with Python optimization enabled. The supplied replay retains its fee timing, commit numbers, balances, and capitalization totals. These changes are subsequent to submitted commit `5a15146`; the architecture source and submitted PDF are unchanged. The branch work is left uncommitted for review.

### 17:36:18 — Act · Prepare the post-submission changes for main

I authorized Codex to document, commit, open a pull request, and merge these fixes into `main`. Codex implemented the code, regression tests, and documentation with my authorization; these are AI-assisted changes. The README now identifies the exact submitted revision separately from subsequent work. The merge will retain the original commits rather than squash history, and the submitted architecture source and PDF will remain unchanged. The 87-test suite passed again before publication. The prior entry records the earlier uncommitted checkpoint, not the eventual publication status.

## 2026-09-04 — Go service experiment

### 19:07:34 — Plan · Make the follow-on service testable without risking the host

I want to take the useful parts of the Python POC and exercise them as an actual service: two Go instances, PostgreSQL, a public simulator, and a separate reporting pipeline. This is follow-on work on `feat/go-ledger-service`, not a replacement for the submitted assessment or PDF. Codex is helping with the plan, implementation, and checks.

The plan now separates the six-day compatibility contract from continuous simulation. It covers double-entry, concurrency, retries, outbox delivery, CDC to Iceberg, self-hosted ClickHouse, Metabase, and the tests each claim needs. Docker Compose is the local reference environment. The decision coverage document maps the original choices to planned tests and visual explanations; it does not claim those features already work.

The shared VPS still has roughly 1.6 GiB of available RAM and substantial swap use. Existing services are production-critical. Builds and experiments stay local until measured resource and recovery checks justify a bounded deployment. No existing workload was stopped or reconfigured in this step.

I also pushed back on the first Go scaffold: compressed code and SQL spread through methods make it harder to maintain. The direction is named SQL files with `sqlc`-generated types, explicit transaction boundaries in Go, formatting before commits, and automated checks. Docker access is working after an authorized group change. The service is not deployed yet.

### 19:22:08 — Act · Start with exact money and a tested database boundary

The first Go slice now handles funding, transfers, holds, and final partial capture. Amounts use checked integer minor units. Daily half-even interest and the BHD remainder allocation have unit tests, but the complete six-day compatibility port is still pending. The Python implementation and submitted documents are unchanged; all 87 Python tests still pass.

SQL lives in named query files, with typed Go methods generated by `sqlc`. The transaction code locks the run, command identity, sorted accounts, and finally the journal clock. Posted facts cannot be updated or deleted by the runtime role, and deferred database checks reject an unbalanced batch or an envelope that does not match its postings.

The local PostgreSQL tests initially failed because `SELECT FOR SHARE` needs an update privilege. I limited that grant to the simulation-day column and reran the tests using the application role. The race-enabled suite now passes simultaneous identical retries, changed-payload conflicts, competing transfers and holds, final partial capture, invalid commands, 100 opposite-direction transfers, and an intentionally unbalanced raw batch. Reconciliation checks the journal, balance projection, and active holds at one database snapshot.

This is still a partial service. The delivery adapter currently writes to an inbox in the same database; it does not yet prove network retry behavior. CDC, the reporting stack, full fixture compatibility, independent external reconciliation, and production-host guards still need implementation and tests. Codex implemented and ran these checks with my authorization.

### 19:28:16 — Check · Run the first dashboard through two local instances

Docker Compose now starts the dedicated database, one-shot bootstrap, two identical Go instances, and a loopback-only proxy. The browser can select accounts, submit a transfer, inspect both journal legs, change the shared rate, and run reconciliation. Replica panels use actual heartbeats and explicitly label Go heap memory rather than calling it total container memory.

The browser check loaded the page, submitted a transfer, and returned zero reconciliation differences. A separate HTTP smoke test passed identical retries, a changed-payload conflict, a balanced transfer, and recovery after a 15-second delivery pause. The local image build, TypeScript build, frontend formatting check, and original 87 Python tests passed. I added a CI workflow, but it has not run on GitHub yet.

The page says which capabilities are missing. Local startup is not a safe-deployment claim: there is still no host watchdog or measured whole-stack budget, and no VPS service was changed. The first notification adapter remains same-database delivery. The next work is compatibility and recovery, not calling this first dashboard complete.

### 19:57:00 — Check · Port the six-day example and make migrations explicit

The Go service now replays the supplied six-day example in an isolated run, with balanced counterpart postings. The database tests check the historical closes, the three fees, partial capture and release, principal reversal, the BHD split, and capitalization of AED 0.93 and BHD 0.008. The browser has a journal-cutoff view for the daily balances. This verifies the supplied example, not equivalence with every possible Python input.

Go batch numbers are different from Python commit numbers. Prior-day maintenance and its triggering event are separate journal batches within one database transaction. A prefix query can inspect the boundary between them, but a live reader never saw that intermediate state before commit. The documentation now states this distinction.

I also replaced startup schema execution with numbered Goose migrations and a database migration lock. Queries remain named SQL with generated Go types. Go formatting, vet, race-enabled unit and database integration tests, frontend formatting, and the TypeScript build passed locally. Codex implemented and checked this step with my authorization. The submitted Python code and PDF remain unchanged; no production service was touched.

### 19:59:45 — Check · Read the fixture through the reporting pipeline

The optional local lake profile now sends complete journal batches from PostgreSQL through Debezium into Iceberg, using SeaweedFS for object storage and its REST catalog. Self-hosted ClickHouse read all 12 unique fixture batches and reconstructed the expected customer balances and counterpart totals. A graceful CDC restart resumed ingestion. Crash-window duplicates, lost-slot recovery, and sustained load are not tested yet.

The first ClickHouse startup failed because its default merge thresholds exceeded the smaller worker pool. Aligning those settings fixed startup. The upstream CDC release image also referenced a missing manifest; this experiment pins the working upstream build by digest and records that its release provenance still needs review.

This remains local. SeaweedFS mini mode sizes its volume allowance from free disk space, and limiting Iceberg metadata history does not reclaim historical data files. Neither default is a safe storage budget for the shared VPS. The local notes call these out rather than treating a successful read-back as deployment readiness. Codex performed this implementation and validation with my authorization.

### 20:01:00 — Check · Compare arbitrary transfers with a separate model

A seeded integration test now sends 500 arbitrary transfers through alternating service connections. It includes insufficient-funds outcomes and repeats every seventh command through the other connection. After every request, it compares the account balances with a separate conservation-and-availability model; final journal reconciliation must also pass. The race-enabled test passed. The fixed seed makes failures reproducible, not exhaustive. This adds coverage beyond E1–E10 without changing the supplied fixture or claiming all ledger behaviors are covered.

### 20:06:00 — Check · Stop admission when the independent host watcher disappears

The local stack now has a separate, resource-capped watcher. It reads memory availability, memory and IO pressure, swap activity, and filesystem free space through read-only mounts, without a Docker socket. A dedicated database role publishes an eight-second safety lease. The API role can read it but cannot renew it; an application-role test verifies that permission boundary.

I stopped the local watcher and waited for expiry. HTTP requests reached both replicas and were denied, rate increases and chaos were denied, the journal position stayed unchanged, and setting the rate to zero still worked. The watcher was then restarted. Unit tests, vet, and the race-enabled database suite passed. Codex implemented and ran this check with my authorization, and the worklog keeps that assistance explicit.

This is admission control, not a promise that every container stops consuming resources when pressure rises. Already-admitted work can finish, and background components still need their own enforced budgets. Thresholds are local defaults pending VPS calibration. No production workload was changed.

### 20:09:00 — Check · Restore a local backup and compare the actual records

The recovery drill briefly stopped only the two local API containers, took a 703,072-byte custom-format PostgreSQL backup, and restored it into a newly created disposable database. SHA-256 fingerprints matched all rows in 12 financial and delivery tables. The restored journal had no unbalanced batches, and the runtime role still lacked journal update, posting delete, and host-lease update permissions. Restore plus verification took about 6.3 seconds for this small dataset; that is not a production recovery-time estimate.

The disposable database was removed and both API containers returned healthy. The source database was not replaced or erased. This test reuses cluster roles, pauses writers, and does not recover replication slots, Iceberg storage, or an entire lost host. Those remain separate tests. Codex implemented and ran the drill with my authorization. I also separated checked local evidence from planned coverage in the decision matrix.

### 20:18:00 — Check · Try the complete local stack with smaller limits

The separate `ledger-budget` project started all eight runtime services with memory ceilings totaling 1,280 MiB and no additional container swap allowance. The first test checked the lake too early, before the initial snapshot completed. An explicit catch-up check now separates data readiness from a running container.

The subsequent short experiment committed 619 batches, read the fixture repeatedly through ClickHouse, and finished with successful reconciliation. No container restarted or reported an OOM kill. The requested 20/sec boost returned to baseline automatically; the test does not claim sustained 20/sec throughput. Sampled memory observations and exact limits are recorded in `deploy/local/BUDGET.md`.

The production host still had only 1,631 MiB available in a read-only check. Adding a 512 MiB reserve to these ceilings exceeds that headroom, so this is not deployment approval. Codex performed the experiment locally. No production service was changed, and the main local dashboard remained on port 8088.

### 20:24:00 — Act · Make the simulation exercise failures and exact calculations

The live recipe now alternates AED and BHD groups and includes fractional transfers, insufficient funds, invalid precision, holds, final partial capture, duplicate capture, unknown authorization, currency mismatch, a three-part transfer split, illustrative tax rounding ties, and an identical retry. New evaluated outcomes retain the locked balance, holds, availability, and requested amount. Tax examples retain net, tax, gross, exact rate, and rounding rule in the immutable envelope.

The tax rate is a synthetic 1/20 example, not jurisdictional tax policy. The split uses one value date, not a repayment schedule. Tests verify both half-even ties, the capture/release amounts, rejection without monetary legs, exact retry behavior, and BHD 3.334 + 3.333 + 3.333. The race-enabled database suite passed, including the supplied six-day example. Earlier journal records and the submitted Python/PDF are unchanged.

Codex paused local generation before switching the two replicas to the new recipe, then resumed at one command per second. Reconciliation returned zero differences. A mixed-version generator rollout is not safe yet without that pause; fenced recipe ownership remains pending. Full HTTP attempt/correlation history and a visual inspector are also still pending. This step improves stored decision evidence rather than claiming the complete audit feature is done.

### 20:28:00 — Act · Show the evidence for the selected journal event

Journal batch numbers now open a contextual inspector with the outcome, reason, processing replica, recorded time, booking/value days, available-funds evidence, calculation details, and monetary legs. The selected event stays fixed as newer batches arrive. Older or early-rejected records explicitly say when decision evidence was not recorded. Synthetic tax and same-date splits retain their scope warnings, and the full stored envelope can be expanded.

The safety label now considers both the host lease and database guard. The Sites skill informed readable layout and state handling, while the existing Go/CapRover architecture was preserved. TypeScript and frontend formatting checks and the local image build passed; both updated API instances are healthy. Browser interaction and responsive visual QA were not performed in this step, so these checks do not prove the final visual experience. Codex implemented this with my authorization. The generated image remains a design concept, not a claim that its entire interface exists.

### 20:47:00 — Check · Deliver across HTTP and count recorded decisions

The outbox now leases a batch before sending it over signed HTTP. The receiver verifies the complete batch and deduplicates receipts. Claims, retries, and acknowledgements have append-only audit records. The local proxy blocks the internal receiver route. A test simulates a lost acknowledgement after receipt is committed and verifies that retry still leaves one inbox receipt. This receiver shares PostgreSQL with the ledger; it is not an independent downstream database or exactly-once network delivery.

The analytics endpoint counts recorded decisions in 60 buckets, with fixed 10-minute, one-hour, and 24-hour windows and currency attribution from the command or legacy postings. Matching retries do not increase the count. Integration checks cover currency isolation and agreement between outcome and replica totals. The SQL aggregates once before filling empty buckets, and the HTTP query has a two-second timeout.

Codex implemented and tested this step. The first delivery test raced with the old local workers, which still consumed all runs; stopping those local APIs removed that interference. The new workers only consume the demo and fixture runs. Go vet, race-enabled unit and database tests passed. Both local replicas were rebuilt. No production service or submitted assessment file was changed.

### 20:48:00 — Act · Put events and accounts first in the dashboard

The dashboard now has a dark navigation shell, event time series, outcome and processing-replica breakdowns, and a currency-specific account view. The account selector, transfer choices, current totals, and journal preview follow the selected currency. The time window applies to analytics only; current balances and the latest-batch journal preview say so. A product could group multiple currency accounts into one wallet, but this change does not pretend that grouping exists in the ledger model.

The charts include exact bucket tables, empty states, and stale-data messages. There are no invented percentages or HTTP latency metrics. The responsive rules stack panels and navigation at smaller widths while keeping wide accounting tables scrollable. Sites and visualization guidance informed the layout and metric definitions; the implementation remains in the existing Go application, with no third-party branding or crypto panels. AI assistance remains disclosed.

Codex rebuilt the local preview on port 8088. TypeScript and formatting checks passed. HTTP checks passed for both currencies and all three windows, invalid filters, and the blocked internal route. The transfer smoke test also passed idempotency, conflict, reconciliation, and delivery pause/recovery through the two-replica stack. These are code and HTTP checks, not browser interaction or responsive visual QA; that visual verification remains pending. The VPS was not changed.

### 20:57:00 — Check · Stop lake allocation before using the host's free disk

The pinned SeaweedFS mini command does not expose a volume-count limit. Running its help command inside the existing constrained local lake coincided with an exit-137 probe and one lake restart. The lake recovered; subsequent command probes ran in separate disposable containers. This is also why the earlier short memory samples are not treated as worst-case evidence.

An isolated full-server configuration now uses eight 32 MiB volume slots, with explicit persistent filer metadata and separate upload, CPU, memory, and log limits. Catalog authentication worked. The first arbitrary upload inside the table bucket returned 403, so it was not counted as a capacity test. A regular test bucket on the same isolated server accepted eleven 3 MiB objects, then refused the next write. Logs confirmed allocation exhaustion, and an earlier object's checksum matched both before and after a container restart.

Seven slots had already been allocated to metadata, leaving only one for that bucket. This is not 256 MiB of usable capacity, a filesystem quota, or a tested Iceberg retention policy. The evidence and commands are in `deploy/local/lake/BOUNDED-PROBE.md`. The working local lake and the VPS were not migrated. A fresh read-only VPS check still showed about 1,633 MiB available RAM, so the earlier 1,280 MiB full-stack ceilings plus reserve still do not fit.

Codex performed these local checks while the delegated agent worked only on the frontend. The worklog keeps that assistance explicit. Existing HTTP analytics and pause/recovery smoke tests are now included in the CI workflow; this records configuration, not a claim that remote CI has run.

### 21:05:00 — Act · Turn the dashboard into routed workspaces

At my request, a dedicated Codex agent worked only on the frontend while the main agent continued storage checks. The page now uses persistent hash-routed workspaces instead of a long anchor-scrolling document. The overview combines the compact KPI strip, simulation controls, real event-count chart, outcomes, accounts, watcher evidence, transfers, journal, and inspector. Mobile presentation uses event cards and a drawer/bottom sheet; separate System and Time views keep secondary explanations off the primary dashboard.

The styling uses shared dark tokens, restrained ambient light, clear outcome colors, keyboard focus handling, and reduced-motion rules. Search and journal display pause are scoped to the fetched preview. The chart shows recorded decision counts and declined/rejected counts, not invented monetary volume or latency. The inspector has Summary, Accounting, and Evidence tabs. No ledger policy or API behavior changed for this design.

TypeScript and formatting checks passed. The agent checked unique DOM IDs and literal lookups; the main agent reviewed routing and state handling and rebuilt the local image. These are implementation checks, not proof of visual fidelity or a browser-tested mobile interaction. That verification remains pending. The submitted assessment and production host were not changed.

### 21:16:00 — Fix · Check every dashboard route in the browser

The System screenshot exposed a real layout bug. The secondary-route reset had lower CSS specificity than the overview panel IDs, so the browser kept named grid positions and created narrow implicit columns. Codex corrected the reset, brought the desktop Transfers inspector alongside the form and journal, restored mobile route headings, and placed the transfer form before the journal on the mobile Transfers page. No ledger behavior changed.

Codex inspected screenshots of all six routes at 1920×1080, 1100×900, and 390×844. After rebuilding the two local API containers and restarting their local proxy, browser geometry checks covered all six routes at widths 1920, 1440, 1100, and 390: no document-level horizontal overflow or visible panel narrower than 150 pixels. Wide journal tables still scroll inside their own panel. The updated desktop Transfers layout and mobile event inspector were also inspected visually.

The mobile inspector opened from a real journal event, its Accounting tab selected correctly, Escape closed it, and the navigation drawer opened. Moving the time-laboratory cutoff to zero produced zero balances. TypeScript and formatting checks passed. These are Chromium checks at the listed sizes, not a cross-browser accessibility audit or a load test. AI assistance remains explicit. The submitted PDF and production host were not changed.

### 21:18:00 — Check · Try Lakekeeper without replacing the working lake

Codex tested a separate, local-only Lakekeeper catalog with its own PostgreSQL and bounded SeaweedFS storage. Catalog bootstrap, S3 validation, namespace/table creation, and ClickHouse discovery passed. Repeating the probe after a catalog restart preserved the warehouse and table identities. The table is empty: this is not evidence that CDC or recovery works with this catalog. Commands, ceilings and limitations are in `deploy/local/lake/LAKEKEEPER-PROBE.md`.

A fresh read-only VPS check showed about 1,638 MiB available RAM. The existing smaller full-stack ceilings plus the 512 MiB reserve still exceed that headroom, even before adding a separate catalog. No production workloads were stopped or changed. Lakekeeper remains a candidate, not a reason to skip the deployment gate.

### 21:24:00 — Act · Fence generator claims and commit the cursor with the result

The generator previously relied on duplicate-command replay plus a separate ordinal acknowledgement. Codex replaced that with a five-second claim and increasing token. The financial transaction validates and locks the claim before command/account locks, then commits the result and ordinal together. Expired or superseded workers cannot start that transaction. Deliberate recipe retries still advance the cursor without adding a journal batch. Recipe-version negotiation is not part of this change; changing recipes still requires pausing and draining both replicas.

Go formatting, vet, unit/race tests and the complete integration suite passed. Focused tests then also passed conflict rollback: the failed payload does not advance the cursor. Expiry/takeover tests use controlled database timestamps rather than claiming to kill a process at an exact instruction. A separate local container exercise stopped replica A; replica B advanced from ordinal 6816 to 6819, and A was restarted. Both local APIs now use the new image, and the requested rate is back to one event per second. Analytics HTTP checks passed for both currencies and all three windows, and the rebuilt overview rendered correctly in Chromium.

The submitted files and VPS were not changed. This also corrects the preceding Lakekeeper entry's timestamp and removes the stale README statement that all visual QA was still pending. Codex performed the implementation and testing work.

### 21:31:00 — Document · Make Go the branch entry point and expose the work

At my request, Codex pushed the signed Go-service history and opened draft PR #2 for visibility, without merging it. The root README now introduces the Go application and points to its run instructions, limits and implementation plan. The previous Python guide moved to `docs/python-assessment.md`; Python code, tests and the submitted PDF stay in their existing locations. This makes Go canonical on this branch without pretending that the assessment was a Go submission.

The first remote CI run failed during Compose startup because its blanket wait included the watcher, which has no Docker healthcheck. The workflow now starts the services and explicitly waits for PostgreSQL and the HTTP containers. The later watcher-expiry test remains in place. Its job name is now `compose-integration`, not `local-stack`: this project does not use the LocalStack AWS emulator. This records the fix, not a passing rerun. Codex assistance remains explicit.

### 21:34:00 — Check · Compare complete lake batches at a fixed source cutoff

Codex added a bounded read-only verifier that captures the source run and compares every envelope in the lake through that cutoff. It tolerates identical redelivery and rejects conflicting payloads. Initial SQL had alias-related ordering/type bugs in the test harness; those were corrected before using its result. Five pure comparison tests cover duplicates, missing identities, conflicting contents, JSON key ordering and unsafe numeric values.

The 12-batch assessment comparison passed. The live comparison first timed out at 5,461 of 6,911 batches. Inspection found the CDC process stopped after the earlier catalog interruption: it had exited with code 0, which bypassed its on-failure restart policy. An operator restart resumed from stored offsets; all 7,080 source envelopes at the next captured cutoff then matched. This is manual recovery evidence, not automatic supervision or lost-slot recovery. The supervision gap remains documented. No source facts were edited, no production services changed, and the full deployment goal remains open.

### 21:41:00 — Fix · Restart CDC after a clean-exit sink failure

Codex changed the local CDC policy to `unless-stopped` and applied that exact policy to the existing local container. The connector's clean exit after a catalog failure must not leave reporting silently stopped. Explicit operator stops still remain stopped. Existing resource and log limits were preserved; the production Swarm policy and prolonged-failure alerting are not established by this change.

An operator-only local test stopped the catalog until CDC restarted, then restored the catalog and compared complete source/lake envelopes. The first attempt reached the restart but failed on a query timeout; a separate check later matched 7,432 batches. The verifier now permits two process-timeout retries within the same catch-up budget and source cutoff. The repeated outage test passed with restart count 1 to 2 and all 7,517 captured batches matching; it needed zero timeout retries. Five comparison unit tests remain green. Both local API replicas stayed healthy, and no VPS services were touched.

GitHub's two runs for `bce2326` completed successfully, including Compose startup, generated-query drift, static/unit checks, application-role integration, HTTP checks and watcher expiry. This does not mean the optional lake profile ran in remote CI. The work was performed with Codex. The failed attempt remains recorded rather than rewritten as a first-pass success.

### 21:51:00 — Check · Measure retained lake metadata before enabling cleanup

Codex added a read-only catalog inventory. The offsets table kept 167 snapshots for one current row; the journal had 174 current files totaling about 1.5 MB. The storage directory occupied about 94 MiB in a following sample. Current file sizes are not the full retained footprint, and physical lake rows include local test runs rather than only the live demo. Source database size was about 45.5 MB, with about 2.1 MB of retained-slot WAL. These samples are not a daily growth forecast.

The inventory preserves large snapshot IDs exactly. Three tests cover adjacent 64-bit IDs, safe timestamps, empty tables, and missing or duplicate current-snapshot references. The pinned storage image exposes an Iceberg maintenance worker, but the worker/admin scheduler is not enabled and cleanup has not been tested. No snapshots or objects were deleted. Both GitHub runs for `deaede8` passed; the optional lake still has local-only integration evidence. The frontend agent is separately adapting the supplied template using frontend-design. The submitted PDF and VPS remain unchanged. Codex assistance is explicit here.

### 21:58:00 — Add · Expose source-side CDC state without claiming lake freshness

Codex added a read-only slot query and an additive `cdc_source` object on the status endpoint. It distinguishes absent, inactive, connected and invalidated source states, with retained WAL as exact text or null when unknown. It does not turn a connected consumer into a green reporting-consistency claim. No slot is created, dropped or resnapshotted by this endpoint; financial behavior and resource-guard rules are unchanged.

Go formatting, vet and unit/race checks passed. The complete application-role integration suite passed in 14.369 seconds, including the new read-permission check and the existing denial of watcher-lease renewal. Invalidated/absent states are covered by unit inputs, not a newly executed lost-slot recovery drill. The local image will be rebuilt with the frontend pass; this entry does not claim the new field is already running. The local README startup command also now waits explicitly for database/API/proxy readiness rather than waiting on the watcher as if it had a Docker healthcheck. This documentation was prepared with Codex.

### 22:12:00 — Improve · Apply the supplied visual direction to the working dashboard

At my request, Codex brought back the frontend agent and used frontend-design to adapt the supplied template. The application now has light/dark/system themes, locally served licensed fonts, a collapsible sidebar, grouped account views and denser route-specific layouts. Existing APIs, exact money and safety controls remain the source of truth. The template's invented balances, fake host jitter, simulated exports and misleading accounting examples were not imported.

The first rendered System layout still left large holes. Review led to a compact horizontal flow and independent health/reporting/recovery stacks. Another browser check found percentage bars blocked by CSP, making different counts look equal; DOM width assignments corrected that without weakening the security policy. All six desktop and mobile dark routes were visually reviewed, with additional light views. Geometry passed for six routes × two themes × four widths (1920, 1100, 834 and 390), with no document horizontal overflow or panel overlap. Account snapshots, theme/sidebar persistence, system theme changes, reduced motion, mobile focus restoration and the 1450px transfer drawer were also checked. This is Chromium evidence, not a full accessibility or cross-browser claim.

TypeScript, formatting and five preference tests passed. Both local replicas were rebuilt with the final UI snapshot (image manifest `2187539ead45dc559dfba12f0c67b59e7b8870bcb0d6bc80a92c149426d27d19`). HTTP checks passed matching retries, changed-payload conflicts, balanced transfer, bounded delivery pause and recovery. The new source-side CDC field is running; it still does not claim lake freshness. GitHub's two runs for `1553174` passed before this UI commit. The work was performed with Codex and its delegated frontend agent. No changes were made to the submitted PDF or production workloads.

### 22:13:00 — Test · Observe a stopped CDC consumer through the API

Codex added and ran an operator-only local test that validates the CDC container's project/service labels, stops that consumer, checks the API reports inactive, and restores it in a finally block. Source state returned to streaming after restart. HTTP readiness remained available; retained WAL while stopped was 909,928 bytes. No slot or lake data was deleted. This is a stop/start visibility test, not proof of lost-slot recovery or complete downstream catch-up. The generator remained at its normal shared rate after the separate HTTP smoke test. The frontend changes are signed and pushed to the existing draft PR, not merged. This entry keeps Codex's role explicit.

### 22:35:00 — Check · Reduce the local budget and investigate storage OOMs

Codex tested a separate 1,152 MiB ceiling across all eight budget services. The first attempt gave SeaweedFS 128 MiB and restarted three times during startup; that setting was rejected. At 192 MiB for storage, 384 MiB for CDC and 192 MiB for ClickHouse, a short boost committed 691 batches. Fixture reads and reconciliation passed with zero container restarts. The largest aggregate memory sample was about 632 MiB, not an exact peak or evidence of sustained 20 events/sec. A complete comparison matched 1,479 envelopes before and after stopping and starting all eight budget containers with their volumes retained.

The separate main local lake was repeatedly restarting under its existing 384 MiB cap. Docker OOM events and the kernel's memory-cgroup kill established the cause; checking only the latest running state's OOM flag would have missed it. Recovery matched all 9,562 captured envelopes. Codex then added a soft Go runtime limit of 192 MiB in the main lake and 112 MiB in the budget lake, without raising either hard cap. The main lake had no new restart during the first seven minutes, and its next comparison matched 9,806 envelopes. This is initial evidence, not a fixed-load stability guarantee.

After applying the budget soft limit, its 1,479-envelope comparison passed again. The repeat burst was refused twice by the host-pressure guard. That protection stayed enabled, and the budget generator remains paused. The first direct test invocation also lacked Docker socket permissions; rerunning through the existing Docker-group shell resolved access, not the safety refusal. The current soft-limit profile still needs a successful repeat burst and longer observation.

Compose configuration, JavaScript syntax and whitespace checks passed. The later VPS sample had 1,604 MiB available; the smaller ceilings plus the 512 MiB reserve still exceed that. No production workloads were changed. Storage quotas, maintenance, lost-slot recovery and deployment remain open. Both GitHub runs for each of the preceding frontend and CDC-test commits passed. This entry was prepared with Codex and preserves the failed attempts.

### 22:55:00 — Test · Prepare explicit CDC resnapshot without hiding the safety gate

Codex verified the pinned connector contains Debezium PostgreSQL 3.6.0.Final and tested a local `trust_offset` override. Two ordinary starts resumed from existing offsets. The setting remains an experimental budget-stack overlay, not a changed default or production-support claim. The recovery overlay permits a new snapshot only when needed; the operator script must prove a deliberately missed batch returns, compare complete envelopes, preserve source fingerprints and then return to normal startup.

Neither fault attempt reached slot removal. The first waited two minutes for host admission, timed out before its transfer, and restored normal CDC. The second waited five minutes before stopping CDC and also timed out because host I/O pressure stayed unsafe. Both initial comparisons matched all 1,479 source envelopes without duplicates. The guards were not disabled; no financial record or replication slot was removed. The full missing-slot recovery path remains unexecuted, not passed.

Eight lake comparison/metadata unit tests, script syntax and Compose configuration checks passed. Both CI runs for the rewritten branch tip `1bf0ad7` passed. The main storage container still had zero restarts after its soft memory limit was applied, but variable host admission prevents treating elapsed time as a sustained-load benchmark. A stale README sentence now correctly distinguishes existing network delivery-attempt records from missing HTTP request correlation. No submitted files, other Git branches or production services changed.

### 23:05:00 — Add · Read complete statements at a fixed journal cutoff

Codex added a read-only, typed statement endpoint with exact minor-unit strings, debit/credit totals, running balances and cursor pagination. The cursor includes both batch sequence and posting leg. New commits cannot shift an existing statement, and explicit cutoff zero stays empty. SQL remains in named queries generated by SQLC. Prefix totals still scan qualifying account postings; page limits and a two-second request deadline bound the query rather than claiming constant cost.

The first integration setup incorrectly used future days in the current live profile, then used `authorize` instead of the supported `hold` command. Correcting those inputs and checking their outcomes left the actual policy unchanged. The full application-role integration suite passed in 12.519 seconds, including stable pages across a later commit, repeated pages through another replica, within-batch split pagination, empty BHD accounts, future-cutoff rejection and missing accounts. Go formatting, vet and unit/race tests passed; numeric tests cover totals beyond signed 64-bit range without JSON rounding.

Both local APIs were rebuilt. The first HTTP traversal hit the existing proxy rate limit after finishing AED; the test now paces reads without changing that limit. The repeated test passed all 293 AED and 287 BHD posting lines at cutoff 9,945, including running balances, totals, page boundaries, zero cutoff and invalid query responses. CI now runs this HTTP check. The Accounts UI and exports are not yet wired to the endpoint. No financial behavior, submitted files or production workloads changed.

### 23:24:00 — Add · Browse and export fixed-cutoff statements

Codex connected the statement API to the Accounts route through an internally scrolling dialog, with mobile posting cards and the existing light/dark themes. Previous/Next retain the cutoff; Refresh snapshot captures a new one. CSV downloads fetch all pages with exact minor-unit formatting, validate the complete result and protect untrusted text against spreadsheet formulas. The browser limit is explicitly 20,000 posting lines; larger server-streamed exports remain unimplemented. Cancellation or a failed request creates no partial file.

Formatting, TypeScript and all ten frontend tests passed. Both local replicas were rebuilt. Chromium checks downloaded 301 AED lines at cutoff 10,201 ending at 637.28 and 293 BHD lines at cutoff 10,237 ending at 1,999.189; those values matched the statement view. Pagination returned the identical first page, and refresh advanced the BHD cutoff to 10,264. Cancellation and an injected network failure each created zero download objects. Escape restored focus to the originating account button. Desktop and mobile screenshots were reviewed in both themes. This is not a full cross-browser or accessibility certification; the native dialog's Tab behavior still needs broader keyboard review.

The latest backend commit has one passing and one failing GitHub run. The failed HTTP smoke received 429 where it expected 200. The existing logs do not distinguish which admission condition refused it, so that diagnosis remains open rather than being called a rate-limit fix. No guard was relaxed, no submitted files were changed, and no VPS workloads were touched. This work used the frontend-design skill to preserve the existing visual system rather than introduce a new dashboard design.

### 23:27:38 — Test · Separate HTTP readiness from financial admission

Codex added a bounded 60-second wait for the existing database and host admission signals before the HTTP financial scenario. A healthy HTTP endpoint alone does not mean the independent watcher permits writes after the build and concurrency tests. The scenario still requires both concurrent requests to succeed and match; it does not retry away a failed financial assertion. Failures now print the returned response and observed guard state, and the transfer during the delivery pause must explicitly be accepted. The test restores the previously observed generator rate rather than assuming it was one.

JavaScript syntax and the complete local HTTP smoke passed. No admission rule, threshold or lease was changed. The older CI refusal's exact cause remains unproven; the new diagnostics are intended to make another refusal explainable. The preceding statement entry's clock label was corrected from 23:27 to 23:24, before its commit; this is a wording/timestamp correction, not new verification evidence.

### 23:31:48 — Check · Recover a deliberately missed batch after slot loss

Codex completed the previously blocked recovery drill on the isolated, paused budget stack with the real host guard enabled. The initial 1,479-envelope comparison passed. With CDC stopped, an accepted AED 0.01 transfer created batch 1,480, which was absent from the lake. Only the inactive replication slot was removed. Ordinary startup refused the unavailable source position; financial reconciliation and the source fingerprint remained intact.

The explicit recovery overlay took a fresh snapshot. Streaming became visible before the missing batch reached the lake, so the verifier waited rather than equating connection health with correctness. Complete comparison then matched 1,480 live envelopes across 2,959 physical rows and all 12 assessment envelopes across 24 rows. Those extra rows are identical redeliveries, not extra money. Ordinary startup resumed using the new offsets and the live comparison passed again, with zero query-timeout retries. Recovery left the ordered source journal unchanged. The final API check reported both replicas healthy, generation still paused and 110,480 bytes of retained WAL.

This passes slot-removal/resnapshot recovery for the tested local overlay. It does not establish checkpoint-driven WAL invalidation, crash safety between lake and offset commits, retention cleanup, an ongoing reporting watermark, default-profile integration or VPS capacity. No production workload was changed. The earlier failed pre-fault attempts remain in the log.

### 23:34:57 — Fix · Address both replicas explicitly in the lease test

Both CI runs for the admission-wait change passed the financial HTTP smoke. One later failed the expired-lease test because its six proxy requests observed only one instance. The test had assumed a small sample of load-balanced requests must cover both replicas; that is not a reliable coverage contract.

Codex added a disposable, resource-bounded Compose test runner that addresses each API directly as well as the proxy. Every target must refuse financial commands, rate increases and chaos under an expired lease, allow pause, identify its serving instance and leave the journal unchanged. Syntax and Compose validation passed. The local drill passed with both replica IDs, then the watcher was restarted. After observing its safe lease, normal one-event-per-second generation was restored through the existing API. No production services or admission rules changed. CI and the documented local command now use this deterministic test path.

### 23:38:40 — Improve · Compare larger lake prefixes in bounded chunks

Codex replaced the verifier's all-at-once 10,000-batch read with a captured source count/cutoff and ordered 1,000-envelope chunks, up to the existing 100,000-batch run ceiling. Query/output limits remain, with a two-minute per-chunk catch-up window and ten-minute overall budget. Count and final-cutoff checks detect truncated source traversal; a final retained-prefix count check rejects concurrent source cleanup. The verifier still compares complete envelopes, rejects conflicts and unexpected identities, and counts identical redelivery once. Separate chunks can observe different Iceberg snapshots, so this is not an atomic lake snapshot or an ongoing watermark.

Eight pure tests passed, including wide sequence IDs, malformed chunks and 10,017 synthetic batches with redelivery. The main local comparison passed all 10,848 captured envelopes across eleven chunks, with no query-timeout retries. Its final range first lacked sixteen batches and waited for them to arrive. The recovered budget run matched 1,480 envelopes across 2,959 physical rows; the main assessment run matched all twelve. No source or lake data was changed. CI includes the new chunk tests. This bounds response memory; it does not prove indexed Iceberg queries or sustained throughput. Production workloads remain unchanged.

### 23:42:03 — Improve · Enable tested offset validation in the local default

After the isolated slot-loss drill passed, Codex added `trust_offset` to the default CDC properties. Normal snapshot mode remains `initial`: a missing position requires operator recovery rather than an automatic reset. The compatibility overlay keeps the same explicit setting for repeatable drills. The upstream Technology Preview qualification still applies to this pinned connector.

The main local CDC restarted using existing offsets, and its logs confirmed the selected policy. Both APIs remained healthy. Chunked comparison matched all 10,991 captured live envelopes and all twelve assessment envelopes, with no duplicates or query-timeout retries. The final range initially lacked 51 batches and waited for the lake commit. Compose validation and whitespace checks passed. Both CI runs for the explicit-replica lease test passed. No source records, slots or lake objects were deleted in this change; no VPS services were touched. Checkpoint invalidation, retention and production resource gates remain open.

### 23:48:05 — Add · Establish the durable calendar transition boundary

Codex added immutable day transitions and durable per-customer close jobs. An internal transition locks the run lifecycle exclusively, waits for old-day commands, creates every job and advances the day atomically. Concurrent or later retries of the same transition are idempotent. Next-day commands lock their accounts and refuse unfinished closes as operational errors, rolling back the command claim instead of recording a business rejection. An unrelated pending BHD close does not stop an AED transfer between already-closed accounts. The next day transition waits until all preceding closes finish.

The first SQLC generation found an ambiguous column in the job-scheduling query; qualifying the source columns fixed it. Generated queries, Go vet and unit/race checks passed. The two new runtime-role integration tests passed, followed by the complete integration suite in 13.951 seconds. Tests explicitly mark jobs done to exercise the boundary: the actual close executor and automatic scheduler are not implemented or enabled yet. The fixture and live demo day remain unchanged; this is not a claim of completed continuous simulation.

The backup drill now fingerprints fourteen tables, including calendar state. Its local run restored a 3,121,745-byte backup, matched all fourteen tables and found zero unbalanced batches. The restore/verification portion took 19.445 seconds. Cleanup removed only the disposable restored database; both local APIs restarted healthy and HTTP readiness passed. No VPS workload changed. The next step is executing close jobs with immutable daily accounting evidence, then recurring periods and scheduler integration.

### 23:53:52 — Add · Execute account closes with immutable accrual evidence

Codex implemented the internal close executor. It locks lifecycle, operation identity, account and close job in order, then records one journal batch and outbox item while completing the job in the same transaction. The evidence carries posted balance, exact daily interest and the persisted policy. Accrual does not move posted or reserved funds. Public commands cannot occupy the reserved `system:` operation namespace.

Eight concurrent retries across the two runtime stores returned the identical recorded response and produced one close batch and one outbox item. A reservation did not reduce the interest basis. Negative live balances persist a blocked-job reason without minting a fee or recording a fake successful close; another closed account still accepted its credit. Existing calendar tests now execute real closes rather than manually completing jobs. Go vet, unit/race checks, four targeted integration tests and the full integration suite passed; the full suite took 13.765 seconds.

The executor is not yet scheduled automatically. Recurring capitalization, scheduler admission and the calendar UI remain unfinished, and the live demo day has not advanced. The fixture's fee/finalization policy is unchanged. No VPS service was modified.

## 2026-09-05 — Go service experiment, continued

### 00:22:35 — Add · Capitalize recurring simulation periods atomically

Codex added per-account capitalization to every sixth daily close. The final daily accrual, balanced interest credit, immutable period record, close completion and outbox commit in one transaction. There is no interval where next-day spending sees a completed close but misses the interest credit. Prior daily amounts come from the immutable close envelopes, with sequence links in the period evidence. The six-day cadence is a fixed simulation rule, not a banking month or a configurable calendar. Zero-interest periods are recorded without zero postings; the fixture's terminal finalization is unchanged.

The integration scenario exercised twelve days, three accounts, both currencies and concurrent retries through both runtime stores. Exact half-even ties demonstrate why summing daily rounded amounts differs from rounding the period total. The second period includes the preceding capitalization in its balance basis. Late retries preserved the original response, booking day and instance. An intentionally blocked local period-table insert forced a failure after money and journal writes were staged: balances, journal clock, command claim and job state all rolled back. Runtime permissions and immutable triggers prevented period changes.

SQLC generation, Go vet, unit/race tests and the full integration suite passed; the latter took 18.725 seconds. Backup/restore matched all fifteen financial/delivery/calendar tables from a 3,666,959-byte backup and found zero unbalanced batches. Restore and verification took 26.029 seconds. Cleanup deleted only the disposable restored database; the source remained intact and both local APIs restarted healthy. Both CI runs for the preceding close-executor commit also passed.

This is tested internal behavior, not an enabled calendar. Automatic scheduling, scheduler safety/admission, generated-command dates, the calendar UI and closed-period corrections still need work. The running demo has not been advanced by this change. No VPS services, submitted PDF or main-branch files were modified.

### 00:27:30 — Fix · Preserve generated-command identity across virtual days

Codex moved generated-command date assignment inside the financial transaction, after its lifecycle lock and generator fence. New work receives the locked run day. A deliberate recipe retry restores only the original committed dates before computing the payload hash; changing other inputs still conflicts. Public commands keep their explicit-date validation. This removes the generator's effective Day-1-only behavior without turning retries into new commands at midnight.

The new integration test commits on Day 1, advances to Day 2, replays the original result while close jobs remain pending, refuses new money until those closes finish, then posts the new generated command on Day 2. A public stale-date request remains rejected. Existing stale-worker, expired-claim, changed-payload and durable-cursor tests still pass. Go vet, unit/race tests and the full integration suite passed; the full suite took 18.962 seconds. Both CI runs for recurring capitalization passed as well.

Automatic calendar scheduling and its host/database admission gate are still not enabled. This changes the generator transaction path, not the existing VPS deployment or submitted assessment artifacts.

### 00:35:45 — Add · Gate scheduled calendar work with shared admission

Codex added a bounded calendar step: drain one pending account close, otherwise attempt one due transition. A five-minute simulation day is measured from the preceding committed transition, not caught up in a loop after downtime. The exclusive lifecycle lock makes the due-time check and transition atomic across replicas. Both transitions and closes use the existing shared operation budget, host lease, database guard and journal ceiling inside their transaction. Generator pause stops new transitions but allows existing closes to drain if safety permits. Blocked jobs remain visible and are not blindly retried.

The maintenance worker now supports an explicit `CALENDAR_ENABLED` boolean, off by default. API status includes the serving instance's flag, day, pending/blocked counts, nominal next transition time and cadence. The local Compose configuration still leaves it off: the transfer UI must stop submitting hardcoded Day-1 dates before activation. Calendar exhaustion/run rotation and controlled resolution of blocked jobs are still open work.

SQLC initially rejected an ambiguous run column and then generated a nullable due-time boolean. Qualifying the column and making the nullable fallback explicit fixed those build failures. Go vet, unit/race tests and the full integration suite passed; the full suite took 20.700 seconds. A separate disposable database exercised missing/expired host leases, an expired database guard, safety pause, concurrent replicas, paused close draining and no immediate second transition. The additional run-ceiling refusal check passed in the targeted rerun. Cleanup removed those test databases; an inventory query confirmed none remained. The real demo's watcher evidence was not overwritten.

Both local API containers were rebuilt and restarted healthy. The live status endpoint reported Day 1, scheduling disabled and zero pending/blocked closes. The HTTP smoke passed idempotency, conflict, balanced transfer, bounded delivery pause and recovery. The previously stopped integration container was preserved despite Compose's orphan warning. Both CI runs for the preceding generated-date fix passed. No VPS workload or submitted artifact changed.

### 00:43:03 — Connect · Display the calendar and enable it locally

Codex added a compact calendar readout to the existing health panel and current-day context to the transfer form. Transfers fetch and validate fresh calendar evidence before sending instead of hardcoding Day 1. Unavailable or malformed calendar data stops submission; a boundary race remains an explicit server outcome, not an automatic financial retry. Two frontend tests cover evidence validation and status priority. All twelve frontend tests, formatting and TypeScript compilation passed. The first attempt used the Go toolchain container, which has no npm; the frontend checks were then run with the installed local Node toolchain.

The main Compose stack now explicitly enables the calendar on both replicas. The separate compact recovery overlay explicitly disables it so its fixed-day drills remain controlled. After the local rebuild, the run advanced to Day 2, visibly drained seventeen remaining jobs, and finished all forty account closes. A browser-submitted AED 0.01 transfer was accepted as batch 14004; PostgreSQL confirmed booking/value days 2/2. The HTTP smoke now reads the current day and waits for close completion after pausing generation. It passed and restored one event per second.

Desktop screenshots at 1920×1080 and mobile at 390×844 were inspected, including the calendar section in light mode. The readout uses existing surfaces and typography rather than adding another dashboard card. The browser session was closed afterward. This verifies the first live calendar transition and a post-transition browser transfer, not a completed live six-day capitalization cycle or a multi-day soak. Period-specific inspector explanations, rotation, corrections, analytical freshness and deployment gates remain open. No VPS service or submitted artifact changed.

Post-push hygiene check: the newly generated `calendar.js` needed the same ignore treatment as the other TypeScript build outputs. The source module is tracked; the compiled file stays a build artifact.
