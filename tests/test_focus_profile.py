import json
from datetime import datetime

from src.focus_profile import FocusProfileStore
from src.models import TaskRecord


def test_focus_profile_context_marks_completed_items(tmp_path):
    path = tmp_path / "focus_profile.json"
    payload = {
        "current_focus": "把内容系统跑起来",
        "active_priorities": ["建立稳定发布节奏"],
        "completed_items": ["D333", "CPA"],
        "last_updated": "2026-03-24",
        "stale_after_days": 14,
    }
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")

    context = FocusProfileStore(str(path)).build_context()

    assert "当前主题：把内容系统跑起来" in context
    assert "建立稳定发布节奏" in context
    assert "已完成项目" in context
    assert "D333" in context
    assert "CPA" in context


def test_focus_profile_context_includes_stage_and_mode(tmp_path):
    path = tmp_path / "focus_profile.json"
    path.write_text(
        json.dumps(
            {
                "current_focus": "把内容系统跑起来",
                "current_stage": "从考试型阶段切到内容建设期",
                "coaching_mode": "build",
                "coaching_notes": "现在优先做能沉淀成系统的工作。",
                "last_updated": "2026-03-24",
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    store = FocusProfileStore(str(path))

    context = store.build_context()
    coaching_context = store.build_coaching_context()
    payload = store.coaching_payload()

    assert "当前阶段：从考试型阶段切到内容建设期" in context
    assert "当前模式：建设期模式" in coaching_context
    assert "模式策略：" in coaching_context
    assert payload["key"] == "build"


def test_focus_profile_parses_auto_dormancy(tmp_path):
    path = tmp_path / "focus_profile.json"
    path.write_text(
        json.dumps(
            {
                "current_focus": "把内容系统跑起来",
                "auto_dormancy": {
                    "enabled": True,
                    "idle_after_days": 12,
                    "reminder_interval_days": 4,
                    "restart_message": "先做一个最小动作，把系统重新点起来。",
                },
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    settings = FocusProfileStore(str(path)).dormancy_settings()

    assert settings.enabled is True
    assert settings.idle_after_days == 12
    assert settings.reminder_interval_days == 4
    assert "重新点起来" in settings.restart_message


def test_focus_profile_context_warns_when_stale(tmp_path):
    path = tmp_path / "focus_profile.json"
    payload = {
        "current_focus": "旧目标",
        "active_priorities": ["旧任务"],
        "last_updated": "2025-01-01",
        "stale_after_days": 7,
    }
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")

    context = FocusProfileStore(str(path)).build_context()

    assert "可能过期" in context


def test_focus_profile_store_can_bootstrap_default_file(tmp_path):
    path = tmp_path / "focus_profile.json"
    store = FocusProfileStore(str(path))

    store.ensure_default_exists()

    assert path.exists()
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert "active_priorities" in payload
    assert "evidence_window_days" in payload
    assert payload["coaching_mode"] == "adaptive"


def test_focus_profile_context_auto_deprioritizes_items_without_recent_evidence(tmp_path):
    path = tmp_path / "focus_profile.json"
    path.write_text(
        json.dumps(
            {
                "current_focus": "把内容系统跑起来",
                "active_priorities": [
                    {"name": "内容发布系统", "keywords": ["视频", "剪辑"]},
                    {"name": "D333 冲刺", "keywords": ["D333"]},
                ],
                "active_projects": [
                    {"name": "内容工作流", "keywords": ["视频", "封面"]},
                ],
                "last_updated": "2026-03-24",
                "evidence_window_days": 21,
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    recent_tasks = [
        TaskRecord(
            id="1",
            title="剪视频",
            category="Content",
            priority="MIT",
            scheduled_start=datetime.fromisoformat("2026-03-23T13:00:00+00:00"),
        )
    ]

    context = FocusProfileStore(str(path)).build_context(recent_tasks=recent_tasks)

    assert "当前优先级（近期有任务证据支持）" in context
    assert "内容发布系统" in context
    assert "自动降权优先级" in context
    assert "D333 冲刺" in context
    assert "当前活跃项目（近期有任务证据支持）" in context


def test_focus_profile_refresh_persists_last_seen(tmp_path):
    path = tmp_path / "focus_profile.json"
    path.write_text(
        json.dumps(
            {
                "current_focus": "把内容系统跑起来",
                "active_priorities": [
                    {"name": "内容发布系统", "keywords": ["视频", "剪辑"]},
                ],
                "last_updated": "2026-03-24",
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    store = FocusProfileStore(str(path))
    recent_tasks = [
        TaskRecord(
            id="1",
            title="剪视频",
            category="Content",
            priority="MIT",
            scheduled_start=datetime.fromisoformat("2026-03-24T13:00:00+00:00"),
        )
    ]

    store.build_context(recent_tasks=recent_tasks, persist_activity=True)

    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["active_priorities"][0]["last_seen"] == "2026-03-24"


def test_focus_profile_store_supports_sqlite_backend(tmp_path):
    path = tmp_path / "state.db"
    store = FocusProfileStore(str(path))
    store.ensure_default_exists()

    context = store.build_context()

    assert "当前主题" in context
    assert "当前优先级" in context


def test_focus_profile_store_imports_legacy_json_into_sqlite(tmp_path):
    legacy_path = tmp_path / "focus_profile.json"
    legacy_path.write_text(
        json.dumps(
            {
                "current_focus": "把内容系统跑起来",
                "active_priorities": ["建立稳定发布节奏"],
                "last_updated": "2026-03-24",
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    store = FocusProfileStore(str(tmp_path / "state.db"))

    imported = store.maybe_import_json_file(str(legacy_path))
    context = store.build_context()

    assert imported is True
    assert "把内容系统跑起来" in context
