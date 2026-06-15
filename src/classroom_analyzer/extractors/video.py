"""视频信息提取模块 — 使用ffprobe获取视频元数据"""

import json
import subprocess
from pathlib import Path

from loguru import logger

from classroom_analyzer.config import ClassroomAnalyzerError
from classroom_analyzer.models import VideoInfo


class VideoExtractorError(ClassroomAnalyzerError):
    """视频提取异常。"""
    pass


class VideoExtractor:
    """视频文件信息提取器，使用ffprobe获取元数据。"""

    SUPPORTED_FORMATS = {".mp4", ".flv", ".mkv", ".avi", ".mov", ".wmv"}

    def __init__(self, ffmpeg_path: str = "ffmpeg") -> None:
        """初始化视频提取器。

        Args:
            ffmpeg_path: FFmpeg可执行文件路径（用于推断ffprobe路径）
        """
        self._ffmpeg_path = ffmpeg_path

    def _get_ffprobe_path(self) -> str:
        """根据ffmpeg路径推断ffprobe路径。"""
        import shutil as _shutil
        # 先查系统PATH
        ffprobe = _shutil.which("ffprobe")
        if ffprobe:
            return ffprobe
        # 从ffmpeg路径同目录推断
        if self._ffmpeg_path and self._ffmpeg_path != "ffmpeg":
            p = Path(self._ffmpeg_path).parent / "ffprobe.exe"
            if p.exists():
                return str(p)
            p2 = Path(self._ffmpeg_path).parent / "ffprobe"
            if p2.exists():
                return str(p2)
        return "ffprobe"

    def extract_info(self, file_path: str) -> VideoInfo:
        """提取视频文件信息。

        Args:
            file_path: 视频文件路径

        Returns:
            VideoInfo: 视频信息对象

        Raises:
            VideoExtractorError: 提取失败时抛出
        """
        path = Path(file_path)
        if not path.exists():
            raise VideoExtractorError(f"视频文件不存在：{file_path}")

        probe_data = self._run_ffprobe(file_path)

        try:
            format_info = probe_data.get("format", {})
            streams = probe_data.get("streams", [])

            # 获取视频流
            video_stream = None
            for stream in streams:
                if stream.get("codec_type") == "video":
                    video_stream = stream
                    break

            duration = float(format_info.get("duration", 0.0))
            file_size = int(format_info.get("size", 0))
            fmt = format_info.get("format_name", "unknown")

            resolution = (0, 0)
            if video_stream:
                width = int(video_stream.get("width", 0))
                height = int(video_stream.get("height", 0))
                resolution = (width, height)

            return VideoInfo(
                file_path=str(path.resolve()),
                file_size=file_size,
                duration=duration,
                format=fmt,
                resolution=resolution,
            )
        except (KeyError, ValueError, TypeError) as e:
            raise VideoExtractorError(f"解析ffprobe输出失败：{e}")

    @staticmethod
    def validate_format(file_path: str) -> bool:
        """校验视频文件格式是否受支持。

        Args:
            file_path: 视频文件路径

        Returns:
            bool: 格式是否受支持
        """
        path = Path(file_path)
        suffix = path.suffix.lower()
        if suffix not in VideoExtractor.SUPPORTED_FORMATS:
            logger.error(f"不支持的视频格式：{suffix}，支持格式：{VideoExtractor.SUPPORTED_FORMATS}")
            return False
        if not path.exists():
            logger.error(f"视频文件不存在：{file_path}")
            return False
        return True

    def _run_ffprobe(self, file_path: str) -> dict:
        """运行ffprobe获取视频元数据。

        Args:
            file_path: 视频文件路径

        Returns:
            dict: ffprobe输出的JSON数据

        Raises:
            VideoExtractorError: ffprobe执行失败时抛出
        """
        cmd = [
            self._get_ffprobe_path(),
            "-v", "quiet",
            "-print_format", "json",
            "-show_format",
            "-show_streams",
            str(file_path),
        ]

        logger.debug(f"执行ffprobe：{' '.join(cmd)}")

        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                encoding="utf-8",
                errors="replace",
                timeout=60,
            )
            if result.returncode != 0:
                raise VideoExtractorError(
                    f"ffprobe执行失败（返回码 {result.returncode}）：{result.stderr}"
                )
            return json.loads(result.stdout)
        except FileNotFoundError:
            raise VideoExtractorError(
                "未找到ffprobe，请安装FFmpeg并添加到PATH。\n"
                "下载地址：https://ffmpeg.org/download.html"
            )
        except subprocess.TimeoutExpired:
            raise VideoExtractorError("ffprobe执行超时")
        except json.JSONDecodeError as e:
            raise VideoExtractorError(f"ffprobe输出解析失败：{e}")
