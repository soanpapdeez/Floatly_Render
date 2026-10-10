"""email -> extract -> resolve client -> guard. Person A's orchestrator will call process_email()."""
from dataclasses import dataclass
from typing import Callable
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


def process_email(email: dict, clients: dict, call_llm: Callable[[str, str], str]) -> Result:
    text = f"{email.get('subject', '')}\n{email['body']}"
    parsed = extract(text, list(clients), call_llm)

    # The email's CLAIMED client comes from its text. If it names none, fall back to the
    # sender address. If they disagree, Guard blocks (sender not known for claimed client).
    if parsed.client_id is None:
        match = find_client_by_sender(email["sender"], clients)
        parsed.client_id = match.client_id if match else None

    client = clients.get(parsed.client_id) if parsed.client_id else None
    decision = guard.evaluate(parsed, client, email["sender"])
    return Result(email["id"], parsed, decision)
