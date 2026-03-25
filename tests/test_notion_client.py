from datetime import date
from unittest.mock import Mock, patch

import pytest

from src.config import Config
from src.notion_client import NotionClient, calc_xp


@pytest.fixture
def config():
    return Config(
        notion_token="test_token",
        notion_db_id="test_db_id",
        timezone="America/Toronto",
    )


@pytest.fixture
def notion_client(config):
    return NotionClient(config)


def test_calc_xp_priority_fallback():
    page = {"properties": {"优先级": {"select": {"name": "MIT"}}}}
    assert calc_xp(page) == 10


def test_calc_xp_prefers_formula_value():
    page = {
        "properties": {
            "优先级": {"select": {"name": "MIT"}},
            "XP": {"formula": {"number": 42}},
        }
    }
    assert calc_xp(page) == 42


@patch("src.notion_client.requests.post")
def test_query_tasks_handles_pagination(mock_post, notion_client):
    first_page = Mock()
    first_page.raise_for_status.return_value = None
    first_page.json.return_value = {
        "results": [{"id": "1"}],
        "has_more": True,
        "next_cursor": "cursor-1",
    }

    second_page = Mock()
    second_page.raise_for_status.return_value = None
    second_page.json.return_value = {
        "results": [{"id": "2"}],
        "has_more": False,
        "next_cursor": None,
    }

    mock_post.side_effect = [first_page, second_page]

    tasks = notion_client._query_tasks(date(2024, 1, 1), date(2024, 1, 2))

    assert [task["id"] for task in tasks] == ["1", "2"]
    assert mock_post.call_count == 2
    second_payload = mock_post.call_args_list[1].kwargs["json"]
    assert second_payload["start_cursor"] == "cursor-1"


def test_parse_task_normalizes_task_fields():
    page = {
        "id": "page-1",
        "properties": {
            "任务名称": {"title": [{"plain_text": "完成报告"}]},
            "分类": {"select": {"name": "Work"}},
            "优先级": {"select": {"name": "MIT"}},
            "状态": {"select": {"name": "Done"}},
            "计划日期": {
                "date": {
                    "start": "2024-01-01T13:00:00+00:00",
                    "end": "2024-01-01T14:30:00+00:00",
                }
            },
            "番茄数": {"formula": {"number": 3}},
            "实际用时(min)": {"formula": {"number": 90}},
        },
    }

    task = NotionClient.parse_task(page)

    assert task.id == "page-1"
    assert task.title == "完成报告"
    assert task.category == "Work"
    assert task.is_mit is True
    assert task.xp == 10
    assert task.tomatoes == 3
    assert task.actual_minutes == 90
    assert task.scheduled_start.isoformat() == "2024-01-01T13:00:00+00:00"
