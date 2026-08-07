"""Core enums and models for the Silver Dataset.

Defines all normalized lowercase enums used throughout the Silver Dataset pipeline,
including expected routes, tools, actions, suites, splits, difficulty levels,
and status tracking enums.
"""

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field, model_validator


class ExpectedRoute(str, Enum):
    """Expected routing decision for a case."""

    trending = "trending"
    netflix = "netflix"
    clarification = "clarification"
    out_of_scope = "out_of_scope"


class ExpectedTool(str, Enum):
    """Expected tool selection for a case."""

    tmdb_trending = "tmdb_trending"
    netflix_search = "netflix_search"
    none = "none"


class ExpectedAction(str, Enum):
    """Expected action the agent should take."""

    call_tool = "call_tool"
    ask_clarifying_question = "ask_clarifying_question"
    return_out_of_scope = "return_out_of_scope"
    answer_from_tool_output = "answer_from_tool_output"
    return_no_results = "return_no_results"
    return_controlled_error = "return_controlled_error"


class Suite(str, Enum):
    """Dataset suite identifiers."""

    e2e_routing_silver = "e2e_routing_silver"
    tmdb_agent_silver = "tmdb_agent_silver"
    netflix_agent_silver = "netflix_agent_silver"


class Split(str, Enum):
    """Dataset split partitions."""

    dev = "dev"
    test = "test"
    holdout = "holdout"


class Difficulty(str, Enum):
    """Case difficulty level."""

    easy = "easy"
    medium = "medium"
    hard = "hard"


class ValidationStatus(str, Enum):
    """Automatic validation pipeline result."""

    passed = "passed"
    warning = "warning"
    failed = "failed"


class ReviewStatus(str, Enum):
    """Human review status of a case."""

    not_human_reviewed = "not_human_reviewed"
    human_reviewed = "human_reviewed"


class GenerationMetadata(BaseModel):
    """Metadata tracking LLM generation details for each case."""

    method: str
    model: str
    prompt_version: str
    timestamp: datetime
    batch_id: str
    variation_type: str | None = None


class SilverCase(BaseModel):
    """Core model representing a single case in the Silver Dataset.

    Contains the query, structured expectations, metadata, and validation status
    for one evaluation scenario. All labels are derived deterministically from
    the latent specification before query generation.
    """

    case_id: str
    dataset_version: str
    suite: Suite
    split: Split
    scenario_family: str
    scenario_type: str
    query: str
    conversation_context: list[dict] = Field(default_factory=list)
    language: str
    response_language: str
    expected_route: ExpectedRoute
    expected_tool: ExpectedTool
    expected_action: ExpectedAction
    expected_tool_request: dict | None = None
    user_constraints: dict = Field(default_factory=dict)
    tool_output_fixture_id: str | None = None
    expected_selected_items: list[str] = Field(default_factory=list)
    acceptable_selected_items: list[str] = Field(default_factory=list)
    forbidden_selected_items: list[str] = Field(default_factory=list)
    required_facts: list[dict] = Field(default_factory=list)
    optional_facts: list[dict] = Field(default_factory=list)
    forbidden_claims: list[str] = Field(default_factory=list)
    expected_response_type: str
    difficulty: Difficulty
    tags: list[str] = Field(default_factory=list)
    seed_scenario_id: str
    generation_metadata: GenerationMetadata
    automatic_validation_status: ValidationStatus = ValidationStatus.passed
    review_status: ReviewStatus = ReviewStatus.not_human_reviewed

    @model_validator(mode="after")
    def check_route_tool_action_consistency(self) -> "SilverCase":
        """Enforce route/tool/action consistency rules (Requirement 1.5).

        - When expected_route is 'clarification' or 'out_of_scope',
          expected_tool MUST be 'none'.
        - When expected_action is 'call_tool', expected_tool must NOT be 'none'.
        """
        if self.expected_route in (
            ExpectedRoute.clarification,
            ExpectedRoute.out_of_scope,
        ) and self.expected_tool != ExpectedTool.none:
            raise ValueError(
                f"When expected_route is '{self.expected_route.value}', "
                f"expected_tool must be 'none', got '{self.expected_tool.value}'"
            )

        if (
            self.expected_action == ExpectedAction.call_tool
            and self.expected_tool == ExpectedTool.none
        ):
            raise ValueError(
                "When expected_action is 'call_tool', "
                "expected_tool must not be 'none'"
            )

        return self


def export_json_schema() -> dict:
    """Export the SilverCase JSON Schema for external tooling.

    Returns a complete JSON Schema dictionary derived from the Pydantic model.
    This enables external validation tools and documentation generators to
    consume the dataset contract.
    """
    return SilverCase.model_json_schema()
