"""ASR客户端测试 — mock腾讯云API"""

import json
from unittest.mock import MagicMock, patch, PropertyMock

import pytest

from classroom_analyzer.asr.tencent_asr import TencentASRClient, ASRError
from classroom_analyzer.models import Transcript, TranscriptSegment


@pytest.fixture
def asr_client() -> TencentASRClient:
    """创建mock的ASR客户端。"""
    with patch("classroom_analyzer.asr.tencent_asr.CosS3Client"), \
         patch("classroom_analyzer.asr.tencent_asr.asr_client.AsrClient"):
        client = TencentASRClient(
            secret_id="test_id",
            secret_key="test_key",
            cos_config={
                "bucket": "test-bucket",
                "region": "ap-guangzhou",
                "path_prefix": "asr-upload/",
            },
            asr_config={
                "engine": "16k_zh",
                "enable_diarization": True,
                "speaker_number": 0,
            },
        )
        return client


class TestTencentASRClient:
    """TencentASRClient 测试。"""

    def test_init(self, asr_client: TencentASRClient) -> None:
        assert asr_client.secret_id == "test_id"
        assert asr_client.secret_key == "test_key"
        assert asr_client.cos_config["bucket"] == "test-bucket"

    @patch("classroom_analyzer.asr.tencent_asr.CosS3Client")
    @patch("classroom_analyzer.asr.tencent_asr.asr_client.AsrClient")
    def test_upload_to_cos(self, mock_asr: MagicMock, mock_cos: MagicMock) -> None:
        client = TencentASRClient(
            secret_id="test_id",
            secret_key="test_key",
            cos_config={
                "bucket": "test-bucket",
                "region": "ap-guangzhou",
                "path_prefix": "asr-upload/",
            },
        )

        mock_cos_instance = mock_cos.return_value
        mock_cos_instance.upload_file.return_value = None

        # 需要一个真实临时文件
        import tempfile
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
            f.write(b"fake audio")
            audio_path = f.name

        try:
            url = client._upload_to_cos(audio_path)
            assert "test-bucket" in url
            assert "cos.ap-guangzhou.myqcloud.com" in url
            assert "asr-upload/" in url
            mock_cos_instance.upload_file.assert_called_once()
        finally:
            Path(audio_path).unlink(missing_ok=True)

    @patch("classroom_analyzer.asr.tencent_asr.CosS3Client")
    @patch("classroom_analyzer.asr.tencent_asr.asr_client.AsrClient")
    def test_upload_to_cos_retries_transient_failure(self, mock_asr: MagicMock, mock_cos: MagicMock) -> None:
        client = TencentASRClient(
            secret_id="test_id",
            secret_key="test_key",
            cos_config={
                "bucket": "test-bucket",
                "region": "ap-guangzhou",
                "path_prefix": "asr-upload/",
                "upload_max_retries": 3,
                "upload_retry_base_seconds": 0,
            },
        )

        mock_cos_instance = mock_cos.return_value
        mock_cos_instance.upload_file.side_effect = [Exception("part failed"), None]

        import tempfile
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
            f.write(b"fake audio")
            audio_path = f.name

        try:
            url = client._upload_to_cos(audio_path)
            assert "test-bucket" in url
            assert mock_cos_instance.upload_file.call_count == 2
            mock_cos_instance.put_object.assert_not_called()
        finally:
            Path(audio_path).unlink(missing_ok=True)

    @patch("classroom_analyzer.asr.tencent_asr.CosS3Client")
    @patch("classroom_analyzer.asr.tencent_asr.asr_client.AsrClient")
    def test_upload_to_cos_falls_back_to_put_object_for_small_file(self, mock_asr: MagicMock, mock_cos: MagicMock) -> None:
        client = TencentASRClient(
            secret_id="test_id",
            secret_key="test_key",
            cos_config={
                "bucket": "test-bucket",
                "region": "ap-guangzhou",
                "path_prefix": "asr-upload/",
                "upload_max_retries": 2,
                "upload_retry_base_seconds": 0,
                "direct_upload_max_mb": 64,
            },
        )

        mock_cos_instance = mock_cos.return_value
        mock_cos_instance.upload_file.side_effect = Exception("some upload_part fail after max_retry")
        mock_cos_instance.put_object.return_value = None

        import tempfile
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
            f.write(b"fake audio")
            audio_path = f.name

        try:
            url = client._upload_to_cos(audio_path)
            assert "test-bucket" in url
            assert mock_cos_instance.upload_file.call_count == 2
            mock_cos_instance.put_object.assert_called_once()
        finally:
            Path(audio_path).unlink(missing_ok=True)

    @patch("classroom_analyzer.asr.tencent_asr.CosS3Client")
    @patch("classroom_analyzer.asr.tencent_asr.asr_client.AsrClient")
    def test_upload_to_cos_reports_actionable_error_after_retries(self, mock_asr: MagicMock, mock_cos: MagicMock) -> None:
        client = TencentASRClient(
            secret_id="test_id",
            secret_key="test_key",
            cos_config={
                "bucket": "test-bucket",
                "region": "ap-guangzhou",
                "path_prefix": "asr-upload/",
                "upload_max_retries": 1,
                "upload_retry_base_seconds": 0,
                "direct_upload_max_mb": 64,
            },
        )

        mock_cos_instance = mock_cos.return_value
        mock_cos_instance.upload_file.side_effect = Exception("some upload_part fail after max_retry")
        mock_cos_instance.put_object.side_effect = Exception("network down")

        import tempfile
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
            f.write(b"fake audio")
            audio_path = f.name

        try:
            with pytest.raises(ASRError, match="重试分析"):
                client._upload_to_cos(audio_path)
        finally:
            Path(audio_path).unlink(missing_ok=True)

    def test_parse_result_with_speakers(self, asr_client: TencentASRClient) -> None:
        raw_result = [
            {"StartTime": 0, "EndTime": 5000, "Text": "同学们好", "Speaker": "teacher"},
            {"StartTime": 5000, "EndTime": 8000, "Text": "老师好", "Speaker": "student_1"},
            {"StartTime": 8000, "EndTime": 20000, "Text": "今天我们学习第三章", "Speaker": "teacher"},
        ]

        transcript = asr_client._parse_result(raw_result)
        assert isinstance(transcript, Transcript)
        assert len(transcript.segments) == 3
        assert transcript.segments[0].start_time == 0.0
        assert transcript.segments[0].end_time == 5.0
        assert transcript.segments[0].speaker == "teacher"
        assert transcript.speaker_count == 2

    def test_parse_result_simple_text(self, asr_client: TencentASRClient) -> None:
        raw_result = {"text": "同学们好\n今天我们学习第三章"}

        transcript = asr_client._parse_result(raw_result)
        assert isinstance(transcript, Transcript)
        assert len(transcript.segments) == 2
        assert transcript.speaker_count == 1

    def test_parse_result_empty(self, asr_client: TencentASRClient) -> None:
        raw_result = {}
        transcript = asr_client._parse_result(raw_result)
        assert len(transcript.segments) == 0
        assert transcript.speaker_count == 1

    def test_parse_result_with_result_key(self, asr_client: TencentASRClient) -> None:
        raw_result = {
            "Result": [
                {"StartTime": 1000, "EndTime": 3000, "Text": "测试文本", "Speaker": "speaker_0"},
            ]
        }

        transcript = asr_client._parse_result(raw_result)
        assert len(transcript.segments) == 1
        assert transcript.segments[0].start_time == 1.0

    @patch("classroom_analyzer.asr.tencent_asr.CosS3Client")
    @patch("classroom_analyzer.asr.tencent_asr.asr_client.AsrClient")
    def test_cleanup_cos(self, mock_asr: MagicMock, mock_cos: MagicMock) -> None:
        client = TencentASRClient(
            secret_id="test_id",
            secret_key="test_key",
            cos_config={
                "bucket": "test-bucket",
                "region": "ap-guangzhou",
                "path_prefix": "asr-upload/",
            },
        )

        mock_cos_instance = mock_cos.return_value
        client._cleanup_cos("asr-upload/test-key")
        mock_cos_instance.delete_object.assert_called_once_with(
            Bucket="test-bucket",
            Key="asr-upload/test-key",
        )

    def test_cleanup_cos_for_url(self, asr_client: TencentASRClient) -> None:
        url = "https://test-bucket.cos.ap-guangzhou.myqcloud.com/asr-upload/abc123.wav"
        # 不应该抛异常
        asr_client._cleanup_cos_for_url(url)

    def test_recognize_file_not_exists(self, asr_client: TencentASRClient) -> None:
        with pytest.raises(ASRError, match="音频文件不存在"):
            asr_client.recognize("/nonexistent.wav")


from pathlib import Path
