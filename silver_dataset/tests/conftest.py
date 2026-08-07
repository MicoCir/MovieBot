"""Shared pytest configuration and fixtures for silver_dataset tests."""

import pathlib
import tempfile

import pytest
from hypothesis import settings, HealthCheck

# ---------------------------------------------------------------------------
# Hypothesis settings profiles
# ---------------------------------------------------------------------------
# Default profile: 100 examples minimum as required by the design document.
# CI profile can be registered separately if longer runs are needed.
settings.register_profile(
    "silver",
    max_examples=100,
    suppress_health_check=[HealthCheck.too_slow],
)
settings.register_profile(
    "ci",
    max_examples=300,
    suppress_health_check=[HealthCheck.too_slow],
)
# Load the "silver" profile by default for this module's tests.
settings.load_profile("silver")

# ---------------------------------------------------------------------------
# Custom Hypothesis strategies
# ---------------------------------------------------------------------------
# Strategies for generating model instances (SilverCase, LatentSpecification,
# etc.) are defined in silver_dataset/tests/strategies.py and imported here
# once the models are implemented.
# from silver_dataset.tests.strategies import ...  # noqa: E402 — uncomment later

# ---------------------------------------------------------------------------
# Markers
# ---------------------------------------------------------------------------


def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    """Auto-apply the 'silver' marker to all tests collected from this directory."""
    this_dir = pathlib.Path(__file__).parent
    for item in items:
        if pathlib.Path(item.fspath).is_relative_to(this_dir):
            item.add_marker(pytest.mark.silver)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def tmp_jsonl_dir(tmp_path: pathlib.Path) -> pathlib.Path:
    """Provide a temporary directory for test JSONL file operations.

    Tests that need to write/read JSONL files should use this fixture to get an
    isolated temp directory that is automatically cleaned up after the test.
    """
    jsonl_dir = tmp_path / "jsonl_output"
    jsonl_dir.mkdir()
    return jsonl_dir


@pytest.fixture
def fixtures_dir() -> pathlib.Path:
    """Return the path to the silver_dataset/fixtures/ directory.

    This provides access to deterministic fixture data (TMDB and Netflix
    fixture JSON files) used during testing.
    """
    return pathlib.Path(__file__).resolve().parent.parent / "fixtures"
