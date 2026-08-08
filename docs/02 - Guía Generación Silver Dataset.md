# Guía de Generación del Silver Dataset

## Visión General

El Silver Evaluation Dataset es un conjunto de **seeds estructurados** que representan casos de evaluación para el sistema de recomendación de MovieBot. Cada seed define un escenario completo (ruta esperada, constraints, ítems de referencia, estado esperado) *antes* de la generación de la query en lenguaje natural.

La generación es completamente **offline y determinista**: no requiere llamadas de red ni uso de LLMs. Opera exclusivamente sobre los datasources locales (Netflix CSV y fixture TMDB).

> **Nota:** Esta guía documenta la **infraestructura programática** para construir seeds. La generación física de los ~150 casos del Silver Dataset se realizará en una fase posterior utilizando esta API. Lo que aquí se describe es el contrato, las validaciones y el flujo de persistencia.

## Arquitectura del Sistema

```
src/moviebot/evals/silver/
├── models.py        → Modelos Pydantic (SilverSeed, constraints, componentes)
├── adapters.py      → Adaptadores deterministas (Netflix CSV, fixture TMDB)
├── builder.py       → API programática de construcción de seeds
├── validator.py     → Validaciones de integridad exhaustivas
└── persistence.py   → Serialización JSONL y escritura atómica
```

**Salida:** `evals/datasets/{version}/seeds.jsonl` + `metadata.json`

## Prerequisitos

1. Dataset Netflix disponible en `raw_data/netflix/titles.csv` (y opcionalmente `credits.csv` para filtros por actor/director)
2. Fixture TMDB capturado en `raw_data/tmdb/trending_movies_v1.json` con su metadata de checksum

## Conceptos Clave

### Rutas de un Seed

| Ruta | Descripción | Datasource | Constraint Type |
|------|-------------|------------|-----------------|
| `trending` | Películas en tendencia (TMDB) | Fixture TMDB | `TmdbHardConstraints` |
| `netflix` | Catálogo Netflix | CSV Netflix | `NetflixHardConstraints` |
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

### 1. Instanciar Adaptadores

```python
from pathlib import Path
from moviebot.evals.silver.adapters import NetflixAdapter, TmdbAdapter

netflix = NetflixAdapter(
    titles_path=Path("raw_data/netflix/titles.csv"),
    credits_path=Path("raw_data/netflix/credits.csv"),
)

tmdb = TmdbAdapter(
    fixture_version="v1",
    base_dir=Path("raw_data/tmdb"),
)
```

El `TmdbAdapter` verifica automáticamente el checksum SHA-256 del fixture contra su metadata al cargarse.

### 2. Crear el Builder

```python
from moviebot.evals.silver.builder import SeedBuilder

builder = SeedBuilder(
    netflix_adapter=netflix,
    tmdb_adapter=tmdb,
    schema_version="1.0.0",
    dataset_version="silver_v1",
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
    netflix_seed_item_ids=["tm84618"],  # Taxi Driver (Netflix CSV)
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
result = persistence.persist(seeds, dataset_version="silver_v1")

print(f"Seeds: {result.seeds_path}")
print(f"Metadata: {result.metadata_path}")
print(f"Total: {result.seed_count} seeds")
print(f"Checksum: {result.checksum_sha256}")
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
  "dataset_version": "silver_v1",
  "schema_version": "1.0.0",
  "created_at": "2024-01-15T10:30:00+00:00",
  "seed_count": 150,
  "checksum_sha256": "abc123...",
  "route_distribution": {
    "trending": 50,
    "netflix": 50,
    "both": 25,
    "out_of_scope": 25
  }
}
```

## Tests

Los tests del módulo silver se ejecutan con:

```bash
uv run pytest tests/evals/silver/ -v
```

Incluyen 8 propiedades basadas en Hypothesis, implementadas mediante 10 tests property-based (mínimo 100 ejemplos cada uno), que verifican determinismo, corrección de filtrado, round-trip de serialización, y ausencia de contaminación cruzada. Todos los tests corren con bloqueo de red activo (autouse fixture).
