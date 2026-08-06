# Feature: source-viability-spikes, Property 5: Minimal Sample is Valid Subset
"""Property-based tests for minimal sample validity.

Validates: Requirements 2.5

For any DataFrame with N rows (N ≥ sample_size), the sampling function SHALL produce
a DataFrame where every row exists in the original, the sample size equals the
configured minimum, and no row appears more than once.
"""

from pathlib import Path

import pandas as pd
import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from spikes.netflix.profiler import extract_minimal_sample

SAMPLE_SIZE = 10


def _df_to_csv(df: pd.DataFrame, tmp_dir: Path) -> Path:
    """Write a DataFrame to a temporary CSV file and return the path."""
    csv_path = tmp_dir / "generated.csv"
    df.to_csv(csv_path, index=False)
    return csv_path


# Strategy: generate DataFrames with at least SAMPLE_SIZE rows, unique rows,
# and a few columns. We use unique integer IDs to guarantee row uniqueness.
_text_values = st.text(
    alphabet=st.characters(whitelist_categories=("L", "N", "P", "Z")),
    min_size=1,
    max_size=20,
)


@st.composite
def unique_dataframes(draw: st.DrawFn) -> pd.DataFrame:
    """Generate DataFrames with unique rows and at least SAMPLE_SIZE rows."""
    n_rows = draw(st.integers(min_value=SAMPLE_SIZE, max_value=80))
    # Use unique sequential IDs to guarantee row uniqueness
    ids = list(range(1, n_rows + 1))
    titles = [draw(_text_values) for _ in range(n_rows)]
    values = [
        draw(st.floats(min_value=-1e6, max_value=1e6, allow_nan=False, allow_infinity=False))
        for _ in range(n_rows)
    ]
    return pd.DataFrame({"id": ids, "title": titles, "value": values})


@pytest.mark.property
@settings(max_examples=100)
@given(df=unique_dataframes())
def test_sample_size_equals_configured_minimum(df: pd.DataFrame, tmp_path_factory) -> None:
    """The sample size equals the configured minimum (sample_size)."""
    tmp_dir = tmp_path_factory.mktemp("sample_size")
    csv_path = _df_to_csv(df, tmp_dir)

    sample = extract_minimal_sample(csv_path, sample_size=SAMPLE_SIZE, stratify_column=None)

    assert len(sample) == SAMPLE_SIZE


@pytest.mark.property
@settings(max_examples=100)
@given(df=unique_dataframes())
def test_every_row_in_sample_exists_in_original(df: pd.DataFrame, tmp_path_factory) -> None:
    """Every row in the sample exists in the original DataFrame."""
    tmp_dir = tmp_path_factory.mktemp("sample_subset")
    csv_path = _df_to_csv(df, tmp_dir)

    sample = extract_minimal_sample(csv_path, sample_size=SAMPLE_SIZE, stratify_column=None)

    # Re-read the original from disk (same way the function does)
    original = pd.read_csv(csv_path)

    # Verify each sample row is present in the original via merge
    merged = sample.merge(original, how="inner")
    assert len(merged) >= len(sample), (
        f"Some sample rows not found in original: "
        f"sample={len(sample)}, matched={len(merged)}"
    )


@pytest.mark.property
@settings(max_examples=100)
@given(df=unique_dataframes())
def test_no_duplicate_rows_in_sample(df: pd.DataFrame, tmp_path_factory) -> None:
    """No row appears more than once in the sample."""
    tmp_dir = tmp_path_factory.mktemp("sample_nodupes")
    csv_path = _df_to_csv(df, tmp_dir)

    sample = extract_minimal_sample(csv_path, sample_size=SAMPLE_SIZE, stratify_column=None)

    duplicate_count = sample.duplicated().sum()
    assert duplicate_count == 0, (
        f"Found {duplicate_count} duplicate rows in sample of size {len(sample)}"
    )
