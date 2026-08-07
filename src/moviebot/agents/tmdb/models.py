from pydantic import BaseModel, Field


class TrendingQuery(BaseModel):
    """Intención estructurada extraída para el agente TMDB."""

    keywords: list[str] = Field(default_factory=list)
    genres: list[str] = Field(default_factory=list)
    preferred_recency: bool = True
    min_rating: float | None = Field(default=None, ge=0.0, le=10.0)
