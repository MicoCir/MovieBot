"""Property-based tests for metrics calculator.

**Validates: Requirements 9.1–9.5**

Property 17: For any set of predictions and corresponding SilverCase ground truth,
all calculated metrics SHALL be in the range [0.0, 1.0], and computing them twice
with identical inputs SHALL produce identical results.
"""

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st
from hypothesis.strategies import composite

from silver_dataset.evaluation.metrics import (
    calculate_grounding_metrics,
    calculate_retrieval_metrics,
    calculate_routing_metrics,
    calculate_tool_call_metrics,
)
from silver_dataset.models.case import ExpectedRoute, ExpectedTool
from silver_dataset.tests.strategies import silver_case_strategy


@composite
def routing_prediction_strategy(draw, case):
    """Generate a routing prediction dict matching a SilverCase."""
    # Sometimes predict correct, sometimes predict wrong
    routes = [r.value for r in ExpectedRoute]
    route = draw(st.sampled_from(routes))
    tools = [t.value for t in ExpectedTool]
    tool = draw(st.sampled_from(tools))
    return {"route": route, "tool": tool}


@composite
def tool_call_prediction_strategy(draw, case):
    """Generate a tool call prediction dict matching a SilverCase."""
    tools = [t.value for t in ExpectedTool]
    tool = draw(st.sampled_from(tools))
    # Generate a request dict with some overlap with expected
    request_keys = draw(
        st.lists(st.sampled_from(["genre", "year", "language", "page", "sort_by", "extra_key"]), max_size=5)
    )
    request = {k: draw(st.text(min_size=1, max_size=20)) for k in request_keys}
    return {"tool": tool, "request": request}


@composite
def retrieval_prediction_strategy(draw, case):
    """Generate a retrieval prediction dict matching a SilverCase."""
    # Mix of expected, acceptable, forbidden, and random items
    all_items = (
        list(case.expected_selected_items)
        + list(case.acceptable_selected_items)
        + list(case.forbidden_selected_items)
    )
    extra_items = draw(st.lists(st.text(min_size=1, max_size=20), max_size=3))
    pool = all_items + extra_items if all_items else extra_items
    if pool:
        selected = draw(st.lists(st.sampled_from(pool), max_size=5))
    else:
        selected = draw(st.lists(st.text(min_size=1, max_size=20), max_size=3))
    return {"selected_items": selected}


@composite
def grounding_prediction_strategy(draw, case):
    """Generate a grounding prediction dict matching a SilverCase."""
    response_types = [case.expected_response_type, "recommendation", "error", "list", "clarification"]
    response_type = draw(st.sampled_from(response_types))

    # Generate mentioned titles from expected/acceptable/random
    title_pool = list(case.expected_selected_items) + list(case.acceptable_selected_items)
    extra_titles = draw(st.lists(st.text(min_size=1, max_size=20), max_size=2))
    title_pool = title_pool + extra_titles if title_pool else extra_titles
    if title_pool:
        mentioned_titles = draw(st.lists(st.sampled_from(title_pool), max_size=4))
    else:
        mentioned_titles = []

    # Generate claims - some grounded, some not
    claims = draw(st.lists(st.text(min_size=1, max_size=50), max_size=5))

    # Generate response text
    response = draw(st.text(min_size=0, max_size=200))

    return {
        "response": response,
        "claims": claims,
        "response_type": response_type,
        "mentioned_titles": mentioned_titles,
    }


@composite
def cases_and_predictions_strategy(draw):
    """Generate a list of cases with matching predictions for all four metric types."""
    n = draw(st.integers(min_value=1, max_value=10))
    cases = [draw(silver_case_strategy()) for _ in range(n)]

    routing_preds = [draw(routing_prediction_strategy(case)) for case in cases]
    tool_preds = [draw(tool_call_prediction_strategy(case)) for case in cases]
    retrieval_preds = [draw(retrieval_prediction_strategy(case)) for case in cases]
    grounding_preds = [draw(grounding_prediction_strategy(case)) for case in cases]

    return cases, routing_preds, tool_preds, retrieval_preds, grounding_preds


def _assert_metric_bounded(value: float, name: str) -> None:
    """Assert a metric value is in [0.0, 1.0]."""
    assert 0.0 <= value <= 1.0, f"Metric {name} = {value} is out of bounds [0, 1]"


@pytest.mark.property
@given(data=cases_and_predictions_strategy())
@settings(max_examples=100)
def test_routing_metrics_bounded_and_deterministic(data):
    """Property 17: Routing metrics are bounded [0,1] and deterministic."""
    cases, routing_preds, _, _, _ = data

    result1 = calculate_routing_metrics(routing_preds, cases)
    result2 = calculate_routing_metrics(routing_preds, cases)

    # Bounded
    _assert_metric_bounded(result1.route_accuracy, "route_accuracy")
    _assert_metric_bounded(result1.unnecessary_tool_call_rate, "unnecessary_tool_call_rate")
    _assert_metric_bounded(result1.missed_tool_call_rate, "missed_tool_call_rate")
    _assert_metric_bounded(result1.clarification_precision, "clarification_precision")
    _assert_metric_bounded(result1.clarification_recall, "clarification_recall")
    _assert_metric_bounded(result1.out_of_scope_precision, "out_of_scope_precision")
    _assert_metric_bounded(result1.out_of_scope_recall, "out_of_scope_recall")
    for route, f1_val in result1.macro_f1_by_route.items():
        _assert_metric_bounded(f1_val, f"macro_f1_by_route[{route}]")

    # Deterministic
    assert result1 == result2


@pytest.mark.property
@given(data=cases_and_predictions_strategy())
@settings(max_examples=100)
def test_tool_call_metrics_bounded_and_deterministic(data):
    """Property 17: Tool call metrics are bounded [0,1] and deterministic."""
    cases, _, tool_preds, _, _ = data

    result1 = calculate_tool_call_metrics(tool_preds, cases)
    result2 = calculate_tool_call_metrics(tool_preds, cases)

    # Bounded
    _assert_metric_bounded(result1.tool_selection_accuracy, "tool_selection_accuracy")
    _assert_metric_bounded(result1.tool_request_schema_validity, "tool_request_schema_validity")
    _assert_metric_bounded(result1.required_parameter_accuracy, "required_parameter_accuracy")
    _assert_metric_bounded(result1.unsupported_parameter_rate, "unsupported_parameter_rate")
    _assert_metric_bounded(result1.filter_extraction_f1, "filter_extraction_f1")

    # Deterministic
    assert result1 == result2


@pytest.mark.property
@given(data=cases_and_predictions_strategy())
@settings(max_examples=100)
def test_retrieval_metrics_bounded_and_deterministic(data):
    """Property 17: Retrieval metrics are bounded [0,1] and deterministic."""
    cases, _, _, retrieval_preds, _ = data

    result1 = calculate_retrieval_metrics(retrieval_preds, cases)
    result2 = calculate_retrieval_metrics(retrieval_preds, cases)

    # Bounded
    _assert_metric_bounded(result1.semantic_concept_recall, "semantic_concept_recall")
    _assert_metric_bounded(result1.expected_item_recall, "expected_item_recall")
    _assert_metric_bounded(result1.forbidden_item_violation_rate, "forbidden_item_violation_rate")

    # Deterministic
    assert result1 == result2


@pytest.mark.property
@given(data=cases_and_predictions_strategy())
@settings(max_examples=100)
def test_grounding_metrics_bounded_and_deterministic(data):
    """Property 17: Grounding metrics are bounded [0,1] and deterministic."""
    cases, _, _, _, grounding_preds = data

    result1 = calculate_grounding_metrics(grounding_preds, cases)
    result2 = calculate_grounding_metrics(grounding_preds, cases)

    # Bounded
    _assert_metric_bounded(result1.grounded_title_rate, "grounded_title_rate")
    _assert_metric_bounded(result1.unsupported_claim_rate, "unsupported_claim_rate")
    _assert_metric_bounded(result1.required_facts_coverage, "required_facts_coverage")
    _assert_metric_bounded(result1.response_type_accuracy, "response_type_accuracy")

    # Deterministic
    assert result1 == result2


@pytest.mark.property
def test_all_metrics_with_empty_inputs():
    """Property 17: Empty inputs produce valid bounded metrics."""
    # Empty predictions
    routing = calculate_routing_metrics([], [])
    tool = calculate_tool_call_metrics([], [])
    retrieval = calculate_retrieval_metrics([], [])
    grounding = calculate_grounding_metrics([], [])

    assert routing.route_accuracy == 0.0
    assert tool.tool_selection_accuracy == 0.0
    assert retrieval.expected_item_recall == 0.0
    assert grounding.response_type_accuracy == 0.0
