# LogBook

## Entrada 1

**Sprint:** 0 — Bootstrap  
**Tarea:** Inicialización técnica del proyecto

### Resumen

Se ejecutó el scaffolding completo del proyecto MovieBot: estructura de paquete instalable `src/moviebot/` con subdirectorios (common, routing, agents/tmdb, agents/netflix, repositories, app, interface), modelos Pydantic con invariantes validadas (MovieCandidate, AgentResult, RouteDecision, TrendingQuery, NetflixQuery, ChatState), interfaces Protocol asíncronas (Router, TrendingRepository, NetflixRepository), configuración centralizada con pydantic-settings y SecretStr, módulo de logging desacoplado, endpoint GET `/health` con FastAPI, infraestructura de testing con 30 tests (happy-path, rejection, invariantes, settings, smoke e integración) y quality gates (pytest, ruff check, ruff format, mypy) pasando en verde. No se creó lógica de negocio ni stubs vacíos.
---

## Entrada 2

**Sprint:** 0 — Bootstrap
**Tarea:** Refinamiento del suite de tests

### Resumen

Se redujo el suite de 30 a 19 casos eliminando variantes de validación redundantes, la fixture no utilizada y un smoke test de importación duplicado. Se añadieron únicamente pruebas dirigidas para `AgentResult`, `content_type`, una decisión de ruta válida y la idempotencia del logging. El test de `/health` se aisló de credenciales y del `.env` local. El objetivo fue mantener la cobertura de contratos relevantes sin sobretestear comportamiento genérico de Pydantic; pytest, Ruff y mypy continúan pasando.

---

## Entrada 3

**Sprint:** 1 — Preparación de Datasources
**Tarea:** Infraestructura de datos para el Silver Evaluation Dataset

### Resumen

Se implementaron tres componentes ortogonales: (1) conector HTTP mínimo contra TMDB Trending Movies (`TmdbConnector`) con mapeo a `MovieCandidate`, jerarquía de excepciones tipada, escritura atómica de fixtures inmutables (payload + metadatos de procedencia separados) y captura real de `trending_movies_v1`; (2) inspector programático del dataset Netflix (`NetflixInspector`) como paquete CLI ejecutable que analiza schema, tipos, nulos, duplicados, relaciones 1:N/M:N, cobertura por subconjunto (all/movies/shows), estadísticas de créditos y clasificación de campos para filtros duros; (3) reporte de inspección JSON determinista (`reports/netflix_inspection.json`) con estrategia de identidad y nota de incompatibilidad de géneros cross-source. Se configuró `mypy` estricto (`disallow_untyped_defs`) para los módulos nuevos y se escribieron 171 tests (unitarios + 13 propiedades con Hypothesis); 2 tests de integración live quedan omitidos por defecto (requieren `TMDB_API_KEY`). Quality gates en verde: pytest, ruff check, ruff format, mypy.

---

## Entrada 4

**Sprint:** 1 — Preparación de Datasources
**Tarea:** Correcciones post-revisión

### Resumen

Se corrigieron dos inconsistencias semánticas detectadas en revisión: (1) el metadata del fixture declaraba `"parameters": {"language": "en-US"}` pero la petición HTTP solo envía `api_key` — se alineó metadata con la realidad (`"parameters": {}`) y se añadió un test que verifica coherencia entre query params enviados y metadata registrada; (2) las observaciones del informe listaban `description` como "campo confiable" pese a estar clasificado como "no fiable para filtros duros" — se modificó `_build_observations()` para derivar la lista de campos verificables desde `field_classifications`, eliminando la contradicción. Informe y metadata fixture regenerados. 171 tests pasando, quality gates completos en verde.

---

## Entrada 5

**Sprint:** 2 — Silver Evaluation Dataset
**Tarea:** Infraestructura de seeds estructurados

### Resumen

Se implementó el paquete `src/moviebot/evals/silver/` con cinco módulos: modelos Pydantic del seed estructurado (`models.py`) con discriminador explícito para round-trip JSON, adaptadores deterministas para Netflix CSV y fixture TMDB (`adapters.py`) con filtrado, builder programático (`builder.py`) con API discriminada por ruta y validaciones de consistencia, validador exhaustivo (`validator.py`) con 14 categorías de error que nunca lanza excepciones, y persistencia atómica (`persistence.py`) con staging+rename, protección contra sobreescritura y checksums SHA-256 por seed. Se escribieron 118 tests (40 modelos, 16 adaptadores, 18 builder, 26 validador, 17 persistencia, 1 integración) incluyendo 8 propiedades basadas en Hypothesis, implementadas mediante 10 tests property-based (determinismo, corrección de filtrado, round-trip, subset invariante, no-contaminación, determinismo de persistencia). Todos los tests corren con bloqueo de red autouse. No se introdujeron dependencias nuevas. Quality gates en verde: pytest (289 tests), ruff check, ruff format, mypy.

---

## Entrada 6

**Sprint:** 3 — Netflix Data Pipeline
**Tarea:** Pipeline ETL determinista + Meilisearch Indexer + Netflix Repository + Batch Generator

### Resumen

Se implementó el pipeline completo de datos Netflix con 58 tareas ejecutadas en 16 waves paralelas. Los componentes principales:

1. **ETL Module** (`src/moviebot/etl/`): Funciones puras de normalización (`transformers.py`), modelos de quality report (`quality_report.py`), schema canónico Pydantic (`schema.py` con `CanonicalNetflixTitle` + `EtlMetadata`), y orquestador `NetflixEtl` con escritura atómica (tmp+rename), join de créditos con deduplicación (key=(id,role,person_id), resolución por nombre lex-menor), serialización determinista JSONL (`sort_keys=True, separators=(",",":")`) y generación de checksums SHA-256.

2. **Canonical Adapter** (`src/moviebot/evals/silver/adapters.py`): `CanonicalNetflixAdapter` que reemplaza el parsing CSV directo, lee desde el JSONL canónico, valida integridad via checksum y version matching, y provee filtrado exhaustivo (genres AND, actors OR, directors OR) para ground truth.

3. **Meilisearch Indexer** (`src/moviebot/indexer/`): `MeilisearchIndexer` con idempotencia (checksums matching → skip), immutabilidad (never overwrite), detección de índices no controlados, cleanup en fallo, activación atómica del registry (`index_registry.json`), y `settings_checksum` determinista.

4. **Netflix Repository** (`src/moviebot/repositories/netflix_meilisearch.py`): `MeilisearchNetflixRepository` traduciendo `NetflixQuery` a filtros Meilisearch (genres AND, actors OR, directors OR, inter-campo AND), con `asyncio.to_thread()` para wrappear SDK sync, y retorno de lista vacía en error.

5. **Intent Extractor** (`src/moviebot/agents/netflix/intent_extractor.py`): `IntentExtractorProtocol` + `LlmIntentExtractor` usando OpenAI structured output con prompt para extracción de nombres completos de actores/directores.

6. **Batch Generator** (`src/moviebot/evals/silver/batch_generator.py`): Orquesta 150 seeds desde `case_catalog.json` con validación de distribución (50/50/25/25), cuota NO_RESULTS (7/3/0), re-validación exhaustiva, y abort on SeedBuildError.

7. **Provenance Updates**: Rename `dataset_version` → `silver_dataset_version` en `SeedProvenance` y `DatasetMetadata`, campos `canonical_dataset_version`, `etl_version`, `checksum_sha256` con model_validator para netflix/both sources.

8. **CLI Entrypoints**: 4 módulos con `if __name__ == "__main__"` blocks (ETL, Batch Generator, Indexer, Search).

9. **Runtime Wiring** (`src/moviebot/common/dependencies.py`): `resolve_active_index` con precedencia (explicit → registry → error), factories para repository e intent extractor, y `NetflixAgent` como composition point.

**Tests escritos:** 653 tests offline (unit + property), 52 integration tests (ETL e2e + pipeline roundtrip), 21 integration Meilisearch (requieren servidor). Property tests validan: determinismo ETL, normalización total, credit dedup, filtrado exhaustivo, construcción de filtros, mapeo de hits, registry integrity, IMDb rejection, batch invariantes, NO_RESULTS quota.

**Documentación actualizada:** README con comandos del pipeline, docs/00 con tabla de componentes y diagrama de flujo, docs/01 con infraestructura de datos, docs/02 con arquitectura completa y flujo batch.

Quality gates: 653 tests offline pasan, 52 integración ETL+pipeline pasan. Ruff check, ruff format y mypy sin errores. 21 tests de integración Meilisearch requieren servidor local. 1 warning residual de terceros (Starlette/httpx deprecation).
