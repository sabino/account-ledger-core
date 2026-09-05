# Separate Lakekeeper catalog probe

This is a local compatibility probe, not a replacement for the working CDC profile or a deployment configuration. It uses a separate Docker project and volumes. No service publishes a host port. Authentication is disabled for this disposable catalog; the credentials and encryption key are local test values.

```bash
docker compose -p ledger-catalog-probe -f deploy/local/lake/bounded-probe.yaml -f deploy/local/lake/lakekeeper-probe.yaml up -d --wait catalog query
node service/tests/lakekeeper-smoke.mjs
docker exec -i ledger-catalog-probe-query-1 clickhouse-client --user ledger_owner --password local-analytics-only --multiquery < deploy/local/lake/lakekeeper-query.sql
docker compose -p ledger-catalog-probe -f deploy/local/lake/bounded-probe.yaml -f deploy/local/lake/lakekeeper-probe.yaml restart catalog
node service/tests/lakekeeper-smoke.mjs
```

The Node probe checks the exact project label before connecting. It bootstraps Lakekeeper 0.13.3, validates a dedicated regular S3 bucket, and creates an Iceberg namespace and empty format-v2 table. The query check discovers that table through ClickHouse's REST catalog database and returns zero rows.

On 2026-09-04, repeating the probe after a catalog restart preserved warehouse ID `fab4f386-a8bc-11f1-95b9-7fb3f604bdc3`, table UUID `01a06edf-01dd-7360-97ca-98c4103e815b`, and its metadata location. Initial retry code looked for the wrong warehouse-list field; that harness bug was corrected to use `name`. The repeated probe and ClickHouse check then passed.

This proves metadata persistence and basic catalog/query interoperability, not data-row ingestion, CDC checkpoint recovery, schema evolution, maintenance, or snapshot expiry. Those tests are still needed before choosing Lakekeeper for the full pipeline. The catalog uses PostgreSQL for metadata, not for its Parquet objects; SeaweedFS remains the object store in this probe.

The four long-running containers have combined memory ceilings of 896 MiB: catalog 256, catalog PostgreSQL 192, object storage 192, and ClickHouse 256. The migration container is an additional transient cost. Samples after metadata queries were about 39, 68, 83, and 147 MiB respectively, not measured peaks. Adding a catalog is not a demonstrated memory saving over the integrated SeaweedFS catalog.

The existing bounded-allocation limits apply to the separate object store, but they are not a filesystem quota. The catalog PostgreSQL role is a disposable development superuser. Production authentication, least-privilege identities, backups, retention and the shared-host resource gate remain unresolved. No VPS service was changed for this probe.
