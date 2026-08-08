"""Case catalog loader and validator for the Silver Evaluation Dataset.

Loads and validates `config/evals/silver_v1/case_catalog.json` against
the expected schema, distribution, and NO_RESULTS quota. Converts each
entry to the appropriate SeedBuildRequest type.

Requirements: 4.1, 4.8, 4.12, 4.13, 9.8
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from moviebot.evals.silver.builder import (
    BothSeedBuildRequest,
    NetflixSeedBuildRequest,
    OutOfScopeSeedBuildRequest,
    SeedBuildRequest,
    TrendingSeedBuildRequest,
)
from moviebot.evals.silver.models import (
    NetflixHardConstraints,
    TmdbHardConstraints,
)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

EXPECTED_TOTAL = 150
EXPECTED_DISTRIBUTION: dict[str, int] = {
    "trending": 50,
    "netflix": 50,
    "both": 25,
    "out_of_scope": 25,
}
NO_RESULTS_QUOTA: dict[str, int] = {
    "netflix": 7,
    "trending": 3,
    "both": 0,
}


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------


class CaseCatalogError(ValueError):
    """Raised when the case catalog fails validation."""


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def load_case_catalog(path: Path) -> list[SeedBuildRequest]:
    """Load and validate the case catalog, returning SeedBuildRequest objects.

    Args:
        path: Path to the case_catalog.json file.

    Returns:
        A list of 150 SeedBuildRequest objects ready for SeedBuilder.

    Raises:
        FileNotFoundError: If the catalog file does not exist.
        CaseCatalogError: If the catalog fails schema, distribution,
            quota, or constraint validation.
    """
    if not path.is_file():
        raise FileNotFoundError(f"Case catalog not found: {path}")

    raw = json.loads(path.read_text(encoding="utf-8"))
    _validate_top_level(raw)

    cases: list[dict[str, Any]] = raw["seeds"]

    # Validate total count
    if len(cases) != EXPECTED_TOTAL:
        raise CaseCatalogError(f"Expected {EXPECTED_TOTAL} cases, got {len(cases)}")

    # Parse each case into SeedBuildRequest
    requests: list[SeedBuildRequest] = []
    for i, case in enumerate(cases):
        try:
            request = _parse_case(case)
            requests.append(request)
        except (KeyError, TypeError, ValueError) as exc:
            case_id = case.get("case_id", f"<index {i}>")
            raise CaseCatalogError(f"Invalid case '{case_id}': {exc}") from exc

    # Validate distribution (50/50/25/25)
    _validate_distribution(requests)

    # Validate NO_RESULTS quota (7/3/0)
    _validate_no_results_quota(requests)

    return requests


# ---------------------------------------------------------------------------
# Internal validation helpers
# ---------------------------------------------------------------------------


def _validate_top_level(raw: Any) -> None:
    """Validate the top-level structure of the catalog JSON."""
    if not isinstance(raw, dict):
        raise CaseCatalogError("Case catalog must be a JSON object")
    if "version" not in raw:
        raise CaseCatalogError("Case catalog missing 'version' field")
    if "seeds" not in raw:
        raise CaseCatalogError("Case catalog missing 'seeds' field")
    if not isinstance(raw["seeds"], list):
        raise CaseCatalogError("'seeds' must be an array")


def _validate_distribution(requests: list[SeedBuildRequest]) -> None:
    """Validate the route distribution is exactly 50/50/25/25."""
    distribution: dict[str, int] = {
        "trending": 0,
        "netflix": 0,
        "both": 0,
        "out_of_scope": 0,
    }

    for req in requests:
        if isinstance(req, TrendingSeedBuildRequest):
            distribution["trending"] += 1
        elif isinstance(req, NetflixSeedBuildRequest):
            distribution["netflix"] += 1
        elif isinstance(req, BothSeedBuildRequest):
            distribution["both"] += 1
        elif isinstance(req, OutOfScopeSeedBuildRequest):
            distribution["out_of_scope"] += 1

    if distribution != EXPECTED_DISTRIBUTION:
        raise CaseCatalogError(
            f"Distribution mismatch: expected {EXPECTED_DISTRIBUTION}, "
            f"got {distribution}"
        )


def _validate_no_results_quota(requests: list[SeedBuildRequest]) -> None:
    """Validate the NO_RESULTS quota is exactly 7 netflix + 3 trending + 0 both."""
    no_results_count: dict[str, int] = {
        "netflix": 0,
        "trending": 0,
        "both": 0,
    }

    for req in requests:
        if (
            isinstance(req, NetflixSeedBuildRequest)
            and req.expected_status == "NO_RESULTS"
        ):
            no_results_count["netflix"] += 1
        elif (
            isinstance(req, TrendingSeedBuildRequest)
            and req.expected_status == "NO_RESULTS"
        ):
            no_results_count["trending"] += 1
        elif isinstance(req, BothSeedBuildRequest):
            # Both is always SUCCESS, but check defensively
            no_results_count["both"] += 0

    if no_results_count != NO_RESULTS_QUOTA:
        raise CaseCatalogError(
            f"NO_RESULTS quota mismatch: expected {NO_RESULTS_QUOTA}, "
            f"got {no_results_count}"
        )


# ---------------------------------------------------------------------------
# Case parsing — dispatch by route
# ---------------------------------------------------------------------------


def _parse_case(case: dict[str, Any]) -> SeedBuildRequest:
    """Parse a single case entry into the appropriate SeedBuildRequest type."""
    route = case["route"]
    if route == "netflix":
        return _parse_netflix_case(case)
    elif route == "trending":
        return _parse_trending_case(case)
    elif route == "both":
        return _parse_both_case(case)
    elif route == "out_of_scope":
        return _parse_out_of_scope_case(case)
    else:
        raise CaseCatalogError(f"Unknown route: '{route}'")


def _parse_netflix_case(case: dict[str, Any]) -> NetflixSeedBuildRequest:
    """Parse a netflix route case."""
    constraints = _parse_netflix_constraints(case["hard_constraints"])
    _reject_imdb_constraints(case["case_id"], constraints)

    return NetflixSeedBuildRequest(
        case_id=case["case_id"],
        expected_status=case["expected_status"],
        seed_item_ids=case.get("seed_item_ids", []),
        hard_constraints=constraints,
        semantic_concepts=case.get("semantic_concepts", []),
        difficulty=case["difficulty"],
        tags=case.get("tags", []),
    )


def _parse_trending_case(case: dict[str, Any]) -> TrendingSeedBuildRequest:
    """Parse a trending route case."""
    constraints = _parse_tmdb_constraints(case["hard_constraints"])

    return TrendingSeedBuildRequest(
        case_id=case["case_id"],
        expected_status=case["expected_status"],
        seed_item_ids=case.get("seed_item_ids", []),
        hard_constraints=constraints,
        semantic_concepts=case.get("semantic_concepts", []),
        difficulty=case["difficulty"],
        tags=case.get("tags", []),
    )


def _parse_both_case(case: dict[str, Any]) -> BothSeedBuildRequest:
    """Parse a both route case."""
    tmdb_comp = case["tmdb_component"]
    netflix_comp = case["netflix_component"]

    tmdb_constraints = _parse_tmdb_constraints(tmdb_comp["hard_constraints"])
    netflix_constraints = _parse_netflix_constraints(netflix_comp["hard_constraints"])
    _reject_imdb_constraints(case["case_id"], netflix_constraints)

    return BothSeedBuildRequest(
        case_id=case["case_id"],
        difficulty=case["difficulty"],
        tags=case.get("tags", []),
        # TMDB component
        tmdb_seed_item_ids=tmdb_comp.get("seed_item_ids", []),
        tmdb_hard_constraints=tmdb_constraints,
        tmdb_semantic_concepts=tmdb_comp.get("semantic_concepts", []),
        # Netflix component
        netflix_seed_item_ids=netflix_comp.get("seed_item_ids", []),
        netflix_hard_constraints=netflix_constraints,
        netflix_semantic_concepts=netflix_comp.get("semantic_concepts", []),
    )


def _parse_out_of_scope_case(case: dict[str, Any]) -> OutOfScopeSeedBuildRequest:
    """Parse an out_of_scope route case."""
    return OutOfScopeSeedBuildRequest(
        case_id=case["case_id"],
        difficulty=case["difficulty"],
        tags=case.get("tags", []),
    )


# ---------------------------------------------------------------------------
# Constraint parsing
# ---------------------------------------------------------------------------


def _parse_netflix_constraints(raw: dict[str, Any]) -> NetflixHardConstraints:
    """Parse raw constraint dict into NetflixHardConstraints.

    Strips `constraint_type` before construction (Pydantic handles default).
    """
    data = dict(raw)
    # Ensure constraint_type is correct if present
    ct = data.pop("constraint_type", "netflix")
    if ct != "netflix":
        raise CaseCatalogError(f"Expected constraint_type='netflix', got '{ct}'")
    return NetflixHardConstraints(**data)


def _parse_tmdb_constraints(raw: dict[str, Any]) -> TmdbHardConstraints:
    """Parse raw constraint dict into TmdbHardConstraints."""
    data = dict(raw)
    ct = data.pop("constraint_type", "tmdb")
    if ct != "tmdb":
        raise CaseCatalogError(f"Expected constraint_type='tmdb', got '{ct}'")
    return TmdbHardConstraints(**data)


def _reject_imdb_constraints(case_id: str, constraints: NetflixHardConstraints) -> None:
    """Reject seeds that use non-default min_imdb_score or max_imdb_score.

    Silver v1 does not support IMDb score filtering. The fields exist in
    NetflixHardConstraints for future use but must not appear in the catalog.

    Requirement 9.8: Reject any seed with non-default IMDb constraints.
    """
    if constraints.min_imdb_score is not None:
        raise CaseCatalogError(
            f"Case '{case_id}': min_imdb_score={constraints.min_imdb_score} "
            f"is not allowed in Silver v1. IMDb score filtering is not "
            f"supported in this version."
        )
    if constraints.max_imdb_score is not None:
        raise CaseCatalogError(
            f"Case '{case_id}': max_imdb_score={constraints.max_imdb_score} "
            f"is not allowed in Silver v1. IMDb score filtering is not "
            f"supported in this version."
        )
