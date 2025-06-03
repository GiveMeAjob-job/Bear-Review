# src/main.py - 🔄 主程序优化
import argparse
import sys
from datetime import datetime
from .config import Config
from .notion_client import NotionClient
from .summarizer import TaskSummarizer
from .llm_client import LLMClient
from .notifier import Notifier
from .utils import setup_logger

logger = setup_logger(__name__)


def main():
    """主程序入口"""
    try:
        # 解析命令行参数
        parser = argparse.ArgumentParser(description="Task Master 自动总结工具")
        parser.add_argument(
            "--period",
            choices=["daily", "weekly", "monthly"],
            required=True,
            help="总结周期"
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="试运行，不发送通知"
        )
        parser.add_argument(
            "--verbose",
            action="store_true",
            help="详细日志输出"
        )

        args = parser.parse_args()

        if args.verbose:
            logger.setLevel(logging.DEBUG)

        # 加载配置
        config = Config.from_env()

        # 验证必要配置
        if not config.notion_token or not config.notion_db_id:
            logger.error("Notion配置缺失，请检查环境变量")
            sys.exit(1)

        # 初始化组件
        notion_client = NotionClient(config)
        summarizer = TaskSummarizer()
        llm_client = LLMClient(config)
        notifier = Notifier(config)

        logger.info(f"开始执行 {args.period} 总结任务")

        # 查询任务
        tasks = notion_client.query_period_tasks(args.period)

        if not tasks:
            logger.warning(f"未找到 {args.period} 的已完成任务")
            summary = f"# {args.period.title()} Review\n\n今天还没有完成任何任务，加油！💪"
        else:
            # 聚合统计
            stats, titles = summarizer.aggregate_tasks(tasks)

            # 生成AI总结
            prompt = summarizer.build_prompt(stats, titles, args.period)
            summary = llm_client.ask_llm(prompt)

        # 输出总结
        print("=" * 50)
        print(summary)
        print("=" * 50)

        # 发送通知（除非是试运行）
        if not args.dry_run:
            title = f"Task Master {args.period.title()} Review - {datetime.now().strftime('%Y-%m-%d')}"
            results = notifier.notify_all(title, summary)

            success_count = sum(results.values())
            logger.info(f"通知发送完成: {success_count}/{len(results)} 成功")
        else:
            logger.info("试运行模式，跳过通知发送")

        logger.info(f"{args.period} 总结任务完成")

    except KeyboardInterrupt:
        logger.info("用户中断执行")
        sys.exit(0)
    except Exception as e:
        logger.error(f"执行失败: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()