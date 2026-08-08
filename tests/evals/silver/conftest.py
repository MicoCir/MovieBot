"""Shared fixtures for Silver Dataset Seeds tests.

Provides:
- block_network: autouse fixture that patches socket.socket to reject all network
- netflix_titles_csv: minimal Netflix titles CSV (5-10 rows) in tmp_path
- netflix_credits_csv: minimal Netflix credits CSV in tmp_path
- tmdb_fixture_path: TMDB fixture JSON (3-5 records) with valid metadata + checksum
"""

from __future__ import annotations

import hashlib
import json
import socket
from pathlib import Path

import pytest

# ---------------------------------------------------------------------------
# Network blocking
# ---------------------------------------------------------------------------


class _BlockedSocket:
    """Replacement for socket.socket that raises on any usage."""

    def __init__(self, *args: object, **kwargs: object) -> None:
        raise OSError(
            "Network access is blocked in Silver Dataset tests. "
            "All operations must be offline."
        )


@pytest.fixture(autouse=True)
def block_network(monkeypatch: pytest.MonkeyPatch) -> None:
    """Patch socket.socket to prevent any network access during tests."""
    monkeypatch.setattr(socket, "socket", _BlockedSocket)


# ---------------------------------------------------------------------------
# Netflix test data
# ---------------------------------------------------------------------------

_NETFLIX_TITLES_CSV = """\
id,title,type,description,release_year,age_certification,runtime,genres,production_countries,seasons,imdb_id,imdb_score,imdb_votes,tmdb_popularity,tmdb_score
tm84618,Taxi Driver,MOVIE,A mentally unstable veteran works as a nighttime taxi driver.,1976,R,114,"['drama', 'crime']","['US']",,tt0075314,8.2,808582,46.3,8.2
tm154986,Inception,MOVIE,A thief who steals corporate secrets through dream-sharing technology.,2010,PG-13,148,"['action', 'science fiction', 'adventure']","['US', 'GB']",,tt1375666,8.8,2300000,67.5,8.4
tm70993,The Godfather,MOVIE,The aging patriarch of an organized crime dynasty transfers control to his son.,1972,R,175,"['drama', 'crime']","['US']",,tt0068646,9.2,1800000,82.1,8.7
ts22164,Breaking Bad,SHOW,A chemistry teacher diagnosed with cancer turns to manufacturing methamphetamine.,2008,TV-MA,49,"['drama', 'thriller', 'crime']","['US']",,tt0903747,9.5,1900000,91.2,8.9
tm120801,Parasite,MOVIE,Greed and class discrimination threaten a symbiotic relationship.,2019,R,132,"['drama', 'thriller', 'comedy']","['KR']",,tt6751668,8.5,780000,55.8,8.5
tm257064,Dune,MOVIE,Feature adaptation of Frank Herbert's science fiction novel.,2021,PG-13,155,"['science fiction', 'adventure']","['US', 'CA']",,tt1160419,8.0,650000,72.4,7.9
ts45786,Stranger Things,SHOW,When a young boy disappears his friends and family search for answers.,2016,TV-14,51,"['drama', 'mystery', 'science fiction']","['US']",,tt4574334,8.7,1100000,88.3,8.6
tm312854,Everything Everywhere All at Once,MOVIE,An aging Chinese immigrant is swept up in an adventure.,2022,R,139,"['action', 'adventure', 'comedy']","['US']",,tt6710474,7.8,450000,48.2,7.9
"""

_NETFLIX_CREDITS_CSV = """\
person_id,id,name,character,role
10297,tm84618,Robert De Niro,Travis Bickle,ACTOR
56731,tm84618,Martin Scorsese,,DIRECTOR
27150,tm154986,Leonardo DiCaprio,Dom Cobb,ACTOR
525,tm154986,Christopher Nolan,,DIRECTOR
3084,tm70993,Marlon Brando,Don Vito Corleone,ACTOR
3085,tm70993,Al Pacino,Michael Corleone,ACTOR
1776,tm70993,Francis Ford Coppola,,DIRECTOR
17419,ts22164,Bryan Cranston,Walter White,ACTOR
93221,ts22164,Vince Gilligan,,DIRECTOR
78901,tm120801,Song Kang-ho,Kim Ki-taek,ACTOR
21684,tm120801,Bong Joon-ho,,DIRECTOR
56190,tm257064,Timothee Chalamet,Paul Atreides,ACTOR
5174,tm257064,Denis Villeneuve,,DIRECTOR
88124,ts45786,Millie Bobby Brown,Eleven,ACTOR
12845,ts45786,The Duffer Brothers,,DIRECTOR
91234,tm312854,Michelle Yeoh,Evelyn Quan Wang,ACTOR
67123,tm312854,Daniel Kwan,,DIRECTOR
"""


@pytest.fixture()
def netflix_titles_csv(tmp_path: Path) -> Path:
    """Create a minimal Netflix titles.csv for testing."""
    csv_path = tmp_path / "netflix" / "titles.csv"
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    csv_path.write_text(_NETFLIX_TITLES_CSV, encoding="utf-8")
    return csv_path


@pytest.fixture()
def netflix_credits_csv(tmp_path: Path) -> Path:
    """Create a minimal Netflix credits.csv for testing."""
    csv_path = tmp_path / "netflix" / "credits.csv"
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    csv_path.write_text(_NETFLIX_CREDITS_CSV, encoding="utf-8")
    return csv_path


# ---------------------------------------------------------------------------
# TMDB test data
# ---------------------------------------------------------------------------

_TMDB_FIXTURE_RECORDS: list[dict[str, object]] = [
    {
        "id": 969681,
        "title": "The Last Voyage of the Demeter",
        "overview": "The crew of the merchant ship Demeter attempts to survive the ocean voyage from Carpathia to London.",
        "release_date": "2023-08-11",
        "genre_ids": [27, 14],
        "popularity": 45.6,
        "vote_average": 7.1,
    },
    {
        "id": 872585,
        "title": "Oppenheimer",
        "overview": "The story of American scientist J. Robert Oppenheimer and his role in the development of the atomic bomb.",
        "release_date": "2023-07-19",
        "genre_ids": [18, 36],
        "popularity": 92.3,
        "vote_average": 8.1,
    },
    {
        "id": 346698,
        "title": "Barbie",
        "overview": "Barbie and Ken are having the time of their lives in the colorful and seemingly perfect world of Barbie Land.",
        "release_date": "2023-07-19",
        "genre_ids": [35, 12],
        "popularity": 88.1,
        "vote_average": 7.0,
    },
    {
        "id": 565770,
        "title": "Blue Beetle",
        "overview": "An alien relic chooses Jaime Reyes as its symbiotic host, bestowing the teenager with a suit of armor.",
        "release_date": "2023-08-16",
        "genre_ids": [28, 878],
        "popularity": 61.2,
        "vote_average": 6.8,
    },
    {
        "id": 1022789,
        "title": "Inside Out 2",
        "overview": "Follow Riley in her teenage years as new emotions join the team.",
        "release_date": "2024-06-11",
        "genre_ids": [16, 10751, 35],
        "popularity": 110.5,
        "vote_average": 7.6,
    },
]


def _build_tmdb_fixture_and_metadata(
    records: list[dict[str, object]],
) -> tuple[str, str]:
    """Build fixture JSON content and metadata JSON with valid checksum.

    Returns (fixture_content, metadata_content) as strings.
    """
    fixture_payload = {"results": records}
    fixture_content = json.dumps(fixture_payload, ensure_ascii=False, indent=2)

    checksum = hashlib.sha256(fixture_content.encode("utf-8")).hexdigest()

    metadata = {
        "fixture_version": "v1",
        "checksum_sha256": checksum,
        "created_at": "2024-01-15T10:00:00Z",
    }
    metadata_content = json.dumps(metadata, ensure_ascii=False, indent=2)

    return fixture_content, metadata_content


@pytest.fixture()
def tmdb_fixture_path(tmp_path: Path) -> Path:
    """Create a TMDB fixture JSON + metadata with valid SHA-256 checksum.

    Returns the base directory (tmp_path / "tmdb") where:
    - trending_movies_v1.json contains 5 test records
    - trending_movies_v1.metadata.json contains the matching checksum
    """
    tmdb_dir = tmp_path / "tmdb"
    tmdb_dir.mkdir(parents=True, exist_ok=True)

    fixture_content, metadata_content = _build_tmdb_fixture_and_metadata(
        _TMDB_FIXTURE_RECORDS
    )

    fixture_path = tmdb_dir / "trending_movies_v1.json"
    fixture_path.write_text(fixture_content, encoding="utf-8")

    metadata_path = tmdb_dir / "trending_movies_v1.metadata.json"
    metadata_path.write_text(metadata_content, encoding="utf-8")

    return tmdb_dir
