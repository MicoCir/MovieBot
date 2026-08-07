"""Modelos Pydantic para fixtures TMDB."""

import re
from datetime import UTC, datetime
from pathlib import Path

from pydantic import BaseModel, field_validator


class ProvenanceMetadata(BaseModel):
    """Metadatos de procedencia del fixture TMDB."""

    version: str
    endpoint: str
    captured_at: str  # ISO 8601 UTC (validado por field_validator)
    parameters: dict[str, str]  # Solo parámetros no sensibles
    checksum_sha256: str  # 64-char hex string (validado por field_validator)

    @field_validator("version")
    @classmethod
    def validate_version(cls, v: str) -> str:
        """Valida que sea un string seguro para nombre de archivo."""
        if not re.fullmatch(r"[a-zA-Z0-9_-]+", v):
            raise ValueError(
                "version debe matchear [a-zA-Z0-9_-]+ (prevención de path traversal)"
            )
        return v

    @field_validator("captured_at")
    @classmethod
    def validate_captured_at(cls, v: str) -> str:
        """Valida que sea un string ISO 8601 estrictamente UTC."""
        try:
            dt = datetime.fromisoformat(v)
        except ValueError:
            raise ValueError("captured_at debe ser ISO 8601 válido")
        if dt.tzinfo is None or dt.utcoffset() != UTC.utcoffset(None):
            raise ValueError("captured_at debe ser UTC (Z o +00:00)")
        return v

    @field_validator("checksum_sha256")
    @classmethod
    def validate_checksum(cls, v: str) -> str:
        """Valida que sea un string hexadecimal de 64 caracteres."""
        if not re.fullmatch(r"[0-9a-f]{64}", v):
            raise ValueError("checksum_sha256 debe ser un string hex de 64 caracteres")
        return v


class FixturePaths(BaseModel):
    """Rutas de los archivos del fixture capturado."""

    payload_path: Path
    metadata_path: Path
