"""Property-based and unit tests for Silver Dataset adapters.

Tests cover:
- Property 2: Determinismo del filtrado Netflix
- Property 3: Determinismo del filtrado TMDB
- Property 4: Corrección del filtrado Netflix
- Property 5: Corrección del filtrado TMDB
- Unit tests for error handling, edge cases, and data integrity
"""

from __future__ import annotations

import hashlib
import json
import socket
from pathlib import Path

import pytest
from hypothesis import HealthCheck, given, settings

from moviebot.evals.silver.adapters import NetflixAdapter, TmdbAdapter
from moviebot.evals.silver.models import (
    NetflixHardConstraints,
    TmdbHardConstraints,
)
from tests.evals.silver.strategies import (
    netflix_hard_constraints,
    tmdb_hard_constraints,
)

_SUPPRESS_FIXTURE_CHECK = [HealthCheck.function_scoped_fixture]


# ===========================================================================
# Property Tests — Netflix Filtering (Task 3.5)
# ===========================================================================


class TestNetflixFilteringProperties:
    """Property-based tests for Netflix adapter filtering.

    **Validates: Requirements 2.5, 2.6, 2.7, 2.8, 5.1, 5.2**
    """

    @given(constraints=netflix_hard_constraints())
    @settings(max_examples=100, suppress_health_check=_SUPPRESS_FIXTURE_CHECK)
    def test_determinism_netflix_filter(
        self,
        constraints: NetflixHardConstraints,
        netflix_titles_csv: Path,
        netflix_credits_csv: Path,
    ) -> None:
        """Property 2: Determinismo del filtrado Netflix.

        Two invocations with the same inputs produce identical results.

        **Validates: Requirements 5.1, 5.2**
        """
        adapter = NetflixAdapter(
            titles_path=netflix_titles_csv,
            credits_path=netflix_credits_csv,
        )
        result1 = adapter.filter(constraints)
        result2 = adapter.filter(constraints)
        assert result1 == result2

    @given(constraints=netflix_hard_constraints())
    @settings(max_examples=100, suppress_health_check=_SUPPRESS_FIXTURE_CHECK)
    def test_correctness_netflix_filter(
        self,
        constraints: NetflixHardConstraints,
        netflix_titles_csv: Path,
        netflix_credits_csv: Path,
    ) -> None:
        """Property 4: Corrección del filtrado Netflix.

        Each returned ID satisfies ALL constraints verified individually.

        **Validates: Requirements 2.5, 2.6, 2.7, 2.8**
        """
        adapter = NetflixAdapter(
            titles_path=netflix_titles_csv,
            credits_path=netflix_credits_csv,
        )
        result_ids = adapter.filter(constraints)

        for item_id in result_ids:
            title = adapter.get_title(item_id)
            assert title is not None, f"ID {item_id} not found in adapter"

            # Check type constraint
            if constraints.type is not None:
                assert title.type.lower() == constraints.type

            # Check genres constraint (all requested genres must be present)
            if constraints.genres:
                title_genres_lower = {g.lower() for g in title.genres}
                for genre in constraints.genres:
                    assert genre in title_genres_lower, (
                        f"Title {item_id} missing genre '{genre}', "
                        f"has: {title_genres_lower}"
                    )

            # Check year range
            if constraints.min_year is not None:
                assert title.release_year >= constraints.min_year
            if constraints.max_year is not None:
                assert title.release_year <= constraints.max_year

            # Check IMDB score range
            if constraints.min_imdb_score is not None:
                assert title.imdb_score is not None
                assert title.imdb_score >= constraints.min_imdb_score
            if constraints.max_imdb_score is not None:
                assert title.imdb_score is not None
                assert title.imdb_score <= constraints.max_imdb_score

            # Check actors (at least one must match)
            if constraints.actors:
                title_actors = adapter.get_actors_for_title(item_id)
                filter_actors = {a.lower() for a in constraints.actors}
                assert filter_actors.intersection(title_actors), (
                    f"Title {item_id} has no matching actors. "
                    f"Filter: {filter_actors}, Title: {title_actors}"
                )

            # Check directors (at least one must match)
            if constraints.directors:
                title_directors = adapter.get_directors_for_title(item_id)
                filter_directors = {d.lower() for d in constraints.directors}
                assert filter_directors.intersection(title_directors), (
                    f"Title {item_id} has no matching directors. "
                    f"Filter: {filter_directors}, Title: {title_directors}"
                )


# ===========================================================================
# Property Tests — TMDB Filtering (Task 3.6)
# ===========================================================================


class TestTmdbFilteringProperties:
    """Property-based tests for TMDB adapter filtering.

    **Validates: Requirements 3.6, 3.10, 5.1, 5.2**
    """

    @given(constraints=tmdb_hard_constraints())
    @settings(max_examples=100, suppress_health_check=_SUPPRESS_FIXTURE_CHECK)
    def test_determinism_tmdb_filter(
        self,
        constraints: TmdbHardConstraints,
        tmdb_fixture_path: Path,
    ) -> None:
        """Property 3: Determinismo del filtrado TMDB.

        Two invocations with the same inputs produce identical results.

        **Validates: Requirements 5.1, 5.2**
        """
        adapter = TmdbAdapter(fixture_version="v1", base_dir=tmdb_fixture_path)
        result1 = adapter.filter(constraints)
        result2 = adapter.filter(constraints)
        assert result1 == result2

    @given(constraints=tmdb_hard_constraints())
    @settings(max_examples=100, suppress_health_check=_SUPPRESS_FIXTURE_CHECK)
    def test_correctness_tmdb_filter(
        self,
        constraints: TmdbHardConstraints,
        tmdb_fixture_path: Path,
    ) -> None:
        """Property 5: Corrección del filtrado TMDB.

        Each returned ID satisfies ALL constraints verified individually.

        **Validates: Requirements 3.6, 3.10**
        """
        adapter = TmdbAdapter(fixture_version="v1", base_dir=tmdb_fixture_path)
        result_ids = adapter.filter(constraints)

        for item_id in result_ids:
            record = adapter.get_record(item_id)
            assert record is not None, f"ID {item_id} not found in adapter"

            # Check genre_ids (all requested genre_ids must be present)
            if constraints.genre_ids:
                genre_set = set(constraints.genre_ids)
                record_genre_set = set(record.genre_ids)
                assert genre_set <= record_genre_set, (
                    f"Record {item_id} missing genre_ids. "
                    f"Required: {genre_set}, Has: {record_genre_set}"
                )

            # Check year range
            if constraints.min_year is not None:
                assert record.release_year is not None
                assert record.release_year >= constraints.min_year
            if constraints.max_year is not None:
                assert record.release_year is not None
                assert record.release_year <= constraints.max_year

            # Check vote_average range
            if constraints.min_vote_average is not None:
                assert record.vote_average is not None
                assert record.vote_average >= constraints.min_vote_average
            if constraints.max_vote_average is not None:
                assert record.vote_average is not None
                assert record.vote_average <= constraints.max_vote_average


# ===========================================================================
# Unit Tests — Adapters (Task 3.7)
# ===========================================================================


class TestNetflixAdapterUnit:
    """Unit tests for NetflixAdapter error handling and edge cases.

    **Validates: Requirements 10.6, 10.7, 10.9**
    """

    def test_file_not_found_titles(self, tmp_path: Path) -> None:
        """Netflix: FileNotFoundError when titles.csv doesn't exist."""
        missing_path = tmp_path / "nonexistent" / "titles.csv"
        with pytest.raises(FileNotFoundError, match="títulos requerido"):
            NetflixAdapter(titles_path=missing_path)

    def test_type_error_with_tmdb_constraints(
        self,
        netflix_titles_csv: Path,
        netflix_credits_csv: Path,
    ) -> None:
        """Netflix: TypeError when receiving TmdbHardConstraints."""
        adapter = NetflixAdapter(
            titles_path=netflix_titles_csv,
            credits_path=netflix_credits_csv,
        )
        tmdb_constraints = TmdbHardConstraints(genre_ids=[28])
        with pytest.raises(TypeError, match="NetflixHardConstraints"):
            adapter.filter(tmdb_constraints)  # type: ignore[arg-type]

    def test_null_genres_excluded_when_filtering_by_genre(self, tmp_path: Path) -> None:
        """Netflix: null/unparseable genres excluded from results when filtering by genre."""
        # Create a CSV with titles that have unparseable/empty genres
        csv_content = (
            "id,title,type,description,release_year,age_certification,"
            "runtime,genres,production_countries,seasons,imdb_id,"
            "imdb_score,imdb_votes,tmdb_popularity,tmdb_score\n"
            "tm00001,Good Movie,MOVIE,A movie,2020,R,120,"
            "\"['drama']\",\"['US']\",,tt0000001,8.0,100,10.0,8.0\n"
            "tm00002,Bad Genres,MOVIE,Another movie,2020,R,90,"
            ",\"['US']\",,tt0000002,7.0,50,5.0,7.0\n"
            "tm00003,Unparseable,MOVIE,Third movie,2020,R,100,"
            "not a list,\"['US']\",,tt0000003,7.5,80,8.0,7.5\n"
        )
        csv_path = tmp_path / "titles.csv"
        csv_path.write_text(csv_content, encoding="utf-8")

        adapter = NetflixAdapter(titles_path=csv_path)
        constraints = NetflixHardConstraints(genres=["drama"])
        result = adapter.filter(constraints)

        # Only tm00001 should match — the others have empty/unparseable genres
        assert "tm00001" in result
        assert "tm00002" not in result
        assert "tm00003" not in result

    def test_actors_directors_via_credits(
        self,
        netflix_titles_csv: Path,
        netflix_credits_csv: Path,
    ) -> None:
        """Netflix: actors/directors filtering works via credits.csv."""
        adapter = NetflixAdapter(
            titles_path=netflix_titles_csv,
            credits_path=netflix_credits_csv,
        )

        # Filter by actor
        constraints_actor = NetflixHardConstraints(actors=["Leonardo DiCaprio"])
        result = adapter.filter(constraints_actor)
        assert "tm154986" in result  # Inception

        # Filter by director
        constraints_director = NetflixHardConstraints(directors=["Christopher Nolan"])
        result = adapter.filter(constraints_director)
        assert "tm154986" in result  # Inception

    def test_credits_missing_raises_when_required(
        self,
        netflix_titles_csv: Path,
        tmp_path: Path,
    ) -> None:
        """Netflix: controlled error if credits.csv missing and required for actors/directors."""
        missing_credits = tmp_path / "nonexistent" / "credits.csv"
        adapter = NetflixAdapter(
            titles_path=netflix_titles_csv,
            credits_path=missing_credits,
        )
        constraints = NetflixHardConstraints(actors=["some actor"])
        with pytest.raises(FileNotFoundError, match="créditos requerido"):
            adapter.filter(constraints)

    def test_does_not_modify_csv_files(
        self,
        netflix_titles_csv: Path,
        netflix_credits_csv: Path,
    ) -> None:
        """Netflix: does not modify CSV files (compare SHA-256 checksums before/after)."""
        # Compute checksums before
        titles_hash_before = hashlib.sha256(netflix_titles_csv.read_bytes()).hexdigest()
        credits_hash_before = hashlib.sha256(
            netflix_credits_csv.read_bytes()
        ).hexdigest()

        # Perform operations
        adapter = NetflixAdapter(
            titles_path=netflix_titles_csv,
            credits_path=netflix_credits_csv,
        )
        adapter.filter(NetflixHardConstraints(type="movie"))
        adapter.filter(NetflixHardConstraints(genres=["drama"]))
        adapter.filter(NetflixHardConstraints(actors=["Leonardo DiCaprio"]))

        # Compute checksums after
        titles_hash_after = hashlib.sha256(netflix_titles_csv.read_bytes()).hexdigest()
        credits_hash_after = hashlib.sha256(
            netflix_credits_csv.read_bytes()
        ).hexdigest()

        assert titles_hash_before == titles_hash_after
        assert credits_hash_before == credits_hash_after


class TestTmdbAdapterUnit:
    """Unit tests for TmdbAdapter error handling and edge cases.

    **Validates: Requirements 10.6, 10.7, 10.9**
    """

    def test_file_not_found_fixture(self, tmp_path: Path) -> None:
        """TMDB: FileNotFoundError when fixture doesn't exist."""
        with pytest.raises(FileNotFoundError, match="Fixture TMDB no encontrado"):
            TmdbAdapter(fixture_version="v1", base_dir=tmp_path)

    def test_file_not_found_metadata(self, tmp_path: Path) -> None:
        """TMDB: FileNotFoundError when metadata doesn't exist."""
        tmdb_dir = tmp_path / "tmdb_no_meta"
        tmdb_dir.mkdir()
        # Create fixture but no metadata
        fixture = {"results": []}
        fixture_path = tmdb_dir / "trending_movies_v1.json"
        fixture_path.write_text(json.dumps(fixture), encoding="utf-8")
        with pytest.raises(FileNotFoundError, match="Metadata TMDB no encontrado"):
            TmdbAdapter(fixture_version="v1", base_dir=tmdb_dir)

    def test_checksum_mismatch_raises_value_error(self, tmp_path: Path) -> None:
        """TMDB: ValueError when checksum doesn't match."""
        tmdb_dir = tmp_path / "tmdb_bad_checksum"
        tmdb_dir.mkdir()

        fixture = {"results": []}
        fixture_content = json.dumps(fixture, ensure_ascii=False)
        fixture_path = tmdb_dir / "trending_movies_v1.json"
        fixture_path.write_text(fixture_content, encoding="utf-8")

        # Write metadata with wrong checksum
        metadata = {
            "fixture_version": "v1",
            "checksum_sha256": "a" * 64,  # wrong checksum
            "created_at": "2024-01-01T00:00:00Z",
        }
        metadata_path = tmdb_dir / "trending_movies_v1.metadata.json"
        metadata_path.write_text(json.dumps(metadata), encoding="utf-8")

        with pytest.raises(ValueError, match="Checksum SHA-256"):
            TmdbAdapter(fixture_version="v1", base_dir=tmdb_dir)

    def test_type_error_with_netflix_constraints(self, tmdb_fixture_path: Path) -> None:
        """TMDB: TypeError when receiving NetflixHardConstraints."""
        adapter = TmdbAdapter(fixture_version="v1", base_dir=tmdb_fixture_path)
        netflix_constraints = NetflixHardConstraints(genres=["drama"])
        with pytest.raises(TypeError, match="TmdbHardConstraints"):
            adapter.filter(netflix_constraints)  # type: ignore[arg-type]

    def test_records_with_none_release_year_excluded_by_year_filter(
        self, tmp_path: Path
    ) -> None:
        """TMDB: records with release_year=None excluded when filtering by year."""
        tmdb_dir = tmp_path / "tmdb_null_year"
        tmdb_dir.mkdir()

        records = [
            {
                "id": 111,
                "title": "No Date Movie",
                "overview": "A movie without a date",
                "release_date": "",  # will produce None release_year
                "genre_ids": [28],
                "popularity": 10.0,
                "vote_average": 7.0,
            },
            {
                "id": 222,
                "title": "Dated Movie",
                "overview": "A movie with a date",
                "release_date": "2023-05-01",
                "genre_ids": [28],
                "popularity": 20.0,
                "vote_average": 8.0,
            },
        ]
        fixture_content = json.dumps({"results": records}, ensure_ascii=False)
        fixture_path = tmdb_dir / "trending_movies_v1.json"
        fixture_path.write_text(fixture_content, encoding="utf-8")

        checksum = hashlib.sha256(fixture_content.encode("utf-8")).hexdigest()
        metadata = {
            "fixture_version": "v1",
            "checksum_sha256": checksum,
            "created_at": "2024-01-01T00:00:00Z",
        }
        metadata_path = tmdb_dir / "trending_movies_v1.metadata.json"
        metadata_path.write_text(json.dumps(metadata), encoding="utf-8")

        adapter = TmdbAdapter(fixture_version="v1", base_dir=tmdb_dir)
        constraints = TmdbHardConstraints(min_year=2020)
        result = adapter.filter(constraints)

        # Only the dated movie should be returned
        assert "tmdb:222" in result
        assert "tmdb:111" not in result


class TestNetworkBlocking:
    """Verify network blocking is active via autouse fixture.

    **Validates: Requirements 10.9**
    """

    def test_network_blocked(self) -> None:
        """Network blocking active via autouse fixture."""
        with pytest.raises(OSError, match="Network access is blocked"):
            socket.socket()
