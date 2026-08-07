"""LLM-based quality assessment for Silver Dataset cases.

Uses a local LLM (Ollama) to evaluate coherence and quality of generated
cases. The critic does NOT modify labels — it only assesses and emits
status, confidence, and warnings.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from silver_dataset.models.case import SilverCase


@dataclass
class CriticResult:
    """Result of LLM-based quality assessment.

    Attributes:
        status: Assessment outcome — "passed", "warning", or "failed".
        confidence: Model's confidence in the assessment (0.0 to 1.0).
        warnings: List of quality concern descriptions.
    """

    status: str  # "passed", "warning", "failed"
    confidence: float
    warnings: list[str] = field(default_factory=list)


class Critic:
    """LLM-based quality assessment for Silver Dataset cases.

    Evaluates coherence between a case's query and its expected labels,
    checking for issues like:
    - Query doesn't match expected route semantics
    - Query exposes internal label names
    - Query is incoherent or nonsensical

    Does NOT modify labels — only assesses quality.
    """

    def __init__(
        self,
        base_url: str = "http://localhost:11434/v1",
        model: str = "qwen3.5:27b",
        api_key: str = "ollama",
        timeout: float = 60.0,
    ) -> None:
        """Initialize the Critic with LLM client configuration.

        Args:
            base_url: OpenAI-compatible API base URL.
            model: Model identifier for quality assessment.
            api_key: API key (placeholder for Ollama).
            timeout: Request timeout in seconds.
        """
        self._base_url = base_url
        self._model = model
        self._api_key = api_key
        self._timeout = timeout
        self._client = None

    def _get_client(self):
        """Lazily initialize the OpenAI client."""
        if self._client is None:
            try:
                from openai import OpenAI

                self._client = OpenAI(
                    base_url=self._base_url,
                    api_key=self._api_key,
                    timeout=self._timeout,
                )
            except Exception:
                self._client = None
        return self._client

    def assess(self, case: SilverCase) -> CriticResult:
        """Assess the quality of a Silver Dataset case using LLM.

        Sends the case query and expected labels to the LLM for coherence
        evaluation. If the LLM is unavailable, returns a warning result.

        Args:
            case: A validated SilverCase instance to assess.

        Returns:
            CriticResult with status, confidence, and any warnings.
        """
        client = self._get_client()
        if client is None:
            return CriticResult(
                status="warning",
                confidence=0.0,
                warnings=["LLM critic unavailable — skipping quality assessment"],
            )

        prompt = self._build_assessment_prompt(case)

        try:
            response = client.chat.completions.create(
                model=self._model,
                messages=[
                    {
                        "role": "system",
                        "content": (
                            "You are a quality assessor for a chatbot evaluation dataset. "
                            "Evaluate whether the query is coherent with its expected labels. "
                            "Respond with JSON: {\"status\": \"passed\"|\"warning\"|\"failed\", "
                            "\"confidence\": 0.0-1.0, \"warnings\": [\"...\"]}"
                        ),
                    },
                    {"role": "user", "content": prompt},
                ],
                temperature=0.1,
            )

            return self._parse_response(response)

        except Exception as e:
            return CriticResult(
                status="warning",
                confidence=0.0,
                warnings=[f"Critic assessment failed: {e}"],
            )

    def _build_assessment_prompt(self, case: SilverCase) -> str:
        """Build the assessment prompt for the LLM."""
        return (
            f"Evaluate this chatbot evaluation case:\n\n"
            f"Query: \"{case.query}\"\n"
            f"Expected route: {case.expected_route.value}\n"
            f"Expected tool: {case.expected_tool.value}\n"
            f"Expected action: {case.expected_action.value}\n"
            f"Language: {case.language}\n"
            f"Difficulty: {case.difficulty.value}\n\n"
            f"Is this query coherent with the expected labels? "
            f"Does it make sense as a natural user request that should be routed "
            f"to '{case.expected_route.value}'?"
        )

    def _parse_response(self, response) -> CriticResult:
        """Parse the LLM response into a CriticResult."""
        import json

        try:
            content = response.choices[0].message.content
            # Try to extract JSON from the response
            data = json.loads(content)
            status = data.get("status", "warning")
            if status not in ("passed", "warning", "failed"):
                status = "warning"
            confidence = float(data.get("confidence", 0.5))
            confidence = max(0.0, min(1.0, confidence))
            warnings = data.get("warnings", [])
            if not isinstance(warnings, list):
                warnings = []
            return CriticResult(
                status=status,
                confidence=confidence,
                warnings=[str(w) for w in warnings],
            )
        except (json.JSONDecodeError, KeyError, IndexError, TypeError):
            return CriticResult(
                status="warning",
                confidence=0.0,
                warnings=["Could not parse critic LLM response"],
            )
