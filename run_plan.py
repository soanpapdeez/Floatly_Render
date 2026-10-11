"""Demo of the planner: python run_plan.py [goal] [deadline]"""
import json
import sys
from app.models import Client
from app.planner import load_open_invoices, make_plan, format_plan

goal = float(sys.argv[1]) if len(sys.argv) > 1 else 6000
deadline = sys.argv[2] if len(sys.argv) > 2 else "2026-10-16"

with open("data/clients.json", encoding="utf-8") as f:
    clients = {row["client_id"]: Client(**row) for row in json.load(f)}

plan = make_plan(goal, deadline, load_open_invoices(), clients)
print(format_plan(plan))