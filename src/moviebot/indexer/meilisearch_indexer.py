# src/moviebot/indexer/meilisearch_indexer.py
"""Meilisearch indexer for the Netflix canonical dataset.

Ingests the canonical dataset (titles.jsonl) into a versioned, immutable
Meilisearch index with idempotency guarantees and atomic registry activation.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import tempfile
import time
from dataclasses import dataclass
from datetime import UTC
from pathlib import Path
from typing import Any, ClassVar

import meilisearch

from moviebot.etl.schema import EtlMetadata

logger = logging.getLogger(__name__)


class MeilisearchIndexError(Exception):
    """Error during Meilisearch indexing operations.

    Raised for: connection failures, task failures, timeouts,
    document count mismatches, and checksum conflicts.
    """


@dataclass(frozen=True)
class IndexerConfig:
    """Configuration for the Meilisearch indexer."""

    meilisearch_url: str
    meilisearch_api_key: str | None
    canonical_dataset_version: str
    schema_version: str
    titles_jsonl_path: Path
    registry_path: Path  # config/meilisearch/index_registry.json
    batch_size: int = 500  # documents per ingestion batch
    task_timeout_seconds: int = 120

    @property
    def metadata_path(self) -> Path:
        """Derived: metadata.json in the same directory as titles.jsonl."""
        return self.titles_jsonl_path.parent / "metadata.json"


@dataclass(frozen=True)
class IndexResult:
    """Result of an ingestion operation."""

    index_name: str  # e.g. "netflix_v1"
    document_count: int
    dataset_checksum: str  # 64-char hex, no prefix
    settings_checksum: str  # 64-char hex, no prefix
    activated: bool


class MeilisearchIndexer:
    """Ingests canonical dataset into a versioned Meilisearch index.

    The indexer ensures:
    - Idempotency: same dataset + settings → no recreation needed
    - Immutability: never overwrites an existing index with different data
    - Atomic activation: registry updated only after full validation
    - Cleanup: partial indices are deleted on failure
    """

    SEARCHABLE_ATTRIBUTES: ClassVar[list[str]] = [
        "title",
        "description",
        "genres",
        "actors",
        "directors",
    ]
    FILTERABLE_ATTRIBUTES: ClassVar[list[str]] = [
        "type",
        "genres",
        "release_year",
        "age_certification",
        "imdb_score",
        "tmdb_score",
        "actors",
        "directors",
    ]
    SORTABLE_ATTRIBUTES: ClassVar[list[str]] = []  # Not required in v1

    def __init__(self, config: IndexerConfig) -> None:
        self._config = config
        self._client = meilisearch.Client(
            config.meilisearch_url,
            config.meilisearch_api_key,
        )

    @property
    def index_name(self) -> str:
        """Return the index name: netflix_{canonical_dataset_version}."""
        return f"netflix_{self._config.canonical_dataset_version}"

    async def ingest(self) -> IndexResult:
        """Full ingestion: validate → check idempotency → create → configure → ingest → validate → activate.

        Raises:
            FileNotFoundError: titles.jsonl or metadata.json does not exist
            ValueError: JSONL not parseable, metadata inconsistent, or checksum mismatch
            MeilisearchIndexError: connection error, task failure, or checksum conflict
        """
        # Step 0: Validate metadata and compute dataset checksum
        metadata = self._validate_metadata()
        dataset_checksum = metadata.output_checksum_sha256
        settings_checksum = self._compute_settings_checksum()
        target_index = self.index_name

        # Step 1: Read and parse titles.jsonl
        documents = self._read_documents()

        # Step 2: Check idempotency via registry
        registry = self._load_registry()
        idempotency_result = self._check_idempotency(
            registry, target_index, dataset_checksum, settings_checksum, len(documents)
        )
        if idempotency_result is not None:
            return idempotency_result

        # Step 2b: Check if index exists in Meilisearch but NOT in registry
        self._check_uncontrolled_index(registry, target_index)

        # Steps 3-9: Create index, configure, ingest, validate, activate
        index_created = False
        try:
            # Step 3: Create index with primary_key="id"
            self._create_index(target_index)
            index_created = True

            # Step 4: Configure searchable + filterable attributes
            self._configure_settings(target_index)

            # Step 5: Batch ingest documents
            task_uids = self._batch_ingest(target_index, documents)

            # Step 6: Wait for all tasks
            self._wait_for_tasks(task_uids)

            # Step 7: Validate document count
            self._validate_document_count(target_index, len(documents))

            # Step 8: Compute checksums (already computed above)
            # Step 9: Activate index (update registry atomically)
            self._activate(
                target_index,
                dataset_checksum,
                settings_checksum,
                len(documents),
                registry,
            )

            logger.info(
                "Successfully ingested %d documents into index '%s'",
                len(documents),
                target_index,
            )

            return IndexResult(
                index_name=target_index,
                document_count=len(documents),
                dataset_checksum=dataset_checksum,
                settings_checksum=settings_checksum,
                activated=True,
            )

        except (MeilisearchIndexError, Exception) as exc:
            # Clean up partially created index on failure
            if index_created:
                self._cleanup_index(target_index)
            # Never activate a failed index
            if isinstance(exc, MeilisearchIndexError):
                raise
            raise MeilisearchIndexError(
                f"Unexpected error during ingestion: {exc}"
            ) from exc

    async def activate(self, index_name: str) -> None:
        """Mark an index as active by updating the registry atomically.

        Atomic write: temp file → validate JSON parseable → atomic rename.
        On activation failure, the registry is NOT modified.
        """
        registry = self._load_registry()
        if index_name not in registry.get("indexes", {}):
            raise MeilisearchIndexError(
                f"Cannot activate index '{index_name}': not found in registry"
            )
        registry["active_index"] = index_name
        registry["indexes"][index_name]["status"] = "active"
        self._atomic_write_registry(registry)
        logger.info("Activated index '%s'", index_name)

    # ─── Private Methods ─────────────────────────────────────────────────

    def _validate_metadata(self) -> EtlMetadata:
        """Read and validate metadata.json, verify consistency with titles.jsonl."""
        metadata_path = self._config.metadata_path
        titles_path = self._config.titles_jsonl_path

        if not titles_path.exists():
            raise FileNotFoundError(f"titles.jsonl not found at: {titles_path}")
        if not metadata_path.exists():
            raise FileNotFoundError(f"metadata.json not found at: {metadata_path}")

        # Parse metadata
        try:
            raw = metadata_path.read_text(encoding="utf-8")
            metadata = EtlMetadata.model_validate_json(raw)
        except Exception as exc:
            raise ValueError(
                f"Failed to parse metadata.json at {metadata_path}: {exc}"
            ) from exc

        # Verify canonical_dataset_version matches config
        if metadata.canonical_dataset_version != self._config.canonical_dataset_version:
            raise ValueError(
                f"Metadata canonical_dataset_version '{metadata.canonical_dataset_version}' "
                f"does not match config '{self._config.canonical_dataset_version}'"
            )

        # Compute SHA-256 of titles.jsonl and verify against metadata
        computed_checksum = self._compute_file_checksum(titles_path)
        if computed_checksum != metadata.output_checksum_sha256:
            raise ValueError(
                f"titles.jsonl checksum mismatch: computed={computed_checksum}, "
                f"metadata={metadata.output_checksum_sha256}"
            )

        return metadata

    def _compute_file_checksum(self, path: Path) -> str:
        """Compute SHA-256 hex digest of a file."""
        h = hashlib.sha256()
        with open(path, "rb") as f:
            while chunk := f.read(65536):
                h.update(chunk)
        return h.hexdigest()

    def _compute_settings_checksum(self) -> str:
        """Compute deterministic SHA-256 of the index settings configuration."""
        settings = {
            "filterableAttributes": sorted(self.FILTERABLE_ATTRIBUTES),
            "primaryKey": "id",
            "searchableAttributes": self.SEARCHABLE_ATTRIBUTES,
            "sortableAttributes": self.SORTABLE_ATTRIBUTES,
        }
        payload = json.dumps(
            settings, sort_keys=True, separators=(",", ":"), ensure_ascii=False
        ).encode("utf-8")
        return hashlib.sha256(payload).hexdigest()

    def _read_documents(self) -> list[dict[str, Any]]:
        """Read and parse titles.jsonl into a list of documents."""
        titles_path = self._config.titles_jsonl_path
        documents: list[dict[str, Any]] = []

        try:
            with open(titles_path, "r", encoding="utf-8") as f:
                for line_num, line in enumerate(f, start=1):
                    stripped = line.strip()
                    if not stripped:
                        continue
                    try:
                        doc = json.loads(stripped)
                        documents.append(doc)
                    except json.JSONDecodeError as exc:
                        raise ValueError(
                            f"Invalid JSON at line {line_num} in {titles_path}: {exc}"
                        ) from exc
        except OSError as exc:
            raise FileNotFoundError(
                f"Cannot read titles.jsonl at {titles_path}: {exc}"
            ) from exc

        if not documents:
            raise ValueError(
                f"titles.jsonl at {titles_path} contains no valid documents"
            )

        return documents

    def _load_registry(self) -> dict[str, Any]:
        """Load the index registry JSON, returning empty structure if not found."""
        registry_path = self._config.registry_path
        if not registry_path.exists():
            return {"active_index": None, "indexes": {}}
        try:
            raw = registry_path.read_text(encoding="utf-8")
            return json.loads(raw)
        except (json.JSONDecodeError, OSError) as exc:
            logger.warning("Failed to read registry at %s: %s", registry_path, exc)
            return {"active_index": None, "indexes": {}}

    def _check_idempotency(
        self,
        registry: dict[str, Any],
        target_index: str,
        dataset_checksum: str,
        settings_checksum: str,
        document_count: int,
    ) -> IndexResult | None:
        """Check if index already exists with matching checksums.

        Returns IndexResult if idempotent (no work needed), None if new ingestion required.
        Raises MeilisearchIndexError if checksums differ (conflict).
        """
        indexes = registry.get("indexes", {})
        if target_index not in indexes:
            return None

        existing = indexes[target_index]
        existing_dataset_checksum = existing.get("dataset_checksum", "")
        existing_settings_checksum = existing.get("settings_checksum", "")

        if (
            existing_dataset_checksum == dataset_checksum
            and existing_settings_checksum == settings_checksum
        ):
            # True idempotency: same data, same settings → return success
            logger.info(
                "Index '%s' already exists with matching checksums. Skipping ingestion.",
                target_index,
            )
            return IndexResult(
                index_name=target_index,
                document_count=existing.get("document_count", document_count),
                dataset_checksum=dataset_checksum,
                settings_checksum=settings_checksum,
                activated=existing.get("status") == "active",
            )

        # Checksums differ → conflict, never overwrite
        raise MeilisearchIndexError(
            f"Index '{target_index}' already exists in registry with different checksums. "
            f"Registry dataset_checksum={existing_dataset_checksum}, "
            f"new dataset_checksum={dataset_checksum}. "
            f"Registry settings_checksum={existing_settings_checksum}, "
            f"new settings_checksum={settings_checksum}. "
            "Cannot overwrite an existing index."
        )

    def _check_uncontrolled_index(
        self, registry: dict[str, Any], target_index: str
    ) -> None:
        """Abort if index exists in Meilisearch but NOT in the registry.

        We never interact with indices we didn't create.
        """
        try:
            self._client.get_index(target_index)
        except meilisearch.errors.MeilisearchApiError as exc:
            if "index_not_found" in str(exc):
                # Index doesn't exist in Meilisearch, safe to proceed
                return
            raise MeilisearchIndexError(
                f"Error checking index '{target_index}' in Meilisearch: {exc}"
            ) from exc
        except Exception as exc:
            raise MeilisearchIndexError(
                f"Cannot connect to Meilisearch at {self._config.meilisearch_url}: {exc}"
            ) from exc

        # Index exists in Meilisearch but not in registry → abort
        indexes = registry.get("indexes", {})
        if target_index not in indexes:
            raise MeilisearchIndexError(
                f"Index '{target_index}' exists in Meilisearch but is NOT in the registry. "
                "Refusing to interact with an uncontrolled index. "
                "Please remove it manually or add it to the registry."
            )

    def _create_index(self, target_index: str) -> None:
        """Create the Meilisearch index with primary_key='id'."""
        try:
            task_info = self._client.create_index(target_index, {"primaryKey": "id"})
            self._wait_for_single_task(task_info.task_uid)
        except meilisearch.errors.MeilisearchApiError as exc:
            raise MeilisearchIndexError(
                f"Failed to create index '{target_index}': {exc}"
            ) from exc
        except Exception as exc:
            raise MeilisearchIndexError(
                f"Cannot connect to Meilisearch at {self._config.meilisearch_url}: {exc}"
            ) from exc

    def _configure_settings(self, target_index: str) -> None:
        """Configure searchable, filterable, and sortable attributes."""
        try:
            index = self._client.index(target_index)

            # Update searchable attributes
            task_info = index.update_searchable_attributes(self.SEARCHABLE_ATTRIBUTES)
            self._wait_for_single_task(task_info.task_uid)

            # Update filterable attributes
            task_info = index.update_filterable_attributes(self.FILTERABLE_ATTRIBUTES)
            self._wait_for_single_task(task_info.task_uid)

            # Update sortable attributes (empty list in v1)
            if self.SORTABLE_ATTRIBUTES:
                task_info = index.update_sortable_attributes(self.SORTABLE_ATTRIBUTES)
                self._wait_for_single_task(task_info.task_uid)

        except meilisearch.errors.MeilisearchApiError as exc:
            raise MeilisearchIndexError(
                f"Failed to configure settings for index '{target_index}': {exc}"
            ) from exc
        except MeilisearchIndexError:
            raise
        except Exception as exc:
            raise MeilisearchIndexError(
                f"Error configuring settings for '{target_index}': {exc}"
            ) from exc

    def _batch_ingest(
        self, target_index: str, documents: list[dict[str, Any]]
    ) -> list[int]:
        """Ingest documents in batches, returning task UIDs."""
        task_uids: list[int] = []
        batch_size = self._config.batch_size

        try:
            index = self._client.index(target_index)
            for i in range(0, len(documents), batch_size):
                batch = documents[i : i + batch_size]
                task_info = index.add_documents(batch)
                task_uids.append(task_info.task_uid)
                logger.debug(
                    "Submitted batch %d/%d (%d documents)",
                    (i // batch_size) + 1,
                    (len(documents) + batch_size - 1) // batch_size,
                    len(batch),
                )
        except meilisearch.errors.MeilisearchApiError as exc:
            raise MeilisearchIndexError(
                f"Failed to ingest documents into '{target_index}': {exc}"
            ) from exc
        except Exception as exc:
            raise MeilisearchIndexError(
                f"Error during batch ingestion into '{target_index}': {exc}"
            ) from exc

        return task_uids

    def _wait_for_tasks(self, task_uids: list[int]) -> None:
        """Wait for all tasks to complete successfully."""
        for uid in task_uids:
            self._wait_for_single_task(uid)

    def _wait_for_single_task(self, task_uid: int) -> None:
        """Wait for a single task to reach 'succeeded' status.

        Raises MeilisearchIndexError on failure or timeout.
        """
        timeout = self._config.task_timeout_seconds
        start_time = time.monotonic()

        while True:
            elapsed = time.monotonic() - start_time
            if elapsed > timeout:
                raise MeilisearchIndexError(
                    f"Task {task_uid} timed out after {timeout}s"
                )

            try:
                task = self._client.get_task(task_uid)
            except Exception as exc:
                raise MeilisearchIndexError(
                    f"Failed to check status of task {task_uid}: {exc}"
                ) from exc

            status = task.status
            if status == "succeeded":
                return
            elif status == "failed":
                error_info = getattr(task, "error", None) or {}
                raise MeilisearchIndexError(f"Task {task_uid} failed: {error_info}")
            elif status in ("enqueued", "processing"):
                time.sleep(0.1)
            else:
                raise MeilisearchIndexError(
                    f"Task {task_uid} has unexpected status: {status}"
                )

    def _validate_document_count(self, target_index: str, expected: int) -> None:
        """Verify the document count in the index matches expected."""
        try:
            index = self._client.index(target_index)
            stats = index.get_stats()
            actual = stats.number_of_documents
        except Exception as exc:
            raise MeilisearchIndexError(
                f"Failed to get stats for index '{target_index}': {exc}"
            ) from exc

        if actual != expected:
            raise MeilisearchIndexError(
                f"Document count mismatch in index '{target_index}': "
                f"expected={expected}, actual={actual}"
            )

    def _activate(
        self,
        target_index: str,
        dataset_checksum: str,
        settings_checksum: str,
        document_count: int,
        registry: dict[str, Any],
    ) -> None:
        """Activate the index by atomically updating the registry."""
        from datetime import datetime

        created_at = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")

        # Update registry data
        if "indexes" not in registry:
            registry["indexes"] = {}

        registry["indexes"][target_index] = {
            "canonical_dataset_version": self._config.canonical_dataset_version,
            "schema_version": self._config.schema_version,
            "dataset_checksum": dataset_checksum,
            "settings_checksum": settings_checksum,
            "document_count": document_count,
            "created_at": created_at,
            "status": "active",
        }
        registry["active_index"] = target_index

        self._atomic_write_registry(registry)

    def _atomic_write_registry(self, registry: dict[str, Any]) -> None:
        """Write registry atomically: temp file → validate JSON → os.replace."""
        registry_path = self._config.registry_path

        # Ensure parent directory exists
        registry_path.parent.mkdir(parents=True, exist_ok=True)

        # Serialize to JSON
        content = json.dumps(registry, indent=2, ensure_ascii=False) + "\n"

        # Write to temp file in the same directory (for atomic rename)
        temp_fd = None
        temp_path = None
        try:
            temp_fd, temp_path_str = tempfile.mkstemp(
                dir=str(registry_path.parent),
                prefix="index_registry_",
                suffix=".tmp",
            )
            temp_path = Path(temp_path_str)
            os.write(temp_fd, content.encode("utf-8"))
            os.close(temp_fd)
            temp_fd = None

            # Validate the temp file is parseable as valid JSON
            validation_content = temp_path.read_text(encoding="utf-8")
            json.loads(validation_content)

            # Atomic rename
            os.replace(str(temp_path), str(registry_path))
            logger.info("Registry updated atomically at %s", registry_path)

        except Exception as exc:
            # Clean up temp file on failure
            if temp_fd is not None:
                try:
                    os.close(temp_fd)
                except OSError:
                    pass
            if temp_path is not None and temp_path.exists():
                try:
                    temp_path.unlink()
                except OSError:
                    pass
            raise MeilisearchIndexError(
                f"Failed to write registry atomically: {exc}"
            ) from exc

    def _cleanup_index(self, target_index: str) -> None:
        """Delete a partially created index from Meilisearch."""
        try:
            task_info = self._client.delete_index(target_index)
            # Best-effort wait for deletion
            try:
                self._wait_for_single_task(task_info.task_uid)
            except MeilisearchIndexError:
                pass  # Cleanup is best-effort
            logger.info("Cleaned up partial index '%s'", target_index)
        except (meilisearch.errors.MeilisearchApiError, OSError) as exc:
            logger.warning(
                "Failed to clean up partial index '%s': %s", target_index, exc
            )


# ─── CLI Entrypoint ──────────────────────────────────────────────────────────

if __name__ == "__main__":
    import argparse
    import asyncio
    import sys

    parser = argparse.ArgumentParser(
        description="Ingest Netflix canonical dataset into a versioned Meilisearch index.",
    )
    parser.add_argument(
        "--canonical-version",
        type=str,
        required=True,
        help="Canonical dataset version (e.g. 'v1'). Used to derive index name and JSONL path.",
    )
    parser.add_argument(
        "--url",
        type=str,
        default="http://localhost:7700",
        help="Meilisearch server URL (default: http://localhost:7700)",
    )
    parser.add_argument(
        "--api-key",
        type=str,
        default=None,
        help="Meilisearch API key (optional)",
    )
    parser.add_argument(
        "--schema-version",
        type=str,
        default="1.0.0",
        help="Schema version (default: 1.0.0)",
    )
    parser.add_argument(
        "--registry",
        type=Path,
        default=Path("config/meilisearch/index_registry.json"),
        help="Path to the index registry JSON (default: config/meilisearch/index_registry.json)",
    )

    args = parser.parse_args()

    # Derive titles.jsonl path from canonical-version
    titles_jsonl_path = Path(
        f"data/processed/netflix/{args.canonical_version}/titles.jsonl"
    )

    config = IndexerConfig(
        meilisearch_url=args.url,
        meilisearch_api_key=args.api_key,
        canonical_dataset_version=args.canonical_version,
        schema_version=args.schema_version,
        titles_jsonl_path=titles_jsonl_path,
        registry_path=args.registry,
    )

    indexer = MeilisearchIndexer(config)

    try:
        result = asyncio.run(indexer.ingest())
    except (FileNotFoundError, ValueError, MeilisearchIndexError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)

    print("=== Meilisearch Indexer Result ===")
    print(f"  Index name:        {result.index_name}")
    print(f"  Document count:    {result.document_count}")
    print(f"  Dataset checksum:  {result.dataset_checksum}")
    print(f"  Activated:         {result.activated}")
