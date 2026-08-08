"""BatchGenerator — Orquesta la generación de los 150 seeds del Silver Dataset.

Genera seeds a partir de un catálogo declarativo (case_catalog.json),
delegando construcción a SeedBuilder y persistencia a SeedPersistence.

Requirements: 4.1, 4.2, 4.3, 4.4, 4.5, 4.6, 4.7, 4.8, 4.9, 4.10, 4.11,
              4.12, 4.13, 4.14, 4.15, 4.16
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import ClassVar

from moviebot.evals.silver.adapters import CanonicalNetflixAdapter, TmdbAdapter
from moviebot.evals.silver.builder import SeedBuilder
from moviebot.evals.silver.case_catalog import load_case_catalog
from moviebot.evals.silver.models import SilverSeed
from moviebot.evals.silver.persistence import PersistenceResult, SeedPersistence


@dataclass(frozen=True)
class BatchGeneratorConfig:
    """Configuración del generador batch."""

    canonical_dataset_version: str
    silver_dataset_version: str
    schema_version: str
    etl_version: str
    tmdb_fixture_version: str
    case_catalog_path: Path  # config/evals/silver_v1/case_catalog.json
    output_base_dir: Path  # evals/datasets/


class BatchGenerator:
    """Genera los 150 seeds del Silver Dataset desde el catálogo declarativo."""

    EXPECTED_DISTRIBUTION: ClassVar[dict[str, int]] = {
        "trending": 50,
        "netflix": 50,
        "both": 25,
        "out_of_scope": 25,
    }
    NO_RESULTS_QUOTA: ClassVar[dict[str, int]] = {
        "netflix": 7,
        "trending": 3,
        "both": 0,
    }

    def __init__(
        self,
        config: BatchGeneratorConfig,
        netflix_adapter: CanonicalNetflixAdapter,
        tmdb_adapter: TmdbAdapter,
    ) -> None:
        """Configura el generador con adaptadores y configuración.

        Args:
            config: Configuración con versiones y rutas.
            netflix_adapter: Adaptador canónico Netflix ya inicializado.
            tmdb_adapter: Adaptador TMDB ya inicializado.
        """
        self._config = config
        self._netflix_adapter = netflix_adapter
        self._tmdb_adapter = tmdb_adapter

    def generate(self) -> PersistenceResult:
        """Genera y persiste los 150 seeds.

        Steps:
        0. Validar versiones config vs adaptadores
        1. Cargar y validar case_catalog.json
        2. Construir cada seed via SeedBuilder
        3. Validar distribución (50/50/25/25)
        4. Validar cuota NO_RESULTS (7/3/0)
        5. Re-validar eligible_item_ids para todos NO_RESULTS seeds
        6. Persistir via SeedPersistence

        Raises:
            SeedBuildError: si algún seed falla construcción (aborta completamente)
            ValueError: si distribución, cuota o versiones no coinciden
        """
        # Step 0: Validate versions match adapters
        self._validate_versions()

        # Step 1: Load case catalog
        requests = load_case_catalog(self._config.case_catalog_path)

        # Step 2: Build each seed via SeedBuilder
        builder = SeedBuilder(
            netflix_adapter=self._netflix_adapter,
            tmdb_adapter=self._tmdb_adapter,
            schema_version=self._config.schema_version,
            silver_dataset_version=self._config.silver_dataset_version,
            canonical_dataset_version=self._config.canonical_dataset_version,
            etl_version=self._config.etl_version,
        )

        seeds: list[SilverSeed] = []
        for request in requests:
            # SeedBuildError propagates — abort entirely on failure (Req 4.14)
            seed = builder.build(request)
            seeds.append(seed)

        # Step 3: Validate distribution (50/50/25/25)
        self._validate_distribution(seeds)

        # Step 4: Validate NO_RESULTS quota (7/3/0)
        self._validate_no_results_quota(seeds)

        # Step 5: Re-validate eligible_item_ids for all NO_RESULTS seeds (Req 4.16)
        self._revalidate_no_results_eligible(seeds)

        # Step 6: Persist via SeedPersistence
        persistence = SeedPersistence(
            base_output_dir=self._config.output_base_dir,
            netflix_adapter=self._netflix_adapter,
            tmdb_adapter=self._tmdb_adapter,
            schema_version=self._config.schema_version,
        )
        return persistence.persist(seeds, self._config.silver_dataset_version)

    def _validate_versions(self) -> None:
        """Validate config versions match adapter metadata.

        Checks:
        - config.canonical_dataset_version == netflix_adapter.canonical_dataset_version
        - config.etl_version == netflix_adapter.etl_version
        - config.tmdb_fixture_version == tmdb_adapter.fixture_version

        Raises:
            ValueError: if any version mismatch is detected.
        """
        # Validate canonical_dataset_version
        if (
            self._config.canonical_dataset_version
            != self._netflix_adapter.canonical_dataset_version
        ):
            raise ValueError(
                f"canonical_dataset_version mismatch: config has "
                f"'{self._config.canonical_dataset_version}' but adapter has "
                f"'{self._netflix_adapter.canonical_dataset_version}'"
            )

        # Validate etl_version
        if self._config.etl_version != self._netflix_adapter.etl_version:
            raise ValueError(
                f"etl_version mismatch: config has "
                f"'{self._config.etl_version}' but adapter has "
                f"'{self._netflix_adapter.etl_version}'"
            )

        # Validate tmdb_fixture_version
        if self._config.tmdb_fixture_version != self._tmdb_adapter.fixture_version:
            raise ValueError(
                f"tmdb_fixture_version mismatch: config has "
                f"'{self._config.tmdb_fixture_version}' but adapter has "
                f"'{self._tmdb_adapter.fixture_version}'"
            )

    def _validate_distribution(self, seeds: list[SilverSeed]) -> None:
        """Validate seed distribution matches expected 50/50/25/25.

        Raises:
            ValueError: if distribution does not match.
        """
        distribution: dict[str, int] = {
            "trending": 0,
            "netflix": 0,
            "both": 0,
            "out_of_scope": 0,
        }
        for seed in seeds:
            distribution[seed.expected_route] = (
                distribution.get(seed.expected_route, 0) + 1
            )

        if distribution != self.EXPECTED_DISTRIBUTION:
            raise ValueError(
                f"Distribution mismatch: expected {self.EXPECTED_DISTRIBUTION}, "
                f"got {distribution}"
            )

    def _validate_no_results_quota(self, seeds: list[SilverSeed]) -> None:
        """Validate NO_RESULTS quota matches expected 7/3/0.

        Raises:
            ValueError: if quota does not match.
        """
        no_results_count: dict[str, int] = {"netflix": 0, "trending": 0, "both": 0}

        for seed in seeds:
            if seed.expected_status == "NO_RESULTS":
                route = seed.expected_route
                if route in no_results_count:
                    no_results_count[route] += 1

        if no_results_count != self.NO_RESULTS_QUOTA:
            raise ValueError(
                f"NO_RESULTS quota mismatch: expected {self.NO_RESULTS_QUOTA}, "
                f"got {no_results_count}"
            )

    def _revalidate_no_results_eligible(self, seeds: list[SilverSeed]) -> None:
        """Re-validate that ALL NO_RESULTS seeds have eligible_item_ids == [].

        For each NO_RESULTS seed, recalculate eligible items from the adapter
        and verify the result is empty.

        Raises:
            ValueError: if any NO_RESULTS seed has non-empty eligible.
        """
        for seed in seeds:
            if seed.expected_status != "NO_RESULTS":
                continue

            # Re-validate eligible from adapter
            if seed.expected_route == "netflix" and seed.hard_constraints is not None:
                eligible = self._netflix_adapter.filter(seed.hard_constraints)  # type: ignore[arg-type]
                # CanonicalNetflixAdapter.filter returns None if is_default(), or list
                if eligible is None:
                    eligible = []
                if eligible != []:
                    raise ValueError(
                        f"NO_RESULTS re-validation failed for seed "
                        f"'{seed.case_id}': eligible_item_ids is not empty "
                        f"(found {len(eligible)} items)"
                    )
            elif (
                seed.expected_route == "trending" and seed.hard_constraints is not None
            ):
                eligible = self._tmdb_adapter.filter(seed.hard_constraints)  # type: ignore[arg-type]
                if eligible != []:
                    raise ValueError(
                        f"NO_RESULTS re-validation failed for seed "
                        f"'{seed.case_id}': eligible_item_ids is not empty "
                        f"(found {len(eligible)} items)"
                    )

            # Verify the seed itself has eligible_item_ids == []
            if seed.eligible_item_ids != []:
                raise ValueError(
                    f"NO_RESULTS seed '{seed.case_id}' has "
                    f"eligible_item_ids={seed.eligible_item_ids}, expected []"
                )


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(
        description="Generate Silver Dataset batch: produce 150 seeds from case catalog."
    )
    parser.add_argument(
        "--canonical-version",
        type=str,
        required=True,
        help="Canonical dataset version identifier (e.g. 'v1')",
    )
    parser.add_argument(
        "--silver-version",
        type=str,
        required=True,
        help="Silver dataset version identifier (e.g. 'silver_v1')",
    )
    parser.add_argument(
        "--catalog",
        type=Path,
        default=Path("config/evals/silver_v1/case_catalog.json"),
        help="Path to case catalog JSON (default: config/evals/silver_v1/case_catalog.json)",
    )
    parser.add_argument(
        "--tmdb-fixture-version",
        type=str,
        default="v1",
        help="TMDB fixture version (default: v1)",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("evals/datasets"),
        help="Base output directory for seeds (default: evals/datasets)",
    )
    parser.add_argument(
        "--schema-version",
        type=str,
        default="1.0.0",
        help="Schema version string (default: 1.0.0)",
    )
    parser.add_argument(
        "--etl-version",
        type=str,
        default="1.0.0",
        help="ETL version string (default: 1.0.0)",
    )

    args = parser.parse_args()

    # Construct config
    config = BatchGeneratorConfig(
        canonical_dataset_version=args.canonical_version,
        silver_dataset_version=args.silver_version,
        schema_version=args.schema_version,
        etl_version=args.etl_version,
        tmdb_fixture_version=args.tmdb_fixture_version,
        case_catalog_path=args.catalog,
        output_base_dir=args.output_dir,
    )

    # Instantiate adapters
    netflix_adapter = CanonicalNetflixAdapter(
        canonical_dataset_version=args.canonical_version,
    )
    tmdb_adapter = TmdbAdapter(
        fixture_version=args.tmdb_fixture_version,
    )

    # Instantiate generator and run
    generator = BatchGenerator(
        config=config,
        netflix_adapter=netflix_adapter,
        tmdb_adapter=tmdb_adapter,
    )
    result = generator.generate()

    print("Batch generation completed successfully.")
    print(f"  seed_count: {result.seed_count}")
    print(f"  checksum_sha256: {result.checksum_sha256}")
    print(f"  output_path: {result.seeds_path}")
