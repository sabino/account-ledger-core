import assert from "node:assert/strict";
import test from "node:test";
import { sourceChunk, completePrefix, chunkSize } from "./lake-chunks.mjs";
import { matchedBatches } from "./lake-comparison.mjs";
const row = (sequence) => ({
  sequence: String(sequence),
  envelope: JSON.stringify({ amount: "100", id: String(sequence) }),
});

test("chunks retain exact large identities and exclude later commits", () => {
  const { expected, through } = sourceChunk(
    [row("9007199254740993")],
    "9007199254740992",
    "9007199254740993",
  );
  assert.equal(through, "9007199254740993");
  assert.equal(matchedBatches(expected, [row(through), row(through)]), 1);
  assert.throws(() => sourceChunk([row("9007199254740994")], "0", through));
});
test("empty, repeated, reordered and oversized chunks fail", () => {
  for (const rows of [
    [],
    [row(1), row(1)],
    [row(2), row(1)],
    Array.from({ length: chunkSize + 1 }, (_, i) => row(i + 1)),
  ])
    assert.throws(() => sourceChunk(rows, "0", "9999"));
  assert.throws(() => sourceChunk([row(1)], "1", "2"));
});
test("more than ten thousand batches compare in bounded chunks with redelivery", () => {
  let count = 0,
    through = "0";
  const total = 10017;
  while (count < total) {
    const rows = Array.from(
      { length: Math.min(chunkSize, total - count) },
      (_, i) => row(count + i + 1),
    );
    const chunk = sourceChunk(rows, through, String(total));
    assert.equal(
      matchedBatches(chunk.expected, [...rows, rows[0]]),
      rows.length,
    );
    count += rows.length;
    through = chunk.through;
  }
  completePrefix(count, total, through, String(total));
  assert.throws(() => completePrefix(count - 1, total, through, String(total)));
  assert.throws(() => completePrefix(count, total, "10016", String(total)));
});
