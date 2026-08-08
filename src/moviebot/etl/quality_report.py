# src/moviebot/etl/quality_report.py
"""Quality report models for the Netflix ETL pipeline.

Tracks discarded records, field nullifications, and coverage statistics
produced during ETL execution.
"""

from __future__ import annotations

from dataclasses import dataclass

from pydantic import BaseModel, Field


@dataclass(frozen=True)
class DiscardedRecord:
    """A record that was discarded during ETL validation.

    Records are discarded when mandatory fields fail validation
    (invalid id, empty title, invalid type, out-of-range release_year).
    """

    id_value: str
    """The value of the id field (even if invalid)."""

    field: str
    """Which field caused the discard (e.g., 'id', 'title', 'type', 'release_year')."""

    reason: str
    """Human-readable reason for discard."""

    original_value: str
    """The original value of the failing field."""


@dataclass(frozen=True)
class FieldNullification:
    """A field that was converted to null (or defaulted) during ETL transformation.

    Covers both length exceedances (field → null) and default substitutions
    (e.g., malformed genres → []). The reason field documents the specific case.
    """

    id_value: str
    """The id of the record."""

    field: str
    """Which field was nullified (e.g., 'description', 'imdb_score', 'genres')."""

    reason: str
    """Reason for nullification (e.g., 'exceeded max_length 2000',
    'value 11.5 outside range 0.0-10.0',
    'malformed genres literal, defaulted to []')."""

    original_length: int | None
    """Original string length (for length exceedances), None otherwise."""

    max_length: int | None
    """The max allowed length (for length exceedances), None otherwise."""


class QualityReport(BaseModel):
    """ETL quality report summarizing data quality issues.

    Serialized to quality_report.json alongside the canonical dataset.
    """

    model_config = {"arbitrary_types_allowed": True}

    total_discarded: int = Field(
        ge=0,
        description="Total number of records discarded during ETL.",
    )

    discarded_records: list[DiscardedRecord] = Field(
        default_factory=list,
        description="List of discarded records, sorted by (id_value, field).",
    )

    field_coverage: dict[str, float] = Field(
        default_factory=dict,
        description="Percentage of non-null values per field (0.0-100.0).",
    )

    type_distribution: dict[str, int] = Field(
        default_factory=dict,
        description="Count per type ('movie', 'show').",
    )

    field_nullifications: list[FieldNullification] = Field(
        default_factory=list,
        description="List of field nullifications, sorted by (id_value, field).",
    )
