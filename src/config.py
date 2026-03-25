import os
from dataclasses import dataclass
from typing import List, Optional


VALID_NOTIFICATION_MODES = {"disabled", "summary", "full", "smart"}
VALID_TASK_SOURCES = {"notion", "sqlite"}


@dataclass
class TelegramTarget:
    name: str
    bot_token: str
    chat_id: str


@dataclass
class Config:
    task_source: str = "sqlite"
    sqlite_db_path: str = ".bear_review/tasks.db"
    notion_token: str = ""
    notion_db_id: str = ""
    deepseek_key: Optional[str] = None
    openai_key: Optional[str] = None
    llm_provider: str = "deepseek"
    llm_model: str = "deepseek-chat"
    telegram_bot_token: Optional[str] = None
    telegram_chat_id: Optional[str] = None
    telegram_bot_token_2: Optional[str] = None
    telegram_chat_id_2: Optional[str] = None
    email_smtp_server: Optional[str] = None
    email_username: Optional[str] = None
    email_password: Optional[str] = None
    timezone: str = "America/Toronto"
    max_retries: int = 3
    focus_goal: str = "保持高效且有序的一天"
    notification_mode: str = "summary"
    notification_title_prefix: str = "Bear Review"
    telegram_message_limit: int = 3500

    @classmethod
    def from_env(cls) -> "Config":
        task_source = os.getenv("TASK_SOURCE", "").strip().lower()
        if task_source not in VALID_TASK_SOURCES:
            task_source = "notion" if (os.getenv("NOTION_TOKEN") and os.getenv("NOTION_DB_ID")) else "sqlite"

        llm_provider = os.getenv("LLM_PROVIDER", "").strip().lower()
        if not llm_provider:
            if os.getenv("DEEPSEEK_KEY"):
                llm_provider = "deepseek"
            elif os.getenv("OPENAI_KEY"):
                llm_provider = "openai"
            else:
                llm_provider = "deepseek"

        notification_mode = os.getenv("NOTIFICATION_MODE", "summary").strip().lower()
        if notification_mode not in VALID_NOTIFICATION_MODES:
            notification_mode = "summary"

        default_model = "deepseek-chat" if llm_provider == "deepseek" else "gpt-4o-mini"

        return cls(
            task_source=task_source,
            sqlite_db_path=os.getenv("SQLITE_DB_PATH", ".bear_review/tasks.db"),
            notion_token=os.getenv("NOTION_TOKEN", ""),
            notion_db_id=os.getenv("NOTION_DB_ID", ""),
            deepseek_key=os.getenv("DEEPSEEK_KEY"),
            openai_key=os.getenv("OPENAI_KEY"),
            llm_provider=llm_provider,
            llm_model=os.getenv("LLM_MODEL", default_model),
            telegram_bot_token=os.getenv("TELEGRAM_BOT_TOKEN"),
            telegram_chat_id=os.getenv("TELEGRAM_CHAT_ID"),
            telegram_bot_token_2=os.getenv("TELEGRAM_BOT_TOKEN_2"),
            telegram_chat_id_2=os.getenv("TELEGRAM_CHAT_ID_2"),
            email_smtp_server=os.getenv("EMAIL_SMTP_SERVER"),
            email_username=os.getenv("EMAIL_USERNAME"),
            email_password=os.getenv("EMAIL_PASSWORD"),
            timezone=os.getenv("TIMEZONE", "America/Toronto") or "America/Toronto",
            max_retries=int(os.getenv("MAX_RETRIES", "3")),
            focus_goal=os.getenv("FOCUS_GOAL", "保持高效且有序的一天"),
            notification_mode=notification_mode,
            notification_title_prefix=os.getenv("NOTIFICATION_TITLE_PREFIX", "Bear Review"),
            telegram_message_limit=int(os.getenv("TELEGRAM_MESSAGE_LIMIT", "3500")),
        )

    @property
    def notifications_enabled(self) -> bool:
        return self.notification_mode != "disabled"

    @property
    def email_enabled(self) -> bool:
        return all([self.email_smtp_server, self.email_username, self.email_password])

    def telegram_targets(self) -> List[TelegramTarget]:
        targets: List[TelegramTarget] = []

        if self.telegram_bot_token and self.telegram_chat_id:
            targets.append(
                TelegramTarget(
                    name="telegram_primary",
                    bot_token=self.telegram_bot_token,
                    chat_id=self.telegram_chat_id,
                )
            )

        if self.telegram_chat_id_2:
            bot_token = self.telegram_bot_token_2 or self.telegram_bot_token
            if bot_token:
                targets.append(
                    TelegramTarget(
                        name="telegram_secondary",
                        bot_token=bot_token,
                        chat_id=self.telegram_chat_id_2,
                    )
                )

        return targets

    def validate_runtime(self) -> None:
        if self.task_source == "notion" and (not self.notion_token or not self.notion_db_id):
            raise ValueError("环境变量 NOTION_TOKEN 和 NOTION_DB_ID 必须设置")

        if self.task_source not in VALID_TASK_SOURCES:
            raise ValueError(f"不支持的 TASK_SOURCE: {self.task_source}")

        if self.llm_provider == "deepseek" and not self.deepseek_key:
            raise ValueError("LLM_PROVIDER=deepseek 时必须提供 DEEPSEEK_KEY")

        if self.llm_provider == "openai" and not self.openai_key:
            raise ValueError("LLM_PROVIDER=openai 时必须提供 OPENAI_KEY")
