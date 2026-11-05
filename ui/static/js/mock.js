// Mock-data fallback: lets every card render (clearly labelled "Sample") when the server has no goal yet
// or an endpoint is empty. Shapes match /api/dashboard. Dates are relative to today so it never looks stale.
import { addDays, isoDay, day } from "./util.js";

const CLIENTS = [
  { client_id: "acme", name: "Acme", history_days_late: [0, 2, 0], expected_days_late: 1 },
  { client_id: "brightco", name: "BrightCo", history_days_late: [0, 0, 1], expected_days_late: 1 },
  { client_id: "zenlabs", name: "ZenLabs", history_days_late: [5, 9], expected_days_late: 7 },
  { client_id: "northwind", name: "Northwind", history_days_late: [0, 0, 1, 0], expected_days_late: 1 },
  { client_id: "skyline", name: "Skyline", history_days_late: [0, 0], expected_days_late: 0 },
  { client_id: "pixelforge", name: "PixelForge", history_days_late: [0, 3], expected_days_late: 2 },
];

export function mockDashboard(todayIso) {
  const today = day(todayIso) || day(new Date());
  const toFri = ((5 - today.getDay() + 7) % 7) || 7;
  const deadline = addDays(today, Math.max(3, toFri));
  const D = (n) => isoDay(addDays(today, n));
  const dl = isoDay(deadline), span = Math.round((deadline - today) / 86400000);
  const item = (id, c, amount, due, late, action = "reminder", pct = 0, reason = "") => ({
    invoice_id: id, client_id: c, amount, due_date: D(due), expected_pay_date: D(due + late), action, discount_pct: pct,
    cash_if_paid: Math.round(amount * (1 - pct / 100) * 100) / 100, remind_on: D(due - 2), reason,
  });
  const items = [
    item("OPEN-004", "northwind", 3500, span + 1, 1, "early_pay_offer", 2, "Northwind usually pays a day after the due date, which is after your deadline. Offering 2% off if they pay by the deadline (costs $70.00) is the cheapest way to close the gap."),
    item("OPEN-005", "skyline", 600, 0, 0, "reminder", 0, "Skyline usually pays on the due date, so this should arrive before your deadline. No discount needed."),
    item("OPEN-001", "acme", 1500, 1, 1, "reminder", 0, "Acme usually pays about 1 day after the due date, before your deadline. No discount needed."),
    item("OPEN-002", "brightco", 950, 2, 1, "reminder", 0, "BrightCo usually pays about 1 day after the due date, before your deadline. No discount needed."),
    item("OPEN-006", "pixelforge", 450, span + 2, 2, "reminder", 0, "PixelForge will probably pay after your deadline, but a discount isn't needed to reach the goal."),
    item("OPEN-003", "zenlabs", 2000, 1, 7, "reminder", 0, "ZenLabs will probably pay after your deadline, but a discount isn't needed to reach the goal."),
  ];
  const now = Date.now() / 1000;
  const email = (i, sender, client, intent, pct, decision, reasons, bank = null) => ({
    row: i, ts: now - (8 - i) * 1800, email_id: `sample-${i}`, sender, subject: "Sample", body: null, sample_id: null, partial: false,
    extracted: { client_id: client, intent, discount_pct: pct, new_bank_account: bank, new_due_date: null }, decision, reasons, approval_id: null,
  });
  const emails = [
    email(7, "billing@acme-pay.com", "acme", "discount_request", 70, "block", ["Sender billing@acme-pay.com is not a known email for Acme (possible spoofing).", "Requested discount 70% exceeds the 10% limit."]),
    email(6, "ap@northwind.com", "northwind", "bank_change", null, "needs_approval", ["New bank account is not on file; verify with the client through another channel."], "ACC-NORTH-777"),
    email(5, "finance@zenlabs.in", "zenlabs", "discount_request", 8, "needs_approval", ["Discount 8% is above 5% and needs human approval."]),
    email(4, "accounts@brightco.io", "brightco", "discount_request", 3, "allow", ["All checks passed."]),
    email(3, "accounts@brightco-billing.com", "brightco", "bank_change", null, "block", ["Sender accounts@brightco-billing.com is not a known email for BrightCo (possible spoofing)."], "ACC-EVIL-999"),
    email(2, "billing@acme.com", "acme", "discount_request", 15, "block", ["Requested discount 15% exceeds the 10% limit."]),
    email(1, "billing@acme.com", "acme", "payment_confirmation", null, "allow", ["All checks passed."]),
  ];
  const expected = items.filter((i) => i.expected_pay_date <= dl).reduce((s, i) => s + i.amount, 0);
  const best = expected + items.filter((i) => i.action === "early_pay_offer").reduce((s, i) => s + i.cash_if_paid, 0);
  return {
    sample: true, launched: false, plan_source: "sample", today: isoDay(today), now,
    clients: CLIENTS,
    contractors: [{ contractor_id: "ravi-dev", name: "Ravi (developer)", amount_due: 1200 }, { contractor_id: "meera-design", name: "Meera (designer)", amount_due: 1800 }],
    goal: { amount: 6000, deadline: dl, deadline_label: deadline.toLocaleDateString("en-GB", { weekday: "long", day: "numeric", month: "short", year: "numeric" }), goal_id: null },
    plan: { goal_amount: 6000, deadline: dl, expected_on_track: expected, best_case: best, shortfall: Math.max(0, 6000 - best), covered: best >= 6000, total_discount_cost: 70, items },
    summary: { text: `Sample plan. Float expects $${expected.toLocaleString()} from clients who usually pay in time and offers Northwind 2% off to pay early, which brings the best case to $${best.toLocaleString()}.`, source: "sample" },
    state: null, approvals: { pending: 0, items: [] }, emails, guard_counts: { allow: 2, needs_approval: 2, block: 3 },
    audit: [
      { id: 1, ts: now - 5400, event: "goal_previewed", details: { goal: 6000, deadline: dl, source: "rules", summary_source: "template" } },
      { id: 2, ts: now - 3600, event: "email_decision", details: { email_id: "sample-7", sender: "billing@acme-pay.com", client: "acme", intent: "discount_request", decision: "block", reasons: ["Requested discount 70% exceeds the 10% limit."] } },
      { id: 3, ts: now - 1800, event: "email_decision", details: { email_id: "sample-6", sender: "ap@northwind.com", client: "northwind", intent: "bank_change", decision: "needs_approval", reasons: ["New bank account is not on file; verify with the client through another channel."] } },
    ],
    paypal_errors: [],
  };
}
