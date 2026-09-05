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
