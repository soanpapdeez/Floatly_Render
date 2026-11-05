// "Projected cash balance": smooth mauve line (best case, offers accepted), gradient fill, faint dashed ice line
// (no discounts), goal line, deadline marker, dashed crosshair + glowing marker + floating tooltip. Keyboard: ← →.
import { s, root, lin, niceMax, fmtAxis, smooth, drawIn, uid } from "./svg.js";
import { money, showTip, hideTip, esc, day } from "../util.js";

export function renderArea(host, series, { height = 240, goal = 0, deadline = null, today = null, animate = true } = {}) {
  if (!series.length) { host.innerHTML = ""; return null; }
  const vmax = niceMax(Math.max(goal * 1.1, ...series.map((p) => Math.max(p.best, p.expected))));
  const { svg, w, h } = root(host, height, `Projected cash in, reaching ${money(series[series.length - 1].best)} best case against a ${money(goal)} goal.`);
  svg.setAttribute("tabindex", "0");
  const L = 44, R = 16, T = 18, B = 26;
  const t0 = series[0].t, t1 = series[series.length - 1].t;
  const x = lin(t0, t1, L, w - R), y = lin(0, vmax, h - B, T);

  const gradId = uid("ga"), glowId = uid("gl");
  const defs = s("defs", {}, svg);
  const lg = s("linearGradient", { id: gradId, x1: 0, x2: 0, y1: 0, y2: 1 }, defs);
  s("stop", { offset: "0%", style: "stop-color: var(--mauve); stop-opacity: .38" }, lg);
  s("stop", { offset: "100%", style: "stop-color: var(--mauve); stop-opacity: 0" }, lg);
  const f = s("filter", { id: glowId, x: "-100%", y: "-100%", width: "300%", height: "300%" }, defs);
  s("feGaussianBlur", { stdDeviation: 4 }, f);

  for (let k = 0; k <= 4; k++) {
    const v = (vmax / 4) * k;
    s("line", { x1: L, x2: w - R, y1: y(v), y2: y(v), style: "stroke: var(--white-06)" }, svg);
    s("text", { x: L - 10, y: y(v) + 3, "text-anchor": "end", style: "fill: var(--muted); font-size: 10px", text: `$${fmtAxis(v)}` }, svg);
  }
  // x labels: one per day at midnight
  const days = series.filter((p) => new Date(p.t).getHours() === 0);
  const every = Math.ceil(days.length / Math.max(2, Math.floor((w - L) / 70)));
  days.forEach((p, i) => {
    if (i % every) return;
    s("text", { x: x(p.t), y: h - 6, "text-anchor": "middle", style: "fill: var(--muted); font-size: 10px",
      text: new Date(p.t).toLocaleDateString("en-GB", { weekday: "short", day: "numeric" }) }, svg);
  });
  if (goal > 0 && goal <= vmax) {
    s("line", { x1: L, x2: w - R, y1: y(goal), y2: y(goal), style: "stroke: var(--lime); stroke-dasharray: 5 5; opacity: .7" }, svg);
    s("text", { x: w - R, y: y(goal) - 6, "text-anchor": "end", style: "fill: var(--lime); font-size: 10px; font-weight: 600", text: `goal ${money(goal)}` }, svg);
  }
  const dl = deadline ? day(deadline).getTime() + 86400000 - 1 : null;
  if (dl && dl >= t0 && dl <= t1) {
    s("line", { x1: x(dl), x2: x(dl), y1: T, y2: h - B, style: "stroke: var(--mauve-55); stroke-dasharray: 3 4" }, svg);
    s("text", { x: x(dl) - 6, y: T + 2, "text-anchor": "end", style: "fill: var(--mauve); font-size: 10px; font-weight: 600", text: "deadline" }, svg);
  }

  const pb = series.map((p) => ({ x: x(p.t), y: y(p.best) }));
  const pe = series.map((p) => ({ x: x(p.t), y: y(p.expected) }));
  const line = smooth(pb);
  s("path", { d: `${line} L${pb[pb.length - 1].x},${h - B} L${pb[0].x},${h - B} Z`, style: `fill: url(#${gradId})`, class: animate ? "fade-in" : null }, svg);
  drawIn(s("path", { d: smooth(pe), style: "fill: none; stroke: var(--ice); stroke-width: 1.4; stroke-dasharray: 4 5; opacity: .55" }, svg), false);
  drawIn(s("path", { d: line, style: "fill: none; stroke: var(--mauve); stroke-width: 2.4; stroke-linecap: round" }, svg), animate);

  // crosshair
  const cross = s("g", { style: "opacity: 0; transition: opacity 120ms" }, svg);
  const vline = s("line", { y1: T, y2: h - B, style: "stroke: var(--white-35); stroke-dasharray: 3 4" }, cross);
  const hline = s("line", { x1: L, x2: w - R, style: "stroke: var(--white-20); stroke-dasharray: 3 4" }, cross);
  const glow = s("circle", { r: 9, filter: `url(#${glowId})`, style: "fill: var(--mauve)" }, cross);
  const dot = s("circle", { r: 4.5, style: "fill: var(--text); stroke: var(--mauve); stroke-width: 2.5" }, cross);
  let idx = series.length - 1;

  const place = (i, clientX, clientY) => {
    idx = Math.max(0, Math.min(series.length - 1, i));
    const p = series[idx], px = x(p.t), py = y(p.best);
    vline.setAttribute("x1", px); vline.setAttribute("x2", px);
    hline.setAttribute("y1", py); hline.setAttribute("y2", py);
    for (const c of [glow, dot]) { c.setAttribute("cx", px); c.setAttribute("cy", py); }
    cross.style.opacity = 1;
    const prevDay = series[Math.max(0, idx - 4)];
    const change = prevDay.best > 0 ? ((p.best - prevDay.best) / prevDay.best) * 100 : p.best > 0 ? 100 : 0;
    const d = new Date(p.t);
    const box = svg.getBoundingClientRect(), k = box.width / w;
    showTip(`<div class="tip-s">${esc(d.toLocaleDateString("en-GB", { weekday: "short", day: "numeric", month: "short" }))}, ${String(d.getHours()).padStart(2, "0")}:00</div>
      <div class="row" style="gap:8px"><span class="tip-v">${money(p.best)}</span>
      <span class="delta ${change > 0 ? "up" : "flat"}">${change > 0 ? "+" : ""}${change.toFixed(change > 0 && change < 10 ? 1 : 0)}%</span></div>
      <div class="tip-s">best case · ${money(p.expected)} with no discounts</div>`,
      clientX ?? box.left + px * k, clientY ?? box.top + py * k);
  };
  const nearest = (clientX) => {
    const box = svg.getBoundingClientRect(), px = ((clientX - box.left) / box.width) * w;
    let best = 0, bd = Infinity;
    series.forEach((p, i) => { const dd = Math.abs(x(p.t) - px); if (dd < bd) { bd = dd; best = i; } });
    return best;
  };
  svg.addEventListener("pointermove", (e) => place(nearest(e.clientX), e.clientX, e.clientY));
  svg.addEventListener("pointerleave", () => { cross.style.opacity = 0; hideTip(); });
  svg.addEventListener("focus", () => place(idx));
  svg.addEventListener("blur", () => { cross.style.opacity = 0; hideTip(); });
  svg.addEventListener("keydown", (e) => {
    if (e.key === "ArrowRight") { e.preventDefault(); place(idx + 1); }
    if (e.key === "ArrowLeft") { e.preventDefault(); place(idx - 1); }
  });
  // resting marker on "now"
  const nowI = today ? series.findIndex((p) => p.t >= Date.now()) : -1;
  if (nowI > 0) s("circle", { cx: x(series[nowI].t), cy: y(series[nowI].best), r: 3.5, style: "fill: var(--mauve)" }, svg);
  return svg;
}
