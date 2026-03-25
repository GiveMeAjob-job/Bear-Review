from src.config import Config
from src.notion_client import NotionClient
from src.sqlite_task_store import SQLiteTaskStore
from src.task_source import create_task_source


def test_create_task_source_returns_sqlite_store(tmp_path):
    source = create_task_source(
        Config(
            task_source="sqlite",
            sqlite_db_path=str(tmp_path / "tasks.db"),
            timezone="America/Toronto",
        )
    )

    assert isinstance(source, SQLiteTaskStore)


def test_create_task_source_returns_notion_client():
    source = create_task_source(
        Config(
            task_source="notion",
            notion_token="token",
            notion_db_id="db",
            timezone="America/Toronto",
        )
    )

    assert isinstance(source, NotionClient)
