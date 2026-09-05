import assert from "node:assert/strict";

// Iceberg IDs can exceed JavaScript's exact integer range. Never compare rounded IDs.
export function parseMetadata(text) {
  return JSON.parse(text, (_key, value, context) => {
    if (typeof value !== "number" || Number.isSafeInteger(value)) return value;
    assert.ok(
      context?.source,
      "use a Node version with JSON source-text access",
    );
    return context.source;
  });
}

export function currentSnapshot(metadata) {
  const id = metadata["current-snapshot-id"];
  if (id === undefined || String(id) === "-1") return null;
  const matches = (metadata.snapshots || []).filter(
    (snapshot) => String(snapshot["snapshot-id"]) === String(id),
  );
  assert.equal(matches.length, 1, "current snapshot must resolve uniquely");
  return matches[0];
}
