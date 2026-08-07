"""Filtered loading API for the Silver Dataset.

Provides ``SilverDatasetLoader`` for programmatic access to Silver Dataset
cases with combined filter support, checksum validation, and holdout access
control (Tasks 7.1–7.6, Requirements 8.1–8.6).
"""

import hashlib
import json
from pathlib import Path
from typing import Literal

from silver_dataset.io.jsonl import read_jsonl
from silver_dataset.models.case import ExpectedRoute, SilverCase, Split, Suite


class LoaderError(Exception):
    """Raised when dataset integrity validation fails.

    Covers two cases:
    - Unknown version: no JSONL file found for the requested version.
    - Checksum mismatch: loaded file content does not match stored checksum.
    """


def _compute_checksum(cases: list[SilverCase]) -> str:
    """Compute SHA-256 checksum over sorted canonical JSON lines.

    Produces a deterministic digest that is stable for identical content and
    changes when any case is added, removed, or modified.

    Args:
        cases: List of ``SilverCase`` instances.

    Returns:
        Hex-encoded SHA-256 digest string.
    """
    lines = sorted(case.model_dump_json() for case in cases)
    payload = "\n".join(lines).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


class SilverDatasetLoader:
    """Programmatic access to filtered Silver Dataset cases.

    Reads cases from JSONL files in ``dataset_dir``, validates checksums when
    available, enforces holdout access control in development mode, and returns
    a stable-ordered, filtered list of ``SilverCase`` instances.

    File naming conventions (searched in order):
    - If ``version`` is given: ``silver_{version}.jsonl``
    - If no version is given: ``silver.jsonl`` (unversioned default)

    Checksum files follow the same naming pattern with ``.checksum`` extension:
    ``silver_{version}.checksum`` or ``silver.checksum``.

    Args:
        dataset_dir: Directory containing JSONL and checksum files.
        mode: ``"development"`` blocks holdout access; ``"evaluation"`` allows it.
    """

    def __init__(
        self,
        dataset_dir: Path,
        mode: Literal["development", "evaluation"] = "development",
    ) -> None:
        self._dataset_dir = Path(dataset_dir)
        self._mode = mode

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def load(
        self,
        version: str | None = None,
        suite: Suite | None = None,
        split: Split | None = None,
        route: ExpectedRoute | None = None,
        tags: list[str] | None = None,
    ) -> list[SilverCase]:
        """Load cases with combined filters.

        All filters are combinable with AND semantics.  For the ``tags``
        filter a case must carry ALL specified tags to be included.

        Steps performed:
        1. Resolve JSONL file path for the requested version (raises
           ``LoaderError`` if not found).
        2. Holdout access control: raise ``PermissionError`` when
           ``split=Split.holdout`` is requested in development mode.
        3. Read and parse the JSONL file (parse errors are silently
           discarded — only valid cases are considered).
        4. Validate checksum if a ``.checksum`` file exists (raises
           ``LoaderError`` on mismatch).
        5. Apply filters.
        6. Sort by ``case_id`` for stable ordering.
        7. Return filtered list (may be empty — no exception is raised).

        Args:
            version: Dataset version identifier (e.g. ``"silver_v1"``).
                     When ``None`` the unversioned ``silver.jsonl`` is used.
            suite: Restrict to a specific ``Suite``.
            split: Restrict to a specific ``Split``.
            route: Restrict to a specific ``ExpectedRoute``.
            tags: Restrict to cases that carry ALL listed tags.

        Returns:
            Filtered, stable-ordered list of ``SilverCase`` instances.

        Raises:
            PermissionError: When ``split=Split.holdout`` is requested in
                development mode.
            LoaderError: When the version/JSONL file is not found, or when
                the checksum does not match.
        """
        # Step 1 — resolve file paths
        jsonl_path, checksum_path = self._resolve_paths(version)

        # Step 2 — holdout access control (check before any I/O)
        if split is Split.holdout and self._mode == "development":
            raise PermissionError(
                "Access to the holdout split is not allowed in development mode. "
                "Instantiate SilverDatasetLoader with mode='evaluation' to enable it."
            )

        # Step 3 — read cases (discard parse errors)
        cases, _errors = read_jsonl(jsonl_path)

        # Step 4 — checksum validation
        if checksum_path.exists():
            expected_checksum = checksum_path.read_text(encoding="utf-8").strip()
            actual_checksum = _compute_checksum(cases)
            if actual_checksum != expected_checksum:
                raise LoaderError(
                    f"Checksum mismatch for '{jsonl_path.name}'. "
                    f"Expected {expected_checksum!r}, got {actual_checksum!r}. "
                    "The dataset file may have been modified after it was versioned."
                )

        # Step 5 — apply filters
        filtered = self._apply_filters(cases, suite=suite, split=split, route=route, tags=tags)

        # Step 6 — stable ordering by case_id
        filtered.sort(key=lambda c: c.case_id)

        # Step 7 — return (may be empty)
        return filtered

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _resolve_paths(self, version: str | None) -> tuple[Path, Path]:
        """Resolve JSONL and checksum file paths for the given version.

        Args:
            version: Version string or ``None`` for the unversioned file.

        Returns:
            Tuple of ``(jsonl_path, checksum_path)``.

        Raises:
            LoaderError: When the JSONL file does not exist.
        """
        if version is not None:
            stem = f"silver_{version}"
        else:
            stem = "silver"

        jsonl_path = self._dataset_dir / f"{stem}.jsonl"
        checksum_path = self._dataset_dir / f"{stem}.checksum"

        if not jsonl_path.exists():
            raise LoaderError(
                f"Unknown dataset version: no JSONL file found at '{jsonl_path}'. "
                f"Make sure the dataset has been generated for version {version!r}."
            )

        return jsonl_path, checksum_path

    @staticmethod
    def _apply_filters(
        cases: list[SilverCase],
        suite: Suite | None,
        split: Split | None,
        route: ExpectedRoute | None,
        tags: list[str] | None,
    ) -> list[SilverCase]:
        """Apply all active filters to a list of cases.

        Filters are combined with AND semantics.  ``None`` means "no filter"
        for that dimension.  The ``tags`` filter requires a case to have ALL
        listed tags (AND semantics within the tags list as well).

        Args:
            cases: Full list of cases loaded from the JSONL file.
            suite: Optional suite filter.
            split: Optional split filter.
            route: Optional route filter.
            tags: Optional list of tags (all must be present).

        Returns:
            Filtered list of cases.
        """
        result: list[SilverCase] = []
        for case in cases:
            if suite is not None and case.suite != suite:
                continue
            if split is not None and case.split != split:
                continue
            if route is not None and case.expected_route != route:
                continue
            if tags is not None:
                if not all(tag in case.tags for tag in tags):
                    continue
            result.append(case)
        return result
