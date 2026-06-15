"""共享测试fixtures"""

import json
import tempfile
from pathlib import Path

import pytest
import yaml

from classroom_analyzer.models import (
    AppConfig,
    AudioInfo,
    EventTimeline,
    KeyFrame,
    QualityCheckItem,
    QualityReport,
    ScoreCard,
    ScoreDimension,
    ScoringDimensionConfig,
    TeachingEvent,
    Transcript,
    TranscriptSegment,
    VideoInfo,
)


@pytest.fixture
def sample_video_info() -> VideoInfo:
    """示例视频信息。"""
    return VideoInfo(
        file_path="/path/to/video.mp4",
        file_size=823000000,
        duration=3120.0,  # 52分钟
        format="mov,mp4,m4a,3gp,3g2,mj2",
        resolution=(1920, 1080),
    )


@pytest.fixture
def sample_audio_info() -> AudioInfo:
    """示例音频信息。"""
    return AudioInfo(
        file_path="/path/to/audio.wav",
        duration=3120.0,
        sample_rate=16000,
        channels=1,
        format="wav",
    )


@pytest.fixture
def sample_transcript_segments() -> list[TranscriptSegment]:
    """示例转录片段。"""
    return [
        TranscriptSegment(
            start_time=0.0,
            end_time=15.0,
            text="同学们好，今天我们来学习第三章的内容。",
            speaker="teacher",
        ),
        TranscriptSegment(
            start_time=15.0,
            end_time=20.0,
            text="老师好！",
            speaker="student_1",
        ),
        TranscriptSegment(
            start_time=20.0,
            end_time=120.0,
            text="首先，我们来看一下这个概念的定义。在数学中，函数是一种特殊的对应关系……",
            speaker="teacher",
        ),
        TranscriptSegment(
            start_time=120.0,
            end_time=135.0,
            text="请问谁能举个例子？",
            speaker="teacher",
        ),
        TranscriptSegment(
            start_time=135.0,
            end_time=150.0,
            text="我来试试，y=2x就是一个函数。",
            speaker="student_2",
        ),
        TranscriptSegment(
            start_time=150.0,
            end_time=180.0,
            text="非常好！y=2x确实是一个一次函数，大家注意它的形式……",
            speaker="teacher",
        ),
    ]


@pytest.fixture
def sample_transcript(sample_transcript_segments: list[TranscriptSegment]) -> Transcript:
    """示例转录文本。"""
    return Transcript(
        segments=sample_transcript_segments,
        duration=180.0,
        speaker_count=3,
    )


@pytest.fixture
def sample_teaching_events() -> list[TeachingEvent]:
    """示例教学事件。"""
    return [
        TeachingEvent(
            event_type="环节切换",
            subtype="开场",
            start_time=0.0,
            end_time=15.0,
            description="教师开始上课，进行开场白",
            confidence=0.95,
            related_text="同学们好，今天我们来学习第三章的内容。",
        ),
        TeachingEvent(
            event_type="互动指令",
            subtype="提问",
            start_time=120.0,
            end_time=135.0,
            description="教师向学生提问，要求举例",
            confidence=0.9,
            related_text="请问谁能举个例子？",
        ),
        TeachingEvent(
            event_type="学生应答",
            subtype="个人回答",
            start_time=135.0,
            end_time=150.0,
            description="学生举例y=2x",
            confidence=0.85,
            related_text="我来试试，y=2x就是一个函数。",
        ),
        TeachingEvent(
            event_type="教师反馈",
            subtype="肯定",
            start_time=150.0,
            end_time=180.0,
            description="教师肯定学生回答并进一步讲解",
            confidence=0.9,
            related_text="非常好！y=2x确实是一个一次函数",
        ),
    ]


@pytest.fixture
def sample_event_timeline(sample_teaching_events: list[TeachingEvent]) -> EventTimeline:
    """示例事件时间轴。"""
    return EventTimeline(events=sample_teaching_events)


@pytest.fixture
def sample_score_dimensions() -> list[ScoreDimension]:
    """示例评分维度结果。"""
    return [
        ScoreDimension(
            name="教学环节完整度",
            score=22.0,
            max_score=25.0,
            weight=0.25,
            evidence="有开场和讲授，缺少总结环节",
        ),
        ScoreDimension(
            name="互动质量",
            score=18.0,
            max_score=25.0,
            weight=0.25,
            evidence="有提问和学生回答，但互动频次较低",
        ),
        ScoreDimension(
            name="知识讲解清晰度",
            score=17.0,
            max_score=20.0,
            weight=0.20,
            evidence="概念引入明确，有典型例题",
        ),
        ScoreDimension(
            name="教学节奏",
            score=12.0,
            max_score=15.0,
            weight=0.15,
            evidence="节奏适中，无明显停顿",
        ),
        ScoreDimension(
            name="规范符合度",
            score=11.0,
            max_score=15.0,
            weight=0.15,
            evidence="基本符合规范，缺少知识总结",
        ),
    ]


@pytest.fixture
def sample_score_card(sample_score_dimensions: list[ScoreDimension]) -> ScoreCard:
    """示例评分卡。"""
    return ScoreCard(
        dimensions=sample_score_dimensions,
        total_score=80.0,
        total_max=100.0,
    )


@pytest.fixture
def sample_quality_report(
    sample_video_info: VideoInfo,
    sample_score_card: ScoreCard,
) -> QualityReport:
    """示例质检报告。"""
    check_items = [
        QualityCheckItem(
            description="有无开场白和课堂纪律提醒",
            passed=True,
            evidence="教师进行了开场白",
            timestamp=0.0,
        ),
        QualityCheckItem(
            description="是否按时上下课",
            passed=False,
            evidence="课程52分钟，预期45分钟",
            timestamp=None,
        ),
        QualityCheckItem(
            description="互动环节是否有学生参与",
            passed=True,
            evidence="互动事件2次",
            timestamp=120.0,
        ),
    ]
    return QualityReport(
        video_info=sample_video_info,
        transcript_summary="说话人3人",
        check_items=check_items,
        event_summary={"total": 4, "环节切换": 1, "互动指令": 1, "学生应答": 1, "教师反馈": 1},
        score_card=sample_score_card,
    )


@pytest.fixture
def sample_app_config() -> AppConfig:
    """示例应用配置。"""
    return AppConfig(
        scoring_dimensions=[
            ScoringDimensionConfig(name="教学环节完整度", weight=0.25, criteria="开场→引入→讲授→练习→互动→总结，缺环节扣分"),
            ScoringDimensionConfig(name="互动质量", weight=0.25, criteria="提问频次、学生参与度、反馈质量"),
            ScoringDimensionConfig(name="知识讲解清晰度", weight=0.20, criteria="概念引入明确、例题典型、方法总结到位"),
            ScoringDimensionConfig(name="教学节奏", weight=0.15, criteria="节奏合理，无冗长停顿或赶进度"),
            ScoringDimensionConfig(name="规范符合度", weight=0.15, criteria="按教研规范执行"),
        ],
        quality_checklist=[
            "有无开场白和课堂纪律提醒",
            "是否按时上下课",
            "互动环节是否有学生参与",
            "是否有知识总结",
            "有无不当言论",
        ],
        event_types=["环节切换", "互动指令", "学生应答", "教师反馈", "知识节点", "节奏信号"],
        api_keys={
            "tencent_cloud": {
                "secret_id": "test_secret_id",
                "secret_key": "test_secret_key",
            },
            "cos": {
                "bucket": "test-bucket-1234567890",
                "region": "ap-guangzhou",
                "path_prefix": "asr-upload/",
            },
            "llm": {
                "base_url": "https://api.deepseek.com/v1",
                "api_key": "test_llm_api_key",
                "model": "deepseek-chat",
            },
        },
        asr_config={
            "engine": "16k_zh",
            "language": "zh",
            "enable_diarization": True,
            "speaker_number": 0,
        },
        analysis_config={
            "chunk_size": 2000,
            "chunk_overlap": 200,
            "smart_sampling": True,
        },
        cos_config={
            "bucket": "test-bucket-1234567890",
            "region": "ap-guangzhou",
            "path_prefix": "asr-upload/",
        },
    )


@pytest.fixture
def tmp_config_dir(tmp_path: Path) -> Path:
    """临时配置目录，包含有效的YAML和JSON配置文件。"""
    # YAML配置
    yaml_config = {
        "scoring": {
            "dimensions": [
                {"name": "教学环节完整度", "weight": 0.25, "criteria": "缺环节扣分"},
                {"name": "互动质量", "weight": 0.25, "criteria": "提问频次"},
                {"name": "知识讲解清晰度", "weight": 0.20, "criteria": "概念明确"},
                {"name": "教学节奏", "weight": 0.15, "criteria": "节奏合理"},
                {"name": "规范符合度", "weight": 0.15, "criteria": "按规范执行"},
            ]
        },
        "quality_checklist": [
            "有无开场白",
            "是否按时",
            "互动参与",
        ],
        "event_types": [
            "环节切换",
            "互动指令",
        ],
    }
    yaml_path = tmp_path / "config.yaml"
    yaml_path.write_text(yaml.dump(yaml_config, allow_unicode=True), encoding="utf-8")

    # JSON配置
    json_config = {
        "tencent_cloud": {
            "secret_id": "test_secret_id",
            "secret_key": "test_secret_key",
        },
        "cos": {
            "bucket": "test-bucket-1234567890",
            "region": "ap-guangzhou",
            "path_prefix": "asr-upload/",
        },
        "asr": {
            "engine": "16k_zh",
            "language": "zh",
            "enable_diarization": True,
            "speaker_number": 0,
        },
        "llm": {
            "base_url": "https://api.deepseek.com/v1",
            "api_key": "test_llm_api_key",
            "model": "deepseek-chat",
        },
        "analysis": {
            "chunk_size": 2000,
            "chunk_overlap": 200,
            "smart_sampling": True,
        },
    }
    json_path = tmp_path / "api_keys.json"
    json_path.write_text(json.dumps(json_config, ensure_ascii=False, indent=2), encoding="utf-8")

    return tmp_path
