// "Payment-delay estimate": per invoice, the client's past days-late as pale-blue dots inside a capsule (min..max),
// the predicted days late as a bright dot, a mean line, a shaded typical band, and max/min labels.
import { s, root, lin } from "./svg.js";
import { showTip, hideTip, esc, initials } from "../util.js";

export function renderDelays(host, rows, { height = 150, animate = true } = {}) {
  const all = rows.flatMap((r) => r.hist.concat([r.predicted]));
  const hi = Math.max(6, ...all) + 1;
  const { svg, w, h } = root(host, height, `Predicted days late per invoice, from each client's payment history. Up to ${hi - 1} days.`);
  const L = 26, R = 46, T = 10, B = 22;
  const y = lin(0, hi, h - B, T);
  const n = Math.max(1, rows.length), step = (w - L - R) / n;
  const histAll = rows.flatMap((r) => r.hist);
  const mean = histAll.length ? histAll.reduce((a, b) => a + b, 0) / histAll.length : 0;
  const sd = histAll.length ? Math.sqrt(histAll.reduce((a, b) => a + (b - mean) ** 2, 0) / histAll.length) : 0;
  const mx = all.length ? Math.max(...all) : 0, mn = all.length ? Math.min(...all) : 0;

  s("rect", { x: L, width: w - L - R, y: y(mean + sd), height: Math.max(2, y(Math.max(0, mean - sd)) - y(mean + sd)), rx: 8, style: "fill: var(--ice-12)" }, svg);
  for (const v of [0, Math.round(hi / 2), hi]) s("text", { x: L - 8, y: y(v) + 3, "text-anchor": "end", style: "fill: var(--muted); font-size: 10px", text: `${v}d` }, svg);
  s("line", { x1: L, x2: w - R, y1: y(mean), y2: y(mean), style: "stroke: var(--ice-45); stroke-dasharray: 4 4" }, svg);
  s("text", { x: w - R + 6, y: y(mean) + 3, style: "fill: var(--ice); font-size: 10px", text: `avg ${mean.toFixed(1)}` }, svg);
  s("text", { x: w - R + 6, y: y(mx) + 3, style: "fill: var(--muted); font-size: 10px", text: `max ${mx}` }, svg);
  if (mn !== mx) s("text", { x: w - R + 6, y: Math.min(h - B - 2, y(mn) + 3), style: "fill: var(--muted); font-size: 10px", text: `min ${mn}` }, svg);

  rows.forEach((r, i) => {
    const cx = L + step * i + step / 2;
    const g = s("g", { class: animate ? "fade-in" : null, style: `animation-delay:${i * 60}ms` }, svg);
    const lo = Math.min(...r.hist, r.predicted), top = Math.max(...r.hist, r.predicted);
    s("rect", { x: cx - 4, y: y(top) - 4, width: 8, height: Math.max(8, y(lo) - y(top) + 8), rx: 4, style: "fill: var(--ice-25)" }, g);
    r.hist.forEach((v, j) => s("circle", { cx: cx + (j % 2 ? 7 : -7) * (r.hist.filter((x) => x === v).length > 1 ? 1 : 0), cy: y(v), r: 2.2, style: "fill: var(--ice)" }, g));
    s("circle", { cx, cy: y(r.predicted), r: 4.5, style: `fill: var(${r.atRisk ? "--amber" : "--ice"}); stroke: var(--bg-card); stroke-width: 2` }, g);
    s("text", { x: cx, y: h - 6, "text-anchor": "middle", style: `fill: var(${r.atRisk ? "--amber" : "--muted"}); font-size: 10px; font-weight: 600`, text: initials(r.name) }, svg);
    const hit = s("rect", { x: cx - step / 2, y: T, width: step, height: h - B - T, style: "fill: transparent" }, svg);
    hit.addEventListener("pointermove", (e) => showTip(
      `<div class="tip-t">${esc(r.name)} · ${esc(r.invoice_id)}</div>
       <div class="tip-v ${r.atRisk ? "t-amber" : "t-ice"}">~${r.predicted} day${r.predicted === 1 ? "" : "s"} late</div>
       <div class="tip-s">Past payments: ${r.hist.length ? r.hist.map((v) => `${v}d`).join(", ") : "no history (assumed 7d)"}.<br>
       ${r.status === "paid" ? "Already paid, confirmed by PayPal." : r.atRisk ? "Lands after your deadline." : `Has ${Math.max(0, r.slack)} day(s) of slack before the deadline.`}</div>`, e.clientX, e.clientY));
    hit.addEventListener("pointerleave", hideTip);
  });
  return svg;
}
