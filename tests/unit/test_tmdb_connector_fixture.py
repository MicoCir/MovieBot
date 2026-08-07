"""Tests unitarios para captura de fixture via TmdbConnector.

Valida: Requisitos 3.10, 3.13, 3.14
"""

import hashlib
import json

import httpx

from moviebot.common.config import Settings
from moviebot.repositories.fixture_writer import InMemoryFixtureWriter
from moviebot.repositories.tmdb_connector import TmdbConnector
from moviebot.repositories.tmdb_models import ProvenanceMetadata

# --- Helpers ---

_FAKE_API_KEY = "super-secret-key-12345"

_VALID_TMDB_RESPONSE = {
    "page": 1,
    "results": [
        {
            "id": 123456,
            "title": "Example Movie",
            "overview": "A great movie",
            "release_date": "2024-01-15",
            "genre_ids": [28, 12],
            "popularity": 345.67,
            "vote_average": 7.2,
        }
    ],
    "total_pages": 1,
    "total_results": 1,
}


def _make_settings() -> Settings:
    """Crea Settings con API key de prueba."""
    return Settings(
        openai_api_key="fake-openai-key",
        openai_model="gpt-4",
        tmdb_api_key=_FAKE_API_KEY,
    )


def _mock_transport() -> httpx.MockTransport:
    """Transport que retorna una respuesta TMDB válida."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            status_code=200,
            json=_VALID_TMDB_RESPONSE,
        )

    return httpx.MockTransport(handler)


# --- Test: captura exitosa genera Payload_File y Metadata_File con checksum SHA-256 correcto (Req 3.13) ---


class TestCaptureFixtureChecksumIntegrity:
    """Verificar que el checksum SHA-256 en metadata corresponde al payload."""

    async def test_checksum_matches_payload_bytes(self) -> None:
        """El checksum almacenado en metadata es el SHA-256 real del payload."""
        settings = _make_settings()
        writer = InMemoryFixtureWriter()
        client = httpx.AsyncClient(transport=_mock_transport())

        connector = TmdbConnector(
            settings=settings, client=client, fixture_writer=writer
        )

        await connector.capture_fixture("v1")

        # Extraer payload y metadata del writer
        assert "v1" in writer.fixtures
        payload_bytes, metadata_bytes = writer.fixtures["v1"]

        # Deserializar metadata
        metadata_dict = json.loads(metadata_bytes)

        # Calcular checksum esperado
        expected_checksum = hashlib.sha256(payload_bytes).hexdigest()

        # Verificar que el checksum en metadata coincide
        assert metadata_dict["checksum_sha256"] == expected_checksum

    async def test_payload_is_valid_json_matching_response(self) -> None:
        """El payload serializado es JSON válido y semánticamente equivalente a la respuesta."""
        settings = _make_settings()
        writer = InMemoryFixtureWriter()
        client = httpx.AsyncClient(transport=_mock_transport())

        connector = TmdbConnector(
            settings=settings, client=client, fixture_writer=writer
        )

        await connector.capture_fixture("v1")

        payload_bytes, _ = writer.fixtures["v1"]
        payload_dict = json.loads(payload_bytes)

        # Verificar equivalencia semántica con la respuesta original
        assert payload_dict == _VALID_TMDB_RESPONSE


# --- Test: Metadata_File no contiene API key ni secretos (Req 3.10) ---


class TestMetadataExcludesSecrets:
    """Verificar que la metadata no contiene la API key ni secretos."""

    async def test_api_key_not_in_metadata_bytes(self) -> None:
        """El valor de la API key no aparece en ningún lugar de los bytes de metadata."""
        settings = _make_settings()
        writer = InMemoryFixtureWriter()
        client = httpx.AsyncClient(transport=_mock_transport())

        connector = TmdbConnector(
            settings=settings, client=client, fixture_writer=writer
        )

        await connector.capture_fixture("v1")

        _, metadata_bytes = writer.fixtures["v1"]

        # La API key en texto plano NO debe aparecer en metadata
        assert _FAKE_API_KEY.encode("utf-8") not in metadata_bytes

    async def test_api_key_not_in_metadata_string(self) -> None:
        """Verificación adicional: la API key no está en la representación string."""
        settings = _make_settings()
        writer = InMemoryFixtureWriter()
        client = httpx.AsyncClient(transport=_mock_transport())

        connector = TmdbConnector(
            settings=settings, client=client, fixture_writer=writer
        )

        await connector.capture_fixture("v1")

        _, metadata_bytes = writer.fixtures["v1"]
        metadata_str = metadata_bytes.decode("utf-8")

        assert _FAKE_API_KEY not in metadata_str

    async def test_parameters_only_contain_non_sensitive_data(self) -> None:
        """Los parameters en metadata solo contienen datos no sensibles (language)."""
        settings = _make_settings()
        writer = InMemoryFixtureWriter()
        client = httpx.AsyncClient(transport=_mock_transport())

        connector = TmdbConnector(
            settings=settings, client=client, fixture_writer=writer
        )

        await connector.capture_fixture("v1")

        _, metadata_bytes = writer.fixtures["v1"]
        metadata_dict = json.loads(metadata_bytes)

        # Parameters solo debe contener datos no sensibles, no api_key
        assert "api_key" not in metadata_dict["parameters"]
        assert metadata_dict["parameters"] == {}


# --- Test: Metadata_File contiene todos los campos obligatorios de ProvenanceMetadata (Req 3.14) ---


class TestMetadataContainsAllRequiredFields:
    """Verificar que el metadata tiene todos los campos de ProvenanceMetadata."""

    async def test_metadata_has_all_provenance_fields(self) -> None:
        """El metadata contiene version, endpoint, captured_at, parameters, checksum_sha256."""
        settings = _make_settings()
        writer = InMemoryFixtureWriter()
        client = httpx.AsyncClient(transport=_mock_transport())

        connector = TmdbConnector(
            settings=settings, client=client, fixture_writer=writer
        )

        await connector.capture_fixture("v1")

        _, metadata_bytes = writer.fixtures["v1"]
        metadata_dict = json.loads(metadata_bytes)

        # Verificar que todos los campos obligatorios están presentes
        required_fields = {
            "version",
            "endpoint",
            "captured_at",
            "parameters",
            "checksum_sha256",
        }
        assert required_fields.issubset(metadata_dict.keys()), (
            f"Campos faltantes: {required_fields - metadata_dict.keys()}"
        )

    async def test_metadata_validates_as_provenance_metadata(self) -> None:
        """El metadata puede ser validado como ProvenanceMetadata sin errores."""
        settings = _make_settings()
        writer = InMemoryFixtureWriter()
        client = httpx.AsyncClient(transport=_mock_transport())

        connector = TmdbConnector(
            settings=settings, client=client, fixture_writer=writer
        )

        await connector.capture_fixture("v1")

        _, metadata_bytes = writer.fixtures["v1"]
        metadata_dict = json.loads(metadata_bytes)

        # Debe validar exitosamente como ProvenanceMetadata
        provenance = ProvenanceMetadata(**metadata_dict)

        assert provenance.version == "v1"
        assert provenance.endpoint == "https://api.themoviedb.org/3/trending/movie/week"
        assert provenance.parameters == {}
        assert len(provenance.checksum_sha256) == 64

    async def test_captured_at_is_utc_iso8601(self) -> None:
        """El campo captured_at es un timestamp ISO 8601 UTC válido."""
        settings = _make_settings()
        writer = InMemoryFixtureWriter()
        client = httpx.AsyncClient(transport=_mock_transport())

        connector = TmdbConnector(
            settings=settings, client=client, fixture_writer=writer
        )

        await connector.capture_fixture("v1")

        _, metadata_bytes = writer.fixtures["v1"]
        metadata_dict = json.loads(metadata_bytes)

        # ProvenanceMetadata valida que captured_at sea ISO 8601 UTC
        # Si no fuera UTC, esta validación lanzaría
        provenance = ProvenanceMetadata(**metadata_dict)
        assert provenance.captured_at  # no vacío


# --- Test: metadata parameters match actual HTTP request parameters ---


class TestMetadataParametersMatchRequest:
    """Verificar que los parámetros declarados en metadata coinciden con los enviados."""

    async def test_metadata_parameters_match_sent_query_params(self) -> None:
        """Los parameters en metadata deben reflejar exactamente los query params
        no sensibles enviados en la petición HTTP real."""
        captured_request: list[httpx.Request] = []

        def _handler(request: httpx.Request) -> httpx.Response:
            captured_request.append(request)
            return httpx.Response(status_code=200, json=_VALID_TMDB_RESPONSE)

        transport = httpx.MockTransport(_handler)
        settings = _make_settings()
        writer = InMemoryFixtureWriter()
        client = httpx.AsyncClient(transport=transport)

        connector = TmdbConnector(
            settings=settings, client=client, fixture_writer=writer
        )

        await connector.capture_fixture("v1")

        # Extract actual query params sent (excluding secrets)
        request = captured_request[0]
        sent_params = dict(request.url.params)
        non_sensitive_sent = {k: v for k, v in sent_params.items() if k != "api_key"}

        # Extract metadata parameters
        _, metadata_bytes = writer.fixtures["v1"]
        metadata_dict = json.loads(metadata_bytes)
        metadata_params = metadata_dict["parameters"]

        # They must match exactly
        assert metadata_params == non_sensitive_sent, (
            f"Metadata parameters {metadata_params} don't match "
            f"actual non-sensitive request params {non_sensitive_sent}"
        )
