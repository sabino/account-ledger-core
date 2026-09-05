-- +goose Up
-- +goose StatementBegin
CREATE TABLE host_guard (
 id boolean PRIMARY KEY DEFAULT true CHECK(id),
 observed_at timestamptz NOT NULL DEFAULT now(),
 safe_until timestamptz NOT NULL DEFAULT now(),
 reason text NOT NULL,
 evidence jsonb NOT NULL
);
DO $$ BEGIN
 IF NOT EXISTS(SELECT FROM pg_roles WHERE rolname='ledger_watch') THEN
  CREATE ROLE ledger_watch NOLOGIN;
 END IF;
 GRANT USAGE ON SCHEMA public TO ledger_watch;
 GRANT SELECT, INSERT, UPDATE ON host_guard TO ledger_watch;
 IF EXISTS(SELECT FROM pg_roles WHERE rolname='ledger_app') THEN
  GRANT SELECT ON host_guard TO ledger_app;
 END IF;
END $$;
-- +goose StatementEnd
