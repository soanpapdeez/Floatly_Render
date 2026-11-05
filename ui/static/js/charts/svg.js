// Tiny SVG toolkit shared by every chart: element builder, scales, ticks, smooth paths, draw-in, resize.
export const NS = "http://www.w3.org/2000/svg";

/** s("rect", {x, y, style: "fill: var(--lime)"}, parent) -> SVGElement. null/undefined attrs are skipped. */
export function s(tag, attrs = {}, parent = null) {
  const el = document.createElementNS(NS, tag);
  for (const [k, v] of Object.entries(attrs)) {
    if (v === null || v === undefined || v === false) continue;
    if (k === "text") el.textContent = v;
    else if (k === "class") el.setAttribute("class", v);
    else el.setAttribute(k, typeof v === "number" ? +v.toFixed(2) : v);
  }
  if (parent) parent.appendChild(el);
  return el;
}

/** Fresh <svg> sized to the host's current width. Returns { svg, w, h }. */
export function root(host, height, label) {
  host.innerHTML = "";
  const w = Math.max(220, Math.round(host.clientWidth || host.getBoundingClientRect().width || 320));
  const svg = s("svg", { viewBox: `0 0 ${w} ${height}`, width: w, height, role: "img", "aria-label": label, preserveAspectRatio: "xMidYMid meet" }, host);
  return { svg, w, h: height };
}

export const lin = (d0, d1, r0, r1) => (v) => r0 + ((v - d0) / (d1 - d0 || 1)) * (r1 - r0);

export function niceMax(v) {
  if (!(v > 0)) return 1;
  const p = Math.pow(10, Math.floor(Math.log10(v)));
  const n = v / p;
  return (n <= 1 ? 1 : n <= 2 ? 2 : n <= 2.5 ? 2.5 : n <= 5 ? 5 : 10) * p;
}

export const fmtAxis = (v) => (v >= 1000 ? `${+(v / 1000).toFixed(1)}k` : `${Math.round(v)}`);

/** Monotone cubic (Fritsch–Carlson) path through points [{x, y}] — smooth without overshooting. */
export function smooth(pts) {
  const n = pts.length;
  if (n === 0) return "";
  if (n === 1) return `M${pts[0].x},${pts[0].y}`;
  const dx = [], dy = [], m = [], t = [];
  for (let i = 0; i < n - 1; i++) { dx[i] = pts[i + 1].x - pts[i].x; dy[i] = pts[i + 1].y - pts[i].y; m[i] = dx[i] ? dy[i] / dx[i] : 0; }
  t[0] = m[0]; t[n - 1] = m[n - 2];
  for (let i = 1; i < n - 1; i++) t[i] = m[i - 1] * m[i] <= 0 ? 0 : (m[i - 1] + m[i]) / 2;
  for (let i = 0; i < n - 1; i++) {
    if (m[i] === 0) { t[i] = 0; t[i + 1] = 0; continue; }
    const a = t[i] / m[i], b = t[i + 1] / m[i], h = a * a + b * b;
    if (h > 9) { const k = 3 / Math.sqrt(h); t[i] = k * a * m[i]; t[i + 1] = k * b * m[i]; }
  }
  let d = `M${pts[0].x.toFixed(2)},${pts[0].y.toFixed(2)}`;
  for (let i = 0; i < n - 1; i++) {
    const c = dx[i] / 3;
    d += `C${(pts[i].x + c).toFixed(2)},${(pts[i].y + c * t[i]).toFixed(2)} ${(pts[i + 1].x - c).toFixed(2)},${(pts[i + 1].y - c * t[i + 1]).toFixed(2)} ${pts[i + 1].x.toFixed(2)},${pts[i + 1].y.toFixed(2)}`;
  }
  return d;
}

/** Give a path a stroke draw-in animation (CSS .draw-line), only the first time a chart renders. */
export function drawIn(path, animate) {
  if (!animate) return path;
  try { const len = Math.ceil(path.getTotalLength()); path.style.setProperty("--len", len); path.classList.add("draw-line"); } catch { /* not in DOM */ }
  return path;
}

/** Re-render on width changes (debounced). Returns the observer. */
export function onResize(host, fn) {
  let w = host.clientWidth, t = null;
  const ro = new ResizeObserver(() => {
    if (Math.abs(host.clientWidth - w) < 4) return;
    w = host.clientWidth; clearTimeout(t); t = setTimeout(fn, 120);
  });
  ro.observe(host);
  return ro;
}

let gid = 0;
export const uid = (p = "g") => `${p}${++gid}`;
