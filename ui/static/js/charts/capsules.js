// "Guard activity": discount-% zones (lime allow, amber approval, coral block) with each client email plotted as a
// capsule at the discount it asked for, coloured by Guard's verdict. Emails with no discount sit on the baseline as rings.
import { s, root } from "./svg.js";
import { showTip, hideTip, esc, verdictPill, fmtTs } from "../util.js";

const TONE = { allow: "--lime", needs_approval: "--amber", block: "--coral" };

export function renderGuardBands(host, rows, policy, { height = 150, animate = true } = {}) {
  const lo = policy.approval_discount_pct ?? 5, hiLim = policy.max_discount_pct ?? 10;
  const top = Math.max(30, Math.ceil(Math.max(0, ...rows.map((r) => r.pct || 0)) / 10) * 10);
  const blocked = rows.filter((r) => r.decision === "block").length;
  const { svg, w, h } = root(host, height, `Guard decisions by requested discount. ${rows.length} emails, ${blocked} blocked.`);
  const L = 30, R = 64, T = 8, B = 16;
  // broken scale: 0..max limit gets 62% of the height, the rest above it squeezes into 38%
  const split = T + (h - B - T) * 0.38;
  const y = (v) => (v <= hiLim ? (h - B) - (v / hiLim) * (h - B - split) : split - ((Math.min(v, top) - hiLim) / (top - hiLim)) * (split - T));

  const band = (a, b, fill, label, tone) => {
    s("rect", { x: L, width: w - L - R, y: y(b), height: y(a) - y(b), style: `fill: var(${fill})` }, svg);
    s("text", { x: w - R + 8, y: (y(a) + y(b)) / 2 + 3, style: `fill: var(${tone}); font-size: 10px; font-weight: 600`, text: label }, svg);
  };
  band(0, lo, "--lime-12", "allow", "--lime");
  band(lo, hiLim, "--amber-12", "approval", "--amber");
  band(hiLim, top, "--coral-12", "block", "--coral");
  for (const v of [0, lo, hiLim, top]) s("text", { x: L - 8, y: y(v) + 3, "text-anchor": "end", style: "fill: var(--muted); font-size: 10px", text: `${v}%` }, svg);
  s("line", { x1: L, x2: w - R, y1: split, y2: split, style: "stroke: var(--bg-card); stroke-width: 2; stroke-dasharray: 3 3" }, svg);

  if (!rows.length) {
    s("text", { x: (L + w - R) / 2, y: h / 2, "text-anchor": "middle", style: "fill: var(--muted); font-size: 12px", text: "No client emails yet" }, svg);
    return svg;
  }
  const n = rows.length, step = (w - L - R) / Math.max(n, 6);
  const cw = Math.max(8, Math.min(22, step * 0.72));
  let prev = null;
  rows.forEach((r, i) => {
    const cx = L + step * i + step / 2;
    const v = r.pct === null || r.pct === undefined ? null : +r.pct;
    const cy = v === null ? h - B - 5 : y(v);
    if (prev) s("path", { d: `M${prev.x + cw / 2},${prev.y} H${cx - cw / 2 - 2} V${cy}`, style: "fill: none; stroke: var(--white-10); stroke-width: 1" }, svg);
    const g = s("g", { class: animate ? "pop-in" : null, style: `animation-delay:${i * 45}ms`, tabindex: 0, role: "img",
      "aria-label": `${r.client}: ${v === null ? "no discount" : v + "% asked"}, ${r.decision}` }, svg);
    if (v === null) s("rect", { x: cx - cw / 2, y: cy - 4, width: cw, height: 8, rx: 4, style: `fill: none; stroke: var(${TONE[r.decision] || "--muted"}); stroke-width: 1.5` }, g);
    else s("rect", { x: cx - cw / 2, y: cy - 5, width: cw, height: 10, rx: 5, style: `fill: var(${TONE[r.decision] || "--muted"})` }, g);
    const show = (x, yy) => showTip(`<div class="tip-t">${esc(r.client)} ${verdictPill(r.decision)}</div>
      <div class="tip-s">${esc(r.sender || "")} · ${esc(fmtTs(r.ts))}</div>
      <div class="tip-s" style="margin-top:6px">AI read: <b class="t-2">${esc((r.intent || "").replace(/_/g, " "))}${v !== null ? `, ${v}% requested` : ""}</b><br>Rule: ${esc(r.reason)}</div>`, x, yy);
    g.addEventListener("pointermove", (e) => show(e.clientX, e.clientY));
    g.addEventListener("pointerleave", hideTip);
    g.addEventListener("focus", () => { const b = g.getBoundingClientRect(); show(b.left + b.width / 2, b.top); });
    g.addEventListener("blur", hideTip);
    prev = { x: cx, y: cy };
  });
  return svg;
}
