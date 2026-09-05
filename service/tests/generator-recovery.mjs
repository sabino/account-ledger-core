import assert from "node:assert/strict";
import { execFileSync } from "node:child_process";
import { setTimeout as delay } from "node:timers/promises";

// Operator-only local exercise. Never point this at a production Docker context.
function container(service) {
  const name = `ledger-lab-${service}-1`;
  const [state] = JSON.parse(
    execFileSync("docker", ["inspect", name], { encoding: "utf8" }),
  );
  assert.equal(state.Config.Labels["com.docker.compose.project"], "ledger-lab");
  assert.equal(state.Config.Labels["com.docker.compose.service"], service);
  assert.equal(state.State.Running, true);
  return {
    name,
    url: `http://${state.NetworkSettings.Networks["ledger-lab_default"].IPAddress}:8080`,
  };
}
const a = container("api-a"),
  b = container("api-b");
async function request(url, path, body) {
  const response = await fetch(url + path, {
    method: body ? "POST" : "GET",
    headers: { "Content-Type": "application/json" },
    body: body ? JSON.stringify(body) : undefined,
    signal: AbortSignal.timeout(5000),
  });
  assert.equal(response.status, 200, await response.clone().text());
  return response.json();
}
const initial = await request(b.url, "/api/status");
assert.equal(
  initial.host_guard.safe,
  true,
  "wait for the real host guard before testing",
);
let stopped = false;
try {
  await request(b.url, "/api/controls", { eps: 1 });
  const before = await request(b.url, "/api/status");
  stopped = true;
  execFileSync("docker", ["stop", "--time", "5", a.name], {
    stdio: "pipe",
    timeout: 15000,
  });
  const deadline = Date.now() + 15000;
  let after;
  do {
    await delay(500);
    after = await request(b.url, "/api/status");
    assert.equal(
      after.host_guard.safe,
      true,
      "host guard intervened; failover observation is inconclusive",
    );
  } while (
    BigInt(after.generated) < BigInt(before.generated) + 3n &&
    Date.now() < deadline
  );
  assert.equal(after.serving_instance, "replica-b");
  assert.ok(
    BigInt(after.generated) >= BigInt(before.generated) + 3n,
    "survivor did not advance three ordinals",
  );
  console.log(
    JSON.stringify({
      before: before.generated,
      after: after.generated,
      survivor: after.serving_instance,
      scope:
        "local replica stop with generation progress; lease-expiry fencing is covered separately by integration tests",
    }),
  );
} finally {
  if (stopped)
    execFileSync("docker", ["start", a.name], {
      stdio: "pipe",
      timeout: 15000,
    });
  await request(b.url, "/api/controls", { eps: initial.eps });
}
