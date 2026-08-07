# MovieBot
Agente conversacional recomendador de películas

## Setup del entorno

### Requisitos previos
- [uv](https://docs.astral.sh/uv/) instalado
- Python 3.12+

### Instalación

```bash
# Crear entorno virtual
uv venv .venv --python 3.12

# Activar entorno virtual (Windows PowerShell)
.venv\Scripts\Activate.ps1

# Instalar dependencias
uv sync
```

### Gestión de dependencias

El proyecto usa `uv` con `pyproject.toml` para gestionar dependencias.

```bash
uv add nombre_libreria       # Añadir dependencia
uv remove nombre_libreria    # Eliminar dependencia
uv sync                      # Instalar todo desde el lockfile
```
