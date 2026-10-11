"""
Planner (Float): goal -> which open invoices to just remind, and which to offer an early-pay discount.

Deterministic and explainable on purpose: NO AI here. Every plan item carries a plain-language reason,
and every number is computed from client payment history we can show on screen.

Discount offers never exceed guard.APPROVAL_DISCOUNT_PCT, so Guard's limits still apply to us.

The method:
  1. For each open invoice, estimate when it will really be paid:
       expected pay date = due date + (average of the client's last RECENT_N days_late, rounded UP).
  2. Invoices expected by the deadline are "on track": normal reminder, no discount (do not waste money).
  3. Invoices expected AFTER the deadline are "at risk". If on-track cash is still short of the goal,
     offer early-pay discounts, cheapest first, until the best case (every offer accepted) covers the goal.
  4. Anything still short is reported honestly as a shortfall.
"""

import json
import math
from dataclasses import dataclass, asdict, field
from datetime import date, timedelta
from typing import Optional

from . import guard
from .data import DATA_DIR
from .models import Client


RECENT_N = 3                 # how many recent paid invoices to average
DEFAULT_DAYS_LATE = 7        # clients with no history: assume late (conservative)
REMIND_DAYS_BEFORE = 2       # "remind clients 2 days before due date"


@dataclass
class OpenInvoice:
    invoice_id: str
    client_id: str
    amount: float
    due_date: str            # YYYY-MM-DD, from OUR records / PayPal, never from an email


@dataclass
class PlanItem:
    client_id: str
    amount: float
    due_date: str
    invoice_id: str
    expected_pay_date: str
    action: str              # "reminder" | "early_pay_offer"
    discount_pct: float      # 0 for reminders
    cash_if_paid: float      # what we receive if the client follows this action
    remind_on: str           # when to send the reminder
    reason: str              # plain-language explanation shown in the UI / audit log


@dataclass
class Plan:
    goal_amount: float
    deadline: str
    expected_on_track: float     # cash expected by the deadline with NO discounts
    best_case: float             # if every offer is accepted
    shortfall: float             # goal - best_case (0 if covered)
    covered: bool
    total_discount_cost: float   # most we would give away if every offer is accepted
    items: list = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)


def load_open_invoices(path=None) -> list:
    path = path or (DATA_DIR / "open_invoices.json")
    with open(path, encoding="utf-8") as f:
        return [OpenInvoice(**row) for row in json.load(f)]


def expected_days_late(client: Client) -> int:
    """Average of the last RECENT_N paid invoices, rounded UP (conservative)."""
    recent = [
        h["days_late"]
        for h in client.payment_history
        if h.get("status") == "paid"
    ][-RECENT_N:]

    if not recent:
        return DEFAULT_DAYS_LATE

    return math.ceil(sum(recent) / len(recent))


def discount_tier(days_early_needed: int) -> int:
    """The more days earlier we need them to pay, the bigger the incentive.
    Capped by Guard's auto limit.
    """
    if days_early_needed <= 3:
        tier = 2
    elif days_early_needed <= 7:
        tier = 3
    else:
        tier = 5

    return min(tier, guard.APPROVAL_DISCOUNT_PCT)


def make_plan(
    goal_amount: float,
    deadline: str,
    open_invoices: list,
    clients: dict
) -> Plan:
    deadline_d = date.fromisoformat(deadline)
    on_track, at_risk = [], []

    for inv in open_invoices:
        client = clients.get(inv.client_id)

        if client is None:
            raise ValueError(
                f"Open invoice {inv.invoice_id} has unknown client {inv.client_id!r}"
            )

        late = expected_days_late(client)
        due_d = date.fromisoformat(inv.due_date)
        expected = due_d + timedelta(days=late)

        row = (inv, client, late, due_d, expected)

        (
            on_track if expected <= deadline_d else at_risk
        ).append(row)

    expected_on_track = round(
        sum(r[0].amount for r in on_track),
        2
    )

    # Cheapest discounts first (smaller % first),
    # bigger invoices first within the same %.
    candidates = []

    for inv, client, late, due_d, expected in at_risk:
        days_early = (expected - deadline_d).days

        candidates.append(
            (
                discount_tier(days_early),
                -inv.amount,
                inv,
                client,
                late,
                due_d,
                expected,
                days_early,
            )
        )

    candidates.sort(key=lambda c: (c[0], c[1]))

    cash = expected_on_track
    chosen = {}

    for (
        tier,
        _,
        inv,
        client,
        late,
        due_d,
        expected,
        days_early,
    ) in candidates:
        if cash >= goal_amount:
            break

        cash += inv.amount * (1 - tier / 100)
        chosen[inv.invoice_id] = tier

    items = []

    # On-track invoices: normal reminder, no discount.
    for inv, client, late, due_d, expected in on_track:
        items.append(
            PlanItem(
                client_id=inv.client_id,
                amount=inv.amount,
                due_date=inv.due_date,
                invoice_id=inv.invoice_id,
                expected_pay_date=expected.isoformat(),
                action="reminder",
                discount_pct=0,
                cash_if_paid=round(inv.amount, 2),
                remind_on=(
                    due_d - timedelta(days=REMIND_DAYS_BEFORE)
                ).isoformat(),
                reason=(
                    f"{client.name} usually pays about {late} day(s) "
                    f"after the due date, so this should arrive around "
                    f"{expected.isoformat()}, before your {deadline} deadline. "
                    f"No discount needed."
                ),
            )
        )

    # At-risk invoices: either offer an early-pay discount
    # or send a normal reminder.
    for inv, client, late, due_d, expected in at_risk:
        days_early = (expected - deadline_d).days
        tier = chosen.get(inv.invoice_id)

        if tier:
            cost = round(inv.amount * tier / 100, 2)

            items.append(
                PlanItem(
                    client_id=inv.client_id,
                    amount=inv.amount,
                    due_date=inv.due_date,
                    invoice_id=inv.invoice_id,
                    expected_pay_date=expected.isoformat(),
                    action="early_pay_offer",
                    discount_pct=tier,
                    cash_if_paid=round(
                        inv.amount * (1 - tier / 100),
                        2
                    ),
                    remind_on=(
                        due_d - timedelta(days=REMIND_DAYS_BEFORE)
                    ).isoformat(),
                    reason=(
                        f"{client.name} usually pays around "
                        f"{expected.isoformat()}, {days_early} day(s) "
                        f"after your {deadline} deadline. Offering "
                        f"{tier}% off if they pay by {deadline} "
                        f"(costs ${cost:,.2f}) is the cheapest way "
                        f"to close the gap."
                    ),
                )
            )

        else:
            items.append(
                PlanItem(
                    client_id=inv.client_id,
                    amount=inv.amount,
                    due_date=inv.due_date,
                    invoice_id=inv.invoice_id,
                    expected_pay_date=expected.isoformat(),
                    action="reminder",
                    discount_pct=0,
                    cash_if_paid=round(inv.amount, 2),
                    remind_on=(
                        due_d - timedelta(days=REMIND_DAYS_BEFORE)
                    ).isoformat(),
                    reason=(
                        f"{client.name} will probably pay around "
                        f"{expected.isoformat()}, after your deadline, "
                        f"but a discount isn't needed to reach the goal. "
                        f"Normal reminder only."
                    ),
                )
            )

    best_case = round(cash, 2)

    shortfall = round(
        max(0.0, goal_amount - best_case),
        2
    )

    total_cost = round(
        sum(
            i.amount * i.discount_pct / 100
            for i in items
        ),
        2
    )

    items.sort(
        key=lambda i: (
            i.action != "early_pay_offer",
            i.expected_pay_date
        )
    )

    return Plan(
        goal_amount=goal_amount,
        deadline=deadline,
        expected_on_track=expected_on_track,
        best_case=best_case,
        shortfall=shortfall,
        covered=shortfall == 0,
        total_discount_cost=total_cost,
        items=items,
    )


def format_plan(plan: Plan) -> str:
    lines = [
        f"Goal: ${plan.goal_amount:,.2f} by {plan.deadline}",
        f"Expected with no discounts: ${plan.expected_on_track:,.2f}",
        f"Best case with offers accepted: ${plan.best_case:,.2f}  "
        f"({'GOAL COVERED' if plan.covered else f'SHORT by ${plan.shortfall:,.2f}'}",
        f"Most we could give away: ${plan.total_discount_cost:,.2f}",
        "",
    ]

    for i in plan.items:
        tag = (
            f"OFFER {i.discount_pct:g}%"
            if i.action == "early_pay_offer"
            else "reminder  "
        )

        lines.append(
            f"[{tag}] {i.invoice_id} {i.client_id} "
            f"${i.amount:,.2f} -> {i.reason}"
        )

    return "\n".join(lines)