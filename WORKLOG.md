# Worklog

All timestamps use America/Sao_Paulo (`UTC-03:00`).

## How I kept the log

I used a lightweight Plan–Do–Check–Act loop. I planned by turning uncertain wording into explicit questions, did the smallest useful piece, checked it against arithmetic and tests, and acted on what the checks exposed.

The times below are real checkpoints, not claims that I worked continuously between them. When several related changes landed at the same recorded second, I describe them as one checkpoint instead of inventing a false minute-by-minute sequence. AI tools helped with research, independent review, implementation, tests, and editing. I made the final policy choices and remain responsible for the result.

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

I gave the untouched specification to three independent AI reviewers with different focuses: arithmetic and time, adversarial specification reading, and implementation choices. I compared their anonymized answers with mine rather than asking them to confirm my preferred result.

The reviews converged on accepting Claim-1, Claim-3, Claim-4, and Claim-5 and refusing Claim-2, Claim-6, Claim-7, and Claim-8. Under the policy I was considering, they also reproduced three AED 25.00 fees, AED 0.93 interest, and BHD 0.008 interest. That agreement gave me confidence in the arithmetic, while the disagreements helped me identify which conclusions still depended on disclosed policy.

### 14:05:26 — Act · Choose Python and avoid a framework

I chose Python because the deliverable needed to be readable under discussion, not impressive through infrastructure. Arbitrary-size integers fit exact minor-unit money, dataclasses could keep the model explicit, and the standard test tools were enough. A framework or database would have added setup while hiding the decisions I actually needed to defend.

### 14:26:55 — Act · Fix the language of the model before it spreads

While writing out the mental model, I noticed that short acceptance labels could be confused with authorization identifiers. I renamed them to `Claim-1` through `Claim-8` and moved ambiguity labels to `AMB-*`. I also wrote down the difference between an input event, a policy decision, a journal fact, and a projection. No arithmetic changed; I was removing vocabulary that could make correct behavior hard to explain.

### 14:45:56 — Check · Work the scenario by hand

Before trusting code, I worked through authorizations, accepted and rejected events, postings, fees, daily closes, and interest seperately. I used that hand-worked result as the oracle for implementation. If the program disagreed, I wanted to investigate the transition where the disagreement began instead of adjusting an expected final balance until a test turned green.

## 2026-09-02 — Reference experiments

### 16:44:20 — Check · See what a real ledger engine would enforce

I replayed the scenario in Formance Ledger v2.4.12. Balanced movements, metadata, and atomic execution mapped well to the model, and the numbers agreed with my selected interpretation. The useful lesson was the boundary: the engine could reject an invalid movement, but it could not tell me whether the assessment intended a partial capture or an automatic fee refund.

### 17:39:30 — Check · Push schema and atomicity harder

I repeated the experiment with stricter Numscript templates, schemas, and rejection probes. That made me more comfortable keeping the journal narrow and uncompromising while placing the assessment-specific choices in pure policy functions. I kept the architectural lesson and dropped the external dependency from the deliverable.

## 2026-09-02 — Implementation

### 18:14:06 — Do · Model money and events first

I started with immutable money values and typed events because every later calculation depended on them. Amounts became integer minor units with an explicit currency scale and round-half-even behavior. I deliberately rejected exponent notation, excess precision, and cross-currency arithmetic rather than guessing what the caller meant.

