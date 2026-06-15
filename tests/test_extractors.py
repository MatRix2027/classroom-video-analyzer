"""媒体处理模块测试 — mock FFmpeg"""

import json
import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from classroom_analyzer.extractors.audio import AudioExtractor, AudioExtractorError
from classroom_analyzer.extractors.frames import FrameExtractor, FrameExtractorError
from classroom_analyzer.extractors.video import VideoExtractor, VideoExtractorError
from classroom_analyzer.models import AudioInfo, KeyFrame, TeachingEvent, VideoInfo


class TestVideoExtractor:
    """VideoExtractor 测试。"""

    def _make_extractor(self) -> VideoExtractor:
        """创建测试用的 VideoExtractor 实例。"""
        return VideoExtractor(ffmpeg_path="ffmpeg")

    def test_validate_format_mp4(self, tmp_path: Path) -> None:
        video = tmp_path / "test.mp4"
        video.write_text("fake")
        assert VideoExtractor.validate_format(str(video)) is True

    def test_validate_format_unsupported(self, tmp_path: Path) -> None:
        video = tmp_path / "test.xyz"
        video.write_text("fake")
        assert VideoExtractor.validate_format(str(video)) is False

    def test_validate_format_not_exists(self) -> None:
        assert VideoExtractor.validate_format("/nonexistent/video.mp4") is False

    @patch("classroom_analyzer.extractors.video.subprocess.run")
    def test_extract_info(self, mock_run: MagicMock, tmp_path: Path) -> None:
        video = tmp_path / "test.mp4"
        video.write_text("fake")

        mock_run.return_value = MagicMock(
            returncode=0,
            stdout=json.dumps({
                "format": {
                    "duration": "3120.5",
                    "size": "823000000",
                    "format_name": "mov,mp4,m4a,3gp,3g2,mj2",
                },
                "streams": [
                    {
                        "codec_type": "video",
                        "width": 1920,
                        "height": 1080,
                    },
                ],
            }),
        )

        extractor = self._make_extractor()
        info = extractor.extract_info(str(video))
        assert isinstance(info, VideoInfo)
        assert info.duration == 3120.5
        assert info.resolution == (1920, 1080)
        assert info.file_size == 823000000

    @patch("classroom_analyzer.extractors.video.subprocess.run")
    def test_extract_info_no_video_stream(self, mock_run: MagicMock, tmp_path: Path) -> None:
        video = tmp_path / "test.mp4"
        video.write_text("fake")

        mock_run.return_value = MagicMock(
            returncode=0,
            stdout=json.dumps({
                "format": {"duration": "60.0", "size": "1000", "format_name": "mp4"},
                "streams": [],
            }),
        )

        extractor = self._make_extractor()
        info = extractor.extract_info(str(video))
        assert info.resolution == (0, 0)

    @patch("classroom_analyzer.extractors.video.subprocess.run")
    def test_extract_info_ffprobe_not_found(self, mock_run: MagicMock, tmp_path: Path) -> None:
        video = tmp_path / "test.mp4"
        video.write_text("fake")

        mock_run.side_effect = FileNotFoundError("ffprobe not found")

        extractor = self._make_extractor()
        with pytest.raises(VideoExtractorError, match="未找到ffprobe"):
            extractor.extract_info(str(video))

    @patch("classroom_analyzer.extractors.video.subprocess.run")
    def test_extract_info_ffprobe_failure(self, mock_run: MagicMock, tmp_path: Path) -> None:
        video = tmp_path / "test.mp4"
        video.write_text("fake")

        mock_run.return_value = MagicMock(
            returncode=1,
            stderr="ffprobe error",
        )

        extractor = self._make_extractor()
        with pytest.raises(VideoExtractorError, match="ffprobe执行失败"):
            extractor.extract_info(str(video))

    def test_extract_info_file_not_exists(self) -> None:
        extractor = self._make_extractor()
        with pytest.raises(VideoExtractorError, match="视频文件不存在"):
            extractor.extract_info("/nonexistent.mp4")


class TestAudioExtractor:
    """AudioExtractor 测试。"""

    @patch("classroom_analyzer.extractors.audio.subprocess.run")
    def test_extract_success(self, mock_run: MagicMock, tmp_path: Path) -> None:
        video = tmp_path / "test.mp4"
        video.write_text("fake")
        output = tmp_path / "audio.wav"

        # 第一次调用：ffmpeg提取音频
        # 第二次调用：ffprobe获取时长
        mock_run.side_effect = [
            MagicMock(returncode=0),  # ffmpeg成功
            MagicMock(  # ffprobe成功
                returncode=0,
                stdout=json.dumps({"format": {"duration": "60.5"}}),
            ),
        ]

        # 模拟输出文件存在
        with patch.object(Path, "exists", return_value=True):
            extractor = AudioExtractor(ffmpeg_path="ffmpeg")
            result = extractor.extract(str(video), str(output))

        assert isinstance(result, AudioInfo)
        assert result.sample_rate == 16000
        assert result.channels == 1
        assert result.format == "wav"

    @patch("classroom_analyzer.extractors.audio.subprocess.run")
    def test_extract_ffmpeg_not_found(self, mock_run: MagicMock, tmp_path: Path) -> None:
        video = tmp_path / "test.mp4"
        video.write_text("fake")
        output = tmp_path / "audio.wav"

        mock_run.side_effect = FileNotFoundError("ffmpeg not found")

        extractor = AudioExtractor(ffmpeg_path="nonexistent_ffmpeg")
        with pytest.raises(AudioExtractorError, match="未找到FFmpeg"):
            extractor.extract(str(video), str(output))

    def test_extract_video_not_exists(self, tmp_path: Path) -> None:
        extractor = AudioExtractor(ffmpeg_path="ffmpeg")
        with pytest.raises(AudioExtractorError, match="视频文件不存在"):
            extractor.extract("/nonexistent.mp4", str(tmp_path / "audio.wav"))

    def test_build_extract_cmd(self) -> None:
        extractor = AudioExtractor(ffmpeg_path="/usr/bin/ffmpeg")
        cmd = extractor._build_extract_cmd("video.mp4", "audio.wav", 16000)
        assert cmd[0] == "/usr/bin/ffmpeg"
        assert "-vn" in cmd
        assert "pcm_s16le" in cmd
        assert "16000" in cmd
        assert "-ac" in cmd
        assert "1" in cmd


class TestFrameExtractor:
    """FrameExtractor 测试。"""

    @patch("classroom_analyzer.extractors.frames.subprocess.run")
    def test_extract_at_timestamp(self, mock_run: MagicMock, tmp_path: Path) -> None:
        mock_run.return_value = MagicMock(returncode=0)

        # 模拟输出文件存在
        with patch.object(Path, "exists", return_value=True):
            extractor = FrameExtractor(ffmpeg_path="ffmpeg")
            result = extractor.extract_at_timestamp(
                video_path="video.mp4",
                timestamp=120.0,
                output_dir=str(tmp_path),
                frame_name="frame_test_120",
            )

        assert result.endswith("frame_test_120.jpg")

    @patch("classroom_analyzer.extractors.frames.subprocess.run")
    def test_extract_at_timestamp_failure(self, mock_run: MagicMock, tmp_path: Path) -> None:
        mock_run.return_value = MagicMock(returncode=1, stderr="error")

        extractor = FrameExtractor(ffmpeg_path="ffmpeg")
        result = extractor.extract_at_timestamp(
            video_path="video.mp4",
            timestamp=120.0,
            output_dir=str(tmp_path),
            frame_name="frame_test",
        )
        # 截帧失败返回空字符串，不抛异常
        assert result == ""

    @patch("classroom_analyzer.extractors.frames.subprocess.run")
    def test_extract_for_events(self, mock_run: MagicMock, tmp_path: Path) -> None:
        mock_run.return_value = MagicMock(returncode=0)

        events = [
            TeachingEvent(
                event_type="互动指令",
                subtype="提问",
                start_time=120.0,
                end_time=135.0,
                description="提问",
                confidence=0.9,
            ),
            TeachingEvent(
                event_type="知识节点",
                subtype="概念引入",
                start_time=200.0,
                end_time=220.0,
                description="引入概念",
                confidence=0.85,
            ),
        ]

        with patch.object(Path, "exists", return_value=True):
            extractor = FrameExtractor(ffmpeg_path="ffmpeg")
            keyframes = extractor.extract_for_events(
                video_path="video.mp4",
                events=events,
                output_dir=str(tmp_path),
            )

        assert len(keyframes) == 2
        assert isinstance(keyframes[0], KeyFrame)

    def test_build_frame_cmd(self) -> None:
        extractor = FrameExtractor(ffmpeg_path="ffmpeg")
        cmd = extractor._build_frame_cmd("video.mp4", 120.5, "frame.jpg")
        assert cmd[0] == "ffmpeg"
        assert "-ss" in cmd
        assert "120.500" in cmd
        assert "-frames:v" in cmd
        assert "1" in cmd
