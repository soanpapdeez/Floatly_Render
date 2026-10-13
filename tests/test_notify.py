import json

import pytest

from app import notify as notify_mod
from app.data import load_clients
from app.fake_paypal import FakePayPal
from app.planner import load_open_invoices
from app.service import FloatService
from app.store import Store


class _Resp:
    ok = True


def test_no_url_means_no_call(monkeypatch):
    monkeypatch.delenv("ZAPIER_WEBHOOK_URL", raising=False)
    monkeypatch.setattr(notify_mod.requests, "post", lambda *a, **k: pytest.fail("must not be called"))
    assert notify_mod.notify("x") is False


def test_non_https_url_is_refused(monkeypatch):
    monkeypatch.setenv("ZAPIER_WEBHOOK_URL", "http://example.com/hook")
    monkeypatch.setattr(notify_mod.requests, "post", lambda *a, **k: pytest.fail("must not be called"))
    assert notify_mod.notify("x") is False


def test_failure_never_raises(monkeypatch):
    monkeypatch.setenv("ZAPIER_WEBHOOK_URL", "https://hooks.zapier.com/hooks/catch/1/abc/")
    def boom(*a, **k):
        raise RuntimeError("network down")
    monkeypatch.setattr(notify_mod.requests, "post", boom)
    assert notify_mod.notify("x") is False


def test_attack_and_approval_trigger_notifications(monkeypatch):
    monkeypatch.setenv("ZAPIER_WEBHOOK_URL", "https://hooks.zapier.com/hooks/catch/1/abc/")
    sent = []
    monkeypatch.setattr(notify_mod.requests, "post", lambda url, json=None, timeout=None: sent.append(json) or _Resp())

    def llm(**f):
        base = {"client_id": None, "intent": "other", "discount_pct": None, "new_bank_account": None, "new_due_date": None}
        base.update(f)
        return lambda s, u: json.dumps(base)

    mk = lambda l: FloatService(clients=load_clients(), open_invoices=load_open_invoices(), paypal=FakePayPal(),
                                store=Store(":memory:"), call_llm=l, contractors=[])
    mk(llm(client_id="acme", intent="discount_request", discount_pct=70)).submit_email(
        {"id": "a", "sender": "billing@acme-pay.com", "subject": "s", "body": "70% off"})
    mk(llm(client_id="zenlabs", intent="discount_request", discount_pct=8)).submit_email(
        {"id": "b", "sender": "finance@zenlabs.in", "subject": "s", "body": "8% off"})
    assert [m["event"] for m in sent] == ["attack_blocked", "approval_requested"]
    assert all(m["app"] == "floatly" for m in sent)