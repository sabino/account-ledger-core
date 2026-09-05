import assert from "node:assert/strict";
import { randomUUID } from "node:crypto";

// Run with the watcher stopped. An expired lease must affect both replicas.
const base = process.env.LEDGER_URL || "http://localhost:8088";
const targets = (process.env.LEDGER_REPLICA_URLS || "").split(",").filter(Boolean);
assert.equal(new Set(targets).size, 2, "provide two distinct direct replica URLs through the guard-runner Compose service");
const request = async (path, body, target = base) => {
  const response = await fetch(target + path, {
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
for (const target of [...targets, base]) {
  const observed = await request("/api/status", undefined, target);
  assert.equal(observed.status, 200);
  assert.equal(observed.body.host_guard.safe, false);
  assert.equal(observed.body.sequence, before);
  const result = await request("/api/commands", {
    id: randomUUID(), kind: "transfer", account: "ACC-001", destination: "ACC-002",
    currency: "AED", amount: "0.01", booked_day: 1, value_day: 1,
  }, target);
  assert.equal(result.status, 429, JSON.stringify(result));
  assert.ok(result.instance, "response must identify the serving instance");
  replicas.add(result.instance);
  assert.equal((await request("/api/controls", { eps: 20 }, target)).status, 429);
  assert.equal((await request("/api/chaos/outbox", {}, target)).status, 429);
  assert.equal((await request("/api/controls", { eps: 0 }, target)).status, 200);
}
assert.equal(replicas.size, 2, "must exercise both replicas");
assert.equal((await request("/api/controls", { eps: 20 })).status, 429);
assert.equal((await request("/api/chaos/outbox", {})).status, 429);
assert.equal((await request("/api/controls", { eps: 0 })).status, 200);
assert.equal((await request("/api/status")).body.sequence, before);
console.log("Expired host lease blocks both direct replicas and the proxy; rate increases and chaos are refused, pause remains available.", [...replicas]);
