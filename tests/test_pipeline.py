"""Pipeline 集成测试 — Mock各子模块，验证流程编排和断点恢复"""

import json
import pytest
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock

from classroom_analyzer.pipeline import AnalysisPipeline, PipelineError
from classroom_analyzer.models import (
    VideoInfo,
    AudioInfo,
    Transcript,
    TranscriptSegment,
    EventTimeline,
    TeachingEvent,
    ScoreCard,
    QualityReport,
    AnalysisResult,
    AppConfig,
    ScoringDimensionConfig,
    QualityCheckItem,
    ScoreDimension,
)


def make_mock_config() -> AppConfig:
    """构造一个最小化的 AppConfig 用于测试。"""
    return AppConfig(
        scoring_dimensions=[
            ScoringDimensionConfig(name="教学内容", weight=0.25, criteria="", max_score=10.0),
            ScoringDimensionConfig(name="教学方法", weight=0.25, criteria="", max_score=10.0),
            ScoringDimensionConfig(name="教学表现力", weight=0.25, criteria="", max_score=10.0),
            ScoringDimensionConfig(name="教学效果", weight=0.25, criteria="", max_score=10.0),
        ],
        quality_checklist=["检查项1", "检查项2"],
        event_types=["环节切换", "互动指令"],
        api_keys={
            "tencent_cloud": {"secret_id": "test", "secret_key": "test"},
            "llm": {"api_key": "test", "base_url": "https://api.test.com"},
            "cos": {"bucket": "test-bucket", "region": "ap-guangzhou"},
        },
        asr_config={"engine": "16k_zh", "enable_diarization": True},
        analysis_config={"level": "L4_L6", "prompt_version": "spark_standard"},
        cos_config={"bucket": "test-bucket", "region": "ap-guangzhou"},
    )


def make_pipeline(config: AppConfig = None) -> AnalysisPipeline:
    """构造 AnalysisPipeline 实例（不触发真实IO）。"""
    if config is None:
        config = make_mock_config()
    pipe = AnalysisPipeline(config=config, force=False)
    return pipe


def _make_video_info() -> VideoInfo:
    return VideoInfo(
        file_path="test.mp4",
        file_size=1_000_000,
        duration=300.0,
        format="mp4",
        resolution=(1920, 1080),
    )


def _make_audio_info(output_path: str) -> AudioInfo:
    return AudioInfo(
        file_path=output_path,
        duration=300.0,
        sample_rate=16000,
        channels=1,
        format="wav",
    )


def _make_transcript() -> Transcript:
    return Transcript(
        segments=[
            TranscriptSegment(start_time=0.0, end_time=5.0, text="同学们好", speaker="teacher"),
            TranscriptSegment(start_time=5.0, end_time=10.0, text="今天学习新内容", speaker="teacher"),
        ],
        duration=300.0,
        speaker_count=1,
    )


class TestAnalysisPipelineInit:
    """测试 AnalysisPipeline 初始化。"""

    def test_init_with_config(self):
        """传入 AppConfig 应能正常初始化，各子模块已挂载。"""
        config = make_mock_config()
        pipe = AnalysisPipeline(config=config, force=False)
        assert pipe is not None
        assert pipe._config is config
        assert hasattr(pipe, "_video_extractor")
        assert hasattr(pipe, "_audio_extractor")
        assert hasattr(pipe, "_asr_client")
        assert hasattr(pipe, "_llm_analyzer")

    def test_init_force_flag(self):
        """force=True 时 _force 应为 True，影响断点恢复逻辑。"""
        config = make_mock_config()
        pipe = AnalysisPipeline(config=config, force=True)
        assert pipe._force is True

    def test_init_force_false_by_default(self):
        """默认 force=False。"""
        config = make_mock_config()
        pipe = AnalysisPipeline(config=config)
        assert pipe._force is False


class TestAnalysisPipelineRun:
    """测试完整流程编排。"""

    def test_run_full_pipeline(self, tmp_path):
        """验证完整流程：video → audio → ASR → LLM → frames → reports。"""
        pipe = make_pipeline()
        output_dir = str(tmp_path / "output")

        video_info = _make_video_info()
        audio_info = _make_audio_info(str(tmp_path / "audio.wav"))
        transcript = _make_transcript()
        event_timeline = EventTimeline(events=[])

        pipe._video_extractor = Mock()
        pipe._audio_extractor = Mock()
        pipe._asr_client = Mock()
        pipe._llm_analyzer = Mock()
        pipe._frame_extractor = Mock()
        pipe._quality_report_generator = Mock()
        pipe._score_card_generator = Mock()

        pipe._video_extractor.extract_info.return_value = video_info
        pipe._audio_extractor.extract.return_value = audio_info
        pipe._asr_client.recognize.return_value = transcript
        pipe._llm_analyzer.detect_events.return_value = event_timeline
        pipe._llm_analyzer.assess_quality.return_value = ([], [
            ScoreDimension(
                name="教学内容", score=8.0, max_score=25.0, weight=0.25,
                evidence="内容充实", details="详见课堂录音", grade="良",
                timestamp=60.0,
            )
        ])
        pipe._frame_extractor.extract_for_events.return_value = []
        pipe._quality_report_generator.generate.return_value = None
        pipe._score_card_generator.generate.return_value = None

        with patch.object(AnalysisPipeline, "validate_format", return_value=True, create=True), \
             patch("classroom_analyzer.pipeline.VideoExtractor.validate_format", return_value=True):
            result = pipe.run(video_path="test.mp4", output_dir=output_dir)

        assert isinstance(result, AnalysisResult)
        assert result.video_info == video_info
        assert result.audio_info == audio_info
        assert result.transcript == transcript
        assert result.event_timeline == event_timeline
        assert result.output_dir == output_dir

    def test_run_calls_all_steps(self, tmp_path):
        """验证各子步骤方法都被调用。"""
        pipe = make_pipeline()
        output_dir = str(tmp_path / "output")

        pipe._video_extractor = Mock()
        pipe._audio_extractor = Mock()
        pipe._asr_client = Mock()
        pipe._llm_analyzer = Mock()
        pipe._frame_extractor = Mock()
        pipe._quality_report_generator = Mock()
        pipe._score_card_generator = Mock()

        pipe._video_extractor.extract_info.return_value = _make_video_info()
        pipe._audio_extractor.extract.return_value = _make_audio_info(
            str(tmp_path / "audio.wav")
        )
        pipe._asr_client.recognize.return_value = _make_transcript()
        pipe._llm_analyzer.detect_events.return_value = EventTimeline(events=[])
        pipe._llm_analyzer.assess_quality.return_value = ([], [])
        pipe._frame_extractor.extract_for_events.return_value = []
        pipe._quality_report_generator.generate.return_value = None
        pipe._score_card_generator.generate.return_value = None

        with patch("classroom_analyzer.pipeline.VideoExtractor.validate_format", return_value=True):
            pipe.run(video_path="test.mp4", output_dir=output_dir)

        pipe._video_extractor.extract_info.assert_called_once()
        pipe._audio_extractor.extract.assert_called_once()
        pipe._asr_client.recognize.assert_called_once()
        pipe._llm_analyzer.detect_events.assert_called_once()
        pipe._llm_analyzer.assess_quality.assert_called_once()
        pipe._frame_extractor.extract_for_events.assert_called_once()

    def test_run_video_not_exists_raises_pipeline_error(self, tmp_path):
        """传入不存在的视频路径应抛出 PipelineError。"""
        pipe = make_pipeline()
        output_dir = str(tmp_path / "output")

        with pytest.raises(PipelineError):
            pipe.run(video_path="definitely_not_exists.mp4", output_dir=output_dir)

    def test_run_with_progress_callback(self, tmp_path):
        """进度回调应在各步骤被调用。"""
        pipe = make_pipeline()
        output_dir = str(tmp_path / "output")

        pipe._video_extractor = Mock()
        pipe._audio_extractor = Mock()
        pipe._asr_client = Mock()
        pipe._llm_analyzer = Mock()
        pipe._frame_extractor = Mock()
        pipe._quality_report_generator = Mock()
        pipe._score_card_generator = Mock()

        pipe._video_extractor.extract_info.return_value = _make_video_info()
        pipe._audio_extractor.extract.return_value = _make_audio_info(
            str(tmp_path / "audio.wav")
        )
        pipe._asr_client.recognize.return_value = _make_transcript()
        pipe._llm_analyzer.detect_events.return_value = EventTimeline(events=[])
        pipe._llm_analyzer.assess_quality.return_value = ([], [])
        pipe._frame_extractor.extract_for_events.return_value = []
        pipe._quality_report_generator.generate.return_value = None
        pipe._score_card_generator.generate.return_value = None

        callback_calls: list[tuple[int, str]] = []
        def capture_cb(step: int, msg: str) -> None:
            callback_calls.append((step, msg))

        with patch("classroom_analyzer.pipeline.VideoExtractor.validate_format", return_value=True):
            pipe.run(video_path="test.mp4", output_dir=output_dir, progress_callback=capture_cb)

        # 至少应有一次回调
        assert len(callback_calls) > 0


class TestAnalysisPipelineResume:
    """测试断点恢复逻辑（force=False 时，中间文件存在则跳过该步）。"""

    def test_resume_skips_audio_extraction_when_exists(self, tmp_path):
        """当音频文件已存在且 force=False 时，音频提取步骤应被跳过。"""
        pipe = make_pipeline()
        output_dir = str(tmp_path / "output")
        Path(output_dir).mkdir(parents=True, exist_ok=True)

        # 预先创建音频文件，模拟已有断点
        audio_path = Path(output_dir) / "audio.wav"
        audio_path.write_bytes(b"RIFF" + b"\x00" * 40)  # 伪WAV头

        pipe._video_extractor = Mock()
        pipe._audio_extractor = Mock()
        pipe._asr_client = Mock()
        pipe._llm_analyzer = Mock()
        pipe._frame_extractor = Mock()
        pipe._quality_report_generator = Mock()
        pipe._score_card_generator = Mock()

        pipe._video_extractor.extract_info.return_value = _make_video_info()
        pipe._asr_client.recognize.return_value = _make_transcript()
        pipe._llm_analyzer.detect_events.return_value = EventTimeline(events=[])
        pipe._llm_analyzer.assess_quality.return_value = ([], [])
        pipe._frame_extractor.extract_for_events.return_value = []
        pipe._quality_report_generator.generate.return_value = None
        pipe._score_card_generator.generate.return_value = None

        with patch("classroom_analyzer.pipeline.VideoExtractor.validate_format", return_value=True):
            result = pipe.run(video_path="test.mp4", output_dir=output_dir)

        # 音频提取不应被调用（已有缓存）
        pipe._audio_extractor.extract.assert_not_called()
        assert isinstance(result, AnalysisResult)

    def test_resume_skips_asr_when_transcript_exists(self, tmp_path):
        """当转录文件已存在且 force=False 时，ASR 步骤应被跳过。"""
        pipe = make_pipeline()
        output_dir = str(tmp_path / "output")
        Path(output_dir).mkdir(parents=True, exist_ok=True)

        # 预先创建音频和转录文件
        audio_path = Path(output_dir) / "audio.wav"
        audio_path.write_bytes(b"RIFF" + b"\x00" * 40)
        transcript_path = Path(output_dir) / "transcript.txt"
        transcript_path.write_text(
            "[00:00-00:05] teacher: 同学们好\n",
            encoding="utf-8",
        )

        pipe._video_extractor = Mock()
        pipe._audio_extractor = Mock()
        pipe._asr_client = Mock()
        pipe._llm_analyzer = Mock()
        pipe._frame_extractor = Mock()
        pipe._quality_report_generator = Mock()
        pipe._score_card_generator = Mock()

        pipe._video_extractor.extract_info.return_value = _make_video_info()
        pipe._llm_analyzer.detect_events.return_value = EventTimeline(events=[])
        pipe._llm_analyzer.assess_quality.return_value = ([], [])
        pipe._frame_extractor.extract_for_events.return_value = []
        pipe._quality_report_generator.generate.return_value = None
        pipe._score_card_generator.generate.return_value = None

        with patch("classroom_analyzer.pipeline.VideoExtractor.validate_format", return_value=True):
            result = pipe.run(video_path="test.mp4", output_dir=output_dir)

        # ASR 不应被调用
        pipe._asr_client.recognize.assert_not_called()
        assert isinstance(result, AnalysisResult)

    def test_force_flag_ignores_cache(self, tmp_path):
        """当 force=True 时，即使中间文件存在也应重新执行所有步骤。"""
        config = make_mock_config()
        pipe = AnalysisPipeline(config=config, force=True)
        output_dir = str(tmp_path / "output")
        Path(output_dir).mkdir(parents=True, exist_ok=True)

        # 预先创建音频文件
        audio_path = Path(output_dir) / "audio.wav"
        audio_path.write_bytes(b"RIFF" + b"\x00" * 40)

        pipe._video_extractor = Mock()
        pipe._audio_extractor = Mock()
        pipe._asr_client = Mock()
        pipe._llm_analyzer = Mock()
        pipe._frame_extractor = Mock()
        pipe._quality_report_generator = Mock()
        pipe._score_card_generator = Mock()

        pipe._video_extractor.extract_info.return_value = _make_video_info()
        pipe._audio_extractor.extract.return_value = _make_audio_info(str(audio_path))
        pipe._asr_client.recognize.return_value = _make_transcript()
        pipe._llm_analyzer.detect_events.return_value = EventTimeline(events=[])
        pipe._llm_analyzer.assess_quality.return_value = ([], [])
        pipe._frame_extractor.extract_for_events.return_value = []
        pipe._quality_report_generator.generate.return_value = None
        pipe._score_card_generator.generate.return_value = None

        with patch("classroom_analyzer.pipeline.VideoExtractor.validate_format", return_value=True):
            pipe.run(video_path="test.mp4", output_dir=output_dir)

        # force=True 时音频提取应被调用
        pipe._audio_extractor.extract.assert_called_once()


class TestAnalysisPipelineSteps:
    """测试各步骤方法。"""

    def test_step_read_video_valid(self, tmp_path):
        """传入支持的格式应能正常返回 VideoInfo。"""
        pipe = make_pipeline()
        video_info = _make_video_info()
        pipe._video_extractor = Mock()
        pipe._video_extractor.extract_info.return_value = video_info

        with patch("classroom_analyzer.pipeline.VideoExtractor.validate_format", return_value=True):
            result = pipe._step_read_video("test.mp4")
        assert result == video_info

    def test_step_read_video_unsupported_format(self):
        """传入不支持的格式应抛出 PipelineError。"""
        pipe = make_pipeline()
        with pytest.raises(PipelineError, match="不支持的视频格式"):
            pipe._step_read_video("test.txt")

    def test_load_transcript_from_file(self, tmp_path):
        """_load_transcript 应正确解析 MM:SS 格式的转录文本。"""
        pipe = make_pipeline()
        transcript_file = tmp_path / "transcript.txt"
        transcript_file.write_text(
            "[00:00-00:05] teacher: 同学们好\n"
            "[00:05-00:10] student: 老师好\n",
            encoding="utf-8",
        )
        result = pipe._load_transcript(str(transcript_file))
        assert len(result.segments) == 2
        assert result.segments[0].text == "同学们好"
        assert result.segments[0].start_time == 0.0
        assert result.segments[0].end_time == 5.0
        assert result.segments[1].speaker == "student"

    def test_save_and_load_events(self, tmp_path):
        """_save_events + _load_events 应形成完整的序列化/反序列化闭环。"""
        pipe = make_pipeline()
        events_file = tmp_path / "events.json"
        original = EventTimeline(events=[
            TeachingEvent(
                event_type="环节切换",
                subtype="开场",
                start_time=0.0,
                end_time=30.0,
                description="课程开始",
                confidence=0.9,
                related_text="同学们好",
            )
        ])
        pipe._save_events(original, str(events_file))
        loaded = pipe._load_events(str(events_file))

        assert len(loaded.events) == 1
        assert loaded.events[0].event_type == "环节切换"
        assert loaded.events[0].start_time == 0.0
        assert loaded.events[0].description == "课程开始"
