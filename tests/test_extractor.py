from app.extractor import extract

CLIENTS = ["acme", "brightco"]


def fake(payload):
    return lambda s, u: payload


def test_valid_json_parsed():
    r = extract("x", CLIENTS, fake('{"client_id":"acme","intent":"discount_request","discount_pct":70,"new_bank_account":null,"new_due_date":null}'))
    assert r.client_id == "acme" and r.intent == "discount_request" and r.discount_pct == 70.0


def test_markdown_fenced_and_prose_tolerated():
    r = extract("x", CLIENTS, fake('Sure!\n```json\n{"client_id":null,"intent":"other","discount_pct":null,"new_bank_account":null,"new_due_date":null}\n```'))
    assert r.intent == "other"


def test_percent_string_accepted():
    r = extract("x", CLIENTS, fake('{"client_id":"acme","intent":"discount_request","discount_pct":"12%","new_bank_account":null,"new_due_date":null}'))
    assert r.discount_pct == 12.0


def test_bad_output_fails_closed():
    assert extract("x", CLIENTS, fake("not json")).intent == "other"
    assert extract("x", CLIENTS, fake('{"intent":"hack"}')).intent == "other"
    assert extract("x", CLIENTS, fake('{"client_id":"acme","intent":"discount_request","discount_pct":500}')).intent == "other"


def test_invented_client_dropped_and_bad_date_dropped():
    r = extract("x", CLIENTS, fake('{"client_id":"hacker","intent":"deadline_extension","discount_pct":null,"new_bank_account":null,"new_due_date":"next friday"}'))
    assert r.client_id is None and r.new_due_date is None


def test_retries_once_then_succeeds():
    calls = []

    def flaky(s, u):
        calls.append(1)
        return "oops" if len(calls) == 1 else '{"client_id":null,"intent":"other","discount_pct":null,"new_bank_account":null,"new_due_date":null}'
    assert extract("x", CLIENTS, flaky).intent == "other" and len(calls) == 2
