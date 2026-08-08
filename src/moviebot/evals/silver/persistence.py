"""Persistence — Escritura atómica y versionada del Silver Dataset."""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
from collections import Counter
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from pydantic import BaseModel

from moviebot.evals.silver.adapters import NetflixAdapter, TmdbAdapter
from moviebot.evals.silver.models import SilverSeed
from moviebot.evals.silver.validator import SeedValidator

_SAFE_VERSION_PATTERN = re.compile(r"^[a-zA-Z0-9_-]+$")


class DatasetMetadata(BaseModel):
    """Metadata del dataset persistido."""

    dataset_version: str
    schema_version: str
    created_at: str  # ISO 8601 UTC timestamp
    seed_count: int
    checksum_sha256: str  # SHA-256 del archivo seeds.jsonl
    route_distribution: dict[str, int]  # e.g., {"trending": 5, "netflix": 3, ...}


@dataclass
class PersistenceResult:
    """Resultado de la operación de persistencia."""

    seeds_path: Path
    metadata_path: Path
    seed_count: int
    checksum_sha256: str


class SeedPersistence:
    """Serializa, valida y persiste seeds a disco.

    Escribe seeds.jsonl y metadata.json bajo
    base_output_dir / dataset_version /
    """

    def __init__(
        self,
        base_output_dir: Path,
        *,
        netflix_adapter: NetflixAdapter | None = None,
        tmdb_adapter: TmdbAdapter | None = None,
        schema_version: str,
    ) -> None:
        """Configura persistencia con directorio base y adaptadores para validación."""
        self._base_output_dir = base_output_dir
        self._schema_version = schema_version
        self._validator = SeedValidator(
            netflix_adapter=netflix_adapter,
            tmdb_adapter=tmdb_adapter,
        )

    def persist(
        self,
        seeds: list[SilverSeed],
        dataset_version: str,
    ) -> PersistenceResult:
        """Persiste seeds validados a disco.

        Steps:
        1. Validate dataset_version (safe path component)
        2. Verify seeds not empty
        3. Verify provenance.schema_version and provenance.dataset_version match
        4. Create base_output_dir if needed
        5. Verify final directory doesn't exist (overwrite protection)
        6. Validate via SeedValidator.validate_batch()
        7. Sort seeds by case_id
        8. Compute per-seed checksum (on copies, don't mutate originals)
        9. Write atomically (staging dir → rename)
        10. Return PersistenceResult

        Raises:
            ValueError: dataset_version unsafe, seeds empty, provenance mismatch,
                        validation errors
            FileExistsError: output directory already exists
        """
        # 1. Validate dataset_version
        if not _SAFE_VERSION_PATTERN.match(dataset_version):
            raise ValueError(
                f"dataset_version contiene caracteres inseguros: '{dataset_version}'"
            )

        # 2. Verify non-empty
        if not seeds:
            raise ValueError("seeds vacío: no se puede persistir un dataset vacío")

        # 3. Provenance consistency check
        for seed in seeds:
            if seed.provenance.schema_version != self._schema_version:
                raise ValueError(
                    f"Seed '{seed.case_id}': provenance.schema_version "
                    f"'{seed.provenance.schema_version}' no coincide con "
                    f"schema_version del persister '{self._schema_version}'"
                )
            if seed.provenance.dataset_version != dataset_version:
                raise ValueError(
                    f"Seed '{seed.case_id}': provenance.dataset_version "
                    f"'{seed.provenance.dataset_version}' no coincide con "
                    f"dataset_version '{dataset_version}'"
                )

        # 4. Create base_output_dir if needed
        self._base_output_dir.mkdir(parents=True, exist_ok=True)

        # 5. Check final directory doesn't exist
        final_dir = self._base_output_dir / dataset_version
        if final_dir.exists():
            raise FileExistsError(f"Directorio de salida ya existe: {final_dir}")

        # 6. Validate batch
        result = self._validator.validate_batch(seeds)
        if not result.is_valid:
            error_msgs = "; ".join(
                f"[{e.case_id}] {e.validation_id}: {e.message}"
                for e in result.errors[:10]
            )
            raise ValueError(f"Validación del lote falló: {error_msgs}")

        # 7. Sort by case_id
        sorted_seeds = sorted(seeds, key=lambda s: s.case_id)

        # 8. Compute per-seed checksum (on COPIES, don't mutate originals)
        seeds_with_checksum: list[SilverSeed] = []
        for seed in sorted_seeds:
            checksum = self._compute_seed_checksum(seed)
            # Create a copy with checksum set
            seed_data = seed.model_dump(mode="json")
            seed_data["provenance"]["checksum_sha256"] = checksum
            seeds_with_checksum.append(SilverSeed.model_validate(seed_data))

        # 9. Atomic publish
        return self._atomic_publish_directory(
            seeds_with_checksum, dataset_version, final_dir
        )

    def _compute_seed_checksum(self, seed: SilverSeed) -> str:
        """Compute SHA-256 checksum for a seed.

        Serializes the seed to canonical JSON EXCLUDING provenance.checksum_sha256,
        then returns the SHA-256 hex digest.
        """
        seed_data = seed.model_dump(mode="json")
        # Exclude checksum_sha256 from provenance for the computation
        seed_data["provenance"]["checksum_sha256"] = None
        canonical = json.dumps(
            seed_data, sort_keys=True, separators=(",", ":"), ensure_ascii=False
        )
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    def _atomic_publish_directory(
        self,
        seeds: list[SilverSeed],
        dataset_version: str,
        final_dir: Path,
    ) -> PersistenceResult:
        """Write seeds atomically: staging → rename.

        On failure, cleans up staging directory.
        """
        staging_suffix = uuid4().hex[:8]
        staging_dir = self._base_output_dir / f"{dataset_version}.tmp.{staging_suffix}"

        try:
            staging_dir.mkdir(parents=True, exist_ok=False)

            # Write seeds.jsonl
            seeds_path = staging_dir / "seeds.jsonl"
            lines: list[str] = []
            for seed in seeds:
                line = json.dumps(
                    seed.model_dump(mode="json"),
                    sort_keys=True,
                    separators=(",", ":"),
                    ensure_ascii=False,
                )
                lines.append(line)

            seeds_content = "\n".join(lines) + "\n"
            seeds_path.write_text(seeds_content, encoding="utf-8")

            # fsync seeds.jsonl
            fd = os.open(str(seeds_path), os.O_RDONLY)
            try:
                os.fsync(fd)
            finally:
                os.close(fd)

            # Compute file checksum
            file_checksum = hashlib.sha256(seeds_content.encode("utf-8")).hexdigest()

            # Compute route distribution
            route_distribution: dict[str, int] = dict(
                Counter(s.expected_route for s in seeds)
            )

            # Write metadata.json
            metadata = DatasetMetadata(
                dataset_version=dataset_version,
                schema_version=self._schema_version,
                created_at=datetime.now(UTC).isoformat(),
                seed_count=len(seeds),
                checksum_sha256=file_checksum,
                route_distribution=route_distribution,
            )
            metadata_path = staging_dir / "metadata.json"
            metadata_path.write_text(
                metadata.model_dump_json(indent=2),
                encoding="utf-8",
            )

            # fsync metadata.json
            fd = os.open(str(metadata_path), os.O_RDONLY)
            try:
                os.fsync(fd)
            finally:
                os.close(fd)

            # Atomic rename
            staging_dir.rename(final_dir)

            return PersistenceResult(
                seeds_path=final_dir / "seeds.jsonl",
                metadata_path=final_dir / "metadata.json",
                seed_count=len(seeds),
                checksum_sha256=file_checksum,
            )

        except Exception:
            # Cleanup staging on any failure
            if staging_dir.exists():
                shutil.rmtree(staging_dir, ignore_errors=True)
            raise
