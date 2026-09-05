import assert from "node:assert/strict";
import { execFileSync } from "node:child_process";
import { setTimeout as delay } from "node:timers/promises";

// Operator-only local catalog outage; no public chaos endpoint or Docker socket
// is added to the application. Never run with a production Docker context.
const docker = (args) =>
  execFileSync("docker", args, {
    encoding: "utf8",
    timeout: 20000,
    maxBuffer: 1024 * 1024,
  });
function inspect(service) {
  const [c] = JSON.parse(docker(["inspect", `ledger-lab-${service}-1`]));
  assert.equal(c.Config.Labels["com.docker.compose.project"], "ledger-lab");
  assert.equal(c.Config.Labels["com.docker.compose.service"], service);
  return c;
}
const before = inspect("cdc");
assert.equal(before.State.Running, true);
assert.equal(before.HostConfig.RestartPolicy.Name, "unless-stopped");
assert.equal(inspect("lake").State.Running, true);
let restore = false;
try {
  restore = true;
  docker(["stop", "--time", "5", "ledger-lab-lake-1"]);
  const deadline = Date.now() + 90000;
  let current;
  do {
    await delay(5000);
    current = inspect("cdc");
    console.log(
      JSON.stringify({
        phase: "catalog unavailable",
        cdc_status: current.State.Status,
        restart_count: current.RestartCount,
        prior_restarts: before.RestartCount,
      }),
    );
    assert.ok(
      Date.now() < deadline,
      "CDC did not exercise a restart; outage result is inconclusive",
    );
  } while (current.RestartCount <= before.RestartCount);
} finally {
  if (restore) docker(["start", "ledger-lab-lake-1"]);
}
const deadline = Date.now() + 60000;
while (inspect("lake").State.Health?.Status !== "healthy") {
  assert.ok(
    Date.now() < deadline,
    "catalog did not become healthy after restoration",
  );
  await delay(2000);
}
execFileSync(
  process.execPath,
  ["service/tests/lake-reconcile.mjs", "ledger-lab", "demo"],
  {
    stdio: "inherit",
    timeout: 160000,
  },
);
console.log(
  JSON.stringify({
    scope:
      "local catalog outage, supervised CDC restart and complete-envelope catch-up",
    before_restarts: before.RestartCount,
    after_restarts: inspect("cdc").RestartCount,
    excludes:
      "lost replication slot, host loss, simultaneous durable-store loss and production capacity",
  }),
);
