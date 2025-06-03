# src/config.py - 配置管理
import os
from dataclasses import dataclass
from typing import Optional


@dataclass
class Config:
    # Notion配置
    notion_token: str
    notion_db_id: str

    # LLM配置
    deepseek_key: Optional[str] = None
    openai_key: Optional[str] = None
    llm_provider: str = "deepseek"  # deepseek, openai

    # 通知配置
    telegram_bot_token: Optional[str] = None
    telegram_chat_id: Optional[str] = None
    email_smtp_server: Optional[str] = None
    email_username: Optional[str] = None
    email_password: Optional[str] = None

    # 系统配置
    timezone: str = "America/Toronto"
    max_retries: int = 3

    @classmethod
    def from_env(cls) -> 'Config':
        # 获取 LLM_PROVIDER，如果没设置且有 DEEPSEEK_KEY 则默认用 deepseek
        llm_provider = os.getenv("LLM_PROVIDER", "")
        if not llm_provider:
            if os.getenv("DEEPSEEK_KEY"):
                llm_provider = "deepseek"
            elif os.getenv("OPENAI_KEY"):
                llm_provider = "openai"
            else:
                llm_provider = "deepseek"  # 默认值

        return cls(
            notion_token=os.getenv("NOTION_TOKEN", ""),
            notion_db_id=os.getenv("NOTION_DB_ID", ""),
            deepseek_key=os.getenv("DEEPSEEK_KEY"),
            openai_key=os.getenv("OPENAI_KEY"),
            llm_provider=llm_provider,
            telegram_bot_token=os.getenv("TELEGRAM_BOT_TOKEN"),
            telegram_chat_id=os.getenv("TELEGRAM_CHAT_ID"),
            email_smtp_server=os.getenv("EMAIL_SMTP_SERVER"),
            email_username=os.getenv("EMAIL_USERNAME"),
            email_password=os.getenv("EMAIL_PASSWORD"),
            timezone=os.getenv("TIMEZONE", "America/Toronto"),  # 改为多伦多时区
            max_retries=int(os.getenv("MAX_RETRIES", "3"))
        )