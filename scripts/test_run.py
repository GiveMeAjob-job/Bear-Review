# scripts/test_run.py - 本地测试脚本
"""
本地测试运行脚本
用于在部署前测试系统功能
"""

import os
import sys
from datetime import datetime

# 添加 src 目录到路径
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from config import Config
from notion_client import NotionClient
from summarizer import TaskSummarizer
from llm_client import LLMClient


def test_system(period: str = "daily", dry_run: bool = True):
    """测试系统功能"""
    print(f"🧪 测试 {period} 总结功能\n")

    try:
        # 加载配置
        config = Config.from_env()
        print("✅ 配置加载成功")

        # 初始化组件
        notion_client = NotionClient(config)
        summarizer = TaskSummarizer()
        llm_client = LLMClient(config)
        print("✅ 组件初始化成功")

        # 查询任务
        print(f"🔍 查询 {period} 任务...")
        tasks = notion_client.query_period_tasks(period)
        print(f"📋 找到 {len(tasks)} 个已完成任务")

        if not tasks:
            print("⚠️  没有找到已完成任务，生成示例总结")
            summary = f"# {period.title()} Review\n\n暂无已完成任务，继续努力！💪"
        else:
            # 聚合统计
            stats, titles = summarizer.aggregate_tasks(tasks)
            print(f"📊 统计信息: {stats}")

            # 生成提示词
            prompt = summarizer.build_prompt(stats, titles, period)
            print(f"📝 生成提示词 ({len(prompt)} 字符)")

            # 调用 AI
            print("🤖 正在生成 AI 总结...")
            summary = llm_client.ask_llm(prompt)

        # 输出结果
        print("\n" + "=" * 50)
        print("📄 AI 总结结果:")
        print("=" * 50)
        print(summary)
        print("=" * 50)

        if not dry_run:
            print("\n📤 发送通知...")
            # 这里可以添加通知发送测试
        else:
            print("\n🏃 试运行模式，跳过通知发送")

        print("\n✅ 测试完成！")

    except Exception as e:
        print(f"\n❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="本地测试脚本")
    parser.add_argument("--period", choices=["daily", "weekly", "monthly"],
                        default="daily", help="测试周期")
    parser.add_argument("--no-dry-run", action="store_true",
                        help="实际发送通知")

    args = parser.parse_args()

    test_system(args.period, not args.no_dry_run)