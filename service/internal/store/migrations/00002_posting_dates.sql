-- +goose Up
-- +goose StatementBegin
-- Only the local initial slice predates posting-level dates. Its monetary
-- entries all used Day 1. Refuse to guess if another dataset is encountered.
DO $$ BEGIN
 IF EXISTS (
  SELECT 1 FROM postings p JOIN journal_batches b USING (run_id, sequence)
  WHERE b.value_day <> 1
 ) THEN RAISE EXCEPTION 'posting-date migration requires explicit historical mapping';
 END IF;
END $$;

ALTER TABLE postings ADD COLUMN value_day integer NOT NULL DEFAULT 1 CHECK (value_day > 0);
ALTER TABLE postings ADD COLUMN kind text NOT NULL DEFAULT 'legacy';
ALTER TABLE holds ADD COLUMN value_day integer NOT NULL DEFAULT 1 CHECK (value_day > 0);
CREATE INDEX postings_value_day ON postings (run_id, account_id, value_day, sequence);

CREATE TABLE fee_assessments (
 run_id text NOT NULL,
 account_id text NOT NULL,
 value_day integer NOT NULL CHECK (value_day > 0),
 PRIMARY KEY (run_id, account_id, value_day),
 FOREIGN KEY (run_id, account_id) REFERENCES accounts (run_id, id)
);
CREATE TABLE reversals (
 run_id text NOT NULL,
 target_event text NOT NULL,
 command_id text NOT NULL,
 PRIMARY KEY (run_id, target_event),
 FOREIGN KEY (run_id, target_event) REFERENCES command_results (run_id, id),
 FOREIGN KEY (run_id, command_id) REFERENCES command_results (run_id, id)
);
CREATE TABLE periods (
 run_id text PRIMARY KEY REFERENCES runs,
 start_day integer NOT NULL CHECK (start_day > 0),
 through_day integer NOT NULL CHECK (through_day >= start_day),
 command_id text NOT NULL,
 FOREIGN KEY (run_id, command_id) REFERENCES command_results (run_id, id)
);
GRANT SELECT, INSERT ON fee_assessments, reversals, periods TO ledger_app;
GRANT UPDATE(finalized) ON runs TO ledger_app;

-- Validate new metadata without changing previously posted envelopes.
CREATE OR REPLACE FUNCTION posting_metadata_matches() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE doc jsonb;
BEGIN
 SELECT envelope INTO doc FROM journal_batches WHERE run_id=NEW.run_id AND sequence=NEW.sequence;
 IF NEW.kind <> 'legacy' AND (
  (doc->'legs'->NEW.leg->>'value_day')::integer IS DISTINCT FROM NEW.value_day OR
  doc->'legs'->NEW.leg->>'kind' IS DISTINCT FROM NEW.kind
 ) THEN RAISE EXCEPTION 'posting metadata differs from envelope'; END IF;
 RETURN NULL;
END $$;
CREATE CONSTRAINT TRIGGER posting_metadata AFTER INSERT ON postings
DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION posting_metadata_matches();
-- +goose StatementEnd
