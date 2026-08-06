"""Netflix/Kaggle dataset viability spike.

Acquires the Netflix Shows dataset from Kaggle (shivamb/netflix-shows),
profiles it, computes a SHA-256 fingerprint, extracts a minimal sample,
and persists all artifacts for downstream consumption.

Requirements validated: 2.1, 2.2, 2.3, 2.4, 2.5, 2.6
"""

from __future__ import annotations

import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path

from spikes.common.fingerprint import compute_sha256
from spikes.common.models import ViabilityStatus
from spikes.netflix.models import DataProfile, NetflixSpikeResult
from spikes.netflix.profiler import extract_minimal_sample, profile_dataset

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

KAGGLE_DATASET = "shivamb/netflix-shows"
EXPECTED_CSV_NAME = "netflix_titles.csv"
DEFAULT_CSV_PATH = Path("spikes/netflix/netflix_titles.csv")
ARTIFACTS_DIR = Path("spikes/artifacts")

LICENSE_INFO = (
    "Dataset: Netflix Movies and TV Shows (shivamb/netflix-shows on Kaggle). "
    "License: CC0 1.0 Universal (Public Domain Dedication). "
    "Attribution: Shivam Bansal. "
    "Redistribution: Permitted without restriction under CC0. "
    "The full dataset CSV should not be committed to Git due to size; "
    "only the minimal sample and profile are stored in artifacts/."
)

MANUAL_DOWNLOAD_PROCEDURE = (
    "Manual download procedure for Netflix dataset:\n"
    "1. Visit https://www.kaggle.com/datasets/shivamb/netflix-shows\n"
    "2. Click 'Download' (requires free Kaggle account)\n"
    "3. Extract the ZIP file\n"
    "4. Place 'netflix_titles.csv' at: spikes/netflix/netflix_titles.csv\n"
    "5. Re-run this spike script\n"
    "\n"
    "Alternatively, configure Kaggle API credentials:\n"
    "  - Set environment variables KAGGLE_USERNAME and KAGGLE_KEY\n"
    "  - Or place kaggle.json in ~/.kaggle/kaggle.json\n"
    "  - Then re-run this spike for automatic download."
)


# ---------------------------------------------------------------------------
# Kaggle download helpers
# ---------------------------------------------------------------------------


def _kaggle_credentials_available() -> bool:
    """Check if Kaggle API credentials are configured."""
    # Check environment variables
    if os.environ.get("KAGGLE_USERNAME") and os.environ.get("KAGGLE_KEY"):
        return True
    # Check kaggle.json file
    kaggle_json = Path.home() / ".kaggle" / "kaggle.json"
    return kaggle_json.exists()


def _download_from_kaggle(destination_dir: Path) -> Path | None:
    """Attempt to download the Netflix dataset via the Kaggle API.

    Returns the path to the downloaded CSV on success, or None on failure.
    """
    try:
        from kaggle.api.kaggle_api_extended import KaggleApi  # type: ignore[import-untyped]

        api = KaggleApi()
        api.authenticate()

        # Download and unzip into the destination directory
        destination_dir.mkdir(parents=True, exist_ok=True)
        api.dataset_download_files(
            KAGGLE_DATASET,
            path=str(destination_dir),
            unzip=True,
        )

        csv_path = destination_dir / EXPECTED_CSV_NAME
        if csv_path.exists():
            return csv_path
        return None

    except Exception:
        return None


# ---------------------------------------------------------------------------
# CSV reading with encoding fallback
# ---------------------------------------------------------------------------


def _try_read_csv(csv_path: Path) -> tuple[bool, str]:
    """Validate that the CSV can be read. Tries UTF-8 first, then Latin-1.

    Returns a tuple (success, encoding_used_or_error_message).
    """
    import pandas as pd

    # Try UTF-8 first
    try:
        df = pd.read_csv(csv_path, encoding="utf-8", nrows=5)
        if len(df) == 0:
            return False, "CSV file is empty (0 rows)"
        return True, "utf-8"
    except UnicodeDecodeError:
        pass
    except Exception as e:
        # Could be a completely broken file
        return False, f"Error reading CSV: {e}"

    # Fallback to Latin-1
    try:
        df = pd.read_csv(csv_path, encoding="latin-1", nrows=5)
        if len(df) == 0:
            return False, "CSV file is empty (0 rows)"
        return True, "latin-1"
    except Exception as e:
        return False, f"Error reading CSV with latin-1 fallback: {e}"


# ---------------------------------------------------------------------------
# Main spike execution
# ---------------------------------------------------------------------------


def run_netflix_spike(
    csv_path: Path | None = None,
    artifacts_dir: Path | None = None,
) -> NetflixSpikeResult:
    """Execute the Netflix dataset viability spike.

    Parameters
    ----------
    csv_path : Path | None
        Explicit path to the Netflix CSV. If None, attempts Kaggle download
        or falls back to the default location.
    artifacts_dir : Path | None
        Directory where artifacts are persisted. Defaults to spikes/artifacts/.

    Returns
    -------
    NetflixSpikeResult
        Complete result of the spike execution including profile, fingerprint,
        and sample information.
    """
    start_time = time.time()
    errors: list[str] = []
    artifacts_produced: list[str] = []

    if artifacts_dir is None:
        artifacts_dir = ARTIFACTS_DIR
    artifacts_dir.mkdir(parents=True, exist_ok=True)

    resolved_csv_path: Path | None = csv_path

    # -----------------------------------------------------------------------
    # Step 1: Acquire dataset (Req 2.1, 2.2)
    # -----------------------------------------------------------------------
    kaggle_download_attempted = False
    manual_procedure_documented = False

    if resolved_csv_path is None:
        # Check if CSV already exists at default location
        if DEFAULT_CSV_PATH.exists():
            resolved_csv_path = DEFAULT_CSV_PATH
        else:
            # Try Kaggle API download
            if _kaggle_credentials_available():
                kaggle_download_attempted = True
                downloaded = _download_from_kaggle(DEFAULT_CSV_PATH.parent)
                if downloaded is not None:
                    resolved_csv_path = downloaded
                else:
                    errors.append(
                        "Kaggle API download failed. "
                        "Manual procedure documented."
                    )
                    manual_procedure_documented = True
            else:
                errors.append(
                    "Kaggle credentials not found. "
                    "Manual procedure documented."
                )
                manual_procedure_documented = True

    # If we still don't have a CSV, return with manual procedure documented
    if resolved_csv_path is None or not resolved_csv_path.exists():
        duration = time.time() - start_time
        result = NetflixSpikeResult(
            spike_name="netflix",
            executed_at=datetime.now(timezone.utc),
            status=ViabilityStatus.CONFIRMED,
            duration_seconds=round(duration, 2),
            artifacts_produced=artifacts_produced,
            errors=errors,
            csv_path=None,
            row_count=None,
            column_count=None,
            fingerprint=None,
            sample_path=None,
            license_info=LICENSE_INFO,
        )

        # Persist the manual procedure as an artifact
        if manual_procedure_documented:
            procedure_path = artifacts_dir / "netflix_manual_procedure.txt"
            procedure_path.write_text(MANUAL_DOWNLOAD_PROCEDURE, encoding="utf-8")
            result.artifacts_produced.append(str(procedure_path))

        # Persist partial result JSON
        _persist_result_json(result, artifacts_dir)
        return result

    # -----------------------------------------------------------------------
    # Step 2: Validate CSV readability (encoding fallback)
    # -----------------------------------------------------------------------
    readable, encoding_or_error = _try_read_csv(resolved_csv_path)

    if not readable:
        duration = time.time() - start_time
        if "empty" in encoding_or_error.lower():
            # CSV vacío → status=blocked
            errors.append(f"CSV is empty or unreadable: {encoding_or_error}")
            result = NetflixSpikeResult(
                spike_name="netflix",
                executed_at=datetime.now(timezone.utc),
                status=ViabilityStatus.BLOCKED,
                duration_seconds=round(duration, 2),
                artifacts_produced=artifacts_produced,
                errors=errors,
                csv_path=str(resolved_csv_path),
                row_count=0,
                column_count=None,
                fingerprint=None,
                sample_path=None,
                license_info=LICENSE_INFO,
            )
            _persist_result_json(result, artifacts_dir)
            return result
        else:
            # CSV corrupto and both encodings failed
            errors.append(f"CSV corrupt/unreadable: {encoding_or_error}")
            result = NetflixSpikeResult(
                spike_name="netflix",
                executed_at=datetime.now(timezone.utc),
                status=ViabilityStatus.BLOCKED,
                duration_seconds=round(duration, 2),
                artifacts_produced=artifacts_produced,
                errors=errors,
                csv_path=str(resolved_csv_path),
                row_count=None,
                column_count=None,
                fingerprint=None,
                sample_path=None,
                license_info=LICENSE_INFO,
            )
            _persist_result_json(result, artifacts_dir)
            return result

    # -----------------------------------------------------------------------
    # Step 3: Compute SHA-256 fingerprint (Req 2.1, 2.6)
    # -----------------------------------------------------------------------
    fingerprint = compute_sha256(resolved_csv_path)

    # -----------------------------------------------------------------------
    # Step 4: Profile dataset (Req 2.3)
    # -----------------------------------------------------------------------
    profile: DataProfile = profile_dataset(resolved_csv_path)

    # Persist profile JSON
    profile_path = artifacts_dir / "netflix_profile.json"
    profile_path.write_text(profile.model_dump_json(indent=2), encoding="utf-8")
    artifacts_produced.append(str(profile_path))

    # -----------------------------------------------------------------------
    # Step 5: Extract minimal sample (Req 2.5)
    # -----------------------------------------------------------------------
    sample_df = extract_minimal_sample(resolved_csv_path, sample_size=50)
    sample_path = artifacts_dir / "netflix_sample.csv"
    sample_df.to_csv(sample_path, index=False, encoding="utf-8")
    artifacts_produced.append(str(sample_path))

    # -----------------------------------------------------------------------
    # Step 6: Persist fingerprint (Req 2.6)
    # -----------------------------------------------------------------------
    fingerprint_path = artifacts_dir / "netflix_fingerprint.txt"
    fingerprint_content = (
        f"file: {resolved_csv_path.name}\n"
        f"sha256: {fingerprint}\n"
        f"computed_at: {datetime.now(timezone.utc).isoformat()}\n"
    )
    fingerprint_path.write_text(fingerprint_content, encoding="utf-8")
    artifacts_produced.append(str(fingerprint_path))

    # -----------------------------------------------------------------------
    # Step 7: Build result (Req 2.4 - license info)
    # -----------------------------------------------------------------------
    duration = time.time() - start_time
    result = NetflixSpikeResult(
        spike_name="netflix",
        executed_at=datetime.now(timezone.utc),
        status=ViabilityStatus.CONFIRMED,
        duration_seconds=round(duration, 2),
        artifacts_produced=artifacts_produced,
        errors=errors,
        csv_path=str(resolved_csv_path),
        row_count=profile.row_count,
        column_count=profile.column_count,
        fingerprint=fingerprint,
        sample_path=str(sample_path),
        license_info=LICENSE_INFO,
    )

    # Persist complete result JSON
    _persist_result_json(result, artifacts_dir)

    return result


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _persist_result_json(result: NetflixSpikeResult, artifacts_dir: Path) -> None:
    """Serialize the spike result to JSON in the artifacts directory."""
    result_path = artifacts_dir / "netflix_spike_result.json"
    result_path.write_text(result.model_dump_json(indent=2), encoding="utf-8")
    if str(result_path) not in result.artifacts_produced:
        result.artifacts_produced.append(str(result_path))


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------


if __name__ == "__main__":
    import sys

    # Allow passing a CSV path as argument
    csv_arg = Path(sys.argv[1]) if len(sys.argv) > 1 else None

    print("=" * 60)
    print("  Netflix Dataset Viability Spike")
    print("=" * 60)
    print()

    result = run_netflix_spike(csv_path=csv_arg)

    print(f"Status: {result.status.value}")
    print(f"Duration: {result.duration_seconds}s")
    print(f"License: {result.license_info}")
    print()

    if result.fingerprint:
        print(f"SHA-256: {result.fingerprint}")
    if result.row_count is not None:
        print(f"Rows: {result.row_count}")
    if result.column_count is not None:
        print(f"Columns: {result.column_count}")
    if result.sample_path:
        print(f"Sample: {result.sample_path}")
    print()

    if result.errors:
        print("Errors/Warnings:")
        for err in result.errors:
            print(f"  - {err}")
        print()

    print(f"Artifacts produced: {len(result.artifacts_produced)}")
    for artifact in result.artifacts_produced:
        print(f"  - {artifact}")

    # Exit with error code if blocked
    if result.status == ViabilityStatus.BLOCKED:
        sys.exit(1)
