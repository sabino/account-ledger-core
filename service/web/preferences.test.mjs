import assert from "node:assert/strict";
import test from "node:test";
import {
  readPreference,
  writePreference,
  themePreference,
  resolvedTheme,
  sidebarCollapsed,
} from "./preferences.ts";

test("invalid and absent preferences follow the system", () => {
  for (const value of [null, "", "unknown", "DARK"])
    assert.equal(themePreference(value), "system");
  assert.equal(themePreference("light"), "light");
  assert.equal(themePreference("dark"), "dark");
});

test("only system preference responds to system color changes", () => {
  assert.equal(resolvedTheme("system", true), "dark");
  assert.equal(resolvedTheme("system", false), "light");
  assert.equal(resolvedTheme("light", true), "light");
  assert.equal(resolvedTheme("dark", false), "dark");
});

test("theme and sidebar preferences survive a storage round trip independently", () => {
  const data = new Map();
  const store = {
    getItem: (key) => data.get(key) ?? null,
    setItem: (key, value) => data.set(key, value),
  };
  assert.equal(writePreference(store, "ledger.theme", "dark"), true);
  assert.equal(writePreference(store, "ledger.sidebar", "collapsed"), true);
  assert.equal(themePreference(readPreference(store, "ledger.theme")), "dark");
  assert.equal(sidebarCollapsed(readPreference(store, "ledger.sidebar")), true);
  writePreference(store, "ledger.sidebar", "expanded");
  assert.equal(
    sidebarCollapsed(readPreference(store, "ledger.sidebar")),
    false,
  );
  assert.equal(themePreference(readPreference(store, "ledger.theme")), "dark");
});

test("blocked storage does not break the app", () => {
  const blocked = {
    getItem() {
      throw new Error("blocked");
    },
    setItem() {
      throw new Error("quota");
    },
  };
  assert.equal(readPreference(blocked, "ledger.theme"), null);
  assert.equal(writePreference(blocked, "ledger.theme", "dark"), false);
  assert.equal(readPreference(undefined, "ledger.theme"), null);
  assert.equal(writePreference(undefined, "ledger.theme", "dark"), false);
});

test("sidebar only collapses for its explicit saved state", () => {
  for (const value of [null, "", "false", "expanded", "unknown"])
    assert.equal(sidebarCollapsed(value), false);
  assert.equal(sidebarCollapsed("collapsed"), true);
});
