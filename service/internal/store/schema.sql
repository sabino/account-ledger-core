-- Dedicated simulation database only. Migration owner is separate from runtime.
CREATE TABLE IF NOT EXISTS runs (
 id text PRIMARY KEY, profile text NOT NULL CHECK(profile IN ('live','fixture')),
 created_at timestamptz NOT NULL DEFAULT now(), day integer NOT NULL DEFAULT 1 CHECK(day>0),
 policy jsonb NOT NULL DEFAULT '{"version":"simulation-v1","rate_denominator":2500,"fee_aed":2500}',
 finalized boolean NOT NULL DEFAULT false
);
CREATE TABLE IF NOT EXISTS journal_clock(run_id text PRIMARY KEY REFERENCES runs, position bigint NOT NULL DEFAULT 0);
CREATE TABLE IF NOT EXISTS accounts (
 run_id text REFERENCES runs, id text, name text NOT NULL, currency text NOT NULL CHECK(currency IN ('AED','BHD')),
 class text NOT NULL CHECK(class IN ('asset','liability','income','expense','equity')),
 customer boolean NOT NULL DEFAULT true, balance bigint NOT NULL DEFAULT 0,
 held bigint NOT NULL DEFAULT 0 CHECK(held>=0), version bigint NOT NULL DEFAULT 0,
 PRIMARY KEY(run_id,id), UNIQUE(run_id,id,currency)
);
CREATE TABLE IF NOT EXISTS command_results (
 run_id text REFERENCES runs, id text, hash text NOT NULL, response jsonb,
 created_at timestamptz NOT NULL DEFAULT now(), PRIMARY KEY(run_id,id)
);
CREATE TABLE IF NOT EXISTS journal_batches (
 run_id text REFERENCES runs, sequence bigint, command_id text NOT NULL, kind text NOT NULL,
 booked_day integer NOT NULL CHECK(booked_day>0), value_day integer NOT NULL CHECK(value_day>0),
 instance text NOT NULL, created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
 envelope jsonb NOT NULL, PRIMARY KEY(run_id,sequence),
 FOREIGN KEY(run_id,command_id) REFERENCES command_results(run_id,id)
);
CREATE TABLE IF NOT EXISTS postings (
 run_id text, sequence bigint, leg integer CHECK(leg>=0), account_id text NOT NULL,
 currency text NOT NULL, units bigint NOT NULL CHECK(units<>0),
 PRIMARY KEY(run_id,sequence,leg),
 FOREIGN KEY(run_id,sequence) REFERENCES journal_batches,
 FOREIGN KEY(run_id,account_id,currency) REFERENCES accounts(run_id,id,currency)
);
CREATE INDEX IF NOT EXISTS postings_account ON postings(run_id,account_id,sequence);
CREATE TABLE IF NOT EXISTS holds (
 run_id text, id text, account_id text NOT NULL, amount bigint NOT NULL CHECK(amount>0),
 state text NOT NULL CHECK(state IN ('active','declined','captured')),
 captured bigint NOT NULL DEFAULT 0 CHECK(captured>=0), released bigint NOT NULL DEFAULT 0 CHECK(released>=0),
 PRIMARY KEY(run_id,id), FOREIGN KEY(run_id,account_id) REFERENCES accounts(run_id,id),
 CHECK(captured+released<=amount)
);
CREATE TABLE IF NOT EXISTS outbox (
 run_id text, sequence bigint, attempts integer NOT NULL DEFAULT 0,
 ready_at timestamptz NOT NULL DEFAULT now(), delivered_at timestamptz,
 PRIMARY KEY(run_id,sequence), FOREIGN KEY(run_id,sequence) REFERENCES journal_batches
);
CREATE TABLE IF NOT EXISTS notification_inbox (
 run_id text, sequence bigint, received_at timestamptz NOT NULL DEFAULT now(),
 PRIMARY KEY(run_id,sequence), FOREIGN KEY(run_id,sequence) REFERENCES journal_batches
);
CREATE TABLE IF NOT EXISTS controls (
 run_id text PRIMARY KEY REFERENCES runs, eps integer NOT NULL DEFAULT 1 CHECK(eps BETWEEN 0 AND 20),
 boost_until timestamptz, next_at timestamptz NOT NULL DEFAULT now(), ordinal bigint NOT NULL DEFAULT 0,
 pause_reason text NOT NULL DEFAULT '', outbox_pause_until timestamptz,
 budget_second bigint NOT NULL DEFAULT 0,budget_used integer NOT NULL DEFAULT 0,
 guard_until timestamptz, guard_reason text NOT NULL DEFAULT 'guard not initialized'
);
CREATE TABLE IF NOT EXISTS replica_heartbeats (
 id text PRIMARY KEY, seen_at timestamptz NOT NULL, requests bigint NOT NULL DEFAULT 0,
 heap_bytes bigint NOT NULL DEFAULT 0
);

CREATE OR REPLACE FUNCTION immutable_fact() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN RAISE EXCEPTION 'posted facts are immutable'; END $$;
DROP TRIGGER IF EXISTS immutable_journal ON journal_batches;
CREATE TRIGGER immutable_journal BEFORE UPDATE OR DELETE ON journal_batches FOR EACH ROW EXECUTE FUNCTION immutable_fact();
DROP TRIGGER IF EXISTS immutable_postings ON postings;
CREATE TRIGGER immutable_postings BEFORE UPDATE OR DELETE ON postings FOR EACH ROW EXECUTE FUNCTION immutable_fact();

CREATE OR REPLACE FUNCTION balanced_batch() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE n integer; doc jsonb; batch_kind text;
BEGIN
 SELECT envelope,kind INTO doc,batch_kind FROM journal_batches WHERE run_id=NEW.run_id AND sequence=NEW.sequence;
 SELECT count(*) INTO n FROM postings WHERE run_id=NEW.run_id AND sequence=NEW.sequence;
 IF n=1 OR EXISTS(SELECT 1 FROM postings WHERE run_id=NEW.run_id AND sequence=NEW.sequence GROUP BY currency HAVING sum(units)<>0)
 THEN RAISE EXCEPTION 'unbalanced journal batch'; END IF;
 IF doc->>'kind' IS DISTINCT FROM batch_kind OR
    jsonb_array_length(doc->'legs') IS DISTINCT FROM n OR
    EXISTS(SELECT 1 FROM postings p WHERE p.run_id=NEW.run_id AND p.sequence=NEW.sequence AND
      (doc->'legs'->p.leg->>'account' IS DISTINCT FROM p.account_id OR
       doc->'legs'->p.leg->>'currency' IS DISTINCT FROM p.currency OR
       (doc->'legs'->p.leg->>'units')::bigint IS DISTINCT FROM p.units))
 THEN RAISE EXCEPTION 'incomplete batch envelope'; END IF;
 RETURN NULL;
END $$;
DROP TRIGGER IF EXISTS balanced_journal ON journal_batches;
CREATE CONSTRAINT TRIGGER balanced_journal AFTER INSERT ON journal_batches DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION balanced_batch();
DROP TRIGGER IF EXISTS balanced_postings ON postings;
CREATE CONSTRAINT TRIGGER balanced_postings AFTER INSERT ON postings DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION balanced_batch();

-- App role is created by deployment, never by an internet-facing process.
DO $$ BEGIN
 IF EXISTS(SELECT 1 FROM pg_roles WHERE rolname='ledger_app') THEN
  GRANT USAGE ON SCHEMA public TO ledger_app;
  GRANT SELECT ON ALL TABLES IN SCHEMA public TO ledger_app;
  GRANT INSERT ON command_results,journal_batches,postings,holds,outbox,notification_inbox,replica_heartbeats TO ledger_app;
  GRANT UPDATE ON accounts,command_results,holds,outbox,controls,journal_clock,replica_heartbeats TO ledger_app;
  -- SELECT FOR SHARE needs UPDATE privilege on at least one column. Policy and
  -- finalized state remain outside this grant; live calendar work owns day.
  GRANT UPDATE(day) ON runs TO ledger_app;
 END IF;
END $$;
