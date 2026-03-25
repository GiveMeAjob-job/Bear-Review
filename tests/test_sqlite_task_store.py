from datetime import date, datetime

from src.config import Config
from src.sqlite_task_store import SQLiteTaskStore


def build_config(tmp_path):
    return Config(
        task_source="sqlite",
        sqlite_db_path=str(tmp_path / "tasks.db"),
        timezone="America/Toronto",
    )


def test_sqlite_task_store_records_and_fetches_daily_tasks(tmp_path):
    store = SQLiteTaskStore(build_config(tmp_path))
    start = datetime.fromisoformat("2026-03-24T13:00:00-04:00")

    task = store.record_done_task(
        title="剪完第一条视频",
        category="Content",
        priority="MIT",
        scheduled_start=start,
        actual_minutes=45,
        tomatoes=2,
    )

    tasks = store.fetch_tasks_for_date(date(2026, 3, 24))

    assert task.title == "剪完第一条视频"
    assert len(tasks) == 1
    assert tasks[0].category == "Content"
    assert tasks[0].is_mit is True
    assert tasks[0].actual_minutes == 45


def test_sqlite_task_store_fetch_recent_tasks_respects_window(tmp_path):
    store = SQLiteTaskStore(build_config(tmp_path))
    store.record_done_task(
        title="旧任务",
        scheduled_start=datetime.fromisoformat("2026-03-01T10:00:00-05:00"),
    )
    store.record_done_task(
        title="新任务",
        scheduled_start=datetime.fromisoformat("2026-03-24T10:00:00-04:00"),
    )

    tasks = store.fetch_recent_tasks(7)

    assert [task.title for task in tasks] == ["新任务"]


def test_sqlite_task_store_updates_task_by_id(tmp_path):
    store = SQLiteTaskStore(build_config(tmp_path))
    task = store.record_done_task(
        title="剪完第一条视频",
        category="Content",
        priority="MIT",
        scheduled_start=datetime.fromisoformat("2026-03-24T09:30:00-04:00"),
        actual_minutes=45,
        tomatoes=2,
    )

    updated = store.update_done_task(
        task.id,
        title="剪完第二条视频",
        category="Content",
        priority="重要",
        scheduled_start=datetime.fromisoformat("2026-03-24T11:00:00-04:00"),
        actual_minutes=60,
        tomatoes=3,
        note="补了封面和字幕",
    )

    assert updated is not None
    assert updated.title == "剪完第二条视频"
    assert updated.priority == "重要"
    assert updated.actual_minutes == 60
    assert updated.raw["note"] == "补了封面和字幕"


def test_sqlite_task_store_deletes_task_by_id(tmp_path):
    store = SQLiteTaskStore(build_config(tmp_path))
    task = store.record_done_task(
        title="准备删除的任务",
        scheduled_start=datetime.fromisoformat("2026-03-24T09:30:00-04:00"),
    )

    deleted = store.delete_task(task.id)

    assert deleted is True
    assert store.get_task(task.id) is None


def test_sqlite_task_store_saves_and_lists_manual_aliases(tmp_path):
    store = SQLiteTaskStore(build_config(tmp_path))

    alias = store.save_task_alias(
        alias_name="视频粗剪",
        title="剪完第一条视频",
        category="Content",
        priority="MIT",
        actual_minutes=45,
        tomatoes=2,
        note="默认走粗剪流程",
    )

    aliases = store.list_task_aliases()

    assert alias.alias_name == "视频粗剪"
    assert aliases[0].title == "剪完第一条视频"
    assert aliases[0].note == "默认走粗剪流程"


def test_sqlite_task_store_updates_and_deletes_manual_aliases(tmp_path):
    store = SQLiteTaskStore(build_config(tmp_path))
    alias = store.save_task_alias(
        alias_name="审计复盘",
        title="背一章审计",
        category="Study",
        priority="重要",
        actual_minutes=30,
    )

    updated = store.save_task_alias(
        alias_name="审计复盘",
        title="背两章审计",
        category="Study",
        priority="重要",
        actual_minutes=50,
        alias_id=alias.id,
    )
    deleted = store.delete_task_alias(alias.id)

    assert updated.title == "背两章审计"
    assert updated.actual_minutes == 50
    assert deleted is True
    assert store.get_task_alias(alias.id) is None
