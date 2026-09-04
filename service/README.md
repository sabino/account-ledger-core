# Ledger Lab: Go service experiment

This is follow-on work, not the submitted Python assessment. It is incomplete and not deployed yet. Start with [the plan](../docs/go-service-plan.md) for the intended full system and [decision coverage](../docs/go-service-decision-coverage.md) for the compatibility work still required.

## Run locally

From the repository root, with Docker Compose and working Docker daemon access:

```bash
docker compose up --build -d --wait
```

Open **http://localhost:8088**. There are two identical Go instances, a dedicated PostgreSQL database, and a local reverse proxy. Forty fictional accounts receive explicit, balanced funding entries. One shared generator sends transfers at a low rate. Changing the slider affects everyone, not just one browser.

The local passwords in `compose.yaml` and `deploy/local/init.sql` are disposable development credentials. Do not use this configuration as a public deployment. PostgreSQL has no published host port. The web port binds to loopback.

```bash
docker compose --profile test run --rm test-runner
docker compose stop api-a
docker compose start api-a
docker compose down
```

The test profile uses isolated run IDs in the local database and the restricted application role. It adds test records; it does not erase existing runs. Ordinary `down` preserves the named database volume. No automatic destructive reset is provided.

## What works in this slice

- Exact AED/BHD minor-unit arithmetic, checked overflow, half-even rounding, and deterministic allocation.
- Durable funding, same-currency transfers, holds, and one final partial capture.
- Matching retries return the stored outcome. A changed payload with the same key conflicts.
- Sorted account locks and a short per-run journal-order lock.
- Immutable journal rows, balanced batch checks, and matching complete batch envelopes.
- Account picker, statements, shared rate controls, actual replica heartbeats, and reconciliation.
- A same-database outbox/inbox adapter with a bounded delivery pause.
- A separate host watcher with a restricted database role. Missing or stale telemetry blocks new simulation commands, rate increases, and chaos; stopping generation remains available.
- The isolated six-day fixture, including historical fees, linked principal reversal, installment allocation, daily interest, and final capitalization. A knowledge-cutoff slider shows how later records change historical projections.

Continuous virtual-day transitions, external reconciliation, a network delivery sink, reporting integration, Metabase, backup recovery, and deployment gates are still being worked on. Fixture tests are not evidence for these missing features or general equivalence with every Python input.

The Go fixture retains the supplied numbers, not the Python journal positions. Each balanced batch includes its counterpart postings. Prior-day maintenance and the triggering event are separate batches inside one database transaction, so readers cannot observe the intermediate maintenance batch before that transaction commits.

## Scenario mix and calculation evidence

The live generator now uses a reproducible twelve-step recipe, alternating AED and BHD between groups: a fractional transfer, insufficient funds, invalid precision, a hold, final partial capture, duplicate capture, unknown authorization, currency mismatch, a three-part transfer split, two illustrative tax rounding ties, and an exact retry of the first command. Outcomes depend on actual account state; the tests establish the expected outcomes from a known funded setup. The retry advances the generator cursor but does not append another monetary batch.

`split_transfer` allocates a total across postings on the same value date. BHD 10.000 becomes 3.334 + 3.333 + 3.333. This is not a dated repayment schedule. `purchase` interprets the requested amount as net, applies an explicitly synthetic 1/20 tax rate with half-even rounding per purchase, and debits the gross amount while crediting the merchant's deposit liability and a separate illustrative tax-payable liability. It is not a tax-compliance implementation. The stored calculation includes the rate, rule label, net, tax, gross, and rounding method.

New evaluated outcomes retain the locked account's balance, held amount, available amount, and requested amount alongside the command, policy, processing instance, and resulting legs. Select a journal batch number to inspect that same event's evidence, calculations, and accounting entries. The selected record stays in view while newer events arrive. Invalid inputs can be rejected before that evidence exists, and the inspector says when evidence is missing. Existing immutable batches are not retroactively enriched. HTTP attempt/correlation history and network delivery-attempt tracing remain separate pending audit work.

When changing generator recipes, pause generation and let admitted work drain before updating replicas. Resume only when both run the new version. A fenced, versioned generator lease remains pending; a mixed-version rolling generator is not currently supported safely.

## Code and queries

`internal/domain` owns exact money functions. `internal/store` owns explicit transactions. Named SQL lives under `queries/`; `sqlc` generates `internal/db`. Do not edit generated files. Numbered SQL migrations live under `internal/store/migrations`; Goose records applied versions and takes a PostgreSQL migration lock. The dedicated migration command, not the HTTP server, runs them.

With Go and Node installed, run these from `service/`:

```bash
make generate
make web
make format
make check
make test
```

Go is not required for the Compose workflow. The Dockerfile pins the Go and Node toolchain images and serves compiled TypeScript assets from the Go binary; there is no Node server in production. Formatting uses `gofmt` and Prettier. Queries use generated parameter/result types, not hand-written scan lists in business code.

## Limits, not capacity claims

The local configuration caps each API at 128 MiB / 0.25 CPU, PostgreSQL at 512 MiB / 0.5 CPU, and the proxy at 64 MiB / 0.1 CPU. Test containers have a separate, local-only allowance. Application controls enforce a shared command budget and a 100,000-batch run ceiling. Database size and retained WAL have a fail-closed guard.

These are configuration limits, not a measured 24-hour forecast or permission to deploy the whole stack on a busy host. Go heap shown on the page is not total container memory. Host-threshold calibration, enforcement of the combined deployment budget, and lake retention controls remain deployment prerequisites.

The local watcher samples host memory availability, memory/IO pressure, swap activity, and the free space of the PostgreSQL volume's filesystem every two seconds. It uses read-only metric mounts and no Docker socket. Its safety lease expires after eight seconds; the API role cannot renew it. Defaults reserve 512 MiB available memory and 5 GiB disk, and deny admission above 2% full memory pressure, 5% full IO pressure (10-second averages), or 16 MiB/s swap activity. These defaults need validation against the VPS baseline. Already-admitted work can finish; this is admission control, not a hard CPU or disk quota, nor a watchdog that stops containers.

The local expired-lease check is reproducible:

```bash
docker compose stop watchdog
sleep 10
node service/tests/guard-smoke.mjs
docker compose start watchdog
```

The check leaves generation paused. Resume it from the dashboard after the watcher reports safe. It does not restart or reconfigure any service outside this Compose project.

## Local backup/restore drill

```bash
node service/tests/backup-restore.mjs
```

Run from the repository root with access to the local Docker socket. This briefly stops the two API containers, takes a custom-format PostgreSQL backup in memory, restores it into a newly named disposable database, and compares all rows in 12 financial/delivery tables by SHA-256 fingerprints. It also checks batch balancing and the restored runtime role's lack of journal mutation and host-lease update privileges. Cleanup removes only the new restore database and restarts the API containers.

This is not an online backup consistency test, an off-host backup, point-in-time recovery, or a measured production RTO. It reuses the existing cluster roles and does not restore replication slots or the object store. The drill must not be run while someone needs uninterrupted access to the local dashboard.
