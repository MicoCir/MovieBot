# tests/unit/test_netflix_repository.py
"""Unit tests for MeilisearchNetflixRepository.

Tests filter construction, type filtering, empty semantic_query behavior,
age_certification OR semantics, actor/director filter semantics,
error handling, and _escape_filter_value.

Validates: Requirements 6.1–6.15, 10.8b–h
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from moviebot.agents.netflix.models import NetflixQuery
from moviebot.common.models import MovieCandidate
from moviebot.repositories.netflix_meilisearch import MeilisearchNetflixRepository

# ─── Helpers ────────────────────────────────────────────────────────────────


def _make_repo(
    index_name: str = "netflix_v1",
    limit: int = 20,
) -> MeilisearchNetflixRepository:
    """Create a repository instance with a mocked meilisearch client."""
    with patch("moviebot.repositories.netflix_meilisearch.meilisearch.Client"):
        repo = MeilisearchNetflixRepository(
            meilisearch_url="http://localhost:7700",
            meilisearch_api_key="test-key",
            index_name=index_name,
            limit=limit,
        )
    return repo


def _make_hit(
    id: str = "tm001",
    title: str = "Test Movie",
    type: str = "movie",
    release_year: int = 2020,
    description: str | None = "A test movie",
    genres: list[str] | None = None,
) -> dict:
    """Create a Meilisearch hit dict."""
    hit: dict = {
        "id": id,
        "title": title,
        "type": type,
        "release_year": release_year,
    }
    if description is not None:
        hit["description"] = description
    if genres is not None:
        hit["genres"] = genres
    else:
        hit["genres"] = ["drama"]
    return hit


# ─── Tests: _build_filter – Genre Filters ───────────────────────────────────


class TestBuildFilterGenres:
    """Test genre filter construction with AND semantics."""

    def test_single_genre_produces_equality_filter(self) -> None:
        """Single genre produces: genres = "drama"."""
        repo = _make_repo()
        query = NetflixQuery(genres=["Drama"])
        result = repo._build_filter(query)
        assert result == 'genres = "drama"'

    def test_multi_genre_produces_and_filter(self) -> None:
        """Multiple genres produce AND: genres = "drama" AND genres = "crime"."""
        repo = _make_repo()
        query = NetflixQuery(genres=["Drama", "Crime"])
        result = repo._build_filter(query)
        assert 'genres = "drama"' in result
        assert 'genres = "crime"' in result
        assert " AND " in result

    def test_genres_normalized_to_lowercase(self) -> None:
        """Genre values are normalized to lowercase."""
        repo = _make_repo()
        query = NetflixQuery(genres=["Science Fiction"])
        result = repo._build_filter(query)
        assert 'genres = "science fiction"' in result

    def test_genres_trimmed(self) -> None:
        """Genre values are trimmed of whitespace."""
        repo = _make_repo()
        query = NetflixQuery(genres=["  Drama  "])
        result = repo._build_filter(query)
        assert 'genres = "drama"' in result


# ─── Tests: _build_filter – Actor Filters ───────────────────────────────────


class TestBuildFilterActors:
    """Test actor filter construction with OR semantics."""

    def test_single_actor_produces_equality_filter(self) -> None:
        """Single actor produces: actors = "tom hanks"."""
        repo = _make_repo()
        query = NetflixQuery(actors=["Tom Hanks"])
        result = repo._build_filter(query)
        assert result == 'actors = "tom hanks"'

    def test_multiple_actors_produce_or_filter(self) -> None:
        """Multiple actors produce OR: (actors = "tom hanks" OR actors = "meg ryan")."""
        repo = _make_repo()
        query = NetflixQuery(actors=["Tom Hanks", "Meg Ryan"])
        result = repo._build_filter(query)
        assert 'actors = "tom hanks"' in result
        assert 'actors = "meg ryan"' in result
        assert " OR " in result

    def test_actors_normalized_to_lowercase(self) -> None:
        """Actor names are normalized to lowercase."""
        repo = _make_repo()
        query = NetflixQuery(actors=["Robert De Niro"])
        result = repo._build_filter(query)
        assert 'actors = "robert de niro"' in result


# ─── Tests: _build_filter – Director Filters ────────────────────────────────


class TestBuildFilterDirectors:
    """Test director filter construction with OR semantics."""

    def test_single_director_produces_equality_filter(self) -> None:
        """Single director produces: directors = "steven spielberg"."""
        repo = _make_repo()
        query = NetflixQuery(directors=["Steven Spielberg"])
        result = repo._build_filter(query)
        assert result == 'directors = "steven spielberg"'

    def test_multiple_directors_produce_or_filter(self) -> None:
        """Multiple directors produce OR: (directors = "spielberg" OR directors = "nolan")."""
        repo = _make_repo()
        query = NetflixQuery(directors=["Steven Spielberg", "Christopher Nolan"])
        result = repo._build_filter(query)
        assert 'directors = "steven spielberg"' in result
        assert 'directors = "christopher nolan"' in result
        assert " OR " in result

    def test_directors_normalized_to_lowercase(self) -> None:
        """Director names are normalized to lowercase."""
        repo = _make_repo()
        query = NetflixQuery(directors=["Martin Scorsese"])
        result = repo._build_filter(query)
        assert 'directors = "martin scorsese"' in result


# ─── Tests: _build_filter – Actor + Director AND inter-campo ────────────────


class TestBuildFilterActorDirectorCombined:
    """Test that actors + directors combine with AND inter-campo."""

    def test_actor_and_director_combined_with_and(self) -> None:
        """Actor + director produce AND inter-campo."""
        repo = _make_repo()
        query = NetflixQuery(actors=["Tom Hanks"], directors=["Steven Spielberg"])
        result = repo._build_filter(query)
        assert 'actors = "tom hanks"' in result
        assert 'directors = "steven spielberg"' in result
        assert " AND " in result

    def test_multiple_actors_and_directors_combined(self) -> None:
        """Multiple actors OR + multiple directors OR combined with AND."""
        repo = _make_repo()
        query = NetflixQuery(
            actors=["Tom Hanks", "Meg Ryan"],
            directors=["Steven Spielberg", "Nora Ephron"],
        )
        result = repo._build_filter(query)
        # Should have OR within actors group, OR within directors, AND between groups
        assert 'actors = "tom hanks"' in result
        assert 'actors = "meg ryan"' in result
        assert 'directors = "steven spielberg"' in result
        assert 'directors = "nora ephron"' in result
        # The actor/director groups are parenthesized and joined with AND
        assert " AND " in result


# ─── Tests: _build_filter – Age Certification OR ────────────────────────────


class TestBuildFilterAgeCertification:
    """Test age_certification filter with OR semantics."""

    def test_single_certification(self) -> None:
        """Single certification produces equality filter."""
        repo = _make_repo()
        query = NetflixQuery(age_certification=["PG-13"])
        result = repo._build_filter(query)
        assert 'age_certification = "pg-13"' in result

    def test_multiple_certifications_produce_or(self) -> None:
        """Multiple certifications produce OR."""
        repo = _make_repo()
        query = NetflixQuery(age_certification=["PG-13", "R"])
        result = repo._build_filter(query)
        assert 'age_certification = "pg-13"' in result
        assert 'age_certification = "r"' in result
        assert " OR " in result

    def test_certifications_normalized_lowercase(self) -> None:
        """Age certification values are normalized to lowercase."""
        repo = _make_repo()
        query = NetflixQuery(age_certification=["TV-MA"])
        result = repo._build_filter(query)
        assert 'age_certification = "tv-ma"' in result


# ─── Tests: _build_filter – Type Filter ─────────────────────────────────────


class TestBuildFilterType:
    """Test type filter construction."""

    def test_type_movie_produces_filter(self) -> None:
        """type="movie" produces type = "movie" filter."""
        repo = _make_repo()
        query = NetflixQuery(type="movie")
        result = repo._build_filter(query)
        assert result == 'type = "movie"'

    def test_type_show_produces_filter(self) -> None:
        """type="show" produces type = "show" filter."""
        repo = _make_repo()
        query = NetflixQuery(type="show")
        result = repo._build_filter(query)
        assert result == 'type = "show"'

    def test_type_any_no_filter(self) -> None:
        """type="any" does not produce a type filter."""
        repo = _make_repo()
        query = NetflixQuery(type="any")
        result = repo._build_filter(query)
        assert result is None


# ─── Tests: _build_filter – Empty / No filters ──────────────────────────────


class TestBuildFilterEmpty:
    """Test _build_filter with no constraints returns None."""

    def test_empty_query_returns_none(self) -> None:
        """An empty NetflixQuery produces no filter."""
        repo = _make_repo()
        query = NetflixQuery()
        result = repo._build_filter(query)
        assert result is None

    def test_only_semantic_query_returns_none(self) -> None:
        """A query with only semantic_query produces no filter."""
        repo = _make_repo()
        query = NetflixQuery(semantic_query="action movies")
        result = repo._build_filter(query)
        assert result is None


# ─── Tests: _build_filter – Year Range ──────────────────────────────────────


class TestBuildFilterYearRange:
    """Test year range filter construction."""

    def test_min_year_only(self) -> None:
        """min_year produces >= filter."""
        repo = _make_repo()
        query = NetflixQuery(min_year=2020)
        result = repo._build_filter(query)
        assert result == "release_year >= 2020"

    def test_max_year_only(self) -> None:
        """max_year produces <= filter."""
        repo = _make_repo()
        query = NetflixQuery(max_year=2022)
        result = repo._build_filter(query)
        assert result == "release_year <= 2022"

    def test_both_year_range(self) -> None:
        """Both min_year and max_year produce range filter."""
        repo = _make_repo()
        query = NetflixQuery(min_year=2020, max_year=2022)
        result = repo._build_filter(query)
        assert "release_year >= 2020" in result
        assert "release_year <= 2022" in result
        assert " AND " in result


# ─── Tests: _escape_filter_value ─────────────────────────────────────────────


class TestEscapeFilterValue:
    """Test _escape_filter_value with special characters."""

    def test_plain_string_unchanged(self) -> None:
        """A string with no special characters is unchanged."""
        result = MeilisearchNetflixRepository._escape_filter_value("tom hanks")
        assert result == "tom hanks"

    def test_double_quotes_escaped(self) -> None:
        """Double quotes are escaped with backslash."""
        result = MeilisearchNetflixRepository._escape_filter_value('Someone "Special"')
        assert result == 'Someone \\"Special\\"'

    def test_backslashes_escaped(self) -> None:
        """Backslashes are escaped before quotes."""
        result = MeilisearchNetflixRepository._escape_filter_value("path\\to\\file")
        assert result == "path\\\\to\\\\file"

    def test_single_quotes_not_escaped(self) -> None:
        """Single quotes do not need escaping in double-quoted strings."""
        result = MeilisearchNetflixRepository._escape_filter_value("O'Connor")
        assert result == "O'Connor"

    def test_hyphens_preserved(self) -> None:
        """Hyphens are preserved without escaping."""
        result = MeilisearchNetflixRepository._escape_filter_value("jean-luc picard")
        assert result == "jean-luc picard"

    def test_backslash_before_quote(self) -> None:
        """Backslash followed by quote: both are escaped correctly."""
        result = MeilisearchNetflixRepository._escape_filter_value('test\\"value')
        assert result == 'test\\\\\\"value'


# ─── Tests: search() – Happy Path ───────────────────────────────────────────


class TestSearchHappyPath:
    """Test search method maps results and applies filters."""

    @pytest.mark.asyncio
    async def test_search_returns_movie_candidates(self) -> None:
        """search() returns list of MovieCandidate from Meilisearch hits."""
        repo = _make_repo()

        hits = [
            _make_hit(id="tm001", title="Movie One", type="movie", release_year=2020),
            _make_hit(id="ts002", title="Show Two", type="show", release_year=2021),
        ]
        mock_result = {"hits": hits}

        mock_index = MagicMock()
        mock_index.search.return_value = mock_result
        repo._client = MagicMock()
        repo._client.index.return_value = mock_index

        query = NetflixQuery(semantic_query="action")

        with patch(
            "moviebot.repositories.netflix_meilisearch.asyncio.to_thread"
        ) as mock_to_thread:
            mock_to_thread.return_value = mock_result
            results = await repo.search(query)

        assert len(results) == 2
        assert all(isinstance(r, MovieCandidate) for r in results)
        assert results[0].id == "tm001"
        assert results[0].title == "Movie One"
        assert results[0].source == "netflix"
        assert results[0].content_type == "movie"
        assert results[0].release_year == 2020
        assert results[1].id == "ts002"
        assert results[1].content_type == "show"

    @pytest.mark.asyncio
    async def test_search_passes_filter_to_meilisearch(self) -> None:
        """search() passes constructed filter to Meilisearch search params."""
        repo = _make_repo()
        mock_result = {"hits": []}

        repo._client = MagicMock()
        repo._client.index.return_value.search.return_value = mock_result

        query = NetflixQuery(type="movie", genres=["Drama"])

        with patch(
            "moviebot.repositories.netflix_meilisearch.asyncio.to_thread"
        ) as mock_to_thread:
            mock_to_thread.return_value = mock_result
            await repo.search(query)

            # Verify to_thread was called with correct args
            call_args = mock_to_thread.call_args
            # First positional arg is the callable, second is search text
            search_text = call_args[0][1]
            search_params = call_args[0][2]

            assert search_text == ""
            assert "filter" in search_params
            assert 'type = "movie"' in search_params["filter"]
            assert 'genres = "drama"' in search_params["filter"]

    @pytest.mark.asyncio
    async def test_search_with_empty_semantic_query(self) -> None:
        """Empty semantic_query sends empty string to Meilisearch."""
        repo = _make_repo()
        mock_result = {"hits": []}

        repo._client = MagicMock()
        repo._client.index.return_value.search.return_value = mock_result

        query = NetflixQuery(type="movie")

        with patch(
            "moviebot.repositories.netflix_meilisearch.asyncio.to_thread"
        ) as mock_to_thread:
            mock_to_thread.return_value = mock_result
            await repo.search(query)

            call_args = mock_to_thread.call_args
            search_text = call_args[0][1]
            assert search_text == ""

    @pytest.mark.asyncio
    async def test_search_no_filters_omits_filter_param(self) -> None:
        """When no filters present, search_params does not include 'filter' key."""
        repo = _make_repo()
        mock_result = {"hits": []}

        repo._client = MagicMock()
        repo._client.index.return_value.search.return_value = mock_result

        query = NetflixQuery(semantic_query="fun movies")

        with patch(
            "moviebot.repositories.netflix_meilisearch.asyncio.to_thread"
        ) as mock_to_thread:
            mock_to_thread.return_value = mock_result
            await repo.search(query)

            call_args = mock_to_thread.call_args
            search_params = call_args[0][2]
            assert "filter" not in search_params
            assert search_params == {"limit": 20}


# ─── Tests: search() – Error Handling ────────────────────────────────────────


class TestSearchErrorHandling:
    """Test error handling: connection failures return empty list."""

    @pytest.mark.asyncio
    async def test_connection_failure_returns_empty_list(self) -> None:
        """When Meilisearch is unreachable, search returns empty list."""
        repo = _make_repo()

        query = NetflixQuery(semantic_query="action movies")

        with patch(
            "moviebot.repositories.netflix_meilisearch.asyncio.to_thread"
        ) as mock_to_thread:
            mock_to_thread.side_effect = Exception("Connection refused")
            results = await repo.search(query)

        assert results == []

    @pytest.mark.asyncio
    async def test_meilisearch_error_returns_empty_list(self) -> None:
        """Any Meilisearch exception returns empty list (no crash)."""
        repo = _make_repo()

        query = NetflixQuery(genres=["drama"])

        with patch(
            "moviebot.repositories.netflix_meilisearch.asyncio.to_thread"
        ) as mock_to_thread:
            mock_to_thread.side_effect = RuntimeError("Internal server error")
            results = await repo.search(query)

        assert results == []


# ─── Tests: search() – Actor/Director Not Found ─────────────────────────────


class TestSearchActorDirectorNotFound:
    """Test that actor/director not found returns empty list (no relaxation)."""

    @pytest.mark.asyncio
    async def test_actor_not_found_returns_empty(self) -> None:
        """When actor filter matches nothing, empty list returned (no relaxation)."""
        repo = _make_repo()
        mock_result = {"hits": []}

        with patch(
            "moviebot.repositories.netflix_meilisearch.asyncio.to_thread"
        ) as mock_to_thread:
            mock_to_thread.return_value = mock_result
            query = NetflixQuery(actors=["Nonexistent Actor"])
            results = await repo.search(query)

        assert results == []

    @pytest.mark.asyncio
    async def test_director_not_found_returns_empty(self) -> None:
        """When director filter matches nothing, empty list returned (no relaxation)."""
        repo = _make_repo()
        mock_result = {"hits": []}

        with patch(
            "moviebot.repositories.netflix_meilisearch.asyncio.to_thread"
        ) as mock_to_thread:
            mock_to_thread.return_value = mock_result
            query = NetflixQuery(directors=["Nonexistent Director"])
            results = await repo.search(query)

        assert results == []

    @pytest.mark.asyncio
    async def test_partial_name_not_found_returns_empty(self) -> None:
        """Partial name (e.g., 'spielberg') returns empty (exact match, no relaxation)."""
        repo = _make_repo()
        mock_result = {"hits": []}

        with patch(
            "moviebot.repositories.netflix_meilisearch.asyncio.to_thread"
        ) as mock_to_thread:
            mock_to_thread.return_value = mock_result
            query = NetflixQuery(directors=["spielberg"])
            results = await repo.search(query)

        assert results == []


# ─── Tests: _map_hit_to_candidate ────────────────────────────────────────────


class TestMapHitToCandidate:
    """Test hit-to-MovieCandidate mapping."""

    def test_full_hit_mapped_correctly(self) -> None:
        """All fields are mapped from hit to MovieCandidate."""
        repo = _make_repo()
        hit = {
            "id": "tm123",
            "title": "Great Movie",
            "type": "movie",
            "release_year": 2021,
            "description": "A great movie about things",
            "genres": ["drama", "thriller"],
        }
        candidate = repo._map_hit_to_candidate(hit)

        assert candidate.id == "tm123"
        assert candidate.title == "Great Movie"
        assert candidate.content_type == "movie"
        assert candidate.release_year == 2021
        assert candidate.description == "A great movie about things"
        assert candidate.genres == ["drama", "thriller"]
        assert candidate.source == "netflix"
        assert candidate.popularity is None
        assert candidate.vote_average is None

    def test_hit_without_description(self) -> None:
        """Hit without description maps to description=None."""
        repo = _make_repo()
        hit = {
            "id": "ts456",
            "title": "Some Show",
            "type": "show",
            "genres": [],
        }
        candidate = repo._map_hit_to_candidate(hit)

        assert candidate.description is None
        assert candidate.content_type == "show"

    def test_hit_without_release_year(self) -> None:
        """Hit without release_year maps to release_year=None."""
        repo = _make_repo()
        hit = {
            "id": "tm789",
            "title": "Unknown Year Movie",
            "type": "movie",
            "genres": ["comedy"],
        }
        candidate = repo._map_hit_to_candidate(hit)

        assert candidate.release_year is None


# ─── Tests: Combined Filters ────────────────────────────────────────────────


class TestBuildFilterCombined:
    """Test complex filter combinations."""

    def test_type_and_genres_and_actors(self) -> None:
        """type + genres + actors all combined with AND at top level."""
        repo = _make_repo()
        query = NetflixQuery(type="movie", genres=["drama"], actors=["Tom Hanks"])
        result = repo._build_filter(query)
        assert 'type = "movie"' in result
        assert 'genres = "drama"' in result
        assert 'actors = "tom hanks"' in result
        # All parts joined with AND
        parts = result.split(" AND ")
        assert len(parts) == 3

    def test_all_filters_together(self) -> None:
        """All filter types combined in a single query."""
        repo = _make_repo()
        query = NetflixQuery(
            type="movie",
            genres=["drama", "crime"],
            min_year=2015,
            max_year=2022,
            age_certification=["R", "PG-13"],
            actors=["Tom Hanks"],
            directors=["Steven Spielberg"],
        )
        result = repo._build_filter(query)
        assert result is not None
        assert 'type = "movie"' in result
        assert 'genres = "drama"' in result
        assert 'genres = "crime"' in result
        assert "release_year >= 2015" in result
        assert "release_year <= 2022" in result
        assert 'age_certification = "r"' in result
        assert 'age_certification = "pg-13"' in result
        assert 'actors = "tom hanks"' in result
        assert 'directors = "steven spielberg"' in result
