-- sqlc-only description of a PostgreSQL system view. Never a migration.
CREATE TABLE pg_replication_slots (
  slot_name text,
  database text,
  restart_lsn pg_lsn,
  active boolean,
  wal_status text,
  invalidation_reason text
);
