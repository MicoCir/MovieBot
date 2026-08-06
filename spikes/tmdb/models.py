"""Pydantic models for the TMDB viability spike."""

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel

from spikes.common.models import SpikeResult


class TmdbMovie(BaseModel):
    """Model representing a single movie from the TMDB trending endpoint."""

    id: int
    title: str
    original_title: str
    overview: str
    release_date: str
    genre_ids: list[int]
    popularity: float
    vote_average: float
    vote_count: int
    poster_path: str | None = None
    backdrop_path: str | None = None
    adult: bool
    original_language: str
    media_type: Literal["movie"]
    video: bool


class TmdbTrendingResponse(BaseModel):
    """Model representing the full response from TMDB trending endpoint."""

    page: int
    results: list[TmdbMovie]
    total_pages: int
    total_results: int


class FieldEntry(BaseModel):
    """A single entry in the field inventory documenting a JSON field."""

    name: str
    observed_type: str
    example_value: Any
    path: str  # JSON path e.g. "results[0].title"


class TmdbSpikeResult(SpikeResult):
    """Extended spike result with TMDB-specific metadata."""

    endpoint_used: str = ""
    response_code: int | None = None
    field_count: int = 0
    snapshot_path: str | None = None
