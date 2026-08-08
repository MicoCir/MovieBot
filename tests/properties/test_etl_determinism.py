"""Property test for ETL determinism (Property 1).

Verifies that two runs of the ETL pipeline with identical input CSVs produce
byte-for-byte identical outputs for titles.jsonl and quality_report.json.

**Validates: Requirements 1.2**
"""

from __future__ import annotations

import hashlib
import tempfile
from pathlib import Path

from hypothesis import given, settings
from hypothesis import strategies as st

from moviebot.etl.netflix_etl import EtlConfig, NetflixEtl

# ---------------------------------------------------------------------------
# Strategies for generating valid CSV content
# ---------------------------------------------------------------------------

_TITLES_HEADER = "id,title,type,release_year,description,age_certification,genres,imdb_score,tmdb_score,tmdb_popularity"
_CREDITS_HEADER = "id,role,person_id,name,character"

# Valid Netflix IDs: tm or ts followed by digits
_valid_id = st.builds(
    lambda prefix, num: f"{prefix}{num}",
    st.sampled_from(["tm", "ts"]),
    st.integers(min_value=1, max_value=99999),
)

# Valid types for titles
_valid_type = st.sampled_from(["MOVIE", "Show", "movie", "SHOW", "Movie", "show"])

# Valid release years
_valid_year = st.integers(min_value=1888, max_value=2100)

# Simple text without commas or quotes (safe for CSV without quoting)
_safe_text = st.text(
    alphabet=st.characters(
        whitelist_categories=("L", "N", "Zs"),
        blacklist_characters=',"\r\n',
    ),
    min_size=1,
    max_size=50,
).filter(lambda s: s.strip())

# Optional description
_optional_description = st.one_of(st.just(""), _safe_text)

# Optional age certification
_optional_age_cert = st.one_of(
    st.just(""),
    st.sampled_from(["PG", "PG-13", "R", "TV-MA", "TV-14", "G"]),
)

# Genres as Python list literal string (safe for CSV)
_genre_names = st.sampled_from(
    [
        "drama",
        "comedy",
        "action",
        "thriller",
        "horror",
        "romance",
        "documentary",
        "animation",
        "crime",
        "fantasy",
    ]
)
_genres_literal = st.lists(_genre_names, min_size=0, max_size=4, unique=True).map(repr)

# Optional float scores
_optional_score = st.one_of(
    st.just(""),
    st.floats(min_value=0.0, max_value=10.0, allow_nan=False, allow_infinity=False).map(
        lambda f: f"{f:.2f}"
    ),
)

_optional_popularity = st.one_of(
    st.just(""),
    st.floats(
        min_value=0.0, max_value=9999.0, allow_nan=False, allow_infinity=False
    ).map(lambda f: f"{f:.2f}"),
)


@st.composite
def _title_row(draw: st.DrawFn) -> tuple[str, str]:
    """Generate a valid title CSV row and the id used."""
    title_id = draw(_valid_id)
    title = draw(_safe_text)
    title_type = draw(_valid_type)
    year = draw(_valid_year)
    description = draw(_optional_description)
    age_cert = draw(_optional_age_cert)
    genres = draw(_genres_literal)
    imdb = draw(_optional_score)
    tmdb_score = draw(_optional_score)
    tmdb_pop = draw(_optional_popularity)

    row = f"{title_id},{title},{title_type},{year},{description},{age_cert},{genres},{imdb},{tmdb_score},{tmdb_pop}"
    return (row, title_id)


# Roles for credits
_valid_role = st.sampled_from(["ACTOR", "DIRECTOR", "actor", "director"])

# Person names
_person_name = st.text(
    alphabet=st.characters(
        whitelist_categories=("L", "Zs"),
        blacklist_characters=',"\r\n',
    ),
    min_size=2,
    max_size=30,
).filter(lambda s: s.strip())

_person_id = st.integers(min_value=1, max_value=99999).map(str)

_optional_character = st.one_of(st.just(""), _safe_text)


@st.composite
def _credit_row(draw: st.DrawFn, title_ids: list[str]) -> str:
    """Generate a valid credit CSV row for one of the given title IDs."""
    credit_id = draw(st.sampled_from(title_ids))
    role = draw(_valid_role)
    person = draw(_person_id)
    name = draw(_person_name)
    character = draw(_optional_character)

    return f"{credit_id},{role},{person},{name},{character}"


@st.composite
def _csv_data(draw: st.DrawFn) -> tuple[str, str]:
    """Generate titles CSV content and credits CSV content.

    Returns (titles_csv, credits_csv).
    """
    # Generate between 1 and 10 title rows
    num_titles = draw(st.integers(min_value=1, max_value=10))
    title_rows_and_ids: list[tuple[str, str]] = []
    for _ in range(num_titles):
        title_rows_and_ids.append(draw(_title_row()))

    title_rows = [row for row, _ in title_rows_and_ids]
    title_ids = [tid for _, tid in title_rows_and_ids]

    # Generate between 0 and 15 credit rows referencing the title IDs
    num_credits = draw(st.integers(min_value=0, max_value=15))
    credit_rows: list[str] = []
    for _ in range(num_credits):
        credit_rows.append(draw(_credit_row(title_ids)))

    titles_csv = _TITLES_HEADER + "\n" + "\n".join(title_rows) + "\n"
    credits_csv = _CREDITS_HEADER + "\n" + "\n".join(credit_rows) + "\n"

    return (titles_csv, credits_csv)


def _sha256_of_file(path: Path) -> str:
    """Compute SHA-256 hex digest of a file."""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while True:
            chunk = f.read(65536)
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()


def _run_etl(titles_csv: str, credits_csv: str, base_dir: Path, version: str) -> Path:
    """Run the ETL pipeline with the given CSV content and return the output dir."""
    titles_path = base_dir / "titles.csv"
    credits_path = base_dir / "credits.csv"
    output_base = base_dir / "output"

    titles_path.write_text(titles_csv, encoding="utf-8")
    credits_path.write_text(credits_csv, encoding="utf-8")

    config = EtlConfig(
        titles_path=titles_path,
        credits_path=credits_path,
        output_base_dir=output_base,
        canonical_dataset_version=version,
        etl_version="1.0.0",
        schema_version="1.0.0",
    )

    etl = NetflixEtl(config)
    result = etl.run()
    return result.output_dir


# ---------------------------------------------------------------------------
# Property 1: Determinismo del ETL
# ---------------------------------------------------------------------------


@given(csv_data=_csv_data())
@settings(max_examples=50, deadline=30000)
def test_property_1_etl_determinism(csv_data: tuple[str, str]) -> None:
    """Property 1: Determinismo del ETL.

    **Validates: Requirements 1.2**

    Two runs of the ETL with the same input CSVs produce identical SHA-256
    checksums for titles.jsonl and quality_report.json.
    Note: metadata.json may differ in `generated_at` field, so we don't check it.
    """
    titles_csv, credits_csv = csv_data

    # Run 1
    with tempfile.TemporaryDirectory() as tmp1:
        output_dir_1 = _run_etl(titles_csv, credits_csv, Path(tmp1), "run1")
        hash_titles_1 = _sha256_of_file(output_dir_1 / "titles.jsonl")
        hash_quality_1 = _sha256_of_file(output_dir_1 / "quality_report.json")

    # Run 2
    with tempfile.TemporaryDirectory() as tmp2:
        output_dir_2 = _run_etl(titles_csv, credits_csv, Path(tmp2), "run2")
        hash_titles_2 = _sha256_of_file(output_dir_2 / "titles.jsonl")
        hash_quality_2 = _sha256_of_file(output_dir_2 / "quality_report.json")

    # Verify determinism: same input → same output
    assert hash_titles_1 == hash_titles_2, (
        f"titles.jsonl SHA-256 differs between runs:\n"
        f"  Run 1: {hash_titles_1}\n"
        f"  Run 2: {hash_titles_2}"
    )
    assert hash_quality_1 == hash_quality_2, (
        f"quality_report.json SHA-256 differs between runs:\n"
        f"  Run 1: {hash_quality_1}\n"
        f"  Run 2: {hash_quality_2}"
    )
