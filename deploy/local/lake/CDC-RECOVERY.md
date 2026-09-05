# Explicit local CDC resnapshot

This is an operator experiment on `ledger-budget`, not a production runbook or a public dashboard action. The normal connector must not silently skip an unavailable source position. Recovery keeps immutable source batches and appends a fresh lake snapshot; readers must deduplicate `(run_id, sequence)` and reject conflicting envelopes.

## Configuration under test

The pinned container contains `debezium-connector-postgres-3.6.0.Final.jar`. The [PostgreSQL connector documentation](https://debezium.io/documentation/reference/connectors/postgresql.html#postgresql-property-offset-mismatch-strategy) describes `trust_offset`: fail when the slot has advanced past the durable connector offset rather than trusting the newer slot position. The property is marked Technology Preview upstream, so this is a compatibility experiment, not a production-support claim.

The normal `offset-safety.yaml` overlay sets that policy. It has passed an ordinary restart using the existing durable offsets. The separate `resnapshot.yaml` overlay temporarily changes snapshot mode to `when_needed`. Under the [versioned connector validation](https://github.com/debezium/debezium/blob/v3.6.0.Final/debezium-connector-common/src/main/java/io/debezium/connector/common/BaseSourceTask.java), an unavailable source position can then trigger a new snapshot. It does not erase the financial journal or purge old lake rows.

From the repository root, with local Docker access:

```bash
LEDGER_HTTP_PORT=8089 docker compose -p ledger-budget \
  -f compose.yaml -f deploy/local/budget.yaml \
  -f deploy/local/compact-budget.yaml -f deploy/local/lake/offset-safety.yaml \
  up -d --no-deps cdc

node service/tests/cdc-resnapshot.mjs exercise
```

The exercise requires the existing eight-service budget stack, a paused generator and at most 5,000 source batches. It validates exact local container ownership. Do not run it while anyone else is changing this isolated dataset.

## What the exercise must prove

1. Normal ingestion has reached a complete captured source cutoff.
2. With CDC stopped, one accepted AED 0.01 transfer creates a batch absent from the lake. Public admission guards remain in force; unsafe host pressure postpones this step.
3. Only the inactive `ledger_lake` replication slot in the isolated PostgreSQL database is removed. No source rows, offsets table, lake objects or volumes are deleted.
4. Normal startup refuses the unavailable position, and the API reports the source slot absent. Financial reconciliation still passes.
5. The explicit recovery overlay snapshots the source and resumes streaming. Complete envelopes match for both the live run and the assessment fixture. Existing rows are redelivered, and identical duplicates must not multiply logical balances.
6. The ordinary configuration resumes using the newly persisted offsets. Comparison passes again, and the source-journal fingerprint is unchanged by recovery.

Failure before slot removal restores the normal consumer. Failure during recovery explicitly stops the consumer rather than advertising an incomplete recovery as healthy. The operator can retry without injecting another fault:

```bash
node service/tests/cdc-resnapshot.mjs recover
```

This command does not automatically drop an existing invalidated slot or advance a cursor. If a different failure needs those operations, investigate and resolve that exact target first.

## Evidence and limits

The first exercise attempt timed out waiting for host admission before creating its transfer. It restored normal streaming; no slot was removed and no financial records changed. The subsequent attempt added a five-minute pre-stop safety wait and checks that the transfer is genuinely absent from the old lake. That attempt also timed out at host admission, before stopping CDC. Both initial comparisons matched all 1,479 source envelopes with no duplicates.

The later attempt on 2026-09-04 passed with the host guard enabled. It stopped the isolated consumer, accepted an AED 0.01 transfer at sequence 1,480 and proved that batch was missing from the old lake. After slot removal, ordinary startup refused the unavailable source position. Explicit resnapshot recovery matched all 1,480 live envelopes (2,959 physical rows, including 1,479 identical redeliveries) and all 12 assessment envelopes (24 physical rows). Recovery preserved the ordered source-journal fingerprint and financial reconciliation passed. Returning to ordinary startup resumed streaming and the full live comparison passed again with the same counts and zero query-timeout retries. The generator remained paused.

The missing batch did not appear immediately when streaming became visible: comparison initially found 1,479 of 1,480 batches and waited for the remaining lake commit. This is direct evidence that a connected slot cannot be used as proof of reporting completeness. The stricter policy remains an explicit budget-stack overlay; this result does not claim that the default profile or a deployed service already uses it.

This test deliberately removes a slot; it does not generate 512 MiB of retained WAL, force checkpoint invalidation, measure retention overshoot, simulate a primary failover, or prove crash safety between a lake commit and an offset commit. A connected slot is still not an ongoing completed-ingestion watermark. Retention, maintenance, production supervision and the shared-host budget remain separate gates.
