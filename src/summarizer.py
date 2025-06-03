# src/summarizer.py
def build_daily_prompt(tasks):
    total = len(tasks)
    xp = sum(calc_xp(t) for t in tasks)
    cats = {}
    for t in tasks:
        c = t["properties"]["分类"]["select"]["name"]
        cats[c] = cats.get(c, 0) + 1
    cat_lines = ", ".join(f"{k}:{v}" for k,v in cats.items())
    task_titles = "\n".join(f"- {t['properties']['任务名称']['title'][0]['plain_text']}"
                            for t in tasks)

    return f"""# Daily Review
已完成任务 {total} 个，分类分布：{cat_lines}，获得 XP {xp}。
## 任务清单
{task_titles}

请用中文输出：
1. 归纳今天 3 个亮点
2. 1 个最大改进点
3. 明天 3 条行动建议（保持具体可执行）"""
