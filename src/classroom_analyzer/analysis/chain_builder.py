"""教学互动链重构 — 将扁平事件列表转换为因果关联的互动链。

当前事件检测产出的是孤立的事件列表，每个事件只有类型、时间、描述。
评分时 LLM 看到的是离散片段，无法理解"教师提问→学生回答→教师追问"
之间的因果关系。

本模块将扁平事件重构为互动链（interaction chain），每条链展示完整的
"发起→回应→反馈→追问→再回应"对话过程，帮助 LLM 做上下文关联判断。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from classroom_analyzer.models import EventTimeline, TeachingEvent, _format_time


# ── 事件类型分类 ──
INTERACTION_EVENTS = {"互动指令", "学生应答", "教师反馈"}
CHAIN_BOUNDARY_EVENTS = {"环节切换"}
STANDALONE_EVENTS = {"知识节点", "节奏信号"}


@dataclass
class InteractionLink:
    """互动链中的单个链接（一次发起→回应→反馈的原子交互）。"""
    initiation: Optional[TeachingEvent] = None    # 教师发起（互动指令）
    response: Optional[TeachingEvent] = None       # 学生应答
    feedback: Optional[TeachingEvent] = None       # 教师反馈

    @property
    def time_range(self) -> str:
        """链节的时间范围显示。"""
        events = [e for e in (self.initiation, self.response, self.feedback) if e]
        if not events:
            return ""
        start = min(e.start_time for e in events)
        end = max(e.end_time for e in events)
        return f"{_format_time(start)}-{_format_time(end)}"

    def to_text(self, indent: str = "  ") -> str:
        """格式化为可读文本。"""
        lines = []
        if self.initiation:
            lines.append(f"{indent}📍 [{_format_time(self.initiation.start_time)}] 教师发起 → \"{self.initiation.description}\"")
        if self.response:
            lines.append(f"{indent}📍 [{_format_time(self.response.start_time)}] 学生应答 → \"{self.response.description}\"")
        if self.feedback:
            lines.append(f"{indent}📍 [{_format_time(self.feedback.start_time)}] 教师反馈 → \"{self.feedback.description}\"")
        return "\n".join(lines)


@dataclass
class InteractionChain:
    """教学互动链：一段连续的师生互动序列。"""
    chain_id: int
    links: list[InteractionLink] = field(default_factory=list)
    annotations: list[TeachingEvent] = field(default_factory=list)  # 穿插的知识节点/节奏信号

    @property
    def time_range(self) -> str:
        """整条链的时间范围。"""
        all_events = []
        for link in self.links:
            for e in (link.initiation, link.response, link.feedback):
                if e:
                    all_events.append(e)
        if not all_events:
            return ""
        start = min(e.start_time for e in all_events)
        end = max(e.end_time for e in all_events)
        return f"{_format_time(start)}-{_format_time(end)}"

    def to_text(self) -> str:
        """格式化为 Prompt 可用的互动链文本。"""
        lines = []
        lines.append(f"### 互动链 #{self.chain_id} [{self.time_range}]")
        lines.append("")

        for i, link in enumerate(self.links, 1):
            lines.append(f"**回合 {i}**：")
            lines.append(link.to_text("  "))
            lines.append("")

        if self.annotations:
            lines.append("📝 穿插的教学事件：")
            for ann in self.annotations:
                lines.append(f"  - [{_format_time(ann.start_time)}] {ann.event_type}: {ann.description}")
            lines.append("")

        lines.append("---")
        return "\n".join(lines)


def build_interaction_chains(events: EventTimeline) -> list[InteractionChain]:
    """从扁平事件列表中重建互动链。

    算法：
    1. 遍历所有事件，区分交互事件和非交互事件
    2. 遇到环节切换 → 结束当前链，开始新链
    3. 连续的互动指令/学生应答/教师反馈 → 构建链内回合
    4. 知识节点/节奏信号 → 作为链的注释（不影响链的连续性）
    5. 超过 60 秒无交互事件 → 自动结束当前链

    Args:
        events: 事件时间轴

    Returns:
        重建后的互动链列表
    """
    if not events.events:
        return []

    chains: list[InteractionChain] = []
    chain_id = 0

    current_chain: Optional[InteractionChain] = None
    current_link: Optional[InteractionLink] = None
    # 追踪当前状态：上一次看到的是什么类型的交互事件
    last_interaction_time: float = 0.0

    INTERACTION_GAP_SECONDS = 60.0  # 超过此间隔自动断链

    for event in events.events:
        # ── 环节切换：强制结束当前链 ──
        if event.event_type in CHAIN_BOUNDARY_EVENTS:
            _flush_chain(current_chain, current_link, chains)
            current_chain = None
            current_link = None
            last_interaction_time = 0.0
            continue

        # ── 交互事件类型 ──
        if event.event_type in INTERACTION_EVENTS:
            time_gap = event.start_time - last_interaction_time if last_interaction_time > 0 else 0

            # 长时间无交互：自动断链
            if time_gap > INTERACTION_GAP_SECONDS and current_chain is not None:
                _flush_chain(current_chain, current_link, chains)
                current_chain = None
                current_link = None

            # 需要开始新链
            if current_chain is None:
                chain_id += 1
                current_chain = InteractionChain(chain_id=chain_id)
                current_link = None

            last_interaction_time = event.start_time

            if event.event_type == "互动指令":
                # 教师发起新的互动回合：如果当前有未完成的 link，先保存
                if current_link is not None:
                    current_chain.links.append(current_link)
                current_link = InteractionLink(initiation=event)

            elif event.event_type == "学生应答":
                if current_link is None:
                    # 孤立的应答（没有前置发起）→ 创建新 link
                    current_link = InteractionLink(response=event)
                elif current_link.response is None:
                    current_link.response = event
                else:
                    # 已有应答 → 这是二次应答，保存当前 link 开新
                    current_chain.links.append(current_link)
                    current_link = InteractionLink(response=event)

            elif event.event_type == "教师反馈":
                if current_link is None:
                    # 孤立的反馈 → 创建新 link
                    current_link = InteractionLink(feedback=event)
                elif current_link.feedback is None:
                    current_link.feedback = event
                    # 反馈完成后，这个回合完成
                    current_chain.links.append(current_link)
                    current_link = None
                else:
                    # 已有反馈 → 保存当前，这是新的反馈（可能是对上一个回应的二次反馈）
                    current_chain.links.append(current_link)
                    current_link = InteractionLink(feedback=event)

        # ── 非交互事件（知识节点/节奏信号）→ 作为链注释 ──
        elif event.event_type in STANDALONE_EVENTS:
            if current_chain is not None:
                current_chain.annotations.append(event)
            else:
                # 没有活跃链，创建一条仅含注释的链
                chain_id += 1
                current_chain = InteractionChain(chain_id=chain_id, annotations=[event])
                _flush_chain(current_chain, current_link, chains)
                current_chain = None
                current_link = None

    # 处理最后未完成的链
    _flush_chain(current_chain, current_link, chains)

    return chains


def _flush_chain(
    chain: Optional[InteractionChain],
    current_link: Optional[InteractionLink],
    chains: list[InteractionChain],
) -> None:
    """将当前链和未完成的链接刷新到链列表。"""
    if current_link is not None and chain is not None:
        # 链接中至少有一个事件才算有效
        if any([current_link.initiation, current_link.response, current_link.feedback]):
            chain.links.append(current_link)

    if chain is not None and (chain.links or chain.annotations):
        chains.append(chain)


def format_chains_for_prompt(chains: list[InteractionChain]) -> str:
    """将互动链列表格式化为 Prompt 文本。

    Args:
        chains: 互动链列表

    Returns:
        格式化的 Markdown 文本
    """
    if not chains:
        return "（未检测到明显的教学互动链）"

    parts = []
    parts.append(f"共重建 {len(chains)} 条教学互动链：\n")
    for chain in chains:
        parts.append(chain.to_text())

    return "\n".join(parts)
