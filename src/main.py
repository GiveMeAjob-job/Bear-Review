import argparse
import os
import notion_client
import summarizer
import llm_client

parser = argparse.ArgumentParser()
parser.add_argument("--period", choices=["daily", "weekly", "monthly"], required=True)
args = parser.parse_args()

db_id = os.getenv("NOTION_DB_ID")

if args.period == "daily":
    tasks = notion_client.query_today_tasks(db_id)
    prompt = summarizer.build_daily_prompt(tasks)
elif args.period == "weekly":
    tasks = notion_client.query_this_week_tasks(db_id)
    prompt = summarizer.build_weekly_prompt(tasks)
elif args.period == "monthly":
    tasks = notion_client.query_this_month_tasks(db_id)
    prompt = summarizer.build_monthly_prompt(tasks)
else:
    raise ValueError("Unsupported period")

answer = llm_client.ask_llm(prompt)
print(answer)
