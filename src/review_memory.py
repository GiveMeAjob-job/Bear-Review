import json
import re
from collections import Counter
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

from .models import ReviewReport
from .sqlite_state_store import SQLiteStateStore
from .utils import setup_logger

logger = setup_logger(__name__)


@dataclass
class MemoryEntry:
    period: str
    title: str
    preview: str
    generated_at: str
    stats: Dict
    tags: List[str]
    follow_up: str


class ReviewMemoryStore:
    def __init__(self, path: str, max_entries: int = 40):
        self.path = Path(path)
        self.max_entries = max_entries
        self.entries: List[MemoryEntry] = []
        self._loaded = False
        self._sqlite = SQLiteStateStore(path, "review_memory") if self.path.suffix == ".db" else None

    def load(self) -> None:
        if self._loaded:
            return

        if self._sqlite:
            payload = self._sqlite.load_payload()
            if payload is None:
                self.entries = []
                self._loaded = True
                return
        elif not self.path.exists():
            self.entries = []
            self._loaded = True
            return

        try:
            if self._sqlite:
                payload = payload or {}
            else:
                payload = json.loads(self.path.read_text(encoding="utf-8"))
            records = payload.get("entries", [])
            self.entries = [
                MemoryEntry(
                    period=record.get("period", ""),
                    title=record.get("title", ""),
                    preview=record.get("preview", ""),
                    generated_at=record.get("generated_at", ""),
                    stats=record.get("stats", {}) or {},
                    tags=record.get("tags", []) or [],
                    follow_up=record.get("follow_up", ""),
                )
                for record in records
            ]
        except Exception as exc:
            logger.warning("读取复盘记忆失败，将使用空记忆: %s", exc)
            self.entries = []

        self._loaded = True

    def build_context(self, period: str, current_stats: Dict) -> str:
        self.load()
        if not self.entries:
            return "无历史记忆。请把本次输出写成可延续的下一步，而不是一次性总结。"

        recent_same = self.recent_entries(period=period, limit=2)
        recent_all = self.recent_entries(limit=4)

        tag_counter = Counter()
        for entry in recent_all:
            tag_counter.update(entry.tags)

        recurring_tags = [tag for tag, count in tag_counter.items() if count >= 2][:5]
        last_follow_up = recent_same[-1].follow_up if recent_same else (recent_all[-1].follow_up if recent_all else "")
        previous_stats = recent_same[-1].stats if recent_same else {}

        lines = ["这是一个连续复盘系统，请基于历史记忆判断变化，而不是重复上次的结论。"]

        if recent_same:
            lines.append("最近同周期复盘：")
            for entry in recent_same:
                lines.append(f"- {entry.generated_at} | {entry.preview}")

        if previous_stats:
            lines.append(f"与上次同周期相比：{self._describe_stat_change(previous_stats, current_stats)}")

        if recurring_tags:
            lines.append(f"近期高频标签：{', '.join(recurring_tags)}")
            lines.append("如果这些问题本次仍存在，只需指出它仍未解决和新的证据，不要整段重复旧建议。")

        if last_follow_up:
            lines.append(f"上一次承诺跟进：{last_follow_up}")
            lines.append("请明确判断这次对这项跟进是完成、部分完成还是未推进，并说明原因。")

        lines.append("本次输出优先写新变化、真正有效的杠杆和下一轮唯一值得追踪的动作。")
        return "\n".join(lines)

    def recent_entries(self, period: Optional[str] = None, limit: int = 4) -> List[MemoryEntry]:
        self.load()
        items = self.entries if period is None else [entry for entry in self.entries if entry.period == period]
        if limit <= 0:
            return []
        return items[-limit:]

    def latest_follow_up_entry(self, period: str) -> Optional[MemoryEntry]:
        self.load()
        same_period = [entry for entry in self.entries if entry.period == period and entry.follow_up]
        if same_period:
            return same_period[-1]

        with_follow_up = [entry for entry in self.entries if entry.follow_up]
        return with_follow_up[-1] if with_follow_up else None

    def record_report(self, report: ReviewReport, generated_at: Optional[str] = None) -> None:
        self.load()
        timestamp = generated_at or datetime.now().isoformat()
        delivery_policy = (report.signals or {}).get("delivery_policy", "normal")
        if delivery_policy in {"suppress", "restart_nudge"}:
            logger.info("当前输出属于休眠状态管理，不写入长期复盘记忆")
            return
        tags = self._extract_tags(report.content)
        follow_up = self._extract_follow_up(report.content)
        total_tasks = (report.stats or {}).get("total", 0)

        if total_tasks == 0 and not tags:
            logger.info("复盘无有效任务且无标签，本次不写入长期记忆")
            return

        if not follow_up:
            follow_up = self._fallback_follow_up(report.preview)

        self.entries.append(
            MemoryEntry(
                period=report.period,
                title=report.title,
                preview=report.preview,
                generated_at=timestamp,
                stats=report.stats or {},
                tags=tags,
                follow_up=follow_up,
            )
        )
        self.entries = self.entries[-self.max_entries :]

    def save(self) -> None:
        self.load()
        payload = {
            "version": 1,
            "entries": [
                {
                    "period": entry.period,
                    "title": entry.title,
                    "preview": entry.preview,
                    "generated_at": entry.generated_at,
                    "stats": entry.stats,
                    "tags": entry.tags,
                    "follow_up": entry.follow_up,
                }
                for entry in self.entries
            ],
        }
        if self._sqlite:
            self._sqlite.save_payload(payload)
        else:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self.path.write_text(
                json.dumps(payload, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        logger.info("🧠 已更新复盘记忆: %s", self.path)

    def maybe_import_json_file(self, json_path: str) -> bool:
        if not self._sqlite:
            return False
        imported = self._sqlite.maybe_import_json_file(json_path)
        if imported:
            self._loaded = False
            self.entries = []
            logger.info("🧠 已从 JSON 导入复盘记忆到 SQLite: %s -> %s", json_path, self.path)
        return imported

    def _extract_tags(self, content: str) -> List[str]:
        match = re.search(r"复盘标签[:：]\s*(.+)", content)
        if not match:
            return []
        raw = match.group(1)
        parts = re.split(r"[，,、；;|/]", raw)
        tags = [part.strip() for part in parts if part.strip()]
        return tags[:5]

    def _extract_follow_up(self, content: str) -> str:
        match = re.search(r"下一轮跟进[:：]\s*(.+)", content)
        if match:
            return match.group(1).strip()
        return ""

    def _fallback_follow_up(self, preview: str) -> str:
        preview = preview.strip().replace("\n", " ")
        if len(preview) <= 90:
            return preview
        return preview[:90].rstrip() + "…"

    def _describe_stat_change(self, previous: Dict, current: Dict) -> str:
        keys = [
            ("total", "任务数"),
            ("xp", "XP"),
            ("mit_count", "MIT"),
            ("tomatoes", "番茄"),
            ("work_hours", "工作时长"),
        ]
        changes = []
        for key, label in keys:
            if key not in previous and key not in current:
                continue
            before = previous.get(key, 0) or 0
            after = current.get(key, 0) or 0
            delta = after - before
            if delta > 0:
                changes.append(f"{label}+{delta}")
            elif delta < 0:
                changes.append(f"{label}{delta}")
            else:
                changes.append(f"{label}持平")
        return "，".join(changes) if changes else "暂无可比较的核心指标"
