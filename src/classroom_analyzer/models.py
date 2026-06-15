"""核心数据模型 — 所有dataclass定义"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from typing import Optional


def _format_time(seconds: float) -> str:
    """将秒数格式化为 HH:MM:SS 或 MM:SS。"""
    hours = int(seconds) // 3600
    minutes = (int(seconds) % 3600) // 60
    secs = int(seconds) % 60
    if hours > 0:
        return f"{hours:01d}:{minutes:02d}:{secs:02d}"
    return f"{minutes:02d}:{secs:02d}"


@dataclass
class VideoInfo:
    """视频文件信息。"""
    file_path: str
    file_size: int  # 字节
    duration: float  # 秒
    format: str
    resolution: tuple[int, int]  # (width, height)


@dataclass
class AudioInfo:
    """音频文件信息。"""
    file_path: str
    duration: float  # 秒
    sample_rate: int  # 采样率
    channels: int  # 声道数
    format: str


@dataclass
class TranscriptSegment:
    """转录文本片段。"""
    start_time: float  # 秒
    end_time: float  # 秒
    text: str
    speaker: str


@dataclass
class Transcript:
    """完整转录文本。"""
    segments: list[TranscriptSegment] = field(default_factory=list)
    duration: float = 0.0
    speaker_count: int = 0

    def to_text(self) -> str:
        """将转录文本格式化为可读文本。"""
        lines: list[str] = []
        for seg in self.segments:
            time_range = f"[{_format_time(seg.start_time)}-{_format_time(seg.end_time)}]"
            lines.append(f"{time_range} {seg.speaker}: {seg.text}")
        return "\n".join(lines)

    def get_segments_by_speaker(self, speaker: str) -> list[TranscriptSegment]:
        """按说话人筛选片段。"""
        return [seg for seg in self.segments if seg.speaker == speaker]

    def get_segments_in_range(self, start: float, end: float) -> list[TranscriptSegment]:
        """按时间范围筛选片段。"""
        return [
            seg for seg in self.segments
            if seg.start_time >= start and seg.end_time <= end
        ]


@dataclass
class TeachingEvent:
    """教学事件。"""
    event_type: str  # 环节切换/互动指令/学生应答/教师反馈/知识节点/节奏信号
    subtype: str
    start_time: float  # 秒
    end_time: float  # 秒
    description: str
    confidence: float  # 0.0-1.0
    related_text: str = ""


@dataclass
class EventTimeline:
    """教学事件时间轴。"""
    events: list[TeachingEvent] = field(default_factory=list)

    def get_events_by_type(self, event_type: str) -> list[TeachingEvent]:
        """按事件类型筛选。"""
        return [e for e in self.events if e.event_type == event_type]

    def get_events_in_range(self, start: float, end: float) -> list[TeachingEvent]:
        """按时间范围筛选事件（与范围有重叠即包含）。"""
        return [
            e for e in self.events
            if e.start_time < end and e.end_time > start
        ]

    def to_json(self) -> str:
        """序列化为JSON字符串。"""
        data = []
        for e in self.events:
            data.append({
                "event_type": e.event_type,
                "subtype": e.subtype,
                "start_time": e.start_time,
                "end_time": e.end_time,
                "start_time_display": _format_time(e.start_time),
                "end_time_display": _format_time(e.end_time),
                "description": e.description,
                "confidence": e.confidence,
                "related_text": e.related_text,
            })
        return json.dumps(data, ensure_ascii=False, indent=2)


@dataclass
class KeyFrame:
    """关键帧。"""
    file_path: str
    timestamp: float  # 秒
    trigger_event: Optional[TeachingEvent] = None


@dataclass
class QualityCheckItem:
    """质检清单项。"""
    description: str
    passed: bool
    evidence: str
    timestamp: Optional[float] = None  # 秒，可为None
    is_red_line: bool = False  # 是否红线项（一票否决）


@dataclass
class ScoringPoint:
    """单个得分/扣分证据点，用于人工逐分核验。

    Attributes:
        point_type: "+" 加分 / "-" 扣分
        reason: 行为描述
        quote: 原文引用
        at: 时间点（秒）
        duration: 持续时间（秒），可选
    """
    point_type: str  # "+" 加分 / "-" 扣分
    reason: str  # 行为描述
    quote: str = ""  # 原文引用
    at: Optional[float] = None  # 时间点（秒）
    duration: Optional[float] = None  # 持续时间（秒），可选


@dataclass
class ScoreDimension:
    """评分维度结果。"""
    name: str
    score: float
    max_score: float
    weight: float
    evidence: str
    details: str = ""
    grade: str = ""  # 等级：优/良/中/差
    timestamp: Optional[float] = None  # 证据对应时间点
    scoring_points: list[ScoringPoint] = field(default_factory=list)
    score_std: Optional[float] = None  # 多轮评估标准差（单轮时为 None）
    round_scores: list[float] = field(default_factory=list)  # 各轮原始分（多轮时记录）
    source_model: str = "text"  # 评分来源："text"（文本模型）或 "vision"（视觉模型）


@dataclass
class ScoreCard:
    """评分卡。"""
    dimensions: list[ScoreDimension] = field(default_factory=list)
    total_score: float = 0.0
    total_max: float = 100.0
    grade: str = ""  # 总等级：博学/挑战/创新
    red_line_violation: bool = False  # 红线违规（一票否决）
    level: str = ""  # 班型：L1_L3/L4_L6/L7_L9
    num_rounds: int = 1  # 评估轮数（1 为单轮）

    def compute_grade(self, level: str = "L4_L6") -> str:
        """根据总分和班型计算等级。
        
        常规班型等级区间（百分制）：
        - [90, 100] 创新 / [70, 90) 挑战 / [50, 70) 博学 / [0, 50) 不达标
        
        QC-v4 新版质检等级区间（百分制，合格线75分）：
        - [85, 100] 优 / [75, 85) 良 / [50, 75) 待改进 / [0, 50) 不合格
        
        红线违规时直接判定为"不达标（红线违规）"。
        """
        if self.total_max <= 0:
            self.grade = "博学"
            return self.grade
        
        pct = (self.total_score / self.total_max) * 100
        if self.red_line_violation:
            self.grade = "不达标（红线违规）"
        elif level == "QC-v4":
            # QC-v4 新版质检等级（合格线75分）
            if pct >= 85:
                self.grade = "优"
            elif pct >= 75:
                self.grade = "良"
            elif pct >= 50:
                self.grade = "待改进"
            else:
                self.grade = "不合格"
        elif pct >= 90:
            self.grade = "创新"
        elif pct >= 70:
            self.grade = "挑战"
        elif pct >= 50:
            self.grade = "博学"
        else:
            self.grade = "不达标"
        
        self.level = level
        return self.grade

    def to_json(self) -> str:
        """序列化为JSON字符串。"""
        data = {
            "dimensions": [
                {
                    "name": d.name,
                    "score": d.score,
                    "max_score": d.max_score,
                    "weight": d.weight,
                    "evidence": d.evidence,
                    "details": d.details,
                    "grade": d.grade,
                    "timestamp": d.timestamp,
                    "score_std": d.score_std,
                    "round_scores": d.round_scores,
                    "source_model": d.source_model,
                    "scoring_points": [
                        {
                            "type": sp.point_type,
                            "reason": sp.reason,
                            "quote": sp.quote,
                            "at": sp.at,
                            "duration": sp.duration,
                        }
                        for sp in d.scoring_points
                    ],
                }
                for d in self.dimensions
            ],
            "total_score": self.total_score,
            "total_max": self.total_max,
            "grade": self.grade,
            "red_line_violation": self.red_line_violation,
            "level": self.level,
            "num_rounds": self.num_rounds,
        }
        return json.dumps(data, ensure_ascii=False, indent=2)


@dataclass
class QualityReport:
    """质检报告。"""
    video_info: VideoInfo
    transcript_summary: str
    check_items: list[QualityCheckItem] = field(default_factory=list)
    event_summary: dict = field(default_factory=dict)
    score_card: ScoreCard = field(default_factory=ScoreCard)
    level: str = ""  # 班型

    def to_markdown(self) -> str:
        """生成Markdown格式报告。"""
        lines: list[str] = []
        lines.append(f"# 课堂质检报告 — {self.video_info.file_path}")

        # 基本信息
        lines.append("")
        lines.append("## 基本信息")
        lines.append(f"- 课程时长：{_format_time(self.video_info.duration)}")
        if self.level:
            level_names = {"L1_L3": "学前（L1-L3）", "L4_L6": "小低（L4-L6）", "L7_L9": "小高（L7-L9）"}
            lines.append(f"- 评分标准：{level_names.get(self.level, self.level)}")

        # 转录摘要
        if self.transcript_summary:
            lines.append(f"- {self.transcript_summary}")

        # 事件统计
        if self.event_summary:
            total_events = self.event_summary.get("total", 0)
            lines.append(f"- 识别教学事件：{total_events}个")

        # 红线检测
        red_line_items = [item for item in self.check_items if item.is_red_line]
        if red_line_items:
            lines.append("")
            lines.append("## 🚫 红线检测（一票否决）")
            for item in red_line_items:
                status = "❌ 触发" if not item.passed else "✅ 未触发"
                ts = f" [{_format_time(item.timestamp)}]" if item.timestamp is not None else ""
                lines.append(f"- {status} {item.description}{ts}")
                if item.evidence:
                    lines.append(f"  > {item.evidence}")

        # 质检结果
        lines.append("")
        lines.append("## 质检结果")

        passed_items = [item for item in self.check_items if item.passed and not item.is_red_line]
        failed_items = [item for item in self.check_items if not item.passed and not item.is_red_line]

        if passed_items:
            lines.append("")
            lines.append("### ✅ 通过项")
            for item in passed_items:
                ts = f"（{_format_time(item.timestamp)}）" if item.timestamp is not None else ""
                lines.append(f"- [x] {item.description}{ts}")
                if item.evidence:
                    lines.append(f"  > {item.evidence}")

        if failed_items:
            lines.append("")
            lines.append("### ❌ 未通过项")
            for item in failed_items:
                ts = f"（{_format_time(item.timestamp)}）" if item.timestamp is not None else ""
                lines.append(f"- [ ] {item.description}{ts}")
                if item.evidence:
                    lines.append(f"  > {item.evidence}")

        # 评分卡
        if self.score_card and self.score_card.dimensions:
            lines.append("")
            lines.append("## 评分卡")
            lines.append("")
            if self.score_card.num_rounds > 1:
                lines.append(f"> ⚡ 基于 **{self.score_card.num_rounds}** 轮独立评估取均值，标准差反映评分稳定性")
                lines.append("")
            # 表头根据是否多轮调整
            if self.score_card.num_rounds > 1:
                lines.append("| 维度 | 均值 | 满分 | ±σ | 等级 |")
                lines.append("|------|------|------|-----|------|")
                for d in self.score_card.dimensions:
                    grade_str = d.grade if d.grade else ""
                    std_str = f"±{d.score_std:.2f}" if d.score_std is not None else "-"
                    lines.append(f"| {d.name} | {d.score:.1f} | {d.max_score:.1f} | {std_str} | {grade_str} |")
            else:
                lines.append("| 维度 | 得分 | 满分 | 等级 |")
                lines.append("|------|------|------|------|")
                for d in self.score_card.dimensions:
                    grade_str = d.grade if d.grade else ""
                    lines.append(f"| {d.name} | {d.score:.1f} | {d.max_score:.1f} | {grade_str} |")
            lines.append(f"| **总分** | **{self.score_card.total_score:.1f}** | **{self.score_card.total_max:.1f}** | **{self.score_card.grade}** |")

            # 逐分核验表（人工复核用）
            if any(d.scoring_points for d in self.score_card.dimensions):
                lines.append("")
                lines.append("## 📊 逐分核验（人工复核用）")
                for d in self.score_card.dimensions:
                    if not d.scoring_points:
                        continue
                    lines.append("")
                    lines.append(f"### {d.name}")
                    lines.append("| 类型 | 行为描述 | 原文引用 | 时间点 |")
                    lines.append("|------|---------|---------|--------|")
                    for sp in d.scoring_points:
                        type_icon = "➕加分" if sp.point_type == "+" else "➖扣分"
                        quote_str = f'"{sp.quote}"' if sp.quote else "-"
                        time_str = _format_time(sp.at) if sp.at is not None else "-"
                        lines.append(f"| {type_icon} | {sp.reason} | {quote_str} | {time_str} |")

            # 多轮一致性摘要
            if self.score_card.num_rounds > 1 and any(d.round_scores for d in self.score_card.dimensions):
                lines.append("")
                lines.append("## 📈 多轮评估一致性")
                lines.append("")
                lines.append("| 维度 | " + " | ".join(f"第{r+1}轮" for r in range(self.score_card.num_rounds)) + " | 均值±σ |")
                lines.append("|------|" + "|".join("------" for _ in range(self.score_card.num_rounds)) + "|---------|")
                for d in self.score_card.dimensions:
                    if not d.round_scores:
                        continue
                    rounds_str = " | ".join(f"{s:.1f}" for s in d.round_scores)
                    std_str = f"±{d.score_std:.2f}" if d.score_std is not None else "-"
                    lines.append(f"| {d.name} | {rounds_str} | {d.score:.1f}{std_str} |")

            # 时间戳核验表
            lines.append("")
            lines.append("## 📍 时间戳核验（快速定位证据）")
            lines.append("")
            lines.append("| 维度 | 时间点 | 证据摘要 |")
            lines.append("|------|--------|---------|")
            for d in self.score_card.dimensions:
                ts = _format_time(d.timestamp) if d.timestamp is not None else "-"
                evidence_short = d.evidence[:50] + "..." if len(d.evidence) > 50 else d.evidence
                lines.append(f"| {d.name} | {ts} | {evidence_short} |")
            for item in self.check_items:
                ts = _format_time(item.timestamp) if item.timestamp is not None else "-"
                status = "✅" if item.passed else "❌"
                evidence_short = item.evidence[:50] + "..." if len(item.evidence) > 50 else item.evidence
                lines.append(f"| {status}{item.description} | {ts} | {evidence_short} |")

        lines.append("")
        return "\n".join(lines)


@dataclass
class AnalysisResult:
    """完整分析结果。"""
    video_info: VideoInfo
    audio_info: AudioInfo
    transcript: Transcript
    event_timeline: EventTimeline
    keyframes: list[KeyFrame] = field(default_factory=list)
    quality_report: Optional[QualityReport] = None
    score_card: Optional[ScoreCard] = None
    output_dir: str = ""


@dataclass
class ScoringDimensionConfig:
    """评分维度配置。"""
    name: str
    weight: float
    criteria: str
    max_score: float = 100.0  # 维度满分（如10分制为10）


@dataclass
class AppConfig:
    """应用配置。"""
    scoring_dimensions: list[ScoringDimensionConfig] = field(default_factory=list)
    quality_checklist: list[str] = field(default_factory=list)
    event_types: list[str] = field(default_factory=list)
    api_keys: dict = field(default_factory=dict)
    asr_config: dict = field(default_factory=dict)
    analysis_config: dict = field(default_factory=dict)
    cos_config: dict = field(default_factory=dict)
    red_lines: list[dict] = field(default_factory=list)  # 红线淘汰行为列表
