// Guard Inbox: every client email, split into "Extracted request" (what the AI read) | "Guard decision" (what the rules did).
import { api, poll } from "../api.js";
import { setViewCounts } from "../shell.js";
import { $, $$, esc, icon, fmtTs, verdictPill, cardState, toast, sameData } from "../util.js";

let meta = null, feed = [], view = "all", last = null;
const open = new Set();

const field = (k, ico, v, none = "none") =>
  `<div class="xf"><div class="k">${icon(ico)}${esc(k)}</div><div class="v ${v === null || v === undefined || v === "" ? "none" : ""}">${v === null || v === undefined || v === "" ? none : v}</div></div>`;

function row(e) {
  const x = e.extracted || {};
  const cname = x.client_id ? (meta?.clients || []).find((c) => c.client_id === x.client_id)?.name || x.client_id : null;
  const known = meta && x.client_id ? (meta.clients.find((c) => c.client_id === x.client_id)?.known_emails || []).includes(String(e.sender || "").toLowerCase()) : null;
  const id = `m-${e.row ?? e.audit_id}`;
  const bodyOpen = open.has(id);
  return `<article class="mail v-${esc(e.decision)}-row" aria-label="${esc(e.sender)}: ${esc(e.decision)}">
    <section>
      <div class="col-h">${icon("mail")}<span class="label">${esc(fmtTs(e.ts, { date: true }))}</span>${e.sample_id ? `<span class="tag">sample ${esc(e.sample_id)}</span>` : ""}</div>
      <div class="from">${esc(e.sender || "unknown sender")}</div>
      ${e.subject ? `<div class="subj">${esc(e.subject)}</div>` : ""}
      ${e.body ? `<div class="untrusted-h">${icon("lock")}Untrusted text · shown as-is, never used for amounts</div>
        <pre class="untrusted ${bodyOpen ? "open" : ""}" id="${id}">${esc(e.body)}</pre>
        <button class="linkish" type="button" data-toggle="${id}" aria-expanded="${bodyOpen}" aria-controls="${id}">${bodyOpen ? "Show less" : "Show full email"}</button>`
        : `<p class="label-xs">${e.partial ? "Logged before the UI kept email text (audit only)." : ""}</p>`}
    </section>
    <section>
      <div class="col-h">${icon("sparkle")}<span class="label">Extracted request</span></div>
      <div class="xfields">
        ${field("Claims to be", "user", cname ? esc(cname) : null, "no known client")}
        ${field("Intent", "zap", x.intent ? esc(x.intent.replace(/_/g, " ")) : null)}
        ${field("Discount requested", "percent", x.discount_pct !== null && x.discount_pct !== undefined ? `${esc(x.discount_pct)}%` : null)}
        ${field("Bank account", "bank", x.new_bank_account ? `<span class="mono">${esc(x.new_bank_account)}</span>` : null)}
        ${field("New due date", "calendar", x.new_due_date ? esc(x.new_due_date) : null)}
        ${field("Sender on file", "shield", known === null ? null : known ? `<span class="t-lime">yes</span>` : `<span class="t-coral">no</span>`, "n/a")}
      </div>
      ${e.partial ? `<p class="label-xs">Only intent and client were in the audit entry.</p>` : ""}
    </section>
    <section>
      <div class="col-h">${icon("scale")}<span class="label">Guard decision</span></div>
      <div class="verdict-row">${verdictPill(e.decision, true)}${e.approval_id ? `<a class="card-link" href="/approvals#ap-${esc(e.approval_id)}">Approval #${esc(e.approval_id)} →</a>` : ""}</div>
      <ul class="rules">${(e.reasons || []).map((r) => `<li>${icon(e.decision === "allow" ? "check" : e.decision === "block" ? "ban" : "hourglass", e.decision === "allow" ? "t-lime" : e.decision === "block" ? "t-coral" : "t-amber")}<span>${esc(r)}</span></li>`).join("")}</ul>
    </section>
  </article>`;
}

function render() {
  const counts = { all: feed.length, allow: 0, needs_approval: 0, block: 0 };
  feed.forEach((e) => { if (e.decision in counts) counts[e.decision] += 1; });
  setViewCounts(counts);
  const list = feed.filter((e) => view === "all" || e.decision === view);
  const key = [view, list.map((e) => `${e.row}-${e.audit_id}`), [...open]];
  if (sameData(last, key)) return;
  last = key;
  cardState($("#card-mail"), "ready");
  $("#mail-list").innerHTML = list.length ? list.map(row).join("")
    : `<div class="empty">${icon("shield")}<div><b>${feed.length ? "No emails with this verdict" : "No client emails yet"}</b><br>${feed.length ? "Try another filter." : `Run a sample attack from <a class="card-link" href="/simulate">Simulate</a>, or test one above.`}</div></div>`;
}

async function load() {
  try {
    [meta, feed] = await Promise.all([meta ? Promise.resolve(meta) : api.meta(), api.emails(200)]);
    render();
  } catch (e) {
    if (!last) cardState($("#card-mail"), "error", { message: e.message, retry: load }); else toast(e.message, "err");
  }
}

$("#mail-list").addEventListener("click", (e) => {
  const b = e.target.closest("[data-toggle]");
  if (!b) return;
  const id = b.dataset.toggle;
  open.has(id) ? open.delete(id) : open.add(id);
  last = null; render();
});
$("#try-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const out = $("#try-out"), btn = $("#try-form button");
  btn.disabled = true; out.textContent = "Reading…";
  try {
    const r = await api.email({ id: `ui-${Date.now()}`, sender: $("#f-sender").value.trim(), subject: $("#f-subj").value, body: $("#f-body").value });
    out.innerHTML = `${verdictPill(r.decision)} ${esc((r.reasons || [])[0] || "")}`;
    if (r.approval_id) document.dispatchEvent(new CustomEvent("float:pending", { detail: { n: (await api.meta()).pending_approvals } }));
    await load();
  } catch (err) { out.innerHTML = `<span class="t-coral">${esc(err.message)}</span>`; }
  btn.disabled = false;
});
document.addEventListener("float:view", (e) => { view = e.detail.view; render(); });

cardState($("#card-mail"), "loading");
await load();
poll(load, 10);
