import pytest

from app.data import load_clients
from app.planner import load_open_invoices, make_plan
from app.summarizer import summarize_plan, template_summary

CLIENTS = load_clients()


@pytest.fixture
def plan():
    return make_plan(6000, "2026-10-16", load_open_invoices(), CLIENTS)


def test_template_mentions_real_numbers(plan):
    t = template_summary(plan, CLIENTS)
    assert "$6,000.00" in t and "$3,050.00" in t and "Northwind" in t and "$6,445.00" in t


def test_good_ai_text_is_used(plan):
    ai = "Float expects $3,050.00 on time and offers Northwind 3% off, costing $105.00, for a best case of $6,445.00."
    out = summarize_plan(plan, CLIENTS, lambda s, u: ai)
    assert out["source"] == "ai" and out["text"] == ai


def test_invented_number_falls_back_to_template(plan):
    out = summarize_plan(plan, CLIENTS, lambda s, u: "You will receive $9,999.00 by Friday.")
    assert out["source"] == "template"


def test_broken_ai_falls_back_to_template(plan):
    def boom(s, u):
        raise RuntimeError("down")
    assert summarize_plan(plan, CLIENTS, boom)["source"] == "template"


def test_no_ai_uses_template(plan):
    assert summarize_plan(plan, CLIENTS)["source"] == "template"


def test_shortfall_text(plan):
    p = make_plan(50000, "2026-10-16", load_open_invoices(), CLIENTS)
    assert "short" in template_summary(p, CLIENTS)