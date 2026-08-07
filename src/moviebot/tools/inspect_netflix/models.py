"""Modelos Pydantic del inspector Netflix."""

from pydantic import BaseModel


class ColumnInfo(BaseModel):
    """Información de una columna de un CSV."""

    name: str
    inferred_type: str  # Canonical_Type_Names
    null_count: int
    unique_count: int | None = None
    min_value: int | float | None = None
    max_value: int | float | None = None


class DuplicateStats(BaseModel):
    """Estadísticas de duplicados para un CSV."""

    exact_duplicate_rows: int
    key_columns: list[str]
    duplicate_key_values: int
    duplicate_key_extra_rows: int


class CsvSchema(BaseModel):
    """Schema verificado de un archivo CSV."""

    filename: str
    row_count: int
    columns: list[ColumnInfo]
    exact_duplicates: DuplicateStats
    key_duplicates: DuplicateStats


class CardinalityStats(BaseModel):
    """Estadísticas de cardinalidad min/max/avg."""

    min_value: int
    max_value: int
    avg_value: float  # 2 decimales


class RelationshipStats(BaseModel):
    """Estadísticas de relaciones entre títulos y créditos."""

    titles_to_credits_1n: CardinalityStats
    titles_to_persons_mn_titles_per_person: CardinalityStats
    titles_to_persons_mn_persons_per_title: CardinalityStats
    titles_without_credits: int
    credits_without_title: int


class CreditCoverageSubset(BaseModel):
    """Cobertura de créditos para un subconjunto de títulos."""

    pct_with_actors: float  # 2 decimales
    pct_with_directors: float  # 2 decimales
    pct_with_both: float  # 2 decimales


class CreditCoverage(BaseModel):
    """Cobertura de créditos desglosada por subconjunto."""

    all_titles: CreditCoverageSubset
    movies_only: CreditCoverageSubset
    shows_only: CreditCoverageSubset


class CoverageEntry(BaseModel):
    """Entrada de cobertura para un campo."""

    field: str
    pct_non_null: float  # 2 decimales
    unique_count: int
    min_value: int | float | None = None
    max_value: int | float | None = None


class CoverageStats(BaseModel):
    """Estadísticas de cobertura desglosadas por subconjunto."""

    all_titles: list[CoverageEntry]
    movies_only: list[CoverageEntry]
    shows_only: list[CoverageEntry]


class FieldClassification(BaseModel):
    """Clasificación de un campo para uso como filtro."""

    field: str
    category: str
    coverage_pct: float
    reason: str


class GenreStats(BaseModel):
    """Estadísticas de géneros del dataset."""

    unique_genres: list[str]  # ordenados alfabéticamente
    titles_per_genre: dict[str, int]
    titles_null_or_empty_genres: int
    unparseable_count: int


class CreditStatsSubset(BaseModel):
    """Estadísticas de créditos para un subconjunto de títulos."""

    records_per_role: dict[str, int]
    unique_persons_per_role: dict[str, int]
    avg_actors_per_title: float
    avg_directors_per_title: float
    titles_with_zero_actors: int
    titles_with_zero_directors: int


class CreditStats(BaseModel):
    """Estadísticas de créditos desglosadas por subconjunto."""

    all_titles: CreditStatsSubset
    movies_only: CreditStatsSubset
    shows_only: CreditStatsSubset


class TypeDistribution(BaseModel):
    """Distribución del campo type en titles.csv."""

    counts: dict[str, int]
    null_or_unrecognized: int


class IdentityStrategy(BaseModel):
    """Estrategia de identidad para títulos."""

    netflix_format: str
    tmdb_format: str
    cross_source: str


class InspectionReport(BaseModel):
    """Reporte completo de inspección del dataset Netflix."""

    schemas: list[CsvSchema]
    type_distribution: TypeDistribution
    coverage: CoverageStats
    genre_stats: GenreStats
    credit_stats: CreditStats
    credit_coverage: CreditCoverage
    relationships: RelationshipStats
    field_classifications: list[FieldClassification]
    identity_strategy: IdentityStrategy
    observations: list[str]
    genre_incompatibility_note: str
