# src/moviebot/repositories/netflix_meilisearch.py
"""Implementación concreta de NetflixRepository sobre Meilisearch."""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING

import meilisearch

from moviebot.common.models import MovieCandidate

if TYPE_CHECKING:
    from moviebot.agents.netflix.models import NetflixQuery

logger = logging.getLogger(__name__)


class MeilisearchNetflixRepository:
    """Implementación de NetflixRepository sobre Meilisearch.

    Traduce NetflixQuery a búsquedas Meilisearch con filtros estructurados
    y mapea los resultados a MovieCandidate.
    """

    DEFAULT_LIMIT: int = 20

    def __init__(
        self,
        meilisearch_url: str,
        meilisearch_api_key: str | None = None,
        index_name: str = "netflix",
        limit: int = DEFAULT_LIMIT,
    ) -> None:
        """Inicializa el repository con conexión a Meilisearch.

        Args:
            meilisearch_url: URL del servidor Meilisearch.
            meilisearch_api_key: API key para autenticación (opcional).
            index_name: Nombre del índice Meilisearch a consultar.
            limit: Máximo de resultados a retornar por búsqueda.
        """
        self._client = meilisearch.Client(meilisearch_url, meilisearch_api_key)
        self._index_name = index_name
        self._limit = limit

    async def search(self, query: NetflixQuery) -> list[MovieCandidate]:
        """Traduce NetflixQuery a búsqueda Meilisearch y mapea resultados.

        Returns empty list on Meilisearch error (logs warning).
        """
        search_text = query.semantic_query or ""
        filter_expr = self._build_filter(query)

        search_params: dict = {"limit": self._limit}
        if filter_expr:
            search_params["filter"] = filter_expr

        try:
            result = await asyncio.to_thread(
                self._client.index(self._index_name).search,
                search_text,
                search_params,
            )
        except Exception:
            logger.warning(
                "Meilisearch search failed for index '%s'",
                self._index_name,
                exc_info=True,
            )
            return []

        hits = result.get("hits", [])
        return [self._map_hit_to_candidate(hit) for hit in hits]

    def _build_filter(self, query: NetflixQuery) -> str | None:
        """Construye la expresión de filtro Meilisearch.

        Semántica:
        - genres: AND intra-campo (documento debe contener TODOS los géneros)
        - actors: OR intra-campo (al menos uno presente)
        - directors: OR intra-campo (al menos uno presente)
        - actors + directors: AND inter-campo
        - age_certification: OR intra-campo
        - type: "movie"/"show" → filtro exacto, "any" → sin filtro
        - min_year/max_year: filtros de rango sobre release_year

        Todos los valores de filtro se normalizan con value.strip().lower()
        antes de construir las expresiones.
        """
        parts: list[str] = []

        # Type filter
        if query.type in ("movie", "show"):
            parts.append(f'type = "{query.type}"')

        # Genres filter (AND)
        for genre in query.genres:
            normalized = self._escape_filter_value(genre.strip().lower())
            parts.append(f'genres = "{normalized}"')

        # Year range filters
        if query.min_year is not None:
            parts.append(f"release_year >= {query.min_year}")
        if query.max_year is not None:
            parts.append(f"release_year <= {query.max_year}")

        # Age certification filter (OR)
        if query.age_certification:
            cert_clauses = [
                f'age_certification = "{self._escape_filter_value(c.strip().lower())}"'
                for c in query.age_certification
            ]
            if len(cert_clauses) == 1:
                parts.append(cert_clauses[0])
            else:
                parts.append(f"({' OR '.join(cert_clauses)})")

        # Actors filter (OR intra-campo)
        actors_expr: str | None = None
        if query.actors:
            actor_clauses = [
                f'actors = "{self._escape_filter_value(a.strip().lower())}"'
                for a in query.actors
            ]
            if len(actor_clauses) == 1:
                actors_expr = actor_clauses[0]
            else:
                actors_expr = f"({' OR '.join(actor_clauses)})"

        # Directors filter (OR intra-campo)
        directors_expr: str | None = None
        if query.directors:
            director_clauses = [
                f'directors = "{self._escape_filter_value(d.strip().lower())}"'
                for d in query.directors
            ]
            if len(director_clauses) == 1:
                directors_expr = director_clauses[0]
            else:
                directors_expr = f"({' OR '.join(director_clauses)})"

        # Combine actors and directors with AND inter-campo
        if actors_expr and directors_expr:
            parts.append(f"{actors_expr} AND {directors_expr}")
        elif actors_expr:
            parts.append(actors_expr)
        elif directors_expr:
            parts.append(directors_expr)

        if not parts:
            return None

        return " AND ".join(parts)

    @staticmethod
    def _escape_filter_value(value: str) -> str:
        """Escapes a value for use in Meilisearch filter expressions.

        Handles backslashes and double quotes. Meilisearch filter syntax
        uses double quotes for string values — internal double quotes are
        escaped with backslash.
        """
        return value.replace("\\", "\\\\").replace('"', '\\"')

    def _map_hit_to_candidate(self, hit: dict) -> MovieCandidate:
        """Mapea un hit de Meilisearch a MovieCandidate.

        Maps:
        - id: from document id
        - title: from document title
        - description: from document description (or None)
        - release_year: from document release_year
        - genres: from document genres
        - source: "netflix"
        - content_type: from document type field
        - popularity: None
        - vote_average: None
        """
        return MovieCandidate(
            id=hit["id"],
            title=hit["title"],
            description=hit.get("description"),
            release_year=hit.get("release_year"),
            genres=hit.get("genres", []),
            source="netflix",
            content_type=hit["type"],
            popularity=None,
            vote_average=None,
        )


if __name__ == "__main__":
    import argparse
    import json

    from moviebot.agents.netflix.models import NetflixQuery

    parser = argparse.ArgumentParser(
        description="Manual search against Meilisearch Netflix index."
    )
    parser.add_argument("--query", type=str, required=True, help="Semantic query text.")
    parser.add_argument(
        "--index", type=str, required=True, help="Meilisearch index name."
    )
    parser.add_argument(
        "--url",
        type=str,
        default="http://localhost:7700",
        help="Meilisearch server URL (default: http://localhost:7700).",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=20,
        help="Maximum number of results (default: 20).",
    )

    args = parser.parse_args()

    repository = MeilisearchNetflixRepository(
        meilisearch_url=args.url,
        index_name=args.index,
        limit=args.limit,
    )
    netflix_query = NetflixQuery(semantic_query=args.query)
    results = asyncio.run(repository.search(netflix_query))

    output = [candidate.model_dump(mode="json") for candidate in results]
    print(json.dumps(output, indent=2, ensure_ascii=False))
