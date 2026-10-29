"""Confirms your sandbox credentials work.  python check_paypal.py"""
import app  # loads .env
from app.paypal_client import get_access_token

try:
    get_access_token()
    print("OK - got a sandbox access token. Credentials work.")
except Exception as e:
    print(f"FAILED ({type(e).__name__}). Check PAYPAL_CLIENT_ID, PAYPAL_CLIENT_SECRET and PAYPAL_MODE in .env.")
    raise SystemExit(1)