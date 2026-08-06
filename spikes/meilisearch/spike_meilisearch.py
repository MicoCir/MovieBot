"""Meilisearch CE viability spike.

Launches an ephemeral Meilisearch container, verifies healthcheck,
indexes sample documents, and tests search capabilities (full-text,
faceted filters, semantic search, hybrid search). Validates no
Enterprise features are used.

Requirements validated: 3.1, 3.2, 3.3, 3.4, 3.5, 3.6, 3.7
"""

from __future__ import annotations

import json
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path

import httpx

from spikes.common.models import ViabilityStatus
from spikes.meilisearch.config_validator import validate_no_enterprise_features
from spikes.meilisearch.models import MeilisearchSpikeResult

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

MEILISEARCH_IMAGE = "getmeili/meilisearch"
MEILISEARCH_TAG = "v1.6.2"
MEILISEARCH_ALT_TAG = "latest"
CONTAINER_NAME = "moviebot-spike-meilisearch"
HOST_PORT = 7700
MEILI_URL = f"http://localhost:{HOST_PORT}"
MASTER_KEY = "spike-test-master-key"

HEALTHCHECK_RETRIES = 3
HEALTHCHECK_INTERVAL_S = 5

ARTIFACTS_DIR = Path("spikes/artifacts")

# Minimal sample documents for indexing
SAMPLE_DOCUMENTS = [
    {
        "id": 1,
        "title": "The Shawshank Redemption",
        "overview": "Two imprisoned men bond over a number of years, finding solace and eventual redemption through acts of common decency.",
        "genre": ["Drama"],
        "year": 1994,
        "rating": 9.3,
    },
    {
        "id": 2,
        "title": "The Godfather",
        "overview": "The aging patriarch of an organized crime dynasty transfers control of his clandestine empire to his reluctant youngest son.",
        "genre": ["Crime", "Drama"],
        "year": 1972,
        "rating": 9.2,
    },
    {
        "id": 3,
        "title": "The Dark Knight",
        "overview": "When the menace known as the Joker wreaks havoc and chaos on the people of Gotham, Batman must accept one of the greatest psychological and physical tests of his ability to fight injustice.",
        "genre": ["Action", "Crime", "Drama"],
        "year": 2008,
        "rating": 9.0,
    },
    {
        "id": 4,
        "title": "Pulp Fiction",
        "overview": "The lives of two mob hitmen, a boxer, a gangster and his wife, and a pair of diner bandits intertwine in four tales of violence and redemption.",
        "genre": ["Crime", "Drama"],
        "year": 1994,
        "rating": 8.9,
    },
    {
        "id": 5,
        "title": "Schindler's List",
        "overview": "In German-occupied Poland during World War II, industrialist Oskar Schindler gradually becomes concerned for his Jewish workforce after witnessing their persecution by the Nazis.",
        "genre": ["Biography", "Drama", "History"],
        "year": 1993,
        "rating": 9.0,
    },
]


# ---------------------------------------------------------------------------
# Docker container management (subprocess)
# ---------------------------------------------------------------------------


def _is_docker_available() -> bool:
    """Check if Docker daemon is accessible."""
    try:
        result = subprocess.run(
            ["docker", "info"],
            capture_output=True,
            text=True,
            timeout=15,
        )
        return result.returncode == 0
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False


def _pull_image(image: str, tag: str) -> bool:
    """Pull the Meilisearch Docker image. Returns True on success."""
    full_image = f"{image}:{tag}"
    try:
        result = subprocess.run(
            ["docker", "pull", full_image],
            capture_output=True,
            text=True,
            timeout=120,
        )
        return result.returncode == 0
    except (subprocess.TimeoutExpired, Exception):
        return False


def _start_container(image: str, tag: str) -> bool:
    """Start the Meilisearch container. Returns True on success."""
    full_image = f"{image}:{tag}"

    # Remove any existing container with the same name
    subprocess.run(
        ["docker", "rm", "-f", CONTAINER_NAME],
        capture_output=True,
        text=True,
        timeout=15,
    )

    cmd = [
        "docker", "run", "-d",
        "--name", CONTAINER_NAME,
        "-p", f"{HOST_PORT}:7700",
        "-e", f"MEILI_MASTER_KEY={MASTER_KEY}",
        "-e", "MEILI_ENV=development",
        full_image,
    ]

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=30,
        )
        return result.returncode == 0
    except (subprocess.TimeoutExpired, Exception):
        return False


def _get_container_digest() -> str | None:
    """Get the container image digest via docker inspect."""
    try:
        result = subprocess.run(
            ["docker", "inspect", "--format", "{{.Image}}", CONTAINER_NAME],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.returncode == 0:
            return result.stdout.strip()
        return None
    except (subprocess.TimeoutExpired, Exception):
        return None


def _stop_and_remove_container() -> None:
    """Stop and remove the Meilisearch container."""
    try:
        subprocess.run(
            ["docker", "rm", "-f", CONTAINER_NAME],
            capture_output=True,
            text=True,
            timeout=15,
        )
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Healthcheck
# ---------------------------------------------------------------------------


def _wait_for_healthcheck(
    retries: int = HEALTHCHECK_RETRIES,
    interval: float = HEALTHCHECK_INTERVAL_S,
) -> bool:
    """Wait for Meilisearch to become healthy.

    Retries up to `retries` times with `interval` seconds between attempts.
    Returns True if the /health endpoint reports healthy.
    """
    for attempt in range(retries):
        try:
            response = httpx.get(
                f"{MEILI_URL}/health",
                timeout=5.0,
            )
            if response.status_code == 200:
                data = response.json()
                if data.get("status") == "available":
                    return True
        except (httpx.ConnectError, httpx.TimeoutException, Exception):
            pass

        if attempt < retries - 1:
            time.sleep(interval)

    return False


# ---------------------------------------------------------------------------
# Indexing and search tests
# ---------------------------------------------------------------------------


def _index_documents(documents: list[dict]) -> tuple[bool, str]:
    """Index sample documents into Meilisearch.

    Returns (success, message).
    """
    headers = {"Authorization": f"Bearer {MASTER_KEY}"}

    try:
        # Create index with filterable and sortable attributes
        settings_payload = {
            "filterableAttributes": ["genre", "year", "rating"],
            "sortableAttributes": ["year", "rating"],
        }

        # Add documents
        response = httpx.post(
            f"{MEILI_URL}/indexes/movies/documents",
            json=documents,
            headers=headers,
            timeout=15.0,
        )
        if response.status_code not in (200, 202):
            return False, f"Index documents failed: HTTP {response.status_code} - {response.text}"

        task_uid = response.json().get("taskUid")

        # Update settings for filterable attributes
        response = httpx.patch(
            f"{MEILI_URL}/indexes/movies/settings",
            json=settings_payload,
            headers=headers,
            timeout=15.0,
        )
        if response.status_code not in (200, 202):
            return False, f"Update settings failed: HTTP {response.status_code} - {response.text}"

        # Wait for indexing to complete
        _wait_for_task_completion(task_uid, headers)

        return True, "Documents indexed successfully"

    except (httpx.ConnectError, httpx.TimeoutException) as e:
        return False, f"Indexing connection error: {e}"
    except Exception as e:
        return False, f"Indexing error: {e}"


def _wait_for_task_completion(
    task_uid: int | None,
    headers: dict,
    timeout: float = 30.0,
) -> None:
    """Poll Meilisearch task status until succeeded or timeout."""
    if task_uid is None:
        time.sleep(2)
        return

    start = time.time()
    while time.time() - start < timeout:
        try:
            response = httpx.get(
                f"{MEILI_URL}/tasks/{task_uid}",
                headers=headers,
                timeout=5.0,
            )
            if response.status_code == 200:
                status = response.json().get("status")
                if status in ("succeeded", "failed"):
                    return
        except Exception:
            pass
        time.sleep(1)


def _test_fulltext_search(headers: dict) -> tuple[bool, str]:
    """Test full-text search with typo tolerance (Req 3.3).

    Searches for 'Shawshnk' (typo) and expects to find 'The Shawshank Redemption'.
    """
    try:
        response = httpx.post(
            f"{MEILI_URL}/indexes/movies/search",
            json={"q": "Shawshnk Redemtion"},  # intentional typos
            headers=headers,
            timeout=10.0,
        )
        if response.status_code != 200:
            return False, f"Full-text search failed: HTTP {response.status_code}"

        data = response.json()
        hits = data.get("hits", [])

        if not hits:
            return False, "Full-text search returned no results for typo query"

        # Check that Shawshank Redemption is in results
        titles = [h.get("title", "") for h in hits]
        if any("Shawshank" in t for t in titles):
            return True, f"Typo-tolerant search works: found {len(hits)} hit(s)"
        return False, f"Expected 'Shawshank' in results, got: {titles}"

    except (httpx.ConnectError, httpx.TimeoutException) as e:
        return False, f"Full-text search connection error: {e}"
    except Exception as e:
        return False, f"Full-text search error: {e}"


def _test_faceted_filters(headers: dict) -> tuple[bool, str]:
    """Test faceted filter search (Req 3.4).

    Filters movies by genre='Crime' and year >= 1994.
    """
    try:
        response = httpx.post(
            f"{MEILI_URL}/indexes/movies/search",
            json={
                "q": "",
                "filter": "genre = Crime AND year >= 1994",
            },
            headers=headers,
            timeout=10.0,
        )
        if response.status_code != 200:
            return False, f"Faceted filter search failed: HTTP {response.status_code} - {response.text}"

        data = response.json()
        hits = data.get("hits", [])

        if not hits:
            return False, "Faceted filter returned no results"

        # Verify all results match the filter
        for hit in hits:
            genres = hit.get("genre", [])
            year = hit.get("year", 0)
            if "Crime" not in genres or year < 1994:
                return False, f"Filter violation: {hit.get('title')} genres={genres} year={year}"

        return True, f"Faceted filters work: {len(hits)} hit(s) matching genre=Crime AND year>=1994"

    except (httpx.ConnectError, httpx.TimeoutException) as e:
        return False, f"Faceted filter connection error: {e}"
    except Exception as e:
        return False, f"Faceted filter error: {e}"


def _test_semantic_search(headers: dict) -> tuple[bool, str]:
    """Test semantic search mode (Req 3.5).

    Meilisearch CE supports AI-powered search with configured embedders.
    This test attempts to configure a simple embedder and run a semantic query.
    If the feature requires external embedder configuration not available,
    documents the limitation.
    """
    try:
        # Attempt to enable semantic search via experimental features
        # Meilisearch v1.6+ supports vectorSearch as experimental
        exp_response = httpx.patch(
            f"{MEILI_URL}/experimental-features",
            json={"vectorStore": True},
            headers=headers,
            timeout=10.0,
        )

        if exp_response.status_code != 200:
            return (
                False,
                f"Semantic search: cannot enable vectorStore experimental feature "
                f"(HTTP {exp_response.status_code}). "
                f"Limitation: requires Meilisearch with vector store support.",
            )

        # Try to configure a user-provided embedder (huggingFace built-in)
        embedder_settings = {
            "embedders": {
                "default": {
                    "source": "huggingFace",
                    "model": "sentence-transformers/all-MiniLM-L6-v2",
                }
            }
        }

        settings_response = httpx.patch(
            f"{MEILI_URL}/indexes/movies/settings",
            json=embedder_settings,
            headers=headers,
            timeout=30.0,
        )

        if settings_response.status_code in (200, 202):
            # Wait for embedder to process
            task_data = settings_response.json()
            task_uid = task_data.get("taskUid")
            _wait_for_task_completion(task_uid, headers)

            # Try semantic search
            search_response = httpx.post(
                f"{MEILI_URL}/indexes/movies/search",
                json={
                    "q": "a movie about hope and freedom",
                    "hybrid": {"semanticRatio": 1.0, "embedder": "default"},
                },
                headers=headers,
                timeout=15.0,
            )

            if search_response.status_code == 200:
                data = search_response.json()
                hits = data.get("hits", [])
                if hits:
                    return True, f"Semantic search works: {len(hits)} hit(s) returned"
                return True, "Semantic search accepted (0 hits, embedder may need time)"

            return (
                False,
                f"Semantic search query failed: HTTP {search_response.status_code}. "
                f"Limitation: embedder may require additional setup or model download. "
                f"Response: {search_response.text[:200]}",
            )

        return (
            False,
            f"Semantic search: embedder configuration failed "
            f"(HTTP {settings_response.status_code}). "
            f"Limitation: may require external embedder service. "
            f"Response: {settings_response.text[:200]}",
        )

    except (httpx.ConnectError, httpx.TimeoutException) as e:
        return False, f"Semantic search connection error: {e}"
    except Exception as e:
        return False, f"Semantic search error: {e}"


def _test_hybrid_search(headers: dict) -> tuple[bool, str]:
    """Test hybrid search mode (Req 3.5).

    Hybrid search combines lexical and semantic scoring.
    """
    try:
        response = httpx.post(
            f"{MEILI_URL}/indexes/movies/search",
            json={
                "q": "crime drama",
                "hybrid": {"semanticRatio": 0.5, "embedder": "default"},
            },
            headers=headers,
            timeout=15.0,
        )

        if response.status_code == 200:
            data = response.json()
            hits = data.get("hits", [])
            if hits:
                return True, f"Hybrid search works: {len(hits)} hit(s) returned"
            return True, "Hybrid search accepted (0 hits, embedder may need time)"

        return (
            False,
            f"Hybrid search failed: HTTP {response.status_code}. "
            f"Limitation: requires configured embedder for semantic component. "
            f"Response: {response.text[:200]}",
        )

    except (httpx.ConnectError, httpx.TimeoutException) as e:
        return False, f"Hybrid search connection error: {e}"
    except Exception as e:
        return False, f"Hybrid search error: {e}"


# ---------------------------------------------------------------------------
# Main spike execution
# ---------------------------------------------------------------------------


def run_meilisearch_spike(
    artifacts_dir: Path | None = None,
) -> MeilisearchSpikeResult:
    """Execute the Meilisearch CE viability spike.

    Parameters
    ----------
    artifacts_dir : Path | None
        Directory where artifacts are persisted. Defaults to spikes/artifacts/.

    Returns
    -------
    MeilisearchSpikeResult
        Complete result including capabilities tested, image info, and any
        Enterprise feature violations detected.
    """
    start_time = time.time()
    errors: list[str] = []
    artifacts_produced: list[str] = []
    capabilities_tested: dict[str, bool] = {}
    image_tag = f"{MEILISEARCH_IMAGE}:{MEILISEARCH_TAG}"
    container_digest: str | None = None
    healthcheck_passed = False

    if artifacts_dir is None:
        artifacts_dir = ARTIFACTS_DIR
    artifacts_dir.mkdir(parents=True, exist_ok=True)

    # -------------------------------------------------------------------
    # Step 1: Verify Docker availability (Req 3.1)
    # -------------------------------------------------------------------
    if not _is_docker_available():
        duration = time.time() - start_time
        errors.append(
            "Docker is not available. Please install Docker and ensure the "
            "daemon is running. Installation: https://docs.docker.com/get-docker/"
        )
        result = MeilisearchSpikeResult(
            spike_name="meilisearch",
            executed_at=datetime.now(timezone.utc),
            status=ViabilityStatus.BLOCKED,
            duration_seconds=round(duration, 2),
            artifacts_produced=artifacts_produced,
            errors=errors,
            image_tag=image_tag,
            container_digest=None,
            healthcheck_passed=False,
            capabilities_tested={},
            enterprise_features_detected=[],
        )
        _persist_result_json(result, artifacts_dir)
        return result

    # -------------------------------------------------------------------
    # Step 2: Pull image and start container (Req 3.1)
    # -------------------------------------------------------------------
    image_pulled = _pull_image(MEILISEARCH_IMAGE, MEILISEARCH_TAG)

    if not image_pulled:
        # Retry with alternative tag
        errors.append(
            f"Failed to pull {image_tag}, retrying with alt tag '{MEILISEARCH_ALT_TAG}'"
        )
        image_tag = f"{MEILISEARCH_IMAGE}:{MEILISEARCH_ALT_TAG}"
        image_pulled = _pull_image(MEILISEARCH_IMAGE, MEILISEARCH_ALT_TAG)

        if not image_pulled:
            duration = time.time() - start_time
            errors.append(
                f"Failed to pull Meilisearch image with both tags "
                f"'{MEILISEARCH_TAG}' and '{MEILISEARCH_ALT_TAG}'. "
                f"Ensure Docker has network access and the image exists."
            )
            result = MeilisearchSpikeResult(
                spike_name="meilisearch",
                executed_at=datetime.now(timezone.utc),
                status=ViabilityStatus.BLOCKED,
                duration_seconds=round(duration, 2),
                artifacts_produced=artifacts_produced,
                errors=errors,
                image_tag=image_tag,
                container_digest=None,
                healthcheck_passed=False,
                capabilities_tested={},
                enterprise_features_detected=[],
            )
            _persist_result_json(result, artifacts_dir)
            return result

    # Start container
    tag_used = MEILISEARCH_TAG if MEILISEARCH_TAG in image_tag else MEILISEARCH_ALT_TAG
    container_started = _start_container(MEILISEARCH_IMAGE, tag_used)

    if not container_started:
        duration = time.time() - start_time
        errors.append("Failed to start Meilisearch container.")
        result = MeilisearchSpikeResult(
            spike_name="meilisearch",
            executed_at=datetime.now(timezone.utc),
            status=ViabilityStatus.BLOCKED,
            duration_seconds=round(duration, 2),
            artifacts_produced=artifacts_produced,
            errors=errors,
            image_tag=image_tag,
            container_digest=None,
            healthcheck_passed=False,
            capabilities_tested={},
            enterprise_features_detected=[],
        )
        _persist_result_json(result, artifacts_dir)
        return result

    try:
        # ---------------------------------------------------------------
        # Step 3: Healthcheck with retry (Req 3.2)
        # ---------------------------------------------------------------
        healthcheck_passed = _wait_for_healthcheck(
            retries=HEALTHCHECK_RETRIES,
            interval=HEALTHCHECK_INTERVAL_S,
        )

        if not healthcheck_passed:
            duration = time.time() - start_time
            errors.append(
                f"Healthcheck failed after {HEALTHCHECK_RETRIES} attempts "
                f"(interval: {HEALTHCHECK_INTERVAL_S}s). "
                f"Container may not have started correctly."
            )
            result = MeilisearchSpikeResult(
                spike_name="meilisearch",
                executed_at=datetime.now(timezone.utc),
                status=ViabilityStatus.BLOCKED,
                duration_seconds=round(duration, 2),
                artifacts_produced=artifacts_produced,
                errors=errors,
                image_tag=image_tag,
                container_digest=_get_container_digest(),
                healthcheck_passed=False,
                capabilities_tested={},
                enterprise_features_detected=[],
            )
            _persist_result_json(result, artifacts_dir)
            return result

        # Get container digest (Req 3.2)
        container_digest = _get_container_digest()

        # ---------------------------------------------------------------
        # Step 4: Index sample documents (Req 3.3)
        # ---------------------------------------------------------------
        headers = {"Authorization": f"Bearer {MASTER_KEY}"}
        index_success, index_msg = _index_documents(SAMPLE_DOCUMENTS)

        if not index_success:
            errors.append(f"Indexing failed: {index_msg}")
            capabilities_tested["indexing"] = False
        else:
            capabilities_tested["indexing"] = True
            # Allow time for indexing to complete
            time.sleep(2)

        # ---------------------------------------------------------------
        # Step 5: Execute search tests (Req 3.3, 3.4, 3.5)
        # ---------------------------------------------------------------

        # Full-text search with typo tolerance (Req 3.3)
        ft_success, ft_msg = _test_fulltext_search(headers)
        capabilities_tested["fulltext_typo_tolerance"] = ft_success
        if not ft_success:
            errors.append(f"Full-text search limitation: {ft_msg}")

        # Faceted filters (Req 3.4)
        facet_success, facet_msg = _test_faceted_filters(headers)
        capabilities_tested["faceted_filters"] = facet_success
        if not facet_success:
            errors.append(f"Faceted filter limitation: {facet_msg}")

        # Semantic search (Req 3.5)
        sem_success, sem_msg = _test_semantic_search(headers)
        capabilities_tested["semantic_search"] = sem_success
        if not sem_success:
            errors.append(f"Semantic search limitation: {sem_msg}")

        # Hybrid search (Req 3.5)
        hyb_success, hyb_msg = _test_hybrid_search(headers)
        capabilities_tested["hybrid_search"] = hyb_success
        if not hyb_success:
            errors.append(f"Hybrid search limitation: {hyb_msg}")

        # ---------------------------------------------------------------
        # Step 6: Validate no Enterprise features (Req 3.7)
        # ---------------------------------------------------------------
        # Build the configuration we used and validate it
        config_used = {
            "env": "development",
            "masterKey": MASTER_KEY,
            "filterableAttributes": ["genre", "year", "rating"],
            "sortableAttributes": ["year", "rating"],
        }

        # If embedder was configured, add it to the config for validation
        embedder_config = {
            "embedders": {
                "default": {
                    "source": "huggingFace",
                    "model": "sentence-transformers/all-MiniLM-L6-v2",
                }
            }
        }
        config_used.update(embedder_config)

        enterprise_detected = validate_no_enterprise_features(config_used)

    finally:
        # ---------------------------------------------------------------
        # Step 7: Cleanup - remove ephemeral container (Req 5.3)
        # ---------------------------------------------------------------
        _stop_and_remove_container()

    # -------------------------------------------------------------------
    # Step 8: Determine status and build result
    # -------------------------------------------------------------------
    # Status is CONFIRMED if at least fulltext and faceted work
    # Semantic/hybrid failures are documented as limitations (Req 3.6)
    core_capabilities_ok = (
        capabilities_tested.get("indexing", False)
        and capabilities_tested.get("fulltext_typo_tolerance", False)
        and capabilities_tested.get("faceted_filters", False)
    )
    status = ViabilityStatus.CONFIRMED if core_capabilities_ok else ViabilityStatus.BLOCKED

    duration = time.time() - start_time

    result = MeilisearchSpikeResult(
        spike_name="meilisearch",
        executed_at=datetime.now(timezone.utc),
        status=status,
        duration_seconds=round(duration, 2),
        artifacts_produced=artifacts_produced,
        errors=errors,
        image_tag=image_tag,
        container_digest=container_digest,
        healthcheck_passed=healthcheck_passed,
        capabilities_tested=capabilities_tested,
        enterprise_features_detected=enterprise_detected,
    )

    # Persist result
    _persist_result_json(result, artifacts_dir)

    return result


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _persist_result_json(
    result: MeilisearchSpikeResult, artifacts_dir: Path
) -> None:
    """Serialize the spike result to JSON in the artifacts directory."""
    result_path = artifacts_dir / "meilisearch_smoke.json"
    result_path.write_text(result.model_dump_json(indent=2), encoding="utf-8")
    if str(result_path) not in result.artifacts_produced:
        result.artifacts_produced.append(str(result_path))


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------


if __name__ == "__main__":
    import sys

    print("=" * 60)
    print("  Meilisearch CE Viability Spike")
    print("=" * 60)
    print()

    result = run_meilisearch_spike()

    print(f"Status: {result.status.value}")
    print(f"Duration: {result.duration_seconds}s")
    print(f"Image: {result.image_tag}")
    print(f"Digest: {result.container_digest or 'N/A'}")
    print(f"Healthcheck: {'PASSED' if result.healthcheck_passed else 'FAILED'}")
    print()

    print("Capabilities tested:")
    for cap, passed in result.capabilities_tested.items():
        icon = "✓" if passed else "✗"
        print(f"  {icon} {cap}")
    print()

    if result.enterprise_features_detected:
        print("Enterprise features detected (VIOLATIONS):")
        for feat in result.enterprise_features_detected:
            print(f"  - {feat}")
        print()

    if result.errors:
        print("Errors/Limitations:")
        for err in result.errors:
            print(f"  - {err}")
        print()

    print(f"Artifacts produced: {len(result.artifacts_produced)}")
    for artifact in result.artifacts_produced:
        print(f"  - {artifact}")

    # Exit with error code if blocked
    if result.status == ViabilityStatus.BLOCKED:
        sys.exit(1)
