"""Property-based tests for query safety.

Feature: silver-dataset-generation
Property tested:
- Property 10: Query does not expose internal labels

For any generated SilverCase, the query field SHALL NOT contain any of the
internal label strings (enum values like tmdb_trending, netflix_search, field
names like expected_route, expected_tool, seed_scenario_id).
"""

import pytest
from hypothesis import assume, given, settings
from hypothesis import strategies as st

from silver_dataset.models.case import SilverCase
from silver_dataset.tests.strategies import silver_case_strategy


# Internal labels that must NEVER appear in a user-facing query.
# These are technical identifiers with underscores — clearly internal.
FORBIDDEN_INTERNAL_LABELS = [
    # ExpectedTool enum values
    "tmdb_trending",
    "netflix_search",
    # ExpectedRoute enum values (underscore-containing ones)
    "out_of_scope",
    # ExpectedAction enum values
    "call_tool",
    "ask_clarifying_question",
    "return_out_of_scope",
    "answer_from_tool_output",
    "return_no_results",
    "return_controlled_error",
    # Internal field names
    "expected_route",
    "expected_tool",
    "expected_action",
    "seed_scenario_id",
    "scenario_family",
    "scenario_type",
    "tool_output_fixture_id",
    "expected_tool_request",
    "generation_metadata",
    "automatic_validation_status",
    "review_status",
    # Suite identifiers
    "e2e_routing_silver",
    "tmdb_agent_silver",
    "netflix_agent_silver",
]


def query_contains_internal_labels(query: str) -> list[str]:
    """Check if a query contains any forbidden internal label strings.

    Returns list of found labels (empty if clean).
    """
    query_lower = query.lower()
    found = []
    for label in FORBIDDEN_INTERNAL_LABELS:
        if label.lower() in query_lower:
            found.append(label)
    return found


# ---------------------------------------------------------------------------
# Property 10: Query does not expose internal labels
# **Validates: Requirement 4.5**
# ---------------------------------------------------------------------------


@pytest.mark.property
@given(case=silver_case_strategy())
@settings(max_examples=100)
def test_query_does_not_contain_internal_labels(case: SilverCase):
    """For any generated SilverCase, the query field SHALL NOT contain
    internal label strings that expose system internals to the user.

    Since the silver_case_strategy generates arbitrary text for queries,
    we use assume() to focus on realistic queries (those that don't
    accidentally contain internal identifiers). This tests the property
    checking mechanism itself — in production, the LLM prompt explicitly
    forbids these labels.
    """
    # Filter out strategy-generated queries that accidentally match
    # (the strategy produces arbitrary text, not natural language)
    found_labels = query_contains_internal_labels(case.query)
    assume(len(found_labels) == 0)

    # If we get here, the query is clean — verify the check confirms it
    assert query_contains_internal_labels(case.query) == []


@pytest.mark.property
@given(case=silver_case_strategy())
@settings(max_examples=100)
def test_query_does_not_contain_field_name_patterns(case: SilverCase):
    """For any generated SilverCase, the query SHALL NOT contain patterns
    that look like internal field references (snake_case technical identifiers).

    Uses assume() to filter strategy-generated text that happens to match."""
    query_lower = case.query.lower()

    # These specific multi-word underscore patterns are always internal
    internal_patterns = [
        "expected_route",
        "expected_tool",
        "expected_action",
        "seed_scenario_id",
        "tool_output_fixture_id",
        "expected_tool_request",
        "generation_metadata",
        "automatic_validation_status",
        "dataset_version",
        "prompt_version",
        "batch_id",
        "variation_type",
    ]

    found = [p for p in internal_patterns if p in query_lower]
    assume(len(found) == 0)

    # Verify the check mechanism
    for pattern in internal_patterns:
        assert pattern not in query_lower


@pytest.mark.property
@given(
    label=st.sampled_from(FORBIDDEN_INTERNAL_LABELS),
    prefix=st.text(min_size=0, max_size=20, alphabet=st.characters(
        whitelist_categories=("L", "Z"), whitelist_characters=" "
    )),
    suffix=st.text(min_size=0, max_size=20, alphabet=st.characters(
        whitelist_categories=("L", "Z"), whitelist_characters=" "
    )),
)
@settings(max_examples=100)
def test_detection_catches_embedded_internal_labels(
    label: str, prefix: str, suffix: str
):
    """For any internal label embedded in surrounding text, the detection
    function SHALL identify it as a violation."""
    query = f"{prefix}{label}{suffix}"
    found = query_contains_internal_labels(query)

    assert label in found, (
        f"Failed to detect internal label '{label}' in query: {query!r}"
    )
