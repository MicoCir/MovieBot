"""Coverage matrix models for the Silver Dataset.

Defines the CoverageMatrix and CoverageCell models that specify the complete
set of scenario combinations to be generated. The matrix drives the latent
engine to produce LatentSpecifications covering all required families, suites,
languages, and difficulty levels per Requirement 2.
"""

from pydantic import BaseModel, Field

from silver_dataset.models.case import (
    Difficulty,
    ExpectedAction,
    ExpectedRoute,
    ExpectedTool,
    Suite,
)


class CoverageCell(BaseModel):
    """A single cell in the coverage matrix defining one scenario class.

    Each cell represents one combination of suite + scenario family + type
    with associated routing expectations. When expanded, it generates
    count_target * len(languages) * len(difficulties) * len(variations)
    latent specifications.
    """

    suite: Suite
    scenario_family: str
    scenario_type: str
    route: ExpectedRoute
    tool: ExpectedTool
    action: ExpectedAction
    languages: list[str] = Field(default_factory=lambda: ["en", "es"])
    difficulties: list[Difficulty] = Field(
        default_factory=lambda: [Difficulty.easy, Difficulty.medium, Difficulty.hard]
    )
    variations: list[str] = Field(
        default_factory=lambda: ["original", "paraphrase", "typo"]
    )
    fixture_ids: list[str] = Field(default_factory=list)
    count_target: int = 1
    tags: list[str] = Field(default_factory=list)

    def expected_case_count(self) -> int:
        """Calculate total expected cases from this cell."""
        return (
            self.count_target
            * len(self.languages)
            * len(self.difficulties)
            * len(self.variations)
        )


class CoverageMatrix(BaseModel):
    """Complete coverage matrix defining all required scenario combinations.

    The matrix is the entry point for the generation pipeline. It describes
    all scenario families across suites, languages, difficulties, and
    variation types. The latent engine expands it into individual
    LatentSpecification instances.
    """

    cells: list[CoverageCell]
    version: str = "1.0"
    description: str = ""

    def total_expected_cases(self) -> int:
        """Calculate total expected cases from all cells."""
        total = 0
        for cell in self.cells:
            total += cell.expected_case_count()
        return total

    def cells_by_suite(self, suite: Suite) -> list[CoverageCell]:
        """Filter cells by suite."""
        return [c for c in self.cells if c.suite == suite]

    def cells_by_family(self, family: str) -> list[CoverageCell]:
        """Filter cells by scenario family."""
        return [c for c in self.cells if c.scenario_family == family]

    def suite_expected_cases(self, suite: Suite) -> int:
        """Calculate total expected cases for a specific suite."""
        return sum(c.expected_case_count() for c in self.cells_by_suite(suite))


def default_coverage_matrix() -> CoverageMatrix:
    """Build the default coverage matrix per Requirement 2.

    Defines cells for 3 suites covering scenario families:
    routing direct, ambiguity, multi-intent, multi-turn, out of scope,
    distractors, negations, prompt injection, and robustness (linguistic).

    Target distribution:
    - e2e_routing_silver: 120-160 cases (8 cells × 18 = 144)
    - tmdb_agent_silver: 60-90 cases (4 cells × 18 = 72)
    - netflix_agent_silver: 80-110 cases (5 cells × 18 = 90)
    - Total: 306 cases (within 250-350 target)

    Each cell defaults to 2 languages × 3 difficulties × 3 variations = 18 cases.
    """
    cells: list[CoverageCell] = []

    # ─── Suite: e2e_routing_silver (8 cells → 144 cases) ───────────────
    # This suite focuses on routing decisions across all scenario families.

    cells.append(
        CoverageCell(
            suite=Suite.e2e_routing_silver,
            scenario_family="routing_direct",
            scenario_type="trending_direct",
            route=ExpectedRoute.trending,
            tool=ExpectedTool.tmdb_trending,
            action=ExpectedAction.call_tool,
            tags=["routing", "direct"],
        )
    )

    cells.append(
        CoverageCell(
            suite=Suite.e2e_routing_silver,
            scenario_family="routing_direct",
            scenario_type="netflix_direct",
            route=ExpectedRoute.netflix,
            tool=ExpectedTool.netflix_search,
            action=ExpectedAction.call_tool,
            tags=["routing", "direct"],
        )
    )

    cells.append(
        CoverageCell(
            suite=Suite.e2e_routing_silver,
            scenario_family="ambiguity",
            scenario_type="ambiguous_intent",
            route=ExpectedRoute.clarification,
            tool=ExpectedTool.none,
            action=ExpectedAction.ask_clarifying_question,
            tags=["routing", "ambiguity"],
        )
    )

    cells.append(
        CoverageCell(
            suite=Suite.e2e_routing_silver,
            scenario_family="out_of_scope",
            scenario_type="unrelated_topic",
            route=ExpectedRoute.out_of_scope,
            tool=ExpectedTool.none,
            action=ExpectedAction.return_out_of_scope,
            tags=["routing", "out_of_scope"],
        )
    )

    cells.append(
        CoverageCell(
            suite=Suite.e2e_routing_silver,
            scenario_family="distractors",
            scenario_type="distractor_with_intent",
            route=ExpectedRoute.trending,
            tool=ExpectedTool.tmdb_trending,
            action=ExpectedAction.call_tool,
            tags=["routing", "distractors"],
        )
    )

    cells.append(
        CoverageCell(
            suite=Suite.e2e_routing_silver,
            scenario_family="negations",
            scenario_type="negated_request",
            route=ExpectedRoute.clarification,
            tool=ExpectedTool.none,
            action=ExpectedAction.ask_clarifying_question,
            tags=["routing", "negations"],
        )
    )

    cells.append(
        CoverageCell(
            suite=Suite.e2e_routing_silver,
            scenario_family="prompt_injection",
            scenario_type="injection_attempt",
            route=ExpectedRoute.out_of_scope,
            tool=ExpectedTool.none,
            action=ExpectedAction.return_out_of_scope,
            tags=["routing", "security", "prompt_injection"],
        )
    )

    cells.append(
        CoverageCell(
            suite=Suite.e2e_routing_silver,
            scenario_family="robustness",
            scenario_type="linguistic_noise",
            route=ExpectedRoute.trending,
            tool=ExpectedTool.tmdb_trending,
            action=ExpectedAction.call_tool,
            variations=["original", "typo", "code_switch"],
            tags=["routing", "robustness", "linguistic"],
        )
    )

    # ─── Suite: tmdb_agent_silver (4 cells → 72 cases) ─────────────────
    # This suite focuses on TMDB tool call scenarios.

    cells.append(
        CoverageCell(
            suite=Suite.tmdb_agent_silver,
            scenario_family="routing_direct",
            scenario_type="trending_query",
            route=ExpectedRoute.trending,
            tool=ExpectedTool.tmdb_trending,
            action=ExpectedAction.call_tool,
            fixture_ids=["tmdb_trending_normal"],
            tags=["tmdb", "direct"],
        )
    )

    cells.append(
        CoverageCell(
            suite=Suite.tmdb_agent_silver,
            scenario_family="multi_intent",
            scenario_type="trending_with_filter",
            route=ExpectedRoute.trending,
            tool=ExpectedTool.tmdb_trending,
            action=ExpectedAction.call_tool,
            fixture_ids=["tmdb_trending_normal"],
            tags=["tmdb", "multi_intent"],
        )
    )

    cells.append(
        CoverageCell(
            suite=Suite.tmdb_agent_silver,
            scenario_family="multi_turn",
            scenario_type="trending_followup",
            route=ExpectedRoute.trending,
            tool=ExpectedTool.tmdb_trending,
            action=ExpectedAction.answer_from_tool_output,
            fixture_ids=["tmdb_trending_normal"],
            tags=["tmdb", "multi_turn"],
        )
    )

    cells.append(
        CoverageCell(
            suite=Suite.tmdb_agent_silver,
            scenario_family="robustness",
            scenario_type="tmdb_no_results",
            route=ExpectedRoute.trending,
            tool=ExpectedTool.tmdb_trending,
            action=ExpectedAction.return_no_results,
            fixture_ids=["tmdb_trending_empty"],
            variations=["original", "paraphrase", "code_switch"],
            tags=["tmdb", "robustness", "empty_results"],
        )
    )

    # ─── Suite: netflix_agent_silver (5 cells → 90 cases) ──────────────
    # This suite focuses on Netflix RAG search scenarios.

    cells.append(
        CoverageCell(
            suite=Suite.netflix_agent_silver,
            scenario_family="routing_direct",
            scenario_type="netflix_search_query",
            route=ExpectedRoute.netflix,
            tool=ExpectedTool.netflix_search,
            action=ExpectedAction.call_tool,
            fixture_ids=["netflix_search_normal"],
            tags=["netflix", "direct"],
        )
    )

    cells.append(
        CoverageCell(
            suite=Suite.netflix_agent_silver,
            scenario_family="multi_intent",
            scenario_type="netflix_genre_and_year",
            route=ExpectedRoute.netflix,
            tool=ExpectedTool.netflix_search,
            action=ExpectedAction.call_tool,
            fixture_ids=["netflix_search_normal"],
            tags=["netflix", "multi_intent"],
        )
    )

    cells.append(
        CoverageCell(
            suite=Suite.netflix_agent_silver,
            scenario_family="multi_turn",
            scenario_type="netflix_refinement",
            route=ExpectedRoute.netflix,
            tool=ExpectedTool.netflix_search,
            action=ExpectedAction.answer_from_tool_output,
            fixture_ids=["netflix_search_normal"],
            tags=["netflix", "multi_turn"],
        )
    )

    cells.append(
        CoverageCell(
            suite=Suite.netflix_agent_silver,
            scenario_family="distractors",
            scenario_type="netflix_with_noise",
            route=ExpectedRoute.netflix,
            tool=ExpectedTool.netflix_search,
            action=ExpectedAction.call_tool,
            fixture_ids=["netflix_search_normal"],
            tags=["netflix", "distractors"],
        )
    )

    cells.append(
        CoverageCell(
            suite=Suite.netflix_agent_silver,
            scenario_family="robustness",
            scenario_type="netflix_no_results",
            route=ExpectedRoute.netflix,
            tool=ExpectedTool.netflix_search,
            action=ExpectedAction.return_no_results,
            fixture_ids=["netflix_search_empty"],
            variations=["original", "paraphrase", "code_switch"],
            tags=["netflix", "robustness", "empty_results"],
        )
    )

    return CoverageMatrix(
        cells=cells,
        version="1.0",
        description=(
            "Default coverage matrix for the Silver Dataset. "
            "Covers 9 scenario families across 3 suites with "
            "English/Spanish languages and easy/medium/hard difficulties."
        ),
    )
