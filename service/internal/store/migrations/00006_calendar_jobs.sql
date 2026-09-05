-- +goose Up
-- +goose StatementBegin
CREATE TABLE day_transitions (
 run_id text REFERENCES runs, from_day integer NOT NULL CHECK(from_day>0),
 to_day integer NOT NULL CHECK(to_day=from_day+1),
 recorded_at timestamptz NOT NULL DEFAULT clock_timestamp(),
 instance text NOT NULL, PRIMARY KEY(run_id,from_day)
);
CREATE TRIGGER immutable_day_transition BEFORE UPDATE OR DELETE ON day_transitions
 FOR EACH ROW EXECUTE FUNCTION immutable_fact();
CREATE TABLE account_close_jobs (
 run_id text, account_id text, day integer NOT NULL CHECK(day>0),
 state text NOT NULL DEFAULT 'pending' CHECK(state IN ('pending','blocked','done')),
 reason text NOT NULL DEFAULT '',
 PRIMARY KEY(run_id,account_id,day),
 FOREIGN KEY(run_id,account_id) REFERENCES accounts(run_id,id),
 FOREIGN KEY(run_id,day) REFERENCES day_transitions(run_id,from_day)
);
CREATE INDEX account_close_pending ON account_close_jobs(run_id,day,account_id) WHERE state<>'done';
DO $$ BEGIN
 IF EXISTS(SELECT 1 FROM pg_roles WHERE rolname='ledger_app') THEN
  GRANT SELECT,INSERT ON day_transitions TO ledger_app;
  GRANT SELECT,INSERT,UPDATE ON account_close_jobs TO ledger_app;
 END IF;
END $$;
-- +goose StatementEnd
