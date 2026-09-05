export type Calendar = {
  enabled: boolean;
  day: number;
  pending: number;
  blocked: number;
  day_seconds: number;
  period_days: number;
};

export function readCalendar(value: unknown): Calendar {
  const c = value as Calendar | undefined;
  if (
    !c ||
    typeof c.enabled !== "boolean" ||
    !Number.isInteger(c.day) ||
    c.day < 1 ||
    c.day > 366 ||
    !Number.isSafeInteger(c.pending) ||
    c.pending < 0 ||
    !Number.isSafeInteger(c.blocked) ||
    c.blocked < 0 ||
    c.day_seconds !== 300 ||
    c.period_days !== 6
  ) {
    throw new Error(
      "Calendar state unavailable. Refresh before sending money.",
    );
  }
  return c;
}

export function calendarMessage(c: Calendar, eps: number): string {
  if (c.blocked)
    return `${c.blocked} blocked close${c.blocked === 1 ? "" : "s"}; operator resolution required.`;
  if (c.pending)
    return `${c.pending} close${c.pending === 1 ? "" : "s"} pending. Affected accounts wait before spending.`;
  if (!c.enabled) return "Automatic clock disabled.";
  if (eps === 0) return "Clock paused with generation.";
  return "Five-minute days, subject to safety checks. Interest credited every six days.";
}
