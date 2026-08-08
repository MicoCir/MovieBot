# Guía de Generación del Silver Dataset

## Visión General

El Silver Evaluation Dataset es un conjunto de **seeds estructurados** que representan casos de evaluación para el sistema de recomendación de MovieBot. Cada seed define un escenario completo (ruta esperada, constraints, ítems de referencia, estado esperado) *antes* de la generación de la query en lenguaje natural.

La generación es completamente **offline y determinista**: no requiere llamadas de red ni uso de LLMs. Opera exclusivamente sobre los datasources locales (dataset canónico Netflix JSONL y fixture TMDB).

> **Nota:** Esta guía documenta la infraestructura programática para construir seeds. El código del pipeline está implementado, pero el catálogo declarativo (`config/evals/silver_v1/case_catalog.json`) no forma parte de este checkout. Por tanto, el batch no puede ejecutarse hasta que ese catálogo se cree y se versiona junto al proyecto. La creación del catálogo es determinista y no requiere LLM; sí requiere decisiones de diseño sobre las consultas que se quieren evaluar.

## Estado de la implementación

En el estado actual del repositorio:

- Los CSV de Netflix están disponibles en `raw_data/netflix/`.
- El fixture TMDB y su checksum están disponibles en `raw_data/tmdb/`.
- El ETL y los adaptadores offline están implementados y validados por tests.
- Falta `config/evals/silver_v1/case_catalog.json`, que es el input declarativo que falta para producir los 150 seeds.
- No se necesita `OPENAI_API_KEY`, Meilisearch ni conexión de red para ejecutar el ETL y el `BatchGenerator` con esos inputs locales.

La guía debe leerse, por tanto, en este orden: preparar datasources, crear el catálogo, validarlo y ejecutar el batch.

## Arquitectura del Sistema

```
src/moviebot/
├── etl/                 → Pipeline ETL: CSVs crudos → dataset canónico (titles.jsonl + metadata.json)
│   ├── netflix_etl.py       → Orquestador: lectura, normalización, join, validación, escritura atómica
│   ├── transformers.py      → Funciones puras de normalización (tipos, géneros, nombres, scores)
│   ├── quality_report.py    → Modelo del quality report (registros descartados, field nullifications)
│   └── schema.py            → CanonicalNetflixTitle + EtlMetadata (contrato del JSONL)
├── evals/silver/
│   ├── models.py        → Modelos Pydantic (SilverSeed, constraints, componentes)
│   ├── adapters.py      → CanonicalNetflixAdapter (lee JSONL canónico) + NetflixAdapter (legacy CSV) + TmdbAdapter
│   ├── builder.py       → API programática de construcción de seeds (SeedBuilder)
│   ├── batch_generator.py → BatchGenerator: orquesta generación de 150 seeds desde case_catalog.json
│   ├── case_catalog.py  → Loader y validación del catálogo declarativo
│   ├── validator.py     → Validaciones de integridad exhaustivas
│   └── persistence.py   → Serialización JSONL y escritura atómica (SeedPersistence)
├── indexer/
│   ├── meilisearch_indexer.py → MeilisearchIndexer: ingesta dataset canónico en índice versionado
│   └── index_metadata.py     → Modelo del registry de índices (index_registry.json)
├── repositories/
│   ├── protocols.py           → NetflixRepository protocol
│   └── netflix_meilisearch.py → MeilisearchNetflixRepository: queries Meilisearch para el agente
└── agents/netflix/
    ├── models.py              → NetflixQuery (con actors/directors)
    └── intent_extractor.py    → IntentExtractorProtocol + LlmIntentExtractor
```

**Salida ETL:** `data/processed/netflix/{version}/titles.jsonl` + `metadata.json` + `quality_report.json`

**Salida Seeds:** `evals/datasets/{version}/seeds.jsonl` + `metadata.json`

### Flujo de datos entre componentes

```text
CSVs crudos (titles.csv + credits.csv)
    ↓
NetflixEtl (src/moviebot/etl/)
    ↓
Dataset Canónico (titles.jsonl + metadata.json)
    ↓                              ↓
CanonicalNetflixAdapter      MeilisearchIndexer
(ground truth exhaustivo)    (ingesta en índice runtime)
    ↓                              ↓
BatchGenerator               Meilisearch (netflix_{version})
(case_catalog.json → seeds)        ↓
    ↓                        MeilisearchNetflixRepository
Silver Dataset               (NetflixQuery → búsqueda runtime)
(seeds.jsonl)
```

- **ETL → Dataset Canónico:** normalización única en un solo punto (tipos, géneros, actores, directores)
- **CanonicalNetflixAdapter:** consume el JSONL para computar `eligible_item_ids` (filtrado exhaustivo)
- **MeilisearchIndexer:** consume el mismo JSONL para poblar el índice de búsqueda
- **MeilisearchNetflixRepository:** consulta Meilisearch en runtime para el agente Netflix
- **BatchGenerator:** lee el catálogo declarativo y produce los 150 seeds determinísticamente

## Prerequisitos

1. **Dataset canónico generado:** Ejecutar el ETL (`python -m moviebot.etl.netflix_etl --version v1`) para producir `data/processed/netflix/v1/titles.jsonl` + `metadata.json` a partir de los CSVs crudos
2. CSVs fuente disponibles en `raw_data/netflix/titles.csv` y `raw_data/netflix/credits.csv` (input del ETL)
3. Fixture TMDB capturado en `raw_data/tmdb/trending_movies_v1.json` con su metadata de checksum
4. Catálogo declarativo creado en `config/evals/silver_v1/case_catalog.json` (ver la sección siguiente)

Meilisearch solo es necesario para probar el runtime de Netflix. No es un prerequisito para generar el Silver Dataset.

## Conceptos Clave

### Rutas de un Seed

| Ruta | Descripción | Datasource | Constraint Type |
|------|-------------|------------|-----------------|
| `trending` | Películas en tendencia (TMDB) | Fixture TMDB | `TmdbHardConstraints` |
| `netflix` | Catálogo Netflix | Dataset canónico (JSONL) | `NetflixHardConstraints` |
| `both` | Ambas fuentes combinadas | Ambos | Componentes independientes |
| `out_of_scope` | Fuera del dominio | Ninguno | Ninguno |

### Estados Esperados

| Estado | Significado |
|--------|-------------|
| `SUCCESS` | Existen ítems que satisfacen los constraints |
| `NO_RESULTS` | Los constraints son válidos pero no producen resultados |
| `OUT_OF_SCOPE` | La consulta está fuera del dominio del sistema |

### Hard Constraints

Restricciones verificables determinísticamente contra el datasource:

- **TMDB:** `genre_ids`, `min_year`/`max_year`, `min_vote_average`/`max_vote_average`
- **Netflix:** `type`, `genres`, `min_year`/`max_year`, `min_imdb_score`/`max_imdb_score`, `actors`, `directors`

### Eligible Item IDs

Conjunto exhaustivo de IDs que satisfacen TODOS los hard constraints de un seed. Se calcula automáticamente por el builder cuando los constraints son no-default. Es `None` cuando el seed solo tiene `semantic_concepts` (no calculable determinísticamente).

## Flujo de Generación

### 0. Crear el catálogo declarativo

El repositorio no genera automáticamente el catálogo: debe crearse como un artefacto de diseño, revisarse y versionarse. El catálogo contiene solicitudes de construcción, no `SilverSeed` ya calculados. El `BatchGenerator` calcula `eligible_item_ids`, la procedencia y los checksums a partir de los datasources locales.

Crear el directorio y el archivo:

```powershell
New-Item -ItemType Directory -Force -Path config/evals/silver_v1
```

La estructura mínima del archivo es:

```json
{
  "version": "1.0.0",
  "seeds": [
    {
      "case_id": "netflix-action-001",
      "route": "netflix",
      "expected_status": "SUCCESS",
      "seed_item_ids": ["tm00001"],
      "hard_constraints": {
        "constraint_type": "netflix",
        "type": "movie",
        "genres": ["action"],
        "min_year": 2010
      },
      "semantic_concepts": [],
      "difficulty": "easy",
      "tags": ["genre", "year"]
    },
    {
      "case_id": "trending-no-results-001",
      "route": "trending",
      "expected_status": "NO_RESULTS",
      "seed_item_ids": [],
      "hard_constraints": {
        "constraint_type": "tmdb",
        "min_year": 2099
      },
      "semantic_concepts": [],
      "difficulty": "hard",
      "tags": ["no-results"]
    },
    {
      "case_id": "both-action-001",
      "route": "both",
      "tmdb_component": {
        "seed_item_ids": ["tmdb:969681"],
        "hard_constraints": {
          "constraint_type": "tmdb",
          "genre_ids": [28]
        },
        "semantic_concepts": []
      },
      "netflix_component": {
        "seed_item_ids": ["tm00001"],
        "hard_constraints": {
          "constraint_type": "netflix",
          "type": "movie",
          "genres": ["action"]
        },
        "semantic_concepts": []
      },
      "difficulty": "hard",
      "tags": ["multi-source"]
    },
    {
      "case_id": "out-of-scope-001",
      "route": "out_of_scope",
      "difficulty": "easy",
      "tags": ["out-of-scope"]
    }
  ]
}
```

Los IDs del ejemplo son ilustrativos: deben sustituirse por IDs reales del datasource cargado. Para descubrir candidatos antes de escribir cada caso:

```bash
uv run python -c "from moviebot.evals.silver.adapters import CanonicalNetflixAdapter; from moviebot.evals.silver.models import NetflixHardConstraints; a=CanonicalNetflixAdapter(canonical_dataset_version='v1'); print(a.filter(NetflixHardConstraints(type='movie', genres=['action']))[:20])"
uv run python -c "from moviebot.evals.silver.adapters import TmdbAdapter; from moviebot.evals.silver.models import TmdbHardConstraints; a=TmdbAdapter(fixture_version='v1'); print(a.filter(TmdbHardConstraints(genre_ids=[28]))[:20])"
```

Reglas que debe cumplir el catálogo completo:

| Ruta | Casos | Estado y campos relevantes |
|------|------:|----------------------------|
| `netflix` | 50 | 43 `SUCCESS` y 7 `NO_RESULTS`; constraints `NetflixHardConstraints` |
| `trending` | 50 | 47 `SUCCESS` y 3 `NO_RESULTS`; constraints `TmdbHardConstraints` |
| `both` | 25 | Siempre `SUCCESS`; un componente TMDB y otro Netflix |
| `out_of_scope` | 25 | Solo `difficulty`/`tags`; no tiene IDs ni constraints |

Además, todos los `case_id` deben ser únicos y cumplir `^[a-zA-Z0-9_-]+$` con un máximo de 64 caracteres. En Silver v1 no se permiten `min_imdb_score` ni `max_imdb_score`. Un caso `SUCCESS` debe tener al menos un ID que satisfaga todos sus hard constraints; un caso `NO_RESULTS` debe tener `seed_item_ids: []` y sus constraints deben devolver exactamente cero IDs. Si se usan `semantic_concepts`, el título/overview asociado debe tener texto no vacío.

Validar primero la forma, la distribución y la cuota del catálogo:

```bash
uv run python -c "from pathlib import Path; from moviebot.evals.silver.case_catalog import load_case_catalog; cases=load_case_catalog(Path('config/evals/silver_v1/case_catalog.json')); print(f'Catalogo valido: {len(cases)} casos')"
```

Esta validación no sustituye a la ejecución del batch: el `BatchGenerator` vuelve a validar IDs, constraints, elegibles y procedencia contra los datasources reales.

### 1. Instanciar Adaptadores

```python
from pathlib import Path
from moviebot.evals.silver.adapters import CanonicalNetflixAdapter, TmdbAdapter

# El CanonicalNetflixAdapter lee desde el dataset canónico producido por el ETL.
# Valida checksums, versiones y consistencia con metadata.json automáticamente.
netflix = CanonicalNetflixAdapter(
    canonical_dataset_version="v1",
    base_dir=Path("data/processed/netflix"),
)

tmdb = TmdbAdapter(
    fixture_version="v1",
    base_dir=Path("raw_data/tmdb"),
)
```

El `CanonicalNetflixAdapter` verifica al inicializarse que el SHA-256 del `titles.jsonl` coincide con el registrado en `metadata.json`, garantizando integridad del dataset canónico. Expone `etl_version`, `schema_version` y `canonical_dataset_version` para trazabilidad.

El `TmdbAdapter` verifica automáticamente el checksum SHA-256 del fixture contra su metadata al cargarse.

### 2. Crear el Builder

```python
from moviebot.evals.silver.builder import SeedBuilder

builder = SeedBuilder(
    netflix_adapter=netflix,
    tmdb_adapter=tmdb,
    schema_version="1.0.0",
    silver_dataset_version="silver_v1",
    canonical_dataset_version="v1",
    etl_version="1.0.0",
)
```

### 3. Construir Seeds

#### Seed Netflix (SUCCESS)

```python
from moviebot.evals.silver.builder import NetflixSeedBuildRequest
from moviebot.evals.silver.models import NetflixHardConstraints

# Los IDs y constraints deben coincidir con datos reales del dataset cargado.
# Usa netflix_adapter.filter() para descubrir IDs elegibles antes de construir.
request = NetflixSeedBuildRequest(
    case_id="netflix-crime-70s",
    expected_status="SUCCESS",
    seed_item_ids=["tm84618"],  # Taxi Driver (1976, drama+crime)
    hard_constraints=NetflixHardConstraints(
        type="movie",
        genres=["crime"],
        min_year=1970,
        max_year=1979,
    ),
    semantic_concepts=[],
    difficulty="easy",
    tags=["genre-filter", "year-range"],
)

seed = builder.build(request)
```

#### Seed Trending (SUCCESS)

```python
from moviebot.evals.silver.builder import TrendingSeedBuildRequest
from moviebot.evals.silver.models import TmdbHardConstraints

# Los IDs deben existir en el fixture TMDB cargado y satisfacer los constraints.
# Usa tmdb_adapter.filter() para descubrir IDs elegibles.
request = TrendingSeedBuildRequest(
    case_id="trending-scifi-action",
    expected_status="SUCCESS",
    seed_item_ids=["tmdb:969681"],  # Spider-Man: Brand New Day (sci-fi+action+adventure)
    hard_constraints=TmdbHardConstraints(
        genre_ids=[878, 28],  # Sci-Fi + Action
        min_year=2026,
    ),
    semantic_concepts=[],
    difficulty="medium",
    tags=["genre-filter"],
)

seed = builder.build(request)
```

#### Seed Both (siempre SUCCESS)

```python
from moviebot.evals.silver.builder import BothSeedBuildRequest

# Cada componente usa IDs de su propio datasource.
# Los IDs TMDB deben tener prefijo "tmdb:", los Netflix no.
request = BothSeedBuildRequest(
    case_id="both-scifi-action",
    difficulty="hard",
    tags=["multi-source"],
    tmdb_seed_item_ids=["tmdb:969681"],  # Spider-Man (fixture TMDB)
    tmdb_hard_constraints=TmdbHardConstraints(genre_ids=[878], min_year=2026),
    tmdb_semantic_concepts=[],
    netflix_seed_item_ids=["tm84618"],  # Taxi Driver (dataset canónico)
    netflix_hard_constraints=NetflixHardConstraints(
        type="movie",
        genres=["crime"],
        min_year=1970,
        max_year=1979,
    ),
    netflix_semantic_concepts=[],
)

seed = builder.build(request)
```

#### Seed Out of Scope

```python
from moviebot.evals.silver.builder import OutOfScopeSeedBuildRequest

request = OutOfScopeSeedBuildRequest(
    case_id="oos-weather",
    difficulty="easy",
    tags=["out-of-scope", "non-movie"],
)

seed = builder.build(request)
```

#### Seed NO_RESULTS

```python
request = NetflixSeedBuildRequest(
    case_id="netflix-impossible-combo",
    expected_status="NO_RESULTS",
    seed_item_ids=[],
    hard_constraints=NetflixHardConstraints(
        genres=["drama"],
        min_year=2099,  # No hay películas de 2099
    ),
    semantic_concepts=[],
    difficulty="hard",
    tags=["no-results"],
)

seed = builder.build(request)
```

### 4. Persistir el Dataset

```python
from pathlib import Path
from moviebot.evals.silver.persistence import SeedPersistence

persistence = SeedPersistence(
    base_output_dir=Path("evals/datasets"),
    netflix_adapter=netflix,
    tmdb_adapter=tmdb,
    schema_version="1.0.0",
)

# seeds es una lista de SilverSeed construidos en el paso anterior
result = persistence.persist(seeds, silver_dataset_version="silver_v1")

print(f"Seeds: {result.seeds_path}")
print(f"Metadata: {result.metadata_path}")
print(f"Total: {result.seed_count} seeds")
print(f"Checksum: {result.checksum_sha256}")
```

### 5. Generación Batch (150 seeds desde catálogo declarativo)

Para generar el batch completo de 150 seeds del Silver Dataset se usa el `BatchGenerator`:

```python
from pathlib import Path
from moviebot.evals.silver.batch_generator import BatchGenerator, BatchGeneratorConfig

config = BatchGeneratorConfig(
    canonical_dataset_version="v1",
    silver_dataset_version="silver_v1",
    schema_version="1.0.0",
    etl_version="1.0.0",
    tmdb_fixture_version="v1",
    case_catalog_path=Path("config/evals/silver_v1/case_catalog.json"),
    output_base_dir=Path("evals/datasets"),
)

generator = BatchGenerator(
    config=config,
    netflix_adapter=netflix,
    tmdb_adapter=tmdb,
)

result = generator.generate()
print(f"Seeds generados: {result.seed_count}")
print(f"Checksum: {result.checksum_sha256}")
```

O mediante CLI:

```bash
uv run python -m moviebot.evals.silver.batch_generator \
    --canonical-version v1 \
    --silver-version silver_v1
```

## Validaciones Automáticas

El sistema de persistencia ejecuta automáticamente un lote completo de validaciones antes de escribir:

| Validación | Descripción |
|------------|-------------|
| `DUPLICATE_CASE_ID` | Unicidad de identificadores |
| `ROUTE_SOURCES_MISMATCH` | Consistencia ruta ↔ fuentes |
| `CONSTRAINT_TYPE_MISMATCH` | Tipo de constraint compatible con ruta |
| `ID_NOT_FOUND` | IDs existen en el datasource |
| `CONSTRAINT_MISMATCH` | Cada seed_item satisface los constraints |
| `CROSS_CONTAMINATION` | No mezclar IDs Netflix/TMDB |
| `ELIGIBLE_MISMATCH` | Eligible recalculado coincide con el almacenado |
| `SEMANTIC_TEXT_EMPTY` | Items con semantic_concepts tienen texto |
| `NO_RESULTS_ELIGIBLE_NOT_EMPTY` | NO_RESULTS requiere eligible vacío |
| `FIXTURE_VERSION_INCONSISTENT` | Versión de fixture uniforme en el lote |

Si cualquier validación falla, la persistencia aborta sin crear archivos.

## Garantías del Sistema

- **Determinismo:** dado el mismo datasource y los mismos inputs, el resultado es idéntico byte a byte
- **Atomicidad:** la escritura usa staging + rename atómico; si falla, no quedan archivos parciales
- **Protección contra sobreescritura:** no se puede persistir sobre un directorio existente
- **Inmutabilidad de inputs:** los objetos seed pasados a `persist()` no se mutan
- **Aislamiento:** el paquete `evals/` no importa de `moviebot.routing`, `moviebot.agents`, ni `moviebot.repositories`
- **Offline:** ninguna operación requiere conexión a internet

## Formato de Salida

### seeds.jsonl

Una línea JSON por seed, ordenados por `case_id`. Serialización canónica: `sort_keys=True, separators=(",",":")`.

### metadata.json

```json
{
  "silver_dataset_version": "silver_v1",
  "schema_version": "1.0.0",
  "created_at": "2024-01-15T10:30:00+00:00",
  "seed_count": 150,
  "checksum_sha256": "abc123...",
  "route_distribution": {
    "trending": 50,
    "netflix": 50,
    "both": 25,
    "out_of_scope": 25
  },
  "canonical_dataset_version": "v1",
  "canonical_dataset_checksum": "639ff997...",
  "etl_version": "1.0.0"
}
```

## Tests

Los tests del módulo silver se ejecutan con:

```bash
uv run pytest tests/evals/silver/ -v
```

Incluyen 8 propiedades basadas en Hypothesis, implementadas mediante 10 tests property-based (mínimo 100 ejemplos cada uno), que verifican determinismo, corrección de filtrado, round-trip de serialización, y ausencia de contaminación cruzada. Todos los tests corren con bloqueo de red activo (autouse fixture).
