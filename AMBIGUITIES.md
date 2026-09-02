# Ambiguities

I use this log to record every underspecified point I found during design, implementation, and verification, together with the bounded policy I selected. Every decision below is closed for this implementation. I identify production behavior outside this six-day core explicitly instead of implying that I implemented it.

## AMB-01 — Stream sequence, booked day, and value date

**Ambiguity:** Events have a supplied replay order, a booked day, and a `value_date`. E10 is labelled Day 5 but follows the Day 6 E9 in the required stream order.

**Resolution:** I replay E1–E10 exactly in the supplied sequence and retain booked day and value day separately. The processing trace therefore shows E9 at commit 9 followed by E10 at commit 10, while still showing E10 as booked Day 5 and value-dated Day 5.

My daily financial report is a final-known, value-dated projection: a monetary posting contributes to Day N when its `value_day <= N`. E10 consequently appears in ACC-002's Day 5 and Day 6 balances and interest even though I process it after E9. The report header identifies the final event-knowledge commit and the later interest-finalization commit; I never rewrite the source stream into date order.

## AMB-02 — Meaning of “closing balance evaluated at end of Day N”

**Ambiguity:** A historical day's balance changes when E7 and E9 arrive with Day 2 value dates. Claim-1 also asks for a value before fees that are generated in E7's atomic append.

**Resolution:** I give every balance projection two explicit axes: `effective_through`, the value-day cutoff, and `known_through`, the immutable journal-commit cutoff. An append batch also retains an ordinal for each fact in that atomic commit.

E7 and its three derived fees deliberately share commit 7. I calculate Claim-1's “before any fee is assessed” value as an explicit projection at the E7 knowledge cutoff that excludes `OVERDRAFT_FEE` postings; I do not present it as a fictitious intra-commit state. The final daily report labels its global knowledge and finalization cutoffs.

## AMB-03 — Fee assessment after ordinary and backdated activity

**Ambiguity:** The rules define a daily closing-balance fee but do not define when a day closes, how a newly received backdated entry affects prior fee eligibility, or how quiet negative days are swept.

**Resolution:** I do not let a normal same-day posting immediately close its day or create a fee from a temporary intraday negative balance. When processing crosses to a later booked day, I reconcile every earlier day using the facts known at that boundary. Interest finalization performs a final sweep through the complete requested window, including days with no input event.

I handle an accepted backdated monetary posting separately: I rescan from its earliest affected value day through the latest recorded day in the current replay prefix. For each `(account, assessed_day)`, I calculate the close without the not-yet-created candidate fee but including fees already appended for earlier days. If that close is negative and the stable account/day fee identity does not exist, I append one fee. At E7 this produces fees for Days 2, 4, and 5.

## AMB-04 — Reversal scope and fee consequences

**Ambiguity:** E9 reverses E7, but the prompt does not define a generic reversal state machine or say whether E7's independently generated fees are refunded.

**Resolution:** I implement reversal only for direct debit postings in this bounded core. E9 appends an equal-and-opposite posting for E7 and links it to the exact reversed posting. I reject a missing target, a target that is not a direct debit, or an already-reversed target.

The reversal does not delete E7, reconsider authorization decisions, or implicitly reverse independently generated fees. Append-only accounting would permit separate compensating fee-refund postings, but no such event or cascade policy is supplied, so I do not invent one.

## AMB-05 — Settlement below the authorization hold

**Ambiguity:** Auth-A holds AED 200.00 and later settles for AED 185.00. The prompt does not state partial-capture, exact-match, or tolerance rules.

**Resolution:** I accept a positive settlement for an active matching authorization when it does not exceed the hold, debit the actual settlement amount, and release the authorization's full remaining hold. I treat it as a single final capture. Multi-capture and over-capture are outside my chosen scope and are rejected explicitly if encountered.

## AMB-06 — Unknown authorization settlement

**Ambiguity:** E6 references Auth-Z, which has no preceding authorization. Claim-4 proposes rejection without moving funds, but the non-negotiable rules do not independently define missing-authorization, forced-presentment, or error-recording behavior.

**Resolution:** I adopt the fail-closed behavior stated by Claim-4 for this bounded core. I store a settlement referencing an unknown authorization as an `EventRejected` receipt with `AUTHORIZATION_NOT_FOUND`; it creates no monetary posting and no implicit authorization. This is my selected domain policy, not a claim that every production payment rail lacks a separately controlled forced- or offline-presentment path.

## AMB-07 — Authorization approval sufficiency and evaluation time

**Ambiguity:** “Approved only if available remains nonnegative” states a necessary condition but does not formally say it is sufficient. A later backdated posting can also change the value-dated balance on which an earlier decision was based.

**Resolution:** For an otherwise valid supplied authorization, I make the nonnegative post-hold test both necessary and sufficient; this core has no additional fraud, risk, merchant, or scheme rules. I decide each authorization once at its supplied stream position and preserve the approved or declined fact. A later backdated posting does not rewrite that historical decision. A decline creates no active hold.

## AMB-08 — Authorization lifecycle after the six-day window

**Ambiguity:** Auth-B is never settled inside the window, and the prompt provides no expiry, cancellation, standalone release, or authorization-reversal event.

**Resolution:** An authorization I approve in this core remains active until its one matching final settlement; later value-dated entries do not retest it.

Auth-B is actually declined at E8 and never creates a hold, so “never settled” does not mean it remains active. I leave production expiry, cancellation, release, reversal, and forced-presentment states for the architecture document.

## AMB-09 — BHD 10.000 split into three equal installments

**Ambiguity:** Exact equality is impossible at BHD's required three-decimal precision because `10.000 / 3` is recurring.

**Resolution:** I allocate atomic minor units deterministically so the entries sum exactly to BHD 10.000. `divmod(10000, 3)` yields quotient 3333 and remainder 1; I assign the extra unit to installment ordinal 1, producing BHD 3.334, BHD 3.333, and BHD 3.333.

I retain E10 as one accepted source event. Its three child postings use stable IDs `posting:E10:1` through `posting:E10:3` and are appended in one atomic commit.

## AMB-10 — Fee currency for a non-AED account

**Ambiguity:** The fee is specified as AED 25.00 “per account,” while ACC-002 is a BHD account.

**Resolution:** I do not invent FX, translate the AED fee, or permit mixed-currency account postings. My assessment policy defines an AED fee only.

If an input command tries to append a backdated posting whose fee calculation needs an unsupported currency, or tries to cross a day boundary while a prior unsupported-currency close remains unresolved, I store that command as an `UNSUPPORTED_FEE_CURRENCY` rejection without its direct monetary effect. A same-day non-backdated BHD debit may still be offset before close. If a negative BHD close remains at administrative interest finalization, I fail the operation with `UnsupportedFeeCurrencyError` atomically before appending anything.

The supplied ACC-002 stream never becomes negative, so this fail-closed boundary does not alter the required replay.

## AMB-11 — Daily-interest ordering and fee asymmetry

**Ambiguity:** The prompt does not explicitly state whether interest follows fee generation, whether Day 6 interest includes capitalization, or whether a later value-dated reversal restates previously computed interest as it does not automatically refund fees.

**Resolution:** After replaying the complete stream, I first reconcile all overdraft fees through Day 6. I then calculate interest once from the final-known, post-fee, pre-capitalization Day 1–Day 6 closes. I retain each rounded daily accrual using round-to-nearest, ties-to-even at the account currency's precision.

Fees are path-dependent retained postings; uncapitalized interest is a final-restated view. I make this asymmetry explicit. I calculate Day 6 interest before appending one nonzero capitalization credit per account/currency, so capitalization does not earn interest on itself; if an account's rounded accrual sum is zero, I append no zero-value posting. The report labels both Day 6's pre-capitalization basis and post-capitalization close.

## AMB-12 — Interest denomination and scope

**Ambiguity:** The rate is global wording and does not explicitly say whether it applies to both accounts and currencies.

**Resolution:** I apply the rate to every positive account close in that account's own currency and precision; I perform no FX translation. A zero or negative close earns exactly zero interest.

## AMB-13 — Idempotency and generated identities

**Ambiguity:** Replaying an input or recomputing a derived financial effect can append duplicates unless both source and semantic operation identities are defined.

**Resolution:** I define input-event idempotency using the source event ID plus its complete content. Replaying the identical event returns the stored receipt and appends nothing; reusing the ID for different content raises `DuplicateEventIdError`. The journal atomically rejects duplicate record IDs.

I use semantic rather than trigger-specific generated identities:

- fee: `fee:{account_id}:day:{assessed_day}`
- daily accrual: `interest-accrual:{account_id}:day:{day}`
- capitalization: `interest-capitalization:{account_id}:day:{through_day}`
- finalization marker: `interest-finalization:days:{start_day}-{through_day}`

The event or operation that exposed a fee remains separate `caused_by` provenance; it is not part of fee uniqueness. I treat the policy-version string as the policy identity: repeating finalization for the same window and version returns the existing result, while a different window or version raises `AlreadyFinalizedError`. A caller must issue a new version whenever any policy field changes.

I retain the policy version on every stored fact, but this bounded core does not re-rate one journal under multiple policies. That would require a separately versioned production period or ledger projection.

## AMB-14 — Required intentionally failing test

**Ambiguity:** The assessment requires one failing test but does not say whether the ordinary correctness command must also fail or which design boundary it should expose.

**Resolution:** I keep the ordinary correctness suite separately runnable and green. I provide a documented separate command for one genuinely failing, inline-annotated test; I do not skip it or mark it as an expected failure.

The selected test finalizes Days 1–6, then receives on booked Day 7 an ACC-001 AED 100.00 credit value-dated Day 3. The controlled correction workflow asserted by this red test would preserve the original AED 0.93 capitalization, accept the principal, append an AED 0.16 interest correction, and produce AED 491.09; another production policy could instead reject the correction. My bounded core stores `FINALIZED_PERIOD_CORRECTION_UNSUPPORTED`, so the separate test exits nonzero.

## AMB-15 — Numeric range and input grammar

**Ambiguity:** Currency precision is specified, but maximum amount and accepted decimal grammar are not.

**Resolution:** I store authoritative money as Python integers in each currency's minor unit: AED cents and BHD thousandths. Python integers do not silently overflow; practical capacity is bounded by memory. I parse plain signed decimal text lexically, reject excess fractional precision, and do not accept exponent notation or non-finite values. I represent the rate as exact ratio `1 / 2500` and round with an explicit integer ties-to-even operation.

## AMB-16 — Per-day authorization and error reporting

**Ambiguity:** The replay must print authorization states and errors per day, but the prompt does not say whether states are occurrence records or end-of-day snapshots, how the two date axes apply, or whether an error repeats later.

**Resolution:** I deliberately use different axes for different output facts:

- the processing trace remains in immutable source/commit order and prints both booked day and value day;
- daily balances, fees, interest, and authorization snapshots are projected by effective/value day under the report's final knowledge cutoff;
- an error appears only on the rejected source event's recorded/booked day;
- rejected events remain in the journal and do not stop later replay.

I render authorization rows as end-of-day state snapshots so active, settled, and declined outcomes remain understandable after their occurrence.

## AMB-17 — Direct debit versus authorization scarcity

**Ambiguity:** The prompt explicitly bounds authorization approval by available balance, but does not say that a supplied direct debit must pass the same scarcity check. Applying the authorization rule to E7 would remove the intended overdraft-fee scenario.

**Resolution:** I do not reject E7, or another valid AED direct debit, solely because funds are insufficient; overdraft fees then govern its negative daily close. Other input invariants and the supported fee-currency boundary still apply. I apply the nonnegative available-balance rule only to authorizations and expose named domain operations rather than a generic caller-controlled “force” switch.

## AMB-18 — Counterpart accounts and double-entry scope

**Ambiguity:** The prompt names only two customer accounts and supplies signed credits, debits, fees, reversals, and interest. It does not identify funding, merchant, settlement, fee-income, or interest-expense counterpart accounts.

**Resolution:** I store the supplied effects as signed postings on the named customer accounts. I do not invent external origins, legal ownership, cash pools, or general-ledger counterparties. This is a scoped in-memory customer-ledger model, not a claim that a production ledger should omit balanced counter-entries and reconciliation.

## AMB-19 — Processing acceptance versus business decline

**Ambiguity:** The prompt describes authorization approval but does not define whether a valid authorization request that fails the balance test is an invalid event or a successfully processed business decline.

**Resolution:** I preserve the two axes separately. E8 is a valid command and receives an `EventAccepted` processing receipt plus an `AuthorizationDeclined` outcome for Auth-B; it creates no hold or monetary posting. E6 cannot execute its requested settlement because Auth-Z does not exist, so it receives only an `EventRejected` receipt. Both attempts remain auditable, but I do not treat a decline as a processing error.
