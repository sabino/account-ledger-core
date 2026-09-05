import assert from "node:assert/strict";
import { normalize } from "./lake-comparison.mjs";

export const chunkSize = 1000;
export function sourceChunk(rows, after, cutoff) {
  assert.match(after, /^\d+$/);
  assert.match(cutoff, /^\d+$/);
  assert.ok(
    rows.length > 0 && rows.length <= chunkSize,
    "missing or oversized source chunk",
  );
  let previous = BigInt(after);
  const expected = new Map();
  for (const row of rows) {
    assert.match(row.sequence, /^\d+$/);
    const sequence = BigInt(row.sequence);
    assert.ok(
      sequence > previous && sequence <= BigInt(cutoff),
      "source chunk is unordered or beyond its cutoff",
    );
    expected.set(row.sequence, normalize(row.envelope));
    previous = sequence;
  }
  return { expected, through: rows.at(-1).sequence };
}

export function completePrefix(observed, captured, through, cutoff) {
  assert.equal(
    observed,
    captured,
    "source prefix changed or was truncated during comparison",
  );
  assert.equal(
    through,
    cutoff,
    "comparison stopped before the captured cutoff",
  );
}
