from datetime import datetime

from src.intervention_engine import InterventionEngine
from src.models import ReviewReport, TaskRecord
from src.review_memory import ReviewMemoryStore


def build_task(title: str, category: str = "Work", priority: str = "MIT") -> TaskRecord:
    return TaskRecord(
        id=title,
        title=title,
        category=category,
        priority=priority,
        scheduled_start=datetime.fromisoformat("2026-03-24T13:00:00+00:00"),
        xp=10,
        tomatoes=2,
    )


def test_intervention_engine_marks_action_done_when_recent_tasks_match(tmp_path):
    memory = ReviewMemoryStore(str(tmp_path / "memory.json"))
    memory.record_report(
        ReviewReport(
            period="daily",
            title="Daily 1",
            content="复盘标签：主线推进\n下一轮跟进：先剪视频再发布",
            preview="日报速览：推进内容主线",
            stats={"total": 2, "xp": 20, "mit_count": 1, "tomatoes": 2, "work_hours": 2},
        ),
        generated_at="2026-03-23T02:20:00-04:00",
    )

    result = InterventionEngine().evaluate(
        "daily",
        current_stats={"total": 2, "xp": 20, "mit_count": 1, "tomatoes": 2, "work_hours": 2},
        current_tasks=[build_task("剪视频"), build_task("发布视频")],
        memory_store=memory,
        recent_tasks=[build_task("剪视频"), build_task("发布视频")],
        coaching_mode="build",
    )

    assert result.action_review.status == "done"
    assert result.should_notify is False
    assert result.principles
    assert any(item["key"] == "watch_for_real_opportunity" for item in result.principles)
    assert result.coaching_mode["key"] == "build"


def test_intervention_engine_raises_notify_when_output_drops_to_zero(tmp_path):
    memory = ReviewMemoryStore(str(tmp_path / "memory.json"))
    for index in range(2):
        memory.record_report(
            ReviewReport(
                period="daily",
                title=f"Daily {index}",
                content="复盘标签：主线推进\n下一轮跟进：先做最难 MIT",
                preview="日报速览：完成 3 项",
                stats={"total": 3, "xp": 30, "mit_count": 2, "tomatoes": 3, "work_hours": 3},
            ),
            generated_at=f"2026-03-2{index + 1}T02:20:00-04:00",
        )

    result = InterventionEngine().evaluate(
        "daily",
        current_stats={"total": 0, "xp": 0, "mit_count": 0, "tomatoes": 0, "work_hours": 0},
        current_tasks=[],
        memory_store=memory,
        recent_tasks=[],
        coaching_mode="recovery",
    )

    assert result.should_notify is True
    assert any(signal.key == "zero_output" for signal in result.anomalies)
    assert any(item["key"] == "soldier_on" for item in result.principles)
    assert any(item["key"] == "no_self_pity" for item in result.principles)


def test_intervention_engine_sprint_mode_notifies_more_aggressively(tmp_path):
    memory = ReviewMemoryStore(str(tmp_path / "sprint-memory.json"))
    memory.record_report(
        ReviewReport(
            period="daily",
            title="Daily Sprint",
            content="复盘标签：推进\n下一轮跟进：先交付第一版脚本",
            preview="日报速览：冲刺推进",
            stats={"total": 2, "xp": 20, "mit_count": 1, "tomatoes": 2, "work_hours": 2},
        ),
        generated_at="2026-03-23T02:20:00-04:00",
    )
    result = InterventionEngine().evaluate(
        "daily",
        current_stats={"total": 2, "xp": 12, "mit_count": 0, "tomatoes": 1, "work_hours": 1},
        current_tasks=[build_task("修正脚本", priority="次要")],
        recent_tasks=[build_task("修正脚本", priority="次要")],
        memory_store=memory,
        coaching_mode="sprint",
    )

    assert result.coaching_mode["key"] == "sprint"
    assert result.should_notify is True
