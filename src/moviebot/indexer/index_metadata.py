# src/moviebot/indexer/index_metadata.py
"""Index registry models for Meilisearch index lifecycle management.

Defines the Pydantic models that represent the `index_registry.json` structure,
tracking all managed indexes and which one is currently active.
"""

from typing import Literal

from pydantic import BaseModel, Field


class IndexMetadata(BaseModel):
    """Metadata for a single Meilisearch index entry in the registry."""

    canonical_dataset_version: str = Field(
        description="Canonical dataset version used to build this index",
    )
    schema_version: str = Field(
        pattern=r"^\d+\.\d+\.\d+$",
        description="Semantic version of the canonical schema at index creation time",
    )
    dataset_checksum: str = Field(
        pattern=r"^[0-9a-f]{64}$",
        description="SHA-256 hex digest of the titles.jsonl used for ingestion",
    )
    settings_checksum: str = Field(
        pattern=r"^[0-9a-f]{64}$",
        description="SHA-256 hex digest of the deterministic JSON representation of index settings",
    )
    document_count: int = Field(
        ge=0,
        description="Number of documents ingested into the index",
    )
    created_at: str = Field(
        pattern=r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$",
        description="ISO 8601 UTC timestamp of index creation",
    )
    status: Literal["active", "inactive", "failed"] = Field(
        description="Current status of the index",
    )


class IndexRegistry(BaseModel):
    """Top-level model for `index_registry.json`.

    Tracks all managed Meilisearch indexes and identifies the currently active one.
    The active index is the one used by the Netflix Repository at runtime.
    """

    active_index: str | None = Field(
        default=None,
        description="Name of the currently active index, or None if no index is active",
    )
    indexes: dict[str, IndexMetadata] = Field(
        default_factory=dict,
        description="Mapping of index name to its metadata",
    )
