# Ambiguities

I use this as a live decision log. I leave `Open` entries intentionally unresolved in the initial language-neutral scaffold, and I will resolve every entry before I call the implementation complete.

## A-01 — Stream sequence, booked day, and value date

**Ambiguity:** Events have a supplied replay order, a booked day, and a `value_date`. E10 is labelled Day 5 but follows the Day 6 E9 in the required stream order.

**Resolution:** Preserve supplied sequence as ingestion order. Never sort or mutate events. Balance queries will distinguish the knowledge/sequence cutoff from the effective `value_date` cutoff. The exact per-day presentation for the late-listed E10 remains **Open** until the output contract is designed.

## A-02 — Meaning of “closing balance evaluated at end of Day N”

**Ambiguity:** A historical day's balance changes when E7 and E9 arrive with Day 2 value dates.

**Resolution:** A balance result must identify both `balance_day` and `known_through_sequence` (or equivalent). A printed number without both semantics is not sufficient internally, even if the human-readable report uses a shorter label.

## A-03 — Fee assessment after a backdated event

**Ambiguity:** The rules do not explicitly describe when a newly received backdated entry causes prior daily fee eligibility to be recomputed.

**Resolution:** **Open.** The intended interpretation appears to recompute each affected value-dated close through the applicable knowledge cutoff, with a deterministic fee identity per account/day. Confirm by completing the full hand-worked replay before implementation.

## A-04 — Fee consequences after reversal

**Ambiguity:** E9 reverses E7 but there is no instruction to reverse overdraft fees that E7 caused.

**Resolution:** A reversal only appends an equal and opposite effect for its target. It does not delete the target or independently generated fees. Removing a fee would require a separate linked fee-reversal event and an explicit policy; none is supplied, so no automatic fee reversal will be invented.

## A-05 — Settlement below the authorization hold

**Ambiguity:** Auth-A holds AED 200.00 and later settles for AED 185.00. The prompt does not state partial-capture or tolerance rules.

**Resolution:** Provisionally accept a settlement for an active matching authorization when it does not exceed the hold, debit the actual settlement amount, and release the authorization's full remaining hold. Multi-capture and over-capture are out of scope and must be rejected explicitly if encountered.

## A-06 — Unknown authorization settlement

**Ambiguity:** The prompt does not prescribe an error representation for Auth-Z.

**Resolution:** Append/preserve evidence of the rejected settlement attempt, emit a deterministic domain error in replay output, create no debit, and create no authorization implicitly.

## A-07 — Rejected authorization representation

**Ambiguity:** The rule defines when an authorization is approved but not whether a rejected authorization disappears or remains in history.

**Resolution:** Preserve the authorization event and its rejected state for auditability, but create no active hold.

## A-08 — Authorization lifecycle after the six-day window

**Ambiguity:** Auth-B is never settled inside the window; no expiry time or release event is supplied.

**Resolution:** Keep an approved hold active through Day 6 unless the actual balance test rejects it. Do not invent an expiry. Production expiry and release states will be discussed in the architecture document rather than synthesized into the fixture.

## A-09 — BHD 10.000 split into three equal instalments

**Ambiguity:** Exact equality is impossible at BHD's required three-decimal precision because `10.000 / 3` is recurring.

**Resolution:** Allocate atomic minor units deterministically so the entries sum exactly to BHD 10.000. The exact tie-break order for distributing the single extra minor unit remains **Open** until the event representation is chosen.

## A-10 — Fee currency for a non-AED account

**Ambiguity:** The fee is specified as AED 25.00 “per account,” while ACC-002 is a BHD account.

**Resolution:** Do not invent FX or allow mixed-currency postings in an account. The supplied stream never makes ACC-002 negative, so the ambiguity is not exercised. A production product-specific fee schedule is deferred.

## A-11 — Daily-interest ordering

**Ambiguity:** The prompt does not explicitly state whether a day's interest is calculated before or after that day's fee, or whether Day 6 interest includes the capitalization credit posted at the end of Day 6.

**Resolution:** **Open.** The proposed ordering is: apply known value-dated financial events, assess at most one fee, calculate/store that day's rounded accrual from the resulting positive close, and on Day 6 append one credit equal to the exact sum of stored accruals. The capitalization must not earn interest on itself that day.

## A-12 — Interest denomination and scope

**Ambiguity:** The rate is global wording and does not explicitly say whether it applies to both accounts/currencies.

**Resolution:** Provisionally apply it to every positive account balance in the account's own currency and precision; no FX translation is involved.

## A-13 — Idempotency of generated fees and capitalization

**Ambiguity:** A replay can recompute the same derived financial effects more than once.

**Resolution:** Generated entries need stable identities derived from their cause and period, and duplicate generation must be rejected or return the existing result. Exact key shape remains **Open** until the event model exists.

## A-14 — Required intentionally failing test

**Ambiguity:** The assessment requires one failing test but does not say whether the ordinary correctness command must also fail.

**Resolution:** Keep the ordinary correctness suite separately runnable and green. Provide a documented separate command/target for one genuinely failing, inline-annotated test. Do not mark it skipped or expected-to-fail merely to make the test runner green. Select its subject only after the design exposes a real limitation.

## A-15 — Numeric range and overflow

**Ambiguity:** Currency precision is specified but maximum amount is not.

**Resolution:** Use an exact numeric representation with checked failure rather than floating point or wraparound. The concrete type and supported range remain **Open** pending the language decision and will be documented in NUMBERS.md.
