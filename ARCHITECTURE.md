# Architecture & Trade-offs

This is an implementation-dependent outline. I will fill it with concrete evidence after the ledger exists.

## Append-only at scale

I will ground this section in the implementation's actual storage and access patterns before naming a bottleneck.

## Value-dated entries in production

I will ground this discussion in the time model I implement.

## Authorization lifecycle

I will separate the model's supported transitions from my production recommendations.

## What I cut and why

My current deliberate cuts:

- I am not building a distributed runtime or consensus model; horizontal partitioning and cross-partition transfers remain production concerns.
- I am not building a production FX engine; I retain each account's currency precision without inventing conversion policy.
- I am not building regulatory-reporting integration; I will address value-date audit and control implications in this document.
