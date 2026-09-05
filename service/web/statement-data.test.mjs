import assert from "node:assert/strict";
import test from "node:test";
import { decimalMinor, csvText, statementCSV } from "./statement-data.ts";

const line = (sequence, change, balance) => ({
  sequence,
  leg: 1,
  recorded_at: "2026-09-04T12:00:00Z",
  booked_day: 1,
  value_day: 1,
  kind: "credit",
  command_id: "example",
  instance: "replica-a",
  debit_minor: BigInt(change) < 0n ? String(-BigInt(change)) : "0",
  credit_minor: BigInt(change) > 0n ? change : "0",
  change_minor: change,
  balance_minor: balance,
});
const page = (lines, opening, closing, next = null) => ({
  account_id: "ACC-021",
  name: 'A "quoted", name',
  currency: "BHD",
  class: "liability",
  cutoff: "9007199254740993",
  posting_count: "2",
  total_debit_minor: "1",
  total_credit_minor: "10000",
  closing_balance_minor: "9999",
  page_opening_balance_minor: opening,
  page_closing_balance_minor: closing,
  lines,
  next,
});
const pages = () => [
  page([line("9007199254740992", "10000", "10000")], "0", "10000", {
    sequence: "9007199254740992",
    leg: 1,
  }),
  page([line("9007199254740993", "-1", "9999")], "10000", "9999"),
];

test("money formatting preserves minor units and large values exactly", () => {
  assert.equal(decimalMinor("10001", "BHD"), "10.001");
  assert.equal(decimalMinor("-1", "AED"), "-0.01");
  assert.equal(
    decimalMinor("9223372036854775808", "AED"),
    "92233720368547758.08",
  );
  assert.throws(() => decimalMinor("1.2", "AED"));
  assert.throws(() => decimalMinor("1", "USD"));
});
test("CSV keeps dates, exact IDs, currencies, quotes and all pages", () => {
  const csv = statementCSV(pages());
  assert.equal(csv.split("\r\n").length, 4);
  assert.ok(csv.includes('"9007199254740993"'));
  assert.ok(csv.includes('"A ""quoted"", name"'));
  assert.ok(csv.includes("0.000,10.000,10.000,10.000"));
  assert.ok(csv.includes("0.001,0.000,-0.001,9.999"));
});
test("untrusted CSV text cannot become a spreadsheet formula", () => {
  for (const value of [
    "=SUM(1,2)",
    "+cmd",
    "-cmd",
    "@cmd",
    "  =1",
    "\tformula",
    "\rformula",
    "\nformula",
  ])
    assert.ok(csvText(value).startsWith("\"'"));
  assert.equal(csvText("ordinary"), '"ordinary"');
});
test("partial, mixed-cutoff and contradictory exports fail before download", () => {
  assert.throws(() => statementCSV(pages().slice(0, 1)));
  for (const mutate of [
    (p) => (p[1].cutoff = "99"),
    (p) => (p[1].account_id = "other"),
    (p) => (p[1].page_opening_balance_minor = "99"),
    (p) => (p[1].lines[0].balance_minor = "0"),
    (p) => (p[1].lines[0].sequence = "9007199254740992"),
    (p) => (p[0].total_credit_minor = "1"),
    (p) => (p[0].posting_count = "20001"),
    (p) => (p[1].lines[0].credit_minor = "1"),
  ]) {
    const p = pages();
    mutate(p);
    assert.throws(() => statementCSV(p));
  }
});
test("empty accounts export a header without inventing a balance", () => {
  const empty = page([], "0", "0");
  Object.assign(empty, {
    posting_count: "0",
    total_debit_minor: "0",
    total_credit_minor: "0",
    closing_balance_minor: "0",
  });
  assert.equal(statementCSV([empty]).split("\r\n").length, 2);
});
