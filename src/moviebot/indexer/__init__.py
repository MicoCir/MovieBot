# src/moviebot/indexer/__init__.py
"""Meilisearch indexer module for the Netflix data pipeline."""

from moviebot.indexer.meilisearch_indexer import (
    IndexerConfig,
    IndexResult,
    MeilisearchIndexer,
    MeilisearchIndexError,
)

__all__ = [
    "IndexResult",
    "IndexerConfig",
    "MeilisearchIndexError",
    "MeilisearchIndexer",
]
