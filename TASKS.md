# Status (updated Thu 29 Oct 2026)
Deadline: Thu 12 Nov 2026, 3:00 PM EST = Fri 13 Nov 1:30 AM IST. **We submit Tue 10 Nov.**

## Done
Extractor + Guard, goal parser, planner, orchestrator, approvals, audit log, real sandbox run (issue, pay, check,
payout, check again, no double payouts), cancel_invoice + get_payout_status verified, UI wired and redesigned,
FLOAT_FAKE switch, Render hosted demo, Zapier zap, LICENSE.md.

Thu 29 Oct:
- Seed due dates relative to today (test proves a cash gap and a discount offer)
- payout_waiting / payout_held logged only when they change; "$" amounts in audit text
- PayPal polling crash-safe (paypal_error in the audit log, retried next check); final payout states complete
- decide() returns a plain-language effect (raw result in effect_details); UI hint corrected
- Plan and payout tables on AG Grid (plain-table fallback kept); demo chip for the 8% approval
- check_paypal.py no longer prints part of the token; README rewritten
- 108 tests pass

## Before feature freeze (Sun 1 Nov)
| What | Owner | Status |
|---|---|---|
| "(GOAL COVERED" bracket | | |
| 12 red-team emails (m39-m50) + run_inbox.py x3 on Groq | Tanisha | |
| Fresh-clone test | Tanisha | |
| Secrets scan of git history; rotate keys if needed | both | |
| UI redesign (optional; must be final before recording) | both | |
| Render + Zap check after last push | teammate | |
| **Feature freeze** | both | **Sun 1 Nov** |

## After freeze
| What | Owner | Due |
|---|---|---|
| Record + upload video (YouTube, public) | both | Mon 2 - Fri 6 Nov |
| README: fill demo URL + video URL | both | Sat 7 Nov |
| Repo public, LICENSE visible, hosted URL check | both | Sat 7 - Mon 9 Nov |
| Devpost draft complete | both | Mon 9 Nov |
| **Submit** | both | **Tue 10 Nov** |

## Rules that must never break
1. PayPal is the only source of truth for "paid". 2. Amounts and dates never come from email text.
3. Every PayPal action is idempotent. 4. Sandbox only. 5. No secret is ever committed or printed.