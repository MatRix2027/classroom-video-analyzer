"""SQLite 数据库层 — 任务持久化"""

from __future__ import annotations

import sqlite3
import threading
from datetime import datetime, timezone
from typing import Any, Optional

from loguru import logger

from classroom_analyzer.paths import get_data_dir

DATA_DIR = get_data_dir()
DB_PATH = DATA_DIR / "tasks.db"


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _parse_db_time(value: Any) -> Optional[datetime]:
    if not value:
        return None
    text = str(value).strip()
    if not text:
        return None
    try:
        if text.endswith("Z"):
            text = f"{text[:-1]}+00:00"
        if "T" not in text and " " in text:
            text = text.replace(" ", "T", 1)
        parsed = datetime.fromisoformat(text)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)
    except ValueError:
        return None

# 线程安全的数据库锁
_db_lock = threading.Lock()

# SQL 建表语句
_CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS tasks (
    id TEXT PRIMARY KEY,
    filename TEXT NOT NULL,
    video_path TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending',
    progress INTEGER DEFAULT 0,
    current_stage TEXT,
    total_score REAL,
    grade TEXT,
    scoring_data TEXT,
    metadata_json TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    analysis_started_at TIMESTAMP,
    status_updated_at TIMESTAMP,
    completed_at TIMESTAMP
);
"""

_CREATE_FEEDBACK_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS calibration_feedback (
    id TEXT PRIMARY KEY,
    task_id TEXT NOT NULL,
    feedback_type TEXT NOT NULL,
    dimension_name TEXT,
    ai_score REAL,
    human_score REAL,
    human_grade TEXT,
    time_range TEXT,
    issue_summary TEXT NOT NULL,
    correction_suggestion TEXT,
    evidence_note TEXT,
    reviewer TEXT,
    status TEXT NOT NULL DEFAULT 'new',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
"""


def _get_conn() -> sqlite3.Connection:
    """获取数据库连接，确保 data 目录存在。"""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def init_db() -> None:
    """初始化数据库，创建表结构。"""
    with _db_lock:
        conn = _get_conn()
        try:
            conn.execute(_CREATE_TABLE_SQL)
            conn.execute(_CREATE_FEEDBACK_TABLE_SQL)
            _ensure_column(conn, "tasks", "metadata_json", "TEXT")
            _ensure_column(conn, "tasks", "analysis_started_at", "TIMESTAMP")
            _ensure_column(conn, "tasks", "status_updated_at", "TIMESTAMP")
            conn.commit()
            logger.info(f"数据库初始化完成：{DB_PATH}")
        finally:
            conn.close()


def _ensure_column(conn: sqlite3.Connection, table: str, column: str, column_type: str) -> None:
    columns = [row["name"] for row in conn.execute(f"PRAGMA table_info({table})").fetchall()]
    if column not in columns:
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {column_type}")


def create_task(task_id: str, filename: str, video_path: str, metadata_json: str = "{}") -> None:
    """创建新任务记录。"""
    now = _utc_now()
    with _db_lock:
        conn = _get_conn()
        try:
            conn.execute(
                "INSERT INTO tasks (id, filename, video_path, status, progress, current_stage, metadata_json, "
                "created_at, status_updated_at) VALUES (?, ?, ?, 'pending', 0, '等待开始', ?, ?, ?)",
                (task_id, filename, video_path, metadata_json, now, now),
            )
            conn.commit()
        finally:
            conn.close()


def update_task_status(
    task_id: str,
    status: str,
    progress: int,
    current_stage: str,
) -> None:
    """更新任务状态。"""
    now = _utc_now()
    with _db_lock:
        conn = _get_conn()
        try:
            conn.execute(
                "UPDATE tasks SET status=?, progress=?, current_stage=?, status_updated_at=? WHERE id=?",
                (status, progress, current_stage, now, task_id),
            )
            conn.commit()
        finally:
            conn.close()


def mark_task_started(task_id: str, status: str = "extracting", current_stage: str = "准备开始分析...") -> None:
    """记录真实分析开始时间，用于耗时展示和失败重试重新计时。"""
    now = _utc_now()
    with _db_lock:
        conn = _get_conn()
        try:
            conn.execute(
                "UPDATE tasks SET status=?, progress=0, current_stage=?, "
                "analysis_started_at=?, status_updated_at=?, completed_at=NULL WHERE id=?",
                (status, current_stage, now, now, task_id),
            )
            conn.commit()
        finally:
            conn.close()


def update_task_completed(
    task_id: str,
    total_score: float,
    grade: str,
    scoring_data: str,
) -> None:
    """标记任务完成，写入评分数据。"""
    now = _utc_now()
    with _db_lock:
        conn = _get_conn()
        try:
            conn.execute(
                "UPDATE tasks SET status='completed', progress=100, "
                "current_stage='分析完成', total_score=?, grade=?, "
                "scoring_data=?, completed_at=?, status_updated_at=? WHERE id=?",
                (total_score, grade, scoring_data, now, now, task_id),
            )
            conn.commit()
        finally:
            conn.close()


def update_task_failed(task_id: str, error_message: str) -> None:
    """标记任务失败。"""
    with _db_lock:
        conn = _get_conn()
        try:
            conn.execute(
                "UPDATE tasks SET status='failed', current_stage=?, status_updated_at=? WHERE id=?",
                (error_message, _utc_now(), task_id),
            )
            conn.commit()
        finally:
            conn.close()


def get_task(task_id: str) -> Optional[dict[str, Any]]:
    """获取单个任务详情。"""
    with _db_lock:
        conn = _get_conn()
        try:
            row = conn.execute(
                "SELECT * FROM tasks WHERE id=?", (task_id,)
            ).fetchone()
            if row is None:
                return None
            return dict(row)
        finally:
            conn.close()


def get_task_status(task_id: str) -> Optional[dict[str, Any]]:
    """获取任务状态（轮询用）。"""
    with _db_lock:
        conn = _get_conn()
        try:
            row = conn.execute(
                "SELECT id, status, progress, current_stage, created_at, analysis_started_at, "
                "status_updated_at, completed_at FROM tasks WHERE id=?",
                (task_id,),
            ).fetchone()
            if row is None:
                return None
            return dict(row)
        finally:
            conn.close()


def mark_stale_running_tasks_failed(max_age_minutes: int = 30) -> int:
    """Mark orphaned background jobs as failed after a server restart or long inactivity."""
    running_statuses = ("extracting", "transcribing", "analyzing", "scoring")
    now_dt = datetime.now(timezone.utc)
    failed_ids: list[str] = []
    with _db_lock:
        conn = _get_conn()
        try:
            rows = conn.execute(
                "SELECT id, status_updated_at, analysis_started_at, created_at FROM tasks "
                "WHERE status IN (?, ?, ?, ?)",
                running_statuses,
            ).fetchall()
            for row in rows:
                last_seen = (
                    _parse_db_time(row["status_updated_at"])
                    or _parse_db_time(row["analysis_started_at"])
                    or _parse_db_time(row["created_at"])
                )
                if last_seen is None:
                    continue
                age_minutes = (now_dt - last_seen).total_seconds() / 60
                if age_minutes >= max_age_minutes:
                    failed_ids.append(row["id"])

            if failed_ids:
                now = _utc_now()
                message = (
                    "分析中断：后台服务可能已休眠或重启，当前任务已停止。"
                    "请点击“重试分析”继续处理已上传的视频。"
                )
                conn.executemany(
                    "UPDATE tasks SET status='failed', current_stage=?, status_updated_at=? WHERE id=?",
                    [(message, now, task_id) for task_id in failed_ids],
                )
                conn.commit()
            return len(failed_ids)
        finally:
            conn.close()


def get_tasks(page: int = 1, page_size: int = 10) -> tuple[list[dict[str, Any]], int]:
    """获取任务列表（分页，按日期降序）。"""
    offset = (page - 1) * page_size
    with _db_lock:
        conn = _get_conn()
        try:
            total = conn.execute("SELECT COUNT(*) FROM tasks").fetchone()[0]
            rows = conn.execute(
                "SELECT id, filename, status, total_score, grade, created_at "
                "FROM tasks ORDER BY created_at DESC LIMIT ? OFFSET ?",
                (page_size, offset),
            ).fetchall()
            return [dict(row) for row in rows], total
        finally:
            conn.close()


def search_tasks(keyword: str, page: int = 1, page_size: int = 10) -> tuple[list[dict[str, Any]], int]:
    """搜索任务列表（按文件名模糊搜索）。"""
    offset = (page - 1) * page_size
    like_pattern = f"%{keyword}%"
    with _db_lock:
        conn = _get_conn()
        try:
            total = conn.execute(
                "SELECT COUNT(*) FROM tasks WHERE filename LIKE ?",
                (like_pattern,),
            ).fetchone()[0]
            rows = conn.execute(
                "SELECT id, filename, status, total_score, grade, created_at "
                "FROM tasks WHERE filename LIKE ? ORDER BY created_at DESC LIMIT ? OFFSET ?",
                (like_pattern, page_size, offset),
            ).fetchall()
            return [dict(row) for row in rows], total
        finally:
            conn.close()


def create_calibration_feedback(feedback: dict[str, Any]) -> dict[str, Any]:
    """保存人工校对反馈。"""
    with _db_lock:
        conn = _get_conn()
        try:
            conn.execute(
                """
                INSERT INTO calibration_feedback (
                    id, task_id, feedback_type, dimension_name, ai_score, human_score,
                    human_grade, time_range, issue_summary, correction_suggestion,
                    evidence_note, reviewer, status
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    feedback["id"],
                    feedback["task_id"],
                    feedback["feedback_type"],
                    feedback.get("dimension_name"),
                    feedback.get("ai_score"),
                    feedback.get("human_score"),
                    feedback.get("human_grade"),
                    feedback.get("time_range"),
                    feedback["issue_summary"],
                    feedback.get("correction_suggestion"),
                    feedback.get("evidence_note"),
                    feedback.get("reviewer"),
                    feedback.get("status", "new"),
                ),
            )
            conn.commit()
            row = conn.execute(
                "SELECT * FROM calibration_feedback WHERE id=?",
                (feedback["id"],),
            ).fetchone()
            return dict(row)
        finally:
            conn.close()


def get_task_feedback(task_id: str) -> list[dict[str, Any]]:
    """获取某个任务下的人工校对反馈。"""
    with _db_lock:
        conn = _get_conn()
        try:
            rows = conn.execute(
                "SELECT * FROM calibration_feedback WHERE task_id=? ORDER BY created_at DESC",
                (task_id,),
            ).fetchall()
            return [dict(row) for row in rows]
        finally:
            conn.close()


def list_calibration_feedback(
    page: int = 1,
    page_size: int = 20,
    status: str = "",
    feedback_type: str = "",
) -> tuple[list[dict[str, Any]], int]:
    """分页获取人工校对反馈池。"""
    offset = (page - 1) * page_size
    where: list[str] = []
    params: list[Any] = []
    if status:
        where.append("f.status=?")
        params.append(status)
    if feedback_type:
        where.append("f.feedback_type=?")
        params.append(feedback_type)
    where_sql = f"WHERE {' AND '.join(where)}" if where else ""

    with _db_lock:
        conn = _get_conn()
        try:
            total = conn.execute(
                f"SELECT COUNT(*) FROM calibration_feedback f {where_sql}",
                params,
            ).fetchone()[0]
            rows = conn.execute(
                f"""
                SELECT f.*, t.filename, t.total_score, t.grade
                FROM calibration_feedback f
                LEFT JOIN tasks t ON t.id = f.task_id
                {where_sql}
                ORDER BY f.created_at DESC
                LIMIT ? OFFSET ?
                """,
                [*params, page_size, offset],
            ).fetchall()
            return [dict(row) for row in rows], total
        finally:
            conn.close()
