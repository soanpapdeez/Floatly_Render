"""
Float command line.
  python run_float.py plan [goal] [deadline]        show the plan (no keys needed)
  python run_float.py simulate                      full offline dry run with a FAKE PayPal (no keys needed)
  python run_float.py issue [goal] [deadline]       create + send REAL sandbox PayPal invoices
  python run_float.py check [goal] [deadline]       poll PayPal; pay contractors from money that has arrived
  python run_float.py email <email_id>              run one sample inbox email through extract -> Guard
  python run_float.py audit                         print the audit log
"""
import sys

from app.data import load_clients, load_inbox
from app.orchestrator import (check_and_pay, handle_email, load_contractors, make_goal_id, run_goal)
from app.planner import format_plan, load_open_invoices, make_plan
from app.store import Store


def _args(default_goal=6000.0, default_deadline="2026-10-16"):
    goal = float(sys.argv[2]) if len(sys.argv) > 2 else default_goal
    deadline = sys.argv[3] if len(sys.argv) > 3 else default_deadline
    return goal, deadline


def _print_audit(store, limit=200):
    for e in store.list_audit(limit):
        d = e["details"]
        why = d.get("reason") or d.get("reasons") or ""
        print(f"#{e['id']:<3} {e['event']:<15} {d.get('key') or d.get('email_id') or d.get('goal_id') or ''}  {why}")


def cmd_plan():
    goal, deadline = _args()
    print(format_plan(make_plan(goal, deadline, load_open_invoices(), load_clients())))


def cmd_simulate():
    from app.fake_paypal import FakePayPal
    from app.llm import mock_llm
    clients, open_invoices, inbox = load_clients(), load_open_invoices(), {e["id"]: e for e in load_inbox()}
    paypal, store = FakePayPal(), Store(":memory:")
    goal, deadline = 6000.0, "2026-10-16"

    print("=== ACT 1: the plan ===")
    goal_id, plan = run_goal(goal, deadline, clients=clients, open_invoices=open_invoices,
                             paypal=paypal, store=store, today="2026-10-12")
    print(format_plan(plan))
    print(f"\nInvoices sent via (fake) PayPal: {len(store.list_invoices(goal_id))}")

    print("\n=== before any client pays: contractors must NOT be paid ===")
    out = check_and_pay(goal_id, load_contractors(), paypal=paypal, store=store)
    print("payouts:", len(out["payouts"]))

    print("\n=== clients pay (simulated) ===")
    for inv in store.list_invoices(goal_id):
        paypal.mark_paid(inv["paypal_invoice_id"])
    out = check_and_pay(goal_id, load_contractors(), paypal=paypal, store=store)
    print("payouts:", [(p["contractor_id"], p["amount"], p["status"]) for p in out["payouts"]])

    print("\n=== re-run: nobody may be paid twice ===")
    out = check_and_pay(goal_id, load_contractors(), paypal=paypal, store=store)
    print("payouts:", len(out["payouts"]), "| fake PayPal saw", len(paypal.payouts), "payout request(s)")

    print("\n=== ACT 2: attack emails ===")
    for eid in ("m04", "m06", "m20"):
        if eid in inbox:
            r = handle_email(inbox[eid], clients, open_invoices, mock_llm, store)
            print(f"{eid}: {r.decision.decision.upper()} - {'; '.join(r.decision.reasons)}")

    print("\n=== audit log ===")
    _print_audit(store)


def cmd_issue():
    import app.paypal_client as paypal
    goal, deadline = _args()
    store = Store()
    goal_id, plan = run_goal(goal, deadline, clients=load_clients(), open_invoices=load_open_invoices(),
                             paypal=paypal, store=store)
    print(format_plan(plan))
    print(f"\nIssued/kept {len(store.list_invoices(goal_id))} invoice(s) for {goal_id}")


def cmd_check():
    import app.paypal_client as paypal
    store, goal_id = Store(), make_goal_id(*_args())
    out = check_and_pay(goal_id, load_contractors(), paypal=paypal, store=store)
    for i in out["invoices"]:
        print(f"invoice {i['key']:<28} {i['paypal_invoice_id']}  ${i['amount']:,.2f}  {i['status']}")
    for p in out["payouts"]:
        print(f"payout  {p['contractor_id']:<14} ${p['amount']:,.2f}  {p['status']}  {p['batch_id']}")


def cmd_email():
    from app.llm import get_llm
    inbox = {e["id"]: e for e in load_inbox()}
    r = handle_email(inbox[sys.argv[2]], load_clients(), load_open_invoices(), get_llm(), Store())
    print(r.parsed)
    print(r.decision.decision.upper(), "-", "; ".join(r.decision.reasons))


COMMANDS = {"plan": cmd_plan, "simulate": cmd_simulate, "issue": cmd_issue, "check": cmd_check,
            "email": cmd_email, "audit": lambda: _print_audit(Store())}

if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "plan"
    if cmd not in COMMANDS:
        sys.exit(__doc__)
    COMMANDS[cmd]()