"""Property tests for fixture serialization and metadata (Properties 3, 4, 5).

Tests the fixture capture pipeline: round-trip serialization, metadata completeness
with checksum integrity, and secret exclusion from metadata.
"""

from __future__ import annotations

import hashlib
import json

import httpx
import pytest
from hypothesis import given, settings
from hypothesis import strategies as st
from pydantic import SecretStr

from moviebot.common.config import Settings
from moviebot.repositories.fixture_writer import InMemoryFixtureWriter
from moviebot.repositories.tmdb_connector import TmdbConnector


def _tmdb_movie_object() -> st.SearchStrategy[dict]:
    """Generate a TMDB movie object (as returned in `results` array)."""
    return st.fixed_dictionaries(
        {
            "id": st.integers(min_value=1, max_value=10_000_000),
            "title": st.text(min_size=1, max_size=200).filter(lambda s: s.strip()),
        },
        optional={
            "overview": st.one_of(st.none(), st.text(max_size=500)),
            "release_date": st.one_of(
                st.none(),
                st.just(""),
                st.dates().map(lambda d: d.isoformat()),
            ),
            "genre_ids": st.one_of(
                st.none(),
                st.lists(st.integers(min_value=1, max_value=99999), max_size=8),
            ),
            "popularity": st.one_of(
                st.none(),
                st.floats(min_value=0.0, max_value=10000.0, allow_nan=False),
            ),
            "vote_average": st.one_of(
                st.none(),
                st.floats(min_value=0.0, max_value=10.0, allow_nan=False),
            ),
        },
    )


def _tmdb_response(
    min_results: int = 0, max_results: int = 10
) -> st.SearchStrategy[dict]:
    """Generate a full TMDB trending response dict with valid structure."""
    return st.fixed_dictionaries(
        {
            "page": st.just(1),
            "results": st.lists(
                _tmdb_movie_object(),
                min_size=min_results,
                max_size=max_results,
            ),
            "total_pages": st.integers(min_value=1, max_value=100),
            "total_results": st.integers(min_value=0, max_value=2000),
        }
    )


# A known secret key value used in tests — must NOT appear in metadata
_TEST_SECRET_KEY = "test-secret-key-XYZ-9a8b7c6d5e4f"


def _make_settings() -> Settings:
    """Create a Settings instance with a known test API key."""
    return Settings(
        openai_api_key=SecretStr("fake-openai-key"),
        openai_model="gpt-4",
        tmdb_api_key=SecretStr(_TEST_SECRET_KEY),
    )


def _make_mock_transport(response_dict: dict) -> httpx.MockTransport:
    """Create a MockTransport that returns the given dict as a JSON response."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            status_code=200,
            json=response_dict,
        )

    return httpx.MockTransport(handler)


@pytest.mark.asyncio
@given(response_data=_tmdb_response(min_results=0, max_results=10))
@settings(max_examples=50, deadline=None)
async def test_property_3_roundtrip_payload_serialization(
    response_data: dict,
) -> None:
    """Property 3: Round-trip de serialización del payload de fixture.

    **Validates: Requirements 2.2**

    For any valid TMDB response dict, capturing a fixture and reading back
    the payload bytes produces a semantically equivalent JSON object.
    """
    transport = _make_mock_transport(response_data)
    client = httpx.AsyncClient(transport=transport)
    writer = InMemoryFixtureWriter()
    settings_obj = _make_settings()

    connector = TmdbConnector(
        settings=settings_obj,
        client=client,
        fixture_writer=writer,
    )

    await connector.capture_fixture("v1")

    # Read back payload from InMemoryFixtureWriter
    payload_bytes, _metadata_bytes = writer.fixtures["v1"]
    deserialized = json.loads(payload_bytes)

    # Semantic equivalence: the deserialized payload must equal the original dict
    assert deserialized == response_data, (
        f"Round-trip failed: deserialized payload differs from original.\n"
        f"Original keys: {sorted(response_data.keys())}\n"
        f"Deserialized keys: {sorted(deserialized.keys())}"
    )


@pytest.mark.asyncio
@given(response_data=_tmdb_response(min_results=1, max_results=10))
@settings(max_examples=50, deadline=None)
async def test_property_4_metadata_complete_and_checksum_integrity(
    response_data: dict,
) -> None:
    """Property 4: Metadata del fixture es completa y checksum íntegro.

    **Validates: Requirements 2.3, 3.13, 3.14**

    For every successful fixture capture, the metadata contains all mandatory
    fields and the checksum_sha256 matches SHA-256 of the payload bytes.
    """
    transport = _make_mock_transport(response_data)
    client = httpx.AsyncClient(transport=transport)
    writer = InMemoryFixtureWriter()
    settings_obj = _make_settings()

    connector = TmdbConnector(
        settings=settings_obj,
        client=client,
        fixture_writer=writer,
    )

    await connector.capture_fixture("v1")

    payload_bytes, metadata_bytes = writer.fixtures["v1"]
    metadata = json.loads(metadata_bytes)

    # Verify all mandatory fields are present
    required_fields = {
        "version",
        "endpoint",
        "captured_at",
        "parameters",
        "checksum_sha256",
    }
    actual_fields = set(metadata.keys())
    missing = required_fields - actual_fields
    assert not missing, f"Metadata missing required fields: {missing}"

    # Verify field types
    assert isinstance(metadata["version"], str)
    assert isinstance(metadata["endpoint"], str)
    assert isinstance(metadata["captured_at"], str)
    assert isinstance(metadata["parameters"], dict)
    assert isinstance(metadata["checksum_sha256"], str)

    # Verify checksum integrity: checksum_sha256 == SHA-256 of payload bytes
    expected_checksum = hashlib.sha256(payload_bytes).hexdigest()
    assert metadata["checksum_sha256"] == expected_checksum, (
        f"Checksum mismatch!\n"
        f"  metadata checksum: {metadata['checksum_sha256']}\n"
        f"  actual SHA-256:    {expected_checksum}"
    )


@pytest.mark.asyncio
@given(response_data=_tmdb_response(min_results=0, max_results=10))
@settings(max_examples=50, deadline=None)
async def test_property_5_metadata_excludes_secrets(
    response_data: dict,
) -> None:
    """Property 5: Metadata excluye secretos.

    **Validates: Requirements 2.4, 3.10**

    For every fixture capture, the API key value does NOT appear anywhere
    in the serialized metadata content.
    """
    transport = _make_mock_transport(response_data)
    client = httpx.AsyncClient(transport=transport)
    writer = InMemoryFixtureWriter()
    settings_obj = _make_settings()

    connector = TmdbConnector(
        settings=settings_obj,
        client=client,
        fixture_writer=writer,
    )

    await connector.capture_fixture("v1")

    _payload_bytes, metadata_bytes = writer.fixtures["v1"]
    metadata_str = metadata_bytes.decode("utf-8")

    # The secret API key must NOT appear in metadata
    assert _TEST_SECRET_KEY not in metadata_str, (
        f"API key leaked into metadata!\n"
        f"  Secret: {_TEST_SECRET_KEY!r}\n"
        f"  Found in metadata content"
    )
