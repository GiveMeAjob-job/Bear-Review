from datetime import datetime

import pytz

from src.config import Config
from src.models import TaskRecord
from src.summarizer import TaskSummarizer


def build_task(**overrides):
    base = TaskRecord(
        id="1",
        title="任务A",
        category="Work",
        priority="MIT",
        scheduled_start=datetime.fromisoformat("2024-01-01T13:00:00+00:00"),
        scheduled_end=datetime.fromisoformat("2024-01-01T14:00:00+00:00"),
        xp=10,
        tomatoes=2,
        actual_minutes=60,
    )
    for key, value in overrides.items():
        setattr(base, key, value)
    return base


def test_get_detailed_stats_supports_normalized_tasks():
    summarizer = TaskSummarizer(Config(timezone="America/Toronto"))
    tasks = [
        build_task(),
        build_task(
            id="2",
            title="任务B",
            category="Health",
            priority="次要",
            xp=5,
            tomatoes=1,
            actual_minutes=30,
            scheduled_start=datetime.fromisoformat("2024-01-01T15:00:00+00:00"),
            scheduled_end=datetime.fromisoformat("2024-01-01T15:30:00+00:00"),
        ),
    ]

    stats, details = summarizer.get_detailed_stats(tasks)

    assert stats["total"] == 2
    assert stats["xp"] == 15
    assert stats["tomatoes"] == 3
    assert stats["mit_count"] == 1
    assert stats["cats"] == {"Work": 1, "Health": 1}
    assert details[0]["title"] == "任务A"


def test_build_prompt_keeps_backward_compatibility_with_title_list():
    summarizer = TaskSummarizer()
    stats = {
        "total": 2,
        "xp": 15,
        "cats": {"Work": 2},
        "mit_count": 1,
        "tomatoes": 3,
        "xp_per_tomato": 5,
    }

    prompt = summarizer.build_prompt(stats, ["任务1", "任务2"], "daily")

    assert "【当前数据与用户偏好】" in prompt
    assert "【输出要求】" in prompt
    assert "- 任务1" in prompt
    assert "- 任务2" in prompt
    assert "复盘标签" in prompt


def test_build_prompt_includes_focus_context():
    summarizer = TaskSummarizer()
    prompt = summarizer.build_prompt(
        {
            "total": 1,
            "xp": 10,
            "cats": {"Work": 1},
            "mit_count": 1,
            "tomatoes": 2,
            "xp_per_tomato": 5,
        },
        ["任务1"],
        "daily",
        focus_context="当前主题：做内容系统",
        coaching_context="当前模式：建设期模式",
    )

    assert "【当前焦点档案】" in prompt
    assert "【当前教练模式】" in prompt
    assert "当前主题：做内容系统" in prompt
    assert "当前模式：建设期模式" in prompt


def test_get_trend_stats_excludes_sleep_from_work_hours():
    summarizer = TaskSummarizer(Config(timezone="America/Toronto"))
    tasks = [
        build_task(title="Study block", category="Study"),
        build_task(
            id="2",
            title="睡觉",
            category="Sleep",
            priority="",
            xp=0,
            tomatoes=0,
            actual_minutes=0,
            scheduled_start=datetime.fromisoformat("2024-01-01T03:00:00+00:00"),
            scheduled_end=datetime.fromisoformat("2024-01-01T11:00:00+00:00"),
        ),
    ]

    stats = summarizer.get_trend_stats(tasks)

    assert stats["total"] == 2
    assert stats["sleep_hours"] == 8.0
    assert stats["actual_work_hours"] == 1.0


def test_build_preview_returns_compact_digest():
    summarizer = TaskSummarizer(Config(timezone="America/Toronto"))
    preview = summarizer.build_preview(
        "daily",
        {"total": 3, "xp": 20, "mit_count": 2},
        "# Daily Review\n\n今天不错，重点推进了核心任务。",
        intervention_summary="干预判断：记录即可 | 行动闭环：已观察到较强执行证据",
    )

    assert "日报速览" in preview
    assert "完成 3 项" in preview
    assert "干预判断" in preview


def test_build_decision_card_returns_action_focused_card():
    summarizer = TaskSummarizer(Config(timezone="America/Toronto"))
    card = summarizer.build_decision_card(
        "daily",
        {"total": 3, "xp": 20, "mit_count": 2},
        {
            "should_notify": True,
            "action_review": {"status": "partial", "previous_follow_up": "先剪视频再发布"},
            "anomalies": [{"summary": "MIT 直接掉到 0，主线推进断档"}],
            "principles": [
                {
                    "key": "soldier_on",
                    "name": "继续向前（soldier on）",
                    "summary": "局面差时先守住最小推进，不因为一轮失手就整体停摆。",
                    "action_rule": "把下一步压缩成低阻力、可完成的最小动作。",
                }
            ],
            "coaching_mode": {
                "key": "build",
                "name": "建设期模式",
                "current_stage": "从考试阶段切到内容系统建设期",
                "decision_rule": "建议必须朝证据最强的主线集中资源，弱信号方向自动降级。",
            },
        },
        "今天推进。\n下一轮跟进：下午先剪出第一条视频",
    )

    assert "日报决策卡" in card
    assert "当前判断：值得提醒" in card
    assert "上次动作：先剪视频再发布" in card
    assert "当前模式：建设期模式" in card
    assert "当前阶段：从考试阶段切到内容系统建设期" in card
    assert "模式策略：建议必须朝证据最强的主线集中资源，弱信号方向自动降级。" in card
    assert "当前原则：继续向前（soldier on）" in card
    assert "执行口径：把下一步压缩成低阻力、可完成的最小动作。" in card
    assert "现在只跟一件事：下午先剪出第一条视频" in card
