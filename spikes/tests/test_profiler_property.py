# Feature: source-viability-spikes, Property 4: Data Profiling Produces Complete Statistics
"""Property-based tests for the Netflix data profiler.

Validates: Requirements 2.3

For any valid CSV-like DataFrame with at least one row and one column, the data
profiler SHALL produce a profile containing the correct row count, the correct
column count, a null percentage between 0 and 100 for each column, a non-negative
duplicate count, and at least one representative value per non-empty column.
"""

from pathlib import Path

import pandas as pd
import pytest
from hypothesis import given, settings
from hypothesis import strategies as st
from hypothesis.extra.pandas import column, data_frames

from spikes.netflix.profiler import profile_dataset


# --- Strategies ---

# Generate column names as simple ASCII identifiers to avoid CSV encoding issues
_col_names = st.text(
    alphabet=st.characters(whitelist_categories=("Ll",), whitelist_characters="_"),
    min_size=1,
    max_size=8,
).map(lambda s: f"col_{s}")

# Strategy for DataFrames with ≥1 row and ≥1 column, mixing types including nulls
_cell_values = st.one_of(
    st.integers(min_value=-1_000_000, max_value=1_000_000),
    st.floats(allow_nan=False, allow_infinity=False, min_value=-1e6, max_value=1e6),
    st.text(min_size=0, max_size=20, alphabet=st.characters(whitelist_categories=("L", "N"))),
    st.none(),
)


@st.composite
def dataframes_with_at_least_one_row_and_col(draw: st.DrawFn) -> pd.DataFrame:
    """Generate a DataFrame with ≥1 row, ≥1 column, and varied value types."""
    n_cols = draw(st.integers(min_value=1, max_value=5))
    n_rows = draw(st.integers(min_value=1, max_value=30))

    # Generate unique column names
    col_names = draw(
        st.lists(_col_names, min_size=n_cols, max_size=n_cols, unique=True)
    )

    # Build data dict
    data: dict[str, list] = {}
    for col_name in col_names:
        col_data = draw(st.lists(_cell_values, min_size=n_rows, max_size=n_rows))
        data[col_name] = col_data

    return pd.DataFrame(data)


# --- Property Test ---


@pytest.mark.property
@settings(max_examples=100)
@given(df=dataframes_with_at_least_one_row_and_col())
def test_data_profiling_produces_complete_statistics(
    df: pd.DataFrame, tmp_path_factory
) -> None:
    """Profile statistics are correct and complete for any valid DataFrame.

    **Validates: Requirements 2.3**
    """
    # Write DataFrame to a temporary CSV for profile_dataset to consume
    tmp_path = tmp_path_factory.mktemp("profiler")
    csv_path = tmp_path / "data.csv"
    df.to_csv(csv_path, index=False)

    # Profile the dataset
    profile = profile_dataset(csv_path)

    # --- Assertions ---

    # Row count matches actual DataFrame rows
    assert profile.row_count == len(df), (
        f"Expected row_count={len(df)}, got {profile.row_count}"
    )

    # Column count matches actual DataFrame columns
    assert profile.column_count == len(df.columns), (
        f"Expected column_count={len(df.columns)}, got {profile.column_count}"
    )

    # Number of column profiles matches column count
    assert len(profile.columns) == len(df.columns)

    # Per-column assertions
    for col_profile in profile.columns:
        # Null percentage must be in [0, 100]
        assert 0 <= col_profile.null_percentage <= 100, (
            f"Column '{col_profile.name}' has null_percentage={col_profile.null_percentage}, "
            "expected value in [0, 100]"
        )

    # Duplicate count must be non-negative
    assert profile.duplicate_count >= 0, (
        f"Expected non-negative duplicate_count, got {profile.duplicate_count}"
    )

    # At least one representative value per non-all-null column
    # Re-read the CSV as profile_dataset does, to match its view of the data
    df_read = pd.read_csv(csv_path)
    for col_profile in profile.columns:
        col_series = df_read[col_profile.name]
        non_null_count = col_series.notna().sum()
        if non_null_count > 0:
            assert len(col_profile.representative_values) >= 1, (
                f"Column '{col_profile.name}' has {non_null_count} non-null values "
                "but no representative values in the profile"
            )
