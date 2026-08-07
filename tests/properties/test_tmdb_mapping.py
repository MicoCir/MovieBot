"""Property-based tests for TMDB mapping (Properties 1, 2, 7).

Feature: datasource-preparation
"""

from __future__ import annotations

from typing import Any

import httpx
import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from moviebot.common.config import Settings
from moviebot.common.models import MovieCandidate
from moviebot.repositories.tmdb_connector import TmdbConnector
from moviebot.repositories.tmdb_errors import TmdbInvalidResponseError

from .conftest import tmdb_movie_object, tmdb_response


def _make_settings() -> Settings:
    """Create a minimal Settings for testing (no real API calls)."""
    return Settings(
        openai_api_key="test-openai-key",
        openai_model="gpt-4",
        tmdb_api_key="test-tmdb-key",
    )


def _make_mock_transport(response_body: dict[str, Any]) -> httpx.MockTransport:
    """Create a MockTransport that returns the given JSON body with HTTP 200."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            status_code=200,
            json=response_body,
        )

    return httpx.MockTransport(handler)


# --- Strategy for invalid TMDB responses (Property 2) ---


@st.composite
def invalid_tmdb_response(draw: st.DrawFn) -> dict[str, Any]:
    """Generate dicts that are structurally invalid TMDB responses.

    Either missing `results` entirely, or `results` is not a list.
    """
    strategy_choice = draw(st.integers(min_value=0, max_value=2))

    if strategy_choice == 0:
        # Missing 'results' key entirely
        base = draw(
            st.dictionaries(
                keys=st.text(min_size=1, max_size=20).filter(lambda s: s != "results"),
                values=st.one_of(st.integers(), st.text(max_size=50), st.booleans()),
                min_size=0,
                max_size=5,
            )
        )
        return base
    elif strategy_choice == 1:
        # 'results' is not a list — use non-list values
        non_list_value = draw(
            st.one_of(
                st.integers(),
                st.text(max_size=50),
                st.booleans(),
                st.none(),
                st.dictionaries(
                    keys=st.text(min_size=1, max_size=10),
                    values=st.integers(),
                    max_size=3,
                ),
            )
        )
        return {"results": non_list_value, "page": 1}
    else:
        # 'results' is a non-list type (float, set-like representation is not JSON)
        non_list_value = draw(st.floats(allow_nan=False, allow_infinity=False))
        return {"results": non_list_value, "page": 1}


# --- Strategy for mixed valid/invalid items (Property 1) ---


@st.composite
def tmdb_response_with_mixed_items(draw: st.DrawFn) -> dict[str, Any]:
    """Generate a TMDB response with a mix of valid and invalid items.

    Valid items have int `id` + str `title`. Invalid items may have
    missing id, non-int id, missing title, or non-str title.
    """
    valid_items = draw(st.lists(tmdb_movie_object(), min_size=0, max_size=10))

    # Generate some invalid items
    invalid_items = draw(
        st.lists(
            st.one_of(
                # Missing id
                st.fixed_dictionaries({"title": st.text(min_size=1, max_size=50)}),
                # Non-int id
                st.fixed_dictionaries(
                    {
                        "id": st.text(min_size=1, max_size=10),
                        "title": st.text(min_size=1, max_size=50),
                    }
                ),
                # Missing title
                st.fixed_dictionaries(
                    {"id": st.integers(min_value=1, max_value=10_000_000)}
                ),
                # Non-str title
                st.fixed_dictionaries(
                    {
                        "id": st.integers(min_value=1, max_value=10_000_000),
                        "title": st.integers(),
                    }
                ),
                # Not a dict at all
                st.integers(),
                st.text(max_size=20),
                st.none(),
            ),
            min_size=0,
            max_size=5,
        )
    )

    # Shuffle all items together
    all_items = draw(st.permutations(valid_items + invalid_items))

    return {
        "page": 1,
        "results": all_items,
        "total_pages": 1,
        "total_results": len(all_items),
    }


# =============================================================================
# Property 1: Mapeo TMDB produce MovieCandidates correctos para elementos válidos
# =============================================================================


class TestProperty1TmdbMapping:
    """Property 1: Mapeo TMDB produce MovieCandidates correctos para elementos válidos.

    **Validates: Requirements 1.5, 1.6, 1.7, 1.8, 1.9, 1.10, 1.11, 1.12, 1.13**
    """

    @given(response=tmdb_response(min_results=0, max_results=20))
    @settings(deadline=None, max_examples=100)
    @pytest.mark.asyncio
    async def test_valid_items_produce_correct_candidates(
        self, response: dict[str, Any]
    ) -> None:
        """All valid TMDB items (int id + str title) produce MovieCandidates
        with correct field mappings.

        **Validates: Requirements 1.5, 1.6–1.13**
        """
        transport = _make_mock_transport(response)
        client = httpx.AsyncClient(transport=transport)
        connector = TmdbConnector(settings=_make_settings(), client=client)

        candidates = await connector.get_trending()

        # Count expected valid items
        results = response["results"]
        expected_valid = [
            item
            for item in results
            if isinstance(item, dict)
            and isinstance(item.get("id"), int)
            and isinstance(item.get("title"), str)
        ]

        # Number of candidates matches valid items
        assert len(candidates) == len(expected_valid)

        # Each candidate has correct properties
        for candidate, item in zip(candidates, expected_valid):
            # id has tmdb: prefix
            assert candidate.id == f"tmdb:{item['id']}"
            # title preserved
            assert candidate.title == item["title"]
            # source is tmdb
            assert candidate.source == "tmdb"
            # content_type is movie
            assert candidate.content_type == "movie"

            # Optional fields: description
            overview = item.get("overview")
            if isinstance(overview, str):
                assert candidate.description == overview
            else:
                assert candidate.description is None

            # Optional fields: release_year
            release_date = item.get("release_date")
            if isinstance(release_date, str) and len(release_date) >= 4:
                try:
                    expected_year = int(release_date[:4])
                    assert candidate.release_year == expected_year
                except (ValueError, IndexError):
                    assert candidate.release_year is None
            else:
                assert candidate.release_year is None

            # Optional fields: genres
            genre_ids = item.get("genre_ids")
            if isinstance(genre_ids, list):
                assert candidate.genres == [str(gid) for gid in genre_ids]
            else:
                assert candidate.genres == []

            # Optional fields: popularity
            popularity = item.get("popularity")
            if isinstance(popularity, (int, float)):
                assert candidate.popularity == float(popularity)
            else:
                assert candidate.popularity is None

            # Optional fields: vote_average
            vote_average = item.get("vote_average")
            if isinstance(vote_average, (int, float)):
                assert candidate.vote_average == float(vote_average)
            else:
                assert candidate.vote_average is None

    @given(response=tmdb_response_with_mixed_items())
    @settings(deadline=None, max_examples=100)
    @pytest.mark.asyncio
    async def test_invalid_items_are_silently_skipped(
        self, response: dict[str, Any]
    ) -> None:
        """Invalid items (non-int id, non-str title, missing fields, non-dicts)
        are silently skipped without error.

        **Validates: Requirements 1.13**
        """
        transport = _make_mock_transport(response)
        client = httpx.AsyncClient(transport=transport)
        connector = TmdbConnector(settings=_make_settings(), client=client)

        candidates = await connector.get_trending()

        # Count expected valid items
        results = response["results"]
        expected_valid_count = sum(
            1
            for item in results
            if isinstance(item, dict)
            and isinstance(item.get("id"), int)
            and isinstance(item.get("title"), str)
        )

        assert len(candidates) == expected_valid_count

        # All returned candidates are proper MovieCandidates
        for candidate in candidates:
            assert isinstance(candidate, MovieCandidate)
            assert candidate.id.startswith("tmdb:")
            assert candidate.source == "tmdb"
            assert candidate.content_type == "movie"


# =============================================================================
# Property 2: Estructura TMDB inválida produce error
# =============================================================================


class TestProperty2InvalidStructure:
    """Property 2: Estructura TMDB inválida produce error.

    **Validates: Requirements 1.4, 1.16, 1.22**
    """

    @given(response_body=invalid_tmdb_response())
    @settings(deadline=None, max_examples=100)
    @pytest.mark.asyncio
    async def test_invalid_structure_raises_error(
        self, response_body: dict[str, Any]
    ) -> None:
        """A response without valid `results` list raises TmdbInvalidResponseError.

        **Validates: Requirements 1.4, 1.16, 1.22**
        """
        transport = _make_mock_transport(response_body)
        client = httpx.AsyncClient(transport=transport)
        connector = TmdbConnector(settings=_make_settings(), client=client)

        with pytest.raises(TmdbInvalidResponseError) as exc_info:
            await connector.fetch_trending_raw()

        # Verify error has required fields (Req 1.22)
        error = exc_info.value
        assert hasattr(error, "message")
        assert hasattr(error, "operation")
        assert isinstance(error.message, str)
        assert isinstance(error.operation, str)
        assert len(error.message) > 0
        assert len(error.operation) > 0


# =============================================================================
# Property 7: Round-trip parcial de MovieCandidate
# =============================================================================


class TestProperty7RoundTrip:
    """Property 7: Round-trip parcial de MovieCandidate.

    **Validates: Requirements 3.7**
    """

    @given(response=tmdb_response(min_results=1, max_results=20))
    @settings(deadline=None, max_examples=100)
    @pytest.mark.asyncio
    async def test_round_trip_preserves_key_fields(
        self, response: dict[str, Any]
    ) -> None:
        """Mapping TMDB objects to MovieCandidate and serializing preserves
        id, title, genres, and source.

        **Validates: Requirements 3.7**
        """
        transport = _make_mock_transport(response)
        client = httpx.AsyncClient(transport=transport)
        connector = TmdbConnector(settings=_make_settings(), client=client)

        candidates = await connector.get_trending()

        results = response["results"]
        valid_items = [
            item
            for item in results
            if isinstance(item, dict)
            and isinstance(item.get("id"), int)
            and isinstance(item.get("title"), str)
        ]

        for candidate, item in zip(candidates, valid_items):
            # Serialize to dict (simulating model_dump)
            serialized = candidate.model_dump()

            # Verify round-trip preservation
            assert serialized["id"] == f"tmdb:{item['id']}"
            assert serialized["title"] == item["title"]
            assert serialized["source"] == "tmdb"

            # Genres round-trip
            genre_ids = item.get("genre_ids")
            if isinstance(genre_ids, list):
                expected_genres = [str(gid) for gid in genre_ids]
            else:
                expected_genres = []
            assert serialized["genres"] == expected_genres
