# debug_time_analysis.py - 调试三天时间计算问题

import os
import sys
from datetime import datetime, timedelta
import pytz
from dotenv import load_dotenv

# 添加项目路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from src.config import Config
from src.notion_client import NotionClient
from src.summarizer import TaskSummarizer

load_dotenv()


def debug_three_days_time():
    """调试三天的时间计算问题"""
    print("🔍 开始调试三天时间计算...\n")

    # 初始化
    cfg = Config.from_env()
    notion = NotionClient(cfg)
    summarizer = TaskSummarizer()

    tz = pytz.timezone(cfg.timezone)
    today = datetime.now(tz).date()

    print(f"📅 当前日期: {today}")
    print(f"🌍 时区: {cfg.timezone}\n")

    # 分析每一天
    for days_ago in [1, 2, 3]:
        target_date = today - timedelta(days=days_ago)
        print(f"\n{'=' * 60}")
        print(f"📊 分析 {target_date} 的任务")
        print(f"{'=' * 60}")

        # 获取当天任务
        tasks = notion._query_tasks(target_date, target_date)
        print(f"找到 {len(tasks)} 个任务\n")

        # 详细打印每个任务的时间
        for i, task in enumerate(tasks, 1):
            props = task["properties"]

            # 获取任务名称
            title = "未命名"
            if props.get("任务名称", {}).get("title"):
                title = props["任务名称"]["title"][0].get("plain_text", "未命名")

            # 获取时间信息
            date_prop = props.get("计划日期", {}).get("date", {})
            start_str = date_prop.get("start", "无")
            end_str = date_prop.get("end", "无")

            print(f"{i}. {title}")
            print(f"   原始时间: {start_str} → {end_str}")

            # 解析并显示更友好的时间
            if start_str != "无":
                try:
                    start_dt = datetime.fromisoformat(start_str.replace('Z', '+00:00'))
                    # 转换到本地时区
                    start_local = start_dt.astimezone(tz)
                    print(f"   开始时间: {start_local.strftime('%Y-%m-%d %H:%M')} ({start_local.strftime('%A')})")

                    if end_str != "无" and end_str != start_str:
                        end_dt = datetime.fromisoformat(end_str.replace('Z', '+00:00'))
                        end_local = end_dt.astimezone(tz)
                        print(f"   结束时间: {end_local.strftime('%Y-%m-%d %H:%M')} ({end_local.strftime('%A')})")

                        # 计算持续时间
                        duration = end_dt - start_dt
                        hours = duration.total_seconds() / 3600
                        print(f"   持续时间: {hours:.1f} 小时")

                        # 检查是否跨天
                        if start_local.date() != end_local.date():
                            print(f"   ⚠️  跨天任务！从 {start_local.date()} 到 {end_local.date()}")

                except Exception as e:
                    print(f"   ❌ 时间解析错误: {e}")

            print()

        # 使用 summarizer 聚合统计
        if tasks:
            stats, titles = summarizer.aggregate_tasks(tasks)
            print(f"\n📈 聚合统计结果:")
            print(f"   总任务数: {stats['total']}")
            print(f"   总XP: {stats['xp']}")
            print(f"   MIT完成: {stats['mit_count']}")
            print(f"   工作时段: {stats.get('start_time', '?')} - {stats.get('end_time', '?')}")
            print(f"   时间跨度: {stats.get('focus_span', '?')}")

            # 这里是关键！看看是怎么算出24.5小时的
            if 'work_hours' in stats:
                print(f"   ⚠️  计算的工作时长: {stats['work_hours']} 小时")

            # 手动计算验证
            print(f"\n🔍 手动验证时间计算:")
            all_starts = []
            all_ends = []
            total_duration = 0

            for task in tasks:
                date_prop = task["properties"].get("计划日期", {}).get("date", {})
                start_str = date_prop.get("start")
                end_str = date_prop.get("end")

                if start_str:
                    try:
                        start_dt = datetime.fromisoformat(start_str.replace('Z', '+00:00'))
                        all_starts.append(start_dt)

                        if end_str and end_str != start_str:
                            end_dt = datetime.fromisoformat(end_str.replace('Z', '+00:00'))
                            all_ends.append(end_dt)
                            duration = (end_dt - start_dt).total_seconds() / 3600
                            total_duration += duration
                    except:
                        pass

            if all_starts:
                earliest = min(all_starts)
                latest = max(all_ends) if all_ends else max(all_starts)
                span = (latest - earliest).total_seconds() / 3600

                print(f"   最早开始: {earliest.astimezone(tz).strftime('%H:%M')}")
                print(f"   最晚结束: {latest.astimezone(tz).strftime('%H:%M')}")
                print(f"   时间跨度: {span:.1f} 小时")
                print(f"   所有任务总时长: {total_duration:.1f} 小时")

                if span > 24:
                    print(f"   ❌ 错误：时间跨度超过24小时！可能是日期计算错误")
                if total_duration > 24:
                    print(f"   ❌ 错误：任务总时长超过24小时！")


def analyze_time_patterns():
    """分析时间模式，找出问题"""
    cfg = Config.from_env()
    notion = NotionClient(cfg)

    print("\n\n🎯 时间模式分析")
    print("=" * 60)

    # 获取最近7天的所有任务，分析跨天模式
    tz = pytz.timezone(cfg.timezone)
    today = datetime.now(tz).date()
    week_ago = today - timedelta(days=7)

    all_tasks = notion._query_tasks(week_ago, today)

    # 统计跨天任务
    cross_day_tasks = []
    late_night_tasks = []

    for task in all_tasks:
        props = task["properties"]
        title = props.get("任务名称", {}).get("title", [{}])[0].get("plain_text", "未命名")
        date_prop = props.get("计划日期", {}).get("date", {})
        start_str = date_prop.get("start")
        end_str = date_prop.get("end")

        if start_str and end_str and start_str != end_str:
            try:
                start_dt = datetime.fromisoformat(start_str.replace('Z', '+00:00'))
                end_dt = datetime.fromisoformat(end_str.replace('Z', '+00:00'))

                start_local = start_dt.astimezone(tz)
                end_local = end_dt.astimezone(tz)

                # 检查跨天
                if start_local.date() != end_local.date():
                    cross_day_tasks.append({
                        'title': title,
                        'start': start_local,
                        'end': end_local,
                        'duration': (end_dt - start_dt).total_seconds() / 3600
                    })

                # 检查深夜任务（晚上10点后开始）
                if start_local.hour >= 22:
                    late_night_tasks.append({
                        'title': title,
                        'start': start_local,
                        'end': end_local
                    })

            except:
                pass

    print(f"\n📊 时间模式统计:")
    print(f"   总任务数: {len(all_tasks)}")
    print(f"   跨天任务: {len(cross_day_tasks)} ({len(cross_day_tasks) / len(all_tasks) * 100:.1f}%)")
    print(f"   深夜任务: {len(late_night_tasks)} ({len(late_night_tasks) / len(all_tasks) * 100:.1f}%)")

    if cross_day_tasks:
        print(f"\n⚠️  跨天任务详情:")
        for task in cross_day_tasks[:5]:  # 只显示前5个
            print(f"   • {task['title']}")
            print(f"     {task['start'].strftime('%m-%d %H:%M')} → {task['end'].strftime('%m-%d %H:%M')}")
            print(f"     持续 {task['duration']:.1f} 小时")


if __name__ == "__main__":
    # 运行调试
    debug_three_days_time()
    analyze_time_patterns()

    print("\n\n💡 可能的问题:")
    print("1. 跨天任务被重复计算")
    print("2. 时区转换错误")
    print("3. 把任务持续时间累加当成了工作时长")
    print("4. 没有正确处理日期边界")