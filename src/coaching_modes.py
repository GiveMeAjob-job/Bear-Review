from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Dict, List


@dataclass(frozen=True)
class CoachingMode:
    key: str
    name: str
    summary: str
    prompt_guidance: str
    decision_rule: str
    principle_biases: Dict[str, int] = field(default_factory=dict)
    notify_bias: int = 0


_DEFAULT_MODE_KEY = "adaptive"

_MODES = {
    "adaptive": CoachingMode(
        key="adaptive",
        name="自适应模式",
        summary="先尊重真实任务证据，再决定是降压、修节奏还是加码推进。",
        prompt_guidance="不要预设用户该被鼓励还是被施压，先看这轮数据真正说明了什么。",
        decision_rule="如果阶段信息模糊，就少做叙事，多做基于证据的收敛判断。",
    ),
    "recovery": CoachingMode(
        key="recovery",
        name="恢复期模式",
        summary="先恢复基线和连续性，不用进攻性目标继续消耗自己。",
        prompt_guidance="建议优先保住睡眠、节奏和低阻力推进，不要一上来追求激进突破。",
        decision_rule="动作必须小、稳、可完成，避免把短期波动解释成失败。",
        principle_biases={"soldier_on": 2, "no_self_pity": 2},
        notify_bias=-1,
    ),
    "stabilize": CoachingMode(
        key="stabilize",
        name="稳态修复模式",
        summary="先把作息、MIT 和番茄这些基本盘拉回稳定，再谈扩张。",
        prompt_guidance="建议要同时给出一个推进动作和一个防偏航边界，优先减少波动。",
        decision_rule="重点修复重复掉线点，不要为了看起来努力而额外加任务。",
        principle_biases={"soldier_on": 1, "turn_setback_into_feedback": 2},
    ),
    "build": CoachingMode(
        key="build",
        name="建设期模式",
        summary="围绕长期资产、系统和可复用成果做复利，不为短期热闹分心。",
        prompt_guidance="优先押注能沉淀成系统、内容、流程或长期能力的工作。",
        decision_rule="建议必须朝证据最强的主线集中资源，弱信号方向自动降级。",
        principle_biases={"watch_for_real_opportunity": 2, "no_envy": 1},
    ),
    "sprint": CoachingMode(
        key="sprint",
        name="冲刺期模式",
        summary="在明确窗口期里收窄范围、提高反馈密度，对分心更不客气。",
        prompt_guidance="建议应更直接，优先保主线、砍次要项，并明确掉线成本。",
        decision_rule="只保留一个主目标和少量配套动作，异常出现时要更快暴露和纠偏。",
        principle_biases={"watch_for_real_opportunity": 2, "turn_setback_into_feedback": 2, "soldier_on": 1},
        notify_bias=1,
    ),
}


def available_mode_keys() -> List[str]:
    return list(_MODES)


def resolve_mode(key: str) -> CoachingMode:
    normalized = (key or "").strip().lower()
    return _MODES.get(normalized, _MODES[_DEFAULT_MODE_KEY])


def mode_payload(mode: CoachingMode) -> Dict[str, object]:
    return asdict(mode)


def build_mode_context(mode: CoachingMode, current_stage: str = "", notes: str = "") -> str:
    lines = []
    if current_stage:
        lines.append(f"当前阶段：{current_stage}")
    lines.append(f"当前模式：{mode.name}")
    lines.append(f"模式说明：{mode.summary}")
    lines.append("模式策略：")
    lines.append(f"- {mode.prompt_guidance}")
    lines.append(f"- {mode.decision_rule}")
    if notes:
        lines.append(f"模式备注：{notes}")
    return "\n".join(lines)
