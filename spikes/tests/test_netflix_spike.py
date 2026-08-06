"""Unit tests for the Netflix spike.

Tests profiling, sampling, fingerprint stability, and the full spike run
using a small known CSV fixture matching the Netflix schema.

Requirements validated: 2.3, 2.5, 2.6
"""

from __future__ import annotations

import hashlib
from pathlib import Path

import pandas as pd
import pytest

from spikes.common.fingerprint import compute_sha256
from spikes.netflix.profiler import extract_minimal_sample, profile_dataset
from spikes.netflix.spike_netflix import run_netflix_spike

# ---------------------------------------------------------------------------
# Netflix CSV schema columns
# ---------------------------------------------------------------------------

NETFLIX_COLUMNS = [
    "show_id",
    "type",
    "title",
    "director",
    "cast",
    "country",
    "date_added",
    "release_year",
    "rating",
    "duration",
    "listed_in",
    "description",
]

# ---------------------------------------------------------------------------
# Fixture: small known CSV with 10 rows
# ---------------------------------------------------------------------------


@pytest.fixture()
def netflix_csv(tmp_path: Path) -> Path:
    """Create a small Netflix-schema CSV fixture with 10 known rows."""
    rows = [
        {
            "show_id": "s1",
            "type": "Movie",
            "title": "The Grand Adventure",
            "director": "John Smith",
            "cast": "Alice, Bob",
            "country": "United States",
            "date_added": "January 1, 2021",
            "release_year": 2020,
            "rating": "PG-13",
            "duration": "120 min",
            "listed_in": "Action, Adventure",
            "description": "A thrilling adventure movie.",
        },
        {
            "show_id": "s2",
            "type": "TV Show",
            "title": "Mystery Lane",
            "director": "Jane Doe",
            "cast": "Charlie, Dana",
            "country": "United Kingdom",
            "date_added": "February 15, 2021",
            "release_year": 2019,
            "rating": "TV-MA",
            "duration": "2 Seasons",
            "listed_in": "Crime, Mystery",
            "description": "A detective solves cases.",
        },
        {
            "show_id": "s3",
            "type": "Movie",
            "title": "Comedy Night",
            "director": None,
            "cast": "Eve, Frank",
            "country": "Canada",
            "date_added": "March 10, 2020",
            "release_year": 2018,
            "rating": "R",
            "duration": "95 min",
            "listed_in": "Comedies",
            "description": "A hilarious comedy show.",
        },
        {
            "show_id": "s4",
            "type": "TV Show",
            "title": "Space Odyssey",
            "director": "Ray Lee",
            "cast": "Grace, Hank",
            "country": "United States",
            "date_added": "April 5, 2021",
            "release_year": 2021,
            "rating": "TV-14",
            "duration": "1 Season",
            "listed_in": "Sci-Fi, Drama",
            "description": "Astronauts explore the galaxy.",
        },
        {
            "show_id": "s5",
            "type": "Movie",
            "title": "Romantic Escape",
            "director": "Maria Garcia",
            "cast": "Ivy, Jake",
            "country": "France",
            "date_added": "May 20, 2020",
            "release_year": 2017,
            "rating": "PG",
            "duration": "110 min",
            "listed_in": "Romantic Movies",
            "description": "A couple travels Europe.",
        },
        {
            "show_id": "s6",
            "type": "Movie",
            "title": "Horror House",
            "director": "Tom Dark",
            "cast": "Kate, Leo",
            "country": "United States",
            "date_added": "October 31, 2020",
            "release_year": 2020,
            "rating": "R",
            "duration": "88 min",
            "listed_in": "Horror Movies",
            "description": "A family moves into a haunted house.",
        },
        {
            "show_id": "s7",
            "type": "TV Show",
            "title": "Cooking Masters",
            "director": None,
            "cast": "Nora, Oscar",
            "country": "Japan",
            "date_added": "June 1, 2021",
            "release_year": 2021,
            "rating": "TV-G",
            "duration": "3 Seasons",
            "listed_in": "Reality TV",
            "description": "Chefs compete for a prize.",
        },
        {
            "show_id": "s8",
            "type": "Movie",
            "title": "Documentary Earth",
            "director": "Sue Green",
            "cast": None,
            "country": "Australia",
            "date_added": "July 15, 2019",
            "release_year": 2019,
            "rating": "TV-PG",
            "duration": "90 min",
            "listed_in": "Documentaries",
            "description": "Explores nature around the world.",
        },
        {
            "show_id": "s9",
            "type": "TV Show",
            "title": "Anime Legends",
            "director": "Kenji Yamada",
            "cast": "Pete, Quinn",
            "country": "Japan",
            "date_added": "August 20, 2021",
            "release_year": 2021,
            "rating": "TV-14",
            "duration": "1 Season",
            "listed_in": "Anime, Action",
            "description": "Warriors fight for peace.",
        },
        {
            "show_id": "s10",
            "type": "Movie",
            "title": "Kids World",
            "director": "Lily Brown",
            "cast": "Rose, Sam",
            "country": "United States",
            "date_added": "December 25, 2020",
            "release_year": 2020,
            "rating": "G",
            "duration": "75 min",
            "listed_in": "Children & Family Movies",
            "description": "An animated film for kids.",
        },
    ]
    df = pd.DataFrame(rows)
    csv_path = tmp_path / "netflix_titles.csv"
    df.to_csv(csv_path, index=False)
    return csv_path


# ---------------------------------------------------------------------------
# Tests: Profile statistics match expected values (Req 2.3)
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestProfileDataset:
    """Tests that profile_dataset produces correct statistics for known data."""

    def test_row_count(self, netflix_csv: Path):
        """Profile reports correct number of rows."""
        profile = profile_dataset(netflix_csv)
        assert profile.row_count == 10

    def test_column_count(self, netflix_csv: Path):
        """Profile reports correct number of columns."""
        profile = profile_dataset(netflix_csv)
        assert profile.column_count == 12

    def test_column_names(self, netflix_csv: Path):
        """Profile includes all expected column names."""
        profile = profile_dataset(netflix_csv)
        column_names = [col.name for col in profile.columns]
        assert column_names == NETFLIX_COLUMNS

    def test_null_percentage_director(self, netflix_csv: Path):
        """Director column has 20% nulls (2 out of 10)."""
        profile = profile_dataset(netflix_csv)
        director_col = next(c for c in profile.columns if c.name == "director")
        assert director_col.null_percentage == pytest.approx(20.0, abs=0.1)

    def test_null_percentage_cast(self, netflix_csv: Path):
        """Cast column has 10% nulls (1 out of 10)."""
        profile = profile_dataset(netflix_csv)
        cast_col = next(c for c in profile.columns if c.name == "cast")
        assert cast_col.null_percentage == pytest.approx(10.0, abs=0.1)

    def test_no_nulls_in_show_id(self, netflix_csv: Path):
        """show_id column has 0% nulls."""
        profile = profile_dataset(netflix_csv)
        show_id_col = next(c for c in profile.columns if c.name == "show_id")
        assert show_id_col.null_percentage == 0.0

    def test_unique_count_type_column(self, netflix_csv: Path):
        """Type column has 2 unique values: Movie and TV Show."""
        profile = profile_dataset(netflix_csv)
        type_col = next(c for c in profile.columns if c.name == "type")
        assert type_col.unique_count == 2

    def test_unique_count_show_id(self, netflix_csv: Path):
        """show_id has 10 unique values (all distinct)."""
        profile = profile_dataset(netflix_csv)
        show_id_col = next(c for c in profile.columns if c.name == "show_id")
        assert show_id_col.unique_count == 10

    def test_duplicate_count_zero(self, netflix_csv: Path):
        """No duplicate rows in the fixture."""
        profile = profile_dataset(netflix_csv)
        assert profile.duplicate_count == 0

    def test_file_size_bytes_positive(self, netflix_csv: Path):
        """File size is a positive integer."""
        profile = profile_dataset(netflix_csv)
        assert profile.file_size_bytes > 0

    def test_representative_values_type(self, netflix_csv: Path):
        """Type column representative values include Movie and TV Show."""
        profile = profile_dataset(netflix_csv)
        type_col = next(c for c in profile.columns if c.name == "type")
        assert "Movie" in type_col.representative_values
        assert "TV Show" in type_col.representative_values

    def test_release_year_inferred_as_integer(self, netflix_csv: Path):
        """release_year is inferred as integer type."""
        profile = profile_dataset(netflix_csv)
        year_col = next(c for c in profile.columns if c.name == "release_year")
        assert year_col.inferred_type == "integer"


# ---------------------------------------------------------------------------
# Tests: Sample is valid subset (Req 2.5)
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestExtractMinimalSample:
    """Tests that extract_minimal_sample produces a valid subset."""

    def test_sample_size_equals_requested_when_larger(self, netflix_csv: Path):
        """When dataset is larger than sample_size, returns exactly sample_size rows."""
        sample = extract_minimal_sample(netflix_csv, sample_size=5)
        assert len(sample) == 5

    def test_sample_returns_all_rows_when_smaller(self, netflix_csv: Path):
        """When dataset has fewer rows than sample_size, returns all rows."""
        sample = extract_minimal_sample(netflix_csv, sample_size=50)
        assert len(sample) == 10

    def test_sample_columns_match_original(self, netflix_csv: Path):
        """Sample has same columns as the original dataset."""
        sample = extract_minimal_sample(netflix_csv, sample_size=5)
        assert list(sample.columns) == NETFLIX_COLUMNS

    def test_sample_rows_exist_in_original(self, netflix_csv: Path):
        """Every row in the sample exists in the original dataset."""
        original = pd.read_csv(netflix_csv)
        sample = extract_minimal_sample(netflix_csv, sample_size=5)

        for _, row in sample.iterrows():
            # Check that each sample row's show_id exists in original
            assert row["show_id"] in original["show_id"].values

    def test_sample_no_duplicate_rows(self, netflix_csv: Path):
        """Sample contains no duplicate rows."""
        sample = extract_minimal_sample(netflix_csv, sample_size=5)
        assert sample.duplicated().sum() == 0

    def test_stratified_sample_includes_both_types(self, netflix_csv: Path):
        """Stratified sample includes rows from both 'Movie' and 'TV Show'."""
        sample = extract_minimal_sample(netflix_csv, sample_size=5, stratify_column="type")
        types_in_sample = sample["type"].unique().tolist()
        assert "Movie" in types_in_sample
        assert "TV Show" in types_in_sample


# ---------------------------------------------------------------------------
# Tests: Fingerprint is stable across runs (Req 2.6)
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestFingerprintStability:
    """Tests that SHA-256 fingerprint is deterministic for the same file."""

    def test_fingerprint_is_deterministic(self, netflix_csv: Path):
        """Computing fingerprint twice on same file yields identical results."""
        fp1 = compute_sha256(netflix_csv)
        fp2 = compute_sha256(netflix_csv)
        assert fp1 == fp2

    def test_fingerprint_is_64_char_hex(self, netflix_csv: Path):
        """Fingerprint is a valid 64-character lowercase hex string."""
        fp = compute_sha256(netflix_csv)
        assert len(fp) == 64
        assert fp == fp.lower()
        assert all(c in "0123456789abcdef" for c in fp)

    def test_fingerprint_matches_manual_calculation(self, netflix_csv: Path):
        """Fingerprint matches independently computed SHA-256."""
        content = netflix_csv.read_bytes()
        expected = hashlib.sha256(content).hexdigest()
        assert compute_sha256(netflix_csv) == expected

    def test_different_csv_produces_different_fingerprint(self, tmp_path: Path):
        """Modifying a CSV changes the fingerprint."""
        csv_a = tmp_path / "a.csv"
        csv_b = tmp_path / "b.csv"
        csv_a.write_text("col1,col2\n1,2\n", encoding="utf-8")
        csv_b.write_text("col1,col2\n3,4\n", encoding="utf-8")
        assert compute_sha256(csv_a) != compute_sha256(csv_b)


# ---------------------------------------------------------------------------
# Tests: Full spike run with provided CSV (integration-level unit test)
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestRunNetflixSpike:
    """Tests the full spike run with a known CSV fixture."""

    def test_spike_returns_confirmed_status(self, netflix_csv: Path, tmp_path: Path):
        """Spike returns CONFIRMED status when CSV is valid."""
        from spikes.common.models import ViabilityStatus

        artifacts_dir = tmp_path / "artifacts"
        result = run_netflix_spike(csv_path=netflix_csv, artifacts_dir=artifacts_dir)
        assert result.status == ViabilityStatus.CONFIRMED

    def test_spike_reports_correct_row_count(self, netflix_csv: Path, tmp_path: Path):
        """Spike result contains correct row count from profiling."""
        artifacts_dir = tmp_path / "artifacts"
        result = run_netflix_spike(csv_path=netflix_csv, artifacts_dir=artifacts_dir)
        assert result.row_count == 10

    def test_spike_reports_correct_column_count(self, netflix_csv: Path, tmp_path: Path):
        """Spike result contains correct column count."""
        artifacts_dir = tmp_path / "artifacts"
        result = run_netflix_spike(csv_path=netflix_csv, artifacts_dir=artifacts_dir)
        assert result.column_count == 12

    def test_spike_computes_fingerprint(self, netflix_csv: Path, tmp_path: Path):
        """Spike result includes a non-null SHA-256 fingerprint."""
        artifacts_dir = tmp_path / "artifacts"
        result = run_netflix_spike(csv_path=netflix_csv, artifacts_dir=artifacts_dir)
        assert result.fingerprint is not None
        assert len(result.fingerprint) == 64

    def test_spike_fingerprint_matches_csv(self, netflix_csv: Path, tmp_path: Path):
        """Spike fingerprint matches direct SHA-256 computation on the CSV."""
        artifacts_dir = tmp_path / "artifacts"
        result = run_netflix_spike(csv_path=netflix_csv, artifacts_dir=artifacts_dir)
        expected = compute_sha256(netflix_csv)
        assert result.fingerprint == expected

    def test_spike_produces_artifacts(self, netflix_csv: Path, tmp_path: Path):
        """Spike produces profile JSON and sample CSV artifacts."""
        artifacts_dir = tmp_path / "artifacts"
        result = run_netflix_spike(csv_path=netflix_csv, artifacts_dir=artifacts_dir)
        assert len(result.artifacts_produced) >= 2
        # Check artifact files exist
        assert (artifacts_dir / "netflix_profile.json").exists()
        assert (artifacts_dir / "netflix_sample.csv").exists()
        assert (artifacts_dir / "netflix_fingerprint.txt").exists()

    def test_spike_sample_path_set(self, netflix_csv: Path, tmp_path: Path):
        """Spike result includes the sample path."""
        artifacts_dir = tmp_path / "artifacts"
        result = run_netflix_spike(csv_path=netflix_csv, artifacts_dir=artifacts_dir)
        assert result.sample_path is not None

    def test_spike_includes_license_info(self, netflix_csv: Path, tmp_path: Path):
        """Spike result includes license information."""
        artifacts_dir = tmp_path / "artifacts"
        result = run_netflix_spike(csv_path=netflix_csv, artifacts_dir=artifacts_dir)
        assert "CC0" in result.license_info
        assert result.license_info != ""
