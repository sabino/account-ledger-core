# Ambiguities

The assessment intentionally leaves business behavior unspecified. Each item below states the question and the choice implemented here. These are bounded choices, not claims about every bank or payment rail.

## AMB-01 — Event order

E10 is listed after E9 although its booked day is earlier. I preserve supplied order, store booked and value days separately, and never date-sort events.

## AMB-02 — Historical balance

A late value-dated event can change a historical balance. Every projection therefore has a value-day cutoff and a journal-knowledge cutoff.

## AMB-03 — Daily close

The close boundary is unspecified. I close prior days when booked time advances, rescan days changed by a backdated posting, and sweep once before interest. A temporary same-day negative balance does not receive a fee.

## AMB-04 — Reversal scope

It is unclear whether E9 also refunds fees caused after E7. I reverse only E7's debit. Existing fee facts remain; a refund needs its own event and policy.

## AMB-05 — Settlement below the hold

Auth-A settles for less than its AED 200.00 hold. I treat AED 185.00 as one final capture and release AED 15.00. Multi-capture is unsupported.

## AMB-06 — Unknown authorization

Forced settlement is unspecified. I reject E6, move no money, and create no implicit authorization.

## AMB-07 — Authorization approval

The prompt does not say whether its balance test is sufficient. In this exercise, an otherwise valid authorization is approved exactly when available balance remains nonnegative. Later information does not rewrite the decision.

## AMB-08 — Hold endings

Approved holds have no expiry, void, or cancellation rule. Here, an approved hold remains active until its one final settlement. Auth-B is declined and never becomes active.

## AMB-09 — BHD installments

BHD 10.000 cannot be divided into three identical three-decimal values. I allocate minor units left to right: BHD 3.334, 3.333, and 3.333.

## AMB-10 — BHD overdraft fees

The only supplied fee is AED 25.00, while ACC-002 uses BHD. I do not invent FX or a BHD fee. A negative BHD close that needs a fee fails explicitly.

## AMB-11 — Interest order

I reconcile fees, compute daily interest from final-known pre-capitalization closes, round each day, and capitalize the exact rounded sum.

## AMB-12 — Interest currency

I apply 0.04% to every positive close in that account's own currency and precision, including BHD.

## AMB-13 — Idempotency

The same event ID and content is an idempotent no-op. Different content with the same ID is an error. Derived IDs use stable business dimensions.

## AMB-14 — Required failing test

I keep it in `known_limitation/` with a separate command so the correctness suite stays green. It exposes missing post-finalization correction handling.

## AMB-15 — Number input

Maximum money size and input syntax are unspecified. I use arbitrary-size Python integers and plain decimal text. Exponents and excess precision fail.

## AMB-16 — Daily report semantics

I show authorization state at each day's end. An error appears only on the rejected event's booked day.

## AMB-17 — Ordinary debits

I apply the available-balance scarcity rule only to authorizations. A valid AED debit may overdraw the account and trigger fees.

## AMB-18 — Accounting boundary

The prompt gives no counterpart accounts. I model customer-account effects only and do not claim to be a balanced general ledger.

## AMB-19 — Declined versus rejected

E8 is an accepted request with a declined business outcome. E6 is a rejected request because its requested settlement cannot be performed.

## The two choices most likely to be challenged

### Why does E7 create three fees?

E7 arrives on Day 5 with value day 2. It changes the reconstructed closes for Days 2–5. Including retained earlier fees as days advance gives negative closes on Days 2, 4, and 5, so each receives one AED 25.00 fee.

### Why do those fees remain after E9?

E9 names E7's debit, not every later consequence associated with E7. The original facts remain visible and E9 adds the opposite AED 620.00 principal posting. With no fee-refund instruction, the program does not invent one.
