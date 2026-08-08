# MovieBot

Agente conversacional recomendador de películas.

## Requisitos del sistema

- Python ≥ 3.12
- [uv](https://docs.astral.sh/uv/) como gestor de paquetes y entornos

## Instalación

```bash
uv sync
```

## Configuración

Copiar `.env.example` a `.env` y completar las variables requeridas:

```bash
cp .env.example .env
```

Variables relevantes:

| Variable | Descripción |
|----------|-------------|
| `TMDB_API_KEY` | API key v3 de TMDB (requerida para el conector de trending) |
| `OPENAI_API_KEY` | Clave de OpenAI |
| `OPENAI_MODEL` | Modelo a utilizar (e.g. `gpt-4`) |

## Ejecución

```bash
uv run uvicorn moviebot.interface.api:app --reload
```

## Herramientas CLI

### Inspector Netflix

Analiza los CSVs del dataset Netflix y genera un reporte de inspección:

```bash
uv run python -m moviebot.tools.inspect_netflix --output reports/netflix_inspection.json
```

Opciones:
- `--titles PATH` — ruta a titles.csv (default: `raw_data/netflix/titles.csv`)
- `--credits PATH` — ruta a credits.csv (default: `raw_data/netflix/credits.csv`)
- `--output PATH` — ruta de salida (si se omite, emite a stdout)
- `--format json|text` — formato de salida (default: `json`)

### Captura de fixture TMDB

La implementación actual consulta la ventana semanal (`week`). El endpoint de Trending Movies de TMDB solo admite las ventanas `day` y `week`; no existe una ventana nativa de un mes o de un año. Consulta la [documentación oficial de TMDB](https://developer.themoviedb.org/reference/trending-movies).

Captura una snapshot inmutable del endpoint TMDB Trending Movies. Requiere `OPENAI_API_KEY`, `OPENAI_MODEL` y `TMDB_API_KEY` configuradas en `.env`, ya que `Settings()` valida su presencia al instanciarse:

```python
import asyncio
from moviebot.common.config import Settings
from moviebot.repositories.tmdb_connector import TmdbConnector

async def main():
    settings = Settings()
    async with TmdbConnector(settings=settings) as connector:
        paths = await connector.capture_fixture("v1")
        print(f"Payload: {paths.payload_path}")
        print(f"Metadata: {paths.metadata_path}")

asyncio.run(main())
```

Notas:
- Si ya existe un fixture con la misma versión, la operación falla sin sobrescribir (conflicto).
- La escritura es atómica: si falla, no quedan archivos parciales.

Si en el futuro se necesitan tendencias mensuales o anuales, habrá que construirlas agregando snapshots diarios/semanales almacenados por la aplicación. Usar `discover/movie` con filtros de fecha sería una estrategia diferente, no equivalente a Trending.

## Tests

```bash
uv run pytest
```

Los tests de integración se excluyen por defecto (configurado en `pyproject.toml`). Para ejecutarlos (requieren `OPENAI_API_KEY`, `OPENAI_MODEL`, `TMDB_API_KEY` y conexión a internet):

```bash
uv run pytest -m integration
```

Para ejecutar solo los tests del Silver Dataset (offline, sin credenciales):

```bash
uv run pytest tests/evals/silver/ -v
```

## Lint

```bash
uv run ruff check src/moviebot/ tests/
```

## Formato

```bash
uv run ruff format --check src/moviebot/ tests/
```

## Type checking

```bash
uv run mypy src/moviebot/
```

## Estructura del proyecto

```
src/moviebot/
├── common/          # Config, modelos compartidos, errores, logging
├── repositories/    # Conector TMDB, FixtureWriter, protocols
├── routing/         # Router de queries
├── agents/          # Agentes TMDB y Netflix
├── evals/           # Evaluación offline
│   └── silver/      # Silver Dataset: modelos, adaptadores, builder, validator, persistence
├── tools/           # Herramientas CLI (inspect_netflix)
├── app/             # Estado de la aplicación
└── interface/       # API FastAPI
```

## Artefactos generados

| Archivo | Descripción |
|---------|-------------|
| `raw_data/tmdb/trending_movies_v1.json` | Payload del fixture TMDB (respuesta real) |
| `raw_data/tmdb/trending_movies_v1.metadata.json` | Metadatos de procedencia (checksum SHA-256, endpoint, timestamp UTC) |
| `reports/netflix_inspection.json` | Reporte de inspección del dataset Netflix (determinista) |

### Salida esperada (Silver Dataset)

Los siguientes archivos se generarán cuando se construya físicamente el dataset usando la infraestructura de `moviebot.evals.silver`:

| Archivo | Descripción |
|---------|-------------|
| `evals/datasets/silver_v1/seeds.jsonl` | Seeds estructurados del Silver Evaluation Dataset (JSONL) |
| `evals/datasets/silver_v1/metadata.json` | Metadata del dataset (checksum, distribución por ruta, versión) |

Ver [docs/02 - Guía Generación Silver Dataset.md](docs/02%20-%20Guía%20Generación%20Silver%20Dataset.md) para detalles del flujo de generación.
