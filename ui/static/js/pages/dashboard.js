// Dashboard: goal strip, 3 metric cards, cash-runway hero, activity timeline, stat tiles, AI plan card,
// projected balance chart. Polls /api/dashboard (which polls PayPal) every few seconds once a plan is launched.
import { api, poll } from "../api.js";
import { buildModel } from "../derive.js";
import { mockDashboard } from "../mock.js";
import { renderBars } from "../charts/bars.js";
import { renderDelays } from "../charts/dots.js";
import { renderGuardBands } from "../charts/capsules.js";
import { renderArea } from "../charts/area.js";
import { onResize } from "../charts/svg.js";
import { renderRunway } from "../hero-runway.js";
import { renderTimeline } from "../timeline.js";
import { selectView } from "../shell.js";
import { $, $$, esc, icon, money, fmtDay, countUp, toast, cardState, avatar, store, sameData, plural, relTs } from "../util.js";

const BOOT = window.FLOAT_BOOT || {};
const POLL = (BOOT.mode && BOOT.mode.poll_seconds) || 6;
const CARDS = ["card-cash", "card-delay", "card-guard", "card-hero", "card-activity", "card-tiles", "card-plan", "card-area"];

let raw = null;            // last payload (real or mock)
let model = null;
let previewOverride = null; // a preview the owner asked for while another goal is already running
let range = store.get("range", "deadline");
let firstPaint = true;
const drawn = {};          // last data drawn per chart, so polling never redraws (or shifts) unchanged charts
let poller = null;

// ------------------------------------------------------------------------------------------------ data
async function load({ tick = false } = {}) {
  let p;
  try {
    p = await api.dashboard({ tick });
  } catch (e) {
    if (!raw) { p = { ...mockDashboard(), offline: true, offlineError: e.message }; }
    else { showAlert("net", "alert", "Can't reach the Float server", `${e.message} Showing the last known state; retrying.`); return; }
  }
  clearAlert("net");
  if (!p.offline && !p.plan) p = withMock(p);                       // nothing launched or previewed yet
  if (previewOverride) p = { ...p, ...previewOverride };
  raw = p;
  model = buildModel(p);
  render();
}

/** Sample plan + the server's real clients / emails / audit / approvals, so Guard data is never fake when it exists. */
function withMock(real) {
  const m = mockDashboard(real.today);
  return {
    ...m, mode: real.mode, policy: real.policy, today: real.today, now: real.now,
    clients: real.clients && real.clients.length ? real.clients : m.clients,
    contractors: real.contractors && real.contractors.length ? real.contractors : m.contractors,
    emails: real.emails && real.emails.length ? real.emails : m.emails,
    audit: real.audit && real.audit.length ? real.audit : m.audit,
    approvals: real.approvals || m.approvals, paypal_errors: real.paypal_errors || [],
    sampleEmails: !(real.emails && real.emails.length),
  };
}

// ------------------------------------------------------------------------------------------------ alerts
function showAlert(id, cls, title, text, { dismiss = false, actions = "" } = {}) {
  const host = $("#alerts");
  let el = $(`[data-alert="${id}"]`, host);
  const html = `${icon(cls.includes("ice") ? "sparkle" : "alert")}<div style="flex:1"><div class="alert-t">${esc(title)}</div><div class="alert-s">${text}</div></div>${actions}${dismiss ? `<button class="ic-btn sm" type="button" data-dismiss aria-label="Dismiss">${icon("x")}</button>` : ""}`;
  if (!el) { el = document.createElement("div"); el.dataset.alert = id; host.appendChild(el); }
  el.className = cls;
  if (el.dataset.html !== html) { el.innerHTML = html; el.dataset.html = html; }
  const b = $("[data-dismiss]", el);
  if (b) b.onclick = () => { const seen = store.get("dismissed", []); store.set("dismissed", [...seen, id].slice(-50)); el.remove(); };
}
const clearAlert = (id) => $(`#alerts [data-alert="${id}"]`)?.remove();

function renderAlerts() {
  const dismissed = new Set(store.get("dismissed", []));
  const errs = raw.paypal_errors || [];
  const want = new Set();
  for (const e of errs) {
    const id = `pp-${e.id}`;
    if (dismissed.has(id)) continue;
    want.add(id);
    const d = e.details || {};
    showAlert(id, "alert", e.event === "discount_apply_failed" ? "A discount could not be applied in PayPal" : `PayPal ${d.step || "call"} failed`,
      `${esc(d.reason || d.error || "")} <span class="t-muted">· ${esc(relTs(e.ts))} · <a class="card-link" href="/audit#a-${esc(e.id)}">audit #${esc(e.id)}</a></span>`, { dismiss: true });
  }
  $$("#alerts [data-alert^='pp-']").forEach((el) => { if (!want.has(el.dataset.alert)) el.remove(); });
  if (raw.tick_error) showAlert("tick", "alert", "The last PayPal check failed", `${esc(raw.tick_error)}. Float retries on the next check.`); else clearAlert("tick");
  if (raw.offline) showAlert("offline", "alert amber", "Showing sample data", `Can't reach the Float server (${esc(raw.offlineError || "")}). Nothing here is real.`); else clearAlert("offline");
  if (raw.sample && !raw.offline) {
    showAlert("sample", "alert ice", "Sample plan · nothing has been sent",
      `Type a goal in <b>Ask Floatly</b> (top right) and Float will build your real plan from client payment history.${raw.sampleEmails ? " Guard numbers are sample too: run an attack from <a class='card-link' href='/simulate'>Simulate</a>." : ""}`);
  } else clearAlert("sample");
  if (!raw.sample && !model.launched) {
    showAlert("preview", "alert ice", "Preview · nothing has been sent yet",
      `Run plan issues ${plural(model.items.length, "invoice")} through PayPal Invoicing. Paid is only ever decided by PayPal.`,
      { actions: previewOverride ? `<button class="btn sm ghost" type="button" id="drop-preview">Back to live goal</button>` : "" });
    const b = $("#drop-preview"); if (b) b.onclick = () => { previewOverride = null; load(); };
  } else clearAlert("preview");
}

// ------------------------------------------------------------------------------------------------ render
function render() {
  const m = model;
  renderAlerts();

  // goal strip
  $("#goal-text").innerHTML = m.goal.amount ? `${money(m.goal.amount)} <span class="t-muted">by</span> ${esc(fmtDay(m.goal.deadline))}` : "No goal yet";
  $("#goal-meta").innerHTML = `${icon("calendar")}<span>${m.sample ? "sample" : m.launched ? "live" : "preview"} · ${esc(m.goal.label || "")}</span>`;
  $("#goal-state").innerHTML = m.covered
    ? `<span class="pill fill-lime">${icon("check")}Covered in best case</span>`
    : `<span class="pill v-block">${icon("alert")}Short ${money(m.shortfall)}</span>`;
  const ids = [...new Set(m.items.map((i) => i.client_id))];
  $("#goal-avatars").innerHTML = ids.slice(0, 6).map((id) => avatar(id, raw.clients)).join("");

  renderCash(m); renderDelay(m); renderGuard(m); renderHero(m); renderActivity(); renderTiles(m); renderPlan(m); renderBalance(m);
  for (const id of CARDS) cardState($(`#${id}`), "ready");
  firstPaint = false;
}

function renderCash(m) {
  countUp($("#cash-big"), m.projected, (v) => money(v));
  $("#cash-of").textContent = `of ${money(m.goal.amount)}`;
  const covered = m.projected >= m.goal.amount;
  $("#cash-tags").innerHTML = `<span class="tag lime">best case ${money(m.best)}</span>${m.received ? `<span class="tag ice">${money(m.received)} received</span>` : ""}${covered ? "" : `<span class="tag amber">${money(Math.max(0, m.goal.amount - m.projected))} gap without offers</span>`}`;
  draw("bars", $("#chart-bars"), m.daily, (host, d, a) => renderBars(host, d, { animate: a }));
}

function renderDelay(m) {
  const risk = m.delays.filter((d) => d.atRisk).length;
  $("#delay-risk").innerHTML = risk ? `<span class="t-amber">${risk} after deadline</span>` : `<span class="t-lime">all before deadline</span>`;
  draw("dots", $("#chart-dots"), m.delays, (host, d, a) => renderDelays(host, d, { animate: a }));
}

function renderGuard(m) {
  const c = { allow: 0, needs_approval: 0, block: 0 };
  m.guard.forEach((g) => { if (g.decision in c) c[g.decision] += 1; });
  $("#guard-counts").innerHTML = `<span class="pill v-allow">${c.allow} allowed</span><span class="pill v-needs_approval">${c.needs_approval} approval</span><span class="pill v-block">${c.block} blocked</span>`;
  draw("guard", $("#chart-guard"), m.guard.slice(-24), (host, d, a) => renderGuardBands(host, d, raw.policy || BOOT.policy || {}, { animate: a }));
}

function renderHero(m) {
  const key = { items: m.items, best: m.best, goal: m.goal, pp: m.payoutPlan, ap: m.approvals.map((a) => a.id), bl: m.emails.filter((e) => e.decision === "block").length, today: m.today };
  if (sameData(drawn.hero, key)) return;
  const stage = $("#hero-stage");
  const res = renderRunway(stage, m, { animate: !drawn.hero });
  drawn.hero = key;
  const badge = document.createElement("div");
  badge.className = "hero-badge";
  badge.innerHTML = `<span class="label">best case by ${esc(fmtDay(m.deadline))}</span><span class="mid ${m.covered ? "t-lime" : "t-coral"}">${money(m.best)}</span><span class="label-xs">goal ${money(m.goal.amount)}</span>`;
  stage.appendChild(badge);
  const note = document.createElement("div");
  note.className = "hero-note";
  note.textContent = res.late ? `${plural(res.late, "invoice")} land after the deadline and aren't counted on this route.` : "Hover or tab to a pin for the invoice, amount and reason.";
  stage.appendChild(note);
}

function renderActivity() {
  const entries = (raw.audit || []).filter((e) => e.event !== "goal_previewed").slice(-5).reverse();
  if (sameData(drawn.activity, entries.map((e) => e.id))) return;
  drawn.activity = entries.map((e) => e.id);
  renderTimeline($("#activity-list"), entries, raw.clients, { link: true });
}

function renderTiles(m) {
  const st = m.stats;
  countUp($("#v-sent"), st.sent);
  setDelta("#d-sent", st.sentToday ? `+${st.sentToday} today` : `${st.sent}/${st.planned}`, st.sentToday ? "up" : "flat");
  countUp($("#v-paid"), st.paidAmount, (v) => money(v));
  const share = m.goal.amount ? Math.round((st.paidAmount / m.goal.amount) * 100) : 0;
  setDelta("#d-paid", `${share}% of goal`, share > 0 ? "up" : "flat");
  countUp($("#v-pay"), st.payoutsAmount, (v) => money(v));
  setDelta("#d-pay", st.payoutsWaiting ? `${st.payoutsWaiting} waiting` : `${st.payoutsCount} sent`, st.payoutsWaiting ? "flat" : "up");
  countUp($("#v-block"), st.blocked);
  setDelta("#d-block", st.blockedToday ? `+${st.blockedToday} today` : "none today", st.blockedToday ? "warn" : "flat");
}
function setDelta(sel, text, cls) { const el = $(sel); el.textContent = text; el.className = `delta ${cls}`; }

function renderPlan(m) {
  const sub = $("#card-plan [data-sub]");
  if (sub) sub.textContent = raw.sample ? "sample" : raw.summary && raw.summary.source === "ai" ? "written by AI, numbers checked" : "from the plan";
  $("#plan-text").textContent = (raw.summary && raw.summary.text) || "Ask Floatly for a goal to get a plan.";
  const offers = m.items.filter((i) => i.offer).length;
  $("#plan-nums").innerHTML = `<span class="tag ice">${plural(m.items.length, "invoice")}</span><span class="tag lime">${plural(offers, "offer")}</span><span class="tag">max cost ${money(m.totalDiscountCost, { cents: true })}</span>`;
  const btn = $("#plan-cta"), label = $("span", btn), note = $("#plan-note");
  btn.disabled = false;
  if (m.sample) {
    label.textContent = "Ask Floatly"; btn.dataset.do = "ask";
    note.textContent = "Nothing is sent until you run a plan.";
  } else if (!m.launched) {
    label.textContent = "Run plan"; btn.dataset.do = "launch";
    note.textContent = `Sends ${plural(m.items.filter((i) => !(i.offer && i.discount_pct > (raw.policy || {}).approval_discount_pct)).length, "invoice")} via PayPal Invoicing.`;
  } else {
    label.textContent = "Check PayPal now"; btn.dataset.do = "tick";
    note.textContent = `Running · PayPal is polled every ${POLL}s · payouts only from cleared money.`;
  }
}

function renderBalance(m) {
  const now = Date.now(), end = { "1D": now + 86400000, "1W": now + 7 * 86400000, "1M": now + 30 * 86400000 }[range];
  const startT = range === "deadline" ? m.series[0]?.t : Math.min(now, m.series[0]?.t ?? now) - 0;
  let series = m.series;
  if (range === "deadline") series = m.series.filter((p) => p.t <= new Date(m.deadline).getTime() + 2 * 86400000);
  else series = m.series.filter((p) => p.t >= startT && p.t <= end);
  if (series.length < 2) series = m.series.slice(0, Math.max(2, Math.min(m.series.length, 5)));
  $$("#range button").forEach((b) => b.setAttribute("aria-pressed", String(b.dataset.range === range)));
  draw("area", $("#chart-area"), { series, goal: m.goal.amount, deadline: m.deadline },
    (host, d, a) => renderArea(host, d.series, { goal: d.goal, deadline: d.deadline, today: m.today, animate: a, height: window.innerWidth < 700 ? 200 : 250 }));
}

/** Draw a chart only if its data changed (no flicker/shift while polling). First paint animates. */
function draw(key, host, data, fn) {
  if (sameData(drawn[key], data)) return;
  const animate = !(key in drawn);
  drawn[key] = data;
  fn(host, data, animate);
  if (!host.dataset.ro) { host.dataset.ro = "1"; onResize(host, () => fn(host, drawn[key], false)); }
}

// ------------------------------------------------------------------------------------------------ actions
async function ask(text) {
  const btn = $("#plan-cta");
  btn.disabled = true;
  try {
    const r = await api.preview(text);
    if (!r.ok) { toast(r.error || "Float couldn't read that goal.", "err", 6000); return; }
    const running = raw && raw.launched && raw.goal && raw.goal.goal_id !== r.goal_id;
    previewOverride = running ? { goal: { ...r.goal, goal_id: r.goal_id }, plan: r.plan, summary: r.summary, launched: false, state: null, plan_source: "preview", sample: false } : null;
    toast(`Read as ${money(r.goal.amount)} by ${r.goal.deadline_label}. Nothing is sent until you press Run plan.`, "info");
    $("#cmd-input").value = "";
    Object.keys(drawn).forEach((k) => delete drawn[k]);
    await load();
    selectView("overview", { emit: false });
  } catch (e) {
    toast(e.message, "err");
  } finally { btn.disabled = false; }
}

async function launch() {
  const btn = $("#plan-cta");
  btn.disabled = true; $("span", btn).textContent = "Sending via PayPal…";
  try {
    const r = await api.launch(model.goal.amount, model.goal.deadline);
    previewOverride = null;
    toast(`Plan running. ${plural((r.invoices || []).length, "invoice")} issued through PayPal.`, "ok");
    await load({ tick: true });
  } catch (e) {
    toast(`Couldn't launch: ${e.message}`, "err", 7000);
    btn.disabled = false; $("span", btn).textContent = "Run plan";
  }
}

async function tickNow() {
  try { await load({ tick: true }); toast("Checked PayPal.", "info", 2000); } catch (e) { toast(e.message, "err"); }
}

function bind() {
  $("#plan-cta").addEventListener("click", () => {
    const d = $("#plan-cta").dataset.do;
    if (d === "ask") $("#cmd-input").focus();
    else if (d === "launch") launch();
    else tickNow();
  });
  $("#card-hero [data-action=refresh]")?.addEventListener("click", tickNow);
  $$("#range button").forEach((b) => b.addEventListener("click", () => { range = b.dataset.range; store.set("range", range); renderBalance(model); }));
  document.addEventListener("float:ask", (e) => ask(e.detail.text));
  document.addEventListener("float:view", (e) => {
    const target = { overview: "#overview", runway: "#card-hero", activity: "#card-activity" }[e.detail.view];
    const el = $(target);
    if (el) el.scrollIntoView({ behavior: matchMedia("(prefers-reduced-motion: reduce)").matches ? "auto" : "smooth", block: "start" });
  });
  $$("[data-action=more]").forEach((b) => b.addEventListener("click", () => toast("More options are coming soon.", "info", 1800)));
}

// ------------------------------------------------------------------------------------------------ boot
bind();
CARDS.forEach((id) => cardState($(`#${id}`), "loading"));
await load({ tick: false }).catch((e) => CARDS.forEach((id) => cardState($(`#${id}`), "error", { message: e.message, retry: () => load() })));
const q = new URLSearchParams(location.search).get("ask");
if (q) { history.replaceState(null, "", "/"); ask(q); }
poller = poll(() => load({ tick: !!(raw && raw.launched && !previewOverride) }), POLL);
