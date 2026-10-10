"""
Guard: deterministic rules, no AI. Precedence BLOCK > NEEDS_APPROVAL > ALLOW.
Fails closed: anything unrecognised is never auto-allowed.
"""
from typing import Optional
from .models import (Client, ParsedRequest, Decision, ALLOW, NEEDS_APPROVAL, BLOCK)

# ---- tunable policy ----
MAX_DISCOUNT_PCT = 10        # above -> BLOCK
APPROVAL_DISCOUNT_PCT = 5    # above (and <= MAX) -> NEEDS_APPROVAL
MAX_AUTO_PAYOUT = 2000       # in client currency; above -> NEEDS_APPROVAL

_KNOWN_INTENTS = {"discount_request", "bank_change", "deadline_extension", "payment_confirmation"}


def evaluate(req: ParsedRequest, client: Optional[Client], sender_email: str,
             payout_amount: Optional[float] = None) -> Decision:
    d = Decision()

    if client is None or req.client_id is None:
        d.escalate(BLOCK, "Client is unknown or could not be identified.")
        return d

    sender = (sender_email or "").strip().lower()
    if sender not in [e.lower() for e in client.known_emails]:
        d.escalate(BLOCK, f"Sender {sender_email} is not a known email for {client.name} (possible spoofing).")

    if req.intent == "discount_request":
        if req.discount_pct is None:
            d.escalate(NEEDS_APPROVAL, "Discount requested but the amount is unclear.")
        elif req.discount_pct > MAX_DISCOUNT_PCT:
            d.escalate(BLOCK, f"Requested discount {req.discount_pct:g}% exceeds the {MAX_DISCOUNT_PCT}% limit.")
        elif req.discount_pct > APPROVAL_DISCOUNT_PCT:
            d.escalate(NEEDS_APPROVAL, f"Discount {req.discount_pct:g}% is above {APPROVAL_DISCOUNT_PCT}% and needs human approval.")

    if req.intent == "bank_change":
        if not req.new_bank_account:
            d.escalate(NEEDS_APPROVAL, "Bank change requested but no account was given.")
        elif req.new_bank_account not in client.known_accounts:
            d.escalate(NEEDS_APPROVAL, "New bank account is not on file; verify with the client through another channel.")

    if payout_amount is not None and payout_amount > MAX_AUTO_PAYOUT:
        d.escalate(NEEDS_APPROVAL, f"Payout {payout_amount:g} exceeds the auto-approve limit of {MAX_AUTO_PAYOUT}.")

    if req.intent not in _KNOWN_INTENTS:
        d.escalate(NEEDS_APPROVAL, "Request type not recognised; routed to a human.")

    if not d.reasons:
        d.reasons.append("All checks passed.")
    return d
