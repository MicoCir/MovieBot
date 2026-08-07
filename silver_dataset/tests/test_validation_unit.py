"""Unit tests for the validation pipeline.

Tests SchemaValidator, RuleValidator, Deduplicator, and assign_validation_status
with specific examples and edge cases.
"""

import pathlib
import json
import tempfile
from datetime import datetime

import pytest

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
from silver_dataset.models.fixtures import FixtureRegistry
from silver_dataset.validation.schema_validator import SchemaValidator
from silver_dataset.validation.rule_validator import RuleValidator
from silver_dataset.validation.deduplicator import Deduplicator, DuplicatePair
from silver_dataset.validation.critic import CriticResult
from silver_dataset.validation.status import assign_validation_status


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _valid_case_dict(**overrides) -> dict:
    """Create a valid SilverCase dictionary with optional field overrides."""
    base = {
        "case_id": "test_case_001",
        "dataset_version": "silver_v1",
        "suite": "e2e_routing_silver",
        "split": "dev",
        "scenario_family": "trending_basic",
        "scenario_type": "direct_request",
        "query": "What movies are trending today?",
        "conversation_context": [],
        "language": "en",
        "response_language": "en",
        "expected_route": "trending",
        "expected_tool": "tmdb_trending",
        "expected_action": "call_tool",
        "expected_tool_request": {"time_window": "day"},
        "user_constraints": {},
        "tool_output_fixture_id": None,
        "expected_selected_items": [],
        "acceptable_selected_items": [],
        "forbidden_selected_items": [],
        "required_facts": [],
        "optional_facts": [],
        "forbidden_claims": [],
        "expected_response_type": "recommendation_list",
        "difficulty": "easy",
        "tags": ["trending", "basic"],
        "seed_scenario_id": "seed_trending_001",
        "generation_metadata": {
            "method": "latent_to_query",
            "model": "qwen3.5:27b",
            "prompt_version": "v1",
            "timestamp": "2024-01-15T10:00:00",
            "batch_id": "batch_001",
            "variation_type": None,
        },
        "automatic_validation_status": "passed",
        "review_status": "not_human_reviewed",
    }
    base.update(overrides)
    return base


def _make_case(case_id: str, query: str) -> SilverCase:
    """Create a minimal valid SilverCase with given case_id and query."""
    return SilverCase(
        case_id=case_id,
        dataset_version="silver_v1",
        suite=Suite.e2e_routing_silver,
        split=Split.dev,
        scenario_family="test_family",
        scenario_type="test_type",
        query=query,
        language="en",
        response_language="en",
        expected_route=ExpectedRoute.trending,
        expected_tool=ExpectedTool.tmdb_trending,
        expected_action=ExpectedAction.call_tool,
        expected_response_type="recommendation",
        difficulty=Difficulty.easy,
        tags=[],
        seed_scenario_id="seed_001",
        generation_metadata=GenerationMetadata(
            method="test",
            model="test_model",
            prompt_version="v1",
            timestamp=datetime(2024, 1, 1),
            batch_id="batch_test",
        ),
    )


@pytest.fixture
def fixture_registry(tmp_path: pathlib.Path) -> FixtureRegistry:
    """Create a FixtureRegistry with sample fixtures for testing."""
    # Create TMDB fixture
    tmdb_dir = tmp_path / "tmdb"
    tmdb_dir.mkdir()
    tmdb_fixture = {
        "results": [
            {"id": 100, "title": "Test Movie 1", "overview": "A test movie"},
            {"id": 200, "title": "Test Movie 2", "overview": "Another test movie"},
            {"id": 300, "title": "Test Movie 3", "overview": "Third test movie"},
        ]
    }
    (tmdb_dir / "tmdb_trending_normal.json").write_text(
        json.dumps(tmdb_fixture), encoding="utf-8"
    )

    # Create Netflix fixture
    netflix_dir = tmp_path / "netflix"
    netflix_dir.mkdir()
    netflix_fixture = {
        "results": [
            {"show_id": "s1", "title": "Netflix Show 1", "type": "Movie"},
            {"show_id": "s2", "title": "Netflix Show 2", "type": "TV Show"},
        ]
    }
    (netflix_dir / "netflix_search_comedy.json").write_text(
        json.dumps(netflix_fixture), encoding="utf-8"
    )

    return FixtureRegistry(tmp_path)


# ===========================================================================
# Test SchemaValidator
# ===========================================================================


class TestSchemaValidator:
    """Unit tests for SchemaValidator."""

    def test_valid_case_returns_parsed_case_and_no_errors(self):
        """A valid dict should parse successfully with no errors."""
        validator = SchemaValidator()
        raw = _valid_case_dict()

        case, errors = validator.validate(raw)

        assert case is not None
        assert errors == []
        assert case.case_id == "test_case_001"
        assert case.expected_route == ExpectedRoute.trending

    def test_missing_required_field_returns_none_and_errors(self):
        """Missing a required field should return None and error messages."""
        validator = SchemaValidator()
        raw = _valid_case_dict()
        del raw["case_id"]

        case, errors = validator.validate(raw)

        assert case is None
        assert len(errors) > 0

    def test_invalid_enum_value_returns_none_and_errors(self):
        """Invalid enum value should return None and errors."""
        validator = SchemaValidator()
        raw = _valid_case_dict(expected_route="invalid_route")

        case, errors = validator.validate(raw)

        assert case is None
        assert len(errors) > 0

    def test_inconsistent_route_tool_returns_none_and_errors(self):
        """Route/tool inconsistency caught by model_validator should fail."""
        validator = SchemaValidator()
        raw = _valid_case_dict(
            expected_route="out_of_scope",
            expected_tool="tmdb_trending",
            expected_action="return_out_of_scope",
        )

        case, errors = validator.validate(raw)

        assert case is None
        assert len(errors) > 0

    def test_empty_dict_returns_multiple_errors(self):
        """Empty dict should produce multiple validation errors."""
        validator = SchemaValidator()

        case, errors = validator.validate({})

        assert case is None
        assert len(errors) > 0

    def test_extra_fields_are_ignored(self):
        """Extra fields not in the schema should be silently ignored."""
        validator = SchemaValidator()
        raw = _valid_case_dict(extra_unknown_field="should be ignored")

        case, errors = validator.validate(raw)

        assert case is not None
        assert errors == []


# ===========================================================================
# Test RuleValidator
# ===========================================================================


class TestRuleValidator:
    """Unit tests for RuleValidator with fixture reference checks."""

    def test_valid_case_with_existing_fixture_passes(
        self, fixture_registry: FixtureRegistry
    ):
        """A case referencing an existing fixture with valid IDs should pass."""
        validator = RuleValidator(fixture_registry)
        case = SilverCase(
            case_id="case_001",
            dataset_version="silver_v1",
            suite=Suite.tmdb_agent_silver,
            split=Split.dev,
            scenario_family="trending",
            scenario_type="basic",
            query="What's trending?",
            language="en",
            response_language="en",
            expected_route=ExpectedRoute.trending,
            expected_tool=ExpectedTool.tmdb_trending,
            expected_action=ExpectedAction.call_tool,
            expected_response_type="recommendation",
            difficulty=Difficulty.easy,
            tags=[],
            seed_scenario_id="seed_001",
            tool_output_fixture_id="tmdb_trending_normal",
            expected_selected_items=["100", "200"],
            generation_metadata=GenerationMetadata(
                method="test",
                model="test",
                prompt_version="v1",
                timestamp=datetime(2024, 1, 1),
                batch_id="batch",
            ),
        )

        violations = validator.validate(case)

        assert violations == []

    def test_nonexistent_fixture_reports_violation(
        self, fixture_registry: FixtureRegistry
    ):
        """A case referencing a nonexistent fixture should report a violation."""
        validator = RuleValidator(fixture_registry)
        case = SilverCase(
            case_id="case_002",
            dataset_version="silver_v1",
            suite=Suite.tmdb_agent_silver,
            split=Split.dev,
            scenario_family="trending",
            scenario_type="basic",
            query="What's trending?",
            language="en",
            response_language="en",
            expected_route=ExpectedRoute.trending,
            expected_tool=ExpectedTool.tmdb_trending,
            expected_action=ExpectedAction.call_tool,
            expected_response_type="recommendation",
            difficulty=Difficulty.easy,
            tags=[],
            seed_scenario_id="seed_001",
            tool_output_fixture_id="tmdb_nonexistent_fixture",
            expected_selected_items=[],
            generation_metadata=GenerationMetadata(
                method="test",
                model="test",
                prompt_version="v1",
                timestamp=datetime(2024, 1, 1),
                batch_id="batch",
            ),
        )

        violations = validator.validate(case)

        assert len(violations) >= 1
        assert "does not exist" in violations[0]

    def test_item_id_not_in_fixture_reports_violation(
        self, fixture_registry: FixtureRegistry
    ):
        """Item IDs not present in the fixture should be flagged."""
        validator = RuleValidator(fixture_registry)
        case = SilverCase(
            case_id="case_003",
            dataset_version="silver_v1",
            suite=Suite.tmdb_agent_silver,
            split=Split.dev,
            scenario_family="trending",
            scenario_type="basic",
            query="What's trending?",
            language="en",
            response_language="en",
            expected_route=ExpectedRoute.trending,
            expected_tool=ExpectedTool.tmdb_trending,
            expected_action=ExpectedAction.call_tool,
            expected_response_type="recommendation",
            difficulty=Difficulty.easy,
            tags=[],
            seed_scenario_id="seed_001",
            tool_output_fixture_id="tmdb_trending_normal",
            expected_selected_items=["100", "999"],  # 999 doesn't exist
            generation_metadata=GenerationMetadata(
                method="test",
                model="test",
                prompt_version="v1",
                timestamp=datetime(2024, 1, 1),
                batch_id="batch",
            ),
        )

        violations = validator.validate(case)

        assert len(violations) >= 1
        assert any("999" in v for v in violations)

    def test_items_without_fixture_id_reports_violation(
        self, fixture_registry: FixtureRegistry
    ):
        """Having item IDs without a fixture reference should be flagged."""
        validator = RuleValidator(fixture_registry)
        case = SilverCase(
            case_id="case_004",
            dataset_version="silver_v1",
            suite=Suite.e2e_routing_silver,
            split=Split.dev,
            scenario_family="trending",
            scenario_type="basic",
            query="What's trending?",
            language="en",
            response_language="en",
            expected_route=ExpectedRoute.trending,
            expected_tool=ExpectedTool.tmdb_trending,
            expected_action=ExpectedAction.call_tool,
            expected_response_type="recommendation",
            difficulty=Difficulty.easy,
            tags=[],
            seed_scenario_id="seed_001",
            tool_output_fixture_id=None,
            expected_selected_items=["100"],
            generation_metadata=GenerationMetadata(
                method="test",
                model="test",
                prompt_version="v1",
                timestamp=datetime(2024, 1, 1),
                batch_id="batch",
            ),
        )

        violations = validator.validate(case)

        assert len(violations) >= 1
        assert "no tool_output_fixture_id" in violations[0]

    def test_netflix_fixture_item_ids_validated(
        self, fixture_registry: FixtureRegistry
    ):
        """Netflix fixture uses show_id field for item ID validation."""
        validator = RuleValidator(fixture_registry)
        case = SilverCase(
            case_id="case_005",
            dataset_version="silver_v1",
            suite=Suite.netflix_agent_silver,
            split=Split.dev,
            scenario_family="search",
            scenario_type="comedy",
            query="Find me a comedy on Netflix",
            language="en",
            response_language="en",
            expected_route=ExpectedRoute.netflix,
            expected_tool=ExpectedTool.netflix_search,
            expected_action=ExpectedAction.call_tool,
            expected_response_type="recommendation",
            difficulty=Difficulty.easy,
            tags=[],
            seed_scenario_id="seed_002",
            tool_output_fixture_id="netflix_search_comedy",
            expected_selected_items=["s1"],  # Valid
            acceptable_selected_items=["s2"],  # Valid
            forbidden_selected_items=["s99"],  # Invalid — doesn't exist
            generation_metadata=GenerationMetadata(
                method="test",
                model="test",
                prompt_version="v1",
                timestamp=datetime(2024, 1, 1),
                batch_id="batch",
            ),
        )

        violations = validator.validate(case)

        assert len(violations) == 1
        assert "s99" in violations[0]
        assert "forbidden_selected_items" in violations[0]


# ===========================================================================
# Test Deduplicator
# ===========================================================================


class TestDeduplicator:
    """Unit tests for Deduplicator with known duplicate pairs."""

    def test_exact_duplicates_detected(self):
        """Identical queries should be flagged as exact duplicates."""
        case_a = _make_case("case_001", "What movies are trending today?")
        case_b = _make_case("case_002", "What movies are trending today?")
        dedup = Deduplicator()

        pairs = dedup.find_duplicates([case_a, case_b])

        assert len(pairs) == 1
        assert pairs[0].match_type == "exact"
        assert pairs[0].similarity == 1.0

    def test_normalized_duplicates_case_insensitive(self):
        """Case-insensitive matches should be detected as normalized duplicates."""
        case_a = _make_case("case_001", "What Movies Are Trending?")
        case_b = _make_case("case_002", "what movies are trending?")
        dedup = Deduplicator()

        pairs = dedup.find_duplicates([case_a, case_b])

        assert len(pairs) == 1
        assert pairs[0].match_type == "normalized"

    def test_normalized_duplicates_extra_punctuation(self):
        """Extra punctuation should be stripped in normalization."""
        case_a = _make_case("case_001", "What movies are trending???")
        case_b = _make_case("case_002", "What movies are trending")
        dedup = Deduplicator()

        pairs = dedup.find_duplicates([case_a, case_b])

        assert len(pairs) == 1
        assert pairs[0].match_type == "normalized"

    def test_distinct_queries_not_flagged(self):
        """Clearly different queries should not be flagged."""
        case_a = _make_case("case_001", "What movies are trending today?")
        case_b = _make_case("case_002", "Find me a comedy show on Netflix")
        dedup = Deduplicator()

        pairs = dedup.find_duplicates([case_a, case_b])

        assert len(pairs) == 0

    def test_semantic_similar_detected_above_threshold(self):
        """Queries very similar but not exact should be flagged with semantic match."""
        case_a = _make_case("case_001", "what movies are trending right now")
        case_b = _make_case("case_002", "what movies are trending right here")
        dedup = Deduplicator(similarity_threshold=0.80)

        pairs = dedup.find_duplicates([case_a, case_b])

        # These are similar enough that at 0.80 threshold they should match
        assert len(pairs) >= 1

    def test_empty_list_returns_no_duplicates(self):
        """Empty case list should return empty results."""
        dedup = Deduplicator()

        pairs = dedup.find_duplicates([])

        assert pairs == []

    def test_single_case_returns_no_duplicates(self):
        """Single case list should return no duplicates."""
        case = _make_case("case_001", "Trending movies")
        dedup = Deduplicator()

        pairs = dedup.find_duplicates([case])

        assert pairs == []

    def test_multiple_duplicates_in_list(self):
        """All duplicate pairs in a multi-case list should be found."""
        case_a = _make_case("case_001", "trending movies")
        case_b = _make_case("case_002", "trending movies")
        case_c = _make_case("case_003", "trending movies")
        dedup = Deduplicator()

        pairs = dedup.find_duplicates([case_a, case_b, case_c])

        # Three cases all equal → 3 pairs: (a,b), (a,c), (b,c)
        assert len(pairs) == 3

    def test_invalid_threshold_raises_error(self):
        """Threshold outside [0,1] should raise ValueError."""
        with pytest.raises(ValueError):
            Deduplicator(similarity_threshold=1.5)

        with pytest.raises(ValueError):
            Deduplicator(similarity_threshold=-0.1)


# ===========================================================================
# Test assign_validation_status
# ===========================================================================


class TestAssignValidationStatus:
    """Unit tests for validation status assignment logic."""

    def test_all_pass_returns_passed(self):
        """No errors and no warnings → passed."""
        result = assign_validation_status(
            schema_errors=[],
            rule_violations=[],
            critic_result=CriticResult(status="passed", confidence=0.95),
        )
        assert result == ValidationStatus.passed

    def test_schema_errors_returns_failed(self):
        """Schema errors → failed regardless of other results."""
        result = assign_validation_status(
            schema_errors=["Missing field 'case_id'"],
            rule_violations=[],
            critic_result=CriticResult(status="passed", confidence=0.9),
        )
        assert result == ValidationStatus.failed

    def test_rule_violations_returns_failed(self):
        """Rule violations → failed."""
        result = assign_validation_status(
            schema_errors=[],
            rule_violations=["Fixture does not exist"],
            critic_result=CriticResult(status="passed", confidence=0.9),
        )
        assert result == ValidationStatus.failed

    def test_critic_failed_returns_failed(self):
        """Critic status 'failed' → failed."""
        result = assign_validation_status(
            schema_errors=[],
            rule_violations=[],
            critic_result=CriticResult(status="failed", confidence=0.8),
        )
        assert result == ValidationStatus.failed

    def test_critic_warning_returns_warning(self):
        """Critic status 'warning' → warning."""
        result = assign_validation_status(
            schema_errors=[],
            rule_violations=[],
            critic_result=CriticResult(status="warning", confidence=0.6),
        )
        assert result == ValidationStatus.warning

    def test_no_critic_defaults_to_passed(self):
        """No critic result (None) → passed if schema and rules pass."""
        result = assign_validation_status(
            schema_errors=[],
            rule_violations=[],
            critic_result=None,
        )
        assert result == ValidationStatus.passed

    def test_schema_errors_take_priority_over_critic_warning(self):
        """Schema errors should produce failed even if critic says warning."""
        result = assign_validation_status(
            schema_errors=["Invalid type for field"],
            rule_violations=[],
            critic_result=CriticResult(status="warning", confidence=0.5),
        )
        assert result == ValidationStatus.failed
