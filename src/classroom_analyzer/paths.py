"""Runtime path helpers for local development and packaged deployments."""

from __future__ import annotations

import os
from pathlib import Path


def get_project_root() -> Path:
    """Return the project root that contains config/, prompts/, web/, and data/.

    In Docker/Render the package is imported from site-packages after
    ``pip install .``, so resolving paths relative to ``__file__`` points at the
    Python installation. The container sets CLASSROOM_ANALYZER_PROJECT_ROOT=/app.
    Local editable runs fall back to the repository root.
    """
    env_root = os.environ.get("CLASSROOM_ANALYZER_PROJECT_ROOT", "").strip()
    if env_root:
        return Path(env_root).expanduser().resolve()

    cwd = Path.cwd().resolve()
    if (cwd / "config").exists() and (cwd / "src" / "classroom_analyzer").exists():
        return cwd

    return Path(__file__).resolve().parent.parent.parent


def get_data_dir() -> Path:
    """Return the writable runtime data directory.

    Local runs use ``<project>/data``. Cloud deployments can set
    ``CLASSROOM_ANALYZER_DATA_DIR`` to a persistent disk mount such as
    ``/var/data`` so uploaded videos, task DB, and generated reports survive
    redeploys and restarts.
    """
    env_data_dir = os.environ.get("CLASSROOM_ANALYZER_DATA_DIR", "").strip()
    if env_data_dir:
        return Path(env_data_dir).expanduser().resolve()
    if os.environ.get("RENDER"):
        return Path("/var/data").resolve()
    return get_project_root() / "data"
