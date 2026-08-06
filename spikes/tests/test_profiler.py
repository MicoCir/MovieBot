"""Unit tests for the Netflix data profiler and sampler."""

import pytest
import pandas as pd
from pathlib import Path


@pytest.fixture
def sample_csv(tmp_path: Path) -> Path:
    """Create a small CSV fixture resembling the Netflix dataset."""
    csv_path = tmp_path / "netflix_sample.csv"
    csv_path.write_text(
        "show_id,type,title,director,country,release_year,rating\n"
        "s1,Movie,The Grand Adventure,John Doe,United States,2020,PG-13\n"
        "s2,TV Show,Mystery Hour,,United Kingdom,2019,TV-MA\n"
        "s3,Movie,Ocean Depths,Jane Smith,United States,2021,PG\n"
        "s4,TV Show,Code Breaker,Bob Lee,Canada,2020,TV-14\n"
        "s5,Movie,Mountain Peak,,France,2018,R\n"
        "s6,TV Show,Night Watch,Alice Chen,Japan,2022,TV-MA\n"
        "s7,Movie,Desert Storm,John Doe,United States,2020,PG-13\n"
        "s8,Movie,The Grand Adventure,John Doe,United States,2020,PG-13\n",  # duplicate of s1
        encoding="utf-8",
    )
    return csv_path


@pytest.fixture
def small_csv(tmp_path: Path) -> Path:
    """Create a very small CSV for edge case testing."""
    csv_path = tmp_path / "small.csv"
    csv_path.write_text(
        "id,value\n"
        "1,hello\n"
        "2,world\n",
        encoding="utf-8",
    )
    return csv_path


class TestProfileDataset:
    """Tests for profile_dataset function."""

    def test_row_count(self, sample_csv: Path):
        from spikes.netflix.profiler import profile_dataset

        profile = profile_dataset(sample_csv)
        assert profile.row_count == 8

    def test_column_count(self, sample_csv: Path):
        from spikes.netflix.profiler import profile_dataset

        profile = profile_dataset(sample_csv)
        assert profile.column_count == 7

    def test_duplicate_count(self, sample_csv: Path):
        from spikes.netflix.profiler import profile_dataset

        profile = profile_dataset(sample_csv)
        # Row s8 is an exact duplicate of s1 (same show_id and all values)
        # Wait - s8 has show_id "s8" while s1 has "s1", so they differ
        # Actually only if all columns match. s1 and s8 differ in show_id.
        assert profile.duplicate_count == 0

    def test_duplicate_detection_with_real_dupes(self, tmp_path: Path):
        from spikes.netflix.profiler import profile_dataset

        csv_path = tmp_path / "dupes.csv"
        csv_path.write_text(
            "a,b\n"
            "1,x\n"
            "2,y\n"
            "1,x\n"
            "3,z\n",
            encoding="utf-8",
        )
        profile = profile_dataset(csv_path)
        assert profile.duplicate_count == 1

    def test_null_percentage(self, sample_csv: Path):
        from spikes.netflix.profiler import profile_dataset

        profile = profile_dataset(sample_csv)
        # director column has 2 nulls out of 8 rows = 25%
        director_col = next(c for c in profile.columns if c.name == "director")
        assert director_col.null_percentage == 25.0

    def test_unique_count(self, sample_csv: Path):
        from spikes.netflix.profiler import profile_dataset

        profile = profile_dataset(sample_csv)
        type_col = next(c for c in profile.columns if c.name == "type")
        assert type_col.unique_count == 2  # "Movie" and "TV Show"

    def test_representative_values_max_five(self, sample_csv: Path):
        from spikes.netflix.profiler import profile_dataset

        profile = profile_dataset(sample_csv)
        for col in profile.columns:
            assert len(col.representative_values) <= 5

    def test_inferred_types(self, sample_csv: Path):
        from spikes.netflix.profiler import profile_dataset

        profile = profile_dataset(sample_csv)
        type_col = next(c for c in profile.columns if c.name == "type")
        assert type_col.inferred_type == "string"

        year_col = next(c for c in profile.columns if c.name == "release_year")
        assert year_col.inferred_type == "integer"

    def test_file_size_bytes(self, sample_csv: Path):
        from spikes.netflix.profiler import profile_dataset

        profile = profile_dataset(sample_csv)
        assert profile.file_size_bytes == sample_csv.stat().st_size
        assert profile.file_size_bytes > 0


class TestExtractMinimalSample:
    """Tests for extract_minimal_sample function."""

    def test_sample_size_respected(self, sample_csv: Path):
        from spikes.netflix.profiler import extract_minimal_sample

        sample = extract_minimal_sample(sample_csv, sample_size=4)
        assert len(sample) == 4

    def test_sample_no_duplicates(self, sample_csv: Path):
        from spikes.netflix.profiler import extract_minimal_sample

        sample = extract_minimal_sample(sample_csv, sample_size=5)
        assert sample.duplicated().sum() == 0

    def test_sample_is_subset_of_original(self, sample_csv: Path):
        from spikes.netflix.profiler import extract_minimal_sample

        sample = extract_minimal_sample(sample_csv, sample_size=4)
        original = pd.read_csv(sample_csv).drop_duplicates().reset_index(drop=True)

        # Every row in sample must exist in original (merge-based check handles NaN)
        merged = sample.merge(original, how="inner")
        assert len(merged) == len(sample)

    def test_sample_capped_at_available_rows(self, small_csv: Path):
        from spikes.netflix.profiler import extract_minimal_sample

        sample = extract_minimal_sample(small_csv, sample_size=100)
        assert len(sample) == 2  # Only 2 rows available

    def test_stratified_sampling_includes_both_types(self, sample_csv: Path):
        from spikes.netflix.profiler import extract_minimal_sample

        sample = extract_minimal_sample(sample_csv, sample_size=6, stratify_column="type")
        types_in_sample = set(sample["type"].unique())
        assert "Movie" in types_in_sample
        assert "TV Show" in types_in_sample

    def test_random_sampling_when_no_stratify_column(self, sample_csv: Path):
        from spikes.netflix.profiler import extract_minimal_sample

        sample = extract_minimal_sample(sample_csv, sample_size=4, stratify_column=None)
        assert len(sample) == 4

    def test_random_sampling_when_column_missing(self, sample_csv: Path):
        from spikes.netflix.profiler import extract_minimal_sample

        sample = extract_minimal_sample(
            sample_csv, sample_size=4, stratify_column="nonexistent"
        )
        assert len(sample) == 4

    def test_empty_csv(self, tmp_path: Path):
        from spikes.netflix.profiler import extract_minimal_sample

        csv_path = tmp_path / "empty.csv"
        csv_path.write_text("a,b\n", encoding="utf-8")
        sample = extract_minimal_sample(csv_path, sample_size=10)
        assert len(sample) == 0
