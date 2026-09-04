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

-- name: NextGeneratedCommand :one
SELECT ordinal FROM controls WHERE run_id = 'demo' AND eps > 0 AND next_at <= now()
  AND pause_reason = '' AND guard_until > now();

-- name: AcknowledgeGeneratedCommand :exec
UPDATE controls SET ordinal = ordinal + 1,
  eps = CASE WHEN boost_until < now() THEN 1 ELSE eps END,
  next_at = now() + make_interval(secs => 1.0 / GREATEST(1, CASE WHEN boost_until < now() THEN 1 ELSE eps END))
WHERE run_id = 'demo' AND ordinal = $1;

-- name: ClaimDelivery :one
SELECT o.run_id, o.sequence FROM outbox o JOIN controls c ON c.run_id = o.run_id
WHERE delivered_at IS NULL AND ready_at <= now()
  AND (c.outbox_pause_until IS NULL OR c.outbox_pause_until < now())
ORDER BY o.sequence LIMIT 1 FOR UPDATE OF o SKIP LOCKED;

-- name: AcceptDelivery :exec
INSERT INTO notification_inbox (run_id, sequence) VALUES ($1, $2) ON CONFLICT DO NOTHING;

-- name: CompleteDelivery :exec
UPDATE outbox SET delivered_at = now(), attempts = attempts + 1 WHERE run_id = $1 AND sequence = $2;

-- name: Heartbeat :exec
INSERT INTO replica_heartbeats (id, seen_at, heap_bytes) VALUES ($1, now(), $2)
ON CONFLICT (id) DO UPDATE SET seen_at = now(), heap_bytes = excluded.heap_bytes;

-- name: SimulationStatus :one
SELECT c.eps, c.ordinal, j.position, c.guard_reason, c.pause_reason,
  COALESCE(c.guard_until > now(), false)::boolean AS fresh,
  (SELECT count(*) FROM outbox WHERE delivered_at IS NULL) AS pending,
  pg_database_size(current_database())::bigint AS database_bytes
FROM controls c JOIN journal_clock j USING (run_id) WHERE c.run_id = 'demo';

-- name: ListReplicas :many
SELECT * FROM replica_heartbeats ORDER BY id LIMIT 10;

-- name: SetRate :execrows
UPDATE controls SET eps = $1, boost_until = CASE WHEN $1 > 1
  THEN now() + interval '60 seconds' ELSE NULL END WHERE run_id = 'demo'
  AND ($1 = 0 OR EXISTS (SELECT FROM host_guard WHERE id AND safe_until > now()));

-- name: PauseOutbox :execrows
UPDATE controls SET outbox_pause_until = now() + interval '15 seconds'
WHERE run_id = 'demo' AND (outbox_pause_until IS NULL OR outbox_pause_until < now() - interval '45 seconds')
 AND EXISTS (SELECT FROM host_guard WHERE id AND safe_until > now());
