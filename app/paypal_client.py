"""PayPal access (SANDBOX ONLY). Person A builds Invoicing/Payouts on top of this."""
import os
import requests

SANDBOX_URL = "https://api-m.sandbox.paypal.com"


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
