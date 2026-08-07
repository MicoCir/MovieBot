"""Property-based tests for the baseline runner and failure analysis.

Feature: silver-dataset-generation, Property 22: Failure analysis is read-only

For any execution of the failure analysis pipeline over a set of SilverCase
instances, no case's labels, query, or expected_* fields SHALL be modified
after the analysis completes.

**Validates: Requirements 10.3**
"""

import copy

import pytest
from hypothesis import given, settings

from silver_dataset.evaluation.failure_analysis import analyze_failures
from silver_dataset.evaluation.runner import RunTrace
from silver_dataset.tests.strategies import silver_case_strategy

from hypothesis import strategies as st


# ---------------------------------------------------------------------------
# Helper strategy: generate a list of RunTrace instances for the given cases
# ---------------------------------------------------------------------------


@st.composite
def run_traces_for_cases(draw, cases):
    """Generate a list of RunTrace instances (mix of success and failure) for a list of cases."""
    traces = []
    run_id = draw(st.text(min_size=1, max_size=20))
    dataset_version = draw(st.text(min_size=1, max_size=20))

    for case in cases:
        # Randomly decide if this trace is a success, functional failure, or infra error
        outcome = draw(st.sampled_from(["success", "functional", "infra"]))
        if outcome == "success":
            error = None
            is_infra = False
            prediction = {"route": case.expected_route.value}
        elif outcome == "functional":
            error = draw(st.text(min_size=1, max_size=80))
            is_infra = False
            prediction = {}
        else:
            error = "ConnectionError: timed out"
            is_infra = True
            prediction = {}

        traces.append(
            RunTrace(
                run_id=run_id,
                case_id=case.case_id,
                dataset_version=dataset_version,
                code_version="dev",
                attempt=1,
                prediction=prediction,
                error=error,
                is_infra_error=is_infra,
                duration_ms=draw(st.floats(min_value=0.0, max_value=5000.0, allow_nan=False)),
            )
        )
    return traces


# ---------------------------------------------------------------------------
# Property 22: Failure analysis is read-only
# ---------------------------------------------------------------------------


@pytest.mark.property
@settings(max_examples=100)
@given(cases=st.lists(silver_case_strategy(), min_size=1, max_size=5))
def test_failure_analysis_is_read_only(cases):
    """Failure analysis SHALL NOT modify any case's labels, query, or expected_* fields.

    **Validates: Requirements 10.3**

    Strategy:
    1. Deep-copy the list of cases before running analysis.
    2. Build synthetic traces for those cases (mix of success/failure).
    3. Run analyze_failures().
    4. Compare every field of every case against the pre-analysis snapshot.
    """
    # Deep copy the cases before running analysis
    cases_before = copy.deepcopy(cases)

    # Build traces deterministically (always include at least one failure)
    traces = []
    for i, case in enumerate(cases):
        if i == 0:
            # Ensure at least one failure exists so analysis does real work
            traces.append(
                RunTrace(
                    run_id="run-test",
                    case_id=case.case_id,
                    dataset_version=case.dataset_version,
                    code_version="dev",
                    attempt=1,
                    prediction={},
                    error="ValueError: wrong answer",
                    is_infra_error=False,
                    duration_ms=10.0,
                )
            )
        else:
            traces.append(
                RunTrace(
                    run_id="run-test",
                    case_id=case.case_id,
                    dataset_version=case.dataset_version,
                    code_version="dev",
                    attempt=1,
                    prediction={"route": case.expected_route.value},
                    error=None,
                    is_infra_error=False,
                    duration_ms=5.0,
                )
            )

    # Run the failure analysis
    analysis = analyze_failures(traces, cases)

    # Assert that the analysis produced valid output (sanity check)
    assert analysis.total_failures >= 1

    # Verify that no case labels, query, or expected_* fields were modified
    assert len(cases) == len(cases_before), "analyze_failures must not add or remove cases"

    for case, original in zip(cases, cases_before):
        # Identity fields
        assert case.case_id == original.case_id, "case_id must not be modified"
        assert case.dataset_version == original.dataset_version, "dataset_version must not be modified"

        # Query field (must never be changed)
        assert case.query == original.query, "query must not be modified by failure analysis"

        # Expected label fields
        assert case.expected_route == original.expected_route, "expected_route must not be modified"
        assert case.expected_tool == original.expected_tool, "expected_tool must not be modified"
        assert case.expected_action == original.expected_action, "expected_action must not be modified"
        assert case.expected_tool_request == original.expected_tool_request, (
            "expected_tool_request must not be modified"
        )
        assert case.expected_selected_items == original.expected_selected_items, (
            "expected_selected_items must not be modified"
        )
        assert case.acceptable_selected_items == original.acceptable_selected_items, (
            "acceptable_selected_items must not be modified"
        )
        assert case.forbidden_selected_items == original.forbidden_selected_items, (
            "forbidden_selected_items must not be modified"
        )
        assert case.required_facts == original.required_facts, "required_facts must not be modified"
        assert case.optional_facts == original.optional_facts, "optional_facts must not be modified"
        assert case.forbidden_claims == original.forbidden_claims, "forbidden_claims must not be modified"

        # Metadata fields
        assert case.suite == original.suite, "suite must not be modified"
        assert case.split == original.split, "split must not be modified"
        assert case.scenario_family == original.scenario_family, "scenario_family must not be modified"
        assert case.scenario_type == original.scenario_type, "scenario_type must not be modified"
        assert case.difficulty == original.difficulty, "difficulty must not be modified"
        assert case.tags == original.tags, "tags must not be modified"
        assert case.automatic_validation_status == original.automatic_validation_status, (
            "automatic_validation_status must not be modified"
        )
        assert case.review_status == original.review_status, "review_status must not be modified"
