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
};
const $ = <T extends HTMLElement = HTMLElement>(id: string) =>
  document.getElementById(id) as T;
let accounts: Account[] = [];
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
    .filter((a) => a.customer)
    .map(
      (a) =>
        `<option value="${esc(a.id)}">${esc(a.name)} / ${a.id} / ${a.currency}</option>`,
    )
    .join("");
  if (previous) source.value = previous;
  destinations();
  const statement = $<HTMLSelectElement>("statement"),
    v = statement.value;
  statement.innerHTML =
    '<option value="">All accounts</option>' +
    accounts
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
  const rows = await api(
    "journal?account=" +
      encodeURIComponent($<HTMLSelectElement>("statement").value),
  );
  $("journal").innerHTML = rows
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
      return `<tr><td>#${r.sequence}<small>${new Date(row.at).toLocaleTimeString()}</small></td><td>${esc(r.kind)}<small>${esc(r.id)}</small></td><td class="${esc(r.status)}">${esc(r.status)}<small>${esc(r.reason || "")}</small></td><td>${legs(true)}</td><td>${legs(false)}</td><td>${esc(r.instance)}</td></tr>`;
    })
    .join("");
}
async function refresh() {
  try {
    const [status, list] = await Promise.all([api("status"), api("accounts")]);
    accounts = list;
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
    $("guard").textContent = status.guard_fresh
      ? "Within DB budget"
      : status.guard_reason || "Guard stale";
    $("replicas").innerHTML = status.replicas
      .map(
        (r: any) =>
          `<div class="node ${r.healthy ? "" : "unhealthy"}"><strong>${esc(r.id)}</strong><span>${r.healthy ? "● Online" : "○ Stale heartbeat"} · ${(r.heap_bytes / 1048576).toFixed(1)} MiB Go heap</span></div>`,
      )
      .join("");
    await journal();
  } catch (e) {
    $("connection").textContent = "○ Connection unavailable";
    console.error(e);
  }
}
$("source").addEventListener("change", destinations);
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
