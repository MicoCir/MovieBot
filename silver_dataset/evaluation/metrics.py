"""Metric calculators for Silver Dataset evaluation layers.

Provides four metric models (RoutingMetrics, ToolCallMetrics, RetrievalMetrics,
GroundingMetrics) and corresponding calculation functions that compare predictions
against SilverCase ground truth.

All metrics are bounded in [0.0, 1.0] and computed deterministically using
structural comparisons (exact match, set operations). Semantic evaluation is
stubbed as optional.

Edge case handling:
- Empty predictions list → all metrics return 0.0
- Zero denominator in any ratio → returns 0.0
"""

from collections import defaultdict

from pydantic import BaseModel

from silver_dataset.models.case import SilverCase


class RoutingMetrics(BaseModel):
    """Layer 1: Routing decision metrics."""

    route_accuracy: float
    macro_f1_by_route: dict[str, float]
    unnecessary_tool_call_rate: float
    missed_tool_call_rate: float
    clarification_precision: float
    clarification_recall: float
    out_of_scope_precision: float
    out_of_scope_recall: float


class ToolCallMetrics(BaseModel):
    """Layer 2: Tool call metrics."""

    tool_selection_accuracy: float
    tool_request_schema_validity: float
    required_parameter_accuracy: float
    unsupported_parameter_rate: float
    filter_extraction_f1: float


class RetrievalMetrics(BaseModel):
    """Layer 3: Retrieval and selection metrics."""

    semantic_concept_recall: float
    expected_item_recall: float
    forbidden_item_violation_rate: float


class GroundingMetrics(BaseModel):
    """Layer 4: Grounding and response metrics."""

    grounded_title_rate: float
    unsupported_claim_rate: float
    required_facts_coverage: float
    response_type_accuracy: float


def _safe_divide(numerator: float, denominator: float) -> float:
    """Divide with zero-denominator protection, returning 0.0 on division by zero."""
    if denominator == 0:
        return 0.0
    return numerator / denominator


def _compute_precision_recall(
    predictions: list[str], ground_truths: list[str], target_label: str
) -> tuple[float, float]:
    """Compute precision and recall for a binary classification target.

    Args:
        predictions: List of predicted labels.
        ground_truths: List of ground truth labels.
        target_label: The label considered as "positive".

    Returns:
        (precision, recall) tuple, each in [0.0, 1.0].
    """
    tp = sum(
        1
        for pred, gt in zip(predictions, ground_truths)
        if pred == target_label and gt == target_label
    )
    fp = sum(
        1
        for pred, gt in zip(predictions, ground_truths)
        if pred == target_label and gt != target_label
    )
    fn = sum(
        1
        for pred, gt in zip(predictions, ground_truths)
        if pred != target_label and gt == target_label
    )

    precision = _safe_divide(tp, tp + fp)
    recall = _safe_divide(tp, tp + fn)
    return precision, recall


def _compute_f1(precision: float, recall: float) -> float:
    """Compute F1 score from precision and recall."""
    return _safe_divide(2 * precision * recall, precision + recall)


def calculate_routing_metrics(
    predictions: list[dict], cases: list[SilverCase]
) -> RoutingMetrics:
    """Calculate routing decision metrics.

    Args:
        predictions: List of dicts with at least {"route": "predicted_route"}.
        cases: Corresponding list of SilverCase with ground truth.

    Returns:
        RoutingMetrics with all values in [0.0, 1.0].
    """
    if not predictions or not cases:
        return RoutingMetrics(
            route_accuracy=0.0,
            macro_f1_by_route={},
            unnecessary_tool_call_rate=0.0,
            missed_tool_call_rate=0.0,
            clarification_precision=0.0,
            clarification_recall=0.0,
            out_of_scope_precision=0.0,
            out_of_scope_recall=0.0,
        )

    n = min(len(predictions), len(cases))
    pred_routes = [predictions[i].get("route", "") for i in range(n)]
    gt_routes = [cases[i].expected_route.value for i in range(n)]

    # Route accuracy: correct / total
    correct = sum(1 for p, g in zip(pred_routes, gt_routes) if p == g)
    route_accuracy = _safe_divide(correct, n)

    # Macro F1 by route: per-route F1 averaged
    all_routes = set(gt_routes) | set(pred_routes)
    macro_f1_by_route: dict[str, float] = {}
    for route in sorted(all_routes):
        precision, recall = _compute_precision_recall(pred_routes, gt_routes, route)
        macro_f1_by_route[route] = _compute_f1(precision, recall)

    # Unnecessary tool call rate: predicted tool != "none" but expected tool is "none"
    unnecessary_count = 0
    unnecessary_eligible = 0
    for i in range(n):
        expected_tool = cases[i].expected_tool.value
        predicted_tool = predictions[i].get("tool", "none")
        if expected_tool == "none":
            unnecessary_eligible += 1
            if predicted_tool != "none":
                unnecessary_count += 1
    unnecessary_tool_call_rate = _safe_divide(unnecessary_count, unnecessary_eligible)

    # Missed tool call rate: predicted tool == "none" but expected tool != "none"
    missed_count = 0
    missed_eligible = 0
    for i in range(n):
        expected_tool = cases[i].expected_tool.value
        predicted_tool = predictions[i].get("tool", "none")
        if expected_tool != "none":
            missed_eligible += 1
            if predicted_tool == "none":
                missed_count += 1
    missed_tool_call_rate = _safe_divide(missed_count, missed_eligible)

    # Clarification precision/recall
    clarification_precision, clarification_recall = _compute_precision_recall(
        pred_routes, gt_routes, "clarification"
    )

    # Out-of-scope precision/recall
    oos_precision, oos_recall = _compute_precision_recall(
        pred_routes, gt_routes, "out_of_scope"
    )

    return RoutingMetrics(
        route_accuracy=route_accuracy,
        macro_f1_by_route=macro_f1_by_route,
        unnecessary_tool_call_rate=unnecessary_tool_call_rate,
        missed_tool_call_rate=missed_tool_call_rate,
        clarification_precision=clarification_precision,
        clarification_recall=clarification_recall,
        out_of_scope_precision=oos_precision,
        out_of_scope_recall=oos_recall,
    )


def calculate_tool_call_metrics(
    predictions: list[dict], cases: list[SilverCase]
) -> ToolCallMetrics:
    """Calculate tool call metrics.

    Args:
        predictions: List of dicts with {"tool": "...", "request": {...}}.
        cases: Corresponding list of SilverCase with ground truth.

    Returns:
        ToolCallMetrics with all values in [0.0, 1.0].
    """
    if not predictions or not cases:
        return ToolCallMetrics(
            tool_selection_accuracy=0.0,
            tool_request_schema_validity=0.0,
            required_parameter_accuracy=0.0,
            unsupported_parameter_rate=0.0,
            filter_extraction_f1=0.0,
        )

    n = min(len(predictions), len(cases))

    # Tool selection accuracy: correct tool / total
    tool_correct = 0
    for i in range(n):
        predicted_tool = predictions[i].get("tool", "")
        expected_tool = cases[i].expected_tool.value
        if predicted_tool == expected_tool:
            tool_correct += 1
    tool_selection_accuracy = _safe_divide(tool_correct, n)

    # Tool request schema validity: proportion of cases where all keys match
    schema_valid_count = 0
    schema_total = 0
    for i in range(n):
        expected_request = cases[i].expected_tool_request
        if expected_request is None:
            continue
        schema_total += 1
        predicted_request = predictions[i].get("request", {}) or {}
        expected_keys = set(expected_request.keys())
        predicted_keys = set(predicted_request.keys())
        if expected_keys == predicted_keys:
            schema_valid_count += 1
    tool_request_schema_validity = _safe_divide(schema_valid_count, schema_total)

    # Required parameter accuracy: overlap of required params
    required_param_hits = 0
    required_param_total = 0
    for i in range(n):
        expected_request = cases[i].expected_tool_request
        if expected_request is None:
            continue
        expected_keys = set(expected_request.keys())
        predicted_request = predictions[i].get("request", {}) or {}
        predicted_keys = set(predicted_request.keys())
        required_param_total += len(expected_keys)
        required_param_hits += len(expected_keys & predicted_keys)
    required_parameter_accuracy = _safe_divide(required_param_hits, required_param_total)

    # Unsupported parameter rate: extra params / total params predicted
    extra_params_count = 0
    total_predicted_params = 0
    for i in range(n):
        expected_request = cases[i].expected_tool_request
        if expected_request is None:
            continue
        predicted_request = predictions[i].get("request", {}) or {}
        expected_keys = set(expected_request.keys())
        predicted_keys = set(predicted_request.keys())
        total_predicted_params += len(predicted_keys)
        extra_params_count += len(predicted_keys - expected_keys)
    unsupported_parameter_rate = _safe_divide(extra_params_count, total_predicted_params)

    # Filter extraction F1: F1 of filter key-value pairs
    filter_tp = 0
    filter_fp = 0
    filter_fn = 0
    for i in range(n):
        expected_request = cases[i].expected_tool_request
        if expected_request is None:
            continue
        predicted_request = predictions[i].get("request", {}) or {}
        # Convert to sets of (key, str(value)) for structural comparison
        expected_pairs = {(k, str(v)) for k, v in expected_request.items()}
        predicted_pairs = {(k, str(v)) for k, v in predicted_request.items()}
        filter_tp += len(expected_pairs & predicted_pairs)
        filter_fp += len(predicted_pairs - expected_pairs)
        filter_fn += len(expected_pairs - predicted_pairs)

    filter_precision = _safe_divide(filter_tp, filter_tp + filter_fp)
    filter_recall = _safe_divide(filter_tp, filter_tp + filter_fn)
    filter_extraction_f1 = _compute_f1(filter_precision, filter_recall)

    return ToolCallMetrics(
        tool_selection_accuracy=tool_selection_accuracy,
        tool_request_schema_validity=tool_request_schema_validity,
        required_parameter_accuracy=required_parameter_accuracy,
        unsupported_parameter_rate=unsupported_parameter_rate,
        filter_extraction_f1=filter_extraction_f1,
    )


def calculate_retrieval_metrics(
    predictions: list[dict], cases: list[SilverCase]
) -> RetrievalMetrics:
    """Calculate retrieval and selection metrics.

    Args:
        predictions: List of dicts with {"selected_items": [...]}.
        cases: Corresponding list of SilverCase with ground truth.

    Returns:
        RetrievalMetrics with all values in [0.0, 1.0].
    """
    if not predictions or not cases:
        return RetrievalMetrics(
            semantic_concept_recall=1.0,
            expected_item_recall=0.0,
            forbidden_item_violation_rate=0.0,
        )

    n = min(len(predictions), len(cases))

    # Expected item recall: expected items found / total expected
    expected_hits = 0
    expected_total = 0
    for i in range(n):
        expected_items = set(cases[i].expected_selected_items)
        if not expected_items:
            continue
        predicted_items = set(predictions[i].get("selected_items", []) or [])
        expected_total += len(expected_items)
        expected_hits += len(expected_items & predicted_items)
    expected_item_recall = _safe_divide(expected_hits, expected_total)

    # Forbidden item violation rate: forbidden items selected / total selected
    forbidden_violations = 0
    total_selected = 0
    for i in range(n):
        forbidden_items = set(cases[i].forbidden_selected_items)
        predicted_items = predictions[i].get("selected_items", []) or []
        total_selected += len(predicted_items)
        forbidden_violations += len(set(predicted_items) & forbidden_items)
    forbidden_item_violation_rate = _safe_divide(forbidden_violations, total_selected)

    # Semantic concept recall: stub at 1.0 (requires semantic comparison)
    semantic_concept_recall = 1.0

    return RetrievalMetrics(
        semantic_concept_recall=semantic_concept_recall,
        expected_item_recall=expected_item_recall,
        forbidden_item_violation_rate=forbidden_item_violation_rate,
    )


def calculate_grounding_metrics(
    predictions: list[dict], cases: list[SilverCase]
) -> GroundingMetrics:
    """Calculate grounding and response metrics.

    Args:
        predictions: List of dicts with {"response": "...", "claims": [...],
                     "response_type": "...", "mentioned_titles": [...]}.
        cases: Corresponding list of SilverCase with ground truth.

    Returns:
        GroundingMetrics with all values in [0.0, 1.0].
    """
    if not predictions or not cases:
        return GroundingMetrics(
            grounded_title_rate=0.0,
            unsupported_claim_rate=0.0,
            required_facts_coverage=0.0,
            response_type_accuracy=0.0,
        )

    n = min(len(predictions), len(cases))

    # Grounded title rate: titles mentioned that exist in expected/acceptable items
    grounded_titles = 0
    total_mentioned_titles = 0
    for i in range(n):
        mentioned_titles = predictions[i].get("mentioned_titles", []) or []
        if not mentioned_titles:
            continue
        # Valid titles are from expected + acceptable items
        valid_titles = set(cases[i].expected_selected_items) | set(
            cases[i].acceptable_selected_items
        )
        total_mentioned_titles += len(mentioned_titles)
        grounded_titles += sum(1 for t in mentioned_titles if t in valid_titles)
    grounded_title_rate = _safe_divide(grounded_titles, total_mentioned_titles)

    # Unsupported claim rate: claims not traceable to facts
    unsupported_claims = 0
    total_claims = 0
    for i in range(n):
        claims = predictions[i].get("claims", []) or []
        if not claims:
            continue
        total_claims += len(claims)
        # Required + optional facts form the set of supported facts
        supported_facts_values: set[str] = set()
        for fact in cases[i].required_facts:
            for v in fact.values():
                supported_facts_values.add(str(v).lower())
        for fact in cases[i].optional_facts:
            for v in fact.values():
                supported_facts_values.add(str(v).lower())
        for claim in claims:
            claim_lower = str(claim).lower()
            # A claim is supported if any fact value is contained in it
            is_supported = any(
                fact_val in claim_lower for fact_val in supported_facts_values if fact_val
            )
            if not is_supported:
                unsupported_claims += 1
    unsupported_claim_rate = _safe_divide(unsupported_claims, total_claims)

    # Required facts coverage: covered required facts / total required facts
    covered_facts = 0
    total_required_facts = 0
    for i in range(n):
        required_facts = cases[i].required_facts
        if not required_facts:
            continue
        total_required_facts += len(required_facts)
        response = str(predictions[i].get("response", "")).lower()
        claims = [str(c).lower() for c in (predictions[i].get("claims", []) or [])]
        combined_text = response + " " + " ".join(claims)
        for fact in required_facts:
            # A fact is covered if any of its values appear in the response/claims
            fact_values = [str(v).lower() for v in fact.values() if v]
            is_covered = any(val in combined_text for val in fact_values if val)
            if is_covered:
                covered_facts += 1
    required_facts_coverage = _safe_divide(covered_facts, total_required_facts)

    # Response type accuracy: correct response type / total
    response_type_correct = 0
    for i in range(n):
        predicted_type = predictions[i].get("response_type", "")
        expected_type = cases[i].expected_response_type
        if predicted_type == expected_type:
            response_type_correct += 1
    response_type_accuracy = _safe_divide(response_type_correct, n)

    return GroundingMetrics(
        grounded_title_rate=grounded_title_rate,
        unsupported_claim_rate=unsupported_claim_rate,
        required_facts_coverage=required_facts_coverage,
        response_type_accuracy=response_type_accuracy,
    )
