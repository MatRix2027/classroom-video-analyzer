"""评价标准 API 路由"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml
from fastapi import APIRouter

from classroom_analyzer.paths import get_project_root
from classroom_analyzer.server.models import (
    StandardDimension,
    StandardLevel,
    StandardsResponse,
)

router = APIRouter(prefix="/api", tags=["standards"])

# 项目根目录
PROJECT_ROOT = get_project_root()
CONFIG_PATH = PROJECT_ROOT / "config" / "default.yaml"


@router.get("/standards", response_model=StandardsResponse)
async def get_standards() -> StandardsResponse:
    """获取 QC-v4 评价标准 JSON。"""
    config_data = _load_yaml_config()
    if not config_data:
        return StandardsResponse()

    # 解析各班型标准
    levels_data = config_data.get("levels", {})
    levels: dict[str, StandardLevel] = {}

    for level_key, level_config in levels_data.items():
        # 将 YAML key (如 "L4-L6") 转换为标准 key (如 "L4_L6")
        normalized_key = level_key.replace("-", "_")

        dimensions = []
        for dim in level_config.get("dimensions", []):
            dimensions.append(
                StandardDimension(
                    name=dim.get("name", ""),
                    category=dim.get("category", ""),
                    weight=float(dim.get("weight", 0.0)),
                    max_score=float(dim.get("max_score", 10.0)),
                    criteria_excellent=dim.get("criteria_excellent", ""),
                    criteria_good=dim.get("criteria_good", ""),
                    criteria_average=dim.get("criteria_average", ""),
                    criteria_poor=dim.get("criteria_poor", ""),
                )
            )

        levels[normalized_key] = StandardLevel(
            description=level_config.get("description", ""),
            student_focus=level_config.get("student_focus", ""),
            dimensions=dimensions,
            quality_checklist=level_config.get("quality_checklist", []),
        )

    # 解析红线淘汰行为
    red_lines = config_data.get("red_lines", [])

    # 解析等级制
    grade_system = config_data.get("grade_system", [])

    return StandardsResponse(
        levels=levels,
        red_lines=red_lines,
        grade_system=grade_system,
    )


def _load_yaml_config() -> dict[str, Any]:
    """加载 YAML 配置文件。"""
    if not CONFIG_PATH.exists():
        return {}

    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)
    return data or {}
