"""Turn an approval result into one plain sentence for the UI and the audit log."""


def _last4(acct) -> str:
    s = "".join(ch for ch in str(acct or "") if ch.isalnum())
    return f" ending in {s[-4:]}" if len(s) >= 4 else ""


def _invoice_ref(key) -> str:
    parts = str(key or "").split(":")
    return parts[1] if len(parts) > 1 else (parts[0] or "the invoice")


def describe_effect(intent: str, approved: bool, details: dict | None = None, client_name: str | None = None) -> str:
    """intent: the approval's intent. approved: owner's choice.
    details: what the action returned (e.g. reissue_discounted's dict). client_name: for the sentence."""
    d = details or {}
    intent = (intent or "").lower()
    who = f" for {client_name}" if client_name else " for this client"
    if not approved:
        return "No change was made."
    if "discount" in intent:
        if d.get("applied") and d.get("new_amount") is not None:
            pct = d.get("discount_pct")
            off = f" ({float(pct):g}% off)" if pct else ""
            return (f"Invoice {_invoice_ref(d.get('old_key'))} was cancelled in PayPal and re-sent "
                    f"at ${float(d['new_amount']):,.2f}{off}.")
        return f"Approved, but no invoice was changed: {d.get('note') or d.get('reason') or 'it is no longer unpaid'}"
    if "bank" in intent:
        if d.get("applied"):
            acct = d.get("account") or d.get("bank_account") or d.get("account_id")
            return f"Bank account{_last4(acct)} is now trusted{who}."
        return f"Approved, but nothing was changed: {d.get('note') or 'no new account was given'}"
    if "extension" in intent or "due" in intent:
        return "Recorded only: the due date in PayPal was not changed."
    return "Approved and recorded; no money action was taken."
