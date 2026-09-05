import assert from "node:assert/strict";

const base = process.env.LEDGER_URL || "http://localhost:8088";
const observations = [];
for (const currency of ["AED", "BHD"]) {
  for (const window of ["10m", "1h", "24h"]) {
    const start = performance.now();
    const response = await fetch(`${base}/api/analytics?currency=${currency}&window=${window}`);
    assert.equal(response.status, 200);
    const data = await response.json();
    assert.equal(data.currency, currency);
    assert.equal(data.buckets.length, 60);
    assert.equal(Date.parse(data.through) - Date.parse(data.since), data.bucket_seconds * 60 * 1000);
    let total = 0;
    data.buckets.forEach((bucket, index) => {
      for (const name of ["total", "accepted", "declined", "rejected"]) {
        assert.ok(Number.isSafeInteger(bucket[name]) && bucket[name] >= 0);
      }
      assert.equal(bucket.total, bucket.accepted + bucket.declined + bucket.rejected);
      assert.ok(Math.abs(Date.parse(bucket.at) - Date.parse(data.since) - index * data.bucket_seconds * 1000) <= 1);
      total += bucket.total;
    });
    assert.equal(total, data.instances.reduce((sum, instance) => sum + instance.total, 0));
    observations.push({ currency, window, decisions: total, observed_ms: Math.round(performance.now() - start) });
  }
}
for (const query of ["currency=USD", "window=1year", "currency=AED&window=-1"]) {
  assert.equal((await fetch(`${base}/api/analytics?${query}`)).status, 400);
}
assert.equal((await fetch(`${base}/internal/notifications`, { method: "POST", body: "{}" })).status, 404);
console.log(JSON.stringify({ scope: "HTTP analytics contract; timings are single observations, not a benchmark", observations }, null, 2));
