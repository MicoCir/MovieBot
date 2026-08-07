"""Content-addressable checksums for dataset integrity verification.

Provides deterministic SHA-256 computation over sorted canonical JSON
representations of SilverCase instances, ensuring that:
- Identical content always produces the same hash (determinism)
- Any modification to any case changes the hash (sensitivity)
- Order of input cases does not affect the result (order-independence)
"""

import hashlib

from silver_dataset.models.case import SilverCase


def compute_dataset_checksum(cases: list[SilverCase]) -> str:
    """Compute deterministic SHA-256 over sorted, canonical JSON of all cases.

    Sort by model_dump_json() to ensure deterministic ordering regardless
    of input order. Then compute SHA-256 over the concatenated lines.

    Args:
        cases: List of SilverCase instances to checksum.

    Returns:
        Hex-encoded SHA-256 hash string.
    """
    lines = sorted(case.model_dump_json() for case in cases)
    payload = "\n".join(lines).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def verify_checksum(cases: list[SilverCase], expected: str) -> bool:
    """Verify dataset integrity against stored checksum.

    Args:
        cases: List of SilverCase instances to verify.
        expected: Expected hex-encoded SHA-256 hash string.

    Returns:
        True if computed checksum matches expected, False otherwise.
    """
    return compute_dataset_checksum(cases) == expected
