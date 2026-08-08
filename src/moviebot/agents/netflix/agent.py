# src/moviebot/agents/netflix/agent.py
"""Netflix agent composition point: receives protocols via constructor injection."""

from __future__ import annotations

from moviebot.agents.netflix.intent_extractor import IntentExtractorProtocol
from moviebot.common.models import AgentResult
from moviebot.repositories.protocols import NetflixRepository


class NetflixAgent:
    """Agente Netflix que orquesta extracción de intención y búsqueda.

    Recibe dependencias via constructor injection (protocolos, no clases concretas).
    Provee la interfaz que un grafo LangGraph puede invocar.
    """

    def __init__(
        self,
        intent_extractor: IntentExtractorProtocol,
        repository: NetflixRepository,
    ) -> None:
        """Inicializa el agente con sus dependencias inyectadas.

        Args:
            intent_extractor: Implementación del protocolo de extracción de intención.
            repository: Implementación del protocolo NetflixRepository.
        """
        self._intent_extractor = intent_extractor
        self._repository = repository

    async def search(self, user_text: str) -> AgentResult:
        """Extract intent → search repository → return AgentResult.

        Args:
            user_text: Texto libre del usuario describiendo lo que busca.

        Returns:
            AgentResult con candidatos, interpretación del query, y warnings.
        """
        query = await self._intent_extractor.extract(user_text)
        candidates = await self._repository.search(query)
        return AgentResult(
            candidates=candidates,
            query_interpretation=query.model_dump(),
            warnings=[],
        )
