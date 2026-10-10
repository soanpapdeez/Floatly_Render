"""Shared data contract. Both people code against these - change only by agreeing together."""
from dataclasses import dataclass, field
from typing import Optional

ALLOW, NEEDS_APPROVAL, BLOCK = "allow", "needs_approval", "block"
_RANK = {ALLOW: 0, NEEDS_APPROVAL: 1, BLOCK: 2}

INTENTS = ["discount_request", "bank_change", "deadline_extension",
           "payment_confirmation", "other"]


@dataclass
class Client:
    client_id: str
    name: str
    known_emails: list
    known_accounts: list
    currency: str = "USD"
    payment_history: list = field(default_factory=list)

    @property
    def payment_history_count(self) -> int:
        return len(self.payment_history)


@dataclass
class ParsedRequest:
    """What the AI extracts from an email. Extraction only - never a decision."""
    client_id: Optional[str]
    intent: str
    discount_pct: Optional[float] = None
    new_bank_account: Optional[str] = None
    new_due_date: Optional[str] = None
    raw_message: str = ""


@dataclass
class Decision:
    decision: str = ALLOW
    reasons: list = field(default_factory=list)  # plain-language, shown in the UI

    def escalate(self, level: str, reason: str) -> None:
        if _RANK[level] > _RANK[self.decision]:
            self.decision = level
        self.reasons.append(reason)
