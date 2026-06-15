"""Prompt模板管理模块 — 加载Markdown模板并用Jinja2渲染"""

from pathlib import Path

from jinja2 import BaseLoader, Environment
from loguru import logger

from classroom_analyzer.config import ClassroomAnalyzerError


class PromptTemplateError(ClassroomAnalyzerError):
    """Prompt模板异常。"""
    pass


class PromptTemplates:
    """Prompt模板管理器：从Markdown文件加载模板，用Jinja2渲染变量。"""

    def __init__(self, prompts_dir: str) -> None:
        """初始化模板管理器。

        Args:
            prompts_dir: Prompt模板文件目录路径
        """
        self.prompts_dir = Path(prompts_dir)
        self._env = Environment(
            loader=BaseLoader(),
            keep_trailing_newline=True,
        )
        self._cache: dict[str, str] = {}

        if not self.prompts_dir.exists():
            logger.warning(f"Prompt模板目录不存在：{prompts_dir}")

    def load(self, template_name: str) -> str:
        """加载指定名称的Prompt模板。

        Args:
            template_name: 模板名称（不含.md扩展名）

        Returns:
            str: 模板内容

        Raises:
            PromptTemplateError: 模板文件不存在或读取失败
        """
        if template_name in self._cache:
            return self._cache[template_name]

        template_path = self.prompts_dir / f"{template_name}.md"

        if not template_path.exists():
            raise PromptTemplateError(f"Prompt模板不存在：{template_path}")

        try:
            content = template_path.read_text(encoding="utf-8")
            self._cache[template_name] = content
            logger.debug(f"加载Prompt模板：{template_name}")
            return content
        except OSError as e:
            raise PromptTemplateError(f"读取Prompt模板失败：{e}")

    def render(self, template_name: str, **kwargs: object) -> str:
        """加载并渲染Prompt模板。

        Args:
            template_name: 模板名称（不含.md扩展名）
            **kwargs: 模板变量

        Returns:
            str: 渲染后的Prompt文本

        Raises:
            PromptTemplateError: 渲染失败
        """
        content = self.load(template_name)

        try:
            template = self._env.from_string(content)
            rendered = template.render(**kwargs)
            logger.debug(f"渲染Prompt模板：{template_name}（变量：{list(kwargs.keys())}）")
            return rendered
        except Exception as e:
            raise PromptTemplateError(f"渲染Prompt模板失败（{template_name}）：{e}")
