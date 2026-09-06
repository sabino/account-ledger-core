# Ledger Lab — browser edition

Status: scoped, not implemented or deployed. This document starts the stacked `feat/browser-ledger-lab` PR, based on `feat/go-ledger-service`. Nothing here replaces the Go service, its tests, the Python assessment, the existing documentation or the submitted PDF.

## The intended experience

A publicly accessible static site whose simulation runs entirely on the visitor's device. There is no application API, PostgreSQL, CDC connector, warehouse or remote monitoring service behind this edition. The actual browser execution and storage are real; replicas, network failures, queues and infrastructure scaling are modeled. The interface must keep that distinction visible.

An explanatory landing page opens a shared simulation shell. Separate routed modules present different responsibilities, without embedding unrelated applications in iframes or duplicating the ledger state:

| Workspace | Responsibility |
| --- | --- |
| Start | Explain the experiment, money origin, limits and a short guided scenario |
| Bank app | Choose a synthetic customer, inspect currency accounts, move money, authorize/capture and read statements |
| Backoffice | Inspect commands, journal batches, balanced legs, rejected decisions, corrections and reconciliation |
| Control plane | Set a bounded generation rate, change modeled replicas/capacity, inject and recover from named faults |
| Monitoring | Grafana-like time-series panels for throughput, outcomes, latency, backlog and recovery, with metric definitions |
| Data infrastructure | Follow the journal-to-outbox/reporting path, inspect deduplication, checkpoints, lag and derived views |

These are simulated roles, not authentication or access-control boundaries. Every visitor owns an independent sandbox. No real customer data, credentials or money should be entered.

## Reuse rather than replace

Keep the Go implementation as the executable reference and preserve the supplied v2's visual language. The browser edition belongs in its own directory with its own entry point, tests and static build. Shared fixture expectations should detect differences in exact arithmetic, currency precision, partial capture, retries, historical projections and rounding. A feature not yet ported must be listed as unavailable, not represented by an inert control or a made-up success.

The landing page should teach through the money-to-evidence path. The working modules should retain compact, readable layouts, light/dark themes, exact tabular amounts, mobile journal cards and clear inspection panels. Monitoring should have denser operational charts than the customer-facing Bank app. Charts should be derived from recorded simulation activity, never randomly jittered to look live.

## Browser execution and persistence

- Use IndexedDB for the journal, accounts, command identities, holds, delivery state, reporting projections and bounded telemetry. Use localStorage only for small preferences. IndexedDB transactions must commit a command result, postings, balance changes and outbox work together, or commit none of them.
- Use integer minor units and BigInt arithmetic. Serialize amounts as decimal strings in exports. A customer's multi-currency view groups separate AED/BHD ledger accounts; it does not combine their balances or invent FX.
- Run bounded scheduling off the main UI thread where practical. A simulated replica is not a separate host. More modeled replicas must not be described as added real compute capacity.
- Coordinate multiple tabs with one scheduler owner and durable command identities. Do not depend on tab-local memory for deduplication or assume a timing delay establishes ownership. Test ownership transfer and concurrent requests against IndexedDB's actual transaction behavior.
- Ask for persistent storage through the browser's supported API and show whether it was granted. Show quota estimates as origin-wide browser estimates, not exact application size or guaranteed free disk. Catch quota failures without falling back to an in-memory success.
- Start with one generated command per second, a proposed maximum of 20, and a finite journal/run ceiling. Bound chart samples, page journal reads and stop safely at configured storage/history limits. Validate the caps on a slower browser before treating them as defaults.
- Provide versioned export and validated import into a new sandbox. Never overwrite the current sandbox implicitly. Explain that clearing site data can remove the simulation and that persistent storage is not a backup.
- Background tabs can be throttled and closed browsers stop execution. Resume must not silently generate an unlimited catch-up workload or pretend the simulation ran while closed.

Browser storage capacity and persistence vary by browser and origin. IndexedDB is appropriate for larger transactional local datasets; it does not grant unlimited storage or synchronize different domains. See [IndexedDB](https://developer.mozilla.org/en-US/docs/Web/API/IndexedDB_API) and [storage quotas and eviction](https://developer.mozilla.org/en-US/docs/Web/API/Storage_API/Storage_quotas_and_eviction_criteria).

## Failure experiments and honest metrics

Named experiments should cover a replica stopping before a commit, acknowledgement loss after a commit, duplicate delivery, reporting-consumer pause, constrained modeled capacity and recovery. Failure points need deterministic seeds or explicit scripts so the same experiment is reproducible. Each experiment must state the expected money, delivery and reporting behavior, then check what actually happened.

Reconciliation should independently recompute per-currency batch balance, account totals and active holds from persisted facts. Reporting comparison should use a complete named source prefix; neither equal counts nor an active modeled connector proves completeness. Checkpoint progress and duplicate effects must be separately visible.

Monitoring must distinguish:

| Measurement | Source |
| --- | --- |
| Committed/declined/rejected commands, retries, queue depth | Actual records in the local simulation |
| Browser processing duration and storage estimate | Real browser observations, labeled with scope |
| Replica capacity, network latency and virtual service failures | Explicit simulation model inputs and outcomes |
| PostgreSQL WAL, Docker CPU/RAM, ClickHouse utilization | Not present; show only explicitly labeled modeled estimates if useful |

A modeled reporting queue is not actual PostgreSQL CDC, Iceberg or ClickHouse. A browser transaction is not proof of distributed consensus, database high availability or production ledger correctness. The original Go edition remains available for demonstrating actual service/database behavior.

## Static hosting without disturbing the existing site

Read-only inspection on 6 September confirmed that `sabino.pro` is the custom domain of `sabino/sabino.github.io`, published by GitHub Pages from `master` at the repository root. The intended integration is an additive `ledger/` static directory, with relative asset paths and client-side workspace routes. Preserve the existing homepage, CNAME and unrelated files. No new backend or VPS container is needed for this approach.

Prepare and verify the browser edition in this repository first. Publishing to the portfolio repository is a separate, narrowly scoped change containing only the verified static artifact and necessary deployment documentation. Do not switch the whole portfolio's build system or repoint its apex DNS merely to host this subpage.

Prefer `https://sabino.pro/ledger/` as the canonical storage origin. `ledger.sabino.pro` may redirect there once its current DNS/routing is inspected. If both origins independently serve the application, their browser databases are separate: changes will not synchronize automatically. A subdirectory also shares an origin with the portfolio, so database names must be specific to this application; it is not a security boundary against other same-origin scripts.

## Delivery slices and acceptance

1. Implement the local accounting core and IndexedDB transaction boundary. Test funding, transfers, insufficient funds, exact retries, identity conflicts, holds/capture, rounding, balanced batches and reload persistence.
2. Connect the shared shell, landing page, Bank and Backoffice modules to that real local core. Preserve responsive behavior and usable loading/error states.
3. Add bounded scheduling, modeled replicas, delivery/reporting consumers and deterministic chaos controls. Demonstrate recovery and no duplicate financial effect.
4. Add the monitoring and data workspaces, quota/persistence display, export/import and clear scope explanations. Verify multi-tab behavior, cancellation and storage failure.
5. Build static assets and test them under `/ledger/`, including direct links, desktop/mobile layouts and a full reload. Open the portfolio change only after these checks pass; verify the published URL without changing the Go deployment.

The initial stacked PR records this plan only. Completion means a working and verified browser edition, not just the existence of this document or a dashboard screenshot.
