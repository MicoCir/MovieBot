"""Evaluation components for the Silver Dataset.

Provides metric calculators (routing, tool calls, retrieval, grounding),
baseline runner with tracing, scorecard generation, and failure analysis.
"""

from silver_dataset.evaluation.failure_analysis import (
    FailureAnalysis,
    FailureGroup,
    analyze_failures,
    detect_hard_cases,
    propose_new_seeds,
    write_baseline_results_md,
    write_failure_analysis_md,
)
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
from silver_dataset.evaluation.runner import (
    BaselineRunner,
    RunResult,
    RunTrace,
)
from silver_dataset.evaluation.scorecard import (
    Scorecard,
    generate_scorecard,
)

__all__ = [
    # Metrics
    "GroundingMetrics",
    "RetrievalMetrics",
    "RoutingMetrics",
    "ToolCallMetrics",
    "calculate_grounding_metrics",
    "calculate_retrieval_metrics",
    "calculate_routing_metrics",
    "calculate_tool_call_metrics",
    # Runner
    "BaselineRunner",
    "RunResult",
    "RunTrace",
    # Scorecard
    "Scorecard",
    "generate_scorecard",
    # Failure analysis
    "FailureAnalysis",
    "FailureGroup",
    "analyze_failures",
    "detect_hard_cases",
    "propose_new_seeds",
    "write_baseline_results_md",
    "write_failure_analysis_md",
]
