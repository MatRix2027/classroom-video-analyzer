import pytest

from classroom_analyzer.server.routers import tasks


@pytest.mark.anyio
async def test_model_config_uses_provider_nested_keys(monkeypatch):
    class FakeConfigManager:
        def __init__(self, *args, **kwargs):
            pass

        def _load_json(self):
            return {
                "llm": {
                    "provider": "deepseek",
                    "deepseek": {
                        "model": "deepseek-chat",
                        "api_key": "text-key",
                    },
                },
                "vision": {
                    "provider": "doubao_vision",
                    "doubao_vision": {
                        "model": "doubao-vision-pro-32k",
                        "api_key": "vision-key",
                    },
                },
            }

    import classroom_analyzer.config as config_module

    monkeypatch.setattr(config_module, "ConfigManager", FakeConfigManager)

    payload = await tasks.get_model_config()

    assert payload["text_provider"] == "deepseek"
    assert payload["text_model"] == "deepseek-chat"
    assert payload["text_enabled"] is True
    assert payload["vision_provider"] == "doubao_vision"
    assert payload["vision_model"] == "doubao-vision-pro-32k"
    assert payload["vision_enabled"] is True
    assert payload["config_status"] == "ok"
