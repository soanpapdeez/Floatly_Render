"""
Optional Zapier notification: tells the owner (email / Slack / WhatsApp, via a Zap) when a human decision
is needed or an attack was blocked.

Set ZAPIER_WEBHOOK_URL in .env to turn it on (a "Catch Hook" URL from Zapier). With no URL it does nothing.
It NEVER raises: a failed notification must never break the money logic.
"""
import os

import requests


def notify(event: str, **payload) -> bool:
    url = os.getenv("ZAPIER_WEBHOOK_URL", "").strip()
    if not url.startswith("https://"):
        return False
    try:
        r = requests.post(url, json={"app": "floatly", "event": event, **payload}, timeout=5)
        return r.ok
    except Exception:
        return False