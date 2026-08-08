# tests/unit/test_etl_pipeline.py
"""Unit tests for the Netflix ETL pipeline orchestrator (NetflixEtl).

Tests cover:
- FileExistsError when output directory already exists
- Metadata generation with correct checksums and structure
- Quality report content with known discarded records
- FieldNullification for malformed genres
- Output checksum reproducibility (determinism)
- Temp directory cleanup on simulated failure
- End-to-end with small fixture CSVs

Validates: Requirements 1.1, 1.2, 1.11, 1.12, 1.13, 1.14
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from moviebot.etl.netflix_etl import EtlConfig, NetflixEtl
from moviebot.etl.schema import EtlMetadata

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

TITLES_HEADER = "id,title,type,release_year,description,age_certification,genres,imdb_score,tmdb_score,tmdb_popularity"
CREDITS_HEADER = "id,role,person_id,name,character"


def _write_csv(path: Path, header: str, rows: list[list[str]]) -> None:
    """Write a CSV file with the given header and rows using csv module for proper quoting."""
    import csv

    with open(path, "w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(header.split(","))
        for row in rows:
            writer.writerow(row)


def _make_config(tmp_path: Path, version: str = "v1") -> EtlConfig:
    """Create an EtlConfig pointing to CSVs and output in tmp_path."""
    return EtlConfig(
        titles_path=tmp_path / "titles.csv",
        credits_path=tmp_path / "credits.csv",
        output_base_dir=tmp_path / "output",
        canonical_dataset_version=version,
        etl_version="1.0.0",
        schema_version="1.0.0",
    )


def _valid_title_row(
    id_val: str = "tm100",
    title: str = "Test Movie",
    type_val: str = "MOVIE",
    release_year: str = "2020",
    description: str = "A great movie.",
    age_cert: str = "PG-13",
    genres: str = "['Drama', 'Action']",
    imdb: str = "7.5",
    tmdb_score: str = "7.0",
    tmdb_pop: str = "50.0",
) -> list[str]:
    return [
        id_val,
        title,
        type_val,
        release_year,
        description,
        age_cert,
        genres,
        imdb,
        tmdb_score,
        tmdb_pop,
    ]


def _valid_credit_row(
    id_val: str = "tm100",
    role: str = "ACTOR",
    person_id: str = "p1",
    name: str = "John Doe",
    character: str = "Hero",
) -> list[str]:
    return [id_val, role, person_id, name, character]


# ---------------------------------------------------------------------------
# Test: FileExistsError when output directory already exists
# ---------------------------------------------------------------------------


class TestFileExistsError:
    """Req 1.14: ETL SHALL abort if output version directory already exists."""

    def test_raises_file_exists_error_when_output_dir_exists(
        self, tmp_path: Path
    ) -> None:
        config = _make_config(tmp_path)
        _write_csv(config.titles_path, TITLES_HEADER, [_valid_title_row()])
        _write_csv(config.credits_path, CREDITS_HEADER, [_valid_credit_row()])

        # Pre-create the output directory
        output_dir = config.output_base_dir / config.canonical_dataset_version
        output_dir.mkdir(parents=True)

        etl = NetflixEtl(config)
        with pytest.raises(FileExistsError, match="already exists"):
            etl.run()


# ---------------------------------------------------------------------------
# Test: Metadata generation
# ---------------------------------------------------------------------------


class TestMetadataGeneration:
    """Req 1.12: metadata.json includes correct structure and checksums."""

    def test_metadata_validates_against_etl_metadata_model(
        self, tmp_path: Path
    ) -> None:
        config = _make_config(tmp_path)
        _write_csv(config.titles_path, TITLES_HEADER, [_valid_title_row()])
        _write_csv(config.credits_path, CREDITS_HEADER, [_valid_credit_row()])

        etl = NetflixEtl(config)
        result = etl.run()

        metadata_path = result.output_dir / "metadata.json"
        assert metadata_path.exists()

        raw = json.loads(metadata_path.read_text(encoding="utf-8"))
        # This will raise ValidationError if structure is wrong
        meta = EtlMetadata(**raw)

        assert meta.canonical_dataset_version == "v1"
        assert meta.etl_version == "1.0.0"
        assert meta.schema_version == "1.0.0"
        assert meta.document_count == 1
        assert meta.discarded_count == 0
        assert "titles.csv" in meta.source_checksums
        assert "credits.csv" in meta.source_checksums
        assert len(meta.output_checksum_sha256) == 64
        assert meta.type_distribution == {"movie": 1}

    def test_metadata_source_checksums_match_result(self, tmp_path: Path) -> None:
        config = _make_config(tmp_path)
        _write_csv(config.titles_path, TITLES_HEADER, [_valid_title_row()])
        _write_csv(config.credits_path, CREDITS_HEADER, [_valid_credit_row()])

        etl = NetflixEtl(config)
        result = etl.run()

        metadata_path = result.output_dir / "metadata.json"
        raw = json.loads(metadata_path.read_text(encoding="utf-8"))
        meta = EtlMetadata(**raw)

        # Checksums from result match those in metadata
        assert meta.source_checksums == result.source_checksums
        assert meta.output_checksum_sha256 == result.output_checksum_sha256


# ---------------------------------------------------------------------------
# Test: Quality report with known discarded records
# ---------------------------------------------------------------------------


class TestQualityReport:
    """Req 1.11: quality_report.json with discarded records info."""

    def test_quality_report_records_discarded_for_invalid_type(
        self, tmp_path: Path
    ) -> None:
        config = _make_config(tmp_path)
        rows = [
            _valid_title_row(id_val="tm1", type_val="MOVIE"),
            _valid_title_row(id_val="tm2", type_val="INVALID_TYPE"),
            _valid_title_row(id_val="tm3", type_val="SHOW"),
        ]
        _write_csv(config.titles_path, TITLES_HEADER, rows)
        _write_csv(config.credits_path, CREDITS_HEADER, [])

        etl = NetflixEtl(config)
        result = etl.run()

        assert result.document_count == 2
        assert result.discarded_count == 1

        report_path = result.output_dir / "quality_report.json"
        raw = json.loads(report_path.read_text(encoding="utf-8"))

        assert raw["total_discarded"] == 1
        assert len(raw["discarded_records"]) == 1
        discarded = raw["discarded_records"][0]
        assert discarded["id_value"] == "tm2"
        assert discarded["field"] == "type"
        assert discarded["original_value"] == "INVALID_TYPE"

    def test_quality_report_records_discarded_for_invalid_id(
        self, tmp_path: Path
    ) -> None:
        config = _make_config(tmp_path)
        rows = [
            _valid_title_row(id_val="BADID"),
            _valid_title_row(id_val="tm5", type_val="SHOW"),
        ]
        _write_csv(config.titles_path, TITLES_HEADER, rows)
        _write_csv(config.credits_path, CREDITS_HEADER, [])

        etl = NetflixEtl(config)
        result = etl.run()

        assert result.document_count == 1
        assert result.discarded_count == 1

        report_path = result.output_dir / "quality_report.json"
        raw = json.loads(report_path.read_text(encoding="utf-8"))
        discarded = raw["discarded_records"][0]
        assert discarded["id_value"] == "BADID"
        assert discarded["field"] == "id"

    def test_quality_report_has_field_coverage_and_type_distribution(
        self, tmp_path: Path
    ) -> None:
        config = _make_config(tmp_path)
        rows = [
            _valid_title_row(id_val="tm1", type_val="MOVIE"),
            _valid_title_row(id_val="tm2", type_val="SHOW"),
        ]
        _write_csv(config.titles_path, TITLES_HEADER, rows)
        _write_csv(config.credits_path, CREDITS_HEADER, [])

        etl = NetflixEtl(config)
        result = etl.run()

        report_path = result.output_dir / "quality_report.json"
        raw = json.loads(report_path.read_text(encoding="utf-8"))

        assert "field_coverage" in raw
        assert "type_distribution" in raw
        assert raw["type_distribution"] == {"movie": 1, "show": 1}
        # All required fields should have 100% coverage
        assert raw["field_coverage"]["id"] == 100.0
        assert raw["field_coverage"]["title"] == 100.0


# ---------------------------------------------------------------------------
# Test: FieldNullification for malformed genres
# ---------------------------------------------------------------------------


class TestFieldNullificationMalformedGenres:
    """ETL registers FieldNullification when parse_genres returns ([], True)."""

    def test_malformed_genres_registers_exactly_one_nullification(
        self, tmp_path: Path
    ) -> None:
        config = _make_config(tmp_path)
        # Malformed genres literal: not a valid Python list
        malformed_genres = "drama action"
        rows = [
            _valid_title_row(id_val="tm10", genres=malformed_genres),
        ]
        _write_csv(config.titles_path, TITLES_HEADER, rows)
        _write_csv(config.credits_path, CREDITS_HEADER, [])

        etl = NetflixEtl(config)
        result = etl.run()

        report_path = result.output_dir / "quality_report.json"
        raw = json.loads(report_path.read_text(encoding="utf-8"))

        nullifications = raw["field_nullifications"]
        assert len(nullifications) == 1
        n = nullifications[0]
        assert n["id_value"] == "tm10"
        assert n["field"] == "genres"
        assert n["reason"] == "malformed genres literal, defaulted to []"
        assert n["original_length"] is None
        assert n["max_length"] is None

    def test_valid_genres_do_not_produce_nullification(self, tmp_path: Path) -> None:
        config = _make_config(tmp_path)
        rows = [
            _valid_title_row(id_val="tm20", genres="['Comedy', 'Drama']"),
        ]
        _write_csv(config.titles_path, TITLES_HEADER, rows)
        _write_csv(config.credits_path, CREDITS_HEADER, [])

        etl = NetflixEtl(config)
        result = etl.run()

        report_path = result.output_dir / "quality_report.json"
        raw = json.loads(report_path.read_text(encoding="utf-8"))

        assert raw["field_nullifications"] == []


# ---------------------------------------------------------------------------
# Test: Output checksum reproducibility (determinism)
# ---------------------------------------------------------------------------


class TestDeterminism:
    """Req 1.2: Same inputs → same outputs byte-for-byte."""

    def test_output_checksums_are_reproducible(self, tmp_path: Path) -> None:
        # Run ETL twice with identical inputs in separate directories
        dir1 = tmp_path / "run1"
        dir1.mkdir()
        dir2 = tmp_path / "run2"
        dir2.mkdir()

        rows = [
            _valid_title_row(id_val="tm1"),
            _valid_title_row(id_val="tm2", title="Another Movie", type_val="SHOW"),
        ]
        credits = [
            _valid_credit_row(id_val="tm1", name="Alice Smith"),
            _valid_credit_row(
                id_val="tm2", role="DIRECTOR", person_id="p2", name="Bob Brown"
            ),
        ]

        for d in (dir1, dir2):
            _write_csv(d / "titles.csv", TITLES_HEADER, rows)
            _write_csv(d / "credits.csv", CREDITS_HEADER, credits)

        config1 = EtlConfig(
            titles_path=dir1 / "titles.csv",
            credits_path=dir1 / "credits.csv",
            output_base_dir=dir1 / "output",
            canonical_dataset_version="v1",
            etl_version="1.0.0",
            schema_version="1.0.0",
        )
        config2 = EtlConfig(
            titles_path=dir2 / "titles.csv",
            credits_path=dir2 / "credits.csv",
            output_base_dir=dir2 / "output",
            canonical_dataset_version="v1",
            etl_version="1.0.0",
            schema_version="1.0.0",
        )

        result1 = NetflixEtl(config1).run()
        result2 = NetflixEtl(config2).run()

        assert result1.output_checksum_sha256 == result2.output_checksum_sha256
        assert result1.document_count == result2.document_count

        # JSONL files are byte-identical
        jsonl1 = (result1.output_dir / "titles.jsonl").read_bytes()
        jsonl2 = (result2.output_dir / "titles.jsonl").read_bytes()
        assert jsonl1 == jsonl2


# ---------------------------------------------------------------------------
# Test: Temp directory cleanup on failure
# ---------------------------------------------------------------------------


class TestAtomicWriteCleanup:
    """Req 1.14: No partial output on failure; temp dir cleaned up."""

    def test_temp_dir_cleaned_up_on_failure(self, tmp_path: Path) -> None:
        config = _make_config(tmp_path)
        _write_csv(config.titles_path, TITLES_HEADER, [_valid_title_row()])
        _write_csv(config.credits_path, CREDITS_HEADER, [_valid_credit_row()])

        etl = NetflixEtl(config)

        # Monkeypatch _write_jsonl to simulate a failure mid-write
        original_write_jsonl = etl._write_jsonl

        def failing_write_jsonl(documents, path):
            # Write partial content then raise
            original_write_jsonl(documents, path)
            raise RuntimeError("Simulated write failure")

        with (
            patch.object(etl, "_write_jsonl", side_effect=failing_write_jsonl),
            pytest.raises(RuntimeError, match="Simulated write failure"),
        ):
            etl.run()

        output_dir = config.output_base_dir / config.canonical_dataset_version
        # Output dir should NOT exist after failure
        assert not output_dir.exists()

        # No leftover temp directories in the parent
        parent = config.output_base_dir
        if parent.exists():
            leftover = [
                p
                for p in parent.iterdir()
                if p.is_dir() and p.name.startswith(".etl_tmp_")
            ]
            assert leftover == []

    def test_no_partial_output_on_os_replace_failure(self, tmp_path: Path) -> None:
        config = _make_config(tmp_path)
        _write_csv(config.titles_path, TITLES_HEADER, [_valid_title_row()])
        _write_csv(config.credits_path, CREDITS_HEADER, [_valid_credit_row()])

        etl = NetflixEtl(config)

        # Simulate os.replace failure
        with (
            patch("os.replace", side_effect=OSError("Simulated rename failure")),
            pytest.raises(OSError, match="Simulated rename failure"),
        ):
            etl.run()

        output_dir = config.output_base_dir / config.canonical_dataset_version
        assert not output_dir.exists()


# ---------------------------------------------------------------------------
# Test: End-to-end with small fixture CSVs
# ---------------------------------------------------------------------------


class TestEndToEnd:
    """End-to-end ETL run with small fixture CSVs."""

    def test_end_to_end_valid_csvs(self, tmp_path: Path) -> None:
        config = _make_config(tmp_path)
        title_rows = [
            _valid_title_row(
                id_val="tm1",
                title="The Matrix",
                type_val="MOVIE",
                release_year="1999",
                genres="['Action', 'Sci-Fi']",
                imdb="8.7",
            ),
            _valid_title_row(
                id_val="tm2",
                title="Inception",
                type_val="MOVIE",
                release_year="2010",
                genres="['Action', 'Thriller']",
                imdb="8.8",
            ),
            _valid_title_row(
                id_val="ts3",
                title="Breaking Bad",
                type_val="SHOW",
                release_year="2008",
                genres="['Drama', 'Crime']",
                imdb="9.5",
            ),
        ]
        credit_rows = [
            _valid_credit_row(
                id_val="tm1", role="ACTOR", person_id="p1", name="Keanu Reeves"
            ),
            _valid_credit_row(
                id_val="tm1", role="DIRECTOR", person_id="p10", name="Lana Wachowski"
            ),
            _valid_credit_row(
                id_val="tm2", role="ACTOR", person_id="p2", name="Leonardo DiCaprio"
            ),
            _valid_credit_row(
                id_val="tm2", role="DIRECTOR", person_id="p11", name="Christopher Nolan"
            ),
            _valid_credit_row(
                id_val="ts3", role="ACTOR", person_id="p3", name="Bryan Cranston"
            ),
        ]
        _write_csv(config.titles_path, TITLES_HEADER, title_rows)
        _write_csv(config.credits_path, CREDITS_HEADER, credit_rows)

        etl = NetflixEtl(config)
        result = etl.run()

        # Check result
        assert result.document_count == 3
        assert result.discarded_count == 0

        # Check output directory structure
        assert result.output_dir.exists()
        assert (result.output_dir / "titles.jsonl").exists()
        assert (result.output_dir / "metadata.json").exists()
        assert (result.output_dir / "quality_report.json").exists()

        # Verify JSONL content
        jsonl_path = result.output_dir / "titles.jsonl"
        lines = jsonl_path.read_text(encoding="utf-8").strip().split("\n")
        assert len(lines) == 3

        docs = [json.loads(line) for line in lines]
        # Documents sorted by id (léxico-ascendente)
        assert docs[0]["id"] == "tm1"
        assert docs[1]["id"] == "tm2"
        assert docs[2]["id"] == "ts3"

        # Check genres normalized (lowercase + sorted)
        assert docs[0]["genres"] == ["action", "sci-fi"]
        assert docs[2]["genres"] == ["crime", "drama"]

        # Check actors/directors joined and normalized
        assert docs[0]["actors"] == ["keanu reeves"]
        assert docs[0]["directors"] == ["lana wachowski"]
        assert docs[1]["actors"] == ["leonardo dicaprio"]
        assert docs[1]["directors"] == ["christopher nolan"]
        assert docs[2]["actors"] == ["bryan cranston"]
        assert docs[2]["directors"] == []

    def test_end_to_end_mixed_valid_and_invalid(self, tmp_path: Path) -> None:
        config = _make_config(tmp_path)
        title_rows = [
            _valid_title_row(id_val="tm1", title="Valid Movie", type_val="MOVIE"),
            _valid_title_row(
                id_val="INVALID_ID", title="Bad ID Movie", type_val="MOVIE"
            ),
            _valid_title_row(id_val="tm3", title="", type_val="MOVIE"),  # empty title
            _valid_title_row(
                id_val="tm4",
                title="No Year",
                type_val="SHOW",
                release_year="not_a_year",
            ),
        ]
        credit_rows = [
            _valid_credit_row(
                id_val="tm1", role="ACTOR", person_id="p1", name="Jane Doe"
            ),
        ]
        _write_csv(config.titles_path, TITLES_HEADER, title_rows)
        _write_csv(config.credits_path, CREDITS_HEADER, credit_rows)

        etl = NetflixEtl(config)
        result = etl.run()

        assert result.document_count == 1
        assert result.discarded_count == 3

        # Quality report records all 3 discarded records
        report_path = result.output_dir / "quality_report.json"
        raw = json.loads(report_path.read_text(encoding="utf-8"))
        assert raw["total_discarded"] == 3
        assert len(raw["discarded_records"]) == 3

    def test_end_to_end_no_credits_produces_empty_actor_director_lists(
        self, tmp_path: Path
    ) -> None:
        """Req 1.18: Titles without credits have empty actor/director lists."""
        config = _make_config(tmp_path)
        _write_csv(
            config.titles_path,
            TITLES_HEADER,
            [
                _valid_title_row(id_val="tm1"),
            ],
        )
        _write_csv(config.credits_path, CREDITS_HEADER, [])

        etl = NetflixEtl(config)
        result = etl.run()

        jsonl_path = result.output_dir / "titles.jsonl"
        doc = json.loads(jsonl_path.read_text(encoding="utf-8").strip())
        assert doc["actors"] == []
        assert doc["directors"] == []

    def test_end_to_end_type_normalization(self, tmp_path: Path) -> None:
        """Req 1.4: Type normalized to lowercase 'movie' or 'show'."""
        config = _make_config(tmp_path)
        _write_csv(
            config.titles_path,
            TITLES_HEADER,
            [
                _valid_title_row(id_val="tm1", type_val="Movie"),
                _valid_title_row(id_val="tm2", type_val="SHOW"),
                _valid_title_row(id_val="tm3", type_val="  show  "),
            ],
        )
        _write_csv(config.credits_path, CREDITS_HEADER, [])

        etl = NetflixEtl(config)
        result = etl.run()

        jsonl_path = result.output_dir / "titles.jsonl"
        lines = jsonl_path.read_text(encoding="utf-8").strip().split("\n")
        docs = [json.loads(line) for line in lines]

        assert all(doc["type"] in ("movie", "show") for doc in docs)
