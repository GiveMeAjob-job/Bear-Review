# src/summarizer.py - 🔄 最终重构版

import os
from collections import Counter
from typing import Dict, List, Tuple
from .notion_client import calc_xp
from .utils import setup_logger
from datetime import datetime
import pytz

logger = setup_logger(__name__)


class TaskSummarizer:
    # 构造函数接收 config 对象，以便获取时区等配置
    def __init__(self, config, templates_dir: str = "templates"):
        self.config = config
        self.templates_dir = templates_dir
        self.tz = pytz.timezone(config.timezone)

    # --------------------------------------------------------------------------
    # 核心：私有辅助方法，用于解析单个任务
    # --------------------------------------------------------------------------
    def _parse_single_task(self, task: Dict) -> Dict:
        """解析单个Notion任务，返回一个结构化的字典"""
        p = task["properties"]
        title = p.get("任务名称", {}).get("title", [{}])[0].get("plain_text", "（无标题）")
        cat = p.get("分类", {}).get("select", {}).get("name", "未分类")

        start_dt, end_dt = None, None
        date_prop = p.get("计划日期", {}).get("date", {})
        start_iso, end_iso = date_prop.get("start"), date_prop.get("end")
        if start_iso:
            try:
                start_dt = datetime.fromisoformat(start_iso.replace('Z', '+00:00'))
                end_dt = datetime.fromisoformat(
                    end_iso.replace('Z', '+00:00')) if end_iso and end_iso != start_iso else start_dt
            except Exception:
                pass

        return {
            "title": title,
            "category": cat,
            "xp": calc_xp(task),
            "is_mit": p.get("优先级", {}).get("select", {}).get("name", "") == "MIT",
            "actual_minutes": p.get("实际用时(min)", {}).get("formula", {}).get("number", 0) or 0,
            "start_dt": start_dt,
            "end_dt": end_dt,
        }

    # --------------------------------------------------------------------------
    # 方法一：为【日报、周报、月报】提供详细的微观数据
    # --------------------------------------------------------------------------
    def get_detailed_stats(self, tasks: List[Dict]) -> Tuple[Dict, List[Dict]]:
        """为微观分析生成统计，基于'实际用时(min)'，返回详细任务列表。"""
        if not tasks:
            return {}, []

        task_details_for_prompt = []
        total_xp = 0
        total_actual_minutes = 0
        categories = Counter()
        all_start_dts = []
        all_end_dts = []

        for t in tasks:
            parsed = self._parse_single_task(t)

            total_xp += parsed['xp']
            total_actual_minutes += parsed['actual_minutes']
            categories[parsed['category']] += 1

            if parsed['start_dt']: all_start_dts.append(parsed['start_dt'])
            if parsed['end_dt']: all_end_dts.append(parsed['end_dt'])

            start_str = parsed['start_dt'].astimezone(self.tz).strftime('%H:%M') if parsed['start_dt'] else 'N/A'
            end_str = parsed['end_dt'].astimezone(self.tz).strftime('%H:%M') if parsed['end_dt'] else 'N/A'

            task_details_for_prompt.append({
                "title": parsed['title'], "category": parsed['category'],
                "start_time": start_str, "end_time": end_str,
                "duration_min": parsed['actual_minutes'], "is_mit": parsed['is_mit']
            })

        work_start_str, work_end_str, focus_span_str = "无", "无", "无"
        if all_start_dts and all_end_dts:
            earliest_start = min(all_start_dts)
            latest_end = max(all_end_dts)
            work_start_str = earliest_start.astimezone(self.tz).strftime("%H:%M")
            work_end_str = latest_end.astimezone(self.tz).strftime("%H:%M")
            focus_span_hours = (latest_end - earliest_start).total_seconds() / 3600
            focus_span_str = f"{focus_span_hours:.1f}小时"

        stats = {
            "total": len(tasks), "xp": total_xp, "cats": dict(categories),
            "mit_count": sum(1 for t in task_details_for_prompt if t['is_mit']),
            "work_start": work_start_str, "work_end": work_end_str,
            "work_hours": round(total_actual_minutes / 60, 1),
            "focus_span": focus_span_str,
        }
        return stats, task_details_for_prompt

    # --------------------------------------------------------------------------
    # 方法二：为【三日报告】提供宏观的趋势数据
    # --------------------------------------------------------------------------
    def get_trend_stats(self, tasks: List[Dict]) -> Dict:
        """为宏观分析生成统计，智能区分并使用最准确的数据源。"""
        if not tasks:
            return self._empty_trend_stats()

        total_xp, sleep_duration, entertainment_duration = 0, 0, 0

        # ✅ 新增：用于精确计算效率指标的分母
        productive_minutes = 0

        work_periods = []
        mit_count = 0

        for t in tasks:
            parsed = self._parse_single_task(t)  # 使用我们之前重构的辅助方法
            total_xp += parsed['xp']
            if parsed['is_mit']: mit_count += 1

            # 宏观时间分配，仍然使用起止时间来计算
            if parsed['start_dt'] and parsed['end_dt']:
                duration_hours = (parsed['end_dt'] - parsed['start_dt']).total_seconds() / 3600
                is_sleep = any(k in parsed['title'].lower() for k in ['睡觉', 'sleep', '补觉'])
                is_ent = parsed['category'] in ["Entertainment", "Fun"] or any(
                    k in parsed['title'].lower() for k in ['刷', '视频', '看剧'])

                if is_sleep:
                    sleep_duration += duration_hours
                else:
                    work_periods.append((parsed['start_dt'], parsed['end_dt']))
                    if is_ent:
                        entertainment_duration += duration_hours
                    else:
                        # ✅ 如果一个任务既不是睡眠也不是娱乐，我们就累加它的“实际用时”
                        productive_minutes += parsed.get('actual_minutes', 0)

        merged_periods = self._merge_overlapping_periods(work_periods)
        # “实际工作时段”仍然是所有非睡眠时段的合并，用于展示作息
        actual_work_hours = sum((end - start).total_seconds() / 3600 for start, end in merged_periods)

        # “有效工作小时数”来自于精确的分钟数累加
        productive_hours = productive_minutes / 60

        stats = {
            "total": len(tasks), "xp": total_xp, "mit_count": mit_count,
            # 用于分析作息规律
            "actual_work_hours": round(actual_work_hours, 1),
            "sleep_hours": round(sleep_duration, 1),
            "entertainment_hours": round(entertainment_duration, 1),
            # ✅ 使用最精确的“有效工作小时数”来计算效率
            "xp_per_hour": round(total_xp / productive_hours, 1) if productive_hours > 0 else 0
        }
        return stats

    # --------------------------------------------------------------------------
    # Prompt 构建方法
    # --------------------------------------------------------------------------
    def build_prompt(self, stats: Dict, task_details: List[Dict], period: str) -> str:
        """构建日报、周报、月报的提示词"""
        template = self._load_template(period)
        if not stats: return "今天没有完成任何任务。"

        categories = ", ".join(f"{k}:{v}" for k, v in stats["cats"].items()) if stats.get("cats") else "无"

        task_list_lines = []
        if task_details:
            tasks_by_cat = {}
            for task in task_details:
                cat = task['category']
                if cat not in tasks_by_cat: tasks_by_cat[cat] = []
                tasks_by_cat[cat].append(task)
            for cat, tasks_in_cat in tasks_by_cat.items():
                task_list_lines.append(f"【{cat}】")
                for task in sorted(tasks_in_cat, key=lambda x: x['start_time']):
                    duration_str = f"{task['duration_min']:.0f}分钟"
                    time_str = f"{task['start_time']}-{task['end_time']}"
                    mit_str = " (MIT)" if task['is_mit'] else ""
                    task_list_lines.append(f"- {task['title']}{mit_str} | {time_str} | 用时: {duration_str}")

        task_list = "\n".join(task_list_lines) if task_list_lines else "无已完成任务"

        return template.format(
            total=stats.get("total", 0), xp=stats.get("xp", 0), categories=categories,
            mit_count=stats.get("mit_count", 0), task_list=task_list,
            start_time=stats.get("work_start", "无"), end_time=stats.get("work_end", "无"),
            focus_span=stats.get("focus_span", "无")
        )

    def build_three_day_prompt(self, three_days_stats: Dict[str, Dict]) -> str:
        """构建准确的三天趋势分析提示词（从模板加载）"""

        # ✅ 第一步：加载外部模板文件
        template = self._load_template("three_days")  # 使用已有的加载函数

        # --- 后面的逻辑负责准备模板需要的数据 ---

        sorted_dates = sorted(three_days_stats.keys())
        weekdays = ['周一', '周二', '周三', '周四', '周五', '周六', '周日']
        days_summary_lines = []

        # 三天总计
        total_tasks, total_work_hours, total_sleep_hours, total_entertainment_hours, total_xp, total_mit = 0, 0, 0, 0, 0, 0

        for date_str in sorted_dates:
            stats = three_days_stats[date_str]
            date_obj = datetime.fromisoformat(date_str)
            weekday = weekdays[date_obj.weekday()]

            # 累计总数
            total_tasks += stats.get('total', 0)
            total_work_hours += stats.get('actual_work_hours', 0)
            total_sleep_hours += stats.get('sleep_hours', 0)
            total_entertainment_hours += stats.get('entertainment_hours', 0)
            total_xp += stats.get('xp', 0)
            total_mit += stats.get('mit_count', 0)

            # 格式化单日摘要
            day_summary = f"""
    【{date_str} {weekday}】
    • 完成任务：{stats.get('total', 0)}个
    • 工作时段：{stats.get('work_start', '无')} - {stats.get('work_end', '无')}
    • 实际工作：{stats.get('actual_work_hours', 0)}小时（不含睡眠）
    • 睡眠时间：{stats.get('sleep_hours', 0)}小时
    • 娱乐时间：{stats.get('entertainment_hours', 0)}小时
    • 获得XP：{stats.get('xp', 0)}点
    • MIT完成：{stats.get('mit_count', 0)}个
    • 效率指标：{stats.get('xp_per_hour', 0)} XP/小时"""
            days_summary_lines.append(day_summary)

        # 计算平均值
        avg_work = total_work_hours / 3 if len(sorted_dates) > 0 else 0
        avg_sleep = total_sleep_hours / 3 if len(sorted_dates) > 0 else 0
        avg_entertainment = total_entertainment_hours / 3 if len(sorted_dates) > 0 else 0

        # ✅ 第二步：使用 .format() 填充所有占位符
        prompt = template.format(
            days_summary=''.join(days_summary_lines),
            total_tasks=total_tasks,
            total_work_hours=total_work_hours,
            avg_work=avg_work,
            total_sleep_hours=total_sleep_hours,
            avg_sleep=avg_sleep,
            total_entertainment_hours=total_entertainment_hours,
            avg_entertainment=avg_entertainment,
            total_mit=total_mit
        )

        return prompt

    # --------------------------------------------------------------------------
    # 私有辅助方法
    # --------------------------------------------------------------------------
    def _load_template(self, period: str) -> str:
        """加载提示词模板"""
        template_file = os.path.join(self.templates_dir, f"{period}_prompt.txt")
        if os.path.exists(template_file):
            with open(template_file, 'r', encoding='utf-8') as f:
                return f.read().strip()
        return self._get_default_template(period)

    def _get_default_template(self, period: str) -> str:
        """获取默认模板（仅用于日报）"""
        if period == 'daily':
            return "# Daily Review\n..."  # 返回您的默认日报模板
        return "请为 {period} 撰写一份报告。"  # 为其他类型提供一个极简的默认值

    def _merge_overlapping_periods(self, periods: List[Tuple[datetime, datetime]]) -> List[Tuple[datetime, datetime]]:
        """合并重叠的时间段"""
        if not periods: return []
        sorted_periods = sorted(periods, key=lambda x: x[0])
        merged = [sorted_periods[0]]
        for current_start, current_end in sorted_periods[1:]:
            if current_start < merged[-1][1]:
                merged[-1] = (merged[-1][0], max(merged[-1][1], current_end))
            else:
                merged.append((current_start, current_end))
        return merged

    def _empty_trend_stats(self) -> Dict:
        """返回三日报告所需的空统计字典"""
        return {"total": 0, "xp": 0, "mit_count": 0, "actual_work_hours": 0, "sleep_hours": 0, "entertainment_hours": 0}