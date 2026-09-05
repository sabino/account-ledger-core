-- name: OpeningSettlementLines :many
SELECT b.command_id AS reference,p.currency,p.value_day,sum(p.units)::text AS amount
FROM postings p JOIN journal_batches b USING(run_id,sequence)
WHERE p.run_id=$1 AND p.sequence<=sqlc.arg(cutoff)::bigint
 AND p.account_id IN ('settlement-AED','settlement-BHD')
 AND b.command_id LIKE 'seed-%'
GROUP BY b.sequence,b.command_id,p.currency,p.value_day
ORDER BY b.sequence,p.currency,p.value_day LIMIT 10001;
