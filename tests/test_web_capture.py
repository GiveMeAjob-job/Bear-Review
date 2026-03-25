from datetime import datetime

import pytz

from src.engine_state import EngineStateStore
from src.focus_profile import FocusProfileStore
from src.models import ReviewReport, TaskAlias, TaskRecord
from src.review_memory import ReviewMemoryStore
from src.web_capture import build_capture_page, build_dashboard_snapshot, normalize_submission


def test_build_capture_page_renders_recent_tasks():
    task = TaskRecord(
        id="1",
        title="剪完第一条视频",
        category="Content",
        priority="MIT",
        scheduled_start=datetime.fromisoformat("2026-03-24T13:30:00+00:00"),
        xp=10,
        tomatoes=2,
        raw={"note": "先完成粗剪。"},
    )
    second_task = TaskRecord(
        id="2",
        title="背完一章",
        category="Study",
        priority="重要",
        scheduled_start=datetime.fromisoformat("2026-03-23T13:30:00+00:00"),
        xp=5,
        tomatoes=1,
    )
    third_task = TaskRecord(
        id="3",
        title="出门买菜",
        category="Life",
        priority="",
        scheduled_start=datetime.fromisoformat("2026-03-22T13:30:00+00:00"),
        xp=0,
        tomatoes=0,
    )
    manual_alias = TaskAlias(
        id="91",
        alias_name="视频粗剪",
        title="剪完第一条视频",
        category="Content",
        priority="MIT",
        actual_minutes=45,
        tomatoes=2,
        note="保留粗剪结构",
    )
    dashboard = build_dashboard_snapshot(
        tasks=[task, second_task, third_task],
        manual_aliases=[manual_alias],
        timezone="America/Toronto",
    )

    html = build_capture_page(
        [task, second_task, third_task],
        timezone="America/Toronto",
        message="已记录：剪完第一条视频",
        form_values={
            "task_id": "1",
            "title": "剪完第一条视频",
            "category": "Content",
            "priority": "MIT",
            "task_date": "2026-03-24",
            "start": "09:30",
            "minutes": "45",
            "tomatoes": "2",
            "xp": "10",
            "note": "先完成粗剪。",
        },
        form_mode="edit",
        active_task_id="1",
        manual_aliases=[manual_alias],
        active_alias_id="91",
        dashboard=dashboard,
    )

    assert "Bear Review Capture" in html
    assert "首页控制台" in html
    assert "当前主线" in html
    assert "当前建议动作" in html
    assert "系统状态" in html
    assert "更新首页控制台" in html
    assert "剪完第一条视频" in html
    assert "已记录：剪完第一条视频" in html
    assert "保存修改" in html
    assert "常用别名" in html
    assert "手工别名" in html
    assert "视频粗剪" in html
    assert "保存为手工别名" in html
    assert "删除别名" in html
    assert "编辑别名" in html
    assert "alias_name" in html
    assert "一键 MIT" in html
    assert "今天" in html
    assert "现在开始" in html
    assert "结束=开始+时长" in html
    assert "复制上一条时间 09:30 / 30 分钟" in html
    assert "上一条做变体" in html
    assert "最近分类" in html
    assert "高频模板" in html
    assert "Study" in html
    assert "Life" in html
    assert "Alias" in html
    assert "/?variant=1&focus=1#task-1" in html
    assert "复用" in html
    assert "删除" in html
    assert "row-active" in html
    assert "id='task-1'" in html
    assert "data-label='操作'" in html
    assert "先完成粗剪。" in html


def test_normalize_submission_parses_form_values():
    payload = normalize_submission(
        {
            "title": "剪完第一条视频",
            "category": "Content",
            "priority": "MIT",
            "task_date": "2026-03-24",
            "start": "09:30",
            "end": "10:15",
            "minutes": "45",
            "tomatoes": "2",
            "xp": "10",
            "note": "先完成粗剪。",
        },
        timezone="America/Toronto",
    )

    tz = pytz.timezone("America/Toronto")
    assert payload["title"] == "剪完第一条视频"
    assert payload["category"] == "Content"
    assert payload["priority"] == "MIT"
    assert payload["actual_minutes"] == 45
    assert payload["tomatoes"] == 2
    assert payload["xp"] == 10
    assert payload["scheduled_start"].astimezone(tz).strftime("%H:%M") == "09:30"
    assert payload["scheduled_end"].astimezone(tz).strftime("%H:%M") == "10:15"


def test_build_capture_page_renders_template_links():
    task = TaskRecord(
        id="2",
        title="写完 CPA 总结",
        category="Study",
        priority="重要",
        scheduled_start=datetime.fromisoformat("2026-03-24T16:00:00+00:00"),
        xp=5,
        tomatoes=1,
    )
    duplicate = TaskRecord(
        id="3",
        title="写完 CPA 总结",
        category="Study",
        priority="重要",
        scheduled_start=datetime.fromisoformat("2026-03-23T16:00:00+00:00"),
        xp=5,
        tomatoes=1,
    )

    html = build_capture_page([task, duplicate], timezone="America/Toronto", form_mode="reuse")

    assert "/?alias=2&focus=2#task-2" in html
    assert "/?variant=2&focus=2#task-2" in html
    assert "/?reuse=2&focus=2#task-2" in html
    assert "/?edit=2&focus=2#task-2" in html
    assert "x2" in html
    assert "已载入模板" not in html


def test_build_capture_page_renders_manual_alias_links():
    task = TaskRecord(
        id="2",
        title="写完 CPA 总结",
        category="Study",
        priority="重要",
        scheduled_start=datetime.fromisoformat("2026-03-24T16:00:00+00:00"),
        xp=5,
        tomatoes=1,
    )
    manual_alias = TaskAlias(
        id="5",
        alias_name="CPA 总结",
        title="写完 CPA 总结",
        category="Study",
        priority="重要",
        actual_minutes=40,
        tomatoes=1,
    )

    html = build_capture_page(
        [task],
        timezone="America/Toronto",
        manual_aliases=[manual_alias],
        active_alias_id="5",
    )

    assert "/?manual_alias=5&alias_focus=5#alias-5" in html
    assert "/?edit_alias=5&alias_focus=5#alias-5" in html
    assert "删除别名" in html
    assert "alias-card is-active" in html


def test_build_capture_page_uses_recent_categories_and_mobile_labels():
    tasks = [
        TaskRecord(
            id="10",
            title="剪视频",
            category="Content",
            priority="MIT",
            scheduled_start=datetime.fromisoformat("2026-03-24T13:00:00+00:00"),
        ),
        TaskRecord(
            id="11",
            title="学习审计",
            category="Study",
            priority="重要",
            scheduled_start=datetime.fromisoformat("2026-03-23T13:00:00+00:00"),
        ),
        TaskRecord(
            id="12",
            title="出门办事",
            category="Life",
            priority="",
            scheduled_start=datetime.fromisoformat("2026-03-22T13:00:00+00:00"),
        ),
        TaskRecord(
            id="13",
            title="健康散步",
            category="Health",
            priority="",
            scheduled_start=datetime.fromisoformat("2026-03-21T13:00:00+00:00"),
        ),
    ]

    html = build_capture_page(tasks, timezone="America/Toronto")

    assert "最近分类" in html
    assert "Content" in html
    assert "Study" in html
    assert "Life" in html
    assert "Health" in html
    assert "td[data-label]::before" in html


def test_build_dashboard_snapshot_reads_focus_memory_and_engine_state(tmp_path):
    db_path = tmp_path / "state.db"
    tz = pytz.timezone("America/Toronto")
    current_local_day = datetime.now(tz).date()
    current_start = tz.localize(datetime.combine(current_local_day, datetime.min.time())).astimezone(pytz.UTC)
    focus_store = FocusProfileStore(str(db_path))
    focus_store.ensure_default_exists()
    profile = focus_store.load()
    profile.current_focus = "把内容系统跑起来"
    profile.current_stage = "建设期"
    profile.coaching_mode = "build"
    profile.coaching_notes = "优先沉淀系统资产"
    focus_store.save(profile)

    memory_store = ReviewMemoryStore(str(db_path))
    memory_store.record_report(
        report=ReviewReport(
            period="daily",
            title="Daily",
            content="复盘标签：主线推进\n下一轮跟进：先剪第一条视频",
            preview="日报速览：推进内容主线",
            stats={"total": 2, "xp": 10, "mit_count": 1},
        ),
        generated_at=datetime.now(tz).isoformat(),
    )
    memory_store.save()

    engine_store = EngineStateStore(str(db_path))
    engine_store.load()
    engine_store.state.last_active_date = current_local_day.isoformat()
    engine_store.save()

    alias = TaskAlias(
        id="1",
        alias_name="视频粗剪",
        title="剪完第一条视频",
        category="Content",
        priority="MIT",
        actual_minutes=45,
        tomatoes=2,
    )
    snapshot = build_dashboard_snapshot(
        tasks=[
            TaskRecord(
                id="1",
                title="剪完第一条视频",
                category="Content",
                priority="MIT",
                scheduled_start=current_start,
                actual_minutes=45,
            )
        ],
        manual_aliases=[alias],
        timezone="America/Toronto",
        focus_profile_store=focus_store,
        memory_store=memory_store,
        engine_state_store=engine_store,
    )

    assert snapshot.current_focus == "把内容系统跑起来"
    assert snapshot.coaching_mode_name == "建设期模式"
    assert snapshot.next_action == "先剪第一条视频"
    assert snapshot.tasks_today == 1
    assert snapshot.manual_alias_count == 1
    assert snapshot.is_dormant is False
