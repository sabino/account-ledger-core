import assert from "node:assert/strict";

// Read-only: no commands, rate changes or fake balances are submitted.
const origin = process.env.LEDGER_URL || "http://localhost:8088";
const response = await fetch(`${origin}/api/financial`, {
  signal: AbortSignal.timeout(5000),
});
assert.equal(response.status, 200);
const data = await response.json();
assert.equal(data.runId, "demo");
assert.equal(data.timeZone, "UTC");
assert.ok(Number.isFinite(Date.parse(data.asOf)));
assert.equal(data.daily.length, 7);
const amount = (value) => {
  assert.equal(typeof value, "string");
  assert.match(value, /^-?\d+$/);
  return BigInt(value);
};
for (const currency of ["AED", "BHD"]) {
  const summary = data.byCurrency[currency];
  for (const period of [summary.today, summary.run]) {
    assert.equal(
      amount(period.processedMinor),
      amount(period.transfersMinor) +
        amount(period.capturesMinor) +
        amount(period.purchasesGrossMinor),
    );
    assert.ok(Number.isSafeInteger(period.operations));
    assert.ok(period.operations >= 0);
  }
  const balances = summary.balances;
  assert.equal(
    amount(balances.availableMinor),
    amount(balances.postedMinor) - amount(balances.heldMinor),
  );
  assert.ok(amount(summary.run.processedMinor) >= amount(summary.today.processedMinor));
  for (const [series, count] of [[data.hourly[currency], 24], [data.minute[currency], 60]]) {
    assert.equal(series.length, count);
    let previous = -Infinity;
    for (const bucket of series) {
      const at = Date.parse(bucket.start);
      assert.ok(at > previous && at <= Date.parse(data.asOf));
      previous = at;
      assert.ok(amount(bucket.amountMinor) >= 0n);
    }
  }
  assert.equal(data.daily.at(-1)[currency], summary.today.processedMinor);
}
assert.equal(data.daily.at(-1).date, data.day);
assert.equal(data.daily.at(-1).partial, true);
console.log(JSON.stringify({
  check: "financial aggregates", as_of: data.asOf, run: data.runId,
  today: Object.fromEntries(["AED", "BHD"].map((c) => [c, data.byCurrency[c].today.processedMinor])),
  scope: "read-only HTTP shape, exact sum, stock/flow and bucket consistency; integration tests independently exercise economic counting",
}));
