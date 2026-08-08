# src/moviebot/agents/netflix/models.py
from typing import Literal, Self

from pydantic import BaseModel, Field, model_validator


class NetflixQuery(BaseModel):
    """Intención estructurada extraída para el agente Netflix."""

    semantic_query: str = ""
    type: Literal["movie", "show", "any"] = "any"
    genres: list[str] = Field(default_factory=list)
    min_year: int | None = None
    max_year: int | None = None
    age_certification: list[str] = Field(default_factory=list)
    actors: list[str] = Field(default_factory=list)
    directors: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_year_range(self) -> Self:
        """Garantiza min_year <= max_year cuando ambos están presentes."""
        if (
            self.min_year is not None
            and self.max_year is not None
            and self.min_year > self.max_year
        ):
            raise ValueError(
                f"min_year ({self.min_year}) no puede ser mayor que "
                f"max_year ({self.max_year})"
            )
        return self
