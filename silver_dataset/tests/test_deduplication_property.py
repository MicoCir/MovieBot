"""Property-based tests for deduplication detection.

Feature: silver-dataset-generation, Property 18: Duplicate detection
**Validates: Requirement 6.5**

For any pair of cases where queries are exact/normalized duplicates,
the deduplicator SHALL flag them as duplicates.
"""

import pytest
from hypothesis import given, settings, assume
from hypothesis import strategies as st

from silver_dataset.models.case import (
    Difficulty,
    ExpectedAction,
    ExpectedRoute,
    ExpectedTool,
    GenerationMetadata,
    ReviewStatus,
    SilverCase,
    Split,
    Suite,
    ValidationStatus,
)
from silver_dataset.validation.deduplicator import Deduplicator


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_case(case_id: str, query: str) -> SilverCase:
    """Create a minimal valid SilverCase with the given case_id and query."""
    from datetime import datetime

    return SilverCase(
        case_id=case_id,
        dataset_version="test_v1",
        suite=Suite.e2e_routing_silver,
        split=Split.dev,
        scenario_family="test_family",
        scenario_type="test_type",
        query=query,
        conversation_context=[],
        language="en",
        response_language="en",
        expected_route=ExpectedRoute.trending,
        expected_tool=ExpectedTool.tmdb_trending,
        expected_action=ExpectedAction.call_tool,
        expected_tool_request=None,
        user_constraints={},
        tool_output_fixture_id=None,
        expected_selected_items=[],
        acceptable_selected_items=[],
        forbidden_selected_items=[],
        required_facts=[],
        optional_facts=[],
        forbidden_claims=[],
        expected_response_type="recommendation",
        difficulty=Difficulty.easy,
        tags=[],
        seed_scenario_id="seed_001",
        generation_metadata=GenerationMetadata(
            method="test",
            model="test_model",
            prompt_version="v1",
            timestamp=datetime(2024, 1, 1),
            batch_id="batch_test",
            variation_type=None,
        ),
        automatic_validation_status=ValidationStatus.passed,
        review_status=ReviewStatus.not_human_reviewed,
    )


# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------

# Generate non-empty query strings (printable text, reasonable length)
query_strategy = st.text(
    alphabet=st.characters(whitelist_categories=("L", "N", "P", "Z")),
    min_size=3,
    max_size=80,
)


# ---------------------------------------------------------------------------
# Property Tests
# ---------------------------------------------------------------------------


@pytest.mark.property
class TestDeduplicationProperty:
    """Property 18: Duplicate detection."""

    @given(query=query_strategy)
    @settings(max_examples=100)
    def test_exact_duplicates_are_always_detected(self, query: str):
        """For any pair with identical queries, deduplicator SHALL flag them."""
        assume(len(query.strip()) > 0)

        case_a = _make_case("case_001", query)
        case_b = _make_case("case_002", query)
        dedup = Deduplicator(similarity_threshold=0.85)

        duplicates = dedup.find_duplicates([case_a, case_b])

        assert len(duplicates) >= 1, (
            f"Exact duplicate pair not detected for query: {query!r}"
        )
        pair = duplicates[0]
        assert pair.match_type == "exact"
        assert pair.similarity == 1.0
        assert {pair.case_id_1, pair.case_id_2} == {"case_001", "case_002"}

    @given(
        query=st.text(
            alphabet=st.characters(
                whitelist_categories=("Nd",),
                whitelist_characters="abcdefghijklmnopqrstuvwxyz ",
            ),
            min_size=3,
            max_size=80,
        )
    )
    @settings(max_examples=100)
    def test_normalized_duplicates_detected_for_case_changes(self, query: str):
        """For any pair differing only in ASCII case, deduplicator SHALL flag them.

        Normalized match: case-insensitive with extra punctuation stripped.
        Tests with ASCII-only letters to avoid Unicode locale-specific edge cases
        (e.g., Turkish dotless-i) that are outside the scope of this property.
        """
        assume(len(query.strip()) > 0)
        # Ensure at least one letter present so case change matters
        assume(any(c.isalpha() for c in query))

        upper_query = query.upper()
        lower_query = query.lower()

        # Skip if no actual difference after case change
        assume(upper_query != lower_query)

        case_a = _make_case("case_001", upper_query)
        case_b = _make_case("case_002", lower_query)
        dedup = Deduplicator(similarity_threshold=0.85)

        duplicates = dedup.find_duplicates([case_a, case_b])

        assert len(duplicates) >= 1, (
            f"Normalized duplicate not detected: {upper_query!r} vs {lower_query!r}"
        )
        pair = duplicates[0]
        assert pair.match_type in ("exact", "normalized"), (
            f"Expected exact or normalized match, got {pair.match_type}"
        )

    @given(query=query_strategy)
    @settings(max_examples=100)
    def test_normalized_duplicates_detected_for_extra_whitespace(self, query: str):
        """For any pair differing only in whitespace, deduplicator SHALL flag them."""
        assume(len(query.strip()) > 0)

        # Add extra whitespace
        padded_query = f"  {query}  "
        spaced_query = "  ".join(query.split())

        # Ensure they're actually different strings
        assume(padded_query != query or spaced_query != query)

        case_a = _make_case("case_001", query)
        case_b = _make_case("case_002", padded_query)
        dedup = Deduplicator(similarity_threshold=0.85)

        duplicates = dedup.find_duplicates([case_a, case_b])

        assert len(duplicates) >= 1, (
            f"Normalized duplicate not detected with whitespace: "
            f"{query!r} vs {padded_query!r}"
        )

    @given(query=query_strategy)
    @settings(max_examples=100)
    def test_no_self_duplicates_reported(self, query: str):
        """A single case should never produce duplicate pairs with itself."""
        assume(len(query.strip()) > 0)

        case_a = _make_case("case_001", query)
        dedup = Deduplicator(similarity_threshold=0.85)

        duplicates = dedup.find_duplicates([case_a])

        assert len(duplicates) == 0, "Single case should not produce duplicates"

    @given(
        query_a=st.text(min_size=10, max_size=50, alphabet="abcdefghijklmnopqrstuvwxyz "),
        query_b=st.text(min_size=10, max_size=50, alphabet="0123456789"),
    )
    @settings(max_examples=100)
    def test_dissimilar_queries_not_flagged(self, query_a: str, query_b: str):
        """Queries with very low similarity should NOT be flagged as duplicates."""
        assume(len(query_a.strip()) >= 5)
        assume(len(query_b.strip()) >= 5)

        case_a = _make_case("case_001", query_a)
        case_b = _make_case("case_002", query_b)
        dedup = Deduplicator(similarity_threshold=0.85)

        duplicates = dedup.find_duplicates([case_a, case_b])

        # Alphabetic vs numeric strings should never be similar enough
        assert len(duplicates) == 0, (
            f"Dissimilar queries falsely flagged: {query_a!r} vs {query_b!r}"
        )
