// "Cash runway" hero: an isometric topographic mountain whose height is the projected cumulative cash balance.
// A white dashed route climbs from S (today) to the flag (deadline). The route's altitude at each moment IS the
// cash you'd have by then, so a payment landing makes the route climb; a quiet day makes it traverse a contour.
// Pins: ice = invoice expected paid, lime = early-pay discount offered, amber = approval pending,
//       coral = blocked attack (stopped at the gate, on the ground ring), white = contractor payout.
// If the best case misses the goal, the summit flag floats above the route's end with a coral gap marker.
import { s, uid } from "./charts/svg.js";
import { money, fmtDay, day, daysBetween, esc, showTip, hideTip, verdictPill, clientName } from "./util.js";

const W = 760, H = 500, CX = 380, CY = 340, R = 250, TILT = 0.42, HPX = 228, LEVELS = 24;
const A = 1.7, B = 1.55;                                  // profile shape: f(r) = (1 - r^A)^B

const wob = (th, L) => 0.9 + 0.055 * Math.sin(3 * th + 0.6) + 0.035 * Math.sin(5 * th + 2.1 + L * 1.4) + 0.018 * Math.sin(9 * th + L * 5);
const centre = (L) => ({ x: 0.1 * Math.pow(L, 1.2), y: -0.16 * Math.pow(L, 1.1) });   // summit sits back-right
const radiusAt = (th, L) => wob(th, L) * Math.pow(1 - Math.pow(Math.min(0.9999, Math.max(0, L)), 1 / B), 1 / A);

function ground(th, L) {                                   // normalised ground position of altitude L along angle th
  const c = centre(L), r = radiusAt(th, L);
  return { gx: c.x + r * Math.cos(th), gy: c.y + r * Math.sin(th) };
}
const screen = (gx, gy, L) => ({ x: CX + gx * R, y: CY + gy * R * TILT - L * HPX });
const P = (th, L) => { const g = ground(th, L); return screen(g.gx, g.gy, L); };
const smoothstep = (a, b, x) => { const t = Math.max(0, Math.min(1, (x - a) / (b - a))); return t * t * (3 - 2 * t); };

function contourPath(L) {
  const n = 132;
  let d = "";
  for (let i = 0; i <= n; i++) {
    const p = P((i / n) * Math.PI * 2, L);
    d += `${i ? "L" : "M"}${p.x.toFixed(1)},${p.y.toFixed(1)}`;
  }
  return d + "Z";
}

function ellipsePoint(th, k) { return { x: CX + Math.cos(th) * R * k, y: CY + Math.sin(th) * R * k * TILT }; }

export function renderRunway(host, m, { animate = true, onPin = null } = {}) {
  host.innerHTML = "";
  const svg = s("svg", { viewBox: `0 0 ${W} ${H}`, preserveAspectRatio: "xMidYMid meet", role: "group",
    "aria-label": m.goal.amount ? `Cash runway to ${money(m.goal.amount)} by ${fmtDay(m.goal.deadline)}. Best case ${money(m.best)}${m.covered ? ", goal covered" : `, short by ${money(m.shortfall)}`}.` : "Cash runway: no goal yet." }, host);
  const defs = s("defs", {}, svg);
  const wash = uid("wash"), mask = uid("rm"), glow = uid("glow");
  const rg = s("radialGradient", { id: wash, cx: "50%", cy: "62%", r: "55%" }, defs);
  s("stop", { offset: "0%", style: "stop-color: var(--mauve); stop-opacity: .14" }, rg);
  s("stop", { offset: "60%", style: "stop-color: var(--ice); stop-opacity: .04" }, rg);
  s("stop", { offset: "100%", style: "stop-color: var(--ice); stop-opacity: 0" }, rg);
  const gf = s("filter", { id: glow, x: "-50%", y: "-50%", width: "200%", height: "200%" }, defs);
  s("feGaussianBlur", { stdDeviation: 5 }, gf);
  s("ellipse", { cx: CX, cy: CY - 60, rx: 360, ry: 230, style: `fill: url(#${wash})` }, svg);

  // ---------------------------------------------------------------- the money -> altitude mapping
  const target = m.goal.amount || 0;
  const today = day(m.today), deadline = day(m.deadline);
  const nDays = Math.max(1, daysBetween(today, deadline) + 1);            // today .. end of deadline day
  const raw = m.items.filter((i) => i.status !== "cancelled").map((i) => {
    const dd = i.landed ? day(i.landed) : day(i.best);
    const di = i.landed ? -1 : Math.max(0, daysBetween(today, dd < today ? today : dd));
    return { ...i, di, inWindow: (i.landed ? day(i.landed) : dd) <= deadline };
  });
  // stagger payments that land on the same day so each gets its own spot on the route
  const land = raw.map((l) => {
    const same = raw.filter((x) => x.di === l.di), k = same.indexOf(l);
    const t = l.di < 0 ? 0.03 + 0.03 * k : (l.di + 0.2 + 0.6 * (k + 0.5) / same.length) / nDays;
    return { ...l, t: Math.max(0.03, Math.min(0.97, t)) };
  });
  const finalBal = land.filter((l) => l.inWindow).reduce((acc, l) => acc + l.amount, 0);
  const peak = Math.max(target, finalBal, 1) * 1.07;
  const tw = Math.min(0.5 / nDays, 0.6 / Math.max(1, land.length));
  const balanceAt = (t) => land.filter((l) => l.inWindow).reduce((acc, l) => acc + l.amount * smoothstep(l.t - tw, l.t + tw * 0.3, t), 0);
  // the route sweeps sideways with both time and money, so a big climb on one day still moves across the face
  const prog = (t) => 0.45 * t + 0.55 * (finalBal ? balanceAt(t) / finalBal : t);
  const thAt = (t) => { const u = prog(t); return 2.6 - 1.95 * u + 0.18 * Math.sin(u * Math.PI * 2.2); };
  const levelOf = (v) => Math.min(0.985, v / peak);
  const routePt = (t) => P(thAt(t), levelOf(balanceAt(t)));

  // ---------------------------------------------------------------- compass ring (drawn first; terrain occludes the back)
  s("ellipse", { cx: CX, cy: CY, rx: R * 1.2, ry: R * 1.2 * TILT, style: "fill: none; stroke: var(--white-06)" }, svg);
  const ticks = s("g", { style: "stroke: var(--white-20); stroke-width: 1" }, svg);
  for (let a = 0; a < 360; a += 4) {
    const th = (a * Math.PI) / 180, long = a % 20 === 0;
    const p1 = ellipsePoint(th, 1.12), p2 = ellipsePoint(th, long ? 1.17 : 1.145);
    s("line", { x1: p1.x, y1: p1.y, x2: p2.x, y2: p2.y, style: long ? "stroke: var(--white-35)" : null }, ticks);
  }
  s("ellipse", { cx: CX, cy: CY, rx: R * 1.08, ry: R * 1.08 * TILT, style: "fill: none; stroke: var(--ice); stroke-width: 2.5; opacity: .75" }, svg);
  for (const [lab, a] of [["N", -90], ["E", 0], ["S", 90], ["W", 180]]) {
    const p = ellipsePoint((a * Math.PI) / 180, 1.25);
    s("text", { x: p.x, y: p.y + 4, "text-anchor": "middle", style: "fill: var(--text-2); font-size: 13px; font-weight: 700", text: lab }, svg);
  }

  // ---------------------------------------------------------------- terrain: stacked contour slabs (painter's order)
  const terr = s("g", {}, svg);
  const goalL = target ? levelOf(target) : null;
  for (let k = 0; k < LEVELS; k++) {
    const L = k / LEVELS;
    const op = 0.18 + 0.55 * (k / LEVELS);
    s("path", { d: contourPath(L), class: animate ? "fade-in" : null,
      style: `fill: var(--bg-card); stroke: var(--text); stroke-opacity: ${op.toFixed(2)}; stroke-width: ${k === 0 ? 1.4 : 1}; animation-delay: ${k * 22}ms` }, terr);
  }
  if (goalL) {
    s("path", { d: contourPath(goalL), style: "fill: none; stroke: var(--lime); stroke-width: 1.4; stroke-dasharray: 2 4; opacity: .9" }, svg);
    const gp = P(-0.25, goalL);
    s("text", { x: gp.x + 10, y: gp.y - 4, style: "fill: var(--lime); font-size: 11px; font-weight: 600", text: `goal ${money(target)}` }, svg);
  }

  // ---------------------------------------------------------------- route (dashed, revealed with a mask)
  const pts = [];
  for (let i = 0; i <= 180; i++) pts.push(routePt(i / 180));
  const d = pts.map((p, i) => `${i ? "L" : "M"}${p.x.toFixed(1)},${p.y.toFixed(1)}`).join("");
  const mk = s("mask", { id: mask, maskUnits: "userSpaceOnUse", x: 0, y: 0, width: W, height: H }, defs);
  const mpath = s("path", { d, style: "fill: none; stroke: var(--white); stroke-width: 8" }, mk);
  if (animate) { try { mpath.style.setProperty("--len", 2400); mpath.classList.add("draw-line"); mpath.style.animationDuration = "1100ms"; mpath.style.animationDelay = "350ms"; } catch { /* ignore */ } }
  s("path", { d, mask: `url(#${mask})`, style: "fill: none; stroke: var(--white); stroke-width: 2.4; stroke-dasharray: 5 6; stroke-linecap: round" }, svg);

  // ---------------------------------------------------------------- pins
  const pinLayer = s("g", {}, svg);
  const used = [];
  const pin = ({ x, y, color, glyph, label, tip, stem = 46, ring = false, text = null }) => {
    let st = stem, hx = x;
    for (let tries = 0; tries < 6 && used.some((u) => Math.abs(u.x - hx) < 28 && Math.abs(u.top - (y - st)) < 28); tries++) {
      hx = x + (tries % 2 ? -1 : 1) * 30 * Math.ceil((tries + 1) / 2); st += 8;
    }
    used.push({ x: hx, top: y - st });
    const g = s("g", { class: `pin${animate ? " pop-in" : ""}`, tabindex: 0, role: "button", "aria-label": label, style: `animation-delay:${500 + used.length * 70}ms` }, pinLayer);
    s("path", { d: `M${x},${y} L${x},${y - st * 0.55} L${hx},${y - st + 13}`, fill: "none", style: "stroke: var(--white-60); stroke-width: 1.4" }, g);
    s("circle", { cx: x, cy: y, r: 2.6, style: "fill: var(--white)" }, g);
    const head = s("g", { class: "pin-head" }, g);
    s("circle", { cx: hx, cy: y - st, r: 13.5, style: `fill: var(${color}); stroke: var(--bg-card); stroke-width: ${ring ? 0 : 2}` }, head);
    if (text) s("text", { x: hx, y: y - st + 4.5, "text-anchor": "middle", style: "fill: var(--on-accent); font-size: 12px; font-weight: 800", text }, head);
    else s("use", { href: `#i-${glyph}`, x: hx - 7.5, y: y - st - 7.5, width: 15, height: 15, style: "fill: none; stroke: var(--on-accent); stroke-width: 2.2; stroke-linecap: round; stroke-linejoin: round" }, head);
    const show = (cx, cy) => showTip(tip, cx, cy);
    g.addEventListener("pointerenter", (e) => show(e.clientX, e.clientY));
    g.addEventListener("pointermove", (e) => show(e.clientX, e.clientY));
    g.addEventListener("pointerleave", hideTip);
    g.addEventListener("focus", () => { const b = head.getBoundingClientRect(); show(b.left + b.width / 2, b.top); });
    g.addEventListener("blur", hideTip);
    if (onPin) g.addEventListener("click", () => onPin(label));
    return g;
  };

  // S = today
  const s0 = routePt(0);
  pin({ ...s0, color: "--text", text: "S", stem: 40, label: `Start: today, ${fmtDay(m.today)}`,
    tip: `<div class="tip-t">Today · ${esc(fmtDay(m.today))}</div><div class="tip-s">Received so far: <b class="t-2">${money(m.received)}</b>, confirmed by PayPal.</div>` });

  for (const l of land.filter((x) => x.inWindow)) {
    const p = routePt(l.t);
    const paid = l.status === "paid";
    const tip = `<div class="tip-t">${esc(l.name)} · ${esc(l.invoice_id)}</div>
      <div class="tip-v ${l.offer ? "t-lime" : "t-ice"}">${money(l.amount, { cents: true })}</div>
      <div class="tip-s">${paid ? "Paid · confirmed by PayPal" : l.offer ? `If they take ${l.discount_pct}% off, it lands by ${esc(fmtDay(l.best))}` : `Expected ${esc(fmtDay(l.expected))}`}</div>
      <div class="tip-s" style="margin-top:6px">${esc(l.reason || "")}</div>`;
    pin({ ...p, color: l.offer && !paid ? "--lime" : "--ice", glyph: paid ? "check" : l.offer ? "percent" : "file",
      label: `${l.name} ${l.invoice_id}, ${money(l.amount)}, ${paid ? "paid" : l.offer ? "discount offered" : "expected " + fmtDay(l.expected)}`, tip });
  }

  for (const po of m.payoutPlan.filter((x) => x.at && day(x.at) <= deadline)) {
    const t = po.released ? 0.06 : Math.min(1, (daysBetween(today, day(po.at)) + 0.62) / nDays);
    const p = routePt(t);
    pin({ ...p, color: "--white", glyph: "out", stem: 62,
      label: `Payout to ${po.name}, ${money(po.amount)}, ${po.released ? "released" : "after money clears"}`,
      tip: `<div class="tip-t">Payout · ${esc(po.name)}</div><div class="tip-v">${money(po.amount)}</div>
        <div class="tip-s">${po.released ? `Released via PayPal Payouts (${esc(po.status)}).` : `Released only after ${money(po.need)} of client money has cleared in PayPal.`}</div>` });
  }

  m.approvals.slice(0, 3).forEach((a, i) => {
    const p = P(3.05 + i * 0.32, 0.26 + i * 0.1);
    pin({ ...p, color: "--amber", glyph: "hourglass", stem: 40,
      label: `Approval pending: ${a.client_name || a.client_id}, ${(a.intent || "").replace(/_/g, " ")}`,
      tip: `<div class="tip-t">Approval #${esc(a.id)} · ${esc(a.client_name || a.client_id)}</div>
        <div class="tip-s">${esc((a.reasons || []).join(" "))}</div>
        ${a.preview ? `<div class="tip-s" style="margin-top:6px">Approve: <b class="t-2">${esc(a.preview.approve)}</b></div>` : ""}` });
  });

  const blocked = m.emails.filter((e) => e.decision === "block");
  blocked.slice(0, 4).forEach((e, i) => {
    const th = -0.35 + i * 0.32;
    const p = ellipsePoint(th, 1.0);
    pin({ ...p, color: "--coral", glyph: "ban", stem: 34 + (i % 2) * 18,
      label: `Blocked: ${e.sender}`,
      tip: `<div class="tip-t">Blocked at the gate ${verdictPill("block")}</div><div class="tip-s">${esc(e.sender || "")}${e.extracted?.client_id ? ` claiming to be ${esc(clientName(e.extracted.client_id, []))}` : ""}</div>
        <div class="tip-s" style="margin-top:6px">${esc((e.reasons || []).join(" "))}</div>${i === 3 && blocked.length > 4 ? `<div class="tip-s">+${blocked.length - 4} more</div>` : ""}` });
  });

  // ---------------------------------------------------------------- flag (deadline) + shortfall gap
  const end = routePt(1);
  if (m.covered || !target) {
    pin({ ...end, color: "--text", glyph: "flag", stem: 54, label: `Deadline ${fmtDay(m.deadline)}: ${money(finalBal)} projected`,
      tip: `<div class="tip-t">Deadline · ${esc(fmtDay(m.deadline))}</div><div class="tip-v t-lime">${money(finalBal)}</div>
        <div class="tip-s">Best case by the deadline. Goal ${money(target)} ${target ? "covered" : ""}.</div>` });
  } else {
    const top = P(thAt(1), levelOf(target));
    s("line", { x1: end.x, y1: end.y, x2: top.x, y2: top.y, style: "stroke: var(--coral); stroke-width: 2; stroke-dasharray: 3 4" }, svg);
    s("circle", { cx: end.x, cy: end.y, r: 5, style: "fill: none; stroke: var(--coral); stroke-width: 2" }, svg);
    const lx = Math.max(end.x, top.x) + 46, ly = (end.y + top.y) / 2;
    s("line", { x1: Math.max(end.x, top.x) + 4, y1: ly, x2: lx, y2: ly, style: "stroke: var(--coral-25)" }, svg);
    s("rect", { x: lx, y: ly - 13, width: 112, height: 26, rx: 13, style: "fill: var(--bg-card); stroke: var(--coral)" }, svg);
    s("text", { x: lx + 56, y: ly + 4, "text-anchor": "middle", style: "fill: var(--coral); font-size: 11.5px; font-weight: 700", text: `short ${money(m.shortfall)}` }, svg);
    pin({ ...top, color: "--text", glyph: "flag", stem: 40, label: `Goal ${money(target)} by ${fmtDay(m.deadline)}, short ${money(m.shortfall)}`,
      tip: `<div class="tip-t">Goal not reached in the best case</div><div class="tip-v t-coral">short ${money(m.shortfall)}</div>
        <div class="tip-s">Even if every early-pay offer is accepted, ${money(finalBal)} arrives by ${esc(fmtDay(m.deadline))}. Float reports this honestly instead of offering bigger discounts than Guard allows.</div>` });
  }
  const late = land.filter((l) => !l.inWindow).length;
  return { svg, late };
}
