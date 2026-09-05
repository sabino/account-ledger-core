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
- Account picker, bounded recent account activity, shared rate controls, actual replica heartbeats, and reconciliation.
- Leased outbox delivery over signed HTTP, an idempotent receiver, and append-only delivery-attempt records. A bounded pause lets the backlog accumulate and recover.
- A separate host watcher with a restricted database role. Missing or stale telemetry blocks new simulation commands, rate increases, and chaos; stopping generation remains available.
- The isolated six-day fixture, including historical fees, linked principal reversal, installment allocation, daily interest, and final capitalization. A knowledge-cutoff slider shows how later records change historical projections.

Continuous virtual-day transitions, external reconciliation, Metabase, and deployment gates are still being worked on. The optional local lake profile and a small paused-writer backup/restore drill have separate checks; they are not proof of full production reporting or disaster recovery. Fixture tests are not evidence for missing features or general equivalence with every Python input.

The internal calendar boundary records an immutable transition and schedules one durable close job per customer account in the same transaction as advancing the run day. It waits for old-day commands; repeating the same transition is idempotent. Next-day money involving an account with unfinished close work returns an operational error without storing a business rejection. Already-closed accounts can transact while another account remains pending, but another calendar advance waits for all closes.

The internal close executor records the posted balance basis, exact daily interest and persisted policy in an immutable journal batch, completing its job and enqueuing delivery in the same transaction. Ordinary daily accrual does not move money. At every sixth simulation day, the same close transaction credits the sum of that account's six rounded daily amounts against the matching currency's interest-expense account. The final-day basis is calculated before capitalization. The credit has the period-end value day and the worker's current booking day; subsequent days include that credit in their basis. This fixed six-day cadence is a simulation rule, not a banking month or a configurable product calendar.

Period evidence includes all six daily calculations, links to the five earlier immutable close batches, and an immutable per-account period record linked to the final close batch. A zero total still completes the period, without zero-value postings. Account locks, including the expense counterpart, are acquired in sorted order. The next-day spending barrier is released only when accrual, capitalization, journal, outbox and period recording all commit. Concurrent or later retries return the original response, including its original booking day and instance.

Negative live balances block the affected close with an explicit missing-product-policy reason; this does not invent an AED/BHD overdraft fee or refund policy. The fixture's fee and terminal-finalization behavior is unchanged. The `system:` command-ID prefix is reserved for internal operations and cannot be submitted through `Process`. Closed-period corrections and product-calendar configuration remain unfinished.

The worker has an opt-in `CALENDAR_ENABLED=true` mode, disabled by default in the binary and enabled on both APIs in the main local Compose configuration. Each replica attempts at most one calendar operation per two-second maintenance tick. It drains pending account closes first; otherwise it advances a running simulation no sooner than five minutes after the last committed transition (or run creation for the first one). There is no catch-up loop after downtime. Both replicas must use the same flag and version. The status endpoint reports that instance's flag, current day, pending/blocked closes, nominal next transition time and simulation cadence. The nominal time is not a promise: pause, unfinished closes or safety admission can defer it.

Scheduled transitions and closes use the same shared 20-operation-per-second admission budget, fresh host lease, database/WAL guard and run ceiling as public traffic. Admission is inside the calendar transaction, after the lifecycle lock and before operation/account locks. Pausing the generator stops new transitions but permits existing close work to drain while safety allows it. A safety pause or expired lease stops that drain too. Blocked jobs are not automatically retried; they require an explicit policy/operator resolution. Capacity exhaustion and the bounded calendar horizon still require the planned run-rotation workflow.

The health panel displays calendar day and close progress. The transfer form fetches fresh calendar state before sending and fails without sending if that evidence is invalid or unavailable. A boundary race can still produce an explicit server rejection; it does not automatically resubmit money. The compact budget/recovery overlay keeps scheduling disabled for its fixed-day recovery drills. The scheduler's integration tests use a newly created disposable database so expired-lease experiments cannot replace the real demo watcher evidence.

Generated commands now receive the current day only after the transaction has acquired the run lifecycle and generator fences. When the recipe deliberately retries an earlier command, its original committed dates are retained and every other payload field must still match. This permits an exact retry across a day boundary without a duplicate credit or a date-induced identity conflict. New money still waits for the relevant account closes; ordinary public commands continue to validate their explicit dates.

## Event analytics and currency views

The dashboard separates recorded decisions from operational state. Its two time-series charts show new journal batches and declined/rejected decisions over 10 minutes, one hour, or 24 hours, in 60 equal buckets. Counts come from one PostgreSQL query snapshot. Empty buckets mean no recorded batch, not proof that the service was healthy. Matching retries do not append another decision; these are not HTTP request, latency, or error-rate metrics. Outcome and processing-instance breakdowns use the same window and currency. Exact bucket counts are expandable below each chart.

Currency attribution uses the recorded command, with a posting-currency fallback for older records. An older decision with neither is excluded from currency-specific analytics rather than guessed. The endpoint permits only AED/BHD (or an all-currency count view), three fixed windows, and a two-second query timeout. It aggregates events once before joining the 60 buckets. The browser refreshes analytics every ten seconds and labels failures as stale; current operational snapshots refresh more frequently.

Each current ledger account is single-currency. A customer-facing multi-currency wallet could group separate AED and BHD accounts, but that grouping is not implemented here. The selector changes account choices, current customer totals, and the journal preview; it never converts or combines currencies. Current balances and operational counters are not limited by the event window. The journal preview filters the latest 60 fetched batches, so it is not a complete filtered event search. The six-day laboratory remains an explicitly separate, two-currency fixture.

The layout uses client-side hash routes for Overview, Journal, Accounts, Transfers, System, and Time. It moves persistent panels between workspaces without a full reload, rather than presenting one long scrolling page. The desktop overview keeps controls, charts, accounts, health, journal, and evidence together; smaller layouts use an icon rail or navigation drawer, mobile event cards, and an inspector drawer/bottom sheet. Search covers the currently fetched journal preview, and pausing that display does not pause the shared generator. Motion has a reduced-motion override. There are no crypto panels, invented trends, or third-party branding.

Light, dark and system appearance settings are available in the header. Theme and sidebar preferences survive reloads when browser storage is available; denied storage does not stop the application. Space Grotesk and IBM Plex Mono are served locally with their OFL licenses in the embedded assets, without runtime font requests to Google. The Accounts route groups actual account classes and loads an explicitly dated snapshot of recent batches when an account expands. Its Full posted statement action opens separate, fixed-cutoff history with pagination and CSV export. The System route separates the conceptual request/commit/delivery path from observed health, source-side CDC evidence and recovery controls.

On 2026-09-04, all six routes were visually reviewed in Chromium at desktop and mobile sizes. Geometry checks covered all six routes in both themes at widths 1920, 1100, 834 and 390: no document-level horizontal overflow or overlapping panels was found. The time-laboratory table intentionally scrolls within its own region on small screens. Checks also covered persistent theme/sidebar choices, system-color changes, reduced motion, account expansion, mobile modal focus restoration and the transfer inspector at a 1450px viewport. Five pure preference tests run in CI. Browser review caught percentage bars blocked by CSP; setting their measured widths through DOM properties fixed the display without relaxing the policy. This evidence is not a cross-browser or full accessibility audit.

## Complete posted statements API

`GET /api/statements?account=ACC-001&limit=50` captures the current committed journal cutoff and returns monetary posting lines in `(sequence, leg)` order. A following page supplies that same `cutoff` plus `after_sequence` and `after_leg` from `next`. A null `next` means the statement is complete. Limits are 1–100 lines per request; invalid parameters return 400 and an unknown account returns 404. Explicit `cutoff=0` returns an empty prefix, not the latest state.

Each page contains exact minor-unit strings, accounting debits/credits, normal-side balance changes, running balances, booking/value days and recorded timestamps. The response also gives full-prefix debit/credit totals and closing balance, plus the page's opening/closing balances. Liability balances increase on credits; asset balances increase on debits. Currencies are never combined. This is a posted statement, not available funds after holds, a value-date-filtered projection, or a complete history of rejected HTTP attempts.

Read-only repeatable-read transactions keep each page internally consistent. The fixed cutoff and immutable postings keep later commits out of subsequent pages. Cursor pagination includes the posting leg so a multi-part credit cannot be skipped at a page boundary. Prefix totals still scan the account's qualifying postings; the endpoint has a two-second deadline, not an unlimited historical-query budget.

Run `node service/tests/statements-smoke.mjs` after rebuilding the local APIs. It traverses one AED and one BHD account, checks every running balance and page boundary, and tests invalid queries without submitting commands or changing generation. Requests are paced below the local proxy's read-rate limit.

In Accounts, expand an account and choose Full posted statement. Next/Previous preserve the captured cutoff; Refresh snapshot deliberately captures a newer one. The dialog scrolls internally and uses stacked posting rows on mobile. CSV export fetches all pages at the same cutoff, validates identities, ordering, accounting sides, running balances, totals and completeness, then creates the download. Untrusted text fields are protected against spreadsheet formulas. Browser export is capped at 20,000 posting lines and paced at two requests per second; cancellation, failed requests or validation errors produce no partial file. Larger accounts remain browsable, but a server-streamed export is not implemented. Spreadsheet applications may still apply their own number formatting when opening exact CSV values.

## CDC source visibility

`GET /api/status` reports `cdc_source` separately from financial readiness. Its state is `absent` when the configured slot is not present, `inactive` when it has no consumer, `streaming` when PostgreSQL reports an active consumer, or `invalidated` when PostgreSQL reports the slot lost/invalid. Absence alone cannot distinguish a disabled optional profile from a missing expected slot. Retained WAL bytes are exact decimal text, or null when the source restart position is unknown. Unknown is not zero.

This is source-side evidence only: an active connection does not prove successful Iceberg commits, a current ClickHouse query, or a reconciled reporting cutoff. The existing retained-WAL resource guard remains separate from business approval. The isolated budget-stack [lost-slot drill](../deploy/local/lake/CDC-RECOVERY.md) passed explicit resnapshot and whole-envelope reconciliation with stricter offset validation. That validation is now enabled and restart-tested in the default local profile. Checkpoint-driven WAL invalidation and live lake freshness remain open work.

With the optional local lake profile running, `node service/tests/cdc-source-smoke.mjs` checks exact project/container labels, stops only the local CDC consumer, observes `inactive` through the status API, verifies HTTP readiness and restarts the consumer in a finally block. It then waits for `streaming`. On 2026-09-04 that transition passed, with 909,928 retained WAL bytes observed while stopped. This test does not invalidate a slot, reconcile the lake or submit a financial command. It requires Docker access and is not a public fault-control endpoint.

## Notification delivery boundary

The worker commits a 15-second delivery lease before making an HTTP call. Only its lease token can acknowledge that attempt. The receiver checks an HMAC signature and the complete payload against the recorded journal batch before inserting a unique inbox receipt. A lost acknowledgement is safe to retry. Claims, retries, and acknowledgements are append-only audit rows; the operational outbox lease is mutable.

The local reverse proxy denies `/internal/`, and destinations are fixed configuration, not public input. Local credentials are examples only. Delivery uses HTTP inside the local network, not encryption, and the simulated receiver still shares PostgreSQL with the ledger. This tests a network boundary and acknowledgement loss, not an independent downstream database, host failure, or exactly-once network delivery. The integration test simulates losing the acknowledgement after the receiver commits, then verifies one receipt after retry.

The Go fixture retains the supplied numbers, not the Python journal positions. Each balanced batch includes its counterpart postings. Prior-day maintenance and the triggering event are separate batches inside one database transaction, so readers cannot observe the intermediate maintenance batch before that transaction commits.

## Scenario mix and calculation evidence

The live generator now uses a reproducible twelve-step recipe, alternating AED and BHD between groups: a fractional transfer, insufficient funds, invalid precision, a hold, final partial capture, duplicate capture, unknown authorization, currency mismatch, a three-part transfer split, two illustrative tax rounding ties, and an exact retry of the first command. Outcomes depend on actual account state; the tests establish the expected outcomes from a known funded setup. The retry advances the generator cursor but does not append another monetary batch.

`split_transfer` allocates a total across postings on the same value date. BHD 10.000 becomes 3.334 + 3.333 + 3.333. This is not a dated repayment schedule. `purchase` interprets the requested amount as net, applies an explicitly synthetic 1/20 tax rate with half-even rounding per purchase, and debits the gross amount while crediting the merchant's deposit liability and a separate illustrative tax-payable liability. It is not a tax-compliance implementation. The stored calculation includes the rate, rule label, net, tax, gross, and rounding method.

New evaluated outcomes retain the locked account's balance, held amount, available amount, and requested amount alongside the command, policy, processing instance, and resulting legs. Select a journal batch number to inspect that same event's evidence, calculations, and accounting entries. The selected record stays in view while newer events arrive. Invalid inputs can be rejected before that evidence exists, and the inspector says when evidence is missing. Existing immutable batches are not retroactively enriched. HTTP request/correlation history remains pending. Network delivery already records append-only claim, retry and acknowledgement events, as described above.

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
docker compose --profile test run --rm --no-deps guard-runner
docker compose start watchdog
```

The check leaves generation paused. Resume it from the dashboard after the watcher reports safe. It does not restart or reconfigure any service outside this Compose project.

## Local backup/restore drill

```bash
node service/tests/backup-restore.mjs
```

Run from the repository root with access to the local Docker socket. This briefly stops the two API containers, takes a custom-format PostgreSQL backup in memory, restores it into a newly named disposable database, and compares all rows in 15 financial/delivery/calendar tables by SHA-256 fingerprints. It also checks batch balancing and the restored runtime role's lack of journal mutation and host-lease update privileges. Cleanup removes only the new restore database and restarts the API containers.

This is not an online backup consistency test, an off-host backup, point-in-time recovery, or a measured production RTO. It reuses the existing cluster roles and does not restore replication slots or the object store. The drill must not be run while someone needs uninterrupted access to the local dashboard.
