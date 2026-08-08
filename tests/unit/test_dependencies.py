# tests/unit/test_dependencies.py
"""Unit tests for runtime wiring: resolve_active_index, create_*, NetflixAgent."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import AsyncMock

import pytest

from moviebot.agents.netflix.agent import NetflixAgent
from moviebot.agents.netflix.models import NetflixQuery
from moviebot.common.config import Settings
from moviebot.common.dependencies import (
    create_intent_extractor,
    create_netflix_repository,
    resolve_active_index,
)
from moviebot.common.models import AgentResult, MovieCandidate

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_settings(**overrides) -> Settings:
    """Create a Settings instance with minimal valid values."""
    defaults = {
        "openai_api_key": "test-openai-key",
        "openai_model": "gpt-4o-mini",
        "tmdb_api_key": "test-tmdb-key",
        "_env_file": None,
    }
    defaults.update(overrides)
    return Settings(**defaults)


# ---------------------------------------------------------------------------
# resolve_active_index tests
# ---------------------------------------------------------------------------


class TestResolveActiveIndex:
    """Tests for resolve_active_index precedence logic."""

    def test_explicit_override(self, tmp_path: Path):
        """When meilisearch_index is set, use it directly (no registry needed)."""
        settings = _make_settings(
            meilisearch_index="netflix_v2",
            meilisearch_registry_path=tmp_path / "nonexistent.json",
        )
        result = resolve_active_index(settings)
        assert result == "netflix_v2"

    def test_reads_active_index_from_valid_registry(self, tmp_path: Path):
        """When meilisearch_index is None, read active_index from registry."""
        registry = tmp_path / "index_registry.json"
        registry.write_text(
            json.dumps({"active_index": "netflix_v1", "indexes": {}}),
            encoding="utf-8",
        )

        settings = _make_settings(
            meilisearch_index=None,
            meilisearch_registry_path=registry,
        )
        result = resolve_active_index(settings)
        assert result == "netflix_v1"

    def test_error_when_registry_does_not_exist(self, tmp_path: Path):
        """When meilisearch_index is None and registry doesn't exist → FileNotFoundError."""
        settings = _make_settings(
            meilisearch_index=None,
            meilisearch_registry_path=tmp_path / "missing_registry.json",
        )
        with pytest.raises(FileNotFoundError, match="registry"):
            resolve_active_index(settings)

    def test_error_when_registry_json_is_invalid(self, tmp_path: Path):
        """When registry file contains invalid JSON → ValueError."""
        registry = tmp_path / "index_registry.json"
        registry.write_text("not valid json {{{{", encoding="utf-8")

        settings = _make_settings(
            meilisearch_index=None,
            meilisearch_registry_path=registry,
        )
        with pytest.raises(ValueError, match="no es un JSON válido"):
            resolve_active_index(settings)

    def test_error_when_registry_missing_active_index(self, tmp_path: Path):
        """When registry JSON has no active_index key → ValueError."""
        registry = tmp_path / "index_registry.json"
        registry.write_text(json.dumps({"indexes": {}}), encoding="utf-8")

        settings = _make_settings(
            meilisearch_index=None,
            meilisearch_registry_path=registry,
        )
        with pytest.raises(ValueError, match="no contiene 'active_index'"):
            resolve_active_index(settings)


# ---------------------------------------------------------------------------
# create_intent_extractor tests
# ---------------------------------------------------------------------------


class TestCreateIntentExtractor:
    """Tests for create_intent_extractor factory."""

    def test_receives_correct_model(self):
        """The extractor uses the model specified in Settings."""
        settings = _make_settings(openai_model="gpt-4o")
        extractor = create_intent_extractor(settings)
        assert extractor._model == "gpt-4o"

    def test_receives_different_model(self):
        """Changing openai_model in Settings is propagated to the extractor."""
        settings = _make_settings(openai_model="gpt-3.5-turbo")
        extractor = create_intent_extractor(settings)
        assert extractor._model == "gpt-3.5-turbo"


# ---------------------------------------------------------------------------
# create_netflix_repository tests
# ---------------------------------------------------------------------------


class TestCreateNetflixRepository:
    """Tests for create_netflix_repository factory."""

    def test_uses_resolved_index(self, tmp_path: Path):
        """Repository is created with the resolved active index name."""
        registry = tmp_path / "index_registry.json"
        registry.write_text(
            json.dumps({"active_index": "netflix_v3"}), encoding="utf-8"
        )

        settings = _make_settings(
            meilisearch_index=None,
            meilisearch_registry_path=registry,
        )
        repo = create_netflix_repository(settings)
        assert repo._index_name == "netflix_v3"

    def test_uses_explicit_override(self):
        """When meilisearch_index is set, repository uses it."""
        settings = _make_settings(meilisearch_index="custom_index")
        repo = create_netflix_repository(settings)
        assert repo._index_name == "custom_index"


# ---------------------------------------------------------------------------
# Protocol-based injection tests
# ---------------------------------------------------------------------------


class TestProtocolInjection:
    """Tests for protocol-based dependency injection in NetflixAgent."""

    def test_agent_accepts_any_intent_extractor_implementation(self):
        """NetflixAgent accepts any object implementing IntentExtractorProtocol."""

        class FakeExtractor:
            async def extract(self, user_text: str) -> NetflixQuery:
                return NetflixQuery(semantic_query=user_text)

        class FakeRepository:
            async def search(self, query: NetflixQuery) -> list[MovieCandidate]:
                return []

        # Should not raise — protocols are structural, not nominal
        agent = NetflixAgent(
            intent_extractor=FakeExtractor(),
            repository=FakeRepository(),
        )
        assert agent._intent_extractor is not None
        assert agent._repository is not None

    def test_agent_accepts_mock_implementations(self):
        """NetflixAgent works with mock implementations (AsyncMock)."""
        mock_extractor = AsyncMock()
        mock_repository = AsyncMock()

        agent = NetflixAgent(
            intent_extractor=mock_extractor,
            repository=mock_repository,
        )
        assert agent._intent_extractor is mock_extractor
        assert agent._repository is mock_repository


# ---------------------------------------------------------------------------
# NetflixAgent.search() flow tests
# ---------------------------------------------------------------------------


class TestNetflixAgentSearch:
    """Tests for NetflixAgent.search() orchestration flow."""

    @pytest.mark.asyncio
    async def test_search_flow_constructs_agent_result_correctly(self):
        """search() extracts intent → searches repository → returns AgentResult.

        Verifies:
        - intent_extractor.extract is called with user_text
        - repository.search is called with the extracted query
        - AgentResult is constructed with candidates, query_interpretation, warnings=[]
        """
        # Arrange
        query = NetflixQuery(
            semantic_query="sci-fi movies",
            type="movie",
            genres=["sci-fi"],
            actors=["keanu reeves"],
        )

        candidates = [
            MovieCandidate(
                id="tm12345",
                title="The Matrix",
                description="A hacker discovers reality is a simulation.",
                release_year=1999,
                genres=["sci-fi", "action"],
                source="netflix",
                content_type="movie",
            ),
            MovieCandidate(
                id="tm67890",
                title="Interstellar",
                description="A journey through a wormhole.",
                release_year=2014,
                genres=["sci-fi", "drama"],
                source="netflix",
                content_type="movie",
            ),
        ]

        mock_extractor = AsyncMock()
        mock_extractor.extract.return_value = query

        mock_repository = AsyncMock()
        mock_repository.search.return_value = candidates

        agent = NetflixAgent(
            intent_extractor=mock_extractor,
            repository=mock_repository,
        )

        # Act
        result = await agent.search("sci-fi movies with Keanu Reeves")

        # Assert
        mock_extractor.extract.assert_called_once_with(
            "sci-fi movies with Keanu Reeves"
        )
        mock_repository.search.assert_called_once_with(query)

        assert isinstance(result, AgentResult)
        assert result.candidates == candidates
        assert result.query_interpretation == query.model_dump()
        assert result.warnings == []

    @pytest.mark.asyncio
    async def test_search_with_empty_results(self):
        """search() returns AgentResult with empty candidates when no matches."""
        query = NetflixQuery(semantic_query="nonexistent movie xyz")
        mock_extractor = AsyncMock()
        mock_extractor.extract.return_value = query

        mock_repository = AsyncMock()
        mock_repository.search.return_value = []

        agent = NetflixAgent(
            intent_extractor=mock_extractor,
            repository=mock_repository,
        )

        result = await agent.search("nonexistent movie xyz")

        assert result.candidates == []
        assert result.query_interpretation == query.model_dump()
        assert result.warnings == []

    @pytest.mark.asyncio
    async def test_search_query_interpretation_has_all_fields(self):
        """query_interpretation contains all NetflixQuery fields via model_dump()."""
        query = NetflixQuery(
            semantic_query="drama",
            type="show",
            genres=["drama", "thriller"],
            min_year=2020,
            max_year=2024,
            actors=["bryan cranston"],
            directors=["vince gilligan"],
            age_certification=["tv-ma"],
        )

        mock_extractor = AsyncMock()
        mock_extractor.extract.return_value = query

        mock_repository = AsyncMock()
        mock_repository.search.return_value = []

        agent = NetflixAgent(
            intent_extractor=mock_extractor,
            repository=mock_repository,
        )

        result = await agent.search("drama shows 2020-2024")

        interpretation = result.query_interpretation
        assert interpretation["semantic_query"] == "drama"
        assert interpretation["type"] == "show"
        assert interpretation["genres"] == ["drama", "thriller"]
        assert interpretation["min_year"] == 2020
        assert interpretation["max_year"] == 2024
        assert interpretation["actors"] == ["bryan cranston"]
        assert interpretation["directors"] == ["vince gilligan"]
        assert interpretation["age_certification"] == ["tv-ma"]
