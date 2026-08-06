"""SHA-256 fingerprint utilities for file integrity verification."""

import hashlib
from pathlib import Path


def compute_sha256(file_path: Path) -> str:
    """Computes SHA-256 hash of a file, reading in chunks for memory efficiency.

    Args:
        file_path: Path to the file to hash.

    Returns:
        Lowercase 64-character hexadecimal string representing the SHA-256 hash.
    """
    sha256 = hashlib.sha256()
    with open(file_path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            sha256.update(chunk)
    return sha256.hexdigest()
