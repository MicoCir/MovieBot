# src/moviebot/common/models.py
from typing import Literal

from pydantic import BaseModel, Field


class MovieCandidate(BaseModel):
    """Candidato de recomendación proveniente de cualquier fuente."""

    id: str
    title: str
    description: str | None = None
    release_year: int | None = None
    genres: list[str] = Field(default_factory=list)
    source: Literal["tmdb", "netflix"]
    content_type: Literal["movie", "show"]  # OBLIGATORIO — sin default
    popularity: float | None = None
    vote_average: float | None = None


class AgentResult(BaseModel):
    """Resultado producido por un agente especializado."""

    candidates: list[MovieCandidate] = Field(default_factory=list)
    query_interpretation: dict
    warnings: list[str] = Field(default_factory=list)
