# Float + Guard UI redesign

Dark, soft, rounded UI on Flask + Jinja + static CSS + vanilla ES modules. There is no build step. AG Grid and Manrope come from pinned CDN tags. All charts and the hero are hand-written SVG.

Guard, planner, orchestrator and PayPal code are **unchanged**. Only `ui/` was touched, plus this doc. All 108 existing tests still pass.

## 1. Mapping: your data/endpoint → component

| Data / endpoint | Component |
|---|---|
| `/api/mode` (`MODE`, `DEMO_AMOUNT_SCALE`) | Mode badge (top bar, goal strip, Settings) and the scale note banner |
| `app/guard.py` constants (via `/api/meta`, page context) | Guard Inbox "Policy" card, Settings → Guard policy, zone limits in the Guard activity chart |
| `/api/preview` → `goal`, `plan`, `summary` | "Ask Float" command bar, goal strip, AI plan card (summary + CTA), Preview banner |
| `/api/launch` | "Run plan" CTA on the AI plan card |
| `/api/tick/<gid>` (via `/api/dashboard?tick=1`) | Polling for the dashboard and invoices, "Check PayPal now" buttons |
| `plan.items[].expected_pay_date`, `cash_if_paid`, `discount_pct`, `reason` | Cash by deadline bars, Cash runway pins, Projected balance chart, Invoices grid (predicted date, offer, reason tooltip) |
| `plan.expected_on_track / best_case / shortfall / total_discount_cost` | Cash by deadline number, hero badge, shortfall gap marker, "Short $X" pill, Invoices summary |
| `clients[].payment_history[].days_late` + `planner.expected_days_late` | Payment-delay dot/range chart |
| `state.invoices` (`status`, `paypal_invoice_id`, `amount`, `discount_pct`) | Invoices grid status pills ("Paid · confirmed by PayPal"), stat tiles, ice pins with checks |
| `state.payouts` + `contractors.json` | White payout pins, "Payouts released" tile, Simulate → Payments |
| `/api/email` → `parsed` + `decision` + `reasons` | Guard Inbox rows (Extracted request \| Guard decision), Guard activity capsules, coral hero pins |
| `/api/approvals` (+ new `preview`) | Approvals cards ("If you approve / If you reject"), amber hero pins, sidebar badge, bell dot |
| `/api/decide` → `effect`, `effect_details` (+ new `audit_id`) | Post-click effect box with "View audit entry #id" |
| `/api/audit` (all events incl. `paypal_error`, `payout_waiting`) | Activity timeline (dashboard), Audit Log screen, PayPal error alerts |
| `data/inbox.json` (`expected`, `needs_real_llm`) | Simulate: featured attacks + full sample table with expected vs actual |

## 2. New or changed endpoints (`ui/server.py`)

The original routes keep their shapes. Changes only **add** fields:

- `GET /api/mode` now returns `{mode, badge, fake, sample, amount_scale, scale_note, llm_provider, can_simulate_payment, can_simulate_outage, poll_seconds}`. `mode` is unchanged.
- `GET /api/approvals?status=all` returns every approval (it used to return nothing). Each pending item gains `client_name` and `preview`.
- `POST /api/decide` adds `audit_id`.
- `POST /api/email` returns the same response, and also stores the email plus its extraction for the Guard Inbox.
- `GET /api/audit?limit=N` accepts a limit (default 100).
- `POST /api/preview` returns the same response, and is remembered for the dashboard.

New routes:

```text
GET  /api/meta                    mode + policy + clients + contractors + goal_ids + pending count
GET  /api/dashboard?tick=1&goal_id=   one call for the dashboard (tick=1 polls PayPal)
GET  /api/state/<gid>             svc.state(gid) without calling PayPal
GET  /api/emails?limit=200        Guard Inbox feed
GET  /api/samples                 data/inbox.json with expected verdicts
POST /api/simulate/email/<id>     run one sample email through extractor -> Guard
POST /api/simulate/outage         FLOAT_FAKE only: next N status checks raise (body {"checks": 6})
POST /api/simulate/reset          FLOAT_FAKE only: fresh in-memory demo
GET  / /invoices /inbox /approvals /audit /simulate /settings    pages
GET  /classic                     the previous one-page UI
```

Examples:

```json
// GET /api/approvals  (one pending item)
{"id": 2, "client_id": "zenlabs", "client_name": "ZenLabs", "intent": "discount_request", "status": "pending",
 "payload": {"discount_pct": 8.0, "sender": "finance@zenlabs.in", "new_bank_account": null, "new_due_date": null},
 "reasons": ["Discount 8% is above 5% and needs human approval."],
 "preview": {"approve": "Cancels unpaid invoice OPEN-003 ($2,000.00) in PayPal and re-sends it at $1,840.00 (8% off).",
             "reject": "Rejecting changes nothing. The decision is written to the audit log.",
             "kind": "reissue", "recorded_only": false,
             "invoice": {"key": "goal-2026-11-06-6000:OPEN-003", "amount": 2000.0, "new_amount": 1840.0}}}

// GET /api/emails  (one row)
{"row": 3, "ts": 1793891746.8, "email_id": "m04-2869601", "sender": "billing@acme-pay.com", "subject": "URGENT",
 "body": "…", "sample_id": "m04",
 "extracted": {"client_id": "acme", "intent": "discount_request", "discount_pct": 70.0, "new_bank_account": null, "new_due_date": null},
 "decision": "block",
 "reasons": ["Sender billing@acme-pay.com is not a known email for Acme (possible spoofing).", "Requested discount 70% exceeds the 10% limit."],
 "approval_id": null, "partial": false}

// POST /api/simulate/email/m05
{"sample_id": "m05", "expected_decision": "needs_approval", "match": true, "needs_real_llm": false,
 "result": {"decision": "needs_approval", "approval_id": 1, "reasons": ["New bank account is not on file; …"], "parsed": {…}}}

// GET /api/dashboard  (top-level keys)
{"mode": {…}, "policy": {…}, "clients": [{"client_id": "acme", "name": "Acme", "history_days_late": [0, 2, 0], "expected_days_late": 1, …}],
 "contractors": […], "today": "2026-11-05", "now": 1793891746.8,
 "goal": {"amount": 6000.0, "deadline": "2026-11-06", "deadline_label": "Friday, 6 Nov 2026", "goal_id": "goal-2026-11-06-6000"},
 "launched": true, "plan": {…plan.to_dict()…}, "plan_source": "launch", "summary": {"text": "…", "source": "template"},
 "state": {"invoices": […], "payouts": […], "totals": {…}}, "tick_error": null, "goal_ids": […],
 "approvals": {"pending": 2, "items": […]}, "emails": […], "guard_counts": {"allow": 2, "needs_approval": 3, "block": 3},
 "audit": […last 80…], "paypal_errors": […unresolved paypal_error / discount_apply_failed entries…]}
```

Notes:
- The Guard Inbox keeps each email with its extracted fields in a `ui_emails` table, in the same SQLite file as the rest of the data. The audit log only stores intent and decision. Emails that reached the audit log some other way (for example via `run_float.py`) still show up, marked "audit only".
- The approval preview is read-only and mirrors `FloatService.decide()`: bank change → trust the account; discount → cancel the newest unpaid invoice and re-send it; anything else → recorded only.
- The outage simulator wraps the **fake** PayPal object in memory. The real `paypal_client` module is never touched.

## 3. File tree

```text
ui/
  server.py                      routes + new read-only endpoints (StandIn kept)
  index.html                     previous UI, served at /classic
  templates/
    base.html                    shell: sidebar, top bar (greeting, pill sub-nav, Ask Float, mode badge, theme, bell, avatar)
    dashboard.html  invoices.html  inbox.html  approvals.html  audit.html  simulate.html  settings.html
    partials/_icons.html         inline SVG icon sprite
    partials/_sidebar.html       nav + pending badge
    partials/_top_actions.html   command bar, mode badge, theme toggle, bell, avatar
    partials/_macros.html        card_header, skeleton, subnav
  static/css/
    tokens.css                   every colour/size/motion token (+ slate-teal canvas theme)
    base.css                     reset, canvas, app container, layout grid, responsive rules
    components.css               cards, pills, buttons, charts, timeline, inbox, approvals, AG Grid theme, states, motion
  static/js/
    api.js                       fetch client + no-overlap poller (pauses in hidden tabs, backs off on errors)
    util.js                      DOM/format/motion/toast/tooltip/storage helpers
    shell.js                     sliding sub-nav, theme toggle, Ask Float, pending badge
    derive.js                    /api/dashboard payload -> chart-ready view model
    events.js                    audit event -> human title / tone / key-value
    timeline.js                  vertical timeline renderer
    mock.js                      sample payload fallback (clearly labelled)
    hero-runway.js               isometric contour "Cash runway"
    charts/svg.js  bars.js  dots.js  capsules.js  area.js
    pages/dashboard.js  invoices.js  inbox.js  approvals.js  audit.js  simulate.js  settings.js
```

## 5. Run and test

```bash
pip install -r requirements.txt
FLOAT_FAKE=1 python ui/server.py            # http://127.0.0.1:5000  (no keys, no network except CDN font/grid)
# Render / production-like:
FLOAT_FAKE=1 gunicorn ui.server:web
```

Optional environment variables: `FLOAT_OWNER_NAME=Asha` (the greeting) and `UI_POLL_SECONDS=6`.

Demo script for judges:
1. **Simulate → Run all five.** You get Spoofed sender and 70% discount → Block, Swapped bank account and 8% discount → Needs approval, Friendly 3% → Allow.
2. **Guard Inbox.** Each row shows the AI's extracted request beside the rule that fired.
3. **Approvals.** Read "If you approve", then press Approve. The effect and a link to its audit entry appear.
4. **Dashboard → type "I need $6,000 by Friday" → Run plan.**
5. **Invoices** (or Simulate → Payments) → **Client pays.** The next PayPal check confirms it, and payouts are released from cleared money.
6. **Simulate → PayPal outage.** A `paypal_error` alert appears and the app keeps running.

Checks run for this redesign: `pytest` (108 passed), every page loaded in headless Chromium at desktop width with no console errors (dashboard also at 1000 and 390 px), gunicorn serving pages, static files and the API, and the `UI_STANDIN=1` fallback.

Gunicorn caveat: in `FLOAT_FAKE=1` the database is `:memory:`, so run a single worker (the gunicorn default). Extra workers would each have their own demo state.

## 6. Next improvements

- **Server-sent events** instead of polling, so a "paid" from PayPal shows up instantly.
- **Expose the extraction on the audit entry** (`email_decision` could include `discount_pct`, `new_bank_account`, `new_due_date`). That would replace the `ui_emails` table, but it is an orchestrator change, so it was left alone.
- **Plan snapshot in the store** (`plan_created` could carry the items), so a restarted sandbox server doesn't need to recompute the plan.
- **Payout approval cards** for payouts held above $2,000 (`payout_held` is shown in the audit log, but `decide()` has no payout path yet).
- **Pin clustering and zoom** on the runway when a goal has more than about 10 invoices.
- **Vendor AG Grid and Manrope** into `ui/static/vendor/`, so the hosted demo has no CDN dependency at all.
- **Playwright smoke test** in CI that loads every page in `FLOAT_FAKE=1` and fails on console errors.
