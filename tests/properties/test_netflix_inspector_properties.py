"""Property-based tests for Netflix Inspector (Properties 8, 9, 10, 11, 12, 13).

Feature: datasource-preparation
"""

from __future__ import annotations

import csv
import hashlib
import tempfile
from pathlib import Path

from hypothesis import given, settings
from hypothesis import strategies as st

from moviebot.tools.inspect_netflix.inspector import NetflixInspector

from .conftest import genre_list

# =============================================================================
# Shared helpers
# =============================================================================


def _write_csv(path: Path, rows: list[dict[str, str]], fieldnames: list[str]) -> None:
    """Write a CSV file from a list of dicts."""
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def _hash_file(path: Path) -> str:
    """Compute SHA-256 hash of a file's contents."""
    return hashlib.sha256(path.read_bytes()).hexdigest()


# =============================================================================
# Strategies
# =============================================================================


@st.composite
def integer_column(draw: st.DrawFn) -> list[str]:
    """Generate a column of integer strings (excluding 0/1 which overlap with booleans)."""
    values = draw(
        st.lists(
            st.integers(min_value=-9999, max_value=9999).filter(
                lambda x: x not in (0, 1)
            ),
            min_size=1,
            max_size=20,
        )
    )
    return [str(v) for v in values]


@st.composite
def float_column(draw: st.DrawFn) -> list[str]:
    """Generate a column with at least one float pattern string.

    All values must match either int_pattern or float_pattern (but NOT bool
    values like "0" or "1"), with at least one float.
    """
    # At least one float (formatted with decimals so it matches float_pattern)
    floats = draw(
        st.lists(
            st.floats(
                min_value=-9999.0,
                max_value=9999.0,
                allow_nan=False,
                allow_infinity=False,
            ).filter(lambda f: f != int(f)),
            min_size=1,
            max_size=10,
        )
    )
    # Optionally some ints (excluding 0/1 which are boolean-like)
    ints = draw(
        st.lists(
            st.integers(min_value=-999, max_value=999).filter(
                lambda x: x not in (0, 1)
            ),
            min_size=0,
            max_size=5,
        )
    )
    # Format floats to ensure decimal point is present
    float_strs = [f"{v:.4f}" for v in floats]
    int_strs = [str(v) for v in ints]
    return float_strs + int_strs


@st.composite
def boolean_column(draw: st.DrawFn) -> list[str]:
    """Generate a column of boolean-like strings."""
    values = draw(
        st.lists(
            st.sampled_from(["True", "False", "true", "false", "1", "0"]),
            min_size=1,
            max_size=20,
        )
    )
    return values


@st.composite
def list_string_column(draw: st.DrawFn) -> list[str]:
    """Generate a column of list[string] literals."""
    lists = draw(
        st.lists(
            st.lists(
                st.from_regex(r"[a-z]{2,10}", fullmatch=True), min_size=1, max_size=4
            ),
            min_size=1,
            max_size=10,
        )
    )
    return [repr(lst) for lst in lists]


@st.composite
def string_column(draw: st.DrawFn) -> list[str]:
    """Generate a column of plain text strings (not matching int/float/bool/list patterns)."""
    values = draw(
        st.lists(
            st.from_regex(r"[A-Za-z ]{3,20}", fullmatch=True).filter(
                lambda s: (
                    s.strip() and s not in ("True", "False", "true", "false", "1", "0")
                )
            ),
            min_size=1,
            max_size=20,
        )
    )
    return values


@st.composite
def coverage_and_verifiable(draw: st.DrawFn) -> tuple[float, bool, bool]:
    """Generate (coverage_pct, needs_normalization, is_verifiable) tuples."""
    coverage = draw(
        st.floats(min_value=0.0, max_value=100.0, allow_nan=False, allow_infinity=False)
    )
    needs_normalization = draw(st.booleans())
    is_verifiable = draw(st.booleans())
    return (coverage, needs_normalization, is_verifiable)


@st.composite
def dataset_with_known_nulls(
    draw: st.DrawFn,
) -> tuple[list[dict[str, str | None]], dict[str, int]]:
    """Generate a dataset (list of row dicts) with known null counts per column.

    Returns (rows, expected_null_counts_per_column).
    """
    num_rows = draw(st.integers(min_value=1, max_value=15))
    columns = ["col_a", "col_b", "col_c"]

    rows: list[dict[str, str | None]] = []
    null_counts: dict[str, int] = {col: 0 for col in columns}

    for _ in range(num_rows):
        row: dict[str, str | None] = {}
        for col in columns:
            is_null = draw(st.booleans())
            if is_null:
                # Pick a null representation
                null_repr = draw(st.sampled_from([None, "", "[]", "nan"]))
                row[col] = null_repr  # type: ignore[assignment]
                null_counts[col] += 1
            else:
                # Non-null value (ensure it doesn't match null patterns)
                row[col] = draw(st.from_regex(r"[a-z]{3,10}", fullmatch=True))
        rows.append(row)

    return (rows, null_counts)


# =============================================================================
# Property 8: Round-trip del parser de géneros Netflix
# =============================================================================


class TestProperty8GenreRoundTrip:
    """Property 8: Round-trip del parser de géneros Netflix.

    **Validates: Requirements 4.8, 6.1, 6.4**
    """

    @given(genres=genre_list())
    @settings(deadline=None, max_examples=200)
    def test_genre_round_trip(self, genres: list[str]) -> None:
        """Formatting a genre list as a Python literal and parsing it back
        produces the equivalent list.

        **Validates: Requirements 4.8, 6.1, 6.4**
        """
        inspector = NetflixInspector.__new__(NetflixInspector)

        # Format as Python literal (like the CSV stores it)
        literal = repr(genres)

        # Parse back
        parsed = inspector._parse_genres(literal)

        # Verify equivalence
        assert parsed == genres


# =============================================================================
# Property 9: Inferencia de tipos sigue reglas canónicas
# =============================================================================


class TestProperty9TypeInference:
    """Property 9: Inferencia de tipos sigue reglas canónicas.

    **Validates: Requirements 4.2**
    """

    @given(values=integer_column())
    @settings(deadline=None, max_examples=100)
    def test_all_integers_infer_integer(self, values: list[str]) -> None:
        """A column with all integer-pattern values infers 'integer'.

        **Validates: Requirements 4.2**
        """
        inspector = NetflixInspector.__new__(NetflixInspector)
        result = inspector._infer_type(values, "test_col")
        assert result == "integer"

    @given(values=float_column())
    @settings(deadline=None, max_examples=100)
    def test_with_floats_infer_float(self, values: list[str]) -> None:
        """A column with at least one float-pattern value (and rest ints/floats)
        infers 'float'.

        **Validates: Requirements 4.2**
        """
        inspector = NetflixInspector.__new__(NetflixInspector)
        result = inspector._infer_type(values, "test_col")
        assert result == "float"

    @given(values=boolean_column())
    @settings(deadline=None, max_examples=100)
    def test_all_booleans_infer_boolean(self, values: list[str]) -> None:
        """A column with all boolean-pattern values infers 'boolean'.

        **Validates: Requirements 4.2**
        """
        inspector = NetflixInspector.__new__(NetflixInspector)
        result = inspector._infer_type(values, "test_col")
        assert result == "boolean"

    @given(values=list_string_column())
    @settings(deadline=None, max_examples=100)
    def test_all_list_patterns_infer_list_string(self, values: list[str]) -> None:
        """A column with all list-of-strings pattern values infers 'list[string]'.

        **Validates: Requirements 4.2**
        """
        inspector = NetflixInspector.__new__(NetflixInspector)
        result = inspector._infer_type(values, "test_col")
        assert result == "list[string]"

    @given(values=string_column())
    @settings(deadline=None, max_examples=100)
    def test_all_plain_text_infer_string(self, values: list[str]) -> None:
        """A column with all plain-text values infers 'string'.

        **Validates: Requirements 4.2**
        """
        inspector = NetflixInspector.__new__(NetflixInspector)
        result = inspector._infer_type(values, "test_col")
        assert result == "string"

    def test_empty_column_infers_string(self) -> None:
        """An empty column infers 'string'.

        **Validates: Requirements 4.2**
        """
        inspector = NetflixInspector.__new__(NetflixInspector)
        result = inspector._infer_type([], "test_col")
        assert result == "string"


# =============================================================================
# Property 10: Clasificación de campos sigue umbrales sin huecos
# =============================================================================


class TestProperty10ClassificationRules:
    """Property 10: Clasificación de campos sigue umbrales sin huecos.

    **Validates: Requirements 5.2**
    """

    @given(params=coverage_and_verifiable())
    @settings(deadline=None, max_examples=300)
    def test_classification_is_mutually_exclusive_and_exhaustive(
        self, params: tuple[float, bool, bool]
    ) -> None:
        """Every (coverage_pct, needs_normalization, is_verifiable) tuple
        produces exactly one classification category following the strict
        precedence rules with no gaps.

        **Validates: Requirements 5.2**
        """
        coverage_pct, needs_normalization, is_verifiable = params
        inspector = NetflixInspector.__new__(NetflixInspector)

        category, reason = inspector._apply_classification_rules(
            coverage_pct, needs_normalization, is_verifiable, "test_field"
        )

        # Must be one of the three valid categories
        valid_categories = {
            "no fiable para filtros duros",
            "utilizable con normalización previa",
            "utilizable como filtro duro",
        }
        assert category in valid_categories, f"Unknown category: {category}"

        # Verify the category follows the rules:
        # Rule 1: "no fiable" if coverage < 70% OR not verifiable
        if coverage_pct < 70.0 or not is_verifiable:
            assert category == "no fiable para filtros duros"
        # Rule 3: "filtro duro" if coverage >= 90% AND verifiable AND no normalization
        elif coverage_pct >= 90.0 and is_verifiable and not needs_normalization:
            assert category == "utilizable como filtro duro"
        # Rule 2: everything else (>= 70% AND (needs normalization OR < 90%))
        else:
            assert category == "utilizable con normalización previa"

        # Reason is always a non-empty string
        assert isinstance(reason, str)
        assert len(reason) > 0


# =============================================================================
# Property 11: Conteos de nulos y duplicados son correctos
# =============================================================================


class TestProperty11NullsAndDuplicates:
    """Property 11: Conteos de nulos y duplicados son correctos.

    **Validates: Requirements 4.2, 6.5**
    """

    @given(data=dataset_with_known_nulls())
    @settings(deadline=None, max_examples=100)
    def test_null_counts_match_expected(
        self, data: tuple[list[dict[str, str | None]], dict[str, int]]
    ) -> None:
        """The inspector reports exact null counts matching known values.

        **Validates: Requirements 4.2, 6.5**
        """
        rows, expected_null_counts = data
        inspector = NetflixInspector.__new__(NetflixInspector)

        columns = ["col_a", "col_b", "col_c"]
        for col in columns:
            values = [row.get(col) for row in rows]
            null_count = inspector._count_nulls(values, col)
            assert null_count == expected_null_counts[col], (
                f"Column {col}: expected {expected_null_counts[col]} nulls, got {null_count}"
            )

    @given(
        st.lists(
            st.fixed_dictionaries(
                {
                    "id": st.from_regex(r"tm[0-9]{3}", fullmatch=True),
                    "name": st.from_regex(r"[a-z]{3,8}", fullmatch=True),
                }
            ),
            min_size=1,
            max_size=20,
        )
    )
    @settings(deadline=None, max_examples=100)
    def test_duplicate_counts_are_correct(self, rows: list[dict[str, str]]) -> None:
        """Duplicate analysis counts match actual duplicates in data.

        **Validates: Requirements 4.2, 6.5**
        """
        inspector = NetflixInspector.__new__(NetflixInspector)
        key_columns = ["id"]

        stats = inspector._analyze_duplicates(rows, key_columns)

        # Compute expected duplicates manually
        from collections import Counter

        key_counter: Counter[tuple[str | None, ...]] = Counter()
        for row in rows:
            key = tuple(row.get(col) for col in key_columns)
            key_counter[key] += 1

        expected_dup_keys = sum(1 for c in key_counter.values() if c > 1)
        expected_extra_rows = sum(c - 1 for c in key_counter.values() if c > 1)

        assert stats.duplicate_key_values == expected_dup_keys
        assert stats.duplicate_key_extra_rows == expected_extra_rows


# =============================================================================
# Property 12: Determinismo del inspector
# =============================================================================


class TestProperty12Determinism:
    """Property 12: Determinismo del inspector.

    **Validates: Requirements 6.7**
    """

    @given(
        titles=st.lists(
            st.fixed_dictionaries(
                {
                    "id": st.from_regex(r"tm[0-9]{3}", fullmatch=True),
                    "title": st.from_regex(r"[A-Za-z ]{3,15}", fullmatch=True),
                    "type": st.sampled_from(["MOVIE", "SHOW"]),
                    "genres": st.just("['drama']"),
                    "release_year": st.just("2020"),
                    "description": st.from_regex(r"[a-z ]{5,20}", fullmatch=True),
                    "age_certification": st.just("PG"),
                    "imdb_id": st.from_regex(r"tt[0-9]{5}", fullmatch=True),
                    "imdb_score": st.just("7.5"),
                    "tmdb_popularity": st.just("100.5"),
                    "tmdb_score": st.just("7.0"),
                    "production_countries": st.just("['US']"),
                }
            ),
            min_size=1,
            max_size=5,
        ),
        credits=st.lists(
            st.fixed_dictionaries(
                {
                    "person_id": st.from_regex(r"p[0-9]{3}", fullmatch=True),
                    "id": st.from_regex(r"tm[0-9]{3}", fullmatch=True),
                    "name": st.from_regex(r"[A-Za-z]{3,10}", fullmatch=True),
                    "character": st.from_regex(r"[A-Za-z]{3,10}", fullmatch=True),
                    "role": st.sampled_from(["ACTOR", "DIRECTOR"]),
                }
            ),
            min_size=0,
            max_size=10,
        ),
    )
    @settings(deadline=None, max_examples=30)
    def test_inspector_is_deterministic(
        self,
        titles: list[dict[str, str]],
        credits: list[dict[str, str]],
    ) -> None:
        """Running the inspector twice on the same input produces identical output.

        **Validates: Requirements 6.7**
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            titles_path = tmp / "titles.csv"
            credits_path = tmp / "credits.csv"

            title_fields = [
                "id",
                "title",
                "type",
                "genres",
                "release_year",
                "description",
                "age_certification",
                "imdb_id",
                "imdb_score",
                "tmdb_popularity",
                "tmdb_score",
                "production_countries",
            ]
            credit_fields = ["person_id", "id", "name", "character", "role"]

            _write_csv(titles_path, titles, title_fields)
            _write_csv(credits_path, credits, credit_fields)

            # Run 1
            inspector1 = NetflixInspector(
                titles_path=titles_path, credits_path=credits_path
            )
            report1 = inspector1.run()

            # Run 2
            inspector2 = NetflixInspector(
                titles_path=titles_path, credits_path=credits_path
            )
            report2 = inspector2.run()

            # Compare via model_dump
            assert report1.model_dump() == report2.model_dump()


# =============================================================================
# Property 13: El inspector preserva archivos de entrada
# =============================================================================


class TestProperty13PreservesInput:
    """Property 13: El inspector preserva archivos de entrada.

    **Validates: Requirements 7.2, 7.3**
    """

    @given(
        titles=st.lists(
            st.fixed_dictionaries(
                {
                    "id": st.from_regex(r"tm[0-9]{3}", fullmatch=True),
                    "title": st.from_regex(r"[A-Za-z ]{3,15}", fullmatch=True),
                    "type": st.sampled_from(["MOVIE", "SHOW"]),
                    "genres": st.just("['drama']"),
                    "release_year": st.just("2020"),
                    "description": st.from_regex(r"[a-z ]{5,20}", fullmatch=True),
                    "age_certification": st.just("PG"),
                    "imdb_id": st.from_regex(r"tt[0-9]{5}", fullmatch=True),
                    "imdb_score": st.just("7.5"),
                    "tmdb_popularity": st.just("100.5"),
                    "tmdb_score": st.just("7.0"),
                    "production_countries": st.just("['US']"),
                }
            ),
            min_size=1,
            max_size=5,
        ),
        credits=st.lists(
            st.fixed_dictionaries(
                {
                    "person_id": st.from_regex(r"p[0-9]{3}", fullmatch=True),
                    "id": st.from_regex(r"tm[0-9]{3}", fullmatch=True),
                    "name": st.from_regex(r"[A-Za-z]{3,10}", fullmatch=True),
                    "character": st.from_regex(r"[A-Za-z]{3,10}", fullmatch=True),
                    "role": st.sampled_from(["ACTOR", "DIRECTOR"]),
                }
            ),
            min_size=0,
            max_size=10,
        ),
    )
    @settings(deadline=None, max_examples=30)
    def test_inspector_does_not_modify_input_files(
        self,
        titles: list[dict[str, str]],
        credits: list[dict[str, str]],
    ) -> None:
        """Input file contents remain byte-identical after inspector execution.

        **Validates: Requirements 7.2, 7.3**
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            titles_path = tmp / "titles.csv"
            credits_path = tmp / "credits.csv"

            title_fields = [
                "id",
                "title",
                "type",
                "genres",
                "release_year",
                "description",
                "age_certification",
                "imdb_id",
                "imdb_score",
                "tmdb_popularity",
                "tmdb_score",
                "production_countries",
            ]
            credit_fields = ["person_id", "id", "name", "character", "role"]

            _write_csv(titles_path, titles, title_fields)
            _write_csv(credits_path, credits, credit_fields)

            # Hash files before
            titles_hash_before = _hash_file(titles_path)
            credits_hash_before = _hash_file(credits_path)

            # Snapshot directory listing before
            files_before = set(tmp.iterdir())

            # Run inspector
            inspector = NetflixInspector(
                titles_path=titles_path, credits_path=credits_path
            )
            inspector.run()

            # Hash files after
            titles_hash_after = _hash_file(titles_path)
            credits_hash_after = _hash_file(credits_path)

            # Verify no modification
            assert titles_hash_before == titles_hash_after, "titles.csv was modified!"
            assert credits_hash_before == credits_hash_after, (
                "credits.csv was modified!"
            )

            # Verify no new files were created in the directory
            files_after = set(tmp.iterdir())
            assert files_before == files_after, (
                f"Files were created/deleted: added={files_after - files_before}, "
                f"removed={files_before - files_after}"
            )
