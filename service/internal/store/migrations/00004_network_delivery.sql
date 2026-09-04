-- +goose Up
-- +goose StatementBegin
ALTER TABLE outbox ADD COLUMN lease_token text, ADD COLUMN lease_until timestamptz;
CREATE INDEX outbox_pending_delivery ON outbox(run_id,ready_at,sequence) WHERE delivered_at IS NULL;
CREATE TABLE delivery_attempt_events (
 token text NOT NULL, phase text NOT NULL CHECK(phase IN ('claimed','acknowledged','retry')),
 run_id text NOT NULL, sequence bigint NOT NULL, instance text NOT NULL,
 recorded_at timestamptz NOT NULL DEFAULT clock_timestamp(),
 PRIMARY KEY(token,phase), FOREIGN KEY(run_id,sequence) REFERENCES outbox
);
CREATE TRIGGER immutable_delivery_attempt BEFORE UPDATE OR DELETE ON delivery_attempt_events
FOR EACH ROW EXECUTE FUNCTION immutable_fact();
GRANT SELECT, INSERT ON delivery_attempt_events TO ledger_app;
-- +goose StatementEnd
