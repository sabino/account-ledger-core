import assert from "node:assert/strict";
import { execFileSync } from "node:child_process";
import { currentSnapshot, parseMetadata } from "./lake-metadata.mjs";

// Inventory only: no snapshot expiration, compaction or object deletion.
const project = process.argv[2] || "ledger-lab";
assert.ok(["ledger-lab", "ledger-budget"].includes(project));
const [container] = JSON.parse(
  execFileSync("docker", ["inspect", `${project}-lake-1`], {
    encoding: "utf8",
    timeout: 10000,
  }),
);
assert.equal(container.Config.Labels["com.docker.compose.project"], project);
assert.equal(container.State.Running, true);
const origin = `http://${container.NetworkSettings.Networks[`${project}_default`].IPAddress}:8181`;
const response = await fetch(origin + "/v1/oauth/tokens", {
  method: "POST",
  body: new URLSearchParams({
    grant_type: "client_credentials",
    client_id: "ledger-local",
    client_secret: "local-lake-only",
  }),
  signal: AbortSignal.timeout(10000),
});
assert.equal(response.status, 200);
const token = (await response.json()).access_token;
assert.ok(token);
async function read(path) {
  const response = await fetch(origin + path, {
    headers: { Authorization: `Bearer ${token}` },
    signal: AbortSignal.timeout(10000),
  });
  assert.equal(response.status, 200, `catalog read failed at ${path}`);
  const chunks = [];
  let bytes = 0;
  for await (const chunk of response.body) {
    bytes += chunk.length;
    assert.ok(
      bytes <= 4 * 1024 * 1024,
      "metadata exceeds this diagnostic's bound",
    );
    chunks.push(chunk);
  }
  return parseMetadata(Buffer.concat(chunks).toString("utf8"));
}
const config = await read("/v1/config?warehouse=s3://ledger-lake");
const prefix = config.overrides?.prefix ?? config.defaults?.prefix;
const base = prefix ? `/v1/${prefix}` : "/v1";
const listed = await read(`${base}/namespaces/ledger/tables`);
assert.ok(
  !listed["next-page-token"],
  "pagination requires a separately bounded inventory",
);
assert.ok(listed.identifiers.length <= 10, "unexpected number of tables");
for (const identifier of listed.identifiers) {
  assert.deepEqual(identifier.namespace, ["ledger"]);
  const table = await read(
    `${base}/namespaces/ledger/tables/${encodeURIComponent(identifier.name)}`,
  );
  const metadata = table.metadata;
  const snapshots = metadata.snapshots || [];
  const current = currentSnapshot(metadata);
  console.log(
    JSON.stringify({
      project,
      table: identifier.name,
      observed_at: new Date().toISOString(),
      retained_snapshots: snapshots.length,
      metadata_log_entries: (metadata["metadata-log"] || []).length,
      oldest_snapshot_at: snapshots.length
        ? new Date(
            Math.min(...snapshots.map((s) => s["timestamp-ms"])),
          ).toISOString()
        : null,
      current_records: current?.summary?.["total-records"] ?? null,
      current_data_files: current?.summary?.["total-data-files"] ?? null,
      current_data_bytes: current?.summary?.["total-files-size"] ?? null,
      scope:
        "catalog metadata inventory; current files exclude historical/orphan storage and these are not filesystem quota measurements",
    }),
  );
}
