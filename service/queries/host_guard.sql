-- name: PublishHostGuard :exec
INSERT INTO host_guard (id, observed_at, safe_until, reason, evidence)
VALUES (true, now(), CASE WHEN sqlc.arg(reason)::text = '' THEN now() + interval '8 seconds' ELSE now() END,
 sqlc.arg(reason), sqlc.arg(evidence))
ON CONFLICT (id) DO UPDATE SET observed_at = excluded.observed_at,
 safe_until = excluded.safe_until, reason = excluded.reason, evidence = excluded.evidence;

-- name: HostGuardStatus :one
SELECT observed_at, safe_until > now() AS safe, reason, evidence FROM host_guard WHERE id;
