"""Tiny SQLite store: invoice + payout state (so a retry never double-acts) and the audit log."""
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
"""


class Store:
    def __init__(self, path: str = "float.db"):
        self.conn = sqlite3.connect(path)
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

    # ---- audit log
    def audit(self, event, **details):
        self.conn.execute("INSERT INTO audit (ts, event, details) VALUES (?,?,?)",
                          (time.time(), event, json.dumps(details, default=str)))
        self.conn.commit()

    def list_audit(self, limit=200):
        rows = self.conn.execute("SELECT * FROM audit ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
        out = [{"id": r["id"], "ts": r["ts"], "event": r["event"], "details": json.loads(r["details"])} for r in rows]
        return list(reversed(out))