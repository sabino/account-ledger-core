-- name: EventAnalytics :one
-- One snapshot, 60 equal buckets. Currency is the command currency; legacy
-- records without it fall back to posting currencies. Unattributed decisions
-- belong only to the all-currency view. Retries do not create new decisions.
WITH scope AS (
 SELECT now() AS through, now() - make_interval(secs => sqlc.arg(seconds)::int) AS since
), events AS (
 SELECT floor(extract(epoch FROM (b.created_at-s.since))*60/sqlc.arg(seconds)::int)::int AS bucket,
        b.envelope->>'status' AS status,
        b.envelope->>'instance' AS instance
 FROM journal_batches b, scope s
 WHERE b.run_id=sqlc.arg(run_id) AND b.created_at>=s.since AND b.created_at<s.through
 AND (sqlc.arg(currency)::text='' OR b.envelope->'command'->>'currency'=sqlc.arg(currency)
 OR (coalesce(b.envelope->'command'->>'currency','')='' AND EXISTS (
 SELECT FROM postings p WHERE p.run_id=b.run_id AND p.sequence=b.sequence AND p.currency=sqlc.arg(currency))))
), counts AS (
 SELECT bucket, count(*) AS total,
 count(*) FILTER (WHERE status='accepted') AS accepted,
 count(*) FILTER (WHERE status='declined') AS declined,
 count(*) FILTER (WHERE status='rejected') AS rejected
 FROM events GROUP BY bucket
), buckets AS (
 SELECT n, s.since + (s.through-s.since)*n/60 AS at,
 coalesce(c.total,0) AS total,
 coalesce(c.accepted,0) AS accepted,
 coalesce(c.declined,0) AS declined,
 coalesce(c.rejected,0) AS rejected
 FROM scope s CROSS JOIN generate_series(0,59) n
 LEFT JOIN counts c ON c.bucket=n
)
SELECT jsonb_build_object('since',s.since,'through',s.through,'currency',sqlc.arg(currency)::text,
 'bucket_seconds',sqlc.arg(seconds)::int/60,
 'buckets',(SELECT jsonb_agg(jsonb_build_object('at',at,'total',total,'accepted',accepted,'declined',declined,'rejected',rejected) ORDER BY n) FROM buckets),
 'instances',coalesce((SELECT jsonb_agg(row_to_json(i)) FROM (SELECT coalesce(instance,'unknown') AS instance,count(*) AS total FROM events GROUP BY instance ORDER BY instance) i),'[]'::jsonb))::jsonb
FROM scope s;
