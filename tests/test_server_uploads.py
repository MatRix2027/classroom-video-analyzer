import json
from pathlib import Path

import pytest

from classroom_analyzer.server import services
from classroom_analyzer.server.services import TaskService


@pytest.fixture
def upload_dirs(tmp_path, monkeypatch):
    chunk_dir = tmp_path / "chunks"
    upload_dir = tmp_path / "uploads"
    chunk_dir.mkdir()
    upload_dir.mkdir()
    monkeypatch.setattr(services, "CHUNK_DIR", chunk_dir)
    monkeypatch.setattr(services, "UPLOAD_DIR", upload_dir)
    monkeypatch.setattr(services, "CHUNK_SIZE", 4)
    return chunk_dir, upload_dir


def test_chunked_upload_status_reports_missing_chunks(upload_dirs):
    upload_id = TaskService.init_chunked_upload("lesson.mp4", "mp4", 10)

    TaskService.upload_chunk(upload_id, 0, b"aaaa")
    status = TaskService.get_chunked_upload_status(upload_id)

    assert status["total_chunks"] == 3
    assert status["received_chunks"] == 1
    assert status["missing_chunks"] == [1, 2]
    assert status["complete"] is False


def test_upload_chunk_rejects_unexpected_size(upload_dirs):
    upload_id = TaskService.init_chunked_upload("lesson.mp4", "mp4", 10)

    with pytest.raises(ValueError, match="大小不匹配"):
        TaskService.upload_chunk(upload_id, 0, b"aa")


def test_complete_chunked_upload_requires_all_chunks(upload_dirs):
    upload_id = TaskService.init_chunked_upload("lesson.mp4", "mp4", 10)
    TaskService.upload_chunk(upload_id, 0, b"aaaa")
    TaskService.upload_chunk(upload_id, 2, b"cc")

    with pytest.raises(ValueError, match="缺少 1 个分块"):
        TaskService.complete_chunked_upload(upload_id)


def test_complete_chunked_upload_assembles_in_order(upload_dirs, monkeypatch):
    _, upload_dir = upload_dirs
    created: dict[str, str] = {}

    def fake_create_task(task_id: str, filename: str, video_path: str, metadata_json: str = "{}") -> None:
        created.update(
            task_id=task_id,
            filename=filename,
            video_path=video_path,
            metadata=json.loads(metadata_json),
        )

    monkeypatch.setattr(services.db, "create_task", fake_create_task)
    monkeypatch.setattr(TaskService, "start_analysis", staticmethod(lambda task_id, level="QC-v4": None))

    upload_id = TaskService.init_chunked_upload("lesson.mp4", "mp4", 10)
    TaskService.upload_chunk(upload_id, 2, b"cc")
    TaskService.upload_chunk(upload_id, 0, b"aaaa")
    TaskService.upload_chunk(upload_id, 1, b"bbbb")

    task_id = TaskService.complete_chunked_upload(upload_id, metadata={"video_scope": "课堂片段"})

    assert created["task_id"] == task_id
    assert created["filename"] == "lesson.mp4"
    assert created["metadata"] == {"video_scope": "课堂片段"}
    assert Path(created["video_path"]).read_bytes() == b"aaaabbbbcc"
    assert Path(created["video_path"]).is_relative_to(upload_dir)
