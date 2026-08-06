"""URL validation, payload sanitization, and credential scanning for TMDB spike.

Provides functions to:
- Validate URLs against the authorized TMDB endpoint pattern
- Build safe TMDB trending URLs
- Recursively sanitize payloads by removing sensitive keys
- Scan text for credential patterns
"""

import re
from typing import Any, Literal

# Only the trending/movie endpoint with day or week time window is authorized
AUTHORIZED_PATTERN = re.compile(
    r"^https://api\.themoviedb\.org/3/trending/movie/(day|week)\Z"
)

# Patterns that indicate credentials or sensitive data in text
SENSITIVE_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"api_key=[^&\s]+", re.IGNORECASE),
    re.compile(r"Bearer\s+[A-Za-z0-9\-._~+/]+=*", re.IGNORECASE),
    re.compile(
        r'"(api_key|authorization|token|secret|password)"\s*:\s*"[^"]*"',
        re.IGNORECASE,
    ),
]

# Keys that must be stripped from any payload before persistence
SENSITIVE_KEYS: set[str] = {
    "api_key",
    "authorization",
    "token",
    "secret",
    "password",
    "access_token",
}


def validate_tmdb_url(url: str) -> bool:
    """Return True only if URL matches the authorized TMDB endpoint pattern.

    The authorized pattern is:
        https://api.themoviedb.org/3/trending/movie/(day|week)

    Any other URL, including sub-paths, query parameters, or different
    domains, is rejected.
    """
    return bool(AUTHORIZED_PATTERN.match(url))


def build_tmdb_url(time_window: Literal["day", "week"]) -> str:
    """Construct and validate a TMDB trending URL for the given time window.

    Args:
        time_window: Either "day" or "week".

    Returns:
        The validated URL string.

    Raises:
        AssertionError: If the constructed URL doesn't match the authorized pattern
            (should never happen with valid Literal input).
    """
    url = f"https://api.themoviedb.org/3/trending/movie/{time_window}"
    assert validate_tmdb_url(url), f"Constructed URL failed validation: {url}"
    return url


def sanitize_payload(payload: dict[str, Any]) -> dict[str, Any]:
    """Recursively remove sensitive keys from a JSON payload.

    Traverses nested dicts and lists, removing any key whose lowercase form
    is in SENSITIVE_KEYS. Non-sensitive values are preserved intact.

    Args:
        payload: The dictionary to sanitize.

    Returns:
        A new dictionary with all sensitive keys removed at every nesting level.
    """

    def _sanitize(obj: Any) -> Any:
        if isinstance(obj, dict):
            return {
                k: _sanitize(v)
                for k, v in obj.items()
                if k.lower() not in SENSITIVE_KEYS
            }
        if isinstance(obj, list):
            return [_sanitize(item) for item in obj]
        return obj

    return _sanitize(payload)


def scan_for_credentials(text: str) -> list[str]:
    """Detect credential patterns in text via regex.

    Scans the input text against all SENSITIVE_PATTERNS and returns
    the actual matched strings. An empty list means the text is safe
    to persist.

    Args:
        text: The text to scan for credential patterns.

    Returns:
        A list of matched credential strings found in the text.
        Empty list indicates no credentials detected.
    """
    matches: list[str] = []
    for pattern in SENSITIVE_PATTERNS:
        for match in pattern.finditer(text):
            matches.append(match.group())
    return matches
