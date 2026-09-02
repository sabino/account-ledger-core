# Ambiguities

I use this as a live decision log. I leave `Open` entries intentionally unresolved in the initial language-neutral scaffold, and I will resolve every entry before I call the implementation complete.

## AMB-01 — Stream sequence, booked day, and value date

**Ambiguity:** Events have a supplied replay order, a booked day, and a `value_date`. E10 is labelled Day 5 but follows the Day 6 E9 in the required stream order.

**Resolution:** Preserve supplied sequence as ingestion order. Never sort or mutate events. Balance queries will distinguish the knowledge/sequence cutoff from the effective `value_date` cutoff. The exact per-day presentation for the late-listed E10 remains **Open** until the output contract is designed.

## AMB-02 — Meaning of “closing balance evaluated at end of Day N”

**Ambiguity:** A historical day's balance changes when E7 and E9 arrive with Day 2 value dates.

**Resolution:** A balance result must identify both `balance_day` and `known_through_sequence` (or equivalent). A printed number without both semantics is not sufficient internally, even if the human-readable report uses a shorter label.

## AMB-03 — Fee assessment after a backdated event

**Ambiguity:** The rules do not explicitly describe when a newly received backdated entry causes prior daily fee eligibility to be recomputed.

**Resolution:** After an accepted backdated monetary posting, scan each affected value day through the maximum booked day observed in the current replay prefix, in ascending day order. Generate exactly one fee for each negative close using a stable account/assessed-day identity. An earlier fee participates in later daily closes. At E7 this produces fees for Day 2, Day 4, and Day 5.

## AMB-04 — Fee consequences after reversal

**Ambiguity:** E9 reverses E7 but there is no instruction to reverse overdraft fees that E7 caused.

**Resolution:** A reversal only appends an equal and opposite effect for its target. It does not delete the target or independently generated fees. Removing a fee would require a separate linked fee-reversal event and an explicit policy; none is supplied, so no automatic fee reversal will be invented.

## AMB-05 — Settlement below the authorization hold

**Ambiguity:** Auth-A holds AED 200.00 and later settles for AED 185.00. The prompt does not state partial-capture or tolerance rules.

**Resolution:** Accept a positive settlement for an active matching authorization when it does not exceed the hold, debit the actual settlement amount, and release the authorization's full remaining hold. Treat it as a single final capture. Multi-capture and over-capture are out of scope and must be rejected explicitly if encountered.

## AMB-06 — Unknown authorization settlement

**Ambiguity:** The prompt does not prescribe an error representation for Auth-Z.

**Resolution:** Append/preserve evidence of the rejected settlement attempt, emit a deterministic domain error in replay output, create no debit, and create no authorization implicitly.

## AMB-07 — Authorization approval sufficiency and representation

**Ambiguity:** “Approved only if available remains nonnegative” states a necessary condition but does not formally say it is sufficient. The prompt also does not say whether a declined authorization remains in history.

**Resolution:** For otherwise valid supplied authorization events, make the nonnegative post-hold test both necessary and sufficient; this core has no separate fraud, risk, merchant, or scheme rules. Preserve every authorization event and its approved or declined outcome. A declined authorization creates no active hold.

## AMB-08 — Authorization lifecycle after the six-day window

**Ambiguity:** Auth-B is never settled inside the window; no expiry time or release event is supplied.

**Resolution:** Keep an approved hold active through Day 6 unless the actual balance test rejects it. Do not invent an expiry. Production expiry and release states will be discussed in the architecture document rather than synthesized into the fixture.

## AMB-09 — BHD 10.000 split into three equal instalments

**Ambiguity:** Exact equality is impossible at BHD's required three-decimal precision because `10.000 / 3` is recurring.

**Resolution:** Allocate atomic minor units deterministically so the entries sum exactly to BHD 10.000. `divmod(10000, 3)` yields 3333 and remainder 1; assign the extra unit to installment number 1, meaning the first installment, and produce 3.334, 3.333, and 3.333.

## AMB-10 — Fee currency for a non-AED account

**Ambiguity:** The fee is specified as AED 25.00 “per account,” while ACC-002 is a BHD account.

**Resolution:** Do not invent FX or allow mixed-currency postings in an account. The supplied stream never makes ACC-002 negative, so the ambiguity is not exercised. A production product-specific fee schedule is deferred.

## AMB-11 — Daily-interest ordering

**Ambiguity:** The prompt does not explicitly state whether a day's interest is calculated before or after that day's fee, or whether Day 6 interest includes the capitalization credit posted at the end of Day 6.

**Resolution:** After the complete E1–E10 replay and fee generation, calculate interest once from the final known post-fee, pre-capitalization Day 1–Day 6 closes. Use round-to-nearest, ties-to-even at currency precision. Calculate Day 6's accrual before appending one capitalization credit per account/currency, so the capitalization does not earn interest on itself.

## AMB-12 — Interest denomination and scope

**Ambiguity:** The rate is global wording and does not explicitly say whether it applies to both accounts/currencies.

**Resolution:** Apply it to every positive account balance in the account's own currency and precision; no FX translation is involved.

## AMB-13 — Idempotency of generated fees and capitalization

**Ambiguity:** A replay can recompute the same derived financial effects more than once.

**Resolution:** Generated entries need stable identities derived from their cause and period, and duplicate generation must be rejected or return the existing result. Exact key shape remains **Open** until the event model exists.

## AMB-14 — Required intentionally failing test

**Ambiguity:** The assessment requires one failing test but does not say whether the ordinary correctness command must also fail.

**Resolution:** Keep the ordinary correctness suite separately runnable and green. Provide a documented separate command/target for one genuinely failing, inline-annotated test. Do not skip it or decorate it as an expected failure. The selected case delivers an ACC-001 AED 100.00 credit after Day 6 finalization, with booked day Day 6 and value date Day 3, and expects an append-only AED 0.16 interest correction. The bounded core deliberately lacks that closed-period correction protocol, so the separate command exits nonzero.

## AMB-15 — Numeric range and overflow

**Ambiguity:** Currency precision is specified but maximum amount is not.

**Resolution:** Store authoritative money as Python integers in each currency's minor unit: AED cents and BHD thousandths. Python integers do not silently overflow; practical capacity is bounded by available memory. Represent the 0.04% rate as the exact ratio `1 / 2500` and use an explicit integer round-to-nearest, ties-to-even operation. Reject amounts that cannot be expressed at the account currency's mandated scale.

## AMB-16 — Per-day authorization and error reporting

**Ambiguity:** The replay must print authorization states and errors per day, but the prompt does not say whether states are occurrence records or end-of-day snapshots, or whether an error repeats on later days.

**Resolution:** Print authorization states as end-of-day snapshots so an active, settled, or declined state remains understandable on later rows. Print an error only on the day its source event occurs. A rejected event is recorded but does not stop the rest of the replay.
