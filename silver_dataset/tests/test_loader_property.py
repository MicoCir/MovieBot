"""Property-based tests for the SilverDatasetLoader.

Feature: silver-dataset-generation
Properties tested:
- Property 12: Holdout access control
- Property 13: Loader filter correctness
- Property 14: Loader rejects invalid version
- Property 15: Stable ordering
"""

import json
from datetime import datetime
from pathlib import Path

import pytest
from hypothesis import given, settings, HealthCheck
from hypothesis import strategies as st

from silver_dataset.io.jsonl import write_jsonl
from silver_dataset.io.loader import LoaderError, SilverDatasetLoader
from silver_dataset.models.case import (
    Difficulty,
    ExpectedAction,
    ExpectedRoute,
    ExpectedTool,
    GenerationMetadata,
    SilverCase,
    Split,
    Suite,
    ValidationStatus,
    ReviewStatus,
)


# ---------------------------------------------------------------------------
# Helpers: deterministic test cases with known properties
# ---------------------------------------------------------------------------

def _make_case(
    case_id: str,
    suite: Suite = Suite.e2e_routing_silver,
    split: Split = Split.dev,
    route: ExpectedRoute = ExpectedRoute.trending,
    tool: ExpectedTool = ExpectedTool.tmdb_trending,
    action: ExpectedAction = ExpectedAction.call_tool,
    tags: list[str] | None = None,
) -> SilverCase:
    """Build a valid SilverCase with customizable key fields."""
    # Enforce consistency: clarification/out_of_scope require tool=none
    if route in (ExpectedRoute.clarification, ExpectedRoute.out_of_scope):
        tool = ExpectedTool.none
        if route == ExpectedRoute.out_of_scope:
            action = ExpectedAction.return_out_of_scope
        else:
            action = ExpectedAction.ask_clarifying_question
    # call_tool requires a real tool
    if action == ExpectedAction.call_tool and tool == ExpectedTool.none:
        tool = ExpectedTool.tmdb_trending

    return SilverCase(
        case_id=case_id,
        dataset_version="silver_v1",
        suite=suite,
        split=split,
        scenario_family="test_family",
        scenario_type="test_type",
        query=f"Test query for {case_id}",
        conversation_context=[],
        language="en",
        response_language="en",
        expected_route=route,
        expected_tool=tool,
        expected_action=action,
        expected_tool_request=None,
        user_constraints={},
        tool_output_fixture_id=None,
        expected_selected_items=[],
        acceptable_selected_items=[],
        forbidden_selected_items=[],
        required_facts=[],
        optional_facts=[],
        forbidden_claims=[],
        expected_response_type="movie_list",
        difficulty=Difficulty.easy,
        tags=tags or [],
        seed_scenario_id="seed-001",
        generation_metadata=GenerationMetadata(
            method="test",
            model="test-model",
            prompt_version="v1",
            timestamp=datetime(2024, 1, 1),
            batch_id="batch-test",
            variation_type=None,
        ),
        automatic_validation_status=ValidationStatus.passed,
        review_status=ReviewStatus.not_human_reviewed,
    )


# A fixed set of cases covering different suites, splits, routes, and tags
_DIVERSE_CASES = [
    _make_case("case-01", suite=Suite.e2e_routing_silver, split=Split.dev,
               route=ExpectedRoute.trending, tags=["trending", "en"]),
    _make_case("case-02", suite=Suite.e2e_routing_silver, split=Split.test,
               route=ExpectedRoute.netflix, tool=ExpectedTool.netflix_search,
               action=ExpectedAction.call_tool, tags=["netflix", "en"]),
    _make_case("case-03", suite=Suite.tmdb_agent_silver, split=Split.dev,
               route=ExpectedRoute.trending, tags=["trending", "hard"]),
    _make_case("case-04", suite=Suite.tmdb_agent_silver, split=Split.holdout,
               route=ExpectedRoute.trending, tags=["trending", "holdout-tag"]),
    _make_case("case-05", suite=Suite.netflix_agent_silver, split=Split.dev,
               route=ExpectedRoute.clarification, tags=["clarification"]),
    _make_case("case-06", suite=Suite.netflix_agent_silver, split=Split.holdout,
               route=ExpectedRoute.out_of_scope, tags=["out_of_scope"]),
    _make_case("case-07", suite=Suite.e2e_routing_silver, split=Split.dev,
               route=ExpectedRoute.trending, tags=["trending", "en", "hard"]),
    _make_case("case-08", suite=Suite.e2e_routing_silver, split=Split.test,
               route=ExpectedRoute.out_of_scope, tags=["out_of_scope", "es"]),
]


@pytest.fixture
def dataset_dir(tmp_path: Path) -> Path:
    """Create a temp directory with a silver.jsonl file containing diverse cases."""
    write_jsonl(_DIVERSE_CASES, tmp_path / "silver.jsonl")
    return tmp_path


# ---------------------------------------------------------------------------
# Property 12: Holdout access control
# **Validates: Requirements 7.3, 8.4**
# ---------------------------------------------------------------------------

# Feature: silver-dataset-generation, Property 12: Holdout access control
# **Validates: Requirements 7.3, 8.4**
@pytest.mark.property
def test_holdout_blocked_in_development_mode(dataset_dir: Path):
    """For any load request targeting the holdout split in development mode,
    the loader SHALL reject the request with PermissionError."""
    loader = SilverDatasetLoader(dataset_dir, mode="development")
    with pytest.raises(PermissionError):
        loader.load(split=Split.holdout)


# Feature: silver-dataset-generation, Property 12: Holdout access control
# **Validates: Requirements 7.3, 8.4**
@pytest.mark.property
def test_holdout_allowed_in_evaluation_mode(dataset_dir: Path):
    """For any load request targeting the holdout split in evaluation mode,
    the loader SHALL allow access and return matching cases."""
    loader = SilverDatasetLoader(dataset_dir, mode="evaluation")
    cases = loader.load(split=Split.holdout)
    # We know there are 2 holdout cases in _DIVERSE_CASES (case-04, case-06)
    assert len(cases) == 2
    assert all(c.split == Split.holdout for c in cases)


# Feature: silver-dataset-generation, Property 12: Holdout access control
# **Validates: Requirements 7.3, 8.4**
@pytest.mark.property
@given(
    suite=st.sampled_from(Suite),
    route=st.sampled_from(ExpectedRoute),
)
@settings(
    max_examples=100,
    suppress_health_check=[HealthCheck.function_scoped_fixture],
)
def test_holdout_always_blocked_regardless_of_filters(
    dataset_dir: Path, suite: Suite, route: ExpectedRoute
):
    """For any combination of other filters, requesting holdout in dev mode
    SHALL always raise PermissionError."""
    loader = SilverDatasetLoader(dataset_dir, mode="development")
    with pytest.raises(PermissionError):
        loader.load(split=Split.holdout, suite=suite, route=route)


# Feature: silver-dataset-generation, Property 12: Holdout access control
# **Validates: Requirements 7.3, 8.4**
@pytest.mark.property
@given(
    suite=st.none() | st.sampled_from(Suite),
    route=st.none() | st.sampled_from(ExpectedRoute),
)
@settings(
    max_examples=100,
    suppress_health_check=[HealthCheck.function_scoped_fixture],
)
def test_holdout_always_allowed_in_evaluation_regardless_of_filters(
    dataset_dir: Path, suite: Suite | None, route: ExpectedRoute | None
):
    """For any combination of other filters, requesting holdout in evaluation mode
    SHALL never raise PermissionError."""
    loader = SilverDatasetLoader(dataset_dir, mode="evaluation")
    # Should not raise — may return empty list if filters don't match
    cases = loader.load(split=Split.holdout, suite=suite, route=route)
    # All returned cases must be holdout
    for c in cases:
        assert c.split == Split.holdout


# ---------------------------------------------------------------------------
# Property 13: Loader filter correctness
# **Validates: Requirement 8.1**
# ---------------------------------------------------------------------------

# Feature: silver-dataset-generation, Property 13: Loader filter correctness
# **Validates: Requirement 8.1**
@pytest.mark.property
@given(
    suite=st.none() | st.sampled_from(Suite),
    split=st.none() | st.sampled_from([Split.dev, Split.test]),
    route=st.none() | st.sampled_from(ExpectedRoute),
)
@settings(
    max_examples=100,
    suppress_health_check=[HealthCheck.function_scoped_fixture],
)
def test_all_returned_cases_match_every_filter(
    dataset_dir: Path,
    suite: Suite | None,
    split: Split | None,
    route: ExpectedRoute | None,
):
    """For any valid combination of filters, all cases returned SHALL match
    every specified filter criterion."""
    loader = SilverDatasetLoader(dataset_dir, mode="development")
    cases = loader.load(suite=suite, split=split, route=route)

    for case in cases:
        if suite is not None:
            assert case.suite == suite, (
                f"Case {case.case_id} has suite={case.suite}, expected {suite}"
            )
        if split is not None:
            assert case.split == split, (
                f"Case {case.case_id} has split={case.split}, expected {split}"
            )
        if route is not None:
            assert case.expected_route == route, (
                f"Case {case.case_id} has route={case.expected_route}, expected {route}"
            )


# Feature: silver-dataset-generation, Property 13: Loader filter correctness
# **Validates: Requirement 8.1**
@pytest.mark.property
@given(
    tags=st.lists(
        st.sampled_from(["trending", "en", "hard", "netflix", "clarification",
                         "out_of_scope", "holdout-tag", "es"]),
        min_size=1,
        max_size=3,
        unique=True,
    ),
)
@settings(
    max_examples=100,
    suppress_health_check=[HealthCheck.function_scoped_fixture],
)
def test_tag_filter_all_returned_cases_have_all_tags(
    dataset_dir: Path, tags: list[str]
):
    """For any tags filter, all returned cases SHALL carry ALL specified tags."""
    loader = SilverDatasetLoader(dataset_dir, mode="evaluation")
    cases = loader.load(tags=tags)

    for case in cases:
        for tag in tags:
            assert tag in case.tags, (
                f"Case {case.case_id} missing tag '{tag}', has tags={case.tags}"
            )


# Feature: silver-dataset-generation, Property 13: Loader filter correctness
# **Validates: Requirement 8.1**
@pytest.mark.property
@given(
    suite=st.none() | st.sampled_from(Suite),
    split=st.none() | st.sampled_from([Split.dev, Split.test]),
    route=st.none() | st.sampled_from(ExpectedRoute),
    tags=st.none() | st.lists(
        st.sampled_from(["trending", "en", "hard"]),
        min_size=1,
        max_size=2,
        unique=True,
    ),
)
@settings(
    max_examples=100,
    suppress_health_check=[HealthCheck.function_scoped_fixture],
)
def test_combined_filters_all_criteria_satisfied(
    dataset_dir: Path,
    suite: Suite | None,
    split: Split | None,
    route: ExpectedRoute | None,
    tags: list[str] | None,
):
    """For any valid combination of all filter dimensions, all returned cases
    SHALL satisfy every active filter criterion simultaneously."""
    loader = SilverDatasetLoader(dataset_dir, mode="development")
    cases = loader.load(suite=suite, split=split, route=route, tags=tags)

    for case in cases:
        if suite is not None:
            assert case.suite == suite
        if split is not None:
            assert case.split == split
        if route is not None:
            assert case.expected_route == route
        if tags is not None:
            for tag in tags:
                assert tag in case.tags


# ---------------------------------------------------------------------------
# Property 14: Loader rejects invalid version
# **Validates: Requirement 8.2**
# ---------------------------------------------------------------------------

# Feature: silver-dataset-generation, Property 14: Loader rejects invalid version
# **Validates: Requirement 8.2**
@pytest.mark.property
@given(
    version=st.text(
        alphabet=st.characters(whitelist_categories=("L", "N"), whitelist_characters="_-"),
        min_size=1,
        max_size=30,
    ),
)
@settings(
    max_examples=100,
    suppress_health_check=[HealthCheck.function_scoped_fixture],
)
def test_unknown_version_rejected_before_returning_cases(
    dataset_dir: Path, version: str
):
    """For any load request specifying an unknown version, the loader SHALL
    reject before returning cases."""
    # dataset_dir only contains silver.jsonl (unversioned), never silver_{version}.jsonl
    loader = SilverDatasetLoader(dataset_dir, mode="development")
    with pytest.raises(LoaderError) as exc_info:
        loader.load(version=version)
    assert "Unknown dataset version" in str(exc_info.value)


# Feature: silver-dataset-generation, Property 14: Loader rejects invalid version
# **Validates: Requirement 8.2**
@pytest.mark.property
def test_unknown_version_raised_before_any_io(tmp_path: Path):
    """When no JSONL file exists for the requested version, LoaderError is raised
    immediately without attempting to read or filter data."""
    # Create silver.jsonl but request a versioned file that doesn't exist
    write_jsonl([_DIVERSE_CASES[0]], tmp_path / "silver.jsonl")
    loader = SilverDatasetLoader(tmp_path, mode="development")
    with pytest.raises(LoaderError):
        loader.load(version="nonexistent_v99")


# ---------------------------------------------------------------------------
# Property 15: Stable ordering
# **Validates: Requirement 8.5**
# ---------------------------------------------------------------------------

# Feature: silver-dataset-generation, Property 15: Stable ordering
# **Validates: Requirement 8.5**
@pytest.mark.property
@given(
    suite=st.none() | st.sampled_from(Suite),
    split=st.none() | st.sampled_from([Split.dev, Split.test]),
    route=st.none() | st.sampled_from(ExpectedRoute),
)
@settings(
    max_examples=100,
    suppress_health_check=[HealthCheck.function_scoped_fixture],
)
def test_identical_query_returns_same_order(
    dataset_dir: Path,
    suite: Suite | None,
    split: Split | None,
    route: ExpectedRoute | None,
):
    """For any identical filter query executed multiple times, the loader SHALL
    return cases in the same order."""
    loader = SilverDatasetLoader(dataset_dir, mode="development")

    result_1 = loader.load(suite=suite, split=split, route=route)
    result_2 = loader.load(suite=suite, split=split, route=route)

    assert len(result_1) == len(result_2)
    for c1, c2 in zip(result_1, result_2):
        assert c1.case_id == c2.case_id, (
            f"Order mismatch: {c1.case_id} != {c2.case_id}"
        )


# Feature: silver-dataset-generation, Property 15: Stable ordering
# **Validates: Requirement 8.5**
@pytest.mark.property
def test_stable_ordering_is_sorted_by_case_id(dataset_dir: Path):
    """The loader SHALL sort results by case_id for stable, deterministic ordering."""
    loader = SilverDatasetLoader(dataset_dir, mode="evaluation")
    cases = loader.load()

    case_ids = [c.case_id for c in cases]
    assert case_ids == sorted(case_ids), (
        f"Cases not sorted by case_id: {case_ids}"
    )


# Feature: silver-dataset-generation, Property 15: Stable ordering
# **Validates: Requirement 8.5**
@pytest.mark.property
@given(
    tags=st.none() | st.lists(
        st.sampled_from(["trending", "en", "hard"]),
        min_size=1,
        max_size=2,
        unique=True,
    ),
)
@settings(
    max_examples=100,
    suppress_health_check=[HealthCheck.function_scoped_fixture],
)
def test_stable_ordering_with_tags_filter(dataset_dir: Path, tags: list[str] | None):
    """For any tag filter query executed multiple times, the loader SHALL
    return cases in the same order."""
    loader = SilverDatasetLoader(dataset_dir, mode="evaluation")

    result_1 = loader.load(tags=tags)
    result_2 = loader.load(tags=tags)

    ids_1 = [c.case_id for c in result_1]
    ids_2 = [c.case_id for c in result_2]
    assert ids_1 == ids_2
