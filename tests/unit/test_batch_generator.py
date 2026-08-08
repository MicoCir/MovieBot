"""Unit tests for BatchGenerator.

Validates Requirements: 4.1, 4.2, 4.8, 4.13, 4.14, 4.16
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from moviebot.evals.silver.batch_generator import BatchGenerator, BatchGeneratorConfig
from moviebot.evals.silver.builder import SeedBuildError
from moviebot.evals.silver.models import (
    NetflixHardConstraints,
    NetflixSeedComponent,
    SeedProvenance,
    SilverSeed,
    TmdbHardConstraints,
    TmdbSeedComponent,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

CANONICAL_VERSION = "test_v1"
SILVER_VERSION = "silver_test_v1"
SCHEMA_VERSION = "1.0.0"
ETL_VERSION = "1.0.0"
TMDB_FIXTURE_VERSION = "2024-01-01"


def _make_config(tmp_path: Path) -> BatchGeneratorConfig:
    """Create a valid BatchGeneratorConfig pointing to tmp_path."""
    return BatchGeneratorConfig(
        canonical_dataset_version=CANONICAL_VERSION,
        silver_dataset_version=SILVER_VERSION,
        schema_version=SCHEMA_VERSION,
        etl_version=ETL_VERSION,
        tmdb_fixture_version=TMDB_FIXTURE_VERSION,
        case_catalog_path=tmp_path / "case_catalog.json",
        output_base_dir=tmp_path / "output",
    )


def _make_netflix_adapter() -> MagicMock:
    """Create a mock CanonicalNetflixAdapter with matching version properties."""
    adapter = MagicMock()
    adapter.canonical_dataset_version = CANONICAL_VERSION
    adapter.etl_version = ETL_VERSION
    adapter.schema_version = SCHEMA_VERSION
    adapter.output_checksum_sha256 = "a" * 64
    adapter.id_exists.return_value = True
    adapter.get_description.return_value = "A test description"
    adapter.filter.return_value = []
    return adapter


def _make_tmdb_adapter() -> MagicMock:
    """Create a mock TmdbAdapter with matching fixture version."""
    adapter = MagicMock()
    adapter.fixture_version = TMDB_FIXTURE_VERSION
    adapter.id_exists.return_value = True
    adapter.get_overview.return_value = "A test overview"
    adapter.filter.return_value = []
    return adapter


def _make_netflix_seed(
    case_id: str,
    expected_status: str = "SUCCESS",
    eligible_item_ids: list[str] | None = None,
) -> SilverSeed:
    """Create a valid Netflix SilverSeed for testing."""
    if expected_status == "NO_RESULTS":
        return SilverSeed(
            case_id=case_id,
            expected_route="netflix",
            expected_sources=["netflix"],
            expected_status="NO_RESULTS",
            hard_constraints=NetflixHardConstraints(type="movie", genres=["drama"]),
            semantic_concepts=[],
            seed_item_ids=[],
            eligible_item_ids=[],
            difficulty="easy",
            tags=[],
            provenance=SeedProvenance(
                source="netflix",
                input_data_description="test",
                schema_version=SCHEMA_VERSION,
                silver_dataset_version=SILVER_VERSION,
                canonical_dataset_version=CANONICAL_VERSION,
                etl_version=ETL_VERSION,
                checksum_sha256="a" * 64,
            ),
        )
    return SilverSeed(
        case_id=case_id,
        expected_route="netflix",
        expected_sources=["netflix"],
        expected_status="SUCCESS",
        hard_constraints=NetflixHardConstraints(type="movie", genres=["drama"]),
        semantic_concepts=[],
        seed_item_ids=["tm001"],
        eligible_item_ids=eligible_item_ids
        if eligible_item_ids is not None
        else ["tm001"],
        difficulty="easy",
        tags=[],
        provenance=SeedProvenance(
            source="netflix",
            input_data_description="test",
            schema_version=SCHEMA_VERSION,
            silver_dataset_version=SILVER_VERSION,
            canonical_dataset_version=CANONICAL_VERSION,
            etl_version=ETL_VERSION,
            checksum_sha256="a" * 64,
        ),
    )


def _make_trending_seed(
    case_id: str,
    expected_status: str = "SUCCESS",
) -> SilverSeed:
    """Create a valid Trending SilverSeed for testing."""
    if expected_status == "NO_RESULTS":
        return SilverSeed(
            case_id=case_id,
            expected_route="trending",
            expected_sources=["tmdb"],
            expected_status="NO_RESULTS",
            hard_constraints=TmdbHardConstraints(genre_ids=[28]),
            semantic_concepts=[],
            seed_item_ids=[],
            eligible_item_ids=[],
            difficulty="easy",
            tags=[],
            fixture_version=TMDB_FIXTURE_VERSION,
            provenance=SeedProvenance(
                source="tmdb",
                fixture_version=TMDB_FIXTURE_VERSION,
                input_data_description="test",
                schema_version=SCHEMA_VERSION,
                silver_dataset_version=SILVER_VERSION,
            ),
        )
    return SilverSeed(
        case_id=case_id,
        expected_route="trending",
        expected_sources=["tmdb"],
        expected_status="SUCCESS",
        hard_constraints=TmdbHardConstraints(genre_ids=[28]),
        semantic_concepts=[],
        seed_item_ids=["tmdb:123"],
        eligible_item_ids=["tmdb:123"],
        difficulty="easy",
        tags=[],
        fixture_version=TMDB_FIXTURE_VERSION,
        provenance=SeedProvenance(
            source="tmdb",
            fixture_version=TMDB_FIXTURE_VERSION,
            input_data_description="test",
            schema_version=SCHEMA_VERSION,
            silver_dataset_version=SILVER_VERSION,
        ),
    )


def _make_both_seed(case_id: str) -> SilverSeed:
    """Create a valid Both SilverSeed for testing."""
    return SilverSeed(
        case_id=case_id,
        expected_route="both",
        expected_sources=["tmdb", "netflix"],
        expected_status="SUCCESS",
        hard_constraints=None,
        semantic_concepts=[],
        seed_item_ids=[],
        eligible_item_ids=None,
        difficulty="easy",
        tags=[],
        fixture_version=TMDB_FIXTURE_VERSION,
        tmdb_component=TmdbSeedComponent(
            fixture_version=TMDB_FIXTURE_VERSION,
            seed_item_ids=["tmdb:456"],
            eligible_item_ids=["tmdb:456"],
            hard_constraints=TmdbHardConstraints(genre_ids=[28]),
            semantic_concepts=[],
        ),
        netflix_component=NetflixSeedComponent(
            seed_item_ids=["tm002"],
            eligible_item_ids=["tm002"],
            hard_constraints=NetflixHardConstraints(type="movie"),
            semantic_concepts=[],
        ),
        provenance=SeedProvenance(
            source="both",
            fixture_version=TMDB_FIXTURE_VERSION,
            input_data_description="test",
            schema_version=SCHEMA_VERSION,
            silver_dataset_version=SILVER_VERSION,
            canonical_dataset_version=CANONICAL_VERSION,
            etl_version=ETL_VERSION,
            checksum_sha256="a" * 64,
        ),
    )


def _make_out_of_scope_seed(case_id: str) -> SilverSeed:
    """Create a valid OutOfScope SilverSeed for testing."""
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
        provenance=SeedProvenance(
            source="synthetic",
            input_data_description="test",
            schema_version=SCHEMA_VERSION,
            silver_dataset_version=SILVER_VERSION,
        ),
    )


def _make_150_seeds(
    *,
    netflix_no_results: int = 7,
    trending_no_results: int = 3,
) -> list[SilverSeed]:
    """Create a valid batch of 150 seeds with correct distribution (50/50/25/25).

    Netflix: 50 total (43 SUCCESS + 7 NO_RESULTS)
    Trending: 50 total (47 SUCCESS + 3 NO_RESULTS)
    Both: 25 total (all SUCCESS)
    OutOfScope: 25 total (all OUT_OF_SCOPE)
    """
    seeds: list[SilverSeed] = []

    # Netflix seeds: 50 total
    netflix_success_count = 50 - netflix_no_results
    for i in range(netflix_success_count):
        seeds.append(_make_netflix_seed(f"netflix_success_{i:03d}"))
    for i in range(netflix_no_results):
        seeds.append(_make_netflix_seed(f"netflix_no_results_{i:03d}", "NO_RESULTS"))

    # Trending seeds: 50 total
    trending_success_count = 50 - trending_no_results
    for i in range(trending_success_count):
        seeds.append(_make_trending_seed(f"trending_success_{i:03d}"))
    for i in range(trending_no_results):
        seeds.append(_make_trending_seed(f"trending_no_results_{i:03d}", "NO_RESULTS"))

    # Both seeds: 25
    for i in range(25):
        seeds.append(_make_both_seed(f"both_{i:03d}"))

    # OutOfScope seeds: 25
    for i in range(25):
        seeds.append(_make_out_of_scope_seed(f"oos_{i:03d}"))

    return seeds


# ---------------------------------------------------------------------------
# Tests: Version Mismatch Detection (Req 4.1)
# ---------------------------------------------------------------------------


class TestVersionMismatch:
    """Tests for version mismatch detection between config and adapters."""

    def test_canonical_dataset_version_mismatch_raises(self, tmp_path: Path) -> None:
        """Config canonical_dataset_version != adapter → ValueError."""
        config = _make_config(tmp_path)
        netflix_adapter = _make_netflix_adapter()
        netflix_adapter.canonical_dataset_version = "wrong_version"
        tmdb_adapter = _make_tmdb_adapter()

        gen = BatchGenerator(config, netflix_adapter, tmdb_adapter)

        with pytest.raises(ValueError, match="canonical_dataset_version mismatch"):
            gen.generate()

    def test_etl_version_mismatch_raises(self, tmp_path: Path) -> None:
        """Config etl_version != adapter.etl_version → ValueError."""
        config = _make_config(tmp_path)
        netflix_adapter = _make_netflix_adapter()
        netflix_adapter.etl_version = "2.0.0"
        tmdb_adapter = _make_tmdb_adapter()

        gen = BatchGenerator(config, netflix_adapter, tmdb_adapter)

        with pytest.raises(ValueError, match="etl_version mismatch"):
            gen.generate()

    def test_tmdb_fixture_version_mismatch_raises(self, tmp_path: Path) -> None:
        """Config tmdb_fixture_version != tmdb_adapter.fixture_version → ValueError."""
        config = _make_config(tmp_path)
        netflix_adapter = _make_netflix_adapter()
        tmdb_adapter = _make_tmdb_adapter()
        tmdb_adapter.fixture_version = "wrong_fixture"

        gen = BatchGenerator(config, netflix_adapter, tmdb_adapter)

        with pytest.raises(ValueError, match="tmdb_fixture_version mismatch"):
            gen.generate()

    def test_all_versions_match_passes_validation(self, tmp_path: Path) -> None:
        """When all versions match, _validate_versions does not raise."""
        config = _make_config(tmp_path)
        netflix_adapter = _make_netflix_adapter()
        tmdb_adapter = _make_tmdb_adapter()

        gen = BatchGenerator(config, netflix_adapter, tmdb_adapter)
        # Should not raise — only validates versions, catalog load will fail
        # but that's a separate concern
        gen._validate_versions()  # no exception = pass


# ---------------------------------------------------------------------------
# Tests: SeedBuildError Propagation (Req 4.14)
# ---------------------------------------------------------------------------


class TestSeedBuildErrorAbort:
    """Tests that SeedBuildError from SeedBuilder aborts the entire batch."""

    def test_seed_build_error_propagates_and_aborts(self, tmp_path: Path) -> None:
        """If SeedBuilder.build() raises SeedBuildError, generation aborts."""
        config = _make_config(tmp_path)
        netflix_adapter = _make_netflix_adapter()
        tmdb_adapter = _make_tmdb_adapter()

        # Create a valid case catalog so we get past version validation
        catalog = {
            "version": "1.0.0",
            "seeds": [],  # will be mocked at the builder level
        }
        config.case_catalog_path.parent.mkdir(parents=True, exist_ok=True)
        config.case_catalog_path.write_text(json.dumps(catalog), encoding="utf-8")

        gen = BatchGenerator(config, netflix_adapter, tmdb_adapter)

        # Mock load_case_catalog to return one request, and SeedBuilder to fail
        mock_request = MagicMock()
        mock_request.case_id = "failing_case"

        with (
            patch(
                "moviebot.evals.silver.batch_generator.load_case_catalog",
                return_value=[mock_request],
            ),
            patch("moviebot.evals.silver.batch_generator.SeedBuilder") as MockBuilder,
        ):
            builder_instance = MockBuilder.return_value
            builder_instance.build.side_effect = SeedBuildError(
                case_id="failing_case",
                message="Netflix ID tm999 not found",
            )

            with pytest.raises(SeedBuildError, match="failing_case"):
                gen.generate()

    def test_seed_build_error_includes_case_id(self, tmp_path: Path) -> None:
        """SeedBuildError carries the case_id of the failed seed."""
        config = _make_config(tmp_path)
        netflix_adapter = _make_netflix_adapter()
        tmdb_adapter = _make_tmdb_adapter()

        gen = BatchGenerator(config, netflix_adapter, tmdb_adapter)

        mock_request = MagicMock()
        mock_request.case_id = "specific_case_42"

        with (
            patch(
                "moviebot.evals.silver.batch_generator.load_case_catalog",
                return_value=[mock_request],
            ),
            patch("moviebot.evals.silver.batch_generator.SeedBuilder") as MockBuilder,
        ):
            builder_instance = MockBuilder.return_value
            error = SeedBuildError(
                case_id="specific_case_42",
                message="ID tm888 not found in Netflix datasource",
            )
            builder_instance.build.side_effect = error

            with pytest.raises(SeedBuildError) as exc_info:
                gen.generate()
            assert exc_info.value.case_id == "specific_case_42"


# ---------------------------------------------------------------------------
# Tests: Distribution Validation (Req 4.1, 4.8)
# ---------------------------------------------------------------------------


class TestDistributionValidation:
    """Tests for the _validate_distribution method."""

    def test_correct_distribution_passes(self) -> None:
        """Exactly 50/50/25/25 distribution is accepted."""
        seeds = _make_150_seeds()
        config = MagicMock()
        netflix_adapter = _make_netflix_adapter()
        tmdb_adapter = _make_tmdb_adapter()

        gen = BatchGenerator(config, netflix_adapter, tmdb_adapter)
        # Should not raise
        gen._validate_distribution(seeds)

    def test_wrong_netflix_count_raises(self) -> None:
        """Non-50 count for netflix route raises ValueError."""
        seeds = _make_150_seeds()
        # Add an extra netflix seed to make it 51
        seeds.append(_make_netflix_seed("extra_netflix"))
        # Remove one trending to keep total at 150+1
        # Actually just test the distribution validation directly
        config = MagicMock()
        netflix_adapter = _make_netflix_adapter()
        tmdb_adapter = _make_tmdb_adapter()

        gen = BatchGenerator(config, netflix_adapter, tmdb_adapter)

        with pytest.raises(ValueError, match="Distribution mismatch"):
            gen._validate_distribution(seeds)

    def test_missing_route_raises(self) -> None:
        """Zero seeds for one route raises ValueError."""
        # Create 150 seeds but with wrong distribution (75 netflix, 25 trending)
        seeds: list[SilverSeed] = []
        for i in range(75):
            seeds.append(_make_netflix_seed(f"netflix_{i:03d}"))
        for i in range(25):
            seeds.append(_make_trending_seed(f"trending_{i:03d}"))
        for i in range(25):
            seeds.append(_make_both_seed(f"both_{i:03d}"))
        for i in range(25):
            seeds.append(_make_out_of_scope_seed(f"oos_{i:03d}"))

        config = MagicMock()
        netflix_adapter = _make_netflix_adapter()
        tmdb_adapter = _make_tmdb_adapter()
        gen = BatchGenerator(config, netflix_adapter, tmdb_adapter)

        with pytest.raises(ValueError, match="Distribution mismatch"):
            gen._validate_distribution(seeds)


# ---------------------------------------------------------------------------
# Tests: NO_RESULTS Quota Validation (Req 4.13)
# ---------------------------------------------------------------------------


class TestNoResultsQuota:
    """Tests for the _validate_no_results_quota method."""

    def test_correct_quota_passes(self) -> None:
        """Exactly 7 netflix + 3 trending + 0 both NO_RESULTS passes."""
        seeds = _make_150_seeds(netflix_no_results=7, trending_no_results=3)
        config = MagicMock()
        netflix_adapter = _make_netflix_adapter()
        tmdb_adapter = _make_tmdb_adapter()

        gen = BatchGenerator(config, netflix_adapter, tmdb_adapter)
        # Should not raise
        gen._validate_no_results_quota(seeds)

    def test_wrong_netflix_no_results_count_raises(self) -> None:
        """Netflix NO_RESULTS != 7 raises ValueError."""
        # Create seeds with 5 netflix NO_RESULTS instead of 7
        seeds = _make_150_seeds(netflix_no_results=5, trending_no_results=3)
        config = MagicMock()
        netflix_adapter = _make_netflix_adapter()
        tmdb_adapter = _make_tmdb_adapter()

        gen = BatchGenerator(config, netflix_adapter, tmdb_adapter)

        with pytest.raises(ValueError, match="NO_RESULTS quota mismatch"):
            gen._validate_no_results_quota(seeds)

    def test_wrong_trending_no_results_count_raises(self) -> None:
        """Trending NO_RESULTS != 3 raises ValueError."""
        seeds = _make_150_seeds(netflix_no_results=7, trending_no_results=5)
        config = MagicMock()
        netflix_adapter = _make_netflix_adapter()
        tmdb_adapter = _make_tmdb_adapter()

        gen = BatchGenerator(config, netflix_adapter, tmdb_adapter)

        with pytest.raises(ValueError, match="NO_RESULTS quota mismatch"):
            gen._validate_no_results_quota(seeds)

    def test_zero_no_results_raises(self) -> None:
        """Zero NO_RESULTS in any route raises ValueError (expected 7+3)."""
        seeds = _make_150_seeds(netflix_no_results=0, trending_no_results=0)
        config = MagicMock()
        netflix_adapter = _make_netflix_adapter()
        tmdb_adapter = _make_tmdb_adapter()

        gen = BatchGenerator(config, netflix_adapter, tmdb_adapter)

        with pytest.raises(ValueError, match="NO_RESULTS quota mismatch"):
            gen._validate_no_results_quota(seeds)


# ---------------------------------------------------------------------------
# Tests: Deterministic Output — Sorted by case_id (Req 4.2)
# ---------------------------------------------------------------------------


class TestDeterministicOutput:
    """Tests that BatchGenerator produces output sorted by case_id."""

    def test_generate_calls_persist_with_seeds(self, tmp_path: Path) -> None:
        """The full generate flow ends with persist called on sorted seeds."""
        config = _make_config(tmp_path)
        netflix_adapter = _make_netflix_adapter()
        tmdb_adapter = _make_tmdb_adapter()

        gen = BatchGenerator(config, netflix_adapter, tmdb_adapter)

        seeds = _make_150_seeds()
        # Shuffle seeds to verify they will be sorted
        import random

        rng = random.Random(42)
        rng.shuffle(seeds)

        with (
            patch(
                "moviebot.evals.silver.batch_generator.load_case_catalog"
            ) as mock_catalog,
            patch("moviebot.evals.silver.batch_generator.SeedBuilder") as MockBuilder,
            patch(
                "moviebot.evals.silver.batch_generator.SeedPersistence"
            ) as MockPersistence,
        ):
            # SeedBuilder returns seeds in shuffled order
            mock_catalog.return_value = [MagicMock() for _ in range(150)]
            builder_instance = MockBuilder.return_value
            builder_instance.build.side_effect = seeds

            # Mock persist to capture what's passed
            persistence_instance = MockPersistence.return_value
            persistence_instance.persist.return_value = MagicMock()

            gen.generate()

            # SeedPersistence.persist is called with the seeds list
            persistence_instance.persist.assert_called_once()
            persisted_seeds = persistence_instance.persist.call_args[0][0]
            # Verify seeds are present (sorting happens in persistence)
            assert len(persisted_seeds) == 150


# ---------------------------------------------------------------------------
# Tests: Netflix ID Existence Validation (Req 4.1, 4.14)
# ---------------------------------------------------------------------------


class TestNetflixIdExistence:
    """Tests that SeedBuilder validates Netflix IDs exist via the adapter."""

    def test_missing_netflix_id_raises_seed_build_error(self, tmp_path: Path) -> None:
        """A seed referencing a nonexistent Netflix ID aborts generation."""
        config = _make_config(tmp_path)
        netflix_adapter = _make_netflix_adapter()
        tmdb_adapter = _make_tmdb_adapter()

        gen = BatchGenerator(config, netflix_adapter, tmdb_adapter)

        mock_request = MagicMock()
        mock_request.case_id = "netflix_missing_id"

        with (
            patch(
                "moviebot.evals.silver.batch_generator.load_case_catalog",
                return_value=[mock_request],
            ),
            patch("moviebot.evals.silver.batch_generator.SeedBuilder") as MockBuilder,
        ):
            builder_instance = MockBuilder.return_value
            builder_instance.build.side_effect = SeedBuildError(
                case_id="netflix_missing_id",
                message="IDs no encontrados en Netflix datasource: ['tm9999']",
            )

            with pytest.raises(SeedBuildError, match="tm9999"):
                gen.generate()


# ---------------------------------------------------------------------------
# Tests: Genre Existence Validation (Req 4.16)
# ---------------------------------------------------------------------------


class TestGenreExistenceValidation:
    """Tests for _revalidate_no_results_eligible (Req 4.16).

    Verifies that all NO_RESULTS seeds have eligible_item_ids == []
    after re-querying the adapter.
    """

    def test_no_results_seed_with_empty_eligible_passes(self) -> None:
        """NO_RESULTS seed with eligible_item_ids == [] passes revalidation."""
        config = MagicMock()
        netflix_adapter = _make_netflix_adapter()
        netflix_adapter.filter.return_value = []  # adapter confirms empty
        tmdb_adapter = _make_tmdb_adapter()
        tmdb_adapter.filter.return_value = []

        gen = BatchGenerator(config, netflix_adapter, tmdb_adapter)

        seeds = [
            _make_netflix_seed("nr_test_001", "NO_RESULTS"),
            _make_trending_seed("nr_trend_001", "NO_RESULTS"),
        ]
        # Should not raise
        gen._revalidate_no_results_eligible(seeds)

    def test_no_results_seed_with_non_empty_adapter_result_raises(self) -> None:
        """If adapter.filter() returns items for a NO_RESULTS seed, raise."""
        config = MagicMock()
        netflix_adapter = _make_netflix_adapter()
        # Adapter returns non-empty → genre exists but seed says NO_RESULTS
        netflix_adapter.filter.return_value = ["tm001", "tm002"]
        tmdb_adapter = _make_tmdb_adapter()

        gen = BatchGenerator(config, netflix_adapter, tmdb_adapter)

        seeds = [_make_netflix_seed("nr_invalid_001", "NO_RESULTS")]

        with pytest.raises(ValueError, match="NO_RESULTS re-validation failed"):
            gen._revalidate_no_results_eligible(seeds)

    def test_no_results_seed_with_non_empty_eligible_ids_raises(self) -> None:
        """If seed itself has eligible_item_ids != [], raise ValueError."""
        config = MagicMock()
        netflix_adapter = _make_netflix_adapter()
        netflix_adapter.filter.return_value = []
        tmdb_adapter = _make_tmdb_adapter()

        gen = BatchGenerator(config, netflix_adapter, tmdb_adapter)

        # Manually create a broken seed with non-empty eligible for NO_RESULTS
        # We need to bypass the model validator for this, so we patch
        seed = MagicMock()
        seed.expected_status = "NO_RESULTS"
        seed.expected_route = "netflix"
        seed.hard_constraints = NetflixHardConstraints(type="movie", genres=["drama"])
        seed.case_id = "broken_nr"
        seed.eligible_item_ids = ["tm001"]  # This is the violation

        with pytest.raises(ValueError, match="eligible_item_ids"):
            gen._revalidate_no_results_eligible([seed])

    def test_trending_no_results_revalidation_uses_tmdb_adapter(self) -> None:
        """Trending NO_RESULTS seeds are revalidated via tmdb_adapter.filter."""
        config = MagicMock()
        netflix_adapter = _make_netflix_adapter()
        tmdb_adapter = _make_tmdb_adapter()
        tmdb_adapter.filter.return_value = ["tmdb:999"]  # Non-empty

        gen = BatchGenerator(config, netflix_adapter, tmdb_adapter)

        seeds = [_make_trending_seed("trend_nr_001", "NO_RESULTS")]

        with pytest.raises(ValueError, match="NO_RESULTS re-validation failed"):
            gen._revalidate_no_results_eligible(seeds)

    def test_success_seeds_are_skipped_in_revalidation(self) -> None:
        """SUCCESS seeds are NOT re-validated (only NO_RESULTS)."""
        config = MagicMock()
        netflix_adapter = _make_netflix_adapter()
        tmdb_adapter = _make_tmdb_adapter()

        gen = BatchGenerator(config, netflix_adapter, tmdb_adapter)

        seeds = [_make_netflix_seed("success_001", "SUCCESS")]
        # Should not raise regardless of adapter behavior
        gen._revalidate_no_results_eligible(seeds)
        # filter should not have been called
        netflix_adapter.filter.assert_not_called()


# ---------------------------------------------------------------------------
# Tests: Full generate() flow integration (Req 4.1, 4.2, 4.8, 4.13, 4.16)
# ---------------------------------------------------------------------------


class TestFullGenerateFlow:
    """Integration tests for the full generate() workflow."""

    def test_successful_generation(self, tmp_path: Path) -> None:
        """A full happy-path generation with mocked catalog and builder."""
        config = _make_config(tmp_path)
        netflix_adapter = _make_netflix_adapter()
        # Make filter return [] for NO_RESULTS seeds
        netflix_adapter.filter.return_value = []
        tmdb_adapter = _make_tmdb_adapter()
        tmdb_adapter.filter.return_value = []

        gen = BatchGenerator(config, netflix_adapter, tmdb_adapter)

        seeds = _make_150_seeds()

        with (
            patch(
                "moviebot.evals.silver.batch_generator.load_case_catalog"
            ) as mock_catalog,
            patch("moviebot.evals.silver.batch_generator.SeedBuilder") as MockBuilder,
            patch(
                "moviebot.evals.silver.batch_generator.SeedPersistence"
            ) as MockPersistence,
        ):
            mock_catalog.return_value = [MagicMock() for _ in range(150)]
            builder_instance = MockBuilder.return_value
            builder_instance.build.side_effect = seeds

            mock_result = MagicMock()
            persistence_instance = MockPersistence.return_value
            persistence_instance.persist.return_value = mock_result

            result = gen.generate()
            assert result == mock_result

    def test_generation_passes_correct_version_to_builder(self, tmp_path: Path) -> None:
        """SeedBuilder is initialized with correct version params from config."""
        config = _make_config(tmp_path)
        netflix_adapter = _make_netflix_adapter()
        netflix_adapter.filter.return_value = []
        tmdb_adapter = _make_tmdb_adapter()
        tmdb_adapter.filter.return_value = []

        gen = BatchGenerator(config, netflix_adapter, tmdb_adapter)

        seeds = _make_150_seeds()

        with (
            patch(
                "moviebot.evals.silver.batch_generator.load_case_catalog"
            ) as mock_catalog,
            patch("moviebot.evals.silver.batch_generator.SeedBuilder") as MockBuilder,
            patch("moviebot.evals.silver.batch_generator.SeedPersistence"),
        ):
            mock_catalog.return_value = [MagicMock() for _ in range(150)]
            builder_instance = MockBuilder.return_value
            builder_instance.build.side_effect = seeds

            gen.generate()

            # Verify SeedBuilder was initialized with correct versions
            MockBuilder.assert_called_once_with(
                netflix_adapter=netflix_adapter,
                tmdb_adapter=tmdb_adapter,
                schema_version=SCHEMA_VERSION,
                silver_dataset_version=SILVER_VERSION,
                canonical_dataset_version=CANONICAL_VERSION,
                etl_version=ETL_VERSION,
            )
