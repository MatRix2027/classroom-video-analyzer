"""FFmpeg音频提取模块"""

import subprocess
from pathlib import Path

from loguru import logger

from classroom_analyzer.config import ClassroomAnalyzerError
from classroom_analyzer.models import AudioInfo


class AudioExtractorError(ClassroomAnalyzerError):
    """音频提取异常。"""
    pass


class AudioExtractor:
    """FFmpeg音频提取器：从视频文件中提取音频轨。"""

    def __init__(self, ffmpeg_path: str = "ffmpeg") -> None:
        """初始化音频提取器。

        Args:
            ffmpeg_path: FFmpeg可执行文件路径
        """
        self.ffmpeg_path = ffmpeg_path

    def _get_ffprobe_path(self) -> str:
        """根据ffmpeg路径推断ffprobe路径。"""
        import shutil as _shutil
        ffprobe = _shutil.which("ffprobe")
        if ffprobe:
            return ffprobe
        if self.ffmpeg_path and self.ffmpeg_path != "ffmpeg":
            p = Path(self.ffmpeg_path).parent / "ffprobe.exe"
            if p.exists():
                return str(p)
            p2 = Path(self.ffmpeg_path).parent / "ffprobe"
            if p2.exists():
                return str(p2)
        return "ffprobe"

    def extract(
        self,
        video_path: str,
        output_path: str,
        sample_rate: int = 16000,
    ) -> AudioInfo:
        """从视频文件中提取音频。

        Args:
            video_path: 视频文件路径
            output_path: 输出音频文件路径（WAV格式）
            sample_rate: 采样率（默认16000Hz）

        Returns:
            AudioInfo: 音频信息对象

        Raises:
            AudioExtractorError: 提取失败时抛出
        """
        video = Path(video_path)
        output = Path(output_path)

        if not video.exists():
            raise AudioExtractorError(f"视频文件不存在：{video_path}")

        output.parent.mkdir(parents=True, exist_ok=True)

        cmd = self._build_extract_cmd(video_path, output_path, sample_rate)
        logger.debug(f"执行FFmpeg音频提取：{' '.join(cmd)}")

        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                encoding="utf-8",
                errors="replace",
                timeout=600,
            )
            if result.returncode != 0:
                raise AudioExtractorError(
                    f"FFmpeg音频提取失败（返回码 {result.returncode}）：{result.stderr}"
                )
        except FileNotFoundError:
            raise AudioExtractorError(
                f"未找到FFmpeg：{self.ffmpeg_path}\n"
                "请安装FFmpeg并添加到PATH。"
            )
        except subprocess.TimeoutExpired:
            raise AudioExtractorError("FFmpeg音频提取超时（超过600秒）")

        if not output.exists():
            raise AudioExtractorError(f"音频文件未生成：{output_path}")

        # 获取音频时长（用ffprobe）
        duration = self._get_audio_duration(output_path)

        logger.info(f"音频提取成功：{output_path}（{duration:.1f}秒）")
        return AudioInfo(
            file_path=str(output.resolve()),
            duration=duration,
            sample_rate=sample_rate,
            channels=1,
            format="wav",
        )

    def _build_extract_cmd(
        self,
        video_path: str,
        output_path: str,
        sample_rate: int,
    ) -> list[str]:
        """构建FFmpeg音频提取命令。

        Args:
            video_path: 视频文件路径
            output_path: 输出音频文件路径
            sample_rate: 采样率

        Returns:
            list[str]: 命令参数列表
        """
        return [
            self.ffmpeg_path,
            "-i", video_path,
            "-vn",                    # 不要视频
            "-acodec", "pcm_s16le",   # PCM 16位小端
            "-ar", str(sample_rate),  # 采样率
            "-ac", "1",               # 单声道
            "-y",                     # 覆盖输出
            output_path,
        ]

    def _get_audio_duration(self, audio_path: str) -> float:
        """用ffprobe获取音频文件时长。

        Args:
            audio_path: 音频文件路径

        Returns:
            float: 音频时长（秒）
        """
        import json

        cmd = [
            self._get_ffprobe_path(),
            "-v", "quiet",
            "-print_format", "json",
            "-show_format",
            audio_path,
        ]

        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                encoding="utf-8",
                errors="replace",
                timeout=30,
            )
            if result.returncode == 0:
                data = json.loads(result.stdout)
                return float(data.get("format", {}).get("duration", 0.0))
        except Exception:
            pass

        return 0.0
