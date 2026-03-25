"""
本地测试运行脚本

用于在部署前快速验证 Notion 拉取、总结生成和通知策略。
"""

import argparse
import sys
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.config import Config
from src.llm_client import LLMClient
from src.notion_client import NotionClient
from src.review_service import ReviewService
from src.summarizer import TaskSummarizer

load_dotenv()


def test_system(period: str = "daily", yesterday: bool = False) -> None:
    print(f"🧪 测试 {period} 总结功能\n")

    try:
        config = Config.from_env()
        config.validate_runtime()
        notion_client = NotionClient(config)
        summarizer = TaskSummarizer(config=config)
        llm_client = LLMClient(config)
        service = ReviewService(config, notion_client, summarizer, llm_client)

        report = service.generate_report(period, is_yesterday=yesterday)

        print("=" * 60)
        print(report.title)
        print("=" * 60)
        print(report.content)
        print("\n--- 通知预览 ---")
        print(report.preview)
        print("=" * 60)
    except Exception as exc:
        print(f"\n❌ 测试失败: {exc}")
        import traceback

        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="本地测试脚本")
    parser.add_argument(
        "--period",
        choices=["daily", "three-days", "weekly", "monthly"],
        default="daily",
        help="测试周期",
    )
    parser.add_argument(
        "--yesterday",
        action="store_true",
        help="日报测试时生成昨天的数据",
    )
    args = parser.parse_args()

    test_system(args.period, args.yesterday)
