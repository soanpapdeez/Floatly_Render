import json
from pathlib import Path

import pytest

from app import guard
from app.models import Client
from app.planner import (OpenInvoice, expected_days_late, discount_tier, make_plan,
                         load_open_invoices)

ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture
def clients():
    rows = json.loads((ROOT / "data" / "clients.json").read_text(encoding="utf-8"))
    return {r["client_id"]: Client(**r) for r in rows}


@pytest.fixture
def invoices():
    return load_open_invoices(str(ROOT / "data" / "open_invoices.json"))


def test_expected_days_late_rounds_up(clients):
    assert expected_days_late(clients["acme"]) == 1        # (0,2,0) -> 0.67 -> 1
    assert expected_days_late(clients["zenlabs"]) == 7     # (5,9) -> 7
    assert expected_days_late(clients["skyline"]) == 0


def test_no_history_assumes_late():
    c = Client("x", "X", [], [], payment_history=[])
    assert expected_days_late(c) == 7


def test_discount_tier_never_exceeds_guard_limit():
    for days in range(0, 60):
        assert discount_tier(days) <= guard.APPROVAL_DISCOUNT_PCT


def test_plan_covers_goal_with_cheapest_offer(clients, invoices):
    plan = make_plan(6000, "2026-10-16", invoices, clients)
    assert plan.expected_on_track == 3050            # acme + brightco + skyline
    assert plan.covered and plan.shortfall == 0
    offers = [i for i in plan.items if i.action == "early_pay_offer"]
    assert len(offers) == 1                          # one offer is enough
    assert offers[0].client_id == "northwind"
    assert offers[0].discount_pct == 3
    assert plan.best_case == pytest.approx(3050 + 3500 * 0.97)


def test_no_discounts_when_goal_already_covered(clients, invoices):
    plan = make_plan(2000, "2026-10-16", invoices, clients)
    assert plan.covered
    assert all(i.action == "reminder" for i in plan.items)
    assert plan.total_discount_cost == 0


def test_shortfall_reported_honestly(clients, invoices):
    plan = make_plan(50000, "2026-10-16", invoices, clients)
    assert not plan.covered
    assert plan.shortfall > 0


def test_every_item_has_a_reason(clients, invoices):
    plan = make_plan(6000, "2026-10-16", invoices, clients)
    assert all(i.reason for i in plan.items)
    assert len(plan.items) == len(invoices)


def test_unknown_client_raises(clients):
    with pytest.raises(ValueError):
        make_plan(1000, "2026-10-16", [OpenInvoice("X", "ghost", 100, "2026-10-14")], clients)