// App shell: sliding pill sub-nav, theme toggle, "Ask Float" command bar, pending-approvals badge.
import { api, poll } from "./api.js";
import { $, $$, store, toast } from "./util.js";

const BOOT = window.FLOAT_BOOT || {};

// ---------------------------------------------------------------- sub-nav (top centred pill tabs)
function moveIndicator(nav, btn, animate = true) {
  const ind = $(".subnav-ind", nav);
  if (!ind || !btn) return;
  if (!animate) ind.style.transition = "none";
  ind.style.width = `${btn.offsetWidth}px`;
  ind.style.transform = `translateX(${btn.offsetLeft}px)`;
  if (!animate) { ind.offsetWidth; ind.style.transition = ""; }
}

export function selectView(view, { emit = true, focus = false } = {}) {
  const nav = $(".subnav");
  if (!nav) return;
  const btn = $(`[data-view="${CSS.escape(view)}"]`, nav);
  if (!btn) return;
  $$("[role=tab]", nav).forEach((b) => {
    const on = b === btn;
    b.setAttribute("aria-selected", on ? "true" : "false");
    b.tabIndex = on ? 0 : -1;
  });
  moveIndicator(nav, btn);
  if (focus) btn.focus();
  if (emit) document.dispatchEvent(new CustomEvent("float:view", { detail: { view } }));
}

export function setViewCounts(counts) {
  for (const [k, n] of Object.entries(counts)) {
    const el = $(`.subnav [data-count="${CSS.escape(k)}"]`);
    if (el) el.textContent = n === null || n === undefined ? "" : String(n);
  }
  const nav = $(".subnav"), cur = nav && $("[aria-selected=true]", nav);
  if (cur) moveIndicator(nav, cur, false);
}

function initSubnav() {
  const nav = $(".subnav");
  if (!nav) return;
  const tabs = $$("[role=tab]", nav);
  tabs.forEach((b) => b.addEventListener("click", () => selectView(b.dataset.view)));
  nav.addEventListener("keydown", (e) => {
    const i = tabs.indexOf(document.activeElement);
    if (i < 0) return;
    let j = null;
    if (e.key === "ArrowRight") j = (i + 1) % tabs.length;
    if (e.key === "ArrowLeft") j = (i - 1 + tabs.length) % tabs.length;
    if (e.key === "Home") j = 0;
    if (e.key === "End") j = tabs.length - 1;
    if (j !== null) { e.preventDefault(); selectView(tabs[j].dataset.view, { focus: true }); }
  });
  const sel = $("[aria-selected=true]", nav) || tabs[0];
  requestAnimationFrame(() => moveIndicator(nav, sel, false));
  document.fonts?.ready?.then(() => moveIndicator(nav, $("[aria-selected=true]", nav), false));
  window.addEventListener("resize", () => moveIndicator(nav, $("[aria-selected=true]", nav), false));
}

// ---------------------------------------------------------------- theme (canvas colour)
function initTheme() {
  const btn = $("#theme-toggle");
  if (!btn) return;
  btn.addEventListener("click", () => setCanvas(document.documentElement.dataset.canvas === "slate" ? "plum" : "slate"));
}
export function setCanvas(name) {
  document.documentElement.dataset.canvas = name;
  store.set("canvas", name);
  try { localStorage.setItem("float.canvas", name); } catch { /* ignore */ }
  document.dispatchEvent(new CustomEvent("float:canvas", { detail: { canvas: name } }));
}

// ---------------------------------------------------------------- Ask Float
function initCommand() {
  const form = $("#cmd"), input = $("#cmd-input"), mic = $("#cmd-mic");
  if (!form) return;
  form.addEventListener("submit", (e) => {
    e.preventDefault();
    const q = input.value.trim();
    if (!q) { input.focus(); return; }
    if (BOOT.page === "dashboard") document.dispatchEvent(new CustomEvent("float:ask", { detail: { text: q } }));
    else location.href = `/?ask=${encodeURIComponent(q)}`;
  });
  // Voice input uses the browser's own speech recognition, only when the owner clicks the mic.
  const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
  mic.addEventListener("click", () => {
    if (!SR) { toast("Voice input isn't available in this browser. Type your goal instead.", "info"); input.focus(); return; }
    const rec = new SR();
    rec.lang = "en-US"; rec.interimResults = false; rec.maxAlternatives = 1;
    mic.classList.add("tone-mauve");
    rec.onresult = (ev) => { input.value = ev.results[0][0].transcript; form.requestSubmit(); };
    rec.onend = () => mic.classList.remove("tone-mauve");
    rec.onerror = () => { mic.classList.remove("tone-mauve"); toast("Didn't catch that. Try typing it.", "info"); };
    rec.start();
  });
  document.addEventListener("keydown", (e) => {
    if (e.key === "/" && !/input|textarea|select/i.test(document.activeElement?.tagName || "")) { e.preventDefault(); input.focus(); }
  });
}

// ---------------------------------------------------------------- pending approvals badge + bell
export function setPending(n) {
  $$("[data-pending-count]").forEach((el) => { el.textContent = String(n); el.dataset.n = String(n); });
  const dot = $("#bell-dot");
  if (dot) dot.hidden = !n;
  const bell = $("#bell");
  if (bell) bell.setAttribute("aria-label", n ? `${n} approval${n === 1 ? "" : "s"} waiting` : "Notifications: nothing waiting");
}
document.addEventListener("float:pending", (e) => setPending(e.detail.n));

function initPending() {
  const refresh = async () => { const m = await api.meta(); setPending(m.pending_approvals || 0); };
  refresh().catch(() => {});
  poll(refresh, 20);
}

initSubnav();
initTheme();
initCommand();
initPending();
