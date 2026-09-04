-- name: LatestBookedDay :one
SELECT COALESCE(max(booked_day), 0)::integer AS day
FROM journal_batches WHERE run_id = $1;

-- name: HistoricalBalance :one
SELECT COALESCE(sum(-p.units::numeric), 0)::bigint AS balance
FROM postings p
WHERE p.run_id = sqlc.arg(run_id) AND p.account_id = sqlc.arg(account_id)
AND p.value_day <= sqlc.arg(value_day)
AND (sqlc.arg(known_through)::bigint = 0 OR p.sequence <= sqlc.arg(known_through));

-- name: AssessedFeeDays :many
SELECT value_day FROM fee_assessments WHERE run_id = $1 AND account_id = $2;

-- name: RecordFee :exec
INSERT INTO fee_assessments (run_id, account_id, value_day) VALUES ($1, $2, $3);

-- name: FindReversibleDebit :one
SELECT p.* FROM postings p JOIN journal_batches b USING (run_id, sequence)
WHERE p.run_id = $1 AND p.account_id = $2 AND b.command_id = $3
AND p.kind = 'debit' AND p.units > 0;

-- name: RecordReversal :execrows
INSERT INTO reversals (run_id, target_event, command_id) VALUES ($1, $2, $3)
ON CONFLICT DO NOTHING;

-- name: LockFinalization :one
SELECT * FROM runs WHERE id = $1 FOR UPDATE;

-- name: RecordPeriod :exec
INSERT INTO periods (run_id, start_day, through_day, command_id) VALUES ($1, $2, $3, $4);

-- name: FinalizeRun :exec
UPDATE runs SET finalized = true WHERE id = $1;
