"""Inspector programático del dataset Netflix.

Analiza los CSVs del dataset Netflix y produce un reporte
estructurado de inspección (schema, cobertura, relaciones,
clasificación de campos y estrategia de identidad).
"""

from __future__ import annotations

from moviebot.tools.inspect_netflix.inspector import NetflixInspector

__all__ = ["NetflixInspector"]
