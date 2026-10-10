import json
from pathlib import Path
from .models import Client

DATA_DIR = Path(__file__).resolve().parent.parent / "data"


def load_clients() -> dict:
    raw = json.loads((DATA_DIR / "clients.json").read_text(encoding="utf-8"))
    return {c["client_id"]: Client(**c) for c in raw}


def load_inbox() -> list:
    return json.loads((DATA_DIR / "inbox.json").read_text(encoding="utf-8"))
