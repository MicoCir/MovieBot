"""Data profiling and sampling logic for the Netflix spike."""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from spikes.netflix.models import ColumnProfile, DataProfile


def _infer_column_type(series: pd.Series) -> str:
    """Infer a human-readable type string for a pandas Series."""
    dtype = series.dtype

    if pd.api.types.is_integer_dtype(dtype):
        return "integer"
    if pd.api.types.is_float_dtype(dtype):
        # Check if the column is actually integer values stored as float due to NaN
        non_null = series.dropna()
        if len(non_null) > 0 and (non_null == non_null.astype(int)).all():
            return "integer"
        return "float"
    if pd.api.types.is_bool_dtype(dtype):
        return "boolean"
    if pd.api.types.is_datetime64_any_dtype(dtype):
        return "datetime"
    # Default to string for object dtype and others
    return "string"


def _get_representative_values(series: pd.Series, max_values: int = 5) -> list[str]:
    """Extract up to *max_values* representative (most frequent) values from a Series."""
    non_null = series.dropna()
    if len(non_null) == 0:
        return []

    value_counts = non_null.value_counts()
    top_values = value_counts.head(max_values).index.tolist()
    return [str(v) for v in top_values]


def profile_dataset(csv_path: Path) -> DataProfile:
    """Generate a complete data profile for a CSV file.

    Reads the CSV, computes per-column statistics (type, null %, unique count,
    representative values), and detects duplicate rows.

    Parameters
    ----------
    csv_path : Path
        Path to the CSV file to profile.

    Returns
    -------
    DataProfile
        A Pydantic model with full profiling statistics.
    """
    file_size_bytes = csv_path.stat().st_size
    df = pd.read_csv(csv_path)

    row_count = len(df)
    column_count = len(df.columns)
    duplicate_count = int(df.duplicated().sum())

    columns: list[ColumnProfile] = []
    for col_name in df.columns:
        series = df[col_name]
        null_pct = float(series.isna().mean() * 100)
        unique_count = int(series.nunique(dropna=True))
        inferred_type = _infer_column_type(series)
        representative_values = _get_representative_values(series)

        columns.append(
            ColumnProfile(
                name=str(col_name),
                inferred_type=inferred_type,
                null_percentage=round(null_pct, 2),
                unique_count=unique_count,
                representative_values=representative_values,
            )
        )

    return DataProfile(
        row_count=row_count,
        column_count=column_count,
        columns=columns,
        duplicate_count=duplicate_count,
        file_size_bytes=file_size_bytes,
    )


def extract_minimal_sample(
    csv_path: Path,
    sample_size: int = 50,
    stratify_column: str | None = "type",
) -> pd.DataFrame:
    """Extract a representative minimal sample from a CSV dataset.

    Uses stratified sampling when the stratify column is present and has
    multiple categories, falling back to random sampling otherwise.

    Parameters
    ----------
    csv_path : Path
        Path to the CSV file to sample from.
    sample_size : int
        Target number of rows in the sample (default 50).
    stratify_column : str | None
        Column to stratify by. Set to None to disable stratification.

    Returns
    -------
    pd.DataFrame
        A DataFrame containing the sampled rows.
    """
    df = pd.read_csv(csv_path)

    # If dataset is smaller than or equal to sample_size, return all rows
    if len(df) <= sample_size:
        return df.reset_index(drop=True)

    # Attempt stratified sampling
    if stratify_column and stratify_column in df.columns:
        groups = df.groupby(stratify_column)
        group_counts = groups.size()
        total = group_counts.sum()

        # Allocate proportional samples per group (at least 1 per group)
        allocations: dict[str, int] = {}
        remaining = sample_size

        for group_name, count in group_counts.items():
            proportion = count / total
            alloc = max(1, int(round(proportion * sample_size)))
            # Don't exceed the group size
            alloc = min(alloc, count)
            allocations[group_name] = alloc

        # Adjust if total allocations exceed sample_size
        total_allocated = sum(allocations.values())
        if total_allocated > sample_size:
            # Reduce from largest groups first
            sorted_groups = sorted(allocations.items(), key=lambda x: x[1], reverse=True)
            excess = total_allocated - sample_size
            for group_name, alloc in sorted_groups:
                if excess <= 0:
                    break
                reduction = min(excess, alloc - 1)
                allocations[group_name] = alloc - reduction
                excess -= reduction
        elif total_allocated < sample_size:
            # Add more to largest groups
            sorted_groups = sorted(allocations.items(), key=lambda x: x[1], reverse=True)
            deficit = sample_size - total_allocated
            for group_name, alloc in sorted_groups:
                if deficit <= 0:
                    break
                group_size = group_counts[group_name]
                can_add = group_size - alloc
                addition = min(deficit, can_add)
                allocations[group_name] = alloc + addition
                deficit -= addition

        # Sample from each group
        sampled_parts: list[pd.DataFrame] = []
        for group_name, alloc in allocations.items():
            group_df = groups.get_group(group_name)
            n = min(alloc, len(group_df))
            sampled_parts.append(group_df.sample(n=n, random_state=42))

        sample_df = pd.concat(sampled_parts, ignore_index=True)

        # Final adjustment to exact sample_size
        if len(sample_df) > sample_size:
            sample_df = sample_df.head(sample_size)
        elif len(sample_df) < sample_size:
            # Fill remaining from unsampled rows
            sampled_indices = set()
            for part in sampled_parts:
                sampled_indices.update(part.index.tolist())
            remaining_df = df.loc[~df.index.isin(sampled_indices)]
            need = sample_size - len(sample_df)
            if len(remaining_df) >= need:
                extra = remaining_df.sample(n=need, random_state=42)
            else:
                extra = remaining_df
            sample_df = pd.concat([sample_df, extra], ignore_index=True)

        return sample_df.reset_index(drop=True)

    # Fallback: simple random sampling
    return df.sample(n=sample_size, random_state=42).reset_index(drop=True)
