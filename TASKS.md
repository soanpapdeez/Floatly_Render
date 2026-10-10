# Shared Task List

Deadline (verify on Devpost): **Thu Nov 12** | **Feature freeze: Thu Nov 5** | Aim to submit ~Nov 10
A = money side (PayPal, DB, orchestrator) | B = brain side (AI, Guard, planner, UI)
Rule: anything new after Oct 30 goes in "Nice to have", not the build.

## Day 1 - Oct 10-11 (done by pushing this repo)
- [x] Repo, contract, parser + guard + tests, seed data, 15 sample emails
- [ ] Both: confirm exact deadline + required sponsor tools on Devpost
- A [ ] PayPal dev account, sandbox accounts, keys in .env, `python check_paypal.py` prints OK
- B [ ] Run `python run_inbox.py` with a real LLM; fix prompt until 15/15

## Oct 12-13
- A [ ] Create + send an invoice via Invoicing API; read status back
- B [ ] Add 10+ harder emails (typos, mixed intents, injection attempts) to data/inbox.json

## Oct 14-15
- A [ ] Payouts API call works in sandbox
- A [ ] Payment confirmation (webhook via ngrok, or polling) + store state in DB
- B [ ] Planner: goal -> list of {client_id, amount, due_date}

## Oct 16 - MILESTONE (together)
- [ ] One command: goal -> plan -> invoices -> payment -> payout (ugly is fine)

## Oct 17-23
- A [ ] Error handling, retries, idempotency (no double payouts/invoices), audit log
- B [ ] Attack scenario scripted (70% discount + swapped bank account, spoofed sender)
- B [ ] Approval flow (needs_approval -> human approve/reject) + explanation text in UI
- [ ] **Rough demo video recorded by Oct 23 (insurance)**

## Oct 24-30
- A [ ] Extra sponsor tools / integrations
- B [ ] Real UI: plan, invoices, Guard decisions, approvals
- [ ] Full demo dry-run; fix everything that breaks

## Oct 31 - Nov 5 (FREEZE Nov 5)
- A [ ] README, architecture diagram, from-scratch setup test
- B [ ] Demo script (order + timing)
- [ ] Final demo video (together); Devpost write-up drafted
- [ ] **FREEZE - no new features**

## Nov 6-12 - Buffer (bug fixes only)
- [ ] Fresh-machine test: clone, follow README, demo runs
- [ ] Submit by ~Nov 10; confirm Devpost shows submission complete

## Nice to have
- [ ]
