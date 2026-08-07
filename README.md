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

## Ejecución

```bash
uv run uvicorn moviebot.interface.api:app --reload
```

## Tests

```bash
uv run pytest
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
