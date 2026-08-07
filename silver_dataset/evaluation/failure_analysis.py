"""Failure analysis and hard-case detection for Silver Dataset evaluation.

Groups failures by cause and tags, detects hard cases (cases with repeated
failures), proposes new seeds for future dataset versions, and generates
markdown report artefacts (Tasks 12.5–12.6, Requirements 10.3–10.5).
"""

from collections import defaultdict
from pathlib import Path

from pydantic import BaseModel

from silver_dataset.evaluation.runner import RunTrace
from silver_dataset.evaluation.scorecard import Scorecard
from silver_dataset.models.case import SilverCase


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------


class FailureGroup(BaseModel):
    """A group of failures sharing the same root cause.

    Attributes:
        cause: Short description of the failure cause (e.g. error type or
               'wrong_route', 'missing_tool', 'functional_error').
        count: Number of cases in this group.
        case_ids: Identifiers of the failing cases.
        tags: Union of all tags present across the grouped cases.
    """

    cause: str
    count: int
    case_ids: list[str]
    tags: list[str]


class FailureAnalysis(BaseModel):
    """Full failure analysis result.

    Attributes:
        groups: Failure groups ordered by descending count.
        total_failures: Total number of failed traces (functional + infra).
    """

    groups: list[FailureGroup]
    total_failures: int


# ---------------------------------------------------------------------------
# Analysis functions
# ---------------------------------------------------------------------------


def _extract_cause(trace: RunTrace) -> str:
    """Extract a normalised cause label from a failing trace.

    Priority:
    1. Infrastructure errors → "infra_error"
    2. Functional error with message → first token of the exception type
    3. Wrong route (prediction mismatch) → "wrong_route"
    4. Wrong tool → "wrong_tool"
    5. Generic functional error → "functional_error"
    """
    if trace.is_infra_error:
        return "infra_error"

    if trace.error:
        # Use the exception type name as the cause, removing trailing colon details
        parts = trace.error.split(":")
        exc_type = parts[0].strip()
        return exc_type if exc_type else "functional_error"

    # No error string — classify by prediction vs expected if possible
    # (For traces that succeeded nominally but produced wrong answers;
    # these would be classified during scorecard analysis, not here.)
    return "functional_error"


def analyze_failures(
    traces: list[RunTrace],
    cases: list[SilverCase],
) -> FailureAnalysis:
    """Group failed traces by cause without modifying any case labels.

    Per Requirement 10.3: the failure analysis MUST NOT modify the labels,
    ``query``, or ``expected_*`` fields of any SilverCase instance. This
    function only reads case data (tags) for grouping and never writes back.

    Args:
        traces: All traces from a baseline run.
        cases: SilverCase instances for the same run (used to enrich groups with tags).

    Returns:
        FailureAnalysis with groups sorted by descending count.
    """
    # Build case lookup (read-only access)
    case_by_id: dict[str, SilverCase] = {c.case_id: c for c in cases}

    # Only analyse failed traces
    failed_traces = [t for t in traces if t.error is not None or t.is_infra_error]

    # Group by cause
    groups_map: dict[str, list[RunTrace]] = defaultdict(list)
    for trace in failed_traces:
        cause = _extract_cause(trace)
        groups_map[cause].append(trace)

    # Build FailureGroup instances — read tags from cases (never modify)
    failure_groups: list[FailureGroup] = []
    for cause, group_traces in groups_map.items():
        case_ids = [t.case_id for t in group_traces]
        # Collect union of tags from all cases in this group (read-only)
        all_tags: set[str] = set()
        for case_id in case_ids:
            case = case_by_id.get(case_id)
            if case is not None:
                all_tags.update(case.tags)

        failure_groups.append(
            FailureGroup(
                cause=cause,
                count=len(group_traces),
                case_ids=sorted(case_ids),
                tags=sorted(all_tags),
            )
        )

    # Sort by descending count for readability
    failure_groups.sort(key=lambda g: (-g.count, g.cause))

    return FailureAnalysis(
        groups=failure_groups,
        total_failures=len(failed_traces),
    )


# ---------------------------------------------------------------------------
# Hard-case detection and seed proposal
# ---------------------------------------------------------------------------


def detect_hard_cases(
    traces: list[RunTrace],
    threshold: int = 2,
) -> list[str]:
    """Detect cases that failed repeatedly across multiple attempts.

    A case is considered a "hard case" if it appears in ``threshold`` or more
    failed traces with distinct attempt numbers or if it failed at least
    ``threshold`` times.

    Per Requirement 10.4: hard cases are flagged as seeds for future dataset
    versions; their detection does NOT contaminate test or holdout splits
    (those are not evaluated during baseline runs against the dev split).

    Args:
        traces: All traces from a baseline run.
        threshold: Minimum number of failures to flag a case as hard.

    Returns:
        Sorted list of case_ids considered "hard cases".
    """
    failure_counts: dict[str, int] = defaultdict(int)
    for trace in traces:
        if trace.error is not None or trace.is_infra_error:
            failure_counts[trace.case_id] += 1

    hard_cases = [
        case_id
        for case_id, count in failure_counts.items()
        if count >= threshold
    ]
    return sorted(hard_cases)


def propose_new_seeds(
    hard_case_ids: list[str],
    cases: list[SilverCase],
) -> list[dict]:
    """Generate seed proposals for future dataset versions from hard cases.

    Each proposal captures the scenario family, type, route, and tags of the
    hard case so a future generation run can create more diverse variations of
    the difficult scenarios. No case labels are modified.

    Args:
        hard_case_ids: Case IDs identified as hard cases.
        cases: Full list of SilverCase instances to look up from.

    Returns:
        List of dicts, one per hard case with keys:
        ``source_case_id``, ``scenario_family``, ``scenario_type``,
        ``expected_route``, ``expected_tool``, ``expected_action``,
        ``difficulty``, ``language``, ``tags``, ``suggested_variation_types``.
    """
    case_by_id: dict[str, SilverCase] = {c.case_id: c for c in cases}
    proposals: list[dict] = []

    # All variation types available for the seed engine
    all_variation_types = ["paraphrase", "typo", "translation", "code-switch"]

    for case_id in hard_case_ids:
        case = case_by_id.get(case_id)
        if case is None:
            continue

        proposals.append(
            {
                "source_case_id": case.case_id,
                "scenario_family": case.scenario_family,
                "scenario_type": case.scenario_type,
                "expected_route": case.expected_route.value,
                "expected_tool": case.expected_tool.value,
                "expected_action": case.expected_action.value,
                "difficulty": case.difficulty.value,
                "language": case.language,
                "tags": list(case.tags),
                "suggested_variation_types": all_variation_types,
            }
        )

    return proposals


# ---------------------------------------------------------------------------
# Markdown report generation
# ---------------------------------------------------------------------------


def write_failure_analysis_md(
    analysis: FailureAnalysis,
    output_path: Path,
) -> Path:
    """Write the failure analysis as a markdown file.

    Produces ``failure_analysis.md`` as required by Requirement 10.5.
    The output path is created if it does not exist.

    Args:
        analysis: The FailureAnalysis to render.
        output_path: Path (including filename) where the markdown is written.

    Returns:
        The resolved path where the file was written.
    """
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    lines: list[str] = [
        "# Failure Analysis\n",
        f"**Total failures:** {analysis.total_failures}\n",
        f"**Failure groups:** {len(analysis.groups)}\n",
        "",
    ]

    for group in analysis.groups:
        lines.append(f"## {group.cause} ({group.count} case{'s' if group.count != 1 else ''})\n")
        if group.tags:
            lines.append(f"**Tags:** {', '.join(group.tags)}\n")
        lines.append("**Cases:**\n")
        for case_id in group.case_ids:
            lines.append(f"- {case_id}")
        lines.append("")

    output_path.write_text("\n".join(lines), encoding="utf-8")
    return output_path


def write_baseline_results_md(
    scorecard: Scorecard,
    output_path: Path,
) -> Path:
    """Write the baseline results scorecard as a markdown file.

    Produces ``baseline_results.md`` as required by Requirement 10.5.
    The output path is created if it does not exist.

    Args:
        scorecard: The Scorecard to render.
        output_path: Path (including filename) where the markdown is written.

    Returns:
        The resolved path where the file was written.
    """
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    def _pct(value: float) -> str:
        return f"{value * 100:.1f}%"

    lines: list[str] = [
        "# Baseline Results\n",
        f"**Run ID:** {scorecard.run_id}",
        f"**Dataset version:** {scorecard.dataset_version}",
        "",
        "## Summary\n",
        f"| Metric | Value |",
        f"|--------|-------|",
        f"| Total cases | {scorecard.total_cases} |",
        f"| Successful | {scorecard.successful_cases} |",
        f"| Infrastructure errors | {scorecard.infra_error_cases} |",
        f"| Functional failures | {scorecard.total_cases - scorecard.successful_cases - scorecard.infra_error_cases} |",
        "",
        "## Layer 1: Routing\n",
        f"| Metric | Value |",
        f"|--------|-------|",
        f"| Route accuracy | {_pct(scorecard.routing.route_accuracy)} |",
        f"| Unnecessary tool call rate | {_pct(scorecard.routing.unnecessary_tool_call_rate)} |",
        f"| Missed tool call rate | {_pct(scorecard.routing.missed_tool_call_rate)} |",
        f"| Clarification precision | {_pct(scorecard.routing.clarification_precision)} |",
        f"| Clarification recall | {_pct(scorecard.routing.clarification_recall)} |",
        f"| Out-of-scope precision | {_pct(scorecard.routing.out_of_scope_precision)} |",
        f"| Out-of-scope recall | {_pct(scorecard.routing.out_of_scope_recall)} |",
        "",
        "## Layer 2: Tool Calls\n",
        f"| Metric | Value |",
        f"|--------|-------|",
        f"| Tool selection accuracy | {_pct(scorecard.tool_calls.tool_selection_accuracy)} |",
        f"| Tool request schema validity | {_pct(scorecard.tool_calls.tool_request_schema_validity)} |",
        f"| Required parameter accuracy | {_pct(scorecard.tool_calls.required_parameter_accuracy)} |",
        f"| Unsupported parameter rate | {_pct(scorecard.tool_calls.unsupported_parameter_rate)} |",
        f"| Filter extraction F1 | {_pct(scorecard.tool_calls.filter_extraction_f1)} |",
        "",
        "## Layer 3: Retrieval\n",
        f"| Metric | Value |",
        f"|--------|-------|",
        f"| Semantic concept recall | {_pct(scorecard.retrieval.semantic_concept_recall)} |",
        f"| Expected item recall | {_pct(scorecard.retrieval.expected_item_recall)} |",
        f"| Forbidden item violation rate | {_pct(scorecard.retrieval.forbidden_item_violation_rate)} |",
        "",
        "## Layer 4: Grounding\n",
        f"| Metric | Value |",
        f"|--------|-------|",
        f"| Grounded title rate | {_pct(scorecard.grounding.grounded_title_rate)} |",
        f"| Unsupported claim rate | {_pct(scorecard.grounding.unsupported_claim_rate)} |",
        f"| Required facts coverage | {_pct(scorecard.grounding.required_facts_coverage)} |",
        f"| Response type accuracy | {_pct(scorecard.grounding.response_type_accuracy)} |",
        "",
    ]

    output_path.write_text("\n".join(lines), encoding="utf-8")
    return output_path
