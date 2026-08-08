# Evaluación — MovieBot

Este directorio contiene la infraestructura de evaluación del proyecto MovieBot.

## Estructura

### `datasets/`

Datasets estructurados del Silver Evaluation Dataset. Contiene los 150 seeds JSONL para medir la calidad del routing y las recomendaciones generadas por los agentes.

Generación (después de crear el catálogo declarativo):

```bash
uv run python -m moviebot.evals.silver.batch_generator --canonical-version v1 --silver-version silver_v1
```

Salida: `datasets/{silver_version}/seeds.jsonl` + `metadata.json`.

### Módulo `silver/` (`src/moviebot/evals/silver/`)

Infraestructura programática para construcción, validación y persistencia de seeds:

- `models.py` — Modelos Pydantic (SilverSeed, constraints, componentes)
- `adapters.py` — CanonicalNetflixAdapter (JSONL canónico) + TmdbAdapter (fixture)
- `builder.py` — API de construcción de seeds (SeedBuilder)
- `batch_generator.py` — Generación batch de 150 seeds desde catálogo declarativo
- `case_catalog.py` — Loader del catálogo de casos
- `validator.py` — Validaciones de integridad exhaustivas
- `persistence.py` — Serialización JSONL y escritura atómica

### Prerequisitos

1. Ejecutar el ETL para generar el dataset canónico:
   ```bash
   uv run python -m moviebot.etl.netflix_etl --version v1
   ```
2. Tener el fixture TMDB en `raw_data/tmdb/trending_movies_v1.json`
3. Tener el metadata del fixture en `raw_data/tmdb/trending_movies_v1.metadata.json`
4. Tener el catálogo de casos en `config/evals/silver_v1/case_catalog.json`. Debe contener 150 solicitudes: 50 `trending`, 50 `netflix`, 25 `both` y 25 `out_of_scope`; además, exactamente 7 casos Netflix y 3 trending deben ser `NO_RESULTS`.

La generación del dataset estructurado es offline y no usa LLM ni Meilisearch. La guía completa para crear, validar y ejecutar el catálogo está en [`docs/02 - Guía Generación Silver Dataset.md`](../docs/02%20-%20Guía%20Generación%20Silver%20Dataset.md).
