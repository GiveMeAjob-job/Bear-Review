# src/summarizer.py - 🔄 增强版
import os
from collections import Counter
from typing import Dict, List, Tuple
from .notion_client import calc_xp
from .utils import setup_logger
from datetime import datetime, timedelta
from pytz import timezone

logger = setup_logger(__name__)


class TaskSummarizer:
    def __init__(self, templates_dir: str = "templates", tz_str: str = "America/Toronto"):
        self.templates_dir = templates_dir
        self.tz = timezone(tz_str) # 存储时区信息

    def aggregate_tasks(self, tasks: List[Dict]) -> Tuple[Dict, List[Dict]]:
        """
        聚合任务统计信息。
        返回 stats 字典和包含详细信息的 task_details 列表。
        """
        if not tasks:
            # ... (空任务处理不变)
            return {}, []

        xp_total = 0
        categories = Counter()

        # ✅ 我们将返回一个包含详细信息的列表，而不仅仅是标题
        task_details = []

        for t in tasks:
            p = t["properties"]

            # --- 提取任务的详细信息 ---
            title = p.get("任务名称", {}).get("title", [{}])[0].get("plain_text", "（无标题）")
            cat = p.get("分类", {}).get("select", {}).get("name", "未分类")
            xp = calc_xp(t)
            is_mit = p.get("优先级", {}).get("select", {}).get("name", "") == "MIT"

            # --- 时间和时长提取 ---
            start_str, end_str, actual_minutes_str = "N/A", "N/A", "0"
            actual_minutes = 0

            # 1. 直接获取“实际用时(min)”
            formula_prop = p.get("实际用时(min)", {}).get("formula", {})
            if formula_prop.get("number") is not None:
                actual_minutes = formula_prop["number"]
                actual_minutes_str = f"{actual_minutes:.0f}分钟"

            # 2. 获取开始和结束时间（用于显示）
            date_prop = p.get("计划日期", {}).get("date", {})
            start_iso = date_prop.get("start")
            end_iso = date_prop.get("end")
            if start_iso:
                try:
                    start_dt_local = datetime.fromisoformat(start_iso.replace('Z', '+00:00')).astimezone(self.tz)
                    start_str = start_dt_local.strftime('%H:%M')
                    if end_iso:
                        end_dt_local = datetime.fromisoformat(end_iso.replace('Z', '+00:00')).astimezone(self.tz)
                        end_str = end_dt_local.strftime('%H:%M')
                    else:
                        end_str = start_str
                except Exception:
                    pass

            task_details.append({
                "title": title,
                "category": cat,
                "start_time": start_str,
                "end_time": end_str,
                "duration_min": actual_minutes,
                "xp": xp,
                "is_mit": is_mit
            })

            # --- 累加统计 ---
            xp_total += xp
            categories[cat] += 1

        # --- 聚合总体统计数据 ---
        all_start_times = [datetime.strptime(t['start_time'], '%H:%M') for t in task_details if
                           t['start_time'] != 'N/A']
        all_end_times = [datetime.strptime(t['end_time'], '%H:%M') for t in task_details if t['end_time'] != 'N/A']

        work_start_str, work_end_str, focus_span_str = "无", "无", "无"
        if all_start_times and all_end_times:
            earliest_start = min(all_start_times)
            latest_end = max(all_end_times)
            work_start_str = earliest_start.strftime("%H:%M")
            work_end_str = latest_end.strftime("%H:%M")
            focus_span_hours = (latest_end - earliest_start).total_seconds() / 3600
            focus_span_str = f"{focus_span_hours:.1f}小时"

        total_actual_hours = sum(t['duration_min'] for t in task_details) / 60

        stats = {
            "total": len(tasks),
            "xp": xp_total,
            "cats": dict(categories),
            "mit_count": sum(1 for t in task_details if t['is_mit']),
            "work_start": work_start_str,
            "work_end": work_end_str,
            "work_hours": round(total_actual_hours, 1),
            "focus_span": focus_span_str,
        }

        return stats, task_details

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

    def build_prompt(self, stats: Dict, task_details: List[Dict], period: str) -> str:
        """构建AI提示词"""
        template = self._load_template(period)

        # 格式化分类分布
        if stats["cats"]:
            categories = ", ".join(f"{k}:{v}" for k, v in stats["cats"].items())
        else:
            categories = "无"

        # ✅ 格式化包含详细信息的任务列表
        task_list_lines = []
        if task_details:
            # 按分类分组
            tasks_by_cat = {}
            for task in task_details:
                cat = task['category']
                if cat not in tasks_by_cat:
                    tasks_by_cat[cat] = []
                tasks_by_cat[cat].append(task)

            for cat, tasks_in_cat in tasks_by_cat.items():
                task_list_lines.append(f"【{cat}】")
                for task in tasks_in_cat:
                    duration_str = f"{task['duration_min']:.0f}分钟"
                    time_str = f"{task['start_time']}-{task['end_time']}"
                    mit_str = " (MIT)" if task['is_mit'] else ""
                    task_list_lines.append(f"- {task['title']}{mit_str} | {time_str} | 用时: {duration_str}")

        task_list = "\n".join(task_list_lines) if task_list_lines else "无已完成任务"

        # 使用 format 替换所有占位符
        prompt = template.format(
            total=stats.get("total", 0),
            xp=stats.get("xp", 0),
            categories=categories,
            mit_count=stats.get("mit_count", 0),
            task_list=task_list,
            start_time=stats.get("work_start", "无"),
            end_time=stats.get("work_end", "无"),
            focus_span=stats.get("focus_span", "无")
        )

        logger.info(f"生成 {period} 提示词，长度: {len(prompt)} 字符")
        return prompt

    # src/summarizer.py - 添加三天分析方法

    def build_three_day_prompt(self, three_days_stats: Dict[str, Dict]) -> str:
        """构建准确的三天趋势分析提示词"""

        sorted_dates = sorted(three_days_stats.keys())
        weekdays = ['周一', '周二', '周三', '周四', '周五', '周六', '周日']

        days_summary = []

        # 三天总计
        total_tasks = 0
        total_work_hours = 0
        total_sleep_hours = 0
        total_entertainment_hours = 0
        total_xp = 0
        total_mit = 0

        for date_str in sorted_dates:
            stats = three_days_stats[date_str]
            date_obj = datetime.fromisoformat(date_str)
            weekday = weekdays[date_obj.weekday()]

            # 累计
            total_tasks += stats['total']
            total_work_hours += stats.get('actual_work_hours', 0)
            total_sleep_hours += stats.get('sleep_hours', 0)
            total_entertainment_hours += stats.get('entertainment_hours', 0)
            total_xp += stats['xp']
            total_mit += stats['mit_count']

            # 单日摘要
            day_summary = f"""
    【{date_str} {weekday}】
    • 完成任务：{stats['total']}个
    • 工作时段：{stats.get('work_start', '无')} - {stats.get('work_end', '无')}
    • 实际工作：{stats.get('actual_work_hours', 0)}小时（不含睡眠）
    • 睡眠时间：{stats.get('sleep_hours', 0)}小时
    • 娱乐时间：{stats.get('entertainment_hours', 0)}小时
    • 获得XP：{stats['xp']}点
    • MIT完成：{stats['mit_count']}个
    • 效率指标：{stats.get('xp_per_hour', 0)} XP/小时"""

            days_summary.append(day_summary)

        # 计算平均值
        avg_work = total_work_hours / 3
        avg_sleep = total_sleep_hours / 3
        avg_entertainment = total_entertainment_hours / 3

        prompt = f"""基于以下三天的真实数据，请进行分析（已排除睡眠时间）：

    {''.join(days_summary)}

    【三天汇总】
    • 总任务数：{total_tasks}个
    • 总工作时间：{total_work_hours:.1f}小时（日均{avg_work:.1f}小时）
    • 总睡眠时间：{total_sleep_hours:.1f}小时（日均{avg_sleep:.1f}小时）
    • 总娱乐时间：{total_entertainment_hours:.1f}小时（日均{avg_entertainment:.1f}小时）
    • MIT完成：{total_mit}个

    请用专业的中文分析（不使用markdown，600字内）：

    1. 时间管理评估（150字）
       - 每日实际工作时长是否合理（考虑已排除睡眠）
       - 工作、睡眠、娱乐的时间分配是否平衡
       - 作息规律性评价

    2. 效率分析（150字）
       - XP/小时的效率指标变化
       - MIT任务完成情况
       - 高效时段识别

    3. 问题诊断（150字）
       - 娱乐时间是否过多
       - 睡眠是否充足
       - 工作时段是否过于分散

    4. 改进建议（150字）
       - 基于实际数据的具体建议
       - 时间分配优化方案
       - 提升效率的具体措施

    注意：所有时间统计已经排除睡眠，请基于实际工作时间分析。"""

        return prompt


def aggregate_tasks(self, tasks: List[Dict]) -> Tuple[Dict, List[str]]:
    """聚合任务统计信息（修复并简化时间计算）"""
    if not tasks:
        # ... (空任务处理不变)
        empty = {
            "total": 0, "xp": 0, "cats": {}, "mit_count": 0,
            "work_start": "无", "work_end": "无", "work_hours": 0,
            "focus_span": "无", "time_distribution": {}
        }
        return empty, []

    xp_total = 0
    categories = Counter()
    titles = []
    mit_done_titles = []

    # --- 时间计算变量 ---
    all_start_times = []
    all_end_times = []
    total_duration_minutes = 0
    hour_distribution = Counter()

    for t in tasks:
        p = t["properties"]

        # --- 时间信息处理 ---
        if "计划日期" in p and p["计划日期"].get("date"):
            plan = p["计划日期"]["date"]
            start_iso = plan.get("start")
            end_iso = plan.get("end", start_iso)

            if start_iso:
                try:
                    start_dt = datetime.fromisoformat(start_iso.replace('Z', '+00:00'))
                    end_dt = datetime.fromisoformat(end_iso.replace('Z', '+00:00')) if end_iso else start_dt

                    all_start_times.append(start_dt)
                    all_end_times.append(end_dt)

                    duration = (end_dt - start_dt).total_seconds()
                    total_duration_minutes += duration / 60

                    hour_distribution[start_dt.astimezone(timezone('UTC')).hour] += 1

                except Exception as e:
                    logger.warning(f"时间解析错误: {e}")

        # --- 其他统计 (XP, 分类, 标题等) ---
        xp_total += calc_xp(t)
        cat = p.get("分类", {}).get("select", {}).get("name", "未分类")
        categories[cat] += 1
        title = p.get("任务名称", {}).get("title", [{}])[0].get("plain_text", "（无标题）")
        titles.append(title)
        if p.get("优先级", {}).get("select", {}).get("name", "") == "MIT":
            mit_done_titles.append(title)

    # --- 聚合时间计算结果 ---
    work_start_str = "无"
    work_end_str = "无"
    focus_span_str = "无"

    if all_start_times and all_end_times:
        # 找到最早的开始和最晚的结束
        earliest_start = min(all_start_times)
        latest_end = max(all_end_times)

        # 格式化开始和结束时间
        # 注意：这里可以根据需要转换为本地时区，但为保持简单，先用UTC时间
        tz = timezone("America/Toronto")  # 建议从config传入
        work_start_str = earliest_start.astimezone(tz).strftime("%H:%M")
        work_end_str = latest_end.astimezone(tz).strftime("%H:%M")

        # 计算总时间跨度
        focus_span_seconds = (latest_end - earliest_start).total_seconds()
        span_hours = focus_span_seconds / 3600
        focus_span_str = f"{span_hours:.1f} 小时"

    # --- 准备最终的统计字典 ---
    stats = {
        "total": len(tasks),
        "xp": xp_total,
        "cats": dict(categories),
        "mit_count": len(mit_done_titles),
        "mit_done": mit_done_titles,
        "work_start": work_start_str,
        "work_end": work_end_str,
        "work_hours": round(total_duration_minutes / 60, 1),  # 这是所有任务时长的累加，更准确
        "focus_span": focus_span_str,  # 这是从最早开始到最晚结束的总跨度
        "time_distribution": dict(hour_distribution),
    }

    logger.info(f"任务聚合完成: 总数 {stats['total']}, 工作时段 {stats['work_start']}-{stats['work_end']}")
    logger.info(f"总时长: {stats['work_hours']}小时, 总跨度: {stats['focus_span']}")
    return stats, titles


def _merge_overlapping_periods(self, periods: List[Tuple[datetime, datetime]]) -> List[Tuple[datetime, datetime]]:
    """合并重叠的时间段"""
    if not periods:
        return []

    # 按开始时间排序
    sorted_periods = sorted(periods, key=lambda x: x[0])
    merged = [sorted_periods[0]]

    for current_start, current_end in sorted_periods[1:]:
        last_start, last_end = merged[-1]

        # 如果当前时段与上一个时段重叠或相邻
        if current_start <= last_end:
            # 合并时段
            merged[-1] = (last_start, max(last_end, current_end))
        else:
            # 添加新时段
            merged.append((current_start, current_end))

    return merged


def _empty_stats(self) -> Dict:
    """返回空统计"""
    return {
        "total": 0, "xp": 0, "cats": {}, "mit_count": 0,
        "mit_done": [], "work_start": "无", "work_end": "无",
        "actual_work_hours": 0, "productive_hours": 0,
        "sleep_hours": 0, "entertainment_hours": 0,
        "tasks_per_hour": 0, "xp_per_hour": 0
    }