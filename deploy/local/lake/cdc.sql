-- Local simulation database only; never run against an existing application DB.
DO $$ BEGIN
 IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'ledger_cdc') THEN
  CREATE ROLE ledger_cdc LOGIN REPLICATION PASSWORD 'local-cdc-only';
 END IF;
END $$;
GRANT CONNECT ON DATABASE ledger TO ledger_cdc;
GRANT USAGE ON SCHEMA public TO ledger_cdc;
GRANT SELECT ON journal_batches TO ledger_cdc;
DO $$ BEGIN
 IF NOT EXISTS (SELECT 1 FROM pg_publication WHERE pubname = 'ledger_batches') THEN
  CREATE PUBLICATION ledger_batches FOR TABLE journal_batches;
 END IF;
END $$;
