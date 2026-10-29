# Floatly: Float + Guard

**A cash-flow agent for freelancers that can't be tricked into giving your money away.**

Built for the PayPal AI Hackathon 2026: PayPal Invoicing + Payouts (sandbox) + AI.

- Live demo (offline mode, no keys needed): <RENDER_URL>
- Video (3 min): <YOUTUBE_URL>

## The problem

Freelancers and small shops don't just get paid late, they get squeezed: rent and contractor payments are due
Friday, but the client's money arrives next Thursday. Big companies have a finance team for that gap.

The obvious fix is an AI agent that chases clients and moves money. But an agent that reads client emails is an
attack surface. One reply like "my bank details changed, send it here" or "per our call, take 70% off" can trick a
naive agent into giving money away.

## What it does

- **Float**: you type a goal ("I need $6,000 by Friday"). Float estimates when each open invoice will really be
  paid from the client's payment history, and only where you are still short does it offer the cheapest early-pay
  discount. Every choice comes with a plain-language reason. It sends invoices through **PayPal Invoicing**,
  watches PayPal for payment, and pays contractors through **PayPal Payouts** only after client money has cleared.
- **Guard**: every client email goes through a safety layer before anything happens. The AI only *reads* the email
  into a small structured request. A **deterministic rules engine (no AI)** decides: `allow`, `needs_approval`
  or `block`. Spoofed senders, huge discounts and swapped bank accounts are stopped.
- **Approvals**: anything uncertain lands in the owner's inbox for one tap. Approving a discount cancels the
  client's unpaid invoice and re-sends it at the lower amount. Approving a bank change makes that account trusted
  for that client. Rejecting changes nothing. The owner sees exactly what happened, and every decision and its
  effect is written to the audit log. Zapier emails the owner when something needs attention.

Safety does not depend on the model being right. If the AI misreads an attack, the worst case is "ask a human".

## How AI is used

| Where | What the AI does | What checks it |
|---|---|---|
| Client email -> structured request | Extracts intent, discount %, bank account, due date | Schema validation (fails closed to "other") + Guard rules |
| Goal text -> amount + deadline | Reads the amount | A rule-based reader must agree, otherwise we refuse and ask |
| Plan -> summary | Writes a short explanation | Every `$` figure must exist in the plan, otherwise a template is used |

Model: `openai/gpt-oss-120b` on Groq through an OpenAI-compatible API (any compatible model works).
With no key (`LLM_PROVIDER=mock`), a rule-based mock keeps everything runnable offline.

## Architecture

```
owner goal --> goal_parser (AI + rule check) --> planner --> orchestrator
                                                                | create + send invoice (idempotent)
client email --> extractor (AI) --> Guard (rules, no AI) -------+--> PayPal Invoicing
                     allow / needs_approval / block             | poll status (PayPal = truth)
                                |                               v
                         approvals inbox                 PayPal Payouts (only after money cleared)
                                |
     SQLite audit log <-- every decision + effect --> Zapier webhook --> owner's email

Web UI: ui/server.py (Flask) --> app/service.py (FloatService) --> everything above
```

Rules the code enforces:
1. PayPal is the only source of truth for "paid". An email can never mark an invoice paid.
2. Amounts and due dates come from our records and PayPal, never from email text.
3. Every PayPal action is idempotent: invoices are keyed in the store, payouts carry a fixed request id, so
   re-running never double-sends or double-pays.
4. Outgoing discounts and payouts respect Guard's limits; anything above goes to a human.
5. Every decision is written to the audit log with its reason.

Polling is crash-safe: if a PayPal call fails, it is logged as `paypal_error` and retried on the next check.
Repeating states (a payout waiting for money, the same error) are logged once, not on every check.

Guard policy (tunable at the top of `app/guard.py`): discounts above 10% are blocked, 5-10% need approval,
unknown senders are blocked, unknown bank accounts need approval, due-date extensions over 30 days need approval,
payouts over 2000 need approval.

## Built with

- **PayPal Developer Platform (sandbox)**: Invoicing API (create, send, status, cancel) and Payouts API
  (idempotent request ids, payout status).
- **Groq**: fast `gpt-oss-120b` inference for reading emails and goals.
- **Zapier**: a Catch Hook -> Gmail zap tells the owner when an approval is needed or an attack is blocked.
- **AG Grid**: the invoice table in the dashboard.
- **Render**: hosts the offline demo so anyone can try it without keys.
- Python 3.12, Flask, SQLite.

## Run it (Windows PowerShell; macOS/Linux in comments)

```powershell
py -3.12 -m venv .venv
.venv\Scripts\activate                # source .venv/bin/activate
pip install -r requirements.txt
copy .env.example .env                # cp .env.example .env

python -m pytest -q                   # all tests pass, no keys needed
python run_float.py simulate          # the whole story offline with a fake PayPal
python run_float.py ask "I need $6,000 in 4 days"
```

The seed invoices in `data/open_invoices.json` are shifted to the current date when the app loads them, so the
demo always shows a cash gap and a discount offer.

### Two modes

| Mode | How | URL |
|---|---|---|
| Offline demo (fake PayPal, no keys) | `FLOAT_FAKE=1` in `.env` (the default in `.env.example`), then `python ui/server.py`. To run it next to the real mode: `$env:FLOAT_FAKE="1"; $env:PORT="5001"; python ui/server.py` | http://localhost:5000 (or 5001) |
| Real PayPal sandbox | Fill the PayPal variables, set `FLOAT_FAKE=0` in `.env`, then `python ui/server.py` | http://localhost:5000 |

Real sandbox setup: create a free sandbox business and personal account at developer.paypal.com, create an app,
and fill the PayPal variables below. `python check_paypal.py` confirms the credentials work. Command-line flow:
`python run_float.py issue`, pay a few invoices from the sandbox personal account, then `python run_float.py check`
and `python run_float.py audit`. The project refuses to run unless `PAYPAL_MODE=sandbox`.

### Environment variables (names only; `.env` is never committed)

| Name | Purpose |
|---|---|
| `FLOAT_FAKE` | `1` = fake PayPal, no keys (default); `0` = real sandbox |
| `PORT` | Web server port (default 5000) |
| `LLM_PROVIDER` | `mock` (no key) or `openai` (any OpenAI-compatible API, e.g. Groq) |
| `OPENAI_BASE_URL`, `OPENAI_API_KEY`, `LLM_MODEL` | LLM endpoint, key and model |
| `EXTRACTOR_DEBUG` | `1` prints extractor details while testing |
| `PAYPAL_MODE` | Must be `sandbox` |
| `PAYPAL_CLIENT_ID`, `PAYPAL_CLIENT_SECRET`, `PAYPAL_BUSINESS_EMAIL` | Sandbox app and business account |
| `DEMO_PAYER_EMAIL` | Sandbox personal account that receives and pays every invoice |
| `DEMO_CONTRACTOR_EMAIL` | Sandbox personal account that receives every contractor payout |
| `DEMO_AMOUNT_SCALE` | Multiplies amounts sent to PayPal (default `1`) |
| `ZAPIER_WEBHOOK_URL` | Optional owner notifications |

### Sandbox amount scaling

`DEMO_AMOUNT_SCALE` multiplies every amount sent to PayPal, for example `0.01` turns a $3,500 invoice into $35 in
the sandbox, so the full story runs even with a small sandbox balance. The plan, Guard limits, the dashboard and the
audit log all keep the real (unscaled) amounts. Default `1` = no scaling.

### Hosted demo

Render runs `gunicorn ui.server:web` with `FLOAT_FAKE=1`; secrets live only in Render's environment variables.
The free instance sleeps when idle (first load can take about a minute) and its demo data resets on restart.

## Honest limitations

- Sandbox only. A production version would need real sender authentication (SPF/DKIM/DMARC), compliance review,
  conservative spending caps and human-in-the-loop defaults.
- The open invoices and client payment histories are seeded demo data.
- The plan reports a best case (all offers accepted) and any shortfall. It does not claim an acceptance rate.
- Approving a deadline extension is recorded only; approving a discount or a bank change takes effect.
- Payment status is checked by polling PayPal, not by PayPal webhooks.
- A failed or returned contractor payout is recorded but not retried automatically; the owner handles it in PayPal.
- The AI's reading of an email can vary between runs; Guard's rules are deterministic, and the sample inbox is
  re-run to check results stay the same.
- Amounts are treated as USD (the sandbox currency).

## License

MIT, see [LICENSE.md](LICENSE.md).