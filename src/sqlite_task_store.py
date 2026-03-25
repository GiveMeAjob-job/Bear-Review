from __future__ import annotations

import sqlite3
from datetime import date, datetime, time, timedelta
from pathlib import Path
from typing import List, Mapping, Optional

import pytz

from .config import Config
from .models import TaskAlias, TaskRecord
from .utils import get_date_range, parse_notion_datetime, safe_int, setup_logger

logger = setup_logger(__name__)


class SQLiteTaskStore:
    def __init__(self, config: Config):
        self.config = config
        self.path = Path(config.sqlite_db_path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._ensure_schema()

    def fetch_period_tasks(self, period: str) -> List[TaskRecord]:
        start_date, end_date = get_date_range(period, self.config.timezone)
        return self._fetch_range(start_date, end_date)

    def fetch_tasks_for_date(self, target_date: date) -> List[TaskRecord]:
        return self._fetch_range(target_date, target_date)

    def fetch_yesterday_tasks(self) -> List[TaskRecord]:
        tz = pytz.timezone(self.config.timezone)
        yesterday = datetime.now(tz).date() - timedelta(days=1)
        return self.fetch_tasks_for_date(yesterday)

    def fetch_recent_tasks(self, days: int) -> List[TaskRecord]:
        if days <= 0:
            return []

        tz = pytz.timezone(self.config.timezone)
        end_date = datetime.now(tz).date()
        start_date = end_date - timedelta(days=days - 1)
        return self._fetch_range(start_date, end_date)

    def record_done_task(
        self,
        title: str,
        category: str = "未分类",
        priority: str = "",
        scheduled_start: Optional[datetime] = None,
        scheduled_end: Optional[datetime] = None,
        xp: Optional[int] = None,
        tomatoes: int = 0,
        actual_minutes: int = 0,
        note: str = "",
    ) -> TaskRecord:
        start_dt = self._coerce_datetime(scheduled_start) or self._local_now()
        end_dt = self._coerce_datetime(scheduled_end) or self._default_end(start_dt, actual_minutes)
        actual_minutes = safe_int(actual_minutes)
        tomatoes = safe_int(tomatoes)
        xp_value = safe_int(xp, default=_priority_to_xp(priority))

        payload = {
            "title": title.strip() or "（无标题）",
            "category": category.strip() or "未分类",
            "priority": priority.strip(),
            "status": "Done",
            "scheduled_start": self._to_storage_iso(start_dt),
            "scheduled_end": self._to_storage_iso(end_dt),
            "xp": xp_value,
            "tomatoes": tomatoes,
            "actual_minutes": actual_minutes,
            "note": note.strip(),
            "source": "sqlite",
        }

        with self._connect() as conn:
            cursor = conn.execute(
                """
                INSERT INTO tasks (
                    title, category, priority, status, scheduled_start, scheduled_end,
                    xp, tomatoes, actual_minutes, note, source
                ) VALUES (
                    :title, :category, :priority, :status, :scheduled_start, :scheduled_end,
                    :xp, :tomatoes, :actual_minutes, :note, :source
                )
                """,
                payload,
            )
            row_id = cursor.lastrowid
            row = conn.execute("SELECT * FROM tasks WHERE id = ?", (row_id,)).fetchone()

        logger.info("已写入本地任务: %s (%s)", payload["title"], self.path)
        return self._row_to_task(row)

    def recent_done_tasks(self, limit: int = 10) -> List[TaskRecord]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT * FROM tasks
                WHERE status = 'Done'
                ORDER BY scheduled_start DESC, id DESC
                LIMIT ?
                """,
                (max(limit, 1),),
            ).fetchall()
        return [self._row_to_task(row) for row in rows]

    def get_task(self, task_id: object) -> Optional[TaskRecord]:
        normalized_id = self._normalize_task_id(task_id)
        if normalized_id is None:
            return None

        with self._connect() as conn:
            row = conn.execute("SELECT * FROM tasks WHERE id = ?", (normalized_id,)).fetchone()

        if row is None:
            return None
        return self._row_to_task(row)

    def update_done_task(
        self,
        task_id: object,
        title: str,
        category: str = "未分类",
        priority: str = "",
        scheduled_start: Optional[datetime] = None,
        scheduled_end: Optional[datetime] = None,
        xp: Optional[int] = None,
        tomatoes: int = 0,
        actual_minutes: int = 0,
        note: str = "",
    ) -> Optional[TaskRecord]:
        normalized_id = self._normalize_task_id(task_id)
        if normalized_id is None:
            return None

        start_dt = self._coerce_datetime(scheduled_start) or self._local_now()
        end_dt = self._coerce_datetime(scheduled_end) or self._default_end(start_dt, actual_minutes)
        actual_minutes = safe_int(actual_minutes)
        tomatoes = safe_int(tomatoes)
        xp_value = safe_int(xp, default=_priority_to_xp(priority))

        payload = {
            "task_id": normalized_id,
            "title": title.strip() or "（无标题）",
            "category": category.strip() or "未分类",
            "priority": priority.strip(),
            "status": "Done",
            "scheduled_start": self._to_storage_iso(start_dt),
            "scheduled_end": self._to_storage_iso(end_dt),
            "xp": xp_value,
            "tomatoes": tomatoes,
            "actual_minutes": actual_minutes,
            "note": note.strip(),
        }

        with self._connect() as conn:
            cursor = conn.execute(
                """
                UPDATE tasks
                SET title = :title,
                    category = :category,
                    priority = :priority,
                    status = :status,
                    scheduled_start = :scheduled_start,
                    scheduled_end = :scheduled_end,
                    xp = :xp,
                    tomatoes = :tomatoes,
                    actual_minutes = :actual_minutes,
                    note = :note,
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = :task_id
                """,
                payload,
            )
            if cursor.rowcount <= 0:
                return None
            row = conn.execute("SELECT * FROM tasks WHERE id = ?", (normalized_id,)).fetchone()

        if row is None:
            return None

        logger.info("已更新本地任务: %s (%s)", payload["title"], self.path)
        return self._row_to_task(row)

    def delete_task(self, task_id: object) -> bool:
        normalized_id = self._normalize_task_id(task_id)
        if normalized_id is None:
            return False

        with self._connect() as conn:
            cursor = conn.execute("DELETE FROM tasks WHERE id = ?", (normalized_id,))

        deleted = cursor.rowcount > 0
        if deleted:
            logger.info("已删除本地任务: %s (%s)", normalized_id, self.path)
        return deleted

    def list_task_aliases(self, limit: int = 12) -> List[TaskAlias]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT * FROM task_aliases
                ORDER BY updated_at DESC, id DESC
                LIMIT ?
                """,
                (max(limit, 1),),
            ).fetchall()
        return [self._row_to_alias(row) for row in rows]

    def get_task_alias(self, alias_id: object) -> Optional[TaskAlias]:
        normalized_id = self._normalize_task_id(alias_id)
        if normalized_id is None:
            return None

        with self._connect() as conn:
            row = conn.execute("SELECT * FROM task_aliases WHERE id = ?", (normalized_id,)).fetchone()

        if row is None:
            return None
        return self._row_to_alias(row)

    def save_task_alias(
        self,
        alias_name: str,
        title: str,
        category: str = "未分类",
        priority: str = "",
        actual_minutes: int = 0,
        tomatoes: int = 0,
        xp: Optional[int] = None,
        note: str = "",
        alias_id: object = None,
    ) -> TaskAlias:
        normalized_alias_id = self._normalize_task_id(alias_id)
        payload = {
            "alias_name": alias_name.strip() or title.strip() or "未命名别名",
            "title": title.strip() or "（无标题）",
            "category": category.strip() or "未分类",
            "priority": priority.strip(),
            "actual_minutes": safe_int(actual_minutes),
            "tomatoes": safe_int(tomatoes),
            "xp": safe_int(xp, default=_priority_to_xp(priority)),
            "note": note.strip(),
        }

        with self._connect() as conn:
            if normalized_alias_id is not None:
                cursor = conn.execute(
                    """
                    UPDATE task_aliases
                    SET alias_name = :alias_name,
                        title = :title,
                        category = :category,
                        priority = :priority,
                        actual_minutes = :actual_minutes,
                        tomatoes = :tomatoes,
                        xp = :xp,
                        note = :note,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE id = :alias_id
                    """,
                    {**payload, "alias_id": normalized_alias_id},
                )
                if cursor.rowcount <= 0:
                    normalized_alias_id = None

            if normalized_alias_id is None:
                existing = conn.execute(
                    "SELECT id FROM task_aliases WHERE alias_name = ?",
                    (payload["alias_name"],),
                ).fetchone()
                if existing:
                    normalized_alias_id = int(existing["id"])
                    conn.execute(
                        """
                        UPDATE task_aliases
                        SET title = :title,
                            category = :category,
                            priority = :priority,
                            actual_minutes = :actual_minutes,
                            tomatoes = :tomatoes,
                            xp = :xp,
                            note = :note,
                            updated_at = CURRENT_TIMESTAMP
                        WHERE id = :alias_id
                        """,
                        {**payload, "alias_id": normalized_alias_id},
                    )
                else:
                    cursor = conn.execute(
                        """
                        INSERT INTO task_aliases (
                            alias_name, title, category, priority,
                            actual_minutes, tomatoes, xp, note
                        ) VALUES (
                            :alias_name, :title, :category, :priority,
                            :actual_minutes, :tomatoes, :xp, :note
                        )
                        """,
                        payload,
                    )
                    normalized_alias_id = int(cursor.lastrowid)

            row = conn.execute("SELECT * FROM task_aliases WHERE id = ?", (normalized_alias_id,)).fetchone()

        logger.info("已保存任务别名: %s (%s)", payload["alias_name"], self.path)
        return self._row_to_alias(row)

    def delete_task_alias(self, alias_id: object) -> bool:
        normalized_id = self._normalize_task_id(alias_id)
        if normalized_id is None:
            return False

        with self._connect() as conn:
            cursor = conn.execute("DELETE FROM task_aliases WHERE id = ?", (normalized_id,))

        deleted = cursor.rowcount > 0
        if deleted:
            logger.info("已删除任务别名: %s (%s)", normalized_id, self.path)
        return deleted

    def _fetch_range(self, start_date: date, end_date: date) -> List[TaskRecord]:
        start_iso, end_iso = self._build_date_range(start_date, end_date)
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT * FROM tasks
                WHERE status = 'Done'
                  AND scheduled_start >= ?
                  AND scheduled_start < ?
                ORDER BY scheduled_start ASC, id ASC
                """,
                (start_iso, end_iso),
            ).fetchall()
        logger.info("SQLite 查询到 %s 个任务 (%s 到 %s)", len(rows), start_date, end_date)
        return [self._row_to_task(row) for row in rows]

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.path)
        conn.row_factory = sqlite3.Row
        return conn

    def _ensure_schema(self) -> None:
        with self._connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS tasks (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    title TEXT NOT NULL,
                    category TEXT NOT NULL DEFAULT '未分类',
                    priority TEXT NOT NULL DEFAULT '',
                    status TEXT NOT NULL DEFAULT 'Done',
                    scheduled_start TEXT NOT NULL,
                    scheduled_end TEXT,
                    xp INTEGER NOT NULL DEFAULT 0,
                    tomatoes INTEGER NOT NULL DEFAULT 0,
                    actual_minutes INTEGER NOT NULL DEFAULT 0,
                    note TEXT NOT NULL DEFAULT '',
                    source TEXT NOT NULL DEFAULT 'sqlite',
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );
                CREATE INDEX IF NOT EXISTS idx_tasks_status_start
                ON tasks(status, scheduled_start);
                CREATE TABLE IF NOT EXISTS task_aliases (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    alias_name TEXT NOT NULL UNIQUE,
                    title TEXT NOT NULL,
                    category TEXT NOT NULL DEFAULT '未分类',
                    priority TEXT NOT NULL DEFAULT '',
                    actual_minutes INTEGER NOT NULL DEFAULT 0,
                    tomatoes INTEGER NOT NULL DEFAULT 0,
                    xp INTEGER NOT NULL DEFAULT 0,
                    note TEXT NOT NULL DEFAULT '',
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );
                CREATE INDEX IF NOT EXISTS idx_task_aliases_updated
                ON task_aliases(updated_at DESC);
                """
            )

    def _row_to_task(self, row: sqlite3.Row) -> TaskRecord:
        return self.from_mapping(dict(row))

    def _row_to_alias(self, row: sqlite3.Row) -> TaskAlias:
        return self.alias_from_mapping(dict(row))

    @staticmethod
    def from_mapping(record: Mapping[str, object]) -> TaskRecord:
        return TaskRecord(
            id=str(record.get("id", "")),
            title=str(record.get("title", "") or "（无标题）"),
            category=str(record.get("category", "") or "未分类"),
            priority=str(record.get("priority", "") or ""),
            status=str(record.get("status", "") or ""),
            scheduled_start=parse_notion_datetime(str(record.get("scheduled_start", "") or "")),
            scheduled_end=parse_notion_datetime(str(record.get("scheduled_end", "") or "")),
            xp=safe_int(record.get("xp")),
            tomatoes=safe_int(record.get("tomatoes")),
            actual_minutes=safe_int(record.get("actual_minutes")),
            raw=dict(record),
        )

    @staticmethod
    def alias_from_mapping(record: Mapping[str, object]) -> TaskAlias:
        return TaskAlias(
            id=str(record.get("id", "")),
            alias_name=str(record.get("alias_name", "") or "未命名别名"),
            title=str(record.get("title", "") or "（无标题）"),
            category=str(record.get("category", "") or "未分类"),
            priority=str(record.get("priority", "") or ""),
            actual_minutes=safe_int(record.get("actual_minutes")),
            tomatoes=safe_int(record.get("tomatoes")),
            xp=safe_int(record.get("xp")),
            note=str(record.get("note", "") or ""),
            raw=dict(record),
        )

    def _build_date_range(self, start_date: date, end_date: date) -> tuple[str, str]:
        tz = pytz.timezone(self.config.timezone)
        start_dt = tz.localize(datetime.combine(start_date, time.min))
        end_dt = tz.localize(datetime.combine(end_date + timedelta(days=1), time.min))
        return self._to_storage_iso(start_dt), self._to_storage_iso(end_dt)

    def _coerce_datetime(self, value: Optional[datetime]) -> Optional[datetime]:
        if value is None:
            return None
        if value.tzinfo is None:
            return pytz.timezone(self.config.timezone).localize(value)
        return value

    def _local_now(self) -> datetime:
        return datetime.now(pytz.timezone(self.config.timezone))

    def _default_end(self, start_dt: datetime, actual_minutes: int) -> datetime:
        minutes = max(actual_minutes, 0)
        if minutes <= 0:
            return start_dt
        return start_dt + timedelta(minutes=minutes)

    def _to_storage_iso(self, value: datetime) -> str:
        return value.astimezone(pytz.utc).isoformat()

    def _normalize_task_id(self, task_id: object) -> Optional[int]:
        try:
            return int(str(task_id).strip())
        except (TypeError, ValueError):
            return None


def _priority_to_xp(priority: str) -> int:
    if priority == "MIT":
        return 10
    if priority:
        return 5
    return 0
