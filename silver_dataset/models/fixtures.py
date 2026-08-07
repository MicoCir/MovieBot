"""Fixture registry for deterministic tool output fixtures.

Manages TMDB and Netflix fixture JSON files used by the Silver Dataset
for reproducible, offline evaluation of the chatbot without external API calls.
"""

from __future__ import annotations

import json
from pathlib import Path

from silver_dataset.models.case import Suite


class FixtureRegistry:
    """Manages deterministic tool output fixtures.

    Fixtures are JSON files stored under a root directory with the structure:
        fixtures/tmdb/{fixture_id}.json
        fixtures/netflix/{fixture_id}.json

    Fixture IDs include a prefix identifying their source, e.g.:
        - tmdb_trending_normal
        - netflix_search_comedy
    """

    # Maps suite enum to the corresponding fixture subdirectory name
    _SUITE_TO_SOURCE: dict[Suite, str] = {
        Suite.tmdb_agent_silver: "tmdb",
        Suite.netflix_agent_silver: "netflix",
    }

    # Maps fixture prefix to source directory
    _PREFIX_TO_SOURCE: dict[str, str] = {
        "tmdb": "tmdb",
        "netflix": "netflix",
    }

    def __init__(self, fixtures_dir: Path) -> None:
        """Initialize the registry.

        Args:
            fixtures_dir: Path to the root fixtures directory containing
                          tmdb/ and netflix/ subdirectories.
        """
        self._fixtures_dir = fixtures_dir
        self._cache: dict[str, dict | None] = {}

    def _resolve_path(self, fixture_id: str) -> Path | None:
        """Resolve a fixture ID to its file path.

        The fixture ID prefix determines the subdirectory:
        - IDs starting with 'tmdb_' → fixtures/tmdb/{fixture_id}.json
        - IDs starting with 'netflix_' → fixtures/netflix/{fixture_id}.json

        Returns None if the prefix is unrecognized.
        """
        for prefix, source_dir in self._PREFIX_TO_SOURCE.items():
            if fixture_id.startswith(f"{prefix}_"):
                return self._fixtures_dir / source_dir / f"{fixture_id}.json"
        return None

    def _load_fixture(self, fixture_id: str) -> dict | None:
        """Load and cache a fixture from disk.

        Returns the parsed JSON content or None if the file doesn't exist
        or the fixture_id prefix is unrecognized.
        """
        if fixture_id in self._cache:
            return self._cache[fixture_id]

        path = self._resolve_path(fixture_id)
        if path is None or not path.is_file():
            self._cache[fixture_id] = None
            return None

        with open(path, encoding="utf-8") as f:
            data = json.load(f)

        self._cache[fixture_id] = data
        return data

    def get_fixture(self, fixture_id: str) -> dict | None:
        """Return the fixture dict content by ID, or None if not found.

        Args:
            fixture_id: The fixture identifier (e.g., 'tmdb_trending_normal').

        Returns:
            Parsed JSON dict of the fixture, or None if the fixture doesn't exist.
        """
        return self._load_fixture(fixture_id)

    def fixture_exists(self, fixture_id: str) -> bool:
        """Check whether a fixture file exists for the given ID.

        Args:
            fixture_id: The fixture identifier.

        Returns:
            True if the fixture file exists on disk.
        """
        path = self._resolve_path(fixture_id)
        if path is None:
            return False
        return path.is_file()

    def get_item_ids(self, fixture_id: str) -> set[str]:
        """Extract all item IDs from a fixture's data.

        For TMDB fixtures, items have an 'id' field in the 'results' array.
        For Netflix fixtures, items have a 'show_id' field in the 'results' array.

        Args:
            fixture_id: The fixture identifier.

        Returns:
            Set of string item IDs found in the fixture. Returns empty set
            if the fixture doesn't exist or has no results.
        """
        data = self._load_fixture(fixture_id)
        if data is None:
            return set()

        results = data.get("results", [])
        if not isinstance(results, list):
            return set()

        # Determine the ID field based on fixture source
        if fixture_id.startswith("tmdb_"):
            id_field = "id"
        elif fixture_id.startswith("netflix_"):
            id_field = "show_id"
        else:
            return set()

        ids: set[str] = set()
        for item in results:
            if isinstance(item, dict) and id_field in item:
                ids.add(str(item[id_field]))

        return ids

    def list_fixtures(self, suite: Suite | None = None) -> list[str]:
        """List all available fixture IDs, optionally filtered by suite.

        Args:
            suite: If provided, only return fixtures for the corresponding source.
                   - Suite.tmdb_agent_silver → tmdb fixtures
                   - Suite.netflix_agent_silver → netflix fixtures
                   - Suite.e2e_routing_silver → returns all fixtures (routing tests
                     may reference any fixture)
                   - None → returns all fixtures

        Returns:
            Sorted list of fixture IDs (without .json extension).
        """
        sources: list[str]

        if suite is None or suite == Suite.e2e_routing_silver:
            sources = ["tmdb", "netflix"]
        elif suite in self._SUITE_TO_SOURCE:
            sources = [self._SUITE_TO_SOURCE[suite]]
        else:
            sources = []

        fixture_ids: list[str] = []
        for source in sources:
            source_dir = self._fixtures_dir / source
            if not source_dir.is_dir():
                continue
            for file_path in source_dir.iterdir():
                if file_path.suffix == ".json" and file_path.is_file():
                    fixture_ids.append(file_path.stem)

        return sorted(fixture_ids)
