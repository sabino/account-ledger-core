# Rejected

I use this file to give my final verdict for every supplied acceptance criterion and to record implementation approaches I genuinely selected or attempted and then abandoned. When a criterion depends on an underspecified behavior, I evaluate it under the explicit policy I chose in `AMBIGUITIES.md`; I do not present that choice as the only possible interpretation.

## Verdict summary

- **Accept:** Claim-1, Claim-3, Claim-4, Claim-5.
- **Refuse:** Claim-2, Claim-6, Claim-7, Claim-8.

## Refused acceptance criteria

### Claim-2 — Refuse: E7 causes exactly one fee, on Day 2

Under my selected final-capture and historical fee-reconciliation policies, E7 makes three closes fee-eligible:

```text
Day 2: AED -370.00 before candidate fee
Day 4: AED -180.00 after the retained Day 2 fee
Day 5: AED -205.00 after the retained Day 2 and Day 4 fees
```

I therefore generate fee identities for Days 2, 4, and 5, not only Day 2.

This verdict is policy-conditioned. It depends on accepting E5's AED 185.00 final capture against the AED 200.00 hold and on rescanning closes affected by a late value-dated entry. An exact-match-only settlement policy could change the later closes. I refuse the criterion for my implemented and disclosed contract; I do not claim that the bare numbered rules alone mathematically force three fees.

### Claim-6 — Refuse: E9 restores all balances and fees to pre-E7 values

Immediately before E7, ACC-001's Day 5 close is AED 465.00. E9 appends an AED 620.00 posting that exactly compensates E7's principal, but the three separately appended AED 25.00 fee postings remain. The corresponding close is therefore:

```text
AED 465.00 - (3 × AED 25.00) = AED 390.00
```

I make E9 identify E7's direct debit only. No fee-refund event or cascade policy is supplied, and I do not reconsider Auth-B's earlier decline. Append-only accounting would permit separate compensating fee-refund entries; it does not justify inventing them.

### Claim-7 — Refuse: each BHD installment is 3.334

Exact arithmetic disproves the proposed equal values:

```text
BHD 3.334 × 3 = BHD 10.002
```

BHD 10.000 cannot be divided into three identical representable amounts at three-decimal precision. I use this as-equal-as-representable allocation instead:

```text
BHD 3.334 + BHD 3.333 + BHD 3.333 = BHD 10.000
```

I assign the single remainder unit deterministically to installment ordinal 1.

### Claim-8 — Refuse: discard an interest rounding remainder

The rounded daily accruals must reconcile exactly to the capitalized total. I construct each capitalization from the same rounded daily values that I store alongside it:

```text
ACC-001: 0.10 + 0.09 + 0.25 + 0.17 + 0.16 + 0.16 = AED 0.93
ACC-002: 0.000 + 0.000 + 0.000 + 0.000 + 0.004 + 0.004 = BHD 0.008
```

I create no remainder state to discard or allocate. A mismatch would violate my selected invariant; the normal finalization path prevents it by construction rather than relying on the lower-level journal append primitive to recompute the sum.

## Accepted criteria

- **Claim-1:** I accept it. At the E7 knowledge cutoff and excluding fee postings, the Day 2 close is `AED 1,200.00 - AED 950.00 - AED 620.00 = AED -370.00`. Authorization holds do not change ledger balance.
- **Claim-3:** I accept it under my disclosed final-capture policy. Auth-A is active for AED 200.00; the positive AED 185.00 settlement does not exceed the hold, so I capture it and release the unused AED 15.00.
- **Claim-4:** I accept it under my disclosed fail-closed policy. I retain E6 as an `AUTHORIZATION_NOT_FOUND` rejection and produce no debit or implicit authorization.
- **Claim-5:** I accept it as a conditional invariant. An approved hold changes available balance, not ledger balance. E3 demonstrates this by retaining an AED 250.00 ledger balance while AED 200.00 is held and AED 50.00 remains available. Auth-B itself is declined at E8 and creates no hold.

## Approaches abandoned during the build

### Approach-01 — Decimal-context money parsing

- **Why I considered it:** `decimal.Decimal` provides exact base-ten input and made scale validation concise.
- **Evidence that changed my decision:** My first parser depended on the ambient Decimal arithmetic context when multiplying by the currency scale. An arbitrary-size exact input exposed that this could round before conversion even though Python integers themselves have no fixed-width limit.
- **Why I abandoned it:** The input defines precision but no maximum amount; a context-dependent parser contradicted my chosen unbounded-integer model.
- **What replaced it:** Direct lexical validation followed by integer construction of whole and fractional minor units.
- **Cost or limitation I retained:** The accepted input grammar is deliberately plain decimal text; exponent notation and non-finite values are rejected.

### Approach-02 — Assessing fees only when a monetary posting arrived

- **Why I considered it:** E7 is the fixture's late value-dated posting, so scanning its affected days immediately was enough to produce the expected Days 2, 4, and 5 fees.
- **Evidence that changed my decision:** That approach missed quiet negative days with no later monetary event and treated a temporary negative after the first same-day posting as though the day had already closed.
- **Why I abandoned it:** A daily closing-balance rule requires an explicit close boundary, not merely a posting callback.
- **What replaced it:** I reconcile earlier days when the booked day advances, rescan immediately only for accepted backdated monetary effects, and sweep the remaining requested window before interest finalization.
- **Cost or limitation I retained:** My in-memory core uses supplied booked-day transitions and explicit finalization instead of a production clock or scheduler.

### Approach-03 — Reversing every posting produced by the target event

- **Why I considered it:** A generic event-to-postings lookup was a compact way to construct an opposite effect.
- **Evidence that changed my decision:** It would also have claimed unsupported reversal behavior for settlements or other posting kinds, although the fixture defines only E9's reversal of direct debit E7.
- **Why I abandoned it:** Reversal semantics depend on the originating domain command and cannot safely be generalized from a matching event ID alone.
- **What replaced it:** My bounded reversal command targets direct debit postings only, links every compensating posting to the exact original record, and rejects missing, non-debit, or already-reversed targets.
- **Cost or limitation I retained:** Settlement refunds, credit corrections, fee refunds, and multi-stage payment reversals remain outside this core.

### Approach-04 — Identifying interest finalization only by its ending day

- **Why I considered it:** The fixture has one fixed Day 6 close, so an identity containing only Day 6 initially appeared sufficient.
- **Evidence that changed my decision:** Finalizing Days 1–6 and Days 2–6 would otherwise collide despite representing different accrual windows.
- **Why I abandoned it:** Idempotency must cover the complete operation, not only one boundary field.
- **What replaced it:** I store both `start_day` and `through_day`, derive `interest-finalization:days:{start_day}-{through_day}`, and require the same policy version when returning an existing result.
- **Cost or limitation I retained:** My bounded ledger still supports only one finalized interest window and cannot reopen or version a closed period.

## Reference experiments retained, not rejected

I used Formance and strict Numscript as external validation tools, not as abandoned deliverable implementations. They tested arithmetic, atomic movement, schema, and policy-placement boundaries. I had already selected Python for the deliverable and retained no Formance dependency. Likewise, I evaluated Clojure, Babashka, Joker, Go, and other languages but did not begin implementing the deliverable in them, so I do not inflate them into mid-build rejection entries.
