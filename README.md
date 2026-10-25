# Floatly

**A CFO for freelancers that can't be tricked into giving your money away.**

Built for the PayPal AI Hackathon 2026 (PayPal Invoicing + Payouts in the sandbox, plus AI).

## The problem

Freelancers and small shops don't just get paid late, they get squeezed: rent and contractor payments are due
Friday, but the client's money arrives next Thursday. Big companies have a finance team for that gap.

The obvious fix is an AI agent that chases clients and moves money. But an agent that reads client emails is an
attack surface. One reply like "my bank details changed, send it here" or "per our call, take 70% off" can trick a
naive agent into giving money away.

## What Floatly does

- **Float**: you type a goal ("I need $6,000 in 4 days"). Float estimates when each open invoice will really be
  paid from the client's payment history, and only where you are still short does it offer the cheapest early-pay
  discount. Every choice comes with a plain-language reason. It sends the invoices through **PayPal Invoicing**,
  watches PayPal for payment, and pays contractors through **PayPal Payouts** once the money has arrived.
- **Guard**: every client email goes through a safety layer before anything happens. The AI only *reads* the email
  into a small structured request. A **deterministic rules engine (no AI)** decides: `allow`, `needs_approval`
  or `block`. Spoofed senders, huge discounts and swapped bank accounts are stopped.
- **Approvals**: anything uncertain lands in the owner's inbox for one tap. Approving a discount cancels the
  client's unpaid invoice and re-sends it at the lower amount. Approving a bank change makes that account trusted
  for that client. Every decision and its effect is written to the audit log.

Safety does not depend on the model being right. If the AI misreads an attack, the worst case is "send to a human".

## How AI is used

| Where | What the AI does | What checks it |
|---|---|---|
| Client email -> structured request | Extracts intent, discount %, bank account, due date | Schema validation (fails closed to "other") + Guard rules |
| Goal text -> amount + deadline | Reads the amount | A rule-based reader must agree, otherwise we refuse and ask |
| Plan -> summary | Writes a short explanation | Every `$` figure must exist in the plan, otherwise a template is used |

Model used: `openai/gpt-oss-120b` on Groq's free tier through an OpenAI-compatible API (any compatible model works).
With no key, a rule-based mock keeps everything runnable offline.

## Architecture

```
goal text -> goal_parser -> planner -> orchestrator -> PayPal Invoicing (create + send)
                                            |                     |
client email -> extractor (AI) -> Guard     +-- poll PayPal status +-> PayPal Payouts (contractors)
                  (rules)  -> allow / needs_approval / block
                                |
                    approvals inbox -> owner decides -> reissue invoice / trust account
                                |
                  SQLite: invoices, payouts, approvals, audit log
```

Rules the code enforces:
1. PayPal is the only source of truth for "paid". An email can never mark an invoice paid.
2. Amounts and due dates come from our records and PayPal, never from email text.
3. Every PayPal action is idempotent: invoices are keyed in the store, payouts carry a fixed request id, so
   re-running never double-sends or double-pays.
4. Outgoing discounts and payouts respect Guard's limits; anything above goes to a human.
5. Every decision is written to the audit log with its reason.

Guard policy (tunable at the top of `app/guard.py`): discounts above 10% are blocked, 5-10% need approval,
unknown senders are blocked, unknown bank accounts need approval, due-date extensions over 30 days need approval,
payouts over 2000 need approval.

## Tools used

- **PayPal Developer Platform (sandbox)**: Invoicing API (create, send, status, cancel) and Payouts API
  (idempotent request ids, batch status).
- **AI**: Groq-hosted `gpt-oss-120b` via the OpenAI-compatible API.
- **Zapier** (optional): a webhook tells the owner when an approval is needed or an attack is blocked.
  Set `ZAPIER_WEBHOOK_URL` to enable it.
- Python, SQLite.
<!-- TODO before submitting: add Render / AG Grid / any other sponsor ONLY if it is really integrated -->

## Run it

```
python -m venv .venv
.venv\Scripts\activate            # macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
copy .env.example .env            # macOS/Linux: cp .env.example .env

python -m pytest                  # all tests pass, no keys needed
python run_float.py simulate      # the whole story offline with a fake PayPal
python run_float.py ask "I need $6,000 in 4 days"
```

The seed invoices in `data/open_invoices.json` are shifted to the current date when the app loads them, so the
demo always looks current.

Web UI (no keys needed when `FLOAT_FAKE=1` in `.env`):

```
python ui/server.py
```
<!-- TODO: confirm this is how ui/server.py is started, and that FLOAT_FAKE=1 really selects the fake PayPal -->

Real PayPal sandbox: create a free sandbox business and personal account at developer.paypal.com, create an app,
and fill `PAYPAL_CLIENT_ID`, `PAYPAL_CLIENT_SECRET`, `PAYPAL_BUSINESS_EMAIL`, `DEMO_PAYER_EMAIL` in `.env`
and set `FLOAT_FAKE=0`. Then `python run_float.py issue`, pay a few invoices from the sandbox personal account,
and `python run_float.py check`. The project refuses to run unless `PAYPAL_MODE=sandbox`.

## Honest limitations

- Sandbox only. A production version would need real sender authentication (SPF/DKIM), compliance review,
  conservative spending caps and human-in-the-loop defaults.
- The open invoices and client payment histories are seeded demo data.
- The plan reports a best case (all offers accepted) and any shortfall. It does not claim an acceptance rate.
- Approving a deadline extension is recorded only; approving a discount or a bank change takes effect.
- Amounts are treated as USD (the sandbox currency).

## License

MIT, see `LICENSE.md`.