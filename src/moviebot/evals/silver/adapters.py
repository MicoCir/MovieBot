"""Adaptadores deterministas para datasources del Silver Evaluation Dataset.

Provee carga offline de Netflix CSV y fixture TMDB versionado,
con filtrado determinista usando hard constraints tipados.
"""

from __future__ import annotations

import ast
import csv
import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from moviebot.evals.silver.models import (
    NetflixHardConstraints,
    TmdbHardConstraints,
)

# ---------------------------------------------------------------------------
# Netflix Adapter
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class NetflixTitle:
    """Representación interna de un título Netflix."""

    id: str
    title: str
    type: Literal["MOVIE", "SHOW"]
    description: str | None
    release_year: int
    genres: list[str]  # normalizado lowercase
    imdb_score: float | None
    imdb_id: str | None
    tmdb_popularity: float | None
    tmdb_score: float | None


class NetflixAdapter:
    """Carga el dataset Netflix desde CSV y expone filtrado determinista."""

    def __init__(
        self,
        titles_path: Path = Path("raw_data/netflix/titles.csv"),
        credits_path: Path = Path("raw_data/netflix/credits.csv"),
    ) -> None:
        """Carga titles.csv. Credits se carga lazy al primer uso de actors/directors."""
        if not titles_path.is_file():
            raise FileNotFoundError(f"Archivo de títulos requerido: {titles_path}")
        self._titles_path = titles_path
        self._credits_path = credits_path
        self._titles: list[NetflixTitle] = self._load_titles()
        self._titles_by_id: dict[str, NetflixTitle] = {t.id: t for t in self._titles}
        self._actors_by_title: dict[str, list[str]] | None = None  # lazy
        self._directors_by_title: dict[str, list[str]] | None = None  # lazy

    def _load_titles(self) -> list[NetflixTitle]:
        """Parsea titles.csv y construye lista de NetflixTitle."""
        titles: list[NetflixTitle] = []
        with self._titles_path.open(encoding="utf-8", newline="") as f:
            reader = csv.DictReader(f)
            for row in reader:
                genres = self._parse_genres(row.get("genres", ""))
                title_type = row.get("type", "").upper()
                if title_type not in ("MOVIE", "SHOW"):
                    continue  # skip rows with invalid type

                description = row.get("description") or None
                if description is not None:
                    description = description.strip() or None

                release_year_raw = row.get("release_year", "")
                try:
                    release_year = int(release_year_raw)
                except (ValueError, TypeError):
                    continue  # skip rows without valid release_year

                imdb_score = self._parse_float(row.get("imdb_score", ""))
                imdb_id = row.get("imdb_id") or None
                if imdb_id is not None:
                    imdb_id = imdb_id.strip() or None
                tmdb_popularity = self._parse_float(row.get("tmdb_popularity", ""))
                tmdb_score = self._parse_float(row.get("tmdb_score", ""))

                titles.append(
                    NetflixTitle(
                        id=row["id"].strip(),
                        title=row.get("title", "").strip(),
                        type=title_type,  # type: ignore[arg-type]
                        description=description,
                        release_year=release_year,
                        genres=genres,
                        imdb_score=imdb_score,
                        imdb_id=imdb_id,
                        tmdb_popularity=tmdb_popularity,
                        tmdb_score=tmdb_score,
                    )
                )
        return titles

    def _load_credits(self) -> None:
        """Carga credits.csv y construye índices actor/director por título."""
        actors: dict[str, list[str]] = {}
        directors: dict[str, list[str]] = {}

        with self._credits_path.open(encoding="utf-8", newline="") as f:
            reader = csv.DictReader(f)
            for row in reader:
                title_id = row.get("id", "").strip()
                name = row.get("name", "").strip().lower()
                role = row.get("role", "").strip().upper()

                if not title_id or not name:
                    continue

                if role == "ACTOR":
                    actors.setdefault(title_id, []).append(name)
                elif role == "DIRECTOR":
                    directors.setdefault(title_id, []).append(name)

        self._actors_by_title = actors
        self._directors_by_title = directors

    def _ensure_credits_loaded(self) -> None:
        """Carga credits si aún no se ha hecho. Lanza error si el archivo no existe."""
        if self._actors_by_title is not None:
            return
        if not self._credits_path.is_file():
            raise FileNotFoundError(
                f"Archivo de créditos requerido para filtrar por actors/directors: "
                f"{self._credits_path}"
            )
        self._load_credits()

    def id_exists(self, item_id: str) -> bool:
        """Verifica existencia de un ID en el dataset."""
        return item_id in self._titles_by_id

    def get_title(self, item_id: str) -> NetflixTitle | None:
        """Retorna el título por ID o None si no existe."""
        return self._titles_by_id.get(item_id)

    def get_description(self, item_id: str) -> str | None:
        """Retorna el campo description del título."""
        title = self._titles_by_id.get(item_id)
        return title.description if title else None

    def get_actors_for_title(self, item_id: str) -> list[str]:
        """Retorna actores asociados al título (lowercase)."""
        self._ensure_credits_loaded()
        assert self._actors_by_title is not None
        return self._actors_by_title.get(item_id, [])

    def get_directors_for_title(self, item_id: str) -> list[str]:
        """Retorna directores asociados al título (lowercase)."""
        self._ensure_credits_loaded()
        assert self._directors_by_title is not None
        return self._directors_by_title.get(item_id, [])

    def filter(self, constraints: NetflixHardConstraints) -> list[str]:
        """Retorna IDs que satisfacen TODAS las constraints, orden léxico-ascendente.

        Raises:
            TypeError: si constraints no es NetflixHardConstraints
        """
        if not isinstance(constraints, NetflixHardConstraints):
            raise TypeError(
                "NetflixAdapter solo acepta NetflixHardConstraints, "
                f"recibido: {type(constraints).__name__}"
            )

        # Si actors o directors no vacíos → cargar credits
        if constraints.actors or constraints.directors:
            self._ensure_credits_loaded()

        # Normalizar actors/directors a lowercase para comparación
        filter_actors: set[str] = {a.lower() for a in constraints.actors}
        filter_directors: set[str] = {d.lower() for d in constraints.directors}

        # Normalizar genres (ya deben estar en lowercase por validación del modelo)
        filter_genres: set[str] = set(constraints.genres)

        result_ids: list[str] = []

        for title in self._titles:
            # Filtro por type
            if constraints.type is not None and title.type.lower() != constraints.type:
                continue

            # Filtro por genres (intersección: título debe tener TODOS los géneros)
            if filter_genres:
                if not title.genres:
                    # Excluir títulos con genres vacíos cuando se filtra por género
                    continue
                title_genres_lower = {g.lower() for g in title.genres}
                if not filter_genres.issubset(title_genres_lower):
                    continue

            # Filtro por min_year
            if (
                constraints.min_year is not None
                and title.release_year < constraints.min_year
            ):
                continue

            # Filtro por max_year
            if (
                constraints.max_year is not None
                and title.release_year > constraints.max_year
            ):
                continue

            # Filtro por min_imdb_score
            if constraints.min_imdb_score is not None:
                if title.imdb_score is None:
                    continue
                if title.imdb_score < constraints.min_imdb_score:
                    continue

            # Filtro por max_imdb_score
            if constraints.max_imdb_score is not None:
                if title.imdb_score is None:
                    continue
                if title.imdb_score > constraints.max_imdb_score:
                    continue

            # Filtro por actors (al menos uno debe coincidir)
            if filter_actors:
                assert self._actors_by_title is not None
                title_actors = self._actors_by_title.get(title.id)
                if title_actors is None:
                    # Excluir títulos sin registros en credits
                    continue
                # actors ya están en lowercase en el índice
                if not filter_actors.intersection(title_actors):
                    continue

            # Filtro por directors (al menos uno debe coincidir)
            if filter_directors:
                assert self._directors_by_title is not None
                title_directors = self._directors_by_title.get(title.id)
                if title_directors is None:
                    # Excluir títulos sin registros en credits
                    continue
                # directors ya están en lowercase en el índice
                if not filter_directors.intersection(title_directors):
                    continue

            result_ids.append(title.id)

        return sorted(result_ids)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _parse_genres(raw: str) -> list[str]:
        """Parsea el campo genres del CSV (Python list literal) a lista lowercase."""
        if not raw or not raw.strip():
            return []
        try:
            parsed = ast.literal_eval(raw.strip())
            if isinstance(parsed, list):
                return [str(g).lower() for g in parsed]
        except (ValueError, SyntaxError):
            pass
        return []

    @staticmethod
    def _parse_float(raw: str) -> float | None:
        """Parsea un string a float, retorna None si no es válido."""
        if not raw or not raw.strip():
            return None
        try:
            return float(raw.strip())
        except (ValueError, TypeError):
            return None


# ---------------------------------------------------------------------------
# TMDB Adapter
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class TmdbFixtureRecord:
    """Representación interna de un registro del fixture TMDB."""

    id: str  # formato "tmdb:{numeric_id}"
    title: str
    overview: str | None
    release_date: str | None
    release_year: int | None
    genre_ids: list[int]
    popularity: float | None
    vote_average: float | None


class TmdbAdapter:
    """Carga un fixture TMDB versionado y expone filtrado determinista."""

    def __init__(
        self,
        fixture_version: str,
        base_dir: Path = Path("raw_data/tmdb"),
    ) -> None:
        """Carga y valida el fixture.

        Raises:
            FileNotFoundError: fixture o metadata no encontrado
            ValueError: checksum no coincide
        """
        self._fixture_version = fixture_version
        payload_path = base_dir / f"trending_movies_{fixture_version}.json"
        metadata_path = base_dir / f"trending_movies_{fixture_version}.metadata.json"

        if not payload_path.is_file():
            raise FileNotFoundError(
                f"Fixture TMDB no encontrado: {payload_path} "
                f"(versión: {fixture_version})"
            )
        if not metadata_path.is_file():
            raise FileNotFoundError(
                f"Metadata TMDB no encontrado: {metadata_path} "
                f"(versión: {fixture_version})"
            )

        self._verify_checksum(payload_path, metadata_path)
        self._records: list[TmdbFixtureRecord] = self._load_fixture(payload_path)
        self._records_by_id: dict[str, TmdbFixtureRecord] = {
            r.id: r for r in self._records
        }

    @property
    def fixture_version(self) -> str:
        """Retorna la versión del fixture cargado."""
        return self._fixture_version

    def _verify_checksum(self, payload_path: Path, metadata_path: Path) -> None:
        """Verifica SHA-256 del payload contra metadata.

        Lee el archivo como texto UTF-8 y computa el checksum sobre los bytes
        UTF-8 resultantes, garantizando consistencia cross-platform
        (independiente de line endings del sistema de archivos).

        Raises:
            ValueError: si el checksum calculado no coincide con el esperado.
        """
        payload_text = payload_path.read_text(encoding="utf-8")
        computed = hashlib.sha256(payload_text.encode("utf-8")).hexdigest()

        metadata_text = metadata_path.read_text(encoding="utf-8")
        metadata = json.loads(metadata_text)
        expected = metadata["checksum_sha256"]

        if computed != expected:
            raise ValueError(
                f"Checksum SHA-256 del fixture TMDB no coincide. "
                f"Esperado: {expected}, calculado: {computed} "
                f"(versión: {self._fixture_version})"
            )

    def _load_fixture(self, path: Path) -> list[TmdbFixtureRecord]:
        """Parsea el fixture JSON a registros internos."""
        content = path.read_text(encoding="utf-8")
        data = json.loads(content)
        results: list[dict[str, object]] = data["results"]

        records: list[TmdbFixtureRecord] = []
        for raw in results:
            numeric_id = raw["id"]
            record_id = f"tmdb:{numeric_id}"

            title = str(raw["title"])

            raw_overview = raw.get("overview")
            overview: str | None = str(raw_overview) if raw_overview else None

            raw_release_date = raw.get("release_date")
            release_date: str | None = (
                str(raw_release_date) if raw_release_date else None
            )

            release_year = self._extract_release_year(release_date)

            raw_genre_ids = raw.get("genre_ids", [])
            genre_ids: list[int] = (
                list(raw_genre_ids)  # type: ignore[arg-type]
                if isinstance(raw_genre_ids, list)
                else []
            )

            raw_popularity = raw.get("popularity")
            popularity: float | None = (
                float(raw_popularity)  # type: ignore[arg-type]
                if raw_popularity is not None
                else None
            )

            raw_vote_average = raw.get("vote_average")
            vote_average: float | None = (
                float(raw_vote_average)  # type: ignore[arg-type]
                if raw_vote_average is not None
                else None
            )

            records.append(
                TmdbFixtureRecord(
                    id=record_id,
                    title=title,
                    overview=overview,
                    release_date=release_date,
                    release_year=release_year,
                    genre_ids=genre_ids,
                    popularity=popularity,
                    vote_average=vote_average,
                )
            )

        return records

    @staticmethod
    def _extract_release_year(release_date: str | None) -> int | None:
        """Extrae el año de una fecha en formato YYYY-MM-DD.

        Retorna None si release_date es None, vacío, o no parseable.
        """
        if not release_date:
            return None
        try:
            year_str = release_date.split("-")[0]
            year = int(year_str)
            if 1888 <= year <= 2100:
                return year
            return None
        except (ValueError, IndexError):
            return None

    def id_exists(self, item_id: str) -> bool:
        """Verifica existencia de un ID en el fixture cargado."""
        return item_id in self._records_by_id

    def get_record(self, item_id: str) -> TmdbFixtureRecord | None:
        """Retorna el registro por ID o None si no existe."""
        return self._records_by_id.get(item_id)

    def get_overview(self, item_id: str) -> str | None:
        """Retorna el campo overview del registro."""
        record = self._records_by_id.get(item_id)
        return record.overview if record else None

    def filter(self, constraints: TmdbHardConstraints) -> list[str]:
        """Retorna IDs que satisfacen TODAS las constraints, orden léxico-ascendente.

        Raises:
            TypeError: si constraints no es TmdbHardConstraints o genre_ids inválido
        """
        if not isinstance(constraints, TmdbHardConstraints):
            raise TypeError(
                "TmdbAdapter solo acepta TmdbHardConstraints, "
                f"recibido: {type(constraints).__name__}"
            )

        # Defensa: validar que todos los genre_ids son int (Req 3.14)
        for gid in constraints.genre_ids:
            if not isinstance(gid, int):
                raise TypeError(
                    f"genre_id debe ser int, recibido: {type(gid).__name__} ({gid})"
                )

        result: list[str] = []
        genre_set = set(constraints.genre_ids)

        for record in self._records:
            # Filtro por genre_ids: el registro debe contener TODOS los genre_ids
            if genre_set and not genre_set <= set(record.genre_ids):
                continue

            # Filtro por min_year: excluir registros con release_year=None
            if constraints.min_year is not None:
                if record.release_year is None:
                    continue
                if record.release_year < constraints.min_year:
                    continue

            # Filtro por max_year: excluir registros con release_year=None
            if constraints.max_year is not None:
                if record.release_year is None:
                    continue
                if record.release_year > constraints.max_year:
                    continue

            # Filtro por min_vote_average: excluir registros con vote_average=None
            if constraints.min_vote_average is not None:
                if record.vote_average is None:
                    continue
                if record.vote_average < constraints.min_vote_average:
                    continue

            # Filtro por max_vote_average: excluir registros con vote_average=None
            if constraints.max_vote_average is not None:
                if record.vote_average is None:
                    continue
                if record.vote_average > constraints.max_vote_average:
                    continue

            result.append(record.id)

        return sorted(result)
