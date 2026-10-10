# PayPal AI Hackathon - Guarded Invoice & Payout Agent

An agent that runs one flow: **goal -> plan -> invoices -> payment -> payout**, while a rule-based
**Guard** stops risky client requests (e.g. a spoofed 70% discount, a swapped bank account).

- **AI** only reads a client's message and extracts a small structured request.
- **Guard** is deterministic rules (no AI) that decides: `allow`, `needs_approval`, or `block`, with plain-language reasons.
- **PayPal Sandbox** APIs (Invoicing, Payouts) move the (fake) money.

## Setup (5 min)
```bash
python -m venv .venv && source .venv/bin/activate     # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env                                   # Windows: copy .env.example .env
python -m pytest                                       # 30 tests should pass
python run_inbox.py                                    # 15 sample emails -> decisions
```
Works with no API key (`LLM_PROVIDER=mock`). For a real model set `LLM_PROVIDER=anthropic` (or `openai`),
add the key in `.env`, `pip install anthropic` (or `openai`), and re-run `python run_inbox.py`.
**The mock is for plumbing only - judge the parser on a real model.**

## The contract (change only if you both agree)
```
ParsedRequest  {client_id, intent, discount_pct, new_bank_account, new_due_date, raw_message}
   intent in: discount_request | bank_change | deadline_extension | payment_confirmation | other
Decision       {decision: allow | needs_approval | block, reasons: [plain-language strings]}
Plan item      {client_id, amount, due_date}                      (Person B builds the planner)
Pipeline       process_email(email, clients, call_llm) -> Result(email_id, parsed, decision)
```

## Layout
```
app/models.py         shared data contract
app/extractor.py      prompt + validation (fails closed to intent "other")
app/guard.py          the rules + tunable thresholds at top
app/pipeline.py       email -> extract -> resolve client -> guard
app/llm.py            mock | anthropic | openai adapter
app/paypal_client.py  sandbox auth (A builds Invoicing/Payouts here)
data/clients.json     6 seeded clients w/ payment history
data/inbox.json       15 sample emails with expected results (incl. the attack)
tests/                30 tests;   run_inbox.py = end-to-end demo of the brain
```

## Day 1 split
**Person A:** create PayPal developer account -> Sandbox -> make a business + personal sandbox account ->
create a REST app and copy Client ID/Secret into `.env` -> run `python check_paypal.py` until it prints OK.
**Person B:** run `python run_inbox.py` with a real model, fix the prompt in `extractor.py` until all 15 emails pass,
add more tricky emails to `data/inbox.json`.
Together: agree this contract, confirm the deadline and sponsor-tool requirements on Devpost.

## Rules
- Sandbox only. `paypal_client.py` refuses to run unless `PAYPAL_MODE=sandbox`.
- Never commit `.env`. Commit small and often; keep `main` always runnable.
