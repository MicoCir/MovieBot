"""Tests for SeedValidator — property-based and unit tests.

Covers:
- Property 7: No cross-contamination in valid seeds (task 7.3)
- Unit tests for each validation_id category (task 7.4)
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from hypothesis import given, settings

from moviebot.evals.silver.adapters import NetflixAdapter, TmdbAdapter
from moviebot.evals.silver.models import (
    NetflixHardConstraints,
    NetflixSeedComponent,
    SeedProvenance,
    SilverSeed,
    TmdbHardConstraints,
    TmdbSeedComponent,
)
from moviebot.evals.silver.validator import (
    SeedValidator,
    ValidationResult,
)
from tests.evals.silver.strategies import valid_silver_seed

# Regex patterns for ID format validation
_NETFLIX_ID_RE = re.compile(r"^t[ms]\d+$")
_TMDB_ID_RE = re.compile(r"^tmdb:\d+$")


# ---------------------------------------------------------------------------
# Helpers for building test seeds
# ---------------------------------------------------------------------------


def _base_provenance(**overrides: Any) -> SeedProvenance:
    """Create a minimal valid SeedProvenance."""
    defaults = {
        "source": "tmdb",
        "fixture_version": "v1",
        "input_data_description": "test data",
        "schema_version": "1.0.0",
        "silver_dataset_version": "silver_v1",
        "canonical_dataset_version": "v1",
    }
    defaults.update(overrides)
    return SeedProvenance(**defaults)


def _trending_seed(
    case_id: str = "trending-1",
    seed_item_ids: list[str] | None = None,
    eligible_item_ids: list[str] | None = None,
    **overrides: Any,
) -> SilverSeed:
    """Build a minimal valid trending seed."""
    defaults: dict[str, Any] = {
        "case_id": case_id,
        "expected_route": "trending",
        "expected_sources": ["tmdb"],
        "expected_status": "SUCCESS",
        "hard_constraints": TmdbHardConstraints(min_year=2023),
        "semantic_concepts": [],
        "seed_item_ids": seed_item_ids or ["tmdb:872585"],
        "eligible_item_ids": eligible_item_ids or ["tmdb:346698", "tmdb:872585"],
        "difficulty": "easy",
        "tags": [],
        "provenance": _base_provenance(source="tmdb"),
        "fixture_version": "v1",
    }
    defaults.update(overrides)
    return SilverSeed(**defaults)


def _netflix_seed(
    case_id: str = "netflix-1",
    seed_item_ids: list[str] | None = None,
    eligible_item_ids: list[str] | None = None,
    **overrides: Any,
) -> SilverSeed:
    """Build a minimal valid netflix seed."""
    defaults: dict[str, Any] = {
        "case_id": case_id,
        "expected_route": "netflix",
        "expected_sources": ["netflix"],
        "expected_status": "SUCCESS",
        "hard_constraints": NetflixHardConstraints(min_year=2010),
        "semantic_concepts": [],
        "seed_item_ids": seed_item_ids or ["tm154986"],
        "eligible_item_ids": eligible_item_ids or ["tm154986", "tm257064"],
        "difficulty": "easy",
        "tags": [],
        "provenance": _base_provenance(source="netflix", fixture_version=None),
        "fixture_version": None,
    }
    defaults.update(overrides)
    return SilverSeed(**defaults)


def _both_seed(
    case_id: str = "both-1",
    tmdb_seed_ids: list[str] | None = None,
    netflix_seed_ids: list[str] | None = None,
    **overrides: Any,
) -> SilverSeed:
    """Build a minimal valid 'both' seed."""
    tmdb_component = TmdbSeedComponent(
        fixture_version="v1",
        seed_item_ids=tmdb_seed_ids or ["tmdb:872585"],
        eligible_item_ids=["tmdb:872585"],
        hard_constraints=TmdbHardConstraints(min_year=2023),
        semantic_concepts=[],
    )
    netflix_component = NetflixSeedComponent(
        seed_item_ids=netflix_seed_ids or ["tm154986"],
        eligible_item_ids=["tm154986"],
        hard_constraints=NetflixHardConstraints(min_year=2010),
        semantic_concepts=[],
    )
    defaults: dict[str, Any] = {
        "case_id": case_id,
        "expected_route": "both",
        "expected_sources": ["tmdb", "netflix"],
        "expected_status": "SUCCESS",
        "hard_constraints": None,
        "semantic_concepts": [],
        "seed_item_ids": [],
        "eligible_item_ids": None,
        "difficulty": "medium",
        "tags": [],
        "provenance": _base_provenance(source="both"),
        "fixture_version": None,
        "tmdb_component": tmdb_component,
        "netflix_component": netflix_component,
    }
    defaults.update(overrides)
    return SilverSeed(**defaults)


def _out_of_scope_seed(case_id: str = "oos-1") -> SilverSeed:
    """Build a minimal valid out_of_scope seed."""
    return SilverSeed(
        case_id=case_id,
        expected_route="out_of_scope",
        expected_sources=[],
        expected_status="OUT_OF_SCOPE",
        hard_constraints=None,
        semantic_concepts=[],
        seed_item_ids=[],
        eligible_item_ids=None,
        difficulty="easy",
        tags=[],
        provenance=_base_provenance(source="synthetic", fixture_version=None),
        fixture_version=None,
    )


# ---------------------------------------------------------------------------
# Task 7.3 — Property 7: No cross-contamination in valid seeds
# ---------------------------------------------------------------------------


class TestPropertyNoCrossContamination:
    """**Validates: Requirements 6.5, 6.10**

    Property 7: Ausencia de contaminación cruzada en seeds validados.
    """

    @given(seed=valid_silver_seed())
    @settings(max_examples=100)
    def test_no_netflix_ids_in_tmdb_components(self, seed: SilverSeed) -> None:
        """No Netflix ID (tm*/ts*) appears in TMDB components."""
        if seed.expected_route == "trending":
            for item_id in seed.seed_item_ids:
                assert not _NETFLIX_ID_RE.match(item_id), (
                    f"Netflix ID {item_id} in trending seed_item_ids"
                )
            if seed.eligible_item_ids is not None:
                for item_id in seed.eligible_item_ids:
                    assert not _NETFLIX_ID_RE.match(item_id), (
                        f"Netflix ID {item_id} in trending eligible_item_ids"
                    )

        elif seed.expected_route == "both" and seed.tmdb_component is not None:
            for item_id in seed.tmdb_component.seed_item_ids:
                assert not _NETFLIX_ID_RE.match(item_id), (
                    f"Netflix ID {item_id} in tmdb_component.seed_item_ids"
                )
            if seed.tmdb_component.eligible_item_ids is not None:
                for item_id in seed.tmdb_component.eligible_item_ids:
                    assert not _NETFLIX_ID_RE.match(item_id), (
                        f"Netflix ID {item_id} in tmdb_component.eligible_item_ids"
                    )

    @given(seed=valid_silver_seed())
    @settings(max_examples=100)
    def test_no_tmdb_ids_in_netflix_components(self, seed: SilverSeed) -> None:
        """No TMDB ID (tmdb:*) appears in Netflix components."""
        if seed.expected_route == "netflix":
            for item_id in seed.seed_item_ids:
                assert not _TMDB_ID_RE.match(item_id), (
                    f"TMDB ID {item_id} in netflix seed_item_ids"
                )
            if seed.eligible_item_ids is not None:
                for item_id in seed.eligible_item_ids:
                    assert not _TMDB_ID_RE.match(item_id), (
                        f"TMDB ID {item_id} in netflix eligible_item_ids"
                    )
        elif seed.expected_route == "both" and seed.netflix_component is not None:
            for item_id in seed.netflix_component.seed_item_ids:
                assert not _TMDB_ID_RE.match(item_id), (
                    f"TMDB ID {item_id} in netflix_component.seed_item_ids"
                )
            if seed.netflix_component.eligible_item_ids is not None:
                for item_id in seed.netflix_component.eligible_item_ids:
                    assert not _TMDB_ID_RE.match(item_id), (
                        f"TMDB ID {item_id} in netflix_component.eligible_item_ids"
                    )


# ---------------------------------------------------------------------------
# Task 7.4 — Unit tests for Validator
# ---------------------------------------------------------------------------


class TestDuplicateCaseId:
    """DUPLICATE_CASE_ID: batch with duplicate case_ids."""

    def test_duplicate_case_id_detected(
        self,
        netflix_titles_csv: Path,
        netflix_credits_csv: Path,
        tmdb_fixture_path: Path,
    ) -> None:
        netflix = NetflixAdapter(netflix_titles_csv, netflix_credits_csv)
        tmdb = TmdbAdapter("v1", tmdb_fixture_path)
        validator = SeedValidator(netflix_adapter=netflix, tmdb_adapter=tmdb)

        seed1 = _trending_seed(case_id="dup-case")
        seed2 = _trending_seed(case_id="dup-case")
        result = validator.validate_batch([seed1, seed2])

        assert not result.is_valid
        dup_errors = [
            e for e in result.errors if e.validation_id == "DUPLICATE_CASE_ID"
        ]
        assert len(dup_errors) >= 1
        assert "dup-case" in dup_errors[0].message


class TestIdNotFound:
    """ID_NOT_FOUND: seed_item_id doesn't exist in datasource."""

    def test_tmdb_id_not_found(
        self,
        netflix_titles_csv: Path,
        netflix_credits_csv: Path,
        tmdb_fixture_path: Path,
    ) -> None:
        netflix = NetflixAdapter(netflix_titles_csv, netflix_credits_csv)
        tmdb = TmdbAdapter("v1", tmdb_fixture_path)
        validator = SeedValidator(netflix_adapter=netflix, tmdb_adapter=tmdb)

        seed = _trending_seed(seed_item_ids=["tmdb:999999"])
        result = validator.validate_batch([seed])

        assert not result.is_valid
        id_errors = [e for e in result.errors if e.validation_id == "ID_NOT_FOUND"]
        assert len(id_errors) >= 1
        assert "tmdb:999999" in id_errors[0].message

    def test_netflix_id_not_found(
        self,
        netflix_titles_csv: Path,
        netflix_credits_csv: Path,
        tmdb_fixture_path: Path,
    ) -> None:
        netflix = NetflixAdapter(netflix_titles_csv, netflix_credits_csv)
        tmdb = TmdbAdapter("v1", tmdb_fixture_path)
        validator = SeedValidator(netflix_adapter=netflix, tmdb_adapter=tmdb)

        seed = _netflix_seed(seed_item_ids=["tm000000"])
        result = validator.validate_batch([seed])

        assert not result.is_valid
        id_errors = [e for e in result.errors if e.validation_id == "ID_NOT_FOUND"]
        assert len(id_errors) >= 1
        assert "tm000000" in id_errors[0].message


class TestConstraintMismatch:
    """CONSTRAINT_MISMATCH: seed_item doesn't satisfy hard constraints."""

    def test_tmdb_constraint_mismatch_year(
        self,
        netflix_titles_csv: Path,
        netflix_credits_csv: Path,
        tmdb_fixture_path: Path,
    ) -> None:
        netflix = NetflixAdapter(netflix_titles_csv, netflix_credits_csv)
        tmdb = TmdbAdapter("v1", tmdb_fixture_path)
        validator = SeedValidator(netflix_adapter=netflix, tmdb_adapter=tmdb)

        # Barbie (tmdb:346698) has release_year=2023, use min_year=2024
        seed = _trending_seed(
            seed_item_ids=["tmdb:346698"],
            hard_constraints=TmdbHardConstraints(min_year=2024),
            eligible_item_ids=["tmdb:1022789"],
        )
        result = validator.validate_batch([seed])

        assert not result.is_valid
        cm_errors = [
            e for e in result.errors if e.validation_id == "CONSTRAINT_MISMATCH"
        ]
        assert len(cm_errors) >= 1

    def test_netflix_constraint_mismatch_type(
        self,
        netflix_titles_csv: Path,
        netflix_credits_csv: Path,
        tmdb_fixture_path: Path,
    ) -> None:
        netflix = NetflixAdapter(netflix_titles_csv, netflix_credits_csv)
        tmdb = TmdbAdapter("v1", tmdb_fixture_path)
        validator = SeedValidator(netflix_adapter=netflix, tmdb_adapter=tmdb)

        # ts22164 is SHOW, constraint says movie
        seed = _netflix_seed(
            seed_item_ids=["ts22164"],
            hard_constraints=NetflixHardConstraints(type="movie"),
            eligible_item_ids=[
                "tm120801",
                "tm154986",
                "tm257064",
                "tm312854",
                "tm70993",
                "tm84618",
            ],
        )
        result = validator.validate_batch([seed])

        assert not result.is_valid
        cm_errors = [
            e for e in result.errors if e.validation_id == "CONSTRAINT_MISMATCH"
        ]
        assert len(cm_errors) >= 1


class TestRouteSourcesMismatch:
    """ROUTE_SOURCES_MISMATCH: expected_sources inconsistent with route."""

    def test_trending_wrong_sources(
        self,
        netflix_titles_csv: Path,
        netflix_credits_csv: Path,
        tmdb_fixture_path: Path,
    ) -> None:
        netflix = NetflixAdapter(netflix_titles_csv, netflix_credits_csv)
        tmdb = TmdbAdapter("v1", tmdb_fixture_path)
        validator = SeedValidator(netflix_adapter=netflix, tmdb_adapter=tmdb)

        # Build using model_construct to bypass pydantic validation
        seed = SilverSeed.model_construct(
            case_id="route-src-1",
            expected_route="trending",
            expected_sources=["netflix"],  # wrong!
            expected_status="SUCCESS",
            hard_constraints=TmdbHardConstraints(min_year=2023),
            semantic_concepts=[],
            seed_item_ids=["tmdb:872585"],
            eligible_item_ids=["tmdb:872585"],
            difficulty="easy",
            tags=[],
            provenance=_base_provenance(),
            fixture_version="v1",
            tmdb_component=None,
            netflix_component=None,
        )
        result = validator.validate_batch([seed])

        assert not result.is_valid
        rs_errors = [
            e for e in result.errors if e.validation_id == "ROUTE_SOURCES_MISMATCH"
        ]
        assert len(rs_errors) >= 1


class TestCrossContamination:
    """CROSS_CONTAMINATION: Netflix IDs in TMDB context or vice versa."""

    def test_netflix_id_in_trending_seed(
        self,
        netflix_titles_csv: Path,
        netflix_credits_csv: Path,
        tmdb_fixture_path: Path,
    ) -> None:
        netflix = NetflixAdapter(netflix_titles_csv, netflix_credits_csv)
        tmdb = TmdbAdapter("v1", tmdb_fixture_path)
        validator = SeedValidator(netflix_adapter=netflix, tmdb_adapter=tmdb)

        seed = SilverSeed.model_construct(
            case_id="cross-1",
            expected_route="trending",
            expected_sources=["tmdb"],
            expected_status="SUCCESS",
            hard_constraints=TmdbHardConstraints(min_year=2023),
            semantic_concepts=[],
            seed_item_ids=["tm84618"],  # Netflix ID in trending!
            eligible_item_ids=["tmdb:872585"],
            difficulty="easy",
            tags=[],
            provenance=_base_provenance(),
            fixture_version="v1",
            tmdb_component=None,
            netflix_component=None,
        )
        result = validator.validate_batch([seed])

        assert not result.is_valid
        cc_errors = [
            e for e in result.errors if e.validation_id == "CROSS_CONTAMINATION"
        ]
        assert len(cc_errors) >= 1

    def test_tmdb_id_in_netflix_seed(
        self,
        netflix_titles_csv: Path,
        netflix_credits_csv: Path,
        tmdb_fixture_path: Path,
    ) -> None:
        netflix = NetflixAdapter(netflix_titles_csv, netflix_credits_csv)
        tmdb = TmdbAdapter("v1", tmdb_fixture_path)
        validator = SeedValidator(netflix_adapter=netflix, tmdb_adapter=tmdb)

        seed = SilverSeed.model_construct(
            case_id="cross-2",
            expected_route="netflix",
            expected_sources=["netflix"],
            expected_status="SUCCESS",
            hard_constraints=NetflixHardConstraints(min_year=2010),
            semantic_concepts=[],
            seed_item_ids=["tmdb:872585"],  # TMDB ID in netflix!
            eligible_item_ids=["tm154986"],
            difficulty="easy",
            tags=[],
            provenance=_base_provenance(source="netflix", fixture_version=None),
            fixture_version=None,
            tmdb_component=None,
            netflix_component=None,
        )
        result = validator.validate_batch([seed])

        assert not result.is_valid
        cc_errors = [
            e for e in result.errors if e.validation_id == "CROSS_CONTAMINATION"
        ]
        assert len(cc_errors) >= 1


class TestSemanticTextEmpty:
    """SEMANTIC_TEXT_EMPTY: seed_item has empty text but seed has semantic_concepts."""

    def test_tmdb_empty_overview(
        self,
        netflix_titles_csv: Path,
        netflix_credits_csv: Path,
        tmdb_fixture_path: Path,
    ) -> None:
        netflix = NetflixAdapter(netflix_titles_csv, netflix_credits_csv)
        tmdb = TmdbAdapter("v1", tmdb_fixture_path)
        validator = SeedValidator(netflix_adapter=netflix, tmdb_adapter=tmdb)

        # Mock get_overview to return empty string for one of the IDs
        original_get_overview = tmdb.get_overview

        def patched_overview(item_id: str) -> str | None:
            if item_id == "tmdb:872585":
                return ""  # empty overview!
            return original_get_overview(item_id)

        tmdb.get_overview = patched_overview  # type: ignore[assignment]

        seed = _trending_seed(
            seed_item_ids=["tmdb:872585"],
            semantic_concepts=["nuclear physics"],
        )
        result = validator.validate_batch([seed])

        assert not result.is_valid
        st_errors = [
            e for e in result.errors if e.validation_id == "SEMANTIC_TEXT_EMPTY"
        ]
        assert len(st_errors) >= 1


class TestFixtureVersionInconsistent:
    """FIXTURE_VERSION_INCONSISTENT: multiple fixture_versions in batch."""

    def test_different_fixture_versions(
        self,
        netflix_titles_csv: Path,
        netflix_credits_csv: Path,
        tmdb_fixture_path: Path,
    ) -> None:
        netflix = NetflixAdapter(netflix_titles_csv, netflix_credits_csv)
        tmdb = TmdbAdapter("v1", tmdb_fixture_path)
        validator = SeedValidator(netflix_adapter=netflix, tmdb_adapter=tmdb)

        seed1 = _trending_seed(case_id="fv-1", fixture_version="v1")
        seed2 = SilverSeed.model_construct(
            case_id="fv-2",
            expected_route="trending",
            expected_sources=["tmdb"],
            expected_status="SUCCESS",
            hard_constraints=TmdbHardConstraints(min_year=2023),
            semantic_concepts=[],
            seed_item_ids=["tmdb:872585"],
            eligible_item_ids=["tmdb:872585"],
            difficulty="easy",
            tags=[],
            provenance=_base_provenance(),
            fixture_version="v2",  # different version!
            tmdb_component=None,
            netflix_component=None,
        )
        result = validator.validate_batch([seed1, seed2])

        assert not result.is_valid
        fv_errors = [
            e
            for e in result.errors
            if e.validation_id == "FIXTURE_VERSION_INCONSISTENT"
        ]
        assert len(fv_errors) >= 1


class TestEligibleMismatch:
    """ELIGIBLE_MISMATCH: eligible_item_ids don't match recalculated filter."""

    def test_tmdb_eligible_mismatch(
        self,
        netflix_titles_csv: Path,
        netflix_credits_csv: Path,
        tmdb_fixture_path: Path,
    ) -> None:
        netflix = NetflixAdapter(netflix_titles_csv, netflix_credits_csv)
        tmdb = TmdbAdapter("v1", tmdb_fixture_path)
        validator = SeedValidator(netflix_adapter=netflix, tmdb_adapter=tmdb)

        # min_year=2023: actual eligible should be tmdb:346698, tmdb:565770,
        # tmdb:872585, tmdb:969681; provide wrong list
        seed = _trending_seed(
            seed_item_ids=["tmdb:872585"],
            hard_constraints=TmdbHardConstraints(min_year=2023),
            eligible_item_ids=["tmdb:872585", "tmdb:000001"],  # extra fake ID
        )
        result = validator.validate_batch([seed])

        assert not result.is_valid
        em_errors = [e for e in result.errors if e.validation_id == "ELIGIBLE_MISMATCH"]
        assert len(em_errors) >= 1

    def test_both_eligible_per_component(
        self,
        netflix_titles_csv: Path,
        netflix_credits_csv: Path,
        tmdb_fixture_path: Path,
    ) -> None:
        """Verify eligible validation per component for route 'both'."""
        netflix = NetflixAdapter(netflix_titles_csv, netflix_credits_csv)
        tmdb = TmdbAdapter("v1", tmdb_fixture_path)
        validator = SeedValidator(netflix_adapter=netflix, tmdb_adapter=tmdb)

        # TMDB component with wrong eligible
        tmdb_component = TmdbSeedComponent(
            fixture_version="v1",
            seed_item_ids=["tmdb:872585"],
            eligible_item_ids=["tmdb:872585", "tmdb:000002"],  # wrong
            hard_constraints=TmdbHardConstraints(min_year=2023),
            semantic_concepts=[],
        )
        netflix_component = NetflixSeedComponent(
            seed_item_ids=["tm154986"],
            eligible_item_ids=["tm154986", "tm257064"],  # could be correct
            hard_constraints=NetflixHardConstraints(min_year=2010),
            semantic_concepts=[],
        )
        seed = _both_seed(
            tmdb_component=tmdb_component,
            netflix_component=netflix_component,
        )
        result = validator.validate_batch([seed])

        assert not result.is_valid
        em_errors = [e for e in result.errors if e.validation_id == "ELIGIBLE_MISMATCH"]
        assert len(em_errors) >= 1


class TestNoResultsEligibleNotEmpty:
    """NO_RESULTS_ELIGIBLE_NOT_EMPTY: NO_RESULTS with non-empty eligible."""

    def test_no_results_with_non_empty_eligible(
        self,
        netflix_titles_csv: Path,
        netflix_credits_csv: Path,
        tmdb_fixture_path: Path,
    ) -> None:
        netflix = NetflixAdapter(netflix_titles_csv, netflix_credits_csv)
        tmdb = TmdbAdapter("v1", tmdb_fixture_path)
        validator = SeedValidator(netflix_adapter=netflix, tmdb_adapter=tmdb)

        seed = SilverSeed.model_construct(
            case_id="nr-notempty-1",
            expected_route="trending",
            expected_sources=["tmdb"],
            expected_status="NO_RESULTS",
            hard_constraints=TmdbHardConstraints(min_year=2050),
            semantic_concepts=[],
            seed_item_ids=[],
            eligible_item_ids=["tmdb:872585"],  # not empty!
            difficulty="easy",
            tags=[],
            provenance=_base_provenance(),
            fixture_version="v1",
            tmdb_component=None,
            netflix_component=None,
        )
        result = validator.validate_batch([seed])

        assert not result.is_valid
        ne_errors = [
            e
            for e in result.errors
            if e.validation_id == "NO_RESULTS_ELIGIBLE_NOT_EMPTY"
        ]
        assert len(ne_errors) >= 1


class TestNoResultsEligibleNone:
    """NO_RESULTS_ELIGIBLE_NONE: NO_RESULTS with eligible=None (should be [])."""

    def test_no_results_with_none_eligible(
        self,
        netflix_titles_csv: Path,
        netflix_credits_csv: Path,
        tmdb_fixture_path: Path,
    ) -> None:
        netflix = NetflixAdapter(netflix_titles_csv, netflix_credits_csv)
        tmdb = TmdbAdapter("v1", tmdb_fixture_path)
        validator = SeedValidator(netflix_adapter=netflix, tmdb_adapter=tmdb)

        seed = SilverSeed.model_construct(
            case_id="nr-none-1",
            expected_route="trending",
            expected_sources=["tmdb"],
            expected_status="NO_RESULTS",
            hard_constraints=TmdbHardConstraints(min_year=2050),
            semantic_concepts=[],
            seed_item_ids=[],
            eligible_item_ids=None,  # should be []
            difficulty="easy",
            tags=[],
            provenance=_base_provenance(),
            fixture_version="v1",
            tmdb_component=None,
            netflix_component=None,
        )
        result = validator.validate_batch([seed])

        assert not result.is_valid
        nn_errors = [
            e for e in result.errors if e.validation_id == "NO_RESULTS_ELIGIBLE_NONE"
        ]
        assert len(nn_errors) >= 1


class TestConstraintTypeMismatch:
    """CONSTRAINT_TYPE_MISMATCH: constraint type incompatible with route."""

    def test_netflix_constraints_on_trending(
        self,
        netflix_titles_csv: Path,
        netflix_credits_csv: Path,
        tmdb_fixture_path: Path,
    ) -> None:
        netflix = NetflixAdapter(netflix_titles_csv, netflix_credits_csv)
        tmdb = TmdbAdapter("v1", tmdb_fixture_path)
        validator = SeedValidator(netflix_adapter=netflix, tmdb_adapter=tmdb)

        # Use model_construct to bypass pydantic model_validators
        seed = SilverSeed.model_construct(
            case_id="ctm-1",
            expected_route="trending",
            expected_sources=["tmdb"],
            expected_status="SUCCESS",
            hard_constraints=NetflixHardConstraints(min_year=2020),  # wrong type!
            semantic_concepts=[],
            seed_item_ids=["tmdb:872585"],
            eligible_item_ids=["tmdb:872585"],
            difficulty="easy",
            tags=[],
            provenance=_base_provenance(),
            fixture_version="v1",
            tmdb_component=None,
            netflix_component=None,
        )
        result = validator.validate_batch([seed])

        assert not result.is_valid
        ct_errors = [
            e for e in result.errors if e.validation_id == "CONSTRAINT_TYPE_MISMATCH"
        ]
        assert len(ct_errors) >= 1


class TestAdapterUnavailable:
    """ADAPTER_UNAVAILABLE: adapter not injected produces error, not exception."""

    def test_no_tmdb_adapter(self) -> None:
        """Validator with None tmdb_adapter reports ADAPTER_UNAVAILABLE."""
        validator = SeedValidator(netflix_adapter=None, tmdb_adapter=None)
        seed = _trending_seed(seed_item_ids=["tmdb:872585"])
        result = validator.validate_batch([seed])

        # Must NOT raise — returns result with error
        assert not result.is_valid
        au_errors = [
            e for e in result.errors if e.validation_id == "ADAPTER_UNAVAILABLE"
        ]
        assert len(au_errors) >= 1

    def test_no_netflix_adapter(self) -> None:
        """Validator with None netflix_adapter reports ADAPTER_UNAVAILABLE."""
        validator = SeedValidator(netflix_adapter=None, tmdb_adapter=None)
        seed = _netflix_seed(seed_item_ids=["tm154986"])
        result = validator.validate_batch([seed])

        assert not result.is_valid
        au_errors = [
            e for e in result.errors if e.validation_id == "ADAPTER_UNAVAILABLE"
        ]
        assert len(au_errors) >= 1


class TestAdapterError:
    """ADAPTER_ERROR: adapter exception doesn't propagate, produces error."""

    def test_tmdb_adapter_exception_captured(
        self,
        netflix_titles_csv: Path,
        netflix_credits_csv: Path,
        tmdb_fixture_path: Path,
    ) -> None:
        """Exception from adapter (e.g., checksum invalid) produces ADAPTER_ERROR."""
        netflix = NetflixAdapter(netflix_titles_csv, netflix_credits_csv)
        tmdb = TmdbAdapter("v1", tmdb_fixture_path)
        validator = SeedValidator(netflix_adapter=netflix, tmdb_adapter=tmdb)

        # Make the adapter's id_exists raise
        def raise_on_check(item_id: str) -> bool:
            raise RuntimeError("Simulated adapter failure")

        tmdb.id_exists = raise_on_check  # type: ignore[assignment]

        seed = _trending_seed(seed_item_ids=["tmdb:872585"])
        # Must NOT raise exception
        result = validator.validate_batch([seed])

        assert not result.is_valid
        ae_errors = [e for e in result.errors if e.validation_id == "ADAPTER_ERROR"]
        assert len(ae_errors) >= 1

    def test_netflix_adapter_exception_captured(
        self,
        netflix_titles_csv: Path,
        netflix_credits_csv: Path,
        tmdb_fixture_path: Path,
    ) -> None:
        """Exception from Netflix adapter produces ADAPTER_ERROR."""
        netflix = NetflixAdapter(netflix_titles_csv, netflix_credits_csv)
        tmdb = TmdbAdapter("v1", tmdb_fixture_path)
        validator = SeedValidator(netflix_adapter=netflix, tmdb_adapter=tmdb)

        def raise_on_check(item_id: str) -> bool:
            raise RuntimeError("Simulated Netflix adapter failure")

        netflix.id_exists = raise_on_check  # type: ignore[assignment]

        seed = _netflix_seed(seed_item_ids=["tm154986"])
        result = validator.validate_batch([seed])

        assert not result.is_valid
        ae_errors = [e for e in result.errors if e.validation_id == "ADAPTER_ERROR"]
        assert len(ae_errors) >= 1


class TestOutOfScopeStatusMismatch:
    """OUT_OF_SCOPE_STATUS_MISMATCH: out_of_scope route with wrong status."""

    def test_out_of_scope_with_success_status(
        self,
        netflix_titles_csv: Path,
        netflix_credits_csv: Path,
        tmdb_fixture_path: Path,
    ) -> None:
        netflix = NetflixAdapter(netflix_titles_csv, netflix_credits_csv)
        tmdb = TmdbAdapter("v1", tmdb_fixture_path)
        validator = SeedValidator(netflix_adapter=netflix, tmdb_adapter=tmdb)

        seed = SilverSeed.model_construct(
            case_id="oos-wrong-1",
            expected_route="out_of_scope",
            expected_sources=[],
            expected_status="SUCCESS",  # wrong for out_of_scope!
            hard_constraints=None,
            semantic_concepts=[],
            seed_item_ids=[],
            eligible_item_ids=None,
            difficulty="easy",
            tags=[],
            provenance=_base_provenance(source="synthetic", fixture_version=None),
            fixture_version=None,
            tmdb_component=None,
            netflix_component=None,
        )
        result = validator.validate_batch([seed])

        assert not result.is_valid
        oos_errors = [
            e
            for e in result.errors
            if e.validation_id == "OUT_OF_SCOPE_STATUS_MISMATCH"
        ]
        assert len(oos_errors) >= 1


# ---------------------------------------------------------------------------
# Additional tests (task 7.4 extra requirements)
# ---------------------------------------------------------------------------


class TestValidatorReportsAllErrors:
    """Verify validator reports ALL errors — doesn't stop at first."""

    def test_seed_with_multiple_problems(
        self,
        netflix_titles_csv: Path,
        netflix_credits_csv: Path,
        tmdb_fixture_path: Path,
    ) -> None:
        netflix = NetflixAdapter(netflix_titles_csv, netflix_credits_csv)
        tmdb = TmdbAdapter("v1", tmdb_fixture_path)
        validator = SeedValidator(netflix_adapter=netflix, tmdb_adapter=tmdb)

        # Build a seed with cross-contamination AND id_not_found AND eligible mismatch
        seed = SilverSeed.model_construct(
            case_id="multi-err-1",
            expected_route="trending",
            expected_sources=["tmdb"],
            expected_status="SUCCESS",
            hard_constraints=TmdbHardConstraints(min_year=2023),
            semantic_concepts=[],
            seed_item_ids=["tm84618", "tmdb:999999"],  # Netflix ID + nonexistent
            eligible_item_ids=["tmdb:000001"],  # wrong
            difficulty="easy",
            tags=[],
            provenance=_base_provenance(),
            fixture_version="v1",
            tmdb_component=None,
            netflix_component=None,
        )
        result = validator.validate_batch([seed])

        assert not result.is_valid
        # Should have at least 3 different error types
        validation_ids = {e.validation_id for e in result.errors}
        assert "CROSS_CONTAMINATION" in validation_ids
        assert "ID_NOT_FOUND" in validation_ids
        assert "ELIGIBLE_MISMATCH" in validation_ids


class TestValidatorNeverRaises:
    """Validator NEVER raises exceptions — always returns ValidationResult."""

    def test_adapter_unavailable_no_exception(self) -> None:
        """With adapter not injected produces ADAPTER_UNAVAILABLE, not exception."""
        validator = SeedValidator(netflix_adapter=None, tmdb_adapter=None)
        seed = _trending_seed()
        # No exception raised
        result = validator.validate_batch([seed])
        assert isinstance(result, ValidationResult)
        assert not result.is_valid

    def test_adapter_error_no_exception(
        self,
        netflix_titles_csv: Path,
        netflix_credits_csv: Path,
        tmdb_fixture_path: Path,
    ) -> None:
        """Adapter exception produces ADAPTER_ERROR, doesn't propagate."""
        netflix = NetflixAdapter(netflix_titles_csv, netflix_credits_csv)
        tmdb = TmdbAdapter("v1", tmdb_fixture_path)
        validator = SeedValidator(netflix_adapter=netflix, tmdb_adapter=tmdb)

        # Make filter raise to trigger ADAPTER_ERROR in eligible check
        def raise_on_filter(constraints: Any) -> list[str]:
            raise ValueError("Simulated checksum invalid")

        tmdb.filter = raise_on_filter  # type: ignore[assignment]

        seed = _trending_seed(
            seed_item_ids=["tmdb:872585"],
            eligible_item_ids=["tmdb:872585"],
        )
        result = validator.validate_batch([seed])
        assert isinstance(result, ValidationResult)
        # Should contain ADAPTER_ERROR
        ae_errors = [e for e in result.errors if e.validation_id == "ADAPTER_ERROR"]
        assert len(ae_errors) >= 1


class TestEligibleValidationBothRoute:
    """Verify eligible validation per component for route 'both'."""

    def test_both_validates_each_component_independently(
        self,
        netflix_titles_csv: Path,
        netflix_credits_csv: Path,
        tmdb_fixture_path: Path,
    ) -> None:
        netflix = NetflixAdapter(netflix_titles_csv, netflix_credits_csv)
        tmdb = TmdbAdapter("v1", tmdb_fixture_path)
        validator = SeedValidator(netflix_adapter=netflix, tmdb_adapter=tmdb)

        # Correct eligible for tmdb, wrong for netflix
        # TMDB: min_year=2023 → eligible includes tmdb:346698, tmdb:565770, etc.
        tmdb_eligible = tmdb.filter(TmdbHardConstraints(min_year=2023))
        tmdb_component = TmdbSeedComponent(
            fixture_version="v1",
            seed_item_ids=["tmdb:872585"],
            eligible_item_ids=tmdb_eligible,
            hard_constraints=TmdbHardConstraints(min_year=2023),
            semantic_concepts=[],
        )
        netflix_component = NetflixSeedComponent(
            seed_item_ids=["tm154986"],
            eligible_item_ids=["tm154986", "tm000000"],  # wrong!
            hard_constraints=NetflixHardConstraints(min_year=2010),
            semantic_concepts=[],
        )
        seed = _both_seed(
            tmdb_component=tmdb_component,
            netflix_component=netflix_component,
        )
        result = validator.validate_batch([seed])

        assert not result.is_valid
        em_errors = [e for e in result.errors if e.validation_id == "ELIGIBLE_MISMATCH"]
        assert len(em_errors) >= 1
        # The error should reference netflix_component context
        assert any("netflix_component" in e.message for e in em_errors)
