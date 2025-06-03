# src/main.py
"""
Task-Master 入口脚本
python -m src.main --period daily        # 正常执行
python -m src.main --period daily --dry-run   # 只打印总结，不发通知
"""
from __future__ import annotations

import argparse
import os
import sys
from datetime import datetime

# 相对导入：保证在“src”作为 package 时可用
from . import notion_client, summarizer, llm_client, notifier, config, utils

logger = utils.setup_logger("task_master.main")

# ──────────────────────── CLI 参数 ────────────────────────
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

# ──────────────────────── 环境 & 配置 ────────────────────────
cfg = config.Config.from_env()
if not cfg.notion_db_id:
    logger.error("❌ 环境变量 NOTION_DB_ID 未设置")
    sys.exit(1)

# ──────────────────────── 查询任务 ────────────────────────
period = args.period
logger.info(f"🟢 Start {period} summarization - dry-run={args.dry_run}")

if period == "daily":
    tasks = notion_client.query_today_tasks(cfg.notion_db_id)
    prompt = summarizer.build_daily_prompt(tasks)
elif period == "weekly":
    tasks = notion_client.query_this_week_tasks(cfg.notion_db_id)
    prompt = summarizer.build_weekly_prompt(tasks)
elif period == "monthly":
    tasks = notion_client.query_this_month_tasks(cfg.notion_db_id)
    prompt = summarizer.build_monthly_prompt(tasks)
else:                         # 逻辑上不会到这
    raise ValueError(f"Unsupported period: {period}")

# ──────────────────────── 调用 LLM 生成总结 ────────────────────────
answer = llm_client.ask_llm(prompt)
print("\n" + "=" * 60)
print(answer)
print("=" * 60 + "\n")

# ──────────────────────── 通知 ────────────────────────
if args.dry_run:
    logger.info("Dry-run mode → 不发送任何通知")
    sys.exit(0)

title = f"Task-Master {period.title()} Review · {datetime.now().date()}"
push_results = notifier.notify_all(title, answer)
succ = [k for k, v in push_results.items() if v]
fail = [k for k, v in push_results.items() if not v]

logger.info(f"📨 Push done: success={succ}, fail={fail}")
