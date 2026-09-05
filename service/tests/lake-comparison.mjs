import assert from "node:assert/strict";

function canonical(value) {
  if (typeof value === "number")
    assert.ok(Number.isSafeInteger(value), "unsafe JSON number");
  if (Array.isArray(value)) return value.map(canonical);
  if (value && typeof value === "object")
    return Object.fromEntries(
      Object.keys(value)
        .sort()
        .map((key) => [key, canonical(value[key])]),
    );
  return value;
}
export const normalize = (text) => JSON.stringify(canonical(JSON.parse(text)));

export function matchedBatches(expected, rows) {
  const seen = new Set();
  for (const row of rows) {
    assert.ok(expected.has(row.sequence), `unexpected batch ${row.sequence}`);
    assert.equal(
      normalize(row.envelope),
      expected.get(row.sequence),
      `conflicting envelope at ${row.sequence}`,
    );
    seen.add(row.sequence);
  }
  return seen.size;
}
