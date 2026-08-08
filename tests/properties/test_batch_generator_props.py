"""Property tests for BatchGenerator invariants (Properties 14, 15, 16).

Tests the batch generation constraints at the catalog validation level,
verifying that:
- IMDb constraints are rejected (Property 14)
- Valid catalogs have correct uniqueness and distribution (Property 15)
- Valid catalogs have correct NO_RESULTS quota (Property 16)

**Validates: Requirements 4.1, 4.4, 4.8, 4.13, 9.8**
"""

from __future__ import annotations

import json
import re
import tempfile
from pathlib import Path
from typing import Any

import pytest
from hypothesis import assume, given, settings
from hypothesis import strategies as st

from moviebot.evals.silver.case_catalog import (
    EXPECTED_DISTRIBUTION,
    EXPECTED_TOTAL,
    NO_RESULTS_QUOTA,
    CaseCatalogError,
    load_case_catalog,
)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_CASE_ID_PATTERN = re.compile(r"^[a-zA-Z0-9_-]+$")
_MAX_CASE_ID_LEN = 64

# Valid genres pool (lowercase as required by schema)
_GENRE_POOL = [
    "action",
    "comedy",
    "drama",
    "horror",
    "romance",
    "thriller",
    "documentary",
    "animation",
    "science fiction",
    "fantasy",
]

# Valid difficulty levels
_DIFFICULTIES = ["easy", "medium", "hard"]


# ---------------------------------------------------------------------------
# Strategies — Building blocks for case catalog generation
# ---------------------------------------------------------------------------


@st.composite
def case_id_strategy(draw: st.DrawFn) -> str:
    """Generate a valid case_id matching ^[a-zA-Z0-9_-]+$ with length <= 64."""
    return draw(st.from_regex(r"[a-zA-Z0-9_-]{3,30}", fullmatch=True))


@st.composite
def netflix_hard_constraints_without_imdb(draw: st.DrawFn) -> dict[str, Any]:
    """Generate Netflix hard_constraints WITHOUT IMDb fields (valid for Silver v1)."""
    title_type = draw(st.sampled_from([None, "movie", "show"]))
    genres = draw(
        st.lists(st.sampled_from(_GENRE_POOL), min_size=0, max_size=3, unique=True)
    )

    use_year_range = draw(st.booleans())
    min_year = None
    max_year = None
    if use_year_range:
        min_year = draw(st.integers(min_value=1900, max_value=2020))
        max_year = draw(st.integers(min_value=min_year, max_value=2024))

    result: dict[str, Any] = {"constraint_type": "netflix"}
    if title_type is not None:
        result["type"] = title_type
    if genres:
        result["genres"] = genres
    if min_year is not None:
        result["min_year"] = min_year
    if max_year is not None:
        result["max_year"] = max_year

    return result


@st.composite
def netflix_hard_constraints_with_imdb(draw: st.DrawFn) -> dict[str, Any]:
    """Generate Netflix hard_constraints WITH non-default IMDb fields (invalid for Silver v1)."""
    base = draw(netflix_hard_constraints_without_imdb())

    # At least one IMDb field must be non-None
    use_min = draw(st.booleans())
    use_max = draw(st.booleans())
    assume(use_min or use_max)

    if use_min:
        base["min_imdb_score"] = draw(
            st.floats(min_value=0.0, max_value=10.0, allow_nan=False)
        )
    if use_max:
        max_val = draw(st.floats(min_value=0.0, max_value=10.0, allow_nan=False))
        # Ensure min <= max if both present
        if "min_imdb_score" in base:
            max_val = max(max_val, base["min_imdb_score"])
        base["max_imdb_score"] = max_val

    return base


@st.composite
def tmdb_hard_constraints(draw: st.DrawFn) -> dict[str, Any]:
    """Generate valid TMDB hard_constraints."""
    genre_ids = draw(
        st.lists(
            st.integers(min_value=1, max_value=99999),
            min_size=0,
            max_size=3,
            unique=True,
        )
    )

    use_year_range = draw(st.booleans())
    min_year = None
    max_year = None
    if use_year_range:
        min_year = draw(st.integers(min_value=1900, max_value=2020))
        max_year = draw(st.integers(min_value=min_year, max_value=2024))

    use_vote = draw(st.booleans())
    min_vote = None
    max_vote = None
    if use_vote:
        min_vote = draw(st.floats(min_value=0.0, max_value=9.0, allow_nan=False))
        max_vote = draw(st.floats(min_value=min_vote, max_value=10.0, allow_nan=False))

    result: dict[str, Any] = {"constraint_type": "tmdb"}
    if genre_ids:
        result["genre_ids"] = genre_ids
    if min_year is not None:
        result["min_year"] = min_year
    if max_year is not None:
        result["max_year"] = max_year
    if min_vote is not None:
        result["min_vote_average"] = min_vote
    if max_vote is not None:
        result["max_vote_average"] = max_vote

    return result


@st.composite
def netflix_case(
    draw: st.DrawFn,
    *,
    prefix: str,
    index: int,
    expected_status: str = "SUCCESS",
) -> dict[str, Any]:
    """Generate a valid Netflix route case entry."""
    case_id = f"{prefix}_netflix_{index:03d}"
    difficulty = draw(st.sampled_from(_DIFFICULTIES))
    constraints = draw(netflix_hard_constraints_without_imdb())

    # Ensure at least one non-default constraint for SUCCESS cases
    if expected_status == "SUCCESS" and all(
        k == "constraint_type" for k in constraints
    ):
        constraints["genres"] = ["drama"]

    case: dict[str, Any] = {
        "case_id": case_id,
        "route": "netflix",
        "expected_status": expected_status,
        "hard_constraints": constraints,
        "difficulty": difficulty,
        "tags": [],
    }

    if expected_status == "SUCCESS":
        case["seed_item_ids"] = [f"tm{1000 + index}"]
        case["semantic_concepts"] = []
    else:
        case["seed_item_ids"] = []
        case["semantic_concepts"] = []

    return case


@st.composite
def trending_case(
    draw: st.DrawFn,
    *,
    prefix: str,
    index: int,
    expected_status: str = "SUCCESS",
) -> dict[str, Any]:
    """Generate a valid Trending route case entry."""
    case_id = f"{prefix}_trending_{index:03d}"
    difficulty = draw(st.sampled_from(_DIFFICULTIES))
    constraints = draw(tmdb_hard_constraints())

    # Ensure at least one non-default constraint for SUCCESS cases
    if expected_status == "SUCCESS" and all(
        k == "constraint_type" for k in constraints
    ):
        constraints["genre_ids"] = [28]

    case: dict[str, Any] = {
        "case_id": case_id,
        "route": "trending",
        "expected_status": expected_status,
        "hard_constraints": constraints,
        "difficulty": difficulty,
        "tags": [],
    }

    if expected_status == "SUCCESS":
        case["seed_item_ids"] = [f"tmdb:{5000 + index}"]
        case["semantic_concepts"] = []
    else:
        case["seed_item_ids"] = []
        case["semantic_concepts"] = []

    return case


@st.composite
def both_case(draw: st.DrawFn, *, prefix: str, index: int) -> dict[str, Any]:
    """Generate a valid Both route case entry (always SUCCESS)."""
    case_id = f"{prefix}_both_{index:03d}"
    difficulty = draw(st.sampled_from(_DIFFICULTIES))

    tmdb_constraints = draw(tmdb_hard_constraints())
    netflix_constraints = draw(netflix_hard_constraints_without_imdb())

    # Ensure non-default constraints for SUCCESS
    if all(k == "constraint_type" for k in tmdb_constraints):
        tmdb_constraints["genre_ids"] = [28]
    if all(k == "constraint_type" for k in netflix_constraints):
        netflix_constraints["genres"] = ["drama"]

    return {
        "case_id": case_id,
        "route": "both",
        "difficulty": difficulty,
        "tags": [],
        "tmdb_component": {
            "seed_item_ids": [f"tmdb:{8000 + index}"],
            "hard_constraints": tmdb_constraints,
            "semantic_concepts": [],
        },
        "netflix_component": {
            "seed_item_ids": [f"tm{9000 + index}"],
            "hard_constraints": netflix_constraints,
            "semantic_concepts": [],
        },
    }


@st.composite
def out_of_scope_case(draw: st.DrawFn, *, prefix: str, index: int) -> dict[str, Any]:
    """Generate a valid out_of_scope route case entry."""
    case_id = f"{prefix}_oos_{index:03d}"
    difficulty = draw(st.sampled_from(_DIFFICULTIES))

    return {
        "case_id": case_id,
        "route": "out_of_scope",
        "difficulty": difficulty,
        "tags": [],
    }


@st.composite
def valid_case_catalog_json(draw: st.DrawFn) -> dict[str, Any]:
    """Generate a complete valid case catalog with 150 seeds, correct distribution and quota.

    Distribution: 50 trending, 50 netflix, 25 both, 25 out_of_scope
    NO_RESULTS quota: 7 netflix + 3 trending + 0 both
    """
    prefix = draw(st.from_regex(r"[a-z]{2,5}", fullmatch=True))
    seeds: list[dict[str, Any]] = []

    # --- Netflix seeds: 50 total (43 SUCCESS + 7 NO_RESULTS) ---
    for i in range(43):
        case = draw(netflix_case(prefix=prefix, index=i, expected_status="SUCCESS"))
        seeds.append(case)
    for i in range(43, 50):
        case = draw(netflix_case(prefix=prefix, index=i, expected_status="NO_RESULTS"))
        seeds.append(case)

    # --- Trending seeds: 50 total (47 SUCCESS + 3 NO_RESULTS) ---
    for i in range(47):
        case = draw(trending_case(prefix=prefix, index=i, expected_status="SUCCESS"))
        seeds.append(case)
    for i in range(47, 50):
        case = draw(trending_case(prefix=prefix, index=i, expected_status="NO_RESULTS"))
        seeds.append(case)

    # --- Both seeds: 25 total (all SUCCESS) ---
    for i in range(25):
        case = draw(both_case(prefix=prefix, index=i))
        seeds.append(case)

    # --- Out-of-scope seeds: 25 total ---
    for i in range(25):
        case = draw(out_of_scope_case(prefix=prefix, index=i))
        seeds.append(case)

    return {"version": "1.0.0", "seeds": seeds}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _write_catalog(catalog: dict[str, Any], tmp_dir: Path) -> Path:
    """Write a catalog dict as JSON and return the path."""
    path = tmp_dir / "case_catalog.json"
    path.write_text(
        json.dumps(catalog, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return path


# ---------------------------------------------------------------------------
# Property 14: Rechazo de seeds con IMDb constraints en Silver v1
# ---------------------------------------------------------------------------


@given(
    imdb_constraints=netflix_hard_constraints_with_imdb(),
    route=st.sampled_from(["netflix", "both"]),
)
@settings(max_examples=50, deadline=None)
def test_property_14_imdb_constraints_rejected(
    imdb_constraints: dict[str, Any],
    route: str,
) -> None:
    """Property 14: Rechazo de seeds con IMDb constraints.

    **Validates: Requirements 9.8**

    For any seed definition in the case_catalog whose hard_constraints contains
    min_imdb_score or max_imdb_score with a non-default (non-None) value,
    the catalog loader SHALL reject with CaseCatalogError.
    """
    # Build a minimal catalog with the offending seed
    if route == "netflix":
        bad_seed: dict[str, Any] = {
            "case_id": "test-imdb-reject-001",
            "route": "netflix",
            "expected_status": "SUCCESS",
            "hard_constraints": imdb_constraints,
            "seed_item_ids": ["tm1001"],
            "semantic_concepts": [],
            "difficulty": "easy",
            "tags": [],
        }
    else:
        # For 'both' route, put the IMDb constraints in the netflix_component
        bad_seed = {
            "case_id": "test-imdb-reject-001",
            "route": "both",
            "difficulty": "easy",
            "tags": [],
            "tmdb_component": {
                "seed_item_ids": ["tmdb:5001"],
                "hard_constraints": {"constraint_type": "tmdb", "genre_ids": [28]},
                "semantic_concepts": [],
            },
            "netflix_component": {
                "seed_item_ids": ["tm9001"],
                "hard_constraints": imdb_constraints,
                "semantic_concepts": [],
            },
        }

    # Create a catalog with just one seed (will also fail on count,
    # but we test that IMDb rejection happens first via parsing)
    # Use 150 seeds to avoid the count check interfering
    catalog = _build_catalog_with_bad_imdb_seed(bad_seed)

    with tempfile.TemporaryDirectory() as tmp_dir:
        path = _write_catalog(catalog, Path(tmp_dir))

        with pytest.raises(CaseCatalogError) as exc_info:
            load_case_catalog(path)

        error_msg = str(exc_info.value).lower()
        assert "imdb" in error_msg or "imdb_score" in error_msg, (
            f"Expected IMDb rejection error, got: {exc_info.value}"
        )


def _build_catalog_with_bad_imdb_seed(bad_seed: dict[str, Any]) -> dict[str, Any]:
    """Build a 150-seed catalog where the first seed has bad IMDb constraints.

    The remaining 149 seeds are valid fillers with correct distribution.
    The bad seed replaces the first seed of its route type.
    """
    route = bad_seed["route"]
    seeds: list[dict[str, Any]] = [bad_seed]

    # Fill the rest to reach 150 with correct distribution
    if route == "netflix":
        # Need 49 more netflix (42 SUCCESS + 7 NO_RESULTS, since bad one is SUCCESS)
        for i in range(1, 43):
            seeds.append(_make_netflix_seed(f"fill_nf_{i:03d}", "SUCCESS"))
        for i in range(43, 50):
            seeds.append(_make_netflix_seed(f"fill_nf_{i:03d}", "NO_RESULTS"))
    elif route == "both":
        # Need 50 netflix seeds
        for i in range(43):
            seeds.append(_make_netflix_seed(f"fill_nf_{i:03d}", "SUCCESS"))
        for i in range(43, 50):
            seeds.append(_make_netflix_seed(f"fill_nf_{i:03d}", "NO_RESULTS"))
        # Need 24 more both seeds
        for i in range(1, 25):
            seeds.append(_make_both_seed(f"fill_both_{i:03d}"))
    else:
        # Shouldn't happen but cover it
        for i in range(43):
            seeds.append(_make_netflix_seed(f"fill_nf_{i:03d}", "SUCCESS"))
        for i in range(43, 50):
            seeds.append(_make_netflix_seed(f"fill_nf_{i:03d}", "NO_RESULTS"))

    # Add trending seeds (50 total: 47 SUCCESS + 3 NO_RESULTS)
    for i in range(47):
        seeds.append(_make_trending_seed(f"fill_tr_{i:03d}", "SUCCESS"))
    for i in range(47, 50):
        seeds.append(_make_trending_seed(f"fill_tr_{i:03d}", "NO_RESULTS"))

    # Add both seeds if not already filled
    if route != "both":
        for i in range(25):
            seeds.append(_make_both_seed(f"fill_both_{i:03d}"))

    # Add out_of_scope seeds
    for i in range(25):
        seeds.append(_make_oos_seed(f"fill_oos_{i:03d}"))

    # Trim to exactly 150
    seeds = seeds[:150]

    return {"version": "1.0.0", "seeds": seeds}


def _make_netflix_seed(case_id: str, status: str) -> dict[str, Any]:
    """Create a minimal valid netflix seed."""
    seed: dict[str, Any] = {
        "case_id": case_id,
        "route": "netflix",
        "expected_status": status,
        "hard_constraints": {"constraint_type": "netflix", "genres": ["drama"]},
        "difficulty": "easy",
        "tags": [],
    }
    if status == "SUCCESS":
        seed["seed_item_ids"] = ["tm1001"]
        seed["semantic_concepts"] = []
    else:
        seed["seed_item_ids"] = []
        seed["semantic_concepts"] = []
    return seed


def _make_trending_seed(case_id: str, status: str) -> dict[str, Any]:
    """Create a minimal valid trending seed."""
    seed: dict[str, Any] = {
        "case_id": case_id,
        "route": "trending",
        "expected_status": status,
        "hard_constraints": {"constraint_type": "tmdb", "genre_ids": [28]},
        "difficulty": "easy",
        "tags": [],
    }
    if status == "SUCCESS":
        seed["seed_item_ids"] = ["tmdb:5001"]
        seed["semantic_concepts"] = []
    else:
        seed["seed_item_ids"] = []
        seed["semantic_concepts"] = []
    return seed


def _make_both_seed(case_id: str) -> dict[str, Any]:
    """Create a minimal valid both seed."""
    return {
        "case_id": case_id,
        "route": "both",
        "difficulty": "easy",
        "tags": [],
        "tmdb_component": {
            "seed_item_ids": ["tmdb:8001"],
            "hard_constraints": {"constraint_type": "tmdb", "genre_ids": [28]},
            "semantic_concepts": [],
        },
        "netflix_component": {
            "seed_item_ids": ["tm9001"],
            "hard_constraints": {"constraint_type": "netflix", "genres": ["drama"]},
            "semantic_concepts": [],
        },
    }


def _make_oos_seed(case_id: str) -> dict[str, Any]:
    """Create a minimal valid out_of_scope seed."""
    return {
        "case_id": case_id,
        "route": "out_of_scope",
        "difficulty": "easy",
        "tags": [],
    }


# ---------------------------------------------------------------------------
# Property 15: Uniqueness e invariantes del batch
# ---------------------------------------------------------------------------


@given(catalog=valid_case_catalog_json())
@settings(max_examples=20, deadline=None)
def test_property_15_valid_catalog_has_150_unique_case_ids_correct_distribution(
    catalog: dict[str, Any],
) -> None:
    """Property 15: Uniqueness e invariantes del batch.

    **Validates: Requirements 4.4, 4.1, 4.8**

    For any valid catalog loaded by load_case_catalog:
    - It contains exactly 150 seeds
    - All case_ids are unique
    - All case_ids match ^[a-zA-Z0-9_-]+$ with length <= 64
    - Distribution is exactly 50/50/25/25
    """
    with tempfile.TemporaryDirectory() as tmp_dir:
        path = _write_catalog(catalog, Path(tmp_dir))
        requests = load_case_catalog(path)

    # Exactly 150 seeds
    assert len(requests) == EXPECTED_TOTAL, (
        f"Expected {EXPECTED_TOTAL} requests, got {len(requests)}"
    )

    # All case_ids unique
    case_ids = [req.case_id for req in requests]
    assert len(case_ids) == len(set(case_ids)), (
        f"Duplicate case_ids found: {[cid for cid in case_ids if case_ids.count(cid) > 1]}"
    )

    # All case_ids match pattern and length
    for case_id in case_ids:
        assert len(case_id) <= _MAX_CASE_ID_LEN, (
            f"case_id '{case_id}' exceeds max length {_MAX_CASE_ID_LEN}"
        )
        assert _CASE_ID_PATTERN.match(case_id), (
            f"case_id '{case_id}' does not match pattern ^[a-zA-Z0-9_-]+$"
        )

    # Distribution 50/50/25/25
    from moviebot.evals.silver.builder import (
        BothSeedBuildRequest,
        NetflixSeedBuildRequest,
        OutOfScopeSeedBuildRequest,
        TrendingSeedBuildRequest,
    )

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

    assert distribution == EXPECTED_DISTRIBUTION, (
        f"Distribution mismatch: expected {EXPECTED_DISTRIBUTION}, got {distribution}"
    )


@given(catalog=valid_case_catalog_json())
@settings(max_examples=20, deadline=None)
def test_property_15_case_id_pattern_invariant(
    catalog: dict[str, Any],
) -> None:
    """Property 15 (supplement): All parsed case_ids conform to naming rules.

    **Validates: Requirements 4.4**

    Verifies the regex pattern and length constraints hold for all case_ids
    in any valid catalog.
    """
    with tempfile.TemporaryDirectory() as tmp_dir:
        path = _write_catalog(catalog, Path(tmp_dir))
        requests = load_case_catalog(path)

    for req in requests:
        assert _CASE_ID_PATTERN.match(req.case_id), (
            f"case_id '{req.case_id}' violates pattern"
        )
        assert len(req.case_id) <= _MAX_CASE_ID_LEN, (
            f"case_id '{req.case_id}' too long ({len(req.case_id)} > {_MAX_CASE_ID_LEN})"
        )


# ---------------------------------------------------------------------------
# Property 16: NO_RESULTS quota
# ---------------------------------------------------------------------------


@given(catalog=valid_case_catalog_json())
@settings(max_examples=20, deadline=None)
def test_property_16_no_results_quota_enforced(
    catalog: dict[str, Any],
) -> None:
    """Property 16: NO_RESULTS quota.

    **Validates: Requirements 4.13**

    For any valid catalog loaded by load_case_catalog:
    - Exactly 7 netflix seeds have expected_status='NO_RESULTS'
    - Exactly 3 trending seeds have expected_status='NO_RESULTS'
    - Exactly 0 both seeds have expected_status='NO_RESULTS'
    """
    from moviebot.evals.silver.builder import (
        BothSeedBuildRequest,
        NetflixSeedBuildRequest,
        TrendingSeedBuildRequest,
    )

    with tempfile.TemporaryDirectory() as tmp_dir:
        path = _write_catalog(catalog, Path(tmp_dir))
        requests = load_case_catalog(path)

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
            # Both is always SUCCESS by design; count defensively
            pass

    assert no_results_count == NO_RESULTS_QUOTA, (
        f"NO_RESULTS quota mismatch: expected {NO_RESULTS_QUOTA}, got {no_results_count}"
    )


@given(
    netflix_no_results=st.integers(min_value=0, max_value=50),
    trending_no_results=st.integers(min_value=0, max_value=50),
)
@settings(max_examples=30, deadline=None)
def test_property_16_wrong_quota_rejected(
    netflix_no_results: int,
    trending_no_results: int,
) -> None:
    """Property 16 (supplement): Wrong NO_RESULTS quota is rejected.

    **Validates: Requirements 4.13**

    Any catalog with a NO_RESULTS quota different from 7/3/0 SHALL be
    rejected by load_case_catalog.
    """
    # Skip the correct quota — that passes validation
    assume(
        netflix_no_results != NO_RESULTS_QUOTA["netflix"]
        or trending_no_results != NO_RESULTS_QUOTA["trending"]
    )

    # Ensure we don't exceed route totals
    assume(netflix_no_results <= 50)
    assume(trending_no_results <= 50)

    seeds: list[dict[str, Any]] = []

    # Netflix: some SUCCESS, some NO_RESULTS
    netflix_success = 50 - netflix_no_results
    for i in range(netflix_success):
        seeds.append(_make_netflix_seed(f"nf_s_{i:03d}", "SUCCESS"))
    for i in range(netflix_no_results):
        seeds.append(_make_netflix_seed(f"nf_nr_{i:03d}", "NO_RESULTS"))

    # Trending: some SUCCESS, some NO_RESULTS
    trending_success = 50 - trending_no_results
    for i in range(trending_success):
        seeds.append(_make_trending_seed(f"tr_s_{i:03d}", "SUCCESS"))
    for i in range(trending_no_results):
        seeds.append(_make_trending_seed(f"tr_nr_{i:03d}", "NO_RESULTS"))

    # Both: 25 (always SUCCESS)
    for i in range(25):
        seeds.append(_make_both_seed(f"both_{i:03d}"))

    # Out of scope: 25
    for i in range(25):
        seeds.append(_make_oos_seed(f"oos_{i:03d}"))

    catalog = {"version": "1.0.0", "seeds": seeds}

    with tempfile.TemporaryDirectory() as tmp_dir:
        path = _write_catalog(catalog, Path(tmp_dir))

        with pytest.raises(CaseCatalogError) as exc_info:
            load_case_catalog(path)

        error_msg = str(exc_info.value).lower()
        assert "no_results" in error_msg or "quota" in error_msg, (
            f"Expected NO_RESULTS quota error, got: {exc_info.value}"
        )
