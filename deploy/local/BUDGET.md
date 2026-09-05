# Smaller local budget experiment

This keeps all eight long-running services. It is not a production-approved profile.

```bash
LEDGER_HTTP_PORT=8089 docker compose -p ledger-budget -f compose.yaml -f deploy/local/budget.yaml --profile lake up -d
LEDGER_HTTP_PORT=8089 docker compose -p ledger-budget -f compose.yaml -f deploy/local/budget.yaml --profile lake up -d --no-deps --wait postgres lake api-a api-b proxy clickhouse
node service/tests/budget-smoke.mjs
```

The separate project has its own database, lake, and volumes. It does not replace the interactive dashboard on port 8088. The watcher has no Docker healthcheck, so the explicit wait covers the services that do. The test pauses its generator on completion. It expects the CDC table to exist and waits up to two minutes for all 12 fixture batches before starting the boost.

Runtime memory ceilings total 1,280 MiB: APIs 64 MiB each, watcher 32, proxy 32, PostgreSQL 192, SeaweedFS 192, CDC 448, ClickHouse 256. Each has zero additional swap allowance in the inspected local container configuration. Startup/bootstrap containers are separate transient costs.

The first check queried before the CDC initial snapshot finished and failed. After adding an explicit catch-up condition, the short test committed 619 batches during a 60-second requested-rate boost followed by automatic return to baseline. Repeated fixture reads and reconciliation passed; no container restarted or reported an OOM kill. Sampled per-container memory maxima were approximately CDC 312 MiB, ClickHouse 104 MiB, SeaweedFS 85 MiB, PostgreSQL 61.5 MiB, and 25 MiB combined for the APIs, watcher, and proxy. These are sampled maxima, not simultaneous aggregate peaks.

This is not sustained 20 events/sec evidence, a full-table analytical stress test, maintenance testing, or a 24/48-hour run. The VPS's last read-only check showed 1,631 MiB available memory. These ceilings plus a 512 MiB reserve exceed that headroom. The profile is therefore still an experiment, not deployment approval. Disk quotas, snapshot retention, and the unsafe default volume allowance of SeaweedFS mini mode also remain unresolved.

## Further reduction: 1,152 MiB

Add `-f deploy/local/compact-budget.yaml` after `budget.yaml` in both commands above. This retains all eight services, reduces CDC to 384 MiB and ClickHouse to 192 MiB, and limits ClickHouse to two concurrent queries, one thread per query and 48 MiB query memory. Startup/bootstrap containers remain separate costs. Do not mix Compose project names: this experiment uses `ledger-budget` throughout.

The first attempt also reduced SeaweedFS to 128 MiB. It restarted three times during startup, so that ceiling was rejected and restored to 192 MiB. The following short boost committed 691 batches, with repeated fixture reads and reconciliation passing. All eight containers remained running with zero restarts and no extra swap allowance. The largest aggregate Docker memory sample was 662,303,670 bytes (about 632 MiB), not an exact peak. Individual sampled maxima must not be added and described as simultaneous usage.

After pausing generation, complete source/lake envelopes matched at cutoff 1,479, with no duplicate deliveries. Stopping and starting all eight budget containers preserved that same agreement. This was a container restart with volumes retained, not a cold-host or power-loss test.

The current profile additionally sets SeaweedFS `GOMEMLIMIT=112MiB` within its 192 MiB hard cap. After applying that setting, the 1,479-envelope comparison passed again. Two attempts to repeat the boost were refused by the host-pressure guard; the current soft-limit configuration therefore does not yet have a successful repeat burst. Generation remains paused. The main profile's separate storage OOM investigation is recorded in the [lake notes](lake/README.md#storage-memory-observation).

The later read-only VPS sample showed 1,604 MiB available. Even these lower ceilings plus the 512 MiB reserve total 1,664 MiB, before maintenance or BI costs. This is still not permission to deploy to that host or reduce its existing workloads.
