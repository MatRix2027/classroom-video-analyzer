"""报告生成测试"""

import json
from pathlib import Path

import pytest

from classroom_analyzer.models import (
    QualityCheckItem,
    QualityReport,
    ScoreCard,
    ScoreDimension,
    VideoInfo,
)
from classroom_analyzer.reports.quality_report import QualityReportGenerator
from classroom_analyzer.reports.score_card import ScoreCardGenerator


class TestQualityReportGenerator:
    """QualityReportGenerator 测试。"""

    def test_generate(self, sample_quality_report: QualityReport, tmp_path: Path) -> None:
        output_path = tmp_path / "quality_report.md"
        generator = QualityReportGenerator()
        result_path = generator.generate(sample_quality_report, str(output_path))

        assert Path(result_path).exists()
        content = Path(result_path).read_text(encoding="utf-8")
        assert "# 课堂质检报告" in content
        assert "教学事件统计" in content

    def test_generate_with_check_items(self, tmp_path: Path) -> None:
        video_info = VideoInfo(
            file_path="test.mp4",
            file_size=1000,
            duration=3000.0,
            format="mp4",
            resolution=(1920, 1080),
        )
        report = QualityReport(
            video_info=video_info,
            transcript_summary="测试",
            check_items=[
                QualityCheckItem(description="检查项1", passed=True, evidence="证据1", timestamp=60.0),
                QualityCheckItem(description="检查项2", passed=False, evidence="证据2", timestamp=None),
            ],
            event_summary={"total": 5, "环节切换": 2},
            score_card=ScoreCard(
                dimensions=[
                    ScoreDimension(name="维度1", score=80.0, max_score=100.0, weight=1.0, evidence="好"),
                ],
                total_score=80.0,
                total_max=100.0,
            ),
        )

        output_path = tmp_path / "report.md"
        generator = QualityReportGenerator()
        generator.generate(report, str(output_path))

        content = output_path.read_text(encoding="utf-8")
        assert "✅ 检查项1" in content
        assert "❌ 检查项2" in content
        assert "事件统计" in content

    def test_format_check_items(self) -> None:
        items = [
            QualityCheckItem(description="测试通过", passed=True, evidence="有证据", timestamp=60.0),
        ]
        result = QualityReportGenerator._format_check_items(items)
        assert "✅" in result
        assert "测试通过" in result
        assert "证据：有证据" in result

    def test_format_check_items_empty(self) -> None:
        result = QualityReportGenerator._format_check_items([])
        assert result == ""

    def test_format_event_summary(self) -> None:
        summary = {"total": 10, "环节切换": 3, "互动指令": 7}
        result = QualityReportGenerator._format_event_summary(summary)
        assert "**10**" in result
        assert "环节切换" in result
        assert "互动指令" in result

    def test_format_event_summary_empty(self) -> None:
        result = QualityReportGenerator._format_event_summary({})
        assert result == ""


class TestScoreCardGenerator:
    """ScoreCardGenerator 测试。"""

    def test_generate(self, sample_score_card: ScoreCard, tmp_path: Path) -> None:
        output_path = tmp_path / "score_card.json"
        generator = ScoreCardGenerator()
        result_path = generator.generate(sample_score_card, str(output_path))

        assert Path(result_path).exists()
        data = json.loads(Path(result_path).read_text(encoding="utf-8"))
        assert "dimensions" in data
        assert "total_score" in data
        assert len(data["dimensions"]) == 5

    def test_generate_empty_card(self, tmp_path: Path) -> None:
        score_card = ScoreCard()
        output_path = tmp_path / "score_card.json"
        generator = ScoreCardGenerator()
        generator.generate(score_card, str(output_path))

        data = json.loads(output_path.read_text(encoding="utf-8"))
        assert data["dimensions"] == []
        assert data["total_score"] == 0.0

    def test_generate_valid_json(self, sample_score_card: ScoreCard, tmp_path: Path) -> None:
        output_path = tmp_path / "score_card.json"
        generator = ScoreCardGenerator()
        generator.generate(sample_score_card, str(output_path))

        # 验证是有效JSON
        content = output_path.read_text(encoding="utf-8")
        parsed = json.loads(content)
        assert isinstance(parsed, dict)
