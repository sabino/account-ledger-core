-- name: LockRun :one
SELECT * FROM runs WHERE id = $1 FOR SHARE;

-- name: ClaimCommand :exec
INSERT INTO command_results (run_id, id, hash) VALUES ($1, $2, $3)
ON CONFLICT DO NOTHING;

-- name: LockCommand :one
SELECT * FROM command_results WHERE run_id = $1 AND id = $2 FOR UPDATE;

-- name: LockAccount :one
SELECT * FROM accounts WHERE run_id = $1 AND id = $2 FOR UPDATE;

-- name: UpdateAccount :exec
UPDATE accounts SET balance = $3, held = $4, version = version + 1
WHERE run_id = $1 AND id = $2;

-- name: CreateHold :execrows
INSERT INTO holds (run_id, id, account_id, amount, state, value_day)
VALUES ($1, $2, $3, $4, $5, $6) ON CONFLICT DO NOTHING;

-- name: LockHold :one
SELECT * FROM holds WHERE run_id = $1 AND id = $2 FOR UPDATE;

-- name: CaptureHold :exec
UPDATE holds SET state = 'captured', captured = $3, released = $4
WHERE run_id = $1 AND id = $2;

-- name: NextSequence :one
UPDATE journal_clock SET position = position + 1 WHERE run_id = $1 RETURNING position;

-- name: AppendBatch :exec
INSERT INTO journal_batches (run_id, sequence, command_id, kind, booked_day, value_day, instance, envelope)
VALUES ($1, $2, $3, $4, $5, $6, $7, $8);

-- name: AppendPosting :exec
INSERT INTO postings (run_id, sequence, leg, account_id, currency, units, value_day, kind)
VALUES ($1, $2, $3, $4, $5, $6, $7, $8);

-- name: CompleteCommand :exec
UPDATE command_results SET response = $3 WHERE run_id = $1 AND id = $2;

-- name: EnqueueDelivery :exec
INSERT INTO outbox (run_id, sequence) VALUES ($1, $2);

-- name: ListAccounts :many
SELECT * FROM accounts WHERE run_id = $1 ORDER BY id;

-- name: ListJournal :many
SELECT b.* FROM journal_batches b
WHERE b.run_id = sqlc.arg(run_id)
  AND (sqlc.arg(account_id)::text = '' OR EXISTS (
    SELECT 1 FROM postings p WHERE p.run_id = b.run_id AND p.sequence = b.sequence
    AND p.account_id = sqlc.arg(account_id)))
  AND (sqlc.arg(cutoff)::bigint = 0 OR b.sequence <= sqlc.arg(cutoff))
ORDER BY b.sequence DESC LIMIT 60;

-- name: CurrentSequence :one
SELECT position FROM journal_clock WHERE run_id = $1;

-- name: CountBalanceDifferences :one
SELECT count(*) FROM accounts a LEFT JOIN (
  SELECT account_id, sum(units) units FROM postings WHERE postings.run_id = $1 GROUP BY account_id
) p ON p.account_id = a.id
WHERE a.run_id = $1 AND a.balance <> COALESCE(p.units, 0) *
  CASE WHEN a.class IN ('liability', 'income', 'equity') THEN -1 ELSE 1 END;

-- name: CountUnbalancedBatches :one
SELECT count(*) FROM (
  SELECT sequence, currency FROM postings WHERE run_id = $1
  GROUP BY sequence, currency HAVING sum(units) <> 0
) x;

-- name: CountHoldDifferences :one
SELECT count(*) FROM accounts a LEFT JOIN (
  SELECT account_id, sum(amount) amount FROM holds
  WHERE holds.run_id = $1 AND state = 'active' GROUP BY account_id
) h ON h.account_id = a.id
WHERE a.run_id = $1 AND a.held <> COALESCE(h.amount, 0);
