import assert from "node:assert/strict";
import { randomUUID } from "node:crypto";

const base = process.env.LEDGER_URL || "http://localhost:8088";
async function request(path, body) {
  const response = await fetch(base + path, {
    method: body ? "POST" : "GET",
    headers: body ? { "Content-Type": "application/json" } : {},
    body: body ? JSON.stringify(body) : undefined,
    signal: AbortSignal.timeout(10000),
  });
  const result = await response.json();
  return { status: response.status, result };
}

const initial = await request("/api/status");
assert.equal(initial.status, 200);
assert.equal((await request("/api/controls", { eps: 0 })).status, 200);
try {
  // Readiness is not financial admission. Builds/concurrency tests can leave
  // the independent host watcher temporarily unsafe; never disable it here.
  const deadline = Date.now() + 60000;
  let state;
  while (true) {
    const observed = await request("/api/status");
    assert.equal(observed.status, 200);
    state = observed.result;
    if (state.guard_fresh && !state.guard_reason && !state.pause_reason && state.host_guard?.safe) break;
    if (Date.now() >= deadline) throw new Error("Financial admission did not become safe within 60 seconds");
    console.log("Waiting for financial admission", JSON.stringify({
      guard_fresh: state.guard_fresh, guard_reason: state.guard_reason,
      pause_reason: state.pause_reason, host_guard: state.host_guard,
    }));
    await new Promise(resolve => setTimeout(resolve, 2000));
  }
  const command = {
    id: randomUUID(), kind: "transfer", account: "ACC-001", destination: "ACC-002",
    currency: "AED", amount: "0.01", booked_day: 1, value_day: 1,
  };
  const [first, retry] = await Promise.all([
    request("/api/commands", command), request("/api/commands", command),
  ]);
  assert.equal(first.status, 200, JSON.stringify(first));
  assert.equal(retry.status, 200, JSON.stringify(retry));
  assert.equal(first.result.status, "accepted");
  assert.deepEqual(first.result, retry.result);
  assert.equal((await request("/api/commands", { ...command, amount: "0.02" })).status, 409);
  assert.equal((await request("/api/reconciliation")).result.ok, true);
  assert.equal((await request("/api/chaos/outbox", {})).status, 200);
  const duringPause = await request("/api/commands", { ...command, id: randomUUID() });
  assert.equal(duringPause.status, 200, JSON.stringify(duringPause));
  assert.equal(duringPause.result.status, "accepted");
  assert.ok((await request("/api/status")).result.pending_deliveries > 0);
  await new Promise(resolve => setTimeout(resolve, 17000));
  assert.equal((await request("/api/status")).result.pending_deliveries, 0);
  console.log("HTTP smoke passed: idempotency, conflict, balanced transfer, bounded pause and recovery.");
} catch (error) {
  try {
    console.error("HTTP smoke failure state", JSON.stringify((await request("/api/status")).result));
  } catch (diagnosticError) {
    console.error("Unable to read failure state", diagnosticError.message);
  }
  throw error;
} finally {
  const restored = await request("/api/controls", { eps: initial.result.eps });
  if (restored.status !== 200)
    console.error("Original generator rate could not be restored; safety guard remains authoritative", JSON.stringify(restored));
}
