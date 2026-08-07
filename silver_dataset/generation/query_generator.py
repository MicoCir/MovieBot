"""Ollama-based query generator for the Silver Dataset pipeline.

Generates natural language queries from latent specifications using Ollama
via the OpenAI-compatible API. Handles retry logic, JSON extraction from
noisy LLM output, and generation metadata recording.
"""

import json
import re
import time
from dataclasses import dataclass
from datetime import datetime, timezone

from openai import APIConnectionError, APITimeoutError, OpenAI, OpenAIError

from silver_dataset.models.case import GenerationMetadata, SilverCase, Split
from silver_dataset.models.latent_spec import LatentSpecification


class OllamaUnavailableError(Exception):
    """Raised when Ollama is unreachable or not responding.

    Provides an actionable message to the user without exposing
    internal configuration details.
    """

    def __init__(self, message: str | None = None):
        if message is None:
            message = (
                "The local LLM service is not available. "
                "Please ensure Ollama is running and the model is loaded. "
                "You can start it with: ollama serve"
            )
        super().__init__(message)


@dataclass
class RetryConfig:
    """Configuration for retry behavior with exponential backoff."""

    max_retries: int = 3
    base_delay_seconds: float = 2.0
    backoff_factor: float = 2.0
    timeout_seconds: float = 120.0

    def delay_for_attempt(self, attempt: int) -> float:
        """Calculate delay for a given attempt number (0-indexed)."""
        return self.base_delay_seconds * (self.backoff_factor ** attempt)


class OllamaQueryGenerator:
    """Generates natural language queries from latent specifications using Ollama.

    Uses the OpenAI Python client configured for Ollama's compatible API endpoint.
    Implements retry logic with exponential backoff, robust JSON extraction from
    noisy LLM output, and generation metadata recording.
    """

    def __init__(
        self,
        base_url: str = "http://localhost:11434/v1",
        model: str = "qwen3.5:27b",
        max_retries: int = 3,
        timeout_seconds: float = 120.0,
        prompt_version: str = "v1",
    ):
        self._client = OpenAI(base_url=base_url, api_key="ollama")
        self._model = model
        self._prompt_version = prompt_version
        self._retry_config = RetryConfig(
            max_retries=max_retries,
            timeout_seconds=timeout_seconds,
        )

    def generate_query(
        self,
        spec: LatentSpecification,
        batch_id: str,
    ) -> SilverCase | None:
        """Generate a single case from a latent spec.

        Returns None if max retries are exceeded without a valid response.
        Raises OllamaUnavailableError if Ollama cannot be reached.
        """
        prompt = self._build_prompt(spec)

        for attempt in range(self._retry_config.max_retries):
            if attempt > 0:
                delay = self._retry_config.delay_for_attempt(attempt - 1)
                time.sleep(delay)

            start_time = time.perf_counter()
            try:
                response = self._client.chat.completions.create(
                    model=self._model,
                    messages=[
                        {"role": "system", "content": "You are a dataset generation assistant. Respond ONLY with valid JSON."},
                        {"role": "user", "content": prompt},
                    ],
                    timeout=self._retry_config.timeout_seconds,
                )
                inference_duration_ms = (time.perf_counter() - start_time) * 1000
            except (APIConnectionError, APITimeoutError) as exc:
                raise OllamaUnavailableError() from exc
            except OpenAIError:
                # Transient API error — retry
                continue

            raw_content = response.choices[0].message.content or ""

            try:
                parsed = self._extract_json(raw_content)
            except (json.JSONDecodeError, ValueError):
                # Invalid JSON — retry
                continue

            # Build the SilverCase from spec labels + LLM-generated fields
            try:
                case = self._build_case(
                    spec=spec,
                    parsed=parsed,
                    batch_id=batch_id,
                    inference_duration_ms=inference_duration_ms,
                )
                return case
            except (ValueError, KeyError):
                # Missing required fields in parsed response — retry
                continue

        # Max retries exceeded
        return None

    def _build_prompt(self, spec: LatentSpecification) -> str:
        """Build versioned prompt that demands JSON-only response.

        The prompt includes spec context (scenario family, type, language,
        difficulty) and prohibits exposing internal labels in the output.
        """
        if self._prompt_version == "v1":
            return self._build_prompt_v1(spec)
        # Default to v1 for unknown versions
        return self._build_prompt_v1(spec)

    def _build_prompt_v1(self, spec: LatentSpecification) -> str:
        """Version 1 of the generation prompt."""
        context_parts = [
            f"Scenario family: {spec.scenario_family}",
            f"Scenario type: {spec.scenario_type}",
            f"Language: {spec.language}",
            f"Difficulty: {spec.difficulty.value}",
        ]

        if spec.user_constraints:
            context_parts.append(
                f"User constraints: {json.dumps(spec.user_constraints, ensure_ascii=False)}"
            )

        if spec.variation_type:
            context_parts.append(f"Variation style: {spec.variation_type}")

        context_block = "\n".join(context_parts)

        return f"""Generate a natural user query for an audiovisual recommendation chatbot.

Context:
{context_block}

Rules:
1. The query must sound like a real user message — natural, conversational, and in the specified language.
2. Do NOT include any internal system labels, field names, or technical identifiers in the query.
3. Do NOT mention routing, tools, actions, or any evaluation metadata.
4. If difficulty is "hard", make the query more ambiguous, indirect, or complex.
5. If a variation style is specified, apply it (e.g., typos, code-switching, colloquial).

Respond with ONLY a JSON object in this exact format (no extra text, no markdown):
{{
  "query": "<the natural language user query>",
  "conversation_context": []
}}

The "conversation_context" field should be an empty list for single-turn queries, or a list of message objects with "role" and "content" fields for multi-turn scenarios."""

    def _extract_json(self, raw_response: str) -> dict:
        """Extract JSON block from potentially noisy LLM output.

        Attempts extraction in order:
        1. Direct JSON parse of the full response
        2. Find first '{' and last '}' and parse that substring
        3. Look for ```json...``` code block patterns

        Extra fields not in the expected schema are ignored (kept in dict
        but not used when building the case).

        Raises ValueError or json.JSONDecodeError if no valid JSON found.
        """
        # Strategy 1: Direct parse
        stripped = raw_response.strip()
        try:
            result = json.loads(stripped)
            if isinstance(result, dict):
                return result
        except json.JSONDecodeError:
            pass

        # Strategy 2: Find outermost braces
        first_brace = stripped.find("{")
        last_brace = stripped.rfind("}")
        if first_brace != -1 and last_brace > first_brace:
            candidate = stripped[first_brace : last_brace + 1]
            try:
                result = json.loads(candidate)
                if isinstance(result, dict):
                    return result
            except json.JSONDecodeError:
                pass

        # Strategy 3: Code block pattern
        code_block_pattern = re.compile(
            r"```(?:json)?\s*\n?(.*?)\n?\s*```", re.DOTALL
        )
        match = code_block_pattern.search(stripped)
        if match:
            block_content = match.group(1).strip()
            try:
                result = json.loads(block_content)
                if isinstance(result, dict):
                    return result
            except json.JSONDecodeError:
                pass

        raise ValueError(
            "Could not extract valid JSON from LLM response"
        )

    def _build_case(
        self,
        spec: LatentSpecification,
        parsed: dict,
        batch_id: str,
        inference_duration_ms: float,
    ) -> SilverCase:
        """Build a SilverCase from spec labels and LLM-generated content.

        Labels come deterministically from the spec; only 'query' and
        'conversation_context' come from the LLM output.
        """
        query = parsed.get("query")
        if not query or not isinstance(query, str) or not query.strip():
            raise ValueError("LLM response missing valid 'query' field")

        conversation_context = parsed.get("conversation_context", [])
        if not isinstance(conversation_context, list):
            conversation_context = []

        now = datetime.now(timezone.utc)

        metadata = GenerationMetadata(
            method="ollama",
            model=self._model,
            prompt_version=self._prompt_version,
            timestamp=now,
            batch_id=batch_id,
            variation_type=spec.variation_type,
        )

        return SilverCase(
            case_id=f"{spec.spec_id}_{batch_id}",
            dataset_version="draft",
            suite=spec.suite,
            split=Split.dev,  # Split assigned later by assign_splits
            scenario_family=spec.scenario_family,
            scenario_type=spec.scenario_type,
            query=query.strip(),
            conversation_context=conversation_context,
            language=spec.language,
            response_language=spec.response_language,
            expected_route=spec.route,
            expected_tool=spec.tool,
            expected_action=spec.action,
            expected_tool_request=spec.tool_request_template,
            user_constraints=spec.user_constraints,
            tool_output_fixture_id=spec.fixture_id,
            difficulty=spec.difficulty,
            tags=spec.tags,
            seed_scenario_id=spec.seed_scenario_id or spec.spec_id,
            generation_metadata=metadata,
            expected_response_type="text",
        )
