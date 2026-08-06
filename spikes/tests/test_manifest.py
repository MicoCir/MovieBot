"""Unit tests for the manifest builder.

Tests scenarios:
1. Three successful spike results → manifest has 3 sources, all confirmed
2. One blocked spike (TMDB) → source entry has blocking_evidence and proposed_alternative
3. serialize_manifest → produces valid JSON that can be parsed back
4. save_manifest → file exists on disk with valid content
5. downstream_consumers map is populated

Validates: Requirements 4.1, 4.3, 4.5
"""

import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from spikes.common.manifest import (
    DOWNSTREAM_CONSUMERS,
    SourceEntry,
    ViabilityManifest,
    build_manifest,
    save_manifest,
    serialize_manifest,
)
from spikes.common.models import ViabilityStatus
from spikes.meilisearch.models import MeilisearchSpikeResult
from spikes.netflix.models import ColumnProfile, DataProfile, NetflixSpikeResult
from spikes.tmdb.models import FieldEntry, TmdbSpikeResult


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def confirmed_tmdb_result() -> TmdbSpikeResult:
    """A confirmed TMDB spike result with successful endpoint access."""
    return TmdbSpikeResult(
        spike_name="tmdb",
        executed_at=datetime(2024, 6, 15, 10, 0, 0, tzinfo=timezone.utc),
        status=ViabilityStatus.CONFIRMED,
        duration_seconds=2.5,
        artifacts_produced=[
            "spikes/artifacts/tmdb_snapshot.json",
            "spikes/artifacts/tmdb_field_inventory.json",
        ],
        errors=[],
        endpoint_used="https://api.themoviedb.org/3/trending/movie/day",
        response_code=200,
        field_count=14,
        snapshot_path="spikes/artifacts/tmdb_snapshot.json",
    )


@pytest.fixture
def blocked_tmdb_result() -> TmdbSpikeResult:
    """A blocked TMDB spike result with authentication errors."""
    return TmdbSpikeResult(
        spike_name="tmdb",
        executed_at=datetime(2024, 6, 15, 10, 0, 0, tzinfo=timezone.utc),
        status=ViabilityStatus.BLOCKED,
        duration_seconds=1.2,
        artifacts_produced=["spikes/artifacts/tmdb_blocked_fixture.json"],
        errors=["HTTP 401: Invalid API key", "Authentication failed"],
        endpoint_used="https://api.themoviedb.org/3/trending/movie/day",
        response_code=401,
        field_count=0,
        snapshot_path=None,
    )


@pytest.fixture
def confirmed_netflix_result() -> NetflixSpikeResult:
    """A confirmed Netflix spike result with dataset profiled."""
    return NetflixSpikeResult(
        spike_name="netflix",
        executed_at=datetime(2024, 6, 15, 10, 5, 0, tzinfo=timezone.utc),
        status=ViabilityStatus.CONFIRMED,
        duration_seconds=8.3,
        artifacts_produced=[
            "spikes/artifacts/netflix_profile.json",
            "spikes/artifacts/netflix_sample.csv",
        ],
        errors=[],
        csv_path="spikes/artifacts/netflix_titles.csv",
        row_count=8807,
        column_count=12,
        fingerprint="a1b2c3d4e5f6789012345678901234567890abcdef1234567890abcdef123456",
        sample_path="spikes/artifacts/netflix_sample.csv",
        license_info="CC0 1.0 Universal - Public Domain Dedication",
    )


@pytest.fixture
def confirmed_meilisearch_result() -> MeilisearchSpikeResult:
    """A confirmed Meilisearch spike result with all capabilities passing."""
    return MeilisearchSpikeResult(
        spike_name="meilisearch",
        executed_at=datetime(2024, 6, 15, 10, 10, 0, tzinfo=timezone.utc),
        status=ViabilityStatus.CONFIRMED,
        duration_seconds=15.7,
        artifacts_produced=["spikes/artifacts/meilisearch_smoke.json"],
        errors=[],
        image_tag="getmeili/meilisearch:v1.6.0",
        container_digest="sha256:abc123def456",
        healthcheck_passed=True,
        capabilities_tested={
            "full_text_search": True,
            "faceted_filters": True,
            "semantic_search": True,
            "hybrid_search": True,
        },
        enterprise_features_detected=[],
    )


@pytest.fixture
def sample_field_inventory() -> list[FieldEntry]:
    """A minimal TMDB field inventory for testing."""
    return [
        FieldEntry(
            name="title",
            observed_type="str",
            example_value="Inception",
            path="results[0].title",
        ),
        FieldEntry(
            name="id",
            observed_type="int",
            example_value=27205,
            path="results[0].id",
        ),
        FieldEntry(
            name="popularity",
            observed_type="float",
            example_value=98.7,
            path="results[0].popularity",
        ),
    ]


@pytest.fixture
def sample_netflix_profile() -> DataProfile:
    """A minimal Netflix data profile for testing."""
    return DataProfile(
        row_count=8807,
        column_count=12,
        columns=[
            ColumnProfile(
                name="show_id",
                inferred_type="string",
                null_percentage=0.0,
                unique_count=8807,
                representative_values=["s1", "s2", "s3", "s4", "s5"],
            ),
            ColumnProfile(
                name="type",
                inferred_type="string",
                null_percentage=0.0,
                unique_count=2,
                representative_values=["Movie", "TV Show"],
            ),
        ],
        duplicate_count=0,
        file_size_bytes=5_500_000,
    )


# ---------------------------------------------------------------------------
# Test: Three successful spike results → complete manifest
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestManifestWithAllConfirmed:
    """Test manifest built from three successful spike results (Req 4.1)."""

    def test_manifest_has_three_sources(
        self,
        confirmed_tmdb_result,
        confirmed_netflix_result,
        confirmed_meilisearch_result,
        sample_field_inventory,
        sample_netflix_profile,
    ):
        """Manifest contains exactly 3 source entries, one per spike."""
        manifest = build_manifest(
            confirmed_tmdb_result,
            confirmed_netflix_result,
            confirmed_meilisearch_result,
            tmdb_field_inventory=sample_field_inventory,
            netflix_column_profile=sample_netflix_profile,
        )

        assert len(manifest.sources) == 3

    def test_all_sources_confirmed(
        self,
        confirmed_tmdb_result,
        confirmed_netflix_result,
        confirmed_meilisearch_result,
    ):
        """All source entries have confirmed viability status."""
        manifest = build_manifest(
            confirmed_tmdb_result,
            confirmed_netflix_result,
            confirmed_meilisearch_result,
        )

        for source in manifest.sources:
            assert source.status == ViabilityStatus.CONFIRMED

    def test_each_source_has_required_fields(
        self,
        confirmed_tmdb_result,
        confirmed_netflix_result,
        confirmed_meilisearch_result,
    ):
        """Each source entry has non-empty name, version, provenance (Req 4.1)."""
        manifest = build_manifest(
            confirmed_tmdb_result,
            confirmed_netflix_result,
            confirmed_meilisearch_result,
        )

        for source in manifest.sources:
            assert source.name, "Source name must be non-empty"
            assert source.version_or_date, "Source version/date must be non-empty"
            assert source.provenance, "Source provenance must be non-empty"

    def test_tmdb_field_inventory_included(
        self,
        confirmed_tmdb_result,
        confirmed_netflix_result,
        confirmed_meilisearch_result,
        sample_field_inventory,
    ):
        """TMDB field inventory is included when provided."""
        manifest = build_manifest(
            confirmed_tmdb_result,
            confirmed_netflix_result,
            confirmed_meilisearch_result,
            tmdb_field_inventory=sample_field_inventory,
        )

        assert len(manifest.tmdb_field_inventory) == 3
        assert manifest.tmdb_field_inventory[0].name == "title"

    def test_netflix_column_profile_included(
        self,
        confirmed_tmdb_result,
        confirmed_netflix_result,
        confirmed_meilisearch_result,
        sample_netflix_profile,
    ):
        """Netflix column profile is included when provided."""
        manifest = build_manifest(
            confirmed_tmdb_result,
            confirmed_netflix_result,
            confirmed_meilisearch_result,
            netflix_column_profile=sample_netflix_profile,
        )

        assert manifest.netflix_column_profile is not None
        assert manifest.netflix_column_profile.row_count == 8807

    def test_meilisearch_capabilities_populated(
        self,
        confirmed_tmdb_result,
        confirmed_netflix_result,
        confirmed_meilisearch_result,
    ):
        """Meilisearch confirmed capabilities are populated from result."""
        manifest = build_manifest(
            confirmed_tmdb_result,
            confirmed_netflix_result,
            confirmed_meilisearch_result,
        )

        assert "full_text_search" in manifest.meilisearch_confirmed_capabilities
        assert "faceted_filters" in manifest.meilisearch_confirmed_capabilities
        assert "semantic_search" in manifest.meilisearch_confirmed_capabilities
        assert "hybrid_search" in manifest.meilisearch_confirmed_capabilities

    def test_meilisearch_version_extracted(
        self,
        confirmed_tmdb_result,
        confirmed_netflix_result,
        confirmed_meilisearch_result,
    ):
        """Meilisearch version is extracted from image tag."""
        manifest = build_manifest(
            confirmed_tmdb_result,
            confirmed_netflix_result,
            confirmed_meilisearch_result,
        )

        assert manifest.meilisearch_version == "v1.6.0"

    def test_downstream_consumers_populated(
        self,
        confirmed_tmdb_result,
        confirmed_netflix_result,
        confirmed_meilisearch_result,
    ):
        """Downstream consumers map is non-empty and references future tasks."""
        manifest = build_manifest(
            confirmed_tmdb_result,
            confirmed_netflix_result,
            confirmed_meilisearch_result,
        )

        assert manifest.downstream_consumers
        assert "viability_manifest.json" in manifest.downstream_consumers
        assert len(manifest.downstream_consumers["viability_manifest.json"]) > 0


# ---------------------------------------------------------------------------
# Test: One blocked spike → manifest includes blocking evidence
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestManifestWithBlockedSpike:
    """Test manifest with one blocked spike has evidence and alternative (Req 4.5)."""

    def test_blocked_source_has_blocking_evidence(
        self,
        blocked_tmdb_result,
        confirmed_netflix_result,
        confirmed_meilisearch_result,
    ):
        """Blocked TMDB source entry includes blocking_evidence."""
        manifest = build_manifest(
            blocked_tmdb_result,
            confirmed_netflix_result,
            confirmed_meilisearch_result,
        )

        tmdb_source = manifest.sources[0]
        assert tmdb_source.status == ViabilityStatus.BLOCKED
        assert tmdb_source.blocking_evidence is not None
        assert "401" in tmdb_source.blocking_evidence

    def test_blocked_source_has_proposed_alternative(
        self,
        blocked_tmdb_result,
        confirmed_netflix_result,
        confirmed_meilisearch_result,
    ):
        """Blocked TMDB source entry includes a proposed alternative."""
        manifest = build_manifest(
            blocked_tmdb_result,
            confirmed_netflix_result,
            confirmed_meilisearch_result,
        )

        tmdb_source = manifest.sources[0]
        assert tmdb_source.proposed_alternative is not None
        assert len(tmdb_source.proposed_alternative) > 0

    def test_blocked_source_documents_limitations(
        self,
        blocked_tmdb_result,
        confirmed_netflix_result,
        confirmed_meilisearch_result,
    ):
        """Blocked source has documented limitations (Req 4.3)."""
        manifest = build_manifest(
            blocked_tmdb_result,
            confirmed_netflix_result,
            confirmed_meilisearch_result,
        )

        tmdb_source = manifest.sources[0]
        assert len(tmdb_source.limitations) > 0

    def test_confirmed_sources_have_no_blocking_evidence(
        self,
        blocked_tmdb_result,
        confirmed_netflix_result,
        confirmed_meilisearch_result,
    ):
        """Confirmed sources have no blocking evidence."""
        manifest = build_manifest(
            blocked_tmdb_result,
            confirmed_netflix_result,
            confirmed_meilisearch_result,
        )

        # Netflix and Meilisearch should be confirmed with no blocking evidence
        netflix_source = manifest.sources[1]
        meili_source = manifest.sources[2]

        assert netflix_source.status == ViabilityStatus.CONFIRMED
        assert netflix_source.blocking_evidence is None
        assert meili_source.status == ViabilityStatus.CONFIRMED
        assert meili_source.blocking_evidence is None


# ---------------------------------------------------------------------------
# Test: JSON serialization produces valid parseable output
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestManifestSerialization:
    """Test JSON serialization is valid and roundtrips correctly."""

    def test_serialize_produces_valid_json(
        self,
        confirmed_tmdb_result,
        confirmed_netflix_result,
        confirmed_meilisearch_result,
        sample_field_inventory,
        sample_netflix_profile,
    ):
        """serialize_manifest produces a string parseable as valid JSON."""
        manifest = build_manifest(
            confirmed_tmdb_result,
            confirmed_netflix_result,
            confirmed_meilisearch_result,
            tmdb_field_inventory=sample_field_inventory,
            netflix_column_profile=sample_netflix_profile,
        )

        json_str = serialize_manifest(manifest)

        # Must be valid JSON
        parsed = json.loads(json_str)
        assert isinstance(parsed, dict)

    def test_serialized_json_contains_sources(
        self,
        confirmed_tmdb_result,
        confirmed_netflix_result,
        confirmed_meilisearch_result,
    ):
        """Serialized JSON contains the sources array with correct count."""
        manifest = build_manifest(
            confirmed_tmdb_result,
            confirmed_netflix_result,
            confirmed_meilisearch_result,
        )

        json_str = serialize_manifest(manifest)
        parsed = json.loads(json_str)

        assert "sources" in parsed
        assert len(parsed["sources"]) == 3

    def test_serialized_json_contains_generated_at(
        self,
        confirmed_tmdb_result,
        confirmed_netflix_result,
        confirmed_meilisearch_result,
    ):
        """Serialized JSON has a generated_at timestamp."""
        manifest = build_manifest(
            confirmed_tmdb_result,
            confirmed_netflix_result,
            confirmed_meilisearch_result,
        )

        json_str = serialize_manifest(manifest)
        parsed = json.loads(json_str)

        assert "generated_at" in parsed
        assert parsed["generated_at"] is not None

    def test_serialized_json_roundtrip_to_manifest(
        self,
        confirmed_tmdb_result,
        confirmed_netflix_result,
        confirmed_meilisearch_result,
        sample_field_inventory,
        sample_netflix_profile,
    ):
        """JSON can be parsed back into a ViabilityManifest."""
        manifest = build_manifest(
            confirmed_tmdb_result,
            confirmed_netflix_result,
            confirmed_meilisearch_result,
            tmdb_field_inventory=sample_field_inventory,
            netflix_column_profile=sample_netflix_profile,
        )

        json_str = serialize_manifest(manifest)
        restored = ViabilityManifest.model_validate_json(json_str)

        assert len(restored.sources) == 3
        assert restored.meilisearch_version == manifest.meilisearch_version
        assert len(restored.tmdb_field_inventory) == len(manifest.tmdb_field_inventory)


# ---------------------------------------------------------------------------
# Test: save_manifest → file exists on disk with valid content
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestManifestPersistence:
    """Test save_manifest writes valid JSON to disk."""

    def test_save_manifest_creates_file(
        self,
        tmp_path,
        confirmed_tmdb_result,
        confirmed_netflix_result,
        confirmed_meilisearch_result,
    ):
        """save_manifest creates a file at the specified path."""
        manifest = build_manifest(
            confirmed_tmdb_result,
            confirmed_netflix_result,
            confirmed_meilisearch_result,
        )

        output_path = tmp_path / "manifest.json"
        result_path = save_manifest(manifest, output_path)

        assert result_path.exists()
        assert result_path == output_path

    def test_saved_file_contains_valid_json(
        self,
        tmp_path,
        confirmed_tmdb_result,
        confirmed_netflix_result,
        confirmed_meilisearch_result,
        sample_field_inventory,
        sample_netflix_profile,
    ):
        """Saved file content is valid JSON that parses back to a manifest."""
        manifest = build_manifest(
            confirmed_tmdb_result,
            confirmed_netflix_result,
            confirmed_meilisearch_result,
            tmdb_field_inventory=sample_field_inventory,
            netflix_column_profile=sample_netflix_profile,
        )

        output_path = tmp_path / "output" / "manifest.json"
        save_manifest(manifest, output_path)

        content = output_path.read_text(encoding="utf-8")
        parsed = json.loads(content)
        assert "sources" in parsed
        assert len(parsed["sources"]) == 3

        # Validate it can be loaded back as a manifest
        restored = ViabilityManifest.model_validate_json(content)
        assert restored.meilisearch_version == "v1.6.0"
