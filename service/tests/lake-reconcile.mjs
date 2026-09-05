import assert from "node:assert/strict";
import { execFileSync } from "node:child_process";
import { setTimeout as delay } from "node:timers/promises";
import { matchedBatches, normalize } from "./lake-comparison.mjs";

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
const source = JSON.parse(
  docker([
    "exec",
    `${project}-postgres-1`,
    "psql",
    "-U",
    "ledger_owner",
    "-d",
    "ledger",
    "-At",
    "-v",
    "ON_ERROR_STOP=1",
    "-c",
    `SELECT coalesce(json_agg(t),'[]') FROM (SELECT sequence::text AS sequence, envelope::text AS envelope FROM journal_batches WHERE run_id='${run}' ORDER BY journal_batches.sequence LIMIT 10001) t`,
  ]),
);
assert.ok(
  source.length > 0 && source.length <= 10000,
  "requires 1–10,000 source batches; use a separately designed chunked verifier beyond this bound",
);
const cutoff = source.at(-1).sequence;
assert.match(cutoff, /^\d+$/);
const expected = new Map(
  source.map((row) => [row.sequence, normalize(row.envelope)]),
);
assert.equal(expected.size, source.length);
const deadline = Date.now() + 120000;
let rawRows;
for (;;) {
  const text = docker([
    "exec",
    `${project}-clickhouse-1`,
    "clickhouse-client",
    "--user",
    "ledger_owner",
    "--password",
    "local-analytics-only",
    "--query",
    `SELECT toString(b.sequence) AS sequence, envelope FROM lake.\`ledger.ledger_public_journal_batches\` AS b WHERE run_id='${run}' AND b.sequence<=${cutoff} SETTINGS max_execution_time=15, max_result_rows=20000, result_overflow_mode='throw' FORMAT JSONEachRow`,
  ]).trim();
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
console.log(
  JSON.stringify({
    project,
    run,
    cutoff,
    source_batches: expected.size,
    lake_rows: rawRows,
    duplicate_deliveries: rawRows - expected.size,
    agreement: "every complete envelope matches at the captured source cutoff",
    scope:
      "bounded read-only local check; not storage durability, offset-loss recovery, or an ongoing production watermark",
  }),
);
