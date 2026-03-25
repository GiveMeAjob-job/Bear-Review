from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Dict, List, Sequence

from .coaching_modes import resolve_mode


@dataclass(frozen=True)
class CoachingPrinciple:
    key: str
    name: str
    summary: str
    action_rule: str


_PRINCIPLE_ORDER = [
    CoachingPrinciple(
        key="soldier_on",
        name="继续向前（soldier on）",
        summary="局面差时先守住最小推进，不因为一轮失手就整体停摆。",
        action_rule="把下一步压缩成低阻力、可完成的最小动作。",
    ),
    CoachingPrinciple(
        key="no_self_pity",
        name="不要自怜",
        summary="不要围绕情绪反复解释，把痛苦当成约束条件而不是身份结论。",
        action_rule="先写清楚约束，再决定今天仍然能做的一件事。",
    ),
    CoachingPrinciple(
        key="no_envy",
        name="不要嫉妒",
        summary="不要用别人的进度扰动自己的路线，只看自己的主线和证据。",
        action_rule="判断优先级时只参考当前目标、任务证据和复盘数据。",
    ),
    CoachingPrinciple(
        key="turn_setback_into_feedback",
        name="把逆风变成训练",
        summary="不顺是数据，不是判决；关键是找出系统缺口和下一次改法。",
        action_rule="把异常翻译成一个可验证的实验或边界，而不是一句感慨。",
    ),
    CoachingPrinciple(
        key="watch_for_real_opportunity",
        name="押注少数真正机会",
        summary="风浪会反复出现，但高杠杆机会不多，要把资源集中在最有效的一件事上。",
        action_rule="只保留一个最值得加码的方向，其他动作一律降级。",
    ),
]


def all_principles() -> List[CoachingPrinciple]:
    return list(_PRINCIPLE_ORDER)


def serialize_principles(principles: Sequence[CoachingPrinciple]) -> List[Dict[str, str]]:
    return [asdict(item) for item in principles]


def build_doctrine_context(selected: Sequence[CoachingPrinciple]) -> str:
    lines = ["本系统默认采用以下逆境原则，不把低谷解释成身份判断："]
    lines.extend(f"- {item.name}：{item.summary}" for item in _PRINCIPLE_ORDER)
    if selected:
        lines.append("本次优先调用：")
        for item in selected:
            lines.append(f"- {item.name}：{item.action_rule}")
    lines.append("请把这些原则翻译成今天/本周的判断和动作，不要直接堆砌名言。")
    return "\n".join(lines)


def deserialize_principles(items: Sequence[Dict[str, str]]) -> List[CoachingPrinciple]:
    principles: List[CoachingPrinciple] = []
    for item in items:
        if not item.get("key"):
            continue
        principles.append(
            CoachingPrinciple(
                key=item.get("key", ""),
                name=item.get("name", ""),
                summary=item.get("summary", ""),
                action_rule=item.get("action_rule", ""),
            )
        )
    return principles


def select_principles(
    period: str,
    current_stats: Dict,
    action_status: str,
    anomalies: Sequence[Dict],
    mode_key: str = "adaptive",
) -> List[CoachingPrinciple]:
    scores = {item.key: 0 for item in _PRINCIPLE_ORDER}
    rank_index = {item.key: index for index, item in enumerate(_PRINCIPLE_ORDER)}
    mode = resolve_mode(mode_key)
    total = current_stats.get("total", 0) or 0
    mit_count = current_stats.get("mit_count", 0) or 0
    xp = current_stats.get("xp", 0) or 0
    anomaly_keys = {item.get("key", "") for item in anomalies}
    high_severity = any((item.get("severity", 0) or 0) >= 3 for item in anomalies)
    any_anomaly = bool(anomalies)
    productive = total > 0 or mit_count > 0 or xp > 0
    broken_loop = action_status in {"partial", "no_evidence"}

    if total == 0 or high_severity:
        scores["soldier_on"] += 5
        scores["no_self_pity"] += 4
        scores["turn_setback_into_feedback"] += 3

    if total == 0:
        scores["soldier_on"] += 4
        scores["no_self_pity"] += 4

    if broken_loop:
        scores["soldier_on"] += 3
        scores["turn_setback_into_feedback"] += 4

    if any_anomaly:
        scores["turn_setback_into_feedback"] += 3
        if anomaly_keys & {"zero_output", "mit_drop", "xp_drop", "work_drop", "tomato_break"}:
            scores["no_self_pity"] += 2

    if period in {"three-days", "weekly", "monthly"}:
        scores["watch_for_real_opportunity"] += 3

    if productive and not any_anomaly:
        scores["watch_for_real_opportunity"] += 4

    if action_status == "done":
        scores["watch_for_real_opportunity"] += 3

    if period in {"weekly", "monthly"} or (productive and not broken_loop):
        scores["no_envy"] += 1

    if not any(scores.values()):
        scores["watch_for_real_opportunity"] += 2
        scores["no_envy"] += 1

    for key, bias in mode.principle_biases.items():
        if key in scores:
            scores[key] += bias

    ranked = sorted(
        _PRINCIPLE_ORDER,
        key=lambda item: (-scores[item.key], rank_index[item.key]),
    )
    selected = [item for item in ranked if scores[item.key] > 0][:2]
    if len(selected) < 2:
        for fallback in _PRINCIPLE_ORDER:
            if fallback not in selected:
                selected.append(fallback)
            if len(selected) >= 2:
                break
    return selected
