from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from src.config import Config
from src.llm_client import LLMClient


@pytest.fixture
def base_config():
    return Config(
        notion_token="fake_notion_token",
        notion_db_id="fake_db_id",
        deepseek_key="fake_deepseek_key",
        llm_provider="deepseek",
    )


def build_response(content="总结内容", reasoning_content=""):
    return SimpleNamespace(
        choices=[
            SimpleNamespace(
                message=SimpleNamespace(
                    content=content,
                    reasoning_content=reasoning_content,
                )
            )
        ]
    )


def test_ask_llm_with_reasoner_model_omits_sampling_params(base_config):
    base_config.llm_model = "deepseek-reasoner"

    with patch("src.llm_client.OpenAI") as mock_openai:
        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = build_response()
        mock_openai.return_value = mock_client

        client = LLMClient(base_config)
        client.ask_llm("test prompt")

        _, kwargs = mock_client.chat.completions.create.call_args
        assert "temperature" not in kwargs
        assert "top_p" not in kwargs
        assert kwargs["model"] == "deepseek-reasoner"


def test_ask_llm_with_chat_model_includes_sampling_params(base_config):
    base_config.llm_model = "deepseek-chat"

    with patch("src.llm_client.OpenAI") as mock_openai:
        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = build_response()
        mock_openai.return_value = mock_client

        client = LLMClient(base_config)
        client.ask_llm("test prompt")

        _, kwargs = mock_client.chat.completions.create.call_args
        assert kwargs["temperature"] == 0.7
        assert kwargs["top_p"] == 0.9
        assert kwargs["model"] == "deepseek-chat"


def test_ask_llm_falls_back_to_reasoning_content(base_config):
    with patch("src.llm_client.OpenAI") as mock_openai:
        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = build_response(
            content="",
            reasoning_content="思考结果",
        )
        mock_openai.return_value = mock_client

        client = LLMClient(base_config)

        assert client.ask_llm("test prompt") == "思考结果"
