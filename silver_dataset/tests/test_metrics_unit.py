"""Unit tests for metrics calculator with hand-calculated fixtures.

Tests specific scenarios with known expected results to validate
calculation correctness of all four metric layers.
"""

from datetime import datetime

import pytest

from silver_dataset.evaluation.metrics import (
    calculate_grounding_metrics,
    calculate_retrieval_metrics,
    calculate_routing_metrics,
    calculate_tool_call_metrics,
)
from silver_dataset.models.case import (
    Difficulty,
    ExpectedAction,
    ExpectedRoute,
    ExpectedTool,
    GenerationMetadata,
    ReviewStatus,
    SilverCase,
    Split,
    Suite,
    ValidationStatus,
)


def _make_case(
    route: ExpectedRoute = ExpectedRoute.trending,
    tool: ExpectedTool = ExpectedTool.tmdb_trending,
    action: ExpectedAction = ExpectedAction.call_tool,
    tool_request: dict | None = None,
    expected_items: list[str] | None = None,
    acceptable_items: list[str] | None = None,
    forbidden_items: list[str] | None = None,
    required_facts: list[dict] | None = None,
    optional_facts: list[dict] | None = None,
    response_type: str = "recommendation",
    case_id: str = "test-001",
) -> SilverCase:
    """Helper to create a SilverCase with minimal boilerplate."""
    return SilverCase(
        case_id=case_id,
        dataset_version="v1.0",
        suite=Suite.e2e_routing_silver,
        split=Split.dev,
        scenario_family="test_family",
        scenario_type="test_type",
        query="What are the trending movies?",
        conversation_context=[],
        language="en",
        response_language="en",
        expected_route=route,
        expected_tool=tool,
        expected_action=action,
        expected_tool_request=tool_request,
        user_constraints={},
        tool_output_fixture_id=None,
        expected_selected_items=expected_items or [],
        acceptable_selected_items=acceptable_items or [],
        forbidden_selected_items=forbidden_items or [],
        required_facts=required_facts or [],
        optional_facts=optional_facts or [],
        forbidden_claims=[],
        expected_response_type=response_type,
        difficulty=Difficulty.easy,
        tags=[],
        seed_scenario_id="seed-001",
        generation_metadata=GenerationMetadata(
            method="test",
            model="test-model",
            prompt_version="v1",
            timestamp=datetime(2024, 1, 1),
            batch_id="batch-001",
            variation_type=None,
        ),
        automatic_validation_status=ValidationStatus.passed,
        review_status=ReviewStatus.not_human_reviewed,
    )


class TestRoutingMetrics:
    """Unit tests for calculate_routing_metrics."""

    def test_perfect_routing(self):
        """All predictions correct → accuracy 1.0."""
        cases = [
            _make_case(route=ExpectedRoute.trending, tool=ExpectedTool.tmdb_trending),
            _make_case(route=ExpectedRoute.netflix, tool=ExpectedTool.netflix_search, case_id="c2"),
            _make_case(
                route=ExpectedRoute.clarification, tool=ExpectedTool.none,
                action=ExpectedAction.ask_clarifying_question, case_id="c3"
            ),
        ]
        predictions = [
            {"route": "trending", "tool": "tmdb_trending"},
            {"route": "netflix", "tool": "netflix_search"},
            {"route": "clarification", "tool": "none"},
        ]
        result = calculate_routing_metrics(predictions, cases)
        assert result.route_accuracy == 1.0
        assert result.unnecessary_tool_call_rate == 0.0
        assert result.missed_tool_call_rate == 0.0
        assert result.clarification_precision == 1.0
        assert result.clarification_recall == 1.0

    def test_zero_accuracy(self):
        """All predictions wrong → accuracy 0.0."""
        cases = [
            _make_case(route=ExpectedRoute.trending, tool=ExpectedTool.tmdb_trending),
            _make_case(route=ExpectedRoute.netflix, tool=ExpectedTool.netflix_search, case_id="c2"),
        ]
        predictions = [
            {"route": "netflix", "tool": "tmdb_trending"},
            {"route": "trending", "tool": "netflix_search"},
        ]
        result = calculate_routing_metrics(predictions, cases)
        assert result.route_accuracy == 0.0

    def test_unnecessary_tool_call_rate(self):
        """Predicted tool when none expected → rate = 1/2."""
        cases = [
            _make_case(
                route=ExpectedRoute.clarification, tool=ExpectedTool.none,
                action=ExpectedAction.ask_clarifying_question
            ),
            _make_case(
                route=ExpectedRoute.out_of_scope, tool=ExpectedTool.none,
                action=ExpectedAction.return_out_of_scope, case_id="c2"
            ),
        ]
        predictions = [
            {"route": "clarification", "tool": "tmdb_trending"},  # unnecessary
            {"route": "out_of_scope", "tool": "none"},  # correct
        ]
        result = calculate_routing_metrics(predictions, cases)
        # 1 unnecessary out of 2 cases where expected tool is none
        assert result.unnecessary_tool_call_rate == 0.5

    def test_missed_tool_call_rate(self):
        """Predicted none when tool expected → rate = 1/2."""
        cases = [
            _make_case(route=ExpectedRoute.trending, tool=ExpectedTool.tmdb_trending),
            _make_case(route=ExpectedRoute.netflix, tool=ExpectedTool.netflix_search, case_id="c2"),
        ]
        predictions = [
            {"route": "trending", "tool": "none"},  # missed
            {"route": "netflix", "tool": "netflix_search"},  # correct
        ]
        result = calculate_routing_metrics(predictions, cases)
        # 1 missed out of 2 cases where expected tool != none
        assert result.missed_tool_call_rate == 0.5

    def test_clarification_precision_recall(self):
        """Hand-calculated clarification precision and recall."""
        cases = [
            _make_case(
                route=ExpectedRoute.clarification, tool=ExpectedTool.none,
                action=ExpectedAction.ask_clarifying_question
            ),
            _make_case(route=ExpectedRoute.trending, tool=ExpectedTool.tmdb_trending, case_id="c2"),
            _make_case(route=ExpectedRoute.trending, tool=ExpectedTool.tmdb_trending, case_id="c3"),
        ]
        predictions = [
            {"route": "clarification", "tool": "none"},  # TP
            {"route": "clarification", "tool": "none"},  # FP
            {"route": "trending", "tool": "tmdb_trending"},  # TN
        ]
        result = calculate_routing_metrics(predictions, cases)
        # TP=1, FP=1, FN=0 → precision=1/2=0.5, recall=1/1=1.0
        assert result.clarification_precision == 0.5
        assert result.clarification_recall == 1.0

    def test_empty_inputs(self):
        """Empty inputs return zeroed metrics."""
        result = calculate_routing_metrics([], [])
        assert result.route_accuracy == 0.0
        assert result.macro_f1_by_route == {}

    def test_out_of_scope_precision_recall(self):
        """Hand-calculated OOS precision and recall."""
        cases = [
            _make_case(
                route=ExpectedRoute.out_of_scope, tool=ExpectedTool.none,
                action=ExpectedAction.return_out_of_scope
            ),
            _make_case(
                route=ExpectedRoute.out_of_scope, tool=ExpectedTool.none,
                action=ExpectedAction.return_out_of_scope, case_id="c2"
            ),
            _make_case(route=ExpectedRoute.trending, tool=ExpectedTool.tmdb_trending, case_id="c3"),
        ]
        predictions = [
            {"route": "out_of_scope", "tool": "none"},  # TP
            {"route": "trending", "tool": "none"},  # FN
            {"route": "out_of_scope", "tool": "none"},  # FP
        ]
        result = calculate_routing_metrics(predictions, cases)
        # TP=1, FP=1, FN=1 → precision=1/2=0.5, recall=1/2=0.5
        assert result.out_of_scope_precision == 0.5
        assert result.out_of_scope_recall == 0.5


class TestToolCallMetrics:
    """Unit tests for calculate_tool_call_metrics."""

    def test_perfect_tool_selection(self):
        """All tool predictions correct → accuracy 1.0."""
        cases = [
            _make_case(tool=ExpectedTool.tmdb_trending),
            _make_case(tool=ExpectedTool.netflix_search, case_id="c2"),
        ]
        predictions = [
            {"tool": "tmdb_trending", "request": {}},
            {"tool": "netflix_search", "request": {}},
        ]
        result = calculate_tool_call_metrics(predictions, cases)
        assert result.tool_selection_accuracy == 1.0

    def test_tool_request_schema_validity(self):
        """Keys match expected → schema validity = 1.0; extra key → 0.0."""
        cases = [
            _make_case(tool_request={"genre": "action", "year": "2024"}),
            _make_case(tool_request={"genre": "comedy"}, case_id="c2"),
        ]
        predictions = [
            {"tool": "tmdb_trending", "request": {"genre": "action", "year": "2024"}},  # match
            {"tool": "tmdb_trending", "request": {"genre": "comedy", "extra": "val"}},  # no match
        ]
        result = calculate_tool_call_metrics(predictions, cases)
        # 1 out of 2 have exact key match
        assert result.tool_request_schema_validity == 0.5

    def test_required_parameter_accuracy(self):
        """Overlap of required params: 3 of 4 expected keys present."""
        cases = [
            _make_case(tool_request={"genre": "action", "year": "2024"}),
            _make_case(tool_request={"genre": "comedy", "language": "en"}, case_id="c2"),
        ]
        predictions = [
            {"tool": "tmdb_trending", "request": {"genre": "action", "year": "2024"}},  # 2/2
            {"tool": "tmdb_trending", "request": {"genre": "comedy"}},  # 1/2
        ]
        result = calculate_tool_call_metrics(predictions, cases)
        # Total expected keys: 2+2=4, hits: 2+1=3
        assert result.required_parameter_accuracy == 0.75

    def test_unsupported_parameter_rate(self):
        """Extra params / total predicted params."""
        cases = [
            _make_case(tool_request={"genre": "action"}),
        ]
        predictions = [
            {"tool": "tmdb_trending", "request": {"genre": "action", "extra1": "v", "extra2": "v"}},
        ]
        result = calculate_tool_call_metrics(predictions, cases)
        # 2 extra params out of 3 total predicted
        assert abs(result.unsupported_parameter_rate - 2 / 3) < 1e-9

    def test_filter_extraction_f1(self):
        """Hand-calculated F1 for filter key-value pairs."""
        cases = [
            _make_case(tool_request={"genre": "action", "year": "2024"}),
        ]
        predictions = [
            {"tool": "tmdb_trending", "request": {"genre": "action", "year": "2023"}},
        ]
        result = calculate_tool_call_metrics(predictions, cases)
        # Expected pairs: {("genre","action"), ("year","2024")}
        # Predicted pairs: {("genre","action"), ("year","2023")}
        # TP=1 (genre=action), FP=1 (year=2023), FN=1 (year=2024)
        # Precision=1/2=0.5, Recall=1/2=0.5, F1=0.5
        assert result.filter_extraction_f1 == 0.5

    def test_no_tool_request_cases(self):
        """Cases with None tool_request are skipped."""
        cases = [
            _make_case(tool_request=None),
        ]
        predictions = [
            {"tool": "tmdb_trending", "request": {"genre": "action"}},
        ]
        result = calculate_tool_call_metrics(predictions, cases)
        # No cases with expected_tool_request → schema validity, param accuracy = 0.0
        assert result.tool_request_schema_validity == 0.0
        assert result.required_parameter_accuracy == 0.0
        assert result.unsupported_parameter_rate == 0.0
        assert result.filter_extraction_f1 == 0.0

    def test_empty_inputs(self):
        """Empty inputs return zeroed metrics."""
        result = calculate_tool_call_metrics([], [])
        assert result.tool_selection_accuracy == 0.0


class TestRetrievalMetrics:
    """Unit tests for calculate_retrieval_metrics."""

    def test_perfect_recall(self):
        """All expected items found → recall 1.0."""
        cases = [
            _make_case(expected_items=["item1", "item2", "item3"]),
        ]
        predictions = [
            {"selected_items": ["item1", "item2", "item3", "extra"]},
        ]
        result = calculate_retrieval_metrics(predictions, cases)
        assert result.expected_item_recall == 1.0

    def test_partial_recall(self):
        """2 of 4 expected items found → recall 0.5."""
        cases = [
            _make_case(expected_items=["item1", "item2", "item3", "item4"]),
        ]
        predictions = [
            {"selected_items": ["item1", "item2"]},
        ]
        result = calculate_retrieval_metrics(predictions, cases)
        assert result.expected_item_recall == 0.5

    def test_forbidden_violation(self):
        """Selecting forbidden items → violation rate."""
        cases = [
            _make_case(
                expected_items=["item1"],
                forbidden_items=["bad1", "bad2"],
            ),
        ]
        predictions = [
            {"selected_items": ["item1", "bad1", "other"]},
        ]
        result = calculate_retrieval_metrics(predictions, cases)
        # 1 forbidden in 3 total selected
        assert abs(result.forbidden_item_violation_rate - 1 / 3) < 1e-9

    def test_no_forbidden_violations(self):
        """No forbidden items selected → rate 0.0."""
        cases = [
            _make_case(
                expected_items=["item1", "item2"],
                forbidden_items=["bad1"],
            ),
        ]
        predictions = [
            {"selected_items": ["item1", "item2"]},
        ]
        result = calculate_retrieval_metrics(predictions, cases)
        assert result.forbidden_item_violation_rate == 0.0

    def test_semantic_concept_recall_stub(self):
        """Semantic concept recall is stubbed at 1.0."""
        cases = [_make_case(expected_items=["item1"])]
        predictions = [{"selected_items": []}]
        result = calculate_retrieval_metrics(predictions, cases)
        assert result.semantic_concept_recall == 1.0

    def test_empty_expected_items(self):
        """No expected items → recall is 0.0 (no eligible cases)."""
        cases = [_make_case(expected_items=[])]
        predictions = [{"selected_items": ["item1"]}]
        result = calculate_retrieval_metrics(predictions, cases)
        assert result.expected_item_recall == 0.0

    def test_empty_inputs(self):
        """Empty inputs return appropriate defaults."""
        result = calculate_retrieval_metrics([], [])
        assert result.expected_item_recall == 0.0
        assert result.forbidden_item_violation_rate == 0.0


class TestGroundingMetrics:
    """Unit tests for calculate_grounding_metrics."""

    def test_perfect_grounding(self):
        """All titles grounded, all facts covered, correct type."""
        cases = [
            _make_case(
                expected_items=["The Matrix", "Inception"],
                acceptable_items=["Interstellar"],
                required_facts=[{"title": "The Matrix"}, {"year": "1999"}],
                response_type="recommendation",
            ),
        ]
        predictions = [
            {
                "response": "I recommend The Matrix from 1999 and Inception.",
                "claims": ["The Matrix is from 1999"],
                "response_type": "recommendation",
                "mentioned_titles": ["The Matrix", "Inception"],
            },
        ]
        result = calculate_grounding_metrics(predictions, cases)
        assert result.grounded_title_rate == 1.0
        assert result.required_facts_coverage == 1.0
        assert result.response_type_accuracy == 1.0

    def test_ungrounded_titles(self):
        """Titles not in expected/acceptable → lower grounded rate."""
        cases = [
            _make_case(
                expected_items=["The Matrix"],
                acceptable_items=[],
            ),
        ]
        predictions = [
            {
                "response": "Check out these movies.",
                "claims": [],
                "response_type": "recommendation",
                "mentioned_titles": ["The Matrix", "Unknown Movie"],
            },
        ]
        result = calculate_grounding_metrics(predictions, cases)
        # 1 grounded out of 2 mentioned
        assert result.grounded_title_rate == 0.5

    def test_unsupported_claims(self):
        """Claims not traceable to facts → unsupported rate."""
        cases = [
            _make_case(
                required_facts=[{"title": "The Matrix"}],
                optional_facts=[{"director": "Wachowskis"}],
            ),
        ]
        predictions = [
            {
                "response": "Great movie.",
                "claims": ["The Matrix is great", "Released in 2024", "Won 10 Oscars"],
                "response_type": "recommendation",
                "mentioned_titles": [],
            },
        ]
        result = calculate_grounding_metrics(predictions, cases)
        # "The Matrix is great" → contains "the matrix" (supported)
        # "Released in 2024" → no match → unsupported
        # "Won 10 Oscars" → no match → unsupported
        # 2 unsupported out of 3 total
        assert abs(result.unsupported_claim_rate - 2 / 3) < 1e-9

    def test_required_facts_coverage(self):
        """Partial coverage of required facts."""
        cases = [
            _make_case(
                required_facts=[
                    {"title": "Inception"},
                    {"year": "2010"},
                    {"director": "Nolan"},
                ],
            ),
        ]
        predictions = [
            {
                "response": "Inception from 2010 is a masterpiece.",
                "claims": [],
                "response_type": "recommendation",
                "mentioned_titles": [],
            },
        ]
        result = calculate_grounding_metrics(predictions, cases)
        # "inception" found, "2010" found, "nolan" NOT found
        # 2 of 3 covered
        assert abs(result.required_facts_coverage - 2 / 3) < 1e-9

    def test_response_type_accuracy(self):
        """Correct response type → 1.0; wrong → 0.0."""
        cases = [
            _make_case(response_type="recommendation"),
            _make_case(response_type="error", case_id="c2",
                       route=ExpectedRoute.clarification, tool=ExpectedTool.none,
                       action=ExpectedAction.ask_clarifying_question),
        ]
        predictions = [
            {"response": "", "claims": [], "response_type": "recommendation", "mentioned_titles": []},
            {"response": "", "claims": [], "response_type": "recommendation", "mentioned_titles": []},
        ]
        result = calculate_grounding_metrics(predictions, cases)
        # 1 correct out of 2
        assert result.response_type_accuracy == 0.5

    def test_empty_inputs(self):
        """Empty inputs return zeroed metrics."""
        result = calculate_grounding_metrics([], [])
        assert result.grounded_title_rate == 0.0
        assert result.response_type_accuracy == 0.0

    def test_no_mentioned_titles(self):
        """No mentioned titles → grounded_title_rate = 0.0."""
        cases = [_make_case(expected_items=["The Matrix"])]
        predictions = [
            {
                "response": "Here are some recommendations.",
                "claims": [],
                "response_type": "recommendation",
                "mentioned_titles": [],
            },
        ]
        result = calculate_grounding_metrics(predictions, cases)
        assert result.grounded_title_rate == 0.0

    def test_no_required_facts(self):
        """No required facts → coverage = 0.0 (no eligible cases)."""
        cases = [_make_case(required_facts=[])]
        predictions = [
            {
                "response": "Great movie!",
                "claims": [],
                "response_type": "recommendation",
                "mentioned_titles": [],
            },
        ]
        result = calculate_grounding_metrics(predictions, cases)
        assert result.required_facts_coverage == 0.0
