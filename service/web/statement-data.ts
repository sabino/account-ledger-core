export type StatementCursor = { sequence: string; leg: number };
export type StatementLine = StatementCursor & {
  recorded_at: string;
  booked_day: number;
  value_day: number;
  kind: string;
  command_id: string;
  instance: string;
  debit_minor: string;
  credit_minor: string;
  change_minor: string;
  balance_minor: string;
};
export type StatementPage = {
  account_id: string;
  name: string;
  currency: string;
  class: string;
  cutoff: string;
  posting_count: string;
  total_debit_minor: string;
  total_credit_minor: string;
  closing_balance_minor: string;
  page_opening_balance_minor: string;
  page_closing_balance_minor: string;
  lines: StatementLine[];
  next: StatementCursor | null;
  scope: string;
};
export const statementExportLimit = 20000;

export function decimalMinor(value: string, currency: string): string {
  if (!/^-?\d+$/.test(value) || !["AED", "BHD"].includes(currency))
    throw new Error("Invalid statement amount or currency");
  const amount = BigInt(value),
    digits = currency === "BHD" ? 3 : 2;
  const text = (amount < 0n ? -amount : amount)
    .toString()
    .padStart(digits + 1, "0");
  return `${amount < 0n ? "-" : ""}${text.slice(0, -digits)}.${text.slice(-digits)}`;
}
// CSV text fields are untrusted (e.g. caller-provided command IDs). Prefix dangerous
// spreadsheet inputs; numeric fields are generated separately from validated integers.
export function csvText(value: string): string {
  const safe = /^[\s]*[=+\-@]|^[\t\r\n]/.test(value) ? "'" + value : value;
  return '"' + safe.replaceAll('"', '""') + '"';
}
export function statementCSV(pages: StatementPage[]): string {
  const first = pages[0];
  if (!first) throw new Error("Statement is empty");
  const expected = BigInt(first.posting_count);
  if (expected > BigInt(statementExportLimit))
    throw new Error(
      `Browser export is limited to ${statementExportLimit.toLocaleString()} posting lines. No partial file was created.`,
    );
  let count = 0n,
    debits = 0n,
    credits = 0n,
    balance = 0n;
  let previous: StatementCursor | null = null;
  const rows = [
    "account_id,account_name,currency,cutoff,sequence,leg,recorded_at,booking_day,value_day,kind,command_id,instance,debit,credit,change,posted_balance",
  ];
  for (let index = 0; index < pages.length; index++) {
    const page = pages[index];
    for (const key of [
      "account_id",
      "name",
      "currency",
      "class",
      "cutoff",
      "posting_count",
      "total_debit_minor",
      "total_credit_minor",
      "closing_balance_minor",
    ] as const)
      if (page[key] !== first[key])
        throw new Error("Statement changed during export");
    if (BigInt(page.page_opening_balance_minor) !== balance)
      throw new Error("Statement page gap");
    for (const line of page.lines) {
      if (
        !/^\d+$/.test(line.sequence) ||
        !Number.isInteger(line.leg) ||
        line.leg < 0
      )
        throw new Error("Invalid statement identity");
      const debit = BigInt(line.debit_minor),
        credit = BigInt(line.credit_minor);
      const sign = ["liability", "income", "equity"].includes(first.class)
        ? -1n
        : 1n;
      if (
        debit < 0n ||
        credit < 0n ||
        (debit === 0n) === (credit === 0n) ||
        (debit - credit) * sign !== BigInt(line.change_minor)
      )
        throw new Error("Statement accounting sides differ");
      if (
        previous &&
        (BigInt(line.sequence) < BigInt(previous.sequence) ||
          (line.sequence === previous.sequence && line.leg <= previous.leg))
      )
        throw new Error("Repeated or unordered statement line");
      if (BigInt(line.sequence) > BigInt(first.cutoff))
        throw new Error("Entry beyond statement cutoff");
      balance += BigInt(line.change_minor);
      debits += BigInt(line.debit_minor);
      credits += BigInt(line.credit_minor);
      count++;
      if (balance !== BigInt(line.balance_minor) || count > expected)
        throw new Error("Statement balance or count differs");
      rows.push(
        [
          ...[
            page.account_id,
            page.name,
            page.currency,
            page.cutoff,
            line.sequence,
            String(line.leg),
            line.recorded_at,
            String(line.booked_day),
            String(line.value_day),
            line.kind,
            line.command_id,
            line.instance,
          ].map(csvText),
          ...[
            line.debit_minor,
            line.credit_minor,
            line.change_minor,
            line.balance_minor,
          ].map((value) => decimalMinor(value, page.currency)),
        ].join(","),
      );
      previous = line;
    }
    if (balance !== BigInt(page.page_closing_balance_minor))
      throw new Error("Statement page balance differs");
    if (
      index < pages.length - 1 &&
      (!page.next ||
        !previous ||
        page.next.sequence !== previous.sequence ||
        page.next.leg !== previous.leg)
    )
      throw new Error("Statement cursor differs");
  }
  if (
    pages.at(-1)!.next ||
    count !== expected ||
    balance !== BigInt(first.closing_balance_minor) ||
    debits !== BigInt(first.total_debit_minor) ||
    credits !== BigInt(first.total_credit_minor)
  )
    throw new Error("Incomplete statement; no partial export created");
  return rows.join("\r\n") + "\r\n";
}
