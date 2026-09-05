import assert from "node:assert/strict";
import { execFileSync } from "node:child_process";

// Uses only the disposable ledger-budget project; never the interactive stack.
const docker = (args) =>
  execFileSync("docker", args, { encoding: "utf8", timeout: 15000 });
const names = docker([
  "ps",
  "--filter",
  "label=com.docker.compose.project=ledger-budget",
  "--format",
  "{{.Names}}",
])
  .trim()
  .split("\n");
assert.equal(
  names.length,
  8,
  "all eight long-running budget services must be running",
);
const base = "http://localhost:8089";
async function api(path, body) {
  const r = await fetch(base + path, {
    method: body ? "POST" : "GET",
    headers: body ? { "Content-Type": "application/json" } : {},
    body: body ? JSON.stringify(body) : undefined,
    signal: AbortSignal.timeout(5000),
  });
  const value = await r.json();
  assert.equal(r.status, 200, JSON.stringify(value));
  return value;
}
function bytes(text) {
  const units = { GiB: 2 ** 30, MiB: 2 ** 20, KiB: 2 ** 10, B: 1 };
  for (const [unit, scale] of Object.entries(units)) {
    if (text.endsWith(unit)) return Math.round(parseFloat(text) * scale);
  }
  throw new Error("unknown Docker memory unit: " + text);
}
function fixtureCount() {
  return docker([
    "exec",
    "ledger-budget-clickhouse-1",
    "clickhouse-client",
    "--user",
    "ledger_owner",
    "--password",
    "local-analytics-only",
    "--query",
    "SELECT uniqExact((run_id,sequence)) FROM lake.`ledger.ledger_public_journal_batches` WHERE run_id='assessment-v1'",
  ]).trim();
}
// The container being up is not evidence that its initial snapshot is readable.
const deadline = Date.now() + 120000;
while (fixtureCount() !== "12") {
  assert.ok(
    Date.now() < deadline,
    "fixture did not reach the lake within two minutes",
  );
  await new Promise((resolve) => setTimeout(resolve, 5000));
}
const initial = await api("/api/status");
const peak = {};
let aggregatePeak = 0;
try {
  await api("/api/controls", { eps: 20 });
  for (let sample = 0; sample < 12; sample++) {
    await new Promise((resolve) => setTimeout(resolve, 5000));
    const state = await api("/api/status");
    const stats = docker([
      "stats",
      "--no-stream",
      "--format",
      "{{json .}}",
      ...names,
    ])
      .trim()
      .split("\n")
      .map(JSON.parse);
    for (const row of stats)
      peak[row.Name] = Math.max(
        peak[row.Name] || 0,
        bytes(row.MemUsage.split(" / ")[0]),
      );
    aggregatePeak = Math.max(
      aggregatePeak,
      stats.reduce((sum, row) => sum + bytes(row.MemUsage.split(" / ")[0]), 0),
    );
    console.log(
      JSON.stringify({
        sample,
        sequence: state.sequence,
        eps: state.eps,
        host_safe: state.host_guard.safe,
        pending: state.pending_deliveries,
      }),
    );
    // Real catalog + Parquet read, bounded by the ClickHouse profile.
    assert.equal(fixtureCount(), "12");
  }
  const final = await api("/api/status");
  const state = JSON.parse(docker(["inspect", ...names]));
  for (const container of state) {
    assert.equal(container.State.Running, true);
    assert.equal(container.State.OOMKilled, false);
    assert.equal(container.RestartCount, 0);
    assert.equal(
      container.HostConfig.MemorySwap,
      container.HostConfig.Memory,
      "no container swap allowance",
    );
  }
  assert.equal((await api("/api/reconciliation")).ok, true);
  console.log(
    JSON.stringify({
      committed_batches: String(
        BigInt(final.sequence) - BigInt(initial.sequence),
      ),
      sampled_peak_bytes: peak,
      largest_sampled_aggregate_bytes: aggregatePeak,
      configured_memory_bytes: state.reduce(
        (sum, c) => sum + c.HostConfig.Memory,
        0,
      ),
      note: "sampled memory, not an exact peak or sustained-capacity proof",
    }),
  );
} finally {
  await api("/api/controls", { eps: 0 });
}
