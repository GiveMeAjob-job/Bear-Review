from __future__ import annotations

import argparse
from datetime import date, datetime, time
from typing import Optional

import pytz

from .config import Config
from .engine_state import EngineStateStore
from .focus_profile import FocusProfileStore
from .review_memory import ReviewMemoryStore
from .sqlite_task_store import SQLiteTaskStore
from .web_capture import run_capture_server

DEFAULT_MEMORY_FILE = ".bear_review/review_memory.json"
DEFAULT_FOCUS_PROFILE_FILE = ".bear_review/focus_profile.json"
DEFAULT_ENGINE_STATE_FILE = ".bear_review/engine_state.json"


def _parse_local_datetime(raw_date: str, raw_time: str, timezone: str) -> datetime:
    tz = pytz.timezone(timezone)
    parsed_date = date.fromisoformat(raw_date)
    parsed_time = time.fromisoformat(raw_time)
    return tz.localize(datetime.combine(parsed_date, parsed_time))


def main() -> None:
    parser = argparse.ArgumentParser(description="Quick capture for local Bear Review tasks")
    parser.add_argument(
        "--db-path",
        help="Override sqlite database path for local task capture",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    done_parser = subparsers.add_parser("done", help="Record one completed task")
    done_parser.add_argument("title", help="Completed task title")
    done_parser.add_argument("--category", default="未分类", help="Task category")
    done_parser.add_argument("--priority", default="", help="Task priority, for example MIT")
    done_parser.add_argument("--minutes", type=int, default=0, help="Actual minutes spent")
    done_parser.add_argument("--tomatoes", type=int, default=0, help="Pomodoro count")
    done_parser.add_argument("--xp", type=int, help="Override XP")
    done_parser.add_argument("--date", dest="task_date", help="Task date in YYYY-MM-DD")
    done_parser.add_argument("--start", default="09:00", help="Start time in HH:MM")
    done_parser.add_argument("--end", help="End time in HH:MM")
    done_parser.add_argument("--note", default="", help="Optional note")

    recent_parser = subparsers.add_parser("recent", help="Show recent completed tasks")
    recent_parser.add_argument("--limit", type=int, default=10, help="How many tasks to show")

    serve_parser = subparsers.add_parser("serve", help="Run a lightweight local web capture page")
    serve_parser.add_argument("--host", default="127.0.0.1", help="Host to bind the local server")
    serve_parser.add_argument("--port", type=int, default=8765, help="Port for the local server")

    args = parser.parse_args()
    cfg = Config.from_env()
    if args.db_path:
        cfg.sqlite_db_path = args.db_path

    store = SQLiteTaskStore(cfg)
    _prepare_unified_state(cfg)

    if args.command == "done":
        today = datetime.now(pytz.timezone(cfg.timezone)).date().isoformat()
        task_date = args.task_date or today
        start_dt = _parse_local_datetime(task_date, args.start, cfg.timezone)
        end_dt: Optional[datetime] = None
        if args.end:
            end_dt = _parse_local_datetime(task_date, args.end, cfg.timezone)

        task = store.record_done_task(
            title=args.title,
            category=args.category,
            priority=args.priority,
            scheduled_start=start_dt,
            scheduled_end=end_dt,
            xp=args.xp,
            tomatoes=args.tomatoes,
            actual_minutes=args.minutes,
            note=args.note,
        )
        print(f"已记录: {task.title} | {task.category} | {task.priority or '无优先级'}")
        return

    if args.command == "serve":
        run_capture_server(store, cfg, host=args.host, port=args.port)
        return

    tasks = store.recent_done_tasks(limit=args.limit)
    if not tasks:
        print("最近没有已完成任务。")
        return

    for task in tasks:
        start_str = task.scheduled_start.astimezone(pytz.timezone(cfg.timezone)).strftime("%Y-%m-%d %H:%M") if task.scheduled_start else "无时间"
        print(f"- {start_str} | {task.title} | {task.category} | {task.priority or '无优先级'}")


def _prepare_unified_state(cfg: Config) -> None:
    memory_store = ReviewMemoryStore(cfg.sqlite_db_path)
    focus_store = FocusProfileStore(cfg.sqlite_db_path)
    engine_store = EngineStateStore(cfg.sqlite_db_path)
    memory_store.maybe_import_json_file(DEFAULT_MEMORY_FILE)
    focus_store.maybe_import_json_file(DEFAULT_FOCUS_PROFILE_FILE)
    engine_store.maybe_import_json_file(DEFAULT_ENGINE_STATE_FILE)
    focus_store.ensure_default_exists()


if __name__ == "__main__":
    main()
