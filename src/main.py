import argparse
import json
import logging
import sys
from dataclasses import replace
from datetime import datetime
from pathlib import Path

import pytz
from dotenv import load_dotenv

from .coaching_modes import available_mode_keys
from .config import Config
from .engine_state import EngineStateStore
from .focus_profile import FocusProfileStore
from .llm_client import LLMClient
from .notifier import Notifier
from .review_memory import ReviewMemoryStore
from .review_service import ReviewService
from .summarizer import TaskSummarizer
from .task_source import create_task_source
from .utils import setup_logger

load_dotenv()

logger = setup_logger("bear_review.main")

DEFAULT_MEMORY_FILE = ".bear_review/review_memory.json"
DEFAULT_FOCUS_PROFILE_FILE = ".bear_review/focus_profile.json"
DEFAULT_ENGINE_STATE_FILE = ".bear_review/engine_state.json"


def _write_text_output(path_value: str, content: str) -> None:
    path = Path(path_value)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    logger.info("📝 已写入文件: %s", path)


def _write_metadata_output(path_value: str, report, cfg: Config, dry_run: bool) -> None:
    payload = {
        "period": report.period,
        "title": report.title,
        "preview": report.preview,
        "decision_card": report.decision_card,
        "stats": report.stats,
        "signals": report.signals,
        "notification_mode": cfg.notification_mode,
        "dry_run": dry_run,
        "generated_at": datetime.now(pytz.timezone(cfg.timezone)).isoformat(),
    }
    path = Path(path_value)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    logger.info("🧾 已写入元数据: %s", path)


def _resolve_state_path(cfg: Config, requested_path: str, default_json_path: str) -> str:
    if cfg.task_source == "sqlite" and requested_path == default_json_path:
        return cfg.sqlite_db_path
    return requested_path


def _maybe_import_legacy_state(store, legacy_path: str, effective_path: str) -> None:
    if legacy_path == effective_path:
        return
    importer = getattr(store, "maybe_import_json_file", None)
    if callable(importer):
        importer(legacy_path)


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate periodical summaries")
    parser.add_argument(
        "--period",
        choices=["daily", "three-days", "weekly", "monthly"],
        required=True,
        help="Summary period to run",
    )
    parser.add_argument(
        "--yesterday",
        action="store_true",
        help="Generate report for yesterday (only for daily period)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Skip all notifications and only print the summary",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Enable verbose logging",
    )
    parser.add_argument(
        "--notification-mode",
        choices=["disabled", "summary", "full", "smart"],
        help="Override notification mode from env",
    )
    parser.add_argument(
        "--output-file",
        help="Write the generated report content to a file",
    )
    parser.add_argument(
        "--preview-file",
        help="Write the generated preview content to a file",
    )
    parser.add_argument(
        "--decision-file",
        help="Write the generated decision card to a file",
    )
    parser.add_argument(
        "--metadata-file",
        help="Write report metadata as JSON to a file",
    )
    parser.add_argument(
        "--memory-file",
        default=DEFAULT_MEMORY_FILE,
        help="Path to the persistent review memory JSON file",
    )
    parser.add_argument(
        "--save-memory-in-dry-run",
        action="store_true",
        help="Persist generated review memory even when dry-run is enabled",
    )
    parser.add_argument(
        "--focus-profile-file",
        default=DEFAULT_FOCUS_PROFILE_FILE,
        help="Path to the current focus profile JSON file",
    )
    parser.add_argument(
        "--init-focus-profile",
        action="store_true",
        help="Create a default focus profile file if it does not exist",
    )
    parser.add_argument(
        "--coaching-mode",
        choices=available_mode_keys(),
        help="Override coaching mode for this run without changing focus_profile.json",
    )
    parser.add_argument(
        "--engine-state-file",
        default=DEFAULT_ENGINE_STATE_FILE,
        help="Path to the persistent engine state JSON file",
    )
    args = parser.parse_args()

    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)
        logger.setLevel(logging.DEBUG)

    cfg = Config.from_env()
    if args.notification_mode:
        cfg = replace(cfg, notification_mode=args.notification_mode)

    try:
        cfg.validate_runtime()
        notion = create_task_source(cfg)
        summarizer = TaskSummarizer(config=cfg)
        llm = LLMClient(cfg)
        memory_path = _resolve_state_path(cfg, args.memory_file, DEFAULT_MEMORY_FILE)
        focus_path = _resolve_state_path(cfg, args.focus_profile_file, DEFAULT_FOCUS_PROFILE_FILE)
        engine_path = _resolve_state_path(cfg, args.engine_state_file, DEFAULT_ENGINE_STATE_FILE)
        memory_store = ReviewMemoryStore(memory_path)
        focus_profile_store = FocusProfileStore(focus_path)
        engine_state_store = EngineStateStore(engine_path)
        _maybe_import_legacy_state(memory_store, args.memory_file, memory_path)
        _maybe_import_legacy_state(focus_profile_store, args.focus_profile_file, focus_path)
        _maybe_import_legacy_state(engine_state_store, args.engine_state_file, engine_path)
        if args.init_focus_profile:
            focus_profile_store.ensure_default_exists()
        review_service = ReviewService(
            cfg,
            notion,
            summarizer,
            llm,
            memory_store=memory_store,
            focus_profile_store=focus_profile_store,
            coaching_mode_override=args.coaching_mode or "",
            engine_state_store=engine_state_store,
        )
        notifier = Notifier(cfg)

        current_time = datetime.now(pytz.timezone(cfg.timezone)).strftime("%Y-%m-%d %H:%M:%S %Z")
        logger.info("🚀 Bear Review %s 总结启动", args.period)
        logger.info("📅 时间: %s", current_time)
        logger.info("🗂️ 任务源: %s", cfg.task_source)
        logger.info("🧱 状态存储: memory=%s focus=%s engine=%s", memory_path, focus_path, engine_path)
        logger.info("🔔 通知模式: %s", cfg.notification_mode)
        logger.info("🏃 Dry-run: %s", args.dry_run)

        report = review_service.generate_report(args.period, is_yesterday=args.yesterday)
        print("\n" + "=" * 60)
        print(report.content)
        print("=" * 60 + "\n")

        if args.output_file:
            _write_text_output(args.output_file, report.content)
        if args.preview_file:
            _write_text_output(args.preview_file, report.preview)
        if args.decision_file:
            _write_text_output(args.decision_file, report.decision_card)
        if args.metadata_file:
            _write_metadata_output(args.metadata_file, report, cfg, args.dry_run)

        if not args.dry_run or args.save_memory_in_dry_run:
            memory_store.record_report(
                report,
                generated_at=datetime.now(pytz.timezone(cfg.timezone)).isoformat(),
            )
            memory_store.save()

        if args.dry_run:
            logger.info("Dry-run 模式，不发送通知")
            return

        results = notifier.notify_report(report)
        success = [name for name, ok in results.items() if ok]
        failed = [name for name, ok in results.items() if not ok]
        logger.info("📨 推送完成: 成功=%s 失败=%s", success, failed)
    except Exception as exc:
        logger.error("❌ 运行失败: %s", exc)
        import traceback

        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
