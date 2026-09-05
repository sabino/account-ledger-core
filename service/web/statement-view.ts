import {
  decimalMinor,
  statementCSV,
  statementExportLimit,
  type StatementPage,
  type StatementCursor,
} from "./statement-data.js";

type Helpers = {
  esc: (value: unknown) => string;
  restoreFocus: (account: string) => void;
};
export function createStatementView({ esc, restoreFocus }: Helpers) {
  const el = <T extends HTMLElement = HTMLElement>(id: string) =>
    document.getElementById(id) as T;
  const dialog = el<HTMLDialogElement>("statement-dialog");
  let account = "",
    cutoff: string | undefined,
    current: StatementPage | undefined;
  let cursors: (StatementCursor | null)[] = [null],
    pageIndex = 0,
    busy = false;
  let controller: AbortController | undefined;
  const message = (text: string) => {
    el("statement-message").textContent = text;
  };
  const amount = (minor: string) =>
    `${decimalMinor(minor, current!.currency)} ${current!.currency}`;
  function controls() {
    el<HTMLButtonElement>("statement-prev").disabled = busy || pageIndex === 0;
    el<HTMLButtonElement>("statement-next").disabled = busy || !current?.next;
    el<HTMLButtonElement>("statement-refresh").disabled = busy;
    el<HTMLButtonElement>("statement-export").disabled = busy || !current;
    el<HTMLButtonElement>("statement-cancel-export").hidden =
      !busy || el("statement-export").dataset.active !== "true";
  }
  async function fetchPage(
    cursor: StatementCursor | null,
    signal: AbortSignal,
    limit = 25,
  ) {
    const query = new URLSearchParams({ account, limit: String(limit) });
    if (cutoff !== undefined) query.set("cutoff", cutoff);
    if (cursor) {
      query.set("after_sequence", cursor.sequence);
      query.set("after_leg", String(cursor.leg));
    }
    const response = await fetch("/api/statements?" + query, {
      signal: AbortSignal.any([signal, AbortSignal.timeout(5000)]),
    });
    if (!response.ok)
      throw new Error(
        `Statement request failed (${response.status}). Try again after a short wait.`,
      );
    return (await response.json()) as StatementPage;
  }
  function render() {
    if (!current) return;
    el("statement-title").textContent = current.name;
    el("statement-context").textContent =
      `${current.account_id} / ${current.currency} · Posted statement`;
    el("statement-cutoff").textContent =
      `Fixed journal cutoff #${current.cutoff}`;
    el("statement-closing").textContent = amount(current.closing_balance_minor);
    el("statement-debits").textContent = amount(current.total_debit_minor);
    el("statement-credits").textContent = amount(current.total_credit_minor);
    el("statement-page").textContent =
      `Page ${pageIndex + 1} · ${current.lines.length} of ${current.posting_count} posting lines`;
    el("statement-opening").textContent =
      `This page: ${amount(current.page_opening_balance_minor)} → ${amount(current.page_closing_balance_minor)}`;
    el("statement-lines").innerHTML =
      current.lines
        .map(
          (line) =>
            `<tr><td data-label="Entry"><strong>#${esc(line.sequence)}.${line.leg}</strong><small>${esc(new Date(line.recorded_at).toLocaleString())}</small></td><td data-label="Movement"><strong>${esc(line.kind)}</strong><small>Booked day ${line.booked_day} · Value day ${line.value_day}</small><small class="statement-reference">${esc(line.command_id)}</small></td><td data-label="Debit" class="statement-number">${esc(amount(line.debit_minor))}</td><td data-label="Credit" class="statement-number">${esc(amount(line.credit_minor))}</td><td data-label="Posted balance" class="statement-number">${esc(amount(line.balance_minor))}</td></tr>`,
        )
        .join("") ||
      '<tr><td colspan="5"><div class="empty-state">No monetary postings at this cutoff.</div></td></tr>';
    el("statement-side-note").textContent = [
      "liability",
      "income",
      "equity",
    ].includes(current.class)
      ? "Credits increase this account’s posted balance; debits reduce it."
      : "Debits increase this account’s posted balance; credits reduce it.";
  }
  async function load(index: number, reset = false) {
    controller?.abort();
    const active = new AbortController();
    controller = active;
    busy = true;
    message("Loading fixed-cutoff statement…");
    controls();
    if (reset) {
      cutoff = undefined;
      cursors = [null];
      current = undefined;
      el("statement-lines").replaceChildren();
    }
    try {
      const page = await fetchPage(cursors[index], active.signal);
      if (active.signal.aborted) return;
      current = page;
      cutoff = page.cutoff;
      pageIndex = index;
      render();
      message(
        "Snapshot of posted money. Reservations and rejected attempts are not statement lines.",
      );
      el("statement-scroll").scrollTop = 0;
    } catch (error) {
      if (!active.signal.aborted)
        message(
          `${(error as Error).message} ${current ? "The previous page is still shown." : "Use Refresh snapshot to retry."}`,
        );
    } finally {
      if (controller === active) {
        busy = false;
        controls();
      }
    }
  }
  el("statement-prev").addEventListener(
    "click",
    () => void load(pageIndex - 1),
  );
  el("statement-next").addEventListener("click", () => {
    if (current?.next) {
      cursors[pageIndex + 1] = current.next;
      void load(pageIndex + 1);
    }
  });
  el("statement-refresh").addEventListener("click", () => void load(0, true));
  el("statement-close").addEventListener("click", () => dialog.close());
  dialog.addEventListener("close", () => {
    controller?.abort();
    busy = false;
    document.body.classList.remove("statement-open");
    restoreFocus(account);
  });
  el("statement-cancel-export").addEventListener("click", () => {
    controller?.abort();
    message("Export cancelled. No file was created.");
  });
  el("statement-export").addEventListener("click", async () => {
    if (!current || busy) return;
    if (BigInt(current.posting_count) > BigInt(statementExportLimit)) {
      message(
        `Browser export is limited to ${statementExportLimit.toLocaleString()} lines. Keep browsing with Next page; no partial file was created.`,
      );
      return;
    }
    const active = new AbortController();
    controller = active;
    busy = true;
    el("statement-export").dataset.active = "true";
    controls();
    const pages: StatementPage[] = [];
    let cursor: StatementCursor | null = null,
      count = 0;
    try {
      do {
        // Two export requests/sec, leaving room for the dashboard's normal polls.
        await new Promise<void>((resolve, reject) => {
          active.signal.throwIfAborted();
          const abort = () => {
            clearTimeout(timer);
            reject(active.signal.reason);
          };
          const timer = setTimeout(() => {
            active.signal.removeEventListener("abort", abort);
            resolve();
          }, 500);
          active.signal.addEventListener("abort", abort, { once: true });
        });
        const page = await fetchPage(cursor, active.signal, 100);
        pages.push(page);
        count += page.lines.length;
        if (
          count > statementExportLimit ||
          pages.length > statementExportLimit / 100 + 1
        )
          throw new Error(
            "Export bound exceeded; no partial file was created.",
          );
        cursor = page.next;
        message(
          `Preparing complete CSV: ${count} / ${current.posting_count} posting lines. You can cancel safely.`,
        );
      } while (cursor);
      const csv = statementCSV(pages);
      active.signal.throwIfAborted();
      const url = URL.createObjectURL(
        new Blob([csv], { type: "text/csv;charset=utf-8" }),
      );
      const link = document.createElement("a");
      link.href = url;
      link.download = `statement-${account.replace(/[^a-zA-Z0-9_-]/g, "_")}-${cutoff}.csv`;
      document.body.append(link);
      link.click();
      link.remove();
      setTimeout(() => URL.revokeObjectURL(url), 1000);
      message(
        `Complete CSV downloaded: ${count} posting lines at cutoff #${cutoff}. Amounts are exact; spreadsheet apps may apply their own number formatting.`,
      );
    } catch (error) {
      if (!active.signal.aborted)
        message(`${(error as Error).message} No partial file was created.`);
    } finally {
      if (controller === active) {
        busy = false;
        delete el("statement-export").dataset.active;
        controls();
      }
    }
  });
  return {
    open(id: string) {
      delete el("statement-export").dataset.active;
      el("statement-side-note").textContent = "";
      account = id;
      current = undefined;
      pageIndex = 0;
      el("statement-title").textContent = id;
      el("statement-context").textContent = "Posted statement";
      el("statement-cutoff").textContent = "Capturing journal cutoff…";
      for (const key of [
        "statement-closing",
        "statement-debits",
        "statement-credits",
        "statement-page",
        "statement-opening",
      ])
        el(key).textContent = "—";
      dialog.showModal();
      document.body.classList.add("statement-open");
      void load(0, true);
    },
    close() {
      if (dialog.open) dialog.close();
    },
  };
}
