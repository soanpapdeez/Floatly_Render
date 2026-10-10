from app.guard import evaluate
from app.models import Client, ParsedRequest, ALLOW, NEEDS_APPROVAL, BLOCK

ACME = Client("acme", "Acme", ["billing@acme.com"], ["ACC-ACME-001"])


def test_attack_spoofed_sender_70pct_blocked():
    d = evaluate(ParsedRequest("acme", "discount_request", 70), ACME, "billing@acme-pay.com")
    assert d.decision == BLOCK and len(d.reasons) == 2


def test_small_discount_allowed():
    assert evaluate(ParsedRequest("acme", "discount_request", 3), ACME, "billing@acme.com").decision == ALLOW


def test_boundaries():
    mk = lambda p: evaluate(ParsedRequest("acme", "discount_request", p), ACME, "billing@acme.com").decision
    assert mk(5) == ALLOW and mk(5.1) == NEEDS_APPROVAL and mk(10) == NEEDS_APPROVAL and mk(10.1) == BLOCK


def test_unclear_discount_needs_approval():
    assert evaluate(ParsedRequest("acme", "discount_request", None), ACME, "billing@acme.com").decision == NEEDS_APPROVAL


def test_new_bank_account_needs_approval_known_allowed():
    s = "billing@acme.com"
    assert evaluate(ParsedRequest("acme", "bank_change", new_bank_account="NEW-1"), ACME, s).decision == NEEDS_APPROVAL
    assert evaluate(ParsedRequest("acme", "bank_change", new_bank_account="ACC-ACME-001"), ACME, s).decision == ALLOW
    assert evaluate(ParsedRequest("acme", "bank_change", new_bank_account=None), ACME, s).decision == NEEDS_APPROVAL


def test_fails_closed():
    assert evaluate(ParsedRequest(None, "other"), None, "x@y.com").decision == BLOCK
    assert evaluate(ParsedRequest("acme", "other"), ACME, "billing@acme.com").decision == NEEDS_APPROVAL
    assert evaluate(ParsedRequest("acme", "made_up_intent"), ACME, "billing@acme.com").decision == NEEDS_APPROVAL


def test_sender_case_insensitive():
    assert evaluate(ParsedRequest("acme", "payment_confirmation"), ACME, "Billing@ACME.com").decision == ALLOW


def test_large_payout_needs_approval():
    d = evaluate(ParsedRequest("acme", "payment_confirmation"), ACME, "billing@acme.com", payout_amount=5000)
    assert d.decision == NEEDS_APPROVAL
