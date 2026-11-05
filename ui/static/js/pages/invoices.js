// Invoices: AG Grid (custom dark theme via CSS variables) over plan items + PayPal state. Plain-table fallback.
import { api, poll } from "../api.js";
import { buildModel } from "../derive.js";
import { mockDashboard } from "../mock.js";
import { setViewCounts } from "../shell.js";
import { $, esc, icon, money, pct, fmtDay, daysBetween, avatar, statusPill, confirmedByPayPal, toast, cardState, countUp, plural, sameData } from "../util.js";

const BOOT = window.FLOAT_BOOT || {};
let raw = null, model = null, view = "all", gridApi = null, last = null;

const FILTERS = {
  all: () => true,
  risk: (r) => r.atRisk,
  discounted: (r) => r.discount_pct > 0,
  paid: (r) => r.status === "paid",
};

async function load(tick = false) {
  let p;
  try { p = await api.dashboard({ tick }); } catch (e) {
    if (!raw) { cardState($("#card-grid"), "error", { message: e.message, retry: () => load() }); return; }
    toast(e.message, "err"); return;
  }
  if (!p.plan) p = { ...mockDashboard(p.today), clients: p.clients?.length ? p.clients : mockDashboard().clients };
  raw = p;
  model = buildModel(p);
  render();
}

function rows() {
  return model.items.map((i) => ({ ...i, lateDays: daysBetween(i.due, i.expected), clients: raw.clients }));
}

function render() {
  const m = model, rs = rows();
  const alerts = $("#alerts");
  alerts.innerHTML = m.sample
    ? `<div class="alert ice">${icon("sparkle")}<div><div class="alert-t">Sample invoices</div><div class="alert-s">No goal yet. Ask Float for one on the dashboard; these rows are an example.</div></div></div>`
    : !m.launched ? `<div class="alert ice">${icon("sparkle")}<div><div class="alert-t">Preview · drafts only</div><div class="alert-s">Nothing has been sent. Run the plan on the dashboard to issue these through PayPal Invoicing.</div></div></div>` : "";
  const sub = $("#card-grid [data-sub]");
  if (sub) sub.textContent = m.goal.amount ? `${money(m.goal.amount)} by ${fmtDay(m.goal.deadline)}` : "no goal";

  const live = rs.filter((r) => r.status !== "cancelled");
  countUp($("#s-inv"), live.reduce((s, r) => s + r.amount, 0), (v) => money(v));
  $("#s-inv-n").textContent = plural(live.length, "invoice");
  const paid = rs.filter(FILTERS.paid);
  countUp($("#s-paid"), paid.reduce((s, r) => s + r.amount, 0), (v) => money(v));
  $("#s-paid-n").textContent = `${paid.length} of ${live.length}`;
  const risk = rs.filter(FILTERS.risk);
  countUp($("#s-risk"), risk.reduce((s, r) => s + r.amount, 0), (v) => money(v));
  $("#s-risk-n").textContent = plural(risk.length, "invoice");
  countUp($("#s-disc"), m.totalDiscountCost, (v) => money(v, { cents: true }));
  $("#s-disc-n").textContent = plural(rs.filter(FILTERS.discounted).length, "early-pay offer");
  setViewCounts(Object.fromEntries(Object.entries(FILTERS).map(([k, f]) => [k, rs.filter(f).length])));

  if (sameData(last, rs.map(({ clients, ...r }) => r))) return;
  last = rs.map(({ clients, ...r }) => r);
  cardState($("#card-grid"), "ready");
  if (window.agGrid) renderGrid(rs); else renderPlain(rs);
}

// ---------------------------------------------------------------- AG Grid
const canPay = () => BOOT.mode && BOOT.mode.can_simulate_payment && model && model.launched;

function columns() {
  return [
    { headerName: "Client", field: "name", minWidth: 190, flex: 1.3,
      cellRenderer: (p) => `<div class="cl-cell">${avatar(p.data.client_id, p.data.clients, "")}<div class="cell-stack"><span class="nm">${esc(p.data.name)}</span><span class="sub">${esc(p.data.invoice_id)}${p.data.reissued ? " · re-sent" : ""}</span></div></div>` },
    { headerName: "Amount", field: "amount", type: "rightAligned", minWidth: 120, flex: 0.8,
      cellRenderer: (p) => `<div class="cell-stack" style="align-items:flex-end"><span>${money(p.value, { cents: true })}</span>${p.data.amount !== p.data.original ? `<span class="sub" style="text-decoration:line-through;color:var(--muted);font-size:11px">${money(p.data.original, { cents: true })}</span>` : ""}</div>` },
    { headerName: "Due", field: "due", minWidth: 110, flex: 0.7, valueFormatter: (p) => fmtDay(p.value) },
    { headerName: "Predicted pay date", field: "expected", minWidth: 170, flex: 1,
      tooltipValueGetter: (p) => p.data.reason,
      cellRenderer: (p) => `<div class="cell-stack"><span class="${p.data.atRisk ? "t-amber" : ""}">${esc(fmtDay(p.value))}</span><span class="sub" style="font-size:11px;color:var(--muted)">${p.data.lateDays > 0 ? `~${p.data.lateDays}d late` : "on time"}${p.data.atRisk ? " · after deadline" : ""}</span></div>` },
    { headerName: "Status", field: "status", minWidth: 170, flex: 1,
      cellRenderer: (p) => `<div class="cell-stack" style="gap:3px">${statusPill(p.value)}${p.value === "paid" ? confirmedByPayPal() : ""}</div>` },
    { headerName: "Offer", field: "discount_pct", minWidth: 120, flex: 0.8,
      tooltipValueGetter: (p) => p.data.reason,
      cellRenderer: (p) => p.value > 0 ? `<span class="pill v-allow" title="${esc(p.data.reason)}">${icon("percent")}${pct(p.value)} off</span>` : `<span class="t-muted" title="${esc(p.data.reason)}">reminder</span>` },
    { headerName: "PayPal ref", field: "paypal_id", minWidth: 150, flex: 0.9,
      cellRenderer: (p) => p.value ? `<span class="mono">${esc(p.value)}</span>` : `<span class="t-muted">not sent</span>` },
    { headerName: "", field: "key", minWidth: 130, maxWidth: 150, sortable: false, hide: !canPay(),
      cellRenderer: (p) => p.data.status === "unpaid" ? `<button class="btn sm" type="button" data-pay="${esc(p.value)}" title="Offline demo: pretend the client paid in PayPal">${icon("zap")}Client pays</button>` : "" },
  ];
}

function renderGrid(rs) {
  const host = $("#grid");
  if (!gridApi) {
    gridApi = window.agGrid.createGrid(host, {
      columnDefs: columns(), rowData: rs, animateRows: true, tooltipShowDelay: 250, suppressCellFocus: false,
      defaultColDef: { sortable: true, resizable: true, suppressHeaderMenuButton: true },
      isExternalFilterPresent: () => view !== "all",
      doesExternalFilterPass: (node) => FILTERS[view](node.data),
      rowClassRules: { "row-risk": (p) => p.data.atRisk, "row-offer": (p) => p.data.offer && !p.data.atRisk },
      getRowId: (p) => p.data.invoice_id,
      overlayNoRowsTemplate: `<span class="t-muted">No invoices match this filter.</span>`,
    });
    host.addEventListener("click", onPayClick);
  } else {
    gridApi.setGridOption("columnDefs", columns());
    gridApi.setGridOption("rowData", rs);
  }
}

function renderPlain(rs) {
  const host = $("#grid");
  host.classList.remove("grid-host");
  const list = rs.filter(FILTERS[view]);
  host.innerHTML = `<div class="scroll-x"><table class="plain-grid"><thead><tr><th>Client</th><th>Amount</th><th>Due</th><th>Predicted</th><th>Status</th><th>Offer</th><th>PayPal ref</th><th></th></tr></thead><tbody>
    ${list.map((r) => `<tr><td><div class="cl-cell">${avatar(r.client_id, r.clients, "")}<div class="cell-stack"><span class="nm">${esc(r.name)}</span><span class="label-xs">${esc(r.invoice_id)}</span></div></div></td>
      <td class="num">${money(r.amount, { cents: true })}</td><td>${esc(fmtDay(r.due))}</td><td class="${r.atRisk ? "t-amber" : ""}" title="${esc(r.reason)}">${esc(fmtDay(r.expected))}</td>
      <td>${statusPill(r.status)} ${r.status === "paid" ? confirmedByPayPal() : ""}</td><td title="${esc(r.reason)}">${r.discount_pct > 0 ? pct(r.discount_pct) + " off" : "—"}</td>
      <td class="mono">${esc(r.paypal_id || "—")}</td><td>${canPay() && r.status === "unpaid" ? `<button class="btn sm" data-pay="${esc(r.key)}">Client pays</button>` : ""}</td></tr>`).join("") || `<tr><td colspan="8" class="t-muted">No invoices match this filter.</td></tr>`}
    </tbody></table></div><p class="label-xs" style="margin-top:10px">Table view (the grid library couldn't load).</p>`;
  host.onclick = onPayClick;
}

async function onPayClick(e) {
  const b = e.target.closest("[data-pay]");
  if (!b) return;
  b.disabled = true;
  try {
    await api.pay(b.dataset.pay);
    toast("Fake PayPal marked it paid. Float will confirm on its next PayPal check.", "info");
    await load(true);
  } catch (err) { toast(err.message, "err"); b.disabled = false; }
}

document.addEventListener("float:view", (e) => {
  view = e.detail.view;
  if (gridApi) gridApi.onFilterChanged(); else if (model) renderPlain(rows());
});
$("#card-grid [data-action=refresh]")?.addEventListener("click", () => load(true).then(() => toast("Checked PayPal.", "info", 2000)));

cardState($("#card-grid"), "loading");
window.addEventListener("load", () => load(false).then(() => poll(() => load(!!(model && model.launched)), (BOOT.mode && BOOT.mode.poll_seconds) || 6)));
