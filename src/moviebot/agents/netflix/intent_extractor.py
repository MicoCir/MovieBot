# src/moviebot/agents/netflix/intent_extractor.py
"""Intent extraction: texto de usuario → NetflixQuery estructurada."""

from __future__ import annotations

from typing import Any, Protocol

from openai import AsyncOpenAI

from moviebot.agents.netflix.models import NetflixQuery

_SYSTEM_PROMPT = """\
You are a movie/show search intent extractor for a Netflix catalog. \
Given a user's natural language request, extract a structured query.

Instructions:
- semantic_query: the core search text stripped of explicit filters \
(genres, years, actors, directors, type). Leave empty if the request \
is fully described by filters alone.
- type: "movie", "show", or "any" (default "any").
- genres: list of genres mentioned, normalized to lowercase.
- min_year / max_year: integer year boundaries if mentioned, else null.
- age_certification: list of certifications mentioned (e.g. ["pg-13"]), \
normalized to lowercase. Empty list if none.
- actors: list of actor names mentioned. Always extract the full name \
of actors and directors as they would commonly be known \
(e.g., 'tom hanks' not just 'hanks', 'robert de niro' not just 'de niro'). \
Normalize to lowercase. Return empty list if no actors detected.
- directors: list of director names mentioned. Always extract the full name \
of actors and directors as they would commonly be known \
(e.g., 'steven spielberg' not just 'spielberg', \
'martin scorsese' not just 'scorsese'). \
Normalize to lowercase. Return empty list if no directors detected.

Examples:
- "movies with Tom Hanks" → actors=["tom hanks"], type="movie"
- "directed by Martin Scorsese" → directors=["martin scorsese"]
- "sci-fi shows from the 90s" → genres=["sci-fi"], type="show", \
min_year=1990, max_year=1999
- "something funny" → semantic_query="something funny"
- "Robert De Niro and Al Pacino crime movies" → \
actors=["robert de niro", "al pacino"], genres=["crime"], type="movie"

Return the structured query. If no actors or directors are detected, \
return empty lists for those fields.\
"""


class IntentExtractorProtocol(Protocol):
    """Contrato para extracción de intención de texto a NetflixQuery.

    El componente que implemente este protocolo es responsable de:
    - Extraer semantic_query (texto de búsqueda libre)
    - Identificar type (movie/show/any)
    - Extraer genres mencionados
    - Extraer rangos de año
    - Extraer nombres de actores (normalizados lowercase)
    - Extraer nombres de directores (normalizados lowercase)
    - Extraer age_certification si mencionada

    La implementación concreta puede ser un LLM call, un parser
    basado en reglas, o cualquier otro mecanismo.
    """

    async def extract(self, user_text: str) -> NetflixQuery:
        """Extrae NetflixQuery estructurada desde texto libre del usuario."""
        ...


class LlmIntentExtractor:
    """Implementación concreta usando OpenAI structured output.

    Esta clase usa OpenAI structured output para transformar texto
    de usuario en NetflixQuery, incluyendo extracción de actores y
    directores normalizados a lowercase.
    """

    def __init__(self, openai_client: Any, model: str) -> None:
        """Inicializa el extractor con cliente OpenAI y modelo.

        Args:
            openai_client: Instancia de AsyncOpenAI (o compatible).
            model: Nombre del modelo a usar (e.g., "gpt-4o").
        """
        self._client: AsyncOpenAI = openai_client
        self._model = model

    async def extract(self, user_text: str) -> NetflixQuery:
        """Extrae NetflixQuery usando OpenAI structured output.

        El prompt incluye instrucciones para:
        - Extraer nombres completos de actores mencionados en el texto
        - Extraer nombres completos de directores mencionados en el texto
        - Normalizar nombres a lowercase
        - Retornar listas vacías cuando no se detectan actors/directors

        Args:
            user_text: Texto libre del usuario describiendo lo que busca.

        Returns:
            NetflixQuery con todos los campos extraídos del texto.
        """
        response = await self._client.beta.chat.completions.parse(
            model=self._model,
            messages=[
                {"role": "system", "content": _SYSTEM_PROMPT},
                {"role": "user", "content": user_text},
            ],
            response_format=NetflixQuery,
        )

        parsed = response.choices[0].message.parsed
        if parsed is None:
            # Fallback: return empty query if parsing fails
            return NetflixQuery()

        return parsed
