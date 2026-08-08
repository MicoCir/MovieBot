"""Validator — Validaciones de integridad exhaustivas sobre seeds."""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from moviebot.evals.silver.adapters import NetflixAdapter, TmdbAdapter
from moviebot.evals.silver.models import (
    NetflixHardConstraints,
    SilverSeed,
    TmdbHardConstraints,
)

# ID format patterns
_NETFLIX_ID_PATTERN = re.compile(r"^t[ms]\d+$")
_TMDB_ID_PATTERN = re.compile(r"^tmdb:\d+$")


@dataclass
class ValidationError:
    """Error de validación para un seed específico."""

    case_id: str
    validation_id: str
    message: str


@dataclass
class ValidationResult:
    """Resultado de validación de un lote de seeds."""

    is_valid: bool
    errors: list[ValidationError] = field(default_factory=list)


class SeedValidator:
    """Ejecuta validaciones de integridad sobre seeds individuales y lotes.

    NUNCA lanza excepciones — siempre retorna ValidationResult.
    Si necesita un adaptador no inyectado, genera un ValidationError
    con validation_id='ADAPTER_UNAVAILABLE'.
    """

    def __init__(
        self,
        netflix_adapter: NetflixAdapter | None = None,
        tmdb_adapter: TmdbAdapter | None = None,
    ) -> None:
        """Configura adaptadores opcionales para validación."""
        self._netflix = netflix_adapter
        self._tmdb = tmdb_adapter

    def validate_batch(
        self,
        seeds: list[SilverSeed],
    ) -> ValidationResult:
        """Valida un lote completo de seeds.

        Ejecuta TODAS las validaciones sobre cada seed y reporta
        todos los errores encontrados (no se detiene en el primero).
        """
        errors: list[ValidationError] = []
        seen_ids: set[str] = set()
        fixture_versions_seen: set[str] = set()

        for seed in seeds:
            # DUPLICATE_CASE_ID
            if seed.case_id in seen_ids:
                errors.append(
                    ValidationError(
                        case_id=seed.case_id,
                        validation_id="DUPLICATE_CASE_ID",
                        message=f"case_id duplicado: {seed.case_id}",
                    )
                )
            seen_ids.add(seed.case_id)

            # Per-seed validations
            errors.extend(self._validate_single(seed))

            # Collect fixture versions for batch consistency
            if seed.fixture_version is not None:
                fixture_versions_seen.add(seed.fixture_version)
            if seed.tmdb_component is not None and seed.tmdb_component.fixture_version:
                fixture_versions_seen.add(seed.tmdb_component.fixture_version)

        # FIXTURE_VERSION_INCONSISTENT across batch
        if len(fixture_versions_seen) > 1:
            for seed in seeds:
                has_fixture = seed.fixture_version is not None or (
                    seed.tmdb_component is not None
                    and seed.tmdb_component.fixture_version
                )
                if has_fixture:
                    errors.append(
                        ValidationError(
                            case_id=seed.case_id,
                            validation_id="FIXTURE_VERSION_INCONSISTENT",
                            message=(
                                f"Múltiples fixture_versions en el lote: "
                                f"{sorted(fixture_versions_seen)}"
                            ),
                        )
                    )

        return ValidationResult(is_valid=len(errors) == 0, errors=errors)

    def _validate_single(self, seed: SilverSeed) -> list[ValidationError]:
        """Ejecuta todas las validaciones sobre un seed individual."""
        errors: list[ValidationError] = []

        # For out_of_scope: only route/sources/status consistency
        if seed.expected_route == "out_of_scope":
            errors.extend(self._validate_route_sources(seed))
            errors.extend(self._validate_out_of_scope_status(seed))
            return errors

        errors.extend(self._validate_route_sources(seed))
        errors.extend(self._validate_constraint_type_mismatch(seed))
        errors.extend(self._validate_no_results_eligible(seed))
        errors.extend(self._validate_cross_contamination(seed))
        errors.extend(self._validate_ids_exist(seed))
        errors.extend(self._validate_constraint_compatibility(seed))
        errors.extend(self._validate_semantic_text(seed))
        errors.extend(self._validate_eligible_integrity(seed))

        return errors

    # ------------------------------------------------------------------
    # Individual validation methods
    # ------------------------------------------------------------------

    def _validate_out_of_scope_status(self, seed: SilverSeed) -> list[ValidationError]:
        """OUT_OF_SCOPE_STATUS_MISMATCH."""
        if seed.expected_status != "OUT_OF_SCOPE":
            return [
                ValidationError(
                    case_id=seed.case_id,
                    validation_id="OUT_OF_SCOPE_STATUS_MISMATCH",
                    message=(
                        f"route 'out_of_scope' requiere "
                        f"expected_status='OUT_OF_SCOPE', "
                        f"encontrado: '{seed.expected_status}'"
                    ),
                )
            ]
        return []

    def _validate_route_sources(self, seed: SilverSeed) -> list[ValidationError]:
        """ROUTE_SOURCES_MISMATCH."""
        expected_map: dict[str, list[str]] = {
            "trending": ["tmdb"],
            "netflix": ["netflix"],
            "both": ["tmdb", "netflix"],
            "out_of_scope": [],
        }
        expected = expected_map[seed.expected_route]
        if seed.expected_sources != expected:
            return [
                ValidationError(
                    case_id=seed.case_id,
                    validation_id="ROUTE_SOURCES_MISMATCH",
                    message=(
                        f"expected_sources {seed.expected_sources} "
                        f"incompatible con route '{seed.expected_route}'"
                        f", esperado: {expected}"
                    ),
                )
            ]
        return []

    def _validate_constraint_type_mismatch(
        self, seed: SilverSeed
    ) -> list[ValidationError]:
        """CONSTRAINT_TYPE_MISMATCH."""
        errors: list[ValidationError] = []
        if (
            seed.expected_route == "trending"
            and seed.hard_constraints is not None
            and not isinstance(seed.hard_constraints, TmdbHardConstraints)
        ):
            errors.append(
                ValidationError(
                    case_id=seed.case_id,
                    validation_id="CONSTRAINT_TYPE_MISMATCH",
                    message=(
                        "route 'trending' requiere TmdbHardConstraints, "
                        f"encontrado: "
                        f"{type(seed.hard_constraints).__name__}"
                    ),
                )
            )
        elif (
            seed.expected_route == "netflix"
            and seed.hard_constraints is not None
            and not isinstance(seed.hard_constraints, NetflixHardConstraints)
        ):
            errors.append(
                ValidationError(
                    case_id=seed.case_id,
                    validation_id="CONSTRAINT_TYPE_MISMATCH",
                    message=(
                        "route 'netflix' requiere "
                        "NetflixHardConstraints, encontrado: "
                        f"{type(seed.hard_constraints).__name__}"
                    ),
                )
            )
        return errors

    def _validate_no_results_eligible(self, seed: SilverSeed) -> list[ValidationError]:
        """NO_RESULTS_ELIGIBLE_NONE / NO_RESULTS_ELIGIBLE_NOT_EMPTY."""
        errors: list[ValidationError] = []
        if seed.expected_status != "NO_RESULTS":
            return errors

        if seed.expected_route in ("trending", "netflix"):
            if seed.eligible_item_ids is None:
                errors.append(
                    ValidationError(
                        case_id=seed.case_id,
                        validation_id="NO_RESULTS_ELIGIBLE_NONE",
                        message=("NO_RESULTS requiere eligible_item_ids=[] (no None)"),
                    )
                )
            elif seed.eligible_item_ids != []:
                errors.append(
                    ValidationError(
                        case_id=seed.case_id,
                        validation_id="NO_RESULTS_ELIGIBLE_NOT_EMPTY",
                        message=(
                            f"NO_RESULTS requiere eligible_item_ids=[]"
                            f", encontrado "
                            f"{len(seed.eligible_item_ids)} elementos"
                        ),
                    )
                )
        return errors

    def _validate_cross_contamination(self, seed: SilverSeed) -> list[ValidationError]:
        """CROSS_CONTAMINATION — no mezclar IDs Netflix/TMDB."""
        errors: list[ValidationError] = []

        if seed.expected_route == "trending":
            for item_id in seed.seed_item_ids:
                if _NETFLIX_ID_PATTERN.match(item_id):
                    errors.append(
                        ValidationError(
                            case_id=seed.case_id,
                            validation_id="CROSS_CONTAMINATION",
                            message=(
                                f"ID Netflix '{item_id}' en "
                                f"seed_item_ids de route 'trending'"
                            ),
                        )
                    )
            if seed.eligible_item_ids is not None:
                for item_id in seed.eligible_item_ids:
                    if _NETFLIX_ID_PATTERN.match(item_id):
                        errors.append(
                            ValidationError(
                                case_id=seed.case_id,
                                validation_id="CROSS_CONTAMINATION",
                                message=(
                                    f"ID Netflix '{item_id}' en "
                                    f"eligible_item_ids de route "
                                    f"'trending'"
                                ),
                            )
                        )

        elif seed.expected_route == "netflix":
            for item_id in seed.seed_item_ids:
                if _TMDB_ID_PATTERN.match(item_id):
                    errors.append(
                        ValidationError(
                            case_id=seed.case_id,
                            validation_id="CROSS_CONTAMINATION",
                            message=(
                                f"ID TMDB '{item_id}' en "
                                f"seed_item_ids de route 'netflix'"
                            ),
                        )
                    )
            if seed.eligible_item_ids is not None:
                for item_id in seed.eligible_item_ids:
                    if _TMDB_ID_PATTERN.match(item_id):
                        errors.append(
                            ValidationError(
                                case_id=seed.case_id,
                                validation_id="CROSS_CONTAMINATION",
                                message=(
                                    f"ID TMDB '{item_id}' en "
                                    f"eligible_item_ids de route "
                                    f"'netflix'"
                                ),
                            )
                        )

        elif seed.expected_route == "both":
            if seed.tmdb_component is not None:
                for item_id in seed.tmdb_component.seed_item_ids:
                    if _NETFLIX_ID_PATTERN.match(item_id):
                        errors.append(
                            ValidationError(
                                case_id=seed.case_id,
                                validation_id="CROSS_CONTAMINATION",
                                message=(
                                    f"ID Netflix '{item_id}' en "
                                    f"tmdb_component.seed_item_ids"
                                ),
                            )
                        )
                if seed.tmdb_component.eligible_item_ids is not None:
                    for item_id in seed.tmdb_component.eligible_item_ids:
                        if _NETFLIX_ID_PATTERN.match(item_id):
                            errors.append(
                                ValidationError(
                                    case_id=seed.case_id,
                                    validation_id="CROSS_CONTAMINATION",
                                    message=(
                                        f"ID Netflix '{item_id}' en "
                                        f"tmdb_component"
                                        f".eligible_item_ids"
                                    ),
                                )
                            )
            if seed.netflix_component is not None:
                for item_id in seed.netflix_component.seed_item_ids:
                    if _TMDB_ID_PATTERN.match(item_id):
                        errors.append(
                            ValidationError(
                                case_id=seed.case_id,
                                validation_id="CROSS_CONTAMINATION",
                                message=(
                                    f"ID TMDB '{item_id}' en "
                                    f"netflix_component.seed_item_ids"
                                ),
                            )
                        )
                if seed.netflix_component.eligible_item_ids is not None:
                    for item_id in seed.netflix_component.eligible_item_ids:
                        if _TMDB_ID_PATTERN.match(item_id):
                            errors.append(
                                ValidationError(
                                    case_id=seed.case_id,
                                    validation_id="CROSS_CONTAMINATION",
                                    message=(
                                        f"ID TMDB '{item_id}' en "
                                        f"netflix_component"
                                        f".eligible_item_ids"
                                    ),
                                )
                            )

        return errors

    def _validate_ids_exist(self, seed: SilverSeed) -> list[ValidationError]:
        """ID_NOT_FOUND — each seed_item_id must exist in datasource."""
        errors: list[ValidationError] = []

        if seed.expected_route == "trending":
            errors.extend(self._check_tmdb_ids_exist(seed.case_id, seed.seed_item_ids))
        elif seed.expected_route == "netflix":
            errors.extend(
                self._check_netflix_ids_exist(seed.case_id, seed.seed_item_ids)
            )
        elif seed.expected_route == "both":
            if seed.tmdb_component is not None:
                errors.extend(
                    self._check_tmdb_ids_exist(
                        seed.case_id,
                        seed.tmdb_component.seed_item_ids,
                    )
                )
            if seed.netflix_component is not None:
                errors.extend(
                    self._check_netflix_ids_exist(
                        seed.case_id,
                        seed.netflix_component.seed_item_ids,
                    )
                )

        return errors

    def _check_tmdb_ids_exist(
        self, case_id: str, item_ids: list[str]
    ) -> list[ValidationError]:
        """Check TMDB IDs exist in adapter."""
        errors: list[ValidationError] = []
        if not item_ids:
            return errors
        if self._tmdb is None:
            return [
                ValidationError(
                    case_id=case_id,
                    validation_id="ADAPTER_UNAVAILABLE",
                    message=(
                        "TMDB adapter no inyectado, no se puede validar seed_item_ids"
                    ),
                )
            ]
        try:
            for item_id in item_ids:
                if not _TMDB_ID_PATTERN.match(item_id):
                    errors.append(
                        ValidationError(
                            case_id=case_id,
                            validation_id="ID_NOT_FOUND",
                            message=(
                                f"ID '{item_id}' no tiene formato TMDB "
                                f"esperado (tmdb:*)"
                            ),
                        )
                    )
                elif not self._tmdb.id_exists(item_id):
                    errors.append(
                        ValidationError(
                            case_id=case_id,
                            validation_id="ID_NOT_FOUND",
                            message=(f"ID '{item_id}' no existe en el fixture TMDB"),
                        )
                    )
        except Exception as e:  # noqa: BLE001
            errors.append(
                ValidationError(
                    case_id=case_id,
                    validation_id="ADAPTER_ERROR",
                    message=f"Error del adaptador TMDB: {e}",
                )
            )
        return errors

    def _check_netflix_ids_exist(
        self, case_id: str, item_ids: list[str]
    ) -> list[ValidationError]:
        """Check Netflix IDs exist in adapter."""
        errors: list[ValidationError] = []
        if not item_ids:
            return errors
        if self._netflix is None:
            return [
                ValidationError(
                    case_id=case_id,
                    validation_id="ADAPTER_UNAVAILABLE",
                    message=(
                        "Netflix adapter no inyectado, no se puede "
                        "validar seed_item_ids"
                    ),
                )
            ]
        try:
            for item_id in item_ids:
                if not _NETFLIX_ID_PATTERN.match(item_id):
                    errors.append(
                        ValidationError(
                            case_id=case_id,
                            validation_id="ID_NOT_FOUND",
                            message=(
                                f"ID '{item_id}' no tiene formato "
                                f"Netflix esperado (tm*/ts*)"
                            ),
                        )
                    )
                elif not self._netflix.id_exists(item_id):
                    errors.append(
                        ValidationError(
                            case_id=case_id,
                            validation_id="ID_NOT_FOUND",
                            message=(f"ID '{item_id}' no existe en el dataset Netflix"),
                        )
                    )
        except Exception as e:  # noqa: BLE001
            errors.append(
                ValidationError(
                    case_id=case_id,
                    validation_id="ADAPTER_ERROR",
                    message=f"Error del adaptador Netflix: {e}",
                )
            )
        return errors

    def _validate_constraint_compatibility(
        self, seed: SilverSeed
    ) -> list[ValidationError]:
        """CONSTRAINT_MISMATCH — constraints compatible with each seed_item."""
        errors: list[ValidationError] = []

        if seed.expected_route == "trending":
            if not isinstance(seed.hard_constraints, TmdbHardConstraints):
                return errors
            if self._tmdb is None:
                return errors
            try:
                errors.extend(
                    self._check_tmdb_constraint_compat(
                        seed.case_id,
                        seed.seed_item_ids,
                        seed.hard_constraints,
                    )
                )
            except Exception as e:  # noqa: BLE001
                errors.append(
                    ValidationError(
                        case_id=seed.case_id,
                        validation_id="ADAPTER_ERROR",
                        message=f"Error verificando constraints TMDB: {e}",
                    )
                )

        elif seed.expected_route == "netflix":
            if not isinstance(seed.hard_constraints, NetflixHardConstraints):
                return errors
            if self._netflix is None:
                return errors
            try:
                errors.extend(
                    self._check_netflix_constraint_compat(
                        seed.case_id,
                        seed.seed_item_ids,
                        seed.hard_constraints,
                    )
                )
            except Exception as e:  # noqa: BLE001
                errors.append(
                    ValidationError(
                        case_id=seed.case_id,
                        validation_id="ADAPTER_ERROR",
                        message=(f"Error verificando constraints Netflix: {e}"),
                    )
                )

        elif seed.expected_route == "both":
            if seed.tmdb_component is not None and self._tmdb is not None:
                try:
                    errors.extend(
                        self._check_tmdb_constraint_compat(
                            seed.case_id,
                            seed.tmdb_component.seed_item_ids,
                            seed.tmdb_component.hard_constraints,
                        )
                    )
                except Exception as e:  # noqa: BLE001
                    errors.append(
                        ValidationError(
                            case_id=seed.case_id,
                            validation_id="ADAPTER_ERROR",
                            message=(
                                f"Error verificando constraints TMDB "
                                f"(tmdb_component): {e}"
                            ),
                        )
                    )
            if seed.netflix_component is not None and self._netflix is not None:
                try:
                    errors.extend(
                        self._check_netflix_constraint_compat(
                            seed.case_id,
                            seed.netflix_component.seed_item_ids,
                            seed.netflix_component.hard_constraints,
                        )
                    )
                except Exception as e:  # noqa: BLE001
                    errors.append(
                        ValidationError(
                            case_id=seed.case_id,
                            validation_id="ADAPTER_ERROR",
                            message=(
                                f"Error verificando constraints Netflix "
                                f"(netflix_component): {e}"
                            ),
                        )
                    )

        return errors

    def _check_tmdb_constraint_compat(
        self,
        case_id: str,
        seed_item_ids: list[str],
        constraints: TmdbHardConstraints,
    ) -> list[ValidationError]:
        """Check each TMDB seed_item satisfies the constraints."""
        errors: list[ValidationError] = []
        assert self._tmdb is not None

        for item_id in seed_item_ids:
            record = self._tmdb.get_record(item_id)
            if record is None:
                continue  # ID_NOT_FOUND handled elsewhere

            # genre_ids: record must contain ALL constraint genre_ids
            if constraints.genre_ids:
                record_genres = set(record.genre_ids)
                for gid in constraints.genre_ids:
                    if gid not in record_genres:
                        errors.append(
                            ValidationError(
                                case_id=case_id,
                                validation_id="CONSTRAINT_MISMATCH",
                                message=(
                                    f"ID '{item_id}': genre_id {gid} "
                                    f"no está en genre_ids del "
                                    f"registro {record.genre_ids}"
                                ),
                            )
                        )
                        break

            # min_year
            if constraints.min_year is not None and (
                record.release_year is None
                or record.release_year < constraints.min_year
            ):
                errors.append(
                    ValidationError(
                        case_id=case_id,
                        validation_id="CONSTRAINT_MISMATCH",
                        message=(
                            f"ID '{item_id}': release_year "
                            f"{record.release_year} < min_year "
                            f"{constraints.min_year}"
                        ),
                    )
                )

            # max_year
            if constraints.max_year is not None and (
                record.release_year is None
                or record.release_year > constraints.max_year
            ):
                errors.append(
                    ValidationError(
                        case_id=case_id,
                        validation_id="CONSTRAINT_MISMATCH",
                        message=(
                            f"ID '{item_id}': release_year "
                            f"{record.release_year} > max_year "
                            f"{constraints.max_year}"
                        ),
                    )
                )

            # min_vote_average
            if constraints.min_vote_average is not None and (
                record.vote_average is None
                or record.vote_average < constraints.min_vote_average
            ):
                errors.append(
                    ValidationError(
                        case_id=case_id,
                        validation_id="CONSTRAINT_MISMATCH",
                        message=(
                            f"ID '{item_id}': vote_average "
                            f"{record.vote_average} < "
                            f"min_vote_average "
                            f"{constraints.min_vote_average}"
                        ),
                    )
                )

            # max_vote_average
            if constraints.max_vote_average is not None and (
                record.vote_average is None
                or record.vote_average > constraints.max_vote_average
            ):
                errors.append(
                    ValidationError(
                        case_id=case_id,
                        validation_id="CONSTRAINT_MISMATCH",
                        message=(
                            f"ID '{item_id}': vote_average "
                            f"{record.vote_average} > "
                            f"max_vote_average "
                            f"{constraints.max_vote_average}"
                        ),
                    )
                )

        return errors

    def _check_netflix_constraint_compat(
        self,
        case_id: str,
        seed_item_ids: list[str],
        constraints: NetflixHardConstraints,
    ) -> list[ValidationError]:
        """Check each Netflix seed_item satisfies the constraints."""
        errors: list[ValidationError] = []
        assert self._netflix is not None

        for item_id in seed_item_ids:
            title = self._netflix.get_title(item_id)
            if title is None:
                continue  # ID_NOT_FOUND handled elsewhere

            # type check
            if constraints.type is not None and title.type.lower() != constraints.type:
                errors.append(
                    ValidationError(
                        case_id=case_id,
                        validation_id="CONSTRAINT_MISMATCH",
                        message=(
                            f"ID '{item_id}': type '{title.type}' "
                            f"no coincide con constraint type "
                            f"'{constraints.type}'"
                        ),
                    )
                )

            # genres: title must contain ALL constraint genres
            if constraints.genres:
                title_genres_lower = {g.lower() for g in title.genres}
                for genre in constraints.genres:
                    if genre.lower() not in title_genres_lower:
                        errors.append(
                            ValidationError(
                                case_id=case_id,
                                validation_id="CONSTRAINT_MISMATCH",
                                message=(
                                    f"ID '{item_id}': género "
                                    f"'{genre}' no encontrado en "
                                    f"géneros del título"
                                ),
                            )
                        )
                        break

            # min_year
            if (
                constraints.min_year is not None
                and title.release_year < constraints.min_year
            ):
                errors.append(
                    ValidationError(
                        case_id=case_id,
                        validation_id="CONSTRAINT_MISMATCH",
                        message=(
                            f"ID '{item_id}': release_year "
                            f"{title.release_year} < min_year "
                            f"{constraints.min_year}"
                        ),
                    )
                )

            # max_year
            if (
                constraints.max_year is not None
                and title.release_year > constraints.max_year
            ):
                errors.append(
                    ValidationError(
                        case_id=case_id,
                        validation_id="CONSTRAINT_MISMATCH",
                        message=(
                            f"ID '{item_id}': release_year "
                            f"{title.release_year} > max_year "
                            f"{constraints.max_year}"
                        ),
                    )
                )

            # min_imdb_score
            if constraints.min_imdb_score is not None and (
                title.imdb_score is None
                or title.imdb_score < constraints.min_imdb_score
            ):
                errors.append(
                    ValidationError(
                        case_id=case_id,
                        validation_id="CONSTRAINT_MISMATCH",
                        message=(
                            f"ID '{item_id}': imdb_score "
                            f"{title.imdb_score} < min_imdb_score "
                            f"{constraints.min_imdb_score}"
                        ),
                    )
                )

            # max_imdb_score
            if constraints.max_imdb_score is not None and (
                title.imdb_score is None
                or title.imdb_score > constraints.max_imdb_score
            ):
                errors.append(
                    ValidationError(
                        case_id=case_id,
                        validation_id="CONSTRAINT_MISMATCH",
                        message=(
                            f"ID '{item_id}': imdb_score "
                            f"{title.imdb_score} > max_imdb_score "
                            f"{constraints.max_imdb_score}"
                        ),
                    )
                )

            # actors: at least one must match
            if constraints.actors:
                title_actors = self._netflix.get_actors_for_title(item_id)
                filter_actors = {a.lower() for a in constraints.actors}
                title_actors_lower = {a.lower() for a in title_actors}
                if not filter_actors.intersection(title_actors_lower):
                    errors.append(
                        ValidationError(
                            case_id=case_id,
                            validation_id="CONSTRAINT_MISMATCH",
                            message=(
                                f"ID '{item_id}': ningún actor de "
                                f"{constraints.actors} encontrado en "
                                f"créditos del título"
                            ),
                        )
                    )

            # directors: at least one must match
            if constraints.directors:
                title_dirs = self._netflix.get_directors_for_title(item_id)
                filter_dirs = {d.lower() for d in constraints.directors}
                title_dirs_lower = {d.lower() for d in title_dirs}
                if not filter_dirs.intersection(title_dirs_lower):
                    errors.append(
                        ValidationError(
                            case_id=case_id,
                            validation_id="CONSTRAINT_MISMATCH",
                            message=(
                                f"ID '{item_id}': ningún director de "
                                f"{constraints.directors} encontrado "
                                f"en créditos del título"
                            ),
                        )
                    )

        return errors

    def _validate_semantic_text(self, seed: SilverSeed) -> list[ValidationError]:
        """SEMANTIC_TEXT_EMPTY — seed_items with semantic_concepts need text."""
        errors: list[ValidationError] = []

        if seed.expected_route == "trending":
            if not seed.semantic_concepts:
                return errors
            if self._tmdb is None:
                return [
                    ValidationError(
                        case_id=seed.case_id,
                        validation_id="ADAPTER_UNAVAILABLE",
                        message=(
                            "TMDB adapter no inyectado, no se puede "
                            "validar semantic_concepts"
                        ),
                    )
                ]
            try:
                for item_id in seed.seed_item_ids:
                    overview = self._tmdb.get_overview(item_id)
                    if not overview or not overview.strip():
                        errors.append(
                            ValidationError(
                                case_id=seed.case_id,
                                validation_id="SEMANTIC_TEXT_EMPTY",
                                message=(
                                    f"ID '{item_id}' tiene overview "
                                    f"vacío pero seed tiene "
                                    f"semantic_concepts"
                                ),
                            )
                        )
            except Exception as e:  # noqa: BLE001
                errors.append(
                    ValidationError(
                        case_id=seed.case_id,
                        validation_id="ADAPTER_ERROR",
                        message=(f"Error verificando semantic text TMDB: {e}"),
                    )
                )

        elif seed.expected_route == "netflix":
            if not seed.semantic_concepts:
                return errors
            if self._netflix is None:
                return [
                    ValidationError(
                        case_id=seed.case_id,
                        validation_id="ADAPTER_UNAVAILABLE",
                        message=(
                            "Netflix adapter no inyectado, no se puede "
                            "validar semantic_concepts"
                        ),
                    )
                ]
            try:
                for item_id in seed.seed_item_ids:
                    desc = self._netflix.get_description(item_id)
                    if not desc or not desc.strip():
                        errors.append(
                            ValidationError(
                                case_id=seed.case_id,
                                validation_id="SEMANTIC_TEXT_EMPTY",
                                message=(
                                    f"ID '{item_id}' tiene description "
                                    f"vacía pero seed tiene "
                                    f"semantic_concepts"
                                ),
                            )
                        )
            except Exception as e:  # noqa: BLE001
                errors.append(
                    ValidationError(
                        case_id=seed.case_id,
                        validation_id="ADAPTER_ERROR",
                        message=(f"Error verificando semantic text Netflix: {e}"),
                    )
                )

        elif seed.expected_route == "both":
            # TMDB component semantic check
            if (
                seed.tmdb_component is not None
                and seed.tmdb_component.semantic_concepts
            ):
                if self._tmdb is None:
                    errors.append(
                        ValidationError(
                            case_id=seed.case_id,
                            validation_id="ADAPTER_UNAVAILABLE",
                            message=(
                                "TMDB adapter no inyectado, no se puede "
                                "validar semantic_concepts en "
                                "tmdb_component"
                            ),
                        )
                    )
                else:
                    try:
                        for item_id in seed.tmdb_component.seed_item_ids:
                            overview = self._tmdb.get_overview(item_id)
                            if not overview or not overview.strip():
                                errors.append(
                                    ValidationError(
                                        case_id=seed.case_id,
                                        validation_id=("SEMANTIC_TEXT_EMPTY"),
                                        message=(
                                            f"ID '{item_id}' en "
                                            f"tmdb_component tiene "
                                            f"overview vacío pero "
                                            f"componente tiene "
                                            f"semantic_concepts"
                                        ),
                                    )
                                )
                    except Exception as e:  # noqa: BLE001
                        errors.append(
                            ValidationError(
                                case_id=seed.case_id,
                                validation_id="ADAPTER_ERROR",
                                message=(
                                    f"Error verificando semantic text "
                                    f"TMDB (tmdb_component): {e}"
                                ),
                            )
                        )

            # Netflix component semantic check
            if (
                seed.netflix_component is not None
                and seed.netflix_component.semantic_concepts
            ):
                if self._netflix is None:
                    errors.append(
                        ValidationError(
                            case_id=seed.case_id,
                            validation_id="ADAPTER_UNAVAILABLE",
                            message=(
                                "Netflix adapter no inyectado, no se "
                                "puede validar semantic_concepts en "
                                "netflix_component"
                            ),
                        )
                    )
                else:
                    try:
                        for item_id in seed.netflix_component.seed_item_ids:
                            desc = self._netflix.get_description(item_id)
                            if not desc or not desc.strip():
                                errors.append(
                                    ValidationError(
                                        case_id=seed.case_id,
                                        validation_id=("SEMANTIC_TEXT_EMPTY"),
                                        message=(
                                            f"ID '{item_id}' en "
                                            f"netflix_component tiene "
                                            f"description vacía pero "
                                            f"componente tiene "
                                            f"semantic_concepts"
                                        ),
                                    )
                                )
                    except Exception as e:  # noqa: BLE001
                        errors.append(
                            ValidationError(
                                case_id=seed.case_id,
                                validation_id="ADAPTER_ERROR",
                                message=(
                                    f"Error verificando semantic text "
                                    f"Netflix (netflix_component): {e}"
                                ),
                            )
                        )

        return errors

    def _validate_eligible_integrity(self, seed: SilverSeed) -> list[ValidationError]:
        """ELIGIBLE_MISMATCH — recalculate eligible and compare.

        For route 'both': validate each component independently;
        top-level eligible_item_ids is always None (not validated).
        """
        errors: list[ValidationError] = []

        if seed.expected_route == "trending":
            errors.extend(
                self._check_eligible_tmdb(
                    seed.case_id,
                    seed.eligible_item_ids,
                    seed.hard_constraints,
                    "top-level",
                )
            )
        elif seed.expected_route == "netflix":
            errors.extend(
                self._check_eligible_netflix(
                    seed.case_id,
                    seed.eligible_item_ids,
                    seed.hard_constraints,
                    "top-level",
                )
            )
        elif seed.expected_route == "both":
            if seed.tmdb_component is not None:
                errors.extend(
                    self._check_eligible_tmdb(
                        seed.case_id,
                        seed.tmdb_component.eligible_item_ids,
                        seed.tmdb_component.hard_constraints,
                        "tmdb_component",
                    )
                )
            if seed.netflix_component is not None:
                errors.extend(
                    self._check_eligible_netflix(
                        seed.case_id,
                        seed.netflix_component.eligible_item_ids,
                        seed.netflix_component.hard_constraints,
                        "netflix_component",
                    )
                )

        return errors

    def _check_eligible_tmdb(
        self,
        case_id: str,
        eligible_item_ids: list[str] | None,
        constraints: TmdbHardConstraints | NetflixHardConstraints | None,
        context: str,
    ) -> list[ValidationError]:
        """Validate TMDB eligible_item_ids integrity."""
        errors: list[ValidationError] = []

        if eligible_item_ids is None:
            return errors
        if not isinstance(constraints, TmdbHardConstraints):
            return errors
        if constraints.is_default():
            return errors

        if self._tmdb is None:
            return [
                ValidationError(
                    case_id=case_id,
                    validation_id="ADAPTER_UNAVAILABLE",
                    message=(
                        f"TMDB adapter no inyectado, no se puede "
                        f"recalcular eligible_item_ids ({context})"
                    ),
                )
            ]

        try:
            recalculated = self._tmdb.filter(constraints)
            if sorted(eligible_item_ids) != sorted(recalculated):
                stored_set = set(eligible_item_ids)
                calc_set = set(recalculated)
                extra = sorted(stored_set - calc_set)
                missing = sorted(calc_set - stored_set)
                errors.append(
                    ValidationError(
                        case_id=case_id,
                        validation_id="ELIGIBLE_MISMATCH",
                        message=(
                            f"eligible_item_ids ({context}) no coincide "
                            f"con recálculo. Sobrantes: {extra}, "
                            f"Faltantes: {missing}"
                        ),
                    )
                )
        except Exception as e:  # noqa: BLE001
            errors.append(
                ValidationError(
                    case_id=case_id,
                    validation_id="ADAPTER_ERROR",
                    message=(f"Error recalculando eligible TMDB ({context}): {e}"),
                )
            )

        return errors

    def _check_eligible_netflix(
        self,
        case_id: str,
        eligible_item_ids: list[str] | None,
        constraints: TmdbHardConstraints | NetflixHardConstraints | None,
        context: str,
    ) -> list[ValidationError]:
        """Validate Netflix eligible_item_ids integrity."""
        errors: list[ValidationError] = []

        if eligible_item_ids is None:
            return errors
        if not isinstance(constraints, NetflixHardConstraints):
            return errors
        if constraints.is_default():
            return errors

        if self._netflix is None:
            return [
                ValidationError(
                    case_id=case_id,
                    validation_id="ADAPTER_UNAVAILABLE",
                    message=(
                        f"Netflix adapter no inyectado, no se puede "
                        f"recalcular eligible_item_ids ({context})"
                    ),
                )
            ]

        try:
            recalculated = self._netflix.filter(constraints)
            if sorted(eligible_item_ids) != sorted(recalculated):
                stored_set = set(eligible_item_ids)
                calc_set = set(recalculated)
                extra = sorted(stored_set - calc_set)
                missing = sorted(calc_set - stored_set)
                errors.append(
                    ValidationError(
                        case_id=case_id,
                        validation_id="ELIGIBLE_MISMATCH",
                        message=(
                            f"eligible_item_ids ({context}) no coincide "
                            f"con recálculo. Sobrantes: {extra}, "
                            f"Faltantes: {missing}"
                        ),
                    )
                )
        except Exception as e:  # noqa: BLE001
            errors.append(
                ValidationError(
                    case_id=case_id,
                    validation_id="ADAPTER_ERROR",
                    message=(f"Error recalculando eligible Netflix ({context}): {e}"),
                )
            )

        return errors
