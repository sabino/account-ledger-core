# Architecture & Trade-offs

This document is the working source for my Architecture & Trade-offs PDF.

## Append-only at scale

I will ground this section in the implementation's actual storage and access patterns before naming a bottleneck.

## Value-dated entries in production

I will ground this discussion in the time model I implemented.

## Authorization lifecycle

I will separate the model's supported transitions from my production recommendations.

## What I cut and why

My current deliberate cuts:

- I did not build durability or concurrency behavior; those remain production concerns outside this in-memory core.
- I did not build a distributed runtime or consensus model; horizontal partitioning and cross-partition transfers remain production concerns.
- I did not build an FX engine; I retain each account's currency precision without inventing conversion policy.
- I did not build regulatory-reporting integration; I will address value-date audit and control implications in this document.
