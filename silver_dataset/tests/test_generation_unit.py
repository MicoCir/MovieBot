"""Unit tests for the generation module LLM interaction components.

Feature: silver-dataset-generation
Tests:
- _extract_json: valid JSON, JSON with preamble, JSON in code block, invalid JSON raises
- _build_prompt: returns string containing scenario context
- OllamaUnavailableError: has actionable message
- RetryConfig.delay_for_attempt: computes correct delays
- generate_query: retry behavior with mocked LLM responses
"""

import json
from unittest.mock import MagicMock, patch

import pytest

from silver_dataset.generation.query_generator import (
    OllamaQueryGenerator,
    OllamaUnavailableError,
    RetryConfig,
)
from silver_dataset.models.case import (
    Difficulty,
    ExpectedAction,
    ExpectedRoute,
    ExpectedTool,
    Suite,
)
from silver_dataset.models.latent_spec import LatentSpecification


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def generator() -> OllamaQueryGenerator:
    """Create a default OllamaQueryGenerator instance for testing."""
    return OllamaQueryGenerator()


@pytest.fixture
def sample_spec() -> LatentSpecification:
    """Create a sample LatentSpecification for prompt/generation tests."""
    return LatentSpecification(
        spec_id="test-spec-001",
        suite=Suite.e2e_routing_silver,
        scenario_family="routing_direct",
        scenario_type="trending_basic",
        route=ExpectedRoute.trending,
        tool=ExpectedTool.tmdb_trending,
        action=ExpectedAction.call_tool,
        language="en",
        response_language="en",
        difficulty=Difficulty.easy,
        tool_request_template={"time_window": "day"},
        user_constraints={"genre": "action"},
        fixture_id="tmdb_trending_day_normal",
        variation_type=None,
        seed_scenario_id="seed-001",
        tags=["trending", "basic"],
    )


# ---------------------------------------------------------------------------
# _extract_json unit tests
# ---------------------------------------------------------------------------


class TestExtractJson:
    """Unit tests for _extract_json method."""

    def test_valid_json_direct(self, generator: OllamaQueryGenerator):
        """Valid JSON string is parsed directly."""
        raw = '{"query": "What movies are popular?", "conversation_context": []}'
        result = generator._extract_json(raw)

        assert result["query"] == "What movies are popular?"
        assert result["conversation_context"] == []

    def test_json_with_preamble(self, generator: OllamaQueryGenerator):
        """JSON preceded by LLM chatter is extracted correctly."""
        raw = (
            "Sure! Here's the generated query:\n\n"
            '{"query": "Show me trending films", "conversation_context": []}'
        )
        result = generator._extract_json(raw)

        assert result["query"] == "Show me trending films"
        assert result["conversation_context"] == []

    def test_json_in_code_block(self, generator: OllamaQueryGenerator):
        """JSON wrapped in ```json code block is extracted."""
        raw = (
            "Here you go:\n"
            "```json\n"
            '{"query": "Recommend me a horror movie", "conversation_context": []}\n'
            "```\n"
            "Let me know if you need more."
        )
        result = generator._extract_json(raw)

        assert result["query"] == "Recommend me a horror movie"
        assert result["conversation_context"] == []

    def test_json_in_plain_code_block(self, generator: OllamaQueryGenerator):
        """JSON wrapped in plain ``` code block (no language) is extracted."""
        raw = (
            "Output:\n"
            "```\n"
            '{"query": "What is on Netflix?", "conversation_context": []}\n'
            "```"
        )
        result = generator._extract_json(raw)

        assert result["query"] == "What is on Netflix?"

    def test_invalid_json_raises(self, generator: OllamaQueryGenerator):
        """Completely invalid input raises ValueError."""
        raw = "This is not JSON at all, just plain text without any braces"

        with pytest.raises((ValueError, json.JSONDecodeError)):
            generator._extract_json(raw)

    def test_malformed_json_raises(self, generator: OllamaQueryGenerator):
        """Malformed JSON (missing closing brace) raises an error."""
        raw = '{"query": "incomplete'

        with pytest.raises((ValueError, json.JSONDecodeError)):
            generator._extract_json(raw)

    def test_extra_fields_are_preserved_in_dict(self, generator: OllamaQueryGenerator):
        """Extra fields in the JSON are kept in the returned dict (ignored later)."""
        raw = json.dumps({
            "query": "Find action movies",
            "conversation_context": [],
            "extra_field": "should be preserved",
            "another": 42,
        })
        result = generator._extract_json(raw)

        assert result["query"] == "Find action movies"
        assert result["extra_field"] == "should be preserved"
        assert result["another"] == 42

    def test_json_with_postamble(self, generator: OllamaQueryGenerator):
        """JSON followed by additional text is extracted correctly."""
        raw = (
            '{"query": "Best sci-fi series", "conversation_context": []}\n\n'
            "Note: This query targets Netflix content."
        )
        result = generator._extract_json(raw)

        assert result["query"] == "Best sci-fi series"


# ---------------------------------------------------------------------------
# _build_prompt unit tests
# ---------------------------------------------------------------------------


class TestBuildPrompt:
    """Unit tests for _build_prompt method."""

    def test_prompt_contains_scenario_context(
        self, generator: OllamaQueryGenerator, sample_spec: LatentSpecification
    ):
        """_build_prompt returns a string containing scenario family and type."""
        prompt = generator._build_prompt(sample_spec)

        assert isinstance(prompt, str)
        assert len(prompt) > 0
        assert sample_spec.scenario_family in prompt
        assert sample_spec.scenario_type in prompt

    def test_prompt_contains_language(
        self, generator: OllamaQueryGenerator, sample_spec: LatentSpecification
    ):
        """Prompt includes the target language."""
        prompt = generator._build_prompt(sample_spec)

        assert sample_spec.language in prompt

    def test_prompt_contains_difficulty(
        self, generator: OllamaQueryGenerator, sample_spec: LatentSpecification
    ):
        """Prompt includes the difficulty level."""
        prompt = generator._build_prompt(sample_spec)

        assert sample_spec.difficulty.value in prompt

    def test_prompt_contains_user_constraints_when_present(
        self, generator: OllamaQueryGenerator, sample_spec: LatentSpecification
    ):
        """Prompt includes user constraints when they are non-empty."""
        prompt = generator._build_prompt(sample_spec)

        # The constraint dict should be serialized into the prompt
        assert "genre" in prompt or "action" in prompt

    def test_prompt_contains_variation_type_when_present(
        self, generator: OllamaQueryGenerator,
    ):
        """Prompt includes variation style when specified."""
        spec = LatentSpecification(
            spec_id="test-var",
            suite=Suite.e2e_routing_silver,
            scenario_family="routing",
            scenario_type="basic",
            route=ExpectedRoute.trending,
            tool=ExpectedTool.tmdb_trending,
            action=ExpectedAction.call_tool,
            language="es",
            response_language="es",
            difficulty=Difficulty.medium,
            variation_type="typo",
        )
        prompt = generator._build_prompt(spec)

        assert "typo" in prompt

    def test_prompt_demands_json_format(
        self, generator: OllamaQueryGenerator, sample_spec: LatentSpecification
    ):
        """Prompt explicitly demands JSON output format."""
        prompt = generator._build_prompt(sample_spec)

        assert "JSON" in prompt or "json" in prompt


# ---------------------------------------------------------------------------
# OllamaUnavailableError unit tests
# ---------------------------------------------------------------------------


class TestOllamaUnavailableError:
    """Unit tests for OllamaUnavailableError."""

    def test_default_message_is_actionable(self):
        """Default error message gives user actionable guidance."""
        err = OllamaUnavailableError()
        msg = str(err)

        assert "Ollama" in msg or "ollama" in msg
        assert "ollama serve" in msg.lower() or "running" in msg.lower()

    def test_custom_message_preserved(self):
        """Custom message is preserved when provided."""
        custom = "Custom error: service down"
        err = OllamaUnavailableError(custom)

        assert str(err) == custom

    def test_is_exception_subclass(self):
        """OllamaUnavailableError is a proper Exception subclass."""
        err = OllamaUnavailableError()
        assert isinstance(err, Exception)


# ---------------------------------------------------------------------------
# RetryConfig.delay_for_attempt unit tests
# ---------------------------------------------------------------------------


class TestRetryConfig:
    """Unit tests for RetryConfig delay computation."""

    def test_delay_for_attempt_0(self):
        """Attempt 0 uses base delay."""
        config = RetryConfig(base_delay_seconds=2.0, backoff_factor=2.0)
        assert config.delay_for_attempt(0) == 2.0

    def test_delay_for_attempt_1(self):
        """Attempt 1 applies backoff once."""
        config = RetryConfig(base_delay_seconds=2.0, backoff_factor=2.0)
        assert config.delay_for_attempt(1) == 4.0

    def test_delay_for_attempt_2(self):
        """Attempt 2 applies backoff twice."""
        config = RetryConfig(base_delay_seconds=2.0, backoff_factor=2.0)
        assert config.delay_for_attempt(2) == 8.0

    def test_custom_base_and_factor(self):
        """Custom base delay and factor compute correctly."""
        config = RetryConfig(base_delay_seconds=1.0, backoff_factor=3.0)
        assert config.delay_for_attempt(0) == 1.0
        assert config.delay_for_attempt(1) == 3.0
        assert config.delay_for_attempt(2) == 9.0

    def test_exponential_growth(self):
        """Delays grow exponentially with each attempt."""
        config = RetryConfig(base_delay_seconds=2.0, backoff_factor=2.0)
        delays = [config.delay_for_attempt(i) for i in range(5)]

        # Each delay should be backoff_factor times the previous
        for i in range(1, len(delays)):
            assert delays[i] == delays[i - 1] * config.backoff_factor


# ---------------------------------------------------------------------------
# generate_query retry tests (mocked)
# ---------------------------------------------------------------------------


class TestGenerateQueryRetries:
    """Mock-based tests for generate_query retry behavior."""

    def _make_mock_response(self, content: str) -> MagicMock:
        """Create a mock chat completion response."""
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = content
        return mock_response

    @patch("silver_dataset.generation.query_generator.time.sleep")
    def test_generate_query_succeeds_on_first_try(
        self, mock_sleep, sample_spec: LatentSpecification
    ):
        """generate_query returns a SilverCase on valid first response."""
        gen = OllamaQueryGenerator(max_retries=3)
        valid_response = json.dumps({
            "query": "What movies are trending today?",
            "conversation_context": [],
        })

        with patch.object(gen._client.chat.completions, "create") as mock_create:
            mock_create.return_value = self._make_mock_response(valid_response)
            result = gen.generate_query(sample_spec, batch_id="batch-001")

        assert result is not None
        assert result.query == "What movies are trending today?"
        assert result.generation_metadata.batch_id == "batch-001"
        mock_sleep.assert_not_called()

    @patch("silver_dataset.generation.query_generator.time.sleep")
    def test_generate_query_retries_on_invalid_json(
        self, mock_sleep, sample_spec: LatentSpecification
    ):
        """generate_query retries when LLM returns invalid JSON."""
        gen = OllamaQueryGenerator(max_retries=3)
        valid_response = json.dumps({
            "query": "Show me popular films",
            "conversation_context": [],
        })

        with patch.object(gen._client.chat.completions, "create") as mock_create:
            mock_create.side_effect = [
                self._make_mock_response("This is not JSON"),
                self._make_mock_response(valid_response),
            ]
            result = gen.generate_query(sample_spec, batch_id="batch-002")

        assert result is not None
        assert result.query == "Show me popular films"

    @patch("silver_dataset.generation.query_generator.time.sleep")
    def test_generate_query_returns_none_after_max_retries(
        self, mock_sleep, sample_spec: LatentSpecification
    ):
        """generate_query returns None when max retries are exhausted."""
        gen = OllamaQueryGenerator(max_retries=3)

        with patch.object(gen._client.chat.completions, "create") as mock_create:
            mock_create.return_value = self._make_mock_response("not json at all")
            result = gen.generate_query(sample_spec, batch_id="batch-003")

        assert result is None

    @patch("silver_dataset.generation.query_generator.time.sleep")
    def test_generate_query_raises_on_connection_error(
        self, mock_sleep, sample_spec: LatentSpecification
    ):
        """generate_query raises OllamaUnavailableError on connection failure."""
        from openai import APIConnectionError

        gen = OllamaQueryGenerator(max_retries=3)

        with patch.object(gen._client.chat.completions, "create") as mock_create:
            mock_create.side_effect = APIConnectionError(request=MagicMock())
            with pytest.raises(OllamaUnavailableError):
                gen.generate_query(sample_spec, batch_id="batch-004")

    @patch("silver_dataset.generation.query_generator.time.sleep")
    def test_generate_query_retries_on_transient_api_error(
        self, mock_sleep, sample_spec: LatentSpecification
    ):
        """generate_query retries on transient OpenAI API errors."""
        from openai import OpenAIError

        gen = OllamaQueryGenerator(max_retries=3)
        valid_response = json.dumps({
            "query": "Trending movies please",
            "conversation_context": [],
        })

        with patch.object(gen._client.chat.completions, "create") as mock_create:
            mock_create.side_effect = [
                OpenAIError("transient error"),
                self._make_mock_response(valid_response),
            ]
            result = gen.generate_query(sample_spec, batch_id="batch-005")

        assert result is not None
        assert result.query == "Trending movies please"
