import os
import datetime
import requests

TOKEN = os.getenv("NOTION_TOKEN")
HEADERS = {
    "Authorization": f"Bearer {TOKEN}",
    "Notion-Version": "2022-06-28",
    "Content-Type": "application/json",
}


def _query_tasks(db_id: str, start: datetime.date, end: datetime.date):
    payload = {
        "filter": {
            "and": [
                {
                    "property": "\u8ba1\u5212\u65e5\u671f",
                    "date": {
                        "on_or_after": start.isoformat(),
                    },
                },
                {
                    "property": "\u8ba1\u5212\u65e5\u671f",
                    "date": {
                        "on_or_before": end.isoformat(),
                    },
                },
                {
                    "property": "\u72b6\u6001",
                    "select": {"equals": "Done"},
                },
            ]
        }
    }
    r = requests.post(
        f"https://api.notion.com/v1/databases/{db_id}/query",
        headers=HEADERS,
        json=payload,
    )
    r.raise_for_status()
    return r.json().get("results", [])


def query_today_tasks(db_id: str):
    today = datetime.date.today()
    return _query_tasks(db_id, today, today)


def query_this_week_tasks(db_id: str):
    today = datetime.date.today()
    start = today - datetime.timedelta(days=today.weekday())
    end = start + datetime.timedelta(days=6)
    return _query_tasks(db_id, start, end)


def query_this_month_tasks(db_id: str):
    today = datetime.date.today()
    start = today.replace(day=1)
    if start.month == 12:
        next_month = datetime.date(start.year + 1, 1, 1)
    else:
        next_month = datetime.date(start.year, start.month + 1, 1)
    end = next_month - datetime.timedelta(days=1)
    return _query_tasks(db_id, start, end)


def calc_xp(page):
    pri = (
        page.get("properties", {})
        .get("\u4f18\u5148\u7ea7", {})
        .get("select", {})
        .get("name")
    )
    return 10 if pri == "MIT" else 5
