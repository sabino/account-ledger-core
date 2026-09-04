# Smaller local budget experiment

This keeps all eight long-running services. It is not a production-approved profile.

```bash
LEDGER_HTTP_PORT=8089 docker compose -p ledger-budget -f compose.yaml -f deploy/local/budget.yaml --profile lake up -d --wait
node service/tests/budget-smoke.mjs
```

The separate project has its own database, lake, and volumes. It does not replace the interactive dashboard on port 8088. The test pauses its generator on completion. It expects the CDC table to exist and waits up to two minutes for all 12 fixture batches before starting the boost.

Runtime memory ceilings total 1,280 MiB: APIs 64 MiB each, watcher 32, proxy 32, PostgreSQL 192, SeaweedFS 192, CDC 448, ClickHouse 256. Each has zero additional swap allowance in the inspected local container configuration. Startup/bootstrap containers are separate transient costs.

The first check queried before the CDC initial snapshot finished and failed. After adding an explicit catch-up condition, the short test committed 619 batches during a 60-second requested-rate boost followed by automatic return to baseline. Repeated fixture reads and reconciliation passed; no container restarted or reported an OOM kill. Sampled per-container memory maxima were approximately CDC 312 MiB, ClickHouse 104 MiB, SeaweedFS 85 MiB, PostgreSQL 61.5 MiB, and 25 MiB combined for the APIs, watcher, and proxy. These are sampled maxima, not simultaneous aggregate peaks.

This is not sustained 20 events/sec evidence, a full-table analytical stress test, maintenance testing, or a 24/48-hour run. The VPS's last read-only check showed 1,631 MiB available memory. These ceilings plus a 512 MiB reserve exceed that headroom. The profile is therefore still an experiment, not deployment approval. Disk quotas, snapshot retention, and the unsafe default volume allowance of SeaweedFS mini mode also remain unresolved.
