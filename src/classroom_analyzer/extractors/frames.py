"""事件驱动 + 定期采样 FFmpeg截帧模块"""

import subprocess
from pathlib import Path

from loguru import logger

from classroom_analyzer.config import ClassroomAnalyzerError
from classroom_analyzer.models import KeyFrame, TeachingEvent


class FrameExtractorError(ClassroomAnalyzerError):
    """截帧异常。"""
    pass


class FrameExtractor:
    """事件驱动 + 定期采样 FFmpeg截帧器。

    采样策略（双轨制）：
    1. 事件驱动：为每个教学事件截取关键帧（捕捉教学行为）
    2. 定期采样：按固定间隔采样帧（捕捉学生表情、教学节奏、环境状态）

    两种帧合并去重后，为视觉模型提供更全面的课堂画面覆盖。
    """

    def __init__(self, ffmpeg_path: str = "ffmpeg") -> None:
        """初始化截帧器。

        Args:
            ffmpeg_path: FFmpeg可执行文件路径
        """
        self.ffmpeg_path = ffmpeg_path

    def extract_at_timestamp(
        self,
        video_path: str,
        timestamp: float,
        output_dir: str,
        frame_name: str,
    ) -> str:
        """在指定时间戳截取一帧。

        Args:
            video_path: 视频文件路径
            timestamp: 时间戳（秒）
            output_dir: 输出目录
            frame_name: 帧文件名（不含扩展名）

        Returns:
            str: 截取的帧图片路径

        Raises:
            FrameExtractorError: 截帧失败时抛出
        """
        out_dir = Path(output_dir)
        out_dir.mkdir(parents=True, exist_ok=True)
        output_path = out_dir / f"{frame_name}.jpg"

        cmd = self._build_frame_cmd(video_path, timestamp, str(output_path))
        logger.debug(f"截帧：timestamp={timestamp:.1f}s → {output_path}")

        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                encoding="utf-8",
                errors="replace",
                timeout=30,
            )
            if result.returncode != 0:
                logger.warning(f"截帧失败（timestamp={timestamp:.1f}s）：{result.stderr}")
                # 截帧失败不中断整个流程，返回空路径
                return ""
        except FileNotFoundError:
            raise FrameExtractorError(
                f"未找到FFmpeg：{self.ffmpeg_path}\n"
                "请安装FFmpeg并添加到PATH。"
            )
        except subprocess.TimeoutExpired:
            logger.warning(f"截帧超时（timestamp={timestamp:.1f}s）")
            return ""

        if not output_path.exists():
            logger.warning(f"帧文件未生成：{output_path}")
            return ""

        return str(output_path.resolve())

    def extract_for_events(
        self,
        video_path: str,
        events: list[TeachingEvent],
        output_dir: str,
    ) -> list[KeyFrame]:
        """为每个教学事件截取关键帧。

        Args:
            video_path: 视频文件路径
            events: 教学事件列表
            output_dir: 输出目录

        Returns:
            list[KeyFrame]: 关键帧列表
        """
        keyframes: list[KeyFrame] = []
        out_dir = Path(output_dir)
        out_dir.mkdir(parents=True, exist_ok=True)

        logger.info(f"为 {len(events)} 个教学事件截取关键帧")

        for i, event in enumerate(events):
            # 使用事件开始时间戳截帧
            timestamp = event.start_time
            frame_name = f"frame_{event.event_type}_{timestamp:.0f}"

            # 避免文件名冲突
            frame_path = self.extract_at_timestamp(
                video_path=video_path,
                timestamp=timestamp,
                output_dir=output_dir,
                frame_name=frame_name,
            )

            if frame_path:
                keyframes.append(KeyFrame(
                    file_path=frame_path,
                    timestamp=timestamp,
                    trigger_event=event,
                ))
            else:
                logger.debug(f"事件 {i+1}/{len(events)} 截帧跳过：{event.event_type}@{timestamp:.1f}s")

        logger.info(f"截帧完成：{len(keyframes)}/{len(events)} 成功")
        return keyframes

    def _build_frame_cmd(
        self,
        video_path: str,
        timestamp: float,
        output_path: str,
    ) -> list[str]:
        """构建FFmpeg截帧命令。

        Args:
            video_path: 视频文件路径
            timestamp: 时间戳（秒）
            output_path: 输出帧图片路径

        Returns:
            list[str]: 命令参数列表
        """
        return [
            self.ffmpeg_path,
            "-ss", f"{timestamp:.3f}",  # 精确seek
            "-i", video_path,
            "-frames:v", "1",           # 只截一帧
            "-q:v", "2",                # JPEG质量（2=高质量）
            "-y",                       # 覆盖输出
            output_path,
        ]

    def extract_periodic_frames(
        self,
        video_path: str,
        duration: float,
        output_dir: str,
        interval_seconds: float = 120.0,
    ) -> list[KeyFrame]:
        """按固定时间间隔采样帧，用于捕捉学生表情、教学节奏、环境状态。

        与事件驱动截帧互补：事件帧捕捉教学行为，定期帧捕捉整体课堂状态。

        Args:
            video_path: 视频文件路径
            duration: 视频总时长（秒）
            output_dir: 输出目录
            interval_seconds: 采样间隔（秒），默认120秒（2分钟）

        Returns:
            list[KeyFrame]: 定期采样关键帧列表
        """
        keyframes: list[KeyFrame] = []
        out_dir = Path(output_dir)
        out_dir.mkdir(parents=True, exist_ok=True)

        if duration <= 0 or interval_seconds <= 0:
            logger.warning(f"定期采样参数无效：duration={duration}, interval={interval_seconds}")
            return keyframes

        # 计算采样时间点
        timestamps: list[float] = []
        t = interval_seconds / 2  # 从半间隔开始（避免截到片头黑屏）
        while t < duration:
            timestamps.append(t)
            t += interval_seconds

        logger.info(f"定期采样：视频时长 {duration:.0f}s，间隔 {interval_seconds:.0f}s，共 {len(timestamps)} 个采样点")

        for i, timestamp in enumerate(timestamps):
            frame_name = f"periodic_{i:03d}_{timestamp:.0f}s"
            frame_path = self.extract_at_timestamp(
                video_path=video_path,
                timestamp=timestamp,
                output_dir=output_dir,
                frame_name=frame_name,
            )

            if frame_path:
                keyframes.append(KeyFrame(
                    file_path=frame_path,
                    timestamp=timestamp,
                    trigger_event=None,  # 定期采样帧无关联事件
                ))

        logger.info(f"定期采样完成：{len(keyframes)}/{len(timestamps)} 成功")
        return keyframes
