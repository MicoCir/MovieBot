# tests/integration/test_etl_full.py
"""Integration tests for the Netflix ETL pipeline end-to-end.

Creates small fixture CSVs (~10 titles, ~15 credits including invalid records),
runs the full ETL pipeline, and verifies:
- Output structure (titles.jsonl, metadata.json, quality_report.json)
- Metadata validates against EtlMetadata schema
- Quality report correctly tracks discards
- Checksums match between metadata and actual files
- Two runs produce identical (deterministic) output

Validates: Requirements 1.1, 1.2, 1.12, 10.1
"""

from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path

import pytest

from moviebot.etl.netflix_etl import EtlConfig, EtlResult, NetflixEtl
from moviebot.etl.quality_report import QualityReport
from moviebot.etl.schema import CanonicalNetflixTitle, EtlMetadata

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

TITLES_HEADER = [
    "id",
    "title",
    "type",
    "release_year",
    "description",
    "age_certification",
    "genres",
    "imdb_score",
    "tmdb_score",
    "tmdb_popularity",
]

CREDITS_HEADER = ["id", "role", "person_id", "name", "character"]

# 10 titles: 8 valid, 2 invalid (will be discarded)
FIXTURE_TITLES = [
    # Valid movies
    [
        "tm1001",
        "The Matrix",
        "MOVIE",
        "1999",
        "A hacker discovers reality.",
        "R",
        "['Action', 'Science Fiction']",
        "8.7",
        "8.2",
        "120.5",
    ],
    [
        "tm1002",
        "Inception",
        "MOVIE",
        "2010",
        "Dream within a dream.",
        "PG-13",
        "['Action', 'Thriller']",
        "8.8",
        "8.4",
        "200.0",
    ],
    [
        "tm1003",
        "Amélie",
        "MOVIE",
        "2001",
        "A shy waitress transforms lives.",
        "R",
        "['Comedy', 'Romance']",
        "8.3",
        "7.9",
        "45.0",
    ],
    [
        "tm1004",
        "Parasite",
        "MOVIE",
        "2019",
        "A tale of two families.",
        "R",
        "['Drama', 'Thriller']",
        "8.5",
        "8.6",
        "180.0",
    ],
    # Valid shows
    [
        "ts2001",
        "Breaking Bad",
        "SHOW",
        "2008",
        "A teacher turns to crime.",
        "TV-MA",
        "['Crime', 'Drama']",
        "9.5",
        "9.0",
        "500.0",
    ],
    [
        "ts2002",
        "Stranger Things",
        "SHOW",
        "2016",
        "Kids encounter supernatural forces.",
        "TV-14",
        "['Drama', 'Horror']",
        "8.7",
        "8.3",
        "350.0",
    ],
    # Valid with edge cases: empty description, no age_cert, no scores
    ["tm1005", "Minimal Movie", "MOVIE", "2022", "", "", "[]", "", "", ""],
    # Valid with unicode title and long description
    [
        "tm1006",
        "日本語タイトル",
        "MOVIE",
        "2015",
        "A description.",
        "PG",
        "['Animation']",
        "7.0",
        "6.5",
        "30.0",
    ],
    # INVALID: bad type (will be discarded, Req 1.9)
    [
        "tm1007",
        "Bad Type Movie",
        "DOCUMENTARY",
        "2020",
        "Should be discarded.",
        "G",
        "['Documentary']",
        "6.0",
        "5.5",
        "10.0",
    ],
    # INVALID: non-parseable release year (will be discarded, Req 1.9)
    [
        "tm1008",
        "Bad Year Movie",
        "MOVIE",
        "not_a_year",
        "Should be discarded.",
        "PG",
        "['Drama']",
        "5.0",
        "4.0",
        "5.0",
    ],
]

# 15 credits: covering actors and directors for valid titles, with duplicates
FIXTURE_CREDITS = [
    # Credits for tm1001 (The Matrix)
    ["tm1001", "ACTOR", "p101", "Keanu Reeves", "Neo"],
    ["tm1001", "ACTOR", "p102", "Laurence Fishburne", "Morpheus"],
    ["tm1001", "DIRECTOR", "p201", "Lana Wachowski", ""],
    # Duplicate credit for tm1001 (same id, role, person_id — should dedup)
    ["tm1001", "ACTOR", "p101", "Keanu R.", "Neo v2"],
    # Credits for tm1002 (Inception)
    ["tm1002", "ACTOR", "p103", "Leonardo DiCaprio", "Cobb"],
    ["tm1002", "DIRECTOR", "p202", "Christopher Nolan", ""],
    # Credits for tm1003 (Amélie)
    ["tm1003", "ACTOR", "p104", "Audrey Tautou", "Amélie"],
    ["tm1003", "DIRECTOR", "p203", "Jean-Pierre Jeunet", ""],
    # Credits for ts2001 (Breaking Bad)
    ["ts2001", "ACTOR", "p105", "Bryan Cranston", "Walter White"],
    ["ts2001", "ACTOR", "p106", "Aaron Paul", "Jesse Pinkman"],
    ["ts2001", "DIRECTOR", "p204", "Vince Gilligan", ""],
    # Credits for ts2002 (Stranger Things)
    ["ts2002", "ACTOR", "p107", "Millie Bobby Brown", "Eleven"],
    # Credits for tm1004 (Parasite)
    ["tm1004", "DIRECTOR", "p205", "Bong Joon-ho", ""],
    ["tm1004", "ACTOR", "p108", "Song Kang-ho", "Ki-taek"],
    # Credit for an invalid title (tm1007 — will not appear in output since title is discarded)
    ["tm1007", "ACTOR", "p109", "Ghost Actor", "Role"],
]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _write_fixture_csvs(base_dir: Path) -> tuple[Path, Path]:
    """Write fixture CSVs and return their paths."""
    titles_path = base_dir / "titles.csv"
    credits_path = base_dir / "credits.csv"

    with open(titles_path, "w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(TITLES_HEADER)
        for row in FIXTURE_TITLES:
            writer.writerow(row)

    with open(credits_path, "w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(CREDITS_HEADER)
        for row in FIXTURE_CREDITS:
            writer.writerow(row)

    return titles_path, credits_path


def _make_config(
    titles_path: Path,
    credits_path: Path,
    output_dir: Path,
    version: str = "test_v1",
) -> EtlConfig:
    return EtlConfig(
        titles_path=titles_path,
        credits_path=credits_path,
        output_base_dir=output_dir,
        canonical_dataset_version=version,
        etl_version="1.0.0",
        schema_version="1.0.0",
    )


def _sha256_file(path: Path) -> str:
    """Compute SHA-256 hex digest of a file."""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()


def _run_etl(tmp_path: Path, version: str = "test_v1") -> tuple[EtlResult, Path]:
    """Write fixtures, run ETL, return result and output directory."""
    titles_path, credits_path = _write_fixture_csvs(tmp_path)
    output_dir = tmp_path / "output"
    config = _make_config(titles_path, credits_path, output_dir, version)
    etl = NetflixEtl(config)
    result = etl.run()
    return result, result.output_dir


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.integration
class TestEtlOutputStructure:
    """Verify the ETL produces all expected output files with correct structure."""

    def test_output_files_exist(self, tmp_path: Path) -> None:
        """Req 1.1: ETL produces titles.jsonl, metadata.json, quality_report.json."""
        _, output_dir = _run_etl(tmp_path)

        assert (output_dir / "titles.jsonl").exists()
        assert (output_dir / "metadata.json").exists()
        assert (output_dir / "quality_report.json").exists()

    def test_titles_jsonl_each_line_is_valid_json(self, tmp_path: Path) -> None:
        """Req 1.1: Each line in titles.jsonl is a valid JSON document."""
        _, output_dir = _run_etl(tmp_path)

        titles_path = output_dir / "titles.jsonl"
        lines = titles_path.read_text(encoding="utf-8").strip().splitlines()

        assert len(lines) > 0
        for line in lines:
            doc = json.loads(line)
            assert isinstance(doc, dict)
            assert "id" in doc
            assert "title" in doc

    def test_titles_jsonl_validates_against_canonical_schema(
        self, tmp_path: Path
    ) -> None:
        """Req 1.1, 2.1: Each document conforms to CanonicalNetflixTitle schema."""
        _, output_dir = _run_etl(tmp_path)

        titles_path = output_dir / "titles.jsonl"
        lines = titles_path.read_text(encoding="utf-8").strip().splitlines()

        for line in lines:
            doc = json.loads(line)
            # Should validate without error
            title = CanonicalNetflixTitle.model_validate(doc)
            assert title.type in ("movie", "show")
            assert 1888 <= title.release_year <= 2100

    def test_output_document_count_matches_valid_titles(self, tmp_path: Path) -> None:
        """ETL produces only valid titles (discards invalid ones)."""
        result, output_dir = _run_etl(tmp_path)

        titles_path = output_dir / "titles.jsonl"
        lines = titles_path.read_text(encoding="utf-8").strip().splitlines()

        # We have 10 titles in fixture, 2 are invalid
        assert len(lines) == 8
        assert result.document_count == 8

    def test_titles_sorted_by_id_ascending(self, tmp_path: Path) -> None:
        """Req 1.7: Output records sorted by id in lexicographic ascending order."""
        _, output_dir = _run_etl(tmp_path)

        titles_path = output_dir / "titles.jsonl"
        lines = titles_path.read_text(encoding="utf-8").strip().splitlines()
        ids = [json.loads(line)["id"] for line in lines]

        assert ids == sorted(ids)


@pytest.mark.integration
class TestEtlMetadata:
    """Verify metadata.json is correct and validates against EtlMetadata schema."""

    def test_metadata_validates_against_schema(self, tmp_path: Path) -> None:
        """Req 1.12: metadata.json validates against EtlMetadata Pydantic model."""
        _, output_dir = _run_etl(tmp_path)

        metadata_path = output_dir / "metadata.json"
        raw = json.loads(metadata_path.read_text(encoding="utf-8"))
        metadata = EtlMetadata.model_validate(raw)

        assert metadata.canonical_dataset_version == "test_v1"
        assert metadata.etl_version == "1.0.0"
        assert metadata.schema_version == "1.0.0"
        assert metadata.document_count == 8
        assert metadata.discarded_count == 2

    def test_metadata_output_checksum_matches_file(self, tmp_path: Path) -> None:
        """Req 1.12: output_checksum_sha256 in metadata matches actual titles.jsonl SHA-256."""
        _, output_dir = _run_etl(tmp_path)

        metadata_path = output_dir / "metadata.json"
        raw = json.loads(metadata_path.read_text(encoding="utf-8"))
        metadata = EtlMetadata.model_validate(raw)

        actual_checksum = _sha256_file(output_dir / "titles.jsonl")
        assert metadata.output_checksum_sha256 == actual_checksum

    def test_metadata_source_checksums_match_input_files(self, tmp_path: Path) -> None:
        """Req 1.12: source_checksums match SHA-256 of input CSV files."""
        titles_path, credits_path = _write_fixture_csvs(tmp_path)
        output_dir = tmp_path / "output"
        config = _make_config(titles_path, credits_path, output_dir)
        etl = NetflixEtl(config)
        result = etl.run()

        metadata_path = result.output_dir / "metadata.json"
        raw = json.loads(metadata_path.read_text(encoding="utf-8"))
        metadata = EtlMetadata.model_validate(raw)

        assert metadata.source_checksums["titles.csv"] == _sha256_file(titles_path)
        assert metadata.source_checksums["credits.csv"] == _sha256_file(credits_path)

    def test_metadata_type_distribution(self, tmp_path: Path) -> None:
        """Req 1.12: type_distribution shows correct counts."""
        _, output_dir = _run_etl(tmp_path)

        metadata_path = output_dir / "metadata.json"
        raw = json.loads(metadata_path.read_text(encoding="utf-8"))
        metadata = EtlMetadata.model_validate(raw)

        # 6 movies (tm1001-tm1006, minus invalid tm1007/tm1008) and 2 shows (ts2001, ts2002)
        assert metadata.type_distribution["movie"] == 6
        assert metadata.type_distribution["show"] == 2


@pytest.mark.integration
class TestEtlQualityReport:
    """Verify quality_report.json tracks discards correctly."""

    def test_quality_report_validates_against_schema(self, tmp_path: Path) -> None:
        """Req 1.11: quality_report.json validates as QualityReport."""
        _, output_dir = _run_etl(tmp_path)

        report_path = output_dir / "quality_report.json"
        raw = json.loads(report_path.read_text(encoding="utf-8"))
        report = QualityReport.model_validate(raw)

        assert report.total_discarded == 2

    def test_quality_report_discarded_records_content(self, tmp_path: Path) -> None:
        """Req 1.9, 1.11: Discarded records list the correct IDs and fields."""
        _, output_dir = _run_etl(tmp_path)

        report_path = output_dir / "quality_report.json"
        raw = json.loads(report_path.read_text(encoding="utf-8"))
        report = QualityReport.model_validate(raw)

        discarded_ids = {r.id_value for r in report.discarded_records}
        assert "tm1007" in discarded_ids  # bad type
        assert "tm1008" in discarded_ids  # bad release_year

        # Verify the fields that caused discards
        discarded_by_id = {r.id_value: r for r in report.discarded_records}
        assert discarded_by_id["tm1007"].field == "type"
        assert discarded_by_id["tm1008"].field == "release_year"

    def test_quality_report_field_coverage(self, tmp_path: Path) -> None:
        """Req 1.11: Field coverage reports percentage of non-null fields."""
        _, output_dir = _run_etl(tmp_path)

        report_path = output_dir / "quality_report.json"
        raw = json.loads(report_path.read_text(encoding="utf-8"))
        report = QualityReport.model_validate(raw)

        # All valid documents have 'id', 'title', 'type', 'release_year' → 100%
        assert report.field_coverage["id"] == 100.0
        assert report.field_coverage["title"] == 100.0
        assert report.field_coverage["type"] == 100.0
        assert report.field_coverage["release_year"] == 100.0

        # description: tm1005 has empty → null, so 7 out of 8 = 87.5%
        assert report.field_coverage["description"] == 87.5


@pytest.mark.integration
class TestEtlChecksums:
    """Verify checksums are computed correctly and match between result and metadata."""

    def test_result_checksum_matches_metadata_checksum(self, tmp_path: Path) -> None:
        """Req 1.12: EtlResult.output_checksum_sha256 matches metadata."""
        result, output_dir = _run_etl(tmp_path)

        metadata_path = output_dir / "metadata.json"
        raw = json.loads(metadata_path.read_text(encoding="utf-8"))
        metadata = EtlMetadata.model_validate(raw)

        assert result.output_checksum_sha256 == metadata.output_checksum_sha256

    def test_checksum_is_64_char_lowercase_hex(self, tmp_path: Path) -> None:
        """Checksums are 64-char lowercase hex strings (no prefix)."""
        result, _ = _run_etl(tmp_path)

        import re

        assert re.match(r"^[0-9a-f]{64}$", result.output_checksum_sha256)
        for checksum in result.source_checksums.values():
            assert re.match(r"^[0-9a-f]{64}$", checksum)


@pytest.mark.integration
class TestEtlDeterminism:
    """Verify two ETL runs on the same input produce identical output."""

    def test_two_runs_produce_identical_titles_jsonl(self, tmp_path: Path) -> None:
        """Req 1.2: Two runs with same input produce byte-identical titles.jsonl."""
        # First run
        run1_dir = tmp_path / "run1"
        run1_dir.mkdir()
        titles_path, credits_path = _write_fixture_csvs(run1_dir)
        output1 = run1_dir / "output"
        config1 = _make_config(titles_path, credits_path, output1)
        result1 = NetflixEtl(config1).run()

        # Second run (same fixture CSVs, different tmp directory)
        run2_dir = tmp_path / "run2"
        run2_dir.mkdir()
        titles_path2, credits_path2 = _write_fixture_csvs(run2_dir)
        output2 = run2_dir / "output"
        config2 = _make_config(titles_path2, credits_path2, output2)
        result2 = NetflixEtl(config2).run()

        # titles.jsonl should be byte-identical
        content1 = (result1.output_dir / "titles.jsonl").read_bytes()
        content2 = (result2.output_dir / "titles.jsonl").read_bytes()
        assert content1 == content2

    def test_two_runs_produce_identical_quality_report(self, tmp_path: Path) -> None:
        """Req 1.2: quality_report.json is byte-identical across runs."""
        # First run
        run1_dir = tmp_path / "run1"
        run1_dir.mkdir()
        titles_path, credits_path = _write_fixture_csvs(run1_dir)
        output1 = run1_dir / "output"
        config1 = _make_config(titles_path, credits_path, output1)
        result1 = NetflixEtl(config1).run()

        # Second run
        run2_dir = tmp_path / "run2"
        run2_dir.mkdir()
        titles_path2, credits_path2 = _write_fixture_csvs(run2_dir)
        output2 = run2_dir / "output"
        config2 = _make_config(titles_path2, credits_path2, output2)
        result2 = NetflixEtl(config2).run()

        qr1 = (result1.output_dir / "quality_report.json").read_bytes()
        qr2 = (result2.output_dir / "quality_report.json").read_bytes()
        assert qr1 == qr2

    def test_two_runs_produce_identical_checksums(self, tmp_path: Path) -> None:
        """Req 1.2: SHA-256 checksums are identical across runs."""
        # First run
        run1_dir = tmp_path / "run1"
        run1_dir.mkdir()
        titles_path, credits_path = _write_fixture_csvs(run1_dir)
        output1 = run1_dir / "output"
        config1 = _make_config(titles_path, credits_path, output1)
        result1 = NetflixEtl(config1).run()

        # Second run
        run2_dir = tmp_path / "run2"
        run2_dir.mkdir()
        titles_path2, credits_path2 = _write_fixture_csvs(run2_dir)
        output2 = run2_dir / "output"
        config2 = _make_config(titles_path2, credits_path2, output2)
        result2 = NetflixEtl(config2).run()

        assert result1.output_checksum_sha256 == result2.output_checksum_sha256

    def test_metadata_identical_except_generated_at(self, tmp_path: Path) -> None:
        """Req 1.2: metadata.json is identical except for generated_at timestamp."""
        # First run
        run1_dir = tmp_path / "run1"
        run1_dir.mkdir()
        titles_path, credits_path = _write_fixture_csvs(run1_dir)
        output1 = run1_dir / "output"
        config1 = _make_config(titles_path, credits_path, output1)
        result1 = NetflixEtl(config1).run()

        # Second run
        run2_dir = tmp_path / "run2"
        run2_dir.mkdir()
        titles_path2, credits_path2 = _write_fixture_csvs(run2_dir)
        output2 = run2_dir / "output"
        config2 = _make_config(titles_path2, credits_path2, output2)
        result2 = NetflixEtl(config2).run()

        meta1 = json.loads(
            (result1.output_dir / "metadata.json").read_text(encoding="utf-8")
        )
        meta2 = json.loads(
            (result2.output_dir / "metadata.json").read_text(encoding="utf-8")
        )

        # Remove generated_at before comparing
        meta1.pop("generated_at")
        meta2.pop("generated_at")
        assert meta1 == meta2


@pytest.mark.integration
class TestEtlDataTransformation:
    """Verify the ETL correctly transforms data (normalization, join, dedup)."""

    def test_type_normalized_to_lowercase(self, tmp_path: Path) -> None:
        """Req 1.4: Type is normalized to lowercase 'movie' or 'show'."""
        _, output_dir = _run_etl(tmp_path)

        titles_path = output_dir / "titles.jsonl"
        for line in titles_path.read_text(encoding="utf-8").strip().splitlines():
            doc = json.loads(line)
            assert doc["type"] in ("movie", "show")

    def test_genres_normalized_lowercase_sorted(self, tmp_path: Path) -> None:
        """Req 1.5: Genres are lowercase and alphabetically sorted."""
        _, output_dir = _run_etl(tmp_path)

        titles_path = output_dir / "titles.jsonl"
        for line in titles_path.read_text(encoding="utf-8").strip().splitlines():
            doc = json.loads(line)
            genres = doc["genres"]
            # All lowercase
            assert all(g == g.lower() for g in genres)
            # Sorted
            assert genres == sorted(genres)

    def test_actors_directors_joined_and_normalized(self, tmp_path: Path) -> None:
        """Req 1.7, 1.16: Credits are joined, names normalized to lowercase."""
        _, output_dir = _run_etl(tmp_path)

        titles_path = output_dir / "titles.jsonl"
        docs = {}
        for line in titles_path.read_text(encoding="utf-8").strip().splitlines():
            doc = json.loads(line)
            docs[doc["id"]] = doc

        # The Matrix: should have actors (deduplicated) and director
        matrix = docs["tm1001"]
        # "Keanu Reeves" and "Keanu R." are deduped by (id, role, person_id=p101)
        # Keep lexicographically smallest name: "Keanu R." < "Keanu Reeves"
        assert "keanu r." in matrix["actors"]
        assert "laurence fishburne" in matrix["actors"]
        assert "lana wachowski" in matrix["directors"]

        # All names lowercase
        for doc in docs.values():
            for actor in doc["actors"]:
                assert actor == actor.lower().strip()
            for director in doc["directors"]:
                assert director == director.lower().strip()

    def test_credits_deduplication(self, tmp_path: Path) -> None:
        """Req 1.8: Duplicate (id, role, person_id) keeps lexicographically smallest name."""
        _, output_dir = _run_etl(tmp_path)

        titles_path = output_dir / "titles.jsonl"
        docs = {}
        for line in titles_path.read_text(encoding="utf-8").strip().splitlines():
            doc = json.loads(line)
            docs[doc["id"]] = doc

        # tm1001 has duplicate: (tm1001, ACTOR, p101) with names "Keanu Reeves" and "Keanu R."
        # After dedup & normalization: keep "keanu r." (lexicographically smaller)
        matrix_actors = docs["tm1001"]["actors"]
        # Should NOT have both variants
        keanu_count = sum(1 for a in matrix_actors if "keanu" in a)
        assert keanu_count == 1
        assert "keanu r." in matrix_actors

    def test_title_without_credits_has_empty_lists(self, tmp_path: Path) -> None:
        """Req 1.18: Title without matching credits gets empty actor/director lists."""
        _, output_dir = _run_etl(tmp_path)

        titles_path = output_dir / "titles.jsonl"
        docs = {}
        for line in titles_path.read_text(encoding="utf-8").strip().splitlines():
            doc = json.loads(line)
            docs[doc["id"]] = doc

        # tm1005 "Minimal Movie" has no credits in our fixture
        minimal = docs["tm1005"]
        assert minimal["actors"] == []
        assert minimal["directors"] == []

    def test_empty_optional_fields_become_null(self, tmp_path: Path) -> None:
        """Req 1.10: Empty/whitespace optional fields become null in output."""
        _, output_dir = _run_etl(tmp_path)

        titles_path = output_dir / "titles.jsonl"
        docs = {}
        for line in titles_path.read_text(encoding="utf-8").strip().splitlines():
            doc = json.loads(line)
            docs[doc["id"]] = doc

        # tm1005 has empty description, empty age_cert, empty scores
        minimal = docs["tm1005"]
        assert minimal["description"] is None
        assert minimal["age_certification"] is None
        assert minimal["imdb_score"] is None
        assert minimal["tmdb_score"] is None
        assert minimal["tmdb_popularity"] is None

    def test_numeric_fields_are_proper_types(self, tmp_path: Path) -> None:
        """Req 1.6: Numeric fields are int/float, not strings."""
        _, output_dir = _run_etl(tmp_path)

        titles_path = output_dir / "titles.jsonl"
        for line in titles_path.read_text(encoding="utf-8").strip().splitlines():
            doc = json.loads(line)
            assert isinstance(doc["release_year"], int)
            if doc["imdb_score"] is not None:
                assert isinstance(doc["imdb_score"], (int, float))
            if doc["tmdb_score"] is not None:
                assert isinstance(doc["tmdb_score"], (int, float))
            if doc["tmdb_popularity"] is not None:
                assert isinstance(doc["tmdb_popularity"], (int, float))

    def test_ids_preserved_without_modification(self, tmp_path: Path) -> None:
        """Req 1.3: Native Netflix IDs are preserved unchanged."""
        _, output_dir = _run_etl(tmp_path)

        titles_path = output_dir / "titles.jsonl"
        output_ids = set()
        for line in titles_path.read_text(encoding="utf-8").strip().splitlines():
            doc = json.loads(line)
            output_ids.add(doc["id"])

        # All valid IDs from fixture should be present
        expected_valid_ids = {
            "tm1001",
            "tm1002",
            "tm1003",
            "tm1004",
            "tm1005",
            "tm1006",
            "ts2001",
            "ts2002",
        }
        assert output_ids == expected_valid_ids
