"""Demo of the planner (no keys needed).
   python run_plan.py [goal] [deadline YYYY-MM-DD]
Defaults: $6,000 in 4 days. The seed invoices are shifted so they always look current."""
import json
import sys
from datetime import date, timedelta

from app.models import Client
from app.planner import format_plan, load_open_invoices, make_plan

goal = float(sys.argv[1]) if len(sys.argv) > 1 else 6000
deadline = sys.argv[2] if len(sys.argv) > 2 else (date.today() + timedelta(days=4)).isoformat()

with open("data/clients.json", encoding="utf-8") as f:
    clients = {row["client_id"]: Client(**row) for row in json.load(f)}

plan = make_plan(goal, deadline, load_open_invoices(today=date.today()), clients)
print(format_plan(plan))