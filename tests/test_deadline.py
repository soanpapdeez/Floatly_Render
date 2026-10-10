from app import guard
from app.models import Client, ParsedRequest, ALLOW, NEEDS_APPROVAL

CLIENT = Client(client_id="skyline", name="Skyline",
                known_emails=["pay@skyline.co"], known_accounts=["ACC-SKY-001"])


def _req(due):
    return ParsedRequest("skyline", "deadline_extension", new_due_date=due)


def test_short_extension_allowed():
    d = guard.evaluate(_req("2026-12-05"), CLIENT, "pay@skyline.co", current_due_date="2026-11-15")
    assert d.decision == ALLOW


def test_long_extension_needs_approval():
    d = guard.evaluate(_req("2027-06-30"), CLIENT, "pay@skyline.co", current_due_date="2026-11-15")
    assert d.decision == NEEDS_APPROVAL


def test_missing_current_due_date_fails_closed():
    d = guard.evaluate(_req("2026-11-30"), CLIENT, "pay@skyline.co")
    assert d.decision == NEEDS_APPROVAL


def test_bad_date_fails_closed():
    d = guard.evaluate(_req("2026-13-45"), CLIENT, "pay@skyline.co", current_due_date="2026-11-15")
    assert d.decision == NEEDS_APPROVAL


def test_discount_hidden_in_other_intent_is_still_checked():
    req = ParsedRequest("skyline", "bank_change", discount_pct=30, new_bank_account="ACC-SKY-001")
    d = guard.evaluate(req, CLIENT, "pay@skyline.co")
    assert d.decision == "block"