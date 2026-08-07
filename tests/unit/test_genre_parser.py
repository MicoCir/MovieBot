# tests/unit/test_genre_parser.py
"""Unit tests for NetflixInspector._parse_genres().

Validates: Requirements 6.1, 6.2, 4.11
"""

from pathlib import Path

import pytest

from moviebot.tools.inspect_netflix.inspector import NetflixInspector


@pytest.fixture
def inspector() -> NetflixInspector:
    """Create inspector with dummy paths (only used in run(), not __init__)."""
    return NetflixInspector(
        titles_path=Path("/fake/titles.csv"),
        credits_path=Path("/fake/credits.csv"),
    )


class TestParseGenresValidLists:
    """Tests for valid list literal inputs."""

    def test_valid_list_with_multiple_genres(self, inspector: NetflixInspector) -> None:
        """Valid Python list literal with string elements returns list of strings."""
        result = inspector._parse_genres("['drama', 'crime']")
        assert result == ["drama", "crime"]

    def test_valid_list_single_genre(self, inspector: NetflixInspector) -> None:
        """Single-element list parses correctly."""
        result = inspector._parse_genres("['action']")
        assert result == ["action"]


class TestParseGenresEmptyValues:
    """Tests for null/empty/NaN inputs that return empty list."""

    def test_empty_list_literal(self, inspector: NetflixInspector) -> None:
        """The literal string '[]' returns an empty list."""
        result = inspector._parse_genres("[]")
        assert result == []

    def test_none_returns_empty_list(self, inspector: NetflixInspector) -> None:
        """None input returns an empty list."""
        result = inspector._parse_genres(None)
        assert result == []

    def test_empty_string_returns_empty_list(self, inspector: NetflixInspector) -> None:
        """Empty string returns an empty list."""
        result = inspector._parse_genres("")
        assert result == []

    def test_nan_string_returns_empty_list(self, inspector: NetflixInspector) -> None:
        """The string 'nan' (case-insensitive) returns an empty list."""
        result = inspector._parse_genres("nan")
        assert result == []

    def test_nan_uppercase_returns_empty_list(
        self, inspector: NetflixInspector
    ) -> None:
        """The string 'NaN' returns an empty list."""
        result = inspector._parse_genres("NaN")
        assert result == []


class TestParseGenresMalformed:
    """Tests for malformed inputs that return None."""

    def test_comma_separated_without_brackets(
        self, inspector: NetflixInspector
    ) -> None:
        """A plain comma-separated string (not a list literal) returns None."""
        result = inspector._parse_genres("drama, crime")
        assert result is None

    def test_non_string_elements_returns_none(
        self, inspector: NetflixInspector
    ) -> None:
        """A list literal with non-string elements returns None."""
        result = inspector._parse_genres("['a', 1, 'b']")
        assert result is None

    def test_integer_list_returns_none(self, inspector: NetflixInspector) -> None:
        """A list of integers returns None (elements must all be strings)."""
        result = inspector._parse_genres("[1, 2, 3]")
        assert result is None
