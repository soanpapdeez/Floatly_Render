// Audit Log: filterable, searchable timeline grouped by day. Entries are shown exactly as logged (no de-duplication
// tricks needed: Float already logs repeating states once). #a-<id> in the URL highlights one entry.
import { api, poll } from "../api.js";
import { setViewCounts, selectView } from "../shell.js";
import { categoryOf } from "../events.js";
import { timelineItem } from "../timeline.js";
import { $, esc, icon, cardState, toast, sameData, plural } from "../util.js";

let entries = [], clients = [], view = "all", q = "", last = null;

const dayLabel = (ts) => typeof ts === "number" ? new Date(ts * 1000).toLocaleDateString("en-GB", { weekday: "long", day: "numeric", month: "long" }) : "Earlier";

function render() {
  const counts = { all: entries.length, decision: 0, effect: 0, paypal_error: 0, waiting: 0 };
  entries.forEach((e) => { const c = categoryOf(e.event); if (c in counts) counts[c] += 1; });
  setViewCounts(counts);
  const needle = q.toLowerCase();
  const list = entries.filter((e) => (view === "all" || categoryOf(e.event) === view)
    && (!needle || `${e.event} ${JSON.stringify(e.details)}`.toLowerCase().includes(needle))).slice().reverse();
  const key = [view, q, list.map((e) => e.id ?? e.ts)];
  if (sameData(last, key)) return;
  last = key;
  cardState($("#card-audit"), "ready");
  $("#audit-count").textContent = `${plural(list.length, "event")}${view !== "all" || q ? ` of ${entries.length}` : ""}`;
  if (!list.length) {
    $("#audit-list").innerHTML = `<div class="empty">${icon(view === "paypal_error" ? "shield-check" : "list")}<div><b>${view === "paypal_error" ? "No PayPal errors" : "Nothing here"}</b><br>${entries.length ? "Try another filter or search." : "Launch a plan or run a sample email to start the log."}</div></div>`;
    return;
  }
  let html = "", cur = null;
  for (const e of list) {
    const d = dayLabel(e.ts);
    if (d !== cur) { if (cur !== null) html += "</ol>"; html += `<div class="audit-day">${esc(d)}</div><ol class="timeline wide" style="margin-top:14px">`; cur = d; }
    html += timelineItem(e, clients);
  }
  $("#audit-list").innerHTML = html + "</ol>";
  highlight();
}

function highlight() {
  const id = location.hash.slice(1);
  if (!id) return;
  const el = document.getElementById(id);
  if (el && !el.classList.contains("hl")) { el.classList.add("hl"); el.scrollIntoView({ block: "center" }); }
}

async function load() {
  try {
    const [a, meta] = await Promise.all([api.audit(1000), clients.length ? null : api.meta()]);
    if (meta) clients = meta.clients;
    entries = a;
    render();
  } catch (e) {
    if (!last) cardState($("#card-audit"), "error", { message: e.message, retry: load }); else toast(e.message, "err");
  }
}

$("#q").addEventListener("input", (e) => { q = e.target.value.trim(); render(); });
document.addEventListener("float:view", (e) => { view = e.detail.view; render(); });
window.addEventListener("hashchange", () => { last = null; render(); });
const want = new URLSearchParams(location.search).get("type");
if (want) { view = want; selectView(want, { emit: false }); }

cardState($("#card-audit"), "loading");
await load();
poll(load, 10);
