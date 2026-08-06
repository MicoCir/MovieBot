"""Artifact classifier for Git eligibility determination.

Classifies artifacts as eligible or excluded for Git inclusion based on
size threshold, license type, filename patterns, and artifact type.
"""

import fnmatch
from enum import Enum
from pathlib import Path

from pydantic import BaseModel


class GitEligibility(str, Enum):
    """Git eligibility status for an artifact."""

    ELIGIBLE = "eligible"
    EXCLUDED = "excluded"


class ArtifactClassification(BaseModel):
    """Result of classifying an artifact for Git eligibility."""

    path: str
    eligibility: GitEligibility
    reason: str
    size_bytes: int | None = None


# Classification rules
MAX_GIT_SIZE_BYTES: int = 1_000_000  # 1 MB
EXCLUDED_LICENSES: set[str] = {"proprietary", "unknown", "restricted"}
ALWAYS_EXCLUDED_PATTERNS: set[str] = {"*.env", "credentials*", "*.key"}
ALWAYS_ELIGIBLE_TYPES: set[str] = {"manifest", "script", "sample", "profile", "inventory"}


def classify_artifact(
    path: Path,
    artifact_type: str,
    license_type: str | None = None,
) -> ArtifactClassification:
    """Determines if an artifact is eligible for Git inclusion.

    Classification rules (applied in order):
    1. Excluded if filename matches ALWAYS_EXCLUDED_PATTERNS (fnmatch)
    2. Excluded if license_type is in EXCLUDED_LICENSES
    3. Excluded if file size > MAX_GIT_SIZE_BYTES (checks actual file if exists)
    4. Eligible if artifact_type is in ALWAYS_ELIGIBLE_TYPES
    5. Default: eligible if no exclusion rule applies

    Args:
        path: Path to the artifact file.
        artifact_type: Type of artifact (e.g., "manifest", "script", "dataset").
        license_type: Optional license type (e.g., "proprietary", "MIT").

    Returns:
        ArtifactClassification with path, eligibility, reason, and size_bytes.
    """
    file_name = path.name
    size_bytes: int | None = None

    # Check actual file size if the file exists
    if path.exists() and path.is_file():
        size_bytes = path.stat().st_size

    # Rule 1: Always-excluded filename patterns
    for pattern in ALWAYS_EXCLUDED_PATTERNS:
        if fnmatch.fnmatch(file_name, pattern):
            return ArtifactClassification(
                path=str(path),
                eligibility=GitEligibility.EXCLUDED,
                reason=f"Matches excluded pattern: {pattern}",
                size_bytes=size_bytes,
            )

    # Rule 2: Excluded licenses
    if license_type is not None and license_type.lower() in EXCLUDED_LICENSES:
        return ArtifactClassification(
            path=str(path),
            eligibility=GitEligibility.EXCLUDED,
            reason=f"License type excluded: {license_type}",
            size_bytes=size_bytes,
        )

    # Rule 3: Size threshold
    if size_bytes is not None and size_bytes > MAX_GIT_SIZE_BYTES:
        return ArtifactClassification(
            path=str(path),
            eligibility=GitEligibility.EXCLUDED,
            reason=f"File size ({size_bytes} bytes) exceeds threshold ({MAX_GIT_SIZE_BYTES} bytes)",
            size_bytes=size_bytes,
        )

    # Rule 4: Always-eligible types
    if artifact_type.lower() in ALWAYS_ELIGIBLE_TYPES:
        return ArtifactClassification(
            path=str(path),
            eligibility=GitEligibility.ELIGIBLE,
            reason=f"Artifact type always eligible: {artifact_type}",
            size_bytes=size_bytes,
        )

    # Rule 5: Default eligible
    return ArtifactClassification(
        path=str(path),
        eligibility=GitEligibility.ELIGIBLE,
        reason="No exclusion rule applies",
        size_bytes=size_bytes,
    )
