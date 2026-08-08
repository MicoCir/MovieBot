"""Modelos Pydantic para el Silver Evaluation Dataset."""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, Field, model_validator


class TmdbHardConstraints(BaseModel, extra="forbid"):
    """Restricciones verificables contra el fixture TMDB."""

    constraint_type: Literal["tmdb"] = "tmdb"
    genre_ids: list[int] = Field(default_factory=list, max_length=5)
    min_year: int | None = Field(default=None, ge=1888, le=2100)
    max_year: int | None = Field(default=None, ge=1888, le=2100)
    min_vote_average: float | None = Field(default=None, ge=0.0, le=10.0)
    max_vote_average: float | None = Field(default=None, ge=0.0, le=10.0)

    @model_validator(mode="after")
    def validate_ranges(self) -> TmdbHardConstraints:
        if (
            self.min_year is not None
            and self.max_year is not None
            and self.min_year > self.max_year
        ):
            raise ValueError("min_year > max_year")
        if (
            self.min_vote_average is not None
            and self.max_vote_average is not None
            and self.min_vote_average > self.max_vote_average
        ):
            raise ValueError("min_vote_average > max_vote_average")
        return self

    def is_default(self) -> bool:
        """Retorna True si todos los campos están en sus valores default."""
        return (
            self.genre_ids == []
            and self.min_year is None
            and self.max_year is None
            and self.min_vote_average is None
            and self.max_vote_average is None
        )


class NetflixHardConstraints(BaseModel, extra="forbid"):
    """Restricciones verificables contra el dataset Netflix."""

    constraint_type: Literal["netflix"] = "netflix"
    type: Literal["movie", "show"] | None = None
    genres: list[str] = Field(default_factory=list, max_length=5)
    min_year: int | None = Field(default=None, ge=1888, le=2100)
    max_year: int | None = Field(default=None, ge=1888, le=2100)
    min_imdb_score: float | None = Field(default=None, ge=0.0, le=10.0)
    max_imdb_score: float | None = Field(default=None, ge=0.0, le=10.0)
    actors: list[str] = Field(default_factory=list, max_length=10)
    directors: list[str] = Field(default_factory=list, max_length=10)

    @model_validator(mode="after")
    def validate_genres_lowercase(self) -> NetflixHardConstraints:
        """Rechaza géneros que contengan mayúsculas (deben estar normalizados)."""
        for g in self.genres:
            if g != g.lower():
                raise ValueError(f"genres debe estar en lowercase, encontrado: '{g}'")
        return self

    @model_validator(mode="after")
    def validate_ranges(self) -> NetflixHardConstraints:
        if (
            self.min_year is not None
            and self.max_year is not None
            and self.min_year > self.max_year
        ):
            raise ValueError("min_year > max_year")
        if (
            self.min_imdb_score is not None
            and self.max_imdb_score is not None
            and self.min_imdb_score > self.max_imdb_score
        ):
            raise ValueError("min_imdb_score > max_imdb_score")
        return self

    def is_default(self) -> bool:
        """Retorna True si todos los campos están en sus valores default."""
        return (
            self.type is None
            and self.genres == []
            and self.min_year is None
            and self.max_year is None
            and self.min_imdb_score is None
            and self.max_imdb_score is None
            and self.actors == []
            and self.directors == []
        )


class SeedProvenance(BaseModel):
    """Información de procedencia del seed."""

    source: Literal["netflix", "tmdb", "both", "synthetic"]
    fixture_version: str | None = None
    input_data_description: str = Field(max_length=500)
    schema_version: str = Field(pattern=r"^\d+\.\d+\.\d+$")
    dataset_version: str = Field(pattern=r"^[a-zA-Z0-9_-]+$")
    checksum_sha256: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")


class TmdbSeedComponent(BaseModel):
    """Componente TMDB dentro de un seed 'both'."""

    fixture_version: str
    seed_item_ids: list[str] = Field(default_factory=list, max_length=50)
    eligible_item_ids: list[str] | None = Field(default=None, max_length=500)
    hard_constraints: TmdbHardConstraints
    semantic_concepts: list[str] = Field(default_factory=list, max_length=10)


class NetflixSeedComponent(BaseModel):
    """Componente Netflix dentro de un seed 'both'."""

    seed_item_ids: list[str] = Field(default_factory=list, max_length=50)
    eligible_item_ids: list[str] | None = Field(default=None, max_length=500)
    hard_constraints: NetflixHardConstraints
    semantic_concepts: list[str] = Field(default_factory=list, max_length=10)


class SilverSeed(BaseModel):
    """Modelo principal del seed estructurado."""

    case_id: str = Field(max_length=64, pattern=r"^[a-zA-Z0-9_-]+$")
    expected_route: Literal["trending", "netflix", "both", "out_of_scope"]
    expected_sources: list[Literal["tmdb", "netflix"]]
    expected_status: Literal["SUCCESS", "NO_RESULTS", "OUT_OF_SCOPE"]
    hard_constraints: (
        Annotated[
            TmdbHardConstraints | NetflixHardConstraints,
            Field(discriminator="constraint_type"),
        ]
        | None
    ) = None
    semantic_concepts: list[str] = Field(default_factory=list, max_length=10)
    seed_item_ids: list[str] = Field(default_factory=list, max_length=50)
    eligible_item_ids: list[str] | None = Field(default=None, max_length=500)
    difficulty: Literal["easy", "medium", "hard"]
    tags: list[str] = Field(default_factory=list, max_length=20)
    provenance: SeedProvenance
    fixture_version: str | None = None
    tmdb_component: TmdbSeedComponent | None = None
    netflix_component: NetflixSeedComponent | None = None

    @model_validator(mode="after")
    def validate_route_constraints(self) -> SilverSeed:
        """Valida consistencia entre ruta y campos."""
        route = self.expected_route

        if route == "trending":
            if self.fixture_version is None:
                raise ValueError("route 'trending' requiere fixture_version")
            if self.tmdb_component is not None:
                raise ValueError("route 'trending' no admite tmdb_component")
            if self.netflix_component is not None:
                raise ValueError("route 'trending' no admite netflix_component")
            if not isinstance(self.hard_constraints, TmdbHardConstraints):
                raise ValueError("route 'trending' requiere TmdbHardConstraints")

        elif route == "netflix":
            if self.fixture_version is not None:
                raise ValueError("route 'netflix' no admite fixture_version")
            if self.tmdb_component is not None:
                raise ValueError("route 'netflix' no admite tmdb_component")
            if self.netflix_component is not None:
                raise ValueError("route 'netflix' no admite netflix_component")
            if not isinstance(self.hard_constraints, NetflixHardConstraints):
                raise ValueError("route 'netflix' requiere NetflixHardConstraints")

        elif route == "both":
            if self.expected_status != "SUCCESS":
                raise ValueError("route 'both' solo admite expected_status='SUCCESS'")
            if self.expected_sources != ["tmdb", "netflix"]:
                raise ValueError(
                    "route 'both' requiere expected_sources=['tmdb','netflix']"
                )
            if self.tmdb_component is None:
                raise ValueError("route 'both' requiere tmdb_component")
            if self.netflix_component is None:
                raise ValueError("route 'both' requiere netflix_component")
            if self.seed_item_ids != []:
                raise ValueError("route 'both' requiere seed_item_ids=[]")
            if self.eligible_item_ids is not None:
                raise ValueError("route 'both' requiere eligible_item_ids=None")
            if self.hard_constraints is not None:
                raise ValueError("route 'both' requiere hard_constraints=None")
            if self.semantic_concepts != []:
                raise ValueError("route 'both' requiere semantic_concepts=[]")

        elif route == "out_of_scope":
            if self.expected_status != "OUT_OF_SCOPE":
                raise ValueError(
                    "route 'out_of_scope' requiere expected_status='OUT_OF_SCOPE'"
                )
            if self.expected_sources != []:
                raise ValueError("route 'out_of_scope' requiere expected_sources=[]")
            if self.seed_item_ids != []:
                raise ValueError("route 'out_of_scope' requiere seed_item_ids=[]")
            if self.eligible_item_ids is not None:
                raise ValueError("route 'out_of_scope' requiere eligible_item_ids=None")
            if self.hard_constraints is not None:
                raise ValueError("route 'out_of_scope' requiere hard_constraints=None")
            if self.semantic_concepts != []:
                raise ValueError("route 'out_of_scope' requiere semantic_concepts=[]")
            if self.fixture_version is not None:
                raise ValueError("route 'out_of_scope' no admite fixture_version")
            if self.tmdb_component is not None:
                raise ValueError("route 'out_of_scope' no admite tmdb_component")
            if self.netflix_component is not None:
                raise ValueError("route 'out_of_scope' no admite netflix_component")

        return self

    @model_validator(mode="after")
    def validate_status_constraints(self) -> SilverSeed:
        """Valida consistencia entre status y campos."""
        if self.expected_status == "NO_RESULTS":
            if self.seed_item_ids != []:
                raise ValueError("NO_RESULTS requiere seed_item_ids=[]")
            if self.eligible_item_ids != []:
                raise ValueError("NO_RESULTS requiere eligible_item_ids=[] (no None)")

        if (
            self.expected_status == "OUT_OF_SCOPE"
            and self.expected_route != "out_of_scope"
        ):
            raise ValueError("OUT_OF_SCOPE requiere expected_route='out_of_scope'")

        if self.expected_status == "SUCCESS" and self.expected_route != "out_of_scope":
            if self.expected_route in ("trending", "netflix"):
                if len(self.seed_item_ids) < 1:
                    raise ValueError("SUCCESS requiere al menos un seed_item_id")
            elif self.expected_route == "both":
                if self.tmdb_component is None or self.netflix_component is None:
                    raise ValueError(
                        "SUCCESS/both requiere ambos componentes presentes"
                    )
                if len(self.tmdb_component.seed_item_ids) < 1:
                    raise ValueError(
                        "SUCCESS/both requiere tmdb_component con seed_item_ids"
                    )
                if len(self.netflix_component.seed_item_ids) < 1:
                    raise ValueError(
                        "SUCCESS/both requiere netflix_component con seed_item_ids"
                    )

        return self

    @model_validator(mode="after")
    def validate_content_sufficiency(self) -> SilverSeed:
        """Para SUCCESS: al menos un constraint no-default O un semantic_concept."""
        if self.expected_status != "SUCCESS":
            return self

        if self.expected_route in ("trending", "netflix"):
            has_constraints = (
                self.hard_constraints is not None
                and not self.hard_constraints.is_default()
            )
            has_concepts = len(self.semantic_concepts) > 0
            if not (has_constraints or has_concepts):
                raise ValueError(
                    "SUCCESS requiere al menos un hard constraint no-default "
                    "o al menos un semantic_concept"
                )

        elif self.expected_route == "both":
            if self.tmdb_component is None or self.netflix_component is None:
                raise ValueError("SUCCESS/both requiere ambos componentes presentes")
            tmdb_ok = (
                not self.tmdb_component.hard_constraints.is_default()
                or len(self.tmdb_component.semantic_concepts) > 0
            )
            netflix_ok = (
                not self.netflix_component.hard_constraints.is_default()
                or len(self.netflix_component.semantic_concepts) > 0
            )
            if not (tmdb_ok and netflix_ok):
                raise ValueError("SUCCESS/both requiere contenido en cada componente")

        return self

    @model_validator(mode="after")
    def validate_semantic_eligible_none(self) -> SilverSeed:
        """SUCCESS con solo semantic_concepts acepta eligible_item_ids=None."""
        if self.expected_status != "SUCCESS":
            return self
        if self.expected_route in ("trending", "netflix") and (
            self.hard_constraints is None or self.hard_constraints.is_default()
        ):
            # Solo semantic — eligible puede ser None, no se fuerza eligible != None
            pass
        return self
