import assert from "node:assert/strict";
import test from "node:test";
import { currentSnapshot, parseMetadata } from "./lake-metadata.mjs";

test("adjacent 64-bit snapshot IDs remain distinct", () => {
  const metadata = parseMetadata(`{
    "current-snapshot-id": 9223372036854775806,
    "snapshots": [
      {"snapshot-id": 9223372036854775805, "summary": {"total-records": "10"}},
      {"snapshot-id": 9223372036854775806, "summary": {"total-records": "20"}}
    ]
  }`);
  assert.equal(currentSnapshot(metadata).summary["total-records"], "20");
  assert.notEqual(
    metadata.snapshots[0]["snapshot-id"],
    metadata.snapshots[1]["snapshot-id"],
  );
});

test("safe timestamps remain numbers and empty tables have no current snapshot", () => {
  assert.equal(
    parseMetadata('{"timestamp-ms":1788569000000}')["timestamp-ms"],
    1788569000000,
  );
  assert.equal(currentSnapshot({ "current-snapshot-id": -1 }), null);
  assert.equal(currentSnapshot({}), null);
});

test("missing and duplicate current snapshots fail instead of inventing totals", () => {
  assert.throws(() =>
    currentSnapshot({ "current-snapshot-id": 3, snapshots: [] }),
  );
  assert.throws(() =>
    currentSnapshot({
      "current-snapshot-id": 3,
      snapshots: [{ "snapshot-id": 3 }, { "snapshot-id": 3 }],
    }),
  );
});
