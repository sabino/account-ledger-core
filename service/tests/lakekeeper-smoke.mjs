import assert from "node:assert/strict";
import { execFileSync } from "node:child_process";

function address(service) {
  const container = JSON.parse(
    execFileSync("docker", ["inspect", `ledger-catalog-probe-${service}-1`], {
      encoding: "utf8",
    }),
  )[0];
  assert.equal(
    container.Config.Labels["com.docker.compose.project"],
    "ledger-catalog-probe",
  );
  assert.equal(container.State.Running, true);
  return container.NetworkSettings.Networks["ledger-catalog-probe_default"]
    .IPAddress;
}
const catalog = `http://${address("catalog")}:8181`;
const storage = `http://${address("lake")}:8333`;
async function request(path, body, statuses = [200, 201, 204]) {
  const response = await fetch(catalog + path, {
    method: body ? "POST" : "GET",
    headers: { "Content-Type": "application/json" },
    body: body ? JSON.stringify(body) : undefined,
    signal: AbortSignal.timeout(15000),
  });
  const text = await response.text();
  assert.ok(
    statuses.includes(response.status),
    `${path}: ${response.status} ${text}`,
  );
  return text ? JSON.parse(text) : null;
}
// Development catalog only: Apache-licensed service with no public endpoint.
const bootstrap = await request(
  "/management/v1/bootstrap",
  { "accept-terms-of-use": true },
  [200, 204, 400],
);
if (bootstrap?.error)
  assert.equal(bootstrap.error.type, "CatalogAlreadyBootstrapped");
const bucket = execFileSync(
  "curl",
  [
    "--silent",
    "--show-error",
    "--max-time",
    "10",
    "--aws-sigv4",
    "aws:amz:us-east-1:s3",
    "--user",
    "ledger-local:local-lake-only",
    "-X",
    "PUT",
    "-o",
    "/dev/null",
    "-w",
    "%{http_code}",
    `${storage}/catalog-data`,
  ],
  { encoding: "utf8" },
);
assert.ok(["200", "409"].includes(bucket), bucket);
const listed = await request("/management/v1/warehouse");
let warehouse = listed.warehouses?.find((w) => w.name === "ledger-probe");
if (!warehouse) {
  warehouse = await request("/management/v1/warehouse", {
    "warehouse-name": "ledger-probe",
    "project-id": "00000000-0000-0000-0000-000000000000",
    "storage-profile": {
      type: "s3",
      bucket: "catalog-data",
      "key-prefix": "ledger",
      endpoint: "http://lake:8333",
      region: "us-east-1",
      "path-style-access": true,
      flavor: "s3-compat",
      "sts-enabled": false,
    },
    "storage-credential": {
      type: "s3",
      "credential-type": "access-key",
      "access-key-id": "ledger-local",
      "secret-access-key": "local-lake-only",
    },
  });
}
const config = await request("/catalog/v1/config?warehouse=ledger-probe");
const prefix = config.overrides?.prefix || config.defaults?.prefix;
assert.ok(prefix, "warehouse prefix missing");
const base = `/catalog/v1/${prefix}`;
await request(`${base}/namespaces`, { namespace: ["probe"] }, [200, 201, 409]);
await request(
  `${base}/namespaces/probe/tables`,
  {
    name: "batches",
    schema: {
      type: "struct",
      "schema-id": 0,
      fields: [
        { id: 1, name: "sequence", type: "long", required: true },
        { id: 2, name: "envelope", type: "string", required: true },
      ],
    },
    properties: { "format-version": "2" },
  },
  [200, 201, 409],
);
const table = await request(`${base}/namespaces/probe/tables/batches`);
assert.ok(table["metadata-location"]?.startsWith("s3://catalog-data/ledger/"));
assert.ok(table.metadata["table-uuid"]);
assert.equal(table.metadata.schemas[0].fields[0].type, "long");
console.log(
  JSON.stringify(
    {
      version: "0.13.3",
      warehouse_id: warehouse["warehouse-id"],
      table_uuid: table.metadata["table-uuid"],
      metadata_location: table["metadata-location"],
      scope:
        "catalog bootstrap, S3 validation, namespace/table creation and read; no CDC/data-row compatibility claim",
    },
    null,
    2,
  ),
);
