# tests/integration/test_meilisearch_ingest.py
"""Integration tests for Meilisearch ingest and query.

Requires a running Meilisearch server at localhost:7700.
These tests are marked @pytest.mark.integration so they don't run in CI.

Tests verify:
- MeilisearchIndexer ingests a canonical dataset correctly
- Document count and attributes are configured properly
- MeilisearchNetflixRepository queries with genre (AND), actor (OR),
  director (OR), and combined filters work as expected

Requirements: 5.4, 5.5, 5.6, 5.11, 5.15, 10.3e, 10.3f, 10.8k
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import time
from pathlib import Path

import meilisearch
import pytest

from moviebot.agents.netflix.models import NetflixQuery
from moviebot.indexer.meilisearch_indexer import (
    IndexerConfig,
    MeilisearchIndexer,
)
from moviebot.repositories.netflix_meilisearch import MeilisearchNetflixRepository

MEILISEARCH_URL = "http://localhost:7700"
TEST_INDEX_VERSION = "integration_test"
TEST_INDEX_NAME = f"netflix_{TEST_INDEX_VERSION}"


# ─── Fixture Data ────────────────────────────────────────────────────────────


CANONICAL_DOCUMENTS = [
    {
        "id": "tm10001",
        "title": "The Great Adventure",
        "type": "movie",
        "release_year": 2020,
        "description": "An epic journey across the world.",
        "age_certification": "PG-13",
        "genres": ["action", "adventure"],
        "actors": ["tom hanks", "meg ryan"],
        "directors": ["steven spielberg"],
        "imdb_score": 7.5,
        "tmdb_score": 7.2,
        "tmdb_popularity": 120.5,
    },
    {
        "id": "tm10002",
        "title": "Drama in the City",
        "type": "movie",
        "release_year": 2019,
        "description": "A compelling drama set in New York.",
        "age_certification": "R",
        "genres": ["drama"],
        "actors": ["robert de niro", "al pacino"],
        "directors": ["martin scorsese"],
        "imdb_score": 8.1,
        "tmdb_score": 8.0,
        "tmdb_popularity": 200.0,
    },
    {
        "id": "tm10003",
        "title": "Comedy Night",
        "type": "movie",
        "release_year": 2021,
        "description": "A hilarious comedy about friendship.",
        "age_certification": "PG",
        "genres": ["comedy", "drama"],
        "actors": ["tom hanks", "julia roberts"],
        "directors": ["steven spielberg"],
        "imdb_score": 6.8,
        "tmdb_score": 6.5,
        "tmdb_popularity": 90.0,
    },
    {
        "id": "ts10004",
        "title": "Mystery Series",
        "type": "show",
        "release_year": 2022,
        "description": "A thrilling mystery show.",
        "age_certification": "TV-MA",
        "genres": ["drama", "mystery"],
        "actors": ["robert de niro"],
        "directors": ["david fincher"],
        "imdb_score": 8.5,
        "tmdb_score": 8.3,
        "tmdb_popularity": 300.0,
    },
    {
        "id": "tm10005",
        "title": "Action Explosion",
        "type": "movie",
        "release_year": 2018,
        "description": "Non-stop action from start to finish.",
        "age_certification": "R",
        "genres": ["action"],
        "actors": ["al pacino"],
        "directors": ["martin scorsese", "david fincher"],
        "imdb_score": 6.0,
        "tmdb_score": 5.8,
        "tmdb_popularity": 150.0,
    },
]


# ─── Fixtures ────────────────────────────────────────────────────────────────


@pytest.fixture(scope="module")
def canonical_dataset(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """Create a temporary canonical dataset directory with titles.jsonl and metadata.json."""
    base_dir = tmp_path_factory.mktemp("canonical")
    version_dir = base_dir / TEST_INDEX_VERSION
    version_dir.mkdir()

    # Write titles.jsonl
    titles_path = version_dir / "titles.jsonl"
    jsonl_content = (
        "\n".join(
            json.dumps(doc, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
            for doc in CANONICAL_DOCUMENTS
        )
        + "\n"
    )
    titles_path.write_text(jsonl_content, encoding="utf-8")

    # Compute checksum
    checksum = hashlib.sha256(titles_path.read_bytes()).hexdigest()

    # Write metadata.json
    metadata = {
        "canonical_dataset_version": TEST_INDEX_VERSION,
        "etl_version": "1.0.0",
        "schema_version": "1.0.0",
        "document_count": len(CANONICAL_DOCUMENTS),
        "discarded_count": 0,
        "source_checksums": {
            "titles.csv": "a" * 64,
            "credits.csv": "b" * 64,
        },
        "output_checksum_sha256": checksum,
        "generated_at": "2024-01-15T10:30:00Z",
        "type_distribution": {"movie": 4, "show": 1},
    }
    metadata_path = version_dir / "metadata.json"
    metadata_path.write_text(
        json.dumps(metadata, sort_keys=True, separators=(",", ":"), ensure_ascii=False),
        encoding="utf-8",
    )

    return base_dir


@pytest.fixture(scope="module")
def registry_path(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """Create a temporary registry file."""
    base_dir = tmp_path_factory.mktemp("registry")
    registry_file = base_dir / "index_registry.json"
    registry_file.write_text(
        json.dumps({"active_index": None, "indexes": {}}, indent=2),
        encoding="utf-8",
    )
    return registry_file


@pytest.fixture(scope="module")
def ingested_index(canonical_dataset: Path, registry_path: Path):
    """Ingest the test dataset and return the index name.

    This fixture runs once per module and cleans up after all tests complete.
    """
    titles_path = canonical_dataset / TEST_INDEX_VERSION / "titles.jsonl"

    config = IndexerConfig(
        meilisearch_url=MEILISEARCH_URL,
        meilisearch_api_key=None,
        canonical_dataset_version=TEST_INDEX_VERSION,
        schema_version="1.0.0",
        titles_jsonl_path=titles_path,
        registry_path=registry_path,
        batch_size=10,
        task_timeout_seconds=30,
    )

    indexer = MeilisearchIndexer(config)
    loop = asyncio.new_event_loop()
    try:
        result = loop.run_until_complete(indexer.ingest())
    finally:
        loop.close()

    assert result.index_name == TEST_INDEX_NAME
    assert result.document_count == len(CANONICAL_DOCUMENTS)
    assert result.activated is True

    # Give Meilisearch a moment to fully commit
    time.sleep(0.5)

    yield TEST_INDEX_NAME

    # Cleanup: delete the test index
    try:
        client = meilisearch.Client(MEILISEARCH_URL)
        task = client.delete_index(TEST_INDEX_NAME)
        # Wait for deletion to complete
        client.wait_for_task(task.task_uid, timeout_in_ms=10000)
    except (meilisearch.errors.MeilisearchApiError, OSError):
        pass  # Best effort cleanup


@pytest.fixture(scope="module")
def repository(ingested_index: str) -> MeilisearchNetflixRepository:
    """Create a repository pointing at the test index."""
    return MeilisearchNetflixRepository(
        meilisearch_url=MEILISEARCH_URL,
        index_name=ingested_index,
        limit=20,
    )


# ─── Helper ──────────────────────────────────────────────────────────────────


def run_async(coro):
    """Run an async coroutine synchronously."""
    return asyncio.run(coro)


# ─── Test: Indexer Configuration ─────────────────────────────────────────────


@pytest.mark.integration
class TestMeilisearchIngest:
    """Tests for MeilisearchIndexer ingestion."""

    def test_document_count_matches(self, ingested_index: str):
        """Verify the correct number of documents were ingested. (Req 5.15)"""
        client = meilisearch.Client(MEILISEARCH_URL)
        index = client.get_index(ingested_index)
        stats = index.get_stats()
        assert stats["numberOfDocuments"] == len(CANONICAL_DOCUMENTS)

    def test_searchable_attributes_configured(self, ingested_index: str):
        """Verify searchableAttributes are properly set. (Req 5.4)"""
        client = meilisearch.Client(MEILISEARCH_URL)
        index = client.get_index(ingested_index)
        settings = index.get_settings()

        expected = ["title", "description", "genres", "actors", "directors"]
        assert settings["searchableAttributes"] == expected

    def test_filterable_attributes_configured(self, ingested_index: str):
        """Verify filterableAttributes are properly set. (Req 5.5)"""
        client = meilisearch.Client(MEILISEARCH_URL)
        index = client.get_index(ingested_index)
        settings = index.get_settings()

        expected = sorted(
            [
                "type",
                "genres",
                "release_year",
                "age_certification",
                "imdb_score",
                "tmdb_score",
                "actors",
                "directors",
            ]
        )
        actual = sorted(settings["filterableAttributes"])
        assert actual == expected

    def test_actors_searchable_and_filterable(self, ingested_index: str):
        """Verify actors is both searchable and filterable. (Req 5.11)"""
        client = meilisearch.Client(MEILISEARCH_URL)
        index = client.get_index(ingested_index)
        settings = index.get_settings()

        assert "actors" in settings["searchableAttributes"]
        assert "actors" in settings["filterableAttributes"]

    def test_directors_searchable_and_filterable(self, ingested_index: str):
        """Verify directors is both searchable and filterable. (Req 5.11)"""
        client = meilisearch.Client(MEILISEARCH_URL)
        index = client.get_index(ingested_index)
        settings = index.get_settings()

        assert "directors" in settings["searchableAttributes"]
        assert "directors" in settings["filterableAttributes"]


# ─── Test: Repository Query Filters ─────────────────────────────────────────


@pytest.mark.integration
class TestMeilisearchQuery:
    """Tests for MeilisearchNetflixRepository query filtering."""

    def test_genre_filter_and_semantics(self, repository: MeilisearchNetflixRepository):
        """Genres use AND semantics: docs must contain ALL specified genres.

        Req 5.5 (filterableAttributes includes genres)
        Req 10.8k (genre AND filter)
        """
        # "comedy" AND "drama" — only tm10003 has both
        query = NetflixQuery(genres=["comedy", "drama"])
        results = run_async(repository.search(query))

        result_ids = [r.id for r in results]
        assert "tm10003" in result_ids
        # tm10002 has only "drama", should not appear
        assert "tm10002" not in result_ids

    def test_single_genre_filter(self, repository: MeilisearchNetflixRepository):
        """Single genre filter returns all docs with that genre."""
        query = NetflixQuery(genres=["action"])
        results = run_async(repository.search(query))

        result_ids = [r.id for r in results]
        assert "tm10001" in result_ids  # action, adventure
        assert "tm10005" in result_ids  # action
        # Others don't have "action"
        assert "tm10002" not in result_ids
        assert "ts10004" not in result_ids

    def test_actor_filter_or_semantics(self, repository: MeilisearchNetflixRepository):
        """Actors use OR semantics: docs with at least one specified actor.

        Req 10.3e (actors filterable)
        """
        # "robert de niro" OR "tom hanks"
        query = NetflixQuery(actors=["robert de niro", "tom hanks"])
        results = run_async(repository.search(query))

        result_ids = [r.id for r in results]
        # tom hanks: tm10001, tm10003
        # robert de niro: tm10002, ts10004
        assert "tm10001" in result_ids
        assert "tm10002" in result_ids
        assert "tm10003" in result_ids
        assert "ts10004" in result_ids
        # al pacino only (tm10005) should NOT be here
        assert "tm10005" not in result_ids

    def test_single_actor_filter(self, repository: MeilisearchNetflixRepository):
        """Single actor filter returns docs containing that actor."""
        query = NetflixQuery(actors=["al pacino"])
        results = run_async(repository.search(query))

        result_ids = [r.id for r in results]
        assert "tm10002" in result_ids  # al pacino is in this movie
        assert "tm10005" in result_ids  # al pacino is in this movie
        assert "tm10001" not in result_ids

    def test_director_filter_or_semantics(
        self, repository: MeilisearchNetflixRepository
    ):
        """Directors use OR semantics: docs with at least one specified director.

        Req 10.3f (directors filterable)
        """
        # "steven spielberg" OR "david fincher"
        query = NetflixQuery(directors=["steven spielberg", "david fincher"])
        results = run_async(repository.search(query))

        result_ids = [r.id for r in results]
        # steven spielberg: tm10001, tm10003
        # david fincher: ts10004, tm10005
        assert "tm10001" in result_ids
        assert "tm10003" in result_ids
        assert "ts10004" in result_ids
        assert "tm10005" in result_ids
        # martin scorsese only → tm10002 should NOT be here
        assert "tm10002" not in result_ids

    def test_single_director_filter(self, repository: MeilisearchNetflixRepository):
        """Single director filter returns docs with that director."""
        query = NetflixQuery(directors=["martin scorsese"])
        results = run_async(repository.search(query))

        result_ids = [r.id for r in results]
        assert "tm10002" in result_ids
        assert "tm10005" in result_ids
        assert "tm10001" not in result_ids

    def test_combined_actor_and_director_filter(
        self, repository: MeilisearchNetflixRepository
    ):
        """Combined actor AND director uses AND inter-field semantics.

        Docs must match at least one actor AND at least one director.
        Req 10.3e, 10.3f
        """
        # actor: "tom hanks" AND director: "steven spielberg"
        # tm10001: tom hanks + steven spielberg ✓
        # tm10003: tom hanks + steven spielberg ✓
        query = NetflixQuery(actors=["tom hanks"], directors=["steven spielberg"])
        results = run_async(repository.search(query))

        result_ids = [r.id for r in results]
        assert "tm10001" in result_ids
        assert "tm10003" in result_ids
        assert "tm10002" not in result_ids
        assert "ts10004" not in result_ids
        assert "tm10005" not in result_ids

    def test_combined_actor_director_no_match(
        self, repository: MeilisearchNetflixRepository
    ):
        """Combined actor + director with no overlapping docs → empty results."""
        # actor: "tom hanks" (tm10001, tm10003) AND director: "martin scorsese" (tm10002, tm10005)
        # No doc has both tom hanks AND martin scorsese
        query = NetflixQuery(actors=["tom hanks"], directors=["martin scorsese"])
        results = run_async(repository.search(query))
        assert results == []

    def test_genre_and_actor_combined(self, repository: MeilisearchNetflixRepository):
        """Combined genre AND actor filter: must satisfy both."""
        # genre: "drama" AND actor: "tom hanks"
        # tm10003 has genres=["comedy","drama"] and actors=["tom hanks","julia roberts"] ✓
        # tm10001 has genres=["action","adventure"] — no drama ✗
        query = NetflixQuery(genres=["drama"], actors=["tom hanks"])
        results = run_async(repository.search(query))

        result_ids = [r.id for r in results]
        assert "tm10003" in result_ids
        assert "tm10001" not in result_ids

    def test_nonexistent_actor_returns_empty(
        self, repository: MeilisearchNetflixRepository
    ):
        """Non-existent actor returns empty results (no relaxation). (Req 6.10)"""
        query = NetflixQuery(actors=["nonexistent actor xyz"])
        results = run_async(repository.search(query))
        assert results == []

    def test_nonexistent_director_returns_empty(
        self, repository: MeilisearchNetflixRepository
    ):
        """Non-existent director returns empty results (no relaxation). (Req 6.10)"""
        query = NetflixQuery(directors=["nonexistent director xyz"])
        results = run_async(repository.search(query))
        assert results == []

    def test_type_filter_movie(self, repository: MeilisearchNetflixRepository):
        """Type filter 'movie' returns only movies."""
        query = NetflixQuery(type="movie")
        results = run_async(repository.search(query))

        for result in results:
            assert result.content_type == "movie"
        result_ids = [r.id for r in results]
        assert "ts10004" not in result_ids  # This is a show

    def test_type_filter_show(self, repository: MeilisearchNetflixRepository):
        """Type filter 'show' returns only shows."""
        query = NetflixQuery(type="show")
        results = run_async(repository.search(query))

        for result in results:
            assert result.content_type == "show"
        result_ids = [r.id for r in results]
        assert "ts10004" in result_ids

    def test_year_range_filter(self, repository: MeilisearchNetflixRepository):
        """Year range filter applies correctly."""
        query = NetflixQuery(min_year=2020, max_year=2022)
        results = run_async(repository.search(query))

        result_ids = [r.id for r in results]
        # 2020: tm10001, 2021: tm10003, 2022: ts10004
        assert "tm10001" in result_ids
        assert "tm10003" in result_ids
        assert "ts10004" in result_ids
        # 2019: tm10002, 2018: tm10005 — out of range
        assert "tm10002" not in result_ids
        assert "tm10005" not in result_ids

    def test_result_mapping_to_movie_candidate(
        self, repository: MeilisearchNetflixRepository
    ):
        """Results are correctly mapped to MovieCandidate with source='netflix'."""
        query = NetflixQuery(actors=["tom hanks"], type="movie")
        results = run_async(repository.search(query))

        assert len(results) > 0
        for candidate in results:
            assert candidate.source == "netflix"
            assert candidate.content_type in ("movie", "show")
            assert candidate.id is not None
            assert candidate.title is not None

    def test_empty_query_returns_all_documents(
        self, repository: MeilisearchNetflixRepository
    ):
        """Empty semantic_query with no filters returns all documents. (Req 6.3)"""
        query = NetflixQuery()
        results = run_async(repository.search(query))

        # Should return all 5 documents (within limit)
        assert len(results) == len(CANONICAL_DOCUMENTS)
