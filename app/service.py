"""
FloatService: the ONE object the UI talks to. Every method returns plain dicts/lists (JSON-ready).

    svc = build_service(fake=True)            # offline: fake PayPal, in-memory DB, no keys
    svc = build_service()                     # real: sandbox PayPal + float.db (needs .env)

    svc.preview("I need $6,000 by Friday")    -> parsed goal + plan + AI summary (nothing is sent yet)
    svc.launch(6000, "2026-10-16")            -> issues the PayPal invoices, returns the state
    svc.state(goal_id)                        -> invoices, payouts, totals
    svc.tick(goal_id)                         -> poll PayPal, pay contractors from cleared money, return the state
    svc.submit_email(email)                   -> extract -> Guard -> log; creates an approval if a human must decide
    svc.approvals("pending")                  -> things waiting for the owner
    svc.decide(approval_id, True/False)       -> owner's one-tap approve / reject
    svc.audit(100)                            -> audit log
    svc.simulate_payment(invoice_key)         -> FAKE mode only: pretend a client paid
"""
from dataclasses import asdict
from datetime import date
from typing import Optional

from .orchestrator import check_and_pay, handle_email, load_contractors, make_goal_id, run_goal
from .goal_parser import parse_goal
from .planner import make_plan
from .summarizer import summarize_plan


class FloatService:
    def __init__(self, *, clients, open_invoices, paypal, store, call_llm=None, contractors=None):
        self.clients, self.open_invoices = clients, open_invoices
        self.paypal, self.store, self.call_llm = paypal, store, call_llm
        self.contractors = contractors if contractors is not None else []

    # ---- goal -> plan
    def preview(self, text: str, today: Optional[date] = None) -> dict:
        res = parse_goal(text, self.call_llm, today=today)
        if not res.ok:
            self.store.audit("goal_rejected", reason=res.error, text=text)
            return {"ok": False, "error": res.error}
        g = res.goal
        plan = make_plan(g.amount, g.deadline, self.open_invoices, self.clients)
        summary = summarize_plan(plan, self.clients, self.call_llm)
        self.store.audit("goal_previewed", goal=g.amount, deadline=g.deadline, source=g.source, summary_source=summary["source"])
        return {"ok": True, "goal": asdict(g), "goal_id": make_goal_id(g.amount, g.deadline),
                "plan": plan.to_dict(), "summary": summary}

    def launch(self, goal_amount: float, deadline: str, today: Optional[str] = None) -> dict:
        goal_id, plan = run_goal(goal_amount, deadline, clients=self.clients, open_invoices=self.open_invoices,
                                 paypal=self.paypal, store=self.store, today=today)
        return {**self.state(goal_id), "plan": plan.to_dict()}

    # ---- progress
    def state(self, goal_id: str) -> dict:
        invoices, payouts = self.store.list_invoices(goal_id), self.store.list_payouts(goal_id)
        return {"goal_id": goal_id, "invoices": invoices, "payouts": payouts,
                "totals": {"invoiced": round(sum(i["amount"] for i in invoices), 2),
                           "received": round(sum(i["amount"] for i in invoices if i["status"] == "paid"), 2),
                           "paid_out": round(sum(p["amount"] for p in payouts), 2)}}

    def tick(self, goal_id: str) -> dict:
        check_and_pay(goal_id, self.contractors, paypal=self.paypal, store=self.store)
        return self.state(goal_id)

    def simulate_payment(self, invoice_key: str) -> dict:
        if not hasattr(self.paypal, "mark_paid"):
            raise RuntimeError("simulate_payment only works with the fake PayPal. In the sandbox, pay from the personal account.")
        inv = self.store.get_invoice(invoice_key)
        if not inv:
            raise KeyError(invoice_key)
        self.paypal.mark_paid(inv["paypal_invoice_id"])
        self.store.audit("payment_simulated", key=invoice_key)
        return self.state(inv["goal_id"])

    # ---- client emails + approvals
    def submit_email(self, email: dict) -> dict:
        if self.call_llm is None:
            raise RuntimeError("An LLM is required to read emails.")
        r = handle_email(email, self.clients, self.open_invoices, self.call_llm, self.store)
        approval_id = None
        if r.decision.decision == "needs_approval":
            approval_id = self.store.add_approval(
                email["id"], r.parsed.client_id, r.parsed.intent,
                {"discount_pct": r.parsed.discount_pct, "new_bank_account": r.parsed.new_bank_account,
                 "new_due_date": r.parsed.new_due_date, "sender": email["sender"]},
                r.decision.reasons)
            self.store.audit("approval_requested", approval_id=approval_id, email_id=email["id"], reasons=r.decision.reasons)
        return {"decision": r.decision.decision, "reasons": r.decision.reasons, "parsed": asdict(r.parsed),
                "approval_id": approval_id}

    def approvals(self, status: Optional[str] = "pending") -> list:
        return self.store.list_approvals(status)

    def decide(self, approval_id: int, approve: bool, note: str = "") -> dict:
        """Owner's decision. NOTE: this records the decision and logs it. It does not yet change any invoice
        or account; applying an approved change is a manual follow-up. 'block' decisions never reach here."""
        a = self.store.decide_approval(approval_id, "approved" if approve else "rejected", note)
        self.store.audit("approval_decided", approval_id=approval_id, status=a["status"], intent=a["intent"],
                         client=a["client_id"], note=note)
        return a

    def audit(self, limit: int = 100) -> list:
        return self.store.list_audit(limit)


def build_service(*, fake: bool = False, db_path: Optional[str] = None, call_llm=None) -> FloatService:
    from .data import load_clients
    from .llm import get_llm
    from .planner import load_open_invoices
    from .store import Store
    if fake:
        from .fake_paypal import FakePayPal
        paypal, db_path = FakePayPal(), db_path or ":memory:"      # fake state dies with the process, so the DB must too
    else:
        from . import paypal_client as paypal
        db_path = db_path or "float.db"
    return FloatService(clients=load_clients(), open_invoices=load_open_invoices(), paypal=paypal,
                        store=Store(db_path), call_llm=call_llm or get_llm(), contractors=load_contractors())