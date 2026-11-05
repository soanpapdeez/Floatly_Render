"""Floatly UI server. From the repo root:  pip install flask  then  python ui/server.py
  default            -> app.service.build_service()           (real PayPal sandbox, needs keys in .env)
  FLOAT_FAKE=1       -> app.service.build_service(fake=True) (offline, no keys)
  UI_STANDIN=1       -> built-in sample service (only if app/service.py is missing)
Render: start command  gunicorn ui.server:web   (put keys in Render env vars, never in the repo)

Pages (Jinja templates in ui/templates, static files in ui/static):
  /  /invoices  /inbox  /approvals  /audit  /simulate  /settings      (/classic = the previous one-page UI)

JSON API. The original routes keep their request/response shapes; new fields are only ever ADDED.
  GET  /api/mode                 {mode, badge, fake, amount_scale, ...}
  POST /api/preview              svc.preview(text)                        (also remembered for the dashboard)
  POST /api/launch               svc.launch(amount, deadline)
  GET  /api/tick/<gid>           svc.tick(gid)        (polls PayPal)
  POST /api/pay/<key>            svc.simulate_payment(key)                (FLOAT_FAKE only)
  POST /api/email                svc.submit_email(email)                  (also kept for the Guard Inbox)
  GET  /api/approvals?status=    pending | approved | rejected | all      (+ "preview" of what each button does)
  POST /api/decide               svc.decide(id, approve)                  (+ "audit_id" of the logged decision)
  GET  /api/audit?limit=         svc.audit(limit)
  NEW  GET  /api/meta            mode, Guard policy, clients, contractors, goals, pending count
  NEW  GET  /api/dashboard       everything the dashboard needs in one call (?goal_id=  ?tick=1 polls PayPal)
  NEW  GET  /api/state/<gid>     svc.state(gid)       (no PayPal call)
  NEW  GET  /api/emails          client emails Guard has seen: extracted request + decision
  NEW  GET  /api/samples         the sample inbox (data/inbox.json) with expected verdicts
  NEW  POST /api/simulate/email/<sample_id>   run one sample email through extractor -> Guard
  NEW  POST /api/simulate/outage              FLOAT_FAKE only: next PayPal status checks fail
  NEW  POST /api/simulate/reset               FLOAT_FAKE only: fresh in-memory demo
This file only reads from FloatService / Store and calls its public methods. Guard, planner and PayPal logic are
untouched.
"""
import dataclasses, json, os, re, sys, threading, time
from datetime import date, datetime
from pathlib import Path
from flask import Flask, jsonify, render_template, request, send_file

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT.parent))


class StandIn:
    """Sample data in the shapes from the UI requirements table. Replace by the real service."""
    ITEMS = [("OPEN-004", "northwind", 3395.0, "early_pay_offer", "Usually pays 5 days after the deadline. Offering 3% off if they pay in time costs $105.00, the cheapest way to close the gap."),
             ("OPEN-005", "skyline", 600.0, "reminder", "Usually pays on time, so this should arrive before the deadline. No discount needed."),
             ("OPEN-001", "acme", 1500.0, "reminder", "Usually pays 1 day late, still before the deadline. No discount needed."),
             ("OPEN-002", "brightco", 950.0, "reminder", "Usually pays 1 day late, still before the deadline. No discount needed."),
             ("OPEN-006", "pixelforge", 450.0, "reminder", "Will probably pay after the deadline, but the goal doesn't need it. Normal reminder."),
             ("OPEN-003", "zenlabs", 2000.0, "reminder", "Will probably pay after the deadline, but the goal doesn't need it. Normal reminder.")]
    PAY = [("ravi-dev", 1200.0), ("meera-design", 1800.0)]

    def __init__(s):
        s.goals, s.log, s.appr = {}, [], []

    def _a(s, e, d):
        s.log.insert(0, {"event": e, "details": d, "ts": time.strftime("%H:%M:%S")})

    def preview(s, text):
        amt, m = 6000.0, re.search(r"(\d[\d,.]*)\s*(k)?", text, re.I)
        if m:
            amt = float(m.group(1).replace(",", "")) * (1000 if m.group(2) else 1)
        items = [{"invoice_id": k, "client_id": c, "amount": a, "action": ac, "reason": r} for k, c, a, ac, r in s.ITEMS]
        return {"ok": True, "goal": {"amount": amt, "deadline": "2026-10-16", "deadline_label": "Friday, Oct 16"},
                "plan": {"items": items, "expected": 3050.0, "best_case": 6445.0, "max_discount": 105.0},
                "summary": {"text": "Three clients should pay before Friday ($3,050). Offering Northwind 3% off brings the best case to $6,445 and covers the goal."}}

    def launch(s, amount, deadline):
        gid = f"goal-{deadline}-{int(amount)}"
        s.goals[gid] = {"amount": amount, "deadline": deadline, "paid": set(), "sent": set()}
        s._a("plan_created", gid)
        for k, c, *_ in s.ITEMS:
            s._a("invoice_sent", f"{gid}:{k} {c}")
        return s.tick(gid)

    def tick(s, gid):
        g = s.goals[gid]
        inv = [{"key": k, "client": c, "amount": a, "status": "paid" if k in g["paid"] else "unpaid"} for k, c, a, *_ in s.ITEMS]
        cleared, need, pay = sum(i["amount"] for i in inv if i["status"] == "paid"), 0.0, []
        for n, a in s.PAY:
            need += a
            ok = cleared >= need
            pay.append({"key": n, "name": n, "amount": a, "status": "success" if ok else "waiting"})
            if ok and n not in g["sent"]:
                g["sent"].add(n); s._a("payout_sent", f"{n} ${a:,.0f}")
        return {"goal_id": gid, "goal": g["amount"], "deadline": g["deadline"], "invoices": inv, "payouts": pay,
                "totals": {"cleared": cleared, "expected": 3050.0, "best_case": 6445.0, "goal": g["amount"]}}

    def simulate_payment(s, key):
        for gid, g in s.goals.items():
            g["paid"].add(key); s._a("invoice_status", f"{gid}:{key} paid")
            return s.tick(gid)

    def submit_email(s, e):
        b, sender = e["body"].lower(), e["sender"].lower()
        m = re.search(r"(\d+)\s*%", b); pct = int(m.group(1)) if m else None
        known = sender.endswith(("@acme.com", "@brightco.io", "@zenlabs.in", "@skyline.co", "@northwind.com", "@pixelforge.dev"))
        bank = bool(re.search(r"bank|acc-", b)); why = []
        if not known: why.append(f"Sender {sender} is not a known email for this client (possible spoofing).")
        if pct and pct > 10: why.append(f"Requested discount {pct}% exceeds the 10% limit.")
        if bank: why.append("New bank account is not on file; verify through another channel.")
        d = "block" if (not known or (pct or 0) > 10) else "needs_approval" if bank or (pct or 0) > 5 else "allow"
        if d == "needs_approval" and not why: why.append(f"Discount {pct}% is above 5% and needs human approval.")
        if not why: why.append("All checks passed.")
        aid = None
        if d == "needs_approval":
            aid = len(s.appr) + 1
            s.appr.append({"id": aid, "email_id": e["id"], "sender": e["sender"], "subject": e["subject"], "reasons": why, "status": "pending"})
        s._a("email_decision", f"{e['id']} {d} {why}")
        return {"decision": d, "reasons": why, "parsed": {"discount_pct": pct, "bank_change": bank}, "approval_id": aid}

    def approvals(s, status="pending"):
        return [a for a in s.appr if status is None or a["status"] == status]

    def decide(s, aid, approve):
        a = next(x for x in s.appr if x["id"] == aid)
        a["status"] = "approved" if approve else "rejected"; s._a("approval", f"#{aid} {a['status']}")
        a["effect"] = ("Invoice re-sent at the lower amount." if any("iscount" in r for r in a["reasons"]) else "New bank account is now trusted.") if approve else "No change was made."
        return a

    def audit(s, n=100):
        return s.log[:n]


def make_service():
    if os.getenv("UI_STANDIN") != "1":
        try:
            import app  # noqa: F401  (loads .env)
            from app.service import build_service
            real = os.getenv("FLOAT_FAKE") != "1"
            return build_service() if real else build_service(fake=True), ("Sandbox" if real else "Demo mode")
        except Exception as e:  # service.py missing or broken
            print(f"[ui] using the stand-in service ({type(e).__name__}: {e})")
    return StandIn(), "Sample data"


svc, MODE = make_service()
web = Flask(__name__, template_folder=str(ROOT / "templates"), static_folder=str(ROOT / "static"), static_url_path="/static")
web.json.default = lambda o: dataclasses.asdict(o) if dataclasses.is_dataclass(o) else (sorted(o) if isinstance(o, set) else getattr(o, "__dict__", str(o)))
ASSET_V = str(int(time.time()))                     # cache-buster for static files, changes on every deploy
LOCK = threading.RLock()                            # one lock around everything that writes to the shared SQLite connection


# ---------------------------------------------------------------------------------------------- read-only helpers

BADGES = {"Sandbox": "PAYPAL SANDBOX", "Demo mode": "OFFLINE DEMO", "Sample data": "SAMPLE DATA"}
GOAL_RE = re.compile(r"^goal-(\d{4}-\d{2}-\d{2})-(\d+)$")


def _fake() -> bool:
    return MODE != "Sandbox"


def _scale() -> float:
    try:
        return float(os.getenv("DEMO_AMOUNT_SCALE", "1") or 1)
    except ValueError:
        return 1.0


def _mode_info() -> dict:
    scale = _scale()
    paypal = getattr(svc, "paypal", None)
    return {"mode": MODE, "badge": BADGES.get(MODE, MODE.upper()), "fake": _fake(), "sample": isinstance(svc, StandIn),
            "amount_scale": scale,
            "scale_note": (f"PayPal amounts are scaled x{scale:g}. The UI always shows the real amounts." if scale != 1 else None),
            "llm_provider": (os.getenv("LLM_PROVIDER") or "mock").lower(),
            "can_simulate_payment": isinstance(svc, StandIn) or hasattr(paypal, "mark_paid"),
            "can_simulate_outage": hasattr(paypal, "mark_paid"),
            "poll_seconds": int(os.getenv("UI_POLL_SECONDS", "6"))}


def _policy() -> dict:
    try:
        from app import guard
        g = {k: getattr(guard, k) for k in ("MAX_DISCOUNT_PCT", "APPROVAL_DISCOUNT_PCT", "MAX_AUTO_PAYOUT", "MAX_EXTENSION_DAYS")}
    except Exception:
        g = {"MAX_DISCOUNT_PCT": 10, "APPROVAL_DISCOUNT_PCT": 5, "MAX_AUTO_PAYOUT": 2000, "MAX_EXTENSION_DAYS": 30}
    return {"max_discount_pct": g["MAX_DISCOUNT_PCT"], "approval_discount_pct": g["APPROVAL_DISCOUNT_PCT"],
            "max_auto_payout": g["MAX_AUTO_PAYOUT"], "max_extension_days": g["MAX_EXTENSION_DAYS"],
            "rules": [
                {"rule": f"Discount above {g['MAX_DISCOUNT_PCT']}%", "verdict": "block"},
                {"rule": f"Discount above {g['APPROVAL_DISCOUNT_PCT']}% up to {g['MAX_DISCOUNT_PCT']}%", "verdict": "needs_approval"},
                {"rule": "Sender is not a known email for the client", "verdict": "block"},
                {"rule": "Bank account not on file", "verdict": "needs_approval"},
                {"rule": f"Due-date extension over {g['MAX_EXTENSION_DAYS']} days", "verdict": "needs_approval"},
                {"rule": f"Contractor payout over ${g['MAX_AUTO_PAYOUT']:,}", "verdict": "needs_approval"},
                {"rule": "Request type not recognised", "verdict": "needs_approval"}]}


def _clients() -> dict:
    cl = getattr(svc, "clients", None)
    if cl:
        return cl
    try:
        from app.data import load_clients
        return load_clients()
    except Exception:
        return {}


def _client_rows() -> list:
    try:
        from app.planner import expected_days_late
    except Exception:
        expected_days_late = None
    out = []
    for c in _clients().values():
        hist = [h.get("days_late", 0) for h in c.payment_history if h.get("status") == "paid"]
        out.append({"client_id": c.client_id, "name": c.name, "currency": c.currency,
                    "known_emails": list(c.known_emails), "known_accounts": list(c.known_accounts),
                    "history_days_late": hist,
                    "expected_days_late": expected_days_late(c) if expected_days_late else (round(sum(hist) / len(hist)) if hist else 7)})
    return out


def _contractors() -> list:
    return list(getattr(svc, "contractors", None) or [])


def _store():
    return getattr(svc, "store", None)


def _goal_ids() -> list:
    st = _store()
    if st:
        return st.goal_ids()
    return list(getattr(svc, "goals", {}).keys())


def _label(d: str) -> str:
    try:
        x = date.fromisoformat(d)
        return f"{x:%A}, {x.day} {x:%b %Y}"
    except Exception:
        return d


def _goal_from_id(gid: str):
    m = GOAL_RE.match(gid or "")
    if not m:
        return None
    return {"amount": float(m.group(2)), "deadline": m.group(1), "deadline_label": _label(m.group(1)), "goal_id": gid}


PLANS: dict = {}            # goal_id -> plan dict (from launch, or recomputed by the deterministic planner)
PREVIEW: dict = {}          # the last preview, shown on the dashboard until a plan is launched


def _plan_for(gid: str):
    if gid in PLANS:
        return PLANS[gid], "launch"
    g = _goal_from_id(gid)
    if not g or not hasattr(svc, "open_invoices"):
        return None, None
    try:                                        # same pure function the launch used; nothing is sent
        from app.planner import make_plan
        PLANS[gid] = make_plan(g["amount"], g["deadline"], svc.open_invoices, svc.clients).to_dict()
        return PLANS[gid], "recomputed"
    except Exception:
        return None, None


def _summary_for(plan_dict):
    """Deterministic template summary (no LLM call on every dashboard refresh)."""
    try:
        from app.planner import Plan, PlanItem
        from app.summarizer import template_summary
        p = Plan(**{**plan_dict, "items": [PlanItem(**i) for i in plan_dict["items"]]})
        return {"text": template_summary(p, svc.clients), "source": "template"}
    except Exception:
        return None


# ---------------------------------------------------------------------------------------------- email log (UI side)

class EmailLog:
    """Keeps each client email Guard saw WITH the structured request the AI extracted, so the Guard Inbox can show
    'Extracted request | Guard decision'. The audit log only keeps intent + decision. Stored in the same SQLite file
    as everything else (a separate ui_emails table), or in memory for the stand-in."""

    def __init__(self, store=None):
        self.conn = getattr(store, "conn", None)
        self.mem = []
        if self.conn is not None:
            with LOCK:
                self.conn.execute("CREATE TABLE IF NOT EXISTS ui_emails (id INTEGER PRIMARY KEY AUTOINCREMENT, ts REAL, "
                                  "email TEXT, result TEXT, sample_id TEXT)")
                self.conn.commit()

    def add(self, email: dict, result: dict, sample_id=None):
        email = {k: email.get(k) for k in ("id", "sender", "subject", "body", "current_due_date")}
        if self.conn is None:
            self.mem.append({"row": len(self.mem) + 1, "ts": time.time(), "email": email, "result": result, "sample_id": sample_id})
            return
        with LOCK:
            self.conn.execute("INSERT INTO ui_emails (ts, email, result, sample_id) VALUES (?,?,?,?)",
                              (time.time(), json.dumps(email), json.dumps(result, default=web.json.default), sample_id))
            self.conn.commit()

    def list(self, limit=200) -> list:
        if self.conn is None:
            rows = self.mem[-limit:]
        else:
            with LOCK:
                cur = self.conn.execute("SELECT * FROM ui_emails ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
            rows = [{"row": r["id"], "ts": r["ts"], "email": json.loads(r["email"]), "result": json.loads(r["result"]),
                     "sample_id": r["sample_id"]} for r in reversed(cur)]
        return rows


EMAILS = EmailLog(_store())


def _email_feed(limit=200) -> list:
    """Newest first. UI-logged emails, plus email_decision audit entries the UI didn't see (e.g. run_float.py)."""
    feed, seen = [], set()
    for r in EMAILS.list(limit):
        res = r["result"] or {}
        parsed = res.get("parsed") or {}
        seen.add(r["email"].get("id"))
        feed.append({"row": r["row"], "ts": r["ts"], "email_id": r["email"].get("id"), "sender": r["email"].get("sender"),
                     "subject": r["email"].get("subject"), "body": r["email"].get("body"), "sample_id": r.get("sample_id"),
                     "extracted": {"client_id": parsed.get("client_id"), "intent": parsed.get("intent"),
                                   "discount_pct": parsed.get("discount_pct"), "new_bank_account": parsed.get("new_bank_account"),
                                   "new_due_date": parsed.get("new_due_date")},
                     "decision": res.get("decision"), "reasons": res.get("reasons") or [], "approval_id": res.get("approval_id"),
                     "partial": False})
    try:
        for a in svc.audit(500):
            d = a.get("details") if isinstance(a.get("details"), dict) else None
            if a.get("event") != "email_decision" or not d or d.get("email_id") in seen:
                continue
            feed.append({"row": None, "ts": a.get("ts"), "email_id": d.get("email_id"), "sender": d.get("sender"), "subject": None,
                         "body": None, "sample_id": None,
                         "extracted": {"client_id": d.get("client"), "intent": d.get("intent"), "discount_pct": None,
                                       "new_bank_account": None, "new_due_date": None},
                         "decision": d.get("decision"), "reasons": d.get("reasons") or [], "approval_id": None,
                         "partial": True, "audit_id": a.get("id")})
    except Exception:
        pass
    feed.sort(key=lambda x: x["ts"] if isinstance(x["ts"], (int, float)) else 0, reverse=True)
    return feed[:limit]


# ---------------------------------------------------------------------------------------------- approvals preview

def _ref(key) -> str:
    parts = str(key or "").split(":")
    return parts[1] if len(parts) > 1 else (parts[0] or "the invoice")


def _approval_preview(a: dict) -> dict:
    """What Approve / Reject WILL do, worked out from the same facts FloatService.decide() uses. Read-only."""
    p, intent = a.get("payload") or {}, a.get("intent") or ""
    client = _clients().get(a.get("client_id"))
    name = client.name if client else (a.get("client_id") or "this client")
    reject = "Rejecting changes nothing. The decision is written to the audit log."
    pol = _policy()
    if intent == "bank_change" and p.get("new_bank_account") and client:
        return {"approve": f"Marks bank account {p['new_bank_account']} as trusted for {name}. Guard accepts it from now on. No money moves.",
                "reject": reject, "kind": "trust_account", "recorded_only": False}
    if intent == "discount_request" and p.get("discount_pct") and client:
        pct = float(p["discount_pct"])
        if not 0 < pct <= pol["max_discount_pct"]:
            return {"approve": f"Recorded only: {pct:g}% is outside 0-{pol['max_discount_pct']}%, so no invoice changes.",
                    "reject": reject, "kind": "record", "recorded_only": True}
        st = _store()
        unpaid = st.unpaid_invoices_for_client(a["client_id"]) if st else []
        if not unpaid:
            return {"approve": f"No unpaid invoice for {name} right now, so nothing would change.",
                    "reject": reject, "kind": "record", "recorded_only": True}
        inv = unpaid[0]
        new = round(inv["amount"] * (1 - pct / 100), 2)
        return {"approve": f"Cancels unpaid invoice {_ref(inv['key'])} (${inv['amount']:,.2f}) in PayPal and re-sends it at ${new:,.2f} ({pct:g}% off).",
                "reject": reject, "kind": "reissue", "recorded_only": False,
                "invoice": {"key": inv["key"], "amount": inv["amount"], "new_amount": new}}
    if intent == "deadline_extension":
        when = f" (asked for {p['new_due_date']})" if p.get("new_due_date") else ""
        return {"approve": f"Recorded only: the due date in PayPal is not changed{when}.", "reject": reject,
                "kind": "record", "recorded_only": True}
    return {"approve": "Recorded only: no money action is taken.", "reject": reject, "kind": "record", "recorded_only": True}


def _enrich_approval(a: dict) -> dict:
    a = dict(a)
    c = _clients().get(a.get("client_id"))
    a["client_name"] = c.name if c else a.get("client_id")
    if a.get("status") == "pending" and "payload" in a:
        a["preview"] = _approval_preview(a)
    return a


def _approval_audit(approval_id):
    try:
        for e in reversed(svc.audit(1000)):
            d = e.get("details") if isinstance(e.get("details"), dict) else {}
            if e.get("event") == "approval_decided" and d.get("approval_id") == approval_id:
                return e.get("id")
    except Exception:
        pass
    return None


def _unresolved_paypal_errors(audit: list) -> list:
    """paypal_error / discount_apply_failed entries with no later entry for the same key.
    Float logs a repeating error once, so 'unresolved' means: no newer PayPal status for that key since the error."""
    open_ = {}
    for e in audit:
        d = e.get("details") if isinstance(e.get("details"), dict) else {}
        k = d.get("key")
        if e.get("event") in ("paypal_error", "discount_apply_failed"):
            open_[k or f"#{e.get('id')}"] = e
        elif k and k in open_ and e.get("event") in ("invoice_status", "payout_sent", "payout_status", "invoice_reissued"):
            open_.pop(k, None)
    return list(open_.values())


# ---------------------------------------------------------------------------------------------- errors / pages

@web.errorhandler(Exception)
def oops(e):
    from werkzeug.exceptions import HTTPException
    if isinstance(e, HTTPException):                       # 404 etc. stay what they are
        return jsonify({"error": e.description}), e.code
    return jsonify({"error": f"{type(e).__name__}: {e}"}), 500


@web.get("/favicon.ico")
def favicon(): return ("", 204)                            # no icon file; stop the browser asking


PAGES = {"dashboard": ("/", "dashboard.html"), "invoices": ("/invoices", "invoices.html"), "inbox": ("/inbox", "inbox.html"),
         "approvals": ("/approvals", "approvals.html"), "audit": ("/audit", "audit.html"),
         "simulate": ("/simulate", "simulate.html"), "settings": ("/settings", "settings.html")}


def _page(name):
    def view():
        return render_template(PAGES[name][1], page=name, mode=_mode_info(), policy=_policy(), v=ASSET_V,
                               owner=os.getenv("FLOAT_OWNER_NAME", "friend"))
    view.__name__ = f"page_{name}"
    return view


for _n, (_path, _tpl) in PAGES.items():
    web.add_url_rule(_path, f"page_{_n}", _page(_n))


@web.get("/classic")
def classic(): return send_file(ROOT / "index.html")       # the previous one-page UI, kept as a fallback


# ---------------------------------------------------------------------------------------------- original API (same shapes)

@web.get("/api/mode")
def mode(): return jsonify(_mode_info())


@web.post("/api/preview")
def preview():
    r = svc.preview(request.json["text"])
    if isinstance(r, dict) and r.get("ok"):
        PREVIEW.clear(); PREVIEW.update(r)
    return jsonify(r)


@web.post("/api/launch")
def launch():
    with LOCK:
        r = svc.launch(float(request.json["amount"]), request.json["deadline"])
    if isinstance(r, dict) and r.get("goal_id") and isinstance(r.get("plan"), dict) and "items" in r["plan"]:
        PLANS[r["goal_id"]] = r["plan"]
    return jsonify(r)


@web.get("/api/tick/<gid>")
def tick(gid):
    with LOCK:
        return jsonify(svc.tick(gid))


@web.post("/api/pay/<path:key>")
def pay(key):
    with LOCK:
        return jsonify(svc.simulate_payment(key))


@web.post("/api/email")
def email():
    e = request.json
    with LOCK:
        r = svc.submit_email(e)
        EMAILS.add(e, r)
    return jsonify(r)


@web.get("/api/approvals")
def approvals():
    status = request.args.get("status", "pending")
    with LOCK:
        rows = svc.approvals(None if status == "all" else status)
        return jsonify([_enrich_approval(a) for a in rows])


@web.post("/api/decide")
def decide():
    aid = request.json["id"]
    with LOCK:
        r = svc.decide(aid, bool(request.json["approve"]))
        if isinstance(r, dict):
            r = {**r, "audit_id": _approval_audit(aid)}
    return jsonify(r)


@web.get("/api/audit")
def audit():
    limit = max(1, min(int(request.args.get("limit", 100)), 2000))
    with LOCK:
        return jsonify(svc.audit(limit))


# ---------------------------------------------------------------------------------------------- new API

@web.get("/api/meta")
def meta():
    with LOCK:
        gids = _goal_ids()
        pending = len(svc.approvals("pending"))
    return jsonify({**_mode_info(), "policy": _policy(), "clients": _client_rows(), "contractors": _contractors(),
                    "goal_ids": gids, "active_goal_id": gids[-1] if gids else None, "pending_approvals": pending,
                    "today": date.today().isoformat()})


@web.get("/api/state/<gid>")
def state(gid):
    with LOCK:
        return jsonify(svc.state(gid) if hasattr(svc, "state") else svc.tick(gid))


@web.get("/api/dashboard")
def dashboard():
    """One call for the dashboard. ?tick=1 also polls PayPal (same as /api/tick) for the active goal."""
    with LOCK:
        gids = _goal_ids()
        gid = request.args.get("goal_id") or (gids[-1] if gids else None)
        launched = bool(gid and gid in gids)
        st, tick_error, plan, plan_source, goal, summary = None, None, None, None, None, None
        if launched:
            try:
                st = svc.tick(gid) if request.args.get("tick") == "1" else (svc.state(gid) if hasattr(svc, "state") else svc.tick(gid))
            except Exception as e:                              # never break the page because PayPal hiccuped
                tick_error = f"{type(e).__name__}"
                st = svc.state(gid) if hasattr(svc, "state") else None
            plan, plan_source = _plan_for(gid)
            goal = _goal_from_id(gid) or {"goal_id": gid}
            summary = (PREVIEW.get("summary") if PREVIEW.get("goal_id") == gid else None) or (_summary_for(plan) if plan else None)
        elif PREVIEW:
            g = PREVIEW.get("goal") or {}
            goal = {"amount": g.get("amount"), "deadline": g.get("deadline"), "deadline_label": g.get("deadline_label"),
                    "goal_id": PREVIEW.get("goal_id"), "raw": g.get("raw")}
            plan, plan_source, summary = PREVIEW.get("plan"), "preview", PREVIEW.get("summary")
        aud = svc.audit(300)
        pending = [_enrich_approval(a) for a in svc.approvals("pending")]
    feed = _email_feed(200)
    counts = {"allow": 0, "needs_approval": 0, "block": 0}
    for f in feed:
        if f["decision"] in counts:
            counts[f["decision"]] += 1
    return jsonify({"mode": _mode_info(), "policy": _policy(), "clients": _client_rows(), "contractors": _contractors(),
                    "today": date.today().isoformat(), "now": time.time(),
                    "goal": goal, "launched": launched, "plan": plan, "plan_source": plan_source, "summary": summary,
                    "state": st, "tick_error": tick_error, "goal_ids": gids,
                    "approvals": {"pending": len(pending), "items": pending},
                    "emails": feed[:60], "guard_counts": counts,
                    "audit": aud[-80:], "paypal_errors": _unresolved_paypal_errors(aud)})


@web.get("/api/emails")
def emails():
    return jsonify(_email_feed(int(request.args.get("limit", 200))))


def _samples() -> list:
    try:
        from app.data import load_inbox
        return load_inbox()
    except Exception:
        return []


FEATURED = {"m06": ("Spoofed sender", "A look-alike billing domain asks to move every payment to a new account."),
            "m04": ("70% discount", "Urgent request for 70% off from a domain that only looks like Acme."),
            "m05": ("Swapped bank account", "A real client address asks to send money to an account not on file."),
            "m03": ("8% discount", "A known client asks for 8% off: inside the hard limit, above the auto limit."),
            "m02": ("Friendly 3% ask", "A known client asks for a small loyalty discount. This one is fine.")}


@web.get("/api/samples")
def samples():
    out = []
    for s in _samples():
        exp = s.get("expected") or {}
        f = FEATURED.get(s["id"])
        out.append({"id": s["id"], "sender": s["sender"], "subject": s.get("subject"), "body": s["body"],
                    "expected_decision": exp.get("decision"), "expected_intent": exp.get("intent"),
                    "expected_client": exp.get("client_id"), "needs_real_llm": bool(s.get("needs_real_llm")),
                    "featured": {"title": f[0], "blurb": f[1], "order": list(FEATURED).index(s["id"])} if f else None})
    return jsonify(out)


@web.post("/api/simulate/email/<sid>")
def simulate_email(sid):
    s = next((x for x in _samples() if x["id"] == sid), None)
    if not s:
        return jsonify({"error": f"No sample email {sid}"}), 404
    e = {"id": f"{sid}-{int(time.time() * 1000) % 10_000_000}", "sender": s["sender"], "subject": s.get("subject", ""),
         "body": s["body"]}
    if s.get("current_due_date"):
        e["current_due_date"] = s["current_due_date"]
    with LOCK:
        r = svc.submit_email(e)
        EMAILS.add(e, r, sample_id=sid)
    exp = (s.get("expected") or {}).get("decision")
    return jsonify({"sample_id": sid, "email": e, "result": r, "expected_decision": exp,
                    "match": exp == (r or {}).get("decision"), "needs_real_llm": bool(s.get("needs_real_llm"))})


_OUTAGE = {"left": 0}


@web.post("/api/simulate/outage")
def simulate_outage():
    """FLOAT_FAKE only. The next N PayPal invoice-status checks raise, so you can watch Float log a paypal_error and
    keep going. Wraps the fake PayPal object in memory; the real PayPal client is never touched."""
    paypal = getattr(svc, "paypal", None)
    if not hasattr(paypal, "mark_paid"):
        return jsonify({"error": "Only available in the offline demo (FLOAT_FAKE=1)."}), 400
    n = max(1, min(int((request.json or {}).get("checks", 6)), 50))
    if not getattr(paypal, "_ui_outage_wrapped", False):
        original = paypal.get_invoice_status

        def flaky(invoice_id):
            if _OUTAGE["left"] > 0:
                _OUTAGE["left"] -= 1
                raise ConnectionError("simulated PayPal outage")
            return original(invoice_id)
        paypal.get_invoice_status = flaky
        paypal._ui_outage_wrapped = True
    _OUTAGE["left"] = n
    return jsonify({"ok": True, "failing_checks": n})


@web.post("/api/simulate/reset")
def simulate_reset():
    global svc, MODE, EMAILS
    if not _fake():
        return jsonify({"error": "Reset is only available in the offline demo (FLOAT_FAKE=1)."}), 400
    with LOCK:
        svc, MODE = make_service()
        EMAILS = EmailLog(_store())
        PLANS.clear(); PREVIEW.clear(); _OUTAGE["left"] = 0
    return jsonify({"ok": True})


if __name__ == "__main__":
    print(f"Floatly UI ({MODE}) -> http://127.0.0.1:{os.getenv('PORT', '5000')}")
    web.run(host=os.getenv("HOST", "127.0.0.1"), port=int(os.getenv("PORT", "5000")), debug=False)
