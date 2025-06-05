# tests/test_notion_client.py - Notion客户端测试
import pytest
from unittest.mock import Mock, patch
from datetime import date
from src.config import Config
from src.notion_client import NotionClient, calc_xp


@pytest.fixture
def config():
    return Config(
        notion_token="test_token",
        notion_db_id="test_db_id"
    )


@pytest.fixture
def notion_client(config):
    return NotionClient(config)


def test_calc_xp_mit_task():
    """测试MIT任务XP计算"""
    page = {
        "properties": {
            "优先级": {
                "select": {
                    "name": "MIT"
                }
            }
        }
    }
    assert calc_xp(page) == 10


def test_calc_xp_normal_task():
    """测试普通任务XP计算"""
    page = {
        "properties": {
            "优先级": {
                "select": {
                    "name": "次要"
                }
            }
        }
    }
    assert calc_xp(page) == 5


def test_calc_xp_invalid_data():
    """测试异常数据XP计算"""
    page = {"properties": {}}
    assert calc_xp(page) == 0


@patch('requests.post')
def test_query_tasks_success(mock_post, notion_client):
    """测试成功查询任务"""
    mock_response = Mock()
    mock_response.raise_for_status.return_value = None
    mock_response.json.return_value = {
        "results": [
            {
                "id": "test_id",
                "properties": {
                    "任务名称": {"title": [{"plain_text": "测试任务"}]},
                    "分类": {"select": {"name": "Work"}},
                    "优先级": {"select": {"name": "MIT"}}
                }
            }
        ]
    }
    mock_post.return_value = mock_response

    start_date = date(2024, 1, 1)
    end_date = date(2024, 1, 31)

    tasks = notion_client._query_tasks(start_date, end_date)

    assert len(tasks) == 1
    assert tasks[0]["id"] == "test_id"
    mock_post.assert_called_once()


# tests/test_summarizer.py - 汇总器测试
import pytest
from src.summarizer import TaskSummarizer


@pytest.fixture
def summarizer():
    return TaskSummarizer()


@pytest.fixture
def sample_tasks():
    return [
        {
            "id": "1",
            "properties": {
                "任务名称": {"title": [{"plain_text": "完成报告"}]},
                "分类": {"select": {"name": "Work"}},
                "优先级": {"select": {"name": "MIT"}}
            }
        },
        {
            "id": "2",
            "properties": {
                "任务名称": {"title": [{"plain_text": "健身锻炼"}]},
                "分类": {"select": {"name": "Health"}},
                "优先级": {"select": {"name": "次要"}}
            }
        }
    ]


def test_aggregate_tasks(summarizer, sample_tasks):
    """测试任务聚合功能"""
    stats, titles = summarizer.aggregate_tasks(sample_tasks)

    assert stats["total"] == 2
    assert stats["xp"] == 15  # 10 + 5
    assert stats["mit_count"] == 1
    assert stats["cats"]["Work"] == 1
    assert stats["cats"]["Health"] == 1
    assert "完成报告" in titles
    assert "健身锻炼" in titles


def test_aggregate_empty_tasks(summarizer):
    """测试空任务列表聚合"""
    stats, titles = summarizer.aggregate_tasks([])

    assert stats["total"] == 0
    assert stats["xp"] == 0
    assert stats["mit_count"] == 0
    assert stats["cats"] == {}
    assert titles == []


def test_build_prompt(summarizer):
    """测试提示词构建"""
    stats = {
        "total": 5,
        "xp": 35,
        "cats": {"Work": 3, "Health": 2},
        "mit_count": 2
    }
    titles = ["任务1", "任务2", "任务3"]

    prompt = summarizer.build_prompt(stats, titles, "daily")

    assert "已完成任务 5 个" in prompt
    assert "获得 XP 35" in prompt
    assert "MIT 任务 2 个" in prompt
    assert "Work:3, Health:2" in prompt
    assert "- 任务1" in prompt