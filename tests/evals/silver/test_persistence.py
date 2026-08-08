"""Tests for SeedPersistence — property-based and unit tests.

Covers:
- Property 1: Round-trip de serialización Silver_Seed (task 9.3)
- Property 8: Determinismo de persistencia (task 9.4)
- Unit tests for persistence validation and error paths (task 9.5)

**Validates: Requirements 1.10, 7.8, 7.9, 8.5, 10.4, 10.5, 10.10**
"""

from __future__ import annotations

import hashlib
import json
import shutil
import tempfile
from pathlib import Path
from unittest.mock import patch

import hypothesis.strategies as st
import pytest
from hypothesis import HealthCheck, given, settings

from moviebot.evals.silver.adapters import NetflixAdapter, TmdbAdapter
from moviebot.evals.silver.builder import SeedBuilder
from moviebot.evals.silver.models import SeedProvenance, SilverSeed
from moviebot.evals.silver.persistence import SeedPersistence
from moviebot.evals.silver.validator import SeedValidator, ValidationResult
from tests.evals.silver.strategies import valid_silver_seed

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def netflix_adapter(netflix_titles_csv, netflix_credits_csv):
    """Create a NetflixAdapter from test fixtures."""
    return NetflixAdapter(
        titles_path=netflix_titles_csv,
        credits_path=netflix_credits_csv,
    )


@pytest.fixture()
def tmdb_adapter(tmdb_fixture_path):
    """Create a TmdbAdapter from test fixtures."""
    return TmdbAdapter(fixture_version="v1", base_dir=tmdb_fixture_path)


@pytest.fixture()
def builder(netflix_adapter, tmdb_adapter):
    """Create a SeedBuilder with both adapters."""
    return SeedBuilder(
        netflix_adapter=netflix_adapter,
        tmdb_adapter=tmdb_adapter,
        schema_version="1.0.0",
        dataset_version="test_v1",
    )


def _make_out_of_scope_seed(
    case_id: str,
    schema_version: str = "1.0.0",
    dataset_version: str = "test_v1",
) -> SilverSeed:
    """Create a minimal out_of_scope seed for testing."""
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
            input_data_description="test seed",
            schema_version=schema_version,
            dataset_version=dataset_version,
        ),
        fixture_version=None,
        tmdb_component=None,
        netflix_component=None,
    )


def _noop_fsync(fd: int) -> None:
    """No-op replacement for os.fsync to avoid Windows issues in tests."""


# ===========================================================================
# Property 1: Round-trip de serialización Silver_Seed (Task 9.3)
# ===========================================================================


class TestRoundTripSerialization:
    """**Validates: Requirements 1.10, 7.8**"""

    @given(seed=valid_silver_seed())
    @settings(
        max_examples=100,
        suppress_health_check=[HealthCheck.too_slow],
    )
    def test_roundtrip_serialization_preserves_equality(self, seed: SilverSeed) -> None:
        """Property 1: Round-trip de serialización Silver_Seed.

        Serialize with model_dump(mode='json') and deserialize with
        model_validate(), verify equality.
        """
        serialized = seed.model_dump(mode="json")
        deserialized = SilverSeed.model_validate(serialized)
        assert deserialized == seed


# ===========================================================================
# Property 8: Determinismo de persistencia (Task 9.4)
# ===========================================================================


class TestPersistenceDeterminism:
    """**Validates: Requirements 7.9, 8.5**"""

    @given(
        case_ids=st.lists(
            st.from_regex(r"[a-zA-Z0-9_-]{1,20}", fullmatch=True).filter(
                lambda s: len(s) >= 1
            ),
            min_size=1,
            max_size=5,
            unique=True,
        ),
    )
    @settings(
        max_examples=100,
        suppress_health_check=[
            HealthCheck.too_slow,
            HealthCheck.function_scoped_fixture,
        ],
        deadline=None,
    )
    def test_persistence_determinism_sha256(
        self, case_ids: list[str], tmp_path: Path
    ) -> None:
        """Property 8: Determinismo de persistencia.

        Generate lists of valid out_of_scope seeds (no adapters needed),
        persist twice in DISTINCT temporary directories, compare SHA-256
        of both seeds.jsonl files.
        """
        schema_version = "1.0.0"
        dataset_version = "test_v1"

        seeds = [
            _make_out_of_scope_seed(cid, schema_version, dataset_version)
            for cid in case_ids
        ]

        # Create two distinct base directories using tempfile for isolation
        dir_a = Path(tempfile.mkdtemp())
        dir_b = Path(tempfile.mkdtemp())

        try:
            # Mock the validator to always pass and fsync for Windows compat
            valid_result = ValidationResult(is_valid=True, errors=[])

            with (
                patch.object(
                    SeedValidator, "validate_batch", return_value=valid_result
                ),
                patch("os.fsync", _noop_fsync),
                patch("os.open", return_value=0),
                patch("os.close"),
            ):
                persistence_a = SeedPersistence(
                    base_output_dir=dir_a,
                    schema_version=schema_version,
                )
                result_a = persistence_a.persist(seeds, dataset_version)

                persistence_b = SeedPersistence(
                    base_output_dir=dir_b,
                    schema_version=schema_version,
                )
                result_b = persistence_b.persist(seeds, dataset_version)

            # Compare SHA-256 of both seeds.jsonl files
            content_a = result_a.seeds_path.read_bytes()
            content_b = result_b.seeds_path.read_bytes()

            hash_a = hashlib.sha256(content_a).hexdigest()
            hash_b = hashlib.sha256(content_b).hexdigest()

            assert hash_a == hash_b, (
                f"SHA-256 mismatch: persistence is not deterministic. "
                f"hash_a={hash_a}, hash_b={hash_b}"
            )
            # Also verify the result reports the same checksum
            assert result_a.checksum_sha256 == result_b.checksum_sha256
        finally:
            shutil.rmtree(dir_a, ignore_errors=True)
            shutil.rmtree(dir_b, ignore_errors=True)


# ===========================================================================
# Unit Tests for Persistence (Task 9.5)
# ===========================================================================


class TestPersistenceOverwriteProtection:
    """Protección contra sobreescritura.

    **Validates: Requirements 10.4**
    """

    def test_directory_exists_raises_file_exists_error(self, tmp_path: Path) -> None:
        """Directorio final ya existe → FileExistsError sin modificar contenido."""
        schema_version = "1.0.0"
        dataset_version = "test_v1"

        # Create the final directory beforehand with some content
        final_dir = tmp_path / dataset_version
        final_dir.mkdir(parents=True)
        existing_file = final_dir / "existing.txt"
        existing_file.write_text("original content")

        seeds = [_make_out_of_scope_seed("seed-1", schema_version, dataset_version)]

        valid_result = ValidationResult(is_valid=True, errors=[])
        with patch.object(SeedValidator, "validate_batch", return_value=valid_result):
            persistence = SeedPersistence(
                base_output_dir=tmp_path,
                schema_version=schema_version,
            )

            with pytest.raises(FileExistsError):
                persistence.persist(seeds, dataset_version)

        # Verify existing content not modified
        assert existing_file.read_text() == "original content"


class TestPersistenceAtomicity:
    """Atomicidad con fault injection.

    **Validates: Requirements 10.5**
    """

    def test_write_failure_leaves_no_artifacts(self, tmp_path: Path) -> None:
        """Simular fallo durante escritura → ni directorio final ni staging."""
        schema_version = "1.0.0"
        dataset_version = "test_v1"

        seeds = [_make_out_of_scope_seed("seed-1", schema_version, dataset_version)]

        valid_result = ValidationResult(is_valid=True, errors=[])

        with (
            patch.object(SeedValidator, "validate_batch", return_value=valid_result),
            patch("pathlib.Path.write_text", side_effect=OSError("disk full")),
        ):
            persistence = SeedPersistence(
                base_output_dir=tmp_path,
                schema_version=schema_version,
            )

            with pytest.raises(OSError, match="disk full"):
                persistence.persist(seeds, dataset_version)

        # Neither final dir nor any staging dir should remain
        final_dir = tmp_path / dataset_version
        assert not final_dir.exists()

        # No staging directories either
        for item in tmp_path.iterdir():
            assert ".tmp." not in item.name, f"Staging directory left behind: {item}"

    def test_rename_failure_cleans_staging(self, tmp_path: Path) -> None:
        """Simular fallo del rename → staging se limpia, directorio final no se crea."""
        schema_version = "1.0.0"
        dataset_version = "test_v1"

        seeds = [_make_out_of_scope_seed("seed-1", schema_version, dataset_version)]

        valid_result = ValidationResult(is_valid=True, errors=[])

        # Patch Path.rename to raise after files are written

        def failing_rename(self_path: Path, target: object) -> None:
            raise OSError("rename failed")

        with (
            patch.object(SeedValidator, "validate_batch", return_value=valid_result),
            patch("os.fsync", _noop_fsync),
            patch("os.open", return_value=0),
            patch("os.close"),
            patch.object(Path, "rename", failing_rename),
        ):
            persistence = SeedPersistence(
                base_output_dir=tmp_path,
                schema_version=schema_version,
            )

            with pytest.raises(OSError, match="rename failed"):
                persistence.persist(seeds, dataset_version)

        # Final directory should not exist
        final_dir = tmp_path / dataset_version
        assert not final_dir.exists()

        # No staging directories should remain (cleanup happened)
        for item in tmp_path.iterdir():
            assert ".tmp." not in item.name, f"Staging directory left behind: {item}"


class TestPersistenceEmptyList:
    """Rechazo de lista vacía.

    **Validates: Requirements 10.4**
    """

    def test_empty_seeds_raises_value_error(self, tmp_path: Path) -> None:
        """Seeds vacío → ValueError sin crear archivos."""
        persistence = SeedPersistence(
            base_output_dir=tmp_path,
            schema_version="1.0.0",
        )

        with pytest.raises(ValueError, match="vacío"):
            persistence.persist([], "test_v1")

        # No files created
        assert list(tmp_path.iterdir()) == []


class TestPersistenceMetadataChecksum:
    """Metadata checksum correcto.

    **Validates: Requirements 10.4**
    """

    def test_metadata_checksum_matches_seeds_file(self, tmp_path: Path) -> None:
        """Recalcular SHA-256 de seeds.jsonl y comparar con metadata.json."""
        schema_version = "1.0.0"
        dataset_version = "test_v1"

        seeds = [
            _make_out_of_scope_seed("seed-a", schema_version, dataset_version),
            _make_out_of_scope_seed("seed-b", schema_version, dataset_version),
        ]

        valid_result = ValidationResult(is_valid=True, errors=[])
        with (
            patch.object(SeedValidator, "validate_batch", return_value=valid_result),
            patch("os.fsync", _noop_fsync),
            patch("os.open", return_value=0),
            patch("os.close"),
        ):
            persistence = SeedPersistence(
                base_output_dir=tmp_path,
                schema_version=schema_version,
            )
            result = persistence.persist(seeds, dataset_version)

        # Read seeds.jsonl as text (matching how persistence computes checksum:
        # from the Python string encoded to UTF-8, before platform line-ending
        # translation by write_text)
        seeds_text = result.seeds_path.read_text(encoding="utf-8")
        computed_checksum = hashlib.sha256(seeds_text.encode("utf-8")).hexdigest()

        # Read metadata.json and extract checksum
        metadata = json.loads(result.metadata_path.read_text(encoding="utf-8"))
        stored_checksum = metadata["checksum_sha256"]

        assert computed_checksum == stored_checksum
        assert result.checksum_sha256 == stored_checksum


class TestPersistenceUnsafeVersion:
    """dataset_version con caracteres inseguros.

    **Validates: Requirements 10.4**
    """

    @pytest.mark.parametrize(
        "bad_version",
        [
            "..",
            "../escape",
            "a/b",
            "a\\b",
            "with space",
            "with.dot",
            "",
        ],
    )
    def test_unsafe_characters_raise_value_error(
        self, tmp_path: Path, bad_version: str
    ) -> None:
        """dataset_version con caracteres inseguros → ValueError.

        The test passes the bad version to persist() directly.
        Seeds use a valid provenance (persist checks dataset_version param
        BEFORE checking provenance consistency).
        """
        persistence = SeedPersistence(
            base_output_dir=tmp_path,
            schema_version="1.0.0",
        )
        # Use valid seeds — the error should come from dataset_version validation
        seeds = [_make_out_of_scope_seed("seed-1", "1.0.0", "valid_version")]

        with pytest.raises(ValueError, match="inseguros|vacío"):
            persistence.persist(seeds, bad_version)


class TestPersistenceProvenanceConsistency:
    """Provenance versions inconsistentes.

    **Validates: Requirements 10.4**
    """

    def test_schema_version_mismatch_raises_value_error(self, tmp_path: Path) -> None:
        """Provenance schema_version mismatch → ValueError antes de escribir."""
        seeds = [_make_out_of_scope_seed("seed-1", "2.0.0", "test_v1")]

        persistence = SeedPersistence(
            base_output_dir=tmp_path,
            schema_version="1.0.0",  # Different from seed's provenance
        )

        with pytest.raises(ValueError, match="schema_version"):
            persistence.persist(seeds, "test_v1")

        # No files created
        final_dir = tmp_path / "test_v1"
        assert not final_dir.exists()

    def test_dataset_version_mismatch_raises_value_error(self, tmp_path: Path) -> None:
        """Provenance dataset_version mismatch → ValueError antes de escribir."""
        seeds = [_make_out_of_scope_seed("seed-1", "1.0.0", "other_version")]

        persistence = SeedPersistence(
            base_output_dir=tmp_path,
            schema_version="1.0.0",
        )

        with pytest.raises(ValueError, match="dataset_version"):
            persistence.persist(seeds, "test_v1")

        # No files created
        final_dir = tmp_path / "test_v1"
        assert not final_dir.exists()


class TestPersistenceSeedsNotMutated:
    """Seeds no se mutan.

    **Validates: Requirements 10.10**
    """

    def test_original_seeds_not_mutated_after_persist(self, tmp_path: Path) -> None:
        """Verificar que los objetos pasados a persist() no tienen checksum después."""
        schema_version = "1.0.0"
        dataset_version = "test_v1"

        seeds = [
            _make_out_of_scope_seed("seed-1", schema_version, dataset_version),
            _make_out_of_scope_seed("seed-2", schema_version, dataset_version),
        ]

        # Confirm checksum is None before
        for seed in seeds:
            assert seed.provenance.checksum_sha256 is None

        valid_result = ValidationResult(is_valid=True, errors=[])
        with (
            patch.object(SeedValidator, "validate_batch", return_value=valid_result),
            patch("os.fsync", _noop_fsync),
            patch("os.open", return_value=0),
            patch("os.close"),
        ):
            persistence = SeedPersistence(
                base_output_dir=tmp_path,
                schema_version=schema_version,
            )
            persistence.persist(seeds, dataset_version)

        # Original seeds must still have checksum=None (not mutated)
        for seed in seeds:
            assert seed.provenance.checksum_sha256 is None, (
                f"Seed '{seed.case_id}' was mutated: "
                f"checksum_sha256={seed.provenance.checksum_sha256}"
            )
