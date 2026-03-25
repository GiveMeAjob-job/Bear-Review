from __future__ import annotations

from datetime import date
from typing import Protocol, Sequence

from .config import Config
from .models import TaskRecord
from .notion_client import NotionClient
from .sqlite_task_store import SQLiteTaskStore


class TaskSource(Protocol):
    def fetch_period_tasks(self, period: str) -> Sequence[TaskRecord]:
        ...

    def fetch_tasks_for_date(self, target_date: date) -> Sequence[TaskRecord]:
        ...

    def fetch_yesterday_tasks(self) -> Sequence[TaskRecord]:
        ...

    def fetch_recent_tasks(self, days: int) -> Sequence[TaskRecord]:
        ...


def create_task_source(config: Config) -> TaskSource:
    if config.task_source == "sqlite":
        return SQLiteTaskStore(config)
    return NotionClient(config)
