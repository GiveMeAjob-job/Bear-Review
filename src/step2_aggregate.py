from collections import Counter
from notion_client import calc_xp


def calc_stats(tasks):
    """Calculate XP and category counts from tasks."""
    xp = sum(calc_xp(t) for t in tasks)
    cats = Counter(
        t["properties"]["\u5206\u7c7b"]["select"]["name"] for t in tasks
    )
    titles = [
        t["properties"]["\u4efb\u52a1\u540d\u79f0"]["title"][0]["plain_text"]
        for t in tasks
    ]
    stats = {
        "total": len(tasks),
        "xp": xp,
        "cats": cats,
    }
    return stats, titles
