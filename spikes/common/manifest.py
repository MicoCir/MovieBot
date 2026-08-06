"""Manifest builder for the Viability Manifest.

Consolidates results from all three spikes (TMDB, Netflix, Meilisearch)
into a single structured manifest documenting sources, field inventories,
data profiles, capabilities, and artifact classifications.

Requirements validated: 4.1, 4.2, 4.3, 4.4, 4.5
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from pydantic import BaseModel

from spikes.common.artifact_classifier import (
    ArtifactClassification,
    GitEligibility,
    classify_artifact,
)
from spikes.common.models import ViabilityStatus
from spikes.meilisearch.models import MeilisearchSpikeResult
from spikes.netflix.models import DataProfile, NetflixSpikeResult
from spikes.tmdb.models import FieldEntry, TmdbSpikeResult


class SourceEntry(BaseModel):
    """Registry entry for a single data source (Req 4.1).

    Documents name, version/date, provenance, checksum, viability status,
    limitations, decisions, and blocking evidence when applicable.
    """

    name: str
    version_or_date: str
    provenance: str
    checksum: str | None
    status: ViabilityStatus
    limitations: list[str]
    decisions: list[str]
    blocking_evidence: str | None = None
    proposed_alternative: str | None = None


class ViabilityManifest(BaseModel):
    """Complete Viability Manifest consolidating all spike results.

    This manifest is the primary deliverable of E0-T4, providing
    traceability and evidence for downstream design decisions.
    """

    generated_at: datetime
    sources: list[SourceEntry]
    tmdb_field_inventory: list[FieldEntry]
    netflix_column_profile: DataProfile | None
    meilisearch_version: str
    meilisearch_confirmed_capabilities: list[str]
    meilisearch_excluded_enterprise: list[str]
    downstream_consumers: dict[str, list[str]]
    git_eligible_artifacts: list[str]
    excluded_artifacts: list[str]


# ---------------------------------------------------------------------------
# Downstream consumers map
# ---------------------------------------------------------------------------

# Maps artifact types to future sprint tasks that will consume them (Req 6.4)
DOWNSTREAM_CONSUMERS: dict[str, list[str]] = {
    "tmdb_snapshot.json": ["E1-T2", "E1-T4"],
    "tmdb_field_inventory.json": ["E1-T2", "E4"],
    "netflix_profile.json": ["E1-T2", "E1-T4"],
    "netflix_sample.csv": ["E1-T4", "E5"],
    "meilisearch_smoke.json": ["E4", "E8"],
    "viability_manifest.json": ["E1-T2", "E1-T4", "E4", "E5", "E8"],
}


# ---------------------------------------------------------------------------
# Source entry builders
# ---------------------------------------------------------------------------


def _build_tmdb_source_entry(result: TmdbSpikeResult) -> SourceEntry:
    """Build a SourceEntry from TMDB spike result (Req 4.1, 4.3, 4.5)."""
    limitations: list[str] = []
    decisions: list[str] = []
    blocking_evidence: str | None = None
    proposed_alternative: str | None = None

    if result.status == ViabilityStatus.BLOCKED:
        blocking_evidence = "; ".join(result.errors) if result.errors else "Unknown error"
        proposed_alternative = (
            "Use contractual fixture based on TMDB API documentation "
            "for development until credentials are resolved."
        )
        limitations.append("API access blocked")
    else:
        decisions.append("Endpoint validated; snapshot and field inventory generated")
        if result.field_count > 0:
            decisions.append(
                f"Field inventory contains {result.field_count} documented fields"
            )

    # Derive version/date from execution timestamp
    version_or_date = result.executed_at.strftime("%Y-%m-%d")

    return SourceEntry(
        name="TMDB API (trending/movie)",
        version_or_date=version_or_date,
        provenance=result.endpoint_used or "https://api.themoviedb.org/3/trending/movie/day",
        checksum=None,  # API responses don't have a static checksum
        status=result.status,
        limitations=limitations,
        decisions=decisions,
        blocking_evidence=blocking_evidence,
        proposed_alternative=proposed_alternative,
    )


def _build_netflix_source_entry(result: NetflixSpikeResult) -> SourceEntry:
    """Build a SourceEntry from Netflix spike result (Req 4.1, 4.3, 4.5)."""
    limitations: list[str] = []
    decisions: list[str] = []
    blocking_evidence: str | None = None
    proposed_alternative: str | None = None

    if result.status == ViabilityStatus.BLOCKED:
        blocking_evidence = "; ".join(result.errors) if result.errors else "Unknown error"
        proposed_alternative = (
            "Download dataset manually from Kaggle following documented procedure."
        )
        limitations.append("Dataset acquisition blocked")
    else:
        if result.license_info:
            decisions.append(f"License: {result.license_info[:100]}")
        if result.row_count is not None:
            decisions.append(f"Dataset contains {result.row_count} rows")
        if result.fingerprint:
            decisions.append("SHA-256 fingerprint computed for integrity verification")

    # Full CSV should not be in Git due to size
    limitations.append(
        "Full CSV excluded from Git (size); "
        "only sample and profile are committed"
    )

    version_or_date = result.executed_at.strftime("%Y-%m-%d")

    return SourceEntry(
        name="Netflix/Kaggle Dataset (shivamb/netflix-shows)",
        version_or_date=version_or_date,
        provenance="https://www.kaggle.com/datasets/shivamb/netflix-shows",
        checksum=result.fingerprint,
        status=result.status,
        limitations=limitations,
        decisions=decisions,
        blocking_evidence=blocking_evidence,
        proposed_alternative=proposed_alternative,
    )


def _build_meilisearch_source_entry(result: MeilisearchSpikeResult) -> SourceEntry:
    """Build a SourceEntry from Meilisearch spike result (Req 4.1, 4.3, 4.5)."""
    limitations: list[str] = []
    decisions: list[str] = []
    blocking_evidence: str | None = None
    proposed_alternative: str | None = None

    if result.status == ViabilityStatus.BLOCKED:
        blocking_evidence = "; ".join(result.errors) if result.errors else "Unknown error"
        proposed_alternative = (
            "Verify Docker installation and network access. "
            "Consider alternative search engine if Meilisearch CE is unavailable."
        )
        limitations.append("Meilisearch instance could not be validated")
    else:
        # Document confirmed and failed capabilities
        confirmed = [
            cap for cap, passed in result.capabilities_tested.items() if passed
        ]
        failed = [
            cap for cap, passed in result.capabilities_tested.items() if not passed
        ]

        if confirmed:
            decisions.append(f"Confirmed capabilities: {', '.join(confirmed)}")
        if failed:
            limitations.append(f"Capabilities not confirmed: {', '.join(failed)}")

        if result.enterprise_features_detected:
            limitations.append(
                f"Enterprise features detected (excluded): "
                f"{', '.join(result.enterprise_features_detected)}"
            )

    # Extract version from image tag
    version_or_date = result.image_tag.split(":")[-1] if ":" in result.image_tag else result.image_tag

    return SourceEntry(
        name="Meilisearch Community Edition",
        version_or_date=version_or_date,
        provenance=f"docker://{result.image_tag}",
        checksum=result.container_digest,
        status=result.status,
        limitations=limitations,
        decisions=decisions,
        blocking_evidence=blocking_evidence,
        proposed_alternative=proposed_alternative,
    )


# ---------------------------------------------------------------------------
# Artifact classification helpers
# ---------------------------------------------------------------------------

# Known artifacts and their types for classification
_ARTIFACT_TYPES: dict[str, str] = {
    "tmdb_snapshot.json": "manifest",
    "tmdb_field_inventory.json": "inventory",
    "netflix_profile.json": "profile",
    "netflix_sample.csv": "sample",
    "netflix_fingerprint.txt": "manifest",
    "meilisearch_smoke.json": "manifest",
    "viability_manifest.json": "manifest",
    "netflix_titles.csv": "dataset",
    "netflix_manual_procedure.txt": "manifest",
    "tmdb_blocked_fixture.json": "manifest",
}


def _classify_all_artifacts(
    tmdb_result: TmdbSpikeResult,
    netflix_result: NetflixSpikeResult,
    meilisearch_result: MeilisearchSpikeResult,
) -> tuple[list[str], list[str]]:
    """Classify all artifacts produced by the three spikes.

    Returns (git_eligible_artifacts, excluded_artifacts).
    """
    all_artifact_paths: list[str] = []
    all_artifact_paths.extend(tmdb_result.artifacts_produced)
    all_artifact_paths.extend(netflix_result.artifacts_produced)
    all_artifact_paths.extend(meilisearch_result.artifacts_produced)

    git_eligible: list[str] = []
    excluded: list[str] = []

    for artifact_path_str in all_artifact_paths:
        artifact_path = Path(artifact_path_str)
        artifact_name = artifact_path.name
        artifact_type = _ARTIFACT_TYPES.get(artifact_name, "unknown")

        classification = classify_artifact(
            path=artifact_path,
            artifact_type=artifact_type,
            license_type=None,
        )

        if classification.eligibility == GitEligibility.ELIGIBLE:
            git_eligible.append(artifact_path_str)
        else:
            excluded.append(artifact_path_str)

    # Always exclude the full Netflix CSV if it was referenced
    if netflix_result.csv_path and netflix_result.csv_path not in excluded:
        csv_path = Path(netflix_result.csv_path)
        csv_classification = classify_artifact(
            path=csv_path,
            artifact_type="dataset",
            license_type=None,
        )
        # Force exclude for the full dataset regardless of size on disk
        if netflix_result.csv_path not in excluded:
            excluded.append(netflix_result.csv_path)

    return git_eligible, excluded


# ---------------------------------------------------------------------------
# Main manifest builder
# ---------------------------------------------------------------------------


def build_manifest(
    tmdb_result: TmdbSpikeResult,
    netflix_result: NetflixSpikeResult,
    meilisearch_result: MeilisearchSpikeResult,
    tmdb_field_inventory: list[FieldEntry] | None = None,
    netflix_column_profile: DataProfile | None = None,
) -> ViabilityManifest:
    """Build the consolidated Viability Manifest from spike results.

    Consolidates all source entries, field inventories, data profiles,
    Meilisearch capabilities, downstream consumers, and artifact
    classifications into a single manifest (Req 4.1–4.5).

    Parameters
    ----------
    tmdb_result : TmdbSpikeResult
        Result from the TMDB viability spike.
    netflix_result : NetflixSpikeResult
        Result from the Netflix dataset viability spike.
    meilisearch_result : MeilisearchSpikeResult
        Result from the Meilisearch CE viability spike.
    tmdb_field_inventory : list[FieldEntry] | None
        Pre-computed field inventory from TMDB. If None, empty list is used.
    netflix_column_profile : DataProfile | None
        Pre-computed data profile from Netflix. If None, set to None in manifest.

    Returns
    -------
    ViabilityManifest
        The complete viability manifest ready for JSON serialization.
    """
    # Build source entries (Req 4.1)
    sources = [
        _build_tmdb_source_entry(tmdb_result),
        _build_netflix_source_entry(netflix_result),
        _build_meilisearch_source_entry(meilisearch_result),
    ]

    # Extract Meilisearch version from image tag (Req 4.4)
    meilisearch_version = (
        meilisearch_result.image_tag.split(":")[-1]
        if ":" in meilisearch_result.image_tag
        else meilisearch_result.image_tag
    )

    # Confirmed capabilities (Req 4.4)
    meilisearch_confirmed_capabilities = [
        cap
        for cap, passed in meilisearch_result.capabilities_tested.items()
        if passed
    ]

    # Excluded Enterprise features (Req 4.4)
    meilisearch_excluded_enterprise = list(
        meilisearch_result.enterprise_features_detected
    )

    # Classify artifacts for Git eligibility (Req 5.4)
    git_eligible_artifacts, excluded_artifacts = _classify_all_artifacts(
        tmdb_result, netflix_result, meilisearch_result
    )

    return ViabilityManifest(
        generated_at=datetime.now(timezone.utc),
        sources=sources,
        tmdb_field_inventory=tmdb_field_inventory or [],
        netflix_column_profile=netflix_column_profile,
        meilisearch_version=meilisearch_version,
        meilisearch_confirmed_capabilities=meilisearch_confirmed_capabilities,
        meilisearch_excluded_enterprise=meilisearch_excluded_enterprise,
        downstream_consumers=DOWNSTREAM_CONSUMERS,
        git_eligible_artifacts=git_eligible_artifacts,
        excluded_artifacts=excluded_artifacts,
    )


def serialize_manifest(manifest: ViabilityManifest) -> str:
    """Serialize the manifest to a JSON string with generated_at timestamp.

    Returns a pretty-printed JSON string suitable for persistence.
    """
    return manifest.model_dump_json(indent=2)


def save_manifest(
    manifest: ViabilityManifest,
    output_path: Path | None = None,
) -> Path:
    """Persist the manifest to disk as JSON.

    Parameters
    ----------
    manifest : ViabilityManifest
        The manifest to save.
    output_path : Path | None
        Where to save. Defaults to spikes/artifacts/viability_manifest.json.

    Returns
    -------
    Path
        The path where the manifest was saved.
    """
    if output_path is None:
        output_path = Path("spikes/artifacts/viability_manifest.json")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(serialize_manifest(manifest), encoding="utf-8")
    return output_path
