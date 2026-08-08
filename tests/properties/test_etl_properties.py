"""Property tests for ETL transformer functions (Properties 2, 3, 4, 7, 8, 9).

Tests the pure stateless normalization functions in moviebot.etl.transformers
using Hypothesis to verify universal invariants hold across all inputs.

**Validates: Requirements 1.4, 1.5, 1.6, 1.9, 1.10, 1.16, 1.19, 1.20, 1.21**
"""

from __future__ import annotations

from hypothesis import given, settings
from hypothesis import strategies as st

from moviebot.etl.transformers import (
    normalize_genres,
    normalize_name,
    normalize_type,
    nullify_if_exceeds,
    parse_optional_float,
    parse_release_year,
    validate_id,
    validate_title,
)

# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------

_any_text = st.text(min_size=0, max_size=200)

_whitespace_padding = st.sampled_from(["", " ", "  ", "\t", "\n", " \t\n "])


def _padded_text(inner: st.SearchStrategy[str]) -> st.SearchStrategy[str]:
    """Wraps inner text with optional leading/trailing whitespace."""
    return st.builds(
        lambda pad_l, text, pad_r: pad_l + text + pad_r,
        _whitespace_padding,
        inner,
        _whitespace_padding,
    )


# ---------------------------------------------------------------------------
# Property 2: Normalización de tipos es total
# ---------------------------------------------------------------------------


@given(raw=_any_text)
@settings(max_examples=200)
def test_property_2_normalize_type_output_domain(raw: str) -> None:
    """Property 2: Normalización de tipos es total.

    **Validates: Requirements 1.4**

    For any string input, normalize_type returns exactly one of:
    "movie", "show", or None.
    """
    result = normalize_type(raw)
    assert result in ("movie", "show", None), (
        f"normalize_type({raw!r}) returned {result!r}, "
        f"expected one of 'movie', 'show', or None"
    )


@given(
    valid_type=st.sampled_from(["movie", "show", "Movie", "MOVIE", "Show", "SHOW"]),
    pad_l=_whitespace_padding,
    pad_r=_whitespace_padding,
)
@settings(max_examples=100)
def test_property_2_normalize_type_valid_inputs(
    valid_type: str, pad_l: str, pad_r: str
) -> None:
    """Property 2 (supplement): Valid type values are always recognized.

    **Validates: Requirements 1.4**

    Case-insensitive matching with whitespace tolerance.
    """
    raw = pad_l + valid_type + pad_r
    result = normalize_type(raw)
    assert result == valid_type.strip().lower()


# ---------------------------------------------------------------------------
# Property 3: Géneros normalizados y ordenados
# ---------------------------------------------------------------------------


@given(raw=_any_text)
@settings(max_examples=200)
def test_property_3_normalize_genres_always_sorted_lowercase(raw: str) -> None:
    """Property 3: Géneros normalizados y ordenados.

    **Validates: Requirements 1.5**

    For any input string, normalize_genres returns a list where:
    - All elements are lowercase strings
    - The list is sorted alphabetically
    """
    result = normalize_genres(raw)

    assert isinstance(result, list)
    for genre in result:
        assert isinstance(genre, str)
        assert genre == genre.lower(), (
            f"Genre {genre!r} is not lowercase in output of normalize_genres({raw!r})"
        )
    assert result == sorted(result), (
        f"Genres not sorted: {result} from normalize_genres({raw!r})"
    )


@given(
    genres=st.lists(
        st.text(
            alphabet=st.characters(blacklist_categories=("Cs",)),
            min_size=1,
            max_size=30,
        ).filter(lambda s: s.strip()),
        min_size=1,
        max_size=8,
    )
)
@settings(max_examples=100)
def test_property_3_normalize_genres_valid_list_literal(genres: list[str]) -> None:
    """Property 3 (supplement): Valid Python list literals produce sorted lowercase genres.

    **Validates: Requirements 1.5**
    """
    raw = repr(genres)
    result = normalize_genres(raw)

    expected = sorted(g.strip().lower() for g in genres if g.strip())
    assert result == expected, (
        f"normalize_genres({raw!r}) = {result}, expected {expected}"
    )


# ---------------------------------------------------------------------------
# Property 4: Preservación y normalización de nombres
# ---------------------------------------------------------------------------


@given(raw=_any_text)
@settings(max_examples=200)
def test_property_4_normalize_name_lowercase_trimmed(raw: str) -> None:
    """Property 4: Preservación y normalización de nombres.

    **Validates: Requirements 1.16**

    For any string, normalize_name returns:
    - A lowercase string
    - With no leading/trailing whitespace
    - Internal spaces between words are preserved
    """
    result = normalize_name(raw)

    assert result == result.lower(), (
        f"normalize_name({raw!r}) = {result!r} is not lowercase"
    )
    assert result == result.strip(), (
        f"normalize_name({raw!r}) = {result!r} has leading/trailing whitespace"
    )
    # Internal spaces preserved: the core content after strip+lower matches
    assert result == raw.strip().lower(), (
        f"normalize_name({raw!r}) = {result!r}, expected {raw.strip().lower()!r}"
    )


@given(
    first=st.text(
        alphabet=st.characters(whitelist_categories=("L", "N")),
        min_size=1,
        max_size=20,
    ),
    spaces=st.text(alphabet=" ", min_size=1, max_size=5),
    last=st.text(
        alphabet=st.characters(whitelist_categories=("L", "N")),
        min_size=1,
        max_size=20,
    ),
)
@settings(max_examples=100)
def test_property_4_normalize_name_preserves_internal_spaces(
    first: str, spaces: str, last: str
) -> None:
    """Property 4 (supplement): Internal spaces between words are preserved.

    **Validates: Requirements 1.16**
    """
    raw = f"  {first}{spaces}{last}  "
    result = normalize_name(raw)

    # Internal spaces preserved exactly
    expected = f"{first}{spaces}{last}".lower()
    assert result == expected


# ---------------------------------------------------------------------------
# Property 7: Campos numéricos opcionales
# ---------------------------------------------------------------------------


@given(
    raw=_any_text,
    min_val=st.floats(
        min_value=-1000.0, max_value=0.0, allow_nan=False, allow_infinity=False
    ),
    max_val=st.floats(
        min_value=0.0, max_value=10000.0, allow_nan=False, allow_infinity=False
    ),
)
@settings(max_examples=200)
def test_property_7_parse_optional_float_output_domain(
    raw: str, min_val: float, max_val: float
) -> None:
    """Property 7: Campos numéricos opcionales — output is float or None.

    **Validates: Requirements 1.6, 1.19**

    For any string, parse_optional_float returns either:
    - A float within [min_val, max_val] (not NaN, not Inf)
    - None
    """
    if min_val > max_val:
        min_val, max_val = max_val, min_val

    result = parse_optional_float(raw, min_val, max_val)

    if result is not None:
        assert isinstance(result, float)
        assert min_val <= result <= max_val, (
            f"parse_optional_float({raw!r}, {min_val}, {max_val}) = {result}, "
            f"out of range [{min_val}, {max_val}]"
        )
        import math

        assert not math.isnan(result)
        assert not math.isinf(result)


@given(
    value=st.floats(
        min_value=0.0, max_value=10.0, allow_nan=False, allow_infinity=False
    ),
    pad_l=_whitespace_padding,
    pad_r=_whitespace_padding,
)
@settings(max_examples=100)
def test_property_7_parse_optional_float_valid_in_range(
    value: float, pad_l: str, pad_r: str
) -> None:
    """Property 7 (supplement): Parseable in-range values return float.

    **Validates: Requirements 1.6**
    """
    raw = f"{pad_l}{value}{pad_r}"
    result = parse_optional_float(raw, 0.0, 10.0)
    assert result is not None
    assert abs(result - value) < 1e-10


@given(
    value=st.one_of(
        st.just("nan"),
        st.just("NaN"),
        st.just("inf"),
        st.just("-inf"),
        st.just("Infinity"),
        st.just("-Infinity"),
    )
)
@settings(max_examples=20)
def test_property_7_parse_optional_float_special_values_none(value: str) -> None:
    """Property 7 (supplement): NaN, Inf, -Inf always return None.

    **Validates: Requirements 1.19**
    """
    result = parse_optional_float(value, 0.0, 10.0)
    assert result is None, (
        f"parse_optional_float({value!r}, 0.0, 10.0) = {result}, expected None"
    )


# ---------------------------------------------------------------------------
# Property 8: Descarte de registros inválidos
# ---------------------------------------------------------------------------


@given(raw=_any_text)
@settings(max_examples=200)
def test_property_8_validate_id_output_domain(raw: str) -> None:
    """Property 8: Invalid id → None.

    **Validates: Requirements 1.20**

    validate_id returns either a valid stripped ID matching ^t[ms]\\d+$
    (length ≤ 20) or None.
    """
    import re

    result = validate_id(raw)

    if result is not None:
        assert isinstance(result, str)
        assert len(result) <= 20
        assert re.match(r"^t[ms]\d+$", result), (
            f"validate_id({raw!r}) returned {result!r} which doesn't match pattern"
        )
    # If None, that's valid for any input


@given(raw=_any_text)
@settings(max_examples=200)
def test_property_8_validate_title_output_domain(raw: str) -> None:
    """Property 8: Invalid title → None.

    **Validates: Requirements 1.20**

    validate_title returns either a non-empty stripped string (≤ 500 chars)
    or None.
    """
    result = validate_title(raw)

    if result is not None:
        assert isinstance(result, str)
        assert len(result) > 0
        assert len(result) <= 500
        assert result == result.strip()
    # If None, that's valid for any input


@given(raw=_any_text)
@settings(max_examples=200)
def test_property_8_parse_release_year_output_domain(raw: str) -> None:
    """Property 8: Invalid year → None.

    **Validates: Requirements 1.9, 1.21**

    parse_release_year returns either an int in [1888, 2100] or None.
    """
    result = parse_release_year(raw)

    if result is not None:
        assert isinstance(result, int)
        assert 1888 <= result <= 2100, (
            f"parse_release_year({raw!r}) = {result}, out of range [1888, 2100]"
        )


@given(
    prefix=st.sampled_from(["t", "x", "tm", "ts", "abc", ""]),
    suffix=st.text(min_size=0, max_size=25),
)
@settings(max_examples=200)
def test_property_8_validate_id_invalid_patterns(prefix: str, suffix: str) -> None:
    """Property 8 (supplement): IDs not matching ^t[ms]\\d+$ are rejected.

    **Validates: Requirements 1.20**
    """
    import re

    raw = prefix + suffix
    result = validate_id(raw)

    # If result is not None, it must be a valid pattern
    if result is not None:
        assert re.match(r"^t[ms]\d+$", result)
        assert len(result) <= 20


# ---------------------------------------------------------------------------
# Property 9: Campos opcionales null handling
# ---------------------------------------------------------------------------


@given(
    raw=st.one_of(
        st.none(),
        st.just(""),
        st.just("   "),
        st.just("\t\n"),
        st.text(alphabet=" \t\n\r", min_size=1, max_size=10),
    ),
    max_length=st.integers(min_value=1, max_value=100),
)
@settings(max_examples=100)
def test_property_9_nullify_if_exceeds_empty_whitespace(
    raw: str | None, max_length: int
) -> None:
    """Property 9: Empty/whitespace/None → None.

    **Validates: Requirements 1.10**

    nullify_if_exceeds returns None for None, empty, or whitespace-only inputs.
    """
    result = nullify_if_exceeds(raw, max_length)
    assert result is None, (
        f"nullify_if_exceeds({raw!r}, {max_length}) = {result!r}, expected None"
    )


@given(
    content=st.text(min_size=1, max_size=50).filter(lambda s: s.strip()),
    max_length=st.integers(min_value=1, max_value=10),
)
@settings(max_examples=200)
def test_property_9_nullify_if_exceeds_length_check(
    content: str, max_length: int
) -> None:
    """Property 9: Exceeds max_length → None (no truncation).

    **Validates: Requirements 1.21**

    If the trimmed content exceeds max_length, result is None.
    If within limit, result is the trimmed content.
    """
    raw = f"  {content}  "
    result = nullify_if_exceeds(raw, max_length)
    trimmed = raw.strip()

    if len(trimmed) > max_length:
        assert result is None, (
            f"nullify_if_exceeds({raw!r}, {max_length}) should be None "
            f"(len={len(trimmed)} > {max_length})"
        )
    else:
        assert result == trimmed, (
            f"nullify_if_exceeds({raw!r}, {max_length}) = {result!r}, "
            f"expected {trimmed!r}"
        )


@given(
    raw=st.one_of(st.none(), _any_text),
    max_length=st.integers(min_value=1, max_value=2000),
)
@settings(max_examples=200)
def test_property_9_nullify_if_exceeds_output_domain(
    raw: str | None, max_length: int
) -> None:
    """Property 9: Output is always either None or a valid trimmed string.

    **Validates: Requirements 1.10, 1.21**

    nullify_if_exceeds never returns empty strings, whitespace-only strings,
    or strings exceeding max_length.
    """
    result = nullify_if_exceeds(raw, max_length)

    if result is not None:
        assert isinstance(result, str)
        assert len(result) > 0
        assert result == result.strip()
        assert len(result) <= max_length
