from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any, Optional


class SQLiteStateStore:
    def __init__(self, db_path: str, namespace: str):
        self.path = Path(db_path)
        self.namespace = namespace
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._ensure_schema()

    def load_payload(self) -> Optional[Any]:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT payload FROM system_state WHERE namespace = ?",
                (self.namespace,),
            ).fetchone()
        if row is None:
            return None
        return json.loads(str(row["payload"]))

    def save_payload(self, payload: Any) -> None:
        serialized = json.dumps(payload, ensure_ascii=False, indent=2)
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO system_state(namespace, payload, updated_at)
                VALUES(?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(namespace) DO UPDATE
                SET payload = excluded.payload,
                    updated_at = CURRENT_TIMESTAMP
                """,
                (self.namespace, serialized),
            )

    def exists(self) -> bool:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT 1 FROM system_state WHERE namespace = ?",
                (self.namespace,),
            ).fetchone()
        return row is not None

    def maybe_import_json_file(self, json_path: str) -> bool:
        legacy_path = Path(json_path)
        if self.exists() or not legacy_path.exists():
            return False

        payload = json.loads(legacy_path.read_text(encoding="utf-8"))
        self.save_payload(payload)
        return True

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.path)
        conn.row_factory = sqlite3.Row
        return conn

    def _ensure_schema(self) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS system_state (
                    namespace TEXT PRIMARY KEY,
                    payload TEXT NOT NULL,
                    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
