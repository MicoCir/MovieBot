"""Tests unitarios para los modelos Pydantic del Silver Evaluation Dataset.

Valida: Requisitos 1.2, 1.3, 1.10, 1.11, 1.14, 1.15, 10.1, 10.3, 10.4
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from moviebot.evals.silver.models import (
    NetflixHardConstraints,
    SeedProvenance,
    SilverSeed,
    TmdbHardConstraints,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_provenance(**overrides: object) -> dict:
    """Create a valid provenance dict with optional overrides."""
    base = {
        "source": "netflix",
        "input_data_description": "Test data",
        "schema_version": "1.0.0",
        "silver_dataset_version": "silver_v1",
        "canonical_dataset_version": "v1",
    }
    base.update(overrides)
    return base


def _make_netflix_seed(**overrides: object) -> dict:
    """Create a valid Netflix SUCCESS seed dict with optional overrides."""
    base = {
        "case_id": "test-case-01",
        "expected_route": "netflix",
        "expected_sources": ["netflix"],
        "expected_status": "SUCCESS",
        "hard_constraints": {
            "constraint_type": "netflix",
            "genres": ["drama"],
        },
        "semantic_concepts": [],
        "seed_item_ids": ["tm84618"],
        "eligible_item_ids": ["tm84618", "tm70993"],
        "difficulty": "easy",
        "tags": [],
        "provenance": _make_provenance(),
    }
    base.update(overrides)
    return base


def _make_trending_seed(**overrides: object) -> dict:
    """Create a valid Trending SUCCESS seed dict with optional overrides."""
    base = {
        "case_id": "trending-case-01",
        "expected_route": "trending",
        "expected_sources": ["tmdb"],
        "expected_status": "SUCCESS",
        "hard_constraints": {
            "constraint_type": "tmdb",
            "genre_ids": [18],
        },
        "seed_item_ids": ["tmdb:872585"],
        "eligible_item_ids": ["tmdb:872585"],
        "difficulty": "medium",
        "tags": [],
        "provenance": _make_provenance(source="tmdb"),
        "fixture_version": "v1",
    }
    base.update(overrides)
    return base


def _make_both_seed(**overrides: object) -> dict:
    """Create a valid 'both' route SUCCESS seed dict with optional overrides."""
    base = {
        "case_id": "both-case-01",
        "expected_route": "both",
        "expected_sources": ["tmdb", "netflix"],
        "expected_status": "SUCCESS",
        "hard_constraints": None,
        "semantic_concepts": [],
        "seed_item_ids": [],
        "eligible_item_ids": None,
        "difficulty": "hard",
        "tags": [],
        "provenance": _make_provenance(source="both"),
        "tmdb_component": {
            "fixture_version": "v1",
            "seed_item_ids": ["tmdb:872585"],
            "eligible_item_ids": ["tmdb:872585"],
            "hard_constraints": {"constraint_type": "tmdb", "genre_ids": [18]},
            "semantic_concepts": [],
        },
        "netflix_component": {
            "seed_item_ids": ["tm84618"],
            "eligible_item_ids": ["tm84618"],
            "hard_constraints": {"constraint_type": "netflix", "genres": ["drama"]},
            "semantic_concepts": [],
        },
    }
    base.update(overrides)
    return base


# ---------------------------------------------------------------------------
# Tests: Rangos inválidos rechazados con ValueError (Req 1.14, 1.15)
# ---------------------------------------------------------------------------


class TestInvalidRanges:
    """Rangos inválidos (min > max) rechazados con ValidationError."""

    def test_tmdb_min_year_gt_max_year(self) -> None:
        with pytest.raises(ValidationError, match="min_year > max_year"):
            TmdbHardConstraints(min_year=2020, max_year=2010)

    def test_tmdb_min_vote_gt_max_vote(self) -> None:
        with pytest.raises(
            ValidationError, match="min_vote_average > max_vote_average"
        ):
            TmdbHardConstraints(min_vote_average=8.0, max_vote_average=5.0)

    def test_netflix_min_year_gt_max_year(self) -> None:
        with pytest.raises(ValidationError, match="min_year > max_year"):
            NetflixHardConstraints(min_year=2020, max_year=2010)

    def test_netflix_min_imdb_gt_max_imdb(self) -> None:
        with pytest.raises(ValidationError, match="min_imdb_score > max_imdb_score"):
            NetflixHardConstraints(min_imdb_score=9.0, max_imdb_score=3.0)


# ---------------------------------------------------------------------------
# Tests: Géneros con mayúsculas rechazados (Req 1.3)
# ---------------------------------------------------------------------------


class TestNetflixGenresLowercase:
    """Géneros con mayúsculas rechazados en NetflixHardConstraints."""

    def test_uppercase_genre_rejected(self) -> None:
        with pytest.raises(ValidationError, match="lowercase"):
            NetflixHardConstraints(genres=["Drama"])

    def test_mixed_case_genre_rejected(self) -> None:
        with pytest.raises(ValidationError, match="lowercase"):
            NetflixHardConstraints(genres=["science Fiction"])

    def test_lowercase_genre_accepted(self) -> None:
        c = NetflixHardConstraints(genres=["drama", "comedy"])
        assert c.genres == ["drama", "comedy"]


# ---------------------------------------------------------------------------
# Tests: Longitudes máximas de listas (Req 1.2, 1.3)
# ---------------------------------------------------------------------------


class TestMaxLengthLists:
    """Longitudes máximas de listas rechazadas cuando se exceden."""

    def test_genres_exceeds_5(self) -> None:
        with pytest.raises(ValidationError):
            NetflixHardConstraints(genres=["a", "b", "c", "d", "e", "f"])

    def test_actors_exceeds_10(self) -> None:
        with pytest.raises(ValidationError):
            NetflixHardConstraints(actors=[f"actor{i}" for i in range(11)])

    def test_seed_item_ids_exceeds_50(self) -> None:
        data = _make_netflix_seed(
            seed_item_ids=[f"tm{i:05d}" for i in range(51)],
            eligible_item_ids=[f"tm{i:05d}" for i in range(51)],
        )
        with pytest.raises(ValidationError):
            SilverSeed.model_validate(data)

    def test_tmdb_genre_ids_exceeds_5(self) -> None:
        with pytest.raises(ValidationError):
            TmdbHardConstraints(genre_ids=[1, 2, 3, 4, 5, 6])


# ---------------------------------------------------------------------------
# Tests: case_id inválido (Req 1.2)
# ---------------------------------------------------------------------------


class TestCaseIdValidation:
    """case_id inválido (caracteres especiales, >64 chars) rechazado."""

    def test_special_characters_rejected(self) -> None:
        data = _make_netflix_seed(case_id="invalid!case@id")
        with pytest.raises(ValidationError):
            SilverSeed.model_validate(data)

    def test_exceeds_64_chars_rejected(self) -> None:
        data = _make_netflix_seed(case_id="a" * 65)
        with pytest.raises(ValidationError):
            SilverSeed.model_validate(data)

    def test_valid_case_id_accepted(self) -> None:
        data = _make_netflix_seed(case_id="valid-case_01")
        seed = SilverSeed.model_validate(data)
        assert seed.case_id == "valid-case_01"

    def test_spaces_rejected(self) -> None:
        data = _make_netflix_seed(case_id="has space")
        with pytest.raises(ValidationError):
            SilverSeed.model_validate(data)


# ---------------------------------------------------------------------------
# Tests: Discriminador constraint_type (Req 1.2, Design Decision 4)
# ---------------------------------------------------------------------------


class TestConstraintTypeDiscriminator:
    """Discriminador constraint_type: deserializar JSON produce tipo correcto."""

    def test_tmdb_discriminator(self) -> None:
        data = _make_trending_seed()
        seed = SilverSeed.model_validate(data)
        assert isinstance(seed.hard_constraints, TmdbHardConstraints)
        assert seed.hard_constraints.constraint_type == "tmdb"

    def test_netflix_discriminator(self) -> None:
        data = _make_netflix_seed()
        seed = SilverSeed.model_validate(data)
        assert isinstance(seed.hard_constraints, NetflixHardConstraints)
        assert seed.hard_constraints.constraint_type == "netflix"


# ---------------------------------------------------------------------------
# Tests: extra="forbid" (Design Decision 4)
# ---------------------------------------------------------------------------


class TestExtraForbid:
    """Campos desconocidos rechazados por extra='forbid'."""

    def test_tmdb_unknown_field_rejected(self) -> None:
        with pytest.raises(ValidationError):
            TmdbHardConstraints(genre_ids=[18], unknown_field="oops")  # type: ignore[call-arg]

    def test_netflix_unknown_field_rejected(self) -> None:
        with pytest.raises(ValidationError):
            NetflixHardConstraints(genres=["drama"], unknown_field="oops")  # type: ignore[call-arg]

    def test_tmdb_extra_via_json(self) -> None:
        """Deserialization from JSON also rejects extra fields."""
        data = {"constraint_type": "tmdb", "genre_ids": [18], "bogus": True}
        with pytest.raises(ValidationError):
            TmdbHardConstraints.model_validate(data)

    def test_netflix_extra_via_json(self) -> None:
        data = {"constraint_type": "netflix", "genres": ["drama"], "bogus": 1}
        with pytest.raises(ValidationError):
            NetflixHardConstraints.model_validate(data)


# ---------------------------------------------------------------------------
# Tests: Estados y rutas incompatibles (Req 1.10, 1.11)
# ---------------------------------------------------------------------------


class TestRouteStatusIncompatibility:
    """Estados y rutas incompatibles rechazados."""

    def test_both_with_no_results_rejected(self) -> None:
        """Route 'both' solo admite expected_status='SUCCESS'."""
        data = _make_both_seed(expected_status="NO_RESULTS")
        with pytest.raises(ValidationError, match="both"):
            SilverSeed.model_validate(data)

    def test_trending_with_netflix_constraints_rejected(self) -> None:
        """Route 'trending' con NetflixHardConstraints es rechazado."""
        data = _make_trending_seed(
            hard_constraints={"constraint_type": "netflix", "genres": ["drama"]}
        )
        with pytest.raises(ValidationError):
            SilverSeed.model_validate(data)

    def test_netflix_with_tmdb_constraints_rejected(self) -> None:
        """Route 'netflix' con TmdbHardConstraints es rechazado."""
        data = _make_netflix_seed(
            hard_constraints={"constraint_type": "tmdb", "genre_ids": [18]}
        )
        with pytest.raises(ValidationError):
            SilverSeed.model_validate(data)

    def test_out_of_scope_with_success_status_rejected(self) -> None:
        """Route 'out_of_scope' requiere expected_status 'OUT_OF_SCOPE'."""
        data = {
            "case_id": "oos-case",
            "expected_route": "out_of_scope",
            "expected_sources": [],
            "expected_status": "SUCCESS",
            "hard_constraints": None,
            "semantic_concepts": [],
            "seed_item_ids": [],
            "eligible_item_ids": None,
            "difficulty": "easy",
            "tags": [],
            "provenance": _make_provenance(source="synthetic"),
        }
        with pytest.raises(ValidationError):
            SilverSeed.model_validate(data)


# ---------------------------------------------------------------------------
# Tests: NO_RESULTS con eligible_item_ids=None rechazado (Req 1.11)
# ---------------------------------------------------------------------------


class TestNoResultsEligible:
    """NO_RESULTS con eligible_item_ids=None rechazado (debe ser [])."""

    def test_no_results_eligible_none_rejected(self) -> None:
        data = _make_netflix_seed(
            expected_status="NO_RESULTS",
            seed_item_ids=[],
            eligible_item_ids=None,
            hard_constraints={"constraint_type": "netflix", "genres": ["drama"]},
        )
        with pytest.raises(ValidationError, match="eligible_item_ids"):
            SilverSeed.model_validate(data)

    def test_no_results_with_empty_eligible_accepted(self) -> None:
        data = _make_netflix_seed(
            expected_status="NO_RESULTS",
            seed_item_ids=[],
            eligible_item_ids=[],
            hard_constraints={"constraint_type": "netflix", "genres": ["drama"]},
        )
        seed = SilverSeed.model_validate(data)
        assert seed.eligible_item_ids == []
        assert seed.expected_status == "NO_RESULTS"


# ---------------------------------------------------------------------------
# Tests: Round-trip serialización/deserialización (Req 1.10)
# ---------------------------------------------------------------------------


class TestRoundTrip:
    """model_dump(mode='json') → model_validate() produce igualdad."""

    def test_netflix_seed_round_trip(self) -> None:
        data = _make_netflix_seed()
        seed = SilverSeed.model_validate(data)
        dumped = seed.model_dump(mode="json")
        restored = SilverSeed.model_validate(dumped)
        assert restored == seed

    def test_trending_seed_round_trip(self) -> None:
        data = _make_trending_seed()
        seed = SilverSeed.model_validate(data)
        dumped = seed.model_dump(mode="json")
        restored = SilverSeed.model_validate(dumped)
        assert restored == seed

    def test_both_seed_round_trip(self) -> None:
        data = _make_both_seed()
        seed = SilverSeed.model_validate(data)
        dumped = seed.model_dump(mode="json")
        restored = SilverSeed.model_validate(dumped)
        assert restored == seed

    def test_out_of_scope_round_trip(self) -> None:
        data = {
            "case_id": "oos-round-trip",
            "expected_route": "out_of_scope",
            "expected_sources": [],
            "expected_status": "OUT_OF_SCOPE",
            "hard_constraints": None,
            "semantic_concepts": [],
            "seed_item_ids": [],
            "eligible_item_ids": None,
            "difficulty": "easy",
            "tags": ["out-of-scope"],
            "provenance": _make_provenance(source="synthetic"),
        }
        seed = SilverSeed.model_validate(data)
        dumped = seed.model_dump(mode="json")
        restored = SilverSeed.model_validate(dumped)
        assert restored == seed


# ---------------------------------------------------------------------------
# Tests: is_default() (Req 1.2, 1.3)
# ---------------------------------------------------------------------------


class TestIsDefault:
    """is_default() correcto para constraints con y sin campos activos."""

    def test_tmdb_default_all_none(self) -> None:
        c = TmdbHardConstraints()
        assert c.is_default() is True

    def test_tmdb_not_default_with_genre_ids(self) -> None:
        c = TmdbHardConstraints(genre_ids=[18])
        assert c.is_default() is False

    def test_tmdb_not_default_with_min_year(self) -> None:
        c = TmdbHardConstraints(min_year=2000)
        assert c.is_default() is False

    def test_tmdb_not_default_with_vote_average(self) -> None:
        c = TmdbHardConstraints(min_vote_average=7.0)
        assert c.is_default() is False

    def test_netflix_default_all_none(self) -> None:
        c = NetflixHardConstraints()
        assert c.is_default() is True

    def test_netflix_not_default_with_genres(self) -> None:
        c = NetflixHardConstraints(genres=["drama"])
        assert c.is_default() is False

    def test_netflix_not_default_with_type(self) -> None:
        c = NetflixHardConstraints(type="movie")
        assert c.is_default() is False

    def test_netflix_not_default_with_actors(self) -> None:
        c = NetflixHardConstraints(actors=["actor1"])
        assert c.is_default() is False

    def test_netflix_not_default_with_score_range(self) -> None:
        c = NetflixHardConstraints(min_imdb_score=7.0, max_imdb_score=9.0)
        assert c.is_default() is False


# ---------------------------------------------------------------------------
# Tests: SeedProvenance model_validator for canonical_dataset_version (Req 10.4)
# ---------------------------------------------------------------------------


class TestProvenanceCanonicalDatasetVersion:
    """SeedProvenance validator enforces canonical_dataset_version for netflix/both."""

    def test_netflix_source_without_canonical_version_rejected(self) -> None:
        """source='netflix' without canonical_dataset_version → ValidationError."""
        with pytest.raises(ValidationError, match="canonical_dataset_version"):
            SeedProvenance(
                source="netflix",
                input_data_description="Test data",
                schema_version="1.0.0",
                silver_dataset_version="silver_v1",
                canonical_dataset_version=None,
            )

    def test_both_source_without_canonical_version_rejected(self) -> None:
        """source='both' without canonical_dataset_version → ValidationError."""
        with pytest.raises(ValidationError, match="canonical_dataset_version"):
            SeedProvenance(
                source="both",
                input_data_description="Test data",
                schema_version="1.0.0",
                silver_dataset_version="silver_v1",
                canonical_dataset_version=None,
            )

    def test_tmdb_source_without_canonical_version_accepted(self) -> None:
        """source='tmdb' without canonical_dataset_version is valid."""
        prov = SeedProvenance(
            source="tmdb",
            input_data_description="Test data",
            schema_version="1.0.0",
            silver_dataset_version="silver_v1",
            canonical_dataset_version=None,
        )
        assert prov.canonical_dataset_version is None
        assert prov.source == "tmdb"

    def test_synthetic_source_without_canonical_version_accepted(self) -> None:
        """source='synthetic' without canonical_dataset_version is valid."""
        prov = SeedProvenance(
            source="synthetic",
            input_data_description="OOS test",
            schema_version="1.0.0",
            silver_dataset_version="silver_v1",
            canonical_dataset_version=None,
        )
        assert prov.canonical_dataset_version is None
        assert prov.source == "synthetic"

    def test_netflix_source_with_canonical_version_accepted(self) -> None:
        """source='netflix' with canonical_dataset_version is valid."""
        prov = SeedProvenance(
            source="netflix",
            input_data_description="Test data",
            schema_version="1.0.0",
            silver_dataset_version="silver_v1",
            canonical_dataset_version="v1",
        )
        assert prov.canonical_dataset_version == "v1"

    def test_both_source_with_canonical_version_accepted(self) -> None:
        """source='both' with canonical_dataset_version is valid."""
        prov = SeedProvenance(
            source="both",
            input_data_description="Test data",
            schema_version="1.0.0",
            silver_dataset_version="silver_v1",
            canonical_dataset_version="v1",
        )
        assert prov.canonical_dataset_version == "v1"


# ---------------------------------------------------------------------------
# Tests: SeedProvenance new provenance fields (Req 10.4)
# ---------------------------------------------------------------------------


class TestProvenanceNewFields:
    """Test silver_dataset_version, canonical_dataset_version, etl_version fields."""

    def test_silver_dataset_version_pattern_valid(self) -> None:
        """silver_dataset_version with valid pattern is accepted."""
        prov = SeedProvenance(
            source="tmdb",
            input_data_description="Test",
            schema_version="1.0.0",
            silver_dataset_version="silver_v1-beta",
        )
        assert prov.silver_dataset_version == "silver_v1-beta"

    def test_silver_dataset_version_pattern_invalid_rejected(self) -> None:
        """silver_dataset_version with invalid characters is rejected."""
        with pytest.raises(ValidationError):
            SeedProvenance(
                source="tmdb",
                input_data_description="Test",
                schema_version="1.0.0",
                silver_dataset_version="silver v1!",  # space and ! are invalid
            )

    def test_etl_version_valid_semver(self) -> None:
        """etl_version with valid semver pattern is accepted."""
        prov = SeedProvenance(
            source="netflix",
            input_data_description="Test",
            schema_version="1.0.0",
            silver_dataset_version="silver_v1",
            canonical_dataset_version="v1",
            etl_version="1.2.3",
        )
        assert prov.etl_version == "1.2.3"

    def test_etl_version_invalid_pattern_rejected(self) -> None:
        """etl_version with invalid semver pattern is rejected."""
        with pytest.raises(ValidationError):
            SeedProvenance(
                source="netflix",
                input_data_description="Test",
                schema_version="1.0.0",
                silver_dataset_version="silver_v1",
                canonical_dataset_version="v1",
                etl_version="v1.0",  # not valid semver pattern
            )

    def test_etl_version_none_is_valid(self) -> None:
        """etl_version=None is valid (optional field)."""
        prov = SeedProvenance(
            source="tmdb",
            input_data_description="Test",
            schema_version="1.0.0",
            silver_dataset_version="silver_v1",
            etl_version=None,
        )
        assert prov.etl_version is None

    def test_checksum_sha256_valid_pattern(self) -> None:
        """checksum_sha256 with valid 64-char hex is accepted."""
        checksum = "a" * 64
        prov = SeedProvenance(
            source="netflix",
            input_data_description="Test",
            schema_version="1.0.0",
            silver_dataset_version="silver_v1",
            canonical_dataset_version="v1",
            checksum_sha256=checksum,
        )
        assert prov.checksum_sha256 == checksum

    def test_checksum_sha256_invalid_pattern_rejected(self) -> None:
        """checksum_sha256 with invalid pattern is rejected."""
        with pytest.raises(ValidationError):
            SeedProvenance(
                source="netflix",
                input_data_description="Test",
                schema_version="1.0.0",
                silver_dataset_version="silver_v1",
                canonical_dataset_version="v1",
                checksum_sha256="short",  # too short
            )
