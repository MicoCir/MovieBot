"""Unit tests for FixtureRegistry class."""

import json
import pathlib

import pytest

from silver_dataset.models.case import Suite
from silver_dataset.models.fixtures import FixtureRegistry


@pytest.fixture
def sample_fixtures_dir(tmp_path: pathlib.Path) -> pathlib.Path:
    """Create a temp fixtures directory with sample fixture files."""
    tmdb_dir = tmp_path / "tmdb"
    tmdb_dir.mkdir()
    netflix_dir = tmp_path / "netflix"
    netflix_dir.mkdir()

    # TMDB fixture with 'id' field in results
    tmdb_fixture = {
        "page": 1,
        "results": [
            {"id": 123, "title": "Movie A", "overview": "A great movie"},
            {"id": 456, "title": "Movie B", "overview": "Another movie"},
            {"id": 789, "title": "Movie C", "overview": "Yet another"},
        ],
        "total_pages": 1,
        "total_results": 3,
    }
    (tmdb_dir / "tmdb_trending_normal.json").write_text(
        json.dumps(tmdb_fixture), encoding="utf-8"
    )

    # TMDB empty fixture
    tmdb_empty = {"page": 1, "results": [], "total_pages": 0, "total_results": 0}
    (tmdb_dir / "tmdb_trending_empty.json").write_text(
        json.dumps(tmdb_empty), encoding="utf-8"
    )

    # Netflix fixture with 'show_id' field in results
    netflix_fixture = {
        "results": [
            {"show_id": "s1", "title": "Show A", "type": "Movie"},
            {"show_id": "s2", "title": "Show B", "type": "TV Show"},
        ],
        "total": 2,
    }
    (netflix_dir / "netflix_search_comedy.json").write_text(
        json.dumps(netflix_fixture), encoding="utf-8"
    )

    return tmp_path


class TestFixtureRegistry:
    """Tests for FixtureRegistry."""

    def test_get_fixture_returns_data(self, sample_fixtures_dir: pathlib.Path) -> None:
        registry = FixtureRegistry(sample_fixtures_dir)
        fixture = registry.get_fixture("tmdb_trending_normal")
        assert fixture is not None
        assert fixture["total_results"] == 3
        assert len(fixture["results"]) == 3

    def test_get_fixture_returns_none_for_missing(
        self, sample_fixtures_dir: pathlib.Path
    ) -> None:
        registry = FixtureRegistry(sample_fixtures_dir)
        assert registry.get_fixture("tmdb_nonexistent") is None

    def test_get_fixture_returns_none_for_unknown_prefix(
        self, sample_fixtures_dir: pathlib.Path
    ) -> None:
        registry = FixtureRegistry(sample_fixtures_dir)
        assert registry.get_fixture("unknown_fixture") is None

    def test_fixture_exists_true(self, sample_fixtures_dir: pathlib.Path) -> None:
        registry = FixtureRegistry(sample_fixtures_dir)
        assert registry.fixture_exists("tmdb_trending_normal") is True
        assert registry.fixture_exists("netflix_search_comedy") is True

    def test_fixture_exists_false(self, sample_fixtures_dir: pathlib.Path) -> None:
        registry = FixtureRegistry(sample_fixtures_dir)
        assert registry.fixture_exists("tmdb_nonexistent") is False
        assert registry.fixture_exists("unknown_prefix_thing") is False

    def test_get_item_ids_tmdb(self, sample_fixtures_dir: pathlib.Path) -> None:
        registry = FixtureRegistry(sample_fixtures_dir)
        ids = registry.get_item_ids("tmdb_trending_normal")
        assert ids == {"123", "456", "789"}

    def test_get_item_ids_netflix(self, sample_fixtures_dir: pathlib.Path) -> None:
        registry = FixtureRegistry(sample_fixtures_dir)
        ids = registry.get_item_ids("netflix_search_comedy")
        assert ids == {"s1", "s2"}

    def test_get_item_ids_empty_results(
        self, sample_fixtures_dir: pathlib.Path
    ) -> None:
        registry = FixtureRegistry(sample_fixtures_dir)
        ids = registry.get_item_ids("tmdb_trending_empty")
        assert ids == set()

    def test_get_item_ids_missing_fixture(
        self, sample_fixtures_dir: pathlib.Path
    ) -> None:
        registry = FixtureRegistry(sample_fixtures_dir)
        ids = registry.get_item_ids("tmdb_nonexistent")
        assert ids == set()

    def test_list_fixtures_all(self, sample_fixtures_dir: pathlib.Path) -> None:
        registry = FixtureRegistry(sample_fixtures_dir)
        all_fixtures = registry.list_fixtures()
        assert all_fixtures == sorted(
            ["netflix_search_comedy", "tmdb_trending_empty", "tmdb_trending_normal"]
        )

    def test_list_fixtures_filtered_tmdb(
        self, sample_fixtures_dir: pathlib.Path
    ) -> None:
        registry = FixtureRegistry(sample_fixtures_dir)
        tmdb_fixtures = registry.list_fixtures(suite=Suite.tmdb_agent_silver)
        assert tmdb_fixtures == ["tmdb_trending_empty", "tmdb_trending_normal"]

    def test_list_fixtures_filtered_netflix(
        self, sample_fixtures_dir: pathlib.Path
    ) -> None:
        registry = FixtureRegistry(sample_fixtures_dir)
        netflix_fixtures = registry.list_fixtures(suite=Suite.netflix_agent_silver)
        assert netflix_fixtures == ["netflix_search_comedy"]

    def test_list_fixtures_e2e_returns_all(
        self, sample_fixtures_dir: pathlib.Path
    ) -> None:
        registry = FixtureRegistry(sample_fixtures_dir)
        all_fixtures = registry.list_fixtures(suite=Suite.e2e_routing_silver)
        assert len(all_fixtures) == 3

    def test_caching_returns_same_object(
        self, sample_fixtures_dir: pathlib.Path
    ) -> None:
        registry = FixtureRegistry(sample_fixtures_dir)
        first = registry.get_fixture("tmdb_trending_normal")
        second = registry.get_fixture("tmdb_trending_normal")
        assert first is second
