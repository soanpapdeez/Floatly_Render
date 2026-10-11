"""
Orchestrator: goal -> plan -> PayPal invoices -> watch payments -> pay contractors, with an audit log.

Rules this file enforces (say them in the README and the demo):
  1. PayPal is the ONLY source of truth for "paid". An email can never mark anything paid.
  2. Amounts and due dates come from our own records / the plan, never from email text.
  3. Every PayPal action is idempotent: invoices are keyed in the store, payouts carry a fixed request id,
     so re-running any step never double-sends or double-pays.
  4. Outgoing discounts and payouts respect Guard's limits; anything above goes to a human.
  5. Every decision is written to the audit log with its reason.

Demo env vars (all optional, sandbox only):
  DEMO_PAYER_EMAIL        sandbox PERSONAL account that receives (and pays) every invoice
  DEMO_CONTRACTOR_EMAIL   sandbox PERSONAL account that receives every contractor payout
  DEMO_AMOUNT_SCALE       multiply amounts sent to PayPal (e.g. 0.01) if the sandbox balance is too small
"""
import json
import os
from datetime import date
from typing import Optional

from . import guard
from .data import DATA_DIR
from .pipeline import process_email, find_client_by_sender
from .planner import make_plan, Plan
from .store import Store

PAYOUT_CURRENCY = "USD"
FINAL_PAYOUT_STATES = {"success", "denied", "canceled"}


def make_goal_id(goal_amount: float, deadline: str) -> str:
    return f"goal-{deadline}-{int(goal_amount)}"


def load_contractors() -> list:
    return json.loads((DATA_DIR / "contractors.json").read_text(encoding="utf-8"))


def _scale() -> float:
    return float(os.getenv("DEMO_AMOUNT_SCALE", "1"))


# ------------------------------------------------------------------ 1. issue invoices

def issue_invoices(plan: Plan, goal_id: str, clients: dict, *, paypal, store: Store,
                   today: Optional[str] = None) -> list:
    """Create + send one PayPal invoice per plan item. Safe to re-run: already-issued items are skipped."""
    today = today or date.today().isoformat()
    scale = _scale()
    issued = []
    for item in plan.items:
        key = f"{goal_id}:{item.invoice_id}"
        existing = store.get_invoice(key)
        if existing:
            issued.append(existing)
            continue

        if item.discount_pct > guard.APPROVAL_DISCOUNT_PCT:
            store.audit("invoice_held", key=key, reason=f"Discount {item.discount_pct:g}% is above the auto limit; needs approval.")
            continue

        client = clients[item.client_id]
        if item.action == "early_pay_offer":
            planned_due, label = plan.deadline, f"Invoice {item.invoice_id} (early-pay {item.discount_pct:g}% off)"
        else:
            planned_due, label = item.due_date, f"Invoice {item.invoice_id}"
        due = max(planned_due, today)                       # PayPal should never get a due date in the past
        amount = round(item.cash_if_paid, 2)
        payer = os.getenv("DEMO_PAYER_EMAIL") or client.known_emails[0]

        paypal_id = paypal.create_and_send_invoice({"email": payer, "item": label},
                                                   round(amount * scale, 2), due, currency=client.currency)
        store.save_invoice(key, goal_id, client.client_id, paypal_id, amount, due, item.discount_pct)
        store.audit("invoice_sent", key=key, paypal_invoice_id=paypal_id, client=client.client_id,
                    amount=amount, due_date=due, action=item.action, reason=item.reason)
        issued.append(store.get_invoice(key))
    return issued


# ------------------------------------------------------------------ 2. watch payments (PayPal = truth)

def refresh_invoices(goal_id: str, *, paypal, store: Store) -> list:
    for inv in store.list_invoices(goal_id):
        if inv["status"] in ("paid", "cancelled"):
            continue
        status = paypal.get_invoice_status(inv["paypal_invoice_id"])
        if status != inv["status"]:
            store.set_invoice_status(inv["key"], status)
            store.audit("invoice_status", key=inv["key"], paypal_invoice_id=inv["paypal_invoice_id"], status=status)
    return store.list_invoices(goal_id)


# ------------------------------------------------------------------ 3. pay contractors

def pay_contractors(goal_id: str, contractors: list, *, paypal, store: Store) -> list:
    """Pay each contractor once, only from money PayPal says has arrived."""
    scale = _scale()
    received = sum(i["amount"] for i in store.list_invoices(goal_id) if i["status"] == "paid")
    committed = sum(p["amount"] for p in store.list_payouts(goal_id))

    for c in contractors:
        key = f"payout-{goal_id}-{c['contractor_id']}"
        if store.get_payout(key):
            continue                                            # already paid / submitted
        amount = float(c["amount_due"])
        if amount > guard.MAX_AUTO_PAYOUT:
            store.audit("payout_held", key=key, contractor=c["contractor_id"], amount=amount,
                        reason=f"Payout {amount:g} exceeds the auto-approve limit of {guard.MAX_AUTO_PAYOUT}; needs approval.")
            continue
        if amount > received - committed:
            store.audit("payout_waiting", key=key, contractor=c["contractor_id"], amount=amount,
                        reason=f"Only {received - committed:g} of cleared client money is available so far.")
            continue

        email = os.getenv("DEMO_CONTRACTOR_EMAIL") or c["email"]
        batch_id = paypal.send_payout(email, round(amount * scale, 2), currency=PAYOUT_CURRENCY,
                                      request_id=key, note=f"Payment for {c['name']}")
        store.save_payout(key, goal_id, c["contractor_id"], amount, batch_id, "submitted")
        store.audit("payout_sent", key=key, contractor=c["contractor_id"], amount=amount, batch_id=batch_id)
        committed += amount
    return store.list_payouts(goal_id)


def refresh_payouts(goal_id: str, *, paypal, store: Store) -> list:
    getter = getattr(paypal, "get_payout_status", None)     # optional until paypal_client has it
    if getter:
        for p in store.list_payouts(goal_id):
            if p["status"] in FINAL_PAYOUT_STATES:
                continue
            status = getter(p["batch_id"]).lower()
            if status != p["status"]:
                store.set_payout_status(p["key"], status)
                store.audit("payout_status", key=p["key"], batch_id=p["batch_id"], status=status)
    return store.list_payouts(goal_id)


def check_and_pay(goal_id: str, contractors: list, *, paypal, store: Store) -> dict:
    """One 'tick': refresh invoice status from PayPal, pay contractors if money arrived, refresh payouts."""
    invoices = refresh_invoices(goal_id, paypal=paypal, store=store)
    payouts = pay_contractors(goal_id, contractors, paypal=paypal, store=store)
    payouts = refresh_payouts(goal_id, paypal=paypal, store=store)
    return {"invoices": invoices, "payouts": payouts}


# ------------------------------------------------------------------ whole run

def run_goal(goal_amount: float, deadline: str, *, clients: dict, open_invoices: list, paypal,
             store: Store, today: Optional[str] = None):
    goal_id = make_goal_id(goal_amount, deadline)
    plan = make_plan(goal_amount, deadline, open_invoices, clients)
    store.audit("plan_created", goal_id=goal_id, goal=goal_amount, deadline=deadline,
                covered=plan.covered, best_case=plan.best_case, shortfall=plan.shortfall,
                offers=[i.invoice_id for i in plan.items if i.action == "early_pay_offer"])
    issue_invoices(plan, goal_id, clients, paypal=paypal, store=store, today=today)
    return goal_id, plan


# ------------------------------------------------------------------ incoming client email (Guard)

def handle_email(email: dict, clients: dict, open_invoices: list, call_llm, store: Store):
    """Extract -> Guard -> audit log. The current due date comes from OUR open invoices, never the email.
    Applying an approved change (new bank account, discount) is a human step for now; we only log it."""
    match = find_client_by_sender(email["sender"], clients)
    due = None
    if match:
        dues = sorted(i.due_date for i in open_invoices if i.client_id == match.client_id)
        due = dues[0] if dues else None
    result = process_email(email, clients, call_llm, current_due_date=due)
    store.audit("email_decision", email_id=email["id"], sender=email["sender"],
                client=result.parsed.client_id, intent=result.parsed.intent,
                decision=result.decision.decision, reasons=result.decision.reasons)
    return result