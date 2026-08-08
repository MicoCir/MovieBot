# src/moviebot/etl/schema.py
"""Canonical schema models for the Netflix ETL pipeline.

Defines the contract for the canonical dataset (JSONL) and its metadata.
"""

from typing import Annotated, Literal

from pydantic import BaseModel, Field, field_validator


class CanonicalNetflixTitle(BaseModel, extra="forbid"):
    """Schema canónico v1.0.0 — contrato del dataset JSONL.

    Each line in titles.jsonl is a serialized instance of this model.
    """

    # Required fields
    id: str = Field(max_length=20, pattern=r"^t[ms]\d+$")
    title: str = Field(max_length=500, min_length=1)
    type: Literal["movie", "show"]
    release_year: int = Field(ge=1888, le=2100)

    # Optional fields
    description: str | None = Field(default=None, max_length=2000)
    age_certification: str | None = Field(default=None, max_length=20)
    genres: list[str] = Field(default_factory=list)
    actors: list[str] = Field(default_factory=list)
    directors: list[str] = Field(default_factory=list)
    imdb_score: float | None = Field(default=None, ge=0.0, le=10.0)
    tmdb_score: float | None = Field(default=None, ge=0.0, le=10.0)
    tmdb_popularity: float | None = Field(default=None, ge=0.0, le=10000.0)


class EtlMetadata(BaseModel):
    """Metadata for a canonical dataset version.

    Written to metadata.json alongside titles.jsonl.
    """

    canonical_dataset_version: str = Field(
        pattern=r"^[a-zA-Z0-9_\-]+$",
        description="Safe for use as directory name (no path separators or special chars)",
    )
    etl_version: str = Field(
        pattern=r"^\d+\.\d+\.\d+$",
        description="Semantic version of the ETL code",
    )
    schema_version: str = Field(
        pattern=r"^\d+\.\d+\.\d+$",
        description="Semantic version of the canonical schema",
    )
    document_count: int = Field(ge=0)
    discarded_count: int = Field(ge=0)
    source_checksums: dict[str, Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]] = (
        Field(description="Mapping of source filename to SHA-256 hex digest (64 chars)")
    )
    output_checksum_sha256: str = Field(
        pattern=r"^[0-9a-f]{64}$",
        description="SHA-256 hex digest of the output titles.jsonl file",
    )
    generated_at: str = Field(
        pattern=r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$",
        description="ISO 8601 UTC timestamp of generation",
    )
    type_distribution: dict[str, int] = Field(
        description="Distribution of document types (e.g., {'movie': 4000, 'show': 1849})",
    )

    @field_validator("source_checksums")
    @classmethod
    def validate_checksum_values(cls, v: dict[str, str]) -> dict[str, str]:
        """Ensure all source checksum values are valid 64-char hex strings."""
        import re

        pattern = re.compile(r"^[0-9a-f]{64}$")
        for filename, checksum in v.items():
            if not pattern.match(checksum):
                raise ValueError(
                    f"Invalid checksum for '{filename}': must be 64 lowercase hex characters"
                )
        return v
