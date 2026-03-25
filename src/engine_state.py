from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Dict, Iterable, Optional, Sequence

from .models import TaskRecord
from .sqlite_state_store import SQLiteStateStore
from .utils import setup_logger

logger = setup_logger(__name__)


@dataclass
class DormancySettings:
    enabled: bool = True
    idle_after_days: int = 10
    reminder_interval_days: int = 5
    restart_message: str = "如果你准备好了，先完成一个最小任务，让系统重新启动起来。"


@dataclass
class EngineState:
    last_active_date: str = ""
    dormant_since: str = ""
    last_restart_nudge_date: str = ""
    last_run_date: str = ""


@dataclass
class DormancyDecision:
    enabled: bool
    is_dormant: bool
    just_entered_dormancy: bool
    reminder_due: bool
    wake_detected: bool
    last_active_date: str
    dormant_since: str
    last_restart_nudge_date: str
    idle_after_days: int
    reminder_interval_days: int
    restart_message: str
    delivery_policy: str

    def as_dict(self) -> Dict[str, object]:
        return asdict(self)


class EngineStateStore:
    def __init__(self, path: str):
        self.path = Path(path)
        self._loaded = False
        self.state = EngineState()
        self._sqlite = SQLiteStateStore(path, "engine_state") if self.path.suffix == ".db" else None

    def load(self) -> EngineState:
        if self._loaded:
            return self.state

        if self._sqlite:
            payload = self._sqlite.load_payload()
            if payload is None:
                self.state = EngineState()
                self._loaded = True
                return self.state
        elif not self.path.exists():
            self.state = EngineState()
            self._loaded = True
            return self.state

        try:
            if self._sqlite:
                payload = payload or {}
            else:
                payload = json.loads(self.path.read_text(encoding="utf-8"))
            self.state = EngineState(
                last_active_date=str(payload.get("last_active_date", "") or ""),
                dormant_since=str(payload.get("dormant_since", "") or ""),
                last_restart_nudge_date=str(payload.get("last_restart_nudge_date", "") or ""),
                last_run_date=str(payload.get("last_run_date", "") or ""),
            )
        except Exception as exc:
            logger.warning("读取引擎状态失败，将使用空状态: %s", exc)
            self.state = EngineState()

        self._loaded = True
        return self.state

    def save(self) -> None:
        state = self.load()
        if self._sqlite:
            self._sqlite.save_payload(asdict(state))
        else:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self.path.write_text(
                json.dumps(asdict(state), ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        logger.info("🔥 已更新引擎状态: %s", self.path)

    def maybe_import_json_file(self, json_path: str) -> bool:
        if not self._sqlite:
            return False
        imported = self._sqlite.maybe_import_json_file(json_path)
        if imported:
            self._loaded = False
            self.state = EngineState()
            logger.info("🔥 已从 JSON 导入引擎状态到 SQLite: %s -> %s", json_path, self.path)
        return imported

    def evaluate(
        self,
        settings: DormancySettings,
        current_tasks: Sequence[TaskRecord],
        recent_tasks: Sequence[TaskRecord],
        today: Optional[date] = None,
    ) -> DormancyDecision:
        state = self.load()
        today = today or datetime.now().date()
        state.last_run_date = today.isoformat()

        if not settings.enabled:
            last_active = self._latest_task_date(current_tasks, recent_tasks) or state.last_active_date
            if last_active:
                state.last_active_date = last_active
            if state.dormant_since or state.last_restart_nudge_date:
                state.dormant_since = ""
                state.last_restart_nudge_date = ""
            return DormancyDecision(
                enabled=False,
                is_dormant=False,
                just_entered_dormancy=False,
                reminder_due=False,
                wake_detected=False,
                last_active_date=state.last_active_date,
                dormant_since="",
                last_restart_nudge_date="",
                idle_after_days=settings.idle_after_days,
                reminder_interval_days=settings.reminder_interval_days,
                restart_message=settings.restart_message,
                delivery_policy="normal",
            )

        latest_task_date = self._latest_task_date(current_tasks, recent_tasks)
        if latest_task_date:
            state.last_active_date = latest_task_date

        active_recently = self._is_active_recently(state.last_active_date, settings.idle_after_days, today)
        has_current_activity = bool(current_tasks)
        wake_detected = bool(state.dormant_since) and (has_current_activity or active_recently)

        if has_current_activity or active_recently:
            state.dormant_since = ""
            state.last_restart_nudge_date = ""
            return DormancyDecision(
                enabled=True,
                is_dormant=False,
                just_entered_dormancy=False,
                reminder_due=False,
                wake_detected=wake_detected,
                last_active_date=state.last_active_date,
                dormant_since="",
                last_restart_nudge_date="",
                idle_after_days=settings.idle_after_days,
                reminder_interval_days=settings.reminder_interval_days,
                restart_message=settings.restart_message,
                delivery_policy="normal",
            )

        just_entered = False
        if not state.dormant_since:
            state.dormant_since = today.isoformat()
            just_entered = True

        reminder_due = self._is_reminder_due(
            dormant_since=state.dormant_since,
            last_restart_nudge_date=state.last_restart_nudge_date,
            interval_days=settings.reminder_interval_days,
            today=today,
            just_entered_dormancy=just_entered,
        )

        if reminder_due:
            state.last_restart_nudge_date = today.isoformat()

        return DormancyDecision(
            enabled=True,
            is_dormant=True,
            just_entered_dormancy=just_entered,
            reminder_due=reminder_due,
            wake_detected=False,
            last_active_date=state.last_active_date,
            dormant_since=state.dormant_since,
            last_restart_nudge_date=state.last_restart_nudge_date,
            idle_after_days=settings.idle_after_days,
            reminder_interval_days=settings.reminder_interval_days,
            restart_message=settings.restart_message,
            delivery_policy="restart_nudge" if reminder_due else "suppress",
        )

    def _latest_task_date(self, *task_groups: Iterable[TaskRecord]) -> str:
        candidates = []
        for group in task_groups:
            for task in group:
                if task.scheduled_start:
                    candidates.append(task.scheduled_start.date().isoformat())
        return max(candidates) if candidates else ""

    def _is_active_recently(self, last_active_date: str, idle_after_days: int, today: date) -> bool:
        if not last_active_date:
            return False

        try:
            last_active = date.fromisoformat(last_active_date)
        except ValueError:
            return False

        return (today - last_active).days < idle_after_days

    def _is_reminder_due(
        self,
        dormant_since: str,
        last_restart_nudge_date: str,
        interval_days: int,
        today: date,
        just_entered_dormancy: bool,
    ) -> bool:
        if just_entered_dormancy:
            return False

        baseline_str = last_restart_nudge_date or dormant_since
        if not baseline_str:
            return False

        try:
            baseline = date.fromisoformat(baseline_str)
        except ValueError:
            baseline = today

        return (today - baseline).days >= max(interval_days, 1)
