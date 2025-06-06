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
    def __init__(self, templates_dir: str = "templates"):
        self.templates_dir = templates_dir

    def aggregate_tasks(self, tasks: List[Dict]) -> Tuple[Dict, List[str]]:
        """聚合任务统计信息（修复时间计算）"""
        if not tasks:
            empty = {
                "total": 0, "xp": 0, "cats": {}, "mit_count": 0,
                "mit_done": [], "mit_todo": [],
                "top_bias": [], "ent_minutes": 0,
                "work_start": "无", "work_end": "无", "work_hours": 0,
                "time_distribution": {}  # 新增：时间分布
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

        # 新增：按小时统计任务分布
        hour_distribution = {}
        total_duration_minutes = 0

        # 用于记录实际工作时段（而非单个任务的时间）
        task_times = []  # 存储所有任务的开始时间

        for t in tasks:
            p = t["properties"]

            # 获取任务的时间信息
            if "计划日期" in p and p["计划日期"].get("date"):
                plan = p["计划日期"]["date"]
                start_iso = plan.get("start")
                end_iso = plan.get("end", start_iso)

                if start_iso:
                    try:
                        # 解析开始时间
                        start_dt = datetime.fromisoformat(start_iso.replace('Z', '+00:00'))
                        task_times.append(start_dt)

                        # 统计任务在哪个小时开始
                        hour = start_dt.hour
                        hour_distribution[hour] = hour_distribution.get(hour, 0) + 1

                        # 计算任务持续时间
                        if end_iso and end_iso != start_iso:
                            end_dt = datetime.fromisoformat(end_iso.replace('Z', '+00:00'))
                            duration = (end_dt - start_dt).total_seconds() / 60  # 分钟
                            total_duration_minutes += duration

                    except Exception as e:
                        logger.warning(f"时间解析错误: {e}")

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

        # 计算工作时段（基于所有任务的开始时间）
        work_start_str = "无"
        work_end_str = "无"
        work_hours = 0

        if task_times:
            task_times.sort()
            # 工作开始：最早的任务开始时间
            work_start = task_times[0]
            # 工作结束：最晚的任务开始时间 + 平均任务时长
            avg_duration = total_duration_minutes / len(tasks) if tasks else 60
            work_end = task_times[-1] + timedelta(minutes=avg_duration)

            work_start_str = work_start.strftime("%H:%M")
            work_end_str = work_end.strftime("%H:%M")

            # 计算工作时长（考虑跨天情况）
            if work_end.date() > work_start.date():
                # 跨天了
                work_hours = 24 - work_start.hour + work_end.hour
            else:
                work_hours = (work_end - work_start).total_seconds() / 3600

            # 找出最活跃的时间段
        peak_hours = []
        if hour_distribution:
            max_count = max(hour_distribution.values())
            peak_hours = [h for h, c in hour_distribution.items() if c == max_count]

        stats = {
            "total": len(tasks),
            "xp": xp_total,
            "cats": dict(categories),
            "mit_count": len(mit_done_titles),
            "mit_done": mit_done_titles,
            "mit_todo": mit_todo_titles,
            "top_bias": top_3_bias,
            "ent_minutes": ent_minutes,
            "work_start": work_start_str,
            "work_end": work_end_str,
            "work_hours": round(work_hours, 1),
            "total_duration": round(total_duration_minutes / 60, 1),  # 总时长（小时）
            "time_distribution": hour_distribution,
            "peak_hours": peak_hours
        }

        logger.info(f"任务聚合完成: 总数 {stats['total']}, 工作时段 {stats['work_start']}-{stats['work_end']}")
        logger.info(f"高峰时段: {stats['peak_hours']}, 总工作时长: {stats['work_hours']}小时")
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
- 工作区间：{work_start} - {work_end}（共 {focus_span}）
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
            work_start=stats["work_start"],
            work_end=stats["work_end"],
            focus_span=stats["focus_span"]
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


def aggregate_tasks_smart(self, tasks: List[Dict]) -> Tuple[Dict, List[str]]:
    """智能聚合任务统计（排除睡眠，处理重叠）"""
    if not tasks:
        return self._empty_stats(), []

    # 基础统计变量
    xp_total = 0
    categories = Counter()
    titles = []
    mit_done_titles = []

    # 时间相关变量
    work_periods = []  # 存储实际工作时段
    sleep_duration = 0
    entertainment_duration = 0

    # 按时间排序任务
    time_sorted_tasks = []

    for t in tasks:
        p = t["properties"]

        # 获取基本信息
        title = "（无标题）"
        if p.get("任务名称", {}).get("title"):
            title = p["任务名称"]["title"][0].get("plain_text", "（无标题）")
        titles.append(title)

        # 获取分类
        cat = p.get("分类", {}).get("select", {}).get("name", "未分类")
        categories[cat] += 1

        # 获取时间信息
        date_prop = p.get("计划日期", {}).get("date", {})
        start_str = date_prop.get("start")
        end_str = date_prop.get("end")

        if start_str:
            try:
                start_dt = datetime.fromisoformat(start_str.replace('Z', '+00:00'))
                end_dt = start_dt  # 默认结束时间等于开始时间

                if end_str and end_str != start_str:
                    end_dt = datetime.fromisoformat(end_str.replace('Z', '+00:00'))

                duration_hours = (end_dt - start_dt).total_seconds() / 3600

                # 判断是否是睡眠任务
                is_sleep = any(keyword in title.lower() for keyword in ['睡觉', '睡眠', 'sleep', '补觉'])

                # 判断是否是娱乐任务
                is_entertainment = (cat in ["Entertainment", "Fun", "Life"] or
                                    any(keyword in title for keyword in ['刷', '视频', '电视剧', '小红书']))

                time_sorted_tasks.append({
                    'title': title,
                    'category': cat,
                    'start': start_dt,
                    'end': end_dt,
                    'duration': duration_hours,
                    'is_sleep': is_sleep,
                    'is_entertainment': is_entertainment,
                    'task': t
                })

                if is_sleep:
                    sleep_duration += duration_hours
                elif is_entertainment:
                    entertainment_duration += duration_hours
                else:
                    # 只记录非睡眠的工作时段
                    work_periods.append((start_dt, end_dt))

            except Exception as e:
                logger.warning(f"时间解析错误: {e}")

        # XP 和 MIT 统计
        xp_total += calc_xp(t)

        pri = p.get("优先级", {}).get("select", {}).get("name", "")
        if pri == "MIT":
            mit_done_titles.append(title)

    # 计算实际工作时间（排除睡眠）
    actual_work_hours = 0
    productive_hours = 0

    if work_periods:
        # 合并重叠的时间段
        merged_periods = self._merge_overlapping_periods(work_periods)

        # 计算总工作时间
        for start, end in merged_periods:
            actual_work_hours += (end - start).total_seconds() / 3600

        # 计算有效工作时间（排除娱乐）
        productive_hours = actual_work_hours - (entertainment_duration / 60)

    # 找出最早和最晚的工作时间（不包括睡眠）
    work_start = "无"
    work_end = "无"

    non_sleep_tasks = [t for t in time_sorted_tasks if not t['is_sleep']]
    if non_sleep_tasks:
        earliest = min(t['start'] for t in non_sleep_tasks)
        latest = max(t['end'] for t in non_sleep_tasks)

        # 转换到本地时区
        tz = pytz.timezone(self.config.timezone) if hasattr(self, 'config') else pytz.UTC
        work_start = earliest.astimezone(tz).strftime("%H:%M")
        work_end = latest.astimezone(tz).strftime("%H:%M")

    # 统计结果
    stats = {
        "total": len(tasks),
        "xp": xp_total,
        "cats": dict(categories),
        "mit_count": len(mit_done_titles),
        "mit_done": mit_done_titles,

        # 时间统计
        "work_start": work_start,
        "work_end": work_end,
        "actual_work_hours": round(actual_work_hours, 1),
        "productive_hours": round(productive_hours, 1),
        "sleep_hours": round(sleep_duration, 1),
        "entertainment_hours": round(entertainment_duration, 1),

        # 效率指标
        "tasks_per_hour": round(len(tasks) / actual_work_hours, 1) if actual_work_hours > 0 else 0,
        "xp_per_hour": round(xp_total / actual_work_hours, 1) if actual_work_hours > 0 else 0,
    }

    logger.info(f"智能统计完成:")
    logger.info(f"  总任务: {stats['total']}")
    logger.info(f"  实际工作: {stats['actual_work_hours']}小时（排除睡眠）")
    logger.info(f"  睡眠时间: {stats['sleep_hours']}小时")
    logger.info(f"  娱乐时间: {stats['entertainment_hours']}小时")

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