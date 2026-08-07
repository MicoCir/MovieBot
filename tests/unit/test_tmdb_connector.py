"""Tests unitarios para TmdbConnector.

Valida: Requisitos 1.1, 1.3, 1.15, 1.22, 3.1–3.9
"""

from __future__ import annotations

import httpx
import pytest
from pydantic import SecretStr

from moviebot.common.models import MovieCandidate
from moviebot.repositories.tmdb_connector import TmdbConnector
from moviebot.repositories.tmdb_errors import (
    TmdbConnectionError,
    TmdbHttpError,
    TmdbInvalidResponseError,
    TmdbTimeoutError,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_settings() -> FakeSettings:
    """Crea un Settings fake con tmdb_api_key para tests."""
    return FakeSettings(tmdb_api_key=SecretStr("test-api-key-12345"))


class FakeSettings:
    """Minimal Settings stub for tests."""

    def __init__(self, tmdb_api_key: SecretStr) -> None:
        self.tmdb_api_key = tmdb_api_key


def _valid_tmdb_response(results: list | None = None) -> dict:
    """Genera una respuesta TMDB válida con results por defecto."""
    if results is None:
        results = [
            {
                "id": 123456,
                "title": "Test Movie",
                "overview": "A great movie",
                "release_date": "2024-05-15",
                "genre_ids": [28, 12],
                "popularity": 345.67,
                "vote_average": 7.2,
            }
        ]
    return {
        "page": 1,
        "results": results,
        "total_pages": 1,
        "total_results": len(results),
    }


def _make_transport(
    handler: httpx.MockTransport | None = None,
    status_code: int = 200,
    json_body: dict | list | None = None,
    text_body: str | None = None,
) -> httpx.MockTransport:
    """Crea un MockTransport con respuesta configurable."""
    if handler is not None:
        return handler

    def _handler(request: httpx.Request) -> httpx.Response:
        if text_body is not None:
            return httpx.Response(status_code=status_code, text=text_body)
        body = json_body if json_body is not None else _valid_tmdb_response()
        return httpx.Response(status_code=status_code, json=body)

    return httpx.MockTransport(_handler)


def _make_connector(
    transport: httpx.MockTransport | None = None,
    status_code: int = 200,
    json_body: dict | list | None = None,
    text_body: str | None = None,
) -> TmdbConnector:
    """Crea un TmdbConnector con un client mockeado."""
    t = transport or _make_transport(
        status_code=status_code, json_body=json_body, text_body=text_body
    )
    client = httpx.AsyncClient(transport=t)
    return TmdbConnector(settings=_make_settings(), client=client)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# Test: HTTP 200 con results válidos → lista no vacía de MovieCandidate
# ---------------------------------------------------------------------------


class TestHttp200ValidResults:
    async def test_get_trending_returns_non_empty_list(self) -> None:
        connector = _make_connector()
        result = await connector.get_trending()

        assert len(result) > 0
        assert all(isinstance(c, MovieCandidate) for c in result)

    async def test_fetch_trending_raw_returns_dict_with_results(self) -> None:
        connector = _make_connector()
        result = await connector.fetch_trending_raw()

        assert isinstance(result, dict)
        assert "results" in result
        assert isinstance(result["results"], list)


# ---------------------------------------------------------------------------
# Test: HTTP 401/404/500 → TmdbHttpError con campos correctos
# ---------------------------------------------------------------------------


class TestHttpErrors:
    @pytest.mark.parametrize("status_code", [401, 404, 500])
    async def test_http_error_raises_tmdb_http_error(self, status_code: int) -> None:
        connector = _make_connector(
            status_code=status_code,
            json_body={"status_message": "Error", "status_code": status_code},
        )

        with pytest.raises(TmdbHttpError) as exc_info:
            await connector.fetch_trending_raw()

        err = exc_info.value
        assert err.status_code == status_code
        assert err.operation == "fetch_trending_raw"
        assert isinstance(err.message, str)
        assert isinstance(err.response_body, str)

    async def test_http_error_response_body_is_string(self) -> None:
        connector = _make_connector(
            status_code=500, json_body={"error": "Internal Server Error"}
        )

        with pytest.raises(TmdbHttpError) as exc_info:
            await connector.fetch_trending_raw()

        assert isinstance(exc_info.value.response_body, str)


# ---------------------------------------------------------------------------
# Test: asyncio.TimeoutError → TmdbTimeoutError
# ---------------------------------------------------------------------------


class TestAsyncioTimeout:
    async def test_asyncio_timeout_raises_tmdb_timeout_error(self) -> None:
        """Simula un TimeoutError que asyncio.timeout lanzaría."""

        def _handler(request: httpx.Request) -> httpx.Response:
            raise TimeoutError("asyncio timeout triggered")

        transport = httpx.MockTransport(_handler)
        client = httpx.AsyncClient(transport=transport)
        connector = TmdbConnector(settings=_make_settings(), client=client)  # type: ignore[arg-type]

        with pytest.raises(TmdbTimeoutError) as exc_info:
            await connector.fetch_trending_raw()

        assert exc_info.value.operation == "fetch_trending_raw"


# ---------------------------------------------------------------------------
# Test: httpx.TimeoutException → TmdbTimeoutError
# ---------------------------------------------------------------------------


class TestHttpxTimeout:
    async def test_httpx_timeout_raises_tmdb_timeout_error(self) -> None:
        def _handler(request: httpx.Request) -> httpx.Response:
            raise httpx.ReadTimeout("Read timed out")

        transport = httpx.MockTransport(_handler)
        client = httpx.AsyncClient(transport=transport)
        connector = TmdbConnector(settings=_make_settings(), client=client)  # type: ignore[arg-type]

        with pytest.raises(TmdbTimeoutError) as exc_info:
            await connector.fetch_trending_raw()

        assert exc_info.value.operation == "fetch_trending_raw"


# ---------------------------------------------------------------------------
# Test: JSON no parseable → TmdbInvalidResponseError
# ---------------------------------------------------------------------------


class TestJsonParseError:
    async def test_non_json_response_raises_invalid_response(self) -> None:
        connector = _make_connector(status_code=200, text_body="not valid json {{{{")

        with pytest.raises(TmdbInvalidResponseError) as exc_info:
            await connector.fetch_trending_raw()

        assert exc_info.value.operation == "fetch_trending_raw"
        assert "JSON" in exc_info.value.message or "parseable" in exc_info.value.message


# ---------------------------------------------------------------------------
# Test: httpx.ConnectError / httpx.NetworkError → TmdbConnectionError
# ---------------------------------------------------------------------------


class TestConnectionErrors:
    async def test_connect_error_raises_tmdb_connection_error(self) -> None:
        def _handler(request: httpx.Request) -> httpx.Response:
            raise httpx.ConnectError("Connection refused")

        transport = httpx.MockTransport(_handler)
        client = httpx.AsyncClient(transport=transport)
        connector = TmdbConnector(settings=_make_settings(), client=client)  # type: ignore[arg-type]

        with pytest.raises(TmdbConnectionError) as exc_info:
            await connector.fetch_trending_raw()

        assert exc_info.value.operation == "fetch_trending_raw"

    async def test_network_error_raises_tmdb_connection_error(self) -> None:
        def _handler(request: httpx.Request) -> httpx.Response:
            raise httpx.NetworkError("Network unreachable")

        transport = httpx.MockTransport(_handler)
        client = httpx.AsyncClient(transport=transport)
        connector = TmdbConnector(settings=_make_settings(), client=client)  # type: ignore[arg-type]

        with pytest.raises(TmdbConnectionError) as exc_info:
            await connector.fetch_trending_raw()

        assert exc_info.value.operation == "fetch_trending_raw"


# ---------------------------------------------------------------------------
# Test: results vacío → lista vacía sin error
# ---------------------------------------------------------------------------


class TestEmptyResults:
    async def test_empty_results_returns_empty_list(self) -> None:
        connector = _make_connector(json_body=_valid_tmdb_response(results=[]))
        result = await connector.get_trending()

        assert result == []

    async def test_empty_results_does_not_raise(self) -> None:
        connector = _make_connector(json_body=_valid_tmdb_response(results=[]))
        # Should not raise
        raw = await connector.fetch_trending_raw()
        assert raw["results"] == []


# ---------------------------------------------------------------------------
# Test: results no es lista → TmdbInvalidResponseError
# ---------------------------------------------------------------------------


class TestResultsNotList:
    @pytest.mark.parametrize(
        "body",
        [
            {"page": 1, "results": "not a list"},
            {"page": 1, "results": 42},
            {"page": 1, "results": {"nested": "dict"}},
            {"page": 1},  # results ausente
        ],
    )
    async def test_invalid_results_raises_invalid_response(self, body: dict) -> None:
        connector = _make_connector(json_body=body)

        with pytest.raises(TmdbInvalidResponseError) as exc_info:
            await connector.fetch_trending_raw()

        assert exc_info.value.operation == "fetch_trending_raw"


# ---------------------------------------------------------------------------
# Test: elemento sin id o sin title → omitido silenciosamente
# ---------------------------------------------------------------------------


class TestInvalidElements:
    async def test_element_without_id_is_skipped(self) -> None:
        results = [
            {"title": "No ID Movie", "overview": "desc"},
            {"id": 999, "title": "Valid Movie"},
        ]
        connector = _make_connector(json_body=_valid_tmdb_response(results=results))
        candidates = await connector.get_trending()

        assert len(candidates) == 1
        assert candidates[0].title == "Valid Movie"

    async def test_element_without_title_is_skipped(self) -> None:
        results = [
            {"id": 111, "overview": "No title"},
            {"id": 222, "title": "Has Title"},
        ]
        connector = _make_connector(json_body=_valid_tmdb_response(results=results))
        candidates = await connector.get_trending()

        assert len(candidates) == 1
        assert candidates[0].title == "Has Title"

    async def test_element_with_non_int_id_is_skipped(self) -> None:
        results = [
            {"id": "abc", "title": "String ID"},
            {"id": 333, "title": "Valid"},
        ]
        connector = _make_connector(json_body=_valid_tmdb_response(results=results))
        candidates = await connector.get_trending()

        assert len(candidates) == 1
        assert candidates[0].id == "tmdb:333"

    async def test_element_with_non_str_title_is_skipped(self) -> None:
        results = [
            {"id": 444, "title": 12345},
            {"id": 555, "title": "Real Title"},
        ]
        connector = _make_connector(json_body=_valid_tmdb_response(results=results))
        candidates = await connector.get_trending()

        assert len(candidates) == 1
        assert candidates[0].title == "Real Title"

    async def test_non_dict_elements_are_skipped(self) -> None:
        results = [
            "a string",
            42,
            None,
            {"id": 666, "title": "OK"},
        ]
        connector = _make_connector(json_body=_valid_tmdb_response(results=results))
        candidates = await connector.get_trending()

        assert len(candidates) == 1
        assert candidates[0].id == "tmdb:666"


# ---------------------------------------------------------------------------
# Test: campos opcionales ausentes/null → None en MovieCandidate
# ---------------------------------------------------------------------------


class TestOptionalFieldsNone:
    async def test_all_optional_fields_absent(self) -> None:
        results = [{"id": 100, "title": "Minimal Movie"}]
        connector = _make_connector(json_body=_valid_tmdb_response(results=results))
        candidates = await connector.get_trending()

        assert len(candidates) == 1
        c = candidates[0]
        assert c.description is None
        assert c.release_year is None
        assert c.popularity is None
        assert c.vote_average is None

    async def test_optional_fields_explicitly_null(self) -> None:
        results = [
            {
                "id": 200,
                "title": "Null Fields Movie",
                "overview": None,
                "release_date": None,
                "genre_ids": None,
                "popularity": None,
                "vote_average": None,
            }
        ]
        connector = _make_connector(json_body=_valid_tmdb_response(results=results))
        candidates = await connector.get_trending()

        assert len(candidates) == 1
        c = candidates[0]
        assert c.description is None
        assert c.release_year is None
        assert c.popularity is None
        assert c.vote_average is None


# ---------------------------------------------------------------------------
# Test: release_date vacío o ausente → release_year = None
# ---------------------------------------------------------------------------


class TestReleaseDateEdgeCases:
    async def test_empty_release_date_gives_none_year(self) -> None:
        results = [{"id": 300, "title": "Movie", "release_date": ""}]
        connector = _make_connector(json_body=_valid_tmdb_response(results=results))
        candidates = await connector.get_trending()

        assert candidates[0].release_year is None

    async def test_absent_release_date_gives_none_year(self) -> None:
        results = [{"id": 301, "title": "Movie"}]
        connector = _make_connector(json_body=_valid_tmdb_response(results=results))
        candidates = await connector.get_trending()

        assert candidates[0].release_year is None

    async def test_null_release_date_gives_none_year(self) -> None:
        results = [{"id": 302, "title": "Movie", "release_date": None}]
        connector = _make_connector(json_body=_valid_tmdb_response(results=results))
        candidates = await connector.get_trending()

        assert candidates[0].release_year is None

    async def test_valid_release_date_extracts_year(self) -> None:
        results = [{"id": 303, "title": "Movie", "release_date": "2023-11-20"}]
        connector = _make_connector(json_body=_valid_tmdb_response(results=results))
        candidates = await connector.get_trending()

        assert candidates[0].release_year == 2023


# ---------------------------------------------------------------------------
# Test: genre_ids null → genres = []
# ---------------------------------------------------------------------------


class TestGenreIdsNull:
    async def test_null_genre_ids_gives_empty_list(self) -> None:
        results = [{"id": 400, "title": "Movie", "genre_ids": None}]
        connector = _make_connector(json_body=_valid_tmdb_response(results=results))
        candidates = await connector.get_trending()

        assert candidates[0].genres == []

    async def test_absent_genre_ids_gives_empty_list(self) -> None:
        results = [{"id": 401, "title": "Movie"}]
        connector = _make_connector(json_body=_valid_tmdb_response(results=results))
        candidates = await connector.get_trending()

        assert candidates[0].genres == []

    async def test_valid_genre_ids_converts_to_strings(self) -> None:
        results = [{"id": 402, "title": "Movie", "genre_ids": [28, 12, 35]}]
        connector = _make_connector(json_body=_valid_tmdb_response(results=results))
        candidates = await connector.get_trending()

        assert candidates[0].genres == ["28", "12", "35"]


# ---------------------------------------------------------------------------
# Test: verificar contrato HTTP usando httpx.MockTransport
# ---------------------------------------------------------------------------


class TestHttpContract:
    """Verifica el contrato HTTP: método, URL, parámetros, redacción de secretos."""

    async def test_request_method_is_get(self) -> None:
        captured_request: list[httpx.Request] = []

        def _handler(request: httpx.Request) -> httpx.Response:
            captured_request.append(request)
            return httpx.Response(200, json=_valid_tmdb_response())

        transport = httpx.MockTransport(_handler)
        connector = _make_connector(transport=transport)
        await connector.fetch_trending_raw()

        assert captured_request[0].method == "GET"

    async def test_request_url_is_correct_endpoint(self) -> None:
        captured_request: list[httpx.Request] = []

        def _handler(request: httpx.Request) -> httpx.Response:
            captured_request.append(request)
            return httpx.Response(200, json=_valid_tmdb_response())

        transport = httpx.MockTransport(_handler)
        connector = _make_connector(transport=transport)
        await connector.fetch_trending_raw()

        url = captured_request[0].url
        # Verify base URL without query params
        assert str(url).startswith("https://api.themoviedb.org/3/trending/movie/week")

    async def test_api_key_is_present_in_query_params(self) -> None:
        captured_request: list[httpx.Request] = []

        def _handler(request: httpx.Request) -> httpx.Response:
            captured_request.append(request)
            return httpx.Response(200, json=_valid_tmdb_response())

        transport = httpx.MockTransport(_handler)
        connector = _make_connector(transport=transport)
        await connector.fetch_trending_raw()

        url = captured_request[0].url
        assert url.params.get("api_key") == "test-api-key-12345"

    async def test_api_key_not_in_error_messages(self) -> None:
        """La API key NO aparece en mensajes de error."""
        error_body = "Error: invalid key test-api-key-12345 provided"
        connector = _make_connector(status_code=401, text_body=error_body)

        with pytest.raises(TmdbHttpError) as exc_info:
            await connector.fetch_trending_raw()

        err = exc_info.value
        assert "test-api-key-12345" not in err.response_body
        assert "test-api-key-12345" not in err.message

    async def test_response_body_truncated_to_500_chars(self) -> None:
        """El response_body en TmdbHttpError está truncado a 500 chars."""
        long_body = "x" * 1000
        connector = _make_connector(status_code=500, text_body=long_body)

        with pytest.raises(TmdbHttpError) as exc_info:
            await connector.fetch_trending_raw()

        assert len(exc_info.value.response_body) <= 500

    async def test_secrets_redacted_before_truncation(self) -> None:
        """Los secretos se redactan ANTES de truncar.

        Si el secreto aparece al inicio de un body largo, debe ser redactado
        y el resultado truncado a 500 chars. El secreto no debe estar presente
        en ningún caso.
        """
        # Secreto al inicio seguido de relleno
        api_key = "test-api-key-12345"
        body = api_key + "A" * 600
        connector = _make_connector(status_code=500, text_body=body)

        with pytest.raises(TmdbHttpError) as exc_info:
            await connector.fetch_trending_raw()

        err = exc_info.value
        assert api_key not in err.response_body
        assert "[REDACTED]" in err.response_body
        assert len(err.response_body) <= 500


# ---------------------------------------------------------------------------
# Test: MovieCandidate field mapping correctness
# ---------------------------------------------------------------------------


class TestFieldMapping:
    """Verifica el mapeo correcto de campos TMDB → MovieCandidate."""

    async def test_id_has_tmdb_prefix(self) -> None:
        results = [{"id": 789, "title": "Movie"}]
        connector = _make_connector(json_body=_valid_tmdb_response(results=results))
        candidates = await connector.get_trending()

        assert candidates[0].id == "tmdb:789"

    async def test_source_is_tmdb(self) -> None:
        results = [{"id": 1, "title": "Movie"}]
        connector = _make_connector(json_body=_valid_tmdb_response(results=results))
        candidates = await connector.get_trending()

        assert candidates[0].source == "tmdb"

    async def test_content_type_is_movie(self) -> None:
        results = [{"id": 1, "title": "Movie"}]
        connector = _make_connector(json_body=_valid_tmdb_response(results=results))
        candidates = await connector.get_trending()

        assert candidates[0].content_type == "movie"

    async def test_full_mapping(self) -> None:
        results = [
            {
                "id": 42,
                "title": "The Answer",
                "overview": "About everything",
                "release_date": "2001-06-15",
                "genre_ids": [18, 53],
                "popularity": 99.9,
                "vote_average": 8.5,
            }
        ]
        connector = _make_connector(json_body=_valid_tmdb_response(results=results))
        candidates = await connector.get_trending()

        c = candidates[0]
        assert c.id == "tmdb:42"
        assert c.title == "The Answer"
        assert c.description == "About everything"
        assert c.release_year == 2001
        assert c.genres == ["18", "53"]
        assert c.source == "tmdb"
        assert c.content_type == "movie"
        assert c.popularity == 99.9
        assert c.vote_average == 8.5
