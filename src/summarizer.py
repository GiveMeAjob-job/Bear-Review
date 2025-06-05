# src/summarizer.py - 🔄 增强版
import os
from collections import Counter
from typing import Dict, List, Tuple
from .notion_client import calc_xp
from .utils import setup_logger
from datetime import timedelta

logger = setup_logger(__name__)


class TaskSummarizer:
    def __init__(self, templates_dir: str = "templates"):
        self.templates_dir = templates_dir

    def aggregate_tasks(self, tasks: List[Dict]) -> Tuple[Dict, List[str]]:
        """聚合任务统计信息（含 MIT／偏差／娱乐时长 等）"""
        if not tasks:
            empty = {"total": 0, "xp": 0, "cats": {}, "mit_count": 0,
                     "mit_done": [], "mit_todo": [],
                     "top_bias": [], "ent_minutes": 0}
            return empty, []

        xp_total = 0
        categories = Counter()
        titles = []

        mit_done_titles = []
        mit_todo_titles = []

        bias_list = []  # [(标题, 偏差百分比), …]
        ent_minutes = 0

        for t in tasks:
            p = t["properties"]

            # ① XP
            xp_total += calc_xp(t)

            # ② 分类统计
            cat = p["分类"]["select"]["name"] if p["分类"]["select"] else "未分类"
            categories[cat] += 1

            # ③ 任务标题
            if p["任务名称"]["title"]:
                title = p["任务名称"]["title"][0]["plain_text"]
                titles.append(title)
            else:
                title = "（无标题）"

            # ④ MIT 列表拆分
            pri = p["优先级"]["select"]["name"] if p["优先级"]["select"] else ""
            sta = p["状态"]["select"]["name"] if p["状态"]["select"] else ""
            if pri == "MIT":
                (mit_done_titles if sta == "Done" else mit_todo_titles).append(title)

            # ⑤ 偏差百分比
            try:
                bias_pct = p["偏差%"]["formula"]["string"]
                # 去掉百分号转 float
                if bias_pct not in ("—", ""):
                    bias_list.append((title, abs(float(bias_pct.rstrip("%")))))
            except Exception:
                pass

            # ⑥ 娱乐时长（按分类或标签判断）
            if cat in ("Entertainment", "Fun", "Life"):
                try:
                    ent_minutes += int(p["实际用时(min)"]["formula"]["number"])
                except Exception:
                    pass

        # ⑦ 拿偏差 Top-3
        top_3_bias = sorted(bias_list, key=lambda x: x[1], reverse=True)[:3]

        stats = {
            "total": len(tasks),
            "xp": xp_total,
            "cats": dict(categories),
            "mit_count": len(mit_done_titles),
            "mit_done": mit_done_titles,
            "mit_todo": mit_todo_titles,
            "top_bias": top_3_bias,
            "ent_minutes": ent_minutes,
        }

        logger.info(f"任务聚合完成: 总数 {stats['total']}, XP {stats['xp']}, MIT 完成 {stats['mit_count']}")
        return stats, titles

    def _load_template(self, period: str) -> str:
        """加载提示词模板"""
        template_file = os.path.join(self.templates_dir, f"{period}_prompt.txt")

        if os.path.exists(template_file):
            with open(template_file, 'r', encoding='utf-8') as f:
                return f.read().strip()

        # 默认模板
        return self._get_default_template(period)

    def _get_default_template(self, period: str) -> str:
        """获取默认模板"""
        period_map = {
            "daily": ("今天", "明天", "日"),
            "weekly": ("本周", "下周", "周"),
            "monthly": ("本月", "下月", "月")
        }

        current, next_period, unit = period_map.get(period, ("今天", "明天", "日"))

        return f"""# {period.title()} Review
已完成任务 {{total}} 个，分类分布：{{categories}}，获得 XP {{xp}}，其中 MIT 任务 {{mit_count}} 个。

## 任务清单
{{task_list}}

请用中文输出，要求简洁实用：
1. **{current}亮点** - 总结 3 个主要成就
2. **改进空间** - 指出 1 个最需要优化的方面  
3. **{next_period}行动** - 提供 3 条具体可执行的建议

注意：回复字数控制在 300 字以内，重点突出可操作性。"""

    def build_prompt(self, stats: Dict, titles: List[str], period: str) -> str:
        """构建AI提示词"""
        template = self._load_template(period)

        # 格式化分类分布
        if stats["cats"]:
            categories = ", ".join(f"{k}:{v}" for k, v in stats["cats"].items())
        else:
            categories = "无"

        # 格式化任务列表
        if titles:
            task_list = "\n".join(f"- {title}" for title in titles[:20])  # 限制显示前20个
            if len(titles) > 20:
                task_list += f"\n... 还有 {len(titles) - 20} 个任务"
        else:
            task_list = "无已完成任务"

        prompt = template.format(
            focus_goal = self.config.focus_goal,
            total=stats["total"],
            xp=stats["xp"],
            categories=categories,
            mit_count=stats["mit_count"],
            task_list=task_list
        )

        logger.info(f"生成 {period} 提示词，长度: {len(prompt)} 字符")
        return prompt