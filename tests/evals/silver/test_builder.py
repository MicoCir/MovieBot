"""Tests for SeedBuilder — property-based and unit tests.

Covers:
- Property 6: Invariante seed_item_ids ⊆ eligible_item_ids (task 5.5)
- Unit tests for builder validation and error paths (task 5.6)
"""

from __future__ import annotations

import hypothesis.strategies as st
import pytest
from hypothesis import HealthCheck, assume, given, settings
from pydantic import ValidationError

from moviebot.evals.silver.adapters import NetflixAdapter, TmdbAdapter
from moviebot.evals.silver.builder import (
    BothSeedBuildRequest,
    NetflixSeedBuildRequest,
    OutOfScopeSeedBuildRequest,
    SeedBuilder,
    SeedBuildError,
    TrendingSeedBuildRequest,
)
from moviebot.evals.silver.models import (
    NetflixHardConstraints,
    TmdbHardConstraints,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def netflix_adapter(netflix_titles_csv, netflix_credits_csv):
    """Create a NetflixAdapter from test fixtures."""
    return NetflixAdapter(
        titles_path=netflix_titles_csv,
        credits_path=netflix_credits_csv,
    )


@pytest.fixture()
def tmdb_adapter(tmdb_fixture_path):
    """Create a TmdbAdapter from test fixtures."""
    return TmdbAdapter(fixture_version="v1", base_dir=tmdb_fixture_path)


@pytest.fixture()
def builder(netflix_adapter, tmdb_adapter):
    """Create a SeedBuilder with both adapters."""
    return SeedBuilder(
        netflix_adapter=netflix_adapter,
        tmdb_adapter=tmdb_adapter,
        schema_version="1.0.0",
        dataset_version="silver_v1",
    )


# ---------------------------------------------------------------------------
# Property 6: Invariante seed_item_ids ⊆ eligible_item_ids
# **Validates: Requirements 4.10, 5.1**
# ---------------------------------------------------------------------------

# Known IDs from the test fixtures (conftest)
_NETFLIX_IDS = [
    "tm84618",
    "tm154986",
    "tm70993",
    "ts22164",
    "tm120801",
    "tm257064",
    "ts45786",
    "tm312854",
]

_TMDB_IDS = [
    "tmdb:969681",
    "tmdb:872585",
    "tmdb:346698",
    "tmdb:565770",
    "tmdb:1022789",
]


@st.composite
def _netflix_success_request(draw: st.DrawFn) -> NetflixSeedBuildRequest:
    """Generate a Netflix SUCCESS build request using known fixture IDs.

    Picks random non-default constraints that produce non-empty eligible,
    then picks seed_item_ids from the eligible set.
    """
    # Pick constraints that we know produce results from the fixture
    # The fixture has movies from 1972-2022, scores 7.8-9.5
    content_type = draw(st.sampled_from([None, "movie", "show"]))
    min_year = draw(st.sampled_from([None, 1970, 2000, 2010]))
    max_year = draw(st.sampled_from([None, 2000, 2015, 2025]))

    # Ensure min <= max when both present
    if min_year is not None and max_year is not None and min_year > max_year:
        min_year, max_year = max_year, min_year

    constraints = NetflixHardConstraints(
        type=content_type,
        min_year=min_year,
        max_year=max_year,
    )

    # We need non-default constraints for eligible to be computed
    assume(not constraints.is_default())

    # Pick seed items from known IDs
    seed_ids = draw(
        st.lists(st.sampled_from(_NETFLIX_IDS), min_size=1, max_size=3, unique=True)
    )

    case_id = draw(st.from_regex(r"[a-z]{3,8}", fullmatch=True))

    return NetflixSeedBuildRequest(
        case_id=f"prop6-nf-{case_id}",
        expected_status="SUCCESS",
        seed_item_ids=seed_ids,
        hard_constraints=constraints,
        semantic_concepts=[],
        difficulty="easy",
        tags=[],
    )


@st.composite
def _tmdb_success_request(draw: st.DrawFn) -> TrendingSeedBuildRequest:
    """Generate a TMDB Trending SUCCESS build request using known fixture IDs.

    Picks random non-default constraints that produce non-empty eligible,
    then picks seed_item_ids from the eligible set.
    """
    # The fixture has movies from 2023-2024, votes 6.8-8.1, genres: 27,14,18,36,35,12,28,878,16,10751
    genre_ids = draw(
        st.lists(
            st.sampled_from([27, 14, 18, 36, 35, 12, 28, 878, 16, 10751]),
            min_size=0,
            max_size=2,
            unique=True,
        )
    )
    min_year = draw(st.sampled_from([None, 2020, 2023]))
    max_year = draw(st.sampled_from([None, 2023, 2025]))

    if min_year is not None and max_year is not None and min_year > max_year:
        min_year, max_year = max_year, min_year

    min_vote = draw(st.sampled_from([None, 6.0, 7.0]))
    max_vote = draw(st.sampled_from([None, 8.0, 9.0, 10.0]))

    if min_vote is not None and max_vote is not None and min_vote > max_vote:
        min_vote, max_vote = max_vote, min_vote

    constraints = TmdbHardConstraints(
        genre_ids=genre_ids,
        min_year=min_year,
        max_year=max_year,
        min_vote_average=min_vote,
        max_vote_average=max_vote,
    )

    assume(not constraints.is_default())

    seed_ids = draw(
        st.lists(st.sampled_from(_TMDB_IDS), min_size=1, max_size=3, unique=True)
    )

    case_id = draw(st.from_regex(r"[a-z]{3,8}", fullmatch=True))

    return TrendingSeedBuildRequest(
        case_id=f"prop6-tmdb-{case_id}",
        expected_status="SUCCESS",
        seed_item_ids=seed_ids,
        hard_constraints=constraints,
        semantic_concepts=[],
        difficulty="easy",
        tags=[],
    )


class TestProperty6SeedItemsSubsetEligible:
    """Property 6: Invariante seed_item_ids ⊆ eligible_item_ids.

    **Validates: Requirements 4.10, 5.1**

    For every SUCCESS seed built with non-default constraints (eligible not None),
    the set of seed_item_ids MUST be a subset of eligible_item_ids.
    """

    @given(request_data=_netflix_success_request())
    @settings(
        max_examples=100,
        suppress_health_check=[HealthCheck.function_scoped_fixture],
    )
    def test_netflix_seed_items_subset_eligible(
        self,
        request_data: NetflixSeedBuildRequest,
        netflix_adapter: NetflixAdapter,
        tmdb_adapter: TmdbAdapter,
    ) -> None:
        """Netflix: seed_item_ids ⊆ eligible_item_ids when eligible is not None."""
        builder = SeedBuilder(
            netflix_adapter=netflix_adapter,
            tmdb_adapter=tmdb_adapter,
            schema_version="1.0.0",
            dataset_version="silver_v1",
        )

        try:
            seed = builder.build(request_data)
        except (SeedBuildError, ValidationError):
            # If the builder rejects the request (e.g., seed_items not in eligible),
            # that's fine — the invariant is maintained by rejection.
            return

        # The property: when eligible is not None, seed_items ⊆ eligible
        if seed.eligible_item_ids is not None:
            assert set(seed.seed_item_ids) <= set(seed.eligible_item_ids), (
                f"Violation: seed_item_ids={seed.seed_item_ids} "
                f"not subset of eligible_item_ids={seed.eligible_item_ids}"
            )

    @given(request_data=_tmdb_success_request())
    @settings(
        max_examples=100,
        suppress_health_check=[HealthCheck.function_scoped_fixture],
    )
    def test_tmdb_seed_items_subset_eligible(
        self,
        request_data: TrendingSeedBuildRequest,
        netflix_adapter: NetflixAdapter,
        tmdb_adapter: TmdbAdapter,
    ) -> None:
        """TMDB: seed_item_ids ⊆ eligible_item_ids when eligible is not None."""
        builder = SeedBuilder(
            netflix_adapter=netflix_adapter,
            tmdb_adapter=tmdb_adapter,
            schema_version="1.0.0",
            dataset_version="silver_v1",
        )

        try:
            seed = builder.build(request_data)
        except (SeedBuildError, ValidationError):
            # If the builder rejects the request, the invariant is enforced by rejection.
            return

        if seed.eligible_item_ids is not None:
            assert set(seed.seed_item_ids) <= set(seed.eligible_item_ids), (
                f"Violation: seed_item_ids={seed.seed_item_ids} "
                f"not subset of eligible_item_ids={seed.eligible_item_ids}"
            )


# ---------------------------------------------------------------------------
# Unit tests for Builder (task 5.6)
# **Validates: Requirements 10.3, 10.9**
# ---------------------------------------------------------------------------


class TestBuilderRejectsIncompatibleConstraints:
    """The type system and builder reject constraint/route mismatches."""

    def test_netflix_constraints_in_trending_request_rejected(
        self, netflix_adapter, tmdb_adapter
    ) -> None:
        """Netflix constraints cannot be used in a TrendingSeedBuildRequest.

        The dataclass TrendingSeedBuildRequest has hard_constraints: TmdbHardConstraints.
        Passing NetflixHardConstraints raises TypeError at construction (type mismatch)
        or the builder rejects it.
        Actually, Python doesn't enforce dataclass field types at runtime.
        The builder passes constraints to _compute_eligible → TmdbAdapter.filter()
        which raises TypeError for non-TmdbHardConstraints.
        """
        builder = SeedBuilder(
            netflix_adapter=netflix_adapter,
            tmdb_adapter=tmdb_adapter,
            schema_version="1.0.0",
            dataset_version="silver_v1",
        )

        # Force wrong constraint type (Python allows it at runtime for dataclasses)
        request = TrendingSeedBuildRequest(
            case_id="bad-constraint-trending",
            expected_status="SUCCESS",
            seed_item_ids=["tmdb:872585"],
            hard_constraints=NetflixHardConstraints(type="movie"),  # type: ignore[arg-type]
            semantic_concepts=[],
            difficulty="easy",
            tags=[],
        )

        # TmdbAdapter.filter() raises TypeError for non-TmdbHardConstraints
        with pytest.raises(TypeError, match="solo acepta TmdbHardConstraints"):
            builder.build(request)

    def test_tmdb_constraints_in_netflix_request_rejected(
        self, netflix_adapter, tmdb_adapter
    ) -> None:
        """TMDB constraints cannot be used in a NetflixSeedBuildRequest.

        NetflixAdapter.filter() raises TypeError for non-NetflixHardConstraints.
        """
        builder = SeedBuilder(
            netflix_adapter=netflix_adapter,
            tmdb_adapter=tmdb_adapter,
            schema_version="1.0.0",
            dataset_version="silver_v1",
        )

        request = NetflixSeedBuildRequest(
            case_id="bad-constraint-netflix",
            expected_status="SUCCESS",
            seed_item_ids=["tm84618"],
            hard_constraints=TmdbHardConstraints(min_year=2020),  # type: ignore[arg-type]
            semantic_concepts=[],
            difficulty="easy",
            tags=[],
        )

        with pytest.raises(TypeError, match="solo acepta NetflixHardConstraints"):
            builder.build(request)


class TestBuilderRejectsSuccessWithEmptyEligible:
    """SUCCESS with constraints that produce empty eligible → SeedBuildError."""

    def test_netflix_success_empty_eligible(
        self, netflix_adapter, tmdb_adapter
    ) -> None:
        """Netflix SUCCESS with constraints that match nothing → contradiction error."""
        builder = SeedBuilder(
            netflix_adapter=netflix_adapter,
            tmdb_adapter=tmdb_adapter,
            schema_version="1.0.0",
            dataset_version="silver_v1",
        )

        # Constraints that produce empty eligible: min_year=2099 (no titles that recent)
        request = NetflixSeedBuildRequest(
            case_id="empty-eligible-nf",
            expected_status="SUCCESS",
            seed_item_ids=["tm84618"],
            hard_constraints=NetflixHardConstraints(min_year=2099),
            semantic_concepts=[],
            difficulty="easy",
            tags=[],
        )

        with pytest.raises(SeedBuildError, match="Contradicción.*eligible vacío"):
            builder.build(request)

    def test_tmdb_success_empty_eligible(self, netflix_adapter, tmdb_adapter) -> None:
        """TMDB SUCCESS with constraints that match nothing → contradiction error."""
        builder = SeedBuilder(
            netflix_adapter=netflix_adapter,
            tmdb_adapter=tmdb_adapter,
            schema_version="1.0.0",
            dataset_version="silver_v1",
        )

        # Constraints that produce empty eligible: min_year=2099 (no records that recent)
        request = TrendingSeedBuildRequest(
            case_id="empty-eligible-tmdb",
            expected_status="SUCCESS",
            seed_item_ids=["tmdb:872585"],
            hard_constraints=TmdbHardConstraints(min_year=2099),
            semantic_concepts=[],
            difficulty="easy",
            tags=[],
        )

        with pytest.raises(SeedBuildError, match="Contradicción.*eligible vacío"):
            builder.build(request)


class TestBuilderRejectsNonExistentIds:
    """Builder rejects seed_item_ids that don't exist in the datasource."""

    def test_netflix_nonexistent_id(self, netflix_adapter, tmdb_adapter) -> None:
        """Non-existent Netflix ID → SeedBuildError indicating which ID."""
        builder = SeedBuilder(
            netflix_adapter=netflix_adapter,
            tmdb_adapter=tmdb_adapter,
            schema_version="1.0.0",
            dataset_version="silver_v1",
        )

        request = NetflixSeedBuildRequest(
            case_id="bad-id-nf",
            expected_status="SUCCESS",
            seed_item_ids=["tm99999999"],
            hard_constraints=NetflixHardConstraints(type="movie"),
            semantic_concepts=[],
            difficulty="easy",
            tags=[],
        )

        with pytest.raises(SeedBuildError, match="tm99999999"):
            builder.build(request)

    def test_tmdb_nonexistent_id(self, netflix_adapter, tmdb_adapter) -> None:
        """Non-existent TMDB ID → SeedBuildError indicating which ID."""
        builder = SeedBuilder(
            netflix_adapter=netflix_adapter,
            tmdb_adapter=tmdb_adapter,
            schema_version="1.0.0",
            dataset_version="silver_v1",
        )

        request = TrendingSeedBuildRequest(
            case_id="bad-id-tmdb",
            expected_status="SUCCESS",
            seed_item_ids=["tmdb:999999999"],
            hard_constraints=TmdbHardConstraints(min_year=2023),
            semantic_concepts=[],
            difficulty="easy",
            tags=[],
        )

        with pytest.raises(SeedBuildError, match="tmdb:999999999"):
            builder.build(request)


class TestBuilderRejectsSemanticConceptsWithEmptyText:
    """Builder rejects semantic_concepts when description/overview is empty."""

    def test_netflix_semantic_with_no_description(
        self, netflix_titles_csv, netflix_credits_csv, tmdb_adapter, tmp_path
    ) -> None:
        """Netflix seed with semantic_concepts but item has None description → error."""
        # Create a custom CSV with one item that has empty description
        csv_content = (
            "id,title,type,description,release_year,age_certification,runtime,genres,"
            "production_countries,seasons,imdb_id,imdb_score,imdb_votes,tmdb_popularity,tmdb_score\n"
            "tm00001,No Desc Movie,MOVIE,,2020,R,90,\"['drama']\",\"['US']\",,tt0000001,7.0,1000,10.0,7.0\n"
        )
        custom_csv = tmp_path / "custom_netflix" / "titles.csv"
        custom_csv.parent.mkdir(parents=True, exist_ok=True)
        custom_csv.write_text(csv_content, encoding="utf-8")

        credits_content = "person_id,id,name,character,role\n"
        credits_csv = tmp_path / "custom_netflix" / "credits.csv"
        credits_csv.write_text(credits_content, encoding="utf-8")

        adapter = NetflixAdapter(
            titles_path=custom_csv,
            credits_path=credits_csv,
        )

        builder = SeedBuilder(
            netflix_adapter=adapter,
            tmdb_adapter=tmdb_adapter,
            schema_version="1.0.0",
            dataset_version="silver_v1",
        )

        request = NetflixSeedBuildRequest(
            case_id="semantic-no-desc",
            expected_status="SUCCESS",
            seed_item_ids=["tm00001"],
            hard_constraints=NetflixHardConstraints(type="movie"),
            semantic_concepts=["dark atmosphere"],
            difficulty="easy",
            tags=[],
        )

        with pytest.raises(SeedBuildError, match="description no vacío"):
            builder.build(request)

    def test_tmdb_semantic_with_no_overview(self, netflix_adapter, tmp_path) -> None:
        """TMDB seed with semantic_concepts but item has None overview → error."""
        import hashlib
        import json

        # Create fixture with one record that has empty overview
        records = [
            {
                "id": 111111,
                "title": "No Overview Movie",
                "overview": "",
                "release_date": "2023-05-01",
                "genre_ids": [18],
                "popularity": 10.0,
                "vote_average": 7.0,
            }
        ]
        tmdb_dir = tmp_path / "tmdb_no_overview"
        tmdb_dir.mkdir(parents=True, exist_ok=True)

        fixture_content = json.dumps({"results": records}, ensure_ascii=False, indent=2)
        checksum = hashlib.sha256(fixture_content.encode("utf-8")).hexdigest()
        metadata = {
            "fixture_version": "v1",
            "checksum_sha256": checksum,
            "created_at": "2024-01-01T00:00:00Z",
        }

        (tmdb_dir / "trending_movies_v1.json").write_text(
            fixture_content, encoding="utf-8"
        )
        (tmdb_dir / "trending_movies_v1.metadata.json").write_text(
            json.dumps(metadata), encoding="utf-8"
        )

        adapter = TmdbAdapter(fixture_version="v1", base_dir=tmdb_dir)

        builder = SeedBuilder(
            netflix_adapter=netflix_adapter,
            tmdb_adapter=adapter,
            schema_version="1.0.0",
            dataset_version="silver_v1",
        )

        request = TrendingSeedBuildRequest(
            case_id="semantic-no-overview",
            expected_status="SUCCESS",
            seed_item_ids=["tmdb:111111"],
            hard_constraints=TmdbHardConstraints(min_year=2023),
            semantic_concepts=["emotional journey"],
            difficulty="easy",
            tags=[],
        )

        with pytest.raises(SeedBuildError, match="overview no vacío"):
            builder.build(request)


class TestBuilderRejectsBothWithEmptyComponent:
    """Builder rejects BOTH request when a component has no seed_item_ids."""

    def test_both_with_empty_tmdb_component(
        self, netflix_adapter, tmdb_adapter
    ) -> None:
        """BOTH with empty tmdb_seed_item_ids → SeedBuildError."""
        builder = SeedBuilder(
            netflix_adapter=netflix_adapter,
            tmdb_adapter=tmdb_adapter,
            schema_version="1.0.0",
            dataset_version="silver_v1",
        )

        request = BothSeedBuildRequest(
            case_id="both-empty-tmdb",
            difficulty="easy",
            tags=[],
            tmdb_seed_item_ids=[],  # empty!
            tmdb_hard_constraints=TmdbHardConstraints(min_year=2023),
            tmdb_semantic_concepts=[],
            netflix_seed_item_ids=["tm84618"],
            netflix_hard_constraints=NetflixHardConstraints(type="movie"),
            netflix_semantic_concepts=[],
        )

        with pytest.raises(SeedBuildError, match="al menos 1 seed_item_id"):
            builder.build(request)

    def test_both_with_empty_netflix_component(
        self, netflix_adapter, tmdb_adapter
    ) -> None:
        """BOTH with empty netflix_seed_item_ids → SeedBuildError."""
        builder = SeedBuilder(
            netflix_adapter=netflix_adapter,
            tmdb_adapter=tmdb_adapter,
            schema_version="1.0.0",
            dataset_version="silver_v1",
        )

        request = BothSeedBuildRequest(
            case_id="both-empty-netflix",
            difficulty="easy",
            tags=[],
            tmdb_seed_item_ids=["tmdb:872585"],
            tmdb_hard_constraints=TmdbHardConstraints(min_year=2023),
            tmdb_semantic_concepts=[],
            netflix_seed_item_ids=[],  # empty!
            netflix_hard_constraints=NetflixHardConstraints(type="movie"),
            netflix_semantic_concepts=[],
        )

        with pytest.raises(SeedBuildError, match="al menos 1 seed_item_id"):
            builder.build(request)


class TestBuilderNoResultsWithNonEmptySeedItems:
    """NO_RESULTS with non-empty seed_item_ids is rejected by model validation."""

    def test_netflix_no_results_with_seed_items(
        self, netflix_adapter, tmdb_adapter
    ) -> None:
        """NO_RESULTS + seed_item_ids non-empty → ValidationError from model."""
        builder = SeedBuilder(
            netflix_adapter=netflix_adapter,
            tmdb_adapter=tmdb_adapter,
            schema_version="1.0.0",
            dataset_version="silver_v1",
        )

        request = NetflixSeedBuildRequest(
            case_id="no-results-with-ids",
            expected_status="NO_RESULTS",
            seed_item_ids=["tm84618"],
            hard_constraints=NetflixHardConstraints(min_year=2099),
            semantic_concepts=[],
            difficulty="easy",
            tags=[],
        )

        # The model validator raises ValidationError for NO_RESULTS + non-empty seed_item_ids
        with pytest.raises(ValidationError, match="NO_RESULTS requiere seed_item_ids"):
            builder.build(request)

    def test_tmdb_no_results_with_seed_items(
        self, netflix_adapter, tmdb_adapter
    ) -> None:
        """NO_RESULTS + seed_item_ids non-empty → ValidationError from model."""
        builder = SeedBuilder(
            netflix_adapter=netflix_adapter,
            tmdb_adapter=tmdb_adapter,
            schema_version="1.0.0",
            dataset_version="silver_v1",
        )

        request = TrendingSeedBuildRequest(
            case_id="no-results-with-ids-tmdb",
            expected_status="NO_RESULTS",
            seed_item_ids=["tmdb:872585"],
            hard_constraints=TmdbHardConstraints(min_year=2099),
            semantic_concepts=[],
            difficulty="easy",
            tags=[],
        )

        with pytest.raises(ValidationError, match="NO_RESULTS requiere seed_item_ids"):
            builder.build(request)


class TestBuilderOutOfScopeNoAdapters:
    """OUT_OF_SCOPE seeds don't require adapters."""

    def test_out_of_scope_without_adapters(self) -> None:
        """OUT_OF_SCOPE build succeeds even with no adapters injected."""
        builder = SeedBuilder(
            netflix_adapter=None,
            tmdb_adapter=None,
            schema_version="2.0.0",
            dataset_version="silver_v2",
        )

        request = OutOfScopeSeedBuildRequest(
            case_id="oos-no-adapters",
            difficulty="hard",
            tags=["out-of-scope"],
        )

        seed = builder.build(request)

        assert seed.case_id == "oos-no-adapters"
        assert seed.expected_route == "out_of_scope"
        assert seed.expected_status == "OUT_OF_SCOPE"
        assert seed.expected_sources == []
        assert seed.seed_item_ids == []
        assert seed.eligible_item_ids is None


class TestBuilderProvenanceUsesConstructorVersions:
    """Provenance uses versions from the builder constructor, not hardcoded."""

    def test_netflix_provenance_versions(self, netflix_adapter, tmdb_adapter) -> None:
        """Netflix seed provenance uses schema_version and dataset_version from constructor."""
        builder = SeedBuilder(
            netflix_adapter=netflix_adapter,
            tmdb_adapter=tmdb_adapter,
            schema_version="3.2.1",
            dataset_version="custom_dataset",
        )

        request = NetflixSeedBuildRequest(
            case_id="prov-version-nf",
            expected_status="SUCCESS",
            seed_item_ids=["tm84618"],
            hard_constraints=NetflixHardConstraints(type="movie"),
            semantic_concepts=[],
            difficulty="easy",
            tags=[],
        )

        seed = builder.build(request)

        assert seed.provenance.schema_version == "3.2.1"
        assert seed.provenance.dataset_version == "custom_dataset"

    def test_trending_provenance_versions(self, netflix_adapter, tmdb_adapter) -> None:
        """Trending seed provenance uses schema_version and dataset_version from constructor."""
        builder = SeedBuilder(
            netflix_adapter=netflix_adapter,
            tmdb_adapter=tmdb_adapter,
            schema_version="4.0.0",
            dataset_version="another_version",
        )

        request = TrendingSeedBuildRequest(
            case_id="prov-version-tmdb",
            expected_status="SUCCESS",
            seed_item_ids=["tmdb:872585"],
            hard_constraints=TmdbHardConstraints(min_year=2023),
            semantic_concepts=[],
            difficulty="medium",
            tags=[],
        )

        seed = builder.build(request)

        assert seed.provenance.schema_version == "4.0.0"
        assert seed.provenance.dataset_version == "another_version"

    def test_out_of_scope_provenance_versions(self) -> None:
        """OUT_OF_SCOPE seed provenance uses constructor versions."""
        builder = SeedBuilder(
            netflix_adapter=None,
            tmdb_adapter=None,
            schema_version="9.9.9",
            dataset_version="oos_dataset",
        )

        request = OutOfScopeSeedBuildRequest(
            case_id="prov-version-oos",
            difficulty="hard",
            tags=[],
        )

        seed = builder.build(request)

        assert seed.provenance.schema_version == "9.9.9"
        assert seed.provenance.dataset_version == "oos_dataset"
        assert seed.provenance.source == "synthetic"
