"""Property test for registry and metadata integrity (Property 17).

Verifies that:
1. `_compute_settings_checksum()` is deterministic — same config always produces the same checksum.
2. The settings checksum changes when FILTERABLE_ATTRIBUTES or SEARCHABLE_ATTRIBUTES change.
3. The checksum computation is consistent with the documented algorithm (sorted JSON → SHA-256).

**Validates: Requirements 5.16, 5.17**
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from unittest.mock import patch

from hypothesis import given, settings
from hypothesis import strategies as st

from moviebot.indexer.meilisearch_indexer import IndexerConfig, MeilisearchIndexer

# ---------------------------------------------------------------------------
# Helper: create an indexer instance with a mock meilisearch client
# ---------------------------------------------------------------------------


def _make_indexer() -> MeilisearchIndexer:
    """Create a MeilisearchIndexer with a valid config and mocked client."""
    config = IndexerConfig(
        meilisearch_url="http://localhost:7700",
        meilisearch_api_key="test-key",
        canonical_dataset_version="v1",
        schema_version="1.0.0",
        titles_jsonl_path=Path("/tmp/fake/titles.jsonl"),
        registry_path=Path("/tmp/fake/index_registry.json"),
    )
    with patch("moviebot.indexer.meilisearch_indexer.meilisearch.Client"):
        indexer = MeilisearchIndexer(config)
    return indexer


# ---------------------------------------------------------------------------
# Property 17: Registry and metadata integrity
# ---------------------------------------------------------------------------


@given(n=st.integers(min_value=2, max_value=20))
@settings(max_examples=50, deadline=5000)
def test_property_17_settings_checksum_is_deterministic(n: int) -> None:
    """Property 17: settings_checksum is deterministic.

    **Validates: Requirements 5.16, 5.17**

    Calling `_compute_settings_checksum()` N times on the same indexer
    always returns the same value.
    """
    indexer = _make_indexer()

    checksums = [indexer._compute_settings_checksum() for _ in range(n)]

    # All checksums must be identical
    assert len(set(checksums)) == 1, (
        f"Expected all {n} checksums to be identical, got {len(set(checksums))} distinct values: "
        f"{set(checksums)}"
    )


def test_property_17_settings_checksum_changes_with_filterable_attributes() -> None:
    """Property 17: settings_checksum changes when FILTERABLE_ATTRIBUTES change.

    **Validates: Requirements 5.16, 5.17**

    Modifying the class-level FILTERABLE_ATTRIBUTES produces a different checksum.
    """
    indexer = _make_indexer()

    original_checksum = indexer._compute_settings_checksum()

    # Temporarily modify FILTERABLE_ATTRIBUTES
    original_attrs = MeilisearchIndexer.FILTERABLE_ATTRIBUTES
    try:
        MeilisearchIndexer.FILTERABLE_ATTRIBUTES = original_attrs + ["new_field"]
        modified_checksum = indexer._compute_settings_checksum()
    finally:
        MeilisearchIndexer.FILTERABLE_ATTRIBUTES = original_attrs

    assert original_checksum != modified_checksum, (
        "Expected settings_checksum to change when FILTERABLE_ATTRIBUTES is modified, "
        f"but both produced: {original_checksum}"
    )


def test_property_17_settings_checksum_changes_with_searchable_attributes() -> None:
    """Property 17: settings_checksum changes when SEARCHABLE_ATTRIBUTES change.

    **Validates: Requirements 5.16, 5.17**

    Modifying the class-level SEARCHABLE_ATTRIBUTES produces a different checksum.
    """
    indexer = _make_indexer()

    original_checksum = indexer._compute_settings_checksum()

    # Temporarily modify SEARCHABLE_ATTRIBUTES
    original_attrs = MeilisearchIndexer.SEARCHABLE_ATTRIBUTES
    try:
        MeilisearchIndexer.SEARCHABLE_ATTRIBUTES = ["title", "description"]
        modified_checksum = indexer._compute_settings_checksum()
    finally:
        MeilisearchIndexer.SEARCHABLE_ATTRIBUTES = original_attrs

    assert original_checksum != modified_checksum, (
        "Expected settings_checksum to change when SEARCHABLE_ATTRIBUTES is modified, "
        f"but both produced: {original_checksum}"
    )


def test_property_17_settings_checksum_matches_documented_algorithm() -> None:
    """Property 17: settings_checksum matches the documented algorithm.

    **Validates: Requirements 5.16, 5.17**

    The checksum is computed as:
        SHA-256(json.dumps(settings, sort_keys=True, separators=(",",":"), ensure_ascii=False))
    where settings = {
        "filterableAttributes": sorted(FILTERABLE_ATTRIBUTES),
        "primaryKey": "id",
        "searchableAttributes": SEARCHABLE_ATTRIBUTES,
        "sortableAttributes": SORTABLE_ATTRIBUTES,
    }
    """
    indexer = _make_indexer()

    # Compute expected checksum using the documented algorithm
    settings_dict = {
        "filterableAttributes": sorted(MeilisearchIndexer.FILTERABLE_ATTRIBUTES),
        "primaryKey": "id",
        "searchableAttributes": MeilisearchIndexer.SEARCHABLE_ATTRIBUTES,
        "sortableAttributes": MeilisearchIndexer.SORTABLE_ATTRIBUTES,
    }
    payload = json.dumps(
        settings_dict, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")
    expected_checksum = hashlib.sha256(payload).hexdigest()

    actual_checksum = indexer._compute_settings_checksum()

    assert actual_checksum == expected_checksum, (
        f"settings_checksum does not match documented algorithm:\n"
        f"  Expected: {expected_checksum}\n"
        f"  Actual:   {actual_checksum}"
    )

    # Verify it's a valid SHA-256 hex digest (64 hex chars)
    assert len(actual_checksum) == 64
    assert all(c in "0123456789abcdef" for c in actual_checksum)
