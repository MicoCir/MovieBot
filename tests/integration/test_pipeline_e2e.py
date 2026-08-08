# tests/integration/test_pipeline_e2e.py
"""Integration test: ETL → CanonicalNetflixAdapter → SeedBuilder roundtrip.

Verifies the full pipeline from raw CSVs through to seed construction,
including provenance fields and eligible_item_ids correctness.

Run with: pytest -m integration tests/integration/test_pipeline_e2e.py

Validates: Requirements 3.7, 4.5, 4.6, 7.1, 7.5
"""

from __future__ import annotations

import csv
from pathlib import Path

import pytest

from moviebot.etl.netflix_etl import EtlConfig, NetflixEtl
from moviebot.evals.silver.adapters import CanonicalNetflixAdapter
from moviebot.evals.silver.builder import (
    NetflixSeedBuildRequest,
    SeedBuilder,
)
from moviebot.evals.silver.models import NetflixHardConstraints

pytestmark = pytest.mark.integration


# ---------------------------------------------------------------------------
# Helpers — Fixture CSV generation
# ---------------------------------------------------------------------------

TITLES_HEADER = [
    "id",
    "title",
    "type",
    "release_year",
    "description",
    "age_certification",
    "genres",
    "imdb_score",
    "tmdb_score",
    "tmdb_popularity",
]

CREDITS_HEADER = ["id", "role", "person_id", "name", "character"]


def _write_csv(path: Path, header: list[str], rows: list[list[str]]) -> None:
    """Write a CSV file with proper quoting."""
    with open(path, "w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(header)
        for row in rows:
            writer.writerow(row)


def _create_fixture_csvs(base_dir: Path) -> tuple[Path, Path]:
    """Create fixture CSVs with known, deterministic content.

    Titles:
    - tm100: Action/Drama movie, 2020, score 8.0
    - tm200: Comedy movie, 2019, score 6.5
    - tm300: Drama/Thriller show, 2021, score 9.0
    - tm400: Action movie, 2018, score 7.0
    - tm500: Drama movie, 2022, score 5.5

    Credits:
    - tm100: actors=[alice smith, bob jones], directors=[carol white]
    - tm200: actors=[alice smith], directors=[dave brown]
    - tm300: actors=[eve green, frank black], directors=[carol white]
    - tm400: actors=[bob jones], directors=[grace lee]
    - tm500: actors=[alice smith, eve green], directors=[dave brown]
    """
    titles_path = base_dir / "titles.csv"
    credits_path = base_dir / "credits.csv"

    titles_rows = [
        [
            "tm100",
            "Action Drama Film",
            "MOVIE",
            "2020",
            "An action drama film.",
            "PG-13",
            "['Action', 'Drama']",
            "8.0",
            "7.5",
            "100.0",
        ],
        [
            "tm200",
            "Comedy Gold",
            "MOVIE",
            "2019",
            "A hilarious comedy.",
            "R",
            "['Comedy']",
            "6.5",
            "6.0",
            "50.0",
        ],
        [
            "tm300",
            "Thriller Series",
            "SHOW",
            "2021",
            "A gripping thriller.",
            "TV-MA",
            "['Drama', 'Thriller']",
            "9.0",
            "8.5",
            "200.0",
        ],
        [
            "tm400",
            "Action Blast",
            "MOVIE",
            "2018",
            "Pure action.",
            "PG-13",
            "['Action']",
            "7.0",
            "6.8",
            "80.0",
        ],
        [
            "tm500",
            "Drama Piece",
            "MOVIE",
            "2022",
            "A thoughtful drama.",
            "",
            "['Drama']",
            "5.5",
            "5.0",
            "30.0",
        ],
    ]

    credits_rows = [
        # tm100 actors
        ["tm100", "ACTOR", "p1", "Alice Smith", "Lead"],
        ["tm100", "ACTOR", "p2", "Bob Jones", "Villain"],
        # tm100 directors
        ["tm100", "DIRECTOR", "p3", "Carol White", ""],
        # tm200 actors
        ["tm200", "ACTOR", "p1", "Alice Smith", "Comedian"],
        # tm200 directors
        ["tm200", "DIRECTOR", "p4", "Dave Brown", ""],
        # tm300 actors
        ["tm300", "ACTOR", "p5", "Eve Green", "Detective"],
        ["tm300", "ACTOR", "p6", "Frank Black", "Suspect"],
        # tm300 directors
        ["tm300", "DIRECTOR", "p3", "Carol White", ""],
        # tm400 actors
        ["tm400", "ACTOR", "p2", "Bob Jones", "Hero"],
        # tm400 directors
        ["tm400", "DIRECTOR", "p7", "Grace Lee", ""],
        # tm500 actors
        ["tm500", "ACTOR", "p1", "Alice Smith", "Narrator"],
        ["tm500", "ACTOR", "p5", "Eve Green", "Supporting"],
        # tm500 directors
        ["tm500", "DIRECTOR", "p4", "Dave Brown", ""],
    ]

    _write_csv(titles_path, TITLES_HEADER, titles_rows)
    _write_csv(credits_path, CREDITS_HEADER, credits_rows)

    return titles_path, credits_path


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def pipeline_output(tmp_path: Path) -> tuple[Path, EtlConfig]:
    """Run ETL on fixture CSVs and return output directory and config."""
    titles_path, credits_path = _create_fixture_csvs(tmp_path)

    config = EtlConfig(
        titles_path=titles_path,
        credits_path=credits_path,
        output_base_dir=tmp_path / "processed",
        canonical_dataset_version="test_v1",
        etl_version="1.0.0",
        schema_version="1.0.0",
    )

    etl = NetflixEtl(config)
    result = etl.run()

    return result.output_dir, config


@pytest.fixture()
def adapter(pipeline_output: tuple[Path, EtlConfig]) -> CanonicalNetflixAdapter:
    """Load canonical dataset via CanonicalNetflixAdapter."""
    _output_dir, config = pipeline_output
    return CanonicalNetflixAdapter(
        canonical_dataset_version=config.canonical_dataset_version,
        base_dir=config.output_base_dir,
    )


@pytest.fixture()
def seed_builder(adapter: CanonicalNetflixAdapter) -> SeedBuilder:
    """Create a SeedBuilder with the canonical adapter."""
    return SeedBuilder(
        netflix_adapter=adapter,
        schema_version="1.0.0",
        silver_dataset_version="silver_test_v1",
        canonical_dataset_version=adapter.canonical_dataset_version,
        etl_version=adapter.etl_version,
    )


# ---------------------------------------------------------------------------
# Tests: ETL output → Adapter loading
# ---------------------------------------------------------------------------


class TestEtlToAdapterRoundtrip:
    """Verify that ETL output is correctly loaded by CanonicalNetflixAdapter."""

    def test_adapter_loads_all_titles(self, adapter: CanonicalNetflixAdapter) -> None:
        """All 5 titles from fixture CSVs are loaded."""
        for tid in ["tm100", "tm200", "tm300", "tm400", "tm500"]:
            assert adapter.id_exists(tid), f"Title {tid} should exist"

    def test_adapter_metadata_matches_etl_config(
        self, adapter: CanonicalNetflixAdapter
    ) -> None:
        """Adapter exposes correct version info from ETL metadata."""
        assert adapter.canonical_dataset_version == "test_v1"
        assert adapter.etl_version == "1.0.0"
        assert adapter.schema_version == "1.0.0"
        # Checksum is a 64-char hex string
        assert len(adapter.output_checksum_sha256) == 64

    def test_actors_normalized_and_joined(
        self, adapter: CanonicalNetflixAdapter
    ) -> None:
        """Actors are normalized (lowercase, trimmed) and correctly joined."""
        actors_100 = adapter.get_actors_for_title("tm100")
        assert "alice smith" in actors_100
        assert "bob jones" in actors_100

        actors_300 = adapter.get_actors_for_title("tm300")
        assert "eve green" in actors_300
        assert "frank black" in actors_300

    def test_directors_normalized_and_joined(
        self, adapter: CanonicalNetflixAdapter
    ) -> None:
        """Directors are normalized (lowercase, trimmed) and correctly joined."""
        directors_100 = adapter.get_directors_for_title("tm100")
        assert directors_100 == ["carol white"]

        directors_200 = adapter.get_directors_for_title("tm200")
        assert directors_200 == ["dave brown"]

    def test_genres_normalized_and_sorted(
        self, adapter: CanonicalNetflixAdapter
    ) -> None:
        """Genres are lowercase and alphabetically sorted."""
        title = adapter.get_title("tm100")
        assert title is not None
        assert title.genres == ["action", "drama"]

        title_300 = adapter.get_title("tm300")
        assert title_300 is not None
        assert title_300.genres == ["drama", "thriller"]


# ---------------------------------------------------------------------------
# Tests: Provenance fields in seeds (Req 3.7)
# ---------------------------------------------------------------------------


class TestProvenanceFields:
    """Verify that seeds built via SeedBuilder contain correct provenance."""

    def test_provenance_contains_canonical_dataset_version(
        self, seed_builder: SeedBuilder, adapter: CanonicalNetflixAdapter
    ) -> None:
        """Provenance includes canonical_dataset_version from the adapter."""
        request = NetflixSeedBuildRequest(
            case_id="test-provenance-version",
            expected_status="SUCCESS",
            seed_item_ids=["tm100"],
            hard_constraints=NetflixHardConstraints(genres=["action"]),
            semantic_concepts=[],
            difficulty="easy",
            tags=["test"],
        )
        seed = seed_builder.build(request)

        assert seed.provenance.canonical_dataset_version == "test_v1"

    def test_provenance_contains_etl_version(self, seed_builder: SeedBuilder) -> None:
        """Provenance includes etl_version from the adapter."""
        request = NetflixSeedBuildRequest(
            case_id="test-provenance-etl",
            expected_status="SUCCESS",
            seed_item_ids=["tm200"],
            hard_constraints=NetflixHardConstraints(genres=["comedy"]),
            semantic_concepts=[],
            difficulty="easy",
            tags=["test"],
        )
        seed = seed_builder.build(request)

        assert seed.provenance.etl_version == "1.0.0"

    def test_provenance_contains_schema_version(
        self, seed_builder: SeedBuilder
    ) -> None:
        """Provenance includes schema_version."""
        request = NetflixSeedBuildRequest(
            case_id="test-provenance-schema",
            expected_status="SUCCESS",
            seed_item_ids=["tm300"],
            hard_constraints=NetflixHardConstraints(type="show"),
            semantic_concepts=[],
            difficulty="easy",
            tags=["test"],
        )
        seed = seed_builder.build(request)

        assert seed.provenance.schema_version == "1.0.0"

    def test_provenance_contains_checksum_sha256(
        self, seed_builder: SeedBuilder, adapter: CanonicalNetflixAdapter
    ) -> None:
        """Provenance includes checksum_sha256 matching the adapter's value."""
        request = NetflixSeedBuildRequest(
            case_id="test-provenance-checksum",
            expected_status="SUCCESS",
            seed_item_ids=["tm100"],
            hard_constraints=NetflixHardConstraints(genres=["action"]),
            semantic_concepts=[],
            difficulty="easy",
            tags=["test"],
        )
        seed = seed_builder.build(request)

        assert (
            seed.provenance.canonical_dataset_checksum == adapter.output_checksum_sha256
        )

    def test_provenance_source_is_netflix(self, seed_builder: SeedBuilder) -> None:
        """Provenance source is 'netflix' for Netflix seeds."""
        request = NetflixSeedBuildRequest(
            case_id="test-provenance-source",
            expected_status="SUCCESS",
            seed_item_ids=["tm400"],
            hard_constraints=NetflixHardConstraints(genres=["action"]),
            semantic_concepts=[],
            difficulty="easy",
            tags=["test"],
        )
        seed = seed_builder.build(request)

        assert seed.provenance.source == "netflix"


# ---------------------------------------------------------------------------
# Tests: eligible_item_ids correctness (Req 4.5, 4.6, 7.1, 7.5)
# ---------------------------------------------------------------------------


class TestEligibleItemIds:
    """Verify eligible_item_ids are computed correctly via exhaustive filtering."""

    def test_filter_by_genre_action(
        self, seed_builder: SeedBuilder, adapter: CanonicalNetflixAdapter
    ) -> None:
        """Filtering by genre 'action' returns exactly the action titles."""
        constraints = NetflixHardConstraints(genres=["action"])
        eligible = adapter.filter(constraints)

        # tm100 (action, drama), tm400 (action) are action titles
        assert eligible == ["tm100", "tm400"]

        # Build seed with these constraints
        request = NetflixSeedBuildRequest(
            case_id="test-eligible-action",
            expected_status="SUCCESS",
            seed_item_ids=["tm100"],
            hard_constraints=constraints,
            semantic_concepts=[],
            difficulty="easy",
            tags=["test"],
        )
        seed = seed_builder.build(request)
        assert seed.eligible_item_ids == ["tm100", "tm400"]

    def test_filter_by_genre_drama(
        self, seed_builder: SeedBuilder, adapter: CanonicalNetflixAdapter
    ) -> None:
        """Filtering by genre 'drama' returns all titles with drama."""
        constraints = NetflixHardConstraints(genres=["drama"])
        eligible = adapter.filter(constraints)

        # tm100 (action, drama), tm300 (drama, thriller), tm500 (drama)
        assert eligible == ["tm100", "tm300", "tm500"]

    def test_filter_by_multiple_genres_and_semantics(
        self, adapter: CanonicalNetflixAdapter
    ) -> None:
        """Filtering by genres AND: requires ALL genres present."""
        constraints = NetflixHardConstraints(genres=["action", "drama"])
        eligible = adapter.filter(constraints)

        # Only tm100 has both action AND drama
        assert eligible == ["tm100"]

    def test_filter_by_actor_or_semantics(
        self, adapter: CanonicalNetflixAdapter
    ) -> None:
        """Filtering by actors: OR semantics (at least one match)."""
        constraints = NetflixHardConstraints(actors=["alice smith"])
        eligible = adapter.filter(constraints)

        # tm100, tm200, tm500 have alice smith
        assert eligible == ["tm100", "tm200", "tm500"]

    def test_filter_by_multiple_actors(self, adapter: CanonicalNetflixAdapter) -> None:
        """Multiple actors: OR (at least one actor present)."""
        constraints = NetflixHardConstraints(actors=["bob jones", "eve green"])
        eligible = adapter.filter(constraints)

        # bob jones: tm100, tm400. eve green: tm300, tm500
        assert eligible == ["tm100", "tm300", "tm400", "tm500"]

    def test_filter_by_director_or_semantics(
        self, adapter: CanonicalNetflixAdapter
    ) -> None:
        """Filtering by directors: OR semantics."""
        constraints = NetflixHardConstraints(directors=["carol white"])
        eligible = adapter.filter(constraints)

        # carol white directs tm100 and tm300
        assert eligible == ["tm100", "tm300"]

    def test_filter_by_actor_and_director(
        self, adapter: CanonicalNetflixAdapter
    ) -> None:
        """Actors AND directors: doc must have at least one actor AND at least one director."""
        constraints = NetflixHardConstraints(
            actors=["alice smith"],
            directors=["carol white"],
        )
        eligible = adapter.filter(constraints)

        # alice smith in tm100, tm200, tm500
        # carol white directs tm100, tm300
        # Intersection: tm100 (has alice smith AND carol white)
        assert eligible == ["tm100"]

    def test_filter_by_type_movie(self, adapter: CanonicalNetflixAdapter) -> None:
        """Filtering by type='movie' returns only movies."""
        constraints = NetflixHardConstraints(type="movie")
        eligible = adapter.filter(constraints)

        # tm100, tm200, tm400, tm500 are movies
        assert eligible == ["tm100", "tm200", "tm400", "tm500"]

    def test_filter_by_year_range(self, adapter: CanonicalNetflixAdapter) -> None:
        """Filtering by year range works correctly."""
        constraints = NetflixHardConstraints(min_year=2020, max_year=2022)
        eligible = adapter.filter(constraints)

        # tm100 (2020), tm300 (2021), tm500 (2022)
        assert eligible == ["tm100", "tm300", "tm500"]

    def test_filter_combined_genre_actor_year(
        self, adapter: CanonicalNetflixAdapter
    ) -> None:
        """Combined filtering: genre + actor + year range."""
        constraints = NetflixHardConstraints(
            genres=["drama"],
            actors=["alice smith"],
            min_year=2020,
        )
        eligible = adapter.filter(constraints)

        # drama: tm100, tm300, tm500
        # alice smith: tm100, tm200, tm500
        # min_year >= 2020: tm100, tm300, tm500
        # All three: tm100 (drama + alice + 2020), tm500 (drama + alice + 2022)
        assert eligible == ["tm100", "tm500"]

    def test_no_results_seed_eligible_empty(self, seed_builder: SeedBuilder) -> None:
        """A NO_RESULTS seed has eligible_item_ids == []."""
        # Non-existent actor should produce no results
        constraints = NetflixHardConstraints(actors=["nonexistent person"])
        request = NetflixSeedBuildRequest(
            case_id="test-no-results",
            expected_status="NO_RESULTS",
            seed_item_ids=[],
            hard_constraints=constraints,
            semantic_concepts=[],
            difficulty="medium",
            tags=["test"],
        )
        seed = seed_builder.build(request)
        assert seed.eligible_item_ids == []

    def test_default_constraints_produce_none_eligible(
        self, adapter: CanonicalNetflixAdapter
    ) -> None:
        """Default constraints (all fields at defaults) produce eligible=None."""
        constraints = NetflixHardConstraints()
        assert constraints.is_default()
        eligible = adapter.filter(constraints)
        assert eligible is None

    def test_eligible_ids_are_sorted_lexicographically(
        self, adapter: CanonicalNetflixAdapter
    ) -> None:
        """eligible_item_ids are always returned in lexicographic ascending order."""
        constraints = NetflixHardConstraints(type="movie")
        eligible = adapter.filter(constraints)

        assert eligible is not None
        assert eligible == sorted(eligible)


# ---------------------------------------------------------------------------
# Tests: Roundtrip determinism
# ---------------------------------------------------------------------------


class TestDeterminism:
    """Verify the full pipeline roundtrip is deterministic."""

    def test_etl_produces_identical_output_on_reruns(self, tmp_path: Path) -> None:
        """Two ETL runs on same input produce identical checksums."""
        titles_path, credits_path = _create_fixture_csvs(tmp_path)

        config1 = EtlConfig(
            titles_path=titles_path,
            credits_path=credits_path,
            output_base_dir=tmp_path / "run1",
            canonical_dataset_version="det_v1",
            etl_version="1.0.0",
            schema_version="1.0.0",
        )
        config2 = EtlConfig(
            titles_path=titles_path,
            credits_path=credits_path,
            output_base_dir=tmp_path / "run2",
            canonical_dataset_version="det_v1",
            etl_version="1.0.0",
            schema_version="1.0.0",
        )

        result1 = NetflixEtl(config1).run()
        result2 = NetflixEtl(config2).run()

        assert result1.output_checksum_sha256 == result2.output_checksum_sha256
        assert result1.document_count == result2.document_count

        # JSONL content is byte-identical
        jsonl1 = (result1.output_dir / "titles.jsonl").read_bytes()
        jsonl2 = (result2.output_dir / "titles.jsonl").read_bytes()
        assert jsonl1 == jsonl2

        # Quality report is byte-identical
        qr1 = (result1.output_dir / "quality_report.json").read_bytes()
        qr2 = (result2.output_dir / "quality_report.json").read_bytes()
        assert qr1 == qr2

    def test_adapter_filter_is_deterministic(
        self, adapter: CanonicalNetflixAdapter
    ) -> None:
        """Same constraints produce same eligible list on repeated calls."""
        constraints = NetflixHardConstraints(genres=["drama"], actors=["alice smith"])

        result1 = adapter.filter(constraints)
        result2 = adapter.filter(constraints)

        assert result1 == result2

    def test_seed_builder_produces_same_seed(self, seed_builder: SeedBuilder) -> None:
        """Same request produces identical seed on repeated calls."""
        request = NetflixSeedBuildRequest(
            case_id="determinism-test",
            expected_status="SUCCESS",
            seed_item_ids=["tm100"],
            hard_constraints=NetflixHardConstraints(genres=["action"]),
            semantic_concepts=[],
            difficulty="easy",
            tags=["test"],
        )

        seed1 = seed_builder.build(request)
        seed2 = seed_builder.build(request)

        assert seed1.model_dump() == seed2.model_dump()
