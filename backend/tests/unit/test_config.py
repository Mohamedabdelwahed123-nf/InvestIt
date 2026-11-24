"""Smoke tests: the config module imports and reads the environment safely."""

import pytest

from backend.config import Settings, get_settings


def test_defaults_are_offline(monkeypatch: pytest.MonkeyPatch) -> None:
    for var in ("LLM_PROVIDER", "LANGFUSE_PUBLIC_KEY", "LANGFUSE_SECRET_KEY"):
        monkeypatch.delenv(var, raising=False)
    settings = Settings(_env_file=None)
    assert settings.llm_provider == "fake"
    assert settings.langfuse_enabled is False


def test_reads_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LLM_PROVIDER", "anthropic")
    monkeypatch.setenv("LLM_MODEL", "strong-model")
    monkeypatch.setenv("LLM_MODEL_CHEAP", "cheap-model")
    monkeypatch.setenv("LANGFUSE_PUBLIC_KEY", "pk")
    monkeypatch.setenv("LANGFUSE_SECRET_KEY", "sk")
    settings = Settings(_env_file=None)
    assert settings.llm_model == "strong-model"
    assert settings.llm_model_cheap == "cheap-model"
    assert settings.langfuse_enabled is True
    assert "sk" not in repr(settings)


def test_unknown_provider_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LLM_PROVIDER", "not-a-provider")
    with pytest.raises(ValueError):
        Settings(_env_file=None)


def test_get_settings_is_cached() -> None:
    get_settings.cache_clear()
    assert get_settings() is get_settings()
