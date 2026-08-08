"""Unit tests for CanonicalNetflixAdapter.

Validates Requirements: 3.1, 3.2, 3.3, 3.4, 3.8
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from moviebot.evals.silver.adapters import CanonicalNetflixAdapter
from moviebot.evals.silver.models import NetflixHardConstraints

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

DATASET_VERSION = "test_v1"
ETL_VERSION = "1.0.0"
SCHEMA_VERSION = "1.0.0"


def _serialize_title(doc: dict) -> str:
    """Serialize a title document to a deterministic JSON line."""
    return json.dumps(doc, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _make_titles_jsonl(docs: list[dict]) -> bytes:
    """Create a titles.jsonl bytes payload from a list of docs."""
    lines = [_serialize_title(d) for d in docs]
    content = "\n".join(lines) + "\n"
    return content.encode("utf-8")


def _compute_checksum(data: bytes) -> str:
    """Compute SHA-256 hex digest."""
    return hashlib.sha256(data).hexdigest()


def _make_metadata(
    *,
    canonical_dataset_version: str = DATASET_VERSION,
    etl_version: str = ETL_VERSION,
    schema_version: str = SCHEMA_VERSION,
    document_count: int,
    output_checksum_sha256: str,
) -> str:
    """Create a valid metadata.json string."""
    meta = {
        "canonical_dataset_version": canonical_dataset_version,
        "etl_version": etl_version,
        "schema_version": schema_version,
        "document_count": document_count,
        "discarded_count": 0,
        "source_checksums": {
            "titles.csv": "a" * 64,
            "credits.csv": "b" * 64,
        },
        "output_checksum_sha256": output_checksum_sha256,
        "generated_at": "2024-01-15T10:30:00Z",
        "type_distribution": {"movie": document_count, "show": 0},
    }
    return json.dumps(meta, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _sample_docs() -> list[dict]:
    """Return a minimal set of valid title documents for testing."""
    return [
        {
            "id": "tm001",
            "title": "Test Movie Alpha",
            "type": "movie",
            "release_year": 2020,
            "description": "A test movie",
            "age_certification": "PG-13",
            "genres": ["action", "drama"],
            "actors": ["alice smith", "bob jones"],
            "directors": ["carol white"],
            "imdb_score": 7.5,
            "tmdb_score": 7.0,
            "tmdb_popularity": 100.0,
        },
        {
            "id": "ts002",
            "title": "Test Show Beta",
            "type": "show",
            "release_year": 2019,
            "description": "A test show",
            "age_certification": "TV-MA",
            "genres": ["comedy"],
            "actors": ["dave lee"],
            "directors": ["eve black", "carol white"],
            "imdb_score": 8.0,
            "tmdb_score": 8.5,
            "tmdb_popularity": 200.0,
        },
        {
            "id": "tm003",
            "title": "Test Movie Gamma",
            "type": "movie",
            "release_year": 2021,
            "description": None,
            "age_certification": None,
            "genres": ["drama", "romance"],
            "actors": ["alice smith", "frank green"],
            "directors": ["george hill"],
            "imdb_score": 6.0,
            "tmdb_score": None,
            "tmdb_popularity": None,
        },
    ]


@pytest.fixture
def valid_dataset(tmp_path: Path) -> Path:
    """Create a valid dataset directory and return base_dir."""
    docs = _sample_docs()
    version_dir = tmp_path / DATASET_VERSION
    version_dir.mkdir(parents=True)

    titles_bytes = _make_titles_jsonl(docs)
    checksum = _compute_checksum(titles_bytes)

    (version_dir / "titles.jsonl").write_bytes(titles_bytes)
    metadata_str = _make_metadata(
        document_count=len(docs),
        output_checksum_sha256=checksum,
    )
    (version_dir / "metadata.json").write_text(metadata_str, encoding="utf-8")

    return tmp_path


# ---------------------------------------------------------------------------
# 1. Happy path: valid JSONL + metadata → loads correctly
# ---------------------------------------------------------------------------


class TestHappyPath:
    """Test loading valid JSONL + metadata — Validates: Requirements 3.1"""

    def test_loads_correctly(self, valid_dataset: Path) -> None:
        adapter = CanonicalNetflixAdapter(
            canonical_dataset_version=DATASET_VERSION,
            base_dir=valid_dataset,
        )
        assert adapter.canonical_dataset_version == DATASET_VERSION
        assert adapter.etl_version == ETL_VERSION
        assert adapter.schema_version == SCHEMA_VERSION

    def test_id_exists(self, valid_dataset: Path) -> None:
        adapter = CanonicalNetflixAdapter(
            canonical_dataset_version=DATASET_VERSION,
            base_dir=valid_dataset,
        )
        assert adapter.id_exists("tm001") is True
        assert adapter.id_exists("ts002") is True
        assert adapter.id_exists("tm003") is True
        assert adapter.id_exists("tm999") is False

    def test_get_title(self, valid_dataset: Path) -> None:
        adapter = CanonicalNetflixAdapter(
            canonical_dataset_version=DATASET_VERSION,
            base_dir=valid_dataset,
        )
        title = adapter.get_title("tm001")
        assert title is not None
        assert title.id == "tm001"
        assert title.title == "Test Movie Alpha"
        assert title.type == "movie"
        assert title.release_year == 2020

    def test_get_description(self, valid_dataset: Path) -> None:
        adapter = CanonicalNetflixAdapter(
            canonical_dataset_version=DATASET_VERSION,
            base_dir=valid_dataset,
        )
        assert adapter.get_description("tm001") == "A test movie"
        assert adapter.get_description("tm003") is None
        assert adapter.get_description("nonexistent") is None

    def test_get_actors_for_title(self, valid_dataset: Path) -> None:
        adapter = CanonicalNetflixAdapter(
            canonical_dataset_version=DATASET_VERSION,
            base_dir=valid_dataset,
        )
        assert adapter.get_actors_for_title("tm001") == ["alice smith", "bob jones"]
        assert adapter.get_actors_for_title("nonexistent") == []

    def test_get_directors_for_title(self, valid_dataset: Path) -> None:
        adapter = CanonicalNetflixAdapter(
            canonical_dataset_version=DATASET_VERSION,
            base_dir=valid_dataset,
        )
        assert adapter.get_directors_for_title("tm001") == ["carol white"]
        assert adapter.get_directors_for_title("nonexistent") == []

    def test_output_checksum_exposed(self, valid_dataset: Path) -> None:
        adapter = CanonicalNetflixAdapter(
            canonical_dataset_version=DATASET_VERSION,
            base_dir=valid_dataset,
        )
        docs = _sample_docs()
        expected_checksum = _compute_checksum(_make_titles_jsonl(docs))
        assert adapter.output_checksum_sha256 == expected_checksum


# ---------------------------------------------------------------------------
# 2. Missing titles.jsonl → FileNotFoundError
# ---------------------------------------------------------------------------


class TestMissingTitlesJsonl:
    """Validates: Requirements 3.2"""

    def test_raises_file_not_found(self, tmp_path: Path) -> None:
        version_dir = tmp_path / DATASET_VERSION
        version_dir.mkdir(parents=True)
        # Only create metadata, not titles.jsonl
        (version_dir / "metadata.json").write_text("{}", encoding="utf-8")

        with pytest.raises(FileNotFoundError, match="titles.jsonl"):
            CanonicalNetflixAdapter(
                canonical_dataset_version=DATASET_VERSION,
                base_dir=tmp_path,
            )


# ---------------------------------------------------------------------------
# 3. Missing metadata.json → FileNotFoundError
# ---------------------------------------------------------------------------


class TestMissingMetadata:
    """Validates: Requirements 3.2"""

    def test_raises_file_not_found(self, tmp_path: Path) -> None:
        version_dir = tmp_path / DATASET_VERSION
        version_dir.mkdir(parents=True)
        # Only create titles.jsonl, not metadata.json
        docs = _sample_docs()
        (version_dir / "titles.jsonl").write_bytes(_make_titles_jsonl(docs))

        with pytest.raises(FileNotFoundError, match="metadata.json"):
            CanonicalNetflixAdapter(
                canonical_dataset_version=DATASET_VERSION,
                base_dir=tmp_path,
            )


# ---------------------------------------------------------------------------
# 4. Empty dataset (0 documents) → ValueError
# ---------------------------------------------------------------------------


class TestEmptyDataset:
    """Validates: Requirements 3.8"""

    def test_raises_value_error(self, tmp_path: Path) -> None:
        version_dir = tmp_path / DATASET_VERSION
        version_dir.mkdir(parents=True)

        # Empty titles file (no lines)
        titles_bytes = b""
        checksum = _compute_checksum(titles_bytes)

        (version_dir / "titles.jsonl").write_bytes(titles_bytes)
        metadata_str = _make_metadata(
            document_count=0,
            output_checksum_sha256=checksum,
        )
        (version_dir / "metadata.json").write_text(metadata_str, encoding="utf-8")

        with pytest.raises(ValueError, match="vacío|empty"):
            CanonicalNetflixAdapter(
                canonical_dataset_version=DATASET_VERSION,
                base_dir=tmp_path,
            )


# ---------------------------------------------------------------------------
# 5. Checksum mismatch → ValueError
# ---------------------------------------------------------------------------


class TestChecksumMismatch:
    """Validates: Requirements 3.1"""

    def test_raises_value_error(self, tmp_path: Path) -> None:
        version_dir = tmp_path / DATASET_VERSION
        version_dir.mkdir(parents=True)

        docs = _sample_docs()
        titles_bytes = _make_titles_jsonl(docs)
        # Use a wrong checksum
        wrong_checksum = "0" * 64

        (version_dir / "titles.jsonl").write_bytes(titles_bytes)
        metadata_str = _make_metadata(
            document_count=len(docs),
            output_checksum_sha256=wrong_checksum,
        )
        (version_dir / "metadata.json").write_text(metadata_str, encoding="utf-8")

        with pytest.raises(ValueError, match="[Cc]hecksum"):
            CanonicalNetflixAdapter(
                canonical_dataset_version=DATASET_VERSION,
                base_dir=tmp_path,
            )


# ---------------------------------------------------------------------------
# 6. Version mismatch → ValueError
# ---------------------------------------------------------------------------


class TestVersionMismatch:
    """Validates: Requirements 3.1"""

    def test_raises_value_error(self, tmp_path: Path) -> None:
        version_dir = tmp_path / DATASET_VERSION
        version_dir.mkdir(parents=True)

        docs = _sample_docs()
        titles_bytes = _make_titles_jsonl(docs)
        checksum = _compute_checksum(titles_bytes)

        (version_dir / "titles.jsonl").write_bytes(titles_bytes)
        # metadata has different canonical_dataset_version
        metadata_str = _make_metadata(
            canonical_dataset_version="different_version",
            document_count=len(docs),
            output_checksum_sha256=checksum,
        )
        (version_dir / "metadata.json").write_text(metadata_str, encoding="utf-8")

        with pytest.raises(ValueError, match="[Vv]ersion mismatch"):
            CanonicalNetflixAdapter(
                canonical_dataset_version=DATASET_VERSION,
                base_dir=tmp_path,
            )


# ---------------------------------------------------------------------------
# 7. Filter with genres AND → correct IDs
# ---------------------------------------------------------------------------


class TestFilterGenresAnd:
    """Validates: Requirements 3.4"""

    def test_single_genre(self, valid_dataset: Path) -> None:
        adapter = CanonicalNetflixAdapter(
            canonical_dataset_version=DATASET_VERSION,
            base_dir=valid_dataset,
        )
        constraints = NetflixHardConstraints(genres=["drama"])
        result = adapter.filter(constraints)
        # tm001 has ["action", "drama"], tm003 has ["drama", "romance"]
        assert result == ["tm001", "tm003"]

    def test_multiple_genres_and(self, valid_dataset: Path) -> None:
        adapter = CanonicalNetflixAdapter(
            canonical_dataset_version=DATASET_VERSION,
            base_dir=valid_dataset,
        )
        constraints = NetflixHardConstraints(genres=["action", "drama"])
        result = adapter.filter(constraints)
        # Only tm001 has both action AND drama
        assert result == ["tm001"]

    def test_genre_no_match(self, valid_dataset: Path) -> None:
        adapter = CanonicalNetflixAdapter(
            canonical_dataset_version=DATASET_VERSION,
            base_dir=valid_dataset,
        )
        constraints = NetflixHardConstraints(genres=["horror"])
        result = adapter.filter(constraints)
        assert result == []


# ---------------------------------------------------------------------------
# 8. Filter with actors OR → correct IDs
# ---------------------------------------------------------------------------


class TestFilterActorsOr:
    """Validates: Requirements 3.4"""

    def test_single_actor(self, valid_dataset: Path) -> None:
        adapter = CanonicalNetflixAdapter(
            canonical_dataset_version=DATASET_VERSION,
            base_dir=valid_dataset,
        )
        constraints = NetflixHardConstraints(actors=["alice smith"])
        result = adapter.filter(constraints)
        # tm001 and tm003 have alice smith
        assert result == ["tm001", "tm003"]

    def test_multiple_actors_or(self, valid_dataset: Path) -> None:
        adapter = CanonicalNetflixAdapter(
            canonical_dataset_version=DATASET_VERSION,
            base_dir=valid_dataset,
        )
        constraints = NetflixHardConstraints(actors=["alice smith", "dave lee"])
        result = adapter.filter(constraints)
        # tm001 (alice smith), ts002 (dave lee), tm003 (alice smith)
        assert result == ["tm001", "tm003", "ts002"]

    def test_actor_no_match(self, valid_dataset: Path) -> None:
        adapter = CanonicalNetflixAdapter(
            canonical_dataset_version=DATASET_VERSION,
            base_dir=valid_dataset,
        )
        constraints = NetflixHardConstraints(actors=["nonexistent actor"])
        result = adapter.filter(constraints)
        assert result == []


# ---------------------------------------------------------------------------
# 9. Filter with directors OR → correct IDs
# ---------------------------------------------------------------------------


class TestFilterDirectorsOr:
    """Validates: Requirements 3.4"""

    def test_single_director(self, valid_dataset: Path) -> None:
        adapter = CanonicalNetflixAdapter(
            canonical_dataset_version=DATASET_VERSION,
            base_dir=valid_dataset,
        )
        constraints = NetflixHardConstraints(directors=["carol white"])
        result = adapter.filter(constraints)
        # tm001 (carol white), ts002 (eve black, carol white)
        assert result == ["tm001", "ts002"]

    def test_multiple_directors_or(self, valid_dataset: Path) -> None:
        adapter = CanonicalNetflixAdapter(
            canonical_dataset_version=DATASET_VERSION,
            base_dir=valid_dataset,
        )
        constraints = NetflixHardConstraints(directors=["carol white", "george hill"])
        result = adapter.filter(constraints)
        # tm001 (carol white), ts002 (carol white), tm003 (george hill)
        assert result == ["tm001", "tm003", "ts002"]

    def test_director_no_match(self, valid_dataset: Path) -> None:
        adapter = CanonicalNetflixAdapter(
            canonical_dataset_version=DATASET_VERSION,
            base_dir=valid_dataset,
        )
        constraints = NetflixHardConstraints(directors=["unknown director"])
        result = adapter.filter(constraints)
        assert result == []


# ---------------------------------------------------------------------------
# 10. Filter with actors AND directors inter-field → correct IDs
# ---------------------------------------------------------------------------


class TestFilterActorsAndDirectors:
    """Validates: Requirements 3.4"""

    def test_actor_and_director(self, valid_dataset: Path) -> None:
        adapter = CanonicalNetflixAdapter(
            canonical_dataset_version=DATASET_VERSION,
            base_dir=valid_dataset,
        )
        # alice smith AND carol white → only tm001 has alice smith as actor AND carol white as director
        constraints = NetflixHardConstraints(
            actors=["alice smith"],
            directors=["carol white"],
        )
        result = adapter.filter(constraints)
        # tm001 has actor alice smith + director carol white ✓
        # ts002 has actor dave lee (no alice smith) ✗
        # tm003 has actor alice smith but director george hill (not carol white) ✗
        assert result == ["tm001"]

    def test_multiple_actors_or_and_director(self, valid_dataset: Path) -> None:
        adapter = CanonicalNetflixAdapter(
            canonical_dataset_version=DATASET_VERSION,
            base_dir=valid_dataset,
        )
        # (alice smith OR dave lee) AND (carol white)
        constraints = NetflixHardConstraints(
            actors=["alice smith", "dave lee"],
            directors=["carol white"],
        )
        result = adapter.filter(constraints)
        # tm001: actors=alice smith ✓, directors=carol white ✓
        # ts002: actors=dave lee ✓, directors=eve black, carol white ✓
        # tm003: actors=alice smith ✓, directors=george hill ✗
        assert result == ["tm001", "ts002"]


# ---------------------------------------------------------------------------
# 11. Default constraints → returns None
# ---------------------------------------------------------------------------


class TestFilterDefaultConstraints:
    """Validates: Requirements 3.4"""

    def test_default_returns_none(self, valid_dataset: Path) -> None:
        adapter = CanonicalNetflixAdapter(
            canonical_dataset_version=DATASET_VERSION,
            base_dir=valid_dataset,
        )
        constraints = NetflixHardConstraints()
        result = adapter.filter(constraints)
        assert result is None
