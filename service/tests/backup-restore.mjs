import assert from "node:assert/strict";
import { createHash, randomUUID } from "node:crypto";
import { execFileSync } from "node:child_process";

// Local-only recovery drill. It stops only this project's two API containers,
// restores into a newly named database, and deletes only that disposable copy.
const docker = (args, input) => execFileSync("docker", args, {
  input, maxBuffer: 128 * 1024 * 1024, timeout: 60000,
});
const endpoint = process.env.DOCKER_HOST || docker([
  "context", "inspect", "--format", "{{.Endpoints.docker.Host}}",
]).toString().trim();
assert.ok(endpoint.startsWith("unix://"), "recovery drill requires a local Docker socket");
const config = JSON.parse(docker(["compose", "config", "--format", "json"]));
assert.equal(config.name, "ledger-lab");
assert.equal(config.services.postgres.environment.POSTGRES_DB, "ledger");

const database = "ledger_restore_" + randomUUID().replaceAll("-", "");
const pg = (args, input) => docker(["compose", "exec", "-T", "postgres", ...args], input);
const sql = (name, statement) => pg([
  "psql", "-X", "-v", "ON_ERROR_STOP=1", "-U", "ledger_owner", "-d", name, "-At", "-c", statement,
]);
const tables = ["runs", "journal_clock", "accounts", "command_results", "journal_batches",
  "postings", "holds", "fee_assessments", "reversals", "periods", "outbox", "notification_inbox",
  "day_transitions", "account_close_jobs", "account_periods"];
const fingerprint = (name) => Object.fromEntries(tables.map(table => {
  // Table names come only from the fixed list above, never a user request.
  const rows = sql(name, `SELECT to_jsonb(t)::text FROM ${table} t ORDER BY to_jsonb(t)::text`);
  return [table, createHash("sha256").update(rows).digest("hex")];
}));

let created = false;
try {
  docker(["compose", "stop", "api-a", "api-b"]);
  const before = fingerprint("ledger");
  const backup = pg(["pg_dump", "-U", "ledger_owner", "-d", "ledger", "--format=custom", "--no-publications", "--no-subscriptions"]);
  pg(["createdb", "-U", "ledger_owner", database]);
  created = true;
  const start = performance.now();
  pg(["pg_restore", "-U", "ledger_owner", "-d", database, "--exit-on-error", "--no-publications", "--no-subscriptions"], backup);
  assert.deepEqual(fingerprint(database), before, "restored financial and delivery tables must match exactly");
  const unbalanced = sql(database, "SELECT count(*) FROM (SELECT run_id, sequence, currency FROM postings GROUP BY run_id, sequence, currency HAVING sum(units) <> 0) x").toString().trim();
  assert.equal(unbalanced, "0");
  const permissions = sql(database, "SELECT has_table_privilege('ledger_app','journal_batches','UPDATE'), has_table_privilege('ledger_app','postings','DELETE'), has_table_privilege('ledger_app','host_guard','UPDATE')").toString().trim();
  assert.equal(permissions, "f|f|f");
  console.log(JSON.stringify({ backup_bytes: backup.length, restore_and_verification_ms: Math.round(performance.now() - start), matched_tables: tables.length, unbalanced_batches: 0 }));
} finally {
  try {
    if (created) {
      // The name was generated here and cannot point to the source database.
      assert.ok(database.startsWith("ledger_restore_") && database.length === 47);
      pg(["dropdb", "-U", "ledger_owner", database]);
      console.log("Removed the disposable restored database; source database unchanged.");
    }
  } finally {
    docker(["compose", "start", "--wait", "api-a", "api-b"]);
  }
}
