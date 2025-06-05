# tests/test_llm_client.py
import pytest
from unittest.mock import patch, MagicMock
from src.config import Config
from src.llm_client import LLMClient


# Fixture to create a base config
@pytest.fixture
def base_config():
    return Config(
        notion_token="fake_notion_token",
        notion_db_id="fake_db_id",
        deepseek_key="fake_deepseek_key",
        llm_provider="deepseek"
    )


# Test case for the 'deepseek-reasoner' model
def test_ask_llm_with_reasoner_model(base_config):
    """
    Verify that when using 'deepseek-reasoner', 'temperature' and 'top_p' are NOT sent.
    """
    # Set model in config
    base_config.llm_model = "deepseek-reasoner"

    # Patch the OpenAI client to avoid real network calls
    with patch('src.llm_client.OpenAI') as mock_openai:
        # Create a mock instance for the client and its methods
        mock_client_instance = MagicMock()
        mock_openai.return_value = mock_client_instance

        # Instantiate our LLMClient, which will now use the mock client
        llm_client = LLMClient(base_config)
        llm_client.ask_llm("test prompt")

        # Check that the create method was called
        mock_client_instance.chat.completions.create.assert_called_once()

        # Get the arguments passed to the mocked 'create' method
        _, kwargs = mock_client_instance.chat.completions.create.call_args

        # Assert that the unsupported parameters are NOT in the call
        assert 'temperature' not in kwargs
        assert 'top_p' not in kwargs
        # Assert that the core parameters are still there
        assert 'model' in kwargs
        assert kwargs['model'] == 'deepseek-reasoner'


# Test case for the 'deepseek-chat' model
def test_ask_llm_with_chat_model(base_config):
    """
    Verify that when using a standard model like 'deepseek-chat',
    'temperature' and 'top_p' ARE sent.
    """
    # Set model in config
    base_config.llm_model = "deepseek-chat"

    with patch('src.llm_client.OpenAI') as mock_openai:
        mock_client_instance = MagicMock()
        mock_openai.return_value = mock_client_instance

        llm_client = LLMClient(base_config)
        llm_client.ask_llm("test prompt")

        mock_client_instance.chat.completions.create.assert_called_once()
        _, kwargs = mock_client_instance.chat.completions.create.call_args

        # Assert that the standard parameters ARE in the call
        assert 'temperature' in kwargs
        assert 'top_p' in kwargs
        assert kwargs['temperature'] == 0.7  # Check the default value
        assert kwargs['top_p'] == 0.9
        assert kwargs['model'] == 'deepseek-chat'