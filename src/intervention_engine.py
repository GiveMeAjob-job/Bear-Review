import math
import re
from dataclasses import asdict, dataclass, field
from typing import Dict, List, Optional, Sequence

from .coaching_principles import (
    build_doctrine_context,
    deserialize_principles,
    select_principles,
    serialize_principles,
)
from .coaching_modes import mode_payload, resolve_mode
from .models import TaskRecord
from .review_memory import MemoryEntry, ReviewMemoryStore


@dataclass
class ActionReview:
    status: str
    previous_follow_up: str = ""
    explanation: str = ""
    evidence: List[str] = field(default_factory=list)

    @property
    def label(self) -> str:
        mapping = {
            "no_previous_action": "没有上一次行动可追踪",
            "done": "已观察到较强执行证据",
            "partial": "只观察到部分执行证据",
            "no_evidence": "未观察到明确执行证据",
        }
        return mapping.get(self.status, self.status)


@dataclass
class AnomalySignal:
    key: str
    severity: int
    summary: str
    evidence: str = ""


@dataclass
class InterventionResult:
    action_review: ActionReview
    anomalies: List[AnomalySignal] = field(default_factory=list)
    principles: List[Dict[str, str]] = field(default_factory=list)
    coaching_mode: Dict[str, object] = field(default_factory=dict)
    should_notify: bool = False

    def prompt_context(self) -> str:
        lines = [
            f"通知建议：{'值得主动提醒' if self.should_notify else '无需额外打断，只需记录'}",
            f"行动闭环：{self.action_review.label}",
        ]

        if self.action_review.previous_follow_up:
            lines.append(f"上一次跟进动作：{self.action_review.previous_follow_up}")
        if self.action_review.explanation:
            lines.append(f"闭环说明：{self.action_review.explanation}")
        if self.action_review.evidence:
            lines.append("行动证据：")
            lines.extend(f"- {item}" for item in self.action_review.evidence[:3])

        if self.anomalies:
            lines.append("异常信号：")
            for signal in self.anomalies[:3]:
                detail = f" | {signal.evidence}" if signal.evidence else ""
                lines.append(f"- {signal.summary}{detail}")
        else:
            lines.append("异常信号：当前未发现值得单独打断的明显偏差。")

        if self.principles:
            lines.append("当前操作原则：")
            lines.extend(
                f"- {item.get('name', '')}：{item.get('action_rule', '')}"
                for item in self.principles[:2]
                if item.get("name")
            )

        if self.coaching_mode.get("name"):
            lines.append(f"当前教练模式：{self.coaching_mode.get('name')}")
            decision_rule = self.coaching_mode.get("decision_rule", "")
            if decision_rule:
                lines.append(f"模式口径：{decision_rule}")

        lines.append(build_doctrine_context(deserialize_principles(self.principles)))
        lines.append("如果没有异常，不要硬造危机；如果有异常，请明确指出它为什么值得现在提醒。")
        return "\n".join(lines)

    def preview_summary(self) -> str:
        action_line = f"行动闭环：{self.action_review.label}"
        principle_line = ""
        mode_line = ""
        if self.principles:
            principle_line = " | 原则：" + "；".join(
                item.get("name", "") for item in self.principles[:2] if item.get("name")
            )
        if self.coaching_mode.get("name"):
            mode_line = f" | 模式：{self.coaching_mode.get('name')}"
        if self.anomalies:
            top = "；".join(signal.summary for signal in self.anomalies[:2])
            return (
                f"干预判断：{'值得提醒' if self.should_notify else '记录即可'}"
                f" | {action_line}{mode_line}{principle_line} | 异常：{top}"
            )
        return (
            f"干预判断：{'值得提醒' if self.should_notify else '记录即可'}"
            f" | {action_line}{mode_line}{principle_line}"
        )

    def as_dict(self) -> Dict:
        return {
            "should_notify": self.should_notify,
            "action_review": asdict(self.action_review),
            "anomalies": [asdict(signal) for signal in self.anomalies],
            "principles": self.principles,
            "coaching_mode": self.coaching_mode,
        }


class InterventionEngine:
    def __init__(self, history_limit: int = 4):
        self.history_limit = history_limit

    def evaluate(
        self,
        period: str,
        current_stats: Dict,
        current_tasks: Sequence[TaskRecord],
        memory_store: Optional[ReviewMemoryStore] = None,
        recent_tasks: Optional[Sequence[TaskRecord]] = None,
        coaching_mode: str = "adaptive",
    ) -> InterventionResult:
        mode = resolve_mode(coaching_mode)
        history = memory_store.recent_entries(period=period, limit=self.history_limit) if memory_store else []
        previous_action_entry = memory_store.latest_follow_up_entry(period) if memory_store else None
        action_review = self._evaluate_action_review(
            previous_action_entry,
            current_tasks=current_tasks,
            recent_tasks=recent_tasks or current_tasks,
            current_stats=current_stats,
        )
        anomalies = self._detect_anomalies(period, current_stats, history)
        principles = serialize_principles(
            select_principles(
                period=period,
                current_stats=current_stats,
                action_status=action_review.status,
                anomalies=[asdict(item) for item in anomalies],
                mode_key=mode.key,
            )
        )
        should_notify = self._should_notify(period, current_stats, action_review, anomalies, mode.key)
        return InterventionResult(
            action_review=action_review,
            anomalies=anomalies,
            principles=principles,
            coaching_mode=mode_payload(mode),
            should_notify=should_notify,
        )

    def _evaluate_action_review(
        self,
        previous_entry: Optional[MemoryEntry],
        current_tasks: Sequence[TaskRecord],
        recent_tasks: Sequence[TaskRecord],
        current_stats: Dict,
    ) -> ActionReview:
        if not previous_entry or not previous_entry.follow_up:
            return ActionReview(
                status="no_previous_action",
                explanation="历史记忆里没有可追踪的上一次跟进行动。",
            )

        follow_up = previous_entry.follow_up.strip()
        keywords = self._extract_keywords(follow_up)
        match_score, matched_titles = self._rank_task_matches(
            follow_up,
            keywords,
            current_tasks,
            recent_tasks,
        )

        if match_score > 0:
            threshold = self._done_threshold(len(keywords))
            if match_score >= threshold:
                return ActionReview(
                    status="done",
                    previous_follow_up=follow_up,
                    explanation=f"最近任务与上一次行动有较强重合，累计匹配关键词 {match_score} 个。",
                    evidence=matched_titles,
                )
            return ActionReview(
                status="partial",
                previous_follow_up=follow_up,
                explanation=f"只观察到部分任务证据，累计匹配关键词 {match_score} 个。",
                evidence=matched_titles,
            )

        if "mit" in self._normalize_text(follow_up) and (current_stats.get("mit_count", 0) or 0) > 0:
            return ActionReview(
                status="partial",
                previous_follow_up=follow_up,
                explanation="没有直接匹配到标题，但本次至少完成了 MIT，说明动作方向可能有部分兑现。",
            )

        return ActionReview(
            status="no_evidence",
            previous_follow_up=follow_up,
            explanation="当前任务里没有观察到足够证据，不能把它算作已执行。",
        )

    def _detect_anomalies(
        self,
        period: str,
        current_stats: Dict,
        history: Sequence[MemoryEntry],
    ) -> List[AnomalySignal]:
        if not history:
            return []

        anomalies: List[AnomalySignal] = []
        averages = self._average_stats(history)
        current_total = current_stats.get("total", 0) or 0

        if averages.get("total", 0) >= 2 and current_total == 0:
            anomalies.append(
                AnomalySignal(
                    key="zero_output",
                    severity=3,
                    summary="本轮没有任何完成任务，低于近期常态",
                    evidence=f"近期同周期平均完成 {averages['total']:.1f} 项",
                )
            )

        current_mit = current_stats.get("mit_count", 0) or 0
        if averages.get("mit_count", 0) >= 1.5 and current_mit == 0:
            anomalies.append(
                AnomalySignal(
                    key="mit_drop",
                    severity=3,
                    summary="MIT 直接掉到 0，主线推进断档",
                    evidence=f"近期同周期平均 MIT {averages['mit_count']:.1f}",
                )
            )

        current_xp = current_stats.get("xp", 0) or 0
        avg_xp = averages.get("xp", 0)
        if avg_xp >= 20 and current_xp < avg_xp * 0.6:
            anomalies.append(
                AnomalySignal(
                    key="xp_drop",
                    severity=2,
                    summary="XP 明显低于近期水平",
                    evidence=f"本次 {current_xp}，近期均值 {avg_xp:.1f}",
                )
            )

        work_key = "work_hours" if "work_hours" in current_stats else "actual_work_hours"
        current_work = current_stats.get(work_key, 0) or 0
        avg_work = averages.get(work_key, 0)
        if avg_work >= 2 and current_work < avg_work * 0.6:
            anomalies.append(
                AnomalySignal(
                    key="work_drop",
                    severity=2,
                    summary="有效工作时长明显下滑",
                    evidence=f"本次 {current_work}h，近期均值 {avg_work:.1f}h",
                )
            )

        current_tomatoes = current_stats.get("tomatoes", 0) or 0
        avg_tomatoes = averages.get("tomatoes", 0)
        if avg_tomatoes >= 2 and current_tomatoes == 0:
            anomalies.append(
                AnomalySignal(
                    key="tomato_break",
                    severity=2,
                    summary="番茄执行断档，节奏感消失",
                    evidence=f"近期同周期平均番茄 {avg_tomatoes:.1f}",
                )
            )

        if period == "three-days":
            current_ent = current_stats.get("entertainment_hours", 0) or 0
            avg_ent = averages.get("entertainment_hours", 0)
            if avg_ent >= 1 and current_ent > avg_ent * 1.5 and current_ent - avg_ent >= 1:
                anomalies.append(
                    AnomalySignal(
                        key="entertainment_spike",
                        severity=2,
                        summary="娱乐时长高于近期均值，可能挤压主线推进",
                        evidence=f"本次 {current_ent}h，近期均值 {avg_ent:.1f}h",
                    )
                )

        anomalies.sort(key=lambda item: item.severity, reverse=True)
        return anomalies[:3]

    def _should_notify(
        self,
        period: str,
        current_stats: Dict,
        action_review: ActionReview,
        anomalies: Sequence[AnomalySignal],
        coaching_mode: str,
    ) -> bool:
        if period in {"weekly", "monthly"}:
            return True

        mode = resolve_mode(coaching_mode)
        high_severity = any(signal.severity >= 3 for signal in anomalies)
        any_anomaly = bool(anomalies)
        broken_loop = action_review.status in {"partial", "no_evidence"}
        no_output = (current_stats.get("total", 0) or 0) == 0
        if mode.notify_bias >= 1:
            return high_severity or any_anomaly or broken_loop or no_output
        if mode.notify_bias <= -1:
            return high_severity or no_output
        return high_severity or (any_anomaly and broken_loop) or no_output

    def _average_stats(self, history: Sequence[MemoryEntry]) -> Dict[str, float]:
        keys = {
            "total",
            "xp",
            "mit_count",
            "tomatoes",
            "work_hours",
            "actual_work_hours",
            "entertainment_hours",
        }
        averages: Dict[str, float] = {}
        for key in keys:
            values = [float(entry.stats.get(key, 0) or 0) for entry in history if entry.stats]
            if values:
                averages[key] = sum(values) / len(values)
        return averages

    def _rank_task_matches(
        self,
        follow_up: str,
        keywords: Sequence[str],
        current_tasks: Sequence[TaskRecord],
        recent_tasks: Sequence[TaskRecord],
    ) -> tuple[int, List[str]]:
        candidates = list(current_tasks) + [task for task in recent_tasks if task not in current_tasks]
        matched_keywords = set()
        evidence_titles: List[str] = []

        for task in candidates:
            task_text = self._normalize_text(f"{task.title} {task.category} {task.priority}")
            if not task_text:
                continue

            matched = [
                keyword
                for keyword in keywords
                if keyword and self._normalize_text(keyword) and self._normalize_text(keyword) in task_text
            ]
            score = len(set(matched))

            follow_up_text = self._normalize_text(follow_up)
            if score == 0 and follow_up_text and task_text in follow_up_text:
                score = 1

            if score > 0:
                matched_keywords.update(matched or [follow_up])
                if task.title not in evidence_titles:
                    evidence_titles.append(task.title)

        return len(matched_keywords), evidence_titles[:3]

    def _done_threshold(self, keyword_count: int) -> int:
        if keyword_count <= 1:
            return 1
        return max(2, math.ceil(keyword_count * 0.6))

    def _extract_keywords(self, follow_up: str) -> List[str]:
        raw_tokens = re.split(r"[\s,，、/|；;:：()（）\-]+", follow_up)
        stopwords = {
            "今天",
            "明天",
            "本周",
            "下周",
            "本月",
            "下月",
            "先",
            "再",
            "然后",
            "一个",
            "一次",
            "分钟",
            "小时",
            "之前",
            "之后",
            "上午",
            "下午",
            "晚上",
            "完成",
            "推进",
            "安排",
            "保持",
            "继续",
        }
        keywords: List[str] = []
        for token in raw_tokens:
            token = token.strip()
            if not token:
                continue
            for candidate in self._expand_token(token):
                normalized = self._normalize_text(candidate)
                if not candidate or candidate in stopwords:
                    continue
                if len(normalized) < 2 and normalized not in {"xp", "mit"}:
                    continue
                if candidate not in keywords:
                    keywords.append(candidate)
        return keywords[:8]

    def _expand_token(self, token: str) -> List[str]:
        expanded = [token]
        expanded.extend(re.findall(r"[A-Za-z0-9]{2,}", token))

        for chunk in re.findall(r"[\u4e00-\u9fff]{2,}", token):
            expanded.append(chunk)
            expanded.extend(
                part
                for part in re.split(r"[先再和与把将去做并前后停要]", chunk)
                if len(part) >= 2
            )

        unique: List[str] = []
        for item in expanded:
            if item not in unique:
                unique.append(item)
        return unique

    def _normalize_text(self, value: str) -> str:
        lowered = value.lower().strip()
        lowered = re.sub(r"\s+", "", lowered)
        return re.sub(r"[^\w\u4e00-\u9fff]+", "", lowered)
