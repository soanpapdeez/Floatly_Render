"""Tiny SQLite store: invoice + payout state (so a retry never double-acts), approvals, and the audit log."""
import json
import sqlite3
import time

SCHEMA = """
CREATE TABLE IF NOT EXISTS invoices (
  key TEXT PRIMARY KEY, goal_id TEXT, client_id TEXT, paypal_invoice_id TEXT,
  amount REAL, due_date TEXT, discount_pct REAL, status TEXT, created_at REAL);
CREATE TABLE IF NOT EXISTS payouts (
  key TEXT PRIMARY KEY, goal_id TEXT, contractor_id TEXT, amount REAL,
  batch_id TEXT, status TEXT, created_at REAL);
CREATE TABLE IF NOT EXISTS audit (
  id INTEGER PRIMARY KEY AUTOINCREMENT, ts REAL, event TEXT, details TEXT);
CREATE TABLE IF NOT EXISTS known_accounts (
  client_id TEXT, account TEXT, approved_at REAL, PRIMARY KEY (client_id, account));
CREATE TABLE IF NOT EXISTS approvals (
  id INTEGER PRIMARY KEY AUTOINCREMENT, created_at REAL, email_id TEXT, client_id TEXT, intent TEXT,
  payload TEXT, reasons TEXT, status TEXT, decided_at REAL, note TEXT);
"""


class Store:
    def __init__(self, path: str = "float.db"):
        # check_same_thread=False: a web server (Flask/FastAPI) calls this from several threads.
        self.conn = sqlite3.connect(path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(SCHEMA)
        self.conn.commit()

    # ---- invoices
    def get_invoice(self, key):
        row = self.conn.execute("SELECT * FROM invoices WHERE key=?", (key,)).fetchone()
        return dict(row) if row else None

    def save_invoice(self, key, goal_id, client_id, paypal_invoice_id, amount, due_date, discount_pct, status="unpaid"):
        self.conn.execute("INSERT INTO invoices VALUES (?,?,?,?,?,?,?,?,?)",
                          (key, goal_id, client_id, paypal_invoice_id, amount, due_date, discount_pct, status, time.time()))
        self.conn.commit()

    def set_invoice_status(self, key, status):
        self.conn.execute("UPDATE invoices SET status=? WHERE key=?", (status, key))
        self.conn.commit()

    def list_invoices(self, goal_id):
        rows = self.conn.execute("SELECT * FROM invoices WHERE goal_id=? ORDER BY created_at, key", (goal_id,)).fetchall()
        return [dict(r) for r in rows]

    def goal_ids(self):
        rows = self.conn.execute("SELECT goal_id FROM invoices GROUP BY goal_id ORDER BY MIN(created_at)").fetchall()
        return [r["goal_id"] for r in rows]

    def unpaid_invoices_for_client(self, client_id):
        """Newest first. Only invoices PayPal still reports as unpaid."""
        rows = self.conn.execute("SELECT * FROM invoices WHERE client_id=? AND status='unpaid' "
                                 "ORDER BY created_at DESC, key", (client_id,)).fetchall()
        return [dict(r) for r in rows]

    # ---- bank accounts the owner has approved
    def add_known_account(self, client_id, account):
        self.conn.execute("INSERT OR IGNORE INTO known_accounts VALUES (?,?,?)", (client_id, account, time.time()))
        self.conn.commit()

    def list_known_accounts(self):
        rows = self.conn.execute("SELECT client_id, account FROM known_accounts").fetchall()
        return [(r["client_id"], r["account"]) for r in rows]

    # ---- payouts
    def get_payout(self, key):
        row = self.conn.execute("SELECT * FROM payouts WHERE key=?", (key,)).fetchone()
        return dict(row) if row else None

    def save_payout(self, key, goal_id, contractor_id, amount, batch_id, status="submitted"):
        self.conn.execute("INSERT INTO payouts VALUES (?,?,?,?,?,?,?)",
                          (key, goal_id, contractor_id, amount, batch_id, status, time.time()))
        self.conn.commit()

    def set_payout_status(self, key, status):
        self.conn.execute("UPDATE payouts SET status=? WHERE key=?", (status, key))
        self.conn.commit()

    def list_payouts(self, goal_id):
        rows = self.conn.execute("SELECT * FROM payouts WHERE goal_id=? ORDER BY created_at, key", (goal_id,)).fetchall()
        return [dict(r) for r in rows]

    # ---- approvals (things Guard sent to a human)
    def add_approval(self, email_id, client_id, intent, payload, reasons) -> int:
        cur = self.conn.execute(
            "INSERT INTO approvals (created_at, email_id, client_id, intent, payload, reasons, status) "
            "VALUES (?,?,?,?,?,?,?)",
            (time.time(), email_id, client_id, intent, json.dumps(payload), json.dumps(reasons), "pending"))
        self.conn.commit()
        return cur.lastrowid

    @staticmethod
    def _approval(row):
        d = dict(row)
        d["payload"] = json.loads(d["payload"])
        d["reasons"] = json.loads(d["reasons"])
        return d

    def get_approval(self, approval_id):
        row = self.conn.execute("SELECT * FROM approvals WHERE id=?", (approval_id,)).fetchone()
        return self._approval(row) if row else None

    def list_approvals(self, status=None):
        if status:
            rows = self.conn.execute("SELECT * FROM approvals WHERE status=? ORDER BY id", (status,)).fetchall()
        else:
            rows = self.conn.execute("SELECT * FROM approvals ORDER BY id").fetchall()
        return [self._approval(r) for r in rows]

    def decide_approval(self, approval_id, status, note=""):
        cur = self.conn.execute("UPDATE approvals SET status=?, decided_at=?, note=? WHERE id=? AND status='pending'",
                                (status, time.time(), note, approval_id))
        self.conn.commit()
        if cur.rowcount == 0:
            raise ValueError(f"Approval {approval_id} does not exist or was already decided.")
        return self.get_approval(approval_id)

    # ---- audit log
    def audit(self, event, **details):
        self.conn.execute("INSERT INTO audit (ts, event, details) VALUES (?,?,?)",
                          (time.time(), event, json.dumps(details, default=str)))
        self.conn.commit()

    def list_audit(self, limit=200):
        rows = self.conn.execute("SELECT * FROM audit ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
        out = [{"id": r["id"], "ts": r["ts"], "event": r["event"], "details": json.loads(r["details"])} for r in rows]
        return list(reversed(out))