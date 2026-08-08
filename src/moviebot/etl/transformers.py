"""Pure stateless transformer functions for Netflix ETL normalization.

Each function is side-effect-free and designed for property-based testing.
"""

from __future__ import annotations

import ast
import math
import re

_TYPE_MAP: dict[str, str] = {
    "movie": "movie",
    "show": "show",
}

_ID_PATTERN = re.compile(r"^t[ms]\d+$")


def normalize_type(raw: str) -> str | None:
    """Normaliza type a 'movie'|'show' o None si inválido.

    Applies case-insensitive comparison against known types.
    Returns the canonical lowercase form or None for unrecognized values.
    """
    stripped = raw.strip().lower()
    return _TYPE_MAP.get(stripped)


def parse_genres(raw: str) -> tuple[list[str], bool]:
    """Returns (normalized_list, malformed).

    malformed=True means input wasn't parseable as a Python list literal.
    An empty string is considered a valid empty input (not malformed).
    """
    stripped = raw.strip()
    if not stripped:
        return ([], False)

    try:
        parsed = ast.literal_eval(stripped)
    except (ValueError, SyntaxError):
        return ([], True)

    if not isinstance(parsed, list):
        return ([], True)

    normalized: list[str] = []
    for item in parsed:
        if isinstance(item, str):
            trimmed = item.strip().lower()
            if trimmed:
                normalized.append(trimmed)
    normalized.sort()
    return (normalized, False)


def normalize_genres(raw: str) -> list[str]:
    """Parsea lista literal de géneros → lowercase + trim + sort.

    Uses ast.literal_eval to parse Python list literals.
    Returns [] for malformed input. The ETL orchestrator is responsible
    for registering malformed cases in the quality report via parse_genres.
    """
    genres, _ = parse_genres(raw)
    return genres


def normalize_name(raw: str) -> str:
    """Lowercase + trim preservando espacios internos.

    Strips leading/trailing whitespace and converts to lowercase.
    Internal spaces between words are preserved as-is.
    """
    return raw.strip().lower()


def parse_optional_float(raw: str, min_val: float, max_val: float) -> float | None:
    """Parsea float, retorna None si inválido, NaN, Inf, o fuera de rango.

    Returns None for:
    - Empty or whitespace-only strings
    - Non-parseable values
    - NaN, Infinity, -Infinity
    - Values outside [min_val, max_val]
    """
    stripped = raw.strip()
    if not stripped:
        return None

    try:
        value = float(stripped)
    except (ValueError, OverflowError):
        return None

    if math.isnan(value) or math.isinf(value):
        return None

    if value < min_val or value > max_val:
        return None

    return value


def parse_release_year(raw: str) -> int | None:
    """Parsea int en rango 1888-2100, None si inválido.

    Returns None for non-integer values or values outside range.
    """
    stripped = raw.strip()
    if not stripped:
        return None

    try:
        value = int(stripped)
    except (ValueError, OverflowError):
        return None

    if value < 1888 or value > 2100:
        return None

    return value


def validate_id(raw: str) -> str | None:
    """Valida patrón ^t[ms]\\d+$ y longitud <= 20. Retorna stripped o None.

    Returns the trimmed ID if valid, None otherwise.
    """
    stripped = raw.strip()
    if not stripped:
        return None

    if len(stripped) > 20:
        return None

    if not _ID_PATTERN.match(stripped):
        return None

    return stripped


def validate_title(raw: str) -> str | None:
    """Retorna trimmed title si no vacío y <= 500 chars, else None."""
    stripped = raw.strip()
    if not stripped:
        return None

    if len(stripped) > 500:
        return None

    return stripped


def nullify_if_exceeds(raw: str | None, max_length: int) -> str | None:
    """Retorna el valor trimmed si es válido y no excede max_length.

    Returns None (not truncated) if:
    - raw is None
    - raw is empty or whitespace-only after trimming
    - trimmed value exceeds max_length

    Does NOT truncate — returns None for values that exceed the limit.
    """
    if raw is None:
        return None

    stripped = raw.strip()
    if not stripped:
        return None

    if len(stripped) > max_length:
        return None

    return stripped
