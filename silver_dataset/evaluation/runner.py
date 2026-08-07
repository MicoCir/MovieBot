"""Baseline execution engine for the Silver Dataset.

Provides ``BaselineRunner`` that executes a chatbot function against the dev split,
records per-case ``RunTrace`` instances, detects infrastructure errors, and produces
a ``RunResult`` summary (Tasks 12.1–12.3, Requirement 10.1, 10.6).
"""

import time
import uuid
from typing import Callable

from pydantic import BaseModel

from silver_dataset.io.loader import SilverDatasetLoader
from silver_dataset.models.case import SilverCase, Split


class RunTrace(BaseModel):
    """Single execution trace for one case.

    Attributes:
        run_id: Unique identifier for the entire run.
        case_id: The case being evaluated.
        dataset_version: Version of the dataset used.
        code_version: Version of the chatbot code being tested.
        attempt: Attempt number (1-based).
        prediction: The chatbot's response as a dict.
        error: Error message if the case failed, None otherwise.
        is_infra_error: True if the error is infrastructure-related (not functional).
        duration_ms: Execution time in milliseconds.
    """

    run_id: str
    case_id: str
    dataset_version: str
    code_version: str
    attempt: int
    prediction: dict
    error: str | None = None
    is_infra_error: bool = False
    duration_ms: float


class RunResult(BaseModel):
    """Complete result of a baseline run.

    Attributes:
        run_id: Unique identifier for this run.
        dataset_version: Version of the dataset used.
        traces: All per-case execution traces.
        total_cases: Total number of cases attempted.
        successful: Number of cases that completed without error.
        failed: Number of cases that failed (functional errors).
        infra_errors: Number of cases that failed due to infrastructure issues.
    """

    run_id: str
    dataset_version: str
    traces: list[RunTrace]
    total_cases: int
    successful: int
    failed: int
    infra_errors: int


# Infrastructure error indicators — connection/timeout related exceptions
_INFRA_ERROR_TYPES = (
    "ConnectionError",
    "TimeoutError",
    "ConnectionRefusedError",
    "ConnectionResetError",
    "OSError",
    "BrokenPipeError",
    "ConnectionAbortedError",
    "httpx.ConnectError",
    "httpx.TimeoutException",
    "httpx.ReadTimeout",
    "httpx.ConnectTimeout",
    "requests.ConnectionError",
    "requests.Timeout",
    "urllib3.exceptions.MaxRetryError",
    "socket.timeout",
)

# Substrings in error messages that indicate infra issues
_INFRA_ERROR_KEYWORDS = (
    "connection refused",
    "connection reset",
    "timed out",
    "timeout",
    "connect error",
    "name resolution",
    "dns",
    "network unreachable",
    "no route to host",
    "broken pipe",
    "connection aborted",
)


def _is_infra_error(exception: BaseException) -> bool:
    """Determine if an exception is an infrastructure error.

    Infrastructure errors are connection/timeout/network failures that
    are not the chatbot's functional fault. They should be segregated
    from functional failures in the scorecard.

    Args:
        exception: The caught exception.

    Returns:
        True if the exception represents an infrastructure issue.
    """
    # Check exception type name against known infra types
    exc_type_name = type(exception).__name__
    exc_full_name = f"{type(exception).__module__}.{exc_type_name}"

    if exc_type_name in _INFRA_ERROR_TYPES or exc_full_name in _INFRA_ERROR_TYPES:
        return True

    # Check error message for infra keywords
    error_msg = str(exception).lower()
    return any(keyword in error_msg for keyword in _INFRA_ERROR_KEYWORDS)


class BaselineRunner:
    """Executes chatbot against dev split and records traces.

    The runner wraps each chatbot call in error detection logic that
    categorizes failures as either functional (chatbot bugs) or
    infrastructure (network/timeout issues).

    Args:
        chatbot_fn: Callable that takes a SilverCase and returns a prediction dict.
                    Expected signature: ``(case: SilverCase) -> dict``
        dataset_loader: SilverDatasetLoader instance configured for loading cases.
    """

    def __init__(
        self,
        chatbot_fn: Callable[[SilverCase], dict],
        dataset_loader: SilverDatasetLoader,
    ) -> None:
        self._chatbot_fn = chatbot_fn
        self._loader = dataset_loader

    def run(
        self,
        run_id: str,
        version: str,
        code_version: str = "dev",
    ) -> RunResult:
        """Execute the chatbot against all cases in the dev split.

        Loads cases from the dataset using the loader, executes the chatbot
        function against each case, and records traces with timing and error
        information.

        Args:
            run_id: Unique identifier for this run.
            version: Dataset version to load.
            code_version: Version of the chatbot code being tested.

        Returns:
            RunResult with all traces and summary statistics.
        """
        cases = self._loader.load(version=version, split=Split.dev)
        traces: list[RunTrace] = []

        for case in cases:
            trace = self._execute_case(
                case=case,
                run_id=run_id,
                dataset_version=version,
                code_version=code_version,
            )
            traces.append(trace)

        # Compute summary statistics
        successful = sum(1 for t in traces if t.error is None)
        infra_errors = sum(1 for t in traces if t.is_infra_error)
        failed = sum(1 for t in traces if t.error is not None and not t.is_infra_error)

        return RunResult(
            run_id=run_id,
            dataset_version=version,
            traces=traces,
            total_cases=len(traces),
            successful=successful,
            failed=failed,
            infra_errors=infra_errors,
        )

    def _execute_case(
        self,
        case: SilverCase,
        run_id: str,
        dataset_version: str,
        code_version: str,
        attempt: int = 1,
    ) -> RunTrace:
        """Execute the chatbot against a single case with error detection.

        Wraps the chatbot call in try/except to categorize errors as
        infrastructure vs functional failures.

        Args:
            case: The SilverCase to evaluate.
            run_id: Run identifier.
            dataset_version: Dataset version string.
            code_version: Code version string.
            attempt: Attempt number (1-based).

        Returns:
            RunTrace with prediction or error information.
        """
        start_time = time.perf_counter()

        try:
            prediction = self._chatbot_fn(case)
            duration_ms = (time.perf_counter() - start_time) * 1000.0

            return RunTrace(
                run_id=run_id,
                case_id=case.case_id,
                dataset_version=dataset_version,
                code_version=code_version,
                attempt=attempt,
                prediction=prediction,
                error=None,
                is_infra_error=False,
                duration_ms=duration_ms,
            )

        except Exception as exc:
            duration_ms = (time.perf_counter() - start_time) * 1000.0
            infra = _is_infra_error(exc)

            return RunTrace(
                run_id=run_id,
                case_id=case.case_id,
                dataset_version=dataset_version,
                code_version=code_version,
                attempt=attempt,
                prediction={},
                error=f"{type(exc).__name__}: {exc}",
                is_infra_error=infra,
                duration_ms=duration_ms,
            )
