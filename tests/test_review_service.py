import json
from datetime import date, datetime, timedelta

from src.config import Config
from src.engine_state import EngineStateStore
from src.focus_profile import FocusProfileStore
from src.models import TaskRecord
from src.review_memory import ReviewMemoryStore
from src.review_service import ReviewService
from src.summarizer import TaskSummarizer


class FakeNotion:
    def __init__(self, tasks=None, recent_tasks=None):
        self._tasks = tasks or []
        self._recent_tasks = recent_tasks if recent_tasks is not None else self._tasks

    def fetch_yesterday_tasks(self):
        return self._tasks

    def fetch_period_tasks(self, period):
        return self._tasks

    def fetch_tasks_for_date(self, target_date):
        return self._tasks

    def fetch_recent_tasks(self, days):
        return self._recent_tasks


class FakeLLM:
    def __init__(self, response="AI 总结"):
        self.response = response
        self.prompts = []

    def ask_llm(self, prompt, **kwargs):
        self.prompts.append((prompt, kwargs))
        return self.response


def test_generate_daily_report_builds_review():
    config = Config(notion_token="token", notion_db_id="db", timezone="America/Toronto")
    tasks = [
        TaskRecord(
            id="1",
            title="完成报告",
            category="Work",
            priority="MIT",
            xp=10,
            tomatoes=2,
        )
    ]
    service = ReviewService(
        config=config,
        notion=FakeNotion(tasks),
        summarizer=TaskSummarizer(config=config),
        llm=FakeLLM("今天推进顺利"),
        memory_store=ReviewMemoryStore("/tmp/nonexistent-memory.json"),
        focus_profile_store=FocusProfileStore("/tmp/nonexistent-focus-profile.json"),
        engine_state_store=EngineStateStore("/tmp/nonexistent-engine.json"),
    )

    report = service.generate_report("daily", is_yesterday=True)

    assert report.period == "daily"
    assert "Bear Review Daily Review" in report.title
    assert report.content == "今天推进顺利"
    assert "日报速览" in report.preview
    assert "干预判断" in report.preview
    assert "决策卡" in report.decision_card


def test_generate_empty_report_skips_llm():
    config = Config(notion_token="token", notion_db_id="db", timezone="America/Toronto")
    llm = FakeLLM()
    service = ReviewService(
        config=config,
        notion=FakeNotion([]),
        summarizer=TaskSummarizer(config=config),
        llm=llm,
        memory_store=ReviewMemoryStore("/tmp/nonexistent-memory.json"),
        focus_profile_store=FocusProfileStore("/tmp/nonexistent-focus-profile.json"),
    )

    report = service.generate_report("weekly")

    assert report.content
    assert llm.prompts == []


def test_generate_report_includes_focus_profile_context(tmp_path):
    focus_path = tmp_path / "focus.json"
    focus_path.write_text(
        json.dumps(
            {
                "current_focus": "把内容发布系统跑起来",
                "current_stage": "从考试型目标切到内容建设期",
                "coaching_mode": "build",
                "active_priorities": [
                    {"name": "每周发布 3 条视频", "keywords": ["视频", "剪辑", "发布"]},
                    {"name": "D333 冲刺", "keywords": ["D333"]},
                ],
                "completed_items": ["CPA"],
                "last_updated": "2026-03-24",
                "evidence_window_days": 21,
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    llm = FakeLLM("今天推进顺利")
    service = ReviewService(
        config=Config(notion_token="token", notion_db_id="db", timezone="America/Toronto"),
        notion=FakeNotion(
            tasks=[
                TaskRecord(
                    id="1",
                    title="剪视频",
                    category="Content",
                    priority="MIT",
                    scheduled_start=datetime.fromisoformat("2026-03-24T13:00:00+00:00"),
                    xp=10,
                    tomatoes=2,
                )
            ],
            recent_tasks=[
                TaskRecord(
                    id="1",
                    title="剪视频",
                    category="Content",
                    priority="MIT",
                    scheduled_start=datetime.fromisoformat("2026-03-24T13:00:00+00:00"),
                    xp=10,
                    tomatoes=2,
                )
            ],
        ),
        summarizer=TaskSummarizer(config=Config(timezone="America/Toronto")),
        llm=llm,
        memory_store=ReviewMemoryStore(str(tmp_path / "memory.json")),
        focus_profile_store=FocusProfileStore(str(focus_path)),
        engine_state_store=EngineStateStore(str(tmp_path / "engine.json")),
    )

    service.generate_report("daily")

    prompt = llm.prompts[0][0]
    assert "【当前焦点档案】" in prompt
    assert "【当前教练模式】" in prompt
    assert "【干预系统判断】" in prompt
    assert "本系统默认采用以下逆境原则" in prompt
    assert "当前模式：建设期模式" in prompt
    assert "把内容发布系统跑起来" in prompt
    assert "当前优先级（近期有任务证据支持）" in prompt
    assert "每周发布 3 条视频" in prompt
    assert "自动降权优先级" in prompt
    assert "D333 冲刺" in prompt


def test_generate_report_enters_dormancy_and_skips_llm(tmp_path):
    focus_path = tmp_path / "focus.json"
    focus_path.write_text(
        json.dumps(
            {
                "current_focus": "等待新主线",
                "auto_dormancy": {
                    "enabled": True,
                    "idle_after_days": 10,
                    "reminder_interval_days": 5,
                    "restart_message": "先做一个最小动作，让系统重新启动起来。",
                },
                "last_updated": "2026-03-24",
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    llm = FakeLLM("不应被调用")
    service = ReviewService(
        config=Config(notion_token="token", notion_db_id="db", timezone="America/Toronto"),
        notion=FakeNotion(tasks=[], recent_tasks=[]),
        summarizer=TaskSummarizer(config=Config(timezone="America/Toronto")),
        llm=llm,
        memory_store=ReviewMemoryStore(str(tmp_path / "memory.json")),
        focus_profile_store=FocusProfileStore(str(focus_path)),
        engine_state_store=EngineStateStore(str(tmp_path / "engine.json")),
    )

    report = service.generate_report("daily")

    assert llm.prompts == []
    assert "自动熄火状态" in report.content
    assert report.signals["delivery_policy"] == "suppress"
    assert report.signals["dormancy"]["is_dormant"] is True


def test_generate_report_sends_restart_nudge_when_due(tmp_path):
    focus_path = tmp_path / "focus.json"
    focus_path.write_text(
        json.dumps(
            {
                "current_focus": "等待新主线",
                "auto_dormancy": {
                    "enabled": True,
                    "idle_after_days": 10,
                    "reminder_interval_days": 3,
                    "restart_message": "先做一个最小动作，让系统重新启动起来。",
                },
                "last_updated": "2026-03-24",
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    engine_store = EngineStateStore(str(tmp_path / "engine.json"))
    engine_store.load()
    dormant_since = date.today() - timedelta(days=8)
    last_nudge = date.today() - timedelta(days=4)
    engine_store.state.dormant_since = dormant_since.isoformat()
    engine_store.state.last_active_date = (date.today() - timedelta(days=12)).isoformat()
    engine_store.state.last_restart_nudge_date = last_nudge.isoformat()
    engine_store.save()

    service = ReviewService(
        config=Config(notion_token="token", notion_db_id="db", timezone="America/Toronto"),
        notion=FakeNotion(tasks=[], recent_tasks=[]),
        summarizer=TaskSummarizer(config=Config(timezone="America/Toronto")),
        llm=FakeLLM("不应被调用"),
        memory_store=ReviewMemoryStore(str(tmp_path / "memory.json")),
        focus_profile_store=FocusProfileStore(str(focus_path)),
        engine_state_store=engine_store,
    )

    report = service.generate_report("daily")

    assert "自动熄火决策卡" in report.decision_card
    assert report.signals["delivery_policy"] == "restart_nudge"
    assert report.signals["should_notify"] is True
