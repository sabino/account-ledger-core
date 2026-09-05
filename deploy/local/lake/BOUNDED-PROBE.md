# Bounded lake allocation probe

This is an isolated local experiment, not a replacement for the running lake or a VPS deployment configuration.

```bash
docker compose -f deploy/local/lake/bounded-probe.yaml up -d --wait
node service/tests/lake-capacity-probe.mjs
# Use the probe ID printed by the preceding command:
node service/tests/lake-capacity-probe.mjs --restart-existing PROBE_ID
```

The script requires host access to the local Docker bridge address. It refuses a container outside `ledger-lake-probe`. It does not delete objects or reset the volume. Re-running the fill against an already-full allocation is expected to fail its fresh-space check. To stop this experiment without deleting evidence, use `docker compose -f deploy/local/lake/bounded-probe.yaml stop`.

## What changed

The pinned SeaweedFS `server` command exposes `-volume.max`; `mini` does not. The probe starts master, volume server, filer, S3, and the REST catalog in one process, with eight volume slots and a 32 MiB volume-size target. Filer metadata is explicitly stored under the named `/data` volume. Upload concurrency, upload buffers, maintenance rate, container CPU, memory, PID count, and logs are bounded separately. An operator-only setup container creates the table bucket; it is not a long-running service.

Catalog authentication and configuration retrieval succeeded. An initial attempt to upload arbitrary test paths inside the table bucket returned 403. That was an access restriction, not capacity exhaustion. The fill therefore uses a separate regular S3 bucket on the same isolated volume server, without changing table files.

## Observed on 2026-09-04

Eleven 3 MiB objects were acknowledged: 34,603,008 bytes. The next upload returned HTTP 500. The server log explicitly reported that the volume reached capacity and there were no writable or free volumes left. A previously acknowledged object remained readable and its SHA-256 matched. After restarting only this probe container, the same object's checksum still matched.

The data directory occupied about 33.3 MiB. A single memory sample was 106.3 MiB under a 192 MiB container ceiling; that is not a measured peak. Master metadata allocation had already consumed seven of the eight volume slots, leaving only one for the regular test bucket. This configuration therefore does not provide 256 MiB of usable object capacity. Growth settings need tuning and another test before selecting a deployment size.

## What this does not prove

- A volume count/size target is not a filesystem quota. Upload overshoot, indexes, filer metadata, logs, and maintenance space are additional.
- The failure exposes a generic HTTP 500, not a helpful capacity-specific S3 response. Guards must report pressure before the writer repeatedly reaches this boundary.
- This does not exercise CDC during exhaustion, Iceberg snapshot expiry, catalog recovery after a failed commit, or an independent backup restore.
- A restart verifies persistence across container restart, not host-loss recovery.
- No production service was changed, and the existing local lake was not migrated to this configuration.

The [upstream maintenance documentation](https://github.com/seaweedfs/seaweedfs/wiki/Iceberg-Table-Maintenance) distinguishes snapshot expiry from orphan cleanup. Neither is established by limiting the number of old metadata files in the CDC configuration. Retention remains a separate gate.
