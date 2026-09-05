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
let detailTab = "summary";
let journalPaused = false;
let journalRequest = 0;
let seenSequences = new Set<string>();
let returnFocus: HTMLElement | null = null;
let rateDirty = false;
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

// Routes move the existing controls, never clone their state or reload the app.
const routes: Record<string, { title: string; panels: string[] }> = {
  overview: {
    title: "Overview",
    panels: [
      "simulation-panel",
      "chart-panel",
      "totals-panel",
      "accounts-view",
      "health-panel",
      "transfer-view",
      "audit",
      "inspector-shell",
    ],
  },
  journal: { title: "Journal", panels: ["audit", "inspector-shell"] },
  accounts: { title: "Accounts", panels: ["accounts-view", "totals-panel"] },
  transfers: {
    title: "Transfers",
    panels: ["transfer-view", "audit", "inspector-shell"],
  },
  system: {
    title: "System & recovery",
    panels: [
      "system-view",
      "health-panel",
      "recovery-panel",
      "reconciliation-panel",
      "scope-panel",
    ],
  },
  time: { title: "Time laboratory", panels: ["time-view", "scope-panel"] },
};
function closeInspector() {
  $("inspector-shell").classList.remove("drawer-open");
  $("inspector-shell").removeAttribute("role");
  $("inspector-shell").removeAttribute("aria-modal");
  $("inspector-backdrop").hidden = true;
  document.querySelector<HTMLElement>(".app-shell")!.inert = false;
  $("navigation").inert = matchMedia("(max-width: 1023px)").matches;
  document.body.classList.remove("inspector-open");
  const current = routes[document.body.dataset.view || "overview"];
  $(
    current?.panels.includes("inspector-shell")
      ? "route-grid"
      : "panel-storage",
  ).append($("inspector-shell"));
  if (returnFocus?.isConnected) returnFocus.focus();
  else if (selectedEvent)
    Array.from(document.querySelectorAll<HTMLButtonElement>("[data-sequence]"))
      .find(
        (button) =>
          button.dataset.sequence === selectedEvent?.result.sequence &&
          button.getClientRects().length,
      )
      ?.focus();
  returnFocus = null;
}
function navigation(open: boolean) {
  document.body.classList.toggle("nav-open", open);
  $("nav-backdrop").hidden = !open;
  $("menu-toggle").setAttribute("aria-expanded", String(open));
  document.querySelector<HTMLElement>(".app-shell")!.inert = open;
  $("navigation").inert = !open && matchMedia("(max-width: 1023px)").matches;
  if (open) $("navigation").querySelector<HTMLElement>("a")?.focus();
}
function route() {
  const key = location.hash.slice(1) || "overview";
  if (key === "workspace") {
    $("workspace").focus();
    return;
  }
  const selected = routes[key] ? key : "overview";
  closeInspector();
  navigation(false);
  const grid = $("route-grid"),
    storage = $("panel-storage");
  Array.from(grid.children).forEach((panel) => storage.append(panel));
  routes[selected].panels.forEach((id) => grid.append($(id)));
  document.body.dataset.view = selected;
  $("view-title").textContent = routes[selected].title;
  grid.setAttribute("aria-label", routes[selected].title + " workspace");
  document.title = `${routes[selected].title} · Ledger Lab`;
  document
    .querySelectorAll<HTMLAnchorElement>("[data-route]")
    .forEach((link) => {
      if (link.dataset.route === selected)
        link.setAttribute("aria-current", "page");
      else link.removeAttribute("aria-current");
    });
  window.scrollTo({ top: 0 });
}
window.addEventListener("hashchange", route);
matchMedia("(min-width: 1280px)").addEventListener("change", closeInspector);
matchMedia("(min-width: 1024px)").addEventListener("change", () =>
  navigation(false),
);
$("menu-toggle").addEventListener("click", () =>
  navigation(!document.body.classList.contains("nav-open")),
);
$("nav-backdrop").addEventListener("click", () => navigation(false));
$("close-inspector").addEventListener("click", closeInspector);
$("inspector-backdrop").addEventListener("click", closeInspector);
document.addEventListener("keydown", (event) => {
  if (event.key === "Escape") {
    closeInspector();
    navigation(false);
  }
  if ((event.metaKey || event.ctrlKey) && event.key === "k") {
    event.preventDefault();
    $("search").focus();
  }
  const modal = $("inspector-shell").classList.contains("drawer-open")
    ? $("inspector-shell")
    : document.body.classList.contains("nav-open")
      ? $("navigation")
      : null;
  if (event.key === "Tab" && modal) {
    const items = Array.from(
      modal.querySelectorAll<HTMLElement>(
        'button:not([disabled]):not([tabindex="-1"]), a[href], input, select, [tabindex="0"]',
      ),
    ).filter((el) => el.getClientRects().length);
    const first = items[0],
      last = items.at(-1);
    if (event.shiftKey && document.activeElement === first) {
      event.preventDefault();
      last?.focus();
    } else if (!event.shiftKey && document.activeElement === last) {
      event.preventDefault();
      first?.focus();
    }
  }
});
$("more-metrics").addEventListener("click", () => {
  const expanded = document
    .querySelector(".metrics")!
    .classList.toggle("expanded");
  $("more-metrics").setAttribute("aria-expanded", String(expanded));
  $("more-metrics").textContent = expanded ? "Fewer metrics" : "More metrics";
});
function updateMetric(id: string, value: string) {
  const node = $(id);
  if (node.textContent === value) return;
  node.textContent = value;
  const card = node.closest(".metric");
  card?.classList.remove("updated");
  requestAnimationFrame(() => card?.classList.add("updated"));
}
function rangeFill() {
  const input = $<HTMLInputElement>("eps");
  input.style.setProperty(
    "--range-fill",
    `${(Number(input.value) / Number(input.max)) * 100}%`,
  );
}

// Counts only: monetary calculations stay in integer minor units below.
function chart(
  id: string,
  rows: Bucket[],
  value: (row: Bucket) => number,
  data: Analytics,
) {
  const values = rows.map(value);
  const maximum = Math.max(1, ...values);
  const negativeValues = rows.map((row) => row.declined + row.rejected);
  const points = negativeValues
    .map(
      (v, i) =>
        `${40 + (i * 510) / Math.max(1, values.length - 1)},${145 - (v / maximum) * 125}`,
    )
    .join(" ");
  const label = `${values.reduce((a, b) => a + b, 0)} decisions in ${data.bucket_seconds}-second buckets`;
  const target = $(id);
  const columns = values
    .map(
      (v, i) =>
        `<rect class="chart-bar" x="${40 + (i * 510) / Math.max(1, values.length)}" y="${145 - (v / maximum) * 125}" width="${Math.max(1, 510 / Math.max(1, values.length) - 2)}" height="${(v / maximum) * 125}" rx="1"><title>${esc(new Date(rows[i].at).toLocaleString())}: ${v} decisions; ${negativeValues[i]} declined or rejected</title></rect>`,
    )
    .join("");
  target.innerHTML = `<svg viewBox="0 0 560 165" role="img" aria-label="${esc(label)}"><title>${esc(label)}. Bars: all decisions. Pink line: declined plus rejected.</title><path class="chart-grid" d="M40 20H550 M40 51H550 M40 82.5H550 M40 114H550 M40 145H550"/><text x="0" y="24">${maximum}</text><text x="20" y="149">0</text>${columns}<polyline class="chart-line" points="${points}"/></svg><div class="chart-footer"><span>${esc(new Date(data.since).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }))}</span><span>${data.bucket_seconds}s / bucket</span><span>${esc(new Date(data.through).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }))}</span></div>`;
  $("metric-spark").innerHTML =
    `<svg viewBox="0 0 100 24" aria-hidden="true"><polyline fill="none" stroke="currentColor" stroke-width="1.5" points="${values.map((v, i) => `${(i * 100) / Math.max(1, values.length - 1)},${23 - (v / maximum) * 22}`).join(" ")}" /></svg>`;
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
    updateMetric("event-total", total.toLocaleString());
    updateMetric("event-negative", negative.toLocaleString());
    const accepted = data.buckets.reduce((sum, b) => sum + b.accepted, 0);
    updateMetric(
      "accepted-rate",
      total ? `${((accepted / total) * 100).toFixed(1)}%` : "—",
    );
    $("totals-currency").textContent = data.currency;
    chart("events-chart", data.buckets, (b) => b.total, data);
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
      `${data.currency} · PostgreSQL journal · ${data.bucket_seconds}s buckets · updated ${new Date(data.through).toLocaleTimeString()}${total === 0 ? " · No recorded decisions in this window." : ""}`;
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
  if (journalPaused) return;
  const request = ++journalRequest;
  const selectedCurrency = viewCurrency();
  const rows = await api(
    "journal?account=" +
      encodeURIComponent($<HTMLSelectElement>("statement").value),
  );
  if (
    selectedCurrency !== viewCurrency() ||
    request !== journalRequest ||
    journalPaused
  )
    return;
  journalRows = rows.filter(
    (row: JournalRow) =>
      row.result.command?.currency === selectedCurrency ||
      (!row.result.command?.currency &&
        row.result.legs.some((leg) => leg.currency === selectedCurrency)),
  );
  renderJournal();
  seenSequences = new Set(journalRows.map((row) => row.result.sequence));
}
function renderJournal() {
  const query = $<HTMLInputElement>("search").value.trim().toLowerCase();
  const displayed = journalRows.filter(
    (row) =>
      !query ||
      [
        row.result.id,
        row.result.sequence,
        row.result.kind,
        row.result.status,
        row.result.reason,
        row.result.instance,
        ...row.result.legs.map((l) => l.account),
      ]
        .join(" ")
        .toLowerCase()
        .includes(query),
  );
  const rowClass = (row: JournalRow) =>
    `${selectedEvent?.result.sequence === row.result.sequence ? "selected-event" : ""} ${seenSequences.size && !seenSequences.has(row.result.sequence) ? "new-event" : ""}`;
  $("journal").innerHTML =
    displayed
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
        return `<tr class="${rowClass(row)}" data-outcome="${esc(r.status)}"><td><button class="inspect-event" data-sequence="${esc(r.sequence)}" aria-label="Inspect ${esc(r.id)}" aria-pressed="${selectedEvent?.result.sequence === r.sequence}">#${r.sequence}</button><small>${new Date(row.at).toLocaleTimeString()}</small></td><td>${esc(r.kind)}<small title="${esc(r.id)}">${esc(r.id)}</small></td><td class="${esc(r.status)}">${esc(r.status)}<small title="${esc(r.reason || "")}">${esc(r.reason || "")}</small></td><td>${legs(true)}</td><td>${legs(false)}</td><td>${esc(r.instance)}</td></tr>`;
      })
      .join("") ||
    '<tr><td colspan="6">No matching decisions in this latest-batch preview.</td></tr>';
  $("journal-cards").innerHTML =
    displayed
      .map((row) => {
        const r = row.result;
        const amount = r.command?.amount
          ? `${r.command.amount} ${r.command.currency}`
          : "No requested amount recorded";
        return `<button class="event-card ${rowClass(row)}" data-sequence="${esc(r.sequence)}" data-outcome="${esc(r.status)}" aria-label="Inspect batch ${esc(r.sequence)}" aria-pressed="${selectedEvent?.result.sequence === r.sequence}"><span><strong>#${esc(r.sequence)}</strong><small>${new Date(row.at).toLocaleTimeString()}</small></span><span>${esc(r.kind)}<strong class="${esc(r.status)}">${esc(r.status)}</strong></span><span>${esc(amount)}</span><span class="event-accounts">${esc(r.command?.account || "")}${r.command?.destination ? " → " + esc(r.command.destination) : ""}</span><small>${esc(r.instance)} · batch #${esc(r.sequence)}</small></button>`;
      })
      .join("") ||
    '<div class="empty-state"><span>◇</span><h3>No matching decisions</h3><p>Try another account or search within the latest journal preview.</p></div>';
  $("journal-scope").textContent =
    `${journalPaused ? "Display paused. " : ""}${displayed.length} matching decisions from the latest 60 fetched batches. Currency + search + account filters; not the chart time window.`;
}
function inspectEvent(row: JournalRow, open = true) {
  selectedEvent = row;
  const r = row.result;
  const panel = $("event-inspector");
  panel.replaceChildren();
  let section = "shared";
  const line = (tag: string, value: string, className = "") => {
    const element = document.createElement(tag);
    element.textContent = value;
    element.className = className;
    element.dataset.detailSection = section;
    panel.append(element);
    return element;
  };
  line("p", `${r.kind} · ${new Date(row.at).toLocaleTimeString()}`, "eyebrow");
  line("h3", `#${r.sequence} · ${r.status}`, r.status);
  section = "summary";
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
  facts.dataset.detailSection = "summary";
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
  section = "accounting";
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
  if (r.legs.length) {
    const sums = new Map<string, bigint>();
    r.legs.forEach((leg) =>
      sums.set(
        leg.currency,
        (sums.get(leg.currency) || 0n) + BigInt(leg.units),
      ),
    );
    const balanced = Array.from(sums.values()).every((n) => n === 0n);
    line(
      "p",
      balanced
        ? "✓ Balanced · debits equal credits in each currency."
        : "Accounting discrepancy in these recorded legs.",
      balanced ? "balanced-evidence" : "no-movement",
    );
  }
  line(
    "p",
    "Bank-side credit increases a customer deposit liability. These signs are not customer balance signs.",
    "note",
  );
  const details = document.createElement("details");
  details.dataset.detailSection = "evidence";
  details.open = true;
  const summary = document.createElement("summary"),
    raw = document.createElement("pre");
  summary.textContent = "Stored evidence";
  raw.textContent = JSON.stringify(row, null, 2);
  details.append(summary, raw);
  panel.append(details);
  section = "evidence";
  line(
    "p",
    "This is journal evidence, not a complete HTTP-attempt history. Identical retries return the original outcome without another monetary batch.",
    "note",
  );
  panel
    .querySelectorAll<HTMLElement>("[data-detail-section]")
    .forEach(
      (el) =>
        (el.hidden =
          el.dataset.detailSection !== "shared" &&
          el.dataset.detailSection !== detailTab),
    );
  if (open && matchMedia("(max-width: 1279px)").matches) {
    returnFocus = document.activeElement as HTMLElement;
    $("inspector-shell").classList.add("drawer-open");
    $("inspector-shell").setAttribute("role", "dialog");
    $("inspector-shell").setAttribute("aria-modal", "true");
    $("inspector-backdrop").hidden = false;
    document.body.append($("inspector-shell"));
    document.querySelector<HTMLElement>(".app-shell")!.inert = true;
    $("navigation").inert = true;
    document.body.classList.add("inspector-open");
    $("close-inspector").focus();
  }
}
function selectJournalEvent(event: Event) {
  const button = (event.target as HTMLElement).closest<HTMLButtonElement>(
    "button[data-sequence]",
  );
  const row = journalRows.find(
    (row) => row.result.sequence === button?.dataset.sequence,
  );
  if (row) {
    inspectEvent(row);
    renderJournal();
  }
}
$("journal").addEventListener("click", selectJournalEvent);
$("journal-cards").addEventListener("click", selectJournalEvent);
document
  .querySelectorAll<HTMLButtonElement>("[data-detail]")
  .forEach((button, index, buttons) => {
    button.addEventListener("click", () => {
      detailTab = button.dataset.detail!;
      buttons.forEach((b) => {
        const selected = b === button;
        b.setAttribute("aria-selected", String(selected));
        b.tabIndex = selected ? 0 : -1;
      });
      $("event-inspector").setAttribute("aria-labelledby", button.id);
      if (selectedEvent) inspectEvent(selectedEvent, false);
    });
    button.addEventListener("keydown", (event) => {
      if (!["ArrowLeft", "ArrowRight", "Home", "End"].includes(event.key))
        return;
      event.preventDefault();
      const next =
        event.key === "Home"
          ? 0
          : event.key === "End"
            ? buttons.length - 1
            : (index + (event.key === "ArrowRight" ? 1 : -1) + buttons.length) %
              buttons.length;
      buttons[next].click();
      buttons[next].focus();
    });
  });
$("search").addEventListener("input", () => {
  if (
    location.hash !== "#journal" &&
    location.hash !== "#overview" &&
    location.hash !== "#transfers"
  )
    location.hash = "journal";
  renderJournal();
});
$("journal-pause").addEventListener("click", () => {
  journalPaused = !journalPaused;
  $("journal-pause").setAttribute("aria-pressed", String(journalPaused));
  $("journal-pause").setAttribute(
    "aria-label",
    journalPaused ? "Resume journal display" : "Pause journal display",
  );
  $("journal-pause").textContent = journalPaused ? "▶" : "Ⅱ";
  if (journalPaused) renderJournal();
  else void journal().catch((e) => toast(e.message));
});
async function refresh() {
  try {
    const [status, list] = await Promise.all([api("status"), api("accounts")]);
    accounts = list;
    accountSummary();
    if (!$<HTMLSelectElement>("source").options.length) choices();
    else destinations();
    $("connection").textContent = "● Live · " + status.serving_instance;
    document.body.classList.remove("connection-lost");
    $("clock").textContent = new Date().toLocaleString();
    updateMetric("batches", BigInt(status.sequence).toLocaleString());
    updateMetric("pending", String(status.pending_deliveries));
    updateMetric(
      "db-size",
      (status.database_bytes / 1048576).toFixed(1) + " MiB",
    );
    updateMetric("rate-kpi", String(status.eps));
    $("outbox-health").textContent = status.pending_deliveries
      ? `${status.pending_deliveries} pending`
      : "No backlog";
    $("footer-state").textContent =
      `Last refresh ${new Date().toLocaleTimeString()} · ${status.serving_instance}`;
    if (!rateDirty && document.activeElement !== $("eps")) {
      $<HTMLInputElement>("eps").value = String(status.eps);
      $("rate").textContent = String(status.eps);
      rangeFill();
    }
    $("guard").textContent = !status.host_guard?.safe
      ? status.host_guard?.reason || "Host safety lease stale"
      : status.guard_fresh
        ? "Host + DB checks clear"
        : status.guard_reason || "DB guard stale";
    $("guard").classList.toggle(
      "unsafe",
      !status.host_guard?.safe || !status.guard_fresh,
    );
    const evidence = status.host_guard?.evidence;
    const hostRows = evidence
      ? [
          [
            "Memory available",
            `${(evidence.available_bytes / 1073741824).toFixed(2)} GiB`,
          ],
          [
            "Disk free",
            `${(evidence.disk_free_bytes / 1073741824).toFixed(1)} GiB`,
          ],
          [
            "Memory pressure",
            `${evidence.memory_full_avg10.toFixed(2)}% full / 10s`,
          ],
          ["I/O pressure", `${evidence.io_full_avg10.toFixed(2)}% full / 10s`],
          [
            "Observed",
            new Date(status.host_guard.observed_at).toLocaleTimeString(),
          ],
        ]
      : [["Evidence", "Unavailable"]];
    $("host-facts").innerHTML = hostRows
      .map(([name, value]) => `<dt>${esc(name)}</dt><dd>${esc(value)}</dd>`)
      .join("");
    $("replicas").innerHTML = status.replicas
      .map(
        (r: any) =>
          `<div class="health-line ${r.healthy ? "" : "unhealthy"}"><span>${esc(r.id)}<small>${(r.heap_bytes / 1048576).toFixed(1)} MiB Go heap</small></span><strong>${r.healthy ? "● Online" : "○ Stale"}</strong></div>`,
      )
      .join("");
    await journal();
    if (Date.now() - analyticsUpdated > 10000) await analytics();
  } catch (e) {
    $("connection").textContent = "○ Connection unavailable";
    document.body.classList.add("connection-lost");
    $("footer-state").textContent =
      "Connection unavailable · displayed values may be stale";
    console.error(e);
  }
}
$("source").addEventListener("change", destinations);
$("view-currency").addEventListener("change", () => {
  selectedEvent = undefined;
  seenSequences.clear();
  journalRows = [];
  renderJournal();
  closeInspector();
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
  location.hash = "journal";
  journal().catch((e) => toast(e.message));
});
$("statement").addEventListener("change", () =>
  journal().catch((e) => toast(e.message)),
);
$("eps").addEventListener("input", () => {
  rateDirty = true;
  $("rate").textContent = $<HTMLInputElement>("eps").value;
  rangeFill();
});
$("pause-simulation").addEventListener("click", async () => {
  try {
    await api("controls", { eps: 0 });
    rateDirty = false;
    $<HTMLInputElement>("eps").value = "0";
    $("rate").textContent = "0";
    rangeFill();
    toast("Shared simulation paused");
    await refresh();
  } catch (e) {
    toast((e as Error).message);
  }
});
$("apply-rate").addEventListener("click", async () => {
  try {
    await api("controls", { eps: Number($<HTMLInputElement>("eps").value) });
    rateDirty = false;
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
route();
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
