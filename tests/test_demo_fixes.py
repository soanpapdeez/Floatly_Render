"""Acceptance tests for the pre-freeze fixes. Offline: fake PayPal, mock LLM, in-memory DB."""
from datetime import date, timedelta

import pytest

from app.data import load_clients, load_inbox
from app.effects import describe_effect
from app.fake_paypal import FakePayPal
from app.llm import mock_llm
from app.orchestrator import load_contractors
from app.planner import format_plan, load_open_invoices, make_plan
from app.service import FloatService
from app.store import Store

DECIDE_TODO = pytest.mark.xfail(reason="FloatService.decide() not wired to describe_effect yet", strict=True)


def _svc():
    return FloatService(clients=load_clients(), open_invoices=load_open_invoices(today=date.today()),
                        paypal=FakePayPal(), store=Store(":memory:"), call_llm=mock_llm,
                        contractors=load_contractors())


def _launched():
    svc = _svc()
    p = svc.preview("I need $6,000 in 4 days")
    st = svc.launch(p["goal"]["amount"], p["goal"]["deadline"])
    return svc, st["goal_id"]


def _audit(svc, event):
    return [e for e in svc.store.list_audit(1000) if e["event"] == event]


# 1 + 5: seed data shows a gap and an offer; brackets balanced
def test_seed_shows_gap_and_offer():
    deadline = (date.today() + timedelta(days=4)).isoformat()
    text = format_plan(make_plan(6000.0, deadline, load_open_invoices(today=date.today()), load_clients()))
    assert "[OFFER" in text
    assert text.count("(") == text.count(")")


# 2: payout_waiting is logged once per state, not every tick
def test_payout_waiting_logged_only_on_change():
    svc, gid = _launched()
    for _ in range(3):
        svc.tick(gid)
    keys = [e["details"].get("key") for e in _audit(svc, "payout_waiting")]
    assert keys, "expected payout_waiting entries before any client pays"
    assert len(keys) == len(set(keys)), f"payout_waiting repeated: {keys}"


# 5: waiting text shows a dollar amount
def test_payout_waiting_text_shows_dollars():
    svc, gid = _launched()
    svc.tick(gid)
    for e in _audit(svc, "payout_waiting"):
        assert "$" in str(e["details"].get("reason", "")), e


# 3: decide() returns a plain-language effect
def _decide_m03(approve):
    svc, _ = _launched()
    inbox = {e["id"]: e for e in load_inbox()}
    svc.submit_email(inbox["m03"])
    [a] = svc.approvals("pending")
    return svc, svc.decide(a["id"], approve)


@DECIDE_TODO
def test_approve_discount_effect_is_text():
    svc, res = _decide_m03(True)
    assert isinstance(res["effect"], str)
    assert "$1,840.00" in res["effect"]
    assert _audit(svc, "approval_decided")[-1]["details"].get("effect") == res["effect"]


@DECIDE_TODO
def test_reject_effect_says_no_change():
    _, res = _decide_m03(False)
    assert isinstance(res["effect"], str) and "no change" in res["effect"].lower()


def test_effect_never_shows_full_bank_account():
    s = describe_effect("bank_change", True, {"applied": True, "account": "DE89370400440532013000"})
    assert "3000" in s and "DE89370400440532013000" not in s


# 4: a PayPal hiccup during polling is logged, not raised
def test_paypal_error_does_not_crash_tick(monkeypatch):
    svc, gid = _launched()

    def boom(*a, **k):
        raise ConnectionError("simulated PayPal outage")

    monkeypatch.setattr(svc.paypal, "get_invoice_status", boom)
    st = svc.tick(gid)  # must not raise
    assert "payouts" in st
    assert _audit(svc, "paypal_error")