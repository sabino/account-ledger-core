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
INSERT INTO runs (id, profile) VALUES ($1, $2);

-- name: CreateClock :exec
INSERT INTO journal_clock (run_id) VALUES ($1);

-- name: CreateControls :exec
INSERT INTO controls (run_id, eps) VALUES ($1, 0);
