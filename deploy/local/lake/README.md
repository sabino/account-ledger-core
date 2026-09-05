# Local reporting experiment

This profile exercises PostgreSQL → Debezium → Iceberg on SeaweedFS → self-hosted ClickHouse. It is not a VPS deployment configuration. All credentials are disposable local values and none of these services publishes a host port.

From the repository root:

```bash
docker compose --profile lake up -d
docker compose exec -T clickhouse clickhouse-client --user ledger_owner --password local-analytics-only --multiquery < deploy/local/lake/verify.sql
```

Initial ingestion can take a minute. The fixture check should show 12 unique batches, one envelope variant per sequence, and signed customer postings of -39093 AED minor units and -10008 BHD minor units. Customer accounts are liabilities, so their displayed balances have the opposite sign. The remaining asset, expense, and income legs balance those amounts per currency.

If ClickHouse's first initialization fails before creating the catalog, fix the startup error and explicitly rerun `catalog.sql` using the same client command. Container health alone does not prove the catalog exists or that CDC is caught up.

## What has been checked

The complete fixture was read through the REST catalog and its balances reconstructed from Iceberg envelopes. A graceful CDC container restart resumed ingestion from stored offsets. This is not a test of process death between the lake commit and offset commit, lost-slot recovery, or sustained capacity.

CDC is at-least-once. Consumers must group by `(run_id, sequence)` and reject conflicting envelope variants before trusting the result. `verify.sql` displays that variant count; it is a diagnostic, not an automated production reconciliation gate. Whole-batch envelopes avoid interpreting half a double-entry batch, but reporting remains asynchronous.

The bounded local verifier compares every complete envelope against a captured PostgreSQL cutoff, tolerates identical redeliveries, and fails on conflicting or unexpected batches:

```bash
node --test service/tests/lake-comparison.test.mjs
node service/tests/lake-reconcile.mjs ledger-lab assessment-v1
node service/tests/lake-reconcile.mjs ledger-lab demo
```

It permits only the two named local projects and known runs, up to the simulation's 100,000-batch run budget. It captures source count and cutoff together, then compares ordered ranges of at most 1,000 source envelopes. Each lake range has a 20,000-row result ceiling, 32 MiB command-output ceiling and 15-second query limit. A chunk can wait up to two minutes for ingestion, subject to a ten-minute overall budget; a running command can exceed the deadline by its bounded process timeout. At most two process-timeout retries are allowed across the entire comparison. Identical redeliveries count once, conflicting or unexpected identities fail, and missing source chunks or a changed retained-prefix count fail.

The source cutoff stays fixed while new source batches arrive. Lake queries may observe different Iceberg snapshots, so this is an incremental comparison of immutable envelopes, not one pinned lake snapshot or an ongoing reporting watermark. Queries can still scan many files; bounded response memory does not imply constant query cost. Run it with local Docker access; it does not change source or lake records.

On 2026-09-04, the fixture's 12 envelopes matched. The live check initially failed with 5,461 of 6,911 captured batches present. The CDC writer had exited after a catalog connection failure, while the reader and object store were healthy. It exited with code 0, so the original `on-failure:3` policy did not restart it. After an operator restart, the comparison passed for all 7,080 batches at a new cutoff. No conflicting envelopes or duplicate rows appeared in that compared prefix. Unit tests separately cover identical and conflicting duplicates.

## Local catalog-outage exercise

The CDC container now uses `unless-stopped`, which also restarts clean process exits while respecting an explicit operator stop. This follows [Docker's restart-policy semantics](https://docs.docker.com/engine/containers/start-containers-automatically/). Existing CPU, memory and log caps remain in force. It does not impose a maximum retry count or establish the corresponding CapRover/Swarm policy; production supervision and alerting still need separate configuration.

```bash
node service/tests/lake-recovery.mjs
```

This operator-only local test checks exact project labels, briefly stops the demo's catalog/object-store container, waits up to 90 seconds to observe a CDC restart, and restores the catalog in a finally block. It then compares the live source and lake. There must be activity to exercise a failed sink commit. It never exposes a Docker socket through the public service.

The first run observed an automatic CDC restart, but its first ClickHouse query timed out after catalog restoration. A separate comparison subsequently matched all 7,432 captured batches. The verifier now permits at most two retries specifically for its process-level query timeout, retaining the original source cutoff and two-minute catch-up window; conflicting data and other query errors still fail immediately. A query may finish after the catch-up deadline by up to its own 20-second process timeout. This is not a reason to increase the data limits or treat partial results as success.

The repeated outage exercise passed: CDC's restart counter advanced from 1 to 2, and all 7,517 captured live batches matched after catch-up, with zero query-timeout retries. The local APIs stayed healthy. This establishes that tested outage path, not lost-slot recovery, a prolonged restart loop, host failure or production resource safety.

The upstream release image index referenced a missing manifest. The working upstream build is pinned to its exact digest in Compose. Its runtime reports Iceberg 1.11.0; provenance and release suitability still need review before deployment.

The separate [CDC resnapshot experiment](CDC-RECOVERY.md) passed stricter offset validation and operator-controlled recovery on the paused budget stack: a deliberately missed transfer returned, all 1,480 live and 12 assessment envelopes matched, and ordinary startup resumed from the new offsets. Identical snapshot redeliveries were deduplicated during comparison. This is the tested overlay, not a changed default or a completed checkpoint/WAL-limit drill. Do not infer recovery from a connected slot alone.

## Read-only retention inventory

With Node 24 or newer and local Docker access:

```bash
node --test service/tests/lake-metadata.test.mjs
node service/tests/lake-inventory.mjs ledger-lab
```

The inventory permits only the two local project names, checks container ownership, and reads at most ten table descriptions with a 4 MiB response limit each. It reports retained snapshot counts, metadata-log counts and the current snapshot's physical row/file summary. It does not expire snapshots or delete objects. Large snapshot IDs retain their exact JSON spelling; tests cover adjacent 64-bit IDs that ordinary JavaScript numbers cannot distinguish.

At 21:50 on 2026-09-04 (UTC−03), the offsets table retained 167 snapshots for one current row. The journal table retained 174 snapshots and 174 current data files, totaling 1,540,211 bytes for 13,508 physical rows. These rows include other local test runs and are not a deduplicated count of demo transactions. A subsequent filesystem sample showed 96,260 KiB under `/data`; current data-file bytes do not include all historical files, metadata or storage-engine overhead. The source database was about 45.5 MB and retained-slot WAL about 2.1 MB in that sample. These are observations during a running workload, not an atomic cross-system snapshot or a growth forecast.

The [upstream maintenance documentation](https://github.com/seaweedfs/seaweedfs/wiki/Iceberg-Table-Maintenance) describes a worker and admin scheduler for compaction, snapshot expiry and orphan removal. The pinned 4.45 image exposes that worker, but it is not configured or tested here. Its [versioned defaults](https://github.com/seaweedfs/seaweedfs/blob/4.45/weed/worker/tasks/iceberg/config.go) retain snapshots for seven days and keep at least five. A metadata-log limit alone does not solve retained snapshot/data growth. Maintenance must first be exercised on isolated tables, including read/restart and current-snapshot preservation, before enabling deletion on the running lake.

## Storage memory observation

The main local SeaweedFS container repeatedly restarted under its 384 MiB hard cap. At 22:26 on 2026-09-04 (UTC−03), Docker recorded an OOM event and exit 137; the kernel identified the `weed` process in that container's memory cgroup. The latest running container's `OOMKilled=false` field alone would have missed that history. CDC recovered from its stored offset, and all 9,562 envelopes at a captured source cutoff subsequently matched.

The main profile now sets `GOMEMLIMIT=192MiB`, leaving space below the unchanged 384 MiB hard cap. After recreation, another complete comparison matched 9,806 envelopes with no duplicates or query-timeout retries. Initial observation covered roughly six minutes with no new restart. This is not a sustained stability result: generation is also subject to host-pressure admission, so elapsed time is not a fixed-volume load test.

The [Go runtime memory limit](https://go.dev/doc/gc-guide#Memory_limit) is soft and does not account for every mapping or allocation outside the runtime. It does not replace the container cap, repair unbounded live state, or establish that retained metadata can grow safely. Longer observation and maintenance testing remain required. No hard limits were raised and no production services changed.

## Limits still required before deployment

The separate [bounded allocation probe](BOUNDED-PROBE.md) verifies that the full `server` mode can enforce a finite volume-slot allowance and preserve an acknowledged object through exhaustion and restart. It does not change the default lake profile or establish a total filesystem quota.

- SeaweedFS `mini` derives its volume allowance from available disk space. The small volume-file setting is **not** a total disk quota. Do not deploy this default to the shared VPS.
- Limiting old metadata files does not expire Iceberg snapshots or reclaim their data files. Snapshot retention, compaction, and bounded cleanup are not implemented here.
- PostgreSQL's retained-slot WAL limit is checked at checkpoints, not a hard instantaneous disk quota. Slot invalidation requires an explicit recovery procedure and reconciliation, not silent continuation.
- CPU and memory limits bound individual local containers. They do not establish a safe combined budget on the production-critical host.
- There is no Metabase integration or public arbitrary-query endpoint. ClickHouse is a reporting reader, never the authority for spending money.
