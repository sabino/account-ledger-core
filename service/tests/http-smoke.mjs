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

assert.equal((await request("/api/status")).status, 200);
assert.equal((await request("/api/controls", { eps: 0 })).status, 200);
try {
  const command = {
    id: randomUUID(), kind: "transfer", account: "ACC-001", destination: "ACC-002",
    currency: "AED", amount: "0.01", booked_day: 1, value_day: 1,
  };
  const [first, retry] = await Promise.all([
    request("/api/commands", command), request("/api/commands", command),
  ]);
  assert.equal(first.status, 200);
  assert.equal(retry.status, 200);
  assert.equal(first.result.status, "accepted");
  assert.deepEqual(first.result, retry.result);
  assert.equal((await request("/api/commands", { ...command, amount: "0.02" })).status, 409);
  assert.equal((await request("/api/reconciliation")).result.ok, true);
  assert.equal((await request("/api/chaos/outbox", {})).status, 200);
  await request("/api/commands", { ...command, id: randomUUID() });
  assert.ok((await request("/api/status")).result.pending_deliveries > 0);
  await new Promise(resolve => setTimeout(resolve, 17000));
  assert.equal((await request("/api/status")).result.pending_deliveries, 0);
  console.log("HTTP smoke passed: idempotency, conflict, balanced transfer, bounded pause and recovery.");
} finally {
  await request("/api/controls", { eps: 1 });
}
