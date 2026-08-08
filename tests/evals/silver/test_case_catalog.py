"""Unit tests for case_catalog loader and validator."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from moviebot.evals.silver.builder import (
    BothSeedBuildRequest,
    NetflixSeedBuildRequest,
    OutOfScopeSeedBuildRequest,
    TrendingSeedBuildRequest,
)
from moviebot.evals.silver.case_catalog import (
    CaseCatalogError,
    load_case_catalog,
)

# ---------------------------------------------------------------------------
# Helpers to build a valid 150-case catalog
# ---------------------------------------------------------------------------


def _make_netflix_success_case(idx: int) -> dict:
    return {
        "case_id": f"netflix-success-{idx:03d}",
        "route": "netflix",
        "expected_status": "SUCCESS",
        "hard_constraints": {
            "constraint_type": "netflix",
            "type": "movie",
            "genres": ["drama"],
            "min_year": 2020,
        },
        "seed_item_ids": ["tm84618"],
        "semantic_concepts": ["some concept"],
        "difficulty": "easy",
        "tags": ["genre-filter"],
    }


def _make_netflix_no_results_case(idx: int) -> dict:
    return {
        "case_id": f"netflix-no-results-{idx:03d}",
        "route": "netflix",
        "expected_status": "NO_RESULTS",
        "hard_constraints": {
            "constraint_type": "netflix",
            "type": "movie",
            "genres": ["drama"],
            "actors": ["nonexistent actor xyz"],
        },
        "seed_item_ids": [],
        "semantic_concepts": [],
        "difficulty": "medium",
        "tags": ["no-results"],
    }


def _make_trending_success_case(idx: int) -> dict:
    return {
        "case_id": f"trending-success-{idx:03d}",
        "route": "trending",
        "expected_status": "SUCCESS",
        "hard_constraints": {
            "constraint_type": "tmdb",
            "genre_ids": [28],
            "min_year": 2023,
        },
        "seed_item_ids": ["tmdb:12345"],
        "semantic_concepts": ["action thriller"],
        "difficulty": "easy",
        "tags": ["genre-filter"],
    }


def _make_trending_no_results_case(idx: int) -> dict:
    return {
        "case_id": f"trending-no-results-{idx:03d}",
        "route": "trending",
        "expected_status": "NO_RESULTS",
        "hard_constraints": {
            "constraint_type": "tmdb",
            "genre_ids": [35],
            "min_year": 2099,
        },
        "seed_item_ids": [],
        "semantic_concepts": [],
        "difficulty": "hard",
        "tags": ["no-results"],
    }


def _make_both_case(idx: int) -> dict:
    return {
        "case_id": f"both-case-{idx:03d}",
        "route": "both",
        "expected_status": "SUCCESS",
        "tmdb_component": {
            "hard_constraints": {
                "constraint_type": "tmdb",
                "genre_ids": [878],
                "min_year": 2020,
            },
            "seed_item_ids": ["tmdb:67890"],
            "semantic_concepts": ["space exploration"],
        },
        "netflix_component": {
            "hard_constraints": {
                "constraint_type": "netflix",
                "type": "movie",
                "genres": ["science fiction"],
            },
            "seed_item_ids": ["tm654321"],
            "semantic_concepts": ["interstellar travel"],
        },
        "difficulty": "medium",
        "tags": ["multi-source"],
    }


def _make_out_of_scope_case(idx: int) -> dict:
    return {
        "case_id": f"out-of-scope-{idx:03d}",
        "route": "out_of_scope",
        "expected_status": "OUT_OF_SCOPE",
        "difficulty": "easy",
        "tags": ["non-movie-query"],
    }


def _build_valid_catalog() -> dict:
    """Build a valid catalog with exactly 150 cases respecting distribution and quota."""
    seeds = []
    # 50 netflix: 43 SUCCESS + 7 NO_RESULTS
    for i in range(43):
        seeds.append(_make_netflix_success_case(i))
    for i in range(7):
        seeds.append(_make_netflix_no_results_case(i))
    # 50 trending: 47 SUCCESS + 3 NO_RESULTS
    for i in range(47):
        seeds.append(_make_trending_success_case(i))
    for i in range(3):
        seeds.append(_make_trending_no_results_case(i))
    # 25 both (always SUCCESS)
    for i in range(25):
        seeds.append(_make_both_case(i))
    # 25 out_of_scope
    for i in range(25):
        seeds.append(_make_out_of_scope_case(i))

    return {"version": "1.0.0", "seeds": seeds}


def _write_catalog(tmp_path: Path, catalog: dict) -> Path:
    """Write a catalog dict to a JSON file and return the path."""
    path = tmp_path / "case_catalog.json"
    path.write_text(json.dumps(catalog, indent=2), encoding="utf-8")
    return path


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestLoadCaseCatalog:
    """Tests for load_case_catalog."""

    def test_valid_catalog_loads_successfully(self, tmp_path: Path) -> None:
        """A valid 150-case catalog loads and returns correct types."""
        catalog = _build_valid_catalog()
        path = _write_catalog(tmp_path, catalog)

        requests = load_case_catalog(path)

        assert len(requests) == 150
        netflix = [r for r in requests if isinstance(r, NetflixSeedBuildRequest)]
        trending = [r for r in requests if isinstance(r, TrendingSeedBuildRequest)]
        both = [r for r in requests if isinstance(r, BothSeedBuildRequest)]
        oos = [r for r in requests if isinstance(r, OutOfScopeSeedBuildRequest)]
        assert len(netflix) == 50
        assert len(trending) == 50
        assert len(both) == 25
        assert len(oos) == 25

    def test_file_not_found(self, tmp_path: Path) -> None:
        """Raises FileNotFoundError for missing catalog."""
        with pytest.raises(FileNotFoundError):
            load_case_catalog(tmp_path / "nonexistent.json")

    def test_wrong_total_count(self, tmp_path: Path) -> None:
        """Rejects catalog with wrong total count."""
        catalog = _build_valid_catalog()
        catalog["seeds"] = catalog["seeds"][:100]
        path = _write_catalog(tmp_path, catalog)

        with pytest.raises(CaseCatalogError, match="Expected 150 cases, got 100"):
            load_case_catalog(path)

    def test_distribution_mismatch(self, tmp_path: Path) -> None:
        """Rejects catalog with wrong distribution."""
        catalog = _build_valid_catalog()
        # Replace one out_of_scope with a netflix case
        catalog["seeds"][-1] = _make_netflix_success_case(99)
        path = _write_catalog(tmp_path, catalog)

        with pytest.raises(CaseCatalogError, match="Distribution mismatch"):
            load_case_catalog(path)

    def test_no_results_quota_mismatch(self, tmp_path: Path) -> None:
        """Rejects catalog with wrong NO_RESULTS quota."""
        catalog = _build_valid_catalog()
        # Change one netflix NO_RESULTS to SUCCESS (breaks 7→6)
        for i, seed in enumerate(catalog["seeds"]):
            if seed["route"] == "netflix" and seed["expected_status"] == "NO_RESULTS":
                catalog["seeds"][i] = _make_netflix_success_case(99)
                break
        path = _write_catalog(tmp_path, catalog)

        with pytest.raises(CaseCatalogError, match="NO_RESULTS quota mismatch"):
            load_case_catalog(path)

    def test_rejects_imdb_min_score(self, tmp_path: Path) -> None:
        """Rejects catalog entry with non-default min_imdb_score."""
        catalog = _build_valid_catalog()
        # Add min_imdb_score to first netflix case
        catalog["seeds"][0]["hard_constraints"]["min_imdb_score"] = 7.0
        path = _write_catalog(tmp_path, catalog)

        with pytest.raises(CaseCatalogError, match="min_imdb_score.*not allowed"):
            load_case_catalog(path)

    def test_rejects_imdb_max_score(self, tmp_path: Path) -> None:
        """Rejects catalog entry with non-default max_imdb_score."""
        catalog = _build_valid_catalog()
        catalog["seeds"][0]["hard_constraints"]["max_imdb_score"] = 9.0
        path = _write_catalog(tmp_path, catalog)

        with pytest.raises(CaseCatalogError, match="max_imdb_score.*not allowed"):
            load_case_catalog(path)

    def test_rejects_imdb_in_both_netflix_component(self, tmp_path: Path) -> None:
        """Rejects both seed with IMDb constraint in netflix component."""
        catalog = _build_valid_catalog()
        # Find a both case and add IMDb to its netflix component
        for seed in catalog["seeds"]:
            if seed["route"] == "both":
                seed["netflix_component"]["hard_constraints"]["min_imdb_score"] = 5.0
                break
        path = _write_catalog(tmp_path, catalog)

        with pytest.raises(CaseCatalogError, match="min_imdb_score.*not allowed"):
            load_case_catalog(path)

    def test_unknown_route_rejected(self, tmp_path: Path) -> None:
        """Rejects catalog entry with unknown route."""
        catalog = _build_valid_catalog()
        catalog["seeds"][0]["route"] = "unknown_route"
        path = _write_catalog(tmp_path, catalog)

        with pytest.raises(CaseCatalogError, match="Unknown route"):
            load_case_catalog(path)

    def test_missing_version_field(self, tmp_path: Path) -> None:
        """Rejects catalog without version field."""
        catalog = _build_valid_catalog()
        del catalog["version"]
        path = _write_catalog(tmp_path, catalog)

        with pytest.raises(CaseCatalogError, match="missing 'version'"):
            load_case_catalog(path)

    def test_missing_seeds_field(self, tmp_path: Path) -> None:
        """Rejects catalog without seeds field."""
        catalog = {"version": "1.0.0"}
        path = _write_catalog(tmp_path, catalog)

        with pytest.raises(CaseCatalogError, match="missing 'seeds'"):
            load_case_catalog(path)

    def test_netflix_case_parses_correctly(self, tmp_path: Path) -> None:
        """Netflix cases parse into NetflixSeedBuildRequest with correct fields."""
        catalog = _build_valid_catalog()
        path = _write_catalog(tmp_path, catalog)

        requests = load_case_catalog(path)
        netflix_req = next(
            r for r in requests if isinstance(r, NetflixSeedBuildRequest)
        )

        assert netflix_req.case_id.startswith("netflix-")
        assert netflix_req.hard_constraints.constraint_type == "netflix"
        assert netflix_req.hard_constraints.type == "movie"
        assert netflix_req.hard_constraints.genres == ["drama"]

    def test_trending_case_parses_correctly(self, tmp_path: Path) -> None:
        """Trending cases parse into TrendingSeedBuildRequest with correct fields."""
        catalog = _build_valid_catalog()
        path = _write_catalog(tmp_path, catalog)

        requests = load_case_catalog(path)
        trending_req = next(
            r for r in requests if isinstance(r, TrendingSeedBuildRequest)
        )

        assert trending_req.case_id.startswith("trending-")
        assert trending_req.hard_constraints.constraint_type == "tmdb"
        assert trending_req.hard_constraints.genre_ids == [28]

    def test_both_case_parses_correctly(self, tmp_path: Path) -> None:
        """Both cases parse into BothSeedBuildRequest with both components."""
        catalog = _build_valid_catalog()
        path = _write_catalog(tmp_path, catalog)

        requests = load_case_catalog(path)
        both_req = next(r for r in requests if isinstance(r, BothSeedBuildRequest))

        assert both_req.case_id.startswith("both-")
        assert both_req.tmdb_hard_constraints.constraint_type == "tmdb"
        assert both_req.netflix_hard_constraints.constraint_type == "netflix"
        assert both_req.tmdb_seed_item_ids == ["tmdb:67890"]
        assert both_req.netflix_seed_item_ids == ["tm654321"]

    def test_out_of_scope_case_parses_correctly(self, tmp_path: Path) -> None:
        """Out of scope cases parse into OutOfScopeSeedBuildRequest."""
        catalog = _build_valid_catalog()
        path = _write_catalog(tmp_path, catalog)

        requests = load_case_catalog(path)
        oos_req = next(r for r in requests if isinstance(r, OutOfScopeSeedBuildRequest))

        assert oos_req.case_id.startswith("out-of-scope-")
        assert oos_req.difficulty == "easy"
        assert oos_req.tags == ["non-movie-query"]

    def test_netflix_actors_directors_parsed(self, tmp_path: Path) -> None:
        """Netflix case with actors/directors parses them correctly."""
        catalog = _build_valid_catalog()
        # Add actors and directors to first netflix case
        catalog["seeds"][0]["hard_constraints"]["actors"] = ["robert de niro"]
        catalog["seeds"][0]["hard_constraints"]["directors"] = ["martin scorsese"]
        path = _write_catalog(tmp_path, catalog)

        requests = load_case_catalog(path)
        netflix_req = requests[0]
        assert isinstance(netflix_req, NetflixSeedBuildRequest)
        assert netflix_req.hard_constraints.actors == ["robert de niro"]
        assert netflix_req.hard_constraints.directors == ["martin scorsese"]
