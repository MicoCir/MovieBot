"""Deterministic label derivation from latent specifications.

Derives all evaluation labels from a LatentSpecification before query generation,
ensuring labels are never invented by the LLM. Validates consistency rules
(route/tool/action combinations) and rejects contradictory specs early.
"""

from silver_dataset.models.case import (
    ExpectedAction,
    ExpectedRoute,
    ExpectedTool,
)
from silver_dataset.models.latent_spec import LatentSpecification


class InconsistentSpecError(Exception):
    """Raised when a LatentSpecification contains contradictory combinations.

    Attributes:
        violations: List of human-readable descriptions of the inconsistencies found.
    """

    def __init__(self, violations: list[str]) -> None:
        self.violations = violations
        msg = "Inconsistent specification: " + "; ".join(violations)
        super().__init__(msg)


def validate_spec_consistency(spec: LatentSpecification) -> list[str]:
    """Return list of consistency violations, empty if valid.

    Checks:
    - Route/Tool consistency: clarification/out_of_scope routes require tool=none
    - Action/Tool consistency: call_tool action requires a non-none tool
    - Route/Action consistency: out_of_scope requires return_out_of_scope action;
      clarification requires ask_clarifying_question action
    - Suite/Route consistency: tmdb_agent_silver with call_tool requires tmdb_trending;
      netflix_agent_silver with call_tool requires netflix_search
    - Fixture reference consistency: call_tool/answer_from_tool_output require fixture_id;
      return_out_of_scope/ask_clarifying_question require fixture_id=None
    """
    from silver_dataset.models.case import Suite

    violations: list[str] = []

    # 1. Route/Tool consistency
    if spec.route in (ExpectedRoute.clarification, ExpectedRoute.out_of_scope):
        if spec.tool != ExpectedTool.none:
            violations.append(
                f"Route '{spec.route.value}' requires tool='none', got '{spec.tool.value}'"
            )

    # 2. Action/Tool consistency
    if spec.action == ExpectedAction.call_tool:
        if spec.tool == ExpectedTool.none:
            violations.append(
                "Action 'call_tool' requires a non-none tool"
            )

    # 3. Route/Action consistency
    if spec.route == ExpectedRoute.out_of_scope:
        if spec.action != ExpectedAction.return_out_of_scope:
            violations.append(
                f"Route 'out_of_scope' requires action='return_out_of_scope', "
                f"got '{spec.action.value}'"
            )

    if spec.route == ExpectedRoute.clarification:
        if spec.action != ExpectedAction.ask_clarifying_question:
            violations.append(
                f"Route 'clarification' requires action='ask_clarifying_question', "
                f"got '{spec.action.value}'"
            )

    # 4. Suite/Route consistency
    if spec.suite == Suite.tmdb_agent_silver and spec.action == ExpectedAction.call_tool:
        if spec.tool != ExpectedTool.tmdb_trending:
            violations.append(
                f"Suite 'tmdb_agent_silver' with action='call_tool' requires "
                f"tool='tmdb_trending', got '{spec.tool.value}'"
            )

    if spec.suite == Suite.netflix_agent_silver and spec.action == ExpectedAction.call_tool:
        if spec.tool != ExpectedTool.netflix_search:
            violations.append(
                f"Suite 'netflix_agent_silver' with action='call_tool' requires "
                f"tool='netflix_search', got '{spec.tool.value}'"
            )

    # 5. Fixture reference consistency
    if spec.action in (ExpectedAction.call_tool, ExpectedAction.answer_from_tool_output):
        if spec.fixture_id is None:
            violations.append(
                f"Action '{spec.action.value}' requires a non-None fixture_id"
            )

    if spec.action in (ExpectedAction.return_out_of_scope, ExpectedAction.ask_clarifying_question):
        if spec.fixture_id is not None:
            violations.append(
                f"Action '{spec.action.value}' requires fixture_id=None, "
                f"got '{spec.fixture_id}'"
            )

    return violations


def derive_labels(spec: LatentSpecification) -> dict:
    """Derive deterministic labels from a latent specification.

    Validates consistency rules first, then maps spec fields to the label
    dictionary that will be used to construct a SilverCase.

    Args:
        spec: A fully populated LatentSpecification instance.

    Returns:
        Dictionary of derived label fields ready for SilverCase construction.

    Raises:
        InconsistentSpecError: If the spec contains contradictory route/tool/action
            combinations.
    """
    violations = validate_spec_consistency(spec)
    if violations:
        raise InconsistentSpecError(violations)

    return {
        "expected_route": spec.route,
        "expected_tool": spec.tool,
        "expected_action": spec.action,
        "expected_tool_request": spec.tool_request_template,
        "user_constraints": spec.user_constraints,
        "tool_output_fixture_id": spec.fixture_id,
        "suite": spec.suite,
        "difficulty": spec.difficulty,
        "scenario_family": spec.scenario_family,
        "scenario_type": spec.scenario_type,
        "language": spec.language,
        "response_language": spec.response_language,
        "tags": spec.tags,
        "seed_scenario_id": spec.seed_scenario_id if spec.seed_scenario_id is not None else spec.spec_id,
    }
