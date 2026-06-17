"""SQLite 数据库层 — 任务持久化"""

from __future__ import annotations

import sqlite3
import threading
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

from loguru import logger

from classroom_analyzer.paths import get_project_root

# 项目根目录
PROJECT_ROOT = get_project_root()
DATA_DIR = PROJECT_ROOT / "data"
DB_PATH = DATA_DIR / "tasks.db"

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
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
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
            conn.commit()
            logger.info(f"数据库初始化完成：{DB_PATH}")
        finally:
            conn.close()


def create_task(task_id: str, filename: str, video_path: str) -> None:
    """创建新任务记录。"""
    with _db_lock:
        conn = _get_conn()
        try:
            conn.execute(
                "INSERT INTO tasks (id, filename, video_path, status, progress, current_stage) "
                "VALUES (?, ?, ?, 'pending', 0, '等待开始')",
                (task_id, filename, video_path),
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
    with _db_lock:
        conn = _get_conn()
        try:
            conn.execute(
                "UPDATE tasks SET status=?, progress=?, current_stage=? WHERE id=?",
                (status, progress, current_stage, task_id),
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
    now = datetime.now().isoformat()
    with _db_lock:
        conn = _get_conn()
        try:
            conn.execute(
                "UPDATE tasks SET status='completed', progress=100, "
                "current_stage='分析完成', total_score=?, grade=?, "
                "scoring_data=?, completed_at=? WHERE id=?",
                (total_score, grade, scoring_data, now, task_id),
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
                "UPDATE tasks SET status='failed', current_stage=? WHERE id=?",
                (error_message, task_id),
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
                "SELECT id, status, progress, current_stage, created_at, completed_at FROM tasks WHERE id=?",
                (task_id,),
            ).fetchone()
            if row is None:
                return None
            return dict(row)
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
