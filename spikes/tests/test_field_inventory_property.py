# Feature: source-viability-spikes, Property 3: Field Inventory Completeness
"""Property-based tests for field inventory completeness.

**Validates: Requirements 1.4**

For any valid JSON object, the field inventory generator SHALL produce exactly
one entry per unique field path, where each entry contains the field name, a
correct type observation matching the Python type of the value, and an example
value that is present in the original payload.
"""

from typing import Any

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from spikes.tmdb.spike_tmdb import generate_field_inventory


# --- Strategies ---

# Scalar values that can appear in JSON payloads
json_scalars = st.one_of(
    st.integers(min_value=-1_000_000, max_value=1_000_000),
    st.floats(allow_nan=False, allow_infinity=False),
    st.text(min_size=0, max_size=50),
    st.booleans(),
    st.none(),
)

# Simple flat dictionaries with string keys and scalar values
flat_dicts = st.fixed_dictionaries(
    {},
    optional=st.dictionaries(
        keys=st.from_regex(r"[a-z][a-z0-9_]{0,9}", fullmatch=True),
        values=json_scalars,
        min_size=1,
        max_size=5,
    ),
).flatmap(lambda d: st.just(d) if d else st.fixed_dictionaries(
    {"field": json_scalars}
))

# Dictionaries with at least one key guaranteed
nonempty_scalar_dicts = st.dictionaries(
    keys=st.from_regex(r"[a-z][a-z0-9_]{0,9}", fullmatch=True),
    values=json_scalars,
    min_size=1,
    max_size=6,
)

# Nested dictionaries (object fields)
nested_dicts = st.fixed_dictionaries({
    "id": st.integers(min_value=1, max_value=99999),
    "name": st.text(min_size=1, max_size=20),
    "metadata": st.fixed_dictionaries({
        "created": st.text(min_size=5, max_size=15),
        "score": st.floats(min_value=0, max_value=10, allow_nan=False),
    }),
})

# Dictionaries containing lists
dicts_with_lists = st.fixed_dictionaries({
    "title": st.text(min_size=1, max_size=20),
    "tags": st.lists(st.text(min_size=1, max_size=10), min_size=1, max_size=3),
    "count": st.integers(min_value=0, max_value=100),
})

# Dictionaries with nested objects inside lists
dicts_with_nested_lists = st.fixed_dictionaries({
    "page": st.integers(min_value=1, max_value=10),
    "results": st.lists(
        st.fixed_dictionaries({
            "id": st.integers(min_value=1, max_value=9999),
            "value": st.text(min_size=1, max_size=10),
        }),
        min_size=1,
        max_size=3,
    ),
})


def _expected_type(value: Any) -> str:
    """Determine expected observed_type following generate_field_inventory logic."""
    if isinstance(value, dict):
        return "object"
    elif isinstance(value, list):
        return "array"
    elif value is None:
        return "null"
    else:
        return type(value).__name__


def _collect_expected_paths(payload: dict[str, Any], prefix: str = "") -> set[str]:
    """Collect all expected field paths that generate_field_inventory should produce."""
    paths: set[str] = set()
    for key, value in payload.items():
        current_path = f"{prefix}.{key}" if prefix else key
        paths.add(current_path)

        if isinstance(value, dict):
            paths.update(_collect_expected_paths(value, prefix=current_path))
        elif isinstance(value, list) and value:
            first = value[0]
            item_path = f"{current_path}[0]"
            if isinstance(first, dict):
                paths.update(_collect_expected_paths(first, prefix=item_path))
            else:
                paths.add(item_path)

    return paths


# --- Property Tests ---


@pytest.mark.property
class TestFieldInventoryCompletenessProperty:
    """Property 3: Field Inventory Completeness."""

    @given(payload=nonempty_scalar_dicts)
    @settings(max_examples=100)
    def test_one_entry_per_unique_path_scalars(self, payload: dict[str, Any]):
        """Each unique field path produces exactly one entry (scalar fields)."""
        entries = generate_field_inventory(payload)
        paths = [e.path for e in entries]

        # No duplicate paths
        assert len(paths) == len(set(paths)), (
            f"Duplicate paths found: {paths}"
        )

        # Every key in payload should have an entry
        for key in payload:
            assert key in paths, f"Missing entry for path: {key}"

    @given(payload=nested_dicts)
    @settings(max_examples=100)
    def test_one_entry_per_unique_path_nested(self, payload: dict[str, Any]):
        """Each unique field path produces exactly one entry (nested objects)."""
        entries = generate_field_inventory(payload)
        paths = [e.path for e in entries]

        # No duplicate paths
        assert len(paths) == len(set(paths)), (
            f"Duplicate paths found: {paths}"
        )

        # All expected paths should be present
        expected = _collect_expected_paths(payload)
        for expected_path in expected:
            assert expected_path in paths, (
                f"Missing entry for path: {expected_path}"
            )

    @given(payload=dicts_with_lists)
    @settings(max_examples=100)
    def test_one_entry_per_unique_path_with_lists(self, payload: dict[str, Any]):
        """Each unique field path produces exactly one entry (list fields)."""
        entries = generate_field_inventory(payload)
        paths = [e.path for e in entries]

        # No duplicate paths
        assert len(paths) == len(set(paths)), (
            f"Duplicate paths found: {paths}"
        )

        # All expected paths should be present
        expected = _collect_expected_paths(payload)
        for expected_path in expected:
            assert expected_path in paths, (
                f"Missing entry for path: {expected_path}"
            )

    @given(payload=nonempty_scalar_dicts)
    @settings(max_examples=100)
    def test_correct_type_observation_scalars(self, payload: dict[str, Any]):
        """observed_type matches Python type for each scalar field."""
        entries = generate_field_inventory(payload)

        for entry in entries:
            value = payload[entry.path]
            expected = _expected_type(value)
            assert entry.observed_type == expected, (
                f"For path '{entry.path}' with value {value!r}: "
                f"expected type '{expected}', got '{entry.observed_type}'"
            )

    @given(payload=nested_dicts)
    @settings(max_examples=100)
    def test_correct_type_observation_nested(self, payload: dict[str, Any]):
        """observed_type is 'object' for dict fields and correct for inner scalars."""
        entries = generate_field_inventory(payload)
        entry_map = {e.path: e for e in entries}

        # Top-level "metadata" should be observed as "object"
        assert entry_map["metadata"].observed_type == "object"

        # Nested scalars should have correct types
        assert entry_map["metadata.created"].observed_type == "str"
        assert entry_map["metadata.score"].observed_type == "float"

        # Top-level scalars
        assert entry_map["id"].observed_type == "int"
        assert entry_map["name"].observed_type == "str"

    @given(payload=dicts_with_lists)
    @settings(max_examples=100)
    def test_correct_type_observation_arrays(self, payload: dict[str, Any]):
        """observed_type is 'array' for list fields."""
        entries = generate_field_inventory(payload)
        entry_map = {e.path: e for e in entries}

        assert entry_map["tags"].observed_type == "array"
        assert entry_map["title"].observed_type == "str"
        assert entry_map["count"].observed_type == "int"

    @given(payload=nonempty_scalar_dicts)
    @settings(max_examples=100)
    def test_example_value_exists_in_original_scalars(self, payload: dict[str, Any]):
        """example_value for scalar entries is the actual value from the payload."""
        entries = generate_field_inventory(payload)

        for entry in entries:
            original_value = payload[entry.path]
            assert entry.example_value == original_value, (
                f"For path '{entry.path}': example_value {entry.example_value!r} "
                f"does not match original {original_value!r}"
            )

    @given(payload=dicts_with_nested_lists)
    @settings(max_examples=100)
    def test_example_value_exists_in_original_nested_lists(
        self, payload: dict[str, Any]
    ):
        """example_value for nested list items references data from the original."""
        entries = generate_field_inventory(payload)
        entry_map = {e.path: e for e in entries}

        # "page" scalar should hold exact value
        assert entry_map["page"].example_value == payload["page"]

        # "results" array should note item count
        assert "items" in str(entry_map["results"].example_value)

        # Nested fields in first result element should match original
        first_result = payload["results"][0]
        assert entry_map["results[0].id"].example_value == first_result["id"]
        assert entry_map["results[0].value"].example_value == first_result["value"]

    @given(payload=dicts_with_nested_lists)
    @settings(max_examples=100)
    def test_completeness_combined(self, payload: dict[str, Any]):
        """Combined check: all paths present, unique, with correct types."""
        entries = generate_field_inventory(payload)
        paths = [e.path for e in entries]

        # Uniqueness
        assert len(paths) == len(set(paths))

        # Completeness
        expected = _collect_expected_paths(payload)
        for expected_path in expected:
            assert expected_path in paths

        # Every entry has non-empty name and path
        for entry in entries:
            assert entry.name, "Entry must have a non-empty name"
            assert entry.path, "Entry must have a non-empty path"
            assert entry.observed_type, "Entry must have an observed_type"
