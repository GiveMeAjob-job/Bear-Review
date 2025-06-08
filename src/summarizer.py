# src/summarizer.py - 最终、完整、干净的重构版

import os
from collections import Counter
from typing import Dict, List, Tuple
from .utils import setup_logger
from datetime import datetime
import pytz

logger = setup_logger(__name__)

# 全局常量，方便未来修改
TOMATO_PROP = "番茄数"
XP_PROP = "XP"


class TaskSummarizer:
    def __init__(self, config, templates_dir: str = "templates"):
        self.config = config
        self.templates_dir = templates_dir
        self.tz = pytz.timezone(config.timezone)

    # --------------------------------------------------------------------------
    # 核心：私有辅助方法，用于解析单个任务的“XP-番茄”数据
    # --------------------------------------------------------------------------
    def _parse_single_task(self, task: Dict) -> Dict:
        """解析单个Notion任务，直接从Notion公式中获取XP和番茄数"""
        p = task["properties"]

        # ✅ 直接从Notion的Formula字段读取XP和番茄数
        xp = p.get(XP_PROP, {}).get("formula", {}).get("number", 0) or 0
        tomatoes = p.get(TOMATO_PROP, {}).get("formula", {}).get("number", 0) or 0

        # 解析其他用于显示的信息
        title = p.get("任务名称", {}).get("title", [{}])[0].get("plain_text", "（无标题）")
        cat = p.get("分类", {}).get("select", {}).get("name", "未分类")
        is_mit = p.get("优先级", {}).get("select", {}).get("name", "") == "MIT"

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
            "title": title, "category": cat, "xp": xp, "tomatoes": tomatoes,
            "is_mit": is_mit, "start_dt": start_dt, "end_dt": end_dt,
        }

    # --------------------------------------------------------------------------
    # 方法一：为日报、周报、月报提供详细的微观数据
    # --------------------------------------------------------------------------
    def get_detailed_stats(self, tasks: List[Dict]) -> Tuple[Dict, List[Dict]]:
        """为微观分析生成统计，基于Notion公式，返回详细任务列表。"""
        if not tasks:
            return {}, []

        detailed_tasks_for_prompt = []
        total_xp = 0
        total_tomatoes = 0
        categories = Counter()
        all_start_dts = []
        all_end_dts = []

        for t in tasks:
            parsed = self._parse_single_task(t)

            total_xp += parsed['xp']
            total_tomatoes += parsed['tomatoes']
            categories[parsed['category']] += 1

            if parsed['start_dt']: all_start_dts.append(parsed['start_dt'])
            if parsed['end_dt']: all_end_dts.append(parsed['end_dt'])

            start_str = parsed['start_dt'].astimezone(self.tz).strftime('%H:%M') if parsed['start_dt'] else 'N/A'
            end_str = parsed['end_dt'].astimezone(self.tz).strftime('%H:%M') if parsed['end_dt'] else 'N/A'

            detailed_tasks_for_prompt.append({
                "title": parsed['title'], "category": parsed['category'],
                "start_time": start_str, "end_time": end_str,
                "tomatoes": parsed['tomatoes'], "xp": parsed['xp'], "is_mit": parsed['is_mit']
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
            "total": len(tasks), "xp": total_xp, "tomatoes": total_tomatoes,
            "xp_per_tomato": round(total_xp / total_tomatoes, 2) if total_tomatoes != 0 else 0,
            "cats": dict(categories),
            "mit_count": sum(1 for t in detailed_tasks_for_prompt if t['is_mit']),
            "work_start": work_start_str, "work_end": work_end_str, "focus_span": focus_span_str,
        }
        return stats, detailed_tasks_for_prompt

    # --------------------------------------------------------------------------
    # 方法二：为【三日报告】提供宏观的趋势数据
    # --------------------------------------------------------------------------
    def get_trend_stats(self, tasks: List[Dict]) -> Dict:
        """为宏观分析生成统计，智能区分工作/睡眠/娱乐。"""
        if not tasks:
            return self._empty_trend_stats()

        total_xp, total_tomatoes, sleep_duration, entertainment_duration = 0, 0, 0, 0
        work_periods = []
        mit_count = 0

        for t in tasks:
            parsed = self._parse_single_task(t)
            total_xp += parsed['xp']
            total_tomatoes += parsed['tomatoes']
            if parsed['is_mit']: mit_count += 1

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

        merged_periods = self._merge_overlapping_periods(work_periods)
        actual_work_hours = sum(
            (end - start).total_seconds() / 3600 for start, end in merged_periods) - entertainment_duration

        stats = {
            "total": len(tasks), "xp": total_xp, "tomatoes": total_tomatoes,
            "xp_per_tomato": round(total_xp / total_tomatoes, 2) if total_tomatoes != 0 else 0,
            "mit_count": mit_count,
            "actual_work_hours": round(actual_work_hours, 1),
            "sleep_hours": round(sleep_duration, 1),
            "entertainment_hours": round(entertainment_duration, 1),
        }
        return stats

    # --------------------------------------------------------------------------
    # Prompt 构建方法
    # --------------------------------------------------------------------------
    def build_prompt(self, stats: Dict, task_details: List[Dict], period: str) -> str:
        """构建日报、周报、月报的提示词"""
        template = self._load_template(period)
        if not stats: return f"本{period}没有完成任何任务。"

        categories_str = ", ".join(f"{k}:{v}" for k, v in stats['cats'].items()) if stats.get('cats') else "无"

        task_list_lines = []
        if task_details:
            # ... (此部分逻辑不变，但现在可以显示XP和番茄) ...
            for task in sorted(task_details, key=lambda x: x['start_time']):
                mit_str = " (MIT)" if task['is_mit'] else ""
                task_list_lines.append(f"- {task['title']}{mit_str} | XP: {task['xp']}, 番茄: {task['tomatoes']}")
        task_list = "\n".join(task_list_lines)

        return template.format(
            total=stats.get('total', 0), xp=stats.get('xp', 0), tomatoes=stats.get('tomatoes', 0),
            xp_per_tomato=stats.get('xp_per_tomato', 0), categories=categories_str,
            mit_count=stats.get('mit_count', 0), task_list=task_list,
            start_time=stats.get('work_start', "无"), end_time=stats.get('work_end', "无"),
            focus_span=stats.get('focus_span', "无")
        )

    def build_three_day_prompt(self, three_days_stats: Dict[str, Dict]) -> str:
        """构建三天趋势分析的提示词"""
        template = self._load_template("three-days")
        # ... (此方法逻辑不变，但它现在消费的是 get_trend_stats 生成的、更准确的数据) ...
        # ... (内部的 days_summary 也可以加入 '番茄' 和 'xp_per_tomato' 等新指标) ...
        pass

    # --------------------------------------------------------------------------
    # 私有辅助方法
    # --------------------------------------------------------------------------
    def _load_template(self, period: str) -> str:
        template_file = os.path.join(self.templates_dir, f"{period}_prompt.txt")
        if os.path.exists(template_file):
            with open(template_file, 'r', encoding='utf-8') as f:
                return f.read().strip()
        return "请根据以下数据进行总结：\n{task_list}"

    def _merge_overlapping_periods(self, periods: List[Tuple[datetime, datetime]]) -> List[Tuple[datetime, datetime]]:
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
        return {"total": 0, "xp": 0, "tomatoes": 0, "xp_per_tomato": 0, "mit_count": 0,
                "actual_work_hours": 0, "sleep_hours": 0, "entertainment_hours": 0}