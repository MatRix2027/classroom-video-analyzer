"""分析管线编排器"""

import json
import shutil
import time
from pathlib import Path
from typing import Any, Callable, Optional

from loguru import logger

from classroom_analyzer.analysis.chain_builder import build_interaction_chains, format_chains_for_prompt
from classroom_analyzer.analysis.llm_analyzer import LLMAnalyzer
from classroom_analyzer.analysis.prompt_templates import PromptTemplates
from classroom_analyzer.asr.tencent_asr import TencentASRClient
from classroom_analyzer.config import ClassroomAnalyzerError
from classroom_analyzer.extractors.audio import AudioExtractor
from classroom_analyzer.extractors.frames import FrameExtractor
from classroom_analyzer.extractors.video import VideoExtractor
from classroom_analyzer.models import (
    AnalysisResult,
    AppConfig,
    AudioInfo,
    EventTimeline,
    KeyFrame,
    QualityCheckItem,
    QualityReport,
    ScoreCard,
    ScoreDimension,
    TeachingEvent,
    Transcript,
    VideoInfo,
)
from classroom_analyzer.reports.quality_report import QualityReportGenerator
from classroom_analyzer.reports.score_card import ScoreCardGenerator


class PipelineError(ClassroomAnalyzerError):
    """管线执行异常。"""
    pass


class AnalysisPipeline:
    """分析管线编排器：6步骤串行管线，支持断点恢复。"""

    # 管线步骤定义
    STEPS = [
        "读取视频文件",
        "FFmpeg提取音频",
        "腾讯云ASR转文字",
        "LLM语义分析（事件识别）",
        "事件驱动截帧",
        "生成质检报告（含评分）",
    ]

    # 精细步进映射（float step → display message）
    SUBSTEPS = {
        3.0: "LLM语文分析 — 准备分段文本...",
        3.3: "LLM语义分析 — 事件识别中（可能需要几分钟）...",
        3.6: "LLM语义分析 — 合并结果...",
        5.0: "生成报告 — 文本模型评分（1/2）...",
        5.2: "生成报告 — 文本模型评分完成",
        5.4: "生成报告 — 视觉模型评分（2/2）...",
        5.6: "生成报告 — 视觉模型评分完成",
        5.8: "生成报告 — 合并评分结果...",
    }

    def __init__(self, config: AppConfig, force: bool = False) -> None:
        self._config = config
        self._force = force
        self._ffmpeg_path = self._find_ffmpeg()

        # 初始化各模块
        api_keys = config.api_keys
        tencent = api_keys.get("tencent_cloud", {})

        self._video_extractor = VideoExtractor(ffmpeg_path=self._ffmpeg_path)
        self._audio_extractor = AudioExtractor(ffmpeg_path=self._ffmpeg_path)
        self._frame_extractor = FrameExtractor(ffmpeg_path=self._ffmpeg_path)

        self._asr_client = TencentASRClient(
            secret_id=tencent.get("secret_id", ""),
            secret_key=tencent.get("secret_key", ""),
            cos_config=config.cos_config,
            asr_config=config.asr_config,
        )

        # ── 文本分析器（支持 doubao / deepseek 双后端）──
        llm_config = api_keys.get("llm", {})
        prompts_dir = str(Path(__file__).parent.parent.parent / "prompts")
        self._prompt_templates = PromptTemplates(prompts_dir=prompts_dir)

        llm_provider = llm_config.get("provider", "doubao")
        if llm_provider == "deepseek":
            provider_cfg = llm_config.get("deepseek", {})
            llm_model = provider_cfg.get("model", "deepseek-chat")
            llm_base_url = provider_cfg.get("base_url", "https://api.deepseek.com")
            llm_api_key = provider_cfg.get("api_key", "") or llm_config.get("api_key", "")
        else:
            # 默认 doubao（火山方舟）
            provider_cfg = llm_config.get("doubao", {})
            llm_model = provider_cfg.get("model", llm_config.get("model", "doubao-1.5-pro-32k"))
            llm_base_url = provider_cfg.get(
                "base_url",
                llm_config.get("base_url", "https://ark.cn-beijing.volces.com/api/v3"),
            )
            llm_api_key = provider_cfg.get("api_key", "") or llm_config.get("api_key", "")

        if not llm_api_key or "在此粘贴" in llm_api_key or "在这里粘贴" in llm_api_key:
            raise PipelineError(
                f"未配置文本模型 API Key！请在 api_keys.json 的 llm.{llm_provider}.api_key 中填写"
            )
        logger.info(f"文本分析器：{llm_model} (provider={llm_provider})")

        self._llm_analyzer = LLMAnalyzer(
            api_key=llm_api_key,
            model=llm_model,
            base_url=llm_base_url,
            prompt_templates=self._prompt_templates,
            chunk_size=config.analysis_config.get("chunk_size", 2000),
            chunk_overlap=config.analysis_config.get("chunk_overlap", 200),
            level=config.analysis_config.get("level", "QC-v4"),
        )

        # ── 视觉分析器（支持 qwen_vl / doubao_vision 双后端）──
        vision_config = api_keys.get("vision", {})
        vision_provider = vision_config.get("provider", "qwen_vl")
        
        if vision_provider == "doubao_vision":
            doubao_config = vision_config.get("doubao_vision", {})
            vision_model = doubao_config.get("model", "doubao-vision-pro-32k")
            vision_base_url = doubao_config.get("base_url", "https://ark.cn-beijing.volces.com/api/v3")
            vision_api_key = doubao_config.get("api_key", "") or vision_config.get("api_key", "")
        else:
            # 默认 qwen_vl
            qwen_config = vision_config.get("qwen_vl", {})
            vision_model = qwen_config.get("model", "qwen-vl-max")
            vision_base_url = qwen_config.get("base_url", "https://dashscope.aliyuncs.com/compatible-mode/v1")
            vision_api_key = vision_config.get("api_key", "")
        
        if vision_api_key and "在这里粘贴" not in vision_api_key:
            self._vision_analyzer = LLMAnalyzer(
                api_key=vision_api_key,
                model=vision_model,
                base_url=vision_base_url,
                prompt_templates=self._prompt_templates,
                chunk_size=config.analysis_config.get("chunk_size", 2000),
                chunk_overlap=config.analysis_config.get("chunk_overlap", 200),
                level=config.analysis_config.get("level", "QC-v4"),
            )
            logger.info(f"视觉分析器：{vision_model} (provider={vision_provider})")
        else:
            self._vision_analyzer = None
            logger.info("未配置有效的 vision API key，将跳过视觉增强评分（仅使用文本评分）")

        self._quality_report_generator = QualityReportGenerator()
        self._score_card_generator = ScoreCardGenerator()

    def run(
        self,
        video_path: str,
        output_dir: str,
        progress_callback: Optional[Callable[[float, str], None]] = None,
    ) -> AnalysisResult:
        """执行完整分析管线。

        Args:
            video_path: 视频文件路径
            output_dir: 输出目录路径
            progress_callback: 进度回调 (step_number, message)

        Returns:
            AnalysisResult: 完整分析结果
        """
        out = Path(output_dir)
        out.mkdir(parents=True, exist_ok=True)
        keyframes_dir = out / "keyframes"
        keyframes_dir.mkdir(exist_ok=True)

        # 中间文件路径
        audio_path = out / "audio.wav"
        transcript_path = out / "transcript.txt"
        events_path = out / "events.json"

        # 逐步执行管线
        video_info: Optional[VideoInfo] = None
        audio_info: Optional[AudioInfo] = None
        transcript: Optional[Transcript] = None
        event_timeline: Optional[EventTimeline] = None
        keyframes: list[KeyFrame] = []
        quality_report: Optional[QualityReport] = None
        score_card: Optional[ScoreCard] = None

        # [1/6] 读取视频
        if progress_callback:
            progress_callback(0, self.STEPS[0])
        video_info = self._step_read_video(video_path)
        self._last_video_info = video_info  # 保存供截帧步骤使用
        if progress_callback:
            progress_callback(1, f"{self.STEPS[0]} ✓")

        # [2/6] 提取音频（断点恢复）
        if not self._force and audio_path.exists():
            logger.info(f"音频文件已存在，跳过提取：{audio_path}")
            audio_info = AudioInfo(
                file_path=str(audio_path),
                duration=video_info.duration,
                sample_rate=16000,
                channels=1,
                format="wav",
            )
        else:
            if progress_callback:
                progress_callback(1, self.STEPS[1])
            audio_info = self._step_extract_audio(video_path, str(audio_path))
        if progress_callback:
            progress_callback(2, f"{self.STEPS[1]} ✓")

        # [3/6] ASR转写（断点恢复）
        if not self._force and transcript_path.exists():
            logger.info(f"转录文件已存在，跳过ASR：{transcript_path}")
            transcript = self._load_transcript(str(transcript_path))
        else:
            if progress_callback:
                progress_callback(2, self.STEPS[2])
            enable_diarization = self._config.asr_config.get("enable_diarization", True)
            transcript = self._step_asr(audio_info.file_path, enable_diarization=enable_diarization)
            self._save_transcript(transcript, str(transcript_path))
        if progress_callback:
            progress_callback(3, f"{self.STEPS[2]} ✓")

        # [4/6] LLM语义分析（断点恢复）
        if not self._force and events_path.exists():
            logger.info(f"事件文件已存在，跳过LLM分析：{events_path}")
            event_timeline = self._load_events(str(events_path))
        else:
            if progress_callback:
                progress_callback(3.0, self.SUBSTEPS.get(3.0, self.STEPS[3]))
            # 根据班型选择prompt版本
            prompt_version = self._get_prompt_version()
            event_timeline = self._step_llm_analysis(
                transcript, prompt_version=prompt_version, progress_callback=progress_callback
            )
            self._save_events(event_timeline, str(events_path))
        if progress_callback:
            progress_callback(4, f"{self.STEPS[3]} ✓")

        # [5/6] 事件驱动截帧
        if progress_callback:
            progress_callback(4, self.STEPS[4])
        keyframes = self._step_extract_frames(video_path, event_timeline, str(keyframes_dir))
        if progress_callback:
            progress_callback(5, f"{self.STEPS[4]} ✓")

        # [6/6] 生成报告
        if progress_callback:
            progress_callback(5, self.STEPS[5])
        quality_report, score_card = self._step_generate_reports(
            video_info, transcript, event_timeline, str(out),
            progress_callback=progress_callback,
        )
        if progress_callback:
            progress_callback(6, f"{self.STEPS[5]} ✓")

        return AnalysisResult(
            video_info=video_info,
            audio_info=audio_info,
            transcript=transcript,
            event_timeline=event_timeline,
            keyframes=keyframes,
            quality_report=quality_report,
            score_card=score_card,
            output_dir=str(out),
        )

    def run_step(self, step: int, video_path: str, output_dir: str) -> Any:
        """执行管线中的单个步骤（用于调试和断点恢复）。

        Args:
            step: 步骤编号（1-6）
            video_path: 视频文件路径
            output_dir: 输出目录路径

        Returns:
            该步骤的输出结果
        """
        if step == 1:
            return self._step_read_video(video_path)
        elif step == 2:
            audio_path = str(Path(output_dir) / "audio.wav")
            return self._step_extract_audio(video_path, audio_path)
        else:
            raise PipelineError(f"步骤 {step} 需要前置步骤结果，请使用 run() 方法")

    # ── 步骤实现 ──

    def _step_read_video(self, video_path: str) -> VideoInfo:
        """[1/6] 读取视频文件信息。"""
        logger.info(f"读取视频文件：{video_path}")
        if not VideoExtractor.validate_format(video_path):
            raise PipelineError(f"不支持的视频格式：{video_path}")
        return self._video_extractor.extract_info(video_path)

    def _step_extract_audio(self, video_path: str, output_path: str) -> AudioInfo:
        """[2/6] FFmpeg提取音频。"""
        logger.info(f"提取音频：{video_path} → {output_path}")
        return self._audio_extractor.extract(video_path, output_path, sample_rate=16000)

    def _step_asr(self, audio_path: str, enable_diarization: bool = True) -> Transcript:
        """[3/6] 腾讯云ASR转文字。"""
        logger.info(f"ASR转写：{audio_path}")
        return self._asr_client.recognize(audio_path, enable_diarization=enable_diarization)

    def _get_prompt_version(self) -> str:
        """根据配置返回对应的 Prompt 版本。"""
        return self._config.analysis_config.get("prompt_version", "spark_standard")

    def _step_llm_analysis(
        self,
        transcript: Transcript,
        prompt_version: str = "standard",
        progress_callback: Optional[Callable[[float, str], None]] = None,
    ) -> EventTimeline:
        """[4/6] LLM语义分析。"""
        logger.info(f"LLM语义分析：识别教学事件（prompt={prompt_version}）")

        # 预报告分段信息
        full_text = transcript.to_text()
        n_chars = len(full_text)
        n_segments = len(transcript.segments)
        if progress_callback:
            progress_callback(3.1, f"LLM语义分析 — {n_segments}段对话，共{n_chars}字符，正在识别教学事件...")

        return self._llm_analyzer.detect_events(transcript, self._config.event_types)

    def _step_extract_frames(
        self,
        video_path: str,
        events: EventTimeline,
        output_dir: str,
    ) -> list[KeyFrame]:
        """[5/6] 双轨制截帧：事件驱动 + 定期采样。

        事件驱动帧：捕捉教学行为（提问、反馈、知识节点等）
        定期采样帧：捕捉学生表情、教学节奏、环境状态（每2分钟一帧）

        合并去重后为视觉模型提供更全面的课堂画面覆盖。
        """
        keyframes_dir = str(Path(output_dir) / "keyframes")

        # 1. 事件驱动截帧
        event_frames = self._frame_extractor.extract_for_events(
            video_path, events.events, keyframes_dir
        )
        logger.info(f"事件驱动截帧：{len(event_frames)} 帧")

        # 2. 定期采样截帧（每2分钟采样一帧，用于捕捉学生表情和教学节奏）
        video_duration = self._config.analysis_config.get("video_duration", 0)
        if video_duration <= 0 and hasattr(self, '_last_video_info') and self._last_video_info:
            video_duration = self._last_video_info.duration
        if video_duration > 0:
            periodic_frames = self._frame_extractor.extract_periodic_frames(
                video_path=video_path,
                duration=video_duration,
                output_dir=keyframes_dir,
                interval_seconds=120.0,  # 每2分钟采样一帧
            )
            if not isinstance(periodic_frames, list):
                logger.warning("定期采样截帧返回值不是列表，已忽略该结果")
                periodic_frames = []
            logger.info(f"定期采样截帧：{len(periodic_frames)} 帧")
        else:
            periodic_frames = []
            logger.info("视频时长未知，跳过定期采样")

        # 3. 合并去重（同一秒内的帧只保留一个）
        all_frames = event_frames + periodic_frames
        seen_timestamps: set[int] = set()  # 秒级去重
        unique_frames: list[KeyFrame] = []
        for kf in all_frames:
            ts_key = int(kf.timestamp)
            if ts_key not in seen_timestamps:
                seen_timestamps.add(ts_key)
                unique_frames.append(kf)

        logger.info(f"双轨制截帧完成：事件{len(event_frames)} + 定期{len(periodic_frames)} → 去重后 {len(unique_frames)} 帧")
        return unique_frames

    def _step_generate_reports(
        self,
        video_info: VideoInfo,
        transcript: Transcript,
        events: EventTimeline,
        output_dir: str,
        progress_callback: Optional[Callable[[float, str], None]] = None,
    ) -> tuple[QualityReport, ScoreCard]:
        """[6/6] 生成报告和评分卡。"""
        logger.info("生成质检报告和评分卡")

        # 确定关键帧目录
        keyframes_dir = str(Path(output_dir) / "keyframes")
        if not Path(keyframes_dir).exists():
            keyframes_dir = None
            logger.info("关键帧目录不存在，质量评估将仅基于文本")

        # ── 混合评分：文本模型（8维度）+ 视觉模型（2视觉维度 + 视觉增强维度 + 红线检查）──
        # 视觉维度：视觉模型直接评分的维度（需要看视频才能评）
        VISUAL_DIMENSIONS = {"仪表教态", "语言表达及板书设计"}
        # 视觉增强维度：视觉模型提供观察证据，辅助文本模型评分的维度
        # 不直接用视觉模型评分，但视觉观察结果已注入文本模型的上下文中
        VISUAL_ENHANCED_DIMENSIONS = {
            "课堂效果及整体印象",  # 学生表情/情绪 → 课堂氛围
            "关注公平",           # 学生参与度分布 → 互动机会
            "教学逻辑",           # 教学节奏/环节切换 → 主线清晰度
            "组织教学",           # 课堂秩序 → 环境管理
        }
        prompt_version = self._get_prompt_version()
        num_rounds = self._config.analysis_config.get("num_rounds", 1)
        analysis_mode = str(self._config.analysis_config.get("analysis_mode", "standard")).lower()
        video_scope = str(self._config.analysis_config.get("video_scope", "full"))
        is_clip_analysis = analysis_mode in {"quick", "fast"} or any(
            marker in video_scope for marker in ("片段", "切片", "clip", "segment")
        )
        if is_clip_analysis:
            visual_observation_frames = 10
            visual_score_frames = 4
        elif analysis_mode in {"deep", "full"}:
            visual_observation_frames = 24
            visual_score_frames = 8
        else:
            visual_observation_frames = 16
            visual_score_frames = 6

        # 0. 视觉预观察（如已配置视觉模型 + 有关键帧）
        # 目的：在文本模型评分前，让视觉模型观察课堂画面，输出行为描述
        # 这些观察结果作为额外上下文注入到文本模型评分，提升评分准确性
        visual_observation: str = ""
        if self._vision_analyzer and keyframes_dir:
            kf_path = Path(keyframes_dir)
            kf_count = len(list(kf_path.glob("*.jpg")) + list(kf_path.glob("*.png")))
            if kf_count > 0:
                logger.info(f"【混合评分】步骤0/3：视觉预观察（{kf_count}帧 → 提取课堂行为描述）")
                if progress_callback:
                    progress_callback(5.05, f"生成报告 — 视觉预观察（分析{kf_count}张关键帧，提取行为描述）...")
                try:
                    visual_observation = self._run_visual_observation(
                        keyframes_dir=keyframes_dir,
                        transcript=transcript,
                        events=events,
                        max_frames=visual_observation_frames,
                    )
                    if visual_observation:
                        logger.info(f"视觉预观察完成，提取行为描述 {len(visual_observation)} 字符")
                    if progress_callback:
                        progress_callback(5.1, "生成报告 — 视觉预观察完成 ✓")
                except Exception as e:
                    logger.warning(f"视觉预观察失败（不影响后续评分）：{e}")
                    logger.debug("视觉预观察异常详情：", exc_info=True)
                    visual_observation = ""

        # 1. 文本评分（所有10个维度，注入视觉观察作为上下文）
        logger.info("【混合评分】步骤1/3：文本模型评分（注入视觉观察上下文）")
        if progress_callback:
            progress_callback(5.15, "生成报告 — 文本模型评分中（1/2，可能需要几分钟）...")

        # 1a. 交互链重构（将扁平事件列表转换为因果关联的互动链）
        chains = build_interaction_chains(events)
        interaction_chains_text = format_chains_for_prompt(chains)
        logger.info(f"交互链重构完成：{len(chains)} 条互动链，{sum(len(c.links) for c in chains)} 个回合")

        text_check_items, text_scores = self._llm_analyzer.assess_quality(
            transcript=transcript,
            events=events,
            checklist=self._config.quality_checklist,
            dimensions=self._config.scoring_dimensions,
            prompt_version=prompt_version,
            num_rounds=num_rounds,
            keyframe_dir=None,  # 关键：不看视频（视觉上下文通过 visual_context 注入）
            visual_context=visual_observation,  # 视觉预观察结果作为辅助上下文
            interaction_chains=interaction_chains_text,  # 互动链：提供上下文关联
        )
        if progress_callback:
            progress_callback(5.3, "生成报告 — 文本模型评分完成 ✓")

        # 2. 视觉评分（如已配置视觉模型）
        vision_check_items, vision_scores = None, None
        if self._vision_analyzer and keyframes_dir:
            # 统计关键帧数量，方便排查
            kf_path = Path(keyframes_dir)
            kf_count = len(list(kf_path.glob("*.jpg")) + list(kf_path.glob("*.png")))
            logger.info(f"【混合评分】步骤2/3：视觉模型评分（看视频关键帧，共 {kf_count} 帧）")
            if progress_callback:
                progress_callback(5.35, f"生成报告 — 视觉模型评分中（2/2，{kf_count}张关键帧）...")
            try:
                vision_check_items, vision_scores = self._vision_analyzer.assess_quality(
                    transcript=transcript,
                    events=events,
                    checklist=self._config.quality_checklist,
                    dimensions=self._config.scoring_dimensions,
                    prompt_version=prompt_version,
                    num_rounds=1,  # 视觉模型只跑1轮（节省成本）
                    keyframe_dir=keyframes_dir,
                    max_keyframes=visual_score_frames,
                )
                # 记录视觉模型返回的分数，方便排查0分问题
                if vision_scores:
                    scores_str = ", ".join(f"{d.name}={d.score:.1f}" for d in vision_scores)
                    logger.info(f"视觉模型返回分数：{scores_str}")
                else:
                    logger.warning("视觉模型未返回任何评分维度")
                if progress_callback:
                    progress_callback(5.5, "生成报告 — 视觉模型评分完成 ✓")
            except Exception as e:
                logger.warning(f"视觉评分失败，将使用文本评分结果：{e}")
                logger.debug("视觉评分异常详情：", exc_info=True)
                vision_check_items, vision_scores = None, None
                if progress_callback:
                    progress_callback(5.5, "生成报告 — 视觉模型评分失败，使用文本结果替代")

        # 3. 合并评分结果
        logger.info("【混合评分】步骤3/3：合并评分结果")

        # 按维度名称建立查找表（防止视觉/文本模型返回顺序与配置不一致）
        text_by_name = {d.name: d for d in text_scores} if text_scores else {}
        vision_by_name = {d.name: d for d in vision_scores} if vision_scores else {}

        merged_scores = []
        for i, dim_config in enumerate(self._config.scoring_dimensions):
            dim_name = dim_config.name
            dim_weight = dim_config.weight
            dim_max_score = dim_config.weight * 100

            # 视觉评分是否有效：维度在视觉列表中 + 视觉模型确实返回了该维度 + 分数>0
            vision_dim = vision_by_name.get(dim_name) if vision_by_name else None
            vision_score_valid = (
                vision_dim is not None
                and dim_name in VISUAL_DIMENSIONS
                and vision_dim.score > 0
            )

            if vision_score_valid:
                # 视觉维度：使用视觉模型评分
                dim = vision_dim
                dim.source_model = "vision"
                merged_scores.append(dim)
                logger.debug(f"  维度 '{dim_name}'：使用视觉评分 = {dim.score:.1f}")

            elif dim_name in text_by_name:
                # 使用文本模型评分（含视觉维度 fallback）
                dim = text_by_name[dim_name]
                if dim_name in VISUAL_DIMENSIONS:
                    # 视觉维度 fallback：没有有效视觉评分时，不让文本模型的高分/低分冒充视觉结论。
                    # 统一给中性待复核分，避免“文本证据 5/5”拉高总分，也避免纯文本误扣板书/仪态。
                    fallback_threshold = dim_max_score * 0.60
                    logger.info(
                        f"  维度 '{dim_name}'：视觉评分无效，文本分数 {dim.score:.1f} 不作为最终视觉分，"
                        f"使用待复核中性分 {fallback_threshold:.1f}"
                    )
                    original_evidence = dim.evidence or ""
                    dim.score = fallback_threshold
                    dim.evidence = (
                        f"[视觉维度·待人工校对] 未获得有效的独立视觉评分，当前采用满分60%的中性分。"
                        f"请结合关键帧复核教师仪态、板书/课件结构、课堂软件操作等画面证据。"
                        + (f" 文本模型原判断：{original_evidence}" if original_evidence else "")
                    )
                    dim.source_model = "vision_enhanced"
                else:
                    dim.source_model = "text"
                merged_scores.append(dim)
                logger.debug(f"  维度 '{dim_name}'：使用文本评分 = {dim.score:.1f}")

            else:
                # 默认值（理论上不应到达）
                merged_scores.append(ScoreDimension(
                    name=dim_name,
                    score=0.0,
                    max_score=dim_max_score,
                    weight=dim_weight,
                    evidence="未获得评估结果",
                    grade="差",
                    source_model="text",
                ))

        # 合并质检清单：优先使用视觉模型结果（能看视频，红线检查更准确）
        if vision_check_items:
            check_items = vision_check_items
            logger.info("质检清单：使用视觉模型结果（含视频红线检查）")
        else:
            check_items = text_check_items
            logger.info("质检清单：使用文本模型结果")

        score_dimensions = merged_scores

        # 构建事件摘要
        event_summary: dict[str, Any] = {"total": len(events.events)}
        for event_type in self._config.event_types:
            type_events = events.get_events_by_type(event_type)
            event_summary[event_type] = len(type_events)

        # 检测红线违规
        red_line_violation = any(
            item.is_red_line and not item.passed for item in check_items
        )

        # 为每个评分维度计算等级（10分制：9-10优/7-9良/5-7中/0-5差）
        for d in score_dimensions:
            if d.max_score > 0:
                pct = d.score / d.max_score * 100
                if pct >= 90:
                    d.grade = "优"
                elif pct >= 70:
                    d.grade = "良"
                elif pct >= 50:
                    d.grade = "中"
                else:
                    d.grade = "差"

        # 获取班型
        level = self._config.analysis_config.get("level", "L4_L6")

        # 构建评分卡
        score_card = ScoreCard(
            dimensions=score_dimensions,
            total_score=sum(d.score for d in score_dimensions),
            total_max=sum(d.max_score for d in score_dimensions),
            red_line_violation=red_line_violation,
            level=level,
            num_rounds=num_rounds,
        )
        # 计算等级
        score_card.compute_grade(level=level)

        # 构建质检报告
        transcript_summary = f"说话人{transcript.speaker_count}人"
        quality_report = QualityReport(
            video_info=video_info,
            transcript_summary=transcript_summary,
            check_items=check_items,
            event_summary=event_summary,
            score_card=score_card,
            level=level,
        )

        # 生成文件
        report_path = str(Path(output_dir) / "quality_report.md")
        score_path = str(Path(output_dir) / "score_card.json")

        self._quality_report_generator.generate(quality_report, report_path)
        self._score_card_generator.generate(score_card, score_path)

        return quality_report, score_card

    def _run_visual_observation(
        self,
        keyframes_dir: str,
        transcript: "Transcript",
        events: "EventTimeline",
        max_frames: int = 16,
    ) -> str:
        """视觉预观察：让视觉模型观察关键帧，输出课堂行为描述（不评分）。

        目的：把视觉模型观察到的师生行为、表情、互动状态等信息提取为文本，
        随后注入到文本模型的评分上下文，让文本模型能"看到"视频信息。

        Returns:
            str: 视觉观察报告 JSON 字符串，空字符串表示失败
        """
        if not self._vision_analyzer:
            return ""

        # 采样关键帧：按分析模式控制输入规模，降低短视频/快速分析的等待时间。
        sampled = self._vision_analyzer._sample_keyframes(
            keyframes_dir,
            max_frames=max_frames,
            bucket_count=max(4, min(max_frames, 12)),
        )
        if not sampled:
            logger.warning("视觉预观察：无可用关键帧")
            return ""

        # 构建观察 Prompt
        try:
            observation_prompt = self._prompt_templates.render(
                "visual_observation",
                visual_note=f"以下是从课堂视频中采样的 {len(sampled)} 张关键帧截图，按时间顺序排列。",
            )
        except Exception:
            observation_prompt = (
                f"以下是从课堂视频中采样的 {len(sampled)} 张关键帧截图，按时间顺序排列。\n"
                "请观察每帧中教师的表情、姿态、肢体语言，以及学生的参与状态（举手/低头/走神等），"
                "输出结构化观察报告（JSON格式）。"
            )

        # 构建多模态消息
        import base64
        import os
        user_content: list[dict] = [{"type": "text", "text": observation_prompt}]
        for img_path in sampled:
            b64 = self._vision_analyzer._encode_image(img_path, max_size=720)
            if b64:
                user_content.append({
                    "type": "image_url",
                    "image_url": {"url": f"data:image/jpeg;base64,{b64}"}
                })

        system_msg = (
            "你是一位专业的课堂教学观察员，擅长通过视频截图解读教师和学生的行为状态。"
            "请客观描述你在画面中观察到的事实，不要主观评价好坏。"
        )

        try:
            observation_result = self._vision_analyzer._call_llm([
                {"role": "system", "content": system_msg},
                {"role": "user", "content": user_content},
            ])
            logger.debug(f"视觉观察结果（前500字符）：{observation_result[:500]}")
            return observation_result
        except Exception as e:
            logger.warning(f"视觉预观察调用失败：{e}")
            return ""

    # ── 中间文件持久化 ──

    @staticmethod
    def _save_transcript(transcript: Transcript, output_path: str) -> None:
        """保存转录文本。"""
        logger.debug(f"保存转录文本：{output_path}")
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(transcript.to_text())

    @staticmethod
    def _save_events(events: EventTimeline, output_path: str) -> None:
        """保存教学事件。"""
        logger.debug(f"保存教学事件：{output_path}")
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(events.to_json())

    @staticmethod
    def _load_transcript(transcript_path: str) -> Transcript:
        """从文件加载转录文本。"""
        logger.debug(f"加载转录文本：{transcript_path}")
        segments: list[TranscriptSegment] = []
        speakers: set[str] = set()
        max_end = 0.0

        from classroom_analyzer.models import TranscriptSegment

        with open(transcript_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                # 格式: [MM:SS-MM:SS] speaker: text
                try:
                    time_part, rest = line.split("]", 1)
                    time_part = time_part.lstrip("[")
                    start_str, end_str = time_part.split("-")
                    start_time = _parse_time_str(start_str)
                    end_time = _parse_time_str(end_str)

                    rest = rest.strip()
                    if ": " in rest:
                        speaker, text = rest.split(": ", 1)
                    else:
                        speaker = "unknown"
                        text = rest

                    segments.append(TranscriptSegment(
                        start_time=start_time,
                        end_time=end_time,
                        text=text,
                        speaker=speaker,
                    ))
                    speakers.add(speaker)
                    max_end = max(max_end, end_time)
                except (ValueError, IndexError):
                    logger.warning(f"跳过无法解析的行：{line}")
                    continue

        return Transcript(
            segments=segments,
            duration=max_end,
            speaker_count=len(speakers),
        )

    @staticmethod
    def _load_events(events_path: str) -> EventTimeline:
        """从文件加载教学事件。"""
        logger.debug(f"加载教学事件：{events_path}")
        with open(events_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        events = []
        for item in data:
            events.append(TeachingEvent(
                event_type=item.get("event_type", ""),
                subtype=item.get("subtype", ""),
                start_time=item.get("start_time", 0.0),
                end_time=item.get("end_time", 0.0),
                description=item.get("description", ""),
                confidence=item.get("confidence", 0.0),
                related_text=item.get("related_text", ""),
            ))

        return EventTimeline(events=events)

    # ── 工具方法 ──

    @staticmethod
    def _find_ffmpeg() -> str:
        """查找系统中的FFmpeg路径。

        搜索顺序：
        1. 系统 PATH（shutil.which）
        2. 项目本地 tools/ 目录下的 FFmpeg
        3. 兜底返回 "ffmpeg"（依赖 PATH）
        """
        # 1. 系统 PATH
        ffmpeg_path = shutil.which("ffmpeg")
        if ffmpeg_path:
            logger.debug(f"找到FFmpeg（系统PATH）：{ffmpeg_path}")
            return ffmpeg_path

        # 2. 项目本地 tools/ 目录
        # 从当前文件向上查找项目根目录（包含 pyproject.toml 的目录）
        current = Path(__file__).resolve()
        for parent in [current.parent, *current.parents]:
            tools_bin = parent / "tools" / "ffmpeg-8.1.1-essentials_build" / "bin"
            ffmpeg_exe = tools_bin / "ffmpeg.exe"
            ffprobe_exe = tools_bin / "ffprobe.exe"
            if ffmpeg_exe.exists() and ffprobe_exe.exists():
                logger.info(f"找到本地FFmpeg：{tools_bin}")
                return str(ffmpeg_exe)
            # 也检查非版本化的目录名
            tools_bin2 = parent / "tools" / "ffmpeg" / "bin"
            ffmpeg_exe2 = tools_bin2 / "ffmpeg.exe"
            ffprobe_exe2 = tools_bin2 / "ffprobe.exe"
            if ffmpeg_exe2.exists() and ffprobe_exe2.exists():
                logger.info(f"找到本地FFmpeg：{tools_bin2}")
                return str(ffmpeg_exe2)

        logger.warning(
            "未找到FFmpeg，请安装FFmpeg并添加到PATH，或放置到项目的 tools/ 目录。\n"
            "下载地址：https://ffmpeg.org/download.html"
        )
        return "ffmpeg"


def _parse_time_str(time_str: str) -> float:
    """将 MM:SS 格式转为秒数。"""
    parts = time_str.strip().split(":")
    if len(parts) == 2:
        return float(parts[0]) * 60 + float(parts[1])
    return float(time_str)
