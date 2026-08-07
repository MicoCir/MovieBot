"""Inspector programático del dataset Netflix.

Analiza los CSVs del dataset Netflix y produce un InspectionReport
estructurado con schema, cobertura, relaciones, clasificación de campos
y estrategia de identidad.
"""

from __future__ import annotations

import ast
import csv
import re
from collections import Counter, defaultdict
from pathlib import Path

from moviebot.tools.inspect_netflix.models import (
    CardinalityStats,
    ColumnInfo,
    CoverageEntry,
    CoverageStats,
    CreditCoverage,
    CreditCoverageSubset,
    CreditStats,
    CreditStatsSubset,
    CsvSchema,
    DuplicateStats,
    FieldClassification,
    GenreStats,
    IdentityStrategy,
    InspectionReport,
    RelationshipStats,
    TypeDistribution,
)

# Type aliases for CSV rows
TitleRow = dict[str, str | None]
CreditRow = dict[str, str | None]

# Fields to analyze for coverage
_COVERAGE_FIELDS: list[str] = [
    "title",
    "description",
    "release_year",
    "genres",
    "age_certification",
    "imdb_id",
    "imdb_score",
    "tmdb_popularity",
    "tmdb_score",
]

# Numeric regex patterns for type inference
_INT_PATTERN: re.Pattern[str] = re.compile(r"^-?\d+$")
_FLOAT_PATTERN: re.Pattern[str] = re.compile(r"^-?\d+\.\d+$")
_BOOL_VALUES: frozenset[str] = frozenset({"True", "False", "true", "false", "1", "0"})


class NetflixInspector:
    """Analiza programáticamente los CSVs del dataset Netflix."""

    def __init__(self, titles_path: Path, credits_path: Path) -> None:
        self._titles_path = titles_path
        self._credits_path = credits_path

    def run(self) -> InspectionReport:
        """Ejecuta el análisis completo y retorna el reporte."""
        titles_rows = self._read_csv(self._titles_path)
        credits_rows = self._read_csv(self._credits_path)

        # Schemas
        titles_schema = self._build_schema(
            titles_rows, self._titles_path.name, key_columns=["id"]
        )
        credits_schema = self._build_schema(
            credits_rows,
            self._credits_path.name,
            key_columns=["person_id", "id", "role"],
        )

        # Type distribution
        type_dist = self._analyze_type_distribution(titles_rows)

        # Subsets
        movies = [r for r in titles_rows if r.get("type") == "MOVIE"]
        shows = [r for r in titles_rows if r.get("type") == "SHOW"]

        # Coverage
        coverage = self._analyze_coverage(titles_rows, movies, shows)

        # Genre stats
        genre_stats = self._analyze_genres(titles_rows)

        # Credit stats
        credit_stats = self._analyze_credit_stats(
            titles_rows, movies, shows, credits_rows
        )

        # Credit coverage
        credit_coverage = self._analyze_credit_coverage(
            titles_rows, movies, shows, credits_rows
        )

        # Relationships
        relationships = self._analyze_relationships(titles_rows, credits_rows)

        # Field classifications (based on MOVIE subset)
        field_classifications = self._classify_fields(coverage, credit_coverage)

        # Identity strategy
        identity_strategy = IdentityStrategy(
            netflix_format="campo id nativo (e.g. tm84618)",
            tmdb_format="prefijo tmdb:{numeric_id} (e.g. tmdb:123456)",
            cross_source="identidades independientes, sin canónica compartida",
        )

        # Observations
        observations = self._build_observations(
            coverage, credit_coverage, genre_stats, field_classifications
        )

        # Genre incompatibility note
        genre_incompatibility_note = (
            "Los géneros TMDB (IDs numéricos, e.g. '28', '35') y los géneros Netflix "
            "(nombres string, e.g. 'action', 'comedy') son semánticamente diferentes y "
            "NO directamente comparables. La comparación cross-source de géneros requiere "
            "una tabla de mapeo de IDs TMDB a nombres que está fuera del alcance de esta feature."
        )

        return InspectionReport(
            schemas=[titles_schema, credits_schema],
            type_distribution=type_dist,
            coverage=coverage,
            genre_stats=genre_stats,
            credit_stats=credit_stats,
            credit_coverage=credit_coverage,
            relationships=relationships,
            field_classifications=field_classifications,
            identity_strategy=identity_strategy,
            observations=observations,
            genre_incompatibility_note=genre_incompatibility_note,
        )

    # -------------------------------------------------------------------------
    # CSV reading
    # -------------------------------------------------------------------------

    def _read_csv(self, path: Path) -> list[dict[str, str | None]]:
        """Lee un CSV con DictReader en modo solo lectura."""
        with open(path, "r", newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            rows: list[dict[str, str | None]] = []
            for row in reader:
                # csv.DictReader produces str values; empty strings remain as ""
                normalized: dict[str, str | None] = {}
                for k, v in row.items():
                    if k is None:
                        continue
                    normalized[k] = v if v is not None else None
                rows.append(normalized)
            return rows

    # -------------------------------------------------------------------------
    # Schema analysis
    # -------------------------------------------------------------------------

    def _build_schema(
        self,
        rows: list[dict[str, str | None]],
        filename: str,
        key_columns: list[str],
    ) -> CsvSchema:
        """Construye el schema completo de un CSV."""
        if not rows:
            return CsvSchema(
                filename=filename,
                row_count=0,
                columns=[],
                exact_duplicates=DuplicateStats(
                    exact_duplicate_rows=0,
                    key_columns=[],
                    duplicate_key_values=0,
                    duplicate_key_extra_rows=0,
                ),
                key_duplicates=DuplicateStats(
                    exact_duplicate_rows=0,
                    key_columns=key_columns,
                    duplicate_key_values=0,
                    duplicate_key_extra_rows=0,
                ),
            )

        all_columns = list(rows[0].keys())
        columns = self._analyze_columns(rows, all_columns)
        exact_dups = self._analyze_duplicates(rows, all_columns)
        key_dups = self._analyze_duplicates(rows, key_columns)

        return CsvSchema(
            filename=filename,
            row_count=len(rows),
            columns=columns,
            exact_duplicates=exact_dups,
            key_duplicates=key_dups,
        )

    # -------------------------------------------------------------------------
    # Column analysis with type inference
    # -------------------------------------------------------------------------

    def _analyze_columns(
        self, rows: list[dict[str, str | None]], columns: list[str]
    ) -> list[ColumnInfo]:
        """Analiza cada columna: tipo inferido, nulos, únicos, min/max."""
        result: list[ColumnInfo] = []
        for col in columns:
            values = [row.get(col) for row in rows]
            null_count = self._count_nulls(values, col)
            non_null_values = [v for v in values if not self._is_null(v, col)]
            inferred_type = self._infer_type(non_null_values, col)
            unique_count = len(set(non_null_values)) if non_null_values else 0

            min_val: int | float | None = None
            max_val: int | float | None = None
            if inferred_type in ("integer", "float"):
                numeric_vals = self._extract_numeric_values(
                    non_null_values, inferred_type
                )
                if numeric_vals:
                    min_val = min(numeric_vals)
                    max_val = max(numeric_vals)

            result.append(
                ColumnInfo(
                    name=col,
                    inferred_type=inferred_type,
                    null_count=null_count,
                    unique_count=unique_count,
                    min_value=min_val,
                    max_value=max_val,
                )
            )
        return result

    def _is_null(self, value: str | None, column: str) -> bool:
        """Determina si un valor es nulo según la definición de Null_Value."""
        if value is None:
            return True
        if value == "":
            return True
        # For list fields, "[]" is considered null
        if value == "[]":
            return True
        # NaN detection (csv produces strings)
        return value.lower() == "nan"

    def _count_nulls(self, values: list[str | None], column: str) -> int:
        """Cuenta nulos en una lista de valores."""
        return sum(1 for v in values if self._is_null(v, column))

    def _infer_type(self, non_null_values: list[str | None], column: str) -> str:
        """Infiere el tipo canónico de una columna por multi-pattern detection.

        Reglas (en orden):
        1. Columna vacía → "string"
        2. Todos list_pattern → "list[string]"
        3. Todos bool_pattern → "boolean"
        4. Todos int_pattern → "integer"
        5. Todos int_pattern o float_pattern (al menos un float) → "float"
        6. Todos other → "string"
        7. Mezcla → "mixed"
        """
        if not non_null_values:
            return "string"

        # Classify each value into a pattern category
        patterns: list[str] = []
        for v in non_null_values:
            if v is None:
                continue
            patterns.append(self._classify_pattern(v))

        if not patterns:
            return "string"

        pattern_set = set(patterns)

        # All list_pattern
        if pattern_set == {"list_pattern"}:
            return "list[string]"

        # All bool_pattern
        if pattern_set == {"bool_pattern"}:
            return "boolean"

        # All int_pattern
        if pattern_set == {"int_pattern"}:
            return "integer"

        # All numeric (int or float, at least one float)
        if (
            pattern_set <= {"int_pattern", "float_pattern"}
            and "float_pattern" in pattern_set
        ):
            return "float"

        # All other (plain text)
        if pattern_set == {"other"}:
            return "string"

        # Mixed patterns
        return "mixed"

    def _classify_pattern(self, value: str) -> str:
        """Clasifica un valor individual en su categoría de patrón."""
        # Check list pattern first
        if self._is_list_pattern(value):
            return "list_pattern"
        # Boolean
        if value in _BOOL_VALUES:
            return "bool_pattern"
        # Integer
        if _INT_PATTERN.match(value):
            return "int_pattern"
        # Float
        if _FLOAT_PATTERN.match(value):
            return "float_pattern"
        # Other (plain text)
        return "other"

    def _is_list_pattern(self, value: str) -> bool:
        """Determina si un valor es parseable como lista de strings."""
        try:
            parsed = ast.literal_eval(value)
        except (ValueError, SyntaxError):
            return False
        if not isinstance(parsed, list):
            return False
        return all(isinstance(item, str) for item in parsed)

    def _extract_numeric_values(
        self, non_null_values: list[str | None], inferred_type: str
    ) -> list[int | float]:
        """Extrae valores numéricos para calcular min/max."""
        result: list[int | float] = []
        for v in non_null_values:
            if v is None:
                continue
            try:
                if inferred_type == "integer":
                    result.append(int(v))
                else:
                    result.append(float(v))
            except (ValueError, TypeError):
                pass
        return result

    # -------------------------------------------------------------------------
    # Duplicate analysis
    # -------------------------------------------------------------------------

    def _analyze_duplicates(
        self, rows: list[dict[str, str | None]], key_columns: list[str]
    ) -> DuplicateStats:
        """Analiza duplicados por las columnas clave especificadas."""
        key_counter: Counter[tuple[str | None, ...]] = Counter()
        for row in rows:
            key = tuple(row.get(col) for col in key_columns)
            key_counter[key] += 1

        # duplicate_key_values: number of unique keys that appear more than once
        duplicate_key_values = sum(1 for count in key_counter.values() if count > 1)
        # duplicate_key_extra_rows: total extra rows (count - 1 for each duplicate key)
        duplicate_key_extra_rows = sum(
            count - 1 for count in key_counter.values() if count > 1
        )
        # For exact_duplicates field in CsvSchema, we pass all columns
        # exact_duplicate_rows = total extra identical rows
        exact_duplicate_rows = duplicate_key_extra_rows

        return DuplicateStats(
            exact_duplicate_rows=exact_duplicate_rows,
            key_columns=key_columns,
            duplicate_key_values=duplicate_key_values,
            duplicate_key_extra_rows=duplicate_key_extra_rows,
        )

    # -------------------------------------------------------------------------
    # Type distribution
    # -------------------------------------------------------------------------

    def _analyze_type_distribution(self, titles: list[TitleRow]) -> TypeDistribution:
        """Analiza la distribución del campo type en titles.csv."""
        recognized = {"MOVIE", "SHOW"}
        counts: dict[str, int] = {}
        null_or_unrecognized = 0

        for row in titles:
            val = row.get("type")
            if val is None or val == "" or val not in recognized:
                null_or_unrecognized += 1
            else:
                counts[val] = counts.get(val, 0) + 1

        # Sort keys for determinism
        sorted_counts = dict(sorted(counts.items()))
        return TypeDistribution(
            counts=sorted_counts, null_or_unrecognized=null_or_unrecognized
        )

    # -------------------------------------------------------------------------
    # Genre analysis
    # -------------------------------------------------------------------------

    def _parse_genres(self, raw_value: str | None) -> list[str] | None:
        """Parsea un campo de géneros desde formato literal de lista Python.

        Returns:
            - [] if value is null/empty/"[]"/NaN
            - list[str] if successfully parsed as list of all strings
            - None if unparseable (syntax error or non-string elements)
        """
        if raw_value is None or raw_value == "" or raw_value == "[]":
            return []
        if raw_value.lower() == "nan":
            return []

        try:
            parsed = ast.literal_eval(raw_value)
        except (ValueError, SyntaxError):
            return None

        if not isinstance(parsed, list):
            return None

        # Validate all elements are strings
        if not all(isinstance(item, str) for item in parsed):
            return None

        return parsed

    def _analyze_genres(self, titles: list[TitleRow]) -> GenreStats:
        """Analiza estadísticas de géneros del dataset."""
        genre_counter: Counter[str] = Counter()
        null_or_empty_count = 0
        unparseable_count = 0

        for row in titles:
            raw = row.get("genres")
            parsed = self._parse_genres(raw)

            if parsed is None:
                # Unparseable
                unparseable_count += 1
            elif len(parsed) == 0:
                # Null or empty
                null_or_empty_count += 1
            else:
                for genre in parsed:
                    genre_counter[genre] += 1

        unique_genres = sorted(genre_counter.keys())
        titles_per_genre = dict(sorted(genre_counter.items()))

        return GenreStats(
            unique_genres=unique_genres,
            titles_per_genre=titles_per_genre,
            titles_null_or_empty_genres=null_or_empty_count,
            unparseable_count=unparseable_count,
        )

    # -------------------------------------------------------------------------
    # Relationship analysis
    # -------------------------------------------------------------------------

    def _analyze_relationships(
        self, titles: list[TitleRow], credits: list[CreditRow]
    ) -> RelationshipStats:
        """Analiza relaciones entre títulos y créditos."""
        title_ids: set[str] = set()
        for row in titles:
            _id = row.get("id")
            if _id is not None and _id != "":
                title_ids.add(_id)

        # 1:N — credits per title
        credits_per_title: dict[str, int] = defaultdict(int)
        for row in credits:
            credit_id = row.get("id")
            if credit_id:
                credits_per_title[credit_id] += 1

        # For titles that have no credits, they have 0
        for tid in title_ids:
            if tid not in credits_per_title:
                credits_per_title[tid] = 0

        # Only count title_ids that actually exist in titles
        credits_counts = [credits_per_title[tid] for tid in title_ids]
        titles_to_credits_1n = self._compute_cardinality(credits_counts)

        # M:N — titles per person
        titles_per_person: dict[str, set[str]] = defaultdict(set)
        persons_per_title: dict[str, set[str]] = defaultdict(set)

        for row in credits:
            person_id = row.get("person_id")
            credit_id = row.get("id")
            if person_id and credit_id:
                titles_per_person[person_id].add(credit_id)
                persons_per_title[credit_id].add(person_id)

        # titles per person stats (only persons that actually appear in credits)
        titles_per_person_counts = [len(tids) for tids in titles_per_person.values()]
        mn_titles_per_person = self._compute_cardinality(titles_per_person_counts)

        # persons per title stats (include titles with 0 persons)
        persons_counts = [len(persons_per_title.get(tid, set())) for tid in title_ids]
        mn_persons_per_title = self._compute_cardinality(persons_counts)

        # Titles without credits
        credit_title_ids: set[str] = set()
        for row in credits:
            _id = row.get("id")
            if _id is not None and _id != "":
                credit_title_ids.add(_id)
        titles_without_credits = len(title_ids - credit_title_ids)

        # Credits without title
        credits_without_title = sum(
            1 for row in credits if row.get("id") and row.get("id") not in title_ids
        )

        return RelationshipStats(
            titles_to_credits_1n=titles_to_credits_1n,
            titles_to_persons_mn_titles_per_person=mn_titles_per_person,
            titles_to_persons_mn_persons_per_title=mn_persons_per_title,
            titles_without_credits=titles_without_credits,
            credits_without_title=credits_without_title,
        )

    def _compute_cardinality(self, counts: list[int]) -> CardinalityStats:
        """Computa min/max/avg de una lista de conteos."""
        if not counts:
            return CardinalityStats(min_value=0, max_value=0, avg_value=0.00)
        return CardinalityStats(
            min_value=min(counts),
            max_value=max(counts),
            avg_value=round(sum(counts) / len(counts), 2),
        )

    # -------------------------------------------------------------------------
    # Coverage analysis
    # -------------------------------------------------------------------------

    def _analyze_coverage(
        self,
        all_titles: list[TitleRow],
        movies: list[TitleRow],
        shows: list[TitleRow],
    ) -> CoverageStats:
        """Analiza cobertura de campos desglosada por subconjunto."""
        return CoverageStats(
            all_titles=self._coverage_for_subset(all_titles),
            movies_only=self._coverage_for_subset(movies),
            shows_only=self._coverage_for_subset(shows),
        )

    def _coverage_for_subset(self, subset: list[TitleRow]) -> list[CoverageEntry]:
        """Calcula cobertura para un subconjunto de títulos."""
        total = len(subset)
        entries: list[CoverageEntry] = []

        for field in _COVERAGE_FIELDS:
            values = [row.get(field) for row in subset]
            non_null_values = [v for v in values if not self._is_null(v, field)]
            non_null_count = len(non_null_values)

            pct_non_null = (
                round((non_null_count / total) * 100, 2) if total > 0 else 0.00
            )
            unique_count = len(set(non_null_values))

            min_val: int | float | None = None
            max_val: int | float | None = None

            # Determine if field is numeric for min/max
            if field in ("release_year", "imdb_score", "tmdb_popularity", "tmdb_score"):
                numeric_vals = self._extract_numeric_for_coverage(
                    non_null_values, field
                )
                if numeric_vals:
                    min_val = min(numeric_vals)
                    max_val = max(numeric_vals)

            entries.append(
                CoverageEntry(
                    field=field,
                    pct_non_null=pct_non_null,
                    unique_count=unique_count,
                    min_value=min_val,
                    max_value=max_val,
                )
            )

        return entries

    def _extract_numeric_for_coverage(
        self, non_null_values: list[str | None], field: str
    ) -> list[int | float]:
        """Extrae valores numéricos para campos de cobertura."""
        result: list[int | float] = []
        for v in non_null_values:
            if v is None:
                continue
            try:
                if field == "release_year":
                    result.append(int(v))
                else:
                    result.append(float(v))
            except (ValueError, TypeError):
                pass
        return result

    # -------------------------------------------------------------------------
    # Credit stats
    # -------------------------------------------------------------------------

    def _analyze_credit_stats(
        self,
        all_titles: list[TitleRow],
        movies: list[TitleRow],
        shows: list[TitleRow],
        credits: list[CreditRow],
    ) -> CreditStats:
        """Analiza estadísticas de créditos desglosadas por subconjunto."""
        all_ids = {r.get("id") for r in all_titles if r.get("id")}
        movie_ids = {r.get("id") for r in movies if r.get("id")}
        show_ids = {r.get("id") for r in shows if r.get("id")}

        return CreditStats(
            all_titles=self._credit_stats_for_subset(all_ids, len(all_titles), credits),
            movies_only=self._credit_stats_for_subset(movie_ids, len(movies), credits),
            shows_only=self._credit_stats_for_subset(show_ids, len(shows), credits),
        )

    def _credit_stats_for_subset(
        self,
        title_ids: set[str | None],
        total_titles: int,
        credits: list[CreditRow],
    ) -> CreditStatsSubset:
        """Calcula estadísticas de créditos para un subconjunto."""
        # Filter credits to this subset
        subset_credits = [r for r in credits if r.get("id") in title_ids]

        # Records per role
        records_per_role: Counter[str] = Counter()
        unique_persons_per_role: dict[str, set[str]] = defaultdict(set)
        actors_per_title: Counter[str | None] = Counter()
        directors_per_title: Counter[str | None] = Counter()

        for row in subset_credits:
            role = row.get("role")
            person_id = row.get("person_id")
            title_id = row.get("id")
            if role:
                records_per_role[role] += 1
                if person_id:
                    unique_persons_per_role[role].add(person_id)
            if role == "ACTOR" and title_id:
                actors_per_title[title_id] += 1
            elif role == "DIRECTOR" and title_id:
                directors_per_title[title_id] += 1

        # Average actors/directors per title (denominator = total titles in subset)
        total_actors = sum(actors_per_title.values())
        total_directors = sum(directors_per_title.values())

        avg_actors = round(total_actors / total_titles, 2) if total_titles > 0 else 0.00
        avg_directors = (
            round(total_directors / total_titles, 2) if total_titles > 0 else 0.00
        )

        # Titles with zero actors/directors
        titles_with_actors = set(actors_per_title.keys())
        titles_with_directors = set(directors_per_title.keys())
        titles_with_zero_actors = len(title_ids - titles_with_actors)
        titles_with_zero_directors = len(title_ids - titles_with_directors)

        return CreditStatsSubset(
            records_per_role=dict(sorted(records_per_role.items())),
            unique_persons_per_role={
                k: len(v) for k, v in sorted(unique_persons_per_role.items())
            },
            avg_actors_per_title=avg_actors,
            avg_directors_per_title=avg_directors,
            titles_with_zero_actors=titles_with_zero_actors,
            titles_with_zero_directors=titles_with_zero_directors,
        )

    # -------------------------------------------------------------------------
    # Credit coverage
    # -------------------------------------------------------------------------

    def _analyze_credit_coverage(
        self,
        all_titles: list[TitleRow],
        movies: list[TitleRow],
        shows: list[TitleRow],
        credits: list[CreditRow],
    ) -> CreditCoverage:
        """Analiza cobertura de créditos desglosada por subconjunto."""
        all_ids = {r.get("id") for r in all_titles if r.get("id")}
        movie_ids = {r.get("id") for r in movies if r.get("id")}
        show_ids = {r.get("id") for r in shows if r.get("id")}

        return CreditCoverage(
            all_titles=self._credit_coverage_for_subset(
                all_ids, len(all_titles), credits
            ),
            movies_only=self._credit_coverage_for_subset(
                movie_ids, len(movies), credits
            ),
            shows_only=self._credit_coverage_for_subset(show_ids, len(shows), credits),
        )

    def _credit_coverage_for_subset(
        self,
        title_ids: set[str | None],
        total_titles: int,
        credits: list[CreditRow],
    ) -> CreditCoverageSubset:
        """Calcula cobertura de créditos para un subconjunto."""
        titles_with_actors: set[str] = set()
        titles_with_directors: set[str] = set()

        for row in credits:
            title_id = row.get("id")
            role = row.get("role")
            if title_id and title_id in title_ids:
                if role == "ACTOR":
                    titles_with_actors.add(title_id)
                elif role == "DIRECTOR":
                    titles_with_directors.add(title_id)

        titles_with_both = titles_with_actors & titles_with_directors

        pct_actors = (
            round((len(titles_with_actors) / total_titles) * 100, 2)
            if total_titles > 0
            else 0.00
        )
        pct_directors = (
            round((len(titles_with_directors) / total_titles) * 100, 2)
            if total_titles > 0
            else 0.00
        )
        pct_both = (
            round((len(titles_with_both) / total_titles) * 100, 2)
            if total_titles > 0
            else 0.00
        )

        return CreditCoverageSubset(
            pct_with_actors=pct_actors,
            pct_with_directors=pct_directors,
            pct_with_both=pct_both,
        )

    # -------------------------------------------------------------------------
    # Field classification
    # -------------------------------------------------------------------------

    def _classify_fields(
        self, coverage: CoverageStats, credit_coverage: CreditCoverage
    ) -> list[FieldClassification]:
        """Clasifica campos según umbrales para filtros duros (subset MOVIE only).

        Rules (strict precedence, no gaps):
        1. "no fiable para filtros duros" — coverage < 70% OR not deterministically verifiable
        2. "utilizable con normalización previa" — coverage ≥ 70% AND (requires normalization OR coverage < 90%)
        3. "utilizable como filtro duro" — coverage ≥ 90% AND directly verifiable
        Boundary values (exactly 70% or 90%) belong to the UPPER category.
        """
        classifications: list[FieldClassification] = []

        # Get movie coverage entries as a dict for easy lookup
        movie_coverage_map: dict[str, float] = {}
        for entry in coverage.movies_only:
            movie_coverage_map[entry.field] = entry.pct_non_null

        # Define field properties: (field, needs_normalization, is_verifiable)
        field_defs: list[tuple[str, bool, bool]] = [
            ("type", False, True),  # type field - directly verifiable
            ("genres", True, True),  # needs parsing/normalization
            ("release_year", False, True),  # directly verifiable
            ("age_certification", False, True),  # directly verifiable
            (
                "description",
                False,
                False,
            ),  # not deterministically verifiable (semantic)
            ("imdb_id", False, True),  # directly verifiable
            ("imdb_score", False, True),  # directly verifiable
            ("tmdb_popularity", False, True),  # directly verifiable
            ("tmdb_score", False, True),  # directly verifiable
        ]

        for field, needs_normalization, is_verifiable in field_defs:
            # Get coverage for this field in movie subset
            if field == "type":
                # type is always present (it defines the subset), so 100%
                cov_pct = 100.00
            else:
                cov_pct = movie_coverage_map.get(field, 0.00)

            category, reason = self._apply_classification_rules(
                cov_pct, needs_normalization, is_verifiable, field
            )
            classifications.append(
                FieldClassification(
                    field=field,
                    category=category,
                    coverage_pct=cov_pct,
                    reason=reason,
                )
            )

        # Add actors and directors via credits
        actors_cov = credit_coverage.movies_only.pct_with_actors
        directors_cov = credit_coverage.movies_only.pct_with_directors

        # Actors: verifiable via join, may need normalization of names
        cat_actors, reason_actors = self._apply_classification_rules(
            actors_cov, True, True, "actors (via credits.csv)"
        )
        classifications.append(
            FieldClassification(
                field="actors (via credits.csv)",
                category=cat_actors,
                coverage_pct=actors_cov,
                reason=reason_actors,
            )
        )

        # Directors: verifiable via join, may need normalization of names
        cat_directors, reason_directors = self._apply_classification_rules(
            directors_cov, True, True, "directors (via credits.csv)"
        )
        classifications.append(
            FieldClassification(
                field="directors (via credits.csv)",
                category=cat_directors,
                coverage_pct=directors_cov,
                reason=reason_directors,
            )
        )

        return classifications

    def _apply_classification_rules(
        self,
        coverage_pct: float,
        needs_normalization: bool,
        is_verifiable: bool,
        field: str,
    ) -> tuple[str, str]:
        """Aplica las reglas de clasificación sin huecos.

        Boundary values (exactly 70% or 90%) belong to the UPPER category.
        """
        # Rule 1: "no fiable" if coverage < 70% OR not verifiable
        if coverage_pct < 70.0 or not is_verifiable:
            if not is_verifiable:
                reason = f"valores no determinísticamente verificables (cobertura {coverage_pct:.2f}%)"
            else:
                reason = f"cobertura insuficiente ({coverage_pct:.2f}% < 70%)"
            return ("no fiable para filtros duros", reason)

        # Rule 3: "filtro duro" if coverage >= 90% AND directly verifiable AND no normalization
        if coverage_pct >= 90.0 and not needs_normalization:
            reason = f"cobertura alta ({coverage_pct:.2f}% >= 90%) y directamente verificable"
            return ("utilizable como filtro duro", reason)

        # Rule 2: "normalización previa" — coverage >= 70% AND (needs normalization OR coverage < 90%)
        if needs_normalization:
            reason = f"cobertura {coverage_pct:.2f}%, requiere normalización previa"
        else:
            reason = f"cobertura {coverage_pct:.2f}% (>= 70%, < 90%), verificable con normalización"
        return ("utilizable con normalización previa", reason)

    # -------------------------------------------------------------------------
    # Observations
    # -------------------------------------------------------------------------

    def _build_observations(
        self,
        coverage: CoverageStats,
        credit_coverage: CreditCoverage,
        genre_stats: GenreStats,
        field_classifications: list[FieldClassification] | None = None,
    ) -> list[str]:
        """Construye observaciones relevantes para el Silver Dataset."""
        observations: list[str] = []

        # Coverage-based observations
        movie_coverage_map: dict[str, float] = {}
        for entry in coverage.movies_only:
            movie_coverage_map[entry.field] = entry.pct_non_null

        # Fields classified as "no fiable" should not appear as "confiables"
        no_fiable_fields: set[str] = set()
        if field_classifications:
            no_fiable_fields = {
                fc.field
                for fc in field_classifications
                if fc.category == "no fiable para filtros duros"
            }

        # Identify fields with high coverage that are also usable (not "no fiable")
        high_coverage_fields = [
            f
            for f, pct in movie_coverage_map.items()
            if pct >= 90.0 and f not in no_fiable_fields
        ]
        if high_coverage_fields:
            observations.append(
                f"Campos con cobertura >= 90% y verificables en MOVIE: "
                f"{', '.join(sorted(high_coverage_fields))}"
            )

        # Identify limited fields
        limited_fields = [f for f, pct in movie_coverage_map.items() if pct < 70.0]
        if limited_fields:
            observations.append(
                f"Campos con cobertura limitada (< 70% en MOVIE): "
                f"{', '.join(sorted(limited_fields))}"
            )

        # Credit coverage observations
        actors_pct = credit_coverage.movies_only.pct_with_actors
        directors_pct = credit_coverage.movies_only.pct_with_directors
        observations.append(
            f"Cobertura de actores en MOVIE: {actors_pct:.2f}%, "
            f"directores: {directors_pct:.2f}%. "
            f"Join determinista via titles.id = credits.id permite verificar "
            f"exhaustivamente personas asociadas a cada título."
        )

        # Genre observations
        if genre_stats.unparseable_count > 0:
            observations.append(
                f"Se encontraron {genre_stats.unparseable_count} registros con "
                f"géneros no parseables que requieren tratamiento especial."
            )

        observations.append(
            f"Total géneros únicos encontrados: {len(genre_stats.unique_genres)}. "
            f"Títulos sin género asignado: {genre_stats.titles_null_or_empty_genres}."
        )

        return observations
