// Thin client for ui/server.py. Every call returns parsed JSON or throws an Error with the server's message.

const TIMEOUT_MS = 20000;

async function request(path, { method = "GET", body } = {}) {
  const ctrl = new AbortController();
  const timer = setTimeout(() => ctrl.abort(), TIMEOUT_MS);
  try {
    const r = await fetch(path, {
      method,
      signal: ctrl.signal,
      headers: body !== undefined ? { "Content-Type": "application/json" } : {},
      body: body !== undefined ? JSON.stringify(body) : undefined,
    });
    let data = null;
    try { data = await r.json(); } catch { /* empty body */ }
    if (!r.ok) throw new Error((data && data.error) || `HTTP ${r.status}`);
    return data;
  } catch (e) {
    if (e.name === "AbortError") throw new Error("The server took too long to answer.");
    if (e instanceof TypeError) throw new Error("Can't reach the Float server.");
    throw e;
  } finally {
    clearTimeout(timer);
  }
}

const get = (p) => request(p);
const post = (p, body = {}) => request(p, { method: "POST", body });

export const api = {
  // original routes (unchanged shapes)
  mode: () => get("/api/mode"),
  preview: (text) => post("/api/preview", { text }),
  launch: (amount, deadline) => post("/api/launch", { amount, deadline }),
  tick: (gid) => get(`/api/tick/${encodeURIComponent(gid)}`),
  pay: (key) => post(`/api/pay/${key.split("/").map(encodeURIComponent).join("/")}`),
  email: (email) => post("/api/email", email),
  approvals: (status = "pending") => get(`/api/approvals?status=${encodeURIComponent(status)}`),
  decide: (id, approve) => post("/api/decide", { id, approve }),
  audit: (limit = 100) => get(`/api/audit?limit=${limit}`),
  // new read-mostly routes
  meta: () => get("/api/meta"),
  dashboard: ({ tick = false, goalId = null } = {}) =>
    get(`/api/dashboard?${tick ? "tick=1&" : ""}${goalId ? `goal_id=${encodeURIComponent(goalId)}` : ""}`),
  state: (gid) => get(`/api/state/${encodeURIComponent(gid)}`),
  emails: (limit = 200) => get(`/api/emails?limit=${limit}`),
  samples: () => get("/api/samples"),
  simulateEmail: (id) => post(`/api/simulate/email/${encodeURIComponent(id)}`),
  outage: (checks = 6) => post("/api/simulate/outage", { checks }),
  reset: () => post("/api/simulate/reset"),
};

/** Poll fn every `seconds` without overlapping calls, paused while the tab is hidden, with backoff on errors.
 *  Returns { stop, now }. onError gets the Error; the loop keeps going. */
export function poll(fn, seconds, { onError = () => {}, immediate = false } = {}) {
  let timer = null, stopped = false, running = false, fails = 0;
  const run = async () => {
    if (stopped || running) return;
    if (document.hidden) { schedule(); return; }
    running = true;
    try { await fn(); fails = 0; } catch (e) { fails += 1; onError(e); }
    running = false;
    schedule();
  };
  const schedule = () => {
    clearTimeout(timer);
    if (!stopped) timer = setTimeout(run, seconds * 1000 * Math.min(4, 1 + fails));
  };
  const onVis = () => { if (!document.hidden) { clearTimeout(timer); run(); } };
  document.addEventListener("visibilitychange", onVis);
  immediate ? run() : schedule();
  return {
    stop() { stopped = true; clearTimeout(timer); document.removeEventListener("visibilitychange", onVis); },
    now() { clearTimeout(timer); return run(); },
  };
}
