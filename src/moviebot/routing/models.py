from typing import Literal

from pydantic import BaseModel, Field


class RouteDecision(BaseModel):
    """Decisión del router: qué fuente(s) consultar."""

    route: Literal["trending", "netflix", "both", "out_of_scope"]
    confidence: float = Field(ge=0.0, le=1.0)
    reason: str
