from __future__ import annotations

from datetime import datetime, timedelta
from typing import Dict, Optional, Tuple

import pytz

from .config import Config
from .coaching_modes import build_mode_context, mode_payload, resolve_mode
from .engine_state import DormancyDecision, DormancySettings, EngineStateStore
from .focus_profile import FocusProfileStore
from .intervention_engine import InterventionEngine
from .llm_client import LLMClient
from .models import ReviewReport
from .review_memory import ReviewMemoryStore
from .summarizer import TaskSummarizer
from .task_source import TaskSource


class ReviewService:
    def __init__(
        self,
        config: Config,
        notion: TaskSource,
        summarizer: TaskSummarizer,
        llm: LLMClient,
        memory_store: Optional[ReviewMemoryStore] = None,
        focus_profile_store: Optional[FocusProfileStore] = None,
        intervention_engine: Optional[InterventionEngine] = None,
        coaching_mode_override: str = "",
        engine_state_store: Optional[EngineStateStore] = None,
    ) -> None:
        self.config = config
        self.notion = notion
        self.summarizer = summarizer
        self.llm = llm
        self.memory_store = memory_store
        self.focus_profile_store = focus_profile_store
        self.intervention_engine = intervention_engine or InterventionEngine()
        self.coaching_mode_override = coaching_mode_override
        self.engine_state_store = engine_state_store

    def _recent_task_window_days(self) -> int:
        focus_window = self.focus_profile_store.evidence_window_days() if self.focus_profile_store else 7
        dormancy_window = self._dormancy_settings().idle_after_days
        return max(focus_window, dormancy_window, 7)

    def _fetch_recent_tasks(self):
        return self.notion.fetch_recent_tasks(self._recent_task_window_days())

    def _dormancy_settings(self) -> DormancySettings:
        if self.focus_profile_store:
            return self.focus_profile_store.dormancy_settings()
        return DormancySettings()

    def _build_focus_context(self, recent_tasks) -> str:
        if not self.focus_profile_store:
            return ""

        return self.focus_profile_store.build_context(
            recent_tasks=recent_tasks,
            persist_activity=True,
        )

    def _build_coaching_context(self) -> str:
        if self.focus_profile_store:
            return self.focus_profile_store.build_coaching_context(mode_override=self.coaching_mode_override)
        mode = resolve_mode(self.coaching_mode_override)
        return build_mode_context(mode)

    def _coaching_payload(self) -> Dict[str, object]:
        if self.focus_profile_store:
            return self.focus_profile_store.coaching_payload(mode_override=self.coaching_mode_override)
        return mode_payload(resolve_mode(self.coaching_mode_override))

    def _evaluate_dormancy(self, tasks, recent_tasks) -> Optional[DormancyDecision]:
        if not self.engine_state_store:
            return None

        tz = pytz.timezone(self.config.timezone)
        today = datetime.now(tz).date()
        decision = self.engine_state_store.evaluate(
            settings=self._dormancy_settings(),
            current_tasks=tasks,
            recent_tasks=recent_tasks,
            today=today,
        )
        self.engine_state_store.save()
        return decision

    def _build_dormancy_report(self, period: str, dormancy: DormancyDecision) -> ReviewReport:
        tz = pytz.timezone(self.config.timezone)
        today = datetime.now(tz).date()
        dormant_since = datetime.fromisoformat(dormancy.dormant_since).date() if dormancy.dormant_since else today
        dormant_days = max((today - dormant_since).days, 0)
        title = f"{self.config.notification_title_prefix} Restart Nudge · {today.isoformat()}"
        content = self.summarizer.build_dormancy_review(
            dormant_days=dormant_days,
            idle_after_days=dormancy.idle_after_days,
            last_active_date=dormancy.last_active_date,
            restart_message=dormancy.restart_message,
        )
        preview = self.summarizer.build_dormancy_preview(
            reminder_due=dormancy.reminder_due,
            dormant_days=dormant_days,
            restart_message=dormancy.restart_message,
        )
        decision_card = self.summarizer.build_dormancy_decision_card(
            reminder_due=dormancy.reminder_due,
            dormant_days=dormant_days,
            last_active_date=dormancy.last_active_date,
            reminder_interval_days=dormancy.reminder_interval_days,
            restart_message=dormancy.restart_message,
        )
        signals = {
            "should_notify": dormancy.reminder_due,
            "delivery_policy": dormancy.delivery_policy,
            "dormancy": dormancy.as_dict(),
        }
        return ReviewReport(
            period=period,
            title=title,
            content=content,
            preview=preview,
            decision_card=decision_card,
            stats={"total": 0, "xp": 0, "mit_count": 0},
            signals=signals,
        )

    def generate_report(self, period: str, is_yesterday: bool = False) -> ReviewReport:
        if period == "three-days":
            return self._generate_three_day_report()

        tasks = (
            self.notion.fetch_yesterday_tasks()
            if period == "daily" and is_yesterday
            else self.notion.fetch_period_tasks(period)
        )
        title = self._build_title(period, is_yesterday)
        recent_tasks = self._fetch_recent_tasks()
        current_stats = {"total": len(tasks), "xp": 0, "mit_count": 0}
        coaching_payload = self._coaching_payload()
        coaching_context = self._build_coaching_context()
        dormancy = self._evaluate_dormancy(tasks, recent_tasks)
        if dormancy and dormancy.is_dormant:
            return self._build_dormancy_report(period, dormancy)

        if not tasks:
            content = self.summarizer.build_empty_review(period)
            intervention = self.intervention_engine.evaluate(
                period,
                current_stats=current_stats,
                current_tasks=[],
                memory_store=self.memory_store,
                recent_tasks=recent_tasks,
                coaching_mode=str(coaching_payload.get("key", "adaptive")),
            )
            preview = self.summarizer.build_preview(
                period,
                current_stats,
                content,
                intervention_summary=intervention.preview_summary(),
            )
            decision_card = self.summarizer.build_decision_card(
                period,
                current_stats,
                intervention.as_dict(),
                content,
            )
            return ReviewReport(
                period=period,
                title=title,
                content=content,
                preview=preview,
                decision_card=decision_card,
                stats=current_stats,
                signals=intervention.as_dict(),
            )

        stats, task_details = self.summarizer.get_detailed_stats(tasks)
        memory_context = self.memory_store.build_context(period, stats) if self.memory_store else ""
        focus_context = self._build_focus_context(recent_tasks)
        intervention = self.intervention_engine.evaluate(
            period,
            current_stats=stats,
            current_tasks=tasks,
            memory_store=self.memory_store,
            recent_tasks=recent_tasks,
            coaching_mode=str(coaching_payload.get("key", "adaptive")),
        )
        prompt = self.summarizer.build_prompt(
            stats,
            task_details,
            period,
            memory_context=memory_context,
            focus_context=focus_context,
            coaching_context=coaching_context,
            intervention_context=intervention.prompt_context(),
        )
        content = self.llm.ask_llm(prompt)
        preview = self.summarizer.build_preview(
            period,
            stats,
            content,
            intervention_summary=intervention.preview_summary(),
        )
        decision_card = self.summarizer.build_decision_card(
            period,
            stats,
            intervention.as_dict(),
            content,
        )
        return ReviewReport(
            period=period,
            title=title,
            content=content,
            preview=preview,
            decision_card=decision_card,
            stats=stats,
            prompt=prompt,
            signals=intervention.as_dict(),
        )

    def _generate_three_day_report(self) -> ReviewReport:
        tz = pytz.timezone(self.config.timezone)
        today = datetime.now(tz).date()
        three_days_stats: Dict[str, Dict] = {}
        current_tasks = []

        for days_ago in (1, 2, 3):
            target_date = today - timedelta(days=days_ago)
            tasks = self.notion.fetch_tasks_for_date(target_date)
            # Keep the underlying tasks so action-closure can look for evidence.
            current_tasks.extend(tasks)
            three_days_stats[target_date.isoformat()] = self.summarizer.get_trend_stats(tasks)

        aggregate_stats = {
            "total": sum(day.get("total", 0) for day in three_days_stats.values()),
            "xp": sum(day.get("xp", 0) for day in three_days_stats.values()),
            "mit_count": sum(day.get("mit_count", 0) for day in three_days_stats.values()),
            "tomatoes": sum(day.get("tomatoes", 0) for day in three_days_stats.values()),
            "actual_work_hours": sum(day.get("actual_work_hours", 0) for day in three_days_stats.values()),
            "entertainment_hours": sum(day.get("entertainment_hours", 0) for day in three_days_stats.values()),
        }
        recent_tasks = self._fetch_recent_tasks()
        dormancy = self._evaluate_dormancy(current_tasks, recent_tasks)
        if dormancy and dormancy.is_dormant:
            return self._build_dormancy_report("three-days", dormancy)
        memory_context = self.memory_store.build_context("three-days", aggregate_stats) if self.memory_store else ""
        focus_context = self._build_focus_context(recent_tasks)
        coaching_payload = self._coaching_payload()
        coaching_context = self._build_coaching_context()
        intervention = self.intervention_engine.evaluate(
            "three-days",
            current_stats=aggregate_stats,
            current_tasks=current_tasks,
            memory_store=self.memory_store,
            recent_tasks=recent_tasks,
            coaching_mode=str(coaching_payload.get("key", "adaptive")),
        )
        prompt = self.summarizer.build_three_day_prompt(
            three_days_stats,
            memory_context=memory_context,
            focus_context=focus_context,
            coaching_context=coaching_context,
            intervention_context=intervention.prompt_context(),
        )
        content = self.llm.ask_llm(prompt, max_tokens=1800)
        preview = self.summarizer.build_preview(
            "three-days",
            aggregate_stats,
            content,
            intervention_summary=intervention.preview_summary(),
        )
        decision_card = self.summarizer.build_decision_card(
            "three-days",
            aggregate_stats,
            intervention.as_dict(),
            content,
        )
        return ReviewReport(
            period="three-days",
            title=self._build_title("three-days", False),
            content=content,
            preview=preview,
            decision_card=decision_card,
            stats=aggregate_stats,
            prompt=prompt,
            signals=intervention.as_dict(),
        )

    def _build_title(self, period: str, is_yesterday: bool) -> str:
        tz = pytz.timezone(self.config.timezone)
        today = datetime.now(tz).date()
        target_date = today - timedelta(days=1) if period == "daily" and is_yesterday else today
        label_map = {
            "daily": "Daily Review",
            "three-days": "3-Day Trend",
            "weekly": "Weekly Review",
            "monthly": "Monthly Review",
        }
        label = label_map.get(period, f"{period.title()} Review")
        return f"{self.config.notification_title_prefix} {label} · {target_date.isoformat()}"
