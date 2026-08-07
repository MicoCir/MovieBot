"""Property test for fixture write atomicity (Property 6).

**Validates: Requirements 2.8, 3.15**

Verifies that if a failure occurs at any point during the fixture write process,
no partial files remain on disk. The fixture write is all-or-nothing.
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from moviebot.repositories.fixture_writer import TmpDirFixtureWriter

# Strategy: generate random payload and metadata bytes
payload_bytes = st.binary(min_size=1, max_size=1024)
metadata_bytes = st.binary(min_size=1, max_size=512)

# Strategy: failure injection point (which os.rename call to fail on)
# 0 = fail on first rename (payload), 1 = fail on second rename (metadata)
failure_point = st.integers(min_value=0, max_value=1)

# Strategy: safe version strings
version_strategy = st.from_regex(r"[a-zA-Z0-9_-]{1,20}", fullmatch=True)


@given(
    payload=payload_bytes,
    metadata=metadata_bytes,
    fail_at=failure_point,
    version=version_strategy,
)
@settings(max_examples=100, deadline=None)
def test_atomicity_no_partial_files_on_failure(
    payload: bytes,
    metadata: bytes,
    fail_at: int,
    version: str,
) -> None:
    """Property 6: If write_fixture fails at any point, no fixture files remain.

    **Validates: Requirements 2.8, 3.15**

    We inject an OSError at the Nth os.rename call to simulate failure at
    different stages of the atomic write process. After the failure, the
    target directory must contain NO files matching the fixture name pattern.
    """
    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_path = Path(tmp_dir)
        writer = TmpDirFixtureWriter(tmp_dir=tmp_path)

        # Track how many rename calls have succeeded
        call_count = 0
        original_rename = os.rename

        def failing_rename(src: str, dst: str) -> None:
            nonlocal call_count
            if call_count == fail_at:
                raise OSError(f"Simulated failure at rename call {call_count}")
            call_count += 1
            original_rename(src, dst)

        with patch("os.rename", side_effect=failing_rename), pytest.raises(OSError):
            writer.write_fixture(version, payload, metadata)

        # After the failure, verify no fixture files remain
        payload_name = f"trending_movies_{version}.json"
        metadata_name = f"trending_movies_{version}.metadata.json"

        remaining_files = list(tmp_path.iterdir())
        fixture_files = [
            f
            for f in remaining_files
            if f.name == payload_name or f.name == metadata_name
        ]

        assert fixture_files == [], (
            f"Partial fixture files remain after failure at rename call {fail_at}: "
            f"{[f.name for f in fixture_files]}"
        )

        # Also verify no temp files remain
        temp_files = [f for f in remaining_files if f.name.startswith(".tmp_")]
        assert temp_files == [], (
            f"Temporary files remain after failure: {[f.name for f in temp_files]}"
        )
