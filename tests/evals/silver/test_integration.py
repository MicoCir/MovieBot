"""Integration test: verifica aislamiento de imports del paquete evals.

El paquete src/moviebot/evals/ NO debe importar de:
- moviebot.routing
- moviebot.agents
- moviebot.repositories

El test importa el paquete evals y recorre transitivamente todos los módulos
cargados en sys.modules para verificar que ninguna dependencia directa ni
transitiva pertenezca a los paquetes prohibidos.

Validates: Requirements 9.6
"""

from __future__ import annotations

import importlib
import sys
from pathlib import Path

import pytest

# Módulos prohibidos — ningún módulo transitivo del paquete evals debe pertenecer a estos
_FORBIDDEN_PREFIXES = (
    "moviebot.routing",
    "moviebot.agents",
    "moviebot.repositories",
)

# Directorio raíz del paquete evals (relativo a la raíz del proyecto)
_EVALS_PACKAGE_DIR = Path("src/moviebot/evals")


def _collect_evals_modules() -> list[str]:
    """Descubre todos los módulos Python bajo src/moviebot/evals/ por convención."""
    modules: list[str] = []
    for py_file in sorted(_EVALS_PACKAGE_DIR.rglob("*.py")):
        # Convertir path a nombre de módulo: src/moviebot/evals/silver/models.py → moviebot.evals.silver.models
        relative = py_file.relative_to(Path("src"))
        parts = list(relative.with_suffix("").parts)
        if parts[-1] == "__init__":
            parts = parts[:-1]
        module_name = ".".join(parts)
        if module_name:
            modules.append(module_name)
    return modules


def _get_transitive_imports(root_modules: list[str]) -> set[str]:
    """Importa los módulos raíz y retorna todos los módulos que se cargaron transitivamente.

    Toma un snapshot de sys.modules antes y después para aislar las dependencias.
    """
    # Snapshot antes
    before = set(sys.modules.keys())

    for mod_name in root_modules:
        try:
            importlib.import_module(mod_name)
        except ImportError:
            pass  # skip modules that can't be imported (missing optional deps)

    # Snapshot después — los módulos nuevos son dependencias transitivas
    after = set(sys.modules.keys())
    return after - before


def test_evals_import_isolation_transitive() -> None:
    """Verify src/moviebot/evals/ has no transitive imports from forbidden modules.

    Imports all modules under moviebot.evals and inspects sys.modules to detect
    any direct or transitive dependency on moviebot.routing, moviebot.agents,
    or moviebot.repositories.
    """
    assert _EVALS_PACKAGE_DIR.exists(), f"Directory not found: {_EVALS_PACKAGE_DIR}"

    evals_modules = _collect_evals_modules()
    assert len(evals_modules) > 0, "No evals modules found"

    loaded = _get_transitive_imports(evals_modules)

    violations: list[str] = []
    for mod_name in sorted(loaded):
        for prefix in _FORBIDDEN_PREFIXES:
            if mod_name == prefix or mod_name.startswith(prefix + "."):
                violations.append(mod_name)
                break

    if violations:
        msg_lines = [
            (
                "Import isolation violated! The evals package must not import "
                "(directly or transitively) from runtime modules."
            ),
            "",
            "Forbidden modules loaded after importing moviebot.evals.*:",
        ]
        for mod_name in violations:
            msg_lines.append(f"  {mod_name}")

        pytest.fail("\n".join(msg_lines))
