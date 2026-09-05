import assert from "node:assert/strict";
import test from "node:test";
import { readCalendar, calendarMessage } from "./calendar.ts";

const valid = {
  enabled: true,
  day: 2,
  pending: 0,
  blocked: 0,
  day_seconds: 300,
  period_days: 6,
};
test("calendar dates must come from complete, bounded server evidence", () => {
  assert.deepEqual(readCalendar(valid), valid);
  for (const value of [
    undefined,
    null,
    {},
    { ...valid, day: "2" },
    { ...valid, day: 0 },
    { ...valid, day: 367 },
    { ...valid, pending: -1 },
    { ...valid, blocked: NaN },
    { ...valid, enabled: "true" },
  ]) {
    assert.throws(() => readCalendar(value), /Calendar state unavailable/);
  }
});
test("unfinished close evidence takes priority over clock configuration", () => {
  assert.match(
    calendarMessage({ ...valid, enabled: false, pending: 3 }, 0),
    /3 closes pending/,
  );
  assert.match(
    calendarMessage({ ...valid, pending: 3, blocked: 1 }, 1),
    /1 blocked close;/,
  );
  assert.equal(
    calendarMessage({ ...valid, enabled: false }, 1),
    "Automatic clock disabled.",
  );
  assert.equal(calendarMessage(valid, 0), "Clock paused with generation.");
  assert.match(calendarMessage(valid, 1), /subject to safety checks/);
});
