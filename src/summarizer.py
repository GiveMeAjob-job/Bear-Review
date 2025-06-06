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

        earliest_start = None
        latest_end     = None

        for t in tasks:
            p = t["properties"]

            # 0 开始结束时间
            plan = p["计划日期"]["date"]
            start_iso = plan["start"]
            end_iso   = plan.get("end") or start_iso   # 若无 end 用 start

            start_dt = datetime.fromisoformat(start_iso.replace('Z', '+00:00'))
            end_dt   = datetime.fromisoformat(end_iso.replace('Z', '+00:00'))

            earliest_start = start_dt if earliest_start is None else min(earliest_start, start_dt)
            latest_end     = end_dt   if latest_end   is None else max(latest_end,   end_dt)

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
            "start_time": earliest_start.strftime("%H:%M") if earliest_start else "—",
            "end_time": latest_end.strftime("%H:%M") if latest_end else "—",
            "focus_span": str(latest_end - earliest_start) if earliest_start and latest_end else "—",
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
# Daily Review
- 工作区间：{{start_time}} - {{end_time}}（共 {{focus_span}}）
- 已完成任务 {total} 个，分类分布：{categories}，获得 XP {xp}，其中 MIT 任务 {mit_count} 个。


## 任务清单
{task_list}

每日确保：
健康：吃维生素C，维生素D，酸奶，鱼油，咖啡，补锌，午觉（补觉），喝咖啡，锻炼至少30分钟
学习：学习最少4个小时
MIT事件：最少完成3个MIT事件，检查是否为重复，比如完成D333 Quiz 50题，你可以作为一个MIT事件，但是如果3个都是一样的D333 Quiz 50题，那就算作一个MIT事件

现阶段任务：（根据数字前后区分重要级别，越前面重要级别越高）
1.WGU 的D333 Ethics in Technology 的 Final Exam，Gemini Quiz
2.BQ四周练习计划
3.CPA课程系统
4.Youtube Shorts的短视频制作

请用专业的中文输出（控制在550字内）：
1. *今日完成的活动与总体任务相关性** - 告诉我哪些是相关的，一共花了多少时间，哪些是不相关的。
2. **改进空间** - 1个最需要优化的方面，具体可操作
3. **明日行动** - 3条具体建议，优先级明确

要求：语言积极正面，重点突出可执行性，避免空洞表述。"""

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
            total=stats["total"],
            xp=stats["xp"],
            categories=categories,
            mit_count=stats["mit_count"],
            task_list=task_list
            start_time = stats["start_time"],
            end_time = stats["end_time"],
            focus_span = stats["focus_span"],
        )

        logger.info(f"生成 {period} 提示词，长度: {len(prompt)} 字符")
        return prompt