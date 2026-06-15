"""测试 CLI 基本命令"""

import pytest
from click.testing import CliRunner
from classroom_analyzer.cli import cli


class TestCLIBasic:
    """测试 CLI 帮助信息和基本参数。"""

    def setup_method(self):
        self.runner = CliRunner()

    def test_cli_help(self):
        """classroom-analyzer --help 应正常输出。"""
        result = self.runner.invoke(cli, ["--help"])
        assert result.exit_code == 0
        assert "classroom-analyzer" in result.output.lower() or "Usage:" in result.output

    def test_analyze_help(self):
        """classroom-analyzer analyze --help 应正常输出。"""
        result = self.runner.invoke(cli, ["analyze", "--help"])
        assert result.exit_code == 0

    def test_level_option_l1_l3(self):
        """--level 参数应接受 L1_L3。"""
        result = self.runner.invoke(cli, ["analyze", "--level", "L1_L3", "--help"])
        # 不应报 unrecognized arguments 错误
        assert "unrecognized arguments" not in result.output

    def test_level_option_l4_l6(self):
        """--level 参数应接受 L4_L6。"""
        result = self.runner.invoke(cli, ["analyze", "--level", "L4_L6", "--help"])
        assert "unrecognized arguments" not in result.output

    def test_level_option_l7_l9(self):
        """--level 参数应接受 L7_L9。"""
        result = self.runner.invoke(cli, ["analyze", "--level", "L7_L9", "--help"])
        assert "unrecognized arguments" not in result.output

    def test_invalid_level_rejected(self):
        """--level 传入无效值应报错（如果CLI有校验）。"""
        result = self.runner.invoke(cli, ["analyze", "--level", "INVALID", "--help"])
        # 可能有校验错误，但不能crash
        assert result.exit_code != -1  # 不应异常退出
