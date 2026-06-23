"""FastAPI 应用入口"""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from loguru import logger
from starlette.middleware.base import BaseHTTPMiddleware

from classroom_analyzer.paths import get_project_root
from classroom_analyzer.server.database import init_db, mark_stale_running_tasks_failed
from classroom_analyzer.server.routers import standards, tasks

# 项目根目录
PROJECT_ROOT = get_project_root()
WEB_DIST_DIR = PROJECT_ROOT / "web" / "dist"


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期管理：启动时初始化数据库，关闭时清理资源。"""
    # 启动
    logger.info("火花课堂视频分析服务启动中...")
    init_db()
    stale_count = mark_stale_running_tasks_failed()
    if stale_count:
        logger.warning(f"已标记 {stale_count} 个长时间无更新的运行中任务为失败，可由用户重试")
    logger.info("数据库初始化完成")

    # 检查前端构建产物
    if WEB_DIST_DIR.exists() and (WEB_DIST_DIR / "index.html").exists():
        logger.info(f"前端静态文件目录：{WEB_DIST_DIR}")
    else:
        logger.warning(f"前端构建产物不存在：{WEB_DIST_DIR}，请运行 cd web && npm run build")

    yield

    # 关闭
    logger.info("火花课堂视频分析服务已关闭")


class CacheControlMiddleware(BaseHTTPMiddleware):
    """为静态资源设置 Cache-Control 头，防止 CDN 缓存旧版前端。

    - index.html → no-cache, no-store, must-revalidate（每次都回源）
    - /assets/*  → public, max-age=31536000, immutable（内容哈希文件名，可长期缓存）
    - 其他文件   → no-cache（协商缓存）
    """

    async def dispatch(self, request: Request, call_next):
        response: Response = await call_next(request)
        path = request.url.path

        if path == "/" or path == "/index.html":
            response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
            response.headers["Pragma"] = "no-cache"
            response.headers["Expires"] = "0"
        elif path.startswith("/assets/"):
            # Vite 构建的 assets 文件名含内容哈希（如 index-FtBd38UA.js），可安全长期缓存
            response.headers["Cache-Control"] = "public, max-age=31536000, immutable"
        elif not path.startswith("/api/"):
            # 其他静态文件（favicon 等）使用协商缓存
            response.headers["Cache-Control"] = "no-cache"

        return response


def create_app() -> FastAPI:
    """创建 FastAPI 应用实例。"""
    app = FastAPI(
        title="火花课堂视频分析",
        description="课堂视频智能分析工具 — Web API",
        version="1.0.0",
        lifespan=lifespan,
    )

    # CORS — 允许全部来源（开发环境）
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Cache-Control — 防止 CDN/浏览器缓存旧版前端
    app.add_middleware(CacheControlMiddleware)

    # 注册路由（APIRouter 自带 /api 前缀，这里不再重复添加）
    app.include_router(tasks.router)
    app.include_router(standards.router)

    # 挂载前端静态 assets（内容哈希文件名，安全长期缓存）
    if (WEB_DIST_DIR / "assets").exists():
        app.mount("/assets", StaticFiles(directory=str(WEB_DIST_DIR / "assets")), name="assets")

    # SPA 回退中间件：404 的非 API 请求返回 index.html
    @app.middleware("http")
    async def spa_fallback_middleware(request: Request, call_next):
        response = await call_next(request)
        if response.status_code == 404 and not request.url.path.startswith("/api"):
            index_path = WEB_DIST_DIR / "index.html"
            if index_path.exists():
                return FileResponse(
                    index_path,
                    headers={"Cache-Control": "no-cache, no-store, must-revalidate"},
                )
        return response

    return app


# 创建全局 app 实例（uvicorn 使用）
app = create_app()
