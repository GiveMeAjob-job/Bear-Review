from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, Optional


@dataclass
class TaskRecord:
    id: str
    title: str
    category: str = "未分类"
    priority: str = ""
    status: str = ""
    scheduled_start: Optional[datetime] = None
    scheduled_end: Optional[datetime] = None
    xp: int = 0
    tomatoes: int = 0
    actual_minutes: int = 0
    raw: Dict[str, Any] = field(default_factory=dict)

    @property
    def is_mit(self) -> bool:
        return self.priority == "MIT"


@dataclass
class TaskAlias:
    id: str
    alias_name: str
    title: str
    category: str = "未分类"
    priority: str = ""
    actual_minutes: int = 0
    tomatoes: int = 0
    xp: int = 0
    note: str = ""
    raw: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ReviewReport:
    period: str
    title: str
    content: str
    preview: str
    decision_card: str = ""
    stats: Dict[str, Any] = field(default_factory=dict)
    prompt: str = ""
    signals: Dict[str, Any] = field(default_factory=dict)
