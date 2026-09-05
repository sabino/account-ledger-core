-- name: FindDayTransition :one
SELECT * FROM day_transitions WHERE run_id=$1 AND from_day=$2;

-- name: PendingRunCloses :one
SELECT count(*) FROM account_close_jobs WHERE run_id=$1 AND state<>'done';

-- name: RecordDayTransition :exec
INSERT INTO day_transitions(run_id,from_day,to_day,instance) VALUES($1,$2,$3,$4);

-- name: ScheduleAccountCloses :exec
INSERT INTO account_close_jobs(run_id,account_id,day)
SELECT a.run_id,a.id,sqlc.arg(day)::integer FROM accounts a WHERE a.run_id=sqlc.arg(run_id) AND a.customer;

-- name: AdvanceRunDay :exec
UPDATE runs SET day=$2 WHERE id=$1;

-- name: PendingAccountCloses :one
SELECT count(*) FROM account_close_jobs
WHERE run_id=$1 AND account_id=$2 AND state<>'done';

-- name: LockAccountCloseJob :one
SELECT * FROM account_close_jobs WHERE run_id=$1 AND account_id=$2 AND day=$3 FOR UPDATE;

-- name: SetAccountCloseJob :exec
UPDATE account_close_jobs SET state=$4,reason=$5 WHERE run_id=$1 AND account_id=$2 AND day=$3;

-- name: PriorPeriodCloses :many
SELECT j.day,b.envelope AS response FROM account_close_jobs j
JOIN command_results c ON c.run_id=j.run_id AND c.id='system:close:'||j.day::text||':'||j.account_id
JOIN journal_batches b ON b.run_id=c.run_id AND b.sequence=(c.response->>'sequence')::bigint
 AND b.command_id=c.id AND b.kind='account_close'
WHERE j.run_id=$1 AND j.account_id=$2 AND j.day>=sqlc.arg(start_day)::integer
 AND j.day<sqlc.arg(through_day)::integer AND j.state='done'
ORDER BY j.day;

-- name: RecordAccountPeriod :exec
INSERT INTO account_periods(run_id,account_id,start_day,through_day,sequence,amount)
VALUES($1,$2,$3,$4,$5,$6);
