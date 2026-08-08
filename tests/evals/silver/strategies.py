"""Hypothesis strategies for Silver Dataset Seeds.

Provides composite strategies that generate valid model instances
for property-based testing throughout the silver evaluation suite.
"""

from __future__ import annotations

import hypothesis.strategies as st
from hypothesis import assume

from moviebot.evals.silver.models import (
    NetflixHardConstraints,
    NetflixSeedComponent,
    SeedProvenance,
    SilverSeed,
    TmdbHardConstraints,
    TmdbSeedComponent,
)

# --- Helpers ---

_LOWERCASE_GENRE = st.text(
    alphabet=st.characters(
        whitelist_categories=("Ll",), min_codepoint=97, max_codepoint=122
    ),
    min_size=3,
    max_size=15,
)

_PERSON_NAME = st.text(
    alphabet=st.characters(
        whitelist_categories=("L", "Zs"), min_codepoint=32, max_codepoint=122
    ),
    min_size=2,
    max_size=30,
).filter(lambda s: s.strip() != "")

_SEMVER = st.builds(
    lambda ma, mi, pa: f"{ma}.{mi}.{pa}",
    st.integers(min_value=0, max_value=9),
    st.integers(min_value=0, max_value=99),
    st.integers(min_value=0, max_value=99),
)

_DATASET_VERSION = st.from_regex(r"[a-zA-Z0-9_-]{1,20}", fullmatch=True)

_CASE_ID = st.from_regex(r"[a-zA-Z0-9_-]{1,64}", fullmatch=True).filter(
    lambda s: len(s) >= 1
)

_DIFFICULTY = st.sampled_from(["easy", "medium", "hard"])

_TAG = st.from_regex(r"[a-z0-9_-]{1,20}", fullmatch=True)


# --- Constraint Strategies ---


@st.composite
def tmdb_hard_constraints(draw: st.DrawFn) -> TmdbHardConstraints:
    """Generate valid TmdbHardConstraints instances.

    Ensures:
    - genre_ids has at most 5 items
    - min_year <= max_year when both present
    - min_vote_average <= max_vote_average when both present
    - All values within allowed bounds (ge/le)
    """
    genre_ids = draw(
        st.lists(st.integers(min_value=1, max_value=99999), min_size=0, max_size=5)
    )

    # Generate year range ensuring min <= max
    has_min_year = draw(st.booleans())
    has_max_year = draw(st.booleans())
    min_year: int | None = None
    max_year: int | None = None

    if has_min_year and has_max_year:
        y1 = draw(st.integers(min_value=1888, max_value=2100))
        y2 = draw(st.integers(min_value=1888, max_value=2100))
        min_year = min(y1, y2)
        max_year = max(y1, y2)
    elif has_min_year:
        min_year = draw(st.integers(min_value=1888, max_value=2100))
    elif has_max_year:
        max_year = draw(st.integers(min_value=1888, max_value=2100))

    # Generate vote_average range ensuring min <= max
    has_min_vote = draw(st.booleans())
    has_max_vote = draw(st.booleans())
    min_vote_average: float | None = None
    max_vote_average: float | None = None

    if has_min_vote and has_max_vote:
        v1 = draw(
            st.floats(
                min_value=0.0, max_value=10.0, allow_nan=False, allow_infinity=False
            )
        )
        v2 = draw(
            st.floats(
                min_value=0.0, max_value=10.0, allow_nan=False, allow_infinity=False
            )
        )
        min_vote_average = min(v1, v2)
        max_vote_average = max(v1, v2)
    elif has_min_vote:
        min_vote_average = draw(
            st.floats(
                min_value=0.0, max_value=10.0, allow_nan=False, allow_infinity=False
            )
        )
    elif has_max_vote:
        max_vote_average = draw(
            st.floats(
                min_value=0.0, max_value=10.0, allow_nan=False, allow_infinity=False
            )
        )

    return TmdbHardConstraints(
        genre_ids=genre_ids,
        min_year=min_year,
        max_year=max_year,
        min_vote_average=min_vote_average,
        max_vote_average=max_vote_average,
    )


@st.composite
def netflix_hard_constraints(draw: st.DrawFn) -> NetflixHardConstraints:
    """Generate valid NetflixHardConstraints instances.

    Ensures:
    - genres are lowercase, max 5 items
    - actors/directors max 10 items each
    - min_year <= max_year when both present
    - min_imdb_score <= max_imdb_score when both present
    """
    content_type = draw(st.sampled_from([None, "movie", "show"]))
    genres = draw(st.lists(_LOWERCASE_GENRE, min_size=0, max_size=5, unique=True))

    # Generate year range ensuring min <= max
    has_min_year = draw(st.booleans())
    has_max_year = draw(st.booleans())
    min_year: int | None = None
    max_year: int | None = None

    if has_min_year and has_max_year:
        y1 = draw(st.integers(min_value=1888, max_value=2100))
        y2 = draw(st.integers(min_value=1888, max_value=2100))
        min_year = min(y1, y2)
        max_year = max(y1, y2)
    elif has_min_year:
        min_year = draw(st.integers(min_value=1888, max_value=2100))
    elif has_max_year:
        max_year = draw(st.integers(min_value=1888, max_value=2100))

    # Generate imdb_score range ensuring min <= max
    has_min_score = draw(st.booleans())
    has_max_score = draw(st.booleans())
    min_imdb_score: float | None = None
    max_imdb_score: float | None = None

    if has_min_score and has_max_score:
        s1 = draw(
            st.floats(
                min_value=0.0, max_value=10.0, allow_nan=False, allow_infinity=False
            )
        )
        s2 = draw(
            st.floats(
                min_value=0.0, max_value=10.0, allow_nan=False, allow_infinity=False
            )
        )
        min_imdb_score = min(s1, s2)
        max_imdb_score = max(s1, s2)
    elif has_min_score:
        min_imdb_score = draw(
            st.floats(
                min_value=0.0, max_value=10.0, allow_nan=False, allow_infinity=False
            )
        )
    elif has_max_score:
        max_imdb_score = draw(
            st.floats(
                min_value=0.0, max_value=10.0, allow_nan=False, allow_infinity=False
            )
        )

    actors = draw(st.lists(_PERSON_NAME, min_size=0, max_size=10))
    directors = draw(st.lists(_PERSON_NAME, min_size=0, max_size=10))

    return NetflixHardConstraints(
        type=content_type,
        genres=genres,
        min_year=min_year,
        max_year=max_year,
        min_imdb_score=min_imdb_score,
        max_imdb_score=max_imdb_score,
        actors=actors,
        directors=directors,
    )


# --- Non-default constraint strategies (for SUCCESS seeds) ---


@st.composite
def _non_default_tmdb_constraints(draw: st.DrawFn) -> TmdbHardConstraints:
    """Generate TmdbHardConstraints that are guaranteed non-default."""
    constraints = draw(tmdb_hard_constraints())
    assume(not constraints.is_default())
    return constraints


@st.composite
def _non_default_netflix_constraints(draw: st.DrawFn) -> NetflixHardConstraints:
    """Generate NetflixHardConstraints that are guaranteed non-default."""
    constraints = draw(netflix_hard_constraints())
    assume(not constraints.is_default())
    return constraints


# --- ID generators ---

_NETFLIX_ID = st.one_of(
    st.builds(lambda n: f"tm{n}", st.integers(min_value=10000, max_value=99999)),
    st.builds(lambda n: f"ts{n}", st.integers(min_value=10000, max_value=99999)),
)

_TMDB_ID = st.builds(
    lambda n: f"tmdb:{n}", st.integers(min_value=100000, max_value=999999)
)


# --- Silver Seed Strategy ---


@st.composite
def valid_silver_seed(draw: st.DrawFn) -> SilverSeed:
    """Generate complete valid SilverSeed instances for different routes.

    Generates seeds for routes: trending, netflix, both, out_of_scope
    with consistent route/status/constraints combinations.
    All generated instances pass Pydantic validation without errors.
    """
    route = draw(st.sampled_from(["trending", "netflix", "both", "out_of_scope"]))
    case_id = draw(_CASE_ID)
    difficulty = draw(_DIFFICULTY)
    tags = draw(st.lists(_TAG, min_size=0, max_size=5, unique=True))
    schema_version = draw(_SEMVER)
    silver_dataset_version = draw(_DATASET_VERSION)

    if route == "trending":
        return draw(
            _build_trending_seed(
                case_id, difficulty, tags, schema_version, silver_dataset_version
            )
        )
    elif route == "netflix":
        return draw(
            _build_netflix_seed(
                case_id, difficulty, tags, schema_version, silver_dataset_version
            )
        )
    elif route == "both":
        return draw(
            _build_both_seed(
                case_id, difficulty, tags, schema_version, silver_dataset_version
            )
        )
    else:  # out_of_scope
        return draw(
            _build_out_of_scope_seed(
                case_id, difficulty, tags, schema_version, silver_dataset_version
            )
        )


@st.composite
def _build_trending_seed(
    draw: st.DrawFn,
    case_id: str,
    difficulty: str,
    tags: list[str],
    schema_version: str,
    silver_dataset_version: str,
) -> SilverSeed:
    """Build a valid trending route seed."""
    status = draw(st.sampled_from(["SUCCESS", "NO_RESULTS"]))
    fixture_version = draw(_SEMVER)

    if status == "SUCCESS":
        # Need non-default constraints OR semantic_concepts
        use_constraints = draw(st.booleans())
        if use_constraints:
            constraints = draw(_non_default_tmdb_constraints())
            semantic_concepts = draw(
                st.lists(st.text(min_size=3, max_size=50), min_size=0, max_size=5)
            )
        else:
            constraints = draw(tmdb_hard_constraints())
            # Must have at least one semantic concept
            semantic_concepts = draw(
                st.lists(st.text(min_size=3, max_size=50), min_size=1, max_size=5)
            )
        seed_item_ids = draw(st.lists(_TMDB_ID, min_size=1, max_size=5, unique=True))
        # eligible can be None (if only semantic) or a list containing seed_items
        if constraints.is_default():
            eligible_item_ids = None
        else:
            extra_eligible = draw(
                st.lists(_TMDB_ID, min_size=0, max_size=10, unique=True)
            )
            eligible_item_ids = sorted(set(seed_item_ids) | set(extra_eligible))
    else:
        # NO_RESULTS
        constraints = draw(_non_default_tmdb_constraints())
        semantic_concepts: list[str] = []
        seed_item_ids = []
        eligible_item_ids = []

    provenance = SeedProvenance(
        source="tmdb",
        fixture_version=fixture_version,
        input_data_description="test fixture data",
        schema_version=schema_version,
        silver_dataset_version=silver_dataset_version,
    )

    return SilverSeed(
        case_id=case_id,
        expected_route="trending",
        expected_sources=["tmdb"],
        expected_status=status,
        hard_constraints=constraints,
        semantic_concepts=semantic_concepts,
        seed_item_ids=seed_item_ids,
        eligible_item_ids=eligible_item_ids,
        difficulty=difficulty,
        tags=tags,
        provenance=provenance,
        fixture_version=fixture_version,
    )


@st.composite
def _build_netflix_seed(
    draw: st.DrawFn,
    case_id: str,
    difficulty: str,
    tags: list[str],
    schema_version: str,
    silver_dataset_version: str,
) -> SilverSeed:
    """Build a valid netflix route seed."""
    status = draw(st.sampled_from(["SUCCESS", "NO_RESULTS"]))

    if status == "SUCCESS":
        use_constraints = draw(st.booleans())
        if use_constraints:
            constraints = draw(_non_default_netflix_constraints())
            semantic_concepts = draw(
                st.lists(st.text(min_size=3, max_size=50), min_size=0, max_size=5)
            )
        else:
            constraints = draw(netflix_hard_constraints())
            semantic_concepts = draw(
                st.lists(st.text(min_size=3, max_size=50), min_size=1, max_size=5)
            )
        seed_item_ids = draw(st.lists(_NETFLIX_ID, min_size=1, max_size=5, unique=True))
        if constraints.is_default():
            eligible_item_ids = None
        else:
            extra_eligible = draw(
                st.lists(_NETFLIX_ID, min_size=0, max_size=10, unique=True)
            )
            eligible_item_ids = sorted(set(seed_item_ids) | set(extra_eligible))
    else:
        # NO_RESULTS
        constraints = draw(_non_default_netflix_constraints())
        semantic_concepts = []
        seed_item_ids = []
        eligible_item_ids = []

    provenance = SeedProvenance(
        source="netflix",
        input_data_description="test netflix data",
        schema_version=schema_version,
        silver_dataset_version=silver_dataset_version,
        canonical_dataset_version=silver_dataset_version,
    )

    return SilverSeed(
        case_id=case_id,
        expected_route="netflix",
        expected_sources=["netflix"],
        expected_status=status,
        hard_constraints=constraints,
        semantic_concepts=semantic_concepts,
        seed_item_ids=seed_item_ids,
        eligible_item_ids=eligible_item_ids,
        difficulty=difficulty,
        tags=tags,
        provenance=provenance,
        fixture_version=None,
    )


@st.composite
def _build_both_seed(
    draw: st.DrawFn,
    case_id: str,
    difficulty: str,
    tags: list[str],
    schema_version: str,
    silver_dataset_version: str,
) -> SilverSeed:
    """Build a valid 'both' route seed.

    Both components need content sufficiency (non-default constraints OR semantic_concepts).
    """
    fixture_version = draw(_SEMVER)

    # TMDB component — ensure content sufficiency
    use_tmdb_constraints = draw(st.booleans())
    if use_tmdb_constraints:
        tmdb_constraints = draw(_non_default_tmdb_constraints())
        tmdb_semantic = draw(
            st.lists(st.text(min_size=3, max_size=50), min_size=0, max_size=5)
        )
    else:
        tmdb_constraints = draw(tmdb_hard_constraints())
        tmdb_semantic = draw(
            st.lists(st.text(min_size=3, max_size=50), min_size=1, max_size=5)
        )

    tmdb_seed_ids = draw(st.lists(_TMDB_ID, min_size=1, max_size=5, unique=True))
    if tmdb_constraints.is_default():
        tmdb_eligible = None
    else:
        tmdb_extra = draw(st.lists(_TMDB_ID, min_size=0, max_size=10, unique=True))
        tmdb_eligible = sorted(set(tmdb_seed_ids) | set(tmdb_extra))

    tmdb_component = TmdbSeedComponent(
        fixture_version=fixture_version,
        seed_item_ids=tmdb_seed_ids,
        eligible_item_ids=tmdb_eligible,
        hard_constraints=tmdb_constraints,
        semantic_concepts=tmdb_semantic,
    )

    # Netflix component — ensure content sufficiency
    use_netflix_constraints = draw(st.booleans())
    if use_netflix_constraints:
        netflix_constraints = draw(_non_default_netflix_constraints())
        netflix_semantic = draw(
            st.lists(st.text(min_size=3, max_size=50), min_size=0, max_size=5)
        )
    else:
        netflix_constraints = draw(netflix_hard_constraints())
        netflix_semantic = draw(
            st.lists(st.text(min_size=3, max_size=50), min_size=1, max_size=5)
        )

    netflix_seed_ids = draw(st.lists(_NETFLIX_ID, min_size=1, max_size=5, unique=True))
    if netflix_constraints.is_default():
        netflix_eligible = None
    else:
        netflix_extra = draw(
            st.lists(_NETFLIX_ID, min_size=0, max_size=10, unique=True)
        )
        netflix_eligible = sorted(set(netflix_seed_ids) | set(netflix_extra))

    netflix_component = NetflixSeedComponent(
        seed_item_ids=netflix_seed_ids,
        eligible_item_ids=netflix_eligible,
        hard_constraints=netflix_constraints,
        semantic_concepts=netflix_semantic,
    )

    provenance = SeedProvenance(
        source="both",
        fixture_version=fixture_version,
        input_data_description="test combined data",
        schema_version=schema_version,
        silver_dataset_version=silver_dataset_version,
        canonical_dataset_version=silver_dataset_version,
    )

    return SilverSeed(
        case_id=case_id,
        expected_route="both",
        expected_sources=["tmdb", "netflix"],
        expected_status="SUCCESS",
        hard_constraints=None,
        semantic_concepts=[],
        seed_item_ids=[],
        eligible_item_ids=None,
        difficulty=difficulty,
        tags=tags,
        provenance=provenance,
        fixture_version=None,
        tmdb_component=tmdb_component,
        netflix_component=netflix_component,
    )


def _build_out_of_scope_seed(
    case_id: str,
    difficulty: str,
    tags: list[str],
    schema_version: str,
    silver_dataset_version: str,
) -> st.SearchStrategy[SilverSeed]:
    """Build a valid 'out_of_scope' route seed."""
    provenance = SeedProvenance(
        source="synthetic",
        input_data_description="out of scope test seed",
        schema_version=schema_version,
        silver_dataset_version=silver_dataset_version,
    )

    return st.just(
        SilverSeed(
            case_id=case_id,
            expected_route="out_of_scope",
            expected_sources=[],
            expected_status="OUT_OF_SCOPE",
            hard_constraints=None,
            semantic_concepts=[],
            seed_item_ids=[],
            eligible_item_ids=None,
            difficulty=difficulty,
            tags=tags,
            provenance=provenance,
            fixture_version=None,
            tmdb_component=None,
            netflix_component=None,
        )
    )
