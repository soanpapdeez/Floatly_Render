"""Floatly UI server. From the repo root:  pip install flask  then  python ui/server.py
  default            -> app.service.build_service(fake=True)  (offline, no keys); falls back to the stand-in
  FLOAT_REAL=1       -> app.service.build_service()           (real PayPal sandbox)
  UI_STANDIN=1       -> built-in sample service (use until app/service.py is pushed)
"""
import dataclasses, os, re, sys, time
from pathlib import Path
from flask import Flask, jsonify, request, send_file

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
        return [a for a in s.appr if a["status"] == status]

    def decide(s, aid, approve):
        a = next(x for x in s.appr if x["id"] == aid)
        a["status"] = "approved" if approve else "rejected"; s._a("approval", f"#{aid} {a['status']}")
        return a

    def audit(s, n=100):
        return s.log[:n]


def make_service():
    if os.getenv("UI_STANDIN") != "1":
        try:
            import app  # noqa: F401  (loads .env)
            from app.service import build_service
            real = os.getenv("FLOAT_REAL") == "1"
            return build_service() if real else build_service(fake=True), ("Sandbox" if real else "Demo mode")
        except Exception as e:  # service.py missing or broken
            print(f"[ui] using the stand-in service ({type(e).__name__}: {e})")
    return StandIn(), "Sample data"


svc, MODE = make_service()
web = Flask(__name__)
web.json.default = lambda o: dataclasses.asdict(o) if dataclasses.is_dataclass(o) else (sorted(o) if isinstance(o, set) else getattr(o, "__dict__", str(o)))


@web.errorhandler(Exception)
def oops(e):
    return jsonify({"error": f"{type(e).__name__}: {e}"}), 500


@web.get("/")
def home(): return send_file(ROOT / "index.html")
@web.get("/api/mode")
def mode(): return jsonify({"mode": MODE})
@web.post("/api/preview")
def preview(): return jsonify(svc.preview(request.json["text"]))
@web.post("/api/launch")
def launch(): return jsonify(svc.launch(float(request.json["amount"]), request.json["deadline"]))
@web.get("/api/tick/<gid>")
def tick(gid): return jsonify(svc.tick(gid))
@web.post("/api/pay/<key>")
def pay(key): return jsonify(svc.simulate_payment(key))
@web.post("/api/email")
def email(): return jsonify(svc.submit_email(request.json))
@web.get("/api/approvals")
def approvals(): return jsonify(svc.approvals(request.args.get("status", "pending")))
@web.post("/api/decide")
def decide(): return jsonify(svc.decide(request.json["id"], bool(request.json["approve"])))
@web.get("/api/audit")
def audit(): return jsonify(svc.audit(100))


if __name__ == "__main__":
    print(f"Floatly UI ({MODE}) -> http://127.0.0.1:5000")
    web.run(port=5000, debug=False)