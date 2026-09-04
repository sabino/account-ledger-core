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
