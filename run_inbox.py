"""Run every sample email through extract -> guard and compare with expected labels.
   python run_inbox.py                      (uses LLM_PROVIDER from .env, default mock)
   LLM_PROVIDER=anthropic python run_inbox.py
"""
import os
import sys
from app.data import load_clients, load_inbox
from app.llm import get_llm
from app.pipeline import process_email


def main() -> int:
    provider = os.getenv("LLM_PROVIDER", "mock")
    llm, clients, inbox = get_llm(), load_clients(), load_inbox()
    print(f"Provider: {provider}\n")
    ok = {"client": 0, "intent": 0, "decision": 0}
    for e in inbox:
        r = process_email(e, clients, llm)
        exp = e["expected"]
        c_ok = r.parsed.client_id == exp["client_id"]
        i_ok = r.parsed.intent == exp["intent"]
        d_ok = r.decision.decision == exp["decision"]
        ok["client"] += c_ok; ok["intent"] += i_ok; ok["decision"] += d_ok
        flag = "OK " if (c_ok and i_ok and d_ok) else "BAD"
        print(f"[{flag}] {e['id']}  {str(r.parsed.client_id):<11} {r.parsed.intent:<21} "
              f"{r.decision.decision:<15} {'; '.join(r.decision.reasons)}")
        if flag == "BAD":
            print(f"        expected: {exp}")
    n = len(inbox)
    print(f"\nclient {ok['client']}/{n}  intent {ok['intent']}/{n}  decision {ok['decision']}/{n}")
    return 0 if all(v == n for v in ok.values()) else 1


if __name__ == "__main__":
    sys.exit(main())
