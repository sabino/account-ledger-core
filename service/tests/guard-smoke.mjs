import assert from "node:assert/strict";
import { randomUUID } from "node:crypto";

// Run with the watcher stopped. An expired lease must affect both replicas.
const base = process.env.LEDGER_URL || "http://localhost:8088";
const request = async (path, body) => {
  const response = await fetch(base + path, {
    method: body ? "POST" : "GET",
    headers: body ? { "Content-Type": "application/json" } : {},
    body: body ? JSON.stringify(body) : undefined,
    signal: AbortSignal.timeout(5000),
  });
  return { status: response.status, instance: response.headers.get("x-ledger-instance"), body: await response.json() };
};
const state = await request("/api/status");
assert.equal(state.body.host_guard.safe, false);
const before = state.body.sequence;
const replicas = new Set();
for (let i = 0; i < 6; i++) {
  const result = await request("/api/commands", {
    id: randomUUID(), kind: "transfer", account: "ACC-001", destination: "ACC-002",
    currency: "AED", amount: "0.01", booked_day: 1, value_day: 1,
  });
  assert.equal(result.status, 429);
  replicas.add(result.instance);
}
assert.equal(replicas.size, 2, "must exercise both replicas");
assert.equal((await request("/api/controls", { eps: 20 })).status, 429);
assert.equal((await request("/api/chaos/outbox", {})).status, 429);
assert.equal((await request("/api/controls", { eps: 0 })).status, 200);
assert.equal((await request("/api/status")).body.sequence, before);
console.log("Expired host lease blocks both replicas and chaos; pause remains available.");
