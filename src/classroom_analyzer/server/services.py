"""服务层 — 任务管理与分析管线编排"""

from __future__ import annotations

import math
import threading
import uuid
import json
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Optional

from loguru import logger

from classroom_analyzer.paths import get_data_dir, get_project_root
from classroom_analyzer.server import database as db

# 项目根目录
PROJECT_ROOT = get_project_root()
DATA_DIR = get_data_dir()
UPLOAD_DIR = DATA_DIR / "uploads"
RESULTS_DIR = DATA_DIR / "results"
CONFIG_PATH = PROJECT_ROOT / "config" / "default.yaml"
API_KEYS_PATH = PROJECT_ROOT / "config" / "api_keys.json"

# 确保目录存在
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
RESULTS_DIR.mkdir(parents=True, exist_ok=True)

# 允许的视频格式
ALLOWED_EXTENSIONS = {"mp4", "mov", "mkv", "webm", "flv", "avi"}
MAX_FILE_SIZE = 2 * 1024 * 1024 * 1024  # 2GB

# 分块上传配置
CHUNK_DIR = DATA_DIR / ".chunks"  # 分块临时目录
CHUNK_SIZE = 5 * 1024 * 1024  # 5MB 每块（小到能塞进 Cloudflare 100s 超时）

# 管线步骤到状态的映射
_STEP_STATUS_MAP: dict[int, str] = {
    0: "extracting",
    1: "extracting",
    2: "transcribing",
    3: "analyzing",
    4: "analyzing",
    5: "scoring",
    6: "scoring",
}

# 管线步骤到中文阶段描述
_STEP_STAGE_MAP: dict[int, str] = {
    0: "读取视频文件",
    1: "提取音频",
    2: "语音识别（ASR）",
    3: "智能语义分析（事件识别）",
    4: "关键帧提取与视觉证据准备",
    5: "生成质检报告（含文本评分与视觉评分）",
    6: "分析完成",
}


class TaskService:
    """任务管理服务：创建、启动、查询分析任务。"""

    @staticmethod
    def create_task(
        filename: str,
        file_content: bytes,
        extension: str,
        metadata: dict[str, Any] | None = None,
    ) -> str:
        """创建新任务，保存上传的视频文件。

        Args:
            filename: 原始文件名
            file_content: 视频文件二进制内容
            extension: 文件扩展名

        Returns:
            task_id: 任务 UUID

        Raises:
            ValueError: 文件格式不支持或文件过大
        """
        # 校验扩展名
        ext = extension.lower().lstrip(".")
        if ext not in ALLOWED_EXTENSIONS:
            raise ValueError(f"不支持的视频格式：.{ext}，支持：{', '.join(ALLOWED_EXTENSIONS)}")

        # 校验大小
        if len(file_content) > MAX_FILE_SIZE:
            raise ValueError(f"文件过大，最大支持 2GB")

        # 生成任务 ID
        task_id = uuid.uuid4().hex

        # 保存视频文件
        task_upload_dir = UPLOAD_DIR / task_id
        task_upload_dir.mkdir(parents=True, exist_ok=True)
        video_path = task_upload_dir / f"video.{ext}"
        video_path.write_bytes(file_content)
        logger.info(f"视频已保存：{video_path}（{len(file_content)} bytes）")

        # 写入数据库
        db.create_task(
            task_id,
            filename,
            str(video_path),
            json.dumps(metadata or {}, ensure_ascii=False),
        )

        return task_id

    @staticmethod
    def start_analysis(task_id: str, level: str = "QC-v4") -> None:
        """在后台线程启动分析管线。

        Args:
            task_id: 任务 ID
            level: 班型等级
        """
        task = db.get_task(task_id)
        if task is None:
            raise ValueError(f"任务不存在：{task_id}")
        if task["status"] not in ("pending", "failed"):
            raise ValueError(f"任务状态不允许启动分析：{task['status']}")

        # 更新状态为 extracting
        db.mark_task_started(task_id, "extracting", "准备开始分析...")

        # 启动后台线程
        thread = threading.Thread(
            target=_run_analysis_thread,
            args=(task_id, task["video_path"], level),
            daemon=True,
        )
        thread.start()
        logger.info(f"分析线程已启动：task_id={task_id}, level={level}")

    @staticmethod
    def get_task_detail(task_id: str) -> Optional[dict[str, Any]]:
        """获取任务详情。"""
        return db.get_task(task_id)

    @staticmethod
    def get_task_status(task_id: str) -> Optional[dict[str, Any]]:
        """获取任务状态（轮询用）。"""
        return db.get_task_status(task_id)

    @staticmethod
    def get_tasks(
        page: int = 1,
        page_size: int = 10,
        keyword: str = "",
    ) -> tuple[list[dict[str, Any]], int]:
        """获取任务列表。"""
        if keyword:
            return db.search_tasks(keyword, page, page_size)
        return db.get_tasks(page, page_size)

    @staticmethod
    def get_video_path(task_id: str) -> Optional[str]:
        """获取任务的视频文件路径。"""
        task = db.get_task(task_id)
        if task is None:
            return None
        return task["video_path"]

    # ── 分块上传 ──

    @staticmethod
    def init_chunked_upload(filename: str, extension: str, total_size: int) -> str:
        """初始化分块上传，返回 upload_id。

        Args:
            filename: 原始文件名
            extension: 文件扩展名
            total_size: 文件总大小（字节）
        """
        ext = extension.lower().lstrip(".")
        if ext not in ALLOWED_EXTENSIONS:
            raise ValueError(f"不支持的视频格式：.{ext}，支持：{', '.join(ALLOWED_EXTENSIONS)}")
        if total_size > MAX_FILE_SIZE:
            raise ValueError(f"文件过大，最大支持 2GB")

        upload_id = uuid.uuid4().hex
        chunk_dir = CHUNK_DIR / upload_id
        chunk_dir.mkdir(parents=True, exist_ok=True)
        total_chunks = max(1, math.ceil(total_size / CHUNK_SIZE))

        # 保存元信息
        meta = {
            "filename": filename,
            "extension": ext,
            "total_size": total_size,
            "chunk_size": CHUNK_SIZE,
            "total_chunks": total_chunks,
            "created_at": datetime.now().isoformat(),
        }
        (chunk_dir / "meta.json").write_text(
            __import__("json").dumps(meta, ensure_ascii=False),
            encoding="utf-8",
        )

        logger.info(f"分块上传初始化：upload_id={upload_id}, filename={filename}, size={total_size}")
        return upload_id

    @staticmethod
    def upload_chunk(upload_id: str, chunk_index: int, chunk_data: bytes) -> None:
        """上传单个分块。

        Args:
            upload_id: 上传会话 ID
            chunk_index: 分块序号（从 0 开始）
            chunk_data: 分块二进制数据
        """
        chunk_dir = CHUNK_DIR / upload_id
        if not chunk_dir.exists():
            raise ValueError(f"上传会话不存在：{upload_id}")
        meta_path = chunk_dir / "meta.json"
        if not meta_path.exists():
            raise ValueError(f"上传会话元信息丢失：{upload_id}")

        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        total_chunks = int(meta.get("total_chunks") or 0)
        chunk_size = int(meta.get("chunk_size") or CHUNK_SIZE)
        total_size = int(meta.get("total_size") or 0)
        if chunk_index < 0 or chunk_index >= total_chunks:
            raise ValueError(f"分块序号超出范围：{chunk_index}，应为 0-{max(total_chunks - 1, 0)}")
        if not chunk_data:
            raise ValueError(f"分块 {chunk_index} 为空，请重新上传该分块")

        expected_size = chunk_size if chunk_index < total_chunks - 1 else total_size - chunk_size * (total_chunks - 1)
        if len(chunk_data) != expected_size:
            raise ValueError(
                f"分块 {chunk_index} 大小不匹配：期望 {expected_size} bytes，实际 {len(chunk_data)} bytes"
            )

        chunk_path = chunk_dir / f"{chunk_index:06d}.part"
        chunk_path.write_bytes(chunk_data)
        logger.debug(f"分块 {chunk_index} 已保存：{len(chunk_data)} bytes")

    @staticmethod
    def get_chunked_upload_status(upload_id: str) -> dict[str, Any]:
        """获取分块上传会话状态，用于前端排查和断点重试。"""
        chunk_dir = CHUNK_DIR / upload_id
        if not chunk_dir.exists():
            raise ValueError(f"上传会话不存在：{upload_id}")
        meta_path = chunk_dir / "meta.json"
        if not meta_path.exists():
            raise ValueError(f"上传会话元信息丢失：{upload_id}")

        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        total_chunks = int(meta.get("total_chunks") or 0)
        received = sorted(
            int(path.stem)
            for path in chunk_dir.glob("*.part")
            if path.stem.isdigit()
        )
        received_set = set(received)
        missing = [index for index in range(total_chunks) if index not in received_set]
        return {
            "upload_id": upload_id,
            "filename": meta.get("filename", ""),
            "total_size": int(meta.get("total_size") or 0),
            "chunk_size": int(meta.get("chunk_size") or CHUNK_SIZE),
            "total_chunks": total_chunks,
            "received_chunks": len(received),
            "missing_chunks": missing,
            "complete": total_chunks > 0 and not missing,
        }

    @staticmethod
    def complete_chunked_upload(
        upload_id: str,
        level: str = "QC-v4",
        metadata: dict[str, Any] | None = None,
    ) -> str:
        """组装分块、创建任务并启动分析。

        Args:
            upload_id: 上传会话 ID
            level: 班型等级

        Returns:
            task_id: 创建的任务 ID
        """
        chunk_dir = CHUNK_DIR / upload_id
        if not chunk_dir.exists():
            raise ValueError(f"上传会话不存在：{upload_id}")

        meta_path = chunk_dir / "meta.json"
        if not meta_path.exists():
            raise ValueError(f"上传会话元信息丢失：{upload_id}")

        meta = __import__("json").loads(meta_path.read_text(encoding="utf-8"))
        filename = meta["filename"]
        ext = meta["extension"]
        total_size = meta["total_size"]
        chunk_size = int(meta.get("chunk_size") or CHUNK_SIZE)
        total_chunks = int(meta.get("total_chunks") or max(1, math.ceil(total_size / chunk_size)))

        expected_files = [chunk_dir / f"{index:06d}.part" for index in range(total_chunks)]
        missing = [index for index, path in enumerate(expected_files) if not path.exists()]
        if len(missing) == total_chunks:
            raise ValueError(f"没有收到任何分块：{upload_id}")
        if missing:
            preview = ", ".join(str(index) for index in missing[:10])
            suffix = "..." if len(missing) > 10 else ""
            raise ValueError(f"分块上传不完整，缺少 {len(missing)} 个分块：{preview}{suffix}。请重新上传缺失分块后再提交。")

        logger.info(f"开始组装分块：upload_id={upload_id}, chunks={len(expected_files)}")

        # 创建任务
        task_id = uuid.uuid4().hex
        task_upload_dir = UPLOAD_DIR / task_id
        task_upload_dir.mkdir(parents=True, exist_ok=True)
        video_path = task_upload_dir / f"video.{ext}"

        # 按序拼接分块
        assembled_size = 0
        with open(video_path, "wb") as outfile:
            for part_file in expected_files:
                data = part_file.read_bytes()
                outfile.write(data)
                assembled_size += len(data)

        logger.info(f"分块拼接完成：{video_path}（{assembled_size} bytes）")

        # 校验大小
        if assembled_size != total_size:
            # 清理
            video_path.unlink(missing_ok=True)
            raise ValueError(f"文件大小不匹配：期望 {total_size}，实际 {assembled_size}")

        # 写入数据库
        db.create_task(
            task_id,
            filename,
            str(video_path),
            json.dumps(metadata or {}, ensure_ascii=False),
        )

        # 清理分块临时目录
        __import__("shutil").rmtree(str(chunk_dir), ignore_errors=True)
        logger.info(f"分块临时目录已清理：{chunk_dir}")

        # 启动分析
        TaskService.start_analysis(task_id, level=level)

        return task_id


def _make_progress_callback(task_id: str) -> Callable[[float, str], None]:
    """创建管线进度回调，桥接到数据库更新。支持 float 步进以实现精细进度。"""

    def callback(step: float, message: str) -> None:
        int_step = int(step)
        status = _STEP_STATUS_MAP.get(int_step, "analyzing")
        # float step → 百分比：step=0→0%, step=1→17%, ..., step=6→100%
        progress = min(int(step / 6 * 100), 100)
        stage = message or _STEP_STAGE_MAP.get(int_step, message)
        db.update_task_status(task_id, status, progress, stage)
        logger.debug(f"任务 {task_id} 进度：step={step:.1f}, status={status}, progress={progress}%, stage={stage}")

    return callback


def _run_analysis_thread(task_id: str, video_path: str, level: str) -> None:
    """在后台线程中运行分析管线。"""
    try:
        # 延迟导入，避免循环依赖
        from classroom_analyzer.config import ConfigManager
        from classroom_analyzer.pipeline import AnalysisPipeline

        # 加载配置
        config_manager = ConfigManager(
            config_path=str(CONFIG_PATH),
            api_keys_path=str(API_KEYS_PATH),
        )
        app_config = config_manager.load(level=level)
        task = db.get_task(task_id) or {}
        try:
            task_metadata = json.loads(task.get("metadata_json") or "{}")
        except Exception:
            task_metadata = {}
        if isinstance(task_metadata, dict):
            for key in ("analysis_mode", "video_scope", "analysis_purpose", "course_system", "class_type"):
                value = task_metadata.get(key)
                if value:
                    app_config.analysis_config[key] = value

        # 创建输出目录
        output_dir = RESULTS_DIR / task_id
        output_dir.mkdir(parents=True, exist_ok=True)

        # 创建管线并执行
        pipeline = AnalysisPipeline(app_config, force=False)
        result = pipeline.run(
            video_path=video_path,
            output_dir=str(output_dir),
            progress_callback=_make_progress_callback(task_id),
        )

        # 提取评分数据
        if result.score_card is not None:
            scoring_data = result.score_card.to_json()
            total_score = result.score_card.total_score
            grade = result.score_card.grade
        else:
            scoring_data = "{}"
            total_score = 0.0
            grade = "无评分"

        # 标记完成
        db.update_task_completed(task_id, total_score, grade, scoring_data)
        logger.info(f"分析完成：task_id={task_id}, score={total_score}, grade={grade}")

    except Exception as e:
        error_msg = f"分析失败：{str(e)}"
        logger.error(f"任务 {task_id} {error_msg}", exc_info=True)
        db.update_task_failed(task_id, error_msg)
