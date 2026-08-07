"""Versioning and integrity management.

Implements content-addressable checksums, version registry, integrity verification,
and dataset card generation.
"""

from silver_dataset.versioning.checksum import compute_dataset_checksum, verify_checksum
from silver_dataset.versioning.dataset_card import generate_dataset_card
from silver_dataset.versioning.integrity import DatasetVersion, VersionRegistry

__all__ = [
    "compute_dataset_checksum",
    "verify_checksum",
    "DatasetVersion",
    "VersionRegistry",
    "generate_dataset_card",
]
