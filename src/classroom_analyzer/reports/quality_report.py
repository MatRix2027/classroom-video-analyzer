"""质检报告生成器 — 输出Markdown格式报告"""

from pathlib import Path

from loguru import logger

from classroom_analyzer.config import ClassroomAnalyzerError
from classroom_analyzer.models import QualityCheckItem, QualityReport


def _fmt_ts(seconds: float | None) -> str:
    """格式化时间戳为 HH:MM:SS 或 MM:SS。"""
    if seconds is None:
        return ""
    hours = int(seconds) // 3600
    minutes = (int(seconds) % 3600) // 60
    secs = int(seconds) % 60
    if hours > 0:
        return f"[{hours:01d}:{minutes:02d}:{secs:02d}]"
    return f"[{minutes:02d}:{secs:02d}]"


class ReportGeneratorError(ClassroomAnalyzerError):
    """报告生成异常。"""
    pass


class QualityReportGenerator:
    """质检报告生成器：生成Markdown格式的质检报告。"""

    def generate(self, report: QualityReport, output_path: str) -> str:
        """生成质检报告并保存到文件。

        Args:
            report: 质检报告数据
            output_path: 输出文件路径

        Returns:
            str: 报告文件路径

        Raises:
            ReportGeneratorError: 生成失败时抛出
        """
        try:
            markdown = report.to_markdown()

            # 附加详细事件摘要
            event_summary_md = self._format_event_summary(report.event_summary)
            if event_summary_md:
                markdown += "\n## 教学事件统计\n\n"
                markdown += event_summary_md

            # 附加详细质检项（含时间戳核验）
            check_items_md = self._format_check_items(report.check_items)
            if check_items_md:
                markdown += "\n## 质检详情（含时间戳）\n\n"
                markdown += check_items_md

            # 写入文件
            path = Path(output_path)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(markdown, encoding="utf-8")

            logger.info(f"质检报告已生成：{output_path}")
            return str(path.resolve())

        except Exception as e:
            raise ReportGeneratorError(f"生成质检报告失败：{e}")

    @staticmethod
    def _format_check_items(items: list[QualityCheckItem]) -> str:
        """格式化质检清单详情。"""
        if not items:
            return ""

        lines: list[str] = []

        for item in items:
            status = "✅" if item.passed else "❌"
            red_flag = " 🚫红线" if item.is_red_line else ""
            ts = _fmt_ts(item.timestamp)
            lines.append(f"- {status}{red_flag} {item.description} {ts}")
            if item.evidence:
                lines.append(f"  > 证据：{item.evidence}")

        return "\n".join(lines)

    @staticmethod
    def _format_event_summary(summary: dict) -> str:
        """格式化教学事件统计摘要。"""
        if not summary:
            return ""

        lines: list[str] = []
        total = summary.get("total", 0)
        lines.append(f"共识别教学事件 **{total}** 个：")
        lines.append("")

        for key, value in summary.items():
            if key == "total":
                continue
            lines.append(f"- {key}：{value} 个")

        return "\n".join(lines)
