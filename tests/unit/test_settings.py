# tests/unit/test_settings.py
import pytest

from moviebot.common.config import Settings


def test_settings_explicit_values():
    """Settings se puede instanciar con valores explícitos."""
    s = Settings(
        openai_api_key="key1",
        openai_model="gpt-4o",
        tmdb_api_key="key2",
        _env_file=None,
    )
    assert s.openai_api_key.get_secret_value() == "key1"
    assert s.openai_model == "gpt-4o"
    assert s.meilisearch_url == "http://localhost:7700"
    assert s.log_level == "INFO"


def test_settings_from_env(monkeypatch: pytest.MonkeyPatch):
    """Settings lee variables de entorno correctamente."""
    monkeypatch.setenv("OPENAI_API_KEY", "env-openai")
    monkeypatch.setenv("OPENAI_MODEL", "gpt-4o-mini")
    monkeypatch.setenv("TMDB_API_KEY", "env-tmdb")
    monkeypatch.setenv("LOG_LEVEL", "DEBUG")

    s = Settings(_env_file=None)
    assert s.openai_api_key.get_secret_value() == "env-openai"
    assert s.openai_model == "gpt-4o-mini"
    assert s.tmdb_api_key.get_secret_value() == "env-tmdb"
    assert s.log_level == "DEBUG"
