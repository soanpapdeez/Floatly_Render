"""PayPal access (SANDBOX ONLY): token, invoices and payouts.

Needs in .env (never commit .env):
  PAYPAL_MODE=sandbox
  PAYPAL_CLIENT_ID, PAYPAL_CLIENT_SECRET
  PAYPAL_BUSINESS_EMAIL      the sandbox BUSINESS account email (the invoice sender)

Public functions:
  create_and_send_invoice(client, amount, due_date) -> invoice id
  get_invoice_status(invoice_id)                    -> 'paid' / 'unpaid' / ...
  send_payout(email, amount, request_id=...)        -> payout batch id

Money rule: amounts and due dates must come from our own records or PayPal,
NEVER straight from an email. Guard decides before any of these is called.
"""
import os
import time
import uuid

import requests
from dotenv import load_dotenv

load_dotenv()

SANDBOX_URL = "https://api-m.sandbox.paypal.com"
TIMEOUT = 30


def base_url() -> str:
    if os.getenv("PAYPAL_MODE", "sandbox").lower() != "sandbox":
        raise RuntimeError("Refusing to run: PAYPAL_MODE must be 'sandbox' for this project.")
    return SANDBOX_URL


def get_access_token() -> str:
    cid, secret = os.getenv("PAYPAL_CLIENT_ID"), os.getenv("PAYPAL_CLIENT_SECRET")
    if not cid or not secret:
        raise RuntimeError("Set PAYPAL_CLIENT_ID and PAYPAL_CLIENT_SECRET in .env")
    r = requests.post(f"{base_url()}/v1/oauth2/token", auth=(cid, secret),
                      data={"grant_type": "client_credentials"},
                      headers={"Accept": "application/json"}, timeout=15)
    r.raise_for_status()
    return r.json()["access_token"]


# ---------------------------------------------------------------- helpers

_token_cache = {"value": None, "expires_at": 0.0}


def _cached_token() -> str:
    """Reuse the token for a while instead of asking PayPal on every call."""
    if _token_cache["value"] and time.time() < _token_cache["expires_at"]:
        return _token_cache["value"]
    _token_cache["value"] = get_access_token()
    _token_cache["expires_at"] = time.time() + 30 * 60   # 30 min, safely under PayPal's limit
    return _token_cache["value"]


def _headers(extra: dict = None) -> dict:
    h = {"Authorization": f"Bearer {_cached_token()}", "Content-Type": "application/json"}
    if extra:
        h.update(extra)
    return h


def _check(r: requests.Response) -> requests.Response:
    """Raise a readable error (PayPal's own message) instead of failing silently."""
    if not r.ok:
        raise RuntimeError(f"PayPal {r.status_code}: {r.text[:600]}")
    return r


def _money(amount) -> str:
    """Validate an amount and format it the way PayPal wants ('25.00')."""
    value = float(amount)
    if value <= 0:
        raise ValueError(f"amount must be positive, got {amount!r}")
    return f"{value:.2f}"


# ---------------------------------------------------------- public functions

def create_and_send_invoice(client, amount, due_date: str, currency: str = "USD") -> str:
    """client: {"email": ..., "item": optional description} or just an email string.
    due_date: 'YYYY-MM-DD'. Returns the invoice id (INV2-XXXX-XXXX-XXXX-XXXX)."""
    if isinstance(client, str):
        client = {"email": client}
    business_email = os.getenv("PAYPAL_BUSINESS_EMAIL")
    if not business_email:
        raise RuntimeError("Set PAYPAL_BUSINESS_EMAIL in .env (your sandbox business account email)")

    body = {
        "detail": {
            "currency_code": currency,
            "note": "Invoice sent by Floatly",
            "payment_term": {"term_type": "DUE_ON_DATE_SPECIFIED", "due_date": due_date},
        },
        "invoicer": {
            "name": {"given_name": "Floatly", "surname": "Business"},
            "email_address": business_email,
        },
        "primary_recipients": [{"billing_info": {"email_address": client["email"]}}],
        "items": [{
            "name": client.get("item", "Services"),
            "quantity": "1",
            "unit_amount": {"currency_code": currency, "value": _money(amount)},
        }],
    }
    r = _check(requests.post(f"{base_url()}/v2/invoicing/invoices", headers=_headers(),
                             json=body, timeout=TIMEOUT))
    # The create response returns a link; the invoice id is the last part of it.
    invoice_id = r.json()["href"].rstrip("/").split("/")[-1]

    _check(requests.post(f"{base_url()}/v2/invoicing/invoices/{invoice_id}/send",
                         headers=_headers(),
                         json={"send_to_recipient": True, "send_to_invoicer": True},
                         timeout=TIMEOUT))
    return invoice_id


def get_invoice_status(invoice_id: str) -> str:
    """Returns 'paid', 'unpaid', 'partially_paid', 'cancelled' or 'draft'.
    Any other PayPal status is passed through in lowercase so it is visible."""
    r = _check(requests.get(f"{base_url()}/v2/invoicing/invoices/{invoice_id}",
                            headers=_headers(), timeout=TIMEOUT))
    raw = r.json().get("status", "UNKNOWN")
    mapping = {
        "PAID": "paid",
        "MARKED_AS_PAID": "paid",
        "PARTIALLY_PAID": "partially_paid",
        "CANCELLED": "cancelled",
        "DRAFT": "draft",
        "SENT": "unpaid",
        "UNPAID": "unpaid",
    }
    return mapping.get(raw, raw.lower())


def send_payout(email: str, amount, currency: str = "USD", request_id: str = None,
                note: str = "Payment from Floatly") -> str:
    """Sends one payout and returns the payout batch id.

    IDEMPOTENCY: to retry the SAME payment, pass the SAME request_id (for example
    'payout-<invoice_id>-<contractor>'), so PayPal never pays twice. Only a brand-new
    payment may use the random default.
    """
    request_id = request_id or str(uuid.uuid4())
    body = {
        "sender_batch_header": {
            "sender_batch_id": request_id,
            "email_subject": "You have a payout!",
            "email_message": note,
        },
        "items": [{
            "recipient_type": "EMAIL",
            "amount": {"value": _money(amount), "currency": currency},
            "receiver": email,
            "sender_item_id": request_id,
        }],
    }
    r = _check(requests.post(f"{base_url()}/v1/payments/payouts",
                             headers=_headers({"PayPal-Request-Id": request_id}),
                             json=body, timeout=TIMEOUT))
    return r.json()["batch_header"]["payout_batch_id"]
def get_payout_status(batch_id: str) -> str:
    """Returns the payout status in lowercase ('success', 'pending', 'unclaimed', ...).
    Uses the single item's status when present, otherwise the batch status."""
    r = _check(requests.get(f"{base_url()}/v1/payments/payouts/{batch_id}",
                            headers=_headers(), timeout=TIMEOUT))
    data = r.json()
    items = data.get("items") or []
    raw = (items[0].get("transaction_status") if items
           else data.get("batch_header", {}).get("batch_status", "UNKNOWN"))
    return str(raw).lower()