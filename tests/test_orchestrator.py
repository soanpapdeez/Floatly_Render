import json

import pytest

from app import guard
from app.data import load_clients
from app.fake_paypal import FakePayPal
from app.orchestrator import (check_and_pay, handle_email, load_contractors, run_goal)
from app.planner import load_open_invoices
from app.store import Store

TODAY = "2026-10-12"


@pytest.fixture
def world():
    return dict(clients=load_clients(), open_invoices=load_open_invoices(),
                paypal=FakePayPal(), store=Store(":memory:"))


def _run(w, goal=6000.0):
    return run_goal(goal, "2026-10-16", clients=w["clients"], open_invoices=w["open_invoices"],
                    paypal=w["paypal"], store=w["store"], today=TODAY)


def test_one_invoice_per_plan_item(world):
    goal_id, plan = _run(world)
    assert len(world["paypal"].invoices) == len(plan.items) == 6


def test_offer_invoice_is_discounted_and_due_by_deadline(world):
    goal_id, plan = _run(world)
    nw = world["store"].get_invoice(f"{goal_id}:OPEN-004")          # northwind: 3% offer
    assert nw["amount"] == pytest.approx(3500 * 0.97)
    assert nw["due_date"] == "2026-10-16"


def test_rerun_does_not_create_duplicate_invoices(world):
    _run(world)
    _run(world)
    assert len(world["paypal"].invoices) == 6


def test_due_date_never_in_the_past(world):
    goal_id, _ = _run(world)
    assert all(i["due_date"] >= TODAY for i in world["store"].list_invoices(goal_id))


def test_no_payout_before_money_arrives(world):
    goal_id, _ = _run(world)
    out = check_and_pay(goal_id, load_contractors(), paypal=world["paypal"], store=world["store"])
    assert out["payouts"] == []
    assert world["paypal"].payouts == {}


def test_payouts_after_paid_and_never_twice(world):
    goal_id, _ = _run(world)
    for inv in world["store"].list_invoices(goal_id):
        world["paypal"].mark_paid(inv["paypal_invoice_id"])
    for _ in range(3):                                              # re-run several times
        out = check_and_pay(goal_id, load_contractors(), paypal=world["paypal"], store=world["store"])
    assert len(out["payouts"]) == 2
    assert len(world["paypal"].payouts) == 2


def test_payout_waits_for_enough_money(world):
    goal_id, _ = _run(world)
    # only Skyline ($600) pays: not enough for Ravi ($1200)
    sky = world["store"].get_invoice(f"{goal_id}:OPEN-005")
    world["paypal"].mark_paid(sky["paypal_invoice_id"])
    out = check_and_pay(goal_id, load_contractors(), paypal=world["paypal"], store=world["store"])
    assert out["payouts"] == []


def test_payout_over_limit_is_held(world):
    goal_id, _ = _run(world)
    for inv in world["store"].list_invoices(goal_id):
        world["paypal"].mark_paid(inv["paypal_invoice_id"])
    big = [{"contractor_id": "big", "name": "Big", "email": "b@x.com", "amount_due": guard.MAX_AUTO_PAYOUT + 1}]
    out = check_and_pay(goal_id, big, paypal=world["paypal"], store=world["store"])
    assert out["payouts"] == []
    assert any(e["event"] == "payout_held" for e in world["store"].list_audit())


def _llm(**fields):
    base = {"client_id": None, "intent": "other", "discount_pct": None, "new_bank_account": None, "new_due_date": None}
    base.update(fields)
    return lambda system, user: json.dumps(base)


def test_spoofed_discount_is_blocked_and_logged(world):
    email = {"id": "x1", "sender": "billing@acme-pay.com", "subject": "URGENT", "body": "Acme: 70% off now"}
    r = handle_email(email, world["clients"], world["open_invoices"],
                     _llm(client_id="acme", intent="discount_request", discount_pct=70), world["store"])
    assert r.decision.decision == "block"
    assert any(e["event"] == "email_decision" and e["details"]["decision"] == "block"
               for e in world["store"].list_audit())


def test_email_cannot_mark_invoice_paid(world):
    goal_id, _ = _run(world)
    email = {"id": "x2", "sender": "billing@acme.com", "subject": "Paid", "body": "Acme: we paid, please confirm"}
    handle_email(email, world["clients"], world["open_invoices"],
                 _llm(client_id="acme", intent="payment_confirmation"), world["store"])
    assert all(i["status"] != "paid" for i in world["store"].list_invoices(goal_id))