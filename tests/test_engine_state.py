from datetime import date, datetime, timedelta

import json

from src.engine_state import DormancySettings, EngineStateStore
from src.models import TaskRecord


def build_task(day: date) -> TaskRecord:
    return TaskRecord(
        id=day.isoformat(),
        title="完成任务",
        category="Work",
        priority="MIT",
        scheduled_start=datetime.fromisoformat(f"{day.isoformat()}T13:00:00+00:00"),
    )


def test_engine_state_enters_dormancy_without_recent_activity(tmp_path):
    store = EngineStateStore(str(tmp_path / "engine.json"))
    today = date(2026, 3, 24)

    result = store.evaluate(
        settings=DormancySettings(enabled=True, idle_after_days=10, reminder_interval_days=5),
        current_tasks=[],
        recent_tasks=[],
        today=today,
    )

    assert result.is_dormant is True
    assert result.delivery_policy == "suppress"
    assert result.reminder_due is False


def test_engine_state_sends_restart_nudge_on_interval(tmp_path):
    store = EngineStateStore(str(tmp_path / "engine.json"))
    store.load()
    store.state.dormant_since = "2026-03-10"
    store.state.last_active_date = "2026-03-01"
    store.state.last_restart_nudge_date = "2026-03-15"
    store.save()

    result = store.evaluate(
        settings=DormancySettings(enabled=True, idle_after_days=10, reminder_interval_days=5),
        current_tasks=[],
        recent_tasks=[],
        today=date(2026, 3, 21),
    )

    assert result.is_dormant is True
    assert result.reminder_due is True
    assert result.delivery_policy == "restart_nudge"


def test_engine_state_wakes_when_activity_returns(tmp_path):
    store = EngineStateStore(str(tmp_path / "engine.json"))
    store.load()
    store.state.dormant_since = "2026-03-10"
    store.state.last_restart_nudge_date = "2026-03-15"
    store.save()
    today = date(2026, 3, 24)

    result = store.evaluate(
        settings=DormancySettings(enabled=True, idle_after_days=10, reminder_interval_days=5),
        current_tasks=[build_task(today)],
        recent_tasks=[build_task(today)],
        today=today,
    )

    assert result.is_dormant is False
    assert result.wake_detected is True
    assert result.delivery_policy == "normal"


def test_engine_state_round_trip_with_sqlite_backend(tmp_path):
    store = EngineStateStore(str(tmp_path / "state.db"))
    store.load()
    store.state.dormant_since = "2026-03-10"
    store.state.last_restart_nudge_date = "2026-03-15"
    store.save()

    reloaded = EngineStateStore(str(tmp_path / "state.db"))
    result = reloaded.evaluate(
        settings=DormancySettings(enabled=True, idle_after_days=10, reminder_interval_days=5),
        current_tasks=[],
        recent_tasks=[],
        today=date(2026, 3, 21),
    )

    assert result.is_dormant is True
    assert result.reminder_due is True


def test_engine_state_imports_legacy_json_into_sqlite(tmp_path):
    legacy_path = tmp_path / "engine.json"
    legacy_path.write_text(
        json.dumps(
            {
                "last_active_date": "2026-03-01",
                "dormant_since": "2026-03-10",
                "last_restart_nudge_date": "2026-03-15",
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    store = EngineStateStore(str(tmp_path / "state.db"))

    imported = store.maybe_import_json_file(str(legacy_path))
    result = store.evaluate(
        settings=DormancySettings(enabled=True, idle_after_days=10, reminder_interval_days=5),
        current_tasks=[],
        recent_tasks=[],
        today=date(2026, 3, 21),
    )

    assert imported is True
    assert result.reminder_due is True
