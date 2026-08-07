"""Test de integración live contra la API TMDB.

Requiere la variable de entorno TMDB_API_KEY.
No se ejecuta por defecto — usar: pytest -m integration
"""

from __future__ import annotations

import os

import pytest

pytestmark = pytest.mark.integration


@pytest.fixture()
def _require_tmdb_key() -> None:
    """Skip si TMDB_API_KEY no está en el entorno."""
    if not os.environ.get("TMDB_API_KEY"):
        pytest.skip("TMDB_API_KEY no disponible en variables de entorno")


@pytest.mark.asyncio()
@pytest.mark.usefixtures("_require_tmdb_key")
async def test_fetch_trending_raw_returns_results_list() -> None:
    """Verifica que fetch_trending_raw() retorna un dict con 'results' como lista."""
    from moviebot.common.config import Settings
    from moviebot.repositories.tmdb_connector import TmdbConnector

    settings = Settings()  # type: ignore[call-arg]

    async with TmdbConnector(settings=settings) as connector:
        raw = await connector.fetch_trending_raw()

    assert isinstance(raw, dict)
    assert "results" in raw
    assert isinstance(raw["results"], list)
    assert len(raw["results"]) > 0


@pytest.mark.asyncio()
@pytest.mark.usefixtures("_require_tmdb_key")
async def test_get_trending_returns_valid_movie_candidates() -> None:
    """Verifica que get_trending() retorna al menos un MovieCandidate válido."""
    from moviebot.common.config import Settings
    from moviebot.repositories.tmdb_connector import TmdbConnector

    settings = Settings()  # type: ignore[call-arg]

    async with TmdbConnector(settings=settings) as connector:
        candidates = await connector.get_trending()

    assert len(candidates) >= 1

    # Verificar que al menos el primer candidato tiene campos poblados
    first = candidates[0]
    assert first.id.startswith("tmdb:")
    assert isinstance(first.title, str)
    assert len(first.title) > 0
    assert first.source == "tmdb"
    assert first.content_type == "movie"
    assert isinstance(first.genres, list)
    # popularity y vote_average deberían estar presentes en trending movies
    assert first.popularity is not None
    assert first.vote_average is not None
