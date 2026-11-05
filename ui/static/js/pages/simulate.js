// Simulate: featured attacks with expected verdicts, the whole sample inbox, fake client payments, a PayPal outage.
import { api } from "../api.js";
import { setViewCounts } from "../shell.js";
import { $, $$, esc, icon, verdictPill, toast, money, fmtDay, statusPill } from "../util.js";

const BOOT = window.FLOAT_BOOT || {};
let samples = [];
const results = {};

function resultBox(r) {
  if (!r) return "";
  const got = r.result || {};
  return `<div class="res" role="status">
    <div class="row" style="gap:8px">Guard said ${verdictPill(got.decision)}
      ${r.match ? `<span class="ok-mark">as expected ${icon("check")}</span>` : `<span class="tag amber">expected ${esc(r.expected_decision)}${r.needs_real_llm ? " (needs real AI)" : ""}</span>`}</div>
    <ul class="rules" style="list-style:none;margin:0;padding:0;display:flex;flex-direction:column;gap:4px">${(got.reasons || []).map((x) => `<li class="t-2">· ${esc(x)}</li>`).join("")}</ul>
    <div class="row" style="gap:12px">${got.approval_id ? `<a class="card-link" href="/approvals#ap-${esc(got.approval_id)}">Open approval #${esc(got.approval_id)} →</a>` : ""}<a class="card-link" href="/inbox">See it in Guard Inbox →</a></div>
  </div>`;
}

function featuredCard(s) {
  const tone = { allow: "lime", needs_approval: "amber", block: "coral" }[s.expected_decision];
  return `<article class="card sim" id="sim-${esc(s.id)}">
    <div class="sim-h"><span class="ic-btn tone-${tone}" aria-hidden="true">${icon(s.expected_decision === "block" ? "ban" : s.expected_decision === "allow" ? "check" : "hourglass")}</span>
      <div><div class="sim-t">${esc(s.featured.title)}</div><div class="label">expected ${verdictPill(s.expected_decision)}</div></div></div>
    <p class="sim-b">${esc(s.featured.blurb)}</p>
    <div class="untrusted-h">${icon("mail")}From <b class="t-2">${esc(s.sender)}</b></div>
    <pre class="untrusted">${esc(s.body)}</pre>
    <button class="btn ${tone === "coral" ? "coral" : ""}" type="button" data-run="${esc(s.id)}">${icon("play")}Run through Guard</button>
    <div data-res>${resultBox(results[s.id])}</div>
  </article>`;
}

function renderFeatured() {
  const f = samples.filter((s) => s.featured).sort((a, b) => a.featured.order - b.featured.order);
  $("#featured").innerHTML = f.map(featuredCard).join("") || `<div class="empty">${icon("inbox")}<div><b>No sample emails found</b><br>data/inbox.json is missing.</div></div>`;
}

function renderSamples() {
  $("#samples").innerHTML = `<table class="sample-table"><thead><tr><th>ID</th><th>From</th><th>Email (untrusted)</th><th>Expected</th><th>Result</th><th></th></tr></thead><tbody>
    ${samples.map((s) => { const r = results[s.id]; return `<tr>
      <td class="mono">${esc(s.id)}</td><td>${esc(s.sender)}${s.needs_real_llm ? `<br><span class="tag">needs real AI</span>` : ""}</td>
      <td class="body-cell">${esc(s.body.length > 140 ? s.body.slice(0, 140) + "…" : s.body)}</td>
      <td>${verdictPill(s.expected_decision)}</td>
      <td>${r ? `${verdictPill(r.result.decision)} ${r.match ? icon("check", "t-pos") : icon("alert", "t-amber")}` : `<span class="t-muted">—</span>`}</td>
      <td><button class="btn sm" type="button" data-run="${esc(s.id)}">Run</button></td></tr>`; }).join("")}</tbody></table>`;
}

async function run(id, quiet = false) {
  $$(`[data-run="${CSS.escape(id)}"]`).forEach((b) => (b.disabled = true));
  try {
    const r = await api.simulateEmail(id);
    results[id] = r;
    const card = $(`#sim-${CSS.escape(id)} [data-res]`);
    if (card) card.innerHTML = resultBox(r);
    renderSamples();
    if (!quiet) toast(`${id}: Guard said ${r.result.decision.replace("_", " ")}${r.match ? ", as expected." : "."}`, r.match ? "ok" : "info");
    if (r.result.approval_id) api.meta().then((m) => document.dispatchEvent(new CustomEvent("float:pending", { detail: { n: m.pending_approvals } })));
    return r;
  } catch (e) { toast(e.message, "err"); }
  finally { $$(`[data-run="${CSS.escape(id)}"]`).forEach((b) => (b.disabled = false)); }
}

async function renderPayments() {
  const host = $("#pay-list");
  if (!(BOOT.mode && BOOT.mode.can_simulate_payment)) {
    host.innerHTML = `<div class="empty">${icon("lock")}<div><b>Real PayPal sandbox</b><br>Pay invoices from the sandbox personal account; Float picks it up on the next check.</div></div>`;
    return;
  }
  try {
    const d = await api.dashboard();
    const inv = (d.state && d.state.invoices) || [];
    if (!d.launched || !inv.length) {
      host.innerHTML = `<div class="empty">${icon("file")}<div><b>No invoices sent yet</b><br>Ask Float for a goal on the <a class="card-link" href="/">dashboard</a> and run the plan first.</div></div>`;
      return;
    }
    const name = (id) => (d.clients.find((c) => c.client_id === id) || {}).name || id;
    host.innerHTML = inv.map((i) => `<div class="inner row" style="justify-content:space-between">
      <div><b>${esc(name(i.client_id))}</b> <span class="label">${esc(i.key.split(":").slice(1).join(":"))} · due ${esc(fmtDay(i.due_date))}</span></div>
      <div class="row" style="gap:10px"><span class="num">${money(i.amount, { cents: true })}</span>${statusPill(i.status)}
      ${i.status === "unpaid" ? `<button class="btn sm lime" type="button" data-pay="${esc(i.key)}">${icon("zap")}Client pays</button>` : ""}</div></div>`).join("");
  } catch (e) { host.innerHTML = `<div class="errbox">${icon("alert")}<div>${esc(e.message)}</div></div>`; }
}

document.addEventListener("click", async (e) => {
  const r = e.target.closest("[data-run]");
  if (r) return run(r.dataset.run);
  const p = e.target.closest("[data-pay]");
  if (p) {
    p.disabled = true;
    try {
      await api.pay(p.dataset.pay);
      const d = await api.dashboard({ tick: true });
      const paid = (d.state?.payouts || []).length;
      toast(`Marked paid in fake PayPal. Float checked PayPal: ${paid} payout${paid === 1 ? "" : "s"} released so far.`, "ok", 5000);
      renderPayments();
    } catch (err) { toast(err.message, "err"); p.disabled = false; }
  }
});
$("#run-all").addEventListener("click", async () => {
  const f = samples.filter((s) => s.featured).sort((a, b) => a.featured.order - b.featured.order);
  let ok = 0;
  for (const s of f) { const r = await run(s.id, true); if (r && r.match) ok += 1; }
  $("#run-all-out").textContent = `${ok} of ${f.length} matched the expected verdict.`;
});
$("#outage").addEventListener("click", async () => {
  try {
    await api.outage(6);
    await api.dashboard({ tick: true }).catch(() => {});
    $("#outage-out").innerHTML = `Done. <a class="card-link" href="/audit?type=paypal_error">See paypal_error in the audit log →</a>`;
  } catch (e) { toast(e.message, "err"); }
});
$("#reset").addEventListener("click", async () => {
  const b = $("#reset");
  if (b.dataset.confirm !== "1") { b.dataset.confirm = "1"; b.textContent = "Press again to reset"; setTimeout(() => { b.dataset.confirm = ""; b.textContent = "Reset offline demo"; }, 4000); return; }
  try { await api.reset(); toast("Offline demo reset.", "ok"); Object.keys(results).forEach((k) => delete results[k]); renderFeatured(); renderSamples(); renderPayments(); document.dispatchEvent(new CustomEvent("float:pending", { detail: { n: 0 } })); }
  catch (e) { toast(e.message, "err"); }
});
document.addEventListener("float:view", (e) => {
  $$("[data-panel]").forEach((p) => (p.hidden = p.dataset.panel !== e.detail.view));
  if (e.detail.view === "payments") renderPayments();
});

try {
  samples = await api.samples();
  setViewCounts({ attacks: samples.filter((s) => s.featured).length, samples: samples.length });
  renderFeatured(); renderSamples();
} catch (e) {
  $("#featured").innerHTML = `<div class="errbox">${icon("alert")}<div><b>Couldn't load the sample inbox.</b><br>${esc(e.message)}</div></div>`;
}
