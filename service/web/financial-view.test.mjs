import assert from "node:assert/strict";
import test from "node:test";
import { formatMinor, displayMinor } from "./financial-view.ts";

test("monetary overview preserves large amounts, BHD precision and signs", () => {
  assert.equal(
    formatMinor("9007199254740993001", "BHD"),
    "9,007,199,254,740,993.001",
  );
  assert.equal(formatMinor("10000", "BHD"), "10.000");
  assert.equal(formatMinor("-1", "AED"), "−0.01");
  assert.equal(formatMinor("0", "BHD"), "0.000");
  assert.throws(() => formatMinor("not a minor-unit amount", "AED"));
});
test("missing financial metrics are unavailable, while authoritative zero is exact", () => {
  assert.equal(displayMinor(undefined, "AED"), "Unavailable");
  assert.equal(displayMinor("0", "AED"), "0.00");
  assert.equal(displayMinor("0", "BHD"), "0.000");
});
