"""配置加载测试"""

import json
from pathlib import Path

import pytest
import yaml

from classroom_analyzer.config import ConfigManager, ConfigError, ClassroomAnalyzerError


class TestConfigManager:
    """ConfigManager 测试。"""

    def test_load_success(self, tmp_config_dir: Path) -> None:
        yaml_path = tmp_config_dir / "config.yaml"
        json_path = tmp_config_dir / "api_keys.json"

        manager = ConfigManager(
            config_path=str(yaml_path),
            api_keys_path=str(json_path),
        )
        config = manager.load()

        assert len(config.scoring_dimensions) == 5
        assert len(config.quality_checklist) == 3
        assert len(config.event_types) == 2
        assert config.api_keys["tencent_cloud"]["secret_id"] == "test_secret_id"

    def test_load_caches_result(self, tmp_config_dir: Path) -> None:
        yaml_path = tmp_config_dir / "config.yaml"
        json_path = tmp_config_dir / "api_keys.json"

        manager = ConfigManager(
            config_path=str(yaml_path),
            api_keys_path=str(json_path),
        )
        config1 = manager.load()
        config2 = manager.load()
        assert config1 is config2  # 应该返回同一对象

    def test_load_yaml_not_exists(self, tmp_path: Path) -> None:
        json_path = tmp_path / "api_keys.json"
        json_path.write_text("{}", encoding="utf-8")

        manager = ConfigManager(
            config_path=str(tmp_path / "nonexistent.yaml"),
            api_keys_path=str(json_path),
        )
        with pytest.raises(ConfigError, match="配置文件不存在"):
            manager.load()

    def test_load_json_not_exists(self, tmp_path: Path) -> None:
        yaml_path = tmp_path / "config.yaml"
        yaml_path.write_text("scoring:\n  dimensions: []\nquality_checklist: []\nevent_types: []", encoding="utf-8")

        manager = ConfigManager(
            config_path=str(yaml_path),
            api_keys_path=str(tmp_path / "nonexistent.json"),
        )
        with pytest.raises(ConfigError, match="API密钥文件不存在"):
            manager.load()

    def test_validate_success(self, tmp_config_dir: Path) -> None:
        yaml_path = tmp_config_dir / "config.yaml"
        json_path = tmp_config_dir / "api_keys.json"

        manager = ConfigManager(
            config_path=str(yaml_path),
            api_keys_path=str(json_path),
        )
        config = manager.load()
        assert manager.validate() is True

    def test_validate_missing_secret_id(self, tmp_path: Path) -> None:
        yaml_config = {
            "scoring": {"dimensions": [{"name": "测试", "weight": 1.0, "criteria": "test"}]},
            "quality_checklist": ["检查项"],
            "event_types": ["环节切换"],
        }
        yaml_path = tmp_path / "config.yaml"
        yaml_path.write_text(yaml.dump(yaml_config, allow_unicode=True), encoding="utf-8")

        json_config = {
            "tencent_cloud": {"secret_id": "在这里粘贴你的SecretId", "secret_key": "test_key"},
            "cos": {"bucket": "test-bucket", "region": "ap-guangzhou", "path_prefix": "asr/"},
            "llm": {"base_url": "https://test.com", "api_key": "test_key", "model": "test"},
        }
        json_path = tmp_path / "api_keys.json"
        json_path.write_text(json.dumps(json_config, ensure_ascii=False), encoding="utf-8")

        manager = ConfigManager(
            config_path=str(yaml_path),
            api_keys_path=str(json_path),
        )
        with pytest.raises(ConfigError, match="配置校验失败"):
            manager.load()

    def test_validate_missing_llm_key(self, tmp_path: Path) -> None:
        yaml_config = {
            "scoring": {"dimensions": [{"name": "测试", "weight": 1.0, "criteria": "test"}]},
            "quality_checklist": ["检查项"],
            "event_types": ["环节切换"],
        }
        yaml_path = tmp_path / "config.yaml"
        yaml_path.write_text(yaml.dump(yaml_config, allow_unicode=True), encoding="utf-8")

        json_config = {
            "tencent_cloud": {"secret_id": "real_id", "secret_key": "real_key"},
            "cos": {"bucket": "real-bucket", "region": "ap-guangzhou", "path_prefix": "asr/"},
            "llm": {"base_url": "https://test.com", "api_key": "在这里粘贴你的LLM API Key", "model": "test"},
        }
        json_path = tmp_path / "api_keys.json"
        json_path.write_text(json.dumps(json_config, ensure_ascii=False), encoding="utf-8")

        manager = ConfigManager(
            config_path=str(yaml_path),
            api_keys_path=str(json_path),
        )
        with pytest.raises(ConfigError, match="配置校验失败"):
            manager.load()

    def test_validate_empty_dimensions(self, tmp_path: Path) -> None:
        yaml_config = {
            "scoring": {"dimensions": []},
            "quality_checklist": ["检查项"],
            "event_types": ["环节切换"],
        }
        yaml_path = tmp_path / "config.yaml"
        yaml_path.write_text(yaml.dump(yaml_config, allow_unicode=True), encoding="utf-8")

        json_config = {
            "tencent_cloud": {"secret_id": "real_id", "secret_key": "real_key"},
            "cos": {"bucket": "real-bucket", "region": "ap-guangzhou", "path_prefix": "asr/"},
            "llm": {"base_url": "https://test.com", "api_key": "real_key", "model": "test"},
        }
        json_path = tmp_path / "api_keys.json"
        json_path.write_text(json.dumps(json_config, ensure_ascii=False), encoding="utf-8")

        manager = ConfigManager(
            config_path=str(yaml_path),
            api_keys_path=str(json_path),
        )
        with pytest.raises(ConfigError, match="配置校验失败"):
            manager.load()

    def test_invalid_yaml_syntax(self, tmp_path: Path) -> None:
        yaml_path = tmp_path / "config.yaml"
        yaml_path.write_text(": invalid: yaml: [", encoding="utf-8")

        json_path = tmp_path / "api_keys.json"
        json_path.write_text("{}", encoding="utf-8")

        manager = ConfigManager(
            config_path=str(yaml_path),
            api_keys_path=str(json_path),
        )
        with pytest.raises(ConfigError, match="YAML配置解析失败"):
            manager.load()

    def test_invalid_json_syntax(self, tmp_path: Path) -> None:
        yaml_path = tmp_path / "config.yaml"
        yaml_path.write_text("scoring:\n  dimensions: []", encoding="utf-8")

        json_path = tmp_path / "api_keys.json"
        json_path.write_text("{invalid json}", encoding="utf-8")

        manager = ConfigManager(
            config_path=str(yaml_path),
            api_keys_path=str(json_path),
        )
        with pytest.raises(ConfigError, match="API密钥文件解析失败"):
            manager.load()


class TestClassroomAnalyzerError:
    """基础异常类测试。"""

    def test_inheritance(self) -> None:
        assert issubclass(ConfigError, ClassroomAnalyzerError)
        assert issubclass(ClassroomAnalyzerError, Exception)

    def test_raise_and_catch(self) -> None:
        with pytest.raises(ClassroomAnalyzerError, match="test error"):
            raise ClassroomAnalyzerError("test error")
