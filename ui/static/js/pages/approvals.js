// Approvals: one-tap Approve / Reject cards. The effect of each button is shown BEFORE the click (from the server's
// read-only preview); after the click the real effect and a link to its audit entry replace the buttons.
import { api, poll } from "../api.js";
import { setViewCounts } from "../shell.js";
import { $, $$, esc, icon, fmtTs, avatar, toast, sameData, pct } from "../util.js";

let view = "pending", pending = [], decided = [], audit = [], clients = [], last = null;
const justDone = new Map();   // id -> decide() result, kept on screen after the click

const human = (s) => String(s || "").replace(/_/g, " ");

function facts(a) {
  const p = a.payload || {};
  const rows = [["From", esc(p.sender || "—")]];
  if (p.discount_pct !== null && p.discount_pct !== undefined) rows.push(["Asks for", `${pct(p.discount_pct)} off`]);
  if (p.new_bank_account) rows.push(["New account", `<span class="mono">${esc(p.new_bank_account)}</span>`]);
  if (p.new_due_date) rows.push(["New due date", esc(p.new_due_date)]);
  rows.push(["Email", esc(a.email_id)]);
  return `<dl class="kv">${rows.map(([k, v]) => `<div><dt>${k}</dt><dd>${v}</dd></div>`).join("")}</dl>`;
}

function head(a) {
  return `<div class="card-h">
    ${avatar(a.client_id, clients, "")}
    <div style="min-width:0"><h2 class="card-title">${esc(a.client_name || a.client_id || "Unknown client")}</h2>
      <div class="label">#${esc(a.id)} · ${esc(fmtTs(a.created_at, { date: true }))}</div></div>
    <div class="card-actions"><span class="tag mauve">${esc(human(a.intent))}</span></div>
  </div>`;
}

function pendingCard(a) {
  const done = justDone.get(a.id);
  const pv = a.preview || {};
  return `<article class="card appr" id="ap-${esc(a.id)}" tabindex="0" data-id="${esc(a.id)}" aria-label="Approval ${esc(a.id)} for ${esc(a.client_name)}: ${esc(human(a.intent))}">
    ${head(a)}
    <div class="inner"><div class="label" style="margin-bottom:6px">Why Guard asked you</div>
      <ul class="rules" style="list-style:none;margin:0;padding:0;display:flex;flex-direction:column;gap:6px">${(a.reasons || []).map((r) => `<li class="row" style="flex-wrap:nowrap;align-items:flex-start">${icon("hourglass", "t-amber")}<span class="t-2">${esc(r)}</span></li>`).join("")}</ul></div>
    ${facts(a)}
    <div class="outcome">
      <div class="opt yes"><span class="label">${icon("check")}If you approve</span><span>${esc(pv.approve || "Recorded only.")}</span>${pv.recorded_only ? `<span class="tag amber">recorded only</span>` : ""}</div>
      <div class="opt"><span class="label">${icon("x")}If you reject</span><span>${esc(pv.reject || "Rejecting changes nothing.")}</span></div>
    </div>
    ${done ? doneBox(done) : `<div class="actions">
      <button class="btn lime" type="button" data-decide="1">${icon("check")}Approve</button>
      <button class="btn coral" type="button" data-decide="0">${icon("x")}Reject</button>
    </div>`}
  </article>`;
}

function doneBox(r) {
  const yes = r.status === "approved";
  return `<div class="done ${yes ? "" : "rej"}" role="status">
    <span class="row" style="gap:8px">${yes ? `<span class="ok-mark">Approved ${icon("check")}</span>` : `<span class="pill st-rejected">Rejected</span>`}</span>
    <span>${esc(r.effect || "Decision recorded.")}</span>
    ${r.effect_details && r.effect_details.applied === false && yes ? `<span class="label-xs">${esc(r.effect_details.note || "")}</span>` : ""}
    ${r.audit_id ? `<a class="card-link" href="/audit#a-${esc(r.audit_id)}">View audit entry #${esc(r.audit_id)} →</a>` : ""}
  </div>`;
}

function decidedCard(a) {
  const ev = audit.filter((e) => e.event === "approval_decided" && e.details && e.details.approval_id === a.id).pop();
  const r = { status: a.status, effect: ev ? ev.details.effect || ev.details.reason : a.status === "rejected" ? "No change was made." : "Decision recorded.",
    effect_details: ev ? ev.details.effect_details : null, audit_id: ev ? ev.id : null };
  return `<article class="card appr" id="ap-${esc(a.id)}">${head(a)}${facts(a)}${doneBox(r)}<span class="label-xs">Decided ${esc(fmtTs(a.decided_at, { date: true }))}</span></article>`;
}

function render() {
  setViewCounts({ pending: pending.length + [...justDone.keys()].filter((id) => !pending.some((p) => p.id === id)).length, decided: decided.length });
  const key = [view, pending.map((a) => a.id), decided.map((a) => a.id), [...justDone.keys()]];
  if (sameData(last, key)) return;
  last = key;
  $("#appr-loading").hidden = true;
  $("#kbd-hint").hidden = view !== "pending";
  const host = $("#appr-list");
  if (view === "pending") {
    const shown = [...pending, ...[...justDone.values()].filter((r) => !pending.some((p) => p.id === r.id))];
    host.innerHTML = shown.length ? shown.map(pendingCard).join("") : empty("Nothing waiting for you", "Emails Guard isn't sure about land here. Try the 8% discount or swapped bank account in Simulate.");
  } else {
    host.innerHTML = decided.length ? decided.slice().reverse().map(decidedCard).join("") : empty("No decisions yet", "Approved and rejected requests appear here with their effect.");
  }
  if (location.hash) $(location.hash)?.scrollIntoView({ block: "center" });
}
const empty = (t, s) => `<div class="empty" style="grid-column:1/-1">${icon("check-circle")}<div><b>${esc(t)}</b><br>${s.replace("Simulate", '<a class="card-link" href="/simulate">Simulate</a>')}</div></div>`;

async function load() {
  try {
    const [p, all, au, meta] = await Promise.all([api.approvals("pending"), api.approvals("all"), api.audit(500), clients.length ? null : api.meta()]);
    if (meta) clients = meta.clients;
    pending = p; decided = all.filter((a) => a.status !== "pending"); audit = au;
    render();
    document.dispatchEvent(new CustomEvent("float:pending", { detail: { n: pending.length } }));
  } catch (e) {
    $("#appr-loading").hidden = true;
    if (!last) $("#appr-list").innerHTML = `<div class="errbox" style="grid-column:1/-1">${icon("alert")}<div><b>Couldn't load approvals.</b><br>${esc(e.message)}</div></div>`;
    else toast(e.message, "err");
  }
}

async function decide(card, approve) {
  const id = +card.dataset.id;
  $$("[data-decide]", card).forEach((b) => (b.disabled = true));
  try {
    const r = await api.decide(id, approve);
    justDone.set(id, { ...pending.find((a) => a.id === id), ...r });
    toast(`${approve ? "Approved" : "Rejected"}. ${r.effect || ""}`, approve ? "ok" : "info", 5000);
    last = null;
    await load();
    $(`#ap-${id}`)?.focus();
  } catch (e) {
    toast(e.message, "err");
    $$("[data-decide]", card).forEach((b) => (b.disabled = false));
  }
}

$("#appr-list").addEventListener("click", (e) => {
  const b = e.target.closest("[data-decide]");
  if (b) decide(b.closest("[data-id]"), b.dataset.decide === "1");
});
$("#appr-list").addEventListener("keydown", (e) => {
  const card = e.target.closest("[data-id]");
  if (!card || e.target !== card || !$("[data-decide]", card)) return;
  if (e.key === "a" || e.key === "A") { e.preventDefault(); decide(card, true); }
  if (e.key === "r" || e.key === "R") { e.preventDefault(); decide(card, false); }
});
document.addEventListener("float:view", (e) => { view = e.detail.view; render(); });

await load();
poll(load, 10);
