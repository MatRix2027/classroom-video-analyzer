"""LLM分析模块测试 — mock LLM API"""

import json
from unittest.mock import MagicMock, patch

import pytest

from classroom_analyzer.analysis.llm_analyzer import LLMAnalyzer, LLMAnalyzerError, _extract_json
from classroom_analyzer.analysis.prompt_templates import PromptTemplates, PromptTemplateError
from classroom_analyzer.models import (
    EventTimeline,
    QualityCheckItem,
    ScoreDimension,
    ScoringDimensionConfig,
    TeachingEvent,
    Transcript,
    TranscriptSegment,
)


@pytest.fixture
def llm_analyzer() -> LLMAnalyzer:
    """创建mock的LLM分析器。"""
    with patch("classroom_analyzer.analysis.llm_analyzer.OpenAI"):
        return LLMAnalyzer(
            api_key="test_key",
            model="test-model",
            base_url="https://api.test.com/v1",
            chunk_size=2000,
            chunk_overlap=200,
        )


@pytest.fixture
def sample_transcript() -> Transcript:
    """示例转录文本。"""
    return Transcript(
        segments=[
            TranscriptSegment(start_time=0.0, end_time=30.0, text="同学们好，今天我们来学习函数。", speaker="teacher"),
            TranscriptSegment(start_time=30.0, end_time=35.0, text="老师好！", speaker="student_1"),
            TranscriptSegment(start_time=35.0, end_time=120.0, text="首先我们来看函数的定义……", speaker="teacher"),
        ],
        duration=120.0,
        speaker_count=2,
    )


class TestPromptTemplates:
    """PromptTemplates 测试。"""

    def test_load(self, tmp_path) -> None:
        # 创建临时模板文件
        prompts_dir = tmp_path / "prompts"
        prompts_dir.mkdir()
        (prompts_dir / "test_template.md").write_text("Hello {{ name }}!", encoding="utf-8")

        pt = PromptTemplates(prompts_dir=str(prompts_dir))
        content = pt.load("test_template")
        assert content == "Hello {{ name }}!"

    def test_load_not_exists(self, tmp_path) -> None:
        pt = PromptTemplates(prompts_dir=str(tmp_path))
        with pytest.raises(PromptTemplateError, match="Prompt模板不存在"):
            pt.load("nonexistent")

    def test_render(self, tmp_path) -> None:
        prompts_dir = tmp_path / "prompts"
        prompts_dir.mkdir()
        (prompts_dir / "greeting.md").write_text("Hello {{ user }}, welcome to {{ place }}!", encoding="utf-8")

        pt = PromptTemplates(prompts_dir=str(prompts_dir))
        result = pt.render("greeting", user="Alice", place="Wonderland")
        assert result == "Hello Alice, welcome to Wonderland!"

    def test_cache(self, tmp_path) -> None:
        prompts_dir = tmp_path / "prompts"
        prompts_dir.mkdir()
        (prompts_dir / "test.md").write_text("Cached content", encoding="utf-8")

        pt = PromptTemplates(prompts_dir=str(prompts_dir))
        content1 = pt.load("test")
        content2 = pt.load("test")
        assert content1 == content2


class TestExtractJson:
    """_extract_json 辅助函数测试。"""

    def test_pure_json_array(self) -> None:
        text = '[{"a": 1}]'
        assert _extract_json(text) == text

    def test_pure_json_object(self) -> None:
        text = '{"a": 1, "b": 2}'
        assert _extract_json(text) == text

    def test_json_in_code_block(self) -> None:
        text = '```json\n{"a": 1}\n```'
        assert _extract_json(text) == '{"a": 1}'

    def test_json_with_surrounding_text(self) -> None:
        text = 'Here is the result:\n{"events": []}\nEnd.'
        result = _extract_json(text)
        assert result is not None
        assert "events" in result

    def test_no_json(self) -> None:
        text = "This is just plain text without any JSON."
        assert _extract_json(text) is None

    def test_invalid_json(self) -> None:
        text = '{"broken": json}'
        assert _extract_json(text) is None


class TestLLMAnalyzer:
    """LLMAnalyzer 测试。"""

    def test_init(self, llm_analyzer: LLMAnalyzer) -> None:
        assert llm_analyzer.api_key == "test_key"
        assert llm_analyzer.model == "test-model"
        assert llm_analyzer.chunk_size == 2000

    def test_chunk_transcript_short(self, llm_analyzer: LLMAnalyzer, sample_transcript: Transcript) -> None:
        chunks = llm_analyzer._chunk_transcript(sample_transcript, chunk_size=5000, overlap=200)
        assert len(chunks) == 1

    def test_chunk_transcript_long(self, llm_analyzer: LLMAnalyzer) -> None:
        # 创建长文本转录
        long_segments = [
            TranscriptSegment(
                start_time=i * 10.0,
                end_time=(i + 1) * 10.0,
                text="这是一段测试文字" * 50,
                speaker="teacher",
            )
            for i in range(20)
        ]
        long_transcript = Transcript(segments=long_segments, duration=200.0, speaker_count=1)

        chunks = llm_analyzer._chunk_transcript(long_transcript, chunk_size=500, overlap=50)
        assert len(chunks) > 1

    def test_merge_events(self) -> None:
        chunk1 = [
            TeachingEvent(event_type="环节切换", subtype="开场", start_time=0.0, end_time=10.0, description="开场", confidence=0.9),
        ]
        chunk2 = [
            TeachingEvent(event_type="环节切换", subtype="开场", start_time=0.0, end_time=10.0, description="开场", confidence=0.9),
            TeachingEvent(event_type="互动指令", subtype="提问", start_time=50.0, end_time=60.0, description="提问", confidence=0.85),
        ]

        timeline = LLMAnalyzer._merge_events([chunk1, chunk2])
        assert len(timeline.events) == 2  # 去重后
        assert timeline.events[0].start_time <= timeline.events[1].start_time

    def test_parse_events_response(self) -> None:
        response = json.dumps([
            {
                "event_type": "环节切换",
                "subtype": "开场",
                "start_time": 0.0,
                "end_time": 15.0,
                "description": "教师开始上课",
                "confidence": 0.95,
                "related_text": "同学们好",
            },
        ])

        events = LLMAnalyzer._parse_events_response(response)
        assert len(events) == 1
        assert events[0].event_type == "环节切换"
        assert events[0].confidence == 0.95

    def test_parse_events_response_in_code_block(self) -> None:
        response = '```json\n[{"event_type": "互动指令", "subtype": "提问", "start_time": 30, "end_time": 40, "description": "提问", "confidence": 0.8, "related_text": ""}]\n```'

        events = LLMAnalyzer._parse_events_response(response)
        assert len(events) == 1
        assert events[0].event_type == "互动指令"

    def test_parse_events_response_invalid(self) -> None:
        events = LLMAnalyzer._parse_events_response("No JSON here")
        assert len(events) == 0

    def test_parse_quality_response(self) -> None:
        response = json.dumps({
            "checklist": [
                {"description": "有无开场白", "passed": True, "evidence": "有开场", "timestamp": 0.0},
                {"description": "是否按时", "passed": False, "evidence": "超时", "timestamp": None},
            ],
            "scores": [
                {"name": "教学环节完整度", "score": 85, "evidence": "环节较完整", "details": "有开场讲授"},
                {"name": "互动质量", "score": 70, "evidence": "互动较少", "details": "仅一次提问"},
            ],
        })

        dimensions = [
            ScoringDimensionConfig(name="教学环节完整度", weight=0.5, criteria="完整"),
            ScoringDimensionConfig(name="互动质量", weight=0.5, criteria="互动好"),
        ]

        check_items, score_dims = LLMAnalyzer._parse_quality_response(response, dimensions)
        assert len(check_items) == 2
        assert check_items[0].passed is True
        assert check_items[1].passed is False
        assert len(score_dims) == 2

    def test_parse_quality_response_invalid(self) -> None:
        dimensions = [
            ScoringDimensionConfig(name="测试", weight=1.0, criteria="test"),
        ]
        check_items, score_dims = LLMAnalyzer._parse_quality_response("No JSON", dimensions)
        assert len(check_items) == 0
        assert len(score_dims) == 1  # 填充默认值

    @patch("classroom_analyzer.analysis.llm_analyzer.OpenAI")
    def test_detect_events(self, mock_openai: MagicMock, sample_transcript: Transcript) -> None:
        # Mock LLM响应
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = json.dumps([
            {
                "event_type": "环节切换",
                "subtype": "开场",
                "start_time": 0.0,
                "end_time": 30.0,
                "description": "教师开始上课",
                "confidence": 0.9,
                "related_text": "同学们好",
            },
        ])

        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = mock_response
        mock_openai.return_value = mock_client

        analyzer = LLMAnalyzer(api_key="test", model="test", base_url="https://test.com/v1")
        timeline = analyzer.detect_events(sample_transcript, ["环节切换", "互动指令"])

        assert isinstance(timeline, EventTimeline)
        assert len(timeline.events) >= 1

    @patch("classroom_analyzer.analysis.llm_analyzer.OpenAI")
    def test_call_llm_retry(self, mock_openai: MagicMock) -> None:
        # Mock LLM失败后成功
        success_response = MagicMock()
        success_response.choices = [MagicMock()]
        success_response.choices[0].message.content = "OK"

        mock_client = MagicMock()
        mock_client.chat.completions.create.side_effect = [
            Exception("API Error"),
            success_response,
        ]

        mock_openai.return_value = mock_client

        analyzer = LLMAnalyzer(api_key="test", model="test", base_url="https://test.com/v1")

        with patch("time.sleep"):  # 跳过重试等待
            result = analyzer._call_llm([{"role": "user", "content": "test"}])
        assert result == "OK"

    @patch("classroom_analyzer.analysis.llm_analyzer.OpenAI")
    def test_call_llm_max_retries(self, mock_openai: MagicMock) -> None:
        mock_client = MagicMock()
        mock_client.chat.completions.create.side_effect = Exception("API Error")
        mock_openai.return_value = mock_client

        analyzer = LLMAnalyzer(api_key="test", model="test", base_url="https://test.com/v1")

        with patch("time.sleep"):
            with pytest.raises(LLMAnalyzerError, match="LLM调用失败"):
                analyzer._call_llm([{"role": "user", "content": "test"}])
