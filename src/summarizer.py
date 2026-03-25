import os
import re
from collections import Counter
from datetime import datetime
from typing import Dict, List, Optional, Tuple, Union

import pytz

from .config import Config
from .models import TaskRecord
from .notion_client import NotionClient
from .sqlite_task_store import SQLiteTaskStore
from .utils import project_root, setup_logger

logger = setup_logger(__name__)


class TaskSummarizer:
    def __init__(self, config: Optional[Config] = None, templates_dir: Optional[str] = None):
        self.config = config or Config()
        self.templates_dir = templates_dir or str(project_root() / "templates")
        self.tz = pytz.timezone(self.config.timezone)

    def _normalize_tasks(self, tasks: List[Union[Dict, TaskRecord]]) -> List[TaskRecord]:
        normalized: List[TaskRecord] = []
        for task in tasks:
            if isinstance(task, TaskRecord):
                normalized.append(task)
            else:
                if task.get("properties"):
                    normalized.append(NotionClient.parse_task(task))
                else:
                    normalized.append(SQLiteTaskStore.from_mapping(task))
        return normalized

    def aggregate_tasks(self, tasks: List[Union[Dict, TaskRecord]]) -> Tuple[Dict, List[str]]:
        normalized_tasks = self._normalize_tasks(tasks)
        if not normalized_tasks:
            return {"total": 0, "xp": 0, "cats": {}, "mit_count": 0}, []

        xp_total = 0
        categories = Counter()
        mit_count = 0
        titles = []

        for task in normalized_tasks:
            categories[task.category] += 1
            xp_total += task.xp
            mit_count += int(task.is_mit)
            titles.append(task.title)

        stats = {
            "total": len(normalized_tasks),
            "xp": xp_total,
            "cats": dict(categories),
            "mit_count": mit_count,
        }
        logger.info("任务聚合完成: %s", stats)
        return stats, titles

    def get_detailed_stats(self, tasks: List[Union[Dict, TaskRecord]]) -> Tuple[Dict, List[Dict]]:
        normalized_tasks = self._normalize_tasks(tasks)
        if not normalized_tasks:
            return {}, []

        task_details_for_prompt = []
        total_xp = 0
        total_tomatoes = 0
        total_actual_minutes = 0
        categories = Counter()
        all_start_dts = []
        all_end_dts = []

        for task in normalized_tasks:
            duration_minutes = task.actual_minutes
            if duration_minutes == 0 and task.scheduled_start and task.scheduled_end:
                duration_minutes = int(
                    max((task.scheduled_end - task.scheduled_start).total_seconds() / 60, 0)
                )

            total_xp += task.xp
            total_tomatoes += task.tomatoes
            total_actual_minutes += duration_minutes
            categories[task.category] += 1

            start_dt = task.scheduled_start
            end_dt = task.scheduled_end or task.scheduled_start

            if start_dt:
                all_start_dts.append(start_dt)
            if end_dt:
                all_end_dts.append(end_dt)

            task_details_for_prompt.append(
                {
                    "title": task.title,
                    "category": task.category,
                    "start_time": start_dt.astimezone(self.tz).strftime("%H:%M") if start_dt else "N/A",
                    "end_time": end_dt.astimezone(self.tz).strftime("%H:%M") if end_dt else "N/A",
                    "duration_min": duration_minutes,
                    "xp": task.xp,
                    "tomatoes": task.tomatoes,
                    "is_mit": task.is_mit,
                }
            )

        work_start_str, work_end_str, focus_span_str = "无", "无", "无"
        if all_start_dts and all_end_dts:
            earliest_start = min(all_start_dts)
            latest_end = max(all_end_dts)
            work_start_str = earliest_start.astimezone(self.tz).strftime("%H:%M")
            work_end_str = latest_end.astimezone(self.tz).strftime("%H:%M")
            focus_span_hours = (latest_end - earliest_start).total_seconds() / 3600
            focus_span_str = f"{focus_span_hours:.1f}小时"

        xp_per_tomato = round(total_xp / total_tomatoes, 2) if total_tomatoes > 0 else 0
        stats = {
            "total": len(normalized_tasks),
            "xp": total_xp,
            "tomatoes": total_tomatoes,
            "xp_per_tomato": xp_per_tomato,
            "cats": dict(categories),
            "mit_count": sum(1 for task in task_details_for_prompt if task["is_mit"]),
            "work_start": work_start_str,
            "work_end": work_end_str,
            "work_hours": round(total_actual_minutes / 60, 1),
            "focus_span": focus_span_str,
        }
        return stats, task_details_for_prompt

    def get_trend_stats(self, tasks: List[Union[Dict, TaskRecord]]) -> Dict:
        normalized_tasks = self._normalize_tasks(tasks)
        if not normalized_tasks:
            return self._empty_trend_stats()

        total_xp = 0
        total_tomatoes = 0
        sleep_duration = 0.0
        entertainment_duration = 0.0
        work_periods = []
        mit_count = 0
        earliest_work = None
        latest_work = None

        for task in normalized_tasks:
            total_xp += task.xp
            total_tomatoes += task.tomatoes
            mit_count += int(task.is_mit)

            start_dt = task.scheduled_start
            end_dt = task.scheduled_end or task.scheduled_start
            if not (start_dt and end_dt):
                continue

            duration_hours = max((end_dt - start_dt).total_seconds() / 3600, 0)
            title_lower = task.title.lower()
            category_lower = task.category.lower()
            is_sleep = any(keyword in title_lower for keyword in ["睡觉", "sleep", "补觉"])
            is_ent = category_lower == "entertainment" or any(
                keyword in title_lower for keyword in ["刷", "视频", "看剧"]
            )

            if is_sleep:
                sleep_duration += duration_hours
                continue

            work_periods.append((start_dt, end_dt))
            earliest_work = min(earliest_work, start_dt) if earliest_work else start_dt
            latest_work = max(latest_work, end_dt) if latest_work else end_dt
            if is_ent:
                entertainment_duration += duration_hours

        merged_periods = self._merge_overlapping_periods(work_periods)
        actual_work_hours = sum((end - start).total_seconds() / 3600 for start, end in merged_periods)
        xp_per_tomato = round(total_xp / total_tomatoes, 2) if total_tomatoes > 0 else 0

        return {
            "total": len(normalized_tasks),
            "xp": total_xp,
            "tomatoes": total_tomatoes,
            "xp_per_tomato": xp_per_tomato,
            "mit_count": mit_count,
            "actual_work_hours": round(actual_work_hours, 1),
            "sleep_hours": round(sleep_duration, 1),
            "entertainment_hours": round(entertainment_duration, 1),
            "work_start": earliest_work.astimezone(self.tz).strftime("%H:%M") if earliest_work else "无",
            "work_end": latest_work.astimezone(self.tz).strftime("%H:%M") if latest_work else "无",
        }

    def build_prompt(
        self,
        stats: Dict,
        task_details: List[Dict],
        period: str,
        memory_context: str = "",
        focus_context: str = "",
        coaching_context: str = "",
        intervention_context: str = "",
    ) -> str:
        template = self._load_template(period)
        categories = ", ".join(f"{k}:{v}" for k, v in stats.get("cats", {}).items()) or "无"

        task_list_lines = []
        if task_details:
            if isinstance(task_details[0], str):
                task_list_lines.extend(f"- {title}" for title in task_details)
            else:
                tasks_by_cat: Dict[str, List[Dict]] = {}
                for task in task_details:
                    tasks_by_cat.setdefault(task["category"], []).append(task)

                for cat, tasks_in_cat in sorted(tasks_by_cat.items()):
                    task_list_lines.append(f"【{cat}】")
                    for task in sorted(tasks_in_cat, key=lambda item: item["start_time"]):
                        mit_str = " (MIT)" if task["is_mit"] else ""
                        time_str = f"{task['start_time']}-{task['end_time']}"
                        efficiency = (
                            f"{task['xp']}/{task['tomatoes']}"
                            if task["tomatoes"] > 0
                            else "0/0"
                        )
                        task_list_lines.append(
                            f"- {task['title']}{mit_str} | {time_str} | {efficiency}"
                        )

        task_list = "\n".join(task_list_lines) if task_list_lines else "无已完成任务"
        profile_context = template.format(
            total=stats["total"],
            xp=stats["xp"],
            tomatoes=stats.get("tomatoes", 0),
            xp_per_tomato=stats.get("xp_per_tomato", 0),
            categories=categories,
            mit_count=stats["mit_count"],
            task_list=task_list,
            work_start=stats.get("work_start", "无"),
            work_end=stats.get("work_end", "无"),
            work_hours=stats.get("work_hours", 0),
            focus_span=stats.get("focus_span", "无"),
        )
        prompt = "\n\n".join(
            part
            for part in [
                "你不是在写流水账，而是在做连续复盘和策略校准。",
                f"【本次复盘类型】\n{self._period_brief(period)}",
                f"【历史记忆】\n{memory_context}" if memory_context else "",
                f"【当前焦点档案】\n{focus_context}" if focus_context else "",
                f"【当前教练模式】\n{coaching_context}" if coaching_context else "",
                f"【干预系统判断】\n{intervention_context}" if intervention_context else "",
                f"【当前数据与用户偏好】\n{profile_context}",
                f"【输出要求】\n{self._period_output_contract(period)}",
            ]
            if part
        )
        logger.info("生成 %s 提示词，长度: %s 字符", period, len(prompt))
        return prompt

    def build_three_day_prompt(
        self,
        three_days_stats: Dict[str, Dict],
        memory_context: str = "",
        focus_context: str = "",
        coaching_context: str = "",
        intervention_context: str = "",
    ) -> str:
        template = self._load_template("three_days")
        sorted_dates = sorted(three_days_stats.keys())
        weekdays = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]
        days_summary_lines = []

        total_tasks = 0
        total_xp = 0
        total_tomatoes = 0
        total_work_hours = 0.0
        total_sleep_hours = 0.0
        total_entertainment_hours = 0.0
        total_mit = 0

        for date_str in sorted_dates:
            stats = three_days_stats[date_str]
            weekday = weekdays[datetime.fromisoformat(date_str).weekday()]
            total_tasks += stats.get("total", 0)
            total_xp += stats.get("xp", 0)
            total_tomatoes += stats.get("tomatoes", 0)
            total_work_hours += stats.get("actual_work_hours", 0)
            total_sleep_hours += stats.get("sleep_hours", 0)
            total_entertainment_hours += stats.get("entertainment_hours", 0)
            total_mit += stats.get("mit_count", 0)

            days_summary_lines.append(
                f"""
【{date_str} {weekday}】
• 完成任务：{stats.get('total', 0)}个
• 工作时段：{stats.get('work_start', '无')} - {stats.get('work_end', '无')}
• 实际工作：{stats.get('actual_work_hours', 0)}小时（不含睡眠）
• 睡眠时间：{stats.get('sleep_hours', 0)}小时
• 娱乐时间：{stats.get('entertainment_hours', 0)}小时
• 获得XP：{stats.get('xp', 0)}点
• 番茄数：{stats.get('tomatoes', 0)}个
• MIT完成：{stats.get('mit_count', 0)}个
• 效率指标：{stats.get('xp_per_tomato', 0)} XP/番茄"""
            )

        avg_work = total_work_hours / len(sorted_dates) if sorted_dates else 0
        avg_sleep = total_sleep_hours / len(sorted_dates) if sorted_dates else 0
        avg_entertainment = total_entertainment_hours / len(sorted_dates) if sorted_dates else 0
        avg_xp_per_tomato = round(total_xp / total_tomatoes, 2) if total_tomatoes > 0 else 0

        profile_context = template.format(
            days_summary="".join(days_summary_lines),
            total_tasks=total_tasks,
            total_xp=total_xp,
            total_tomatoes=total_tomatoes,
            avg_xp_per_tomato=avg_xp_per_tomato,
            total_work_hours=total_work_hours,
            avg_work=avg_work,
            total_sleep_hours=total_sleep_hours,
            avg_sleep=avg_sleep,
            total_entertainment_hours=total_entertainment_hours,
            avg_entertainment=avg_entertainment,
            total_mit=total_mit,
        )
        return "\n\n".join(
            part
            for part in [
                "你不是在写趋势复述，而是在识别模式和提出下一步实验。",
                "【本次复盘类型】\n三日趋势分析，重点是找出短期循环、连续偏差和未来72小时最值得验证的动作。",
                f"【历史记忆】\n{memory_context}" if memory_context else "",
                f"【当前焦点档案】\n{focus_context}" if focus_context else "",
                f"【当前教练模式】\n{coaching_context}" if coaching_context else "",
                f"【干预系统判断】\n{intervention_context}" if intervention_context else "",
                f"【当前数据与用户偏好】\n{profile_context}",
                f"【输出要求】\n{self._period_output_contract('three-days')}",
            ]
            if part
        )

    def build_empty_review(self, period: str) -> str:
        title_map = {
            "daily": "Daily Review",
            "weekly": "Weekly Review",
            "monthly": "Monthly Review",
            "three-days": "Three-Day Review",
        }
        heading = title_map.get(period, f"{period.title()} Review")
        return f"# {heading}\n\n暂无已完成任务，继续努力。"

    def build_dormancy_review(
        self,
        dormant_days: int,
        idle_after_days: int,
        last_active_date: str,
        restart_message: str,
    ) -> str:
        lines = [
            "自动熄火状态",
            "",
            f"最近已经连续一段时间没有新的完成任务，系统在静默 {idle_after_days} 天后自动进入休眠。",
            f"当前已休眠 {dormant_days} 天。",
        ]
        if last_active_date:
            lines.append(f"上一次检测到完成任务：{last_active_date}。")
        lines.extend(
            [
                "这不是批评，而是为了在你暂时停更时先关掉无效噪音。",
                "下次一旦检测到新的完成任务，系统会自动恢复正常复盘。",
                restart_message,
                "",
                "复盘标签：自动熄火，低打扰，等待重启",
                "下一轮跟进：完成一个 15-30 分钟的最小任务，让系统重新启动起来",
            ]
        )
        return "\n".join(lines)

    def build_preview(
        self,
        period: str,
        stats: Dict,
        content: str,
        intervention_summary: str = "",
        max_chars: int = 220,
    ) -> str:
        period_label = {
            "daily": "日报",
            "three-days": "三日趋势",
            "weekly": "周报",
            "monthly": "月报",
        }.get(period, period)
        headline = (
            f"{period_label}速览：完成 {stats.get('total', 0)} 项，"
            f"XP {stats.get('xp', 0)}，MIT {stats.get('mit_count', 0)}。"
        )
        cleaned = self._strip_markdown(content)
        if len(cleaned) > max_chars:
            cleaned = cleaned[: max_chars - 1].rstrip() + "…"
        parts = [headline]
        if intervention_summary:
            parts.append(intervention_summary)
        parts.append(cleaned)
        return "\n".join(part for part in parts if part).strip()

    def build_decision_card(self, period: str, stats: Dict, signals: Dict, content: str) -> str:
        period_label = {
            "daily": "日报",
            "three-days": "三日趋势",
            "weekly": "周报",
            "monthly": "月报",
        }.get(period, period)
        action_review = (signals or {}).get("action_review") or {}
        anomalies = (signals or {}).get("anomalies") or []
        principles = (signals or {}).get("principles") or []
        coaching_mode = (signals or {}).get("coaching_mode") or {}
        should_notify = (signals or {}).get("should_notify", True)
        next_follow_up = self._extract_follow_up(content)

        lines = [
            f"{period_label}决策卡",
            f"当前判断：{'值得提醒' if should_notify else '记录即可'}",
            f"行动闭环：{self._action_status_label(action_review.get('status', 'no_previous_action'))}",
        ]

        previous_follow_up = action_review.get("previous_follow_up", "")
        if previous_follow_up:
            lines.append(f"上次动作：{previous_follow_up}")

        if coaching_mode.get("name"):
            lines.append(f"当前模式：{coaching_mode.get('name')}")
        if coaching_mode.get("current_stage"):
            lines.append(f"当前阶段：{coaching_mode.get('current_stage')}")

        if anomalies:
            top_signals = "；".join(signal.get("summary", "") for signal in anomalies[:2] if signal.get("summary"))
            lines.append(f"当前异常：{top_signals}")
        else:
            lines.append("当前异常：无高优先异常")

        decision_rule = coaching_mode.get("decision_rule", "")
        if decision_rule:
            lines.append(f"模式策略：{decision_rule}")

        if principles:
            titles = "；".join(item.get("name", "") for item in principles[:2] if item.get("name"))
            if titles:
                lines.append(f"当前原则：{titles}")
            first_rule = principles[0].get("action_rule", "")
            if first_rule:
                lines.append(f"执行口径：{first_rule}")

        if next_follow_up:
            lines.append(f"现在只跟一件事：{next_follow_up}")
        elif (stats.get("total", 0) or 0) == 0:
            lines.append("现在只跟一件事：先恢复最小推进，不要让今天继续空转。")

        return "\n".join(lines)

    def build_dormancy_decision_card(
        self,
        reminder_due: bool,
        dormant_days: int,
        last_active_date: str,
        reminder_interval_days: int,
        restart_message: str,
    ) -> str:
        lines = [
            "自动熄火决策卡",
            f"当前判断：{'轻提醒重启' if reminder_due else '保持静默'}",
            f"熄火状态：已休眠 {dormant_days} 天",
        ]
        if last_active_date:
            lines.append(f"上次活跃：{last_active_date}")
        lines.append(f"提醒节奏：每 {reminder_interval_days} 天轻提醒一次")
        lines.append(f"现在只跟一件事：{restart_message}")
        return "\n".join(lines)

    def build_dormancy_preview(
        self,
        reminder_due: bool,
        dormant_days: int,
        restart_message: str,
    ) -> str:
        headline = f"自动熄火：已休眠 {dormant_days} 天。"
        if reminder_due:
            return f"{headline}\n本次发送一条低频重启提醒。\n{restart_message}"
        return f"{headline}\n本次继续静默，等待下一次低频提醒窗口。"

    def _load_template(self, period: str) -> str:
        template_file = os.path.join(self.templates_dir, f"{period}_prompt.txt")
        if os.path.exists(template_file):
            with open(template_file, "r", encoding="utf-8") as file:
                return file.read().strip()
        return self._get_default_template(period)

    def _get_default_template(self, period: str) -> str:
        period_map = {
            "daily": ("今天", "明天"),
            "weekly": ("本周", "下周"),
            "monthly": ("本月", "下月"),
            "three_days": ("三天", "接下来"),
        }
        current, next_period = period_map.get(period, ("今天", "明天"))
        return f"""# {period.title()} Review
已完成任务 {{total}} 个，分类分布：{{categories}}
获得 XP {{xp}}，消耗番茄 {{tomatoes}} 个
效率指标：{{xp_per_tomato}} XP/番茄
MIT 任务 {{mit_count}} 个

## 任务清单
{{task_list}}

请用中文输出，要求简洁实用：
1. {current}亮点 - 总结 3 个主要成就
2. 改进空间 - 指出 1 个最需要优化的方面
3. {next_period}行动 - 提供 3 条具体可执行的建议
"""

    def _period_brief(self, period: str) -> str:
        briefs = {
            "daily": "日报不需要复述所有任务，重点是今天真正推进了什么、偏航成本是什么、明天唯一高杠杆动作是什么。",
            "weekly": "周报重点是识别本周真正有效的杠杆、重复损耗，以及下周需要保留/停止/新增的策略。",
            "monthly": "月报重点是系统级模式、错误努力和下个月应该围绕哪一个主题集中资源。",
            "three-days": "三日趋势重点是短期行为循环、精力波动和未来72小时的实验设计。",
        }
        return briefs.get(period, "请围绕变化、杠杆和下一步输出。")

    def _period_output_contract(self, period: str) -> str:
        contracts = {
            "daily": (
                "输出纯文本，不要使用 markdown。\n"
                "只写 4 个短段落和 2 行结尾标签：\n"
                "1. 今日真正推进：只写最影响长期目标的 1-2 个推进。\n"
                "2. 偏航与代价：指出最主要的时间浪费或错误分配。\n"
                "3. 承诺追踪：结合历史记忆，判断上一次跟进是完成、部分完成还是未推进。\n"
                "4. 明日最小杠杆：给出 1 个重点、1 个边界、1 个实验。\n"
                "最后必须单独输出两行：\n"
                "复盘标签：标签1，标签2，标签3\n"
                "下一轮跟进：一句可验证、可追踪的动作\n"
                "避免重复上次已经说过的泛泛建议，除非你能给出新的证据。\n"
                "如果给出了逆境原则，请把它翻译成判断和动作，不要直接复述口号。"
            ),
            "weekly": (
                "输出纯文本，不要使用 markdown。\n"
                "只写 4 个短段落和 2 行结尾标签：\n"
                "1. 本周最有效杠杆：什么真正推动了优先级任务。\n"
                "2. 重复损耗：这周最反复出现的低回报模式。\n"
                "3. 与上周相比：真正变好/变差的地方，不要空泛。\n"
                "4. 下周策略：分别写保留、停止、新增各 1 项。\n"
                "最后必须单独输出两行：\n"
                "复盘标签：标签1，标签2，标签3\n"
                "下一轮跟进：一句可验证、可追踪的动作\n"
                "如果给出了逆境原则，请把它翻译成判断和动作，不要直接复述口号。"
            ),
            "monthly": (
                "输出纯文本，不要使用 markdown。\n"
                "只写 4 个短段落和 2 行结尾标签：\n"
                "1. 本月系统模式：指出最重要的长期行为模式。\n"
                "2. 应该加码和应该停止：各写 1-2 项。\n"
                "3. 下月主题：只给一个主题和一个量化门槛。\n"
                "4. 资源配置建议：时间和精力最该向哪里集中。\n"
                "最后必须单独输出两行：\n"
                "复盘标签：标签1，标签2，标签3\n"
                "下一轮跟进：一句可验证、可追踪的动作\n"
                "如果给出了逆境原则，请把它翻译成判断和动作，不要直接复述口号。"
            ),
            "three-days": (
                "输出纯文本，不要使用 markdown。\n"
                "只写 4 个短段落和 2 行结尾标签：\n"
                "1. 短期循环：指出过去三天最明显的行为模式。\n"
                "2. 窗口期与滑坡点：什么时候效率最好，什么时候最容易偏航。\n"
                "3. 未来72小时风险：如果延续当前模式，会发生什么。\n"
                "4. 下一步实验：给一个最值得马上验证的行为实验。\n"
                "最后必须单独输出两行：\n"
                "复盘标签：标签1，标签2，标签3\n"
                "下一轮跟进：一句可验证、可追踪的动作\n"
                "如果给出了逆境原则，请把它翻译成判断和动作，不要直接复述口号。"
            ),
        }
        return contracts.get(period, "输出纯文本，强调变化、杠杆和下一步。")

    def _merge_overlapping_periods(
        self,
        periods: List[Tuple[datetime, datetime]],
    ) -> List[Tuple[datetime, datetime]]:
        if not periods:
            return []
        sorted_periods = sorted(periods, key=lambda item: item[0])
        merged = [sorted_periods[0]]
        for current_start, current_end in sorted_periods[1:]:
            if current_start < merged[-1][1]:
                merged[-1] = (merged[-1][0], max(merged[-1][1], current_end))
            else:
                merged.append((current_start, current_end))
        return merged

    def _empty_trend_stats(self) -> Dict:
        return {
            "total": 0,
            "xp": 0,
            "tomatoes": 0,
            "xp_per_tomato": 0,
            "mit_count": 0,
            "actual_work_hours": 0,
            "sleep_hours": 0,
            "entertainment_hours": 0,
            "work_start": "无",
            "work_end": "无",
        }

    def _strip_markdown(self, text: str) -> str:
        text = re.sub(r"\[(.+?)\]\(.+?\)", r"\1", text)
        text = re.sub(r"[*_`#>-]", " ", text)
        return re.sub(r"\s+", " ", text).strip()

    def _extract_follow_up(self, content: str) -> str:
        match = re.search(r"下一轮跟进[:：]\s*(.+)", content)
        return match.group(1).strip() if match else ""

    def _action_status_label(self, status: str) -> str:
        mapping = {
            "no_previous_action": "没有上一次行动可追踪",
            "done": "已观察到较强执行证据",
            "partial": "只观察到部分执行证据",
            "no_evidence": "未观察到明确执行证据",
        }
        return mapping.get(status, status)
