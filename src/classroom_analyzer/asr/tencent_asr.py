"""腾讯云ASR客户端 — 录音文件识别（含COS上传中转）"""

import json
import re
import shutil
import subprocess
import time
import uuid
from pathlib import Path
from typing import Callable

from loguru import logger
from qcloud_cos import CosConfig, CosS3Client
from tencentcloud.common import credential
from tencentcloud.common.profile.client_profile import ClientProfile
from tencentcloud.common.profile.http_profile import HttpProfile
from tencentcloud.asr.v20190614 import asr_client, models as asr_models

from classroom_analyzer.config import ClassroomAnalyzerError
from classroom_analyzer.models import Transcript, TranscriptSegment


class ASRError(ClassroomAnalyzerError):
    """ASR识别异常。"""
    pass


class TencentASRClient:
    """腾讯云ASR客户端：支持长音频录音文件识别和说话人分离。

    流程：本地WAV → 上传COS → 获取URL → CreateRecTask → 轮询结果 → 解析 → 清理COS
    """

    # ASR任务状态码
    STATUS_SUCCESS = 2
    STATUS_RUNNING = 1
    STATUS_FAILED = 3

    def __init__(
        self,
        secret_id: str,
        secret_key: str,
        cos_config: dict,
        asr_config: dict | None = None,
    ) -> None:
        """初始化ASR客户端。

        Args:
            secret_id: 腾讯云SecretId
            secret_key: 腾讯云SecretKey
            cos_config: COS配置 {bucket, region, path_prefix}
            asr_config: ASR配置 {engine, language, enable_diarization, speaker_number}
        """
        self.secret_id = secret_id
        self.secret_key = secret_key
        self.cos_config = cos_config
        self.asr_config = asr_config or {}

        # 初始化COS客户端（绕过系统代理，否则翻墙/VPN软件会拦截请求导致 ProxyError）
        cos_region = cos_config.get("region", "ap-guangzhou")
        self._cos_region = cos_region
        self._network_timeout_seconds = int(cos_config.get("timeout_seconds", 60))
        cos_config_obj = CosConfig(
            Region=cos_region,
            SecretId=secret_id,
            SecretKey=secret_key,
            Timeout=self._network_timeout_seconds,
        )
        # 显式禁用代理：翻墙软件的 HTTPS_PROXY 环境变量会让 qcloud_cos 也走代理
        # 走 127.0.0.1:7890 → 代理未开 → ProxyError
        import os as _os
        _saved_proxies = {}
        for _key in ("HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy"):
            _val = _os.environ.pop(_key, None)
            if _val is not None:
                _saved_proxies[_key] = _val
        try:
            self._cos_client = CosS3Client(cos_config_obj)
        finally:
            _os.environ.update(_saved_proxies)
        self._cos_bucket = cos_config.get("bucket", "")
        self._cos_path_prefix = cos_config.get("path_prefix", "asr-upload/")
        self._cos_upload_part_size_mb = int(cos_config.get("upload_part_size_mb", 8))
        self._cos_upload_threads = int(cos_config.get("upload_threads", 2))
        self._cos_upload_max_retries = int(cos_config.get("upload_max_retries", 4))
        self._cos_upload_retry_base_seconds = float(cos_config.get("upload_retry_base_seconds", 2))
        self._cos_direct_upload_max_mb = int(cos_config.get("direct_upload_max_mb", 512))

        # 初始化ASR客户端（同样绕过系统代理）
        cred = credential.Credential(secret_id, secret_key)
        http_profile = HttpProfile(endpoint="asr.tencentcloudapi.com", reqTimeout=self._network_timeout_seconds)
        client_profile = ClientProfile(httpProfile=http_profile)
        import os as _os2
        _saved_proxies2 = {}
        for _key in ("HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy"):
            _val = _os2.environ.pop(_key, None)
            if _val is not None:
                _saved_proxies2[_key] = _val
        try:
            self._asr_client = asr_client.AsrClient(cred, "", client_profile)
        finally:
            _os2.environ.update(_saved_proxies2)

    def recognize(
        self,
        audio_path: str,
        enable_diarization: bool = True,
        progress_callback: Callable[[float, str], None] | None = None,
    ) -> Transcript:
        """识别音频文件，返回转录结果。

        Args:
            audio_path: 音频文件路径（WAV格式）
            enable_diarization: 是否启用说话人分离

        Returns:
            Transcript: 转录结果

        Raises:
            ASRError: 识别失败时抛出
        """
        audio = Path(audio_path)
        if not audio.exists():
            raise ASRError(f"音频文件不存在：{audio_path}")

        # 获取音频时长（用于降级路径的时间戳分发）
        audio_duration = self._get_audio_duration(audio_path)

        # 步骤1：上传COS
        logger.info(f"上传音频到COS：{audio_path}")
        if progress_callback:
            progress_callback(2.0, "腾讯云ASR转文字：正在上传音频到 COS。")
        audio_url = self._upload_to_cos(audio_path, progress_callback=progress_callback)

        try:
            # 步骤2：创建识别任务
            logger.info(f"创建ASR识别任务：{audio_url}")
            if progress_callback:
                progress_callback(2.0, "腾讯云ASR转文字：音频已上传，正在创建识别任务。")
            task_id = self._create_task(audio_url, enable_diarization)

            # 步骤3：轮询任务状态（超时按音频时长动态计算：每10分钟给5分钟，最少15分钟）
            asr_timeout = max(900, int(audio_duration / 60 * 5) + 60)
            logger.info(f"轮询ASR任务状态：task_id={task_id}，超时={asr_timeout}秒（音频{audio_duration:.0f}秒）")
            raw_result = self._poll_task(task_id, timeout=asr_timeout, progress_callback=progress_callback)

            # 步骤4：解析结果（传入音频时长用于降级时间戳）
            logger.info("解析ASR识别结果")
            transcript = self._parse_result(raw_result, audio_duration=audio_duration)

            logger.info(
                f"ASR识别完成：{len(transcript.segments)} 段，"
                f"{transcript.speaker_count} 位说话人，"
                f"{transcript.duration:.1f} 秒"
            )
            return transcript

        finally:
            # 步骤5：清理COS临时文件
            self._cleanup_cos_for_url(audio_url)

    def _upload_to_cos(
        self,
        local_path: str,
        progress_callback: Callable[[float, str], None] | None = None,
    ) -> str:
        """上传文件到COS，返回可访问的URL。

        Args:
            local_path: 本地文件路径

        Returns:
            str: COS上的文件URL

        Raises:
            ASRError: 上传失败时抛出
        """
        # 生成唯一对象键
        file_ext = Path(local_path).suffix
        object_key = f"{self._cos_path_prefix}{uuid.uuid4().hex}{file_ext}"

        upload_errors: list[str] = []
        last_progress_at = 0.0

        def _upload_progress(consumed: int, total: int) -> None:
            nonlocal last_progress_at
            if not progress_callback or total <= 0:
                return
            now = time.monotonic()
            if now - last_progress_at < 5 and consumed < total:
                return
            last_progress_at = now
            percent = max(0, min(100, int(consumed * 100 / total)))
            progress_callback(2.0, f"腾讯云ASR转文字：音频上传 COS 中 {percent}%。")

        for attempt in range(1, self._cos_upload_max_retries + 1):
            try:
                if progress_callback:
                    progress_callback(2.0, f"腾讯云ASR转文字：正在上传音频到 COS（第 {attempt} 次）。")
                self._cos_client.upload_file(
                    Bucket=self._cos_bucket,
                    Key=object_key,
                    LocalFilePath=local_path,
                    PartSize=self._cos_upload_part_size_mb,
                    MAXThread=self._cos_upload_threads,
                    progress_callback=_upload_progress,
                )
                break
            except Exception as e:
                error_text = str(e)
                upload_errors.append(error_text)
                logger.warning(
                    "COS分片上传失败，第 {}/{} 次：{}",
                    attempt,
                    self._cos_upload_max_retries,
                    error_text,
                )
                if attempt < self._cos_upload_max_retries:
                    if progress_callback:
                        progress_callback(2.0, f"腾讯云ASR转文字：COS 上传失败，准备第 {attempt + 1} 次重试。")
                    time.sleep(self._cos_upload_retry_base_seconds * (2 ** (attempt - 1)))
        else:
            file_size_mb = Path(local_path).stat().st_size / 1024 / 1024
            if file_size_mb <= self._cos_direct_upload_max_mb:
                try:
                    logger.info("COS分片上传连续失败，尝试单对象直传：{:.1f} MB", file_size_mb)
                    if progress_callback:
                        progress_callback(2.0, "腾讯云ASR转文字：分片上传失败，正在尝试直接上传音频。")
                    with open(local_path, "rb") as f:
                        self._cos_client.put_object(
                            Bucket=self._cos_bucket,
                            Key=object_key,
                            Body=f,
                        )
                except Exception as direct_error:
                    upload_errors.append(str(direct_error))
                    raise ASRError(
                        "COS上传失败：音频上传到云存储失败，可能是网络波动、文件较大或COS服务临时异常。"
                        "系统已多次重试仍未成功，请稍后在任务页点击“重试分析”。"
                        f" 原始错误：{upload_errors[-1]}"
                    ) from direct_error
            else:
                raise ASRError(
                    "COS上传失败：音频上传到云存储失败，可能是网络波动、文件较大或COS服务临时异常。"
                    "系统已多次重试仍未成功，请稍后在任务页点击“重试分析”。"
                    f" 原始错误：{upload_errors[-1] if upload_errors else 'unknown'}"
                )

        # 生成预签名URL（有效期2小时，给ASR足够时间处理）
        url = self._cos_client.get_presigned_download_url(
            Bucket=self._cos_bucket,
            Key=object_key,
            Expired=7200,  # 2小时
        )
        if not isinstance(url, str):
            url = f"https://{self._cos_bucket}.cos.{self._cos_region}.myqcloud.com/{object_key}"

        logger.debug(f"COS上传成功：{object_key}")
        return url

    def _create_task(self, audio_url: str, enable_diarization: bool) -> int:
        """创建ASR识别任务。

        Args:
            audio_url: 音频文件URL
            enable_diarization: 是否启用说话人分离

        Returns:
            int: 任务ID

        Raises:
            ASRError: 创建任务失败时抛出
        """
        req = asr_models.CreateRecTaskRequest()
        # 使用 16k_zh_en 大模型版引擎（支持说话人分离 + 角色识别）
        # 注意：16k_zh 基础引擎不支持指定说话人数量(SpeakerNumber>0 被忽略)
        req.EngineModelType = self.asr_config.get("engine", "16k_zh_en")
        req.ChannelNum = 1
        req.SourceType = 0  # URL方式
        req.Url = audio_url
        # ResTextFormat=3 返回词粒度结果+标点分段+ResultDetail（含 SpeakerId）
        # 注意：ResTextFormat=0 不返回 ResultDetail
        req.ResTextFormat = 3

        if enable_diarization:
            req.SpeakerDiarization = 1
            # 设为0=自动分离（最多20人），16k引擎不支持指定人数
            # 课堂场景通常2-8人，自动模式足够
            req.SpeakerNumber = self.asr_config.get("speaker_number", 0)

        try:
            resp = self._asr_client.CreateRecTask(req)
            task_id = resp.Data.TaskId
            logger.debug(f"ASR任务创建成功：task_id={task_id}")
            return task_id
        except Exception as e:
            raise ASRError(f"创建ASR识别任务失败：{e}")

    def _poll_task(
        self,
        task_id: int,
        timeout: int = 300,
        progress_callback: Callable[[float, str], None] | None = None,
    ) -> dict:
        """轮询ASR任务状态直到完成。

        Args:
            task_id: 任务ID
            timeout: 超时时间（秒），默认300秒

        Returns:
            dict: 识别结果数据

        Raises:
            ASRError: 轮询超时或任务失败时抛出
        """
        start_time = time.time()
        poll_interval = 10  # 轮询间隔10秒

        while True:
            elapsed = time.time() - start_time
            if elapsed > timeout:
                raise ASRError(f"ASR识别超时（{timeout}秒）")

            req = asr_models.DescribeTaskStatusRequest()
            req.TaskId = task_id

            try:
                resp = self._asr_client.DescribeTaskStatus(req)
            except Exception as e:
                raise ASRError(f"查询ASR任务状态失败：{e}")

            status = resp.Data.Status

            if status == self.STATUS_SUCCESS:
                logger.debug(f"ASR任务完成：task_id={task_id}")

                # 解析 Result（纯文本格式，不含说话人信息）
                result_str = resp.Data.Result or ""
                result_data = None
                if result_str:
                    try:
                        result_data = json.loads(result_str)
                    except json.JSONDecodeError:
                        result_data = {"text": result_str}

                # 解析 ResultDetail（结构化数据，含 SpeakerId/StartMs/EndMs）
                # 这是说话人分离的关键数据源
                result_detail_raw = resp.Data.ResultDetail
                result_detail_data = None
                if result_detail_raw:
                    if isinstance(result_detail_raw, str):
                        try:
                            result_detail_data = json.loads(result_detail_raw)
                        except json.JSONDecodeError:
                            logger.warning("ResultDetail JSON解析失败")
                    elif isinstance(result_detail_raw, list):
                        result_detail_data = result_detail_raw
                    else:
                        # SDK 可能返回已反序列化的对象
                        result_detail_data = result_detail_raw

                logger.info(
                    f"ASR原始结果：Result={type(result_data).__name__}, "
                    f"ResultDetail={type(result_detail_raw).__name__} "
                    f"({len(result_detail_data) if result_detail_data else 0} 条)"
                )

                # 调试：打印 Result 和 ResultDetail 的前200字符（排查格式问题）
                if result_str:
                    logger.debug(f"Result 原文前200字符：{result_str[:200]}")
                if result_detail_raw:
                    if isinstance(result_detail_raw, str):
                        logger.debug(f"ResultDetail 原文前500字符：{result_detail_raw[:500]}")
                    elif isinstance(result_detail_raw, list) and len(result_detail_raw) > 0:
                        first = result_detail_raw[0]
                        if hasattr(first, '__dict__'):
                            logger.debug(f"ResultDetail[0] 属性：{vars(first)}")
                        elif isinstance(first, dict):
                            logger.debug(f"ResultDetail[0] 键：{list(first.keys())}")

                return {
                    "result": result_data,
                    "result_detail": result_detail_data,
                }

            elif status == self.STATUS_FAILED:
                error_msg = resp.Data.ErrorMsg if hasattr(resp.Data, "ErrorMsg") else "未知错误"
                raise ASRError(f"ASR识别失败：{error_msg}")

            elif status == self.STATUS_RUNNING:
                if progress_callback:
                    waited_minutes = int(elapsed // 60)
                    timeout_minutes = max(1, int(timeout // 60))
                    progress_callback(
                        2.0,
                        f"腾讯云ASR转文字：已等待 {waited_minutes} 分钟，最长等待约 {timeout_minutes} 分钟；任务仍在轮询中。",
                    )
                logger.debug(f"ASR任务运行中，{poll_interval}秒后重试（已等待 {elapsed:.0f}秒）")
                time.sleep(poll_interval)

            else:
                if progress_callback:
                    progress_callback(2.0, f"腾讯云ASR转文字：识别任务状态 {status}，继续轮询。")
                logger.warning(f"ASR任务未知状态：{status}，继续等待")
                time.sleep(poll_interval)

    def _parse_result(self, raw_result: dict | list, audio_duration: float = 0.0) -> Transcript:
        """解析ASR识别结果。

        优先使用 ResultDetail（含 SpeakerId/StartMs/EndMs/FinalSentence），
        降级使用 Result（纯文本或简单 JSON）。

        Args:
            raw_result: ASR返回的原始结果，格式：{"result": ..., "result_detail": ...}
            audio_duration: 音频时长（秒），用于降级路径的时间戳分发

        Returns:
            Transcript: 转录结果
        """
        segments: list[TranscriptSegment] = []
        speakers: set[str] = set()
        max_end = 0.0

        normalized_result: dict = {"result": raw_result} if isinstance(raw_result, list) else raw_result

        # ===== 优先路径：ResultDetail（含说话人信息） =====
        result_detail = normalized_result.get("result_detail")
        if result_detail and isinstance(result_detail, list) and len(result_detail) > 0:
            logger.info(f"使用 ResultDetail 解析，共 {len(result_detail)} 条")
            for item in result_detail:
                text, start_ms, end_ms, speaker_id, role_name = (
                    self._extract_sentence_detail(item)
                )
                if not text or not text.strip():
                    continue

                start_time = start_ms / 1000.0
                end_time = end_ms / 1000.0

                # 生成可读的说话人名称
                speaker = self._speaker_id_to_name(speaker_id, role_name)

                segments.append(TranscriptSegment(
                    start_time=start_time,
                    end_time=end_time,
                    text=text.strip(),
                    speaker=speaker,
                ))
                speakers.add(speaker)
                max_end = max(max_end, end_time)

            if segments:
                return Transcript(
                    segments=segments,
                    duration=max_end,
                    speaker_count=len(speakers) if speakers else 1,
                )
            else:
                logger.warning("ResultDetail 解析后无有效片段，尝试 Result 降级")

        # ===== 降级路径1：Result（JSON list 或纯文本） =====
        result_data = normalized_result.get("result", normalized_result)
        result_list = result_data

        # 如果有外层包装
        if isinstance(result_data, dict) and "Result" in result_data:
            result_list = result_data["Result"]

        if isinstance(result_list, list):
            for item in result_list:
                if isinstance(item, str):
                    continue
                # 兼容旧格式（错误字段名）
                start_ms = item.get("StartTime", item.get("StartMs", 0))
                end_ms = item.get("EndTime", item.get("EndMs", 0))
                text = item.get("Text", item.get("FinalSentence", ""))
                speaker = item.get("Speaker", f"speaker_{item.get('SpeakerId', 'unknown')}")

                start_time = start_ms / 1000.0
                end_time = end_ms / 1000.0

                if text.strip():
                    segments.append(TranscriptSegment(
                        start_time=start_time,
                        end_time=end_time,
                        text=text.strip(),
                        speaker=speaker,
                    ))
                    speakers.add(speaker)
                    max_end = max(max_end, end_time)

            if segments:
                return Transcript(
                    segments=segments,
                    duration=max_end,
                    speaker_count=len(speakers) if speakers else 1,
                )

        # ===== 降级路径2：纯文本 → 按标点断句 + 时间戳均匀分布 =====
        logger.warning("ASR 结果无结构化数据，使用标点断句降级路径")
        text = ""
        if isinstance(result_data, dict):
            text = result_data.get("text", "")
        if not text and isinstance(normalized_result.get("result"), dict):
            text = normalized_result["result"].get("text", "")
        if not text:
            # 尝试从 Result 纯文本中提取
            result_str = normalized_result.get("result", "")
            if isinstance(result_str, str) and result_str:
                text = result_str

        if text:
            sentence_list = self._split_text_by_punctuation(text)

            duration = audio_duration if audio_duration > 0 else 60.0
            num_sentences = len(sentence_list) or 1
            if not sentence_list:
                sentence_list = [text]

            for i, sent in enumerate(sentence_list):
                seg_duration = duration / num_sentences
                start_time = i * seg_duration
                end_time = (i + 1) * seg_duration
                segments.append(TranscriptSegment(
                    start_time=start_time,
                    end_time=end_time,
                    text=sent,
                    speaker="speaker_unknown",
                ))
                speakers.add("speaker_unknown")
            max_end = duration
        else:
            logger.warning("ASR降级路径：未找到文本内容")
            max_end = audio_duration if audio_duration > 0 else 0.0

        return Transcript(
            segments=segments,
            duration=max_end,
            speaker_count=len(speakers) if speakers else 1,
        )

    @staticmethod
    def _extract_sentence_detail(item) -> tuple[str, int, int, int | None, str | None]:
        """从 ResultDetail 的一条记录中提取字段。

        兼容 SentenceDetail 对象和 dict 两种格式。

        Returns:
            (text, start_ms, end_ms, speaker_id, role_name)
        """
        if hasattr(item, "FinalSentence"):
            # SentenceDetail 对象格式
            text = item.FinalSentence or ""
            start_ms = item.StartMs or 0
            end_ms = item.EndMs or 0
            speaker_id = item.SpeakerId
            role_name = getattr(item, "SpeakerRoleName", None)
        elif isinstance(item, dict):
            # dict 格式
            text = item.get("FinalSentence", item.get("Text", ""))
            start_ms = item.get("StartMs", item.get("StartTime", 0))
            end_ms = item.get("EndMs", item.get("EndTime", 0))
            speaker_id = item.get("SpeakerId")
            role_name = item.get("SpeakerRoleName")
            if role_name is None and "Speaker" in item:
                role_name = item.get("Speaker")
        else:
            text, start_ms, end_ms, speaker_id, role_name = "", 0, 0, None, None

        return text, start_ms, end_ms, speaker_id, role_name

    @staticmethod
    def _speaker_id_to_name(speaker_id: int | None, role_name: str | None = None) -> str:
        """将说话人 ID 映射为可读名称。

        课堂场景映射规则：
        - 有 role_name 时直接使用（角色分离模式返回的名称如 "teacher"/"student"）
        - speaker_id=0 通常为主说话人（教师）
        - speaker_id>=1 通常为其他说话人（学生）
        """
        if role_name:
            return role_name
        if speaker_id is None:
            return "speaker_unknown"
        if speaker_id == 0:
            return "teacher"
        return f"student_{speaker_id}"

    @staticmethod
    def _split_text_by_punctuation(text: str) -> list[str]:
        """按中文标点断句，保留标点符号在句尾。"""
        sentences = re.split(r"([。！？；])", text)
        sentence_list: list[str] = []
        current = ""
        for part in sentences:
            if part in ("。", "！", "？", "；"):
                current += part
                if current.strip():
                    sentence_list.append(current.strip())
                current = ""
            else:
                current += part
        if current.strip():
            sentence_list.append(current.strip())

        # 如果没有按标点分开，先按换行分，再按逗号分
        if len(sentence_list) <= 1:
            sentence_list = [s.strip() for s in text.splitlines() if s.strip()]
        if len(sentence_list) <= 1:
            sentence_list = [s.strip() for s in text.split("，") if s.strip()]
        if len(sentence_list) <= 1:
            sentence_list = [s.strip() for s in text.split(",") if s.strip()]

        return sentence_list

    @staticmethod
    def _get_audio_duration(audio_path: str) -> float:
        """使用 ffprobe 获取音频时长（秒）。

        Args:
            audio_path: 音频文件路径

        Returns:
            float: 时长（秒），获取失败返回 0.0
        """
        import subprocess
        ffprobe = shutil.which("ffprobe")
        if not ffprobe:
            # 尝试项目本地 tools/ 目录
            # 向上查找项目根目录
            current = Path(__file__).resolve()
            for parent in [current.parent, *current.parents]:
                for tools_bin in [
                    parent / "tools" / "ffmpeg-8.1.1-essentials_build" / "bin" / "ffprobe.exe",
                    parent / "tools" / "ffmpeg" / "bin" / "ffprobe.exe",
                ]:
                    if tools_bin.exists():
                        ffprobe = str(tools_bin)
                        break
                if ffprobe:
                    break

        if not ffprobe:
            logger.warning("未找到 ffprobe，无法获取音频时长")
            return 0.0

        try:
            result = subprocess.run(
                [
                    ffprobe, "-v", "quiet",
                    "-print_format", "json",
                    "-show_format",
                    audio_path,
                ],
                capture_output=True, text=True, timeout=10,
            )
            if result.returncode == 0 and result.stdout.strip():
                data = json.loads(result.stdout)
                duration = float(data.get("format", {}).get("duration", 0))
                logger.debug(f"ffprobe 获取音频时长：{duration:.1f}s ({audio_path})")
                return duration
        except Exception as e:
            logger.warning(f"ffprobe 获取时长失败：{e}")

        return 0.0

    def _cleanup_cos_for_url(self, url: str) -> None:
        """根据URL清理COS临时文件。

        Args:
            url: COS文件URL
        """
        try:
            # 从URL提取object_key
            # URL格式: https://{bucket}.cos.{region}.myqcloud.com/{object_key}
            parts = url.split(".myqcloud.com/")
            if len(parts) == 2:
                object_key = parts[1]
                self._cleanup_cos(object_key)
        except Exception as e:
            logger.warning(f"清理COS临时文件失败：{e}")

    def _cleanup_cos(self, object_key: str) -> None:
        """删除COS上的临时文件。

        Args:
            object_key: COS对象键
        """
        try:
            self._cos_client.delete_object(
                Bucket=self._cos_bucket,
                Key=object_key,
            )
            logger.debug(f"COS临时文件已清理：{object_key}")
        except Exception as e:
            logger.warning(f"清理COS临时文件失败：{e}")
