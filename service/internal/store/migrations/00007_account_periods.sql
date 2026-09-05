-- +goose Up
-- +goose StatementBegin
-- Synthetic six-day cadence, not a banking calendar or the terminal fixture.
CREATE TABLE account_periods (
 run_id text, account_id text, start_day integer NOT NULL CHECK(start_day>0),
 through_day integer NOT NULL CHECK(through_day=start_day+5 AND through_day%6=0),
 sequence bigint NOT NULL, amount bigint NOT NULL CHECK(amount>=0),
 PRIMARY KEY(run_id,account_id,through_day),
 FOREIGN KEY(run_id,account_id) REFERENCES accounts(run_id,id),
 FOREIGN KEY(run_id,sequence) REFERENCES journal_batches(run_id,sequence)
);
CREATE TRIGGER immutable_account_period BEFORE UPDATE OR DELETE ON account_periods
 FOR EACH ROW EXECUTE FUNCTION immutable_fact();
GRANT SELECT,INSERT ON account_periods TO ledger_app;
-- +goose StatementEnd
