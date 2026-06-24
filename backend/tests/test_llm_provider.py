import pytest

from backend.app.services.llm import get_llm_provider


def test_deepseek_provider_is_available_when_key_exists(monkeypatch):
    monkeypatch.setattr("backend.app.services.llm.providers.settings.deepseek_api_key", "sk-test")
    provider = get_llm_provider("deepseek")

    assert provider.name == "deepseek"
    assert provider.default_model
    assert provider.available() is True


def test_openai_compatible_alias_uses_deepseek_provider(monkeypatch):
    monkeypatch.setattr("backend.app.services.llm.providers.settings.deepseek_api_key", "sk-test")
    provider = get_llm_provider("openai-compatible")

    assert provider.name == "deepseek"


def test_mock_provider_is_not_supported():
    with pytest.raises(ValueError):
        get_llm_provider("mock")


def test_unknown_provider_fails_fast():
    with pytest.raises(ValueError):
        get_llm_provider("unknown")
