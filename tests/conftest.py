# tests/conftest.py
import pytest

from moviebot.common.config import Settings


@pytest.fixture
def test_settings() -> Settings:
    """Settings con valores explícitos de prueba (no depende de .env)."""
    return Settings(
        openai_api_key="test-openai-key",
        openai_model="gpt-4o-mini",
        tmdb_api_key="test-tmdb-key",
        meilisearch_url="http://localhost:7700",
        meilisearch_api_key=None,
        meilisearch_index="netflix",
        log_level="DEBUG",
        _env_file=None,
    )
