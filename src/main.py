# src/main.py
"""
Task-Master 入口脚本
python -m src.main --period daily        # 正常执行
python -m src.main --period daily --dry-run   # 只打印总结，不发通知
"""
import argparse
import sys
from datetime import datetime

from .config import Config
from .notion_client import NotionClient
from .summarizer import TaskSummarizer
from .llm_client import LLMClient
from .notifier import Notifier
from .utils import setup_logger
from dotenv import load_dotenv
logger = setup_logger("task_master.main")


def main():
    """主函数"""
    # CLI 参数
    parser = argparse.ArgumentParser(description="Generate periodical summaries")
    parser.add_argument(
        "--period",
        choices=["daily", "weekly", "monthly"],
        required=True,
        help="Summary period to run"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Skip all notifications - only print summary"
    )
    args = parser.parse_args()

    # 设置日志级别
    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)
        logger.setLevel(logging.DEBUG)

    # 环境 & 配置
    cfg = Config.from_env()

    # 调试信息
    logger.info(f"配置加载完成:")
    logger.info(f"- NOTION_TOKEN: {'已设置' if cfg.notion_token else '未设置'}")
    logger.info(f"- NOTION_DB_ID: {cfg.notion_db_id if cfg.notion_db_id else '未设置'}")
    logger.info(f"- LLM_PROVIDER: {cfg.llm_provider}")

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
        logger.info(f"🟢 开始 {period} 总结 - dry-run={args.dry_run}")

        # 查询任务
        tasks = notion.query_period_tasks(period)
        logger.info(f"📋 找到 {len(tasks)} 个已完成任务")

        if not tasks:
            answer = f"# {period.title()} Review\n\n暂无已完成任务，继续努力！💪"
        else:
            # 聚合统计
            stats, titles = summarizer.aggregate_tasks(tasks)
            logger.info(f"📊 统计: {stats}")

            # 构建提示词
            prompt = summarizer.build_prompt(stats, titles, period)

            # 调用 LLM 生成总结
            answer = llm.ask_llm(prompt)

        # 打印结果
        print("\n" + "=" * 60)
        print(answer)
        print("=" * 60 + "\n")

        # 通知
        if args.dry_run:
            logger.info("Dry-run mode → 不发送任何通知")
            return

        title = f"Task-Master {period.title()} Review · {datetime.now().date()}"
        push_results = notifier.notify_all(title, answer)

        succ = [k for k, v in push_results.items() if v]
        fail = [k for k, v in push_results.items() if not v]

        logger.info(f"📨 推送完成: 成功={succ}, 失败={fail}")

    except Exception as e:
        logger.error(f"❌ 运行失败: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()