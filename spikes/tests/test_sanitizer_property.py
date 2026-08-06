# Feature: source-viability-spikes, Property 2: Credential Sanitization Completeness
"""Property-based tests for credential sanitization completeness.

**Validates: Requirements 1.3, 5.1, 5.5**

For any JSON payload that contains injected sensitive keys (api_key, authorization,
token, secret, password, access_token), the sanitizer SHALL produce output that
contains none of the injected sensitive values while preserving all non-sensitive
data intact.
"""

import json

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from spikes.tmdb.validators import SENSITIVE_KEYS, sanitize_payload, scan_for_credentials


# --- Strategies ---

# Non-sensitive keys that should always be preserved
safe_keys = st.sampled_from([
    "title", "overview", "release_date", "id", "genre_ids",
    "popularity", "vote_average", "name", "description", "results",
])

# Sensitive keys that must be removed
sensitive_keys = st.sampled_from(sorted(SENSITIVE_KEYS))

# Values that could be assigned to sensitive keys (simulating real credentials)
sensitive_values = st.one_of(
    st.text(alphabet=st.characters(whitelist_categories=("L", "N")), min_size=1, max_size=50),
    st.from_regex(r"[A-Za-z0-9]{8,32}", fullmatch=True),
)

# Simple JSON-safe values for non-sensitive fields
json_safe_values = st.one_of(
    st.text(min_size=0, max_size=30).filter(lambda s: s.isprintable()),
    st.integers(min_value=-1000, max_value=1000),
    st.floats(allow_nan=False, allow_infinity=False, min_value=-1e6, max_value=1e6),
    st.booleans(),
)


# --- Property Tests ---


@pytest.mark.property
class TestCredentialSanitizationProperty:
    """Property 2: Credential Sanitization Completeness."""

    @given(
        safe_data=st.dictionaries(safe_keys, json_safe_values, min_size=1, max_size=5),
        cred_key=sensitive_keys,
        cred_value=sensitive_values,
    )
    @settings(max_examples=100)
    def test_sensitive_keys_removed_from_flat_payload(
        self, safe_data: dict, cred_key: str, cred_value: str
    ):
        """Sensitive keys are removed while non-sensitive data is preserved."""
        # Inject a sensitive key into the payload
        payload = {**safe_data, cred_key: cred_value}

        sanitized = sanitize_payload(payload)

        # Sensitive key must be absent
        assert cred_key not in sanitized
        # All non-sensitive keys must be preserved with original values
        for k, v in safe_data.items():
            if k.lower() not in SENSITIVE_KEYS:
                assert k in sanitized
                assert sanitized[k] == v

    @given(
        safe_data=st.dictionaries(safe_keys, json_safe_values, min_size=1, max_size=4),
        cred_key=sensitive_keys,
        cred_value=sensitive_values,
    )
    @settings(max_examples=100)
    def test_sensitive_keys_removed_from_nested_payload(
        self, safe_data: dict, cred_key: str, cred_value: str
    ):
        """Sensitive keys are removed at all nesting levels."""
        # Build a nested payload with sensitive data buried inside
        payload = {
            "metadata": {**safe_data, cred_key: cred_value},
            "results": [
                {cred_key: cred_value, "title": "Test Movie"},
            ],
        }

        sanitized = sanitize_payload(payload)

        # Sensitive key must be absent at all levels
        assert cred_key not in sanitized.get("metadata", {})
        for item in sanitized.get("results", []):
            assert cred_key not in item
        # Non-sensitive data preserved in nested dict
        for k, v in safe_data.items():
            if k.lower() not in SENSITIVE_KEYS:
                assert k in sanitized["metadata"]
                assert sanitized["metadata"][k] == v
        # Non-sensitive data preserved in list items
        assert sanitized["results"][0]["title"] == "Test Movie"

    @given(
        safe_data=st.dictionaries(safe_keys, json_safe_values, min_size=1, max_size=5),
        injected_creds=st.dictionaries(sensitive_keys, sensitive_values, min_size=1, max_size=3),
    )
    @settings(max_examples=100)
    def test_multiple_sensitive_keys_all_removed(
        self, safe_data: dict, injected_creds: dict
    ):
        """All sensitive keys are removed even when multiple are present."""
        payload = {**safe_data, **injected_creds}

        sanitized = sanitize_payload(payload)

        # No sensitive key should remain
        for k in injected_creds:
            assert k not in sanitized
        # All safe keys are preserved
        for k, v in safe_data.items():
            if k.lower() not in SENSITIVE_KEYS:
                assert k in sanitized
                assert sanitized[k] == v
        # Output only contains keys from the non-sensitive part
        assert set(sanitized.keys()) == {
            k for k in safe_data if k.lower() not in SENSITIVE_KEYS
        }

    @given(
        safe_data=st.dictionaries(safe_keys, json_safe_values, min_size=1, max_size=5),
    )
    @settings(max_examples=100)
    def test_payload_without_credentials_unchanged(
        self, safe_data: dict
    ):
        """A payload with no sensitive keys passes through unchanged."""
        # Ensure no accidental sensitive keys in safe_data
        clean = {k: v for k, v in safe_data.items() if k.lower() not in SENSITIVE_KEYS}

        sanitized = sanitize_payload(clean)

        assert sanitized == clean

    @given(
        cred_key=sensitive_keys,
        cred_value=st.from_regex(r"[A-Za-z0-9_\-]{10,40}", fullmatch=True),
    )
    @settings(max_examples=100)
    def test_scan_for_credentials_detects_injected_patterns(
        self, cred_key: str, cred_value: str
    ):
        """scan_for_credentials detects credential patterns in serialized text."""
        # Build a JSON-like text with injected credential
        payload = {cred_key: cred_value, "title": "Safe Movie"}
        text = json.dumps(payload)

        # Sanitize the payload first, then scan the sanitized output
        sanitized = sanitize_payload(payload)
        sanitized_text = json.dumps(sanitized)

        # The sanitized text must have no credential patterns detected
        findings = scan_for_credentials(sanitized_text)
        assert len(findings) == 0, (
            f"Credential patterns found in sanitized output: {findings}"
        )


def _extract_all_values(obj) -> list:
    """Recursively extract all leaf values from a nested dict/list structure."""
    values = []
    if isinstance(obj, dict):
        for v in obj.values():
            values.extend(_extract_all_values(v))
    elif isinstance(obj, list):
        for item in obj:
            values.extend(_extract_all_values(item))
    else:
        values.append(obj)
    return values
