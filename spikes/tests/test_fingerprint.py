"""Unit tests for the fingerprint utility."""

import hashlib
from pathlib import Path

import pytest

from spikes.common.fingerprint import compute_sha256


class TestComputeSha256:
    """Tests for compute_sha256 function."""

    def test_known_content_hash(self, tmp_path: Path):
        """SHA-256 of known content matches expected value."""
        file = tmp_path / "hello.txt"
        file.write_bytes(b"hello world")
        expected = hashlib.sha256(b"hello world").hexdigest()
        assert compute_sha256(file) == expected

    def test_returns_lowercase_hex_string(self, tmp_path: Path):
        """Result is a lowercase 64-character hexadecimal string."""
        file = tmp_path / "data.bin"
        file.write_bytes(b"\x00\xff\xab\xcd")
        result = compute_sha256(file)
        assert len(result) == 64
        assert result == result.lower()
        assert all(c in "0123456789abcdef" for c in result)

    def test_empty_file(self, tmp_path: Path):
        """SHA-256 of an empty file matches the known empty hash."""
        file = tmp_path / "empty.bin"
        file.write_bytes(b"")
        expected = hashlib.sha256(b"").hexdigest()
        assert compute_sha256(file) == expected

    def test_deterministic_across_calls(self, tmp_path: Path):
        """Calling compute_sha256 twice on the same file yields the same result."""
        file = tmp_path / "repeat.bin"
        file.write_bytes(b"deterministic content")
        assert compute_sha256(file) == compute_sha256(file)

    def test_large_file_chunked_reading(self, tmp_path: Path):
        """Files larger than one chunk (8192 bytes) are hashed correctly."""
        content = b"A" * 20000  # ~2.5 chunks
        file = tmp_path / "large.bin"
        file.write_bytes(content)
        expected = hashlib.sha256(content).hexdigest()
        assert compute_sha256(file) == expected

    def test_different_content_produces_different_hash(self, tmp_path: Path):
        """Different file contents yield different fingerprints."""
        file_a = tmp_path / "a.bin"
        file_b = tmp_path / "b.bin"
        file_a.write_bytes(b"content A")
        file_b.write_bytes(b"content B")
        assert compute_sha256(file_a) != compute_sha256(file_b)

    def test_file_not_found_raises(self, tmp_path: Path):
        """Raises an appropriate error for non-existent file."""
        missing = tmp_path / "nonexistent.bin"
        with pytest.raises((FileNotFoundError, OSError)):
            compute_sha256(missing)
