// Audit-log entries -> human-readable timeline items. Shared by the dashboard Activity card and the Audit Log screen.
import { esc, money, pct, clientName, fmtDay, verdictPill, icon } from "./util.js";

export const CATEGORIES = {
  decision: ["goal_previewed", "goal_rejected", "plan_created", "email_decision", "approval_requested", "approval_decided"],
  effect: ["invoice_sent", "invoice_status", "invoice_reissued", "payout_sent", "payout_status", "payment_simulated"],
  paypal_error: ["paypal_error", "discount_apply_failed"],
  waiting: ["payout_waiting", "payout_held", "invoice_held"],
};
export const categoryOf = (event) => Object.keys(CATEGORIES).find((k) => CATEGORIES[k].includes(event)) || "other";

const ref = (key) => { const p = String(key || "").split(":"); return p.length > 1 ? p.slice(1).join(":").replace(/:approved-(\d+)$/, " (re-sent #$1)") : p[0]; };
const human = (s) => String(s || "").replace(/_/g, " ");
const ok = (label) => `<span class="ok-mark">${esc(label)} ${icon("check")}</span>`;

export function describe(e, clients = []) {
  const d = e && typeof e.details === "object" && e.details ? e.details : {};
  const cn = (id) => clientName(id, clients);
  const base = { id: e.id, ts: e.ts, event: e.event, category: categoryOf(e.event), tone: "", icon: "list", title: human(e.event), kv: [], status: null };
  if (typeof e.details === "string") return { ...base, kv: [["Details", esc(e.details)]] };

  switch (e.event) {
    case "goal_previewed":
      return { ...base, icon: "sparkle", tone: "mauve", title: "Goal read", kv: [["Goal", money(d.goal)], ["Deadline", fmtDay(d.deadline)], ["Read by", esc(d.source || "rules")], ["Summary", esc(d.summary_source || "")]] };
    case "goal_rejected":
      return { ...base, icon: "alert", tone: "amber", title: "Goal not understood", kv: [["Text", esc(d.text)], ["Why", esc(d.reason)]] };
    case "plan_created":
      return { ...base, icon: "route", tone: "mauve", title: "Plan created", status: d.covered ? { label: "Covered", cls: "st-approved" } : { label: "Short", cls: "st-pending" },
        kv: [["Goal", money(d.goal)], ["Deadline", fmtDay(d.deadline)], ["Best case", money(d.best_case)], ["Shortfall", money(d.shortfall)], ["Offers", esc((d.offers || []).join(", ") || "none")]] };
    case "invoice_sent":
      return { ...base, icon: "send", tone: "ice", title: `Invoice ${esc(ref(d.key))} sent via PayPal`,
        kv: [["Client", esc(cn(d.client))], ["Amount", money(d.amount, { cents: true })], ["Due", fmtDay(d.due_date)], ["Action", esc(human(d.action))], ["PayPal ID", `<span class="mono">${esc(d.paypal_invoice_id)}</span>`], ["Reason", esc(d.reason)]] };
    case "invoice_held":
      return { ...base, icon: "hourglass", tone: "amber", title: `Invoice ${esc(ref(d.key))} held`, kv: [["Why", esc(d.reason)]] };
    case "invoice_status": {
      const paid = d.status === "paid";
      return { ...base, icon: paid ? "check" : "refresh", tone: paid ? "lime" : "ice", title: `Invoice ${esc(ref(d.key))} is ${esc(d.status)}`,
        status: paid ? { label: "Paid · confirmed by PayPal", cls: "st-paid" } : { label: human(d.status), cls: "st-sent" },
        kv: [["PayPal ID", `<span class="mono">${esc(d.paypal_invoice_id)}</span>`], ["Source", "PayPal invoice status"]] };
    }
    case "invoice_reissued":
      return { ...base, icon: "refresh", tone: "lime", title: `Invoice ${esc(ref(d.old_key))} re-sent at ${pct(d.discount_pct)} off`, status: { label: "Approved", cls: "st-approved" },
        kv: [["Old amount", money(d.old_amount, { cents: true })], ["New amount", money(d.new_amount, { cents: true })], ["Approval", `#${esc(d.approval_id)}`], ["Old invoice", "cancelled in PayPal"]] };
    case "discount_apply_failed":
      return { ...base, icon: "alert", tone: "coral", title: "Discount could not be applied", status: { label: "PayPal error", cls: "st-error" },
        kv: [["Invoice", esc(ref(d.key))], ["Error", esc(d.error)], ["What happened", esc(d.reason)]] };
    case "paypal_error":
      return { ...base, icon: "plug-off", tone: "coral", title: `PayPal ${esc(d.step || "call")} failed`, status: { label: "Will retry", cls: "st-error" },
        kv: [["Item", esc(ref(d.key))], ["Error", esc(d.error)], ["What happens", esc(d.reason)]] };
    case "payout_sent":
      return { ...base, icon: "out", tone: "white", title: `Payout to ${esc(d.contractor)} sent`, status: { label: "Released", cls: "st-approved" },
        kv: [["Amount", money(d.amount, { cents: true })], ["Batch", `<span class="mono">${esc(d.batch_id)}</span>`], ["Paid from", "cleared client money"]] };
    case "payout_status":
      return { ...base, icon: "out", tone: "white", title: `Payout ${esc(d.status)}`, status: { label: human(d.status), cls: d.status === "success" ? "st-approved" : "st-pending" },
        kv: [["Batch", `<span class="mono">${esc(d.batch_id)}</span>`]] };
    case "payout_waiting":
      return { ...base, icon: "hourglass", tone: "amber", title: `Payout to ${esc(d.contractor)} waiting`, status: { label: "Waiting for cleared money", cls: "st-waiting" },
        kv: [["Amount", money(d.amount, { cents: true })], ["Why", esc(d.reason)]] };
    case "payout_held":
      return { ...base, icon: "lock", tone: "amber", title: `Payout to ${esc(d.contractor)} held`, status: { label: "Needs approval", cls: "st-pending" },
        kv: [["Amount", money(d.amount, { cents: true })], ["Why", esc(d.reason)]] };
    case "payment_simulated":
      return { ...base, icon: "zap", tone: "", title: `Demo: client paid ${esc(ref(d.key))}`, kv: [["Note", "Fake PayPal marked it paid. Float still waits for the next PayPal status check."]] };
    case "email_decision": {
      const tone = { allow: "lime", needs_approval: "amber", block: "coral" }[d.decision] || "";
      return { ...base, icon: d.decision === "block" ? "ban" : "shield", tone, title: `Guard: ${esc(d.sender || "email")}`,
        statusHtml: verdictPill(d.decision),
        kv: [["Client", esc(d.client ? cn(d.client) : "unknown")], ["AI read", esc(human(d.intent))], ["Rules", esc((d.reasons || []).join(" "))]] };
    }
    case "approval_requested":
      return { ...base, icon: "hourglass", tone: "amber", title: `Approval #${esc(d.approval_id)} requested`, status: { label: "Pending", cls: "st-pending" },
        kv: [["Email", esc(d.email_id)], ["Why", esc((d.reasons || []).join(" "))]] };
    case "approval_decided": {
      const yes = d.status === "approved";
      return { ...base, icon: yes ? "check" : "x", tone: yes ? "lime" : "", title: `Approval #${esc(d.approval_id)} ${esc(d.status)}`,
        statusHtml: yes ? ok("Approved") : `<span class="pill st-rejected">Rejected</span>`,
        kv: [["Client", esc(cn(d.client))], ["Request", esc(human(d.intent))], ["Effect", esc(d.effect || d.reason)]] };
    }
    default:
      return { ...base, kv: Object.entries(d).slice(0, 6).map(([k, v]) => [esc(human(k)), esc(typeof v === "object" ? JSON.stringify(v) : v)]) };
  }
}

export function renderKv(kv) {
  return `<dl class="kv">${kv.filter(([, v]) => v !== "" && v !== undefined && v !== null && v !== "—")
    .map(([k, v]) => `<div class="${String(v).length > 60 ? "full" : ""}"><dt>${k}</dt><dd>${v}</dd></div>`).join("")}</dl>`;
}
