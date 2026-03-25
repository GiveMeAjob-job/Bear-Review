from src.config import Config


def test_validate_runtime_allows_sqlite_without_notion_credentials():
    cfg = Config(
        task_source="sqlite",
        sqlite_db_path=".bear_review/tasks.db",
        llm_provider="deepseek",
        deepseek_key="test-key",
    )

    cfg.validate_runtime()


def test_validate_runtime_requires_notion_credentials_for_notion_source():
    cfg = Config(
        task_source="notion",
        llm_provider="deepseek",
        deepseek_key="test-key",
    )

    try:
        cfg.validate_runtime()
    except ValueError as exc:
        assert "NOTION_TOKEN" in str(exc)
    else:
        raise AssertionError("expected validate_runtime to require Notion credentials")
