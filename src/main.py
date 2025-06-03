# src/main.py
import argparse, notion_client, summarizer, llm_client, os

parser = argparse.ArgumentParser()
parser.add_argument("--period", choices=["daily","weekly","monthly"])
args = parser.parse_args()

db_id = os.getenv("NOTION_DB_ID")

if args.period == "daily":
    tasks = notion_client.query_today_tasks(db_id)
    prompt = summarizer.build_daily_prompt(tasks)
    answer = llm_client.ask_llm(prompt)
    print(answer)                     # 后续可写回 Notion / 发邮件
