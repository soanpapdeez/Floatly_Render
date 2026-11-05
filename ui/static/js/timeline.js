// Vertical timeline (numbered/icon nodes, title, timestamp, nested key/value card, status). Fed by the audit log.
import { describe, renderKv } from "./events.js";
import { esc, icon, fmtTs } from "./util.js";

export function timelineItem(e, clients, { number = null, link = false } = {}) {
  const it = describe(e, clients);
  const status = it.statusHtml || (it.status ? `<span class="pill ${it.status.cls}">${esc(it.status.label)}</span>` : "");
  return `<li class="tl-item" id="a-${esc(it.id)}" data-cat="${esc(it.category)}">
    <span class="tl-node ${it.tone ? `tone-${it.tone}` : ""}" aria-hidden="true">${number !== null ? esc(number) : icon(it.icon)}</span>
    <div class="tl-head">
      <div class="tl-title">${it.title}</div>
      <div class="tl-time">${esc(fmtTs(it.ts, { date: true }))}${link && it.id !== undefined ? ` · <a class="card-link" href="/audit#a-${esc(it.id)}">#${esc(it.id)}</a>` : it.id !== undefined ? ` · #${esc(it.id)}` : ""}</div>
    </div>
    <div class="tl-card">
      ${status ? `<div class="row" style="justify-content:space-between;margin-bottom:10px"><span class="label">${esc(it.event.replace(/_/g, " "))}</span>${status}</div>` : ""}
      ${renderKv(it.kv)}
    </div>
  </li>`;
}

export function renderTimeline(host, entries, clients, opts = {}) {
  if (!entries.length) {
    host.innerHTML = `<div class="empty">${icon("list")}<div><b>No activity yet</b><br>Every decision and PayPal effect will appear here.</div></div>`;
    return;
  }
  host.innerHTML = `<ol class="timeline${opts.wide ? " wide" : ""}">${entries.map((e) => timelineItem(e, clients, opts)).join("")}</ol>`;
}
