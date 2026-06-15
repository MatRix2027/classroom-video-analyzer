"""任务 API 路由"""

from __future__ import annotations

import asyncio
import html as html_module
import typing
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, HTTPException, Query, Request, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, StreamingResponse
from pydantic import BaseModel

from classroom_analyzer.server.models import (
    HealthResponse,
    TaskCreated,
    TaskDetailResponse,
    TaskListResponse,
    TaskListItem,
    TaskStatusResponse,
)
from classroom_analyzer.server.services import TaskService

router = APIRouter(prefix="/api", tags=["tasks"])


# ── 健康检查 ──


@router.get("/health", response_model=HealthResponse)
async def health_check() -> HealthResponse:
    """健康检查端点。"""
    return HealthResponse(status="ok")


# ── 模型配置信息 ──

@router.get("/config/models")
async def get_model_config():
    """获取当前使用的模型配置信息。"""
    import json
    from pathlib import Path

    api_keys_path = Path(__file__).resolve().parent.parent.parent.parent.parent / "config" / "api_keys.json"
    try:
        with open(api_keys_path, "r", encoding="utf-8") as f:
            config = json.load(f)
        llm = config.get("llm", {})
        vision = config.get("vision", {})

        # ── 文本模型：按 provider 读取 ──
        llm_provider = llm.get("provider", "deepseek")
        if llm_provider == "deepseek":
            lp_config = llm.get("deepseek", {})
            text_model = lp_config.get("model", "deepseek-chat")
        elif llm_provider == "doubao":
            lp_config = llm.get("doubao", {})
            text_model = lp_config.get("model", "doubao-1.5-pro-32k")
        else:
            text_model = "unknown"

        # ── 视觉模型：按 provider 读取 ──
        vision_provider = vision.get("provider", "qwen_vl")
        if vision_provider == "doubao_vision":
            vp_config = vision.get("doubao_vision", {})
            vision_model = vp_config.get("model", "doubao-vision-pro-32k")
        else:
            vp_config = vision.get("qwen_vl", {})
            vision_model = vp_config.get("model", "qwen-vl-max")

        return {
            "text_model": text_model,
            "vision_provider": vision_provider,
            "vision_model": vision_model,
            "vision_enabled": bool(
                vision.get("api_key") and "在这里粘贴" not in vision.get("api_key", "")
            ),
        }
    except Exception:
        return {
            "text_model": "unknown",
            "vision_provider": "unknown",
            "vision_model": "unknown",
            "vision_enabled": False,
        }


# ── 任务 CRUD ──


@router.post("/tasks", response_model=TaskCreated)
async def create_task(
    file: UploadFile,
    level: str = Query(default="QC-v4", description="班型等级（默认QC-v4统一标准）"),
    auto_start: bool = Query(default=True, description="是否自动启动分析"),
) -> TaskCreated:
    """上传视频并创建分析任务。

    Args:
        file: 视频文件（multipart/form-data）
        level: 班型等级（L1_L3/L4_L6/L7_L9/QC-v4）
        auto_start: 是否自动启动分析
    """
    if file.filename is None:
        raise HTTPException(status_code=400, detail="文件名不能为空")

    # 读取文件内容
    content = await file.read()
    ext = Path(file.filename).suffix.lstrip(".")

    try:
        # 文件写入移至线程池，避免阻塞事件循环
        task_id = await asyncio.to_thread(
            TaskService.create_task, file.filename, content, ext
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    # 自动启动分析
    if auto_start:
        try:
            TaskService.start_analysis(task_id, level=level)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))

    return TaskCreated(id=task_id)


# ── 分块上传（解决 Cloudflare 100s 超时） ──


class ChunkInitRequest(BaseModel):
    filename: str
    extension: str
    total_size: int


class ChunkInitResponse(BaseModel):
    upload_id: str
    chunk_size: int = 5 * 1024 * 1024  # 建议分块大小 5MB


@router.post("/tasks/upload/init", response_model=ChunkInitResponse)
async def init_chunked_upload(req: ChunkInitRequest) -> ChunkInitResponse:
    """初始化分块上传会话。"""
    try:
        upload_id = TaskService.init_chunked_upload(
            filename=req.filename,
            extension=req.extension,
            total_size=req.total_size,
        )
        return ChunkInitResponse(upload_id=upload_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


class ChunkCompleteRequest(BaseModel):
    level: str = "QC-v4"


@router.post("/tasks/upload/{upload_id}/complete", response_model=TaskCreated)
async def complete_chunked_upload(
    upload_id: str,
    req: ChunkCompleteRequest,
) -> TaskCreated:
    """组装分块、创建任务并启动分析。

    使用 asyncio.to_thread 将同步文件 I/O 移至线程池，
    避免阻塞事件循环导致 Cloudflare 524 超时。
    """
    try:
        task_id = await asyncio.to_thread(
            TaskService.complete_chunked_upload, upload_id, req.level
        )
        return TaskCreated(id=task_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/tasks/upload/{upload_id}/{chunk_index:int}")
async def upload_chunk(
    upload_id: str,
    chunk_index: int,
    file: UploadFile,
) -> dict:
    """上传单个分块。"""
    try:
        chunk_data = await file.read()
        TaskService.upload_chunk(upload_id, chunk_index, chunk_data)
        return {"ok": True, "chunk_index": chunk_index}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


# ── 任务 CRUD（续） ──


@router.get("/tasks", response_model=TaskListResponse)
async def list_tasks(
    page: int = Query(default=1, ge=1, description="页码"),
    page_size: int = Query(default=10, ge=1, le=100, description="每页数量"),
    keyword: str = Query(default="", description="搜索关键词"),
) -> TaskListResponse:
    """获取任务列表（分页，按日期降序）。"""
    items, total = TaskService.get_tasks(page=page, page_size=page_size, keyword=keyword)
    return TaskListResponse(
        items=[TaskListItem(**item) for item in items],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get("/tasks/{task_id}", response_model=TaskDetailResponse)
async def get_task_detail(task_id: str) -> TaskDetailResponse:
    """获取任务详情（含完整评分数据）。"""
    task = TaskService.get_task_detail(task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="任务不存在")

    # 解析 scoring_data JSON
    scoring_data = None
    if task.get("scoring_data"):
        try:
            from classroom_analyzer.server.models import ScoreCardSchema
            scoring_data = ScoreCardSchema.model_validate_json(task["scoring_data"])
        except Exception:
            scoring_data = None

    return TaskDetailResponse(
        id=task["id"],
        filename=task["filename"],
        video_path=task["video_path"],
        status=task["status"],
        progress=task.get("progress", 0),
        current_stage=task.get("current_stage", ""),
        total_score=task.get("total_score"),
        grade=task.get("grade"),
        scoring_data=scoring_data,
        created_at=task.get("created_at"),
        completed_at=task.get("completed_at"),
    )


@router.get("/tasks/{task_id}/status", response_model=TaskStatusResponse)
async def get_task_status(task_id: str) -> TaskStatusResponse:
    """轮询任务状态。"""
    status = TaskService.get_task_status(task_id)
    if status is None:
        raise HTTPException(status_code=404, detail="任务不存在")
    return TaskStatusResponse(**status)


@router.get("/tasks/{task_id}/video")
async def stream_video(task_id: str, request: Request) -> StreamingResponse:
    """视频流播放（支持 Range Request）。"""
    video_path = TaskService.get_video_path(task_id)
    if video_path is None:
        raise HTTPException(status_code=404, detail="任务不存在")

    video_file = Path(video_path)
    if not video_file.exists():
        raise HTTPException(status_code=404, detail="视频文件不存在")

    file_size = video_file.stat().st_size
    content_type = _get_content_type(video_file)

    # 处理 Range 请求
    range_header = request.headers.get("range")

    if range_header:
        # 解析 Range: bytes=start-end
        range_match = range_header.replace("bytes=", "").split("-")
        start = int(range_match[0]) if range_match[0] else 0
        end = int(range_match[1]) if range_match[1] else file_size - 1

        # 确保 range 有效
        if start >= file_size or end >= file_size:
            return StreamingResponse(
                status_code=416,
                headers={"Content-Range": f"bytes */{file_size}"},
            )

        chunk_size = end - start + 1

        async def _range_generator() -> typing.AsyncGenerator[bytes, None]:
            with open(video_file, "rb") as f:
                f.seek(start)
                remaining = chunk_size
                while remaining > 0:
                    read_size = min(8192, remaining)
                    data = f.read(read_size)
                    if not data:
                        break
                    remaining -= len(data)
                    yield data

        return StreamingResponse(
            _range_generator(),
            status_code=206,
            media_type=content_type,
            headers={
                "Content-Range": f"bytes {start}-{end}/{file_size}",
                "Accept-Ranges": "bytes",
                "Content-Length": str(chunk_size),
            },
        )

    # 无 Range 请求，返回完整文件流
    async def _full_generator() -> typing.AsyncGenerator[bytes, None]:
        with open(video_file, "rb") as f:
            while True:
                data = f.read(8192)
                if not data:
                    break
                yield data

    return StreamingResponse(
        _full_generator(),
        media_type=content_type,
        headers={
            "Accept-Ranges": "bytes",
            "Content-Length": str(file_size),
        },
    )


@router.get("/tasks/{task_id}/report/pdf")
async def get_report_pdf(task_id: str) -> HTMLResponse:
    """获取分析报告（暂时返回 HTML，PDF 后续补充）。"""
    task = TaskService.get_task_detail(task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="任务不存在")

    # 读取 markdown 报告
    results_dir = Path(__file__).resolve().parent.parent.parent.parent.parent / "data" / "results" / task_id
    report_md = results_dir / "quality_report.md"

    if report_md.exists():
        md_content = report_md.read_text(encoding="utf-8")
    else:
        md_content = f"# 分析报告\n\n任务 {task_id} 的报告尚未生成。"

    # 简单的 Markdown 转 HTML
    html_content = _md_to_html(md_content, task)
    return HTMLResponse(content=html_content)


# ── 辅助函数 ──


def _get_content_type(path: Path) -> str:
    """根据扩展名返回 Content-Type。"""
    ext = path.suffix.lower()
    content_types = {
        ".mp4": "video/mp4",
        ".mov": "video/quicktime",
        ".mkv": "video/x-matroska",
        ".webm": "video/webm",
        ".flv": "video/x-flv",
        ".avi": "video/x-msvideo",
    }
    return content_types.get(ext, "application/octet-stream")


def _md_to_html(md_content: str, task: dict) -> str:
    """将 Markdown 报告转换为简单的 HTML 页面。"""

    # 简单的 markdown 到 html 转换
    lines = md_content.split("\n")
    html_lines: list[str] = []

    for line in lines:
        stripped = line.strip()
        if stripped.startswith("# "):
            html_lines.append(f"<h1>{html_module.escape(stripped[2:])}</h1>")
        elif stripped.startswith("## "):
            html_lines.append(f"<h2>{html_module.escape(stripped[3:])}</h2>")
        elif stripped.startswith("### "):
            html_lines.append(f"<h3>{html_module.escape(stripped[4:])}</h3>")
        elif stripped.startswith("- [x] "):
            html_lines.append(f"<div style='margin-left:20px;color:green'>&#9745; {html_module.escape(stripped[6:])}</div>")
        elif stripped.startswith("- [ ] "):
            html_lines.append(f"<div style='margin-left:20px;color:red'>&#9744; {html_module.escape(stripped[6:])}</div>")
        elif stripped.startswith("- "):
            html_lines.append(f"<div style='margin-left:20px'>&#8226; {html_module.escape(stripped[2:])}</div>")
        elif stripped.startswith("> "):
            html_lines.append(f"<blockquote style='border-left:3px solid #ccc;padding-left:10px;color:#666'>{html_module.escape(stripped[2:])}</blockquote>")
        elif stripped.startswith("|"):
            # 表格行 - 简单处理
            cells = [c.strip() for c in stripped.split("|") if c.strip()]
            if all(set(c) <= {"-", ":"} for c in cells):
                continue  # 跳过分隔行
            row = "".join(f"<td style='border:1px solid #ddd;padding:6px'>{html_module.escape(c)}</td>" for c in cells)
            html_lines.append(f"<tr>{row}</tr>")
        elif stripped:
            html_lines.append(f"<p>{html_module.escape(stripped)}</p>")
        else:
            html_lines.append("<br>")

    # 构建完整 HTML
    filename = task.get("filename", "未知文件")
    body = "\n".join(html_lines)

    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>课堂分析报告 - {html_module.escape(filename)}</title>
    <style>
        body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; max-width: 900px; margin: 0 auto; padding: 20px; color: #333; }}
        h1 {{ color: #1565c0; border-bottom: 2px solid #1565c0; padding-bottom: 8px; }}
        h2 {{ color: #1976d2; margin-top: 24px; }}
        h3 {{ color: #1e88e5; }}
        table {{ border-collapse: collapse; width: 100%; margin: 10px 0; }}
        td {{ border: 1px solid #ddd; padding: 6px; }}
        tr:nth-child(even) {{ background-color: #f5f5f5; }}
        blockquote {{ border-left: 3px solid #ccc; padding-left: 10px; color: #666; margin: 8px 0; }}
        @media print {{ body {{ max-width: 100%; }} }}
    </style>
</head>
<body>
{body}
</body>
</html>"""
