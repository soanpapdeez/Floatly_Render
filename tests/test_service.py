import json
from datetime import date

import pytest

from app.data import load_clients
from app.fake_paypal import FakePayPal
from app.orchestrator import load_contractors
from app.planner import load_open_invoices
from app.service import FloatService
from app.store import Store

SUN = date(2026, 10, 11)


def _llm(**fields):
    base = {"client_id": None, "intent": "other", "discount_pct": None, "new_bank_account": None, "new_due_date": None}
    base.update(fields)
    return lambda s, u: json.dumps(base)


@pytest.fixture
def svc():
    return FloatService(clients=load_clients(), open_invoices=load_open_invoices(), paypal=FakePayPal(),
                        store=Store(":memory:"), call_llm=None, contractors=load_contractors())


def test_preview_then_launch_then_payouts(svc):
    p = svc.preview("I need $6,000 by Friday", today=SUN)
    assert p["ok"] and p["goal"]["deadline"] == "2026-10-16" and p["plan"]["covered"]
    assert p["summary"]["source"] == "template"
    assert svc.store.goal_ids() == []                                 # preview sent nothing

    st = svc.launch(p["goal"]["amount"], p["goal"]["deadline"], today="2026-10-12")
    assert len(st["invoices"]) == 6 and st["totals"]["received"] == 0
    assert svc.tick(st["goal_id"])["payouts"] == []                   # nobody paid yet -> no payouts

    for inv in st["invoices"]:
        svc.simulate_payment(inv["key"])
    st = svc.tick(st["goal_id"])
    assert len(st["payouts"]) == 2 and st["totals"]["paid_out"] == 3000
    assert len(svc.tick(st["goal_id"])["payouts"]) == 2               # still 2 after another tick


def test_preview_bad_goal(svc):
    r = svc.preview("hello", today=SUN)
    assert not r["ok"] and r["error"]


def test_needs_approval_creates_pending_item_and_owner_can_decide():
    s = FloatService(clients=load_clients(), open_invoices=load_open_invoices(), paypal=FakePayPal(),
                     store=Store(":memory:"), call_llm=_llm(client_id="zenlabs", intent="discount_request", discount_pct=8),
                     contractors=[])
    out = s.submit_email({"id": "e1", "sender": "finance@zenlabs.in", "subject": "Budget", "body": "8% off please"})
    assert out["decision"] == "needs_approval" and out["approval_id"]
    pending = s.approvals("pending")
    assert len(pending) == 1 and pending[0]["payload"]["discount_pct"] == 8
    done = s.decide(out["approval_id"], True, note="ok, long-time client")
    assert done["status"] == "approved" and s.approvals("pending") == []
    with pytest.raises(ValueError):
        s.decide(out["approval_id"], False)                            # cannot decide twice


def test_block_never_creates_an_approval():
    s = FloatService(clients=load_clients(), open_invoices=load_open_invoices(), paypal=FakePayPal(),
                     store=Store(":memory:"), call_llm=_llm(client_id="acme", intent="discount_request", discount_pct=70),
                     contractors=[])
    out = s.submit_email({"id": "e2", "sender": "billing@acme-pay.com", "subject": "URGENT", "body": "70% off"})
    assert out["decision"] == "block" and out["approval_id"] is None and s.approvals(None) == []


def test_simulate_payment_refused_on_real_paypal(svc):
    class Real:       # no mark_paid, like the real module
        pass
    svc.paypal = Real()
    with pytest.raises(RuntimeError):
        svc.simulate_payment("anything")


def test_state_is_json_serialisable(svc):
    p = svc.preview("I need $6,000 by Friday", today=SUN)
    st = svc.launch(p["goal"]["amount"], p["goal"]["deadline"], today="2026-10-12")
    json.dumps(st), json.dumps(p), json.dumps(svc.audit())


def test_build_service_reads_float_fake_from_env(monkeypatch):
    from app.service import build_service
    monkeypatch.setenv("FLOAT_FAKE", "1")
    monkeypatch.setenv("LLM_PROVIDER", "mock")
    svc = build_service()
    assert isinstance(svc.paypal, FakePayPal)
    assert svc.preview("I need $6,000 by 2026-12-31", today=date(2026, 12, 1))["ok"]