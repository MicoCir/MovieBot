# Feature: source-viability-spikes, Property 7: Enterprise Configuration Rejection
"""Property-based tests for Enterprise configuration rejection.

Validates: Requirements 3.7

For any configuration dictionary that contains at least one key from the Enterprise
feature set (useNetwork, network, remotes, sharding, replication, personalization,
analytics), the validator SHALL detect and report all Enterprise features present.
For any configuration dictionary with no Enterprise keys, the validator SHALL return
an empty violation list.
"""

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from spikes.meilisearch.config_validator import (
    ENTERPRISE_FEATURES,
    validate_no_enterprise_features,
    validate_search_params,
)

# Strategy: safe keys that never collide with Enterprise feature names
_safe_keys = st.text(
    alphabet=st.characters(whitelist_categories=("L", "N"), whitelist_characters="_-"),
    min_size=1,
    max_size=20,
).filter(lambda k: k not in ENTERPRISE_FEATURES)

# Strategy: arbitrary JSON-like values (no nested dicts here; nesting tested separately)
_safe_values = st.one_of(
    st.integers(),
    st.floats(allow_nan=False, allow_infinity=False),
    st.text(max_size=50),
    st.booleans(),
    st.none(),
)

# Strategy: a flat dictionary with NO Enterprise keys
_safe_dict = st.dictionaries(keys=_safe_keys, values=_safe_values, max_size=15)

# Strategy: subset of Enterprise keys to inject
_enterprise_subset = st.frozensets(
    st.sampled_from(sorted(ENTERPRISE_FEATURES)), min_size=1
)


@pytest.mark.property
@settings(max_examples=100)
@given(config=_safe_dict)
def test_no_enterprise_keys_returns_empty(config: dict) -> None:
    """Config with no Enterprise keys produces an empty violation list."""
    result = validate_no_enterprise_features(config)
    assert result == [], f"Expected empty list but got {result}"


@pytest.mark.property
@settings(max_examples=100)
@given(base=_safe_dict, enterprise_keys=_enterprise_subset)
def test_all_enterprise_keys_detected_flat(
    base: dict, enterprise_keys: frozenset
) -> None:
    """All injected Enterprise keys in a flat dict are detected and reported."""
    config = dict(base)
    for key in enterprise_keys:
        config[key] = True  # value doesn't matter, presence triggers detection

    result = validate_no_enterprise_features(config)

    # Every injected Enterprise key must appear in the result
    for key in enterprise_keys:
        assert key in result, f"Enterprise key '{key}' not detected"

    # Result should only contain actual Enterprise keys
    for key in result:
        assert key in ENTERPRISE_FEATURES, f"Non-enterprise key '{key}' in result"


@pytest.mark.property
@settings(max_examples=100)
@given(base=_safe_dict, enterprise_keys=_enterprise_subset)
def test_enterprise_keys_detected_nested(
    base: dict, enterprise_keys: frozenset
) -> None:
    """Enterprise keys buried in nested dictionaries are still detected."""
    # Build a nested config with enterprise keys at various depths
    nested_inner = {key: {"enabled": True} for key in enterprise_keys}
    config = dict(base)
    config["settings"] = nested_inner  # enterprise keys one level deep

    result = validate_no_enterprise_features(config)

    for key in enterprise_keys:
        assert key in result, f"Nested enterprise key '{key}' not detected"


@pytest.mark.property
@settings(max_examples=100)
@given(config=_safe_dict)
def test_determinism(config: dict) -> None:
    """validate_no_enterprise_features is deterministic for identical inputs."""
    result1 = validate_no_enterprise_features(config)
    result2 = validate_no_enterprise_features(config)
    assert result1 == result2


@pytest.mark.property
@settings(max_examples=100)
@given(params=_safe_dict)
def test_search_params_no_enterprise_returns_empty(params: dict) -> None:
    """validate_search_params with no Enterprise keys returns empty list."""
    result = validate_search_params(params)
    assert result == []


@pytest.mark.property
@settings(max_examples=100)
@given(base=_safe_dict, enterprise_keys=_enterprise_subset)
def test_search_params_detects_enterprise_keys(
    base: dict, enterprise_keys: frozenset
) -> None:
    """validate_search_params detects all injected Enterprise keys."""
    params = dict(base)
    for key in enterprise_keys:
        params[key] = "some_value"

    result = validate_search_params(params)

    for key in enterprise_keys:
        assert key in result, f"Enterprise key '{key}' not detected in search params"
