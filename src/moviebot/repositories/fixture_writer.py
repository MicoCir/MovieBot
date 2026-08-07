"""Protocolo e implementaciones de escritura de fixtures TMDB."""

from __future__ import annotations

import os
import re
import tempfile
from pathlib import Path
from typing import Protocol

from moviebot.repositories.tmdb_errors import (
    TmdbFixtureConflictError,
    TmdbFixtureInconsistentError,
)
from moviebot.repositories.tmdb_models import FixturePaths

_VERSION_RE = re.compile(r"[a-zA-Z0-9_-]+")


def _validate_version(version: str) -> None:
    """Valida que version sea seguro para nombre de archivo."""
    if not re.fullmatch(_VERSION_RE, version):
        raise ValueError(f"version debe matchear [a-zA-Z0-9_-]+: {version!r}")


def _fixture_filenames(version: str) -> tuple[str, str]:
    """Retorna (payload_filename, metadata_filename) para una versión dada."""
    return (
        f"trending_movies_{version}.json",
        f"trending_movies_{version}.metadata.json",
    )


class FixtureWriter(Protocol):
    """Abstracción de escritura de fixtures para inyección en tests."""

    def write_fixture(
        self, version: str, payload: bytes, metadata: bytes
    ) -> FixturePaths: ...


class LocalFixtureWriter:
    """Escritor de fixtures a disco local.

    Valida que el directorio destino sea exactamente raw_data/tmdb/.
    La ruta base_dir es relativa al CWD.
    """

    def __init__(self, base_dir: Path = Path("raw_data/tmdb")) -> None:
        resolved = base_dir.resolve()
        allowed_root = Path("raw_data/tmdb").resolve()
        if not resolved.is_relative_to(allowed_root):
            raise ValueError(
                f"base_dir debe estar dentro de raw_data/tmdb/: {base_dir}"
            )
        self._base_dir = resolved

    def write_fixture(
        self, version: str, payload: bytes, metadata: bytes
    ) -> FixturePaths:
        """Escribe payload y metadata atómicamente al directorio base."""
        return _write_fixture_to_dir(self._base_dir, version, payload, metadata)


class InMemoryFixtureWriter:
    """Escritor de fixtures en memoria para tests. No escribe a disco."""

    def __init__(self) -> None:
        self.fixtures: dict[str, tuple[bytes, bytes]] = {}

    def write_fixture(
        self, version: str, payload: bytes, metadata: bytes
    ) -> FixturePaths:
        """Almacena fixture en memoria y retorna rutas ficticias."""
        _validate_version(version)
        self.fixtures[version] = (payload, metadata)
        payload_name, metadata_name = _fixture_filenames(version)
        return FixturePaths(
            payload_path=Path(payload_name),
            metadata_path=Path(metadata_name),
        )


class TmpDirFixtureWriter:
    """Escritor de fixtures a un directorio temporal para tests de disco.

    No valida contención — es exclusivo para tests.
    """

    def __init__(self, tmp_dir: Path) -> None:
        self._base_dir = tmp_dir

    def write_fixture(
        self, version: str, payload: bytes, metadata: bytes
    ) -> FixturePaths:
        """Escribe fixture al directorio temporal sin validación de contención."""
        return _write_fixture_to_dir(self._base_dir, version, payload, metadata)


def _write_fixture_to_dir(
    base_dir: Path, version: str, payload: bytes, metadata: bytes
) -> FixturePaths:
    """Lógica compartida de escritura atómica de fixtures.

    1. Valida version
    2. Crea directorio si no existe
    3. Detecta conflicto o estado inconsistente
    4. Escribe atómicamente con temp files + os.rename
    5. Limpia temp files en caso de fallo
    """
    _validate_version(version)

    # Crear directorio si no existe
    try:
        base_dir.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise OSError(f"No se pudo crear el directorio {base_dir}: {exc}") from exc

    payload_name, metadata_name = _fixture_filenames(version)
    payload_path = base_dir / payload_name
    metadata_path = base_dir / metadata_name

    # Detectar conflicto o estado inconsistente
    payload_exists = payload_path.exists()
    metadata_exists = metadata_path.exists()

    if payload_exists and metadata_exists:
        raise TmdbFixtureConflictError(
            message=f"Fixture version {version!r} ya existe: {payload_name}, {metadata_name}",
            operation="write_fixture",
        )

    if payload_exists != metadata_exists:
        existing = payload_name if payload_exists else metadata_name
        missing = metadata_name if payload_exists else payload_name
        raise TmdbFixtureInconsistentError(
            message=(
                f"Estado inconsistente para version {version!r}: "
                f"existe {existing} pero falta {missing}"
            ),
            operation="write_fixture",
        )

    # Escritura atómica: temp files + rename
    tmp_payload_path: Path | None = None
    tmp_metadata_path: Path | None = None

    try:
        # Escribir payload a archivo temporal en el mismo directorio
        fd_p, tmp_payload_str = tempfile.mkstemp(
            dir=str(base_dir), prefix=".tmp_payload_", suffix=".json"
        )
        tmp_payload_path = Path(tmp_payload_str)
        os.write(fd_p, payload)
        os.close(fd_p)

        # Escribir metadata a archivo temporal en el mismo directorio
        fd_m, tmp_metadata_str = tempfile.mkstemp(
            dir=str(base_dir), prefix=".tmp_metadata_", suffix=".json"
        )
        tmp_metadata_path = Path(tmp_metadata_str)
        os.write(fd_m, metadata)
        os.close(fd_m)

        # Rename atómico: payload primero, luego metadata
        os.rename(str(tmp_payload_path), str(payload_path))
        tmp_payload_path = None  # Ya no necesita cleanup

        os.rename(str(tmp_metadata_path), str(metadata_path))
        tmp_metadata_path = None  # Ya no necesita cleanup

    except BaseException:
        # Cleanup de archivos temporales que todavía existan
        if tmp_payload_path is not None:
            try:
                tmp_payload_path.unlink(missing_ok=True)
            except OSError:
                pass
        if tmp_metadata_path is not None:
            try:
                tmp_metadata_path.unlink(missing_ok=True)
            except OSError:
                pass
        # Si el rename de payload tuvo éxito pero metadata falló,
        # remover el payload ya renombrado para no dejar estado parcial
        if payload_path.exists() and not metadata_path.exists():
            try:
                payload_path.unlink(missing_ok=True)
            except OSError:
                pass
        raise

    return FixturePaths(
        payload_path=payload_path,
        metadata_path=metadata_path,
    )
