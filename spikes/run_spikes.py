"""CLI entry point for running all viability spikes.

Executes each spike independently (TMDB, Netflix, Meilisearch), collects
results, builds the consolidated Viability Manifest, classifies artifacts
for Git eligibility, and optionally updates .gitignore.

Requirements validated: 4.1, 5.4, 6.1, 6.2, 6.3, 6.4
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from spikes.common.artifact_classifier import (
    GitEligibility,
    classify_artifact,
)
from spikes.common.manifest import build_manifest, save_manifest
from spikes.common.models import ViabilityStatus
from spikes.meilisearch.models import MeilisearchSpikeResult
from spikes.netflix.models import DataProfile, NetflixSpikeResult
from spikes.tmdb.models import FieldEntry, TmdbSpikeResult

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

ARTIFACTS_DIR = Path("spikes/artifacts")
GITIGNORE_PATH = Path(".gitignore")

# Marker comments for the .gitignore section managed by this script
GITIGNORE_START_MARKER = "# --- Spike excluded artifacts (auto-generated) ---"
GITIGNORE_END_MARKER = "# --- End spike excluded artifacts ---"


# ---------------------------------------------------------------------------
# Spike runners (each wrapped in try/except for isolation)
# ---------------------------------------------------------------------------


def _run_tmdb_spike() -> TmdbSpikeResult | None:
    """Execute the TMDB spike. Returns None on unexpected failure."""
    try:
        from spikes.tmdb.spike_tmdb import run_spike

        print("[TMDB] Starting spike...")
        result = run_spike(time_window="day")
        print(f"[TMDB] Completed — status: {result.status.value}")
        return result
    except Exception as e:
        print(f"[TMDB] FAILED with exception: {e}")
        return None


def _run_netflix_spike(
    csv_path: str | None = None,
) -> NetflixSpikeResult | None:
    """Execute the Netflix spike. Returns None on unexpected failure."""
    try:
        from spikes.netflix.spike_netflix import run_netflix_spike

        print("[Netflix] Starting spike...")
        path_arg = Path(csv_path) if csv_path else None
        result = run_netflix_spike(csv_path=path_arg, artifacts_dir=ARTIFACTS_DIR)
        print(f"[Netflix] Completed — status: {result.status.value}")
        return result
    except Exception as e:
        print(f"[Netflix] FAILED with exception: {e}")
        return None


def _run_meilisearch_spike() -> MeilisearchSpikeResult | None:
    """Execute the Meilisearch spike. Returns None on unexpected failure."""
    try:
        from spikes.meilisearch.spike_meilisearch import run_meilisearch_spike

        print("[Meilisearch] Starting spike...")
        result = run_meilisearch_spike(artifacts_dir=ARTIFACTS_DIR)
        print(f"[Meilisearch] Completed — status: {result.status.value}")
        return result
    except Exception as e:
        print(f"[Meilisearch] FAILED with exception: {e}")
        return None


# ---------------------------------------------------------------------------
# Fallback result builders (for spikes that crash unexpectedly)
# ---------------------------------------------------------------------------


def _fallback_tmdb_result(error_msg: str) -> TmdbSpikeResult:
    """Create a BLOCKED TmdbSpikeResult when the spike crashes."""
    return TmdbSpikeResult(
        spike_name="tmdb",
        executed_at=datetime.now(timezone.utc),
        status=ViabilityStatus.BLOCKED,
        duration_seconds=0.0,
        artifacts_produced=[],
        errors=[f"Spike crashed: {error_msg}"],
        endpoint_used="",
        response_code=None,
        field_count=0,
        snapshot_path=None,
    )


def _fallback_netflix_result(error_msg: str) -> NetflixSpikeResult:
    """Create a BLOCKED NetflixSpikeResult when the spike crashes."""
    return NetflixSpikeResult(
        spike_name="netflix",
        executed_at=datetime.now(timezone.utc),
        status=ViabilityStatus.BLOCKED,
        duration_seconds=0.0,
        artifacts_produced=[],
        errors=[f"Spike crashed: {error_msg}"],
        csv_path=None,
        row_count=None,
        column_count=None,
        fingerprint=None,
        sample_path=None,
        license_info="Unknown (spike failed)",
    )


def _fallback_meilisearch_result(error_msg: str) -> MeilisearchSpikeResult:
    """Create a BLOCKED MeilisearchSpikeResult when the spike crashes."""
    return MeilisearchSpikeResult(
        spike_name="meilisearch",
        executed_at=datetime.now(timezone.utc),
        status=ViabilityStatus.BLOCKED,
        duration_seconds=0.0,
        artifacts_produced=[],
        errors=[f"Spike crashed: {error_msg}"],
        image_tag="unknown",
        container_digest=None,
        healthcheck_passed=False,
        capabilities_tested={},
        enterprise_features_detected=[],
    )


# ---------------------------------------------------------------------------
# Field inventory and profile loading helpers
# ---------------------------------------------------------------------------


def _load_field_inventory() -> list[FieldEntry]:
    """Load field inventory from the TMDB snapshot artifact if available."""
    snapshot_path = ARTIFACTS_DIR / "tmdb_snapshot.json"
    if not snapshot_path.exists():
        return []

    try:
        from spikes.tmdb.spike_tmdb import generate_field_inventory

        payload = json.loads(snapshot_path.read_text(encoding="utf-8"))
        return generate_field_inventory(payload)
    except Exception:
        return []


def _load_netflix_profile() -> DataProfile | None:
    """Load the Netflix profile from artifacts if available."""
    profile_path = ARTIFACTS_DIR / "netflix_profile.json"
    if not profile_path.exists():
        return None

    try:
        data = json.loads(profile_path.read_text(encoding="utf-8"))
        return DataProfile(**data)
    except Exception:
        return None


# ---------------------------------------------------------------------------
# .gitignore update logic
# ---------------------------------------------------------------------------


def _update_gitignore(excluded_artifacts: list[str]) -> None:
    """Update .gitignore with excluded artifact paths.

    Adds or replaces a managed section between start/end markers.
    Only adds paths that aren't already covered by existing patterns.
    """
    if not excluded_artifacts:
        return

    # Build the new section content
    new_lines: list[str] = [GITIGNORE_START_MARKER]
    for artifact_path in sorted(set(excluded_artifacts)):
        # Normalize to forward slashes for .gitignore compatibility
        normalized = artifact_path.replace("\\", "/")
        new_lines.append(normalized)
    new_lines.append(GITIGNORE_END_MARKER)
    new_section = "\n".join(new_lines) + "\n"

    # Read existing .gitignore content
    if GITIGNORE_PATH.exists():
        existing_content = GITIGNORE_PATH.read_text(encoding="utf-8")
    else:
        existing_content = ""

    # Remove any existing managed section
    start_idx = existing_content.find(GITIGNORE_START_MARKER)
    end_idx = existing_content.find(GITIGNORE_END_MARKER)

    if start_idx != -1 and end_idx != -1:
        # Replace existing section
        end_idx += len(GITIGNORE_END_MARKER)
        # Include trailing newline if present
        if end_idx < len(existing_content) and existing_content[end_idx] == "\n":
            end_idx += 1
        updated_content = existing_content[:start_idx] + new_section + existing_content[end_idx:]
    else:
        # Append new section
        if existing_content and not existing_content.endswith("\n"):
            existing_content += "\n"
        updated_content = existing_content + "\n" + new_section

    GITIGNORE_PATH.write_text(updated_content, encoding="utf-8")
    print(f"[GitIgnore] Updated {GITIGNORE_PATH} with {len(excluded_artifacts)} excluded artifact(s)")


# ---------------------------------------------------------------------------
# Summary printer
# ---------------------------------------------------------------------------


def _print_summary(
    tmdb_result: TmdbSpikeResult,
    netflix_result: NetflixSpikeResult,
    meilisearch_result: MeilisearchSpikeResult,
    manifest_path: Path,
    total_duration: float,
) -> None:
    """Print a human-readable summary of all spike results."""
    print()
    print("=" * 70)
    print("  VIABILITY SPIKES — SUMMARY")
    print("=" * 70)
    print()

    # Status overview
    results = [
        ("TMDB", tmdb_result.status, tmdb_result.duration_seconds),
        ("Netflix", netflix_result.status, netflix_result.duration_seconds),
        ("Meilisearch", meilisearch_result.status, meilisearch_result.duration_seconds),
    ]

    for name, status, duration in results:
        icon = "✓" if status == ViabilityStatus.CONFIRMED else "✗"
        print(f"  {icon} {name:<15} {status.value:<12} ({duration:.1f}s)")

    print()
    print(f"  Total duration: {total_duration:.1f}s")
    print(f"  Manifest: {manifest_path}")
    print()

    # Errors summary
    all_errors: list[tuple[str, str]] = []
    for name, result in [("TMDB", tmdb_result), ("Netflix", netflix_result), ("Meilisearch", meilisearch_result)]:
        for err in result.errors:
            all_errors.append((name, err))

    if all_errors:
        print("  Errors/Limitations:")
        for name, err in all_errors:
            print(f"    [{name}] {err[:120]}")
        print()

    # Final verdict
    all_confirmed = all(
        r.status == ViabilityStatus.CONFIRMED
        for r in [tmdb_result, netflix_result, meilisearch_result]
    )
    if all_confirmed:
        print("  VERDICT: All sources confirmed viable ✓")
    else:
        blocked = [name for name, status, _ in results if status == ViabilityStatus.BLOCKED]
        print(f"  VERDICT: Blocked sources: {', '.join(blocked)}")
        print("  Check the manifest for blocking evidence and proposed alternatives.")

    print()
    print("=" * 70)


# ---------------------------------------------------------------------------
# Main CLI entry point
# ---------------------------------------------------------------------------


def main() -> int:
    """Run all viability spikes and produce the consolidated manifest.

    Returns 0 if all spikes confirmed, 1 if any are blocked.
    """
    parser = argparse.ArgumentParser(
        description="Run all MovieBot viability spikes and produce the Viability Manifest.",
    )
    parser.add_argument(
        "--netflix-csv",
        type=str,
        default=None,
        help="Explicit path to the Netflix CSV file (optional).",
    )
    parser.add_argument(
        "--skip-gitignore",
        action="store_true",
        help="Skip updating .gitignore with excluded artifacts.",
    )
    parser.add_argument(
        "--artifacts-dir",
        type=str,
        default=None,
        help="Override the artifacts output directory.",
    )
    args = parser.parse_args()

    # Configure artifacts dir
    global ARTIFACTS_DIR
    if args.artifacts_dir:
        ARTIFACTS_DIR = Path(args.artifacts_dir)
    ARTIFACTS_DIR.mkdir(parents=True, exist_ok=True)

    start_time = time.time()

    print()
    print("=" * 70)
    print("  MovieBot Viability Spikes — CLI Runner")
    print("=" * 70)
    print()

    # -------------------------------------------------------------------
    # Execute each spike independently (Req 6.1, 6.2, 6.3)
    # Failure of one does NOT block the others.
    # -------------------------------------------------------------------

    tmdb_result_or_none = _run_tmdb_spike()
    print()

    netflix_result_or_none = _run_netflix_spike(csv_path=args.netflix_csv)
    print()

    meilisearch_result_or_none = _run_meilisearch_spike()
    print()

    # -------------------------------------------------------------------
    # Build fallback results for any crashed spike
    # -------------------------------------------------------------------

    tmdb_result: TmdbSpikeResult = (
        tmdb_result_or_none
        if tmdb_result_or_none is not None
        else _fallback_tmdb_result("Spike raised an unhandled exception")
    )

    netflix_result: NetflixSpikeResult = (
        netflix_result_or_none
        if netflix_result_or_none is not None
        else _fallback_netflix_result("Spike raised an unhandled exception")
    )

    meilisearch_result: MeilisearchSpikeResult = (
        meilisearch_result_or_none
        if meilisearch_result_or_none is not None
        else _fallback_meilisearch_result("Spike raised an unhandled exception")
    )

    # -------------------------------------------------------------------
    # Load supplementary data for manifest (if spikes succeeded)
    # -------------------------------------------------------------------

    # If TMDB succeeded, load the snapshot and generate field inventory
    tmdb_field_inventory: list[FieldEntry] = []
    if tmdb_result.status == ViabilityStatus.CONFIRMED:
        tmdb_field_inventory = _load_field_inventory()

    # If Netflix succeeded, load the profile
    netflix_profile: DataProfile | None = None
    if netflix_result.status == ViabilityStatus.CONFIRMED:
        netflix_profile = _load_netflix_profile()

    # -------------------------------------------------------------------
    # Build manifest (Req 4.1)
    # -------------------------------------------------------------------

    print("[Manifest] Building viability manifest...")
    manifest = build_manifest(
        tmdb_result=tmdb_result,
        netflix_result=netflix_result,
        meilisearch_result=meilisearch_result,
        tmdb_field_inventory=tmdb_field_inventory,
        netflix_column_profile=netflix_profile,
    )

    # Save manifest (Req 4.1)
    manifest_path = save_manifest(
        manifest,
        output_path=ARTIFACTS_DIR / "viability_manifest.json",
    )
    print(f"[Manifest] Saved to: {manifest_path}")

    # -------------------------------------------------------------------
    # Classify artifacts for Git eligibility (Req 5.4)
    # -------------------------------------------------------------------

    print("[Artifacts] Classifying artifacts for Git eligibility...")
    excluded_artifacts = manifest.excluded_artifacts

    # -------------------------------------------------------------------
    # Update .gitignore with excluded artifacts (Req 5.4)
    # -------------------------------------------------------------------

    if not args.skip_gitignore and excluded_artifacts:
        _update_gitignore(excluded_artifacts)
    elif excluded_artifacts:
        print(f"[GitIgnore] Skipped (--skip-gitignore). {len(excluded_artifacts)} artifact(s) excluded.")

    # -------------------------------------------------------------------
    # Print summary to stdout
    # -------------------------------------------------------------------

    total_duration = time.time() - start_time
    _print_summary(
        tmdb_result=tmdb_result,
        netflix_result=netflix_result,
        meilisearch_result=meilisearch_result,
        manifest_path=manifest_path,
        total_duration=total_duration,
    )

    # Return exit code based on overall status
    all_confirmed = all(
        r.status == ViabilityStatus.CONFIRMED
        for r in [tmdb_result, netflix_result, meilisearch_result]
    )
    return 0 if all_confirmed else 1


if __name__ == "__main__":
    sys.exit(main())
