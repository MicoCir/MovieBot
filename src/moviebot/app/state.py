# src/moviebot/app/state.py
import operator
from typing import Annotated

from pydantic import BaseModel, Field

from moviebot.agents.netflix.models import NetflixQuery
from moviebot.agents.tmdb.models import TrendingQuery
from moviebot.common.errors import Status
from moviebot.common.models import MovieCandidate
from moviebot.routing.models import RouteDecision


class ChatState(BaseModel):
    """Estado del grafo de ejecución LangGraph."""

    user_query: str
    route: RouteDecision | None = None
    trending_query: TrendingQuery | None = None
    netflix_query: NetflixQuery | None = None
    tmdb_candidates: list[MovieCandidate] = Field(default_factory=list)
    netflix_candidates: list[MovieCandidate] = Field(default_factory=list)
    warnings: Annotated[list[str], operator.add] = Field(default_factory=list)
    status: Status | None = None
