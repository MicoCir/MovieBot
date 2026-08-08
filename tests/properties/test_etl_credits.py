"""Property tests for credit deduplication and join (Properties 5, 6).

Tests the NetflixEtl._join_credits() method which handles:
- Deduplication of credits by (id, role, person_id) key
- Join between title documents and credit rows
- Name normalization via normalize_name

**Validates: Requirements 1.7, 1.8, 1.15, 1.17, 1.18**
"""

from __future__ import annotations

from pathlib import Path

from hypothesis import assume, given, settings
from hypothesis import strategies as st

from moviebot.etl.netflix_etl import EtlConfig, NetflixEtl
from moviebot.etl.transformers import normalize_name

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_etl_instance() -> NetflixEtl:
    """Create a minimal NetflixEtl instance to access _join_credits."""
    config = EtlConfig(
        titles_path=Path("dummy_titles.csv"),
        credits_path=Path("dummy_credits.csv"),
        output_base_dir=Path("dummy_output"),
        canonical_dataset_version="v_test",
        etl_version="1.0.0",
        schema_version="1.0.0",
    )
    return NetflixEtl(config)


# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------

# Valid Netflix IDs matching ^t[ms]\d+$
_valid_ids = st.builds(
    lambda prefix, digits: f"t{prefix}{digits}",
    st.sampled_from(["m", "s"]),
    st.integers(min_value=1, max_value=99999).map(str),
)

_roles = st.sampled_from(["actor", "director"])

_person_ids = st.integers(min_value=1, max_value=99999).map(str)

# Names that are non-empty after normalization (strip + lower)
_names = st.text(
    alphabet=st.characters(whitelist_categories=("L", "N", "Zs")),
    min_size=1,
    max_size=40,
).filter(lambda s: s.strip())


# A credit row dict as expected by _join_credits
@st.composite
def _credit_row(
    draw: st.DrawFn, ids: st.SearchStrategy[str] | None = None
) -> dict[str, str]:
    """Generate a single credit row dict."""
    credit_id = draw(ids if ids is not None else _valid_ids)
    role = draw(_roles)
    person_id = draw(_person_ids)
    name = draw(_names)
    return {
        "id": credit_id,
        "role": role,
        "person_id": person_id,
        "name": name,
    }


def _make_document(title_id: str) -> dict:
    """Create a minimal title document with the given id."""
    return {
        "id": title_id,
        "title": "Test Title",
        "type": "movie",
        "release_year": 2020,
        "description": None,
        "age_certification": None,
        "genres": [],
        "actors": [],
        "directors": [],
        "imdb_score": None,
        "tmdb_score": None,
        "tmdb_popularity": None,
    }


# ---------------------------------------------------------------------------
# Property 5: Deduplicación de créditos
# ---------------------------------------------------------------------------


@given(
    title_id=_valid_ids,
    role=_roles,
    person_id=_person_ids,
    names=st.lists(_names, min_size=2, max_size=10),
)
@settings(max_examples=200)
def test_property_5_dedup_keeps_lexicographically_smallest_name(
    title_id: str, role: str, person_id: str, names: list[str]
) -> None:
    """Property 5: Deduplicación de créditos.

    **Validates: Requirements 1.8**

    When multiple credits share the same (id, role, person_id) key but have
    different names, after deduplication only the lexicographically smallest
    normalized name is kept.
    """
    # Build duplicate credit rows with same key but different names
    credits_rows = [
        {"id": title_id, "role": role, "person_id": person_id, "name": name}
        for name in names
    ]

    # Build a document matching the title_id
    doc = _make_document(title_id)
    documents = [doc]

    etl = _make_etl_instance()
    etl._join_credits(documents, credits_rows)

    # Compute expected: lex-smallest normalized name
    normalized_names = [normalize_name(n) for n in names]
    # Filter out empty names (normalize_name may produce empty string)
    valid_normalized = [n for n in normalized_names if n]
    assume(len(valid_normalized) > 0)

    expected_name = min(valid_normalized)

    # Check the appropriate list
    if role == "actor":
        assert expected_name in doc["actors"], (
            f"Expected actor {expected_name!r} not in {doc['actors']}"
        )
        # Only one entry for this person_id
        assert doc["actors"].count(expected_name) == 1
    else:
        assert expected_name in doc["directors"], (
            f"Expected director {expected_name!r} not in {doc['directors']}"
        )
        assert doc["directors"].count(expected_name) == 1


@given(
    title_id=_valid_ids,
    person_id=_person_ids,
    names_actor=st.lists(_names, min_size=2, max_size=5),
    names_director=st.lists(_names, min_size=2, max_size=5),
)
@settings(max_examples=100)
def test_property_5_dedup_per_role_independent(
    title_id: str,
    person_id: str,
    names_actor: list[str],
    names_director: list[str],
) -> None:
    """Property 5 (supplement): Dedup is independent per role.

    **Validates: Requirements 1.8**

    Same (id, person_id) but different roles are treated as separate keys.
    """
    credits_rows = []
    for name in names_actor:
        credits_rows.append(
            {"id": title_id, "role": "actor", "person_id": person_id, "name": name}
        )
    for name in names_director:
        credits_rows.append(
            {"id": title_id, "role": "director", "person_id": person_id, "name": name}
        )

    doc = _make_document(title_id)
    documents = [doc]

    etl = _make_etl_instance()
    etl._join_credits(documents, credits_rows)

    # Each role should have exactly one entry for this person_id
    valid_actor_names = [normalize_name(n) for n in names_actor if normalize_name(n)]
    valid_director_names = [
        normalize_name(n) for n in names_director if normalize_name(n)
    ]
    assume(len(valid_actor_names) > 0 and len(valid_director_names) > 0)

    expected_actor = min(valid_actor_names)
    expected_director = min(valid_director_names)

    assert expected_actor in doc["actors"]
    assert expected_director in doc["directors"]


# ---------------------------------------------------------------------------
# Property 6: Join correcto entre titles y credits
# ---------------------------------------------------------------------------


@given(
    title_ids=st.lists(_valid_ids, min_size=1, max_size=5, unique=True),
    data=st.data(),
)
@settings(max_examples=200)
def test_property_6_join_contains_exactly_matching_credits(
    title_ids: list[str], data: st.DataObject
) -> None:
    """Property 6: Join correcto entre titles y credits.

    **Validates: Requirements 1.7, 1.15, 1.17**

    After join, each document's actors/directors contain exactly the
    deduplicated credits matching that document's id. Credits for
    non-existent titles are ignored.
    """
    documents = [_make_document(tid) for tid in title_ids]

    # Generate credits — some matching existing titles, some for non-existent IDs
    non_existent_id = "tm99999999"
    assume(non_existent_id not in title_ids)

    all_possible_ids = title_ids + [non_existent_id]
    credits_rows: list[dict[str, str]] = data.draw(
        st.lists(
            _credit_row(ids=st.sampled_from(all_possible_ids)),
            min_size=0,
            max_size=20,
        )
    )

    etl = _make_etl_instance()
    etl._join_credits(documents, credits_rows)

    # Manually compute expected results via dedup logic
    deduped: dict[tuple[str, str, str], str] = {}
    for row in credits_rows:
        credit_id = row["id"].strip()
        role = row["role"].strip().lower()
        pid = row["person_id"].strip()
        raw_name = row["name"]

        if credit_id not in title_ids:
            continue
        if role not in ("actor", "director"):
            continue
        normalized = normalize_name(raw_name)
        if not normalized:
            continue

        key = (credit_id, role, pid)
        if key not in deduped or normalized < deduped[key]:
            deduped[key] = normalized

    # Build expected actors/directors per document
    expected_actors: dict[str, set[str]] = {tid: set() for tid in title_ids}
    expected_directors: dict[str, set[str]] = {tid: set() for tid in title_ids}

    for (credit_id, role, _pid), name in deduped.items():
        if role == "actor":
            expected_actors[credit_id].add(name)
        elif role == "director":
            expected_directors[credit_id].add(name)

    # Verify each document
    for doc in documents:
        tid = doc["id"]
        actual_actors = set(doc["actors"])
        actual_directors = set(doc["directors"])

        assert actual_actors == expected_actors[tid], (
            f"Document {tid}: actors mismatch. "
            f"Got {actual_actors}, expected {expected_actors[tid]}"
        )
        assert actual_directors == expected_directors[tid], (
            f"Document {tid}: directors mismatch. "
            f"Got {actual_directors}, expected {expected_directors[tid]}"
        )


@given(title_ids=st.lists(_valid_ids, min_size=1, max_size=5, unique=True))
@settings(max_examples=100)
def test_property_6_no_credits_produces_empty_lists(title_ids: list[str]) -> None:
    """Property 6 (supplement): No credits → empty actor/director lists.

    **Validates: Requirements 1.18**

    When there are no credits for a title, the actors and directors
    lists remain empty.
    """
    documents = [_make_document(tid) for tid in title_ids]

    etl = _make_etl_instance()
    etl._join_credits(documents, [])

    for doc in documents:
        assert doc["actors"] == [], (
            f"Document {doc['id']} should have empty actors, got {doc['actors']}"
        )
        assert doc["directors"] == [], (
            f"Document {doc['id']} should have empty directors, got {doc['directors']}"
        )


@given(
    title_id=_valid_ids,
    data=st.data(),
)
@settings(max_examples=100)
def test_property_6_credits_for_nonexistent_titles_ignored(
    title_id: str, data: st.DataObject
) -> None:
    """Property 6 (supplement): Credits for non-existent titles are ignored.

    **Validates: Requirements 1.7**

    Credits referencing IDs not present in the documents list
    do not appear in any document.
    """
    # Document with one ID
    doc = _make_document(title_id)
    documents = [doc]

    # Generate credits for a different ID
    other_id = "tm00000000"
    assume(other_id != title_id)

    credits_rows: list[dict[str, str]] = data.draw(
        st.lists(
            _credit_row(ids=st.just(other_id)),
            min_size=1,
            max_size=10,
        )
    )

    etl = _make_etl_instance()
    etl._join_credits(documents, credits_rows)

    assert doc["actors"] == []
    assert doc["directors"] == []
