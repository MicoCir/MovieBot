"""Enterprise feature detection for Meilisearch configuration.

Validates that a Meilisearch configuration does not activate any
Enterprise-only capability (useNetwork, network, remotes, sharding,
replication, personalization, analytics).
"""

from typing import Any

ENTERPRISE_FEATURES: frozenset[str] = frozenset(
    {
        "useNetwork",
        "network",
        "remotes",
        "sharding",
        "replication",
        "personalization",
        "analytics",
    }
)


def validate_no_enterprise_features(config: dict[str, Any]) -> list[str]:
    """Check a configuration dictionary for Enterprise-only features.

    Recursively inspects all keys in the config. Any key that matches
    an entry in ENTERPRISE_FEATURES is reported as a violation.

    Args:
        config: Meilisearch configuration dictionary (may be nested).

    Returns:
        List of detected Enterprise feature names. Empty means compliant.
    """
    detected: list[str] = []
    _scan_dict(config, detected)
    return sorted(set(detected))


def validate_search_params(params: dict[str, Any]) -> list[str]:
    """Check search parameters for Enterprise-only options.

    Inspects the search params dictionary for keys that correspond
    to Enterprise-only capabilities.

    Args:
        params: Search parameters dictionary.

    Returns:
        List of detected Enterprise feature names. Empty means compliant.
    """
    detected: list[str] = []
    _scan_dict(params, detected)
    return sorted(set(detected))


def _scan_dict(d: dict[str, Any], detected: list[str]) -> None:
    """Recursively scan a dictionary for Enterprise feature keys."""
    for key, value in d.items():
        if key in ENTERPRISE_FEATURES:
            detected.append(key)
        if isinstance(value, dict):
            _scan_dict(value, detected)
