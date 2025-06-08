# src/summarizer.py - 🔄 基于Notion公式的精简修改版
import os
from collections import Counter
from typing import Dict, List, Tuple
from .utils import setup_logger
from datetime import datetime
import pytz

logger = setup_logger(__name__)


class TaskSummarizer:
    def __init__(self, config, templates_dir: str = "templates"):
        self.config = config
        self.templates_dir = templates_dir
        self.tz = pytz.timezone(config.timezone)

    def aggregate_tasks(self, tasks: List[Dict]) -> Tuple[Dict, List[str]]:
        """聚合任务统计信息 - 现在直接从Notion公式读取XP和番茄数"""
        if not tasks:
            return {"total": 0, "xp": 0, "cats": {}, "mit_count": 0}, []

        xp_total = 0
        tomatoes_total = 0
        categories = Counter()
        mit_count = 0
        titles = []

        for task in tasks:
            try:
                props = task.get("properties", {})

                # 分类统计
                category = (
                    props.get("分类", {})
                    .get("select", {})
                    .get("name", "未分类")
                )
                categories[category] += 1

                # MIT计数
                priority = (
                    props.get("优先级", {})
                    .get("select", {})
                    .get("name", "")
                )
                if priority == "MIT":
                    mit_count += 1

                # ✅ 核心修改：直接从Notion公式读取XP
                xp = props.get("XP", {}).get("formula", {}).get("number", 0) or 0
                xp_total += xp

                # ✅ 核心修改：直接从Notion公式读取番茄数
                tomatoes = props.get("番茄数", {}).get("formula", {}).get("number", 0) or 0
                tomatoes_total += tomatoes

                # 任务标题
                title_prop = props.get("任务名称", {})
                if title_prop.get("title"):
                    title = title_prop["title"][0]["plain_text"]
                    titles.append(title)

            except (KeyError, TypeError, IndexError) as e:
                logger.warning(f"处理任务时出错: {e}, 任务ID: {task.get('id', 'unknown')}")
                continue

        stats = {
            "total": len(tasks),
            "xp": xp_total,
            "tomatoes": tomatoes_total,
            "cats": dict(categories),
            "mit_count": mit_count
        }

        logger.info(
            f"任务聚合完成: 总数 {stats['total']}, XP {stats['xp']}, 番茄 {tomatoes_total}, MIT {stats['mit_count']}")
        return stats, titles

    def get_detailed_stats(self, tasks: List[Dict]) -> Tuple[Dict, List[Dict]]:
        """为日报/周报/月报提供详细的任务数据"""
        if not tasks:
            return {}, []

        task_details_for_prompt = []
        total_xp = 0
        total_tomatoes = 0
        total_actual_minutes = 0
        categories = Counter()
        all_start_dts = []
        all_end_dts = []

        for t in tasks:
            try:
                props = t.get("properties", {})

                # 基础信息
                title = props.get("任务名称", {}).get("title", [{}])[0].get("plain_text", "（无标题）")
                cat = props.get("分类", {}).get("select", {}).get("name", "未分类")
                priority = props.get("优先级", {}).get("select", {}).get("name", "")
                is_mit = priority == "MIT"

                # ✅ 从Notion公式读取
                xp = props.get("XP", {}).get("formula", {}).get("number", 0) or 0
                tomatoes = props.get("番茄数", {}).get("formula", {}).get("number", 0) or 0
                actual_minutes = props.get("实际用时(min)", {}).get("formula", {}).get("number", 0) or 0

                total_xp += xp
                total_tomatoes += tomatoes
                total_actual_minutes += actual_minutes
                categories[cat] += 1

                # 时间信息
                start_dt, end_dt = None, None
                date_prop = props.get("计划日期", {}).get("date", {})
                start_iso = date_prop.get("start")
                end_iso = date_prop.get("end")

                if start_iso:
                    try:
                        start_dt = datetime.fromisoformat(start_iso.replace('Z', '+00:00'))
                        end_dt = datetime.fromisoformat(
                            end_iso.replace('Z', '+00:00')) if end_iso and end_iso != start_iso else start_dt
                    except Exception:
                        pass

                if start_dt: all_start_dts.append(start_dt)
                if end_dt: all_end_dts.append(end_dt)

                start_str = start_dt.astimezone(self.tz).strftime('%H:%M') if start_dt else 'N/A'
                end_str = end_dt.astimezone(self.tz).strftime('%H:%M') if end_dt else 'N/A'

                task_details_for_prompt.append({
                    "title": title,
                    "category": cat,
                    "start_time": start_str,
                    "end_time": end_str,
                    "duration_min": actual_minutes,
                    "xp": xp,
                    "tomatoes": tomatoes,
                    "is_mit": is_mit
                })

            except Exception as e:
                logger.warning(f"解析任务失败: {e}")
                continue

        # 计算时间范围
        work_start_str, work_end_str, focus_span_str = "无", "无", "无"
        if all_start_dts and all_end_dts:
            earliest_start = min(all_start_dts)
            latest_end = max(all_end_dts)
            work_start_str = earliest_start.astimezone(self.tz).strftime("%H:%M")
            work_end_str = latest_end.astimezone(self.tz).strftime("%H:%M")
            focus_span_hours = (latest_end - earliest_start).total_seconds() / 3600
            focus_span_str = f"{focus_span_hours:.1f}小时"

        # ✅ 计算效率指标
        xp_per_tomato = round(total_xp / total_tomatoes, 2) if total_tomatoes > 0 else 0

        stats = {
            "total": len(tasks),
            "xp": total_xp,
            "tomatoes": total_tomatoes,
            "xp_per_tomato": xp_per_tomato,
            "cats": dict(categories),
            "mit_count": sum(1 for t in task_details_for_prompt if t['is_mit']),
            "work_start": work_start_str,
            "work_end": work_end_str,
            "work_hours": round(total_actual_minutes / 60, 1),
            "focus_span": focus_span_str,
        }

        return stats, task_details_for_prompt

    def get_trend_stats(self, tasks: List[Dict]) -> Dict:
        """为三日报告提供趋势数据"""
        if not tasks:
            return self._empty_trend_stats()

        total_xp = 0
        total_tomatoes = 0
        sleep_duration = 0
        entertainment_duration = 0
        work_periods = []
        mit_count = 0

        for t in tasks:
            try:
                props = t.get("properties", {})

                # ✅ 从公式读取
                xp = props.get("XP", {}).get("formula", {}).get("number", 0) or 0
                tomatoes = props.get("番茄数", {}).get("formula", {}).get("number", 0) or 0

                total_xp += xp
                total_tomatoes += tomatoes

                priority = props.get("优先级", {}).get("select", {}).get("name", "")
                if priority == "MIT":
                    mit_count += 1

                # 分析时间分配
                title = props.get("任务名称", {}).get("title", [{}])[0].get("plain_text", "")
                category = props.get("分类", {}).get("select", {}).get("name", "")

                date_prop = props.get("计划日期", {}).get("date", {})
                start_iso = date_prop.get("start")
                end_iso = date_prop.get("end")

                if start_iso and end_iso:
                    start_dt = datetime.fromisoformat(start_iso.replace('Z', '+00:00'))
                    end_dt = datetime.fromisoformat(end_iso.replace('Z', '+00:00'))
                    duration_hours = (end_dt - start_dt).total_seconds() / 3600

                    is_sleep = any(k in title.lower() for k in ['睡觉', 'sleep', '补觉'])
                    is_ent = category == "Entertainment" or any(k in title.lower() for k in ['刷', '视频', '看剧'])

                    if is_sleep:
                        sleep_duration += duration_hours
                    else:
                        work_periods.append((start_dt, end_dt))
                        if is_ent:
                            entertainment_duration += duration_hours

            except Exception as e:
                logger.warning(f"处理趋势数据失败: {e}")
                continue

        # 合并工作时段
        merged_periods = self._merge_overlapping_periods(work_periods)
        actual_work_hours = sum((end - start).total_seconds() / 3600 for start, end in merged_periods)

        # ✅ 计算效率
        xp_per_tomato = round(total_xp / total_tomatoes, 2) if total_tomatoes > 0 else 0

        stats = {
            "total": len(tasks),
            "xp": total_xp,
            "tomatoes": total_tomatoes,
            "xp_per_tomato": xp_per_tomato,
            "mit_count": mit_count,
            "actual_work_hours": round(actual_work_hours, 1),
            "sleep_hours": round(sleep_duration, 1),
            "entertainment_hours": round(entertainment_duration, 1),
        }

        return stats

    def build_prompt(self, stats: Dict, task_details: List[Dict], period: str) -> str:
        """构建AI提示词 - 现在使用详细任务数据而不是标题列表"""
        template = self._load_template(period)

        # 格式化分类分布
        if stats["cats"]:
            categories = ", ".join(f"{k}:{v}" for k, v in stats["cats"].items())
        else:
            categories = "无"

        # 格式化详细任务列表（包含XP和番茄数）
        task_list_lines = []
        if task_details:
            # 按分类分组
            tasks_by_cat = {}
            for task in task_details:
                cat = task['category']
                if cat not in tasks_by_cat:
                    tasks_by_cat[cat] = []
                tasks_by_cat[cat].append(task)

            # 按分类输出
            for cat, tasks_in_cat in sorted(tasks_by_cat.items()):
                task_list_lines.append(f"【{cat}】")
                for task in sorted(tasks_in_cat, key=lambda x: x['start_time']):
                    mit_str = " (MIT)" if task['is_mit'] else ""
                    time_str = f"{task['start_time']}-{task['end_time']}"
                    efficiency = f"{task['xp']}/{task['tomatoes']}" if task['tomatoes'] > 0 else "0/0"
                    task_list_lines.append(
                        f"- {task['title']}{mit_str} | {time_str} | {efficiency}"
                    )

        task_list = "\n".join(task_list_lines) if task_list_lines else "无已完成任务"

        # ✅ 新增番茄和效率数据
        prompt = template.format(
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
            focus_span=stats.get("focus_span", "无")
        )

        logger.info(f"生成 {period} 提示词，长度: {len(prompt)} 字符")
        return prompt

    def build_three_day_prompt(self, three_days_stats: Dict[str, Dict]) -> str:
        """构建三天趋势分析提示词"""
        template = self._load_template("three_days")

        sorted_dates = sorted(three_days_stats.keys())
        weekdays = ['周一', '周二', '周三', '周四', '周五', '周六', '周日']
        days_summary_lines = []

        # 三天总计
        total_tasks = 0
        total_xp = 0
        total_tomatoes = 0
        total_work_hours = 0
        total_sleep_hours = 0
        total_entertainment_hours = 0
        total_mit = 0

        for date_str in sorted_dates:
            stats = three_days_stats[date_str]
            date_obj = datetime.fromisoformat(date_str)
            weekday = weekdays[date_obj.weekday()]

            # 累计总数
            total_tasks += stats.get('total', 0)
            total_xp += stats.get('xp', 0)
            total_tomatoes += stats.get('tomatoes', 0)
            total_work_hours += stats.get('actual_work_hours', 0)
            total_sleep_hours += stats.get('sleep_hours', 0)
            total_entertainment_hours += stats.get('entertainment_hours', 0)
            total_mit += stats.get('mit_count', 0)

            # ✅ 格式化单日摘要，包含番茄和效率数据
            day_summary = f"""
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

            days_summary_lines.append(day_summary)

        # 计算平均值
        avg_work = total_work_hours / 3 if len(sorted_dates) > 0 else 0
        avg_sleep = total_sleep_hours / 3 if len(sorted_dates) > 0 else 0
        avg_entertainment = total_entertainment_hours / 3 if len(sorted_dates) > 0 else 0
        avg_xp_per_tomato = round(total_xp / total_tomatoes, 2) if total_tomatoes > 0 else 0

        # 填充模板
        prompt = template.format(
            days_summary=''.join(days_summary_lines),
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
            total_mit=total_mit
        )

        return prompt

    def _load_template(self, period: str) -> str:
        """加载提示词模板"""
        template_file = os.path.join(self.templates_dir, f"{period}_prompt.txt")
        if os.path.exists(template_file):
            with open(template_file, 'r', encoding='utf-8') as f:
                return f.read().strip()
        return self._get_default_template(period)

    def _get_default_template(self, period: str) -> str:
        """获取默认模板"""
        period_map = {
            "daily": ("今天", "明天", "日"),
            "weekly": ("本周", "下周", "周"),
            "monthly": ("本月", "下月", "月"),
            "three_days": ("三天", "接下来", "趋势")
        }

        current, next_period, unit = period_map.get(period, ("今天", "明天", "日"))

        return f"""# {period.title()} Review
已完成任务 {{total}} 个，分类分布：{{categories}}
获得 XP {{xp}}，消耗番茄 {{tomatoes}} 个
效率指标：{{xp_per_tomato}} XP/番茄
MIT 任务 {{mit_count}} 个

## 任务清单
{{task_list}}

请用中文输出，要求简洁实用：
1. **{current}亮点** - 总结 3 个主要成就
2. **改进空间** - 指出 1 个最需要优化的方面  
3. **{next_period}行动** - 提供 3 条具体可执行的建议

注意：回复字数控制在 300 字以内，重点突出可操作性。"""

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
        return {
            "total": 0,
            "xp": 0,
            "tomatoes": 0,
            "xp_per_tomato": 0,
            "mit_count": 0,
            "actual_work_hours": 0,
            "sleep_hours": 0,
            "entertainment_hours": 0
        }


