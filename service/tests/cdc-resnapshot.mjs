import assert from "node:assert/strict";
import { execFileSync } from "node:child_process";
import { randomUUID } from "node:crypto";
import { setTimeout as delay } from "node:timers/promises";

// Operator-only fault injection, deliberately restricted to the disposable stack.
// Removes its replication cursor, NOT financial facts, lake rows or offset files.
const mode = process.argv[2];
assert.ok(["exercise", "recover"].includes(mode), "use exercise or recover");
const project = "ledger-budget";
const consumer = `${project}-cdc-1`;
const docker = (args, options = {}) =>
  execFileSync("docker", args, {
    encoding: "utf8",
    timeout: 20000,
    maxBuffer: 4 * 1024 * 1024,
    ...options,
  });
const composeFiles = [
  "compose.yaml",
  "deploy/local/budget.yaml",
  "deploy/local/compact-budget.yaml",
  "deploy/local/lake/offset-safety.yaml",
];
function compose(recovery) {
  const files = recovery
    ? [...composeFiles, "deploy/local/lake/resnapshot.yaml"]
    : composeFiles;
  return docker(
    [
      "compose",
      "-p",
      project,
      ...files.flatMap((file) => ["-f", file]),
      "up",
      "-d",
      "--no-deps",
      "cdc",
    ],
    { env: { ...process.env, LEDGER_HTTP_PORT: "8089" }, timeout: 60000 },
  );
}
function inspect(service) {
  const [state] = JSON.parse(docker(["inspect", `${project}-${service}-1`]));
  assert.equal(state.Config.Labels["com.docker.compose.project"], project);
  assert.equal(state.Config.Labels["com.docker.compose.service"], service);
  return state;
}
function sql(query) {
  return docker([
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
    query,
  ]).trim();
}
async function api(path, body) {
  const response = await fetch(`http://localhost:8089${path}`, {
    method: body ? "POST" : "GET",
    headers: body ? { "Content-Type": "application/json" } : {},
    body: body ? JSON.stringify(body) : undefined,
    signal: AbortSignal.timeout(5000),
  });
  const result = await response.json();
  assert.equal(response.status, 200, JSON.stringify(result));
  return result;
}
async function waitFor(label, predicate, seconds = 120) {
  const deadline = Date.now() + seconds * 1000;
  let nextNotice = Date.now() + 30000;
  while (!(await predicate())) {
    assert.ok(Date.now() < deadline, `${label} timed out`);
    if (Date.now() >= nextNotice) {
      console.log(
        JSON.stringify({
          waiting: label,
          deadline: new Date(deadline).toISOString(),
        }),
      );
      nextNotice = Date.now() + 30000;
    }
    await delay(3000);
  }
  console.log(JSON.stringify({ observed: label }));
}
function compare(run = "demo") {
  const output = execFileSync(
    process.execPath,
    ["service/tests/lake-reconcile.mjs", project, run],
    {
      encoding: "utf8",
      timeout: 180000,
      maxBuffer: 1024 * 1024,
    },
  );
  console.log(output.trim());
  return JSON.parse(output.trim().split("\n").at(-1));
}
function fingerprint() {
  // Stable ordered immutable source evidence; delivery bookkeeping may change.
  return sql(
    "SELECT count(*)::text || ':' || md5(string_agg(envelope::text, E'\\n' ORDER BY run_id,sequence)) FROM journal_batches",
  );
}
async function resumeNormally() {
  compose(false);
  await waitFor(
    "normal streaming",
    async () => (await api("/api/status")).cdc_source.state === "streaming",
  );
}
async function recover(expectedSource) {
  docker(["stop", "--time", "5", consumer]);
  compose(true);
  await waitFor(
    "recovery streaming",
    async () => (await api("/api/status")).cdc_source.state === "streaming",
  );
  const result = compare();
  compare("assessment-v1");
  assert.equal(
    fingerprint(),
    expectedSource,
    "recovery changed the source journal",
  );
  assert.equal((await api("/api/reconciliation")).ok, true);
  // The ordinary configuration must use the newly durable offsets successfully.
  await resumeNormally();
  compare();
  assert.equal(fingerprint(), expectedSource);
  return result;
}

for (const service of [
  "postgres",
  "api-a",
  "api-b",
  "lake",
  "clickhouse",
  "proxy",
])
  assert.equal(inspect(service).State.Running, true);
assert.ok(
  inspect("proxy").NetworkSettings.Ports["8080/tcp"]?.some(
    (binding) => binding.HostIp === "127.0.0.1" && binding.HostPort === "8089",
  ),
  "requires the isolated loopback proxy on port 8089",
);
inspect("cdc");
assert.equal(
  (await api("/api/status")).eps,
  0,
  "pause the isolated generator first",
);
const total = Number(sql("SELECT count(*) FROM journal_batches"));
assert.ok(
  total > 0 && total <= 5000,
  "requires a bounded 1–5,000-batch source",
);
if (mode === "recover") {
  try {
    console.log(JSON.stringify({ recovery: await recover(fingerprint()) }));
  } catch (error) {
    docker(["stop", "--time", "5", consumer]);
    throw error;
  }
} else {
  assert.ok(
    inspect("cdc").Config.Env.includes(
      "DEBEZIUM_SOURCE_OFFSET_MISMATCH_STRATEGY=trust_offset",
    ),
  );
  await waitFor(
    "initial streaming",
    async () => (await api("/api/status")).cdc_source.state === "streaming",
  );
  const initial = compare();
  await waitFor(
    "host ready before stopping CDC",
    async () => (await api("/api/status")).host_guard.safe,
    300,
  );
  let removedSlot = false;
  let expectedSource;
  let failure;
  try {
    docker(["stop", "--time", "5", consumer]);
    await waitFor(
      "inactive source",
      async () => (await api("/api/status")).cdc_source.state === "inactive",
    );
    // This accepted batch is absent from the old lake and older than the new slot.
    // A restart that only resumes at the new slot must therefore fail comparison.
    await waitFor(
      "host admits a bounded test command",
      async () => (await api("/api/status")).host_guard.safe,
      300,
    );
    const command = {
      id: `resnapshot-${randomUUID()}`,
      kind: "transfer",
      account: "ACC-001",
      destination: "ACC-002",
      currency: "AED",
      amount: "0.01",
      booked_day: 1,
      value_day: 1,
    };
    assert.equal((await api("/api/commands", command)).status, "accepted");
    const gapSequence = (await api("/api/status")).sequence;
    assert.match(gapSequence, /^\d+$/);
    assert.equal(BigInt(gapSequence), BigInt(initial.cutoff) + 1n);
    assert.equal(
      docker([
        "exec",
        `${project}-clickhouse-1`,
        "clickhouse-client",
        "--user",
        "ledger_owner",
        "--password",
        "local-analytics-only",
        "--query",
        `SELECT count() FROM lake.\`ledger.ledger_public_journal_batches\` WHERE run_id='demo' AND sequence=${gapSequence} SETTINGS max_execution_time=15`,
      ]).trim(),
      "0",
      "test command must be absent from the old lake",
    );
    expectedSource = fingerprint();
    assert.equal(
      sql(
        "SELECT count(*) FROM pg_replication_slots WHERE slot_name='ledger_lake' AND database=current_database() AND plugin='pgoutput' AND NOT active",
      ),
      "1",
    );
    // A command timeout does not prove that the cursor was retained.
    removedSlot = true;
    sql("SELECT pg_drop_replication_slot('ledger_lake')");
    assert.equal((await api("/api/status")).cdc_source.state, "absent");
    const since = new Date().toISOString();
    docker(["start", consumer]);
    await waitFor("normal startup refuses missing WAL position", () => {
      const logs = docker(["logs", "--since", since, consumer], {
        stdio: ["ignore", "pipe", "pipe"],
      });
      return logs.includes("but this is no longer available on the server");
    });
    assert.equal((await api("/api/status")).cdc_source.state, "absent");
    assert.equal((await api("/api/reconciliation")).ok, true);
    assert.equal(fingerprint(), expectedSource);
    console.log(
      JSON.stringify({
        initial_cutoff: initial.cutoff,
        source_after_gap: expectedSource.split(":")[0],
        command_id: command.id,
      }),
    );
  } catch (error) {
    failure = error;
  } finally {
    if (removedSlot) {
      try {
        const result = await recover(expectedSource);
        assert.equal(result.source_batches, initial.source_batches + 1);
        assert.ok(
          result.duplicate_deliveries >=
            initial.duplicate_deliveries + initial.source_batches,
          "recovery must demonstrate a fresh snapshot, not just a connected stream",
        );
        console.log(
          JSON.stringify({
            recovered: true,
            compared: result.source_batches,
            duplicate_deliveries: result.duplicate_deliveries,
          }),
        );
      } catch (error) {
        // Never advertise normal operation after incomplete recovery. Keep the
        // consumer explicitly stopped; an operator can repeat `recover` safely.
        docker(["stop", "--time", "5", consumer]);
        throw new AggregateError(
          [failure, error].filter(Boolean),
          "recovery incomplete; isolated consumer stopped, financial facts retained",
        );
      }
    } else {
      await resumeNormally();
    }
  }
  if (failure) throw failure;
}
assert.equal((await api("/api/status")).eps, 0);
