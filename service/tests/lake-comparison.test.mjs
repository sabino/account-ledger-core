import assert from "node:assert/strict";
import test from "node:test";
import { matchedBatches, normalize } from "./lake-comparison.mjs";

const row = {
  sequence: "10",
  envelope: '{"units":"9007199254740993","status":"accepted"}',
};
const expected = new Map([[row.sequence, normalize(row.envelope)]]);
test("identical redelivery counts once without rounding money", () => {
  assert.equal(matchedBatches(expected, [row, row]), 1);
  assert.ok(normalize(row.envelope).includes("9007199254740993"));
});
test("JSON key ordering is not an envelope conflict", () => {
  assert.equal(
    matchedBatches(expected, [
      { ...row, envelope: '{"status":"accepted","units":"9007199254740993"}' },
    ]),
    1,
  );
});
test("missing batches do not imply agreement", () =>
  assert.equal(matchedBatches(expected, []), 0));
test("conflicting duplicates fail rather than choosing an arbitrary value", () => {
  assert.throws(
    () =>
      matchedBatches(expected, [
        row,
        { ...row, envelope: '{"units":"1","status":"accepted"}' },
      ]),
    /conflicting envelope/,
  );
});
test("unknown identities and unsafe numeric fields fail closed", () => {
  assert.throws(
    () => matchedBatches(expected, [{ ...row, sequence: "11" }]),
    /unexpected batch/,
  );
  assert.throws(
    () => normalize('{"units":9007199254740993}'),
    /unsafe JSON number/,
  );
});
