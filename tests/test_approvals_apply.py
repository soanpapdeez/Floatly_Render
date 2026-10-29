import json
from datetime import date

import pytest

from app.data import load_clients
from app.fake_paypal import FakePayPal
from app.orchestrator import load_contractors
from app.planner import load_open_invoices
from app.service import FloatService
from app.store import Store


def _llm(**fields):
    base = {"client_id": None, "intent": "other", "discount_pct": None, "new_bank_account": None, "new_due_date": None}
    base.update(fields)
    return lambda s, u: json.dumps(base)


def _svc(llm, paypal=None, store=None, contractors=None):
    return FloatService(clients=load_clients(), open_invoices=load_open_invoices(), paypal=paypal or FakePayPal(),
                        store=store or Store(":memory:"), call_llm=llm,
                        contractors=load_contractors() if contractors is None else contractors)


def _launched(svc):
    return svc.launch(6000, "2026-10-16", today="2026-10-12")


def test_approved_discount_cancels_old_invoice_and_sends_new_one():
    svc = _svc(_llm(client_id="zenlabs", intent="discount_request", discount_pct=8))
    st = _launched(svc)
    old = svc.store.get_invoice(f"{st['goal_id']}:OPEN-003")                  # ZenLabs $2000
    out = svc.submit_email({"id": "e1", "sender": "finance@zenlabs.in", "subject": "s", "body": "8% off"})
    res = svc.decide(out["approval_id"], True)
    assert res["effect_details"]["applied"] and res["effect_details"]["new_amount"] == pytest.approx(1840.0)
    assert svc.store.get_invoice(old["key"])["status"] == "cancelled"
    assert svc.paypal.invoices[old["paypal_invoice_id"]]["status"] == "cancelled"
    new = svc.store.get_invoice(res["effect_details"]["new_key"])
    assert new["amount"] == pytest.approx(1840.0) and new["status"] == "unpaid"
    # totals ignore the cancelled invoice
    assert svc.state(st["goal_id"])["totals"]["invoiced"] == pytest.approx(st["totals"]["invoiced"] - 2000 + 1840)


def test_rerun_launch_does_not_resurrect_cancelled_invoice():
    svc = _svc(_llm(client_id="zenlabs", intent="discount_request", discount_pct=8))
    st = _launched(svc)
    out = svc.submit_email({"id": "e1", "sender": "finance@zenlabs.in", "subject": "s", "body": "8% off"})
    svc.decide(out["approval_id"], True)
    n = len(svc.paypal.invoices)
    _launched(svc)
    assert len(svc.paypal.invoices) == n


def test_discounted_invoice_still_pays_contractors_correctly():
    svc = _svc(_llm(client_id="zenlabs", intent="discount_request", discount_pct=8))
    st = _launched(svc)
    out = svc.submit_email({"id": "e1", "sender": "finance@zenlabs.in", "subject": "s", "body": "8% off"})
    svc.decide(out["approval_id"], True)
    for inv in svc.store.list_invoices(st["goal_id"]):
        if inv["status"] == "unpaid":
            svc.simulate_payment(inv["key"])
    st = svc.tick(st["goal_id"])
    assert st["totals"]["received"] == pytest.approx(st["totals"]["invoiced"])
    assert len(st["payouts"]) == 2


def test_rejected_discount_changes_nothing():
    svc = _svc(_llm(client_id="zenlabs", intent="discount_request", discount_pct=8))
    st = _launched(svc)
    n = len(svc.paypal.invoices)
    out = svc.submit_email({"id": "e1", "sender": "finance@zenlabs.in", "subject": "s", "body": "8% off"})
    res = svc.decide(out["approval_id"], False)
    assert res["effect_details"]["applied"] is False and len(svc.paypal.invoices) == n


def test_no_cancel_support_means_nothing_changes():
    class NoCancel:                                   # looks like paypal_client before cancel_invoice exists
        def __init__(self):
            self._p = FakePayPal()

        def __getattr__(self, name):
            if name == "cancel_invoice":
                raise AttributeError(name)
            return getattr(self._p, name)

    svc = _svc(_llm(client_id="zenlabs", intent="discount_request", discount_pct=8), paypal=NoCancel())
    st = _launched(svc)
    out = svc.submit_email({"id": "e1", "sender": "finance@zenlabs.in", "subject": "s", "body": "8% off"})
    res = svc.decide(out["approval_id"], True)
    assert res["effect_details"]["applied"] is False
    assert all(i["status"] == "unpaid" for i in svc.store.list_invoices(st["goal_id"]))


def test_paypal_failure_is_reported_not_raised():
    class Flaky(FakePayPal):
        def create_and_send_invoice(self, *a, **k):
            if getattr(self, "armed", False):
                raise RuntimeError("PayPal 500")
            return super().create_and_send_invoice(*a, **k)
    pp = Flaky()
    svc = _svc(_llm(client_id="zenlabs", intent="discount_request", discount_pct=8), paypal=pp)
    _launched(svc)
    pp.armed = True
    out = svc.submit_email({"id": "e1", "sender": "finance@zenlabs.in", "subject": "s", "body": "8% off"})
    res = svc.decide(out["approval_id"], True)
    assert res["effect_details"]["applied"] is False and "failed" in res["effect_details"]["note"].lower()
    assert any(e["event"] == "discount_apply_failed" for e in svc.audit())


def test_approved_bank_change_is_trusted_afterwards_even_after_restart():
    store = Store(":memory:")
    svc = _svc(_llm(client_id="northwind", intent="bank_change", new_bank_account="ACC-NORTH-902"), store=store)
    email = {"id": "e2", "sender": "ap@northwind.com", "subject": "s", "body": "new account"}
    first = svc.submit_email(email)
    assert first["decision"] == "needs_approval"
    res = svc.decide(first["approval_id"], True)
    assert res["effect_details"]["applied"]
    assert svc.submit_email({**email, "id": "e3"})["decision"] == "allow"          # same account is now known

    svc2 = _svc(_llm(client_id="northwind", intent="bank_change", new_bank_account="ACC-NORTH-902"), store=store)
    assert svc2.submit_email({**email, "id": "e4"})["decision"] == "allow"         # remembered across restart


def test_approved_bank_change_does_not_trust_other_accounts_or_clients():
    svc = _svc(_llm(client_id="northwind", intent="bank_change", new_bank_account="ACC-NORTH-902"))
    out = svc.submit_email({"id": "e2", "sender": "ap@northwind.com", "subject": "s", "body": "x"})
    svc.decide(out["approval_id"], True)
    svc.call_llm = _llm(client_id="northwind", intent="bank_change", new_bank_account="ACC-OTHER-1")
    assert svc.submit_email({"id": "e5", "sender": "ap@northwind.com", "subject": "s", "body": "x"})["decision"] == "needs_approval"
    svc.call_llm = _llm(client_id="acme", intent="bank_change", new_bank_account="ACC-NORTH-902")
    assert svc.submit_email({"id": "e6", "sender": "billing@acme.com", "subject": "s", "body": "x"})["decision"] == "needs_approval"


def test_deadline_extension_approval_is_recorded_only():
    svc = _svc(_llm(client_id="skyline", intent="deadline_extension", new_due_date="2027-01-31"))
    out = svc.submit_email({"id": "e7", "sender": "pay@skyline.co", "subject": "s", "body": "x"})
    assert out["decision"] == "needs_approval"
    assert svc.decide(out["approval_id"], True)["effect_details"]["applied"] is False
