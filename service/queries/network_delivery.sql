-- name: LeaseDelivery :one
WITH candidate AS (
 SELECT o.run_id,o.sequence FROM outbox o JOIN controls c ON c.run_id=o.run_id
 WHERE o.run_id=sqlc.arg(run_id) AND o.delivered_at IS NULL AND o.ready_at <= now()
 AND (o.lease_until IS NULL OR o.lease_until < now())
 AND (c.outbox_pause_until IS NULL OR c.outbox_pause_until < now())
 ORDER BY o.ready_at,o.sequence LIMIT 1 FOR UPDATE OF o SKIP LOCKED
), leased AS (
 UPDATE outbox o SET lease_token=sqlc.arg(token), lease_until=now()+interval '15 seconds', attempts=attempts+1
 FROM candidate c WHERE o.run_id=c.run_id AND o.sequence=c.sequence RETURNING o.run_id,o.sequence
), audit AS (
 INSERT INTO delivery_attempt_events(token,phase,run_id,sequence,instance)
 SELECT sqlc.arg(token),'claimed',run_id,sequence,sqlc.arg(instance) FROM leased
)
SELECT b.run_id,b.sequence,b.envelope FROM journal_batches b JOIN leased l USING(run_id,sequence);

-- name: FinishDelivery :execrows
WITH finished AS (
 UPDATE outbox o SET delivered_at=CASE WHEN sqlc.arg(success)::boolean THEN now() ELSE NULL END,
 ready_at=CASE WHEN sqlc.arg(success)::boolean THEN ready_at ELSE now()+interval '2 seconds' END,
 lease_token=NULL,lease_until=NULL
 WHERE o.run_id=sqlc.arg(run_id) AND o.sequence=sqlc.arg(sequence) AND o.lease_token=sqlc.arg(token)
 RETURNING o.run_id,o.sequence
)
INSERT INTO delivery_attempt_events(token,phase,run_id,sequence,instance)
SELECT sqlc.arg(token),CASE WHEN sqlc.arg(success)::boolean THEN 'acknowledged' ELSE 'retry' END,
run_id,sequence,sqlc.arg(instance) FROM finished;

-- name: ReceiveNotification :one
WITH matched AS (
 SELECT b.run_id,b.sequence FROM journal_batches b WHERE b.run_id=sqlc.arg(run_id) AND b.sequence=sqlc.arg(sequence) AND b.envelope=sqlc.arg(envelope)::jsonb
), accepted AS (
 INSERT INTO notification_inbox(run_id,sequence) SELECT run_id,sequence FROM matched ON CONFLICT DO NOTHING
)
SELECT EXISTS(SELECT FROM matched)::boolean;
