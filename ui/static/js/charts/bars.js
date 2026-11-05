// "Cash by deadline": expected incoming per day (bright lime thin rounded bars) and the best case with every
// early-pay offer accepted (dimmer, shorter bars beside them). Dashed vertical gridlines, deadline marker.
import { s, root, lin, niceMax, fmtAxis } from "./svg.js";
import { money, fmtDay, showTip, hideTip, esc } from "../util.js";

export function renderBars(host, daily, { height = 150, animate = true } = {}) {
  const max = niceMax(Math.max(1, ...daily.map((d) => Math.max(d.expected, d.best))));
  const { svg, w, h } = root(host, height, `Expected incoming per day. Highest day ${money(max)}.`);
  const L = 30, R = 6, T = 8, B = 22;
  const n = daily.length, step = (w - L - R) / n;
  const y = lin(0, max, h - B, T);
  const bw = Math.max(3, Math.min(8, step * 0.18));

  for (const v of [0, max / 2, max]) {
    s("text", { x: L - 8, y: y(v) + 3, "text-anchor": "end", style: "fill: var(--muted); font-size: 10px", text: fmtAxis(v) }, svg);
  }
  let lastLabel = null;
  daily.forEach((d, i) => {
    const cx = L + step * i + step / 2;
    s("line", { x1: cx, x2: cx, y1: T, y2: h - B, style: "stroke: var(--white-06); stroke-dasharray: 2 4" }, svg);
    if (d.isDeadline) {
      s("line", { x1: cx + step / 2, x2: cx + step / 2, y1: T - 4, y2: h - B, style: "stroke: var(--mauve); stroke-dasharray: 3 3; stroke-width: 1.2" }, svg);
      s("text", { x: cx + step / 2 - 4, y: T + 4, "text-anchor": "end", style: "fill: var(--mauve); font-size: 10px; font-weight: 600", text: "deadline" }, svg);
    }
    const g = s("g", {}, svg);
    const bar = (val, x, style, delay) => {
      if (!(val > 0)) return;
      const top = y(val), ht = Math.max(bw, h - B - top);
      s("rect", { x: x - bw / 2, y: h - B - ht, width: bw, height: ht, rx: bw / 2, style: `${style}; animation-delay:${delay}ms`, class: animate ? "grow-y" : null }, g);
    };
    const moved = Math.abs(d.best - d.expected) > 0.005;
    bar(d.expected, moved ? cx - bw * 0.8 : cx, `fill: var(--lime); opacity: ${d.past && !d.isToday ? 0.55 : 1}`, i * 40);
    if (moved) bar(d.best, cx + bw * 0.8, "fill: var(--lime); opacity: .32", i * 40 + 60);
    const every = Math.ceil(n / Math.max(2, Math.floor((w - L) / 64)));
    const want = i % every === 0 || d.isDeadline || i === n - 1;
    if (want && (lastLabel === null || cx - lastLabel > 40)) {
      lastLabel = cx;
      s("text", { x: cx, y: h - 6, "text-anchor": "middle", style: `fill: var(${d.isDeadline ? "--text" : "--muted"}); font-size: 10px`, text: d.isToday ? "today" : fmtDay(d.date, { weekday: false }) }, svg);
    }
    const hit = s("rect", { x: L + step * i, y: T, width: step, height: h - B - T, style: "fill: transparent", tabindex: -1 }, svg);
    hit.addEventListener("pointermove", (e) => showTip(
      `<div class="tip-t">${esc(fmtDay(d.date))}${d.isDeadline ? ' <span class="tag mauve">deadline</span>' : ""}</div>
       <div class="tip-v t-lime">${money(d.expected)}</div><div class="tip-s">expected (no discounts)</div>
       ${moved ? `<div class="tip-s" style="margin-top:6px"><b class="t-2">${money(d.best)}</b> if every offer is accepted</div>` : ""}`, e.clientX, e.clientY));
    hit.addEventListener("pointerleave", hideTip);
  });
  s("line", { x1: L, x2: w - R, y1: h - B, y2: h - B, style: "stroke: var(--border-strong)" }, svg);
  return svg;
}
