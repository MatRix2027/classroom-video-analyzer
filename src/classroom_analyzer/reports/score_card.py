"""评分卡生成器 — 输出JSON格式评分卡"""

from pathlib import Path

from loguru import logger

from classroom_analyzer.config import ClassroomAnalyzerError
from classroom_analyzer.models import ScoreCard


class ScoreCardGeneratorError(ClassroomAnalyzerError):
    """评分卡生成异常。"""
    pass


class ScoreCardGenerator:
    """评分卡生成器：生成JSON格式的评分卡。"""

    def generate(self, score_card: ScoreCard, output_path: str) -> str:
        """生成评分卡并保存到文件。

        Args:
            score_card: 评分卡数据
            output_path: 输出文件路径

        Returns:
            str: 评分卡文件路径

        Raises:
            ScoreCardGeneratorError: 生成失败时抛出
        """
        try:
            json_content = score_card.to_json()

            path = Path(output_path)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json_content, encoding="utf-8")

            logger.info(f"评分卡已生成：{output_path}")
            return str(path.resolve())

        except Exception as e:
            raise ScoreCardGeneratorError(f"生成评分卡失败：{e}")
