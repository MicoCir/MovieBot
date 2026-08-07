# tests/unit/test_tmdb_errors_and_models.py
"""Tests unitarios para excepciones TMDB y modelos de fixture.

Valida: Requisitos 2.3, 2.7
"""

import pytest
from pydantic import ValidationError

from moviebot.common.errors import MovieBotError
from moviebot.repositories.tmdb_errors import (
    TmdbConnectionError,
    TmdbError,
    TmdbFixtureConflictError,
    TmdbFixtureInconsistentError,
    TmdbHttpError,
    TmdbInvalidResponseError,
    TmdbTimeoutError,
)
from moviebot.repositories.tmdb_models import FixturePaths, ProvenanceMetadata

# === Helper: valid metadata kwargs ===

VALID_METADATA_KWARGS = {
    "version": "v1",
    "endpoint": "https://api.themoviedb.org/3/trending/movie/week",
    "captured_at": "2024-12-15T14:30:00Z",
    "parameters": {"language": "en-US"},
    "checksum_sha256": "a" * 64,
}


# === ProvenanceMetadata: valid inputs ===


def test_provenance_metadata_accepts_valid_input():
    meta = ProvenanceMetadata(**VALID_METADATA_KWARGS)
    assert meta.version == "v1"
    assert meta.endpoint == "https://api.themoviedb.org/3/trending/movie/week"
    assert meta.captured_at == "2024-12-15T14:30:00Z"
    assert meta.checksum_sha256 == "a" * 64


def test_provenance_metadata_accepts_utc_plus_zero_offset():
    kwargs = {**VALID_METADATA_KWARGS, "captured_at": "2024-12-15T14:30:00+00:00"}
    meta = ProvenanceMetadata(**kwargs)
    assert meta.captured_at == "2024-12-15T14:30:00+00:00"


def test_provenance_metadata_accepts_version_with_hyphens_and_underscores():
    kwargs = {**VALID_METADATA_KWARGS, "version": "my-fixture_v2"}
    meta = ProvenanceMetadata(**kwargs)
    assert meta.version == "my-fixture_v2"


# === ProvenanceMetadata: version validation (path traversal prevention) ===


@pytest.mark.parametrize(
    "bad_version",
    [
        "../../attack",
        "../secret",
        "v1/subdir",
        "v1\\backslash",
        "has space",
        "has.dot",
        "",
        "v1@special",
    ],
)
def test_provenance_metadata_rejects_version_with_path_traversal(bad_version: str):
    kwargs = {**VALID_METADATA_KWARGS, "version": bad_version}
    with pytest.raises(ValidationError) as exc_info:
        ProvenanceMetadata(**kwargs)
    assert "version" in str(exc_info.value).lower()


# === ProvenanceMetadata: captured_at validation (UTC only) ===


@pytest.mark.parametrize(
    "non_utc_timestamp",
    [
        "2024-12-15T14:30:00+05:00",
        "2024-12-15T14:30:00-03:00",
        "2024-12-15T14:30:00+01:00",
        "2024-12-15T14:30:00+05:30",
    ],
)
def test_provenance_metadata_rejects_non_utc_captured_at(non_utc_timestamp: str):
    kwargs = {**VALID_METADATA_KWARGS, "captured_at": non_utc_timestamp}
    with pytest.raises(ValidationError) as exc_info:
        ProvenanceMetadata(**kwargs)
    assert "captured_at" in str(exc_info.value).lower()


def test_provenance_metadata_rejects_naive_captured_at():
    """Timestamps sin timezone info deben ser rechazados."""
    kwargs = {**VALID_METADATA_KWARGS, "captured_at": "2024-12-15T14:30:00"}
    with pytest.raises(ValidationError) as exc_info:
        ProvenanceMetadata(**kwargs)
    assert "captured_at" in str(exc_info.value).lower()


def test_provenance_metadata_rejects_invalid_iso_format():
    kwargs = {**VALID_METADATA_KWARGS, "captured_at": "not-a-date"}
    with pytest.raises(ValidationError):
        ProvenanceMetadata(**kwargs)


# === ProvenanceMetadata: checksum_sha256 validation ===


@pytest.mark.parametrize(
    "bad_checksum,reason",
    [
        ("a" * 63, "too short"),
        ("a" * 65, "too long"),
        ("G" * 64, "invalid hex chars (uppercase G)"),
        ("A" * 64, "uppercase hex not allowed"),
        ("z" * 64, "invalid hex chars (z)"),
        ("", "empty string"),
    ],
)
def test_provenance_metadata_rejects_invalid_checksum(bad_checksum: str, reason: str):
    kwargs = {**VALID_METADATA_KWARGS, "checksum_sha256": bad_checksum}
    with pytest.raises(ValidationError) as exc_info:
        ProvenanceMetadata(**kwargs)
    assert "checksum_sha256" in str(exc_info.value).lower()


# === FixturePaths model ===


def test_fixture_paths_valid():
    from pathlib import Path

    fp = FixturePaths(
        payload_path=Path("raw_data/tmdb/trending_movies_v1.json"),
        metadata_path=Path("raw_data/tmdb/trending_movies_v1.metadata.json"),
    )
    assert fp.payload_path == Path("raw_data/tmdb/trending_movies_v1.json")
    assert fp.metadata_path == Path("raw_data/tmdb/trending_movies_v1.metadata.json")


# === Exception hierarchy ===


def test_tmdb_error_inherits_moviebot_error():
    assert issubclass(TmdbError, MovieBotError)


def test_tmdb_error_has_message_and_operation():
    err = TmdbError(message="test error", operation="fetch_trending")
    assert err.message == "test error"
    assert err.operation == "fetch_trending"
    assert str(err) == "test error"


def test_tmdb_http_error_inherits_tmdb_error():
    assert issubclass(TmdbHttpError, TmdbError)


def test_tmdb_http_error_has_status_code_and_body():
    err = TmdbHttpError(
        message="Not Found",
        operation="fetch_trending",
        status_code=404,
        response_body='{"error": "not found"}',
    )
    assert err.status_code == 404
    assert err.response_body == '{"error": "not found"}'
    assert err.operation == "fetch_trending"


@pytest.mark.parametrize(
    "exc_class",
    [
        TmdbTimeoutError,
        TmdbConnectionError,
        TmdbInvalidResponseError,
        TmdbFixtureConflictError,
        TmdbFixtureInconsistentError,
    ],
)
def test_tmdb_subclasses_inherit_tmdb_error(exc_class: type):
    assert issubclass(exc_class, TmdbError)
    assert issubclass(exc_class, MovieBotError)


@pytest.mark.parametrize(
    "exc_class",
    [
        TmdbTimeoutError,
        TmdbConnectionError,
        TmdbInvalidResponseError,
        TmdbFixtureConflictError,
        TmdbFixtureInconsistentError,
    ],
)
def test_tmdb_subclasses_can_be_instantiated(exc_class: type):
    err = exc_class(message="some error", operation="some_op")
    assert err.message == "some error"
    assert err.operation == "some_op"


def test_all_tmdb_errors_are_catchable_as_moviebot_error():
    """All TMDB errors can be caught with a single MovieBotError handler."""
    errors = [
        TmdbError(message="base", operation="op"),
        TmdbHttpError(
            message="http", operation="op", status_code=500, response_body=""
        ),
        TmdbTimeoutError(message="timeout", operation="op"),
        TmdbConnectionError(message="conn", operation="op"),
        TmdbInvalidResponseError(message="invalid", operation="op"),
        TmdbFixtureConflictError(message="conflict", operation="op"),
        TmdbFixtureInconsistentError(message="inconsistent", operation="op"),
    ]
    for err in errors:
        assert isinstance(err, MovieBotError)
