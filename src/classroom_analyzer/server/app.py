"""FastAPI application entrypoint."""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from loguru import logger
from starlette.middleware.base import BaseHTTPMiddleware

from classroom_analyzer.paths import get_project_root
from classroom_analyzer.server.database import init_db, mark_stale_running_tasks_failed
from classroom_analyzer.server.routers import standards, tasks

PROJECT_ROOT = get_project_root()
WEB_DIST_DIR = PROJECT_ROOT / "web" / "dist"


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialize storage at startup without making UI availability depend on DB cleanup."""
    logger.info("Classroom video analyzer service starting...")
    try:
        init_db()
        stale_count = mark_stale_running_tasks_failed()
        if stale_count:
            logger.warning(f"Marked {stale_count} stale running task(s) as failed for retry.")
        logger.info("Database initialization complete.")
    except Exception as exc:
        logger.error(
            f"Database startup initialization failed; continuing so health check and UI stay available: {exc}",
            exc_info=True,
        )

    if WEB_DIST_DIR.exists() and (WEB_DIST_DIR / "index.html").exists():
        logger.info(f"Frontend static directory: {WEB_DIST_DIR}")
    else:
        logger.warning(f"Frontend build output missing: {WEB_DIST_DIR}")

    yield

    logger.info("Classroom video analyzer service stopped.")


class CacheControlMiddleware(BaseHTTPMiddleware):
    """Set cache headers for SPA assets."""

    async def dispatch(self, request: Request, call_next):
        response: Response = await call_next(request)
        path = request.url.path

        if path in {"/", "/index.html"}:
            response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
            response.headers["Pragma"] = "no-cache"
            response.headers["Expires"] = "0"
        elif path.startswith("/assets/"):
            response.headers["Cache-Control"] = "public, max-age=31536000, immutable"
        elif not path.startswith("/api/"):
            response.headers["Cache-Control"] = "no-cache"

        return response


def create_app() -> FastAPI:
    """Create FastAPI app instance."""
    app = FastAPI(
        title="火花课堂视频分析",
        description="课堂视频智能分析工具 - Web API",
        version="1.0.0",
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.add_middleware(CacheControlMiddleware)

    app.include_router(tasks.router)
    app.include_router(standards.router)

    if (WEB_DIST_DIR / "assets").exists():
        app.mount("/assets", StaticFiles(directory=str(WEB_DIST_DIR / "assets")), name="assets")

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


app = create_app()
