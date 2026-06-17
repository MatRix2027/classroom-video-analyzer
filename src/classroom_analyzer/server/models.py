"""Pydantic 模型定义 — API 请求/响应类型"""

from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel, Field


# ── 请求模型 ──


class TaskCreateRequest(BaseModel):
    """创建分析任务请求（level 通过 form field 传递）."""

    level: str = Field(default="QC-v4", description="班型等级（默认QC-v4统一标准）")


class TaskStartRequest(BaseModel):
    """启动分析请求."""

    level: str = Field(default="QC-v4", description="班型等级（默认QC-v4统一标准）")


# ── 响应模型 ──


class TaskCreated(BaseModel):
    """任务创建成功响应."""

    id: str = Field(..., description="任务 UUID")


class TaskStatusResponse(BaseModel):
    """任务状态轮询响应."""

    id: str
    status: str
    progress: int = Field(ge=0, le=100, description="进度百分比")
    current_stage: str = Field(default="", description="当前阶段描述")
    created_at: Optional[str] = None
    completed_at: Optional[str] = None


class ScoringPointSchema(BaseModel):
    """评分证据点."""

    type: str = Field(..., description="+ 加分 / - 扣分")
    reason: str = Field(..., description="行为描述")
    quote: str = Field(default="", description="原文引用")
    at: Optional[float] = Field(default=None, description="时间点（秒）")
    duration: Optional[float] = Field(default=None, description="持续时间（秒）")


class ScoreDimensionSchema(BaseModel):
    """评分维度结果."""

    name: str
    score: float
    max_score: float
    weight: float
    evidence: str = ""
    details: str = ""
    grade: str = ""
    timestamp: Optional[float] = None
    score_std: Optional[float] = None
    round_scores: list[float] = Field(default_factory=list)
    source_model: str = "text"  # text/vision — 数据来源模型
    scoring_points: list[ScoringPointSchema] = Field(default_factory=list)


class ScoreCardSchema(BaseModel):
    """评分卡."""

    dimensions: list[ScoreDimensionSchema] = Field(default_factory=list)
    total_score: float = 0.0
    total_max: float = 100.0
    grade: str = ""
    red_line_violation: bool = False
    level: str = ""
    num_rounds: int = 1


class EvidenceStatus(BaseModel):
    """分析证据覆盖状态."""

    mode: str = "unknown"
    duration_seconds: float = 0.0
    is_clip: bool = False
    transcript_available: bool = False
    transcript_segments: int = 0
    speaker_count: int = 0
    events_available: bool = False
    event_count: int = 0
    keyframes_available: bool = False
    keyframe_count: int = 0
    visual_scored: bool = False
    visual_fallback_dimensions: list[str] = Field(default_factory=list)
    review_required: bool = True
    summary: str = ""


class TeachingEventSchema(BaseModel):
    """教学事件证据."""

    event_type: str
    subtype: str = ""
    start_time: float
    end_time: float
    start_time_display: str = ""
    end_time_display: str = ""
    description: str = ""
    confidence: float = 0.0
    related_text: str = ""


class KeyframeSchema(BaseModel):
    """关键帧证据."""

    id: str
    url: str
    filename: str
    timestamp: float
    timestamp_display: str
    event_type: str = ""
    subtype: str = ""
    description: str = ""
    confidence: float = 0.0
    related_text: str = ""


class EvidenceResponse(BaseModel):
    """任务证据包."""

    task_id: str
    status: EvidenceStatus
    events: list[TeachingEventSchema] = Field(default_factory=list)
    keyframes: list[KeyframeSchema] = Field(default_factory=list)


class CalibrationFeedbackCreate(BaseModel):
    """人工校对反馈提交。"""

    feedback_type: str = Field(default="dimension_score", description="反馈类型")
    dimension_name: Optional[str] = Field(default=None, description="关联评分维度")
    ai_score: Optional[float] = Field(default=None, description="工具原评分")
    human_score: Optional[float] = Field(default=None, description="人工建议评分")
    human_grade: Optional[str] = Field(default=None, description="人工建议等级")
    time_range: Optional[str] = Field(default=None, description="相关时间点或时间段")
    issue_summary: str = Field(..., min_length=1, description="差异说明")
    correction_suggestion: Optional[str] = Field(default=None, description="建议调整")
    evidence_note: Optional[str] = Field(default=None, description="证据说明")
    reviewer: Optional[str] = Field(default=None, description="校对人")


class CalibrationFeedbackResponse(BaseModel):
    """人工校对反馈记录。"""

    id: str
    task_id: str
    feedback_type: str
    dimension_name: Optional[str] = None
    ai_score: Optional[float] = None
    human_score: Optional[float] = None
    human_grade: Optional[str] = None
    time_range: Optional[str] = None
    issue_summary: str
    correction_suggestion: Optional[str] = None
    evidence_note: Optional[str] = None
    reviewer: Optional[str] = None
    status: str = "new"
    created_at: Optional[str] = None
    updated_at: Optional[str] = None
    filename: Optional[str] = None
    total_score: Optional[float] = None
    grade: Optional[str] = None


class CalibrationFeedbackListResponse(BaseModel):
    """人工校对反馈列表。"""

    items: list[CalibrationFeedbackResponse] = Field(default_factory=list)
    total: int = 0
    page: int = 1
    page_size: int = 20


class TaskDetailResponse(BaseModel):
    """任务详情响应."""

    id: str
    filename: str
    video_path: str
    status: str
    progress: int = 0
    current_stage: str = ""
    total_score: Optional[float] = None
    grade: Optional[str] = None
    scoring_data: Optional[ScoreCardSchema] = None
    evidence_status: Optional[EvidenceStatus] = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: Optional[str] = None
    completed_at: Optional[str] = None


class TaskListItem(BaseModel):
    """历史任务列表项."""

    id: str
    filename: str
    status: str
    total_score: Optional[float] = None
    grade: Optional[str] = None
    created_at: Optional[str] = None


class TaskListResponse(BaseModel):
    """历史任务列表响应."""

    items: list[TaskListItem] = Field(default_factory=list)
    total: int = 0
    page: int = 1
    page_size: int = 10


class HealthResponse(BaseModel):
    """健康检查响应."""

    status: str = "ok"


class StandardDimension(BaseModel):
    """评价标准维度."""

    name: str
    category: str
    weight: float
    max_score: float
    criteria_excellent: str = ""
    criteria_good: str = ""
    criteria_average: str = ""
    criteria_poor: str = ""


class StandardLevel(BaseModel):
    """评价标准班型."""

    description: str
    student_focus: str = ""
    dimensions: list[StandardDimension] = Field(default_factory=list)
    quality_checklist: list[str] = Field(default_factory=list)


class StandardsResponse(BaseModel):
    """评价标准响应."""

    levels: dict[str, StandardLevel] = Field(default_factory=dict)
    red_lines: list[dict[str, Any]] = Field(default_factory=list)
    grade_system: list[dict[str, Any]] = Field(default_factory=list)
