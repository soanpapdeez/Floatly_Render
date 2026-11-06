// Small shared helpers: DOM, formatting, motion, toasts, tooltip, storage. No framework.

export const $ = (sel, root = document) => root.querySelector(sel);
export const $$ = (sel, root = document) => Array.from(root.querySelectorAll(sel));

const ESC = { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" };
export const esc = (v) => String(v ?? "").replace(/[&<>"']/g, (c) => ESC[c]);

export const icon = (name, cls = "") => `<svg class="i ${cls}" aria-hidden="true"><use href="#i-${name}"/></svg>`;

export const reducedMotion = () => window.matchMedia("(prefers-reduced-motion: reduce)").matches;

// ---------------------------------------------------------------- money + numbers
export function money(n, { cents = false, sign = false } = {}) {
  if (n === null || n === undefined || Number.isNaN(+n)) return "—";
  const v = +n;
  const s = Math.abs(v).toLocaleString("en-US", { minimumFractionDigits: cents ? 2 : 0, maximumFractionDigits: cents ? 2 : 0 });
  return `${v < 0 ? "−" : sign ? "+" : ""}$${s}`;
}
export function moneyShort(n) {
  const v = +n || 0;
  if (Math.abs(v) >= 1000) return `$${(v / 1000).toFixed(Math.abs(v) >= 10000 ? 0 : 1).replace(/\.0$/, "")}k`;
  return `$${Math.round(v)}`;
}
export const pct = (n, d = 0) => (n === null || n === undefined ? "—" : `${(+n).toFixed(d).replace(/\.0+$/, "")}%`);
export const plural = (n, one, many = one + "s") => `${n} ${n === 1 ? one : many}`;
export const clamp = (v, a, b) => Math.max(a, Math.min(b, v));

// ---------------------------------------------------------------- dates (ISO day strings are LOCAL calendar days)
export function day(iso) {
  if (!iso) return null;
  if (iso instanceof Date) return new Date(iso.getFullYear(), iso.getMonth(), iso.getDate());
  const [y, m, d] = String(iso).slice(0, 10).split("-").map(Number);
  return new Date(y, m - 1, d);
}
export const isoDay = (d) => `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
export const addDays = (d, n) => { const x = new Date(d); x.setDate(x.getDate() + n); return x; };
export const daysBetween = (a, b) => Math.round((day(b) - day(a)) / 86400000);
export function fmtDay(iso, { weekday = true } = {}) {
  const d = day(iso);
  if (!d) return "—";
  return d.toLocaleDateString("en-GB", { weekday: weekday ? "short" : undefined, day: "numeric", month: "short" });
}
export function fmtTs(ts, { date = false } = {}) {
  if (ts === null || ts === undefined) return "";
  if (typeof ts === "string" && !/^\d+(\.\d+)?$/.test(ts)) return ts;            // stand-in service gives "14:02:11"
  const d = new Date(+ts * 1000);
  const t = d.toLocaleTimeString("en-GB", { hour: "2-digit", minute: "2-digit" });
  return date ? `${d.toLocaleDateString("en-GB", { day: "numeric", month: "short" })}, ${t}` : t;
}
export function relTs(ts) {
  if (typeof ts !== "number") return fmtTs(ts);
  const s = Date.now() / 1000 - ts;
  if (s < 45) return "just now";
  if (s < 3600) return `${Math.round(s / 60)} min ago`;
  if (s < 86400) return `${Math.round(s / 3600)} h ago`;
  return fmtTs(ts, { date: true });
}

// ---------------------------------------------------------------- clients
export const initials = (name) => String(name || "?").replace(/[^A-Za-z0-9 ]/g, " ").trim().split(/\s+/).map((w) => w[0]).join("").slice(0, 2).toUpperCase() || "?";
export const ownerInitials = (name) => { const w = String(name || "?").trim().split(/\s+/); return (w.length > 1 ? w[0][0] + w[1][0] : w[0].slice(0, 2)).toUpperCase(); };
export function clientIndex(id, clients = []) {
  const i = clients.findIndex((c) => c.client_id === id);
  if (i >= 0) return i % 6;
  let h = 0; for (const ch of String(id || "")) h = (h * 31 + ch.charCodeAt(0)) >>> 0;
  return h % 6;
}
export function clientName(id, clients = []) {
  const c = clients.find((x) => x.client_id === id);
  return c ? c.name : id ? id[0].toUpperCase() + id.slice(1) : "Unknown client";
}
export const avatar = (id, clients, cls = "sm") =>
  `<span class="avatar ${cls} c${clientIndex(id, clients)}" aria-hidden="true">${esc(initials(clientName(id, clients)))}</span>`;

// ---------------------------------------------------------------- pills
const VERDICT = { allow: "Allow", needs_approval: "Needs approval", block: "Block" };
const VERDICT_ICON = { allow: "check", needs_approval: "hourglass", block: "ban" };
export const verdictPill = (d, lg = false) =>
  d ? `<span class="pill ${lg ? "lg" : ""} v-${esc(d)}">${icon(VERDICT_ICON[d] || "alert")}${esc(VERDICT[d] || d)}</span>` : `<span class="pill">—</span>`;
export const verdictLabel = (d) => VERDICT[d] || d;
export function statusPill(status) {
  const s = String(status || "draft").toLowerCase();
  const label = { draft: "Draft", unpaid: "Sent", sent: "Sent", paid: "Paid", cancelled: "Cancelled", held: "Held" }[s] || s;
  const cls = s === "unpaid" ? "st-sent" : `st-${s}`;
  return `<span class="pill ${cls}"><span class="dot"></span>${esc(label)}</span>`;
}
export const confirmedByPayPal = () => `<span class="confirmed">${icon("shield-check")}confirmed by PayPal</span>`;

// ---------------------------------------------------------------- motion
export function countUp(el, to, fmt = (v) => Math.round(v).toLocaleString(), dur = 700) {
  if (!el) return;
  const from = +el.dataset.v || 0;
  el.dataset.v = to;
  if (reducedMotion() || from === to || el.dataset.counted === "1" && Math.abs(from - to) < 0.005) { el.textContent = fmt(to); return; }
  el.dataset.counted = "1";
  const t0 = performance.now();
  const step = (t) => {
    const k = Math.min(1, (t - t0) / dur), e = 1 - Math.pow(1 - k, 3);
    el.textContent = fmt(from + (to - from) * e);
    if (k < 1) requestAnimationFrame(step);
  };
  requestAnimationFrame(step);
}

// ---------------------------------------------------------------- toasts + tooltip
export function toast(msg, kind = "ok", ms = 4200) {
  const host = $("#toasts");
  if (!host) return;
  const t = document.createElement("div");
  t.className = `toast ${kind}`;
  t.innerHTML = `${icon(kind === "err" ? "alert" : kind === "info" ? "sparkle" : "check")}<span>${esc(msg)}</span>`;
  host.appendChild(t);
  setTimeout(() => t.remove(), ms);
}
export function showTip(html, x, y) {
  const tip = $("#tip");
  if (!tip) return;
  tip.innerHTML = html;
  tip.classList.add("on");
  tip.setAttribute("aria-hidden", "false");
  const r = tip.getBoundingClientRect();
  const left = clamp(x + 14, 8, window.innerWidth - r.width - 8);
  const top = y - r.height - 14 < 8 ? y + 18 : y - r.height - 14;
  tip.style.left = `${left}px`;
  tip.style.top = `${top}px`;
}
export function hideTip() {
  const tip = $("#tip");
  if (tip) { tip.classList.remove("on"); tip.setAttribute("aria-hidden", "true"); }
}

// ---------------------------------------------------------------- card states
export function cardState(card, state, { message = "", retry = null, emptyIcon = "inbox", emptyTitle = "Nothing here yet" } = {}) {
  if (!card) return;
  card.classList.toggle("is-loading", state === "loading");
  const sk = card.querySelector("[data-skeleton]");
  if (sk) sk.hidden = state !== "loading";
  let box = card.querySelector(":scope > [data-statebox]");
  if (state === "ready" || state === "loading") { if (box) box.remove(); return; }
  if (!box) { box = document.createElement("div"); box.dataset.statebox = ""; card.appendChild(box); }
  if (state === "error") {
    box.className = "errbox";
    box.innerHTML = `${icon("alert")}<div><b>Couldn't load this.</b><br>${esc(message)}</div>${retry ? `<button class="btn sm" type="button">Retry</button>` : ""}`;
    if (retry) box.querySelector("button").onclick = retry;
  } else {
    box.className = "empty";
    box.innerHTML = `${icon(emptyIcon)}<div><b>${esc(emptyTitle)}</b><br>${esc(message)}</div>`;
  }
}

// ---------------------------------------------------------------- storage (per-viewer conveniences only)
export const store = {
  get(k, d = null) { try { const v = localStorage.getItem(`float.${k}`); return v === null ? d : JSON.parse(v); } catch { return d; } },
  set(k, v) { try { localStorage.setItem(`float.${k}`, JSON.stringify(v)); } catch { /* private mode */ } },
};

export const sameData = (a, b) => JSON.stringify(a) === JSON.stringify(b);
export const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
