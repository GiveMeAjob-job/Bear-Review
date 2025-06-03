import argparse
import os

from step1_fetch import fetch_tasks
from step2_aggregate import calc_stats
from step3_prompt import build_prompt, ask_summary
from step4_output import write_to_console

parser = argparse.ArgumentParser()
parser.add_argument(
    "--period",
    choices=["daily", "weekly", "monthly"],
    required=True,
)
args = parser.parse_args()

db_id = os.getenv("NOTION_DB_ID")

tasks = fetch_tasks(args.period, db_id)
stats, titles = calc_stats(tasks)

if args.period == "daily":
    prompt = build_prompt(stats, titles, "Daily Review", "\u4eca\u5929", "\u660e\u5929")
elif args.period == "weekly":
    prompt = build_prompt(stats, titles, "Weekly Review", "\u672c\u5468", "\u4e0b\u5468")
elif args.period == "monthly":
    prompt = build_prompt(stats, titles, "Monthly Review", "\u672c\u6708", "\u4e0b\u6708")
else:
    raise ValueError("Unsupported period")

summary = ask_summary(prompt)
write_to_console(summary)
