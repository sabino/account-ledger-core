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

The full six-day fee/reversal/finalization port, virtual-day transitions, external reconciliation, a network delivery sink, CDC, Iceberg, ClickHouse, Metabase, host watchdog, backup recovery, and deployment gates are still being worked on. A green first-slice test is not evidence for these missing features.

## Code and queries

`internal/domain` owns exact money functions. `internal/store` owns explicit transactions. Named SQL lives under `queries/`; `sqlc` generates `internal/db`. Do not edit generated files. `internal/store/schema.sql` is the initial schema; versioned migration handling is still needed before public deployment.

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

These are configuration limits, not a measured 24-hour forecast or permission to deploy the whole stack on a busy host. Go heap shown on the page is not total container memory. The host watchdog and lake retention controls are deployment prerequisites.
