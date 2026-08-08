# src/moviebot/etl/netflix_etl.py
"""Netflix ETL pipeline orchestrator.

Transforms raw Netflix CSVs (titles.csv, credits.csv) into a versioned
canonical dataset (JSONL) with deterministic output and atomic writes.
"""

from __future__ import annotations

import csv
import hashlib
import json
import os
import shutil
import tempfile
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from moviebot.etl.quality_report import (
    DiscardedRecord,
    FieldNullification,
    QualityReport,
)
from moviebot.etl.schema import EtlMetadata
from moviebot.etl.transformers import (
    normalize_name,
    normalize_type,
    nullify_if_exceeds,
    parse_genres,
    parse_optional_float,
    parse_release_year,
    validate_id,
    validate_title,
)


@dataclass(frozen=True)
class EtlConfig:
    """Configuración del ETL."""

    titles_path: Path
    credits_path: Path
    output_base_dir: Path  # data/processed/netflix/
    canonical_dataset_version: str  # e.g. "v1"
    etl_version: str  # e.g. "1.0.0"
    schema_version: str  # e.g. "1.0.0"


@dataclass(frozen=True)
class EtlResult:
    """Resultado de la ejecución del ETL."""

    output_dir: Path
    document_count: int
    discarded_count: int
    output_checksum_sha256: str  # 64-char hex, no prefix
    source_checksums: dict[str, str]  # filename -> 64-char hex sha256


class NetflixEtl:
    """Pipeline ETL determinista para Netflix CSVs → JSONL canónico."""

    def __init__(self, config: EtlConfig) -> None:
        self._config = config

    def run(self) -> EtlResult:
        """Ejecuta el pipeline completo. Escritura atómica via tmp+rename."""
        output_dir = (
            self._config.output_base_dir / self._config.canonical_dataset_version
        )

        # Abort if output version directory already exists
        if output_dir.exists():
            raise FileExistsError(f"Output directory already exists: {output_dir}")

        # Compute source checksums from raw bytes
        source_checksums = self._compute_source_checksums()

        # Read and parse CSVs
        titles_rows = self._read_csv(self._config.titles_path)
        credits_rows = self._read_csv(self._config.credits_path)

        # Transform titles and collect quality issues
        documents, discarded_records, field_nullifications = self._transform_titles(
            titles_rows
        )

        # Join credits (deduplicated) into documents
        self._join_credits(documents, credits_rows)

        # Sort documents by id for determinism
        documents.sort(key=lambda doc: doc["id"])

        # Sort internal lists in each document
        for doc in documents:
            doc["genres"] = sorted(doc.get("genres", []))
            doc["actors"] = sorted(doc.get("actors", []))
            doc["directors"] = sorted(doc.get("directors", []))

        # Compute field coverage and type distribution
        field_coverage = self._compute_field_coverage(documents)
        type_distribution = self._compute_type_distribution(documents)

        # Sort quality report records deterministically
        discarded_records.sort(key=lambda r: (r.id_value, r.field))
        field_nullifications.sort(key=lambda r: (r.id_value, r.field))

        # Build quality report
        quality_report = QualityReport(
            total_discarded=len(discarded_records),
            discarded_records=discarded_records,
            field_coverage=field_coverage,
            type_distribution=type_distribution,
            field_nullifications=field_nullifications,
        )

        # Atomic write: tmp dir + os.replace rename
        tmp_dir = None
        try:
            # Create temp directory in the same parent as output_dir for same-filesystem rename
            output_dir.parent.mkdir(parents=True, exist_ok=True)
            tmp_dir = Path(
                tempfile.mkdtemp(prefix=".etl_tmp_", dir=str(output_dir.parent))
            )

            # Write titles.jsonl
            titles_jsonl_path = tmp_dir / "titles.jsonl"
            self._write_jsonl(documents, titles_jsonl_path)

            # Compute output checksum from raw bytes
            output_checksum = self._sha256_file(titles_jsonl_path)

            # Write metadata.json
            metadata = EtlMetadata(
                canonical_dataset_version=self._config.canonical_dataset_version,
                etl_version=self._config.etl_version,
                schema_version=self._config.schema_version,
                document_count=len(documents),
                discarded_count=len(discarded_records),
                source_checksums=source_checksums,
                output_checksum_sha256=output_checksum,
                generated_at=datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
                type_distribution=type_distribution,
            )
            metadata_path = tmp_dir / "metadata.json"
            metadata_content = (
                json.dumps(
                    metadata.model_dump(mode="json"),
                    sort_keys=True,
                    separators=(",", ":"),
                    ensure_ascii=False,
                )
                + "\n"
            )
            metadata_path.write_text(metadata_content, encoding="utf-8")

            # Write quality_report.json
            quality_report_path = tmp_dir / "quality_report.json"
            report_content = (
                json.dumps(
                    quality_report.model_dump(mode="json"),
                    sort_keys=True,
                    separators=(",", ":"),
                    ensure_ascii=False,
                )
                + "\n"
            )
            quality_report_path.write_text(report_content, encoding="utf-8")

            # Atomic rename
            os.replace(str(tmp_dir), str(output_dir))
            tmp_dir = None  # Prevent cleanup since rename succeeded

        except BaseException:
            # Clean up temp directory completely on any failure
            if tmp_dir is not None and tmp_dir.exists():
                shutil.rmtree(str(tmp_dir), ignore_errors=True)
            raise

        return EtlResult(
            output_dir=output_dir,
            document_count=len(documents),
            discarded_count=len(discarded_records),
            output_checksum_sha256=output_checksum,
            source_checksums=source_checksums,
        )

    def _compute_source_checksums(self) -> dict[str, str]:
        """Compute SHA-256 checksums of source CSV files from raw bytes."""
        checksums: dict[str, str] = {}
        checksums[self._config.titles_path.name] = self._sha256_file(
            self._config.titles_path
        )
        checksums[self._config.credits_path.name] = self._sha256_file(
            self._config.credits_path
        )
        return checksums

    def _read_csv(self, path: Path) -> list[dict[str, str]]:
        """Read a CSV file and return rows as list of dicts."""
        with open(path, encoding="utf-8", newline="") as f:
            reader = csv.DictReader(f)
            return list(reader)

    def _transform_titles(
        self, rows: list[dict[str, str]]
    ) -> tuple[list[dict], list[DiscardedRecord], list[FieldNullification]]:
        """Transform title rows, validating and normalizing fields.

        Returns (valid_documents, discarded_records, field_nullifications).
        """
        documents: list[dict] = []
        discarded: list[DiscardedRecord] = []
        nullifications: list[FieldNullification] = []

        for row in rows:
            raw_id = row.get("id", "")
            raw_title = row.get("title", "")
            raw_type = row.get("type", "")
            raw_release_year = row.get("release_year", "")

            # Validate mandatory fields - discard if invalid
            valid_id = validate_id(raw_id)
            if valid_id is None:
                discarded.append(
                    DiscardedRecord(
                        id_value=raw_id.strip() if raw_id else "",
                        field="id",
                        reason="invalid id format",
                        original_value=raw_id,
                    )
                )
                continue

            valid_title = validate_title(raw_title)
            if valid_title is None:
                discarded.append(
                    DiscardedRecord(
                        id_value=valid_id,
                        field="title",
                        reason="invalid or empty title",
                        original_value=raw_title,
                    )
                )
                continue

            valid_type = normalize_type(raw_type)
            if valid_type is None:
                discarded.append(
                    DiscardedRecord(
                        id_value=valid_id,
                        field="type",
                        reason="invalid type value",
                        original_value=raw_type,
                    )
                )
                continue

            valid_year = parse_release_year(raw_release_year)
            if valid_year is None:
                discarded.append(
                    DiscardedRecord(
                        id_value=valid_id,
                        field="release_year",
                        reason="invalid or out-of-range release year",
                        original_value=raw_release_year,
                    )
                )
                continue

            # Process optional fields
            raw_description = row.get("description", None)
            description = nullify_if_exceeds(raw_description, 2000)
            if raw_description is not None:
                trimmed_desc = raw_description.strip()
                if trimmed_desc and len(trimmed_desc) > 2000:
                    nullifications.append(
                        FieldNullification(
                            id_value=valid_id,
                            field="description",
                            reason="exceeded max_length 2000",
                            original_length=len(trimmed_desc),
                            max_length=2000,
                        )
                    )

            raw_age_cert = row.get("age_certification", None)
            age_certification = nullify_if_exceeds(raw_age_cert, 20)
            if raw_age_cert is not None:
                trimmed_cert = raw_age_cert.strip()
                if trimmed_cert and len(trimmed_cert) > 20:
                    nullifications.append(
                        FieldNullification(
                            id_value=valid_id,
                            field="age_certification",
                            reason="exceeded max_length 20",
                            original_length=len(trimmed_cert),
                            max_length=20,
                        )
                    )

            # Parse genres
            raw_genres = row.get("genres", "")
            genres, malformed = parse_genres(raw_genres)
            if malformed:
                nullifications.append(
                    FieldNullification(
                        id_value=valid_id,
                        field="genres",
                        reason="malformed genres literal, defaulted to []",
                        original_length=None,
                        max_length=None,
                    )
                )

            # Parse numeric optional fields
            raw_imdb = row.get("imdb_score", "")
            imdb_score = parse_optional_float(raw_imdb, 0.0, 10.0)

            raw_tmdb_score = row.get("tmdb_score", "")
            tmdb_score = parse_optional_float(raw_tmdb_score, 0.0, 10.0)

            raw_tmdb_pop = row.get("tmdb_popularity", "")
            tmdb_popularity = parse_optional_float(raw_tmdb_pop, 0.0, 10000.0)

            doc: dict = {
                "id": valid_id,
                "title": valid_title,
                "type": valid_type,
                "release_year": valid_year,
                "description": description,
                "age_certification": age_certification,
                "genres": sorted(genres),
                "actors": [],
                "directors": [],
                "imdb_score": imdb_score,
                "tmdb_score": tmdb_score,
                "tmdb_popularity": tmdb_popularity,
            }
            documents.append(doc)

        return documents, discarded, nullifications

    def _join_credits(
        self, documents: list[dict], credits_rows: list[dict[str, str]]
    ) -> None:
        """Join credits into documents by id, with deduplication.

        Credits deduplication: key = (id, role, person_id).
        For duplicate keys, keep entry with lexicographically smallest
        normalized name.
        """
        # Build a mapping from id to document for efficient lookup
        doc_by_id: dict[str, dict] = {doc["id"]: doc for doc in documents}

        # Deduplicate credits: key = (id, role, person_id) -> smallest name
        deduped: dict[tuple[str, str, str], str] = {}

        for credit_row in credits_rows:
            credit_id = credit_row.get("id", "").strip()
            role = credit_row.get("role", "").strip().lower()
            person_id = credit_row.get("person_id", "").strip()
            raw_name = credit_row.get("name", "")

            # Skip if the title is not in our valid documents
            if credit_id not in doc_by_id:
                continue

            # Only process ACTOR and DIRECTOR roles
            if role not in ("actor", "director"):
                continue

            normalized = normalize_name(raw_name)
            if not normalized:
                continue

            key = (credit_id, role, person_id)
            if key not in deduped or normalized < deduped[key]:
                deduped[key] = normalized

        # Assign credits to documents
        for (credit_id, role, _person_id), name in deduped.items():
            doc = doc_by_id.get(credit_id)
            if doc is None:
                continue
            if role == "actor":
                doc["actors"].append(name)
            elif role == "director":
                doc["directors"].append(name)

    def _compute_field_coverage(self, documents: list[dict]) -> dict[str, float]:
        """Compute percentage of non-null values per field (0.0-100.0)."""
        if not documents:
            return {}

        total = len(documents)
        fields = [
            "id",
            "title",
            "type",
            "release_year",
            "description",
            "age_certification",
            "genres",
            "actors",
            "directors",
            "imdb_score",
            "tmdb_score",
            "tmdb_popularity",
        ]

        coverage: dict[str, float] = {}
        for field in fields:
            non_null_count = 0
            for doc in documents:
                value = doc.get(field)
                if value is not None:
                    # For lists, consider empty list as "present" (not null)
                    non_null_count += 1
            coverage[field] = round((non_null_count / total) * 100.0, 2)

        return coverage

    def _compute_type_distribution(self, documents: list[dict]) -> dict[str, int]:
        """Compute count per type ('movie', 'show')."""
        distribution: dict[str, int] = {}
        for doc in documents:
            doc_type = doc["type"]
            distribution[doc_type] = distribution.get(doc_type, 0) + 1
        return distribution

    def _write_jsonl(self, documents: list[dict], path: Path) -> None:
        """Write documents as JSONL with deterministic serialization."""
        with open(path, "w", encoding="utf-8", newline="") as f:
            for doc in documents:
                line = json.dumps(
                    doc, sort_keys=True, separators=(",", ":"), ensure_ascii=False
                )
                f.write(line + "\n")

    @staticmethod
    def _sha256_file(path: Path) -> str:
        """Compute SHA-256 hex digest of a file by reading raw bytes."""
        h = hashlib.sha256()
        with open(path, "rb") as f:
            while True:
                chunk = f.read(65536)
                if not chunk:
                    break
                h.update(chunk)
        return h.hexdigest()


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(
        description="Run Netflix ETL pipeline: transform raw CSVs into canonical JSONL dataset."
    )
    parser.add_argument(
        "--titles",
        type=Path,
        default=Path("raw_data/netflix/titles.csv"),
        help="Path to titles CSV (default: raw_data/netflix/titles.csv)",
    )
    parser.add_argument(
        "--credits",
        type=Path,
        default=Path("raw_data/netflix/credits.csv"),
        help="Path to credits CSV (default: raw_data/netflix/credits.csv)",
    )
    parser.add_argument(
        "--version",
        type=str,
        required=True,
        help="Canonical dataset version identifier (e.g. 'v1')",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("data/processed/netflix"),
        help="Base output directory (default: data/processed/netflix)",
    )
    parser.add_argument(
        "--etl-version",
        type=str,
        default="1.0.0",
        help="ETL version string (default: 1.0.0)",
    )
    parser.add_argument(
        "--schema-version",
        type=str,
        default="1.0.0",
        help="Schema version string (default: 1.0.0)",
    )

    args = parser.parse_args()

    config = EtlConfig(
        titles_path=args.titles,
        credits_path=args.credits,
        output_base_dir=args.output_dir,
        canonical_dataset_version=args.version,
        etl_version=args.etl_version,
        schema_version=args.schema_version,
    )

    etl = NetflixEtl(config)
    result = etl.run()

    print("ETL completed successfully.")
    print(f"  document_count: {result.document_count}")
    print(f"  discarded_count: {result.discarded_count}")
    print(f"  output_checksum_sha256: {result.output_checksum_sha256}")
    print(f"  output_dir: {result.output_dir}")
