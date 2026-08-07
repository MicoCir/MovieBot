"""Tests unitarios para FixtureWriter.

Valida: Requisitos 2.6, 2.7, 2.8, 3.11, 3.12, 3.15, 7.1, 7.4, 7.5
"""

from pathlib import Path
from unittest.mock import patch

import pytest

from moviebot.repositories.fixture_writer import (
    LocalFixtureWriter,
    TmpDirFixtureWriter,
    _validate_version,
)
from moviebot.repositories.tmdb_errors import (
    TmdbFixtureConflictError,
    TmdbFixtureInconsistentError,
)

# --- Helpers ---

SAMPLE_PAYLOAD = b'{"results": [{"id": 1, "title": "Test"}]}'
SAMPLE_METADATA = b'{"version": "v1", "checksum_sha256": "abc123"}'


# --- Test: LocalFixtureWriter rechaza rutas fuera de raw_data/tmdb/ (Req 7.4) ---


class TestLocalFixtureWriterContainment:
    """LocalFixtureWriter valida que base_dir esté dentro de raw_data/tmdb/."""

    def test_rejects_path_outside_tmdb_dir(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Rutas como raw_data/otro_dir/ son rechazadas."""
        monkeypatch.chdir(tmp_path)
        (tmp_path / "raw_data" / "otro_dir").mkdir(parents=True)

        with pytest.raises(ValueError, match="raw_data/tmdb/"):
            LocalFixtureWriter(base_dir=Path("raw_data/otro_dir"))

    def test_rejects_raw_data_backup_dir(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Rutas como raw_data_backup/ son rechazadas."""
        monkeypatch.chdir(tmp_path)
        (tmp_path / "raw_data_backup").mkdir(parents=True)

        with pytest.raises(ValueError, match="raw_data/tmdb/"):
            LocalFixtureWriter(base_dir=Path("raw_data_backup"))


# --- Test: version con path traversal lanza ValueError (Req 2.7) ---


class TestVersionValidation:
    """Versiones con caracteres inseguros son rechazadas."""

    def test_path_traversal_raises_value_error(self) -> None:
        """Versión con ../../attack lanza ValueError."""
        with pytest.raises(ValueError, match="version debe matchear"):
            _validate_version("../../attack")

    def test_dots_in_version_rejected(self) -> None:
        """Puntos no están permitidos en version."""
        with pytest.raises(ValueError, match="version debe matchear"):
            _validate_version("v1.0")

    def test_slash_in_version_rejected(self) -> None:
        """Slashes no están permitidos en version."""
        with pytest.raises(ValueError, match="version debe matchear"):
            _validate_version("dir/v1")

    def test_valid_version_passes(self) -> None:
        """Versiones alfanuméricas con guiones y underscores son válidas."""
        _validate_version("v1")
        _validate_version("my-version_2")
        _validate_version("ABC-123_test")


# --- Test: fixture ya existente lanza TmdbFixtureConflictError (Req 3.11, 2.6) ---


class TestFixtureConflict:
    """Intentar escribir un fixture que ya existe lanza TmdbFixtureConflictError."""

    def test_existing_fixture_raises_conflict_error(self, tmp_path: Path) -> None:
        """Si ambos archivos ya existen, se lanza TmdbFixtureConflictError."""
        writer = TmpDirFixtureWriter(tmp_dir=tmp_path)

        # Escribir el fixture por primera vez
        writer.write_fixture("v1", SAMPLE_PAYLOAD, SAMPLE_METADATA)

        # Intentar escribir de nuevo lanza conflicto
        with pytest.raises(TmdbFixtureConflictError, match="ya existe"):
            writer.write_fixture("v1", SAMPLE_PAYLOAD, SAMPLE_METADATA)


# --- Test: estado inconsistente lanza TmdbFixtureInconsistentError (Req 3.12) ---


class TestFixtureInconsistentState:
    """Estado inconsistente (solo un archivo existe) lanza TmdbFixtureInconsistentError."""

    def test_only_payload_exists_raises_inconsistent(self, tmp_path: Path) -> None:
        """Si solo el payload existe, se detecta estado inconsistente."""
        # Crear solo el archivo payload manualmente
        (tmp_path / "trending_movies_v1.json").write_bytes(SAMPLE_PAYLOAD)

        writer = TmpDirFixtureWriter(tmp_dir=tmp_path)

        with pytest.raises(TmdbFixtureInconsistentError, match="inconsistente"):
            writer.write_fixture("v1", SAMPLE_PAYLOAD, SAMPLE_METADATA)

    def test_only_metadata_exists_raises_inconsistent(self, tmp_path: Path) -> None:
        """Si solo el metadata existe, se detecta estado inconsistente."""
        # Crear solo el archivo metadata manualmente
        (tmp_path / "trending_movies_v1.metadata.json").write_bytes(SAMPLE_METADATA)

        writer = TmpDirFixtureWriter(tmp_dir=tmp_path)

        with pytest.raises(TmdbFixtureInconsistentError, match="inconsistente"):
            writer.write_fixture("v1", SAMPLE_PAYLOAD, SAMPLE_METADATA)


# --- Test: escritura atómica — si falla, no quedan archivos parciales (Req 2.8, 3.15) ---


class TestAtomicWrite:
    """Si falla la escritura, no quedan archivos parciales en disco."""

    def test_no_partial_files_on_write_failure(self, tmp_path: Path) -> None:
        """Simular fallo durante rename: no deben quedar archivos parciales."""
        writer = TmpDirFixtureWriter(tmp_dir=tmp_path)

        with (
            patch("os.rename", side_effect=OSError("Simulated disk failure")),
            pytest.raises(OSError, match="Simulated disk failure"),
        ):
            writer.write_fixture("v1", SAMPLE_PAYLOAD, SAMPLE_METADATA)

        # Verificar que no quedaron archivos finales ni temporales
        remaining_files = list(tmp_path.iterdir())
        assert remaining_files == [], (
            f"No deben quedar archivos parciales, pero encontré: {remaining_files}"
        )


# --- Test: LocalFixtureWriter crea el directorio destino si no existe (Req 7.1) ---


class TestDirectoryCreation:
    """LocalFixtureWriter crea raw_data/tmdb/ si no existe."""

    def test_creates_tmdb_directory_if_not_exists(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Si raw_data/tmdb/ no existe, se crea automáticamente al escribir."""
        monkeypatch.chdir(tmp_path)

        # Crear solo raw_data/ pero NO raw_data/tmdb/
        (tmp_path / "raw_data").mkdir()

        # Instanciar LocalFixtureWriter — el directorio tmdb/ no existe todavía
        writer = LocalFixtureWriter()

        # Escribir fixture — debe crear tmdb/ y escribir exitosamente
        result = writer.write_fixture("v1", SAMPLE_PAYLOAD, SAMPLE_METADATA)

        # Verificar que tmdb/ fue creado
        assert (tmp_path / "raw_data" / "tmdb").is_dir()
        # Verificar que los archivos fueron escritos
        assert result.payload_path.exists()
        assert result.metadata_path.exists()


# --- Test: fallo al crear directorio lanza excepción sin archivos parciales (Req 7.5) ---


class TestDirectoryCreationFailure:
    """Si mkdir falla, se lanza excepción descriptiva sin crear archivos parciales."""

    def test_mkdir_failure_raises_descriptive_error(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Si la creación del directorio falla, se lanza OSError descriptivo."""
        monkeypatch.chdir(tmp_path)
        (tmp_path / "raw_data").mkdir()

        # Monkeypatch Path.mkdir para simular error de filesystem
        original_mkdir = Path.mkdir

        def failing_mkdir(self: Path, *args: object, **kwargs: object) -> None:
            # Solo fallar si es el directorio tmdb
            if "tmdb" in str(self):
                raise OSError("Permission denied: simulated")
            original_mkdir(self, *args, **kwargs)  # type: ignore[arg-type]

        monkeypatch.setattr(Path, "mkdir", failing_mkdir)

        writer = LocalFixtureWriter()

        with pytest.raises(OSError, match="No se pudo crear el directorio"):
            writer.write_fixture("v1", SAMPLE_PAYLOAD, SAMPLE_METADATA)

        # Verificar que no quedaron archivos parciales
        tmdb_dir = tmp_path / "raw_data" / "tmdb"
        if tmdb_dir.exists():
            remaining = list(tmdb_dir.iterdir())
            assert remaining == [], f"Archivos parciales encontrados: {remaining}"
