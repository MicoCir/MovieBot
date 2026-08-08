# tests/unit/test_meilisearch_indexer.py
"""Unit tests for MeilisearchIndexer.

Tests settings configuration, idempotency behavior, error handling,
atomic registry activation, document count validation, partial index
cleanup on failure, and uncontrolled index detection.

Validates: Requirements 5.4, 5.5, 5.6, 5.7, 5.14, 5.15, 5.16, 5.17, 10.3
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from moviebot.indexer.meilisearch_indexer import (
    IndexerConfig,
    IndexResult,
    MeilisearchIndexer,
    MeilisearchIndexError,
)

# ─── Helpers ────────────────────────────────────────────────────────────────


def _make_config(tmp_path: Path, version: str = "v1") -> IndexerConfig:
    """Create a valid IndexerConfig pointing at tmp_path fixtures."""
    return IndexerConfig(
        meilisearch_url="http://localhost:7700",
        meilisearch_api_key="test-key",
        canonical_dataset_version=version,
        schema_version="1.0.0",
        titles_jsonl_path=tmp_path / "titles.jsonl",
        registry_path=tmp_path / "index_registry.json",
        batch_size=2,
        task_timeout_seconds=5,
    )


def _write_fixtures(tmp_path: Path, docs: list[dict[str, Any]] | None = None) -> str:
    """Write titles.jsonl and metadata.json fixtures. Returns dataset checksum.

    Writes as binary to ensure checksum consistency across platforms.
    """
    if docs is None:
        docs = [
            {
                "id": "tm001",
                "title": "Movie One",
                "type": "movie",
                "release_year": 2020,
                "genres": ["drama"],
                "actors": ["actor a"],
                "directors": ["director x"],
            },
            {
                "id": "tm002",
                "title": "Movie Two",
                "type": "show",
                "release_year": 2021,
                "genres": ["comedy"],
                "actors": ["actor b"],
                "directors": ["director y"],
            },
            {
                "id": "tm003",
                "title": "Movie Three",
                "type": "movie",
                "release_year": 2019,
                "genres": ["action"],
                "actors": [],
                "directors": [],
            },
        ]

    # Build JSONL as bytes directly to avoid platform line-ending issues
    lines = [
        json.dumps(d, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
        for d in docs
    ]
    jsonl_bytes = ("\n".join(lines) + "\n").encode("utf-8")

    jsonl_path = tmp_path / "titles.jsonl"
    jsonl_path.write_bytes(jsonl_bytes)

    # Compute checksum from actual file bytes (same as indexer does)
    checksum = hashlib.sha256(jsonl_bytes).hexdigest()

    # Write metadata.json
    metadata = {
        "canonical_dataset_version": "v1",
        "etl_version": "1.0.0",
        "schema_version": "1.0.0",
        "document_count": len(docs),
        "discarded_count": 0,
        "source_checksums": {"titles.csv": "a" * 64, "credits.csv": "b" * 64},
        "output_checksum_sha256": checksum,
        "generated_at": "2024-01-15T10:30:00Z",
        "type_distribution": {"movie": 2, "show": 1},
    }
    meta_path = tmp_path / "metadata.json"
    meta_path.write_text(json.dumps(metadata), encoding="utf-8")

    return checksum


def _make_api_error(code: str = "index_not_found") -> Any:
    """Create a MeilisearchApiError with proper mocked Response.

    The meilisearch SDK's MeilisearchApiError expects a Response-like object
    with .status_code (int) and .text (str with JSON content).
    """
    import meilisearch.errors

    mock_response = MagicMock()
    mock_response.status_code = 404
    mock_response.text = json.dumps(
        {
            "message": f"{code}",
            "code": code,
            "type": "invalid_request",
            "link": "",
        }
    )
    return meilisearch.errors.MeilisearchApiError(code, mock_response)


def _make_task_info(task_uid: int = 1) -> MagicMock:
    """Create a mock TaskInfo object returned by meilisearch SDK."""
    info = MagicMock()
    info.task_uid = task_uid
    return info


def _make_mock_client(
    *,
    get_index_raises: Exception | None = None,
    get_index_returns: Any = None,
    create_index_task_uid: int = 1,
    get_task_status: str = "succeeded",
    stats_count: int = 3,
) -> MagicMock:
    """Create a comprehensive mock meilisearch.Client."""
    client = MagicMock()

    # get_index
    if get_index_raises:
        client.get_index.side_effect = get_index_raises
    elif get_index_returns is not None:
        client.get_index.return_value = get_index_returns
    else:
        client.get_index.return_value = MagicMock()

    # create_index
    client.create_index.return_value = _make_task_info(create_index_task_uid)

    # get_task
    task_mock = MagicMock()
    task_mock.status = get_task_status
    if get_task_status == "failed":
        task_mock.error = {"message": "Task failed"}
    client.get_task.return_value = task_mock

    # index() → mock index object
    mock_index = MagicMock()
    mock_index.update_searchable_attributes.return_value = _make_task_info(2)
    mock_index.update_filterable_attributes.return_value = _make_task_info(3)
    mock_index.add_documents.return_value = _make_task_info(4)
    stats_mock = MagicMock()
    stats_mock.number_of_documents = stats_count
    mock_index.get_stats.return_value = stats_mock
    client.index.return_value = mock_index

    # delete_index
    client.delete_index.return_value = _make_task_info(99)

    return client


# ─── Tests: Settings Configuration ──────────────────────────────────────────


class TestSettingsConfiguration:
    """Verify that the indexer uses correct searchable/filterable attributes."""

    def test_searchable_attributes_include_required_fields(self) -> None:
        """Searchable attributes include title, description, genres, actors, directors."""
        expected = ["title", "description", "genres", "actors", "directors"]
        assert MeilisearchIndexer.SEARCHABLE_ATTRIBUTES == expected

    def test_filterable_attributes_include_required_fields(self) -> None:
        """Filterable attributes include type, genres, release_year, etc."""
        expected = [
            "type",
            "genres",
            "release_year",
            "age_certification",
            "imdb_score",
            "tmdb_score",
            "actors",
            "directors",
        ]
        assert MeilisearchIndexer.FILTERABLE_ATTRIBUTES == expected

    def test_sortable_attributes_empty_in_v1(self) -> None:
        """Sortable attributes are empty for v1."""
        assert MeilisearchIndexer.SORTABLE_ATTRIBUTES == []

    def test_index_name_includes_version(self, tmp_path: Path) -> None:
        """Index name is netflix_{canonical_dataset_version}."""
        config = _make_config(tmp_path, version="v2")
        with patch("moviebot.indexer.meilisearch_indexer.meilisearch.Client"):
            indexer = MeilisearchIndexer(config)
        assert indexer.index_name == "netflix_v2"


# ─── Tests: Happy Path Ingestion ────────────────────────────────────────────


class TestHappyPathIngestion:
    """Test successful end-to-end ingestion flow."""

    @pytest.mark.asyncio
    async def test_full_ingestion_succeeds(self, tmp_path: Path) -> None:
        """Full ingestion creates index, configures, ingests, validates, activates."""
        checksum = _write_fixtures(tmp_path)
        config = _make_config(tmp_path)

        api_error = _make_api_error("index_not_found")
        mock_client = _make_mock_client(get_index_raises=api_error, stats_count=3)

        with patch(
            "moviebot.indexer.meilisearch_indexer.meilisearch.Client",
            return_value=mock_client,
        ):
            indexer = MeilisearchIndexer(config)
            indexer._client = mock_client
            result = await indexer.ingest()

        assert isinstance(result, IndexResult)
        assert result.index_name == "netflix_v1"
        assert result.document_count == 3
        assert result.dataset_checksum == checksum
        assert result.activated is True
        mock_client.create_index.assert_called_once_with(
            "netflix_v1", {"primaryKey": "id"}
        )

    @pytest.mark.asyncio
    async def test_registry_written_after_successful_ingestion(
        self, tmp_path: Path
    ) -> None:
        """After successful ingestion, the registry file is created with correct content."""
        checksum = _write_fixtures(tmp_path)
        config = _make_config(tmp_path)

        api_error = _make_api_error("index_not_found")
        mock_client = _make_mock_client(get_index_raises=api_error, stats_count=3)

        with patch(
            "moviebot.indexer.meilisearch_indexer.meilisearch.Client",
            return_value=mock_client,
        ):
            indexer = MeilisearchIndexer(config)
            indexer._client = mock_client
            await indexer.ingest()

        registry_path = tmp_path / "index_registry.json"
        assert registry_path.exists()
        registry = json.loads(registry_path.read_text(encoding="utf-8"))
        assert registry["active_index"] == "netflix_v1"
        assert "netflix_v1" in registry["indexes"]
        entry = registry["indexes"]["netflix_v1"]
        assert entry["dataset_checksum"] == checksum
        assert entry["document_count"] == 3
        assert entry["status"] == "active"
        assert entry["canonical_dataset_version"] == "v1"
        assert entry["schema_version"] == "1.0.0"


# ─── Tests: Idempotency Behavior ────────────────────────────────────────────


class TestIdempotencyBehavior:
    """Test idempotency: matching checksums skip recreation, different checksums fail."""

    @pytest.mark.asyncio
    async def test_matching_checksums_skip_recreation(self, tmp_path: Path) -> None:
        """When registry has index with matching checksums, return success without recreation."""
        checksum = _write_fixtures(tmp_path)
        config = _make_config(tmp_path)

        # Compute the settings checksum the same way the indexer does
        settings = {
            "filterableAttributes": sorted(MeilisearchIndexer.FILTERABLE_ATTRIBUTES),
            "primaryKey": "id",
            "searchableAttributes": MeilisearchIndexer.SEARCHABLE_ATTRIBUTES,
            "sortableAttributes": MeilisearchIndexer.SORTABLE_ATTRIBUTES,
        }
        settings_payload = json.dumps(
            settings, sort_keys=True, separators=(",", ":"), ensure_ascii=False
        ).encode("utf-8")
        settings_checksum = hashlib.sha256(settings_payload).hexdigest()

        # Write registry with matching checksums
        registry = {
            "active_index": "netflix_v1",
            "indexes": {
                "netflix_v1": {
                    "canonical_dataset_version": "v1",
                    "schema_version": "1.0.0",
                    "dataset_checksum": checksum,
                    "settings_checksum": settings_checksum,
                    "document_count": 3,
                    "created_at": "2024-01-15T10:30:00Z",
                    "status": "active",
                }
            },
        }
        (tmp_path / "index_registry.json").write_text(
            json.dumps(registry), encoding="utf-8"
        )

        mock_client = _make_mock_client()

        with patch(
            "moviebot.indexer.meilisearch_indexer.meilisearch.Client",
            return_value=mock_client,
        ):
            indexer = MeilisearchIndexer(config)
            indexer._client = mock_client
            result = await indexer.ingest()

        assert result.index_name == "netflix_v1"
        assert result.document_count == 3
        assert result.activated is True
        # create_index should NOT be called (idempotency)
        mock_client.create_index.assert_not_called()

    @pytest.mark.asyncio
    async def test_different_checksums_raise_error(self, tmp_path: Path) -> None:
        """When registry has index with different checksums, raise MeilisearchIndexError."""
        _write_fixtures(tmp_path)
        config = _make_config(tmp_path)

        # Write registry with DIFFERENT checksums
        registry = {
            "active_index": "netflix_v1",
            "indexes": {
                "netflix_v1": {
                    "canonical_dataset_version": "v1",
                    "schema_version": "1.0.0",
                    "dataset_checksum": "f" * 64,
                    "settings_checksum": "e" * 64,
                    "document_count": 3,
                    "created_at": "2024-01-15T10:30:00Z",
                    "status": "active",
                }
            },
        }
        (tmp_path / "index_registry.json").write_text(
            json.dumps(registry), encoding="utf-8"
        )

        mock_client = _make_mock_client()

        with patch(
            "moviebot.indexer.meilisearch_indexer.meilisearch.Client",
            return_value=mock_client,
        ):
            indexer = MeilisearchIndexer(config)
            indexer._client = mock_client

            with pytest.raises(MeilisearchIndexError, match="different checksums"):
                await indexer.ingest()

        mock_client.create_index.assert_not_called()


# ─── Tests: Uncontrolled Index ───────────────────────────────────────────────


class TestUncontrolledIndex:
    """Test detection of indices in Meilisearch but not in registry."""

    @pytest.mark.asyncio
    async def test_index_in_meilisearch_not_in_registry_raises_error(
        self, tmp_path: Path
    ) -> None:
        """If index exists in Meilisearch but NOT in registry, raise error."""
        _write_fixtures(tmp_path)
        config = _make_config(tmp_path)

        # get_index succeeds (index exists in Meilisearch), no registry entry
        mock_client = _make_mock_client(get_index_raises=None)

        with patch(
            "moviebot.indexer.meilisearch_indexer.meilisearch.Client",
            return_value=mock_client,
        ):
            indexer = MeilisearchIndexer(config)
            indexer._client = mock_client

            with pytest.raises(MeilisearchIndexError, match="NOT in the registry"):
                await indexer.ingest()

    @pytest.mark.asyncio
    async def test_index_not_in_meilisearch_proceeds(self, tmp_path: Path) -> None:
        """If index does NOT exist in Meilisearch, proceed with creation."""
        _write_fixtures(tmp_path)
        config = _make_config(tmp_path)

        api_error = _make_api_error("index_not_found")
        mock_client = _make_mock_client(get_index_raises=api_error, stats_count=3)

        with patch(
            "moviebot.indexer.meilisearch_indexer.meilisearch.Client",
            return_value=mock_client,
        ):
            indexer = MeilisearchIndexer(config)
            indexer._client = mock_client
            result = await indexer.ingest()

        assert result.activated is True
        assert result.document_count == 3


# ─── Tests: Error Handling ───────────────────────────────────────────────────


class TestErrorHandling:
    """Test error conditions: connection failure, task failure."""

    @pytest.mark.asyncio
    async def test_connection_failure_on_create_index(self, tmp_path: Path) -> None:
        """Connection failure during create_index raises MeilisearchIndexError."""
        _write_fixtures(tmp_path)
        config = _make_config(tmp_path)

        api_error = _make_api_error("index_not_found")
        mock_client = _make_mock_client(get_index_raises=api_error)
        # create_index raises connection error
        mock_client.create_index.side_effect = Exception("Connection refused")

        with patch(
            "moviebot.indexer.meilisearch_indexer.meilisearch.Client",
            return_value=mock_client,
        ):
            indexer = MeilisearchIndexer(config)
            indexer._client = mock_client

            with pytest.raises(MeilisearchIndexError, match="Cannot connect"):
                await indexer.ingest()

    @pytest.mark.asyncio
    async def test_task_failure_raises_error(self, tmp_path: Path) -> None:
        """When a Meilisearch task reports 'failed' status, raise MeilisearchIndexError."""
        _write_fixtures(tmp_path)
        config = _make_config(tmp_path)

        api_error = _make_api_error("index_not_found")
        mock_client = _make_mock_client(
            get_index_raises=api_error,
            get_task_status="failed",
        )

        with patch(
            "moviebot.indexer.meilisearch_indexer.meilisearch.Client",
            return_value=mock_client,
        ):
            indexer = MeilisearchIndexer(config)
            indexer._client = mock_client

            with pytest.raises(MeilisearchIndexError, match="failed"):
                await indexer.ingest()

    @pytest.mark.asyncio
    async def test_connection_failure_on_get_index_check(self, tmp_path: Path) -> None:
        """Non-API exception during get_index raises MeilisearchIndexError."""
        _write_fixtures(tmp_path)
        config = _make_config(tmp_path)

        mock_client = _make_mock_client()
        mock_client.get_index.side_effect = ConnectionError("Network unreachable")

        with patch(
            "moviebot.indexer.meilisearch_indexer.meilisearch.Client",
            return_value=mock_client,
        ):
            indexer = MeilisearchIndexer(config)
            indexer._client = mock_client

            with pytest.raises(MeilisearchIndexError, match="Cannot connect"):
                await indexer.ingest()


# ─── Tests: Document Count Validation ────────────────────────────────────────


class TestDocumentCountValidation:
    """Test that document count mismatch is detected."""

    @pytest.mark.asyncio
    async def test_document_count_mismatch_raises_error(self, tmp_path: Path) -> None:
        """When index stats show different count than expected, raise error."""
        _write_fixtures(tmp_path)  # 3 documents
        config = _make_config(tmp_path)

        api_error = _make_api_error("index_not_found")
        # stats_count=2 but we have 3 documents → mismatch
        mock_client = _make_mock_client(get_index_raises=api_error, stats_count=2)

        with patch(
            "moviebot.indexer.meilisearch_indexer.meilisearch.Client",
            return_value=mock_client,
        ):
            indexer = MeilisearchIndexer(config)
            indexer._client = mock_client

            with pytest.raises(MeilisearchIndexError, match="Document count mismatch"):
                await indexer.ingest()

    @pytest.mark.asyncio
    async def test_document_count_match_succeeds(self, tmp_path: Path) -> None:
        """When document count matches, ingestion succeeds."""
        _write_fixtures(tmp_path)  # 3 documents
        config = _make_config(tmp_path)

        api_error = _make_api_error("index_not_found")
        mock_client = _make_mock_client(get_index_raises=api_error, stats_count=3)

        with patch(
            "moviebot.indexer.meilisearch_indexer.meilisearch.Client",
            return_value=mock_client,
        ):
            indexer = MeilisearchIndexer(config)
            indexer._client = mock_client
            result = await indexer.ingest()

        assert result.document_count == 3


# ─── Tests: Partial Index Cleanup on Failure ─────────────────────────────────


class TestPartialIndexCleanup:
    """Test that partially created indices are cleaned up on failure."""

    @pytest.mark.asyncio
    async def test_cleanup_on_task_failure(self, tmp_path: Path) -> None:
        """When a task fails after index creation, delete_index is called."""
        _write_fixtures(tmp_path)
        config = _make_config(tmp_path)

        api_error = _make_api_error("index_not_found")
        mock_client = _make_mock_client(
            get_index_raises=api_error,
            get_task_status="succeeded",
        )

        # Make create_index succeed, but then a later task (settings config) fails.
        # We simulate: first get_task call returns "succeeded" (create_index),
        # second call returns "failed" (settings configuration).
        succeeded_task = MagicMock()
        succeeded_task.status = "succeeded"
        failed_task = MagicMock()
        failed_task.status = "failed"
        failed_task.error = {"message": "Settings update failed"}
        mock_client.get_task.side_effect = [succeeded_task, failed_task]

        with patch(
            "moviebot.indexer.meilisearch_indexer.meilisearch.Client",
            return_value=mock_client,
        ):
            indexer = MeilisearchIndexer(config)
            indexer._client = mock_client

            with pytest.raises(MeilisearchIndexError):
                await indexer.ingest()

        # delete_index should have been called for cleanup
        mock_client.delete_index.assert_called_once_with("netflix_v1")

    @pytest.mark.asyncio
    async def test_cleanup_on_document_count_mismatch(self, tmp_path: Path) -> None:
        """When document count validation fails, partial index is cleaned up."""
        _write_fixtures(tmp_path)
        config = _make_config(tmp_path)

        api_error = _make_api_error("index_not_found")
        mock_client = _make_mock_client(get_index_raises=api_error, stats_count=999)

        with patch(
            "moviebot.indexer.meilisearch_indexer.meilisearch.Client",
            return_value=mock_client,
        ):
            indexer = MeilisearchIndexer(config)
            indexer._client = mock_client

            with pytest.raises(MeilisearchIndexError, match="Document count mismatch"):
                await indexer.ingest()

        mock_client.delete_index.assert_called_once_with("netflix_v1")

    @pytest.mark.asyncio
    async def test_no_cleanup_when_index_not_created(self, tmp_path: Path) -> None:
        """When failure happens before index creation, no cleanup needed."""
        _write_fixtures(tmp_path)
        config = _make_config(tmp_path)

        # Index exists in Meilisearch but not in registry → error before creation
        mock_client = _make_mock_client(get_index_raises=None)

        with patch(
            "moviebot.indexer.meilisearch_indexer.meilisearch.Client",
            return_value=mock_client,
        ):
            indexer = MeilisearchIndexer(config)
            indexer._client = mock_client

            with pytest.raises(MeilisearchIndexError):
                await indexer.ingest()

        # delete_index should NOT be called (index was not created by us)
        mock_client.delete_index.assert_not_called()


# ─── Tests: Atomic Registry Activation ───────────────────────────────────────


class TestAtomicRegistryActivation:
    """Test atomic write of registry file."""

    @pytest.mark.asyncio
    async def test_registry_json_structure(self, tmp_path: Path) -> None:
        """Registry file has correct JSON structure with active_index and indexes dict."""
        checksum = _write_fixtures(tmp_path)
        config = _make_config(tmp_path)

        api_error = _make_api_error("index_not_found")
        mock_client = _make_mock_client(get_index_raises=api_error, stats_count=3)

        with patch(
            "moviebot.indexer.meilisearch_indexer.meilisearch.Client",
            return_value=mock_client,
        ):
            indexer = MeilisearchIndexer(config)
            indexer._client = mock_client
            await indexer.ingest()

        registry_path = tmp_path / "index_registry.json"
        registry = json.loads(registry_path.read_text(encoding="utf-8"))

        # Structure checks
        assert "active_index" in registry
        assert "indexes" in registry
        assert isinstance(registry["indexes"], dict)
        assert registry["active_index"] == "netflix_v1"

        # Index entry checks
        entry = registry["indexes"]["netflix_v1"]
        assert entry["canonical_dataset_version"] == "v1"
        assert entry["schema_version"] == "1.0.0"
        assert entry["dataset_checksum"] == checksum
        assert len(entry["settings_checksum"]) == 64
        assert entry["document_count"] == 3
        assert entry["status"] == "active"
        # created_at should be ISO format
        assert "T" in entry["created_at"]
        assert entry["created_at"].endswith("Z")

    @pytest.mark.asyncio
    async def test_registry_not_written_on_failure(self, tmp_path: Path) -> None:
        """When ingestion fails, registry is NOT created/modified."""
        _write_fixtures(tmp_path)
        config = _make_config(tmp_path)

        api_error = _make_api_error("index_not_found")
        mock_client = _make_mock_client(
            get_index_raises=api_error,
            get_task_status="failed",
        )

        with patch(
            "moviebot.indexer.meilisearch_indexer.meilisearch.Client",
            return_value=mock_client,
        ):
            indexer = MeilisearchIndexer(config)
            indexer._client = mock_client

            with pytest.raises(MeilisearchIndexError):
                await indexer.ingest()

        registry_path = tmp_path / "index_registry.json"
        assert not registry_path.exists()

    @pytest.mark.asyncio
    async def test_registry_is_valid_json(self, tmp_path: Path) -> None:
        """Registry file is valid parseable JSON after activation."""
        _write_fixtures(tmp_path)
        config = _make_config(tmp_path)

        api_error = _make_api_error("index_not_found")
        mock_client = _make_mock_client(get_index_raises=api_error, stats_count=3)

        with patch(
            "moviebot.indexer.meilisearch_indexer.meilisearch.Client",
            return_value=mock_client,
        ):
            indexer = MeilisearchIndexer(config)
            indexer._client = mock_client
            await indexer.ingest()

        registry_path = tmp_path / "index_registry.json"
        content = registry_path.read_text(encoding="utf-8")
        parsed = json.loads(content)
        assert isinstance(parsed, dict)


# ─── Tests: Settings Checksum Reproducibility ────────────────────────────────


class TestSettingsChecksum:
    """Test that settings_checksum is deterministic and reproducible."""

    def test_settings_checksum_is_deterministic(self, tmp_path: Path) -> None:
        """Computing settings checksum twice produces identical result."""
        config = _make_config(tmp_path)

        with patch("moviebot.indexer.meilisearch_indexer.meilisearch.Client"):
            indexer = MeilisearchIndexer(config)

        checksum1 = indexer._compute_settings_checksum()
        checksum2 = indexer._compute_settings_checksum()

        assert checksum1 == checksum2
        assert len(checksum1) == 64

    def test_settings_checksum_is_64_hex_chars(self, tmp_path: Path) -> None:
        """Settings checksum is a valid 64-character hex string."""
        import re

        config = _make_config(tmp_path)

        with patch("moviebot.indexer.meilisearch_indexer.meilisearch.Client"):
            indexer = MeilisearchIndexer(config)

        checksum = indexer._compute_settings_checksum()
        assert re.match(r"^[0-9a-f]{64}$", checksum)


# ─── Tests: File Validation ──────────────────────────────────────────────────


class TestFileValidation:
    """Test handling of missing/invalid input files."""

    @pytest.mark.asyncio
    async def test_missing_titles_jsonl_raises_error(self, tmp_path: Path) -> None:
        """When titles.jsonl does not exist, raise FileNotFoundError."""
        config = _make_config(tmp_path)

        with patch("moviebot.indexer.meilisearch_indexer.meilisearch.Client"):
            indexer = MeilisearchIndexer(config)

            with pytest.raises(FileNotFoundError, match="titles.jsonl"):
                await indexer.ingest()

    @pytest.mark.asyncio
    async def test_missing_metadata_json_raises_error(self, tmp_path: Path) -> None:
        """When metadata.json does not exist, raise FileNotFoundError."""
        config = _make_config(tmp_path)
        # Write titles.jsonl but not metadata.json
        doc = {"id": "tm001", "title": "Test", "type": "movie", "release_year": 2020}
        (tmp_path / "titles.jsonl").write_text(json.dumps(doc) + "\n", encoding="utf-8")

        with patch("moviebot.indexer.meilisearch_indexer.meilisearch.Client"):
            indexer = MeilisearchIndexer(config)

            with pytest.raises(FileNotFoundError, match="metadata.json"):
                await indexer.ingest()

    @pytest.mark.asyncio
    async def test_metadata_version_mismatch_raises_error(self, tmp_path: Path) -> None:
        """When metadata canonical_dataset_version doesn't match config, raise ValueError."""
        config = _make_config(tmp_path, version="v1")

        doc = {"id": "tm001", "title": "Test", "type": "movie", "release_year": 2020}
        jsonl_bytes = (json.dumps(doc) + "\n").encode("utf-8")
        (tmp_path / "titles.jsonl").write_bytes(jsonl_bytes)

        checksum = hashlib.sha256(jsonl_bytes).hexdigest()
        metadata = {
            "canonical_dataset_version": "v2",  # MISMATCH with config "v1"
            "etl_version": "1.0.0",
            "schema_version": "1.0.0",
            "document_count": 1,
            "discarded_count": 0,
            "source_checksums": {"titles.csv": "a" * 64},
            "output_checksum_sha256": checksum,
            "generated_at": "2024-01-15T10:30:00Z",
            "type_distribution": {"movie": 1},
        }
        (tmp_path / "metadata.json").write_text(json.dumps(metadata), encoding="utf-8")

        with patch("moviebot.indexer.meilisearch_indexer.meilisearch.Client"):
            indexer = MeilisearchIndexer(config)

            with pytest.raises(ValueError, match="does not match config"):
                await indexer.ingest()


# ─── Tests: Batch Ingestion ──────────────────────────────────────────────────


class TestBatchIngestion:
    """Test batch document ingestion behavior."""

    @pytest.mark.asyncio
    async def test_documents_batched_correctly(self, tmp_path: Path) -> None:
        """Documents are split into batches of batch_size."""
        _write_fixtures(tmp_path)  # 3 documents, batch_size=2
        config = _make_config(tmp_path)

        api_error = _make_api_error("index_not_found")
        mock_client = _make_mock_client(get_index_raises=api_error, stats_count=3)
        mock_index = mock_client.index.return_value

        with patch(
            "moviebot.indexer.meilisearch_indexer.meilisearch.Client",
            return_value=mock_client,
        ):
            indexer = MeilisearchIndexer(config)
            indexer._client = mock_client
            await indexer.ingest()

        # batch_size=2, 3 documents → 2 batches (2+1)
        assert mock_index.add_documents.call_count == 2
        first_batch = mock_index.add_documents.call_args_list[0][0][0]
        second_batch = mock_index.add_documents.call_args_list[1][0][0]
        assert len(first_batch) == 2
        assert len(second_batch) == 1


# ─── Tests: Activate Method ──────────────────────────────────────────────────


class TestActivateMethod:
    """Test the standalone activate() method."""

    @pytest.mark.asyncio
    async def test_activate_updates_registry(self, tmp_path: Path) -> None:
        """activate() marks the specified index as active in the registry."""
        config = _make_config(tmp_path)

        # Create initial registry with an inactive index
        registry = {
            "active_index": None,
            "indexes": {
                "netflix_v1": {
                    "canonical_dataset_version": "v1",
                    "schema_version": "1.0.0",
                    "dataset_checksum": "a" * 64,
                    "settings_checksum": "b" * 64,
                    "document_count": 100,
                    "created_at": "2024-01-15T10:30:00Z",
                    "status": "inactive",
                }
            },
        }
        (tmp_path / "index_registry.json").write_text(
            json.dumps(registry), encoding="utf-8"
        )

        with patch("moviebot.indexer.meilisearch_indexer.meilisearch.Client"):
            indexer = MeilisearchIndexer(config)
            await indexer.activate("netflix_v1")

        updated = json.loads(
            (tmp_path / "index_registry.json").read_text(encoding="utf-8")
        )
        assert updated["active_index"] == "netflix_v1"
        assert updated["indexes"]["netflix_v1"]["status"] == "active"

    @pytest.mark.asyncio
    async def test_activate_nonexistent_index_raises_error(
        self, tmp_path: Path
    ) -> None:
        """activate() on an index not in registry raises MeilisearchIndexError."""
        config = _make_config(tmp_path)

        registry = {"active_index": None, "indexes": {}}
        (tmp_path / "index_registry.json").write_text(
            json.dumps(registry), encoding="utf-8"
        )

        with patch("moviebot.indexer.meilisearch_indexer.meilisearch.Client"):
            indexer = MeilisearchIndexer(config)

            with pytest.raises(MeilisearchIndexError, match="not found in registry"):
                await indexer.activate("netflix_v99")
