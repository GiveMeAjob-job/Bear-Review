from unittest.mock import MagicMock, patch

from src.config import Config
from src.llm_client import LLMClient


def test_llm_client_returns_error_message_on_exception():
    config = Config(
        notion_token="fake_notion_token",
        notion_db_id="fake_db_id",
        deepseek_key="fake_deepseek_key",
        llm_provider="deepseek",
    )

    with patch("src.llm_client.OpenAI") as mock_openai:
        mock_client = MagicMock()
        mock_client.chat.completions.create.side_effect = RuntimeError("boom")
        mock_openai.return_value = mock_client

        client = LLMClient(config)
        message = client.ask_llm("test prompt")

    assert message.startswith("[LLM 调用失败]")
