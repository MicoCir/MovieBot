"""TMDB API viability spike — validates credentials, fetches trending data,
sanitizes and persists snapshot, and generates field inventory.

Requirements validated: 1.1, 1.2, 1.3, 1.4, 1.5, 1.6
"""

import json
import logging
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx

from spikes.common.models import ViabilityStatus
from spikes.tmdb.models import FieldEntry, TmdbSpikeResult
from spikes.tmdb.validators import (
    build_tmdb_url,
    sanitize_payload,
    scan_for_credentials,
    validate_tmdb_url,
)

logger = logging.getLogger(__name__)

# Configuration
DEFAULT_TIMEOUT = 10.0  # seconds
MAX_RETRIES = 3
BACKOFF_BASE = 2.0  # seconds, exponential backoff base
ARTIFACTS_DIR = Path(__file__).resolve().parent.parent / "artifacts"


def generate_field_inventory(
    payload: dict[str, Any], prefix: str = ""
) -> list[FieldEntry]:
    """Recursively inspect a JSON payload and produce a field inventory.

    Each unique field path gets exactly one FieldEntry documenting:
    - name: the field key
    - observed_type: Python type name of the value
    - example_value: the actual value (or first element for lists)
    - path: dot-notation JSON path (arrays use [0] indexing)

    Args:
        payload: The dictionary to inspect.
        prefix: Current path prefix for recursion (internal use).

    Returns:
        List of FieldEntry objects, one per unique field path.
    """
    entries: list[FieldEntry] = []

    for key, value in payload.items():
        current_path = f"{prefix}.{key}" if prefix else key

        if isinstance(value, dict):
            # Record the dict field itself
            entries.append(
                FieldEntry(
                    name=key,
                    observed_type="object",
                    example_value="{...}",
                    path=current_path,
                )
            )
            # Recurse into the dict
            entries.extend(generate_field_inventory(value, prefix=current_path))

        elif isinstance(value, list):
            # Record the list field
            entries.append(
                FieldEntry(
                    name=key,
                    observed_type="array",
                    example_value=f"[{len(value)} items]",
                    path=current_path,
                )
            )
            # If list has items, inspect the first element
            if value:
                first = value[0]
                item_path = f"{current_path}[0]"
                if isinstance(first, dict):
                    entries.extend(
                        generate_field_inventory(first, prefix=item_path)
                    )
                else:
                    entries.append(
                        FieldEntry(
                            name=f"{key}[0]",
                            observed_type=type(first).__name__,
                            example_value=first,
                            path=item_path,
                        )
                    )

        else:
            # Scalar value
            observed_type = type(value).__name__ if value is not None else "null"
            entries.append(
                FieldEntry(
                    name=key,
                    observed_type=observed_type,
                    example_value=value,
                    path=current_path,
                )
            )

    return entries


def _get_api_key() -> str | None:
    """Read the TMDB API key from environment variables.

    Checks TMDB_API_KEY first, then TMDB_BEARER_TOKEN.
    """
    return os.environ.get("TMDB_API_KEY") or os.environ.get("TMDB_BEARER_TOKEN")


def _make_request(
    url: str, api_key: str, timeout: float = DEFAULT_TIMEOUT
) -> httpx.Response:
    """Execute HTTP GET with retry logic for 429 responses.

    Implements exponential backoff: 2s, 4s, 8s for rate-limited requests.

    Args:
        url: The validated endpoint URL.
        api_key: Bearer token for Authorization header.
        timeout: Request timeout in seconds.

    Returns:
        The final httpx.Response object.

    Raises:
        httpx.TimeoutException: If the request times out after retries.
        httpx.HTTPError: For other transport-level errors.
    """
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Accept": "application/json",
    }

    last_response: httpx.Response | None = None

    for attempt in range(MAX_RETRIES + 1):
        response = httpx.get(url, headers=headers, timeout=timeout)
        last_response = response

        if response.status_code == 429:
            if attempt < MAX_RETRIES:
                wait = BACKOFF_BASE ** (attempt + 1)
                logger.warning(
                    "Rate limited (429). Retry %d/%d in %.1fs",
                    attempt + 1,
                    MAX_RETRIES,
                    wait,
                )
                time.sleep(wait)
                continue
            else:
                logger.error("Rate limit exceeded after %d retries.", MAX_RETRIES)
                break
        else:
            break

    assert last_response is not None
    return last_response


def _create_blocked_result(
    endpoint: str,
    response_code: int | None,
    error_message: str,
    start_time: float,
) -> TmdbSpikeResult:
    """Create a blocked TmdbSpikeResult for error scenarios."""
    return TmdbSpikeResult(
        spike_name="tmdb",
        executed_at=datetime.now(timezone.utc),
        status=ViabilityStatus.BLOCKED,
        duration_seconds=time.time() - start_time,
        artifacts_produced=[],
        errors=[error_message],
        endpoint_used=endpoint,
        response_code=response_code,
        field_count=0,
        snapshot_path=None,
    )


def _persist_blocked_fixture(
    endpoint: str,
    response_code: int | None,
    error_message: str,
) -> str:
    """Persist a blocking fixture documenting the error encountered.

    Returns the path to the persisted fixture file.
    """
    ARTIFACTS_DIR.mkdir(parents=True, exist_ok=True)
    fixture_path = ARTIFACTS_DIR / "tmdb_blocked_fixture.json"

    fixture = {
        "blocked": True,
        "endpoint": endpoint,
        "response_code": response_code,
        "error_message": error_message,
        "documented_at": datetime.now(timezone.utc).isoformat(),
    }

    fixture_path.write_text(json.dumps(fixture, indent=2, ensure_ascii=False))
    logger.info("Blocked fixture persisted at: %s", fixture_path)
    return str(fixture_path)


def run_spike(
    time_window: str = "day",
    timeout: float = DEFAULT_TIMEOUT,
) -> TmdbSpikeResult:
    """Execute the TMDB viability spike.

    Steps:
    1. Validate API key availability
    2. Build and validate the endpoint URL (Req 1.1, 1.6)
    3. Make the HTTP request with retry logic
    4. Handle errors: 401/403 → blocked, 429 → retry, 5xx → blocked, timeout → blocked (Req 1.5)
    5. Sanitize the response payload (Req 1.3)
    6. Persist the sanitized snapshot (Req 1.2)
    7. Generate and persist the field inventory (Req 1.4)

    Args:
        time_window: "day" or "week" for the trending endpoint.
        timeout: Request timeout in seconds.

    Returns:
        TmdbSpikeResult with all spike metadata.
    """
    start_time = time.time()
    endpoint = ""

    # Step 1: Check credentials
    api_key = _get_api_key()
    if not api_key:
        error_msg = (
            "TMDB API key not found. Set TMDB_API_KEY or TMDB_BEARER_TOKEN "
            "environment variable."
        )
        logger.error(error_msg)
        return _create_blocked_result("", None, error_msg, start_time)

    # Step 2: Build and validate URL (Req 1.1, 1.6)
    try:
        endpoint = build_tmdb_url(time_window)  # type: ignore[arg-type]
    except (AssertionError, ValueError) as e:
        error_msg = f"URL construction failed: {e}"
        logger.error(error_msg)
        return _create_blocked_result("", None, error_msg, start_time)

    # Additional explicit URL validation (Req 1.6)
    if not validate_tmdb_url(endpoint):
        error_msg = f"URL rejected by validator: {endpoint}"
        logger.error(error_msg)
        return _create_blocked_result(endpoint, None, error_msg, start_time)

    # Step 3: Make HTTP request
    try:
        response = _make_request(endpoint, api_key, timeout=timeout)
    except httpx.TimeoutException:
        error_msg = f"Request timed out after {timeout}s for URL: {endpoint}"
        logger.error(error_msg)
        fixture_path = _persist_blocked_fixture(endpoint, None, error_msg)
        result = _create_blocked_result(endpoint, None, error_msg, start_time)
        result.artifacts_produced = [fixture_path]
        return result
    except httpx.HTTPError as e:
        error_msg = f"HTTP transport error: {e}"
        logger.error(error_msg)
        fixture_path = _persist_blocked_fixture(endpoint, None, error_msg)
        result = _create_blocked_result(endpoint, None, error_msg, start_time)
        result.artifacts_produced = [fixture_path]
        return result

    # Step 4: Handle error responses (Req 1.5)
    if response.status_code in (401, 403):
        error_msg = (
            f"Authentication/authorization error {response.status_code} "
            f"from {endpoint}: {response.text[:200]}"
        )
        logger.error(error_msg)
        fixture_path = _persist_blocked_fixture(
            endpoint, response.status_code, error_msg
        )
        result = _create_blocked_result(
            endpoint, response.status_code, error_msg, start_time
        )
        result.artifacts_produced = [fixture_path]
        return result

    if response.status_code == 429:
        error_msg = (
            f"Rate limit exceeded after {MAX_RETRIES} retries for {endpoint}"
        )
        logger.error(error_msg)
        fixture_path = _persist_blocked_fixture(
            endpoint, 429, error_msg
        )
        result = _create_blocked_result(endpoint, 429, error_msg, start_time)
        result.artifacts_produced = [fixture_path]
        return result

    if response.status_code >= 500:
        error_msg = (
            f"Server error {response.status_code} from {endpoint}: "
            f"{response.text[:200]}"
        )
        logger.error(error_msg)
        fixture_path = _persist_blocked_fixture(
            endpoint, response.status_code, error_msg
        )
        result = _create_blocked_result(
            endpoint, response.status_code, error_msg, start_time
        )
        result.artifacts_produced = [fixture_path]
        return result

    if response.status_code != 200:
        error_msg = (
            f"Unexpected status {response.status_code} from {endpoint}: "
            f"{response.text[:200]}"
        )
        logger.error(error_msg)
        fixture_path = _persist_blocked_fixture(
            endpoint, response.status_code, error_msg
        )
        result = _create_blocked_result(
            endpoint, response.status_code, error_msg, start_time
        )
        result.artifacts_produced = [fixture_path]
        return result

    # Step 5: Parse and validate JSON
    try:
        raw_payload: dict[str, Any] = response.json()
    except (json.JSONDecodeError, ValueError) as e:
        error_msg = f"Invalid JSON response: {e}. Body: {response.text[:200]}"
        logger.error(error_msg)
        fixture_path = _persist_blocked_fixture(endpoint, 200, error_msg)
        result = _create_blocked_result(endpoint, 200, error_msg, start_time)
        result.artifacts_produced = [fixture_path]
        return result

    # Step 6: Sanitize payload (Req 1.3)
    sanitized = sanitize_payload(raw_payload)

    # Verify no credentials remain (Req 5.5)
    sanitized_text = json.dumps(sanitized, ensure_ascii=False)
    remaining_creds = scan_for_credentials(sanitized_text)
    if remaining_creds:
        logger.warning(
            "Credentials detected after sanitization: %s. Removing...",
            remaining_creds,
        )
        # Re-sanitize as text-level cleanup
        for cred in remaining_creds:
            sanitized_text = sanitized_text.replace(cred, "[REDACTED]")
        sanitized = json.loads(sanitized_text)

    # Step 7: Persist sanitized snapshot (Req 1.2)
    ARTIFACTS_DIR.mkdir(parents=True, exist_ok=True)
    snapshot_path = ARTIFACTS_DIR / "tmdb_snapshot.json"
    snapshot_path.write_text(
        json.dumps(sanitized, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    logger.info("Snapshot persisted at: %s", snapshot_path)

    # Step 8: Generate field inventory (Req 1.4)
    field_inventory = generate_field_inventory(sanitized)

    inventory_path = ARTIFACTS_DIR / "tmdb_field_inventory.json"
    inventory_data = [entry.model_dump() for entry in field_inventory]
    inventory_path.write_text(
        json.dumps(inventory_data, indent=2, ensure_ascii=False, default=str),
        encoding="utf-8",
    )
    logger.info("Field inventory persisted at: %s", inventory_path)

    # Build success result
    duration = time.time() - start_time
    return TmdbSpikeResult(
        spike_name="tmdb",
        executed_at=datetime.now(timezone.utc),
        status=ViabilityStatus.CONFIRMED,
        duration_seconds=duration,
        artifacts_produced=[str(snapshot_path), str(inventory_path)],
        errors=[],
        endpoint_used=endpoint,
        response_code=response.status_code,
        field_count=len(field_inventory),
        snapshot_path=str(snapshot_path),
    )


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    result = run_spike()
    print(result.model_dump_json(indent=2))
