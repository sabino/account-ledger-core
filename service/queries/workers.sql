-- name: Admit :execrows
UPDATE controls SET
  budget_used = CASE WHEN budget_second = floor(extract(epoch FROM clock_timestamp()))::bigint
    THEN budget_used + 1 ELSE 1 END,
  budget_second = floor(extract(epoch FROM clock_timestamp()))::bigint
WHERE run_id = 'demo' AND pause_reason = '' AND guard_until > now()
  AND EXISTS (SELECT FROM host_guard WHERE id AND safe_until > now())
  AND (budget_second <> floor(extract(epoch FROM clock_timestamp()))::bigint OR budget_used < 20)
  AND (SELECT position FROM journal_clock WHERE run_id = 'demo') < 100000;

-- name: DatabaseFootprint :one
SELECT pg_database_size(current_database())::bigint AS size,
  COALESCE((SELECT max(pg_wal_lsn_diff(pg_current_wal_lsn(), restart_lsn))
    FROM pg_replication_slots WHERE database = current_database()), 0)::bigint AS retained;

-- name: RefreshGuard :exec
UPDATE controls SET guard_until = CASE WHEN sqlc.arg(reason)::text = ''
  THEN now() + interval '10 seconds' ELSE now() END,
  guard_reason = sqlc.arg(reason) WHERE run_id = 'demo';

-- name: ClaimGeneratedCommand :one
UPDATE controls SET generator_token = generator_token + 1,
  generator_until = clock_timestamp() + interval '5 seconds'
WHERE run_id = $1 AND eps > 0 AND next_at <= clock_timestamp()
  AND pause_reason = '' AND guard_until > clock_timestamp()
  AND (generator_until IS NULL OR generator_until <= clock_timestamp())
RETURNING ordinal, generator_token;

-- name: LockGeneratedCommand :one
SELECT ordinal FROM controls
WHERE run_id = $1 AND ordinal = $2 AND generator_token = $3
  AND generator_until > clock_timestamp() AND eps > 0
  AND pause_reason = '' AND guard_until > clock_timestamp()
FOR UPDATE;

-- name: AcknowledgeGeneratedCommand :execrows
UPDATE controls SET ordinal = ordinal + 1,
  generator_until = NULL,
  eps = CASE WHEN boost_until < clock_timestamp() THEN 1 ELSE eps END,
  next_at = clock_timestamp() + make_interval(secs => 1.0 / GREATEST(1, CASE WHEN boost_until < clock_timestamp() THEN 1 ELSE eps END))
WHERE run_id = $1 AND ordinal = $2 AND generator_token = $3;

-- name: Heartbeat :exec
INSERT INTO replica_heartbeats (id, seen_at, heap_bytes) VALUES ($1, now(), $2)
ON CONFLICT (id) DO UPDATE SET seen_at = now(), heap_bytes = excluded.heap_bytes;

-- name: SimulationStatus :one
SELECT c.eps, c.ordinal, j.position, c.guard_reason, c.pause_reason,
  COALESCE(c.guard_until > now(), false)::boolean AS fresh,
  (SELECT count(*) FROM outbox WHERE run_id='demo' AND delivered_at IS NULL) AS pending,
  pg_database_size(current_database())::bigint AS database_bytes
FROM controls c JOIN journal_clock j USING (run_id) WHERE c.run_id = 'demo';

-- name: ListReplicas :many
SELECT * FROM replica_heartbeats ORDER BY id LIMIT 10;

-- name: CDCSourceStatus :one
SELECT (count(*) > 0)::boolean AS present,
  COALESCE(bool_or(active), false)::boolean AS active,
  COALESCE(bool_or(wal_status = 'lost' OR invalidation_reason IS NOT NULL), false)::boolean AS invalidated,
  COALESCE(max(wal_status), 'unknown')::text AS wal_status,
  COALESCE(max(pg_wal_lsn_diff(pg_current_wal_lsn(), restart_lsn))::text, '')::text AS retained_wal_bytes
FROM pg_replication_slots
WHERE database = current_database() AND slot_name = 'ledger_lake';

-- name: SetRate :execrows
UPDATE controls SET eps = $1, boost_until = CASE WHEN $1 > 1
  THEN now() + interval '60 seconds' ELSE NULL END WHERE run_id = 'demo'
  AND ($1 = 0 OR EXISTS (SELECT FROM host_guard WHERE id AND safe_until > now()));

-- name: PauseOutbox :execrows
UPDATE controls SET outbox_pause_until = now() + interval '15 seconds'
WHERE run_id = 'demo' AND (outbox_pause_until IS NULL OR outbox_pause_until < now() - interval '45 seconds')
 AND EXISTS (SELECT FROM host_guard WHERE id AND safe_until > now());
