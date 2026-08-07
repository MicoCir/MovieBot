"""Conector HTTP mínimo contra TMDB Trending Movies."""

from __future__ import annotations

import asyncio
import hashlib
import json
import types
from datetime import UTC, datetime
from typing import Any, Self

import httpx

from moviebot.common.config import Settings
from moviebot.common.models import MovieCandidate
from moviebot.repositories.fixture_writer import FixtureWriter, LocalFixtureWriter
from moviebot.repositories.tmdb_errors import (
    TmdbConnectionError,
    TmdbHttpError,
    TmdbInvalidResponseError,
    TmdbTimeoutError,
)
from moviebot.repositories.tmdb_models import FixturePaths

_TRENDING_ENDPOINT = "https://api.themoviedb.org/3/trending/movie/week"
_TIMEOUT_SECONDS = 10
_MAX_BODY_LENGTH = 500


def _redact_secrets(text: str, secrets: list[str]) -> str:
    """Redacta secretos en un texto antes de truncar."""
    for secret in secrets:
        if secret:
            text = text.replace(secret, "[REDACTED]")
    return text


def _extract_year(release_date: Any) -> int | None:
    """Extrae el año de un string de fecha como '2024-01-15'."""
    if not isinstance(release_date, str) or not release_date:
        return None
    try:
        return int(release_date[:4])
    except (ValueError, IndexError):
        return None


class TmdbConnector:
    """Conector HTTP mínimo contra TMDB Trending Movies.

    Implementa el protocolo TrendingRepository por duck typing.
    """

    def __init__(
        self,
        settings: Settings,
        client: httpx.AsyncClient | None = None,
        fixture_writer: FixtureWriter | None = None,
    ) -> None:
        self._settings = settings
        self._owns_client = client is None
        self._client = client or httpx.AsyncClient()
        self._fixture_writer: FixtureWriter = fixture_writer or LocalFixtureWriter()

    async def fetch_trending_raw(self) -> dict[str, Any]:
        """Llama a TMDB y retorna la respuesta JSON cruda validada.

        Envuelve la operación con asyncio.timeout(10) para garantizar
        un deadline estricto de wall-clock de 10 segundos.
        """
        api_key = self._settings.tmdb_api_key.get_secret_value()
        secrets = [api_key]

        try:
            async with asyncio.timeout(_TIMEOUT_SECONDS):
                response = await self._client.get(
                    _TRENDING_ENDPOINT,
                    params={"api_key": api_key},
                )
        except (TimeoutError, httpx.TimeoutException) as exc:
            raise TmdbTimeoutError(
                message="Timeout al conectar con TMDB (límite: 10s)",
                operation="fetch_trending_raw",
            ) from exc
        except (httpx.ConnectError, httpx.NetworkError) as exc:
            raise TmdbConnectionError(
                message=f"Fallo de conexión/red con TMDB: {exc}",
                operation="fetch_trending_raw",
            ) from exc

        if response.status_code >= 400:
            body = response.text
            body = _redact_secrets(body, secrets)
            body = body[:_MAX_BODY_LENGTH]
            raise TmdbHttpError(
                message=f"Error HTTP {response.status_code} de TMDB",
                operation="fetch_trending_raw",
                status_code=response.status_code,
                response_body=body,
            )

        try:
            data: Any = response.json()
        except (json.JSONDecodeError, ValueError) as exc:
            raise TmdbInvalidResponseError(
                message="Respuesta de TMDB no es JSON válido",
                operation="fetch_trending_raw",
            ) from exc

        if not isinstance(data, dict):
            raise TmdbInvalidResponseError(
                message="Respuesta de TMDB no es un objeto JSON",
                operation="fetch_trending_raw",
            )

        results = data.get("results")
        if not isinstance(results, list):
            raise TmdbInvalidResponseError(
                message="Campo 'results' ausente o no es una lista",
                operation="fetch_trending_raw",
            )

        return data  # type: ignore[no-any-return]

    async def get_trending(self) -> list[MovieCandidate]:
        """Implementa TrendingRepository: mapea results → MovieCandidate."""
        raw = await self.fetch_trending_raw()
        results: list[Any] = raw["results"]
        candidates: list[MovieCandidate] = []

        for item in results:
            if not isinstance(item, dict):
                continue

            item_id = item.get("id")
            title = item.get("title")

            # Campos obligatorios: id debe ser int, title debe ser str
            if not isinstance(item_id, int) or not isinstance(title, str):
                continue

            # Campos opcionales
            overview = item.get("overview")
            description = overview if isinstance(overview, str) else None

            release_year = _extract_year(item.get("release_date"))

            genre_ids = item.get("genre_ids")
            if isinstance(genre_ids, list):
                genres = [str(gid) for gid in genre_ids]
            else:
                genres = []

            popularity_raw = item.get("popularity")
            popularity = (
                float(popularity_raw)
                if isinstance(popularity_raw, (int, float))
                else None
            )

            vote_raw = item.get("vote_average")
            vote_average = (
                float(vote_raw) if isinstance(vote_raw, (int, float)) else None
            )

            candidates.append(
                MovieCandidate(
                    id=f"tmdb:{item_id}",
                    title=title,
                    description=description,
                    release_year=release_year,
                    genres=genres,
                    source="tmdb",
                    content_type="movie",
                    popularity=popularity,
                    vote_average=vote_average,
                )
            )

        return candidates

    async def capture_fixture(self, version: str) -> FixturePaths:
        """Captura fixture inmutable delegando a FixtureWriter.

        Serializa el payload, calcula SHA-256, construye metadata,
        y delega la escritura al FixtureWriter configurado.
        """
        raw_dict = await self.fetch_trending_raw()

        # Serializar payload
        payload_bytes = json.dumps(raw_dict, ensure_ascii=False, indent=2).encode(
            "utf-8"
        )

        # Calcular checksum SHA-256 sobre los bytes exactos
        checksum = hashlib.sha256(payload_bytes).hexdigest()

        # Construir metadata (solo parámetros no sensibles enviados realmente)
        metadata_dict: dict[str, Any] = {
            "version": version,
            "endpoint": _TRENDING_ENDPOINT,
            "captured_at": datetime.now(UTC).isoformat(),
            "parameters": {},
            "checksum_sha256": checksum,
        }

        metadata_bytes = json.dumps(metadata_dict, ensure_ascii=False, indent=2).encode(
            "utf-8"
        )

        return self._fixture_writer.write_fixture(
            version, payload_bytes, metadata_bytes
        )

    async def close(self) -> None:
        """Cierra el cliente HTTP interno si fue creado por el connector."""
        if self._owns_client:
            await self._client.aclose()

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: types.TracebackType | None,
    ) -> None:
        await self.close()
