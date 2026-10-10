"""Person A, day 1: confirms your sandbox credentials work.  python check_paypal.py"""
import app  # loads .env
from app.paypal_client import get_access_token

try:
    token = get_access_token()
    print(f"OK - got sandbox access token ({token[:6]}...). Credentials work.")
except Exception as e:
    print(f"FAILED: {e}")
    raise SystemExit(1)
