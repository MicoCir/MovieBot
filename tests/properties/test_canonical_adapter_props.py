"""Property tests for CanonicalNetflixAdapter filtering (Properties 10, 11).

Tests the deterministic filter behavior of CanonicalNetflixAdapter using
Hypothesis to verify universal invariants hold across randomly generated
datasets and constraints.

**Validates: Requirements 3.4, 7.1, 7.5, 7.6, 7.7**
"""

from __future__ import annotations

import hashlib
import json
import tempfile
from pathlib import Path

from hypothesis import given, settings
from hypothesis import strategies as st

from moviebot.evals.silver.adapters import CanonicalNetflixAdapter
from moviebot.evals.silver.models import NetflixHardConstraints

# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------

# Pool of genres to draw from (lowercase, as required by schema)
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
    "crime",
    "western",
]

# Pool of actor names (lowercase)
_ACTOR_POOL = [
    "tom hanks",
    "meryl streep",
    "robert de niro",
    "cate blanchett",
    "leonardo dicaprio",
    "viola davis",
    "denzel washington",
    "scarlett johansson",
    "brad pitt",
    "emma stone",
]

# Pool of director names (lowercase)
_DIRECTOR_POOL = [
    "steven spielberg",
    "martin scorsese",
    "greta gerwig",
    "christopher nolan",
    "kathryn bigelow",
    "quentin tarantino",
    "denis villeneuve",
    "bong joon-ho",
]


@st.composite
def canonical_title_data(draw: st.DrawFn) -> dict:
    """Generate a valid CanonicalNetflixTitle as a dict.

    Conforms to schema: id matches ^t[ms]\\d+$, type is movie/show,
    release_year in [1888, 2100], genres/actors/directors are lowercase lists.
    """
    title_type = draw(st.sampled_from(["movie", "show"]))
    prefix = "tm" if title_type == "movie" else "ts"
    numeric_id = draw(st.integers(min_value=1, max_value=99999))
    title_id = f"{prefix}{numeric_id}"

    title_name = draw(
        st.text(
            alphabet=st.characters(whitelist_categories=("L", "N", "Zs")),
            min_size=1,
            max_size=50,
        ).filter(lambda s: s.strip())
    )

    release_year = draw(st.integers(min_value=1900, max_value=2024))
    genres = draw(
        st.lists(st.sampled_from(_GENRE_POOL), min_size=0, max_size=4, unique=True)
    )
    actors = draw(
        st.lists(st.sampled_from(_ACTOR_POOL), min_size=0, max_size=4, unique=True)
    )
    directors = draw(
        st.lists(st.sampled_from(_DIRECTOR_POOL), min_size=0, max_size=2, unique=True)
    )

    return {
        "id": title_id,
        "title": title_name.strip(),
        "type": title_type,
        "release_year": release_year,
        "genres": sorted(genres),
        "actors": sorted(actors),
        "directors": sorted(directors),
    }


@st.composite
def canonical_dataset(
    draw: st.DrawFn, min_size: int = 2, max_size: int = 15
) -> list[dict]:
    """Generate a list of unique canonical titles (unique by id)."""
    titles = draw(
        st.lists(canonical_title_data(), min_size=min_size, max_size=max_size)
    )
    # Deduplicate by id, keep first occurrence
    seen_ids: set[str] = set()
    unique_titles: list[dict] = []
    for t in titles:
        if t["id"] not in seen_ids:
            seen_ids.add(t["id"])
            unique_titles.append(t)
    # Must have at least 1 title
    if not unique_titles:
        # Force at least one valid title
        unique_titles.append(
            {
                "id": "tm1",
                "title": "Fallback Title",
                "type": "movie",
                "release_year": 2000,
                "genres": ["drama"],
                "actors": ["tom hanks"],
                "directors": ["steven spielberg"],
            }
        )
    return unique_titles


@st.composite
def netflix_hard_constraints(
    draw: st.DrawFn, dataset: list[dict]
) -> NetflixHardConstraints:
    """Generate random NetflixHardConstraints drawing from the dataset's actual values.

    This ensures constraints are meaningful (can potentially match something).
    """
    # Collect all values present in dataset
    all_genres: list[str] = []
    all_actors: list[str] = []
    all_directors: list[str] = []
    all_years: list[int] = []
    all_types: list[str] = []

    for t in dataset:
        all_genres.extend(t["genres"])
        all_actors.extend(t["actors"])
        all_directors.extend(t["directors"])
        all_years.append(t["release_year"])
        all_types.append(t["type"])

    all_genres = list(set(all_genres))
    all_actors = list(set(all_actors))
    all_directors = list(set(all_directors))

    # Type filter
    type_filter = draw(st.sampled_from([None, "movie", "show"]))

    # Genres filter (AND semantics - pick 0-3 from pool)
    if all_genres:
        genres = draw(
            st.lists(
                st.sampled_from(all_genres),
                min_size=0,
                max_size=min(3, len(all_genres)),
                unique=True,
            )
        )
    else:
        genres = []

    # Actors filter (OR semantics)
    if all_actors:
        actors = draw(
            st.lists(
                st.sampled_from(all_actors),
                min_size=0,
                max_size=min(3, len(all_actors)),
                unique=True,
            )
        )
    else:
        actors = []

    # Directors filter (OR semantics)
    if all_directors:
        directors = draw(
            st.lists(
                st.sampled_from(all_directors),
                min_size=0,
                max_size=min(2, len(all_directors)),
                unique=True,
            )
        )
    else:
        directors = []

    # Year range
    if all_years:
        min_year_val = min(all_years)
        max_year_val = max(all_years)
    else:
        min_year_val = 1900
        max_year_val = 2024

    use_min_year = draw(st.booleans())
    use_max_year = draw(st.booleans())

    min_year = (
        draw(st.integers(min_value=min_year_val - 5, max_value=max_year_val))
        if use_min_year
        else None
    )
    max_year = (
        draw(st.integers(min_value=min_year_val, max_value=max_year_val + 5))
        if use_max_year
        else None
    )

    # Clamp to valid range
    if min_year is not None:
        min_year = max(1888, min(2100, min_year))
    if max_year is not None:
        max_year = max(1888, min(2100, max_year))

    # Ensure min_year <= max_year
    if min_year is not None and max_year is not None and min_year > max_year:
        min_year, max_year = max_year, min_year

    return NetflixHardConstraints(
        type=type_filter,
        genres=genres,
        actors=actors,
        directors=directors,
        min_year=min_year,
        max_year=max_year,
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _create_adapter_from_titles(
    titles: list[dict], tmp_dir: Path
) -> CanonicalNetflixAdapter:
    """Create a CanonicalNetflixAdapter from a list of title dicts in a temp directory."""
    version = "test_v1"
    version_dir = tmp_dir / version
    version_dir.mkdir(parents=True, exist_ok=True)

    # Write titles.jsonl
    titles_path = version_dir / "titles.jsonl"
    lines = []
    for t in titles:
        lines.append(
            json.dumps(t, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
        )
    content = "\n".join(lines) + "\n"
    titles_path.write_text(content, encoding="utf-8")

    # Compute checksum
    raw_bytes = titles_path.read_bytes()
    checksum = hashlib.sha256(raw_bytes).hexdigest()

    # Write metadata.json
    metadata = {
        "canonical_dataset_version": version,
        "etl_version": "1.0.0",
        "schema_version": "1.0.0",
        "document_count": len(titles),
        "discarded_count": 0,
        "source_checksums": {
            "titles.csv": "a" * 64,
            "credits.csv": "b" * 64,
        },
        "output_checksum_sha256": checksum,
        "generated_at": "2024-01-01T00:00:00Z",
        "type_distribution": {
            "movie": sum(1 for t in titles if t["type"] == "movie"),
            "show": sum(1 for t in titles if t["type"] == "show"),
        },
    }
    metadata_path = version_dir / "metadata.json"
    metadata_path.write_text(
        json.dumps(metadata, sort_keys=True, separators=(",", ":"), ensure_ascii=False),
        encoding="utf-8",
    )

    return CanonicalNetflixAdapter(
        canonical_dataset_version=version,
        base_dir=tmp_dir,
    )


def _manual_filter(
    titles: list[dict], constraints: NetflixHardConstraints
) -> list[str] | None:
    """Reference implementation: exhaustive filter matching the adapter semantics.

    - genres: AND (title must have ALL specified genres)
    - actors: OR (title must have at least ONE specified actor)
    - directors: OR (title must have at least ONE specified director)
    - type: exact match (None = no filter)
    - min_year/max_year: range filter
    - Returns sorted IDs or None if is_default()
    """
    if constraints.is_default():
        return None

    filter_genres = {g.lower() for g in constraints.genres}
    filter_actors = {a.lower() for a in constraints.actors}
    filter_directors = {d.lower() for d in constraints.directors}

    result_ids: list[str] = []

    for title in titles:
        # Type filter
        if constraints.type is not None and title["type"] != constraints.type:
            continue

        # Genres AND
        if filter_genres:
            title_genres = {g.lower() for g in title["genres"]}
            if not filter_genres.issubset(title_genres):
                continue

        # min_year
        if (
            constraints.min_year is not None
            and title["release_year"] < constraints.min_year
        ):
            continue

        # max_year
        if (
            constraints.max_year is not None
            and title["release_year"] > constraints.max_year
        ):
            continue

        # Actors OR
        if filter_actors:
            title_actors = {a.lower() for a in title["actors"]}
            if not filter_actors.intersection(title_actors):
                continue

        # Directors OR
        if filter_directors:
            title_directors = {d.lower() for d in title["directors"]}
            if not filter_directors.intersection(title_directors):
                continue

        result_ids.append(title["id"])

    return sorted(result_ids)


# ---------------------------------------------------------------------------
# Property 10: Filtrado exhaustivo del Adapter Canónico
# ---------------------------------------------------------------------------


@given(data=st.data())
@settings(max_examples=50, deadline=None)
def test_property_10_filter_returns_exactly_matching_ids_sorted(
    data: st.DataObject,
) -> None:
    """Property 10: Filtrado exhaustivo del Adapter Canónico.

    **Validates: Requirements 3.4, 7.1, 7.5, 7.6, 7.7**

    For any dataset and any non-default constraints:
    - filter() returns exactly the IDs that match ALL constraints
    - genres use AND semantics (must have ALL)
    - actors use OR semantics (must have at least ONE)
    - directors use OR semantics (must have at least ONE)
    - Result is sorted in lexicographic ascending order
    """
    titles = data.draw(canonical_dataset(), label="dataset")
    constraints = data.draw(netflix_hard_constraints(titles), label="constraints")

    # Skip default constraints (covered by Property 11)
    if constraints.is_default():
        return

    with tempfile.TemporaryDirectory() as tmp_dir:
        adapter = _create_adapter_from_titles(titles, Path(tmp_dir))
        actual = adapter.filter(constraints)
        expected = _manual_filter(titles, constraints)

        assert actual == expected, (
            f"Filter mismatch!\n"
            f"Constraints: {constraints}\n"
            f"Expected: {expected}\n"
            f"Actual: {actual}\n"
            f"Dataset size: {len(titles)}"
        )


@given(data=st.data())
@settings(max_examples=30, deadline=None)
def test_property_10_result_is_always_sorted(data: st.DataObject) -> None:
    """Property 10 (supplement): filter() result is always sorted lexicographically.

    **Validates: Requirements 3.4, 7.5**

    Regardless of constraints, the returned list is always in sorted order.
    """
    titles = data.draw(canonical_dataset(), label="dataset")
    constraints = data.draw(netflix_hard_constraints(titles), label="constraints")

    if constraints.is_default():
        return

    with tempfile.TemporaryDirectory() as tmp_dir:
        adapter = _create_adapter_from_titles(titles, Path(tmp_dir))
        result = adapter.filter(constraints)

        assert result is not None
        assert result == sorted(result), f"Result not sorted: {result}"


@given(data=st.data())
@settings(max_examples=30, deadline=None)
def test_property_10_genres_and_semantics(data: st.DataObject) -> None:
    """Property 10 (supplement): genres use AND semantics.

    **Validates: Requirements 3.4, 7.7**

    When filtering by multiple genres, only titles with ALL specified genres
    are included in the result.
    """
    titles = data.draw(canonical_dataset(min_size=3, max_size=12), label="dataset")

    # Collect genres from dataset
    all_genres = list({g for t in titles for g in t["genres"]})
    if len(all_genres) < 2:
        return  # Need at least 2 genres to test AND semantics

    # Pick 2 genres for AND filter
    chosen_genres = data.draw(
        st.lists(
            st.sampled_from(all_genres),
            min_size=2,
            max_size=min(3, len(all_genres)),
            unique=True,
        ),
        label="genres",
    )

    constraints = NetflixHardConstraints(genres=chosen_genres)

    with tempfile.TemporaryDirectory() as tmp_dir:
        adapter = _create_adapter_from_titles(titles, Path(tmp_dir))
        result = adapter.filter(constraints)

        assert result is not None
        # Every returned title must have ALL genres
        for title_id in result:
            title_data = next(t for t in titles if t["id"] == title_id)
            title_genres_lower = {g.lower() for g in title_data["genres"]}
            for g in chosen_genres:
                assert g.lower() in title_genres_lower, (
                    f"Title {title_id} missing genre '{g}' but was included in results"
                )


@given(data=st.data())
@settings(max_examples=30, deadline=None)
def test_property_10_actors_or_semantics(data: st.DataObject) -> None:
    """Property 10 (supplement): actors use OR semantics.

    **Validates: Requirements 3.4, 7.7**

    When filtering by multiple actors, titles with at least ONE of the
    specified actors are included.
    """
    titles = data.draw(canonical_dataset(min_size=3, max_size=12), label="dataset")

    # Collect actors from dataset
    all_actors = list({a for t in titles for a in t["actors"]})
    if len(all_actors) < 2:
        return  # Need at least 2 actors to test OR semantics

    chosen_actors = data.draw(
        st.lists(
            st.sampled_from(all_actors),
            min_size=2,
            max_size=min(3, len(all_actors)),
            unique=True,
        ),
        label="actors",
    )

    constraints = NetflixHardConstraints(actors=chosen_actors)

    with tempfile.TemporaryDirectory() as tmp_dir:
        adapter = _create_adapter_from_titles(titles, Path(tmp_dir))
        result = adapter.filter(constraints)

        assert result is not None
        # Every returned title must have at least ONE actor from the filter
        filter_actors_set = {a.lower() for a in chosen_actors}
        for title_id in result:
            title_data = next(t for t in titles if t["id"] == title_id)
            title_actors_lower = {a.lower() for a in title_data["actors"]}
            assert filter_actors_set.intersection(title_actors_lower), (
                f"Title {title_id} has no matching actors but was included. "
                f"Title actors: {title_data['actors']}, filter: {chosen_actors}"
            )


@given(data=st.data())
@settings(max_examples=30, deadline=None)
def test_property_10_directors_or_semantics(data: st.DataObject) -> None:
    """Property 10 (supplement): directors use OR semantics.

    **Validates: Requirements 3.4, 7.7**

    When filtering by multiple directors, titles with at least ONE of the
    specified directors are included.
    """
    titles = data.draw(canonical_dataset(min_size=3, max_size=12), label="dataset")

    # Collect directors from dataset
    all_directors = list({d for t in titles for d in t["directors"]})
    if len(all_directors) < 2:
        return  # Need at least 2 directors to test OR semantics

    chosen_directors = data.draw(
        st.lists(
            st.sampled_from(all_directors),
            min_size=2,
            max_size=min(2, len(all_directors)),
            unique=True,
        ),
        label="directors",
    )

    constraints = NetflixHardConstraints(directors=chosen_directors)

    with tempfile.TemporaryDirectory() as tmp_dir:
        adapter = _create_adapter_from_titles(titles, Path(tmp_dir))
        result = adapter.filter(constraints)

        assert result is not None
        # Every returned title must have at least ONE director from the filter
        filter_directors_set = {d.lower() for d in chosen_directors}
        for title_id in result:
            title_data = next(t for t in titles if t["id"] == title_id)
            title_directors_lower = {d.lower() for d in title_data["directors"]}
            assert filter_directors_set.intersection(title_directors_lower), (
                f"Title {title_id} has no matching directors but was included. "
                f"Title directors: {title_data['directors']}, filter: {chosen_directors}"
            )


# ---------------------------------------------------------------------------
# Property 11: Default constraints produce eligible None
# ---------------------------------------------------------------------------


@given(titles_data=canonical_dataset())
@settings(max_examples=30, deadline=None)
def test_property_11_default_constraints_return_none(titles_data: list[dict]) -> None:
    """Property 11: Default constraints produce eligible None.

    **Validates: Requirements 7.6**

    When constraints.is_default() is True, filter() returns None
    (indicating no filtering was applied, eligible_item_ids is None).
    """
    constraints = NetflixHardConstraints()  # All defaults
    assert constraints.is_default()

    with tempfile.TemporaryDirectory() as tmp_dir:
        adapter = _create_adapter_from_titles(titles_data, Path(tmp_dir))
        result = adapter.filter(constraints)

        assert result is None, f"Expected None for default constraints, got: {result}"


@given(
    titles_data=canonical_dataset(),
    type_val=st.sampled_from([None, "movie", "show"]),
    genres=st.just([]),
    actors=st.just([]),
    directors=st.just([]),
)
@settings(max_examples=20, deadline=None)
def test_property_11_only_truly_default_returns_none(
    titles_data: list[dict],
    type_val: str | None,
    genres: list[str],
    actors: list[str],
    directors: list[str],
) -> None:
    """Property 11 (supplement): Only truly default constraints return None.

    **Validates: Requirements 7.6**

    is_default() is True only when ALL fields are at their default values.
    If any field is non-default, filter returns a list (possibly empty).
    """
    constraints = NetflixHardConstraints(
        type=type_val,
        genres=genres,
        actors=actors,
        directors=directors,
    )

    with tempfile.TemporaryDirectory() as tmp_dir:
        adapter = _create_adapter_from_titles(titles_data, Path(tmp_dir))
        result = adapter.filter(constraints)

        if constraints.is_default():
            assert result is None
        else:
            assert isinstance(result, list), (
                f"Non-default constraints should return a list, got None. "
                f"Constraints: {constraints}"
            )
