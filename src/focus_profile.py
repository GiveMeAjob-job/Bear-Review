import json
import re
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

from .coaching_modes import build_mode_context, mode_payload, resolve_mode
from .engine_state import DormancySettings
from .models import TaskRecord
from .sqlite_state_store import SQLiteStateStore
from .utils import setup_logger

logger = setup_logger(__name__)


@dataclass
class FocusItem:
    name: str
    keywords: List[str] = field(default_factory=list)
    last_seen: str = ""

    def search_terms(self) -> List[str]:
        terms: List[str] = []
        if self.name:
            terms.append(self.name)
            terms.extend(self._extract_terms(self.name))
        terms.extend(self.keywords)
        return [term.strip() for term in terms if term and term.strip()]

    @staticmethod
    def _extract_terms(value: str) -> List[str]:
        return [
            token
            for token in re.split(r"[\s,，/|、;；:：()（）\-_]+", value)
            if token and len(token.strip()) >= 2
        ]


@dataclass
class FocusActivity:
    supported_priorities: List[FocusItem] = field(default_factory=list)
    stale_priorities: List[FocusItem] = field(default_factory=list)
    supported_projects: List[FocusItem] = field(default_factory=list)
    stale_projects: List[FocusItem] = field(default_factory=list)


@dataclass
class FocusProfile:
    current_focus: str = ""
    current_stage: str = ""
    coaching_mode: str = "adaptive"
    coaching_notes: str = ""
    auto_dormancy: DormancySettings = field(default_factory=DormancySettings)
    active_priorities: List[FocusItem] = field(default_factory=list)
    active_projects: List[FocusItem] = field(default_factory=list)
    constraints: List[str] = field(default_factory=list)
    operating_rules: List[str] = field(default_factory=list)
    completed_items: List[str] = field(default_factory=list)
    notes: str = ""
    last_updated: str = ""
    stale_after_days: int = 14
    evidence_window_days: int = 21


class FocusProfileStore:
    def __init__(self, path: str):
        self.path = Path(path)
        self._sqlite = SQLiteStateStore(path, "focus_profile") if self.path.suffix == ".db" else None

    def load(self) -> FocusProfile:
        payload = None
        if self._sqlite:
            payload = self._sqlite.load_payload()
            if payload is None:
                return self._default_profile()
        elif not self.path.exists():
            return self._default_profile()

        try:
            if payload is None:
                payload = json.loads(self.path.read_text(encoding="utf-8"))
            return FocusProfile(
                current_focus=payload.get("current_focus", "") or "",
                current_stage=payload.get("current_stage", "") or "",
                coaching_mode=resolve_mode(payload.get("coaching_mode", "adaptive")).key,
                coaching_notes=payload.get("coaching_notes", "") or "",
                auto_dormancy=self._parse_dormancy_settings(payload.get("auto_dormancy")),
                active_priorities=self._parse_items(payload.get("active_priorities")),
                active_projects=self._parse_items(payload.get("active_projects")),
                constraints=payload.get("constraints", []) or [],
                operating_rules=payload.get("operating_rules", []) or [],
                completed_items=self._parse_string_list(payload.get("completed_items")),
                notes=payload.get("notes", "") or "",
                last_updated=payload.get("last_updated", "") or "",
                stale_after_days=int(payload.get("stale_after_days", 14) or 14),
                evidence_window_days=max(int(payload.get("evidence_window_days", 21) or 21), 1),
            )
        except Exception as exc:
            logger.warning("读取焦点档案失败，将退回默认模式: %s", exc)
            profile = self._default_profile()
            profile.current_focus = "当前焦点档案读取失败，请不要假设旧目标仍然有效。"
            profile.operating_rules = ["如果目标不明确，就少做假设，多基于真实任务判断。"]
            return profile

    def save(self, profile: FocusProfile) -> None:
        payload = {
            "current_focus": profile.current_focus,
            "current_stage": profile.current_stage,
            "coaching_mode": resolve_mode(profile.coaching_mode).key,
            "coaching_notes": profile.coaching_notes,
            "auto_dormancy": self._dormancy_to_payload(profile.auto_dormancy),
            "active_priorities": [self._item_to_payload(item) for item in profile.active_priorities],
            "active_projects": [self._item_to_payload(item) for item in profile.active_projects],
            "constraints": profile.constraints,
            "operating_rules": profile.operating_rules,
            "completed_items": profile.completed_items,
            "notes": profile.notes,
            "last_updated": profile.last_updated,
            "stale_after_days": profile.stale_after_days,
            "evidence_window_days": profile.evidence_window_days,
        }
        if self._sqlite:
            self._sqlite.save_payload(payload)
        else:
            if not self.path.parent.exists():
                self.path.parent.mkdir(parents=True, exist_ok=True)
            self.path.write_text(
                json.dumps(payload, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )

    def evidence_window_days(self) -> int:
        return self.load().evidence_window_days

    def dormancy_settings(self) -> DormancySettings:
        return self.load().auto_dormancy

    def coaching_payload(self, mode_override: str = "") -> Dict[str, object]:
        profile = self.load()
        mode = resolve_mode(mode_override or profile.coaching_mode)
        payload = mode_payload(mode)
        payload["current_stage"] = profile.current_stage
        if profile.coaching_notes:
            payload["notes"] = profile.coaching_notes
        return payload

    def build_coaching_context(self, mode_override: str = "") -> str:
        profile = self.load()
        mode = resolve_mode(mode_override or profile.coaching_mode)
        return build_mode_context(mode, current_stage=profile.current_stage, notes=profile.coaching_notes)

    def build_context(
        self,
        recent_tasks: Optional[Sequence[TaskRecord]] = None,
        persist_activity: bool = False,
    ) -> str:
        profile = self.load()
        lines: List[str] = []

        if persist_activity and recent_tasks is not None:
            changed = self.refresh_activity(profile, recent_tasks)
            if changed and self.path.exists():
                self.save(profile)

        if profile.current_focus:
            lines.append(f"当前主题：{profile.current_focus}")
        if profile.current_stage:
            lines.append(f"当前阶段：{profile.current_stage}")

        if recent_tasks is None:
            self._append_static_items(lines, profile)
        else:
            lines.append(f"任务证据窗口：最近 {profile.evidence_window_days} 天已完成任务")
            self._append_evidence_backed_items(lines, profile, recent_tasks)

        if profile.constraints:
            lines.append("当前约束：")
            lines.extend(f"- {item}" for item in profile.constraints)

        if profile.operating_rules:
            lines.append("执行规则：")
            lines.extend(f"- {item}" for item in profile.operating_rules)

        if profile.completed_items:
            lines.append("已完成项目（除非做阶段复盘，否则不要继续当作当前目标提及）：")
            lines.extend(f"- {item}" for item in profile.completed_items[:8])

        stale_note = self._stale_note(profile)
        if stale_note:
            lines.append(stale_note)

        if profile.notes:
            lines.append(f"补充说明：{profile.notes}")

        return "\n".join(lines)

    def refresh_activity(self, profile: FocusProfile, recent_tasks: Sequence[TaskRecord]) -> bool:
        changed = False

        for items in (profile.active_priorities, profile.active_projects):
            refreshed_items, item_changed = self._refresh_items(items, recent_tasks)
            changed = changed or item_changed
            items[:] = refreshed_items

        return changed

    def ensure_default_exists(self) -> None:
        payload = {
            "current_focus": "维护当前最重要的 1-2 条主线，避免继续围绕已完成目标给建议。",
            "current_stage": "当前人生阶段一变，就更新这里，例如：从考试阶段切到内容系统建设期。",
            "coaching_mode": "adaptive",
            "coaching_notes": "状态差时切 recovery / stabilize；明确窗口期时再切 sprint。",
            "auto_dormancy": {
                "enabled": True,
                "idle_after_days": 10,
                "reminder_interval_days": 5,
                "restart_message": "如果你准备好了，先完成一个最小任务，让系统重新启动起来。",
            },
            "active_priorities": [
                {
                    "name": "在这里填写当前真正有效的优先级",
                    "keywords": ["给这个优先级补 2-4 个会真实出现在任务标题里的关键词"],
                }
            ],
            "active_projects": [],
            "constraints": [
                "脚伤恢复期，运动建议应避免高冲击",
            ],
            "operating_rules": [
                "如果目标已完成，应立即从 active_priorities 移出并放到 completed_items",
                "如果某条主线最近长期没有任务证据，系统会自动降权，不应继续复读",
            ],
            "completed_items": [],
            "notes": "",
            "last_updated": datetime.now().date().isoformat(),
            "stale_after_days": 14,
            "evidence_window_days": 21,
        }
        if self._sqlite:
            if self._sqlite.exists():
                return
            self._sqlite.save_payload(payload)
        else:
            if self.path.exists():
                return
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self.path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        logger.info("🧭 已创建默认焦点档案: %s", self.path)

    def maybe_import_json_file(self, json_path: str) -> bool:
        if not self._sqlite:
            return False
        imported = self._sqlite.maybe_import_json_file(json_path)
        if imported:
            logger.info("🧭 已从 JSON 导入焦点档案到 SQLite: %s -> %s", json_path, self.path)
        return imported

    def _append_static_items(self, lines: List[str], profile: FocusProfile) -> None:
        if profile.active_priorities:
            lines.append("当前优先级：")
            lines.extend(self._render_item(item) for item in profile.active_priorities)
        else:
            lines.append("当前优先级：未配置。请不要引用旧项目。")

        if profile.active_projects:
            lines.append("当前活跃项目：")
            lines.extend(self._render_item(item) for item in profile.active_projects)

    def _append_evidence_backed_items(
        self,
        lines: List[str],
        profile: FocusProfile,
        recent_tasks: Sequence[TaskRecord],
    ) -> None:
        activity = self._evaluate_activity(profile, recent_tasks)
        days = profile.evidence_window_days

        if activity.supported_priorities:
            lines.append("当前优先级（近期有任务证据支持）：")
            lines.extend(self._render_item(item) for item in activity.supported_priorities)
        elif profile.active_priorities:
            lines.append(f"当前优先级：最近 {days} 天没有找到明确任务证据，本轮不要沿用旧目标。")
        else:
            lines.append("当前优先级：未配置。请不要引用旧项目。")

        if activity.stale_priorities:
            lines.append(f"自动降权优先级（最近 {days} 天无任务证据，不要当作当前目标）：")
            lines.extend(self._render_item(item) for item in activity.stale_priorities)

        if activity.supported_projects:
            lines.append("当前活跃项目（近期有任务证据支持）：")
            lines.extend(self._render_item(item) for item in activity.supported_projects)
        elif profile.active_projects:
            lines.append(f"当前活跃项目：最近 {days} 天没有找到明确任务证据，本轮不要把它们当作主线。")

        if activity.stale_projects:
            lines.append(f"自动降权项目（最近 {days} 天无任务证据，不要当作当前目标）：")
            lines.extend(self._render_item(item) for item in activity.stale_projects)

    def _evaluate_activity(
        self,
        profile: FocusProfile,
        recent_tasks: Sequence[TaskRecord],
    ) -> FocusActivity:
        supported_priorities, stale_priorities = self._classify_items(profile.active_priorities, recent_tasks)
        supported_projects, stale_projects = self._classify_items(profile.active_projects, recent_tasks)
        return FocusActivity(
            supported_priorities=supported_priorities,
            stale_priorities=stale_priorities,
            supported_projects=supported_projects,
            stale_projects=stale_projects,
        )

    def _classify_items(
        self,
        items: Sequence[FocusItem],
        recent_tasks: Sequence[TaskRecord],
    ) -> Tuple[List[FocusItem], List[FocusItem]]:
        supported: List[FocusItem] = []
        stale: List[FocusItem] = []

        for item in items:
            last_seen = self._find_last_seen(item, recent_tasks)
            candidate = FocusItem(
                name=item.name,
                keywords=item.keywords,
                last_seen=last_seen or item.last_seen,
            )
            if last_seen:
                supported.append(candidate)
            else:
                stale.append(candidate)

        return supported, stale

    def _refresh_items(
        self,
        items: Sequence[FocusItem],
        recent_tasks: Sequence[TaskRecord],
    ) -> Tuple[List[FocusItem], bool]:
        refreshed: List[FocusItem] = []
        changed = False

        for item in items:
            last_seen = self._find_last_seen(item, recent_tasks)
            updated = FocusItem(
                name=item.name,
                keywords=item.keywords,
                last_seen=last_seen or item.last_seen,
            )
            refreshed.append(updated)
            if updated.last_seen != item.last_seen:
                changed = True

        return refreshed, changed

    def _find_last_seen(self, item: FocusItem, recent_tasks: Sequence[TaskRecord]) -> str:
        matched_dates: List[str] = []

        for task in recent_tasks:
            task_text = self._normalize_text(f"{task.title} {task.category} {task.priority}")
            if any(self._matches_term(task_text, term) for term in item.search_terms()):
                if task.scheduled_start:
                    matched_dates.append(task.scheduled_start.date().isoformat())

        return max(matched_dates) if matched_dates else ""

    def _matches_term(self, task_text: str, term: str) -> bool:
        normalized_term = self._normalize_text(term)
        if not normalized_term:
            return False
        return normalized_term in task_text or task_text in normalized_term

    def _render_item(self, item: FocusItem) -> str:
        if item.last_seen:
            return f"- {item.name} | 最近证据: {item.last_seen}"
        return f"- {item.name}"

    def _parse_items(self, items: Any) -> List[FocusItem]:
        parsed: List[FocusItem] = []
        for item in items or []:
            if isinstance(item, str):
                parsed.append(FocusItem(name=item))
                continue
            if isinstance(item, dict):
                name = str(item.get("name", "") or "").strip()
                if not name:
                    continue
                parsed.append(
                    FocusItem(
                        name=name,
                        keywords=self._parse_string_list(item.get("keywords")),
                        last_seen=str(item.get("last_seen", "") or "").strip(),
                    )
                )
        return parsed

    def _parse_string_list(self, values: Any) -> List[str]:
        return [str(value).strip() for value in values or [] if str(value).strip()]

    def _item_to_payload(self, item: FocusItem) -> Dict[str, Any]:
        payload: Dict[str, Any] = {"name": item.name}
        if item.keywords:
            payload["keywords"] = item.keywords
        if item.last_seen:
            payload["last_seen"] = item.last_seen
        return payload

    def _normalize_text(self, value: str) -> str:
        lowered = value.lower().strip()
        lowered = re.sub(r"\s+", "", lowered)
        return re.sub(r"[^\w\u4e00-\u9fff]+", "", lowered)

    def _parse_dormancy_settings(self, payload: Any) -> DormancySettings:
        if not isinstance(payload, dict):
            return DormancySettings()
        return DormancySettings(
            enabled=bool(payload.get("enabled", True)),
            idle_after_days=max(int(payload.get("idle_after_days", 10) or 10), 1),
            reminder_interval_days=max(int(payload.get("reminder_interval_days", 5) or 5), 1),
            restart_message=str(
                payload.get(
                    "restart_message",
                    "如果你准备好了，先完成一个最小任务，让系统重新启动起来。",
                )
                or "如果你准备好了，先完成一个最小任务，让系统重新启动起来。"
            ),
        )

    def _dormancy_to_payload(self, settings: DormancySettings) -> Dict[str, Any]:
        return {
            "enabled": settings.enabled,
            "idle_after_days": settings.idle_after_days,
            "reminder_interval_days": settings.reminder_interval_days,
            "restart_message": settings.restart_message,
        }

    def _stale_note(self, profile: FocusProfile) -> str:
        if not profile.last_updated:
            return "警告：焦点档案没有 last_updated，输出时不要过度依赖其中的项目名。"

        try:
            last_updated = datetime.fromisoformat(profile.last_updated).date()
        except ValueError:
            return "警告：焦点档案 last_updated 格式无效，输出时不要过度依赖其中的项目名。"

        age_days = (datetime.now().date() - last_updated).days
        if age_days > profile.stale_after_days:
            return (
                f"警告：焦点档案距今已 {age_days} 天，可能过期。"
                "如果当前任务数据与档案冲突，应优先相信真实任务数据，不要重复旧目标。"
            )
        return ""

    def _default_profile(self) -> FocusProfile:
        return FocusProfile(
            current_focus="当前焦点未配置，请优先依据近期真实任务判断，不要假设旧目标仍然有效。",
            current_stage="当前阶段未配置。",
            coaching_mode="adaptive",
            auto_dormancy=DormancySettings(),
            operating_rules=[
                "如果没有明确的当前主线，就围绕最近任务里重复出现的方向给建议。",
                "不要提及未在当前焦点档案中声明的旧项目。",
            ],
        )
