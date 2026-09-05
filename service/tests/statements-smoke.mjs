import assert from "node:assert/strict";
import { setTimeout as delay } from "node:timers/promises";

// Read-only HTTP verification. Never changes generation or submits money commands.
const base = process.env.LEDGER_URL || "http://localhost:8088";
async function get(path, status = 200) {
  // Respect the shared proxy's five-requests/sec budget; no burst bypass.
  await delay(350);
  const response = await fetch(base + path, {
    signal: AbortSignal.timeout(5000),
  });
  assert.equal(response.status, status, path);
  return response.json();
}
const accounts = await get("/api/accounts");
for (const currency of ["AED", "BHD"]) {
  const account = accounts.find(
    (item) => item.customer && item.currency === currency,
  );
  assert.ok(account);
  let query = new URLSearchParams({ account: account.id, limit: "17" });
  let cutoff,
    closing,
    last,
    opening = "0",
    count = 0n,
    debits = 0n,
    credits = 0n;
  for (let pageNumber = 0; ; pageNumber++) {
    assert.ok(pageNumber < 1000, "bounded statement traversal");
    const page = await get("/api/statements?" + query);
    cutoff ??= page.cutoff;
    closing ??= page.closing_balance_minor;
    assert.equal(page.cutoff, cutoff);
    assert.equal(page.closing_balance_minor, closing);
    assert.equal(page.currency, currency);
    assert.equal(page.page_opening_balance_minor, opening);
    let running = BigInt(opening);
    for (const line of page.lines) {
      assert.equal(typeof line.change_minor, "string");
      const position = [BigInt(line.sequence), line.leg];
      if (last)
        assert.ok(
          position[0] > last[0] ||
            (position[0] === last[0] && position[1] > last[1]),
        );
      last = position;
      running += BigInt(line.change_minor);
      debits += BigInt(line.debit_minor);
      credits += BigInt(line.credit_minor);
      assert.equal(line.balance_minor, String(running));
      count++;
    }
    opening = page.page_closing_balance_minor;
    assert.equal(String(running), opening);
    if (!page.next) {
      assert.equal(opening, closing);
      assert.equal(String(count), page.posting_count);
      assert.equal(String(debits), page.total_debit_minor);
      assert.equal(String(credits), page.total_credit_minor);
      console.log(
        JSON.stringify({
          account: account.id,
          currency,
          cutoff,
          postings: String(count),
          closing,
          scope: "complete fixed-cutoff posted statement, read-only",
        }),
      );
      break;
    }
    assert.equal(page.next.sequence, String(last[0]));
    assert.equal(page.next.leg, last[1]);
    query = new URLSearchParams({
      account: account.id,
      cutoff,
      after_sequence: page.next.sequence,
      after_leg: String(page.next.leg),
      limit: "17",
    });
  }
  const zero = await get(
    `/api/statements?account=${encodeURIComponent(account.id)}&cutoff=0`,
  );
  assert.deepEqual(zero.lines, []);
  assert.equal(zero.closing_balance_minor, "0");
}
for (const query of [
  "account=ACC-001&limit=101",
  "account=ACC-001&cutoff=-1",
  "account=ACC-001&after_sequence=1&after_leg=0",
  "account=ACC-001&cutoff=1&cutoff=2",
])
  await get("/api/statements?" + query, 400);
await get("/api/statements?account=does-not-exist", 404);
