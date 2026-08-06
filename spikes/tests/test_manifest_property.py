# Feature: source-viability-spikes, Property 8: Manifest Builder Completeness
"""Property-based tests for manifest builder completeness.

Validates: Requirements 4.1

For any set of three spike results (one per source), the manifest builder SHALL
produce a manifest where every source entry contains a non-empty name, version,
provenance, and a valid viability status. No source SHALL be missing from the
output manifest.
"""

import pytest
from datetime import datetime, timezone
from hypothesis import given, settings
from hypothesis import strategies as st

from spikes.common.manifest import build_manifest
from spikes.common.models import ViabilityStatus
from spikes.tmdb.models import TmdbSpikeResult
from spikes.netflix.models import NetflixSpikeResult
from spikes.meilisearch.models import MeilisearchSpikeResult


# ---------------------------------------------------------------------------
# Hypothesis Strategies
# ---------------------------------------------------------------------------

_viability_status = st.sampled_from([ViabilityStatus.CONFIRMED, ViabilityStatus.BLOCKED])

_non_empty_text = st.text(
    alphabet=st.characters(whitelist_categories=("L", "N", "P"), whitelist_characters=" _-/:."),
    min_size=1,
    max_size=50,
)

_artifact_paths = st.lists(
    st.text(
        alphabet=st.characters(whitelist_categories=("L", "N"), whitelist_characters="_-./"),
        min_size=3,
        max_size=30,
    ),
    max_size=5,
)

_errors_list = st.lists(st.text(min_size=1, max_size=100), max_size=3)

_datetime_strategy = st.builds(
    lambda ts: datetime.fromtimestamp(ts, tz=timezone.utc),
    st.floats(min_value=1_000_000_000, max_value=2_000_000_000, allow_nan=False, allow_infinity=False),
)

_duration = st.floats(min_value=0.01, max_value=300.0, allow_nan=False, allow_infinity=False)

# Strategy for TmdbSpikeResult
_tmdb_result_strategy = st.builds(
    TmdbSpikeResult,
    spike_name=st.just("tmdb"),
    executed_at=_datetime_strategy,
    status=_viability_status,
    duration_seconds=_duration,
    artifacts_produced=_artifact_paths,
    errors=_errors_list,
    endpoint_used=st.just("https://api.themoviedb.org/3/trending/movie/day"),
    response_code=st.one_of(st.none(), st.sampled_from([200, 401, 403, 429, 500])),
    field_count=st.integers(min_value=0, max_value=100),
    snapshot_path=st.one_of(st.none(), st.just("spikes/artifacts/tmdb_snapshot.json")),
)

# Strategy for NetflixSpikeResult
_netflix_result_strategy = st.builds(
    NetflixSpikeResult,
    spike_name=st.just("netflix"),
    executed_at=_datetime_strategy,
    status=_viability_status,
    duration_seconds=_duration,
    artifacts_produced=_artifact_paths,
    errors=_errors_list,
    csv_path=st.one_of(st.none(), st.just("spikes/artifacts/netflix_titles.csv")),
    row_count=st.one_of(st.none(), st.integers(min_value=0, max_value=10000)),
    column_count=st.one_of(st.none(), st.integers(min_value=0, max_value=50)),
    fingerprint=st.one_of(
        st.none(),
        st.text(alphabet="0123456789abcdef", min_size=64, max_size=64),
    ),
    sample_path=st.one_of(st.none(), st.just("spikes/artifacts/netflix_sample.csv")),
    license_info=st.text(min_size=0, max_size=100),
)

# Strategy for MeilisearchSpikeResult
_capabilities_strategy = st.dictionaries(
    keys=st.sampled_from(["full_text", "faceted_filters", "semantic_search", "hybrid_search"]),
    values=st.booleans(),
    min_size=1,
    max_size=4,
)

_enterprise_features_strategy = st.lists(
    st.sampled_from(["useNetwork", "network", "remotes", "sharding", "replication", "personalization", "analytics"]),
    max_size=3,
    unique=True,
)

_meilisearch_result_strategy = st.builds(
    MeilisearchSpikeResult,
    spike_name=st.just("meilisearch"),
    executed_at=_datetime_strategy,
    status=_viability_status,
    duration_seconds=_duration,
    artifacts_produced=_artifact_paths,
    errors=_errors_list,
    image_tag=st.sampled_from([
        "getmeili/meilisearch:v1.6.0",
        "getmeili/meilisearch:v1.7.0",
        "getmeili/meilisearch:v1.8.0",
    ]),
    container_digest=st.one_of(
        st.none(),
        st.text(alphabet="0123456789abcdef", min_size=64, max_size=64),
    ),
    healthcheck_passed=st.booleans(),
    capabilities_tested=_capabilities_strategy,
    enterprise_features_detected=_enterprise_features_strategy,
)


# ---------------------------------------------------------------------------
# Property Tests
# ---------------------------------------------------------------------------


@pytest.mark.property
@settings(max_examples=100)
@given(
    tmdb_result=_tmdb_result_strategy,
    netflix_result=_netflix_result_strategy,
    meilisearch_result=_meilisearch_result_strategy,
)
def test_manifest_has_three_source_entries(
    tmdb_result: TmdbSpikeResult,
    netflix_result: NetflixSpikeResult,
    meilisearch_result: MeilisearchSpikeResult,
) -> None:
    """Manifest always contains exactly 3 source entries (one per source)."""
    manifest = build_manifest(tmdb_result, netflix_result, meilisearch_result)
    assert len(manifest.sources) == 3, (
        f"Expected 3 sources, got {len(manifest.sources)}"
    )


@pytest.mark.property
@settings(max_examples=100)
@given(
    tmdb_result=_tmdb_result_strategy,
    netflix_result=_netflix_result_strategy,
    meilisearch_result=_meilisearch_result_strategy,
)
def test_manifest_source_entries_have_non_empty_name(
    tmdb_result: TmdbSpikeResult,
    netflix_result: NetflixSpikeResult,
    meilisearch_result: MeilisearchSpikeResult,
) -> None:
    """Every source entry in the manifest has a non-empty name."""
    manifest = build_manifest(tmdb_result, netflix_result, meilisearch_result)
    for source in manifest.sources:
        assert source.name, f"Source entry has empty name: {source}"
        assert len(source.name.strip()) > 0, f"Source entry has whitespace-only name: {source}"


@pytest.mark.property
@settings(max_examples=100)
@given(
    tmdb_result=_tmdb_result_strategy,
    netflix_result=_netflix_result_strategy,
    meilisearch_result=_meilisearch_result_strategy,
)
def test_manifest_source_entries_have_non_empty_version(
    tmdb_result: TmdbSpikeResult,
    netflix_result: NetflixSpikeResult,
    meilisearch_result: MeilisearchSpikeResult,
) -> None:
    """Every source entry has a non-empty version_or_date."""
    manifest = build_manifest(tmdb_result, netflix_result, meilisearch_result)
    for source in manifest.sources:
        assert source.version_or_date, f"Source '{source.name}' has empty version_or_date"
        assert len(source.version_or_date.strip()) > 0, (
            f"Source '{source.name}' has whitespace-only version_or_date"
        )


@pytest.mark.property
@settings(max_examples=100)
@given(
    tmdb_result=_tmdb_result_strategy,
    netflix_result=_netflix_result_strategy,
    meilisearch_result=_meilisearch_result_strategy,
)
def test_manifest_source_entries_have_non_empty_provenance(
    tmdb_result: TmdbSpikeResult,
    netflix_result: NetflixSpikeResult,
    meilisearch_result: MeilisearchSpikeResult,
) -> None:
    """Every source entry has a non-empty provenance."""
    manifest = build_manifest(tmdb_result, netflix_result, meilisearch_result)
    for source in manifest.sources:
        assert source.provenance, f"Source '{source.name}' has empty provenance"
        assert len(source.provenance.strip()) > 0, (
            f"Source '{source.name}' has whitespace-only provenance"
        )


@pytest.mark.property
@settings(max_examples=100)
@given(
    tmdb_result=_tmdb_result_strategy,
    netflix_result=_netflix_result_strategy,
    meilisearch_result=_meilisearch_result_strategy,
)
def test_manifest_source_entries_have_valid_viability_status(
    tmdb_result: TmdbSpikeResult,
    netflix_result: NetflixSpikeResult,
    meilisearch_result: MeilisearchSpikeResult,
) -> None:
    """Every source entry has a valid ViabilityStatus (CONFIRMED or BLOCKED)."""
    manifest = build_manifest(tmdb_result, netflix_result, meilisearch_result)
    valid_statuses = {ViabilityStatus.CONFIRMED, ViabilityStatus.BLOCKED}
    for source in manifest.sources:
        assert source.status in valid_statuses, (
            f"Source '{source.name}' has invalid status: {source.status}"
        )


@pytest.mark.property
@settings(max_examples=100)
@given(
    tmdb_result=_tmdb_result_strategy,
    netflix_result=_netflix_result_strategy,
    meilisearch_result=_meilisearch_result_strategy,
)
def test_manifest_no_source_missing(
    tmdb_result: TmdbSpikeResult,
    netflix_result: NetflixSpikeResult,
    meilisearch_result: MeilisearchSpikeResult,
) -> None:
    """All three sources (TMDB, Netflix, Meilisearch) are present in the manifest."""
    manifest = build_manifest(tmdb_result, netflix_result, meilisearch_result)
    source_names = [s.name for s in manifest.sources]

    # Check that each expected source is represented
    assert any("TMDB" in name for name in source_names), (
        f"TMDB source missing from manifest. Source names: {source_names}"
    )
    assert any("Netflix" in name for name in source_names), (
        f"Netflix source missing from manifest. Source names: {source_names}"
    )
    assert any("Meilisearch" in name for name in source_names), (
        f"Meilisearch source missing from manifest. Source names: {source_names}"
    )
