import os
from notion_client import (
    query_today_tasks,
    query_this_week_tasks,
    query_this_month_tasks,
)


def fetch_tasks(period: str, db_id: str):
    """Return tasks from Notion for the given period."""
    if period == "daily":
        return query_today_tasks(db_id)
    elif period == "weekly":
        return query_this_week_tasks(db_id)
    elif period == "monthly":
        return query_this_month_tasks(db_id)
    else:
        raise ValueError(f"Unknown period: {period}")
