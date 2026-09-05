import assert from "node:assert/strict";
import { execFileSync } from "node:child_process";
import { setTimeout as delay } from "node:timers/promises";
import { matchedBatches } from "./lake-comparison.mjs";
import { sourceChunk, completePrefix, chunkSize } from "./lake-chunks.mjs";

// Read-only, bounded local comparison. Never treats row count alone as agreement.
const project = process.argv[2] || "ledger-lab";
const run = process.argv[3] || "demo";
assert.ok(["ledger-lab", "ledger-budget"].includes(project));
assert.ok(["demo", "assessment-v1"].includes(run));
const docker = (args) =>
  execFileSync("docker", args, {
    encoding: "utf8",
    timeout: 20000,
    maxBuffer: 32 * 1024 * 1024,
  });
for (const service of ["postgres", "clickhouse"]) {
  const [c] = JSON.parse(docker(["inspect", `${project}-${service}-1`]));
  assert.equal(c.Config.Labels["com.docker.compose.project"], project);
  assert.equal(c.Config.Labels["com.docker.compose.service"], service);
  assert.equal(c.State.Running, true);
}
const sourceQuery = (query) =>
  JSON.parse(
    docker([
      "exec",
      `${project}-postgres-1`,
      "psql",
      "-U",
      "ledger_owner",
      "-d",
      "ledger",
      "-At",
      "-q",
      "-v",
      "ON_ERROR_STOP=1",
      "-c",
      `SET statement_timeout='15s'; ${query}`,
    ]),
  );
const captured = sourceQuery(
  `SELECT json_build_object('cutoff', max(sequence)::text, 'count', count(*)::text) FROM journal_batches WHERE run_id='${run}'`,
);
const total = Number(captured.count);
assert.ok(
  Number.isSafeInteger(total) && total > 0 && total <= 100000,
  "requires 1–100,000 source batches within the simulation run budget",
);
const cutoff = captured.cutoff;
assert.match(cutoff, /^\d+$/);
const overallDeadline = Date.now() + 600000;
let after = "0",
  compared = 0,
  allRows = 0,
  chunks = 0;
let timeoutRetries = 0;
while (BigInt(after) < BigInt(cutoff)) {
  assert.ok(
    Date.now() < overallDeadline,
    "comparison exceeded its ten-minute budget",
  );
  const source = sourceQuery(
    `SELECT coalesce(json_agg(t),'[]') FROM (SELECT sequence::text AS sequence, envelope::text AS envelope FROM journal_batches WHERE run_id='${run}' AND sequence>${after} AND sequence<=${cutoff} ORDER BY journal_batches.sequence LIMIT ${chunkSize}) t`,
  );
  const { expected, through } = sourceChunk(source, after, cutoff);
  const deadline = Math.min(overallDeadline, Date.now() + 120000);
  let rawRows;
  for (;;) {
    let text;
    try {
      text = docker([
        "exec",
        `${project}-clickhouse-1`,
        "clickhouse-client",
        "--user",
        "ledger_owner",
        "--password",
        "local-analytics-only",
        "--query",
        `SELECT toString(b.sequence) AS sequence, envelope FROM lake.\`ledger.ledger_public_journal_batches\` AS b WHERE run_id='${run}' AND b.sequence>${after} AND b.sequence<=${through} SETTINGS max_execution_time=15, max_result_rows=20000, result_overflow_mode='throw' FORMAT JSONEachRow`,
      ]).trim();
    } catch (error) {
      // A returning catalog can outlive one query deadline. Retry only that
      // transport timeout, with the same source cutoff and a finite budget.
      if (
        error.code !== "ETIMEDOUT" ||
        timeoutRetries >= 2 ||
        Date.now() >= deadline
      )
        throw error;
      timeoutRetries++;
      console.log(
        JSON.stringify({
          waiting: true,
          run,
          cutoff,
          query_timeout_retry: timeoutRetries,
        }),
      );
      await delay(5000);
      continue;
    }
    const rows = text ? text.split("\n").map(JSON.parse) : [];
    rawRows = rows.length;
    const matched = matchedBatches(expected, rows);
    if (matched === expected.size) break;
    assert.ok(
      Date.now() < deadline,
      `lake incomplete at fixed cutoff ${cutoff}: ${matched}/${expected.size}`,
    );
    console.log(
      JSON.stringify({
        waiting: true,
        run,
        cutoff,
        matched,
        expected: expected.size,
      }),
    );
    await delay(5000);
  }
  compared += expected.size;
  allRows += rawRows;
  chunks++;
  after = through;
  console.log(
    JSON.stringify({
      chunk: chunks,
      through,
      cutoff,
      compared,
      captured: total,
    }),
  );
  await delay(250);
}
completePrefix(compared, total, after, cutoff);
const retained = sourceQuery(
  `SELECT json_build_object('count', count(*)::text) FROM journal_batches WHERE run_id='${run}' AND sequence<=${cutoff}`,
);
assert.equal(
  retained.count,
  captured.count,
  "source retention changed the compared prefix",
);
console.log(
  JSON.stringify({
    project,
    run,
    cutoff,
    source_batches: compared,
    lake_rows: allRows,
    duplicate_deliveries: allRows - compared,
    chunks,
    source_chunk_limit: chunkSize,
    query_timeout_retries: timeoutRetries,
    agreement: "every complete envelope matches at the captured source cutoff",
    scope:
      "bounded read-only local check; not storage durability, offset-loss recovery, or an ongoing production watermark",
  }),
);
