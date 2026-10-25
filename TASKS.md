# Status and schedule (deadline: Thu 12 Nov 2026, 3:00 PM EST = Fri 13 Nov 1:30 AM IST. We submit Tue 10 Nov.)

## Done and tested offline
Email extractor, Guard, goal parser, planner (with date-shifted seed data), orchestrator (idempotent invoices and
payouts), approvals that take effect, audit log, Zapier notification hook, fake PayPal, `run_float.py simulate`.

## Still to prove or build
| What | Owner | Due |
|---|---|---|
| Real sandbox end-to-end run (issue, pay, check, payout, check again) with screenshots | teammate | now |
| `cancel_invoice` and `get_payout_status` verified against the sandbox | teammate | now |
| UI wired to `FloatService` (see the docstring in `app/service.py`) | teammate | Wed 28 Oct |
| `FLOAT_FAKE=1` so judges can run it with no keys | teammate | Wed 28 Oct |
| Hosted demo URL (Render) | teammate | Thu 29 Oct |
| Zap for `ZAPIER_WEBHOOK_URL`, AG Grid tables | teammate | Sat 31 Oct |
| Groq checks: `ask`, `run_inbox.py` x3, new red-team emails | Tanisha | Mon 26 Oct |
| README TODOs, fresh-clone test | Tanisha | Fri 30 Oct |
| **Feature freeze** | both | **Sun 1 Nov** |
| Record and upload the video (YouTube, public) | both | Mon 2 - Fri 6 Nov |
| Final Devpost text, repo public, license visible, hosted URL check | both | Sat 7 - Mon 9 Nov |
| **Submit** | both | **Tue 10 Nov** |

## Rules that must never break
1. PayPal is the only source of truth for "paid". 2. Amounts and dates never come from email text.
3. Every PayPal action is idempotent. 4. Sandbox only. 5. No secret is ever committed.