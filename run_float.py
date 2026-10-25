"""
Float command line.
  python run_float.py plan [goal] [deadline]        show the plan (no keys needed)
  python run_float.py ask "I need $6,000 in 4 days" read a goal in plain English, show plan + summary
  python run_float.py simulate                      full offline dry run with a FAKE PayPal (no keys needed)
  python run_float.py issue [goal] [deadline]       create + send REAL sandbox PayPal invoices
  python run_float.py check [goal] [deadline]       poll PayPal; pay contractors from money that has arrived
                                                    (with no arguments: the most recent goal)
  python run_float.py email <email_id>              run one sample inbox email through extract -> Guard
  python run_float.py audit                         print the audit log

Default goal: $6,000 in 4 days. The seed invoices are shifted so they always look current.
"""
import sys
from datetime import date, timedelta

from app.data import load_clients, load_inbox
from app.orchestrator import (check_and_pay, handle_email, load_contractors, make_goal_id, run_goal)
from app.planner import format_plan, load_open_invoices, make_plan
from app.store import Store


def _invoices():
    return load_open_invoices(today=date.today())


def _args():
    goal = float(sys.argv[2]) if len(sys.argv) > 2 else 6000.0
    deadline = sys.argv[3] if len(sys.argv) > 3 else (date.today() + timedelta(days=4)).isoformat()
    return goal, deadline


def _print_audit(store, limit=200):
    for e in store.list_audit(limit):
        d = e["details"]
        why = d.get("reason") or d.get("reasons") or d.get("effect") or ""
        print(f"#{e['id']:<3} {e['event']:<18} {d.get('key') or d.get('email_id') or d.get('goal_id') or ''}  {why}")


def cmd_plan():
    goal, deadline = _args()
    print(format_plan(make_plan(goal, deadline, _invoices(), load_clients())))


def cmd_ask():
    from app.goal_parser import parse_goal
    from app.llm import get_llm
    from app.summarizer import summarize_plan
    llm, clients = get_llm(), load_clients()
    res = parse_goal(" ".join(sys.argv[2:]), llm)
    if not res.ok:
        print("Could not read the goal:", res.error)
        return
    g = res.goal
    print(f"Goal: ${g.amount:,.2f} by {g.deadline_label}   (read by: {g.source})\n")
    plan = make_plan(g.amount, g.deadline, _invoices(), clients)
    print(format_plan(plan))
    s = summarize_plan(plan, clients, llm)
    print(f"\nSummary ({s['source']}): {s['text']}")


def cmd_simulate():
    """Whole story offline, through the same FloatService the UI uses. Fake PayPal, in-memory DB, no keys."""
    from app.fake_paypal import FakePayPal
    from app.llm import mock_llm
    from app.service import FloatService
    inbox = {e["id"]: e for e in load_inbox()}
    svc = FloatService(clients=load_clients(), open_invoices=_invoices(), paypal=FakePayPal(),
                       store=Store(":memory:"), call_llm=mock_llm, contractors=load_contractors())

    print("=== ACT 1: goal -> plan ===")
    p = svc.preview("I need $6,000 in 4 days")
    print(f"Goal ${p['goal']['amount']:,.2f} by {p['goal']['deadline_label']}")
    print(p["summary"]["text"])
    st = svc.launch(p["goal"]["amount"], p["goal"]["deadline"])
    goal_id = st["goal_id"]
    print(f"\nInvoices sent via (fake) PayPal: {len(st['invoices'])}, invoiced ${st['totals']['invoiced']:,.2f}")

    print("\n=== before any client pays: contractors must NOT be paid ===")
    print("payouts:", len(svc.tick(goal_id)["payouts"]))

    print("\n=== ACT 2: client emails ===")
    for eid in ("m04", "m06", "m20", "m03"):
        out = svc.submit_email(inbox[eid])
        print(f"{eid}: {out['decision'].upper()} - {'; '.join(out['reasons'])}")

    print("\n=== owner approves ZenLabs' 8% request (the only one that needs a human) ===")
    for a in svc.approvals("pending"):
        res = svc.decide(a["id"], True, note="long-time client")
        print(f"approval #{a['id']} ({a['intent']}, {a['client_id']}): {res['effect']}")

    print("\n=== clients pay (simulated), contractors get paid ===")
    for inv in svc.store.list_invoices(goal_id):
        if inv["status"] == "unpaid":
            svc.simulate_payment(inv["key"])
    st = svc.tick(goal_id)
    print("payouts:", [(p_["contractor_id"], p_["amount"], p_["status"]) for p_ in st["payouts"]])

    print("\n=== re-run: nobody may be paid twice ===")
    st = svc.tick(goal_id)
    print("payouts:", len(st["payouts"]), "| fake PayPal saw", len(svc.paypal.payouts), "payout request(s)")
    print(f"totals: invoiced ${st['totals']['invoiced']:,.2f}, received ${st['totals']['received']:,.2f}, "
          f"paid out ${st['totals']['paid_out']:,.2f}")

    print("\n=== audit log ===")
    _print_audit(svc.store)


def cmd_issue():
    import app.paypal_client as paypal
    goal, deadline = _args()
    store = Store()
    goal_id, plan = run_goal(goal, deadline, clients=load_clients(), open_invoices=_invoices(),
                             paypal=paypal, store=store)
    print(format_plan(plan))
    print(f"\nIssued/kept {len(store.list_invoices(goal_id))} invoice(s) for {goal_id}")


def cmd_check():
    import app.paypal_client as paypal
    store = Store()
    if len(sys.argv) > 2:
        goal_id = make_goal_id(*_args())
    else:
        ids = store.goal_ids()
        if not ids:
            print("No goals yet. Run: python run_float.py issue")
            return
        goal_id = ids[-1]
    print(f"Goal: {goal_id}")
    out = check_and_pay(goal_id, load_contractors(), paypal=paypal, store=store)
    for i in out["invoices"]:
        print(f"invoice {i['key']:<28} {i['paypal_invoice_id']}  ${i['amount']:,.2f}  {i['status']}")
    for p in out["payouts"]:
        print(f"payout  {p['contractor_id']:<14} ${p['amount']:,.2f}  {p['status']}  {p['batch_id']}")


def cmd_email():
    from app.llm import get_llm
    inbox = {e["id"]: e for e in load_inbox()}
    r = handle_email(inbox[sys.argv[2]], load_clients(), _invoices(), get_llm(), Store())
    print(r.parsed)
    print(r.decision.decision.upper(), "-", "; ".join(r.decision.reasons))


COMMANDS = {"ask": cmd_ask, "plan": cmd_plan, "simulate": cmd_simulate, "issue": cmd_issue, "check": cmd_check,
            "email": cmd_email, "audit": lambda: _print_audit(Store())}

if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "plan"
    if cmd not in COMMANDS:
        sys.exit(__doc__)
    COMMANDS[cmd]()