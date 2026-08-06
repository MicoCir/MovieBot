# Feature: source-viability-spikes, Property 9: Artifact Git-Eligibility Classification
"""Property-based tests for artifact Git-eligibility classification.

**Validates: Requirements 5.2, 5.4**

Tests that the classifier correctly marks artifacts as excluded when
size > threshold, license is in excluded set, or filename matches an
excluded pattern, and is deterministic for identical inputs.
"""

import fnmatch
import tempfile
from pathlib import Path

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from spikes.common.artifact_classifier import (
    ALWAYS_ELIGIBLE_TYPES,
    ALWAYS_EXCLUDED_PATTERNS,
    EXCLUDED_LICENSES,
    MAX_GIT_SIZE_BYTES,
    GitEligibility,
    classify_artifact,
)


# --- Strategies ---

sizes = st.integers(min_value=0, max_value=10_000_000)

artifact_types = st.sampled_from(
    list(ALWAYS_ELIGIBLE_TYPES) + ["dataset", "unknown_type", "binary"]
)

license_types = st.one_of(
    st.none(),
    st.sampled_from(list(EXCLUDED_LICENSES) + ["MIT", "CC0", "Apache-2.0"]),
)

# Filenames that match ALWAYS_EXCLUDED_PATTERNS
excluded_filenames = st.sampled_from([
    ".env",
    "production.env",
    "credentials.json",
    "credentials_backup.txt",
    "server.key",
    "private.key",
])

# Filenames that do NOT match any ALWAYS_EXCLUDED_PATTERNS
safe_filenames = st.sampled_from([
    "README.md",
    "manifest.json",
    "data.csv",
    "spike_tmdb.py",
    "profile.json",
    "sample.parquet",
    "config.toml",
])


def _matches_excluded_pattern(filename: str) -> bool:
    """Check if a filename matches any always-excluded pattern."""
    for pattern in ALWAYS_EXCLUDED_PATTERNS:
        if fnmatch.fnmatch(filename, pattern):
            return True
    return False


# --- Property Tests ---


@pytest.mark.property
class TestArtifactClassificationProperty:
    """Property 9: Artifact Git-Eligibility Classification."""

    @given(filename=excluded_filenames, artifact_type=artifact_types, license_type=license_types)
    @settings(max_examples=100)
    def test_excluded_pattern_means_excluded(
        self, filename: str, artifact_type: str, license_type: str | None
    ):
        """If filename matches an excluded pattern, classification is EXCLUDED."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            file_path = Path(tmp_dir) / filename
            file_path.write_bytes(b"x" * 10)

            result = classify_artifact(file_path, artifact_type, license_type)
            assert result.eligibility == GitEligibility.EXCLUDED
            assert "pattern" in result.reason.lower()

    @given(
        filename=safe_filenames,
        artifact_type=artifact_types,
        license_type=st.sampled_from(list(EXCLUDED_LICENSES)),
    )
    @settings(max_examples=100)
    def test_excluded_license_means_excluded(
        self, filename: str, artifact_type: str, license_type: str
    ):
        """If license is in excluded set, classification is EXCLUDED."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            file_path = Path(tmp_dir) / filename
            file_path.write_bytes(b"x" * 10)

            result = classify_artifact(file_path, artifact_type, license_type)
            assert result.eligibility == GitEligibility.EXCLUDED
            assert "license" in result.reason.lower()

    @given(
        filename=safe_filenames,
        artifact_type=artifact_types,
        size=st.integers(min_value=MAX_GIT_SIZE_BYTES + 1, max_value=10_000_000),
    )
    @settings(max_examples=100)
    def test_oversized_file_means_excluded(
        self, filename: str, artifact_type: str, size: int
    ):
        """If file size > MAX_GIT_SIZE_BYTES, classification is EXCLUDED."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            file_path = Path(tmp_dir) / filename
            file_path.write_bytes(b"\x00" * size)

            result = classify_artifact(file_path, artifact_type, license_type=None)
            assert result.eligibility == GitEligibility.EXCLUDED
            assert "size" in result.reason.lower()

    @given(
        filename=safe_filenames,
        artifact_type=st.sampled_from(list(ALWAYS_ELIGIBLE_TYPES)),
        license_type=st.one_of(
            st.none(),
            st.sampled_from(["MIT", "CC0", "Apache-2.0"]),
        ),
        size=st.integers(min_value=0, max_value=MAX_GIT_SIZE_BYTES),
    )
    @settings(max_examples=100)
    def test_eligible_type_no_exclusion_means_eligible(
        self, filename: str, artifact_type: str, license_type: str | None, size: int
    ):
        """If type is in ALWAYS_ELIGIBLE_TYPES and no exclusion applies, classification is ELIGIBLE."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            file_path = Path(tmp_dir) / filename
            file_path.write_bytes(b"\x00" * size)

            result = classify_artifact(file_path, artifact_type, license_type)
            assert result.eligibility == GitEligibility.ELIGIBLE
            assert "eligible" in result.reason.lower()

    @given(
        filename=safe_filenames,
        artifact_type=artifact_types,
        license_type=st.one_of(
            st.none(),
            st.sampled_from(["MIT", "CC0", "Apache-2.0"]),
        ),
        size=st.integers(min_value=0, max_value=MAX_GIT_SIZE_BYTES),
    )
    @settings(max_examples=100)
    def test_deterministic_for_identical_inputs(
        self, filename: str, artifact_type: str, license_type: str | None, size: int
    ):
        """Same inputs always produce the same classification result."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            file_path = Path(tmp_dir) / filename
            file_path.write_bytes(b"\x00" * size)

            result1 = classify_artifact(file_path, artifact_type, license_type)
            result2 = classify_artifact(file_path, artifact_type, license_type)

            assert result1.eligibility == result2.eligibility
            assert result1.reason == result2.reason
            assert result1.size_bytes == result2.size_bytes
