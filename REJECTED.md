# Rejected

I use this file to record acceptance criteria that conflict with the non-negotiable rules or exact arithmetic, plus approaches I genuinely abandon during the build. I keep it separate from AMBIGUITIES.md because an underspecified rule requires a transparent resolution, not a fabricated certainty.

## Refused acceptance criteria

I treat these classifications as provisional until the hand-worked replay and executable tests agree.

### Claim-2 — Refuse: E7 causes exactly one fee, on Day 2

E7 is value-dated Day 2 and therefore changes later value-dated daily closes as well. With historical fee eligibility recomputed through the knowledge cutoff, the negative balance is not confined to Day 2. A stable account/day fee identity prevents duplicates, but “exactly one” does not follow from the supplied rule.

### Claim-6 — Refuse: E9 restores all balances and fees to pre-E7 values

E9 can append an equal and opposite financial effect for E7. It cannot mutate or delete E7, and it does not automatically reverse separately appended fee events. Making the history identical to one in which E7 never arrived would violate append-only auditability.

### Claim-7 — Refuse: each BHD instalment is 3.334

Exact arithmetic disproves it:

```text
BHD 3.334 × 3 = BHD 10.002
```

The three representable instalments must instead differ by at most one BHD minor unit and sum exactly to BHD 10.000.

### Claim-8 — Refuse: discard an interest rounding remainder

The non-negotiable rule requires the rounded daily accruals to sum exactly to the capitalized total. Discarding a difference contradicts that rule. The capitalization must be derived from the stored rounded accruals or use an equally explicit reconciliation allocation.

## Criteria not currently refused

- **Claim-1:** The Day 2 pre-fee balance known at end of Day 5 is provisionally accepted: `AED 1,200.00 - AED 950.00 - AED 620.00 = AED -370.00`.
- **Claim-3:** Auth-A's settlement is provisionally accepted under the documented less-than-or-equal-to-hold resolution.
- **Claim-4:** Auth-Z's unknown-authorization settlement is rejected without moving funds.
- **Claim-5:** An approved hold affects available balance, not ledger balance; this conditional statement does not claim that Auth-B is approved in the stream.

## Approaches abandoned during the build

I have not abandoned an approach yet because the repository is still at the language-neutral scaffold stage. I will add an entry only when I actually attempt or seriously select an approach and then abandon it; I will not manufacture hindsight for presentation.

I will use this format:

```text
### Approach-NN — Short name

- Why it was considered:
- Evidence that changed the decision:
- Why it was abandoned:
- What replaced it:
- Cost or limitation retained:
```
