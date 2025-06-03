import argparse
import os
import notion_client
import summarizer
import llm_client



def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--period", choices=["daily", "weekly", "monthly"], required=True)
    args = parser.parse_args()

    db_id = os.getenv("NOTION_DB_ID")
    if args.period == "daily":
        tasks = notion_client.query_today_tasks(db_id)
        header, highlight, next_p = "Daily Review", "\u4eca\u5929", "\u660e\u5929"
    elif args.period == "weekly":
        tasks = notion_client.query_this_week_tasks(db_id)
        header, highlight, next_p = "Weekly Review", "\u672c\u5468", "\u4e0b\u5468"
    else:  # monthly
        tasks = notion_client.query_this_month_tasks(db_id)
        header, highlight, next_p = "Monthly Review", "\u672c\u6708", "\u4e0b\u6708"

    stats, titles = summarizer.aggregate_tasks(tasks)
    prompt = summarizer.build_prompt(stats, titles, header, highlight, next_p)
    summary = llm_client.ask_llm(prompt)
    print(summary)


if __name__ == "__main__":
    main()

