"""Unit tests for the CLI entry point run_spikes.py.

Tests cover:
- Independent spike execution (failure isolation)
- Manifest generation from spike results
- .gitignore update logic
- Fallback result creation for crashed spikes
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

import pytest

from spikes.common.models import ViabilityStatus
from spikes.meilisearch.models import MeilisearchSpikeResult
from spikes.netflix.models import NetflixSpikeResult
from spikes.run_spikes import (
    GITIGNORE_END_MARKER,
    GITIGNORE_START_MARKER,
    _fallback_meilisearch_result,
    _fallback_netflix_result,
    _fallback_tmdb_result,
    _update_gitignore,
)
from spikes.tmdb.models import TmdbSpikeResult


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def confirmed_tmdb_result() -> TmdbSpikeResult:
    """A successful TMDB spike result."""
    return TmdbSpikeResult(
        spike_name="tmdb",
        executed_at=datetime.now(timezone.utc),
        status=ViabilityStatus.CONFIRMED,
        duration_seconds=1.5,
        artifacts_produced=["spikes/artifacts/tmdb_snapshot.json"],
        errors=[],
        endpoint_used="https://api.themoviedb.org/3/trending/movie/day",
        response_code=200,
        field_count=15,
        snapshot_path="spikes/artifacts/tmdb_snapshot.json",
    )


@pytest.fixture
def confirmed_netflix_result() -> NetflixSpikeResult:
    """A successful Netflix spike result."""
    return NetflixSpikeResult(
        spike_name="netflix",
        executed_at=datetime.now(timezone.utc),
        status=ViabilityStatus.CONFIRMED,
        duration_seconds=2.0,
        artifacts_produced=[
            "spikes/artifacts/netflix_profile.json",
            "spikes/artifacts/netflix_sample.csv",
        ],
        errors=[],
        csv_path="spikes/netflix/netflix_titles.csv",
        row_count=8807,
        column_count=12,
        fingerprint="abc123def456",
        sample_path="spikes/artifacts/netflix_sample.csv",
        license_info="CC0 1.0",
    )


@pytest.fixture
def confirmed_meilisearch_result() -> MeilisearchSpikeResult:
    """A successful Meilisearch spike result."""
    return MeilisearchSpikeResult(
        spike_name="meilisearch",
        executed_at=datetime.now(timezone.utc),
        status=ViabilityStatus.CONFIRMED,
        duration_seconds=30.0,
        artifacts_produced=["spikes/artifacts/meilisearch_smoke.json"],
        errors=[],
        image_tag="getmeili/meilisearch:v1.6.2",
        container_digest="sha256:abc123",
        healthcheck_passed=True,
        capabilities_tested={
            "fulltext_typo_tolerance": True,
            "faceted_filters": True,
            "semantic_search": False,
        },
        enterprise_features_detected=[],
    )


# ---------------------------------------------------------------------------
# Tests: Fallback result creation
# ---------------------------------------------------------------------------


class TestFallbackResults:
    """Tests for fallback result builders when spikes crash."""

    def test_fallback_tmdb_result_is_blocked(self):
        result = _fallback_tmdb_result("Import error")
        assert result.status == ViabilityStatus.BLOCKED
        assert "Import error" in result.errors[0]
        assert result.spike_name == "tmdb"

    def test_fallback_netflix_result_is_blocked(self):
        result = _fallback_netflix_result("Connection timeout")
        assert result.status == ViabilityStatus.BLOCKED
        assert "Connection timeout" in result.errors[0]
        assert result.spike_name == "netflix"

    def test_fallback_meilisearch_result_is_blocked(self):
        result = _fallback_meilisearch_result("Docker not found")
        assert result.status == ViabilityStatus.BLOCKED
        assert "Docker not found" in result.errors[0]
        assert result.spike_name == "meilisearch"
        assert result.healthcheck_passed is False
        assert result.capabilities_tested == {}


# ---------------------------------------------------------------------------
# Tests: .gitignore update
# ---------------------------------------------------------------------------


class TestGitignoreUpdate:
    """Tests for the .gitignore update logic."""

    def test_creates_section_in_empty_gitignore(self, tmp_path: Path, monkeypatch):
        gitignore = tmp_path / ".gitignore"
        gitignore.write_text("", encoding="utf-8")
        monkeypatch.setattr("spikes.run_spikes.GITIGNORE_PATH", gitignore)

        _update_gitignore(["spikes/artifacts/big_file.csv"])

        content = gitignore.read_text(encoding="utf-8")
        assert GITIGNORE_START_MARKER in content
        assert GITIGNORE_END_MARKER in content
        assert "spikes/artifacts/big_file.csv" in content

    def test_appends_to_existing_gitignore(self, tmp_path: Path, monkeypatch):
        gitignore = tmp_path / ".gitignore"
        gitignore.write_text("*.pyc\n__pycache__/\n", encoding="utf-8")
        monkeypatch.setattr("spikes.run_spikes.GITIGNORE_PATH", gitignore)

        _update_gitignore(["spikes/netflix/netflix_titles.csv"])

        content = gitignore.read_text(encoding="utf-8")
        assert "*.pyc" in content
        assert "__pycache__/" in content
        assert "spikes/netflix/netflix_titles.csv" in content

    def test_replaces_existing_managed_section(self, tmp_path: Path, monkeypatch):
        gitignore = tmp_path / ".gitignore"
        existing = (
            "*.pyc\n"
            f"{GITIGNORE_START_MARKER}\n"
            "old/artifact.csv\n"
            f"{GITIGNORE_END_MARKER}\n"
            "*.log\n"
        )
        gitignore.write_text(existing, encoding="utf-8")
        monkeypatch.setattr("spikes.run_spikes.GITIGNORE_PATH", gitignore)

        _update_gitignore(["new/artifact.json"])

        content = gitignore.read_text(encoding="utf-8")
        assert "old/artifact.csv" not in content
        assert "new/artifact.json" in content
        assert "*.pyc" in content
        assert "*.log" in content

    def test_no_update_when_empty_list(self, tmp_path: Path, monkeypatch):
        gitignore = tmp_path / ".gitignore"
        gitignore.write_text("*.pyc\n", encoding="utf-8")
        monkeypatch.setattr("spikes.run_spikes.GITIGNORE_PATH", gitignore)

        _update_gitignore([])

        content = gitignore.read_text(encoding="utf-8")
        assert GITIGNORE_START_MARKER not in content

    def test_normalizes_backslashes(self, tmp_path: Path, monkeypatch):
        gitignore = tmp_path / ".gitignore"
        gitignore.write_text("", encoding="utf-8")
        monkeypatch.setattr("spikes.run_spikes.GITIGNORE_PATH", gitignore)

        _update_gitignore(["spikes\\artifacts\\big_file.csv"])

        content = gitignore.read_text(encoding="utf-8")
        assert "spikes/artifacts/big_file.csv" in content
        assert "\\" not in content


# ---------------------------------------------------------------------------
# Tests: Spike independence (failure isolation)
# ---------------------------------------------------------------------------


class TestSpikeIsolation:
    """Tests that spike failures don't cascade."""

    def test_tmdb_crash_returns_none(self):
        """If TMDB spike raises, _run_tmdb_spike returns None."""
        with patch(
            "spikes.tmdb.spike_tmdb.run_spike",
            side_effect=RuntimeError("TMDB crashed"),
        ):
            from spikes.run_spikes import _run_tmdb_spike

            result = _run_tmdb_spike()
            assert result is None

    def test_netflix_crash_returns_none(self):
        """If Netflix spike raises, _run_netflix_spike returns None."""
        with patch(
            "spikes.netflix.spike_netflix.run_netflix_spike",
            side_effect=RuntimeError("Netflix crashed"),
        ):
            from spikes.run_spikes import _run_netflix_spike

            result = _run_netflix_spike()
            assert result is None

    def test_meilisearch_crash_returns_none(self):
        """If Meilisearch spike raises, _run_meilisearch_spike returns None."""
        with patch(
            "spikes.meilisearch.spike_meilisearch.run_meilisearch_spike",
            side_effect=RuntimeError("Docker not found"),
        ):
            from spikes.run_spikes import _run_meilisearch_spike

            result = _run_meilisearch_spike()
            assert result is None


# ---------------------------------------------------------------------------
# Tests: End-to-end manifest production
# ---------------------------------------------------------------------------


class TestManifestProduction:
    """Tests that the CLI produces a valid manifest from spike results."""

    def test_manifest_produced_with_all_confirmed(
        self,
        tmp_path: Path,
        confirmed_tmdb_result: TmdbSpikeResult,
        confirmed_netflix_result: NetflixSpikeResult,
        confirmed_meilisearch_result: MeilisearchSpikeResult,
        monkeypatch,
    ):
        """With all spikes confirmed, a valid manifest is saved."""
        from spikes.common.manifest import build_manifest, save_manifest

        manifest = build_manifest(
            tmdb_result=confirmed_tmdb_result,
            netflix_result=confirmed_netflix_result,
            meilisearch_result=confirmed_meilisearch_result,
            tmdb_field_inventory=[],
            netflix_column_profile=None,
        )

        output_path = tmp_path / "viability_manifest.json"
        save_manifest(manifest, output_path=output_path)

        assert output_path.exists()
        data = json.loads(output_path.read_text(encoding="utf-8"))
        assert "sources" in data
        assert len(data["sources"]) == 3
        assert "generated_at" in data

    def test_manifest_produced_with_blocked_spike(
        self,
        tmp_path: Path,
        confirmed_tmdb_result: TmdbSpikeResult,
        confirmed_meilisearch_result: MeilisearchSpikeResult,
    ):
        """With one blocked spike, manifest still includes all three sources."""
        from spikes.common.manifest import build_manifest, save_manifest

        blocked_netflix = _fallback_netflix_result("CSV not found")

        manifest = build_manifest(
            tmdb_result=confirmed_tmdb_result,
            netflix_result=blocked_netflix,
            meilisearch_result=confirmed_meilisearch_result,
            tmdb_field_inventory=[],
            netflix_column_profile=None,
        )

        output_path = tmp_path / "viability_manifest.json"
        save_manifest(manifest, output_path=output_path)

        assert output_path.exists()
        data = json.loads(output_path.read_text(encoding="utf-8"))
        assert len(data["sources"]) == 3

        # Find the Netflix source entry
        netflix_entry = next(s for s in data["sources"] if "Netflix" in s["name"])
        assert netflix_entry["status"] == "blocked"
        assert netflix_entry["blocking_evidence"] is not None
