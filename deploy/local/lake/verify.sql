-- Read-only fixture checks. CDC is asynchronous; run after ingestion catches up.
-- Raw delivery may repeat. Reconciliation must deduplicate by (run_id, sequence).
SELECT count() AS raw_rows, uniqExact((run_id, sequence)) AS unique_batches,
       max(sequence) AS latest
FROM lake.`ledger.ledger_public_journal_batches`
WHERE run_id = 'assessment-v1';

SELECT sequence, any(JSONExtractString(envelope, 'status')) AS status,
       any(length(JSONExtractArrayRaw(ifNull(envelope, '{}'), 'legs'))) AS legs,
       uniqExact(envelope) AS envelope_variants
FROM lake.`ledger.ledger_public_journal_batches`
WHERE run_id = 'assessment-v1'
GROUP BY sequence ORDER BY sequence;

WITH batches AS (
  SELECT run_id, sequence, any(ifNull(envelope, '{}')) AS envelope
  FROM lake.`ledger.ledger_public_journal_batches`
  WHERE run_id = 'assessment-v1'
  GROUP BY run_id, sequence
), legs AS (
  SELECT arrayJoin(JSONExtractArrayRaw(envelope, 'legs')) AS leg FROM batches
)
SELECT JSONExtractString(leg, 'account') AS account,
       JSONExtractString(leg, 'currency') AS currency,
       sum(toInt128(JSONExtractString(leg, 'units'))) AS signed_minor_units
FROM legs GROUP BY account, currency ORDER BY account;
