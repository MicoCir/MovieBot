# Feature: source-viability-spikes, Property 6: SHA-256 Fingerprint Determinism
"""Property-based tests for SHA-256 fingerprint determinism.

Validates: Requirements 2.6

For any byte sequence, computing SHA-256 twice SHALL produce identical 64-character
hexadecimal strings, and different byte sequences SHALL produce different fingerprints
(collision resistance within test bounds).
"""

from pathlib import Path

import pytest
from hypothesis import assume, given, settings
from hypothesis import strategies as st

from spikes.common.fingerprint import compute_sha256


@pytest.mark.property
@settings(max_examples=100)
@given(data=st.binary())
def test_fingerprint_determinism(data: bytes, tmp_path_factory) -> None:
    """Two calls on the same bytes produce identical 64-char lowercase hex strings."""
    tmp_path = tmp_path_factory.mktemp("fingerprint")
    file = tmp_path / "input.bin"
    file.write_bytes(data)

    result1 = compute_sha256(file)
    result2 = compute_sha256(file)

    # Determinism: same input → same output
    assert result1 == result2

    # Format: exactly 64 lowercase hex characters
    assert len(result1) == 64
    assert result1 == result1.lower()
    assert all(c in "0123456789abcdef" for c in result1)


@pytest.mark.property
@settings(max_examples=100)
@given(data1=st.binary(min_size=1), data2=st.binary(min_size=1))
def test_different_inputs_produce_different_fingerprints(
    data1: bytes, data2: bytes, tmp_path_factory
) -> None:
    """Different byte sequences produce different fingerprints."""
    assume(data1 != data2)

    tmp_path = tmp_path_factory.mktemp("fingerprint_diff")
    file1 = tmp_path / "file1.bin"
    file2 = tmp_path / "file2.bin"
    file1.write_bytes(data1)
    file2.write_bytes(data2)

    hash1 = compute_sha256(file1)
    hash2 = compute_sha256(file2)

    assert hash1 != hash2
