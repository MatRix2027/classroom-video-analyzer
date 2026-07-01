"""LLM语义分析器 — 教学事件识别与质量评估"""

import base64
import json
import math
import os
import re
import statistics
import time
from pathlib import Path
from typing import Any, Optional
from loguru import logger
from openai import OpenAI
import httpx

from classroom_analyzer.analysis.prompt_templates import PromptTemplates
from classroom_analyzer.config import ClassroomAnalyzerError
from classroom_analyzer.models import (
    EventTimeline,
    QualityCheckItem,
    ScoreDimension,
    ScoringDimensionConfig,
    ScoringPoint,
    TeachingEvent,
    Transcript,
)


class LLMAnalyzerError(ClassroomAnalyzerError):
    """LLM分析异常。"""
    pass


class LLMAnalyzer:
    """LLM语义分析器：教学事件识别和质量评估。

    支持：
    - 滑动窗口分段长文本
    - 教学事件识别（6大类）
    - 质量评估与评分
    - 指数退避重试
    """

    def __init__(
        self,
        api_key: str,
        model: str = "deepseek-chat",
        base_url: str = "https://api.deepseek.com/v1",
        prompt_templates: Optional[PromptTemplates] = None,
        chunk_size: int = 2000,
        chunk_overlap: int = 200,
        level: str = "QC-v4",
        max_retries: int = 2,
    ) -> None:
        """初始化LLM分析器。

        Args:
            api_key: LLM API密钥
            model: 模型名称
            base_url: API基础URL
            prompt_templates: Prompt模板管理器
            chunk_size: 分段大小（字符数）
            chunk_overlap: 分段重叠（字符数）
            level: 评分标准等级（QC-v4/L4_L6/L7_L9等）
        """
        self.api_key = api_key
        self.model = model
        self.base_url = base_url
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap
        self._level = level  # 评分标准等级，用于Prompt模板条件渲染
        self.max_retries = max(1, max_retries)

        # 初始化OpenAI客户端
        # 显式创建 httpx.Client 并禁用代理 — 翻墙软件的 HTTPS_PROXY 环境变量会
        # 把所有请求路由到 127.0.0.1:7890，当翻墙断开时 API 调用全部失败（ProxyError）
        http_client = httpx.Client(
            timeout=httpx.Timeout(600.0, connect=30.0),
            follow_redirects=True,
            proxy=None,  # 显式禁用代理，绕过系统 HTTPS_PROXY 环境变量
        )
        self._client = OpenAI(
            api_key=api_key,
            base_url=base_url,
            http_client=http_client,
            max_retries=0,  # 客户端不重试，由 _call_llm 管理重试逻辑
        )

        # Prompt模板
        self._prompt_templates = prompt_templates

    def detect_events(
        self,
        transcript: Transcript,
        event_types: list[str],
    ) -> EventTimeline:
        """识别教学事件。

        Args:
            transcript: 转录文本
            event_types: 要识别的事件类型列表

        Returns:
            EventTimeline: 教学事件时间轴
        """
        logger.info(f"开始教学事件识别：{len(transcript.segments)} 段，事件类型 {event_types}")

        full_text = transcript.to_text()
        chunks = self._chunk_transcript(transcript, self.chunk_size, self.chunk_overlap)
        logger.info(f"文本分为 {len(chunks)} 段（每段约{self.chunk_size}字，重叠{self.chunk_overlap}字）")

        all_events: list[list[TeachingEvent]] = []
        for i, chunk in enumerate(chunks):
            logger.debug(f"分析第 {i+1}/{len(chunks)} 段文本")

            prompt = self._build_event_detection_prompt(chunk, event_types)
            response = self._call_llm([
                {"role": "system", "content": "你是一位专业的课堂教学分析师，擅长识别和分析教学环节变化。"},
                {"role": "user", "content": prompt},
            ])

            chunk_events = self._parse_events_response(response)
            all_events.append(chunk_events)
            logger.debug(f"第 {i+1} 段识别到 {len(chunk_events)} 个事件")

        # 合并去重
        timeline = self._merge_events(all_events)
        logger.info(f"教学事件识别完成：共 {len(timeline.events)} 个事件")

        return timeline

    # 质量评估输入大小限制（防止超长转录导致 LLM 超时）
    _MAX_TRANSCRIPT_CHARS = 20000   # 转录文本最大字符数
    _MAX_EVENTS_CHARS = 8000        # 事件 JSON 最大字符数
    _MAX_EVENT_COUNT = 80           # 最多保留的事件数量

    def assess_quality(
        self,
        transcript: Transcript,
        events: EventTimeline,
        checklist: list[str],
        dimensions: list[ScoringDimensionConfig],
        prompt_version: str = "standard",
        num_rounds: int = 1,
        keyframe_dir: Optional[str] = None,
        max_keyframes: int = 8,
        visual_context: Optional[str] = None,
        interaction_chains: Optional[str] = None,
    ) -> tuple[list[QualityCheckItem], list[ScoreDimension]]:
        """质量评估与评分（支持多轮评估取均值 + 可选视频帧视觉分析）。

        Args:
            transcript: 转录文本
            events: 教学事件时间轴
            checklist: 质检清单
            dimensions: 评分维度配置
            prompt_version: Prompt版本，"standard" 或 "spark_standard"
            num_rounds: 评估轮数（≥1），多轮时取均值并计算标准差
            keyframe_dir: 关键帧目录路径，传入后LLM将同时分析视频画面
            max_keyframes: 视觉评分最多使用的关键帧数量
            visual_context: 视觉预观察结果文本（由视觉模型提前观察课堂画面生成），
                            注入到文本模型的上下文中，帮助文本模型理解视频中的行为信息

        Returns:
            tuple: (质检清单结果, 评分维度结果)
        """
        logger.info(
            f"开始质量评估与评分（prompt版本：{prompt_version}，评估轮数：{num_rounds}，"
            f"视觉上下文：{'有' if visual_context else '无'}）"
        )

        full_text = transcript.to_text()
        events_json = events.to_json()

        # ── 输入大小控制：截断超长的转录文本和事件 ──
        full_text = self._truncate_transcript(full_text)
        events_json = self._truncate_events(events_json, events)

        # 构建评分维度描述（含每个维度的满分，约束LLM不越界）
        dimensions_desc = "\n".join([
            f"- {d.name}（权重{d.weight}，满分{d.max_score}分）：{d.criteria}"
            for d in dimensions
        ])

        # 显式维度名称清单（末尾约束LLM必须使用这些名称）
        dimension_names = "、".join([d.name for d in dimensions])

        checklist_str = "\n".join([f"- {item}" for item in checklist])

        prompt_text = self._build_quality_assessment_prompt(
            full_text, events_json, checklist_str, dimensions_desc,
            prompt_version=prompt_version,
            level=self._level,
            dimension_names=dimension_names,
            visual_context=visual_context,
            interaction_chains=interaction_chains,
        )

        # 采样关键帧（如有），构建多模态用户消息
        sampled_images: list[str] = []
        if keyframe_dir:
            sampled_images = self._sample_keyframes(keyframe_dir, max_frames=max_keyframes)
            if sampled_images:
                logger.info(f"使用 {len(sampled_images)} 张关键帧进行视觉分析")
            else:
                logger.warning(f"关键帧目录为空或无法读取：{keyframe_dir}")

        # 根据prompt版本选择不同的系统提示
        if prompt_version == "spark_standard":
            vision_note = (
                "你不仅能阅读转录文本，还能查看课堂关键帧截图。"
                "请结合画面信息评估：教师的肢体语言、板书/课件质量、"
                "学生反应（表情、专注度）、课堂环境（背景、着装）等文本无法体现的维度。"
            ) if sampled_images else ""
            visual_ctx_note = (
                "此外，系统已提前对课堂关键帧进行了视觉预分析，"
                "相关观察结果已包含在评估材料中（见「课堂视觉观察报告」部分），"
                "请结合这些视觉证据对相关维度进行评分。"
            ) if visual_context else ""
            system_msg = (
                "你是一位专业的课堂教学质量评估师，严格按照火花思维的评分标准进行评估，"
                "包含红线淘汰检测和等级制评分。"
                + (f" {vision_note}" if vision_note else "")
                + (f" {visual_ctx_note}" if visual_ctx_note else "")
            )
        else:
            system_msg = "你是一位专业的课堂教学质量评估师，擅长客观评估课堂教学质量。"

        # 构建用户消息（多模态或纯文本）
        if sampled_images:
            # 在提示中增加视觉分析指引
            vision_guidance = (
                "\n\n## 关键帧图像（课堂视频截图）\n\n"
                "以下是按时间顺序排列的课堂关键帧截图，请结合图像中的画面信息"
                "（教师姿态、学生表情、板书内容、课件质量、教室环境等）进行综合评估。\n"
            )
            user_content: list[dict[str, Any]] = [
                {"type": "text", "text": prompt_text + vision_guidance}
            ]
            for img_path in sampled_images:
                b64 = self._encode_image(img_path)
                if b64:
                    user_content.append({
                        "type": "image_url",
                        "image_url": {"url": f"data:image/jpeg;base64,{b64}"}
                    })
            user_message: dict[str, Any] = {"role": "user", "content": user_content}
        else:
            user_message = {"role": "user", "content": prompt_text}

        # ── 多轮评估 ──
        all_check_items: list[list[QualityCheckItem]] = []
        all_score_dims: list[list[ScoreDimension]] = []

        for round_idx in range(num_rounds):
            logger.info(f"第 {round_idx+1}/{num_rounds} 轮评估中...")

            response = self._call_llm([
                {"role": "system", "content": system_msg},
                user_message,
            ])

            check_items, score_dimensions = self._parse_quality_response(response, dimensions)
            all_check_items.append(check_items)
            all_score_dims.append(score_dimensions)

            logger.debug(
                f"第 {round_idx+1} 轮完成："
                f"{sum(1 for i in check_items if i.passed)}/{len(check_items)} 项通过，"
                f"总分 {sum(d.score for d in score_dimensions):.1f}"
            )

        # ── 单轮：直接返回 ──
        if num_rounds == 1:
            logger.info(
                f"质量评估完成：{sum(1 for i in all_check_items[0] if i.passed)}/{len(all_check_items[0])} 项通过"
            )
            return all_check_items[0], all_score_dims[0]

        # ── 多轮：合并结果 ──
        logger.info(f"合并 {num_rounds} 轮评估结果...")

        # 1. 质检清单：取第一轮（红线检测各轮一致）
        merged_check_items = all_check_items[0]

        # 2. 评分维度：取均值 + 标准差
        dim_count = len(dimensions)
        merged_score_dims: list[ScoreDimension] = []

        for dim_idx in range(dim_count):
            # 收集各轮该维度的分数
            round_scores: list[float] = []
            round_evidence: list[str] = []
            round_details: list[str] = []
            round_timestamps: list[Optional[float]] = []
            round_grades: list[str] = []
            all_scoring_points: list[ScoringPoint] = []

            for rd in range(num_rounds):
                if dim_idx < len(all_score_dims[rd]):
                    d = all_score_dims[rd][dim_idx]
                    round_scores.append(d.score)
                    round_evidence.append(d.evidence)
                    round_details.append(d.details)
                    round_timestamps.append(d.timestamp)
                    round_grades.append(d.grade)
                    all_scoring_points.extend(d.scoring_points)

            if not round_scores:
                # 所有轮次都没有该维度 → 默认值
                dim_config = dimensions[dim_idx]
                merged_score_dims.append(ScoreDimension(
                    name=dim_config.name,
                    score=0.0, max_score=dim_config.weight * 100,
                    weight=dim_config.weight,
                    evidence="未获得评估结果", grade="差",
                    score_std=None, round_scores=[],
                ))
                continue

            # 计算均值 & 标准差
            mean_score = statistics.mean(round_scores)
            std_score = statistics.stdev(round_scores) if len(round_scores) >= 2 else 0.0

            # 取中位分数那轮的 evidence/details（最有代表性）
            median_idx = _closest_to_median_index(round_scores)

            dim_config = dimensions[dim_idx] if dim_idx < len(dimensions) else ScoringDimensionConfig(
                name=all_score_dims[0][dim_idx].name if dim_idx < len(all_score_dims[0]) else f"维度{dim_idx+1}",
                weight=1.0 / max(dim_count, 1), criteria="",
            )

            # 合并去重 scoring_points
            merged_points = _merge_scoring_points(all_scoring_points)

            # 重新计算等级
            if dim_config.max_score > 0:
                pct = mean_score / dim_config.max_score * 100 if hasattr(dim_config, 'max_score') and dim_config.max_score else mean_score / 100 * 100
                if pct >= 90:
                    grade = "优"
                elif pct >= 70:
                    grade = "良"
                elif pct >= 50:
                    grade = "中"
                else:
                    grade = "差"
            else:
                grade = round_grades[median_idx] if median_idx < len(round_grades) else ""

            merged_score_dims.append(ScoreDimension(
                name=dim_config.name,
                score=mean_score,
                max_score=dim_config.weight * 100,
                weight=dim_config.weight,
                evidence=round_evidence[median_idx] if median_idx < len(round_evidence) else "",
                details=round_details[median_idx] if median_idx < len(round_details) else "",
                grade=grade,
                timestamp=round_timestamps[median_idx] if median_idx < len(round_timestamps) else None,
                scoring_points=merged_points,
                score_std=std_score,
                round_scores=round_scores,
            ))

            logger.debug(
                f"维度 '{dim_config.name}'：{mean_score:.2f}±{std_score:.2f} "
                f"（各轮：{', '.join(f'{s:.1f}' for s in round_scores)}），"
                f"合并证据点 {len(merged_points)} 个"
            )

        logger.info(
            f"多轮评估完成：{sum(1 for i in merged_check_items if i.passed)}/{len(merged_check_items)} 项通过，"
            f"总分 {sum(d.score for d in merged_score_dims):.1f}"
        )
        return merged_check_items, merged_score_dims

    # ── 私有方法 ──

    def _chunk_transcript(
        self,
        transcript: Transcript,
        chunk_size: int = 2000,
        overlap: int = 200,
    ) -> list[str]:
        """将转录文本按滑动窗口分段。

        Args:
            transcript: 转录文本
            chunk_size: 每段字符数
            overlap: 重叠字符数

        Returns:
            list[str]: 分段文本列表
        """
        full_text = transcript.to_text()
        text_len = len(full_text)

        if text_len <= chunk_size:
            return [full_text]

        chunks: list[str] = []
        start = 0
        while start < text_len:
            end = start + chunk_size
            chunk = full_text[start:end]

            # 如果不是最后一段，尝试在重叠区域开始下一段
            chunks.append(chunk)
            start = end - overlap

        return chunks

    @staticmethod
    def _encode_image(image_path: str, max_size: int = 720) -> str | None:
        """将图像文件编码为 base64 字符串，自动压缩大图。

        Args:
            image_path: 图像文件路径
            max_size: 压缩后的最长边像素（默认 720，足够视觉分析）

        Returns:
            str | None: base64 编码字符串，失败返回 None
        """
        try:
            if not os.path.exists(image_path):
                logger.warning(f"图像文件不存在：{image_path}")
                return None
            # 用 Pillow 压缩后再编码，减少请求体体积
            from io import BytesIO
            from PIL import Image
            with Image.open(image_path) as img:
                # 转换为 RGB（兼容 RGBA/JPEG）
                if img.mode in ("RGBA", "P", "LA"):
                    img = img.convert("RGB")
                # 等比例缩放
                w, h = img.size
                if max(w, h) > max_size:
                    scale = max_size / max(w, h)
                    new_w, new_h = int(w * scale), int(h * scale)
                    img = img.resize((new_w, new_h), Image.LANCZOS)
                buf = BytesIO()
                img.save(buf, format="JPEG", quality=82)
                return base64.b64encode(buf.getvalue()).decode("utf-8")
        except Exception as e:
            logger.warning(f"图像编码失败：{image_path}，错误：{e}")
            # fallback：直接读取原文件
            try:
                with open(image_path, "rb") as f:
                    return base64.b64encode(f.read()).decode("utf-8")
            except Exception:
                return None

    @staticmethod
    def _sample_keyframes(
        keyframe_dir: str,
        max_frames: int = 20,
        bucket_count: int = 12,
    ) -> list[str]:
        """从关键帧目录中均匀采样代表性帧。

        策略：
        1. 按时间将课堂分成 bucket_count 个等宽桶
        2. 每个桶最多取 ceil(max_frames/bucket_count) 帧
        3. 优先选择交互类事件帧（互动指令、学生应答、教师反馈）
        4. 确保每种事件类型至少有一帧入选

        Args:
            keyframe_dir: 关键帧目录路径
            max_frames: 最多采样帧数
            bucket_count: 时间桶数量

        Returns:
            list[str]: 采样后的帧文件路径列表
        """
        dir_path = Path(keyframe_dir)
        if not dir_path.exists() or not dir_path.is_dir():
            logger.warning(f"关键帧目录不存在：{keyframe_dir}")
            return []

        # 收集所有帧文件信息
        frames: list[dict[str, Any]] = []
        for f in sorted(dir_path.glob("frame_*.jpg")):
            # 从文件名解析：frame_{event_type}_{timestamp}.jpg
            stem = f.stem  # frame_互动指令_123
            parts = stem.split("_", 2)  # ["frame", "互动指令", "123"]
            if len(parts) >= 3:
                event_type = parts[1]
                try:
                    timestamp = float(parts[2])
                except ValueError:
                    timestamp = 0.0
            else:
                event_type = "未知"
                timestamp = 0.0
            frames.append({
                "path": str(f.resolve()),
                "event_type": event_type,
                "timestamp": timestamp,
            })

        if not frames:
            return []

        # 确定时间范围
        all_timestamps = [f["timestamp"] for f in frames]
        t_min, t_max = min(all_timestamps), max(all_timestamps)
        duration = t_max - t_min
        if duration <= 0:
            # 所有帧同一时间 → 取前 max_frames 张
            return [f["path"] for f in frames[:max_frames]]

        # 事件类型优先级（越高越优先选）
        priority_map = {
            "互动指令": 4,
            "学生应答": 4,
            "教师反馈": 4,
            "知识节点": 3,
            "环节切换": 2,
            "节奏信号": 1,
        }

        # 按时间桶分组
        bucket_width = duration / bucket_count
        buckets: list[list[dict[str, Any]]] = [[] for _ in range(bucket_count)]
        for f in frames:
            bucket_idx = min(int((f["timestamp"] - t_min) / bucket_width), bucket_count - 1)
            buckets[bucket_idx].append(f)

        # 每个桶内排序（优先事件类型 > 高时间戳）
        for b in buckets:
            b.sort(key=lambda f: (
                -priority_map.get(f["event_type"], 0),
                -f["timestamp"],
            ))

        # 从每个桶取帧
        per_bucket = math.ceil(max_frames / bucket_count)
        sampled: list[str] = []
        type_seen: set[str] = set()
        # 第一轮：保证每种事件类型至少一帧
        remaining: list[dict[str, Any]] = []
        for b in buckets:
            for f in b:
                if f["event_type"] not in type_seen:
                    sampled.append(f["path"])
                    type_seen.add(f["event_type"])
                    break
            else:
                # 该桶没有新类型，收集候选
                remaining.extend(b[:per_bucket])

        # 第二轮：补齐到 max_frames
        if len(sampled) < max_frames:
            # 从每个桶补充
            for b in buckets:
                for f in b:
                    if f["path"] not in sampled:
                        sampled.append(f["path"])
                        if len(sampled) >= max_frames:
                            break
                if len(sampled) >= max_frames:
                    break

        logger.info(
            f"关键帧采样：{len(frames)} → {len(sampled)} 帧 "
            f"（{bucket_count}时间桶，每桶最多{per_bucket}帧）"
        )
        return sampled[:max_frames]

    @staticmethod
    def _merge_events(chunk_results: list[list[TeachingEvent]]) -> EventTimeline:
        """合并多段分析结果，基于时间戳去重。

        Args:
            chunk_results: 每段的分析结果

        Returns:
            EventTimeline: 合并后的事件时间轴
        """
        all_events: list[TeachingEvent] = []
        seen: set[tuple[str, float, float]] = set()

        for chunk_events in chunk_results:
            for event in chunk_events:
                # 用(event_type, start_time, end_time)作为去重键
                key = (event.event_type, round(event.start_time, 1), round(event.end_time, 1))
                if key not in seen:
                    seen.add(key)
                    all_events.append(event)

        # 按开始时间排序
        all_events.sort(key=lambda e: e.start_time)

        return EventTimeline(events=all_events)

    def _call_llm(self, messages: list[dict[str, Any]]) -> str:
        """调用LLM API，支持指数退避重试。支持多模态消息（文本+图像）。

        Args:
            messages: 消息列表，每条消息的 content 可以是字符串或 content block 列表

        Returns:
            str: LLM响应文本

        Raises:
            LLMAnalyzerError: 调用失败时抛出
        """
        max_retries = self.max_retries
        base_delay = 2.0

        for attempt in range(max_retries):
            try:
                response = self._client.chat.completions.create(
                    model=self.model,
                    messages=messages,
                    temperature=0.1,
                    max_tokens=8192,  # 长文本输入需足够输出空间容纳完整 JSON（含scoring_points）
                )
                content = response.choices[0].message.content or ""
                logger.debug(f"LLM响应长度：{len(content)} 字符")
                return content

            except Exception as e:
                if attempt < max_retries - 1:
                    delay = base_delay * (2 ** attempt)
                    logger.warning(
                        f"LLM调用失败（第 {attempt+1} 次），{delay}秒后重试：{e}"
                    )
                    time.sleep(delay)
                else:
                    raise LLMAnalyzerError(f"LLM调用失败（已重试{max_retries}次）：{e}")

        # 不应该到达这里，但类型检查需要
        raise LLMAnalyzerError("LLM调用失败")

    @staticmethod
    def _parse_events_response(response: str) -> list[TeachingEvent]:
        """解析LLM返回的教学事件JSON。

        Args:
            response: LLM响应文本

        Returns:
            list[TeachingEvent]: 解析出的教学事件列表
        """
        events: list[TeachingEvent] = []

        # 尝试从响应中提取JSON
        json_str = _extract_json(response)
        if not json_str:
            logger.warning("LLM响应中未找到JSON，尝试逐行解析")
            return events

        try:
            data = json.loads(json_str)
        except json.JSONDecodeError as e:
            logger.warning(f"LLM响应JSON解析失败：{e}")
            return events

        # 期望格式: [{"event_type": ..., "subtype": ..., ...}]
        if isinstance(data, list):
            items = data
        elif isinstance(data, dict):
            # 可能包装在events键下
            items = data.get("events", data.get("event_list", [data]))
        else:
            logger.warning(f"LLM响应JSON格式异常：{type(data)}")
            return events

        for item in items:
            if not isinstance(item, dict):
                continue
            try:
                event = TeachingEvent(
                    event_type=item.get("event_type", "未知"),
                    subtype=item.get("subtype", ""),
                    start_time=float(item.get("start_time", 0)),
                    end_time=float(item.get("end_time", 0)),
                    description=item.get("description", ""),
                    confidence=float(item.get("confidence", 0.5)),
                    related_text=item.get("related_text", ""),
                )
                events.append(event)
            except (ValueError, TypeError) as e:
                logger.warning(f"跳过无法解析的事件：{item}，错误：{e}")
                continue

        return events

    @staticmethod
    def _parse_quality_response(
        response: str,
        dimensions: list[ScoringDimensionConfig],
    ) -> tuple[list[QualityCheckItem], list[ScoreDimension]]:
        """解析LLM返回的质量评估结果。

        Args:
            response: LLM响应文本
            dimensions: 评分维度配置

        Returns:
            tuple: (质检清单结果, 评分维度结果)
        """
        check_items: list[QualityCheckItem] = []
        score_dimensions: list[ScoreDimension] = []

        json_str = _extract_json(response)
        if not json_str:
            logger.warning("LLM响应中未找到JSON，使用默认结果")
            # 返回空结果
            for dim in dimensions:
                score_dimensions.append(ScoreDimension(
                    name=dim.name,
                    score=0.0,
                    max_score=dim.weight * 100,
                    weight=dim.weight,
                    evidence="LLM响应解析失败",
                    grade="差",
                ))
            return check_items, score_dimensions

        try:
            data = json.loads(json_str)
        except json.JSONDecodeError as e:
            logger.warning(f"LLM质量评估响应JSON解析失败：{e}")
            return check_items, score_dimensions

        # 类型检查：LLM可能返回JSON数组而非对象
        # 常见偏离格式：
        #   1) [{"checklist":...}, ...]  → 多个完整响应，取第一个
        #   2) [{"name":"知识传授","score":8.5}, ...]  → 直接是 scores 数组
        #   3) [{"description":...}, ...]  → 直接是 checklist 数组
        if isinstance(data, list):
            if len(data) > 0 and isinstance(data[0], dict):
                first_elem = data[0]
                # 情况1：第一个元素是完整响应对象（含 checklist/scores/red_lines 键）
                if "checklist" in first_elem or "scores" in first_elem or "red_lines" in first_elem:
                    logger.warning("LLM质量评估返回了JSON数组（多响应），使用第一个元素")
                    data = first_elem
                # 情况2：数组元素看起来是评分维度（含 name + score 键）
                elif "name" in first_elem and "score" in first_elem:
                    logger.warning("LLM质量评估返回了JSON数组（scores格式），自动包装")
                    data = {"scores": data, "checklist": [], "red_lines": []}
                # 情况3：数组元素看起来是质检项（含 description + passed 键）
                elif "description" in first_elem and "passed" in first_elem:
                    logger.warning("LLM质量评估返回了JSON数组（checklist格式），自动包装")
                    data = {"checklist": data, "scores": [], "red_lines": []}
                else:
                    # 未知结构：记录键名以便调试
                    keys_sample = list(first_elem.keys())[:5]
                    logger.warning(f"LLM质量评估返回的JSON数组格式无法识别，键样本：{keys_sample}")
                    return check_items, score_dimensions
            else:
                logger.warning("LLM质量评估返回的JSON数组为空或元素类型异常")
                return check_items, score_dimensions
        elif not isinstance(data, dict):
            logger.warning(f"LLM质量评估响应JSON类型异常：{type(data)}")
            return check_items, score_dimensions

        # 解析质检清单结果
        checklist_data = data.get("checklist", [])
        red_line_data = data.get("red_lines", [])
        # 合并红线检测结果到质检清单
        all_check_data = checklist_data + red_line_data
        for item in all_check_data:
            if not isinstance(item, dict):
                continue
            try:
                is_red = bool(item.get("is_red_line", False))
                check_items.append(QualityCheckItem(
                    description=item.get("description", ""),
                    passed=bool(item.get("passed", False)),
                    evidence=item.get("evidence", ""),
                    timestamp=item.get("timestamp"),
                    is_red_line=is_red,
                ))
            except (ValueError, TypeError):
                continue

        # 解析评分维度：按名称对齐（防止 LLM 返回顺序与配置不一致）
        dim_by_name: dict[str, ScoringDimensionConfig] = {d.name: d for d in dimensions}
        scores_data = data.get("scores", [])
        # 第一步：按名称解析所有维度分数
        parsed_scores: dict[str, ScoreDimension] = {}
        for item in scores_data:
            if not isinstance(item, dict):
                continue
            item_name = item.get("name", "")
            dim_config = dim_by_name.get(item_name)
            if dim_config is None:
                # 尝试模糊匹配（LLM 可能返回相近但不完全相同的名称）
                dim_config = _fuzzy_match_dimension(item_name, dimensions)
                if dim_config:
                    logger.warning(
                        f"LLM 返回的维度名 '{item_name}' 通过模糊匹配映射到 '{dim_config.name}'"
                    )
                else:
                    # 未知维度，跳过（可能是 LLM 编造的维度名）
                    logger.warning(f"LLM 返回了未知维度 '{item_name}'（无法模糊匹配），已跳过")
                    continue
            try:
                score_val = float(item.get("score", 0))
                # 从YAML配置读取max_score（10分制），默认100
                dim_max = dim_config.max_score if hasattr(dim_config, 'max_score') and dim_config.max_score else 100
                # 将原始分按维度满分换算为百分比，再乘以权重得到加权分
                # 例如：8分/10分制 → 80% → 0.8 * 0.1 * 100 = 8.0
                max_score = dim_config.weight * 100
                score_val = (score_val / dim_max) * max_score
                # 截断：确保分数不超过维度满分（LLM可能返回越界值）
                score_val = max(0.0, min(score_val, max_score))

                # 读取时间戳
                timestamp_val = item.get("timestamp")
                if timestamp_val is not None:
                    timestamp_val = float(timestamp_val)
                else:
                    timestamp_val = None

                # 解析 scoring_points（多证据点数组）
                sp_list = item.get("scoring_points", [])
                scoring_points: list[ScoringPoint] = []
                for sp in sp_list:
                    if not isinstance(sp, dict):
                        continue
                    try:
                        scoring_points.append(ScoringPoint(
                            point_type=sp.get("type", ""),
                            reason=sp.get("reason", ""),
                            quote=sp.get("quote", ""),
                            at=float(sp.get("at")) if sp.get("at") is not None else None,
                            duration=float(sp.get("duration")) if sp.get("duration") is not None else None,
                        ))
                    except (ValueError, TypeError):
                        continue

                parsed_scores[dim_config.name] = ScoreDimension(
                    name=dim_config.name,
                    score=score_val,
                    max_score=max_score,
                    weight=dim_config.weight,
                    evidence=item.get("evidence", ""),
                    details=item.get("details", ""),
                    timestamp=timestamp_val,
                    scoring_points=scoring_points,
                )
            except (ValueError, TypeError):
                continue

        # 第二步：按配置维度顺序输出（保证一致性）
        for dim_config in dimensions:
            if dim_config.name in parsed_scores:
                score_dimensions.append(parsed_scores[dim_config.name])
            else:
                # 该维度未被 LLM 返回，用默认值填充
                score_dimensions.append(ScoreDimension(
                    name=dim_config.name,
                    score=0.0,
                    max_score=dim_config.weight * 100,
                    weight=dim_config.weight,
                    evidence="未获得评估结果",
                    grade="差",
                ))

        return check_items, score_dimensions

    def _build_event_detection_prompt(
        self,
        transcript_chunk: str,
        event_types: list[str],
    ) -> str:
        """构建教学事件识别Prompt。"""
        event_types_str = "、".join(event_types)

        if self._prompt_templates:
            try:
                return self._prompt_templates.render(
                    "event_detection",
                    transcript_chunk=transcript_chunk,
                    event_types=event_types_str,
                )
            except Exception as e:
                logger.warning(f"使用Prompt模板失败，回退默认模板：{e}")

        # 默认Prompt
        return f"""请分析以下课堂转录文本，识别其中的教学事件。

## 需要识别的事件类型
{event_types_str}

## 课堂转录文本
{transcript_chunk}

## 输出格式
请以JSON数组格式输出，每个事件包含以下字段：
- event_type: 事件类型（如"环节切换"、"互动指令"等）
- subtype: 事件子类型
- start_time: 事件开始时间（秒，浮点数）
- end_time: 事件结束时间（秒，浮点数）
- description: 事件描述
- confidence: 置信度（0.0-1.0）
- related_text: 相关原文

请仅输出JSON，不要输出其他内容。"""

    def _truncate_transcript(self, text: str) -> str:
        """截断超长转录文本，防止 LLM 输入过大导致超时。

        策略：
        - 如果文本在 _MAX_TRANSCRIPT_CHARS 以内，不做处理
        - 超出时：取 前60% + 后20% 的内容，中间保留摘要提示
        """
        max_chars = self._MAX_TRANSCRIPT_CHARS
        if len(text) <= max_chars:
            return text

        head_ratio = 0.6
        tail_ratio = 0.2
        head_size = int(max_chars * head_ratio)
        tail_size = int(max_chars * tail_ratio)

        head = text[:head_size]
        tail = text[-tail_size:]

        truncated = (
            head
            + f"\n\n... [中间部分已截断，原转录共 {len(text)} 字符，"
            f"已保留开头 {head_size} 字符和结尾 {tail_size} 字符] ...\n\n"
            + tail
        )
        logger.info(
            f"转录文本截断：{len(text)} → {len(truncated)} 字符 "
            f"（保留前{head_size}+后{tail_size}）"
        )
        return truncated

    def _truncate_events(
        self, events_json: str, events: EventTimeline
    ) -> str:
        """截断超长事件 JSON，防止 LLM 输入过大。

        策略：
        - JSON 字符串在 _MAX_EVENTS_CHARS 以内：不做处理
        - 超出时：按置信度排序，保留 Top-N 个事件
        """
        if len(events_json) <= self._MAX_EVENTS_CHARS:
            return events_json

        # 按置信度从高到低排序，取 Top-N
        sorted_events = sorted(
            events.events,
            key=lambda e: e.confidence if e.confidence else 0.0,
            reverse=True,
        )
        top_events = sorted_events[: self._MAX_EVENT_COUNT]
        # 按时间重新排序
        top_events.sort(key=lambda e: e.start_time)
        top_timeline = EventTimeline(events=top_events)
        truncated = top_timeline.to_json()
        logger.info(
            f"事件截断：{len(events.events)} → {len(top_events)} 个"
            f"（按置信度取 Top-{self._MAX_EVENT_COUNT}）"
        )
        return truncated

    def _build_quality_assessment_prompt(
        self,
        transcript: str,
        events_json: str,
        checklist: str,
        dimensions_desc: str,
        prompt_version: str = "standard",
        level: str = "QC-v4",
        dimension_names: str = "",
        visual_context: Optional[str] = None,
        interaction_chains: Optional[str] = None,
    ) -> str:
        """构建质量评估Prompt。"""
        # 根据版本选择模板名
        template_name = "quality_assessment"
        if prompt_version == "spark_standard":
            template_name = "quality_assessment"  # 已更新为火花标准版

        if self._prompt_templates:
            try:
                rendered = self._prompt_templates.render(
                    template_name,
                    transcript=transcript,
                    events_json=events_json,
                    checklist=checklist,
                    dimensions=dimensions_desc,
                    level=level,
                    dimension_names=dimension_names,
                    interaction_chains=interaction_chains or "（未检测到明显的教学互动链）",
                )
                # 注入视觉上下文（如有）：在转录文本之后、评分标准之前插入
                if visual_context and visual_context.strip():
                    visual_block = (
                        "\n\n## 课堂视觉观察报告（来自视觉模型对关键帧的分析）\n\n"
                        "以下是视觉模型通过观察课堂关键帧截图生成的行为描述报告。"
                        "请将这些视觉信息作为评分的重要参考依据，"
                        "特别是对于**关注公平**（学生参与均衡性）、**教学方式方法**（互动类型）、"
                        "**仪表教态**、**语言表达及板书设计**等维度。\n\n"
                        f"{visual_context}\n"
                    )
                    # 在课堂转录文本之后插入视觉报告
                    insertion_marker = "## 四、教学事件"
                    if insertion_marker in rendered:
                        rendered = rendered.replace(insertion_marker, visual_block + insertion_marker)
                    else:
                        rendered = rendered + visual_block
                return rendered
            except Exception as e:
                logger.warning(f"使用Prompt模板失败，回退默认模板：{e}")

        # 默认Prompt — 含评分区间精确定义和scoring_points证据数组（P0-2 + P0-1）
        return f"""请评估以下课堂教学的质量。

## 课堂转录文本
{transcript}

## 教学事件
{events_json}

## 质检清单
{checklist}

## 评分维度
{dimensions_desc}

## 评分等级标准（非常重要）

采用**4级10分制**评分体系，区间均使用精确数学区间，9分属于"优"而非"良"：

| 等级 | 区间 | 行为特征 |
|------|------|---------|
| **优** | [9, 10] 即 9 ≤ 分数 ≤ 10 | 该维度表现突出，符合高阶要求 |
| **良** | [7, 9) 即 7 ≤ 分数 < 9 | 该维度表现良好，达到标准要求 |
| **中** | [5, 7) 即 5 ≤ 分数 < 7 | 该维度表现一般，有明显改进空间 |
| **差** | [0, 5) 即 0 ≤ 分数 < 5 | 该维度表现较差，不符合基本要求 |

## 教师等级判定标准

| 总分范围 | 教师等级 | 说明 |
|---------|---------|------|
| [90, 100] | **创新** | 教学表现卓越，可作为培训素材 |
| [70, 90) | **挑战** | 教学能力良好，有提升空间 |
| [50, 70) | **博学** | 基本达标，需要系统培训 |
| [0, 50) | **不合格** | 未达标，需要重点改进或淘汰 |

## 输出格式

请以JSON格式输出，包含以下内容：
{{
    "checklist": [
        {{
            "description": "检查项描述",
            "passed": true/false,
            "evidence": "证据说明",
            "timestamp": 时间戳（秒，浮点数或null）
        }}
    ],
    "scores": [
        {{
            "name": "维度名称",
            "score": 分数（0-10，10分制）,
            "evidence": "评分依据概述（必须含时间戳如[01:23]）",
            "details": "详细分析说明",
            "timestamp": 关键证据对应的时间点（秒，浮点数，如65.0）,
            "grade": "优/良/中/差",
            "scoring_points": [
                {{
                    "type": "+",
                    "reason": "开放式提问，激发学生思考",
                    "quote": "你觉得这道题还可以怎么想？",
                    "at": 142.0
                }},
                {{
                    "type": "+",
                    "reason": "等待学生充分思考后才追问",
                    "quote": "（等待4秒）好，小明你先说说看",
                    "at": 158.0,
                    "duration": 4.2
                }},
                {{
                    "type": "-",
                    "reason": "直接给出答案而非继续引导",
                    "quote": "其实答案就是105",
                    "at": 195.0
                }}
            ]
        }}
    ]
}}

## scoring_points 要求（非常重要）

- 每个评分维度至少提供 3 个 scoring_points（含加分和扣分）
- type 必须是 "+"（加分）或 "-"（扣分）
- quote 必须是从转录文本中提取的原文，不可编造
- at 必须是对应的时间点（秒，浮点数）
- duration 仅在有意义的持续行为时填写（如等待时长、朗读时长），否则省略该字段
- evidence 字段为维度整体评分依据概述，scoring_points 为逐分证据细节

## 时间戳要求

- 所有 evidence 字段**必须**包含精确的时间戳，格式为 [MM:SS] 或 [HH:MM:SS]
- 不要使用模糊描述（如"开头"、"中间"），必须给出具体时间点

CRITICAL: 你的输出必须同时包含 "checklist" 和 "scores" 两个顶层字段。
- checklist: 所有质检项（红线+常规检查）的判定结果
- scores: 所有10个评分维度的评分（0-10分制）、evidence、scoring_points
如果只输出 checklist 不输出 scores，整个评估将失效。

请仅输出JSON，不要输出其他内容。"""


def _extract_json(text: str) -> str | None:
    """从文本中提取JSON字符串。

    支持：
    - 纯JSON
    - Markdown代码块包裹的JSON
    - 前后有其他文字的JSON

    Args:
        text: 可能包含JSON的文本

    Returns:
        str | None: 提取的JSON字符串，未找到返回None
    """
    # 尝试直接解析
    text_stripped = text.strip()
    if text_stripped.startswith(("[", "{")):
        try:
            json.loads(text_stripped)
            return text_stripped
        except json.JSONDecodeError:
            pass

    # 尝试从Markdown代码块提取
    pattern = r"```(?:json)?\s*\n([\s\S]*?)\n```"
    matches = re.findall(pattern, text)
    for match in matches:
        try:
            json.loads(match)
            return match
        except json.JSONDecodeError:
            continue

    # 尝试查找第一个完整的JSON对象或数组
    for start_char, end_char in [("{", "}"), ("[", "]")]:
        start_idx = text.find(start_char)
        if start_idx == -1:
            continue
        # 从后往前找匹配的结束符
        depth = 0
        for i in range(start_idx, len(text)):
            if text[i] == start_char:
                depth += 1
            elif text[i] == end_char:
                depth -= 1
            if depth == 0:
                candidate = text[start_idx:i + 1]
                try:
                    json.loads(candidate)
                    return candidate
                except json.JSONDecodeError:
                    break

    return None


def _closest_to_median_index(scores: list[float]) -> int:
    """返回最接近中位数的元素索引。

    用于从多轮评估中选择"最有代表性"的那轮结果作为 evidence/details 来源。

    Args:
        scores: 各轮分数列表

    Returns:
        int: 最接近中位数的索引
    """
    if len(scores) <= 1:
        return 0
    sorted_scores = sorted(scores)
    median = statistics.median(sorted_scores)
    # 找最接近中位数的那个
    best_idx = 0
    best_dist = abs(scores[0] - median)
    for i, s in enumerate(scores):
        dist = abs(s - median)
        if dist < best_dist:
            best_dist = dist
            best_idx = i
    return best_idx


def _merge_scoring_points(
    all_points: list[ScoringPoint],
    quote_overlap_threshold: float = 0.6,
) -> list[ScoringPoint]:
    """合并多轮评估的 scoring_points，去重。

    去重规则：
    1. 完全相同的 (type, quote) → 保留一个
    2. quote 有较高重叠（>60% 共同字符比例）且 type 相同 → 保留较长的那个
    3. 按 at 时间戳排序输出

    Args:
        all_points: 所有轮次的 scoring_points
        quote_overlap_threshold: quote 重叠阈值（0.0-1.0）

    Returns:
        list[ScoringPoint]: 去重合并后的证据点列表
    """
    if not all_points:
        return []

    merged: list[ScoringPoint] = []

    for sp in all_points:
        is_dup = False
        for existing in merged:
            # 完全相同
            if sp.point_type == existing.point_type and sp.quote == existing.quote:
                is_dup = True
                break
            # 高度重叠
            if sp.point_type == existing.point_type and _quote_overlap(sp.quote, existing.quote) >= quote_overlap_threshold:
                # 保留较长的 quote
                if len(sp.quote) > len(existing.quote):
                    existing.quote = sp.quote
                    existing.reason = sp.reason
                    if sp.at is not None:
                        existing.at = sp.at
                is_dup = True
                break
        if not is_dup:
            merged.append(ScoringPoint(
                point_type=sp.point_type,
                reason=sp.reason,
                quote=sp.quote,
                at=sp.at,
                duration=sp.duration,
            ))

    # 按时间戳排序
    merged.sort(key=lambda p: p.at if p.at is not None else float('inf'))
    return merged


def _quote_overlap(q1: str, q2: str) -> float:
    """计算两个 quote 的重叠度（Jaccard-like）。

    使用字符集重叠比例：交集字符数 / 较短quote字符数。

    Args:
        q1, q2: 两段引用文本

    Returns:
        float: 重叠度 0.0-1.0
    """
    if not q1 or not q2:
        return 0.0
    set1 = set(q1)
    set2 = set(q2)
    if not set1 or not set2:
        return 0.0
    intersection = set1 & set2
    return len(intersection) / min(len(set1), len(set2))


# 维度名称模糊匹配映射表（LLM可能返回的相近名称 → 配置标准名称）
# 用于当非QC-v4班型使用QC-v4.1子维度规则导致LLM混淆时的兜底
_FUZZY_NAME_MAP: dict[str, dict[str, str]] = {
    "L1_L3": {
        "启发引导": "教学方式方法",
        "教学灵活性": "教学逻辑",
        "课堂互动": "关注公平",
        "课堂节奏": "组织教学",
        "仪表举止": "仪表教态",
        "学习效果": "课堂效果及整体印象",
    },
    "L4_L6": {
        "启发引导": "教学方式方法",
        "教学方法灵活应用": "教学逻辑",
        "关注互动": "关注公平",
        "迁移应用": "课堂效果及整体印象",
        "效果外化": "课堂效果及整体印象",
    },
    "L7_L9": {
        "启发引导": "教学方式方法",
        "教学方法灵活应用": "教学逻辑",
        "关注互动": "关注公平",
        "迁移应用": "课堂效果及整体印象",
        "效果外化": "课堂效果及整体印象",
    },
}


def _fuzzy_match_dimension(
    llm_name: str, dimensions: list[ScoringDimensionConfig],
) -> Optional[ScoringDimensionConfig]:
    """模糊匹配LLM返回的维度名称到配置中的标准名称。

    策略：
    1. 精确匹配（已在外层尝试）
    2. 查预定义映射表
    3. 移除所有空格/标点后比较（最宽松）

    Args:
        llm_name: LLM返回的维度名称
        dimensions: 配置维度列表

    Returns:
        Optional[ScoringDimensionConfig]: 匹配的维度配置，未匹配返回None
    """
    # 策略2：预定义映射表（用于已知的 LLM 常见偏差）
    # 映射表键为 LLM 可能返回的名称，值为配置中的标准名称
    known_aliases: dict[str, str] = {
        # L1-L3/L4-L6/L7-L9 → QC-v4 映射
        "启发引导": "教学方式方法",
        "教学灵活性": "教学逻辑",
        "教学方法灵活应用": "教学方式方法",
        "课堂互动": "关注公平",
        "关注互动": "关注公平",
        "学生参与": "关注公平",
        "参与公平": "关注公平",
        "互动公平": "关注公平",
        "课堂节奏": "组织教学",
        "仪表举止": "仪表教态",
        "教师仪态": "仪表教态",
        "仪表仪态": "仪表教态",
        "仪表仪态与教态": "仪表教态",
        "教态仪表": "仪表教态",
        "板书设计": "语言表达及板书设计",
        "语言表达": "语言表达及板书设计",
        "语言表达与板书": "语言表达及板书设计",
        "语言表达与板书设计": "语言表达及板书设计",
        "板书与课件": "语言表达及板书设计",
        "课件板书": "语言表达及板书设计",
        "学习效果": "课堂效果及整体印象",
        "课堂氛围": "课堂效果及整体印象",
        "整体印象": "课堂效果及整体印象",
        "课堂效果": "课堂效果及整体印象",
        "迁移应用": "课堂效果及整体印象",
        "效果外化": "课堂效果及整体印象",
        # QC-v4 → 旧班型映射（反向）
        "教学方式方法": "启发引导",
        "关注公平": "关注互动",
        "组织教学": "课堂节奏",
        "课堂效果及整体印象": "效果外化",
    }
    mapped_name = known_aliases.get(llm_name, "")
    if mapped_name:
        for dim in dimensions:
            if dim.name == mapped_name:
                return dim

    # 策略3：标准化后比较（去除非字母数字中文）
    def _normalize(s: str) -> str:
        return re.sub(r'[\s\W_]+', '', s)

    llm_normalized = _normalize(llm_name)
    for dim in dimensions:
        if _normalize(dim.name) == llm_normalized:
            return dim

    return None
