# tests/unit/test_intent_extractor.py
"""Unit tests for IntentExtractorProtocol and LlmIntentExtractor.

Tests protocol conformance, mocked OpenAI client interactions, and
correct extraction of actors/directors from example queries.

Validates: Requirements 9.2, 10.8a
"""

from unittest.mock import AsyncMock, MagicMock

import pytest

from moviebot.agents.netflix.intent_extractor import (
    IntentExtractorProtocol,
    LlmIntentExtractor,
)
from moviebot.agents.netflix.models import NetflixQuery


def _make_mock_client(parsed_result: NetflixQuery | None) -> MagicMock:
    """Create a mock OpenAI client that returns a parsed NetflixQuery.

    Mocks the chain: client.beta.chat.completions.parse() → response
    where response.choices[0].message.parsed == parsed_result.
    """
    mock_client = MagicMock()
    mock_message = MagicMock()
    mock_message.parsed = parsed_result
    mock_choice = MagicMock()
    mock_choice.message = mock_message
    mock_response = MagicMock()
    mock_response.choices = [mock_choice]

    mock_client.beta.chat.completions.parse = AsyncMock(return_value=mock_response)
    return mock_client


class TestProtocolConformance:
    """Test that LlmIntentExtractor satisfies IntentExtractorProtocol."""

    def test_llm_intent_extractor_satisfies_protocol(self) -> None:
        """LlmIntentExtractor must be structurally compatible with IntentExtractorProtocol."""
        mock_client = _make_mock_client(NetflixQuery())
        extractor = LlmIntentExtractor(openai_client=mock_client, model="gpt-4o")

        # Verify it has the extract method with correct signature
        assert hasattr(extractor, "extract")
        assert callable(extractor.extract)

    def test_protocol_is_runtime_checkable(self) -> None:
        """IntentExtractorProtocol should be usable as a type annotation."""
        mock_client = _make_mock_client(NetflixQuery())
        extractor = LlmIntentExtractor(openai_client=mock_client, model="gpt-4o")

        # Duck typing: LlmIntentExtractor implements the protocol
        protocol_ref: IntentExtractorProtocol = extractor  # noqa: F841
        assert True  # No type error means conformance


class TestLlmIntentExtractorWithActors:
    """Test actor extraction from user queries."""

    @pytest.mark.asyncio
    async def test_movies_with_tom_hanks(self) -> None:
        """'movies with Tom Hanks' → actors=["tom hanks"], type="movie"."""
        expected = NetflixQuery(
            semantic_query="",
            type="movie",
            actors=["tom hanks"],
        )
        mock_client = _make_mock_client(expected)
        extractor = LlmIntentExtractor(openai_client=mock_client, model="gpt-4o")

        result = await extractor.extract("movies with Tom Hanks")

        assert result.actors == ["tom hanks"]
        assert result.type == "movie"

    @pytest.mark.asyncio
    async def test_multiple_actors(self) -> None:
        """Query with multiple actors returns all normalized names."""
        expected = NetflixQuery(
            type="movie",
            actors=["robert de niro", "al pacino"],
            genres=["crime"],
        )
        mock_client = _make_mock_client(expected)
        extractor = LlmIntentExtractor(openai_client=mock_client, model="gpt-4o")

        result = await extractor.extract("Robert De Niro and Al Pacino crime movies")

        assert result.actors == ["robert de niro", "al pacino"]
        assert result.type == "movie"
        assert result.genres == ["crime"]


class TestLlmIntentExtractorWithDirectors:
    """Test director extraction from user queries."""

    @pytest.mark.asyncio
    async def test_directed_by_scorsese(self) -> None:
        """'directed by Martin Scorsese' → directors=["martin scorsese"]."""
        expected = NetflixQuery(
            directors=["martin scorsese"],
        )
        mock_client = _make_mock_client(expected)
        extractor = LlmIntentExtractor(openai_client=mock_client, model="gpt-4o")

        result = await extractor.extract("directed by Martin Scorsese")

        assert result.directors == ["martin scorsese"]


class TestLlmIntentExtractorActorsAndDirectors:
    """Test queries with both actors and directors."""

    @pytest.mark.asyncio
    async def test_actor_and_director_mixed(self) -> None:
        """Query with actor AND director extracts both correctly."""
        expected = NetflixQuery(
            type="movie",
            actors=["leonardo dicaprio"],
            directors=["martin scorsese"],
        )
        mock_client = _make_mock_client(expected)
        extractor = LlmIntentExtractor(openai_client=mock_client, model="gpt-4o")

        result = await extractor.extract(
            "Leonardo DiCaprio movies directed by Martin Scorsese"
        )

        assert result.actors == ["leonardo dicaprio"]
        assert result.directors == ["martin scorsese"]
        assert result.type == "movie"


class TestLlmIntentExtractorNoActorsDirectors:
    """Test queries with no actors or directors produce empty lists."""

    @pytest.mark.asyncio
    async def test_no_actors_no_directors(self) -> None:
        """A purely genre/semantic query returns empty actors/directors lists."""
        expected = NetflixQuery(
            semantic_query="something funny",
            genres=[],
            actors=[],
            directors=[],
        )
        mock_client = _make_mock_client(expected)
        extractor = LlmIntentExtractor(openai_client=mock_client, model="gpt-4o")

        result = await extractor.extract("something funny")

        assert result.actors == []
        assert result.directors == []

    @pytest.mark.asyncio
    async def test_genre_only_query(self) -> None:
        """'sci-fi shows from the 90s' → no actors/directors."""
        expected = NetflixQuery(
            type="show",
            genres=["sci-fi"],
            min_year=1990,
            max_year=1999,
            actors=[],
            directors=[],
        )
        mock_client = _make_mock_client(expected)
        extractor = LlmIntentExtractor(openai_client=mock_client, model="gpt-4o")

        result = await extractor.extract("sci-fi shows from the 90s")

        assert result.actors == []
        assert result.directors == []
        assert result.type == "show"
        assert result.genres == ["sci-fi"]
        assert result.min_year == 1990
        assert result.max_year == 1999


class TestLlmIntentExtractorFallback:
    """Test fallback behavior when OpenAI parsing returns None."""

    @pytest.mark.asyncio
    async def test_parsed_none_returns_empty_query(self) -> None:
        """When parsed is None, fallback returns empty NetflixQuery()."""
        mock_client = _make_mock_client(None)
        extractor = LlmIntentExtractor(openai_client=mock_client, model="gpt-4o")

        result = await extractor.extract("some gibberish query")

        assert result == NetflixQuery()
        assert result.actors == []
        assert result.directors == []
        assert result.semantic_query == ""
        assert result.type == "any"
        assert result.genres == []
        assert result.min_year is None
        assert result.max_year is None


class TestLlmIntentExtractorFullQuery:
    """Test a full query with genres, year range, actors, and directors."""

    @pytest.mark.asyncio
    async def test_full_query_all_fields(self) -> None:
        """Complex query extracts all fields correctly."""
        expected = NetflixQuery(
            semantic_query="epic saga",
            type="movie",
            genres=["drama", "crime"],
            min_year=1990,
            max_year=2010,
            actors=["robert de niro", "joe pesci"],
            directors=["martin scorsese"],
            age_certification=["r"],
        )
        mock_client = _make_mock_client(expected)
        extractor = LlmIntentExtractor(openai_client=mock_client, model="gpt-4o")

        result = await extractor.extract(
            "R-rated epic saga drama crime movies from 1990 to 2010 "
            "with Robert De Niro and Joe Pesci directed by Martin Scorsese"
        )

        assert result.semantic_query == "epic saga"
        assert result.type == "movie"
        assert result.genres == ["drama", "crime"]
        assert result.min_year == 1990
        assert result.max_year == 2010
        assert result.actors == ["robert de niro", "joe pesci"]
        assert result.directors == ["martin scorsese"]
        assert result.age_certification == ["r"]


class TestLlmIntentExtractorClientInteraction:
    """Test that LlmIntentExtractor calls the OpenAI client correctly."""

    @pytest.mark.asyncio
    async def test_passes_user_text_as_message(self) -> None:
        """The user text is passed as the user message to the client."""
        mock_client = _make_mock_client(NetflixQuery())
        extractor = LlmIntentExtractor(openai_client=mock_client, model="gpt-4o-mini")

        await extractor.extract("test query")

        mock_client.beta.chat.completions.parse.assert_called_once()
        call_kwargs = mock_client.beta.chat.completions.parse.call_args[1]
        assert call_kwargs["model"] == "gpt-4o-mini"
        assert call_kwargs["response_format"] == NetflixQuery
        messages = call_kwargs["messages"]
        assert len(messages) == 2
        assert messages[0]["role"] == "system"
        assert messages[1]["role"] == "user"
        assert messages[1]["content"] == "test query"

    @pytest.mark.asyncio
    async def test_uses_configured_model(self) -> None:
        """The model passed to constructor is used in the API call."""
        mock_client = _make_mock_client(NetflixQuery())
        extractor = LlmIntentExtractor(
            openai_client=mock_client, model="gpt-4o-2024-08-06"
        )

        await extractor.extract("any query")

        call_kwargs = mock_client.beta.chat.completions.parse.call_args[1]
        assert call_kwargs["model"] == "gpt-4o-2024-08-06"
