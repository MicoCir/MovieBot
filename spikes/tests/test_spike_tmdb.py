"""Unit tests for the TMDB viability spike.

Validates: Requirements 1.1, 1.2, 1.3, 1.4, 1.5
"""

import json
from pathlib import Path

import httpx
import pytest
import respx

from spikes.common.models import ViabilityStatus
from spikes.tmdb.spike_tmdb import ARTIFACTS_DIR, run_spike


# Sample TMDB-like response payload for mocking
MOCK_TMDB_RESPONSE = {
    "page": 1,
    "results": [
        {
            "id": 123456,
            "title": "Test Movie",
            "original_title": "Test Movie Original",
            "overview": "A movie about testing.",
            "release_date": "2024-01-15",
            "genre_ids": [28, 12],
            "popularity": 150.5,
            "vote_average": 7.8,
            "vote_count": 1200,
            "poster_path": "/test_poster.jpg",
            "backdrop_path": "/test_backdrop.jpg",
            "adult": False,
            "original_language": "en",
            "media_type": "movie",
            "video": False,
        }
    ],
    "total_pages": 10,
    "total_results": 200,
}

TMDB_TRENDING_URL = "https://api.themoviedb.org/3/trending/movie/day"


@pytest.fixture
def artifacts_dir(tmp_path, monkeypatch):
    """Redirect ARTIFACTS_DIR to a temporary directory."""
    monkeypatch.setattr("spikes.tmdb.spike_tmdb.ARTIFACTS_DIR", tmp_path)
    return tmp_path


@pytest.fixture
def mock_api_key(monkeypatch):
    """Provide a fake API key via environment variable."""
    monkeypatch.setenv("TMDB_API_KEY", "fake-test-api-key-12345")


@pytest.mark.unit
class TestTmdbSpikeSuccess:
    """Tests for successful TMDB spike execution (Req 1.1, 1.2, 1.3, 1.4)."""

    @respx.mock
    def test_success_returns_confirmed_status(self, artifacts_dir, mock_api_key):
        """Req 1.1: Spike sends request to authorized endpoint and succeeds."""
        respx.get(TMDB_TRENDING_URL).mock(
            return_value=httpx.Response(200, json=MOCK_TMDB_RESPONSE)
        )

        result = run_spike(time_window="day", timeout=5.0)

        assert result.status == ViabilityStatus.CONFIRMED
        assert result.response_code == 200
        assert result.endpoint_used == TMDB_TRENDING_URL
        assert result.errors == []

    @respx.mock
    def test_success_creates_snapshot_file(self, artifacts_dir, mock_api_key):
        """Req 1.2: Stores payload as sanitized snapshot JSON on success."""
        respx.get(TMDB_TRENDING_URL).mock(
            return_value=httpx.Response(200, json=MOCK_TMDB_RESPONSE)
        )

        result = run_spike(time_window="day", timeout=5.0)

        snapshot_path = artifacts_dir / "tmdb_snapshot.json"
        assert snapshot_path.exists()
        assert result.snapshot_path == str(snapshot_path)

        # Verify it's valid JSON
        content = json.loads(snapshot_path.read_text(encoding="utf-8"))
        assert "results" in content
        assert content["page"] == 1

    @respx.mock
    def test_success_snapshot_is_sanitized(self, artifacts_dir, mock_api_key):
        """Req 1.3: Removes all credentials before persisting."""
        # Inject sensitive keys into the response payload
        payload_with_secrets = {
            **MOCK_TMDB_RESPONSE,
            "api_key": "should-be-removed",
            "authorization": "Bearer secret-token",
            "token": "another-secret",
        }

        respx.get(TMDB_TRENDING_URL).mock(
            return_value=httpx.Response(200, json=payload_with_secrets)
        )

        run_spike(time_window="day", timeout=5.0)

        snapshot_path = artifacts_dir / "tmdb_snapshot.json"
        content = snapshot_path.read_text(encoding="utf-8")

        # Sensitive keys must be removed
        assert "should-be-removed" not in content
        assert "secret-token" not in content
        assert "another-secret" not in content
        assert '"api_key"' not in content
        assert '"authorization"' not in content
        assert '"token"' not in content

    @respx.mock
    def test_success_creates_field_inventory(self, artifacts_dir, mock_api_key):
        """Req 1.4: Generates field inventory with name, type, example."""
        respx.get(TMDB_TRENDING_URL).mock(
            return_value=httpx.Response(200, json=MOCK_TMDB_RESPONSE)
        )

        result = run_spike(time_window="day", timeout=5.0)

        inventory_path = artifacts_dir / "tmdb_field_inventory.json"
        assert inventory_path.exists()
        assert result.field_count > 0

        inventory = json.loads(inventory_path.read_text(encoding="utf-8"))
        assert len(inventory) > 0

        # Each entry should have required fields
        for entry in inventory:
            assert "name" in entry
            assert "observed_type" in entry
            assert "example_value" in entry
            assert "path" in entry

    @respx.mock
    def test_success_field_inventory_contains_expected_fields(
        self, artifacts_dir, mock_api_key
    ):
        """Req 1.4: Field inventory contains expected fields from payload."""
        respx.get(TMDB_TRENDING_URL).mock(
            return_value=httpx.Response(200, json=MOCK_TMDB_RESPONSE)
        )

        run_spike(time_window="day", timeout=5.0)

        inventory_path = artifacts_dir / "tmdb_field_inventory.json"
        inventory = json.loads(inventory_path.read_text(encoding="utf-8"))

        # Collect all field paths from inventory
        paths = {entry["path"] for entry in inventory}

        # Top-level fields
        assert "page" in paths
        assert "results" in paths
        assert "total_pages" in paths
        assert "total_results" in paths

        # Nested fields inside results[0]
        assert "results[0].id" in paths
        assert "results[0].title" in paths
        assert "results[0].popularity" in paths

    @respx.mock
    def test_success_artifacts_produced_list(self, artifacts_dir, mock_api_key):
        """Req 1.2, 1.4: Artifacts list includes snapshot and inventory paths."""
        respx.get(TMDB_TRENDING_URL).mock(
            return_value=httpx.Response(200, json=MOCK_TMDB_RESPONSE)
        )

        result = run_spike(time_window="day", timeout=5.0)

        assert len(result.artifacts_produced) == 2
        artifact_names = [Path(p).name for p in result.artifacts_produced]
        assert "tmdb_snapshot.json" in artifact_names
        assert "tmdb_field_inventory.json" in artifact_names


@pytest.mark.unit
class TestTmdbSpikeAuthError:
    """Tests for authentication error handling (Req 1.5)."""

    @respx.mock
    def test_401_returns_blocked_status(self, artifacts_dir, mock_api_key):
        """Req 1.5: Auth error registers code, message, URL and documents blocking."""
        respx.get(TMDB_TRENDING_URL).mock(
            return_value=httpx.Response(
                401, text='{"status_message": "Invalid API key"}'
            )
        )

        result = run_spike(time_window="day", timeout=5.0)

        assert result.status == ViabilityStatus.BLOCKED
        assert result.response_code == 401
        assert result.endpoint_used == TMDB_TRENDING_URL
        assert len(result.errors) > 0

    @respx.mock
    def test_401_creates_blocked_fixture(self, artifacts_dir, mock_api_key):
        """Req 1.5: Blocked fixture is created on auth error."""
        respx.get(TMDB_TRENDING_URL).mock(
            return_value=httpx.Response(
                401, text='{"status_message": "Invalid API key"}'
            )
        )

        result = run_spike(time_window="day", timeout=5.0)

        fixture_path = artifacts_dir / "tmdb_blocked_fixture.json"
        assert fixture_path.exists()

        fixture = json.loads(fixture_path.read_text())
        assert fixture["blocked"] is True
        assert fixture["response_code"] == 401
        assert fixture["endpoint"] == TMDB_TRENDING_URL
        assert "error_message" in fixture

        # Artifact is tracked
        assert len(result.artifacts_produced) > 0

    @respx.mock
    def test_403_returns_blocked_status(self, artifacts_dir, mock_api_key):
        """Req 1.5: Forbidden also results in blocked status."""
        respx.get(TMDB_TRENDING_URL).mock(
            return_value=httpx.Response(403, text="Forbidden")
        )

        result = run_spike(time_window="day", timeout=5.0)

        assert result.status == ViabilityStatus.BLOCKED
        assert result.response_code == 403


@pytest.mark.unit
class TestTmdbSpikeRateLimit:
    """Tests for rate limit (429) handling (Req 1.5)."""

    @respx.mock
    def test_429_persistent_returns_blocked(self, artifacts_dir, mock_api_key, monkeypatch):
        """Req 1.5: Persistent rate limit results in blocked status after retries."""
        # Reduce backoff to speed up tests
        monkeypatch.setattr("spikes.tmdb.spike_tmdb.BACKOFF_BASE", 0.01)

        respx.get(TMDB_TRENDING_URL).mock(
            return_value=httpx.Response(429, text="Rate limit exceeded")
        )

        result = run_spike(time_window="day", timeout=5.0)

        assert result.status == ViabilityStatus.BLOCKED
        assert result.response_code == 429
        assert len(result.errors) > 0

    @respx.mock
    def test_429_creates_blocked_fixture(self, artifacts_dir, mock_api_key, monkeypatch):
        """Req 1.5: Blocked fixture is created on persistent rate limit."""
        monkeypatch.setattr("spikes.tmdb.spike_tmdb.BACKOFF_BASE", 0.01)

        respx.get(TMDB_TRENDING_URL).mock(
            return_value=httpx.Response(429, text="Rate limit exceeded")
        )

        run_spike(time_window="day", timeout=5.0)

        fixture_path = artifacts_dir / "tmdb_blocked_fixture.json"
        assert fixture_path.exists()

        fixture = json.loads(fixture_path.read_text())
        assert fixture["blocked"] is True
        assert fixture["response_code"] == 429


@pytest.mark.unit
class TestTmdbSpikeTimeout:
    """Tests for timeout handling (Req 1.5)."""

    @respx.mock
    def test_timeout_returns_blocked(self, artifacts_dir, mock_api_key):
        """Req 1.5: Timeout registers error and documents blocking."""
        respx.get(TMDB_TRENDING_URL).mock(
            side_effect=httpx.ConnectTimeout("Connection timed out")
        )

        result = run_spike(time_window="day", timeout=1.0)

        assert result.status == ViabilityStatus.BLOCKED
        assert result.response_code is None
        assert result.endpoint_used == TMDB_TRENDING_URL
        assert len(result.errors) > 0
        assert "timed out" in result.errors[0].lower() or "timeout" in result.errors[0].lower()

    @respx.mock
    def test_timeout_creates_blocked_fixture(self, artifacts_dir, mock_api_key):
        """Req 1.5: Blocked fixture is created on timeout."""
        respx.get(TMDB_TRENDING_URL).mock(
            side_effect=httpx.ConnectTimeout("Connection timed out")
        )

        run_spike(time_window="day", timeout=1.0)

        fixture_path = artifacts_dir / "tmdb_blocked_fixture.json"
        assert fixture_path.exists()

        fixture = json.loads(fixture_path.read_text())
        assert fixture["blocked"] is True
        assert fixture["response_code"] is None


@pytest.mark.unit
class TestTmdbSpikeMissingCredentials:
    """Tests for missing credentials scenario."""

    def test_no_api_key_returns_blocked(self, artifacts_dir, monkeypatch):
        """Spike blocks when no API key is available."""
        monkeypatch.delenv("TMDB_API_KEY", raising=False)
        monkeypatch.delenv("TMDB_BEARER_TOKEN", raising=False)

        result = run_spike(time_window="day", timeout=5.0)

        assert result.status == ViabilityStatus.BLOCKED
        assert result.response_code is None
        assert "TMDB" in result.errors[0]
