"""Shared Hypothesis strategies for property-based tests."""

from hypothesis import strategies as st

# --- TMDB Strategies ---


def tmdb_movie_object(
    *,
    require_id: bool = True,
    require_title: bool = True,
) -> st.SearchStrategy[dict]:
    """Generate a TMDB movie object (as returned in `results` array).

    Args:
        require_id: If True, always include a valid int `id`.
        require_title: If True, always include a valid str `title`.
    """
    id_strategy = (
        st.integers(min_value=1, max_value=10_000_000) if require_id else st.none()
    )
    title_strategy = (
        st.text(min_size=1, max_size=200).filter(lambda s: s.strip())
        if require_title
        else st.none()
    )

    return st.fixed_dictionaries(
        {
            "id": id_strategy,
            "title": title_strategy,
        },
        optional={
            "overview": st.one_of(st.none(), st.text(max_size=500)),
            "release_date": st.one_of(
                st.none(),
                st.just(""),
                st.dates().map(lambda d: d.isoformat()),
            ),
            "genre_ids": st.one_of(
                st.none(),
                st.lists(st.integers(min_value=1, max_value=99999), max_size=8),
            ),
            "popularity": st.one_of(
                st.none(),
                st.floats(min_value=0.0, max_value=10000.0, allow_nan=False),
            ),
            "vote_average": st.one_of(
                st.none(),
                st.floats(min_value=0.0, max_value=10.0, allow_nan=False),
            ),
        },
    )


def tmdb_response(
    min_results: int = 0, max_results: int = 20
) -> st.SearchStrategy[dict]:
    """Generate a full TMDB trending response dict with valid structure."""
    return st.fixed_dictionaries(
        {
            "page": st.just(1),
            "results": st.lists(
                tmdb_movie_object(),
                min_size=min_results,
                max_size=max_results,
            ),
            "total_pages": st.integers(min_value=1, max_value=100),
            "total_results": st.integers(min_value=0, max_value=2000),
        }
    )


# --- Netflix / Genre Strategies ---


def genre_list() -> st.SearchStrategy[list[str]]:
    """Generate a list of genre strings (lowercase, alphabetic)."""
    genre_name = st.from_regex(r"[a-z]{3,15}", fullmatch=True)
    return st.lists(genre_name, min_size=0, max_size=6, unique=True)


def genre_literal_string() -> st.SearchStrategy[str]:
    """Generate a Python literal representation of a genre list (e.g. \"['drama', 'crime']\")."""
    return genre_list().map(repr)
