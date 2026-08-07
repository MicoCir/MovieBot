# src/moviebot/repositories/protocols.py
from typing import Protocol

from moviebot.agents.netflix.models import NetflixQuery
from moviebot.common.models import MovieCandidate


class TrendingRepository(Protocol):
    """Contrato de acceso al datasource TMDB Trending."""

    async def get_trending(self) -> list[MovieCandidate]: ...


class NetflixRepository(Protocol):
    """Contrato de acceso al datasource Netflix (Meilisearch)."""

    async def search(self, query: NetflixQuery) -> list[MovieCandidate]: ...
