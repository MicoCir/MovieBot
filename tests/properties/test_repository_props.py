"""Property tests for MeilisearchNetflixRepository (Properties 12, 13).

Tests the filter construction and hit-to-candidate mapping of
MeilisearchNetflixRepository using Hypothesis to verify universal
invariants hold across randomly generated queries and hits.

**Validates: Requirements 6.5, 6.7, 6.8, 6.9, 6.11, 6.12, 6.15**
"""

from __future__ import annotations

from hypothesis import assume, given, settings
from hypothesis import strategies as st

from moviebot.agents.netflix.models import NetflixQuery
from moviebot.common.models import MovieCandidate
from moviebot.repositories.netflix_meilisearch import MeilisearchNetflixRepository

# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------

# Pool of genre names (some with spaces, accents, mixed case to test normalization)
_GENRE_POOL = [
    "Action",
    "Comedy",
    "Drama",
    "horror",
    "Romance",
    "Science Fiction",
    "  thriller  ",
    "DOCUMENTARY",
    "animation",
    "Fantasy",
]

# Pool of actor names (mixed case, whitespace to test normalization)
_ACTOR_POOL = [
    "Tom Hanks",
    "  Meryl Streep  ",
    "robert de niro",
    "CATE BLANCHETT",
    "Leonardo DiCaprio",
    "Viola Davis",
]

# Pool of director names (mixed case, whitespace to test normalization)
_DIRECTOR_POOL = [
    "Steven Spielberg",
    "  martin scorsese ",
    "GRETA GERWIG",
    "Christopher Nolan",
    "Kathryn Bigelow",
]

# Names with special characters that need escaping
_SPECIAL_CHAR_NAMES = [
    'O"Brien',
    "Jean-Luc Picard",
    "O'Connor",
    'She said "hello"',
    "back\\slash",
    'quote\\"escaped',
]


@st.composite
def netflix_query_with_filters(draw: st.DrawFn) -> NetflixQuery:
    """Generate a NetflixQuery with at least one non-empty filter field.

    Ensures generated queries exercise the filter construction logic.
    """
    query_type = draw(st.sampled_from(["movie", "show", "any"]))
    genres = draw(
        st.lists(st.sampled_from(_GENRE_POOL), min_size=0, max_size=4, unique=True)
    )
    actors = draw(
        st.lists(st.sampled_from(_ACTOR_POOL), min_size=0, max_size=3, unique=True)
    )
    directors = draw(
        st.lists(st.sampled_from(_DIRECTOR_POOL), min_size=0, max_size=3, unique=True)
    )

    # Ensure at least one filter is present
    assume(genres or actors or directors or query_type != "any")

    return NetflixQuery(
        semantic_query="",
        type=query_type,
        genres=genres,
        actors=actors,
        directors=directors,
    )


@st.composite
def netflix_query_with_special_chars(draw: st.DrawFn) -> NetflixQuery:
    """Generate a NetflixQuery with names containing special characters."""
    actors = draw(
        st.lists(
            st.sampled_from(_SPECIAL_CHAR_NAMES), min_size=1, max_size=3, unique=True
        )
    )
    directors = draw(
        st.lists(
            st.sampled_from(_SPECIAL_CHAR_NAMES), min_size=0, max_size=2, unique=True
        )
    )

    return NetflixQuery(
        semantic_query="",
        type="any",
        genres=[],
        actors=actors,
        directors=directors,
    )


@st.composite
def meilisearch_hit(draw: st.DrawFn) -> dict:
    """Generate a valid Meilisearch hit dict for mapping tests.

    Produces hits that conform to the expected structure from Meilisearch.
    """
    title_type = draw(st.sampled_from(["movie", "show"]))
    prefix = "tm" if title_type == "movie" else "ts"
    numeric_id = draw(st.integers(min_value=1, max_value=99999))
    hit_id = f"{prefix}{numeric_id}"

    title = draw(
        st.text(
            alphabet=st.characters(whitelist_categories=("L", "N", "Zs")),
            min_size=1,
            max_size=100,
        ).filter(lambda s: s.strip())
    )

    # Description: either present or absent
    has_description = draw(st.booleans())
    description = (
        draw(st.text(min_size=1, max_size=200).filter(lambda s: s.strip()))
        if has_description
        else None
    )

    release_year = draw(st.integers(min_value=1900, max_value=2024))

    genres = draw(
        st.lists(
            st.sampled_from(["drama", "comedy", "action", "horror", "romance"]),
            min_size=0,
            max_size=4,
            unique=True,
        )
    )

    hit: dict = {
        "id": hit_id,
        "title": title.strip(),
        "type": title_type,
        "release_year": release_year,
        "genres": genres,
    }

    if description is not None:
        hit["description"] = description

    return hit


# ---------------------------------------------------------------------------
# Helper: instantiate repository without real connection
# ---------------------------------------------------------------------------


def _create_repository() -> MeilisearchNetflixRepository:
    """Create a repository instance for testing pure methods.

    We use a dummy URL since we only test _build_filter and _map_hit_to_candidate
    which don't require a real Meilisearch connection.
    """
    return MeilisearchNetflixRepository(
        meilisearch_url="http://localhost:7700",
        meilisearch_api_key=None,
        index_name="netflix_test",
    )


# ---------------------------------------------------------------------------
# Property 12: Construcción correcta de filtros Meilisearch
# ---------------------------------------------------------------------------


@given(query=netflix_query_with_filters())
@settings(max_examples=100, deadline=None)
def test_property_12_genres_use_and_semantics(query: NetflixQuery) -> None:
    """Property 12: Genres in filter use AND between them.

    **Validates: Requirements 6.5**

    Each genre appears as `genres = "X"` and multiple genres are joined with AND.
    Values are lowercase and trimmed.
    """
    if not query.genres:
        return

    repo = _create_repository()
    filter_expr = repo._build_filter(query)

    assert filter_expr is not None

    # Each genre must appear as a separate `genres = "..."` clause
    for genre in query.genres:
        normalized = genre.strip().lower()
        escaped = MeilisearchNetflixRepository._escape_filter_value(normalized)
        expected_clause = f'genres = "{escaped}"'
        assert expected_clause in filter_expr, (
            f"Missing genre clause '{expected_clause}' in filter: {filter_expr}"
        )

    # If multiple genres, they must be joined with AND (not OR)
    if len(query.genres) > 1:
        # Count occurrences of 'genres = "' to verify all are present
        genre_clauses_count = filter_expr.count('genres = "')
        assert genre_clauses_count == len(query.genres), (
            f"Expected {len(query.genres)} genre clauses, found {genre_clauses_count}. "
            f"Filter: {filter_expr}"
        )
        # No OR between genre clauses — verify by checking the substring between them
        # doesn't have OR connecting two genre clauses
        parts = filter_expr.split('genres = "')
        for i in range(2, len(parts)):
            # The part before this genre clause should NOT end with " OR "
            preceding = parts[i - 1]
            assert not preceding.rstrip().endswith("OR"), (
                f"Found OR between genre clauses. Filter: {filter_expr}"
            )


@given(query=netflix_query_with_filters())
@settings(max_examples=100, deadline=None)
def test_property_12_actors_use_or_semantics(query: NetflixQuery) -> None:
    """Property 12: Actors in filter use OR between them.

    **Validates: Requirements 6.7**

    Each actor appears as `actors = "X"` and multiple actors are joined with OR.
    Values are lowercase and trimmed.
    """
    if not query.actors:
        return

    repo = _create_repository()
    filter_expr = repo._build_filter(query)

    assert filter_expr is not None

    # Each actor must appear with normalized value
    for actor in query.actors:
        normalized = actor.strip().lower()
        escaped = MeilisearchNetflixRepository._escape_filter_value(normalized)
        expected_clause = f'actors = "{escaped}"'
        assert expected_clause in filter_expr, (
            f"Missing actor clause '{expected_clause}' in filter: {filter_expr}"
        )

    # If multiple actors, they must be joined with OR
    if len(query.actors) > 1:
        # Extract the actors sub-expression
        actor_clauses = [
            f'actors = "{MeilisearchNetflixRepository._escape_filter_value(a.strip().lower())}"'
            for a in query.actors
        ]
        # Verify OR joins them
        or_joined = " OR ".join(actor_clauses)
        assert or_joined in filter_expr or f"({or_joined})" in filter_expr, (
            f"Actors not properly OR-joined. Expected: {or_joined}\nFilter: {filter_expr}"
        )


@given(query=netflix_query_with_filters())
@settings(max_examples=100, deadline=None)
def test_property_12_directors_use_or_semantics(query: NetflixQuery) -> None:
    """Property 12: Directors in filter use OR between them.

    **Validates: Requirements 6.8**

    Each director appears as `directors = "X"` and multiple directors are joined with OR.
    Values are lowercase and trimmed.
    """
    if not query.directors:
        return

    repo = _create_repository()
    filter_expr = repo._build_filter(query)

    assert filter_expr is not None

    # Each director must appear with normalized value
    for director in query.directors:
        normalized = director.strip().lower()
        escaped = MeilisearchNetflixRepository._escape_filter_value(normalized)
        expected_clause = f'directors = "{escaped}"'
        assert expected_clause in filter_expr, (
            f"Missing director clause '{expected_clause}' in filter: {filter_expr}"
        )

    # If multiple directors, they must be joined with OR
    if len(query.directors) > 1:
        director_clauses = [
            f'directors = "{MeilisearchNetflixRepository._escape_filter_value(d.strip().lower())}"'
            for d in query.directors
        ]
        or_joined = " OR ".join(director_clauses)
        assert or_joined in filter_expr or f"({or_joined})" in filter_expr, (
            f"Directors not properly OR-joined. Expected: {or_joined}\nFilter: {filter_expr}"
        )


@given(query=netflix_query_with_filters())
@settings(max_examples=100, deadline=None)
def test_property_12_actors_and_directors_combined_with_and(
    query: NetflixQuery,
) -> None:
    """Property 12: When both actors and directors present, they combine with AND inter-field.

    **Validates: Requirements 6.9**

    The actors group and directors group are combined with AND.
    """
    if not query.actors or not query.directors:
        return

    repo = _create_repository()
    filter_expr = repo._build_filter(query)

    assert filter_expr is not None

    # Build expected actors expression
    actor_clauses = [
        f'actors = "{MeilisearchNetflixRepository._escape_filter_value(a.strip().lower())}"'
        for a in query.actors
    ]
    if len(actor_clauses) == 1:
        actors_expr = actor_clauses[0]
    else:
        actors_expr = f"({' OR '.join(actor_clauses)})"

    # Build expected directors expression
    director_clauses = [
        f'directors = "{MeilisearchNetflixRepository._escape_filter_value(d.strip().lower())}"'
        for d in query.directors
    ]
    if len(director_clauses) == 1:
        directors_expr = director_clauses[0]
    else:
        directors_expr = f"({' OR '.join(director_clauses)})"

    # They must be combined with AND
    combined = f"{actors_expr} AND {directors_expr}"
    assert combined in filter_expr, (
        f"Actors and directors not combined with AND.\n"
        f"Expected: {combined}\n"
        f"Filter: {filter_expr}"
    )


@given(query=netflix_query_with_filters())
@settings(max_examples=100, deadline=None)
def test_property_12_all_values_lowercase_and_trimmed(query: NetflixQuery) -> None:
    """Property 12: All filter values are lowercase and trimmed.

    **Validates: Requirements 6.7, 6.8, 6.15**

    No filter value in the output should have leading/trailing whitespace
    or uppercase characters (for genre/actor/director values).
    """
    repo = _create_repository()
    filter_expr = repo._build_filter(query)

    if filter_expr is None:
        return

    # Extract all quoted values from the filter expression
    import re

    # Match values inside quotes: field = "value"
    quoted_values = re.findall(
        r'(?:genres|actors|directors) = "([^"]*(?:\\.[^"]*)*)"', filter_expr
    )

    for value in quoted_values:
        # Unescape for checking (backslash sequences)
        unescaped = value.replace('\\"', '"').replace("\\\\", "\\")
        assert unescaped == unescaped.strip(), (
            f"Value has leading/trailing whitespace: '{unescaped}' in filter: {filter_expr}"
        )
        assert unescaped == unescaped.lower(), (
            f"Value not lowercase: '{unescaped}' in filter: {filter_expr}"
        )


@given(query=netflix_query_with_special_chars())
@settings(max_examples=50, deadline=None)
def test_property_12_special_characters_properly_escaped(query: NetflixQuery) -> None:
    """Property 12: Special characters in values are properly escaped.

    **Validates: Requirements 6.15**

    Double quotes and backslashes in filter values are escaped.
    The filter expression remains well-formed.
    """
    repo = _create_repository()
    filter_expr = repo._build_filter(query)

    assert filter_expr is not None

    # Verify the filter expression has balanced quotes
    # Count unescaped double quotes (not preceded by backslash)
    import re

    unescaped_quotes = re.findall(r'(?<!\\)"', filter_expr)
    assert len(unescaped_quotes) % 2 == 0, (
        f"Unbalanced quotes in filter expression: {filter_expr}"
    )

    # Verify each value is properly escaped
    for name in query.actors + query.directors:
        normalized = name.strip().lower()
        escaped = MeilisearchNetflixRepository._escape_filter_value(normalized)
        # The escaped value must appear between quotes in the filter
        assert f'"{escaped}"' in filter_expr, (
            f"Escaped value '\"{escaped}\"' not found in filter: {filter_expr}"
        )


# ---------------------------------------------------------------------------
# Property 13: Mapeo correcto de hits a MovieCandidate
# ---------------------------------------------------------------------------


@given(hit=meilisearch_hit())
@settings(max_examples=100, deadline=None)
def test_property_13_id_matches_hit_id(hit: dict) -> None:
    """Property 13: MovieCandidate.id matches hit["id"].

    **Validates: Requirements 6.12**
    """
    repo = _create_repository()
    candidate = repo._map_hit_to_candidate(hit)

    assert candidate.id == hit["id"]


@given(hit=meilisearch_hit())
@settings(max_examples=100, deadline=None)
def test_property_13_source_is_netflix(hit: dict) -> None:
    """Property 13: MovieCandidate.source is always "netflix".

    **Validates: Requirements 6.12**
    """
    repo = _create_repository()
    candidate = repo._map_hit_to_candidate(hit)

    assert candidate.source == "netflix"


@given(hit=meilisearch_hit())
@settings(max_examples=100, deadline=None)
def test_property_13_content_type_matches_hit_type(hit: dict) -> None:
    """Property 13: MovieCandidate.content_type matches hit["type"].

    **Validates: Requirements 6.12**
    """
    repo = _create_repository()
    candidate = repo._map_hit_to_candidate(hit)

    assert candidate.content_type == hit["type"]


@given(hit=meilisearch_hit())
@settings(max_examples=100, deadline=None)
def test_property_13_genres_matches_hit_genres(hit: dict) -> None:
    """Property 13: MovieCandidate.genres matches hit["genres"].

    **Validates: Requirements 6.12**
    """
    repo = _create_repository()
    candidate = repo._map_hit_to_candidate(hit)

    assert candidate.genres == hit.get("genres", [])


@given(hit=meilisearch_hit())
@settings(max_examples=100, deadline=None)
def test_property_13_popularity_and_vote_average_are_none(hit: dict) -> None:
    """Property 13: MovieCandidate.popularity and vote_average are always None.

    **Validates: Requirements 6.12**
    """
    repo = _create_repository()
    candidate = repo._map_hit_to_candidate(hit)

    assert candidate.popularity is None
    assert candidate.vote_average is None


@given(hit=meilisearch_hit())
@settings(max_examples=100, deadline=None)
def test_property_13_all_fields_correctly_mapped(hit: dict) -> None:
    """Property 13: Complete mapping verification — all fields correct.

    **Validates: Requirements 6.12**

    Comprehensive check that the full mapping is correct:
    - id → hit["id"]
    - title → hit["title"]
    - description → hit.get("description") or None
    - release_year → hit.get("release_year")
    - genres → hit.get("genres", [])
    - source → "netflix"
    - content_type → hit["type"]
    - popularity → None
    - vote_average → None
    """
    repo = _create_repository()
    candidate = repo._map_hit_to_candidate(hit)

    assert isinstance(candidate, MovieCandidate)
    assert candidate.id == hit["id"]
    assert candidate.title == hit["title"]
    assert candidate.description == hit.get("description")
    assert candidate.release_year == hit.get("release_year")
    assert candidate.genres == hit.get("genres", [])
    assert candidate.source == "netflix"
    assert candidate.content_type == hit["type"]
    assert candidate.popularity is None
    assert candidate.vote_average is None
