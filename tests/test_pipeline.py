import pytest
from app.data import load_clients, load_inbox
from app.llm import mock_llm
from app.pipeline import process_email

CLIENTS = load_clients()


@pytest.mark.parametrize("email", load_inbox(), ids=lambda e: e["id"])
def test_inbox_message(email):
    res = process_email(email, CLIENTS, mock_llm)
    exp = email["expected"]
    assert res.parsed.client_id == exp["client_id"]
    assert res.parsed.intent == exp["intent"]
    assert res.decision.decision == exp["decision"], res.decision.reasons


def test_broken_llm_never_auto_allows():
    broken = lambda s, u: "garbage"
    for email in load_inbox():
        assert process_email(email, CLIENTS, broken).decision.decision != "allow"
