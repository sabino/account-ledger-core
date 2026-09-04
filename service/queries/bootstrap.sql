-- name: LockBootstrap :exec
SELECT pg_advisory_xact_lock(937413);

-- name: CreateDemoRun :exec
INSERT INTO runs (id, profile) VALUES ('demo', 'live') ON CONFLICT DO NOTHING;

-- name: CreateDemoClock :exec
INSERT INTO journal_clock (run_id) VALUES ('demo') ON CONFLICT DO NOTHING;

-- name: CreateDemoControls :exec
INSERT INTO controls (run_id) VALUES ('demo') ON CONFLICT DO NOTHING;

-- name: CreateAccount :exec
INSERT INTO accounts (run_id, id, name, currency, class, customer)
VALUES ($1, $2, $3, $4, $5, $6) ON CONFLICT DO NOTHING;

-- name: CreateRun :exec
INSERT INTO runs (id, profile, policy) VALUES ($1, $2,
 jsonb_build_object('version', CASE WHEN $2 = 'fixture' THEN 'assessment-v1' ELSE 'simulation-v1' END,
 'fee_aed', 2500, 'rate_numerator', 1, 'rate_denominator', 2500));

-- name: CreateClock :exec
INSERT INTO journal_clock (run_id) VALUES ($1);

-- name: CreateControls :exec
INSERT INTO controls (run_id, eps) VALUES ($1, 0);
