# tests/unit/test_netflix_inspector.py
"""Unit tests for NetflixInspector.

Validates: Requirements 6.3, 6.5, 6.6, 6.7
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from moviebot.tools.inspect_netflix.inspector import NetflixInspector


@pytest.fixture
def inspector() -> NetflixInspector:
    """Create inspector with dummy paths (methods under test don't need real files)."""
    return NetflixInspector(
        titles_path=Path("/fake/titles.csv"),
        credits_path=Path("/fake/credits.csv"),
    )


# ---------------------------------------------------------------------------
# Test: Type inference (integer, float, string, boolean, list[string], mixed)
# Validates: Requirement 6.3
# ---------------------------------------------------------------------------


class TestTypeInference:
    """Tests for _infer_type with various patterns."""

    def test_infer_integer(self, inspector: NetflixInspector) -> None:
        """All integer-pattern values → 'integer'.

        Note: "0" and "1" are classified as bool_pattern by _classify_pattern,
        so we use values that are unambiguously integer patterns.
        """
        values = ["42", "-7", "100", "2020", "55"]
        assert inspector._infer_type(values, "col") == "integer"

    def test_infer_float(self, inspector: NetflixInspector) -> None:
        """All float-pattern values → 'float'."""
        values = ["1.5", "3.14", "-0.1"]
        assert inspector._infer_type(values, "col") == "float"

    def test_infer_float_mixed_int_and_float(self, inspector: NetflixInspector) -> None:
        """Mix of int and float patterns (at least one float) → 'float'.

        Note: "0" and "1" are classified as bool_pattern, so we use
        unambiguous integer values mixed with floats.
        """
        values = ["10", "2.5", "3"]
        assert inspector._infer_type(values, "col") == "float"

    def test_infer_string(self, inspector: NetflixInspector) -> None:
        """All plain text values → 'string'."""
        values = ["hello", "world", "foo bar"]
        assert inspector._infer_type(values, "col") == "string"

    def test_infer_boolean(self, inspector: NetflixInspector) -> None:
        """All boolean-pattern values → 'boolean'."""
        values = ["True", "False", "true", "false"]
        assert inspector._infer_type(values, "col") == "boolean"

    def test_infer_list_string(self, inspector: NetflixInspector) -> None:
        """All list-pattern values → 'list[string]'."""
        values = ["['drama', 'crime']", "['action']", "['comedy', 'romance']"]
        assert inspector._infer_type(values, "col") == "list[string]"

    def test_infer_mixed(self, inspector: NetflixInspector) -> None:
        """Mix of incompatible patterns → 'mixed'."""
        values = ["42", "hello", "True"]
        assert inspector._infer_type(values, "col") == "mixed"

    def test_infer_empty_column(self, inspector: NetflixInspector) -> None:
        """Empty non_null_values → 'string' (default)."""
        assert inspector._infer_type([], "col") == "string"


# ---------------------------------------------------------------------------
# Test: Null and duplicate counts with inline data
# Validates: Requirement 6.5
# ---------------------------------------------------------------------------


class TestNullsAndDuplicates:
    """Tests for _count_nulls and _analyze_duplicates with inline data."""

    def test_count_nulls_various_null_forms(self, inspector: NetflixInspector) -> None:
        """Counts None, empty string, '[]', and 'nan' as null values."""
        values: list[str | None] = [
            "value1",
            None,
            "",
            "[]",
            "nan",
            "NaN",
            "value2",
        ]
        result = inspector._count_nulls(values, "test_col")
        # None, "", "[]", "nan", "NaN" → 5 nulls
        assert result == 5

    def test_count_nulls_no_nulls(self, inspector: NetflixInspector) -> None:
        """No null values returns 0."""
        values = ["a", "b", "c"]
        assert inspector._count_nulls(values, "col") == 0

    def test_analyze_duplicates_with_duplicates(
        self, inspector: NetflixInspector
    ) -> None:
        """Detects duplicate key values and counts extra rows."""
        rows: list[dict[str, str | None]] = [
            {"id": "tm001", "name": "A"},
            {"id": "tm002", "name": "B"},
            {"id": "tm001", "name": "C"},  # duplicate key 'tm001'
            {"id": "tm003", "name": "D"},
            {"id": "tm002", "name": "E"},  # duplicate key 'tm002'
        ]
        result = inspector._analyze_duplicates(rows, key_columns=["id"])
        # 2 unique keys with duplicates (tm001, tm002)
        assert result.duplicate_key_values == 2
        # Each appears once extra → 2 extra rows total
        assert result.duplicate_key_extra_rows == 2

    def test_analyze_duplicates_no_duplicates(
        self, inspector: NetflixInspector
    ) -> None:
        """No duplicates when all keys are unique."""
        rows: list[dict[str, str | None]] = [
            {"id": "tm001", "name": "A"},
            {"id": "tm002", "name": "B"},
            {"id": "tm003", "name": "C"},
        ]
        result = inspector._analyze_duplicates(rows, key_columns=["id"])
        assert result.duplicate_key_values == 0
        assert result.duplicate_key_extra_rows == 0

    def test_analyze_duplicates_composite_key(
        self, inspector: NetflixInspector
    ) -> None:
        """Composite key with multiple columns."""
        rows: list[dict[str, str | None]] = [
            {"person_id": "p1", "id": "tm001", "role": "ACTOR"},
            {"person_id": "p1", "id": "tm001", "role": "DIRECTOR"},  # different key
            {"person_id": "p1", "id": "tm001", "role": "ACTOR"},  # duplicate
        ]
        result = inspector._analyze_duplicates(
            rows, key_columns=["person_id", "id", "role"]
        )
        assert result.duplicate_key_values == 1  # (p1, tm001, ACTOR)
        assert result.duplicate_key_extra_rows == 1


# ---------------------------------------------------------------------------
# Test: Join titles-credits produces correct relationship (2 credits for 1 title)
# Validates: Requirement 6.3
# ---------------------------------------------------------------------------


class TestRelationships:
    """Tests for _analyze_relationships with minimal inline data."""

    def test_one_title_two_credits(self, inspector: NetflixInspector) -> None:
        """A title with 2 credits should report correct 1:N cardinality."""
        titles: list[dict[str, str | None]] = [
            {"id": "tm001", "type": "MOVIE", "title": "Movie A"},
        ]
        credits: list[dict[str, str | None]] = [
            {"id": "tm001", "person_id": "p1", "role": "ACTOR"},
            {"id": "tm001", "person_id": "p2", "role": "DIRECTOR"},
        ]
        result = inspector._analyze_relationships(titles, credits)

        # 1:N — credits per title: min=2, max=2, avg=2.0
        assert result.titles_to_credits_1n.min_value == 2
        assert result.titles_to_credits_1n.max_value == 2
        assert result.titles_to_credits_1n.avg_value == 2.0

        # M:N — persons per title: min=2, max=2, avg=2.0
        assert result.titles_to_persons_mn_persons_per_title.min_value == 2
        assert result.titles_to_persons_mn_persons_per_title.max_value == 2

        # No orphans
        assert result.titles_without_credits == 0
        assert result.credits_without_title == 0

    def test_title_without_credits(self, inspector: NetflixInspector) -> None:
        """A title with no credits is counted in titles_without_credits."""
        titles: list[dict[str, str | None]] = [
            {"id": "tm001", "type": "MOVIE", "title": "Movie A"},
            {"id": "tm002", "type": "MOVIE", "title": "Movie B"},
        ]
        credits: list[dict[str, str | None]] = [
            {"id": "tm001", "person_id": "p1", "role": "ACTOR"},
        ]
        result = inspector._analyze_relationships(titles, credits)
        assert result.titles_without_credits == 1  # tm002 has no credits

    def test_credits_without_title(self, inspector: NetflixInspector) -> None:
        """Credits referencing non-existent title are counted."""
        titles: list[dict[str, str | None]] = [
            {"id": "tm001", "type": "MOVIE", "title": "Movie A"},
        ]
        credits: list[dict[str, str | None]] = [
            {"id": "tm001", "person_id": "p1", "role": "ACTOR"},
            {"id": "tm999", "person_id": "p2", "role": "ACTOR"},  # orphan
        ]
        result = inspector._analyze_relationships(titles, credits)
        assert result.credits_without_title == 1


# ---------------------------------------------------------------------------
# Test: Non-existent file → exit code ≠ 0 with descriptive message
# Validates: Requirement 6.6
# ---------------------------------------------------------------------------


class TestCLIFileNotFound:
    """Tests for CLI behavior when files don't exist."""

    def test_nonexistent_titles_file(self, tmp_path: Path) -> None:
        """CLI exits with non-zero code when titles file doesn't exist."""
        fake_titles = tmp_path / "nonexistent_titles.csv"
        fake_credits = tmp_path / "credits.csv"
        # Create only credits file
        fake_credits.write_text("id,person_id,role\n", encoding="utf-8")

        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "moviebot.tools.inspect_netflix",
                "--titles",
                str(fake_titles),
                "--credits",
                str(fake_credits),
            ],
            capture_output=True,
            text=True,
            cwd=str(Path(__file__).resolve().parents[2]),
            check=False,
        )
        assert result.returncode != 0
        assert "nonexistent_titles.csv" in result.stderr

    def test_nonexistent_credits_file(self, tmp_path: Path) -> None:
        """CLI exits with non-zero code when credits file doesn't exist."""
        fake_titles = tmp_path / "titles.csv"
        fake_credits = tmp_path / "nonexistent_credits.csv"
        # Create only titles file
        fake_titles.write_text("id,type,title\n", encoding="utf-8")

        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "moviebot.tools.inspect_netflix",
                "--titles",
                str(fake_titles),
                "--credits",
                str(fake_credits),
            ],
            capture_output=True,
            text=True,
            cwd=str(Path(__file__).resolve().parents[2]),
            check=False,
        )
        assert result.returncode != 0
        assert "nonexistent_credits.csv" in result.stderr


# ---------------------------------------------------------------------------
# Test: Determinism — two executions produce identical output
# Validates: Requirement 6.7
# ---------------------------------------------------------------------------


class TestDeterminism:
    """Tests that inspector produces deterministic output."""

    def test_two_runs_produce_identical_json(self, tmp_path: Path) -> None:
        """Two consecutive runs on same data produce byte-identical JSON output."""
        # Create minimal test CSVs
        titles_csv = tmp_path / "titles.csv"
        credits_csv = tmp_path / "credits.csv"
        titles_csv.write_text(
            "id,title,type,description,release_year,age_certification,"
            "runtime,genres,production_countries,seasons,imdb_id,"
            "imdb_score,imdb_votes,tmdb_popularity,tmdb_score\n"
            "tm001,Movie A,MOVIE,A movie,2020,PG-13,"
            "120,\"['drama','action']\",\"['US']\",,"
            "tt0000001,7.5,1000,45.6,7.2\n"
            "tm002,Show B,SHOW,A show,2019,TV-MA,"
            "45,\"['comedy']\",\"['GB']\",3,"
            "tt0000002,8.1,2000,30.2,8.0\n",
            encoding="utf-8",
        )
        credits_csv.write_text(
            "person_id,id,name,character,role\n"
            "p1,tm001,Actor One,Hero,ACTOR\n"
            "p2,tm001,Director One,,DIRECTOR\n"
            "p3,tm002,Actor Two,Villain,ACTOR\n",
            encoding="utf-8",
        )

        # Run twice via subprocess
        cmd = [
            sys.executable,
            "-m",
            "moviebot.tools.inspect_netflix",
            "--titles",
            str(titles_csv),
            "--credits",
            str(credits_csv),
            "--format",
            "json",
        ]
        cwd = str(Path(__file__).resolve().parents[2])

        run1 = subprocess.run(cmd, capture_output=True, text=True, cwd=cwd, check=False)
        run2 = subprocess.run(cmd, capture_output=True, text=True, cwd=cwd, check=False)

        assert run1.returncode == 0, f"Run 1 failed: {run1.stderr}"
        assert run2.returncode == 0, f"Run 2 failed: {run2.stderr}"
        assert run1.stdout == run2.stdout


# ---------------------------------------------------------------------------
# Test: --output + --format text produces readable file
# Validates: Requirement 6.7 (output persistence)
# ---------------------------------------------------------------------------


class TestOutputFormatText:
    """Tests for --output + --format text producing a readable file."""

    def test_output_format_text_creates_readable_file(self, tmp_path: Path) -> None:
        """CLI with --output and --format text creates a readable text file."""
        # Create minimal test CSVs
        titles_csv = tmp_path / "titles.csv"
        credits_csv = tmp_path / "credits.csv"
        output_file = tmp_path / "report.txt"

        titles_csv.write_text(
            "id,title,type,description,release_year,age_certification,"
            "runtime,genres,production_countries,seasons,imdb_id,"
            "imdb_score,imdb_votes,tmdb_popularity,tmdb_score\n"
            "tm001,Movie A,MOVIE,Desc,2020,PG-13,"
            "120,\"['drama']\",\"['US']\",,"
            "tt0000001,7.5,1000,45.6,7.2\n",
            encoding="utf-8",
        )
        credits_csv.write_text(
            "person_id,id,name,character,role\np1,tm001,Actor One,Hero,ACTOR\n",
            encoding="utf-8",
        )

        cmd = [
            sys.executable,
            "-m",
            "moviebot.tools.inspect_netflix",
            "--titles",
            str(titles_csv),
            "--credits",
            str(credits_csv),
            "--output",
            str(output_file),
            "--format",
            "text",
        ]
        cwd = str(Path(__file__).resolve().parents[2])

        result = subprocess.run(
            cmd, capture_output=True, text=True, cwd=cwd, check=False
        )
        assert result.returncode == 0, f"CLI failed: {result.stderr}"

        # Verify file exists and is readable
        assert output_file.exists()
        content = output_file.read_text(encoding="utf-8")
        assert len(content) > 0
        # Should contain human-readable markers
        assert "Netflix Dataset Inspection Report" in content
        # Should contain field classifications
        assert "Field Classifications" in content

    def test_output_creates_parent_directory(self, tmp_path: Path) -> None:
        """CLI with --output creates parent directories if they don't exist."""
        titles_csv = tmp_path / "titles.csv"
        credits_csv = tmp_path / "credits.csv"
        output_file = tmp_path / "subdir" / "nested" / "report.json"

        titles_csv.write_text(
            "id,title,type,description,release_year,age_certification,"
            "runtime,genres,production_countries,seasons,imdb_id,"
            "imdb_score,imdb_votes,tmdb_popularity,tmdb_score\n"
            "tm001,Movie A,MOVIE,Desc,2020,PG-13,"
            "120,\"['drama']\",\"['US']\",,"
            "tt0000001,7.5,1000,45.6,7.2\n",
            encoding="utf-8",
        )
        credits_csv.write_text(
            "person_id,id,name,character,role\np1,tm001,Actor One,Hero,ACTOR\n",
            encoding="utf-8",
        )

        cmd = [
            sys.executable,
            "-m",
            "moviebot.tools.inspect_netflix",
            "--titles",
            str(titles_csv),
            "--credits",
            str(credits_csv),
            "--output",
            str(output_file),
            "--format",
            "json",
        ]
        cwd = str(Path(__file__).resolve().parents[2])

        result = subprocess.run(
            cmd, capture_output=True, text=True, cwd=cwd, check=False
        )
        assert result.returncode == 0, f"CLI failed: {result.stderr}"
        assert output_file.exists()

        # Verify valid JSON
        content = output_file.read_text(encoding="utf-8")
        parsed = json.loads(content)
        assert "schemas" in parsed
