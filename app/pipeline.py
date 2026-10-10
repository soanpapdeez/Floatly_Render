"""email -> extract -> resolve client -> guard. Person A's orchestrator will call process_email()."""
from dataclasses import dataclass
from typing import Callable, Optional
from . import guard
from .extractor import extract
from .models import ParsedRequest, Decision


@dataclass
class Result:
    email_id: str
    parsed: ParsedRequest
    decision: Decision


def find_client_by_sender(sender: str, clients: dict):
    s = (sender or "").strip().lower()
    for c in clients.values():
        if s in [e.lower() for e in c.known_emails]:
            return c
    return None


def process_email(email: dict, clients: dict, call_llm: Callable[[str, str], str],
                  current_due_date: Optional[str] = None,
                  payout_amount: Optional[float] = None) -> Result:
    """
    current_due_date: the invoice's real due date (YYYY-MM-DD) from OUR records / PayPal,
    never from the email text. The orchestrator passes it in. For the sample inbox, an optional
    "current_due_date" key on the email record is used as a stand-in.
    """
    text = f"{email.get('subject', '')}\n{email['body']}"
    parsed = extract(text, list(clients), call_llm)

    # The email's CLAIMED client comes from its text. If it names none, fall back to the
    # sender address. If they disagree, Guard blocks (sender not known for claimed client).
    if parsed.client_id is None:
        match = find_client_by_sender(email["sender"], clients)
        parsed.client_id = match.client_id if match else None

    client = clients.get(parsed.client_id) if parsed.client_id else None
    due = current_due_date or email.get("current_due_date")
    decision = guard.evaluate(parsed, client, email["sender"],
                              payout_amount=payout_amount, current_due_date=due)
    return Result(email["id"], parsed, decision)