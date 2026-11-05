// Turns the /api/dashboard payload into plain view-model JSON that the chart modules render.
// Everything here is arithmetic on Float's own records: plan (from client payment history) + PayPal state.
// Nothing is ever read from email text.
import { day, isoDay, addDays, daysBetween, clientName } from "./util.js";

const baseId = (key) => String(key || "").split(":")[1] || key;

/** PayPal-confirmed paid timestamps by invoice key, from the audit log (invoice_status -> paid). */
function paidTimes(audit = []) {
  const out = {};
  for (const e of audit) {
    const d = e && typeof e.details === "object" ? e.details : null;
    if (d && e.event === "invoice_status" && d.status === "paid" && typeof e.ts === "number") out[d.key] = e.ts;
  }
  return out;
}

export function buildModel(p) {
  const today = day(p.today) || day(new Date());
  const clients = p.clients || [];
  const goal = p.goal || {};
  const plan = p.plan || { items: [] };
  const deadline = day(goal.deadline || plan.deadline) || addDays(today, 3);
  const gid = goal.goal_id || "";
  const invoices = (p.state && p.state.invoices) || [];
  const paidAt = paidTimes(p.audit);

  // latest non-cancelled PayPal invoice per plan invoice (a re-sent discounted invoice replaces the cancelled one)
  const byBase = {};
  for (const inv of invoices) {
    const b = baseId(inv.key);
    (byBase[b] = byBase[b] || []).push(inv);
  }

  const items = (plan.items || []).map((it) => {
    const group = (byBase[it.invoice_id] || []).slice().sort((a, b) => (a.created_at || 0) - (b.created_at || 0));
    const live = group.filter((g) => g.status !== "cancelled");
    const inv = live[live.length - 1] || group[group.length - 1] || null;
    const offer = it.action === "early_pay_offer";
    const status = inv ? inv.status : p.launched ? "held" : "draft";
    const amount = inv ? inv.amount : it.cash_if_paid;
    const expected = day(it.expected_pay_date);
    const best = offer ? deadline : expected;
    let landed = null;
    if (status === "paid") landed = day(new Date((paidAt[inv.key] || p.now || Date.now() / 1000) * 1000));
    return {
      invoice_id: it.invoice_id, client_id: it.client_id, name: clientName(it.client_id, clients),
      amount, original: it.amount, cash_if_paid: it.cash_if_paid, due: it.due_date,
      expected: isoDay(expected), best: isoDay(best), offer,
      discount_pct: inv && inv.discount_pct ? inv.discount_pct : it.discount_pct,
      reason: it.reason, status, key: inv ? inv.key : `${gid}:${it.invoice_id}`, paypal_id: inv ? inv.paypal_invoice_id : null,
      reissued: !!(inv && /:approved-\d+$/.test(inv.key)), cancelledCount: group.length - live.length,
      atRisk: status !== "paid" && expected > deadline,
      landed: landed ? isoDay(landed) : null,
    };
  });

  // when each item's money lands, in the realistic and the best case (cancelled = nothing lands)
  const landing = items.filter((i) => i.status !== "cancelled").map((i) => {
    if (i.landed) return { ...i, expDay: day(i.landed), bestDay: day(i.landed), paid: true };
    const clampToday = (d) => (d < today ? today : d);
    return { ...i, expDay: clampToday(day(i.expected)), bestDay: clampToday(day(i.best)), paid: false };
  });

  const received = landing.filter((l) => l.paid).reduce((s, l) => s + l.amount, 0);
  const byDeadline = (k) => landing.filter((l) => l[k] <= deadline).reduce((s, l) => s + l.amount, 0);
  const projected = byDeadline("expDay"), best = byDeadline("bestDay");
  const target = +goal.amount || +plan.goal_amount || 0;
  const shortfall = Math.max(0, Math.round((target - best) * 100) / 100);

  // per-day buckets from today (or the first payment) to the later of deadline / last expected payment
  const firstDay = landing.reduce((m, l) => (l.expDay < m ? l.expDay : m), today);
  const lastDay = landing.reduce((m, l) => (l.expDay > m ? l.expDay : m), deadline < today ? addDays(today, 3) : deadline);
  const span = Math.max(1, daysBetween(firstDay, lastDay));
  const daily = [];
  for (let k = 0; k <= span; k++) {
    const d = addDays(firstDay, k), iso = isoDay(d);
    daily.push({
      date: iso,
      expected: landing.filter((l) => isoDay(l.expDay) === iso).reduce((s, l) => s + l.amount, 0),
      best: landing.filter((l) => isoDay(l.bestDay) === iso).reduce((s, l) => s + l.amount, 0),
      isDeadline: iso === isoDay(deadline), isToday: iso === isoDay(today), past: d < today,
    });
  }

  // cumulative series in 6-hour steps (payments are placed at noon of their day)
  const series = [];
  const start = firstDay, end = addDays(lastDay, 1);
  for (let t = new Date(start); t <= end; t = new Date(t.getTime() + 6 * 3600 * 1000)) {
    const at = (k) => landing.filter((l) => new Date(l[k].getTime() + 12 * 3600 * 1000) <= t).reduce((s, l) => s + l.amount, 0);
    series.push({ t: t.getTime(), best: at("bestDay"), expected: at("expDay") });
  }

  // payment-delay estimate per invoice (from the client's paid history)
  const delays = items.map((i) => {
    const c = clients.find((x) => x.client_id === i.client_id) || {};
    const hist = c.history_days_late || [];
    return { invoice_id: i.invoice_id, client_id: i.client_id, name: i.name, hist,
      predicted: c.expected_days_late ?? (hist.length ? Math.ceil(hist.reduce((a, b) => a + b, 0) / hist.length) : 7),
      slack: daysBetween(i.due, deadline), atRisk: i.atRisk, status: i.status };
  }).sort((a, b) => a.predicted - b.predicted);

  // Guard activity: one capsule per email, at the requested discount % (null = no discount asked)
  const guard = (p.emails || []).slice().reverse().map((e) => ({
    ts: e.ts, pct: e.extracted ? e.extracted.discount_pct : null, decision: e.decision, sender: e.sender,
    client: e.extracted && e.extracted.client_id ? clientName(e.extracted.client_id, clients) : "Unknown",
    intent: e.extracted ? e.extracted.intent : null, reason: (e.reasons || [])[0] || "",
  }));

  // payouts: released ones, and where the plan's cash would cover the rest
  const payouts = (p.state && p.state.payouts) || [];
  const contractors = p.contractors || [];
  let need = 0;
  const payoutPlan = contractors.map((c) => {
    need += +c.amount_due;
    const done = payouts.find((x) => x.contractor_id === c.contractor_id);
    const cover = series.find((s) => s.best >= need);
    return { id: c.contractor_id, name: c.name, amount: +c.amount_due, released: !!done, status: done ? done.status : "waiting",
      at: done ? isoDay(today) : cover ? isoDay(new Date(cover.t)) : null, need };
  });

  const nowS = p.now || Date.now() / 1000, dayAgo = nowS - 86400;
  const live = invoices.filter((i) => i.status !== "cancelled");
  const blocked = (p.emails || []).filter((e) => e.decision === "block");
  const stats = {
    sent: live.length, planned: items.length,
    sentToday: live.filter((i) => (i.created_at || 0) > dayAgo).length,
    paidCount: live.filter((i) => i.status === "paid").length, paidAmount: received,
    payoutsCount: payouts.length, payoutsAmount: payouts.reduce((s, x) => s + (+x.amount || 0), 0),
    payoutsWaiting: Math.max(0, contractors.length - payouts.length),
    blocked: blocked.length, blockedToday: blocked.filter((e) => (e.ts || 0) > dayAgo).length,
    needsApproval: (p.approvals && p.approvals.pending) || 0,
  };

  return {
    sample: !!p.sample, launched: !!p.launched, planSource: p.plan_source, today: isoDay(today), deadline: isoDay(deadline),
    goal: { amount: target, deadline: isoDay(deadline), label: goal.deadline_label, goal_id: gid },
    items, received, projected, best, shortfall, covered: shortfall === 0,
    totalDiscountCost: plan.total_discount_cost || 0,
    daily, series, delays, guard, payoutPlan, stats,
    approvals: (p.approvals && p.approvals.items) || [],
    emails: p.emails || [],
  };
}
