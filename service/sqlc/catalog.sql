-- sqlc-only description of a PostgreSQL system view. Never a migration.
CREATE TABLE pg_replication_slots (
  database text,
  restart_lsn pg_lsn
);
