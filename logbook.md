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
