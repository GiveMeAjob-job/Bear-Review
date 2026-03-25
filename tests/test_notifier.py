from unittest.mock import Mock, patch

from src.config import Config
from src.models import ReviewReport
from src.notifier import Notifier


@patch("src.notifier.requests.post")
def test_notify_report_uses_preview_in_summary_mode(mock_post):
    response = Mock(status_code=200, text="ok")
    mock_post.return_value = response
    config = Config(
        notion_token="token",
        notion_db_id="db",
        telegram_bot_token="bot",
        telegram_chat_id="123456",
        notification_mode="summary",
    )
    notifier = Notifier(config)
    report = ReviewReport(
        period="daily",
        title="Daily Review",
        content="完整正文",
        preview="简短摘要",
    )

    results = notifier.notify_report(report)

    assert results["telegram_primary"] is True
    payload = mock_post.call_args.kwargs["json"]
    assert "简短摘要" in payload["text"]
    assert "完整正文" not in payload["text"]


def test_notify_report_respects_disabled_mode():
    config = Config(
        notion_token="token",
        notion_db_id="db",
        notification_mode="disabled",
    )
    notifier = Notifier(config)
    report = ReviewReport(period="daily", title="x", content="y", preview="z")

    assert notifier.notify_report(report) == {"notifications_disabled": True}


def test_notify_report_suppresses_smart_mode_without_signal():
    config = Config(
        notion_token="token",
        notion_db_id="db",
        notification_mode="smart",
    )
    notifier = Notifier(config)
    report = ReviewReport(
        period="daily",
        title="x",
        content="完整正文",
        preview="简短摘要",
        signals={"should_notify": False},
    )

    assert notifier.notify_report(report) == {"smart_suppressed": True}


def test_notify_report_suppresses_dormancy_even_in_full_mode():
    config = Config(
        notion_token="token",
        notion_db_id="db",
        notification_mode="full",
    )
    notifier = Notifier(config)
    report = ReviewReport(
        period="daily",
        title="x",
        content="完整正文",
        preview="简短摘要",
        signals={"delivery_policy": "suppress"},
    )

    assert notifier.notify_report(report) == {"dormancy_suppressed": True}


@patch("src.notifier.requests.post")
def test_notify_report_uses_decision_card_in_smart_mode(mock_post):
    response = Mock(status_code=200, text="ok")
    mock_post.return_value = response
    config = Config(
        notion_token="token",
        notion_db_id="db",
        telegram_bot_token="bot",
        telegram_chat_id="123456",
        notification_mode="smart",
    )
    notifier = Notifier(config)
    report = ReviewReport(
        period="daily",
        title="Daily Review",
        content="完整正文",
        preview="简短摘要",
        decision_card="日报决策卡\n当前判断：值得提醒",
        signals={"should_notify": True},
    )

    results = notifier.notify_report(report)

    assert results["telegram_primary"] is True
    payload = mock_post.call_args.kwargs["json"]
    assert "日报决策卡" in payload["text"]
    assert "简短摘要" not in payload["text"]


@patch("src.notifier.requests.post")
def test_notify_report_uses_restart_nudge_when_dormant(mock_post):
    response = Mock(status_code=200, text="ok")
    mock_post.return_value = response
    config = Config(
        notion_token="token",
        notion_db_id="db",
        telegram_bot_token="bot",
        telegram_chat_id="123456",
        notification_mode="full",
    )
    notifier = Notifier(config)
    report = ReviewReport(
        period="daily",
        title="Restart Nudge",
        content="完整正文",
        preview="简短摘要",
        decision_card="自动熄火决策卡\n当前判断：轻提醒重启",
        signals={"delivery_policy": "restart_nudge"},
    )

    results = notifier.notify_report(report)

    assert results["telegram_primary"] is True
    payload = mock_post.call_args.kwargs["json"]
    assert "自动熄火决策卡" in payload["text"]
    assert "完整正文" not in payload["text"]
