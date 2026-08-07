"""Scorecard generation for Silver Dataset evaluation runs.

Aggregates ``RunTrace`` results with ``SilverCase`` ground truth to produce a
``Scorecard`` with per-layer metrics (routing, tool calls, retrieval, grounding)
plus overall statistics (Task 12.4, Requirement 10.2).
"""

from pydantic import BaseModel

from silver_dataset.evaluation.metrics import (
    GroundingMetrics,
    RetrievalMetrics,
    RoutingMetrics,
    ToolCallMetrics,
    calculate_grounding_metrics,
    calculate_retrieval_metrics,
    calculate_routing_metrics,
    calculate_tool_call_metrics,
)
from silver_dataset.evaluation.runner import RunTrace
from silver_dataset.models.case import SilverCase


class Scorecard(BaseModel):
    """Aggregated evaluation scorecard for a baseline run.

    Separates metrics by evaluation layer as required by Requirement 10.2:
    - routing: Layer 1 routing decision metrics
    - tool_calls: Layer 2 tool selection and request metrics
    - retrieval: Layer 3 item retrieval/selection metrics
    - grounding: Layer 4 grounding and response quality metrics

    Attributes:
        run_id: Unique identifier for the run that produced this scorecard.
        dataset_version: Version of the dataset evaluated.
        routing: Layer 1 routing decision metrics.
        tool_calls: Layer 2 tool call metrics.
        retrieval: Layer 3 retrieval/selection metrics.
        grounding: Layer 4 grounding and response metrics.
        total_cases: Total number of cases in the run.
        successful_cases: Cases that completed without any error.
        infra_error_cases: Cases that failed due to infrastructure issues (excluded from
                           functional metrics per Requirement 10.6).
    """

    run_id: str
    dataset_version: str
    routing: RoutingMetrics
    tool_calls: ToolCallMetrics
    retrieval: RetrievalMetrics
    grounding: GroundingMetrics
    total_cases: int
    successful_cases: int
    infra_error_cases: int


def generate_scorecard(
    traces: list[RunTrace],
    cases: list[SilverCase],
) -> Scorecard:
    """Generate a scorecard from run traces and case ground truth.

    Infrastructure error cases are excluded from metric calculations so that
    connection/timeout failures do not distort the functional evaluation of the
    chatbot (Requirement 10.6).

    Args:
        traces: List of RunTrace instances from a baseline run.
        cases: List of SilverCase instances corresponding to the traces
               (matched by case_id).

    Returns:
        Scorecard with per-layer metrics and overall statistics.
    """
    # Build a lookup map for quick access by case_id
    case_by_id: dict[str, SilverCase] = {c.case_id: c for c in cases}

    # Exclude infrastructure error traces from functional metric computation
    functional_traces = [t for t in traces if not t.is_infra_error]

    # Build parallel lists: predictions and corresponding cases
    # Only include traces with matching cases (defensively skip orphaned traces)
    functional_predictions: list[dict] = []
    functional_cases: list[SilverCase] = []
    for trace in functional_traces:
        case = case_by_id.get(trace.case_id)
        if case is not None:
            # Use empty dict as prediction for error traces so metrics are penalized
            functional_predictions.append(trace.prediction)
            functional_cases.append(case)

    # Compute per-layer metrics
    routing = calculate_routing_metrics(functional_predictions, functional_cases)
    tool_calls = calculate_tool_call_metrics(functional_predictions, functional_cases)
    retrieval = calculate_retrieval_metrics(functional_predictions, functional_cases)
    grounding = calculate_grounding_metrics(functional_predictions, functional_cases)

    # Overall statistics
    total_cases = len(traces)
    infra_error_cases = sum(1 for t in traces if t.is_infra_error)
    successful_cases = sum(1 for t in traces if t.error is None)

    # Deduplicate run_id and dataset_version from traces (or use defaults)
    run_id = traces[0].run_id if traces else ""
    dataset_version = traces[0].dataset_version if traces else ""

    return Scorecard(
        run_id=run_id,
        dataset_version=dataset_version,
        routing=routing,
        tool_calls=tool_calls,
        retrieval=retrieval,
        grounding=grounding,
        total_cases=total_cases,
        successful_cases=successful_cases,
        infra_error_cases=infra_error_cases,
    )
