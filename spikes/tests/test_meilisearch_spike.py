"""Unit tests for the Meilisearch CE viability spike.

Tests mock Docker/subprocess for container management and httpx for
Meilisearch HTTP responses, verifying capabilities map population and
Enterprise feature detection.

Requirements validated: 3.2, 3.3, 3.4, 3.5, 3.7
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import httpx
import pytest

from spikes.common.models import ViabilityStatus
from spikes.meilisearch.spike_meilisearch import run_meilisearch_spike


# ---------------------------------------------------------------------------
# Helpers for building mock responses
# ---------------------------------------------------------------------------


def _mock_subprocess_success(*args, **kwargs):
    """Generic subprocess.run mock that returns success (returncode=0)."""
    mock_result = MagicMock()
    mock_result.returncode = 0
    mock_result.stdout = "sha256:abc123fakedigest"
    mock_result.stderr = ""
    return mock_result


def _mock_subprocess_docker_not_available(*args, **kwargs):
    """subprocess.run mock simulating Docker not installed."""
    cmd = args[0] if args else kwargs.get("args", [])
    if cmd and cmd[0] == "docker" and cmd[1] == "info":
        mock_result = MagicMock()
        mock_result.returncode = 1
        mock_result.stdout = ""
        mock_result.stderr = "Cannot connect to the Docker daemon"
        return mock_result
    # Default success for other calls
    return _mock_subprocess_success(*args, **kwargs)


def _make_httpx_response(status_code: int, json_data: dict | None = None):
    """Create a mock httpx.Response."""
    response = MagicMock(spec=httpx.Response)
    response.status_code = status_code
    response.text = str(json_data) if json_data else ""
    if json_data is not None:
        response.json.return_value = json_data
    else:
        response.json.return_value = {}
    return response


# ---------------------------------------------------------------------------
# Test 1: Docker not available → blocked status
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestDockerNotAvailable:
    """When Docker is not available, the spike should report blocked status."""

    @patch("spikes.meilisearch.spike_meilisearch.subprocess.run")
    def test_docker_unavailable_returns_blocked(self, mock_subprocess, tmp_path):
        """Req 3.2: If Docker is unavailable, spike should be blocked."""
        mock_subprocess.side_effect = _mock_subprocess_docker_not_available

        result = run_meilisearch_spike(artifacts_dir=tmp_path)

        assert result.status == ViabilityStatus.BLOCKED
        assert result.healthcheck_passed is False
        assert result.capabilities_tested == {}
        # Error should mention Docker installation
        assert any("Docker" in err for err in result.errors)
        assert any("install" in err.lower() for err in result.errors)

    @patch("spikes.meilisearch.spike_meilisearch.subprocess.run")
    def test_docker_unavailable_file_not_found(self, mock_subprocess, tmp_path):
        """Docker binary not found raises FileNotFoundError → blocked."""
        mock_subprocess.side_effect = FileNotFoundError("docker not found")

        result = run_meilisearch_spike(artifacts_dir=tmp_path)

        assert result.status == ViabilityStatus.BLOCKED
        assert result.healthcheck_passed is False


# ---------------------------------------------------------------------------
# Test 2: Successful full run (all mocked)
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestSuccessfulFullRun:
    """Full successful spike run with all external calls mocked."""

    @patch("spikes.meilisearch.spike_meilisearch.time.sleep", return_value=None)
    @patch("spikes.meilisearch.spike_meilisearch.httpx.post")
    @patch("spikes.meilisearch.spike_meilisearch.httpx.get")
    @patch("spikes.meilisearch.spike_meilisearch.httpx.patch")
    @patch("spikes.meilisearch.spike_meilisearch.subprocess.run")
    def test_full_success_confirmed_status(
        self, mock_subprocess, mock_patch, mock_get, mock_post, mock_sleep, tmp_path
    ):
        """Req 3.2, 3.3, 3.4, 3.5: Successful run produces confirmed status with all capabilities."""
        # subprocess: all Docker commands succeed
        mock_subprocess.side_effect = _mock_subprocess_success

        # httpx.get: healthcheck and task status
        def get_side_effect(url, **kwargs):
            if "/health" in url:
                return _make_httpx_response(200, {"status": "available"})
            if "/tasks/" in url:
                return _make_httpx_response(200, {"status": "succeeded"})
            return _make_httpx_response(200, {})

        mock_get.side_effect = get_side_effect

        # httpx.post: indexing and search operations
        def post_side_effect(url, **kwargs):
            json_body = kwargs.get("json", {})
            if "/documents" in url:
                return _make_httpx_response(202, {"taskUid": 1})
            if "/search" in url:
                # Full-text search with typo tolerance
                q = json_body.get("q", "")
                hybrid = json_body.get("hybrid")
                filter_val = json_body.get("filter")

                if "Shawshnk" in q or "Redemtion" in q:
                    # Typo-tolerant full-text search
                    return _make_httpx_response(200, {
                        "hits": [{"id": 1, "title": "The Shawshank Redemption", "genre": ["Drama"], "year": 1994}],
                        "query": q,
                    })
                elif filter_val and "Crime" in str(filter_val):
                    # Faceted filter search: results must match genre=Crime AND year>=1994
                    return _make_httpx_response(200, {
                        "hits": [
                            {"id": 3, "title": "The Dark Knight", "genre": ["Action", "Crime", "Drama"], "year": 2008},
                            {"id": 4, "title": "Pulp Fiction", "genre": ["Crime", "Drama"], "year": 1994},
                        ],
                        "query": "",
                    })
                elif hybrid and hybrid.get("semanticRatio") == 1.0:
                    # Semantic search
                    return _make_httpx_response(200, {
                        "hits": [{"id": 1, "title": "The Shawshank Redemption"}],
                    })
                elif hybrid and hybrid.get("semanticRatio") == 0.5:
                    # Hybrid search
                    return _make_httpx_response(200, {
                        "hits": [{"id": 2, "title": "The Godfather"}],
                    })
                return _make_httpx_response(200, {"hits": []})
            return _make_httpx_response(200, {})

        mock_post.side_effect = post_side_effect

        # httpx.patch: settings and experimental features
        def patch_side_effect(url, **kwargs):
            if "/experimental-features" in url:
                return _make_httpx_response(200, {"vectorStore": True})
            if "/settings" in url:
                return _make_httpx_response(202, {"taskUid": 2})
            return _make_httpx_response(200, {})

        mock_patch.side_effect = patch_side_effect

        result = run_meilisearch_spike(artifacts_dir=tmp_path)

        # Req 3.2: image tag, healthcheck registered
        assert result.image_tag is not None
        assert "meilisearch" in result.image_tag.lower() or "meili" in result.image_tag.lower()
        assert result.healthcheck_passed is True
        assert result.container_digest is not None

        # Req 3.3: Full-text search with typo tolerance
        assert result.capabilities_tested.get("fulltext_typo_tolerance") is True

        # Req 3.4: Faceted filter search
        assert result.capabilities_tested.get("faceted_filters") is True

        # Req 3.5: Semantic and hybrid search
        assert result.capabilities_tested.get("semantic_search") is True
        assert result.capabilities_tested.get("hybrid_search") is True

        # Overall status
        assert result.status == ViabilityStatus.CONFIRMED

    @patch("spikes.meilisearch.spike_meilisearch.time.sleep", return_value=None)
    @patch("spikes.meilisearch.spike_meilisearch.httpx.post")
    @patch("spikes.meilisearch.spike_meilisearch.httpx.get")
    @patch("spikes.meilisearch.spike_meilisearch.httpx.patch")
    @patch("spikes.meilisearch.spike_meilisearch.subprocess.run")
    def test_full_success_capabilities_map_complete(
        self, mock_subprocess, mock_patch, mock_get, mock_post, mock_sleep, tmp_path
    ):
        """Capabilities map should contain all expected test keys."""
        mock_subprocess.side_effect = _mock_subprocess_success

        def get_side_effect(url, **kwargs):
            if "/health" in url:
                return _make_httpx_response(200, {"status": "available"})
            if "/tasks/" in url:
                return _make_httpx_response(200, {"status": "succeeded"})
            return _make_httpx_response(200, {})

        mock_get.side_effect = get_side_effect

        def post_side_effect(url, **kwargs):
            json_body = kwargs.get("json", {})
            if "/documents" in url:
                return _make_httpx_response(202, {"taskUid": 1})
            if "/search" in url:
                q = json_body.get("q", "")
                hybrid = json_body.get("hybrid")
                filter_val = json_body.get("filter")

                if "Shawshnk" in q:
                    return _make_httpx_response(200, {
                        "hits": [{"id": 1, "title": "The Shawshank Redemption", "genre": ["Drama"], "year": 1994}],
                    })
                elif filter_val and "Crime" in str(filter_val):
                    return _make_httpx_response(200, {
                        "hits": [{"id": 4, "title": "Pulp Fiction", "genre": ["Crime", "Drama"], "year": 1994}],
                    })
                elif hybrid and hybrid.get("semanticRatio") == 1.0:
                    return _make_httpx_response(200, {"hits": [{"id": 1, "title": "The Shawshank Redemption"}]})
                elif hybrid and hybrid.get("semanticRatio") == 0.5:
                    return _make_httpx_response(200, {"hits": [{"id": 2, "title": "The Godfather"}]})
                return _make_httpx_response(200, {"hits": []})
            return _make_httpx_response(200, {})

        mock_post.side_effect = post_side_effect

        def patch_side_effect(url, **kwargs):
            if "/experimental-features" in url:
                return _make_httpx_response(200, {"vectorStore": True})
            if "/settings" in url:
                return _make_httpx_response(202, {"taskUid": 2})
            return _make_httpx_response(200, {})

        mock_patch.side_effect = patch_side_effect

        result = run_meilisearch_spike(artifacts_dir=tmp_path)

        expected_keys = {"indexing", "fulltext_typo_tolerance", "faceted_filters", "semantic_search", "hybrid_search"}
        assert set(result.capabilities_tested.keys()) == expected_keys


# ---------------------------------------------------------------------------
# Test 3: Healthcheck fails → blocked status
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestHealthcheckFails:
    """When healthcheck fails, the spike should report blocked status."""

    @patch("spikes.meilisearch.spike_meilisearch.time.sleep", return_value=None)
    @patch("spikes.meilisearch.spike_meilisearch.httpx.get")
    @patch("spikes.meilisearch.spike_meilisearch.subprocess.run")
    def test_healthcheck_failure_returns_blocked(
        self, mock_subprocess, mock_get, mock_sleep, tmp_path
    ):
        """Req 3.2: Healthcheck failure leads to blocked status."""
        mock_subprocess.side_effect = _mock_subprocess_success

        # Healthcheck always fails (service not available)
        mock_get.side_effect = lambda url, **kwargs: _make_httpx_response(
            503, {"status": "unavailable"}
        )

        result = run_meilisearch_spike(artifacts_dir=tmp_path)

        assert result.status == ViabilityStatus.BLOCKED
        assert result.healthcheck_passed is False
        assert result.capabilities_tested == {}
        assert any("Healthcheck" in err or "healthcheck" in err.lower() for err in result.errors)

    @patch("spikes.meilisearch.spike_meilisearch.time.sleep", return_value=None)
    @patch("spikes.meilisearch.spike_meilisearch.httpx.get")
    @patch("spikes.meilisearch.spike_meilisearch.subprocess.run")
    def test_healthcheck_timeout_returns_blocked(
        self, mock_subprocess, mock_get, mock_sleep, tmp_path
    ):
        """Req 3.2: Healthcheck timeout (ConnectError) leads to blocked."""
        mock_subprocess.side_effect = _mock_subprocess_success

        # Healthcheck raises connection error (container not responding)
        mock_get.side_effect = httpx.ConnectError("Connection refused")

        result = run_meilisearch_spike(artifacts_dir=tmp_path)

        assert result.status == ViabilityStatus.BLOCKED
        assert result.healthcheck_passed is False


# ---------------------------------------------------------------------------
# Test 4: Full-text search fails → capability marked false
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestFulltextSearchFails:
    """When full-text search fails, the capability is marked false and error is documented."""

    @patch("spikes.meilisearch.spike_meilisearch.time.sleep", return_value=None)
    @patch("spikes.meilisearch.spike_meilisearch.httpx.post")
    @patch("spikes.meilisearch.spike_meilisearch.httpx.get")
    @patch("spikes.meilisearch.spike_meilisearch.httpx.patch")
    @patch("spikes.meilisearch.spike_meilisearch.subprocess.run")
    def test_fulltext_failure_marks_capability_false(
        self, mock_subprocess, mock_patch, mock_get, mock_post, mock_sleep, tmp_path
    ):
        """Req 3.3: Full-text search failure is documented in capabilities."""
        mock_subprocess.side_effect = _mock_subprocess_success

        def get_side_effect(url, **kwargs):
            if "/health" in url:
                return _make_httpx_response(200, {"status": "available"})
            if "/tasks/" in url:
                return _make_httpx_response(200, {"status": "succeeded"})
            return _make_httpx_response(200, {})

        mock_get.side_effect = get_side_effect

        def post_side_effect(url, **kwargs):
            json_body = kwargs.get("json", {})
            if "/documents" in url:
                return _make_httpx_response(202, {"taskUid": 1})
            if "/search" in url:
                q = json_body.get("q", "")
                hybrid = json_body.get("hybrid")
                filter_val = json_body.get("filter")

                if "Shawshnk" in q:
                    # Full-text search returns NO results (failure scenario)
                    return _make_httpx_response(200, {"hits": []})
                elif filter_val and "Crime" in str(filter_val):
                    return _make_httpx_response(200, {
                        "hits": [{"id": 4, "title": "Pulp Fiction", "genre": ["Crime", "Drama"], "year": 1994}],
                    })
                elif hybrid and hybrid.get("semanticRatio") == 1.0:
                    return _make_httpx_response(200, {"hits": [{"id": 1, "title": "The Shawshank Redemption"}]})
                elif hybrid and hybrid.get("semanticRatio") == 0.5:
                    return _make_httpx_response(200, {"hits": [{"id": 2, "title": "The Godfather"}]})
                return _make_httpx_response(200, {"hits": []})
            return _make_httpx_response(200, {})

        mock_post.side_effect = post_side_effect

        def patch_side_effect(url, **kwargs):
            if "/experimental-features" in url:
                return _make_httpx_response(200, {"vectorStore": True})
            if "/settings" in url:
                return _make_httpx_response(202, {"taskUid": 2})
            return _make_httpx_response(200, {})

        mock_patch.side_effect = patch_side_effect

        result = run_meilisearch_spike(artifacts_dir=tmp_path)

        # Full-text search should be marked as failed
        assert result.capabilities_tested.get("fulltext_typo_tolerance") is False
        # Error should be documented
        assert any("full-text" in err.lower() or "Full-text" in err for err in result.errors)
        # Other capabilities still work
        assert result.capabilities_tested.get("faceted_filters") is True
        # Status is BLOCKED because core capability (fulltext) failed
        assert result.status == ViabilityStatus.BLOCKED


# ---------------------------------------------------------------------------
# Test 5: Enterprise features detected (integration in spike)
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestEnterpriseFeatureDetection:
    """Enterprise features should be detected and reported in the spike result."""

    @patch("spikes.meilisearch.spike_meilisearch.time.sleep", return_value=None)
    @patch("spikes.meilisearch.spike_meilisearch.httpx.post")
    @patch("spikes.meilisearch.spike_meilisearch.httpx.get")
    @patch("spikes.meilisearch.spike_meilisearch.httpx.patch")
    @patch("spikes.meilisearch.spike_meilisearch.subprocess.run")
    def test_no_enterprise_features_in_clean_config(
        self, mock_subprocess, mock_patch, mock_get, mock_post, mock_sleep, tmp_path
    ):
        """Req 3.7: Clean config should have no Enterprise features detected."""
        mock_subprocess.side_effect = _mock_subprocess_success

        def get_side_effect(url, **kwargs):
            if "/health" in url:
                return _make_httpx_response(200, {"status": "available"})
            if "/tasks/" in url:
                return _make_httpx_response(200, {"status": "succeeded"})
            return _make_httpx_response(200, {})

        mock_get.side_effect = get_side_effect

        def post_side_effect(url, **kwargs):
            json_body = kwargs.get("json", {})
            if "/documents" in url:
                return _make_httpx_response(202, {"taskUid": 1})
            if "/search" in url:
                q = json_body.get("q", "")
                hybrid = json_body.get("hybrid")
                filter_val = json_body.get("filter")
                if "Shawshnk" in q:
                    return _make_httpx_response(200, {
                        "hits": [{"id": 1, "title": "The Shawshank Redemption", "genre": ["Drama"], "year": 1994}],
                    })
                elif filter_val and "Crime" in str(filter_val):
                    return _make_httpx_response(200, {
                        "hits": [{"id": 4, "title": "Pulp Fiction", "genre": ["Crime", "Drama"], "year": 1994}],
                    })
                elif hybrid:
                    return _make_httpx_response(200, {"hits": [{"id": 1, "title": "Test"}]})
                return _make_httpx_response(200, {"hits": []})
            return _make_httpx_response(200, {})

        mock_post.side_effect = post_side_effect

        def patch_side_effect(url, **kwargs):
            if "/experimental-features" in url:
                return _make_httpx_response(200, {"vectorStore": True})
            if "/settings" in url:
                return _make_httpx_response(202, {"taskUid": 2})
            return _make_httpx_response(200, {})

        mock_patch.side_effect = patch_side_effect

        result = run_meilisearch_spike(artifacts_dir=tmp_path)

        # The spike's default config should not trigger enterprise features
        assert result.enterprise_features_detected == []

    @patch("spikes.meilisearch.spike_meilisearch.validate_no_enterprise_features")
    @patch("spikes.meilisearch.spike_meilisearch.time.sleep", return_value=None)
    @patch("spikes.meilisearch.spike_meilisearch.httpx.post")
    @patch("spikes.meilisearch.spike_meilisearch.httpx.get")
    @patch("spikes.meilisearch.spike_meilisearch.httpx.patch")
    @patch("spikes.meilisearch.spike_meilisearch.subprocess.run")
    def test_enterprise_features_flagged_as_violations(
        self,
        mock_subprocess,
        mock_patch,
        mock_get,
        mock_post,
        mock_sleep,
        mock_validate,
        tmp_path,
    ):
        """Req 3.7: Enterprise features detected should be reported in result."""
        mock_subprocess.side_effect = _mock_subprocess_success

        # Simulate enterprise feature detection
        mock_validate.return_value = ["analytics", "personalization"]

        def get_side_effect(url, **kwargs):
            if "/health" in url:
                return _make_httpx_response(200, {"status": "available"})
            if "/tasks/" in url:
                return _make_httpx_response(200, {"status": "succeeded"})
            return _make_httpx_response(200, {})

        mock_get.side_effect = get_side_effect

        def post_side_effect(url, **kwargs):
            json_body = kwargs.get("json", {})
            if "/documents" in url:
                return _make_httpx_response(202, {"taskUid": 1})
            if "/search" in url:
                q = json_body.get("q", "")
                hybrid = json_body.get("hybrid")
                filter_val = json_body.get("filter")
                if "Shawshnk" in q:
                    return _make_httpx_response(200, {
                        "hits": [{"id": 1, "title": "The Shawshank Redemption", "genre": ["Drama"], "year": 1994}],
                    })
                elif filter_val and "Crime" in str(filter_val):
                    return _make_httpx_response(200, {
                        "hits": [{"id": 4, "title": "Pulp Fiction", "genre": ["Crime", "Drama"], "year": 1994}],
                    })
                elif hybrid:
                    return _make_httpx_response(200, {"hits": [{"id": 1, "title": "Test"}]})
                return _make_httpx_response(200, {"hits": []})
            return _make_httpx_response(200, {})

        mock_post.side_effect = post_side_effect

        def patch_side_effect(url, **kwargs):
            if "/experimental-features" in url:
                return _make_httpx_response(200, {"vectorStore": True})
            if "/settings" in url:
                return _make_httpx_response(202, {"taskUid": 2})
            return _make_httpx_response(200, {})

        mock_patch.side_effect = patch_side_effect

        result = run_meilisearch_spike(artifacts_dir=tmp_path)

        # Enterprise features should be flagged
        assert "analytics" in result.enterprise_features_detected
        assert "personalization" in result.enterprise_features_detected
        assert len(result.enterprise_features_detected) == 2


# ---------------------------------------------------------------------------
# Test: Result artifact is persisted to disk
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestArtifactPersistence:
    """Spike result JSON is persisted to the artifacts directory."""

    @patch("spikes.meilisearch.spike_meilisearch.subprocess.run")
    def test_result_json_persisted_on_blocked(self, mock_subprocess, tmp_path):
        """Result JSON file is created even when spike is blocked."""
        mock_subprocess.side_effect = _mock_subprocess_docker_not_available

        run_meilisearch_spike(artifacts_dir=tmp_path)

        result_file = tmp_path / "meilisearch_smoke.json"
        assert result_file.exists()
        # Verify it's valid JSON
        import json
        data = json.loads(result_file.read_text(encoding="utf-8"))
        assert data["spike_name"] == "meilisearch"
        assert data["status"] == "blocked"

    @patch("spikes.meilisearch.spike_meilisearch.time.sleep", return_value=None)
    @patch("spikes.meilisearch.spike_meilisearch.httpx.post")
    @patch("spikes.meilisearch.spike_meilisearch.httpx.get")
    @patch("spikes.meilisearch.spike_meilisearch.httpx.patch")
    @patch("spikes.meilisearch.spike_meilisearch.subprocess.run")
    def test_result_json_persisted_on_success(
        self, mock_subprocess, mock_patch, mock_get, mock_post, mock_sleep, tmp_path
    ):
        """Result JSON file is created on successful run."""
        mock_subprocess.side_effect = _mock_subprocess_success

        def get_side_effect(url, **kwargs):
            if "/health" in url:
                return _make_httpx_response(200, {"status": "available"})
            if "/tasks/" in url:
                return _make_httpx_response(200, {"status": "succeeded"})
            return _make_httpx_response(200, {})

        mock_get.side_effect = get_side_effect

        def post_side_effect(url, **kwargs):
            json_body = kwargs.get("json", {})
            if "/documents" in url:
                return _make_httpx_response(202, {"taskUid": 1})
            if "/search" in url:
                q = json_body.get("q", "")
                hybrid = json_body.get("hybrid")
                filter_val = json_body.get("filter")
                if "Shawshnk" in q:
                    return _make_httpx_response(200, {
                        "hits": [{"id": 1, "title": "The Shawshank Redemption", "genre": ["Drama"], "year": 1994}],
                    })
                elif filter_val and "Crime" in str(filter_val):
                    return _make_httpx_response(200, {
                        "hits": [{"id": 4, "title": "Pulp Fiction", "genre": ["Crime", "Drama"], "year": 1994}],
                    })
                elif hybrid:
                    return _make_httpx_response(200, {"hits": [{"id": 1, "title": "Test"}]})
                return _make_httpx_response(200, {"hits": []})
            return _make_httpx_response(200, {})

        mock_post.side_effect = post_side_effect

        def patch_side_effect(url, **kwargs):
            if "/experimental-features" in url:
                return _make_httpx_response(200, {"vectorStore": True})
            if "/settings" in url:
                return _make_httpx_response(202, {"taskUid": 2})
            return _make_httpx_response(200, {})

        mock_patch.side_effect = patch_side_effect

        run_meilisearch_spike(artifacts_dir=tmp_path)

        result_file = tmp_path / "meilisearch_smoke.json"
        assert result_file.exists()

        import json
        data = json.loads(result_file.read_text(encoding="utf-8"))
        assert data["spike_name"] == "meilisearch"
        assert data["status"] == "confirmed"
        assert data["healthcheck_passed"] is True
        assert "fulltext_typo_tolerance" in data["capabilities_tested"]


# ---------------------------------------------------------------------------
# Test: Image tag registration (Req 3.2)
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestImageTagRegistration:
    """The spike should register the correct image tag in its result."""

    @patch("spikes.meilisearch.spike_meilisearch.subprocess.run")
    def test_image_tag_registered_even_on_blocked(self, mock_subprocess, tmp_path):
        """Req 3.2: Image tag is registered even when Docker is unavailable."""
        mock_subprocess.side_effect = _mock_subprocess_docker_not_available

        result = run_meilisearch_spike(artifacts_dir=tmp_path)

        assert "getmeili/meilisearch" in result.image_tag
        assert "v1.6.2" in result.image_tag
