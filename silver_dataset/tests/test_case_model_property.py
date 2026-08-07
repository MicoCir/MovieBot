"""Property-based tests for the SilverCase model.

Feature: silver-dataset-generation
Properties tested:
- Property 1: Serialization round-trip
- Property 1 extended: JSONL round-trip
- Property 2: Route/tool/action consistency enforcement
- Property 19: Dataset invariants — status fields
"""

import pathlib

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st
from pydantic import ValidationError

from silver_dataset.io.jsonl import read_jsonl, write_jsonl
from silver_dataset.models.case import (
    ExpectedAction,
    ExpectedRoute,
    ExpectedTool,
    ReviewStatus,
    SilverCase,
    ValidationStatus,
)
from silver_dataset.tests.strategies import silver_case_strategy


def _valid_case_data() -> dict:
    """Return a minimal valid SilverCase data dict for mutation-based tests."""
    return {
        "case_id": "test-case-001",
        "dataset_version": "silver_v1",
        "suite": "e2e_routing_silver",
        "split": "dev",
        "scenario_family": "routing_direct",
        "scenario_type": "trending_basic",
        "query": "What movies are trending today?",
        "conversation_context": [],
        "language": "en",
        "response_language": "en",
        "expected_route": "trending",
        "expected_tool": "tmdb_trending",
        "expected_action": "call_tool",
        "expected_tool_request": None,
        "user_constraints": {},
        "tool_output_fixture_id": None,
        "expected_selected_items": [],
        "acceptable_selected_items": [],
        "forbidden_selected_items": [],
        "required_facts": [],
        "optional_facts": [],
        "forbidden_claims": [],
        "expected_response_type": "movie_list",
        "difficulty": "easy",
        "tags": ["trending"],
        "seed_scenario_id": "seed-001",
        "generation_metadata": {
            "method": "ollama",
            "model": "qwen3.5:27b",
            "prompt_version": "v1",
            "timestamp": "2024-01-01T00:00:00",
            "batch_id": "batch-001",
            "variation_type": None,
        },
        "automatic_validation_status": "passed",
        "review_status": "not_human_reviewed",
    }


# Feature: silver-dataset-generation, Property 1: Serialization round-trip
# **Validates: Requirements 1.7, 12.3**
@pytest.mark.property
@given(case=silver_case_strategy())
@settings(max_examples=100)
def test_serialization_round_trip(case: SilverCase):
    """For any valid SilverCase instance, serializing to JSON and parsing back
    SHALL produce an equivalent object at every step (double round-trip)."""
    # Serialize to JSON dict
    json_data = case.model_dump(mode="json")
    # Parse back
    restored = SilverCase.model_validate(json_data)
    # They should be equivalent
    assert restored == case

    # Second round
    json_data_2 = restored.model_dump(mode="json")
    restored_2 = SilverCase.model_validate(json_data_2)
    assert restored_2 == case


# Feature: silver-dataset-generation, Property 2: Route/tool/action consistency enforcement
# **Validates: Requirements 1.5, 6.2**
@pytest.mark.property
@given(case=silver_case_strategy())
@settings(max_examples=100)
def test_valid_cases_have_consistent_route_tool_action(case: SilverCase):
    """For any valid SilverCase produced by the strategy, the route/tool/action
    combination SHALL be consistent:
    - clarification/out_of_scope routes have tool=none
    - call_tool action never has tool=none
    """
    if case.expected_route in (
        ExpectedRoute.clarification,
        ExpectedRoute.out_of_scope,
    ):
        assert case.expected_tool == ExpectedTool.none, (
            f"Route '{case.expected_route.value}' must have tool='none', "
            f"got '{case.expected_tool.value}'"
        )

    if case.expected_action == ExpectedAction.call_tool:
        assert case.expected_tool != ExpectedTool.none, (
            "Action 'call_tool' must have a non-none tool, "
            f"got '{case.expected_tool.value}'"
        )


# Feature: silver-dataset-generation, Property 2: Route/tool/action consistency enforcement
# **Validates: Requirements 1.5, 6.2**
@pytest.mark.property
@given(
    route=st.sampled_from([ExpectedRoute.clarification, ExpectedRoute.out_of_scope]),
    tool=st.sampled_from([ExpectedTool.tmdb_trending, ExpectedTool.netflix_search]),
)
@settings(max_examples=100)
def test_invalid_route_with_non_none_tool_rejected(
    route: ExpectedRoute,
    tool: ExpectedTool,
):
    """For any case with expected_route=clarification or out_of_scope and a
    non-none tool, the model_validator SHALL reject with ValueError."""
    data = _valid_case_data()
    data["expected_route"] = route.value
    data["expected_tool"] = tool.value
    # Ensure action is not call_tool to isolate the route/tool violation
    data["expected_action"] = ExpectedAction.ask_clarifying_question.value

    with pytest.raises(ValidationError) as exc_info:
        SilverCase.model_validate(data)

    assert "expected_tool must be 'none'" in str(exc_info.value)


# Feature: silver-dataset-generation, Property 2: Route/tool/action consistency enforcement
# **Validates: Requirements 1.5, 6.2**
@pytest.mark.property
@given(
    action=st.just(ExpectedAction.call_tool),
    tool=st.just(ExpectedTool.none),
)
@settings(max_examples=100)
def test_invalid_call_tool_with_none_tool_rejected(
    action: ExpectedAction,
    tool: ExpectedTool,
):
    """For any case with expected_action=call_tool and expected_tool=none,
    the model_validator SHALL reject with ValueError."""
    data = _valid_case_data()
    data["expected_action"] = action.value
    data["expected_tool"] = tool.value
    # Use a route that doesn't conflict (trending allows any tool)
    data["expected_route"] = ExpectedRoute.trending.value

    with pytest.raises(ValidationError) as exc_info:
        SilverCase.model_validate(data)

    assert "expected_tool must not be 'none'" in str(exc_info.value)


# Feature: silver-dataset-generation, Property 19: Dataset invariants — status fields
# **Validates: Requirements 6.7, 6.8**
@pytest.mark.property
@given(case=silver_case_strategy())
@settings(max_examples=100)
def test_automatic_validation_status_is_valid_enum(case: SilverCase):
    """For any valid SilverCase, automatic_validation_status SHALL be a valid
    ValidationStatus enum value (passed, warning, or failed)."""
    assert case.automatic_validation_status in ValidationStatus
    assert case.automatic_validation_status.value in ("passed", "warning", "failed")


# Feature: silver-dataset-generation, Property 19: Dataset invariants — status fields
# **Validates: Requirements 6.7, 6.8**
@pytest.mark.property
@given(data=st.data())
@settings(max_examples=100)
def test_review_status_defaults_to_not_human_reviewed(data: st.DataObject):
    """For any case in the Silver Dataset where review_status is not explicitly set,
    review_status SHALL default to not_human_reviewed (silver dataset invariant)."""
    # Build a valid case without explicitly setting review_status to verify the default
    case_data = _valid_case_data()
    # Remove review_status to rely on the model default
    case_data.pop("review_status", None)

    # Vary the automatic_validation_status to show the property holds for all statuses
    status = data.draw(st.sampled_from(ValidationStatus))
    case_data["automatic_validation_status"] = status.value

    case = SilverCase.model_validate(case_data)

    assert case.review_status == ReviewStatus.not_human_reviewed
    assert case.review_status.value == "not_human_reviewed"


# Feature: silver-dataset-generation, Property 1 extended: JSONL round-trip
# **Validates: Requirements 12.1, 12.3**
@pytest.mark.property
@given(cases=st.lists(silver_case_strategy(), min_size=1, max_size=5))
@settings(max_examples=100)
def test_jsonl_round_trip(cases: list[SilverCase]):
    """For any list of valid SilverCase instances, writing to JSONL and
    reading back SHALL produce equivalent objects."""
    import tempfile

    with tempfile.TemporaryDirectory() as tmp_dir:
        jsonl_path = pathlib.Path(tmp_dir) / "test.jsonl"

        # Write
        written = write_jsonl(cases, jsonl_path)
        assert written == len(cases)

        # Read back
        restored, errors = read_jsonl(jsonl_path)
        assert len(errors) == 0
        assert len(restored) == len(cases)

        for original, restored_case in zip(cases, restored):
            assert original == restored_case
