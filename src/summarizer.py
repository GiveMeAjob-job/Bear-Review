from notion_client import calc_xp


def _build_prompt(header: str, tasks, highlight_period: str, next_period: str) -> str:
    total = len(tasks)
    xp = sum(calc_xp(t) for t in tasks)
    cats = {}
    for t in tasks:
        c = t["properties"]["\u5206\u7c7b"]["select"]["name"]
        cats[c] = cats.get(c, 0) + 1
    cat_lines = ", ".join(f"{k}:{v}" for k, v in cats.items())
    task_titles = "\n".join(
        f"- {t['properties']['\u4efb\u52a1\u540d\u79f0']['title'][0]['plain_text']}"
        for t in tasks
    )
    return (
        f"# {header}\n"
        f"\u5df2\u5b8c\u6210\u4efb\u52a1 {total} \u4e2a\uff0c\u5206\u7c7b\u5206\u5e03\uff1a{cat_lines}\uff0c\u83b7\u5f97 XP {xp}\u3002\n"
        f"## \u4efb\u52a1\u6e05\u5355\n"
        f"{task_titles}\n\n"
        f"\u8bf7\u7528\u4e2d\u6587\u8f93\u51fa\uff1a\n"
        f"1. \u5f52\u7ed3{highlight_period} 3 \u4e2a\u4eae\u70b9\n"
        f"2. 1 \u4e2a\u6700\u5927\u6539\u8fdb\u70b9\n"
        f"3. {next_period} 3 \u6761\u884c\u52a8\u5efa\u8bae\uff08\u4fdd\u6301\u5177\u4f53\u53ef\u6267\u884c\uff09"
    )


def build_daily_prompt(tasks):
    return _build_prompt("Daily Review", tasks, "\u4eca\u5929", "\u660e\u5929")


def build_weekly_prompt(tasks):
    return _build_prompt("Weekly Review", tasks, "\u672c\u5468", "\u4e0b\u5468")


def build_monthly_prompt(tasks):
    return _build_prompt("Monthly Review", tasks, "\u672c\u6708", "\u4e0b\u6708")
