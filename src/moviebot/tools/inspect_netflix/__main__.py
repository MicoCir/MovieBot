"""Punto de entrada CLI: python -m moviebot.tools.inspect_netflix.

Ejecuta la inspección del dataset Netflix y emite el reporte
en formato JSON (default) o texto legible.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from moviebot.tools.inspect_netflix.inspector import NetflixInspector


def _sort_for_determinism(obj: Any) -> Any:
    """Recursively sort dicts by key and primitive lists for deterministic output.

    - Dicts: sorted by key
    - Lists of strings: sorted alphabetically
    - Lists of numbers: sorted ascending
    - Lists of dicts or mixed: preserved in original order (structural)
    """
    if isinstance(obj, dict):
        return {k: _sort_for_determinism(v) for k, v in sorted(obj.items())}
    if isinstance(obj, list):
        processed = [_sort_for_determinism(item) for item in obj]
        # Sort homogeneous primitive lists
        if processed and all(isinstance(x, str) for x in processed):
            return sorted(processed)
        if processed and all(
            isinstance(x, (int, float)) and not isinstance(x, bool) for x in processed
        ):
            return sorted(processed)
        return processed
    return obj


def _format_text(report_dict: dict[str, Any]) -> str:
    """Produce una representación legible por humanos del reporte."""
    lines: list[str] = []
    lines.append("=" * 60)
    lines.append("Netflix Dataset Inspection Report")
    lines.append("=" * 60)

    # Schemas
    for schema in report_dict.get("schemas", []):
        lines.append(f"\n--- Schema: {schema['filename']} ---")
        lines.append(f"  Rows: {schema['row_count']}")
        lines.append(f"  Columns: {len(schema['columns'])}")
        for col in schema["columns"]:
            lines.append(
                f"    {col['name']}: {col['inferred_type']} "
                f"(nulls={col['null_count']}, unique={col['unique_count']})"
            )

    # Type distribution
    type_dist = report_dict.get("type_distribution", {})
    lines.append("\n--- Type Distribution ---")
    for k, v in sorted(type_dist.get("counts", {}).items()):
        lines.append(f"  {k}: {v}")
    lines.append(f"  null_or_unrecognized: {type_dist.get('null_or_unrecognized', 0)}")

    # Coverage
    coverage = report_dict.get("coverage", {})
    lines.append("\n--- Coverage ---")
    for subset_name in ("all_titles", "movies_only", "shows_only"):
        subset = coverage.get(subset_name, [])
        if subset:
            lines.append(f"\n  [{subset_name}]")
            for entry in subset:
                field = entry.get("field", "?")
                pct = entry.get("pct_non_null", 0)
                unique = entry.get("unique_count", 0)
                lines.append(f"    {field}: {pct:.2f}% non-null, {unique} unique")

    # Genre stats
    genre_stats = report_dict.get("genre_stats", {})
    lines.append("\n--- Genre Stats ---")
    unique_genres = genre_stats.get("unique_genres", [])
    lines.append(f"  Unique genres: {len(unique_genres)}")
    lines.append(
        f"  Titles with null/empty genres: "
        f"{genre_stats.get('titles_null_or_empty_genres', 0)}"
    )
    lines.append(f"  Unparseable: {genre_stats.get('unparseable_count', 0)}")

    # Credit stats
    credit_stats = report_dict.get("credit_stats", {})
    lines.append("\n--- Credit Stats ---")
    for subset_name in ("all_titles", "movies_only", "shows_only"):
        subset = credit_stats.get(subset_name)
        if subset:
            lines.append(f"\n  [{subset_name}]")
            rpr = subset.get("records_per_role", {})
            for role, count in sorted(rpr.items()):
                lines.append(f"    {role}: {count} records")
            lines.append(
                f"    avg_actors_per_title: {subset.get('avg_actors_per_title', 0)}"
            )
            lines.append(
                f"    avg_directors_per_title: "
                f"{subset.get('avg_directors_per_title', 0)}"
            )

    # Credit coverage
    credit_cov = report_dict.get("credit_coverage", {})
    lines.append("\n--- Credit Coverage ---")
    for subset_name in ("all_titles", "movies_only", "shows_only"):
        subset = credit_cov.get(subset_name)
        if subset:
            lines.append(f"\n  [{subset_name}]")
            lines.append(f"    with actors: {subset.get('pct_with_actors', 0):.2f}%")
            lines.append(
                f"    with directors: {subset.get('pct_with_directors', 0):.2f}%"
            )
            lines.append(f"    with both: {subset.get('pct_with_both', 0):.2f}%")

    # Relationships
    rels = report_dict.get("relationships", {})
    lines.append("\n--- Relationships ---")
    for key in (
        "titles_to_credits_1n",
        "titles_to_persons_mn_titles_per_person",
        "titles_to_persons_mn_persons_per_title",
    ):
        card = rels.get(key, {})
        lines.append(
            f"  {key}: min={card.get('min_value', 0)}, "
            f"max={card.get('max_value', 0)}, avg={card.get('avg_value', 0)}"
        )
    lines.append(f"  titles_without_credits: {rels.get('titles_without_credits', 0)}")
    lines.append(f"  credits_without_title: {rels.get('credits_without_title', 0)}")

    # Field classifications
    lines.append("\n--- Field Classifications ---")
    for fc in report_dict.get("field_classifications", []):
        lines.append(
            f"  {fc['field']}: {fc['category']} "
            f"(coverage={fc['coverage_pct']:.2f}%) - {fc.get('reason', '')}"
        )

    # Identity strategy
    identity = report_dict.get("identity_strategy", {})
    lines.append("\n--- Identity Strategy ---")
    lines.append(f"  Netflix: {identity.get('netflix_format', '')}")
    lines.append(f"  TMDB: {identity.get('tmdb_format', '')}")
    lines.append(f"  Cross-source: {identity.get('cross_source', '')}")

    # Observations
    observations = report_dict.get("observations", [])
    if observations:
        lines.append("\n--- Observations ---")
        for obs in observations:
            lines.append(f"  - {obs}")

    # Genre incompatibility note
    note = report_dict.get("genre_incompatibility_note", "")
    if note:
        lines.append("\n--- Genre Incompatibility Note ---")
        lines.append(f"  {note}")

    lines.append("")
    return "\n".join(lines)


def main() -> None:
    """Punto de entrada principal del CLI."""
    parser = argparse.ArgumentParser(description="Inspección del dataset Netflix")
    parser.add_argument(
        "--titles",
        type=Path,
        default=Path("raw_data/netflix/titles.csv"),
        help="Ruta al archivo titles.csv",
    )
    parser.add_argument(
        "--credits",
        type=Path,
        default=Path("raw_data/netflix/credits.csv"),
        help="Ruta al archivo credits.csv",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Ruta de salida para el reporte (crea directorio si no existe)",
    )
    parser.add_argument(
        "--format",
        choices=["json", "text"],
        default="json",
        dest="output_format",
        help="Formato de salida: json (default) o text",
    )
    args = parser.parse_args()

    # Verificar existencia de archivos de entrada
    for path in [args.titles, args.credits]:
        if not path.is_file():
            print(
                f"Error: archivo no encontrado: {path}",
                file=sys.stderr,
            )
            sys.exit(1)

    inspector = NetflixInspector(titles_path=args.titles, credits_path=args.credits)
    report = inspector.run()

    # Serializar reporte
    report_dict = report.model_dump()

    if args.output_format == "json":
        # JSON determinista: claves ordenadas, listas primitivas ordenadas
        sorted_dict = _sort_for_determinism(report_dict)
        output_str = json.dumps(
            sorted_dict, ensure_ascii=False, indent=2, sort_keys=True
        )
    else:
        output_str = _format_text(report_dict)

    # Emitir resultado
    if args.output is not None:
        # Crear directorio destino si no existe
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(output_str, encoding="utf-8")
    else:
        print(output_str)

    sys.exit(0)


if __name__ == "__main__":
    main()
