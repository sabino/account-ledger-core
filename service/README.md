# Ledger Lab: Go service experiment

This is follow-on work, not the submitted Python assessment. It is incomplete and not deployed yet. Start with [the plan](../docs/go-service-plan.md) for the intended full system and [decision coverage](../docs/go-service-decision-coverage.md) for the compatibility work still required.

## Run locally

From the repository root, with Docker Compose and working Docker daemon access:

```bash
docker compose up --build -d
docker compose up -d --wait postgres api-a api-b proxy
```

Open **http://localhost:8088**. There are two identical Go instances, a dedicated PostgreSQL database, and a local reverse proxy. Forty fictional accounts receive explicit, balanced funding entries. One shared generator sends transfers at a low rate. Changing the slider affects everyone, not just one browser.

The local passwords in `compose.yaml` and `deploy/local/init.sql` are disposable development credentials. Do not use this configuration as a public deployment. PostgreSQL has no published host port. The web port binds to loopback.

The watcher has its own short database lease, not a Docker healthcheck; the explicit wait above covers database and HTTP readiness. Admission stays closed until the watcher publishes a safe observation.

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
- Leased outbox delivery over signed HTTP, an idempotent receiver, and append-only delivery-attempt records. A bounded pause lets the backlog accumulate and recover.
- A separate host watcher with a restricted database role. Missing or stale telemetry blocks new simulation commands, rate increases, and chaos; stopping generation remains available.
- The isolated six-day fixture, including historical fees, linked principal reversal, installment allocation, daily interest, and final capitalization. A knowledge-cutoff slider shows how later records change historical projections.

Continuous virtual-day transitions, external reconciliation, Metabase, and deployment gates are still being worked on. The optional local lake profile and a small paused-writer backup/restore drill have separate checks; they are not proof of full production reporting or disaster recovery. Fixture tests are not evidence for missing features or general equivalence with every Python input.

## Event analytics and currency views

The dashboard separates recorded decisions from operational state. Its two time-series charts show new journal batches and declined/rejected decisions over 10 minutes, one hour, or 24 hours, in 60 equal buckets. Counts come from one PostgreSQL query snapshot. Empty buckets mean no recorded batch, not proof that the service was healthy. Matching retries do not append another decision; these are not HTTP request, latency, or error-rate metrics. Outcome and processing-instance breakdowns use the same window and currency. Exact bucket counts are expandable below each chart.

Currency attribution uses the recorded command, with a posting-currency fallback for older records. An older decision with neither is excluded from currency-specific analytics rather than guessed. The endpoint permits only AED/BHD (or an all-currency count view), three fixed windows, and a two-second query timeout. It aggregates events once before joining the 60 buckets. The browser refreshes analytics every ten seconds and labels failures as stale; current operational snapshots refresh more frequently.

Each current ledger account is single-currency. A customer-facing multi-currency wallet could group separate AED and BHD accounts, but that grouping is not implemented here. The selector changes account choices, current customer totals, and the journal preview; it never converts or combines currencies. Current balances and operational counters are not limited by the event window. The journal preview filters the latest 60 fetched batches, so it is not a complete filtered event search. The six-day laboratory remains an explicitly separate, two-currency fixture.

The dark layout uses client-side hash routes for Overview, Journal, Accounts, Transfers, System, and Time. It moves persistent panels between workspaces without a full reload, rather than presenting one long scrolling page. The desktop overview keeps controls, charts, accounts, health, journal, and evidence together; smaller layouts use an icon rail or navigation drawer, mobile event cards, and an inspector drawer/bottom sheet. Search covers the currently fetched journal preview, and pausing that display does not pause the shared generator. Motion has a reduced-motion override. There are no crypto panels, invented trends, or third-party branding. All six routes received a Chromium visual pass at desktop, laptop and mobile sizes on 2026-09-04, followed by route geometry checks at four widths. This is separate from compilation and HTTP checks, and does not establish cross-browser or full accessibility coverage.

## CDC source visibility

`GET /api/status` reports `cdc_source` separately from financial readiness. Its state is `absent` when the configured slot is not present, `inactive` when it has no consumer, `streaming` when PostgreSQL reports an active consumer, or `invalidated` when PostgreSQL reports the slot lost/invalid. Absence alone cannot distinguish a disabled optional profile from a missing expected slot. Retained WAL bytes are exact decimal text, or null when the source restart position is unknown. Unknown is not zero.

This is source-side evidence only: an active connection does not prove successful Iceberg commits, a current ClickHouse query, or a reconciled reporting cutoff. The existing retained-WAL resource guard remains separate from business approval. Lost-slot resnapshot/reconciliation and live lake freshness are still open work.

## Notification delivery boundary

The worker commits a 15-second delivery lease before making an HTTP call. Only its lease token can acknowledge that attempt. The receiver checks an HMAC signature and the complete payload against the recorded journal batch before inserting a unique inbox receipt. A lost acknowledgement is safe to retry. Claims, retries, and acknowledgements are append-only audit rows; the operational outbox lease is mutable.

The local reverse proxy denies `/internal/`, and destinations are fixed configuration, not public input. Local credentials are examples only. Delivery uses HTTP inside the local network, not encryption, and the simulated receiver still shares PostgreSQL with the ledger. This tests a network boundary and acknowledgement loss, not an independent downstream database, host failure, or exactly-once network delivery. The integration test simulates losing the acknowledgement after the receiver commits, then verifies one receipt after retry.

The Go fixture retains the supplied numbers, not the Python journal positions. Each balanced batch includes its counterpart postings. Prior-day maintenance and the triggering event are separate batches inside one database transaction, so readers cannot observe the intermediate maintenance batch before that transaction commits.

## Scenario mix and calculation evidence

The live generator now uses a reproducible twelve-step recipe, alternating AED and BHD between groups: a fractional transfer, insufficient funds, invalid precision, a hold, final partial capture, duplicate capture, unknown authorization, currency mismatch, a three-part transfer split, two illustrative tax rounding ties, and an exact retry of the first command. Outcomes depend on actual account state; the tests establish the expected outcomes from a known funded setup. The retry advances the generator cursor but does not append another monetary batch.

`split_transfer` allocates a total across postings on the same value date. BHD 10.000 becomes 3.334 + 3.333 + 3.333. This is not a dated repayment schedule. `purchase` interprets the requested amount as net, applies an explicitly synthetic 1/20 tax rate with half-even rounding per purchase, and debits the gross amount while crediting the merchant's deposit liability and a separate illustrative tax-payable liability. It is not a tax-compliance implementation. The stored calculation includes the rate, rule label, net, tax, gross, and rounding method.

New evaluated outcomes retain the locked account's balance, held amount, available amount, and requested amount alongside the command, policy, processing instance, and resulting legs. Select a journal batch number to inspect that same event's evidence, calculations, and accounting entries. The selected record stays in view while newer events arrive. Invalid inputs can be rejected before that evidence exists, and the inspector says when evidence is missing. Existing immutable batches are not retroactively enriched. HTTP attempt/correlation history and network delivery-attempt tracing remain separate pending audit work.

Each generator ordinal now has a five-second database claim with a monotonically increasing fencing token. Processing locks the run, validates and locks the current claim, then acquires command/account locks. The result and cursor advancement commit together, including the recipe's deliberate idempotent retry. A worker that dies before processing leaves the same ordinal available after expiry; a stale token cannot start financial work. Once the transaction holds the claim row, takeover waits for that transaction to finish. This bounds ownership per command, not per long-lived replica leader.

Run `node service/tests/generator-recovery.mjs` from the repository root with local Docker access to exercise a stopped replica and surviving generator. It validates local project labels, restores the stopped replica, and restores the prior requested rate. Integration tests separately cover expiry, takeover, stale claims, conflict rollback and cursor progress through a stored replay. This is not an arbitrary-instruction crash test.

When changing generator recipes, pause generation and let admitted work drain before updating replicas. Resume only when both run the new version. The token does not negotiate recipe versions; mixed-version rolling recipe changes remain unsupported.

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
