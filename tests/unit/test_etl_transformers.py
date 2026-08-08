# tests/unit/test_etl_transformers.py
"""Unit tests for ETL pure transformer functions.

Tests specific edge cases, boundary values, and contracts for each transformer.
Does NOT test ETL orchestrator behavior (e.g., quality report registration).
"""

from moviebot.etl.transformers import (
    normalize_genres,
    normalize_name,
    normalize_type,
    nullify_if_exceeds,
    parse_genres,
    parse_optional_float,
    parse_release_year,
    validate_id,
    validate_title,
)


class TestNormalizeType:
    """Tests for normalize_type — Req 1.4."""

    def test_movie_lowercase(self) -> None:
        assert normalize_type("movie") == "movie"

    def test_show_lowercase(self) -> None:
        assert normalize_type("show") == "show"

    def test_movie_uppercase(self) -> None:
        assert normalize_type("MOVIE") == "movie"

    def test_show_mixed_case(self) -> None:
        assert normalize_type("Show") == "show"

    def test_whitespace_padding(self) -> None:
        assert normalize_type("  movie  ") == "movie"

    def test_empty_string(self) -> None:
        assert normalize_type("") is None

    def test_whitespace_only(self) -> None:
        assert normalize_type("   ") is None

    def test_invalid_type(self) -> None:
        assert normalize_type("documentary") is None

    def test_unicode_invalid(self) -> None:
        assert normalize_type("películas") is None


class TestParseGenres:
    """Tests for parse_genres contract — Req 1.5."""

    def test_empty_string_returns_empty_not_malformed(self) -> None:
        assert parse_genres("") == ([], False)

    def test_whitespace_only_returns_empty_not_malformed(self) -> None:
        assert parse_genres("   ") == ([], False)

    def test_empty_list_literal(self) -> None:
        assert parse_genres("[]") == ([], False)

    def test_single_genre(self) -> None:
        assert parse_genres("['drama']") == (["drama"], False)

    def test_multiple_genres_sorted(self) -> None:
        result, malformed = parse_genres("['Action', 'Drama', 'Comedy']")
        assert malformed is False
        assert result == ["action", "comedy", "drama"]

    def test_genres_with_whitespace(self) -> None:
        result, malformed = parse_genres("[' Drama ', ' action ']")
        assert malformed is False
        assert result == ["action", "drama"]

    def test_not_a_list_is_malformed(self) -> None:
        assert parse_genres("not a list") == ([], True)

    def test_integer_literal_is_malformed(self) -> None:
        assert parse_genres("42") == ([], True)

    def test_dict_literal_is_malformed(self) -> None:
        assert parse_genres("{'key': 'value'}") == ([], True)

    def test_tuple_literal_is_malformed(self) -> None:
        assert parse_genres("('drama', 'action')") == ([], True)

    def test_broken_syntax_is_malformed(self) -> None:
        assert parse_genres("['drama', 'action'") == ([], True)

    def test_non_string_items_filtered(self) -> None:
        result, malformed = parse_genres("['drama', 123, 'action']")
        assert malformed is False
        assert result == ["action", "drama"]

    def test_empty_string_items_filtered(self) -> None:
        result, malformed = parse_genres("['drama', '', '  ', 'action']")
        assert malformed is False
        assert result == ["action", "drama"]

    def test_unicode_genres(self) -> None:
        result, malformed = parse_genres("['ciencia ficción', 'acción']")
        assert malformed is False
        assert result == ["acción", "ciencia ficción"]


class TestNormalizeGenres:
    """Tests for normalize_genres — Req 1.5."""

    def test_malformed_returns_empty(self) -> None:
        assert normalize_genres("not a list") == []

    def test_valid_list_normalized(self) -> None:
        assert normalize_genres("['Drama', 'Action']") == ["action", "drama"]

    def test_empty_string(self) -> None:
        assert normalize_genres("") == []

    def test_broken_syntax_returns_empty(self) -> None:
        assert normalize_genres("['drama',") == []


class TestNormalizeName:
    """Tests for normalize_name — Req 1.16."""

    def test_basic_lowercase_trim(self) -> None:
        assert normalize_name("  Tom Hanks  ") == "tom hanks"

    def test_preserves_internal_spaces(self) -> None:
        assert normalize_name("Robert  De  Niro") == "robert  de  niro"

    def test_empty_string(self) -> None:
        assert normalize_name("") == ""

    def test_whitespace_only(self) -> None:
        assert normalize_name("   ") == ""

    def test_unicode_name(self) -> None:
        assert normalize_name("  José García  ") == "josé garcía"

    def test_already_normalized(self) -> None:
        assert normalize_name("steven spielberg") == "steven spielberg"

    def test_very_long_name(self) -> None:
        long_name = "A" * 1000
        assert normalize_name(long_name) == "a" * 1000

    def test_mixed_unicode_scripts(self) -> None:
        assert normalize_name("  渡辺 Ken  ") == "渡辺 ken"


class TestParseOptionalFloat:
    """Tests for parse_optional_float — Req 1.6, 1.19, 1.21."""

    def test_valid_integer_as_float(self) -> None:
        assert parse_optional_float("5", 0.0, 10.0) == 5.0

    def test_valid_decimal(self) -> None:
        assert parse_optional_float("7.5", 0.0, 10.0) == 7.5

    def test_boundary_min_inclusive(self) -> None:
        assert parse_optional_float("0.0", 0.0, 10.0) == 0.0

    def test_boundary_max_inclusive(self) -> None:
        assert parse_optional_float("10.0", 0.0, 10.0) == 10.0

    def test_tmdb_popularity_max_boundary(self) -> None:
        assert parse_optional_float("10000.0", 0.0, 10000.0) == 10000.0

    def test_below_min_returns_none(self) -> None:
        assert parse_optional_float("-0.1", 0.0, 10.0) is None

    def test_above_max_returns_none(self) -> None:
        assert parse_optional_float("10.1", 0.0, 10.0) is None

    def test_empty_string(self) -> None:
        assert parse_optional_float("", 0.0, 10.0) is None

    def test_whitespace_only(self) -> None:
        assert parse_optional_float("   ", 0.0, 10.0) is None

    def test_non_numeric(self) -> None:
        assert parse_optional_float("abc", 0.0, 10.0) is None

    def test_nan(self) -> None:
        assert parse_optional_float("nan", 0.0, 10.0) is None

    def test_nan_uppercase(self) -> None:
        assert parse_optional_float("NaN", 0.0, 10.0) is None

    def test_infinity(self) -> None:
        assert parse_optional_float("inf", 0.0, 10.0) is None

    def test_negative_infinity(self) -> None:
        assert parse_optional_float("-inf", 0.0, 10.0) is None

    def test_infinity_word(self) -> None:
        assert parse_optional_float("Infinity", 0.0, 10.0) is None

    def test_negative_infinity_word(self) -> None:
        assert parse_optional_float("-Infinity", 0.0, 10000.0) is None

    def test_whitespace_padded_valid(self) -> None:
        assert parse_optional_float("  7.5  ", 0.0, 10.0) == 7.5

    def test_zero_is_valid(self) -> None:
        assert parse_optional_float("0", 0.0, 10.0) == 0.0

    def test_tmdb_popularity_out_of_range(self) -> None:
        assert parse_optional_float("10001.0", 0.0, 10000.0) is None


class TestParseReleaseYear:
    """Tests for parse_release_year — Req 1.6, 1.21."""

    def test_valid_year(self) -> None:
        assert parse_release_year("2020") == 2020

    def test_boundary_min_valid(self) -> None:
        assert parse_release_year("1888") == 1888

    def test_boundary_max_valid(self) -> None:
        assert parse_release_year("2100") == 2100

    def test_below_min_boundary(self) -> None:
        assert parse_release_year("1887") is None

    def test_above_max_boundary(self) -> None:
        assert parse_release_year("2101") is None

    def test_empty_string(self) -> None:
        assert parse_release_year("") is None

    def test_whitespace_only(self) -> None:
        assert parse_release_year("   ") is None

    def test_float_value_invalid(self) -> None:
        assert parse_release_year("2020.5") is None

    def test_non_numeric(self) -> None:
        assert parse_release_year("abc") is None

    def test_whitespace_padded_valid(self) -> None:
        assert parse_release_year("  1999  ") == 1999

    def test_negative_year(self) -> None:
        assert parse_release_year("-100") is None


class TestValidateId:
    """Tests for validate_id — Req 1.20."""

    def test_valid_movie_id(self) -> None:
        assert validate_id("tm12345") == "tm12345"

    def test_valid_show_id(self) -> None:
        assert validate_id("ts99") == "ts99"

    def test_empty_string(self) -> None:
        assert validate_id("") is None

    def test_whitespace_only(self) -> None:
        assert validate_id("   ") is None

    def test_invalid_prefix(self) -> None:
        assert validate_id("xx12345") is None

    def test_no_digits(self) -> None:
        assert validate_id("tm") is None

    def test_exceeds_max_length(self) -> None:
        assert validate_id("tm" + "1" * 19) is None  # 21 chars total

    def test_max_length_boundary(self) -> None:
        assert validate_id("tm" + "1" * 18) == "tm" + "1" * 18  # 20 chars

    def test_whitespace_stripped(self) -> None:
        assert validate_id("  tm123  ") == "tm123"

    def test_letters_after_prefix_invalid(self) -> None:
        assert validate_id("tmabc") is None

    def test_mixed_letters_digits_invalid(self) -> None:
        assert validate_id("tm12a34") is None


class TestValidateTitle:
    """Tests for validate_title — Req 1.20."""

    def test_valid_title(self) -> None:
        assert validate_title("The Matrix") == "The Matrix"

    def test_empty_string(self) -> None:
        assert validate_title("") is None

    def test_whitespace_only(self) -> None:
        assert validate_title("   ") is None

    def test_whitespace_stripped(self) -> None:
        assert validate_title("  The Matrix  ") == "The Matrix"

    def test_max_length_boundary(self) -> None:
        title = "x" * 500
        assert validate_title(title) == title

    def test_exceeds_max_length(self) -> None:
        assert validate_title("x" * 501) is None

    def test_unicode_title(self) -> None:
        assert validate_title("千と千尋の神隠し") == "千と千尋の神隠し"

    def test_single_char_valid(self) -> None:
        assert validate_title("X") == "X"


class TestNullifyIfExceeds:
    """Tests for nullify_if_exceeds — Req 1.10, 1.21."""

    def test_valid_within_limit(self) -> None:
        assert nullify_if_exceeds("hello", 10) == "hello"

    def test_none_input(self) -> None:
        assert nullify_if_exceeds(None, 10) is None

    def test_empty_string(self) -> None:
        assert nullify_if_exceeds("", 10) is None

    def test_whitespace_only(self) -> None:
        assert nullify_if_exceeds("   ", 10) is None

    def test_exceeds_limit_returns_none(self) -> None:
        assert nullify_if_exceeds("x" * 11, 10) is None

    def test_exact_max_length(self) -> None:
        assert nullify_if_exceeds("x" * 10, 10) == "x" * 10

    def test_strips_whitespace_before_check(self) -> None:
        # "  hello  " stripped is "hello" (5 chars), limit is 5
        assert nullify_if_exceeds("  hello  ", 5) == "hello"

    def test_stripped_exceeds_limit(self) -> None:
        # "  helloworld  " stripped is "helloworld" (10 chars), limit is 5
        assert nullify_if_exceeds("  helloworld  ", 5) is None

    def test_description_max_2000(self) -> None:
        # Simulating description field limit
        assert nullify_if_exceeds("x" * 2000, 2000) == "x" * 2000
        assert nullify_if_exceeds("x" * 2001, 2000) is None

    def test_age_certification_max_20(self) -> None:
        # Simulating age_certification field limit
        assert nullify_if_exceeds("PG-13", 20) == "PG-13"
        assert nullify_if_exceeds("x" * 21, 20) is None

    def test_unicode_length_measured_in_chars(self) -> None:
        # Each unicode char counts as 1, regardless of byte length
        unicode_str = "é" * 10
        assert nullify_if_exceeds(unicode_str, 10) == unicode_str
        assert nullify_if_exceeds(unicode_str + "x", 10) is None
