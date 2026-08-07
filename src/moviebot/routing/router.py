# src/moviebot/routing/router.py
from typing import Protocol

from moviebot.routing.models import RouteDecision


class Router(Protocol):
    """Contrato del router de intención."""

    async def route(self, query: str) -> RouteDecision: ...
