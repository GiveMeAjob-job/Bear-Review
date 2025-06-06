# src/summarizer.py - 🔄 增强版
import os
from collections import Counter
from typing import Dict, List, Tuple
from .notion_client import calc_xp
from .utils import setup_logger
from datetime import datetime

logger = setup_logger(__name__)


class TaskSummarizer:
    def __init__(self, templates_dir: str = "templates"):
        self.templates_dir = templates_dir

    def aggregate_tasks(self, tasks: List[Dict]) -> Tuple[Dict, List[str]]:
        """聚合任务统计信息（含 MIT／偏差／娱乐时长 等）"""
        if not tasks:
            empty = {
                "total": 0, "xp": 0, "cats": {}, "mit_count": 0,
                "mit_done": [], "mit_todo": [],
                "top_bias": [], "ent_minutes": 0,
                "start_time": "无", "end_time": "无", "focus_span": "无"
            }
            return empty, []

        xp_total = 0
        categories = Counter()
        titles = []

        mit_done_titles = []
        mit_todo_titles = []

        bias_list = []  # [(标题, 偏差百分比), …]
        ent_minutes = 0

        earliest_start = None
        latest_end = None

        for t in tasks:
            p = t["properties"]

            # 获取计划日期信息
            if "计划日期" in p and p["计划日期"].get("date"):
                plan = p["计划日期"]["date"]
                start_iso = plan.get("start")
                end_iso = plan.get("end", start_iso)  # 如果没有结束时间，使用开始时间

                if start_iso:
                    try:
                        # 处理时区信息
                        start_iso_clean = start_iso.replace('Z', '+00:00')
                        start_dt = datetime.fromisoformat(start_iso_clean)

                        # 更新最早开始时间
                        if earliest_start is None or start_dt < earliest_start:
                            earliest_start = start_dt

                        # 如果有结束时间
                        if end_iso:
                            end_iso_clean = end_iso.replace('Z', '+00:00')
                            end_dt = datetime.fromisoformat(end_iso_clean)

                            # 更新最晚结束时间
                            if latest_end is None or end_dt > latest_end:
                                latest_end = end_dt
                        else:
                            # 如果没有结束时间，假设任务持续1小时
                            if latest_end is None or start_dt > latest_end:
                                latest_end = start_dt

                    except Exception as e:
                        logger.warning(f"处理日期时出错: {e}, 任务ID: {t.get('id', 'unknown')}")

            # ① XP
            xp_total += calc_xp(t)

            # ② 分类统计
            cat = p.get("分类", {}).get("select", {}).get("name", "未分类")
            categories[cat] += 1

            # ③ 任务标题
            title = "（无标题）"
            if p.get("任务名称", {}).get("title"):
                title = p["任务名称"]["title"][0].get("plain_text", "（无标题）")
            titles.append(title)

            # ④ MIT 列表拆分
            pri = p.get("优先级", {}).get("select", {}).get("name", "")
            sta = p.get("状态", {}).get("select", {}).get("name", "")
            if pri == "MIT":
                if sta == "Done":
                    mit_done_titles.append(title)
                else:
                    mit_todo_titles.append(title)

            # ⑤ 偏差百分比
            try:
                bias_formula = p.get("偏差%", {}).get("formula", {})
                if bias_formula:
                    bias_pct = bias_formula.get("string", "")
                    if bias_pct and bias_pct not in ("—", ""):
                        bias_value = abs(float(bias_pct.rstrip("%")))
                        bias_list.append((title, bias_value))
            except Exception:
                pass

            # ⑥ 娱乐时长（按分类或标签判断）
            if cat in ("Entertainment", "Fun", "Life"):
                try:
                    actual_time = p.get("实际用时(min)", {}).get("formula", {}).get("number", 0)
                    if actual_time:
                        ent_minutes += int(actual_time)
                except Exception:
                    pass

        # ⑦ 拿偏差 Top-3
        top_3_bias = sorted(bias_list, key=lambda x: x[1], reverse=True)[:3]

        # 计算时间信息
        start_time_str = "无"
        end_time_str = "无"
        focus_span_str = "无"

        if earliest_start and latest_end:
            # 格式化时间为 HH:MM
            start_time_str = earliest_start.strftime("%H:%M")
            end_time_str = latest_end.strftime("%H:%M")

            # 计算时间跨度
            time_diff = latest_end - earliest_start
            hours = int(time_diff.total_seconds() // 3600)
            minutes = int((time_diff.total_seconds() % 3600) // 60)

            if hours > 0:
                focus_span_str = f"{hours}小时{minutes}分钟"
            else:
                focus_span_str = f"{minutes}分钟"

        stats = {
            "start_time": start_time_str,
            "end_time": end_time_str,
            "focus_span": focus_span_str,
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
        logger.info(f"时间范围: {stats['start_time']} - {stats['end_time']} (共{stats['focus_span']})")

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
        return """# Daily Review
- 工作区间：{start_time} - {end_time}（共 {focus_span}）
- 已完成任务 {total} 个，分类分布：{categories}，获得 XP {xp}，其中 MIT 任务 {mit_count} 个。

## 任务清单
{task_list}

## 每日确保：
健康：吃维生素C，维生素D，酸奶，鱼油，咖啡，补锌，午觉（补觉），喝咖啡，锻炼至少30分钟
学习：学习最少4个小时
MIT事件：最少完成3个MIT事件，检查是否为重复，比如完成D333 Quiz 50题，你可以作为一个MIT事件，但是如果3个都是一样的D333 Quiz 50题，那就算作一个MIT事件

## 现阶段任务：（根据数字前后区分重要级别，越前面重要级别越高）
1.WGU 的D333 Ethics in Technology 的 Final Exam，Gemini Quiz
2.BQ四周练习计划
3.CPA课程系统
4.Youtube Shorts的短视频制作

## 请用专业的中文输出（控制在550字内）：
1. 列出今日完成的各个类别在今日的占比，和占比对应的占比大头的事情和时间。
2. 今日完成的活动与总体任务相关性 - 告诉我哪些是相关的，一共花了多少时间，哪些是不相关的。
3. 改进空间 - 3个最需要优化的方面，具体可操作
4. 明日行动 - 3条具体建议，优先级明确。优化策略，明日执行蓝图。

要求：语言积极正面，重点突出可执行性，避免空洞表述。不要使用markdown格式的加粗（**）、斜体（*）等标记。"""

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

        # 使用 format 替换所有占位符
        prompt = template.format(
            total=stats["total"],
            xp=stats["xp"],
            categories=categories,
            mit_count=stats["mit_count"],
            task_list=task_list,
            start_time=stats["start_time"],
            end_time=stats["end_time"],
            focus_span=stats["focus_span"]
        )

        logger.info(f"生成 {period} 提示词，长度: {len(prompt)} 字符")
        return prompt

    # src/summarizer.py - 添加三天分析方法

    def build_three_day_prompt(self, three_days_stats: Dict[str, Dict]) -> str:
        """构建三天趋势分析的提示词"""

        # 按日期排序（从早到晚）
        sorted_dates = sorted(three_days_stats.keys())

        days_summary = []
        weekdays = ['周一', '周二', '周三', '周四', '周五', '周六', '周日']

        # 总计数据
        total_tasks = 0
        total_xp = 0
        total_mit = 0
        category_totals = {}

        for date_str in sorted_dates:
            stats = three_days_stats[date_str]
            date_obj = datetime.fromisoformat(date_str)
            weekday = weekdays[date_obj.weekday()]

            # 累计统计
            total_tasks += stats['total']
            total_xp += stats['xp']
            total_mit += stats['mit_count']

            # 分类统计
            for cat, count in stats['cats'].items():
                category_totals[cat] = category_totals.get(cat, 0) + count

            # 格式化单日摘要
            cats_str = "、".join(f"{k}({v})" for k, v in stats['cats'].items()) if stats['cats'] else "无"

            day_summary = f"""
    {date_str} {weekday}
    • 完成任务：{stats['total']}个
    • 获得XP：{stats['xp']}点
    • MIT任务：{stats['mit_count']}个
    • 分类分布：{cats_str}
    • 工作时段：{stats['start_time']} - {stats['end_time']}"""

            days_summary.append(day_summary)

        # 格式化分类总计
        cat_total_str = "、".join(
            f"{k}({v})" for k, v in sorted(category_totals.items(), key=lambda x: x[1], reverse=True))

        prompt = f"""基于以下三天的任务完成数据，请进行深度分析和趋势识别：

    【三天数据概览】
    {''.join(days_summary)}

    【三天汇总】
    • 总任务数：{total_tasks}个（日均{total_tasks / 3:.1f}个）
    • 总XP值：{total_xp}点（日均{total_xp / 3:.1f}点）
    • MIT完成：{total_mit}个（日均{total_mit / 3:.1f}个）
    • 分类总计：{cat_total_str}

    请用专业的中文输出，不使用任何markdown格式（控制在600字内）：

    1. 趋势分析（150字）
       - 任务数量的变化趋势（增长/下降/波动）
       - 工作强度的变化（通过XP和MIT判断）
       - 作息时间的规律性

    2. 行为模式识别（150字）
       - 哪些任务类别是重点（根据数量和频率）
       - MIT任务的完成规律
       - 效率高峰期识别

    3. 问题诊断（150字）
       - 发现的效率瓶颈或问题
       - 任务分配是否合理
       - 可能的改进空间

    4. 明日行动建议（150字）
       - 基于三天趋势的具体建议
       - 需要重点关注的任务类别
       - 时间安排优化建议

    要求：
    - 分析要具体，引用实际数据
    - 建议要可执行，避免泛泛而谈
    - 语气积极正面，focus on improvements"""

        return prompt