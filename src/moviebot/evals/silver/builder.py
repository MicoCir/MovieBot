"""Builder — API programática de construcción de seeds."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from moviebot.evals.silver.adapters import (
    CanonicalNetflixAdapter,
    NetflixAdapter,
    TmdbAdapter,
)
from moviebot.evals.silver.models import (
    NetflixHardConstraints,
    NetflixSeedComponent,
    SeedProvenance,
    SilverSeed,
    TmdbHardConstraints,
    TmdbSeedComponent,
)


@dataclass(frozen=True)
class NetflixSeedBuildRequest:
    """Request para construir un seed Netflix."""

    case_id: str
    expected_status: Literal["SUCCESS", "NO_RESULTS"]
    seed_item_ids: list[str]
    hard_constraints: NetflixHardConstraints
    semantic_concepts: list[str]
    difficulty: Literal["easy", "medium", "hard"]
    tags: list[str]


@dataclass(frozen=True)
class TrendingSeedBuildRequest:
    """Request para construir un seed TMDB Trending."""

    case_id: str
    expected_status: Literal["SUCCESS", "NO_RESULTS"]
    seed_item_ids: list[str]
    hard_constraints: TmdbHardConstraints
    semantic_concepts: list[str]
    difficulty: Literal["easy", "medium", "hard"]
    tags: list[str]


@dataclass(frozen=True)
class BothSeedBuildRequest:
    """Request para construir un seed BOTH (siempre SUCCESS)."""

    case_id: str
    difficulty: Literal["easy", "medium", "hard"]
    tags: list[str]
    # Componente TMDB
    tmdb_seed_item_ids: list[str]
    tmdb_hard_constraints: TmdbHardConstraints
    tmdb_semantic_concepts: list[str]
    # Componente Netflix
    netflix_seed_item_ids: list[str]
    netflix_hard_constraints: NetflixHardConstraints
    netflix_semantic_concepts: list[str]


@dataclass(frozen=True)
class OutOfScopeSeedBuildRequest:
    """Request para construir un seed OUT_OF_SCOPE."""

    case_id: str
    difficulty: Literal["easy", "medium", "hard"]
    tags: list[str]


# Tipo union para dispatch
SeedBuildRequest = (
    NetflixSeedBuildRequest
    | TrendingSeedBuildRequest
    | BothSeedBuildRequest
    | OutOfScopeSeedBuildRequest
)


class SeedBuildError(Exception):
    """Error específico del proceso de construcción de seeds."""

    def __init__(self, case_id: str, message: str) -> None:
        self.case_id = case_id
        self.message = message
        super().__init__(f"[{case_id}] {message}")


class SeedBuilder:
    """Construye seeds validados a partir de requests del caller."""

    def __init__(
        self,
        netflix_adapter: NetflixAdapter | CanonicalNetflixAdapter | None = None,
        tmdb_adapter: TmdbAdapter | None = None,
        *,
        schema_version: str,
        silver_dataset_version: str,
        canonical_dataset_version: str | None = None,
        etl_version: str | None = None,
    ) -> None:
        """Configura adaptadores y versiones.

        Args:
            netflix_adapter: Adaptador Netflix (requerido para routes netflix/both).
                Acepta tanto NetflixAdapter (CSV) como CanonicalNetflixAdapter (JSONL).
            tmdb_adapter: Adaptador TMDB (requerido para routes trending/both)
            schema_version: Versión del schema de seeds (e.g. "1.0.0")
            silver_dataset_version: Versión del dataset (e.g. "silver_v1")
            canonical_dataset_version: Versión del dataset canónico (requerido para netflix/both)
            etl_version: Versión del ETL (requerido para netflix/both)
        """
        self._netflix = netflix_adapter
        self._tmdb = tmdb_adapter
        self._schema_version = schema_version
        self._silver_dataset_version = silver_dataset_version
        # When using CanonicalNetflixAdapter, prefer its metadata over constructor args
        if hasattr(netflix_adapter, "canonical_dataset_version"):
            self._canonical_dataset_version = (
                canonical_dataset_version or netflix_adapter.canonical_dataset_version  # type: ignore[union-attr]
            )
        else:
            self._canonical_dataset_version = canonical_dataset_version
        if hasattr(netflix_adapter, "etl_version"):
            self._etl_version = (
                etl_version or netflix_adapter.etl_version  # type: ignore[union-attr]
            )
        else:
            self._etl_version = etl_version

    def build(self, request: SeedBuildRequest) -> SilverSeed:
        """Construye un SilverSeed a partir del request. Dispatch por tipo."""
        if isinstance(request, NetflixSeedBuildRequest):
            return self._build_netflix(request)
        elif isinstance(request, TrendingSeedBuildRequest):
            return self._build_trending(request)
        elif isinstance(request, BothSeedBuildRequest):
            return self._build_both(request)
        elif isinstance(request, OutOfScopeSeedBuildRequest):
            return self._build_out_of_scope(request)
        else:
            raise SeedBuildError(
                case_id=getattr(request, "case_id", "unknown"),
                message=f"Tipo de request no soportado: {type(request).__name__}",
            )

    def _compute_eligible(
        self,
        constraints: TmdbHardConstraints | NetflixHardConstraints,
        adapter: NetflixAdapter | CanonicalNetflixAdapter | TmdbAdapter,
    ) -> list[str] | None:
        """Calcula eligible_item_ids. Retorna None si constraints es default.

        El caller garantiza que constraints y adapter son del mismo tipo
        (TmdbHardConstraints + TmdbAdapter, o NetflixHardConstraints + NetflixAdapter/CanonicalNetflixAdapter).
        """
        if constraints.is_default():
            return None
        return adapter.filter(constraints)  # type: ignore[arg-type]

    def _build_netflix(self, request: NetflixSeedBuildRequest) -> SilverSeed:
        """Construye un seed Netflix."""
        # 1. Verificar adaptador disponible
        if self._netflix is None:
            raise SeedBuildError(
                case_id=request.case_id,
                message="NetflixAdapter no inyectado, requerido para route 'netflix'",
            )

        # 2. Verificar IDs existen en datasource
        missing_ids = [
            sid for sid in request.seed_item_ids if not self._netflix.id_exists(sid)
        ]
        if missing_ids:
            raise SeedBuildError(
                case_id=request.case_id,
                message=f"IDs no encontrados en Netflix datasource: {missing_ids}",
            )

        # 3. Calcular eligible_item_ids
        eligible = self._compute_eligible(request.hard_constraints, self._netflix)

        # 4. Validar según expected_status
        if request.expected_status == "SUCCESS":
            # SUCCESS + eligible vacío → contradicción
            if eligible is not None and eligible == []:
                raise SeedBuildError(
                    case_id=request.case_id,
                    message="Contradicción: constraints producen eligible vacío pero expected_status es SUCCESS",
                )
            # Verificar seed_items ⊆ eligible cuando eligible no es None
            if eligible is not None:
                not_eligible = [
                    sid for sid in request.seed_item_ids if sid not in eligible
                ]
                if not_eligible:
                    raise SeedBuildError(
                        case_id=request.case_id,
                        message=f"seed_item_ids no están en eligible_item_ids: {not_eligible}",
                    )
            # Verificar semantic_concepts vs campo textual
            if request.semantic_concepts:
                for sid in request.seed_item_ids:
                    desc = self._netflix.get_description(sid)
                    if not desc or not desc.strip():
                        raise SeedBuildError(
                            case_id=request.case_id,
                            message=(
                                f"semantic_concepts requiere description no vacío "
                                f"para seed_item '{sid}', pero es None o whitespace"
                            ),
                        )

        elif request.expected_status == "NO_RESULTS":
            # NO_RESULTS: eligible siempre es []
            eligible = []

        # 5. Construir SilverSeed
        # Extraer checksum del adaptador canónico si disponible (duck typing)
        canonical_checksum: str | None = None
        if hasattr(self._netflix, "output_checksum_sha256"):
            canonical_checksum = self._netflix.output_checksum_sha256  # type: ignore[union-attr]

        return SilverSeed(
            case_id=request.case_id,
            expected_route="netflix",
            expected_sources=["netflix"],
            expected_status=request.expected_status,
            hard_constraints=request.hard_constraints,
            semantic_concepts=request.semantic_concepts,
            seed_item_ids=request.seed_item_ids,
            eligible_item_ids=eligible,
            difficulty=request.difficulty,
            tags=request.tags,
            provenance=SeedProvenance(
                source="netflix",
                fixture_version=None,
                input_data_description=(
                    f"Seed Netflix '{request.case_id}' construido desde "
                    f"dataset Netflix con {len(request.seed_item_ids)} seed items"
                ),
                schema_version=self._schema_version,
                silver_dataset_version=self._silver_dataset_version,
                canonical_dataset_version=self._canonical_dataset_version,
                canonical_dataset_checksum=canonical_checksum,
                etl_version=self._etl_version,
            ),
        )

    def _build_trending(self, request: TrendingSeedBuildRequest) -> SilverSeed:
        """Construye un seed TMDB Trending."""
        # 1. Verificar adaptador disponible
        if self._tmdb is None:
            raise SeedBuildError(
                case_id=request.case_id,
                message="TmdbAdapter no inyectado, requerido para route 'trending'",
            )

        # 2. Verificar IDs existen en datasource
        missing_ids = [
            sid for sid in request.seed_item_ids if not self._tmdb.id_exists(sid)
        ]
        if missing_ids:
            raise SeedBuildError(
                case_id=request.case_id,
                message=f"IDs no encontrados en TMDB datasource: {missing_ids}",
            )

        # 3. Calcular eligible_item_ids
        eligible = self._compute_eligible(request.hard_constraints, self._tmdb)

        # 4. Validar según expected_status
        if request.expected_status == "SUCCESS":
            # SUCCESS + eligible vacío → contradicción
            if eligible is not None and eligible == []:
                raise SeedBuildError(
                    case_id=request.case_id,
                    message="Contradicción: constraints producen eligible vacío pero expected_status es SUCCESS",
                )
            # Verificar seed_items ⊆ eligible cuando eligible no es None
            if eligible is not None:
                not_eligible = [
                    sid for sid in request.seed_item_ids if sid not in eligible
                ]
                if not_eligible:
                    raise SeedBuildError(
                        case_id=request.case_id,
                        message=f"seed_item_ids no están en eligible_item_ids: {not_eligible}",
                    )
            # Verificar semantic_concepts vs campo textual (overview para TMDB)
            if request.semantic_concepts:
                for sid in request.seed_item_ids:
                    overview = self._tmdb.get_overview(sid)
                    if not overview or not overview.strip():
                        raise SeedBuildError(
                            case_id=request.case_id,
                            message=(
                                f"semantic_concepts requiere overview no vacío "
                                f"para seed_item '{sid}', pero es None o whitespace"
                            ),
                        )

        elif request.expected_status == "NO_RESULTS":
            # NO_RESULTS: eligible siempre es []
            eligible = []

        # 5. Construir SilverSeed
        return SilverSeed(
            case_id=request.case_id,
            expected_route="trending",
            expected_sources=["tmdb"],
            expected_status=request.expected_status,
            hard_constraints=request.hard_constraints,
            semantic_concepts=request.semantic_concepts,
            seed_item_ids=request.seed_item_ids,
            eligible_item_ids=eligible,
            difficulty=request.difficulty,
            tags=request.tags,
            fixture_version=self._tmdb.fixture_version,
            provenance=SeedProvenance(
                source="tmdb",
                fixture_version=self._tmdb.fixture_version,
                input_data_description=(
                    f"Seed Trending '{request.case_id}' construido desde "
                    f"fixture TMDB {self._tmdb.fixture_version} con "
                    f"{len(request.seed_item_ids)} seed items"
                ),
                schema_version=self._schema_version,
                silver_dataset_version=self._silver_dataset_version,
            ),
        )

    def _build_both(self, request: BothSeedBuildRequest) -> SilverSeed:
        """Construye un seed BOTH (siempre SUCCESS)."""
        # 1. Verificar AMBOS adaptadores disponibles
        if self._tmdb is None:
            raise SeedBuildError(
                case_id=request.case_id,
                message="TmdbAdapter no inyectado, requerido para route 'both'",
            )
        if self._netflix is None:
            raise SeedBuildError(
                case_id=request.case_id,
                message="NetflixAdapter no inyectado, requerido para route 'both'",
            )

        # 2. Verificar no cross-contamination
        for sid in request.tmdb_seed_item_ids:
            if not sid.startswith("tmdb:"):
                raise SeedBuildError(
                    case_id=request.case_id,
                    message=(
                        f"tmdb_seed_item_ids contiene ID no-TMDB: '{sid}' "
                        f"(debe tener prefijo 'tmdb:')"
                    ),
                )
        for sid in request.netflix_seed_item_ids:
            if sid.startswith("tmdb:"):
                raise SeedBuildError(
                    case_id=request.case_id,
                    message=(
                        f"netflix_seed_item_ids contiene ID TMDB: '{sid}' "
                        f"(no debe tener prefijo 'tmdb:')"
                    ),
                )

        # 3. Verificar cada ID existe en su datasource
        tmdb_missing = [
            sid for sid in request.tmdb_seed_item_ids if not self._tmdb.id_exists(sid)
        ]
        if tmdb_missing:
            raise SeedBuildError(
                case_id=request.case_id,
                message=f"IDs no encontrados en TMDB datasource: {tmdb_missing}",
            )
        netflix_missing = [
            sid
            for sid in request.netflix_seed_item_ids
            if not self._netflix.id_exists(sid)
        ]
        if netflix_missing:
            raise SeedBuildError(
                case_id=request.case_id,
                message=f"IDs no encontrados en Netflix datasource: {netflix_missing}",
            )

        # 4. Verificar cada componente tiene al menos 1 seed_item_id
        if len(request.tmdb_seed_item_ids) < 1:
            raise SeedBuildError(
                case_id=request.case_id,
                message="Componente TMDB requiere al menos 1 seed_item_id",
            )
        if len(request.netflix_seed_item_ids) < 1:
            raise SeedBuildError(
                case_id=request.case_id,
                message="Componente Netflix requiere al menos 1 seed_item_id",
            )

        # 5. Calcular eligible por componente
        tmdb_eligible = self._compute_eligible(
            request.tmdb_hard_constraints, self._tmdb
        )
        netflix_eligible = self._compute_eligible(
            request.netflix_hard_constraints, self._netflix
        )

        # 6. Verificar seed_items ⊆ eligible para cada componente
        if tmdb_eligible is not None:
            tmdb_not_eligible = [
                sid for sid in request.tmdb_seed_item_ids if sid not in tmdb_eligible
            ]
            if tmdb_not_eligible:
                raise SeedBuildError(
                    case_id=request.case_id,
                    message=f"tmdb_seed_item_ids no están en tmdb eligible: {tmdb_not_eligible}",
                )
        if netflix_eligible is not None:
            netflix_not_eligible = [
                sid
                for sid in request.netflix_seed_item_ids
                if sid not in netflix_eligible
            ]
            if netflix_not_eligible:
                raise SeedBuildError(
                    case_id=request.case_id,
                    message=f"netflix_seed_item_ids no están en netflix eligible: {netflix_not_eligible}",
                )

        # 7. Verificar semantic_concepts vs texto
        if request.tmdb_semantic_concepts:
            for sid in request.tmdb_seed_item_ids:
                overview = self._tmdb.get_overview(sid)
                if not overview or not overview.strip():
                    raise SeedBuildError(
                        case_id=request.case_id,
                        message=(
                            f"tmdb_semantic_concepts requiere overview no vacío "
                            f"para seed_item '{sid}', pero es None o whitespace"
                        ),
                    )
        if request.netflix_semantic_concepts:
            for sid in request.netflix_seed_item_ids:
                desc = self._netflix.get_description(sid)
                if not desc or not desc.strip():
                    raise SeedBuildError(
                        case_id=request.case_id,
                        message=(
                            f"netflix_semantic_concepts requiere description no vacío "
                            f"para seed_item '{sid}', pero es None o whitespace"
                        ),
                    )

        # 8. Construir componentes
        tmdb_component = TmdbSeedComponent(
            fixture_version=self._tmdb.fixture_version,
            seed_item_ids=request.tmdb_seed_item_ids,
            eligible_item_ids=tmdb_eligible,
            hard_constraints=request.tmdb_hard_constraints,
            semantic_concepts=request.tmdb_semantic_concepts,
        )
        netflix_component = NetflixSeedComponent(
            seed_item_ids=request.netflix_seed_item_ids,
            eligible_item_ids=netflix_eligible,
            hard_constraints=request.netflix_hard_constraints,
            semantic_concepts=request.netflix_semantic_concepts,
        )

        # 9. Construir SilverSeed con campos top-level en default/None
        # Extraer checksum del adaptador canónico si disponible (duck typing)
        canonical_checksum: str | None = None
        if hasattr(self._netflix, "output_checksum_sha256"):
            canonical_checksum = self._netflix.output_checksum_sha256  # type: ignore[union-attr]

        return SilverSeed(
            case_id=request.case_id,
            expected_route="both",
            expected_sources=["tmdb", "netflix"],
            expected_status="SUCCESS",
            hard_constraints=None,
            semantic_concepts=[],
            seed_item_ids=[],
            eligible_item_ids=None,
            difficulty=request.difficulty,
            tags=request.tags,
            fixture_version=self._tmdb.fixture_version,
            tmdb_component=tmdb_component,
            netflix_component=netflix_component,
            provenance=SeedProvenance(
                source="both",
                fixture_version=self._tmdb.fixture_version,
                input_data_description=(
                    f"Seed Both '{request.case_id}' construido desde "
                    f"fixture TMDB {self._tmdb.fixture_version} y dataset Netflix "
                    f"con {len(request.tmdb_seed_item_ids)} TMDB items y "
                    f"{len(request.netflix_seed_item_ids)} Netflix items"
                ),
                schema_version=self._schema_version,
                silver_dataset_version=self._silver_dataset_version,
                canonical_dataset_version=self._canonical_dataset_version,
                canonical_dataset_checksum=canonical_checksum,
                etl_version=self._etl_version,
            ),
        )

    def _build_out_of_scope(self, request: OutOfScopeSeedBuildRequest) -> SilverSeed:
        """Construye un seed OUT_OF_SCOPE."""
        return SilverSeed(
            case_id=request.case_id,
            expected_route="out_of_scope",
            expected_sources=[],
            expected_status="OUT_OF_SCOPE",
            hard_constraints=None,
            semantic_concepts=[],
            seed_item_ids=[],
            eligible_item_ids=None,
            difficulty=request.difficulty,
            tags=request.tags,
            provenance=SeedProvenance(
                source="synthetic",
                fixture_version=None,
                input_data_description="Seed out_of_scope generado para evaluación",
                schema_version=self._schema_version,
                silver_dataset_version=self._silver_dataset_version,
            ),
        )
