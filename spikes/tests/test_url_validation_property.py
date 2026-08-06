# Feature: source-viability-spikes, Property 1: URL Validation Rejects All Non-Authorized Endpoints
"""Property-based tests for TMDB URL validation.

**Validates: Requirements 1.1, 1.6**

For any URL string, the TMDB URL validator SHALL accept it if and only if it
exactly matches the pattern `https://api.themoviedb.org/3/trending/movie/(day|week)`.
All other URL strings SHALL be rejected.
"""

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from spikes.tmdb.validators import build_tmdb_url, validate_tmdb_url


@pytest.mark.property
class TestUrlValidationProperty:
    """Property 1: URL Validation Rejects All Non-Authorized Endpoints."""

    @given(url=st.text())
    @settings(max_examples=100)
    def test_random_strings_are_rejected(self, url: str) -> None:
        """Arbitrary random strings are never accepted as valid TMDB URLs."""
        # The only valid URLs are exactly:
        #   https://api.themoviedb.org/3/trending/movie/day
        #   https://api.themoviedb.org/3/trending/movie/week
        # The probability of st.text() generating one of these is negligible.
        if url not in (
            "https://api.themoviedb.org/3/trending/movie/day",
            "https://api.themoviedb.org/3/trending/movie/week",
        ):
            assert validate_tmdb_url(url) is False

    @given(time_window=st.sampled_from(["day", "week"]))
    @settings(max_examples=100)
    def test_valid_urls_are_accepted(self, time_window: str) -> None:
        """URLs built from authorized time windows are always accepted."""
        url = build_tmdb_url(time_window)
        assert validate_tmdb_url(url) is True

    @given(time_window=st.sampled_from(["day", "week"]))
    @settings(max_examples=100)
    def test_build_produces_correct_format(self, time_window: str) -> None:
        """build_tmdb_url always produces exactly the authorized pattern."""
        url = build_tmdb_url(time_window)
        expected = f"https://api.themoviedb.org/3/trending/movie/{time_window}"
        assert url == expected

    @given(
        time_window=st.sampled_from(["day", "week"]),
        suffix=st.text(min_size=1),
    )
    @settings(max_examples=100)
    def test_valid_url_with_suffix_is_rejected(
        self, time_window: str, suffix: str
    ) -> None:
        """A valid URL with any trailing characters appended is rejected."""
        base = f"https://api.themoviedb.org/3/trending/movie/{time_window}"
        tampered = base + suffix
        # tampered is always different from base since suffix has min_size=1
        assert validate_tmdb_url(tampered) is False

    @given(
        time_window=st.sampled_from(["day", "week"]),
        prefix=st.text(min_size=1),
    )
    @settings(max_examples=100)
    def test_valid_url_with_prefix_is_rejected(
        self, time_window: str, prefix: str
    ) -> None:
        """A valid URL with any leading characters prepended is rejected."""
        base = f"https://api.themoviedb.org/3/trending/movie/{time_window}"
        tampered = prefix + base
        assert validate_tmdb_url(tampered) is False
