type Account = {
  id: string;
  name: string;
  currency: string;
  customer: boolean;
  balance_minor: string;
  held_minor: string;
};
type Leg = { account: string; currency: string; units: string };
type Outcome = {
  id: string;
  kind: string;
  status: string;
  reason?: string;
  sequence: string;
  instance: string;
  legs: Leg[];
  command?: {
    currency: string;
    account: string;
    destination?: string;
    amount?: string;
  };
  decision?: {
    balance_before: string;
    held_before: string;
    available_before: string;
    requested_minor: string;
  };
  calculation?: {
    policy: string;
    net: string;
    tax: string;
    gross: string;
    numerator: number;
    denominator: number;
    rounding: string;
  };
  captured?: string;
  released?: string;
  policy?: unknown;
};
type JournalRow = {
  at: string;
  booked_day: number;
  value_day: number;
  result: Outcome;
};
let journalRows: JournalRow[] = [];
let selectedEvent: JournalRow | undefined;
const $ = <T extends HTMLElement = HTMLElement>(id: string) =>
  document.getElementById(id) as T;
let accounts: Account[] = [];
const viewCurrency = () => $<HTMLSelectElement>("view-currency").value;
type Bucket = {
  at: string;
  total: number;
  accepted: number;
  declined: number;
  rejected: number;
};
type Analytics = {
  since: string;
  through: string;
  currency: string;
  bucket_seconds: number;
  buckets: Bucket[];
  instances: { instance: string; total: number }[];
};
let analyticsRequest = 0;
let analyticsUpdated = 0;

// Counts only: monetary calculations stay in integer minor units below.
function chart(
  id: string,
  rows: Bucket[],
  value: (row: Bucket) => number,
  data: Analytics,
) {
  const values = rows.map(value);
  const maximum = Math.max(1, ...values);
  const points = values
    .map(
      (v, i) =>
        `${40 + (i * 510) / Math.max(1, values.length - 1)},${145 - (v / maximum) * 125}`,
    )
    .join(" ");
  const label = `${values.reduce((a, b) => a + b, 0)} decisions in ${data.bucket_seconds}-second buckets`;
  const target = $(id);
  target.innerHTML = `<svg viewBox="0 0 560 165" role="img" aria-label="${esc(label)}"><title>${esc(label)}</title><path class="chart-grid" d="M40 20H550 M40 82.5H550 M40 145H550"/><text x="0" y="24">${maximum}</text><text x="20" y="149">0</text><polygon class="chart-fill" points="40,145 ${points} 550,145"/><polyline class="chart-line" points="${points}"/></svg><div class="chart-footer"><span>${esc(new Date(data.since).toLocaleTimeString())}</span><span>${data.bucket_seconds}s / bucket</span><span>${esc(new Date(data.through).toLocaleTimeString())}</span></div>`;
  const details = document.createElement("details");
  const summary = document.createElement("summary");
  summary.textContent = "View exact counts";
  const table = document.createElement("table");
  table.innerHTML =
    "<thead><tr><th>Bucket start (local time)</th><th>Decisions</th></tr></thead>";
  const body = document.createElement("tbody");
  rows.forEach((row) => {
    const tr = document.createElement("tr");
    for (const text of [
      new Date(row.at).toLocaleString(),
      String(value(row)),
    ]) {
      const td = document.createElement("td");
      td.textContent = text;
      tr.append(td);
    }
    body.append(tr);
  });
  table.append(body);
  details.append(summary, table);
  target.append(details);
}
function bars(id: string, rows: { label: string; value: number }[]) {
  const total = rows.reduce((sum, row) => sum + row.value, 0);
  $(id).innerHTML =
    rows
      .map(
        (row) =>
          `<div><div class="bar-label"><span>${esc(row.label)}</span><strong>${row.value.toLocaleString()}</strong></div><div class="bar-track"><span style="width:${total ? (100 * row.value) / total : 0}%"></span></div></div>`,
      )
      .join("") || '<p class="note">No recorded decisions in this window.</p>';
}
async function analytics() {
  const request = ++analyticsRequest;
  $("analytics-status").textContent = "Updating event analytics…";
  try {
    const data: Analytics = await api(
      `analytics?currency=${encodeURIComponent(viewCurrency())}&window=${encodeURIComponent($<HTMLSelectElement>("view-window").value)}`,
    );
    if (request !== analyticsRequest) return;
    const total = data.buckets.reduce((sum, b) => sum + b.total, 0);
    const negative = data.buckets.reduce(
      (sum, b) => sum + b.declined + b.rejected,
      0,
    );
    $("event-total").textContent = total.toLocaleString();
    $("event-negative").textContent = negative.toLocaleString();
    chart("events-chart", data.buckets, (b) => b.total, data);
    chart("negative-chart", data.buckets, (b) => b.declined + b.rejected, data);
    bars(
      "outcome-bars",
      ["accepted", "declined", "rejected"].map((status) => ({
        label: status,
        value: data.buckets.reduce(
          (sum, b) => sum + b[status as "accepted" | "declined" | "rejected"],
          0,
        ),
      })),
    );
    bars(
      "instance-bars",
      data.instances.map((r) => ({ label: r.instance, value: r.total })),
    );
    $("analytics-status").textContent =
      `${data.currency} · ${new Date(data.since).toLocaleString()} → ${new Date(data.through).toLocaleString()} · PostgreSQL journal · refreshes every 10 seconds${total === 0 ? " · No decisions recorded in this window." : ""}`;
    analyticsUpdated = Date.now();
  } catch (error) {
    if (request !== analyticsRequest) return;
    $("analytics-status").textContent =
      `Analytics unavailable; previous chart, if present, is stale. ${(error as Error).message}`;
  }
}
function accountSummary() {
  const currency = viewCurrency();
  const selected = accounts.filter(
    (a) => a.customer && a.currency === currency,
  );
  $("account-count").textContent = `${selected.length} · ${currency}`;
  $("customer-total").textContent = money(
    selected.reduce((sum, a) => sum + BigInt(a.balance_minor), 0n).toString(),
    currency,
  );
  $("held-total").textContent =
    `Posted · ${money(selected.reduce((sum, a) => sum + BigInt(a.held_minor), 0n).toString(), currency)} reserved`;
  $("account-list").innerHTML = selected
    .map(
      (a) =>
        `<div class="account-row"><button data-account="${esc(a.id)}">${esc(a.name)}<small>${esc(a.id)}</small></button><span>${money(a.balance_minor, currency)}</span></div>`,
    )
    .join("");
}
const money = (minor: string, currency: string) => {
  const p = currency === "BHD" ? 3 : 2;
  let n = BigInt(minor);
  const sign = n < 0n ? "-" : "";
  if (n < 0n) n = -n;
  const s = n.toString().padStart(p + 1, "0");
  return `${sign}${s.slice(0, -p)}.${s.slice(-p)} ${currency}`;
};
const esc = (s: unknown) =>
  String(s).replace(
    /[&<>"']/g,
    (c) =>
      ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[
        c
      ]!,
  );
async function api(path: string, body?: unknown) {
  const r = await fetch("/api/" + path, {
    headers: body ? { "Content-Type": "application/json" } : {},
    method: body ? "POST" : "GET",
    body: body ? JSON.stringify(body) : undefined,
  });
  if (!r.ok) {
    const text = await r.text();
    let error = text;
    try {
      error = JSON.parse(text).error;
    } catch {}
    throw new Error(error || `Request failed (${r.status})`);
  }
  return r.json();
}
function toast(s: string) {
  $("toast").textContent = s;
  $("toast").style.display = "block";
  setTimeout(() => ($("toast").style.display = "none"), 5000);
}
function choices() {
  const source = $<HTMLSelectElement>("source");
  const previous = source.value;
  source.innerHTML = accounts
    .filter((a) => a.customer && a.currency === viewCurrency())
    .map(
      (a) =>
        `<option value="${esc(a.id)}">${esc(a.name)} / ${a.id} / ${a.currency}</option>`,
    )
    .join("");
  if (Array.from(source.options).some((o) => o.value === previous))
    source.value = previous;
  destinations();
  const statement = $<HTMLSelectElement>("statement"),
    v = statement.value;
  statement.innerHTML =
    '<option value="">All accounts</option>' +
    accounts
      .filter((a) => a.currency === viewCurrency())
      .map((a) => `<option value="${a.id}">${esc(a.name)} / ${a.id}</option>`)
      .join("");
  statement.value = v;
}
function destinations() {
  const source = accounts.find(
    (a) => a.id === $<HTMLSelectElement>("source").value,
  );
  if (!source) return;
  const select = $<HTMLSelectElement>("destination"),
    old = select.value;
  select.innerHTML = accounts
    .filter(
      (a) => a.customer && a.currency === source.currency && a.id !== source.id,
    )
    .map((a) => `<option value="${a.id}">${esc(a.name)} / ${a.id}</option>`)
    .join("");
  if (Array.from(select.options).some((o) => o.value === old))
    select.value = old;
  $("currency").textContent = source.currency;
  $("source-balance").textContent =
    `${money(source.balance_minor, source.currency)} posted · ${money((BigInt(source.balance_minor) - BigInt(source.held_minor)).toString(), source.currency)} available`;
}
async function journal() {
  const selectedCurrency = viewCurrency();
  const rows = await api(
    "journal?account=" +
      encodeURIComponent($<HTMLSelectElement>("statement").value),
  );
  if (selectedCurrency !== viewCurrency()) return;
  journalRows = rows.filter(
    (row: JournalRow) =>
      row.result.command?.currency === selectedCurrency ||
      (!row.result.command?.currency &&
        row.result.legs.some((leg) => leg.currency === selectedCurrency)),
  );
  $("journal").innerHTML =
    journalRows
      .map((row: any) => {
        const r: Outcome = row.result;
        const legs = (positive: boolean) =>
          r.legs
            .filter((l) =>
              positive ? BigInt(l.units) > 0n : BigInt(l.units) < 0n,
            )
            .map(
              (l) =>
                `${esc(l.account)}<small>${money((BigInt(l.units) < 0n ? -BigInt(l.units) : BigInt(l.units)).toString(), l.currency)}</small>`,
            )
            .join("<br>") || "—";
        return `<tr class="${selectedEvent?.result.sequence === r.sequence ? "selected-event" : ""}"><td><button class="inspect-event" data-sequence="${esc(r.sequence)}" aria-label="Inspect ${esc(r.id)}" aria-pressed="${selectedEvent?.result.sequence === r.sequence}">#${r.sequence}</button><small>${new Date(row.at).toLocaleTimeString()}</small></td><td>${esc(r.kind)}<small>${esc(r.id)}</small></td><td class="${esc(r.status)}">${esc(r.status)}<small>${esc(r.reason || "")}</small></td><td>${legs(true)}</td><td>${legs(false)}</td><td>${esc(r.instance)}</td></tr>`;
      })
      .join("") ||
    '<tr><td colspan="6">No matching decisions in this latest-batch preview.</td></tr>';
}
function inspectEvent(row: JournalRow) {
  selectedEvent = row;
  const r = row.result;
  const panel = $("event-inspector");
  panel.replaceChildren();
  const line = (tag: string, value: string, className = "") => {
    const element = document.createElement(tag);
    element.textContent = value;
    element.className = className;
    panel.append(element);
    return element;
  };
  line("p", "WHY THIS HAPPENED", "eyebrow");
  line("h3", `${r.kind} · ${r.status}`, r.status);
  line(
    "p",
    r.reason ||
      (r.legs.length
        ? "The monetary entries were recorded together."
        : "No monetary posting. This decision is still recorded."),
  );
  if (r.status !== "accepted") line("strong", "No money moved", "no-movement");
  const facts = document.createElement("dl");
  facts.className = "decision-facts";
  panel.append(facts);
  const fact = (name: string, value: string) => {
    const label = document.createElement("dt"),
      content = document.createElement("dd");
    label.textContent = name;
    content.textContent = value;
    facts.append(label, content);
  };
  fact("Command", r.id);
  fact("Journal batch", `#${r.sequence}`);
  fact("Processing replica", r.instance);
  fact("Recorded at", new Date(row.at).toLocaleString());
  fact("Booking / value day", `${row.booked_day} / ${row.value_day}`);
  const currency = r.command?.currency;
  if (r.decision && currency) {
    fact("Balance before", money(r.decision.balance_before, currency));
    fact("Reserved before", money(r.decision.held_before, currency));
    fact("Available before", money(r.decision.available_before, currency));
    if (r.kind !== "reversal")
      fact("Amount checked", money(r.decision.requested_minor, currency));
  } else {
    line(
      "p",
      "Pre-decision balance evidence was not recorded for this batch. It may predate this feature or have failed input validation.",
      "note",
    );
  }
  if (r.calculation && currency) {
    const c = r.calculation;
    line("h4", "Illustrative tax · synthetic rule");
    line(
      "p",
      `${money(c.net, currency)} net + ${money(c.tax, currency)} tax = ${money(c.gross, currency)} gross`,
      "calculation",
    );
    line(
      "p",
      `Rate ${c.numerator}/${c.denominator}. ${c.rounding}. ${c.policy}. Not tax-compliance advice.`,
      "note",
    );
  }
  if (r.kind === "capture" && currency && r.status === "accepted") {
    line(
      "p",
      `${money(r.captured || "0", currency)} captured · ${money(r.released || "0", currency)} released`,
    );
  }
  if (r.kind === "split_transfer")
    line(
      "p",
      "Parts share one value date. Extra minor units go to the first parts; nothing is discarded.",
      "note",
    );
  line("h4", "Accounting entries");
  for (const leg of r.legs) {
    const units = BigInt(leg.units);
    line(
      "p",
      `${units > 0n ? "Debit" : "Credit"} ${leg.account} · ${money((units < 0n ? -units : units).toString(), leg.currency)}`,
      "entry-line",
    );
  }
  if (!r.legs.length) line("p", "No monetary legs.");
  const details = document.createElement("details");
  const summary = document.createElement("summary"),
    raw = document.createElement("pre");
  summary.textContent = "Stored evidence";
  raw.textContent = JSON.stringify(row, null, 2);
  details.append(summary, raw);
  panel.append(details);
  line(
    "p",
    "This is journal evidence, not a complete HTTP-attempt history. Identical retries return the original outcome without another monetary batch.",
    "note",
  );
}
$("journal").addEventListener("click", (event) => {
  const button = (event.target as HTMLElement).closest<HTMLButtonElement>(
    "button[data-sequence]",
  );
  const row = journalRows.find(
    (row) => row.result.sequence === button?.dataset.sequence,
  );
  if (row) {
    inspectEvent(row);
    $("journal")
      .querySelectorAll<HTMLButtonElement>("button[data-sequence]")
      .forEach((element) => {
        const selected = element.dataset.sequence === row.result.sequence;
        element.setAttribute("aria-pressed", String(selected));
        element.closest("tr")?.classList.toggle("selected-event", selected);
      });
  }
});
async function refresh() {
  try {
    const [status, list] = await Promise.all([api("status"), api("accounts")]);
    accounts = list;
    accountSummary();
    if (!$<HTMLSelectElement>("source").options.length) choices();
    else destinations();
    $("connection").textContent = "● Connected · " + status.serving_instance;
    $("batches").textContent = status.sequence;
    $("pending").textContent = String(status.pending_deliveries);
    $("db-size").textContent =
      (status.database_bytes / 1048576).toFixed(1) + " MiB";
    if (document.activeElement !== $("eps")) {
      $<HTMLInputElement>("eps").value = String(status.eps);
      $("rate").textContent = String(status.eps);
    }
    $("guard").textContent = !status.host_guard?.safe
      ? status.host_guard?.reason || "Host safety lease stale"
      : status.guard_fresh
        ? "Host + DB checks clear"
        : status.guard_reason || "DB guard stale";
    $("replicas").innerHTML = status.replicas
      .map(
        (r: any) =>
          `<div class="node ${r.healthy ? "" : "unhealthy"}"><strong>${esc(r.id)}</strong><span>${r.healthy ? "● Online" : "○ Stale heartbeat"} · ${(r.heap_bytes / 1048576).toFixed(1)} MiB Go heap</span></div>`,
      )
      .join("");
    await journal();
    if (Date.now() - analyticsUpdated > 10000) await analytics();
  } catch (e) {
    $("connection").textContent = "○ Connection unavailable";
    console.error(e);
  }
}
$("source").addEventListener("change", destinations);
$("view-currency").addEventListener("change", () => {
  selectedEvent = undefined;
  $("event-inspector").textContent =
    "Select a batch number to inspect its decision and entries.";
  choices();
  accountSummary();
  void analytics();
  journal().catch((e) => toast(e.message));
});
$("view-window").addEventListener("change", () => {
  void analytics();
});
$("account-list").addEventListener("click", (event) => {
  const button = (event.target as HTMLElement).closest<HTMLButtonElement>(
    "button[data-account]",
  );
  if (!button) return;
  $<HTMLSelectElement>("statement").value = button.dataset.account!;
  $("audit").scrollIntoView();
  journal().catch((e) => toast(e.message));
});
$("statement").addEventListener("change", () =>
  journal().catch((e) => toast(e.message)),
);
$("eps").addEventListener(
  "input",
  () => ($("rate").textContent = $<HTMLInputElement>("eps").value),
);
$("apply-rate").addEventListener("click", async () => {
  try {
    await api("controls", { eps: Number($<HTMLInputElement>("eps").value) });
    toast("Shared rate updated");
  } catch (e) {
    toast((e as Error).message);
  }
});
$("transfer-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const a = accounts.find(
    (a) => a.id === $<HTMLSelectElement>("source").value,
  )!;
  const button = $("transfer-form").querySelector("button")!;
  button.disabled = true;
  try {
    const r: Outcome = await api("commands", {
      id: crypto.randomUUID(),
      kind: "transfer",
      account: a.id,
      destination: $<HTMLSelectElement>("destination").value,
      currency: a.currency,
      amount: $<HTMLInputElement>("amount").value,
      booked_day: 1,
      value_day: 1,
    });
    $("transfer-result").textContent =
      `${r.status} · batch #${r.sequence} · ${r.instance}${r.reason ? " · " + r.reason : ""}`;
    await refresh();
  } catch (e) {
    toast((e as Error).message);
  } finally {
    button.disabled = false;
  }
});
$("pause-outbox").addEventListener("click", async () => {
  try {
    await api("chaos/outbox", {});
    toast("Delivery paused for 15 seconds. Watch the backlog.");
  } catch (e) {
    toast((e as Error).message);
  }
});
$("reconcile").addEventListener("click", async () => {
  try {
    const r = await api("reconciliation");
    $("reconciled").textContent = r.ok ? "Balanced" : "Mismatch";
    $("reconciliation").textContent =
      `At batch #${r.cutoff}\nBalance differences: ${r.balance_discrepancies}\nUnbalanced batches: ${r.unbalanced_batches}\nHold differences: ${r.hold_discrepancies}\n${r.scope}`;
  } catch (e) {
    toast((e as Error).message);
  }
});
async function poll() {
  await refresh();
  setTimeout(poll, 2500);
}
poll();

let fixtureRequest = 0;
async function showFixture() {
  const request = ++fixtureRequest;
  const known = $<HTMLInputElement>("knowledge").value;
  $("knowledge-label").textContent = known;
  const state = await api("fixture?known=" + known);
  if (request !== fixtureRequest) return;
  $("fixture-days").replaceChildren(
    ...state.daily.map((day: { day: number; AED: string; BHD: string }) => {
      const row = document.createElement("tr");
      for (const text of [
        "Day " + day.day,
        money(day.AED, "AED"),
        money(day.BHD, "BHD"),
      ]) {
        const cell = document.createElement("td");
        cell.textContent = text;
        row.append(cell);
      }
      return row;
    }),
  );
  const last = state.batches[0];
  if (!last) {
    $("fixture-batch").textContent =
      "No records known yet. Both accounts start at zero.";
    return;
  }
  const result = last.result;
  const legs = result.legs.map(
    (leg: {
      units: string;
      account: string;
      currency: string;
      value_day: number;
      kind: string;
    }) => {
      const units = BigInt(leg.units);
      return `${units > 0n ? "Debit " : "Credit"} ${leg.account} · ${money((units < 0n ? -units : units).toString(), leg.currency)} · value Day ${leg.value_day} · ${leg.kind}`;
    },
  );
  $("fixture-batch").textContent =
    `Batch #${last.sequence}: ${result.id} · ${result.status}\n${result.reason || ""}\n${legs.join("\n") || "No monetary posting. The decision is still recorded."}`;
}
let fixtureTimer: ReturnType<typeof setTimeout>;
$("knowledge").addEventListener("input", () => {
  clearTimeout(fixtureTimer);
  fixtureTimer = setTimeout(
    () => showFixture().catch((error) => toast(error.message)),
    180,
  );
});
showFixture().catch((error) => {
  $("fixture-batch").textContent = error.message;
});
