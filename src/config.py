"""Configuration management using Pydantic BaseSettings."""
from __future__ import annotations

import os
from typing import Optional

from pydantic import BaseSettings, validator


class Config(BaseSettings):
    # Notion settings
    notion_token: str = ""
    notion_db_id: str = ""

    # LLM settings
    deepseek_key: Optional[str] = None
    openai_key: Optional[str] = None
    llm_provider: Optional[str] = None
    llm_model: str = os.getenv("LLM_MODEL", "deepseek-reasoner")

    # Notification settings
    telegram_bot_token: Optional[str] = None
    telegram_chat_id: Optional[str] = None
    telegram_bot_token_2: Optional[str] = None
    telegram_chat_id_2: Optional[str] = None

    email_smtp_server: Optional[str] = None
    email_username: Optional[str] = None
    email_password: Optional[str] = None

    # System settings
    timezone: str = "America/Toronto"
    max_retries: int = 3
    focus_goal: str = os.getenv("FOCUS_GOAL", "保持高效且有序的一天")

    class Config:
        env_file = ".env"

    @validator("llm_provider", pre=True, always=True)
    def set_llm_provider(cls, v):
        if v:
            return v
        if os.getenv("DEEPSEEK_KEY"):
            return "deepseek"
        if os.getenv("OPENAI_KEY"):
            return "openai"
        return "deepseek"

    @classmethod
    def from_env(cls) -> "Config":
        """Load configuration from environment variables."""
        return cls()
