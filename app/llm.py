"""
LLM adapter. get_llm() returns call_llm(system, user) -> str.
Providers: mock (offline, regex - for plumbing/tests only), anthropic, openai.
Set LLM_PROVIDER in .env. The mock is NOT a substitute for evaluating a real model.
"""
import json
import os
import re

DEFAULT_MODELS = {"anthropic": "claude-sonnet-5-5", "openai": "gpt-4o-mini"}


def mock_llm(system: str, user: str) -> str:
    final = user.rsplit("Now extract.", 1)[-1]
    allowed = [c.strip() for c in re.search(r"Allowed client ids: ([^\n]+)", final).group(1).split(",")]
    email = final.split('Email: """', 1)[1].rsplit('"""', 1)[0]
    low = email.lower()

    cid = next((c for c in allowed if re.search(rf"\b{re.escape(c.lower())}\b", low)), None)
    pct = acct = due = None

    if re.search(r"ignore (all )?(previous|prior)|disregard .*rules", low):
        intent = "other"
    elif re.search(r"\b(due date|extension|extend|postpone)\b", low):
        intent = "deadline_extension"
        m = re.search(r"\d{4}-\d{2}-\d{2}", email)
        due = m.group(0) if m else None
    elif re.search(r"discount|\d+(\.\d+)?\s*%", low):
        intent = "discount_request"
        m = re.search(r"(\d+(?:\.\d+)?)\s*%", email)
        pct = float(m.group(1)) if m else None
    elif re.search(r"acc-[a-z0-9-]+|new (bank )?account|changed (our )?bank|moved banks|new bank", low):
        intent = "bank_change"
        m = re.search(r"ACC-[A-Z0-9-]+", email, re.I)
        acct = m.group(0).upper() if m else None
    elif re.search(r"\b(paid|payment (has been |was )?(sent|made|done)|transferred)\b", low):
        intent = "payment_confirmation"
    else:
        intent = "other"

    return json.dumps({"client_id": cid, "intent": intent, "discount_pct": pct,
                       "new_bank_account": acct, "new_due_date": due})


def _anthropic(model: str):
    from anthropic import Anthropic
    client = Anthropic()  # reads ANTHROPIC_API_KEY

    def call(system: str, user: str) -> str:
        r = client.messages.create(model=model, max_tokens=300, system=system,
                                   messages=[{"role": "user", "content": user}])
        return r.content[0].text
    return call


def _openai(model: str):
    from openai import OpenAI
    client = OpenAI()  # reads OPENAI_API_KEY

    def call(system: str, user: str) -> str:
        r = client.chat.completions.create(
            model=model, temperature=0,
            messages=[{"role": "system", "content": system}, {"role": "user", "content": user}])
        return r.choices[0].message.content
    return call


def get_llm(provider: str = None):
    provider = (provider or os.getenv("LLM_PROVIDER") or "mock").lower()
    if provider == "mock":
        return mock_llm
    model = os.getenv("LLM_MODEL") or DEFAULT_MODELS.get(provider)
    if provider == "anthropic":
        return _anthropic(model)
    if provider == "openai":
        return _openai(model)
    raise ValueError(f"Unknown LLM_PROVIDER: {provider}")
