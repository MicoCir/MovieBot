# tests/unit/test_etl_schema.py
"""Unit tests for CanonicalNetflixTitle and EtlMetadata models."""

import pytest
from pydantic import ValidationError

from moviebot.etl.schema import CanonicalNetflixTitle, EtlMetadata


class TestCanonicalNetflixTitle:
    """Tests for the CanonicalNetflixTitle model."""

    def test_valid_minimal_title(self) -> None:
        title = CanonicalNetflixTitle(
            id="tm12345",
            title="The Matrix",
            type="movie",
            release_year=1999,
        )
        assert title.id == "tm12345"
        assert title.title == "The Matrix"
        assert title.type == "movie"
        assert title.release_year == 1999
        assert title.description is None
        assert title.genres == []
        assert title.actors == []
        assert title.directors == []

    def test_valid_full_title(self) -> None:
        title = CanonicalNetflixTitle(
            id="ts999",
            title="Breaking Bad",
            type="show",
            release_year=2008,
            description="A high school chemistry teacher turned meth cook.",
            age_certification="TV-MA",
            genres=["crime", "drama"],
            actors=["bryan cranston", "aaron paul"],
            directors=["vince gilligan"],
            imdb_score=9.5,
            tmdb_score=8.9,
            tmdb_popularity=150.5,
        )
        assert title.type == "show"
        assert title.genres == ["crime", "drama"]
        assert title.imdb_score == 9.5

    def test_invalid_id_pattern(self) -> None:
        with pytest.raises(ValidationError):
            CanonicalNetflixTitle(
                id="invalid123",
                title="Test",
                type="movie",
                release_year=2000,
            )

    def test_id_must_start_with_t(self) -> None:
        with pytest.raises(ValidationError):
            CanonicalNetflixTitle(
                id="sm12345",
                title="Test",
                type="movie",
                release_year=2000,
            )

    def test_id_max_length(self) -> None:
        with pytest.raises(ValidationError):
            CanonicalNetflixTitle(
                id="tm1234567890123456789",  # 21 chars
                title="Test",
                type="movie",
                release_year=2000,
            )

    def test_title_min_length(self) -> None:
        with pytest.raises(ValidationError):
            CanonicalNetflixTitle(
                id="tm1",
                title="",
                type="movie",
                release_year=2000,
            )

    def test_title_max_length(self) -> None:
        with pytest.raises(ValidationError):
            CanonicalNetflixTitle(
                id="tm1",
                title="x" * 501,
                type="movie",
                release_year=2000,
            )

    def test_invalid_type(self) -> None:
        with pytest.raises(ValidationError):
            CanonicalNetflixTitle(
                id="tm1",
                title="Test",
                type="documentary",  # type: ignore[arg-type]
                release_year=2000,
            )

    def test_release_year_min(self) -> None:
        with pytest.raises(ValidationError):
            CanonicalNetflixTitle(
                id="tm1",
                title="Test",
                type="movie",
                release_year=1887,
            )

    def test_release_year_max(self) -> None:
        with pytest.raises(ValidationError):
            CanonicalNetflixTitle(
                id="tm1",
                title="Test",
                type="movie",
                release_year=2101,
            )

    def test_release_year_boundaries_valid(self) -> None:
        t1 = CanonicalNetflixTitle(
            id="tm1", title="Test", type="movie", release_year=1888
        )
        t2 = CanonicalNetflixTitle(
            id="tm1", title="Test", type="movie", release_year=2100
        )
        assert t1.release_year == 1888
        assert t2.release_year == 2100

    def test_imdb_score_range(self) -> None:
        # Valid boundaries
        t = CanonicalNetflixTitle(
            id="tm1", title="Test", type="movie", release_year=2000, imdb_score=0.0
        )
        assert t.imdb_score == 0.0
        t = CanonicalNetflixTitle(
            id="tm1", title="Test", type="movie", release_year=2000, imdb_score=10.0
        )
        assert t.imdb_score == 10.0

        # Out of range
        with pytest.raises(ValidationError):
            CanonicalNetflixTitle(
                id="tm1", title="Test", type="movie", release_year=2000, imdb_score=-0.1
            )
        with pytest.raises(ValidationError):
            CanonicalNetflixTitle(
                id="tm1", title="Test", type="movie", release_year=2000, imdb_score=10.1
            )

    def test_tmdb_popularity_range(self) -> None:
        t = CanonicalNetflixTitle(
            id="tm1",
            title="Test",
            type="movie",
            release_year=2000,
            tmdb_popularity=10000.0,
        )
        assert t.tmdb_popularity == 10000.0

        with pytest.raises(ValidationError):
            CanonicalNetflixTitle(
                id="tm1",
                title="Test",
                type="movie",
                release_year=2000,
                tmdb_popularity=10000.1,
            )

    def test_extra_fields_forbidden(self) -> None:
        with pytest.raises(ValidationError):
            CanonicalNetflixTitle(
                id="tm1",
                title="Test",
                type="movie",
                release_year=2000,
                runtime=120,  # type: ignore[call-arg]
            )

    def test_description_max_length(self) -> None:
        with pytest.raises(ValidationError):
            CanonicalNetflixTitle(
                id="tm1",
                title="Test",
                type="movie",
                release_year=2000,
                description="x" * 2001,
            )

    def test_age_certification_max_length(self) -> None:
        with pytest.raises(ValidationError):
            CanonicalNetflixTitle(
                id="tm1",
                title="Test",
                type="movie",
                release_year=2000,
                age_certification="x" * 21,
            )


class TestEtlMetadata:
    """Tests for the EtlMetadata model."""

    def _valid_metadata(self, **overrides) -> dict:  # type: ignore[no-untyped-def]
        base = {
            "canonical_dataset_version": "v1",
            "etl_version": "1.0.0",
            "schema_version": "1.0.0",
            "document_count": 5849,
            "discarded_count": 12,
            "source_checksums": {
                "titles.csv": "a" * 64,
                "credits.csv": "b" * 64,
            },
            "output_checksum_sha256": "c" * 64,
            "generated_at": "2024-01-15T10:30:00Z",
            "type_distribution": {"movie": 4000, "show": 1849},
        }
        base.update(overrides)
        return base

    def test_valid_metadata(self) -> None:
        meta = EtlMetadata(**self._valid_metadata())
        assert meta.canonical_dataset_version == "v1"
        assert meta.etl_version == "1.0.0"
        assert meta.document_count == 5849
        assert meta.type_distribution == {"movie": 4000, "show": 1849}

    def test_canonical_dataset_version_safe_chars(self) -> None:
        # Valid versions
        EtlMetadata(**self._valid_metadata(canonical_dataset_version="v1"))
        EtlMetadata(**self._valid_metadata(canonical_dataset_version="v1-beta"))
        EtlMetadata(**self._valid_metadata(canonical_dataset_version="v1_0"))

        # Invalid: path separators
        with pytest.raises(ValidationError):
            EtlMetadata(**self._valid_metadata(canonical_dataset_version="v1/bad"))
        with pytest.raises(ValidationError):
            EtlMetadata(**self._valid_metadata(canonical_dataset_version="v1\\bad"))
        with pytest.raises(ValidationError):
            EtlMetadata(**self._valid_metadata(canonical_dataset_version="v1 space"))

    def test_etl_version_semver(self) -> None:
        with pytest.raises(ValidationError):
            EtlMetadata(**self._valid_metadata(etl_version="1.0"))
        with pytest.raises(ValidationError):
            EtlMetadata(**self._valid_metadata(etl_version="v1.0.0"))

    def test_schema_version_semver(self) -> None:
        with pytest.raises(ValidationError):
            EtlMetadata(**self._valid_metadata(schema_version="1.0"))

    def test_document_count_non_negative(self) -> None:
        with pytest.raises(ValidationError):
            EtlMetadata(**self._valid_metadata(document_count=-1))

    def test_discarded_count_non_negative(self) -> None:
        with pytest.raises(ValidationError):
            EtlMetadata(**self._valid_metadata(discarded_count=-1))

    def test_source_checksums_invalid_value(self) -> None:
        with pytest.raises(ValidationError):
            EtlMetadata(
                **self._valid_metadata(
                    source_checksums={"titles.csv": "not-a-valid-checksum"}
                )
            )

    def test_source_checksums_uppercase_hex_rejected(self) -> None:
        with pytest.raises(ValidationError):
            EtlMetadata(
                **self._valid_metadata(source_checksums={"titles.csv": "A" * 64})
            )

    def test_output_checksum_invalid(self) -> None:
        with pytest.raises(ValidationError):
            EtlMetadata(**self._valid_metadata(output_checksum_sha256="short"))

    def test_generated_at_iso8601(self) -> None:
        # Valid
        EtlMetadata(**self._valid_metadata(generated_at="2024-01-15T10:30:00Z"))

        # Invalid: not UTC format
        with pytest.raises(ValidationError):
            EtlMetadata(**self._valid_metadata(generated_at="2024-01-15 10:30:00"))
        with pytest.raises(ValidationError):
            EtlMetadata(
                **self._valid_metadata(generated_at="2024-01-15T10:30:00+00:00")
            )
