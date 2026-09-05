type Currency = "AED" | "BHD";
type Period = {
  transfersMinor: string;
  capturesMinor: string;
  purchasesGrossMinor: string;
  processedMinor: string;
  operations: number;
};
type Balances = {
  postedMinor: string;
  heldMinor: string;
  availableMinor: string;
  customerCount: number;
};
type MoneyBucket = { start: string; amountMinor: string };
type Financial = {
  asOf: string;
  day: string;
  timeZone: string;
  runStartedAt: string;
  byCurrency: Record<
    Currency,
    { today: Period; run: Period; balances: Balances }
  >;
  hourly: Record<Currency, MoneyBucket[]>;
  minute: Record<Currency, MoneyBucket[]>;
  daily: Array<{ date: string; AED: string; BHD: string; commands: number }>;
  definition?: string;
};
type Account = {
  customer: boolean;
  currency: string;
  balance_minor: string;
  held_minor: string;
};

// Formatting remains exact even beyond Number.MAX_SAFE_INTEGER.
export function formatMinor(minor: string, currency: string) {
  const scale = currency === "BHD" ? 3 : 2;
  const value = BigInt(minor);
  const digits = (value < 0n ? -value : value)
    .toString()
    .padStart(scale + 1, "0");
  return `${value < 0n ? "−" : ""}${digits.slice(0, -scale).replace(/\B(?=(\d{3})+(?!\d))/g, ",")}.${digits.slice(-scale)}`;
}
export function displayMinor(minor: string | undefined, currency: string) {
  return minor === undefined ? "Unavailable" : formatMinor(minor, currency);
}

export function createFinancialView({
  api,
  esc,
}: {
  api: (path: string) => Promise<Financial>;
  esc: (value: unknown) => string;
}) {
  const $ = <T extends HTMLElement = HTMLElement>(id: string) =>
    document.getElementById(id) as T;
  let latest: Financial | undefined;
  let shown: Financial | undefined;
  let period: "today" | "run" = "today";
  let frozen = false;
  let valueWindow = "today";
  let stale = false;
  let balanceAsOf = "";
  let fallback: Partial<Record<Currency, Balances>> = {};
  const display = displayMinor;
  const dialog = $<HTMLDialogElement>("money-dialog");

  function renderMoney() {
    if (!frozen) shown = latest;
    $("money-asof").textContent = shown
      ? `${frozen ? "Display paused · " : stale ? "Stale snapshot · " : ""}${new Date(shown.asOf).toLocaleString(undefined, { timeZone: "UTC" })} · ${shown.timeZone}`
      : `${frozen ? "Display paused · " : ""}Processed totals unavailable${balanceAsOf ? ` · balances at ${balanceAsOf}` : ""}`;
    $("money-overview").classList.toggle("data-stale", stale);
    $("currency-grid").innerHTML = (["AED", "BHD"] as const)
      .map((currency) => {
        const financial = shown?.byCurrency[currency];
        const current = financial?.[period];
        const comparison = financial?.[period === "today" ? "run" : "today"];
        const balances = financial?.balances || fallback[currency];
        return `<article class="currency-column" data-currency="${currency}"><div class="currency-heading"><h3>${currency}</h3><span>${currency === "AED" ? "UAE dirham" : "Bahraini dinar"}</span><span class="operation-count">${current ? current.operations.toLocaleString() + " operations" : "No aggregate available"}</span></div><div class="money-primary"><div><span class="money-label">${period === "today" ? "Processed today" : "Processed this run"}</span><strong class="processed-value ${current ? "" : "unavailable"}">${display(current?.processedMinor, currency)}</strong></div><div class="money-comparison"><span class="money-label">${period === "today" ? "Since run started" : "Today"}</span><strong>${display(comparison?.processedMinor, currency)}</strong></div></div><dl class="money-breakdown"><div><dt>Transfers</dt><dd>${display(current?.transfersMinor, currency)}</dd></div><div><dt>Captured</dt><dd>${display(current?.capturesMinor, currency)}</dd></div><div><dt>Purchases, gross</dt><dd>${display(current?.purchasesGrossMinor, currency)}</dd></div></dl><div class="balance-title"><span>Customer balances${frozen || stale ? " at snapshot" : " now"}</span><span>${balances ? balances.customerCount + " customer accounts" : "Unavailable"}</span></div><dl class="balance-equation"><div><dt>Posted</dt><dd>${display(balances?.postedMinor, currency)}</dd></div><span aria-hidden="true">−</span><div><dt>Held</dt><dd class="held-value">${display(balances?.heldMinor, currency)}</dd></div><span aria-hidden="true">=</span><div><dt>Available</dt><dd>${display(balances?.availableMinor, currency)}</dd></div></dl></article>`;
      })
      .join("");
    $("money-note").textContent = shown
      ? `${stale ? "Financial refresh unavailable. " : ""}Separate currencies · UTC processing day · run from ${new Date(shown.runStartedAt).toLocaleDateString(undefined, { timeZone: "UTC" })}.`
      : "Complete period aggregates are unavailable. Customer balances come from the current account snapshot.";
  }

  function renderChart() {
    const measure = $<HTMLSelectElement>("chart-measure").value;
    const commands = measure === "commands";
    $("money-chart").hidden = commands;
    $("events-chart").hidden = !commands;
    $("command-legend").hidden = !commands;
    $("analytics-status").hidden = !commands;
    $("value-windows").hidden = commands;
    $("chart-title").textContent = commands
      ? "Command activity"
      : "Value processed";
    $("chart-subtitle").textContent = commands
      ? "Recorded decisions · selected currency and window"
      : `${measure} · committed economic operations`;
    if (commands) return;
    const currency = measure as Currency;
    const window = valueWindow;
    const buckets =
      window === "1h"
        ? latest?.minute[currency]
        : window === "6h"
          ? latest?.hourly[currency]?.slice(-6)
          : latest?.hourly[currency]?.filter(
              (bucket) => bucket.start.slice(0, 10) === latest?.day,
            );
    if (!buckets?.length) {
      $("money-chart").innerHTML =
        '<div class="chart-unavailable"><span>Value history unavailable</span><p>Complete processing-time aggregates are required. Select Command counts to inspect recorded activity.</p></div>';
      return;
    }
    const amounts = buckets.map((b) => BigInt(b.amountMinor));
    const maximum = amounts.reduce((max, n) => (n > max ? n : max), 1n);
    // Only scaled chart coordinates use Number. Totals and labels stay BigInt.
    const heights = amounts.map(
      (n) => (Number((n * 10000n) / maximum) / 10000) * 148,
    );
    const bars = buckets
      .map(
        (b, index) =>
          `<rect class="chart-bar" x="${38 + (index * 510) / buckets.length}" y="${170 - heights[index]}" width="${Math.max(1, 510 / buckets.length - 2)}" height="${heights[index]}" rx="2"><title>${esc(b.start)}: ${formatMinor(b.amountMinor, currency)} ${currency}</title></rect>`,
      )
      .join("");
    const total = amounts.reduce((sum, n) => sum + n, 0n);
    $("money-chart").innerHTML =
      `<div class="chart-legend"><span><i class="legend-dot"></i>${currency} per ${window === "1h" ? "minute" : "hour"}</span><span>${stale ? "Stale · " : ""}${formatMinor(total.toString(), currency)} ${currency} in shown buckets</span></div><svg viewBox="0 0 560 190" role="img" aria-label="${esc(currency)} processed value"><path class="chart-grid" d="M38 22H550 M38 59H550 M38 96H550 M38 133H550 M38 170H550"/>${bars}<text x="0" y="174">0</text></svg><div class="chart-footer"><span>${esc(new Date(buckets[0].start).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", timeZone: "UTC" }))}</span><span>UTC calendar buckets · current bucket partial</span><span>${esc(new Date(buckets.at(-1)!.start).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", timeZone: "UTC" }))}</span></div><details><summary>View exact amounts</summary><table><thead><tr><th>Bucket start (UTC)</th><th>${currency}</th></tr></thead><tbody>${buckets.map((b) => `<tr><td>${esc(b.start)}</td><td>${formatMinor(b.amountMinor, currency)}</td></tr>`).join("")}</tbody></table></details>`;
  }

  $("money-how").addEventListener("click", () => {
    $("money-dialog-title").textContent = "How value is counted";
    $("money-dialog-content").innerHTML =
      "<h3>One operation, counted once</h3><p>Processed value includes committed transfers and splits, final captures, and gross purchases. A split counts its original total once. A purchase counts net plus stored tax once.</p><p>Funding, active holds, declines, rejections and matched retries do not add processed value. Reversals stay outside this gross forward measure.</p><h3>Money moved and money held</h3><p>Customer posted minus active holds equals customer available. These are current balances; processed value is a flow over a period. Currencies remain separate, and internal settlement and tax accounts are excluded from customer balances.</p><h3>Time and completeness</h3><p>Today starts at 00:00 UTC. Run totals start at the recorded run boundary. The current day and current chart bucket are partial. Aggregates cover the retained ledger; journal pagination does not determine the totals.</p><p>This is a synthetic accounting experiment, with no real customer funds.</p>";
    dialog.showModal();
  });
  $("money-daily").addEventListener("click", () => {
    $("money-dialog-title").textContent = "Daily totals";
    $("money-dialog-content").innerHTML = shown
      ? `<p>Gross value processed · UTC · ${stale ? "stale " : ""}snapshot ${esc(shown.asOf)}. Current day is partial. Batch counts include durable decisions and maintenance.</p><div class="table-scroll"><table class="daily-table"><thead><tr><th>UTC day</th><th>Recorded batches</th><th>AED processed</th><th>BHD processed</th></tr></thead><tbody>${shown.daily.map((day) => `<tr><td>${esc(day.date)}${day.date < shown!.runStartedAt.slice(0, 10) ? "<small>Before this run</small>" : day.date === shown!.day ? "<small>Partial day</small>" : ""}</td><td>${day.commands.toLocaleString()}</td><td>${formatMinor(day.AED, "AED")}</td><td>${formatMinor(day.BHD, "BHD")}</td></tr>`).join("")}</tbody></table></div>`
      : "<p>Daily totals unavailable. A complete server aggregate is required; the recent journal is not a complete day.</p>";
    dialog.showModal();
  });
  $("money-dialog-close").addEventListener("click", () => dialog.close());
  $("freeze-money").addEventListener("click", () => {
    frozen = !frozen;
    $("freeze-money").setAttribute("aria-pressed", String(frozen));
    $("freeze-money").setAttribute(
      "aria-label",
      `${frozen ? "Resume" : "Pause"} monetary display`,
    );
    $("freeze-money").textContent = frozen ? "▶" : "Ⅱ";
    renderMoney();
  });
  document
    .querySelectorAll<HTMLButtonElement>("[data-money-period]")
    .forEach((button) =>
      button.addEventListener("click", () => {
        period = button.dataset.moneyPeriod as "today" | "run";
        document
          .querySelectorAll<HTMLButtonElement>("[data-money-period]")
          .forEach((choice) =>
            choice.setAttribute("aria-pressed", String(choice === button)),
          );
        renderMoney();
      }),
    );
  $("chart-measure").addEventListener("change", renderChart);
  document
    .querySelectorAll<HTMLButtonElement>("[data-value-window]")
    .forEach((button) =>
      button.addEventListener("click", () => {
        valueWindow = button.dataset.valueWindow!;
        document
          .querySelectorAll<HTMLButtonElement>("[data-value-window]")
          .forEach((choice) =>
            choice.setAttribute("aria-pressed", String(choice === button)),
          );
        renderChart();
      }),
    );
  $("view-window").addEventListener("change", renderChart);
  renderMoney();
  renderChart();
  return {
    async refresh() {
      try {
        const data = await api("financial");
        if (!data.asOf || !data.byCurrency?.AED || !data.byCurrency?.BHD)
          throw new Error("Incomplete financial snapshot");
        latest = data;
        stale = false;
      } catch {
        stale = true;
      }
      renderMoney();
      renderChart();
    },
    accounts(list: Account[]) {
      if (frozen) return;
      fallback = {};
      for (const currency of ["AED", "BHD"] as const) {
        const rows = list.filter((a) => a.customer && a.currency === currency);
        const posted = rows.reduce(
          (sum, a) => sum + BigInt(a.balance_minor),
          0n,
        );
        const held = rows.reduce((sum, a) => sum + BigInt(a.held_minor), 0n);
        fallback[currency] = {
          postedMinor: String(posted),
          heldMinor: String(held),
          availableMinor: String(posted - held),
          customerCount: rows.length,
        };
      }
      balanceAsOf = new Date().toLocaleTimeString();
      renderMoney();
    },
    stale() {
      stale = true;
      renderMoney();
      renderChart();
    },
  };
}
