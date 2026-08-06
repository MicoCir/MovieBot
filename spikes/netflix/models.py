"""Pydantic models for the Netflix/Kaggle dataset spike."""

from __future__ import annotations

from pydantic import BaseModel

from spikes.common.models import SpikeResult


class ColumnProfile(BaseModel):
    """Profile statistics for a single CSV column."""

    name: str
    inferred_type: str
    null_percentage: float
    unique_count: int
    representative_values: list[str]


class DataProfile(BaseModel):
    """Complete data profile for a CSV dataset."""

    row_count: int
    column_count: int
    columns: list[ColumnProfile]
    duplicate_count: int
    file_size_bytes: int


class NetflixSpikeResult(SpikeResult):
    """Result model specific to the Netflix spike execution."""

    csv_path: str | None = None
    row_count: int | None = None
    column_count: int | None = None
    fingerprint: str | None = None
    sample_path: str | None = None
    license_info: str = ""
