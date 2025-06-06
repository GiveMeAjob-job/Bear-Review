# src/main.py - 完整版本
"""
Task-Master 入口脚本
支持日报、三天趋势分析、周报、月报

使用示例:
python -m src.main --period daily                    # 今天的日报
python -m src.main --period daily --yesterday       # 昨天的日报（解决时区问题）
python -m src.main --period three-days              # 三天趋势分析
python -m src.main --period weekly                  # 周报
python -m src.main --period monthly                 # 月报
python -m src.main --period daily --dry-run         # 试运行（不发送通知）
"""

import argparse
import sys
import logging
from datetime import datetime, timedelta
import pytz

from .config import Config
from .notion_client import NotionClient
from .summarizer import TaskSummarizer
from .llm_client import LLMClient
from .notifier import Notifier
from .utils import setup_logger
from dotenv import load_dotenv

# 加载环境变量
load_dotenv()

logger = setup_logger("task_master.main")


def handle_daily_report(notion: NotionClient, summarizer: TaskSummarizer,
                        llm: LLMClient, is_yesterday: bool = False) -> str:
    """处理日报生成"""
    if is_yesterday:
        # 获取昨天的任务（解决时区问题）
        tz = pytz.timezone(notion.config.timezone)
        now = datetime.now(tz)
        yesterday = (now - timedelta(days=1)).date()

        logger.info(f"⏰ 当前时间: {now.strftime('%Y-%m-%d %H:%M:%S %Z')}")
        logger.info(f"📅 生成昨天({yesterday})的日报")

        tasks = notion.get_yesterday_tasks()
    else:
        # 获取今天的任务
        tasks = notion.query_period_tasks("daily")

    logger.info(f"📋 找到 {len(tasks)} 个已完成任务")

    if not tasks:
        return "# Daily Review\n\n暂无已完成任务，继续努力！💪"

    # 聚合统计
    stats, titles = summarizer.aggregate_tasks(tasks)
    logger.info(f"📊 统计: {stats}")

    # 构建提示词并生成总结
    prompt = summarizer.build_prompt(stats, titles, "daily")
    return llm.ask_llm(prompt)


def handle_three_days_report(notion: NotionClient, summarizer: TaskSummarizer,
                             llm: LLMClient) -> str:
    """处理三天趋势分析"""
    logger.info("🔄 开始三天趋势分析...")

    # 获取三天的数据
    three_days_data = {}
    three_days_stats = {}

    tz = pytz.timezone(notion.config.timezone)
    today = datetime.now(tz).date()

    for days_ago in [1, 2, 3]:  # 昨天、前天、大前天
        target_date = today - timedelta(days=days_ago)
        tasks = notion._query_tasks(target_date, target_date)

        logger.info(f"📅 {target_date}: 找到 {len(tasks)} 个任务")

        if tasks:
            stats, _ = summarizer.aggregate_tasks(tasks)
        else:
            # 空数据时的默认值
            stats = {
                "total": 0, "xp": 0, "cats": {}, "mit_count": 0,
                "mit_done": [], "mit_todo": [], "top_bias": [], "ent_minutes": 0,
                "start_time": "无", "end_time": "无", "focus_span": "无"
            }

        three_days_stats[target_date.isoformat()] = stats

    # 计算三天总计
    total_tasks = sum(s['total'] for s in three_days_stats.values())
    total_xp = sum(s['xp'] for s in three_days_stats.values())
    logger.info(f"📊 三天总计: {total_tasks} 个任务, {total_xp} XP")

    # 生成三天分析prompt
    prompt = summarizer.build_three_day_prompt(three_days_stats)

    # 调用LLM生成分析，增加token限制
    return llm.ask_llm(prompt, max_tokens=1200)


def handle_period_report(notion: NotionClient, summarizer: TaskSummarizer,
                         llm: LLMClient, period: str) -> str:
    """处理周报/月报"""
    tasks = notion.query_period_tasks(period)
    logger.info(f"📋 找到 {len(tasks)} 个已完成任务")

    if not tasks:
        return f"# {period.title()} Review\n\n暂无已完成任务，继续努力！💪"

    # 聚合统计
    stats, titles = summarizer.aggregate_tasks(tasks)
    logger.info(f"📊 统计: {stats}")

    # 构建提示词并生成总结
    prompt = summarizer.build_prompt(stats, titles, period)
    return llm.ask_llm(prompt)


def main():
    """主函数"""
    # CLI 参数
    parser = argparse.ArgumentParser(description="Generate periodical summaries")
    parser.add_argument(
        "--period",
        choices=["daily", "three-days", "weekly", "monthly"],
        required=True,
        help="Summary period to run"
    )
    parser.add_argument(
        "--yesterday",
        action="store_true",
        help="Generate report for yesterday (only for daily period)"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Skip all notifications - only print summary"
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Enable verbose logging"
    )
    args = parser.parse_args()

    # 设置日志级别
    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)
        logger.setLevel(logging.DEBUG)

    # 加载配置
    cfg = Config.from_env()

    # 调试信息
    logger.info(f"🔧 配置加载完成:")
    logger.info(f"   - NOTION_TOKEN: {'已设置' if cfg.notion_token else '未设置'}")
    logger.info(f"   - NOTION_DB_ID: {cfg.notion_db_id if cfg.notion_db_id else '未设置'}")
    logger.info(f"   - LLM_PROVIDER: {cfg.llm_provider}")
    logger.info(f"   - TIMEZONE: {cfg.timezone}")

    # 验证必要配置
    if not cfg.notion_token:
        logger.error("❌ 环境变量 NOTION_TOKEN 未设置")
        sys.exit(1)

    if not cfg.notion_db_id:
        logger.error("❌ 环境变量 NOTION_DB_ID 未设置")
        sys.exit(1)

    try:
        # 初始化组件
        notion = NotionClient(cfg)
        summarizer = TaskSummarizer()
        llm = LLMClient(cfg)
        notifier = Notifier(cfg)

        period = args.period
        logger.info("=" * 60)
        logger.info(f"🚀 Task-Master {period} 总结启动")
        logger.info(f"📅 时间: {datetime.now(pytz.timezone(cfg.timezone)).strftime('%Y-%m-%d %H:%M:%S %Z')}")
        logger.info(f"🔄 Dry-run: {args.dry_run}")
        logger.info("=" * 60)

        # 根据不同的period执行不同逻辑
        if period == "daily":
            answer = handle_daily_report(notion, summarizer, llm, args.yesterday)
        elif period == "three-days":
            answer = handle_three_days_report(notion, summarizer, llm)
        elif period in ["weekly", "monthly"]:
            answer = handle_period_report(notion, summarizer, llm, period)
        else:
            raise ValueError(f"不支持的周期: {period}")

        # 打印结果
        print("\n" + "=" * 60)
        print(answer)
        print("=" * 60 + "\n")

        # 发送通知
        if args.dry_run:
            logger.info("🏃 Dry-run mode → 不发送任何通知")
            return

        # 构建标题
        if period == "three-days":
            title = f"Task-Master 3-Day Trend Analysis · {datetime.now().date()}"
        elif period == "daily" and args.yesterday:
            yesterday = (datetime.now() - timedelta(days=1)).date()
            title = f"Task-Master Daily Review · {yesterday}"
        else:
            title = f"Task-Master {period.title()} Review · {datetime.now().date()}"

        # 发送通知
        push_results = notifier.notify_all(title, answer)

        # 统计结果
        succ = [k for k, v in push_results.items() if v]
        fail = [k for k, v in push_results.items() if not v]

        logger.info("=" * 60)
        logger.info(f"📨 推送完成:")
        logger.info(f"   ✅ 成功: {succ}")
        logger.info(f"   ❌ 失败: {fail}")
        logger.info("=" * 60)

    except Exception as e:
        logger.error(f"❌ 运行失败: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()