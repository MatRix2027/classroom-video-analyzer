"""配置加载与校验模块"""

import json
from pathlib import Path
from typing import Any

import yaml
from loguru import logger

from classroom_analyzer.models import AppConfig, ScoringDimensionConfig


class ClassroomAnalyzerError(Exception):
    """课堂视频分析工具基础异常类。"""
    pass


class ConfigError(ClassroomAnalyzerError):
    """配置相关异常。"""
    pass


def _build_criteria_string(dim: dict[str, Any]) -> str:
    """将YAML维度的多级标准合并为单个criteria字符串。

    支持两种格式：
    1. 单字段 criteria（旧格式）
    2. criteria_excellent / criteria_good / criteria_average / criteria_poor（新格式）
    """
    # 新格式：4级标准
    parts = []
    for level_name in ("excellent", "good", "average", "poor"):
        key = f"criteria_{level_name}"
        if dim.get(key):
            label = {"excellent": "优", "good": "良", "average": "中", "poor": "差"}[level_name]
            parts.append(f"【{label}】{dim[key]}")
    
    if parts:
        return "\n".join(parts)
    
    # 旧格式：单个 criteria
    return dim.get("criteria", "")


class ConfigManager:
    """配置管理器：加载YAML评分配置和JSON API密钥，合并为AppConfig。"""

    def __init__(self, config_path: str, api_keys_path: str) -> None:
        self._config_path = Path(config_path)
        self._api_keys_path = Path(api_keys_path)
        self._yaml_config: dict[str, Any] = {}
        self._api_config: dict[str, Any] = {}
        self._app_config: AppConfig | None = None

    def load(self, level: str = "QC-v4") -> AppConfig:
        """加载并校验配置，返回AppConfig实例。

        Args:
            level: 班型等级，可选 "L1_L3"、"L4_L6"、"L7_L9"、"QC-v4"，默认 "QC-v4"

        Raises:
            ConfigError: 当level参数无效或配置校验失败时抛出
        """
        if self._app_config is not None:
            return self._app_config

        # 校验level参数（Task 3e 配置验证强化）
        valid_levels = {"L1_L3", "L4_L6", "L7_L9", "QC-v4"}
        if level not in valid_levels:
            raise ConfigError(
                f"无效的班型参数：{level}。有效值为：{', '.join(sorted(valid_levels))}"
            )

        # 加载YAML评分配置
        self._yaml_config = self._load_yaml()

        # 校验YAML中是否存在对应班型配置
        levels_data = self._yaml_config.get("levels", {})
        level_key_map = {
            "L1_L3": "L1-L3",
            "L4_L6": "L4-L6",
            "L7_L9": "L7-L9",
            "QC-v4": "QC-v4",
        }
        yaml_level_key = level_key_map.get(level, "QC-v4")
        if levels_data and yaml_level_key not in levels_data:
            available = list(levels_data.keys())
            raise ConfigError(
                f"YAML配置中未找到班型 {level}（键 {yaml_level_key}）的配置。"
                f"可用班型：{available}"
            )

        # 加载JSON API密钥
        self._api_config = self._load_json()

        # 合并为AppConfig（按班型选择评分维度）
        self._app_config = self._merge_config(self._yaml_config, self._api_config, level=level)

        # 校验
        if not self.validate():
            raise ConfigError("配置校验失败，请检查必填字段")

        logger.info(f"配置加载成功（班型：{level}）")
        return self._app_config

    def validate(self) -> bool:
        """校验配置必填字段。"""
        if self._app_config is None:
            return False

        # 校验评分维度
        if not self._app_config.scoring_dimensions:
            logger.error("评分维度不能为空")
            return False

        total_weight = sum(d.weight for d in self._app_config.scoring_dimensions)
        if abs(total_weight - 1.0) > 0.01:
            logger.warning(f"评分维度权重之和为 {total_weight:.2f}，建议调整为 1.0")

        # 校验API密钥
        api_keys = self._app_config.api_keys
        tencent = api_keys.get("tencent_cloud", {})
        if not tencent.get("secret_id") or tencent.get("secret_id") == "在这里粘贴你的SecretId":
            logger.error("腾讯云 SecretId 未配置")
            return False
        if not tencent.get("secret_key") or tencent.get("secret_key") == "在这里粘贴你的SecretKey":
            logger.error("腾讯云 SecretKey 未配置")
            return False

        # 校验LLM配置（必填 — 文本模型需要 API key，支持 provider 选择）
        llm = api_keys.get("llm", {})
        llm_provider = llm.get("provider", "doubao")
        provider_cfg = llm.get(llm_provider, {})
        llm_key_ok = (
            provider_cfg.get("api_key") and "在这里粘贴" not in provider_cfg.get("api_key", "")
        )
        if not llm_key_ok:
            logger.error(
                f"文本模型 ({llm_provider}) API Key 未配置，"
                f"请在 api_keys.json 的 llm.{llm_provider}.api_key 中填写"
            )
            return False

        # 校验视觉模型配置（可选 — 没有视觉模型也可运行，仅使用文本评分）
        vision = api_keys.get("vision", {})
        vision_provider = vision.get("provider", "qwen_vl")
        provider_config = vision.get(vision_provider, {})
        vision_key_ok = (
            vision.get("api_key") and "在这里粘贴" not in vision.get("api_key", "")
        ) or (
            provider_config.get("api_key") and "在这里粘贴" not in provider_config.get("api_key", "")
        )
        if not vision_key_ok:
            logger.warning(
                f"视觉模型 ({vision_provider}) API Key 未配置，将仅使用文本评分"
            )

        # 校验COS配置
        cos = api_keys.get("cos", {})
        if not cos.get("bucket") or cos.get("bucket") == "your-bucket-name-1234567890":
            logger.error("COS Bucket 未配置")
            return False

        # 校验质检清单
        if not self._app_config.quality_checklist:
            logger.error("质检清单不能为空")
            return False

        # 校验事件类型
        if not self._app_config.event_types:
            logger.error("事件类型不能为空")
            return False

        return True

    def _load_yaml(self) -> dict[str, Any]:
        """加载YAML配置文件。"""
        if not self._config_path.exists():
            raise ConfigError(f"配置文件不存在：{self._config_path}")

        try:
            with open(self._config_path, "r", encoding="utf-8") as f:
                config = yaml.safe_load(f)
            logger.debug(f"YAML配置加载成功：{self._config_path}")
            return config or {}
        except yaml.YAMLError as e:
            raise ConfigError(f"YAML配置解析失败：{e}")

    def _load_json(self) -> dict[str, Any]:
        """加载JSON API密钥文件。优先从环境变量 API_KEYS_JSON 读取（云端部署）。"""
        import os

        # 优先从环境变量读取（适合云端部署，无需在容器中挂载密钥文件）
        env_json = os.environ.get("API_KEYS_JSON", "").strip()
        if env_json:
            try:
                config = json.loads(env_json)
                logger.info("API密钥从环境变量 API_KEYS_JSON 加载成功")
                return config
            except json.JSONDecodeError as e:
                raise ConfigError(f"环境变量 API_KEYS_JSON 解析失败：{e}")

        # 回退到文件读取
        if not self._api_keys_path.exists():
            raise ConfigError(
                f"API密钥文件不存在：{self._api_keys_path}\n"
                f"请复制 api_keys.json.template 为 api_keys.json 并填写密钥，"
                f"或设置环境变量 API_KEYS_JSON"
            )

        try:
            with open(self._api_keys_path, "r", encoding="utf-8") as f:
                config = json.load(f)
            logger.debug(f"API密钥加载成功：{self._api_keys_path}")
            return config
        except json.JSONDecodeError as e:
            raise ConfigError(f"API密钥文件解析失败：{e}")

    @staticmethod
    def _merge_config(
        yaml_config: dict[str, Any],
        api_config: dict[str, Any],
        level: str = "QC-v4",
    ) -> AppConfig:
        """合并YAML和JSON配置为AppConfig。

        Args:
            yaml_config: YAML配置字典
            api_config: JSON API密钥字典
            level: 班型等级，从YAML中读取对应维度的评分标准
        """
        # 解析评分维度（按班型选择）
        scoring_data = yaml_config.get("scoring", {})
        dimensions_data = scoring_data.get("dimensions", [])
        
        # 从 levels 嵌套结构中按班型选取
        levels_data = yaml_config.get("levels", {})
        level_key_map = {
            "L1_L3": "L1-L3",
            "L4_L6": "L4-L6",
            "L7_L9": "L7-L9",
            "QC-v4": "QC-v4",
        }
        yaml_level_key = level_key_map.get(level, "QC-v4")
        
        if levels_data and yaml_level_key in levels_data:
            # 新格式：levels.L4-L6.dimensions
            level_config = levels_data[yaml_level_key]
            dimensions_data = level_config.get("dimensions", [])
            # 质检清单也按班型读取
            quality_checklist = []
            if level_config.get("quality_checklist"):
                quality_checklist = level_config["quality_checklist"]
        elif isinstance(dimensions_data, dict):
            # 兼容旧格式
            dimensions_data = dimensions_data.get(yaml_level_key, dimensions_data.get("L4-L6", []))
            quality_checklist = yaml_config.get("quality_checklist", [])

        scoring_dimensions = [
            ScoringDimensionConfig(
                name=d.get("name", ""),
                weight=float(d.get("weight", 0.0)),
                criteria=_build_criteria_string(d),
                max_score=float(d.get("max_score", 100.0)),
            )
            for d in dimensions_data
        ]

        # 解析质检清单（优先从班型配置读取，否则从顶层读取）
        if not quality_checklist:
            quality_checklist = yaml_config.get("quality_checklist", [])

        # 解析事件类型
        event_types = yaml_config.get("event_types", [])

        # 提取子配置
        asr_config = api_config.get("asr", {})
        analysis_config = api_config.get("analysis", {})
        cos_config = api_config.get("cos", {})

        # 合并 YAML analysis 段的配置（优先级低于 API JSON 中的同名字段）
        yaml_analysis = yaml_config.get("analysis", {})
        for k, v in yaml_analysis.items():
            if k not in analysis_config:
                analysis_config[k] = v

        # 将班型等级和prompt版本注入analysis_config
        analysis_config["level"] = level
        analysis_config["prompt_version"] = "spark_standard"

        # 解析红线淘汰行为
        red_lines = yaml_config.get("red_lines", [])

        return AppConfig(
            scoring_dimensions=scoring_dimensions,
            quality_checklist=quality_checklist,
            event_types=event_types,
            api_keys=api_config,
            asr_config=asr_config,
            analysis_config=analysis_config,
            cos_config=cos_config,
            red_lines=red_lines,
        )
