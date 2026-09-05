import assert from "node:assert/strict";
import { execFileSync } from "node:child_process";

// Operator-only local exercise. No public container-control endpoint.
const name = "ledger-lab-cdc-1";
function docker(...args) {
  return execFileSync("docker", args, {
    encoding: "utf8",
    timeout: 20000,
    maxBuffer: 1024 * 1024,
  });
}
const [container] = JSON.parse(docker("inspect", name));
assert.equal(
  container.Config.Labels["com.docker.compose.project"],
  "ledger-lab",
);
assert.equal(container.Config.Labels["com.docker.compose.service"], "cdc");
assert.equal(container.State.Running, true);

async function status() {
  const response = await fetch("http://localhost:8088/api/status", {
    signal: AbortSignal.timeout(3000),
  });
  assert.equal(response.status, 200);
  const value = (await response.json()).cdc_source;
  assert.ok(value, "rebuild the API before exercising source status");
  if (value.retained_wal_bytes !== null) {
    assert.equal(typeof value.retained_wal_bytes, "string");
    assert.ok(BigInt(value.retained_wal_bytes) >= 0n);
  }
  return value;
}
async function waitFor(expected, seconds) {
  const deadline = Date.now() + seconds * 1000;
  let observed;
  do {
    observed = await status();
    if (observed.state === expected) return observed;
    await new Promise((resolve) => setTimeout(resolve, 500));
  } while (Date.now() < deadline);
  assert.fail(
    `expected ${expected}; last source state ${JSON.stringify(observed)}`,
  );
}

await waitFor("streaming", 15);
let restore = false;
let inactive;
try {
  // Set before stop: even a command timeout must attempt restoration.
  restore = true;
  docker("stop", "--time", "5", name);
  inactive = await waitFor("inactive", 15);
  assert.equal(inactive.active, false);
  assert.equal(
    (
      await fetch("http://localhost:8088/readyz", {
        signal: AbortSignal.timeout(3000),
      })
    ).status,
    200,
  );
} finally {
  if (restore) docker("start", name);
}
const connected = await waitFor("streaming", 60);
console.log(
  JSON.stringify({
    observed: [inactive.state, connected.state],
    retained_wal_while_stopped: inactive.retained_wal_bytes,
    scope:
      "local consumer stop/start and API source-state visibility; not slot invalidation, lake catch-up or financial-write verification",
  }),
);
