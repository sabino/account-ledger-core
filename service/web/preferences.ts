export type ThemePreference = "light" | "dark" | "system";
export type PreferenceStore = Pick<Storage, "getItem" | "setItem">;

export function readPreference(
  store: PreferenceStore | undefined,
  key: string,
): string | null {
  try {
    return store?.getItem(key) ?? null;
  } catch {
    return null;
  }
}

export function writePreference(
  store: PreferenceStore | undefined,
  key: string,
  value: string,
): boolean {
  try {
    if (!store) return false;
    store.setItem(key, value);
    return true;
  } catch {
    return false;
  }
}

export function themePreference(value: string | null): ThemePreference {
  return value === "light" || value === "dark" ? value : "system";
}

export function resolvedTheme(
  preference: ThemePreference,
  systemDark: boolean,
): "light" | "dark" {
  return preference === "system" ? (systemDark ? "dark" : "light") : preference;
}

export function sidebarCollapsed(value: string | null): boolean {
  return value === "collapsed";
}
