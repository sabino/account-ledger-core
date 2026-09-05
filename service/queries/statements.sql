-- name: StatementAccount :one
SELECT id, name, currency, class, customer FROM accounts WHERE run_id=$1 AND id=$2;

-- name: StatementTotals :one
SELECT count(*) AS posting_count,
 COALESCE(sum(units),0)::text AS closing_units,
 COALESCE(sum(units) FILTER (WHERE (sequence,leg) <= (sqlc.arg(after_sequence)::bigint,sqlc.arg(after_leg)::integer)),0)::text AS opening_units,
 COALESCE(sum(units) FILTER (WHERE units>0),0)::text AS debit_units,
 COALESCE(-sum(units) FILTER (WHERE units<0),0)::text AS credit_units
FROM postings
WHERE run_id=sqlc.arg(run_id) AND account_id=sqlc.arg(account_id) AND sequence<=sqlc.arg(cutoff)::bigint;

-- name: StatementLines :many
SELECT p.sequence,p.leg,p.units,p.value_day,p.kind,b.booked_day,b.created_at,b.command_id,b.instance
FROM postings p JOIN journal_batches b USING (run_id,sequence)
WHERE p.run_id=sqlc.arg(run_id) AND p.account_id=sqlc.arg(account_id)
 AND p.sequence<=sqlc.arg(cutoff)::bigint
 AND (p.sequence,p.leg) > (sqlc.arg(after_sequence)::bigint,sqlc.arg(after_leg)::integer)
ORDER BY p.sequence,p.leg LIMIT sqlc.arg(page_limit)::integer;
