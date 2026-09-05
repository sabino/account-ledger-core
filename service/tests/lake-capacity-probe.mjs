// Writes only to the isolated ledger-lake-probe project; never the live lake.
// Retains evidence on completion. Re-running uses new keys and may hit the
// already-full allocation. No deletion or automatic reset is performed.
import assert from "node:assert/strict";
import { execFileSync, spawnSync } from "node:child_process";
import { randomBytes, randomUUID, createHash } from "node:crypto";

const inspect = JSON.parse(
  execFileSync("docker", ["inspect", "ledger-lake-probe-lake-1"], {
    encoding: "utf8",
  }),
)[0];
assert.equal(
  inspect.Config.Labels["com.docker.compose.project"],
  "ledger-lake-probe",
);
assert.equal(inspect.State.Running, true);
assert.ok(inspect.Args.includes("-volume.max=8"));
const network = inspect.NetworkSettings.Networks["ledger-lake-probe_default"];
assert.ok(network?.IPAddress);
const origin = `http://${network.IPAddress}`;
const credentials = "ledger-local:local-lake-only";
const id = randomUUID();
const payload = randomBytes(3 * 1024 * 1024);
const checksum = createHash("sha256").update(payload).digest("hex");
const curl = (args, input) =>
  execFileSync(
    "curl",
    ["--silent", "--show-error", "--max-time", "10", ...args],
    { input, maxBuffer: 5 * 1024 * 1024 },
  );
const auth = ["--aws-sigv4", "aws:amz:us-east-1:s3", "--user", credentials];
const started = new Date().toISOString();

if (process.argv[2] === "--restart-existing") {
  const probe = process.argv[3];
  assert.ok(probe && probe.length === 36 && !probe.includes("/"));
  const object = `${origin}:8333/capacity-probe/${encodeURIComponent(probe)}/0`;
  const before = createHash("sha256")
    .update(curl([...auth, "--fail", object]))
    .digest("hex");
  execFileSync("docker", ["restart", "ledger-lake-probe-lake-1"], {
    timeout: 30000,
  });
  let ready = false;
  for (let i = 0; i < 30; i++) {
    try {
      const response = await fetch(`${origin}:8333/status`, {
        signal: AbortSignal.timeout(1000),
      });
      if (response.ok) {
        ready = true;
        break;
      }
    } catch {}
    await new Promise((resolve) => setTimeout(resolve, 1000));
  }
  assert.ok(ready, "probe did not recover after restart");
  const after = createHash("sha256")
    .update(curl([...auth, "--fail", object]))
    .digest("hex");
  assert.equal(after, before);
  console.log(
    JSON.stringify({
      probe,
      restart_checksum_matches: true,
      bytes: payload.length,
      scope:
        "existing S3 object after isolated container restart; not host-loss recovery",
    }),
  );
  process.exit(0);
}

const token = JSON.parse(
  curl([
    "-X",
    "POST",
    `${origin}:8181/v1/oauth/tokens`,
    "--data-urlencode",
    "grant_type=client_credentials",
    "--data-urlencode",
    "client_id=ledger-local",
    "--data-urlencode",
    "client_secret=local-lake-only",
  ]),
);
assert.ok(token.access_token, "catalog authentication failed");
const config = JSON.parse(
  curl([
    "--fail",
    "-H",
    `Authorization: Bearer ${token.access_token}`,
    `${origin}:8181/v1/config?warehouse=s3://ledger-lake`,
  ]),
);
assert.ok(config.defaults || config.overrides, "catalog config unavailable");
// A table bucket restricts arbitrary object paths. Fill a separate regular
// bucket in this same isolated volume server, not the catalog's table files.
const bucketStatus = curl([
  ...auth,
  "-X",
  "PUT",
  "-o",
  "/dev/null",
  "-w",
  "%{http_code}",
  `${origin}:8333/capacity-probe`,
]).toString();
assert.ok(
  ["200", "409"].includes(bucketStatus),
  `bucket setup: ${bucketStatus}`,
);
const put = (key) =>
  curl(
    [
      ...auth,
      "-X",
      "PUT",
      "-H",
      "Content-Type: application/octet-stream",
      "--data-binary",
      "@-",
      "-w",
      "\n%{http_code}",
      `${origin}:8333/capacity-probe/${id}/${key}`,
    ],
    payload,
  ).toString();
let written = 0;
let refusal;
for (let i = 0; i < 120; i++) {
  const response = put(String(i));
  const status = response.slice(-3);
  if (status !== "200") {
    refusal = { status, response: response.slice(0, -4) };
    break;
  }
  written++;
}
assert.ok(
  written > 0,
  "probe needs a fresh allocation with room for its first object",
);
assert.ok(refusal, "120 writes did not reach the configured allocation limit");
assert.ok(
  Number(refusal.status) >= 500,
  `not a storage refusal: ${refusal.response}`,
);
const logs = spawnSync(
  "docker",
  ["logs", "--since", started, "ledger-lake-probe-lake-1"],
  { encoding: "utf8", maxBuffer: 1024 * 1024 },
);
assert.equal(logs.status, 0);
assert.ok(
  (logs.stdout + logs.stderr).includes(
    "No writable volumes and no free volumes left",
  ),
  "HTTP 500 without verified allocation exhaustion",
);
const read = curl([...auth, "--fail", `${origin}:8333/capacity-probe/${id}/0`]);
assert.equal(createHash("sha256").update(read).digest("hex"), checksum);
console.log(
  JSON.stringify(
    {
      project: "ledger-lake-probe",
      probe: id,
      successful_objects: written,
      acknowledged_bytes: written * payload.length,
      refusal,
      existing_object_checksum_matches: true,
      catalog_authenticated: true,
      scope:
        "8 x 32 MiB allocation ceiling, not a filesystem quota; index/metadata/overshoot are additional",
    },
    null,
    2,
  ),
);
